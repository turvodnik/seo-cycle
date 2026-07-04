#!/usr/bin/env python3
"""Visual site-structure map: a collapsible URL tree with page counts and flags.

Sources, first available wins (or force one with --source):
  crawl    seo/crawl/site-crawl.json      — статусы, глубина, noindex
  mirror   seo/content-mirror/records     — зеркало CMS-контента
  sitemap  --sitemap-file <path.xml>      — обычный XML sitemap

Output: seo/crawl/structure-map.html (self-contained, offline) + .md summary
with --write; markdown tree to stdout otherwise.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for, write_text
from seo_cycle_core.html_report import html_page
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("structure-map")


def urls_from_crawl(project_root: pathlib.Path) -> list[dict[str, Any]]:
    path = project_root / "seo" / "crawl" / "site-crawl.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    pages = (report.get("crawl") or {}).get("pages") or []
    return [{"url": p["url"], "status": p.get("status"), "noindex": p.get("noindex"),
             "title": p.get("title", "")} for p in pages if p.get("url")]


def urls_from_mirror(project_root: pathlib.Path) -> list[dict[str, Any]]:
    records_dir = project_root / "seo" / "content-mirror" / "records"
    out = []
    for path in sorted(records_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        url = record.get("url") or record.get("link")
        if url:
            out.append({"url": url, "status": 200, "noindex": False,
                        "title": record.get("title", "")})
    return out


def urls_from_sitemap(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [{"url": loc, "status": None, "noindex": False, "title": ""}
            for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)]


def build_tree(urls: list[dict[str, Any]]) -> dict[str, Any]:
    root: dict[str, Any] = {"name": "/", "children": {}, "pages": []}
    for item in urls:
        parsed = urllib.parse.urlparse(item["url"])
        segments = [s for s in parsed.path.split("/") if s]
        node = root
        for segment in segments[:-1] if segments else []:
            node = node["children"].setdefault(segment, {"name": segment, "children": {}, "pages": []})
        leaf = segments[-1] if segments else ""
        target = node["children"].setdefault(leaf, {"name": leaf or "/", "children": {}, "pages": []}) \
            if leaf else node
        target["pages"].append(item)
    return root


def count_pages(node: dict[str, Any]) -> int:
    return len(node["pages"]) + sum(count_pages(child) for child in node["children"].values())


def tree_markdown(node: dict[str, Any], depth: int = 0) -> list[str]:
    lines = []
    for name, child in sorted(node["children"].items()):
        total = count_pages(child)
        flags = ""
        bad = sum(1 for p in child["pages"] if p.get("status") and p["status"] >= 400)
        noindex = sum(1 for p in child["pages"] if p.get("noindex"))
        if bad:
            flags += f" ⛔{bad}"
        if noindex:
            flags += f" 🚫{noindex}"
        lines.append(f"{'  ' * depth}- /{name} ({total}){flags}")
        if depth < 4:
            lines.extend(tree_markdown(child, depth + 1))
    return lines


def tree_html(node: dict[str, Any], depth: int = 0) -> str:
    parts = []
    for name, child in sorted(node["children"].items()):
        total = count_pages(child)
        bad = sum(1 for p in child["pages"] if p.get("status") and p["status"] >= 400)
        noindex = sum(1 for p in child["pages"] if p.get("noindex"))
        badges = (f" <span class='bad'>⛔ {bad}</span>" if bad else "") + \
                 (f" <span class='mut'>noindex {noindex}</span>" if noindex else "")
        inner = tree_html(child, depth + 1)
        pages = "".join(
            f"<div class='page'><span class='{'bad' if (p.get('status') or 0) >= 400 else 'ok'}'>"
            f"{p.get('status') or '·'}</span> <a href='{html.escape(p['url'])}' target='_blank'>"
            f"{html.escape(urllib.parse.urlparse(p['url']).path or '/')}</a> "
            f"<span class='mut'>{html.escape((p.get('title') or '')[:80])}</span></div>"
            for p in child["pages"][:50]
        )
        open_attr = " open" if depth < 1 else ""
        parts.append(
            f"<details{open_attr}><summary><b>/{html.escape(name)}</b> "
            f"<span class='mut'>{total} стр.</span>{badges}</summary>"
            f"<div class='indent'>{pages}{inner}</div></details>"
        )
    return "".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=("crawl", "mirror", "sitemap"))
    parser.add_argument("--sitemap-file", help="Path to sitemap.xml (source=sitemap)")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    cfg_path = find_config(pathlib.Path.cwd())
    project_root = project_root_for(cfg_path) if cfg_path else pathlib.Path.cwd()
    global log
    log = setup_logging("structure-map", project_root, load_yaml(cfg_path) if cfg_path else {})

    urls: list[dict[str, Any]] = []
    source = args.source
    if source in (None, "crawl"):
        urls = urls_from_crawl(project_root)
        source = "crawl" if urls else source
    if not urls and source in (None, "mirror"):
        urls = urls_from_mirror(project_root)
        source = "mirror" if urls else source
    if not urls and (source == "sitemap" or args.sitemap_file):
        urls = urls_from_sitemap(pathlib.Path(args.sitemap_file or "sitemap.xml"))
        source = "sitemap"
    if not urls:
        print("Нет данных: запустите site-crawl.py --live, seo-cycle sync, "
              "или передайте --sitemap-file sitemap.xml", file=sys.stderr)
        return 0

    tree = build_tree(urls)
    summary = [f"# Карта структуры ({source}, {len(urls)} URL)", ""]
    summary.extend(tree_markdown(tree))
    markdown = "\n".join(summary) + "\n"

    if args.write:
        body = (f"<h1>Структура сайта</h1><p class='mut'>источник: {source} · {len(urls)} URL</p>"
                + tree_html(tree))
        extra_css = (".indent{margin-left:1.2rem}.page{font-size:.9rem;margin:.15rem 0}"
                     ".mut{color:#8b93a3;font-size:.85em}.bad{color:#e05f5f}.ok{color:#3ecf8e}"
                     "details{margin:.3rem 0}summary{cursor:pointer}")
        out_dir = project_root / "seo" / "crawl"
        write_text(out_dir / "structure-map.html", html_page("Структура сайта", body, extra_css=extra_css))
        write_text(out_dir / "structure-map.md", markdown)
        print(f"✓ {out_dir}/structure-map.html", file=sys.stderr)
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
