#!/usr/bin/env python3
"""Own lightweight site crawler (stdlib-only): BFS over one host with findings.

Fills the gap between point checks (lighthouse, link-audit on exports) and a
GUI crawler: walks the site politely (robots.txt honored, delay between hits,
hard page cap), collects per-page SEO essentials, and emits findings:

  broken internal links (4xx/5xx), redirect chains, duplicate/missing titles,
  missing h1/meta description, noindex on linked pages, canonical pointing
  elsewhere, pages deeper than --max-depth.

Network is opt-in: pass --live to crawl, or --input-file <crawl.json> to
re-run findings offline over a previous crawl. Output:
seo/crawl/site-crawl.{json,md} with --write.

Usage:
  python3 scripts/site-crawl.py --live [--start https://site.ru/] [--max-pages 300]
  python3 scripts/site-crawl.py --input-file seo/crawl/site-crawl.json --write
"""

from __future__ import annotations

import argparse
import collections
import html.parser
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("site-crawl")

USER_AGENT = "seo-cycle-crawler/1.0 (+https://github.com/turvodnik/seo-cycle)"
SKIP_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip",
                   ".doc", ".docx", ".xls", ".xlsx", ".mp4", ".webm", ".avif", ".ico", ".css", ".js"}


class PageParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.h1: list[str] = []
        self.meta_description = ""
        self.canonical = ""
        self.noindex = False
        self.links: list[str] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: (value or "") for key, value in attrs}
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])
        elif tag == "meta":
            name = attributes.get("name", "").lower()
            if name == "description":
                self.meta_description = attributes.get("content", "")
            elif name == "robots" and "noindex" in attributes.get("content", "").lower():
                self.noindex = True
        elif tag == "link" and attributes.get("rel", "").lower() == "canonical":
            self.canonical = attributes.get("href", "")
        if tag in ("title", "h1"):
            self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        if self._stack[-1] == "title":
            self.title += data
        elif self._stack[-1] == "h1":
            if self.h1:
                self.h1[-1] += data
            else:
                self.h1.append(data)


def normalize_link(base: str, href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    absolute = urllib.parse.urljoin(base, href)
    absolute, _ = urllib.parse.urldefrag(absolute)
    parsed = urllib.parse.urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return None
    if pathlib.PurePosixPath(parsed.path).suffix.lower() in SKIP_EXTENSIONS:
        return None
    return absolute


def fetch(url: str, timeout: int) -> tuple[int, str, str]:
    """Return (status, final_url, body). Redirects are followed by urllib."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(1_500_000).decode("utf-8", errors="replace") \
                if "html" in content_type else ""
            return response.status, response.geturl(), body
    except urllib.error.HTTPError as err:
        return err.code, url, ""
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        log.info("fetch failed %s: %s", url, err)
        return 0, url, ""


def crawl(start: str, *, max_pages: int, max_depth: int, delay: float, timeout: int) -> dict[str, Any]:
    host = urllib.parse.urlparse(start).netloc
    robots = urllib.robotparser.RobotFileParser()
    robots.set_url(f"{urllib.parse.urlparse(start).scheme}://{host}/robots.txt")
    try:
        robots.read()
    except OSError:
        pass

    queue: collections.deque[tuple[str, int]] = collections.deque([(start, 0)])
    seen: set[str] = {start}
    pages: list[dict[str, Any]] = []
    edges = 0
    while queue and len(pages) < max_pages:
        url, depth = queue.popleft()
        if not robots.can_fetch(USER_AGENT, url):
            pages.append({"url": url, "status": -1, "depth": depth, "note": "blocked_by_robots"})
            continue
        status, final_url, body = fetch(url, timeout)
        parser = PageParser()
        if body:
            try:
                parser.feed(body)
            except Exception:  # noqa: BLE001 - malformed html must not kill the crawl
                pass
        internal: list[str] = []
        for href in parser.links:
            link = normalize_link(final_url, href)
            if not link:
                continue
            if urllib.parse.urlparse(link).netloc == host:
                internal.append(link)
                if link not in seen and depth + 1 <= max_depth and len(seen) < max_pages * 3:
                    seen.add(link)
                    queue.append((link, depth + 1))
        edges += len(internal)
        pages.append({
            "url": url,
            "final_url": final_url,
            "status": status,
            "redirected": final_url != url,
            "depth": depth,
            "title": parser.title.strip(),
            "h1_count": len([h for h in parser.h1 if h.strip()]),
            "meta_description": bool(parser.meta_description.strip()),
            "canonical": parser.canonical.strip(),
            "noindex": parser.noindex,
            "internal_links": len(internal),
            "internal_targets": sorted(set(internal))[:200],
        })
        if delay:
            time.sleep(delay)
    return {"start": start, "host": host, "pages": pages, "edges": edges,
            "truncated": bool(queue), "crawled": len(pages)}


def build_findings(data: dict[str, Any], max_depth: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    pages = [p for p in data.get("pages", []) if "url" in p]
    statuses = {p["url"]: p.get("status", 0) for p in pages}

    def add(severity: str, finding_id: str, title: str, urls: list[str]) -> None:
        if urls:
            findings.append({"severity": severity, "id": finding_id, "title": title,
                             "count": len(urls), "urls": sorted(urls)[:15]})

    add("critical", "broken_internal", "Внутренние ссылки на 4xx/5xx",
        [p["url"] for p in pages if 400 <= (p.get("status") or 0) < 600])
    add("error", "unreachable", "Страницы недоступны (сеть/таймаут)",
        [p["url"] for p in pages if p.get("status") == 0])
    add("warning", "redirected_links", "Внутренние ссылки через редирект",
        [p["url"] for p in pages if p.get("redirected")])
    titles: dict[str, list[str]] = collections.defaultdict(list)
    for p in pages:
        if p.get("status") == 200 and p.get("title"):
            titles[p["title"]].append(p["url"])
    add("warning", "duplicate_title", "Дубли title",
        [url for urls in titles.values() if len(urls) > 1 for url in urls])
    add("warning", "missing_title", "Нет title",
        [p["url"] for p in pages if p.get("status") == 200 and not p.get("title")])
    add("warning", "missing_h1", "Нет H1",
        [p["url"] for p in pages if p.get("status") == 200 and p.get("h1_count") == 0])
    add("info", "multiple_h1", "Несколько H1",
        [p["url"] for p in pages if (p.get("h1_count") or 0) > 1])
    add("warning", "missing_description", "Нет meta description",
        [p["url"] for p in pages if p.get("status") == 200 and not p.get("meta_description")])
    add("warning", "noindex_linked", "noindex на страницах, на которые есть ссылки",
        [p["url"] for p in pages if p.get("noindex")])
    add("info", "canonical_elsewhere", "canonical указывает на другой URL",
        [p["url"] for p in pages
         if p.get("canonical") and urllib.parse.urldefrag(p["canonical"])[0].rstrip("/")
         not in {p["url"].rstrip("/"), p.get("final_url", "").rstrip("/")}])
    add("info", "too_deep", f"Глубже {max_depth - 1} кликов от старта",
        [p["url"] for p in pages if (p.get("depth") or 0) >= max_depth])
    # ссылки, ведущие на несуществующие страницы, которых мы коснулись
    dead_targets = [url for url, status in statuses.items() if 400 <= status < 600]
    sources = [p["url"] for p in pages
               if any(t in dead_targets for t in p.get("internal_targets", []))]
    add("error", "links_to_broken", "Страницы, ссылающиеся на битые URL", sources)
    order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    findings.sort(key=lambda f: order.get(f["severity"], 9))
    return findings


def render_markdown(report: dict[str, Any]) -> str:
    data = report["crawl"]
    lines = [f"# Site crawl — {data.get('host', '?')}", "",
             f"- Обойдено страниц: {data.get('crawled')} (cap {'достигнут' if data.get('truncated') else 'не достигнут'})"
             f" · внутренних ссылок: {data.get('edges')}",
             f"- Findings: {len(report['findings'])}", ""]
    for finding in report["findings"]:
        lines.append(f"## [{finding['severity']}] {finding['title']} — {finding['count']}")
        lines.extend(f"- {url}" for url in finding["urls"])
        lines.append("")
    if not report["findings"]:
        lines.append("Критичных проблем обхода не найдено ✅")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--start", help="Start URL (default: project.domain from config)")
    parser.add_argument("--live", action="store_true", help="Actually crawl the network")
    parser.add_argument("--input-file", help="Reuse a previous site-crawl.json (offline findings)")
    parser.add_argument("--max-pages", type=int, default=300)
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--delay", type=float, default=0.3, help="Seconds between requests")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    cfg_path = find_config(pathlib.Path.cwd())
    project_root = project_root_for(cfg_path) if cfg_path else pathlib.Path.cwd()
    cfg = load_yaml(cfg_path) if cfg_path else {}
    global log
    log = setup_logging("site-crawl", project_root, cfg)

    if args.input_file:
        try:
            previous = json.loads(pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8"))
            data = previous.get("crawl", previous)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read {args.input_file}: {exc}", file=sys.stderr)
            return 2
    elif args.live:
        start = args.start
        if not start:
            domain = nested_get(cfg, "project.domain", "") or ""
            if not domain:
                print("ERROR: pass --start https://site.ru/ (project.domain отсутствует в конфиге)",
                      file=sys.stderr)
                return 2
            start = domain if re.match(r"^https?://", domain) else f"https://{domain}/"
        log.info("crawl start %s max_pages=%s", start, args.max_pages)
        data = crawl(start, max_pages=args.max_pages, max_depth=args.max_depth,
                     delay=args.delay, timeout=args.timeout)
    else:
        print("Сеть выключена по умолчанию: добавьте --live для обхода "
              "или --input-file <site-crawl.json> для offline-анализа.", file=sys.stderr)
        return 0

    report = {"audit_id": "site_crawl", "crawl": data,
              "findings": build_findings(data, args.max_depth)}
    markdown = render_markdown(report)
    if args.write:
        out_dir = project_root / "seo" / "crawl"
        write_text(out_dir / "site-crawl.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        write_text(out_dir / "site-crawl.md", markdown)
        print(f"✓ {out_dir}/site-crawl.md", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else markdown,
          end="" if args.format == "md" else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
