#!/usr/bin/env python3
"""Build a prioritized Google indexing request queue from GSC exports, sitemap, WooCommerce and metrics.

This script does not request indexing. It creates a bounded P0/P1 queue and
blocks junk/technical-risk URLs before any manual Search Console submission.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, rel_display, rel_path
from seo_cycle_core.technical_artifacts import write_technical_report


DEFAULT_UA = "Mozilla/5.0 (compatible; PifagorSEO-GSCIndexingQueue/1.0; +https://pifagor.ai)"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
NOINDEX_RE = re.compile(r"<meta[^>]+name=[\"']robots[\"'][^>]+content=[\"'][^\"']*noindex|x-robots-tag[^\\n\\r]*noindex", re.I)
CANONICAL_RE = re.compile(r"<link[^>]+rel=[\"']canonical[\"'][^>]+href=[\"']([^\"']+)[\"']", re.I)
DISCOVERED_MARKERS = (
    "discovered",
    "currently not indexed",
    "обнаружена",
    "не проиндексирована",
)
JUNK_PATTERNS = (
    r"/wp-json/",
    r"/wp-admin/",
    r"/cart/?$",
    r"/checkout/?$",
    r"/my-account",
    r"/wishlist",
    r"/feed/?$",
    r"/comments/feed",
    r"/page/\d+/?$",
    r"/template/",
    r"/search/",
)
JUNK_QUERY_KEYS = {
    "add-to-cart",
    "bricks",
    "bricks_preview",
    "preview",
    "preview_id",
    "preview_nonce",
    "s",
    "feed",
    "replytocom",
}


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urllib.parse.urlunsplit((scheme, netloc, path, parsed.query, ""))


def canonical_key(url: str) -> str:
    parsed = urllib.parse.urlsplit(normalize_url(url))
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def url_from_row(row: dict[str, Any]) -> str:
    for key in ("url", "URL", "page", "Page", "landing_page", "permalink", "link", "loc"):
        value = row.get(key)
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            return value.strip()
    text = " ".join(str(value) for value in row.values() if value is not None)
    match = URL_RE.search(text)
    return match.group(0).strip() if match else ""


def numeric(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def load_json_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            return [item for item in data["rows"] if isinstance(item, dict)]
        if isinstance(data.get("data"), list):
            return [item for item in data["data"] if isinstance(item, dict)]
    return []


def load_xlsx_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        import openpyxl  # type: ignore
    except ImportError:
        return []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(cell or "").strip() for cell in rows[0]]
    out: list[dict[str, Any]] = []
    for raw in rows[1:]:
        out.append({headers[idx] if idx < len(headers) else f"col_{idx}": value for idx, value in enumerate(raw)})
    return out


def load_table(path: pathlib.Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_json_rows(path)
    if suffix in {".xlsx", ".xlsm"}:
        return load_xlsx_rows(path)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [dict(row) for row in csv.DictReader(io.StringIO(text), dialect=dialect)]


def gsc_page_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for row in rows:
        url = url_from_row(row)
        keys = row.get("keys") if isinstance(row.get("keys"), list) else []
        if not url:
            for item in keys:
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    url = item
                    break
        if not url:
            continue
        key = canonical_key(url)
        current = metrics.setdefault(key, {"clicks": 0.0, "impressions": 0.0, "position": 0.0, "rows": 0.0})
        current["clicks"] += numeric(row.get("clicks") or row.get("Clicks") or row.get("Клики"))
        current["impressions"] += numeric(row.get("impressions") or row.get("Impressions") or row.get("Показы"))
        position = numeric(row.get("position") or row.get("Position") or row.get("Позиция"))
        if position:
            current["position"] += position
            current["rows"] += 1
    for item in metrics.values():
        if item["rows"]:
            item["position"] = round(item["position"] / item["rows"], 2)
    return metrics


def fetch_url(url: str, user_agent: str, timeout: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        if response.headers.get("Content-Encoding") == "gzip" or url.endswith(".gz"):
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
        return data


def parse_sitemap(content: bytes, source: str, user_agent: str, timeout: int, depth: int = 0) -> list[str]:
    if depth > 3:
        return []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    tag = root.tag.split("}")[-1]
    urls: list[str] = []
    if tag == "sitemapindex":
        for loc in root.findall("sm:sitemap/sm:loc", SITEMAP_NS):
            if loc.text:
                child_url = loc.text.strip()
                try:
                    urls.extend(parse_sitemap(fetch_url(child_url, user_agent, timeout), child_url, user_agent, timeout, depth + 1))
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                    continue
    elif tag == "urlset":
        for loc in root.findall("sm:url/sm:loc", SITEMAP_NS):
            if loc.text:
                urls.append(loc.text.strip())
    return urls


def load_sitemap(args: argparse.Namespace, cfg: dict[str, Any], project_root: pathlib.Path) -> list[str]:
    sources: list[tuple[str, bytes]] = []
    for path in args.sitemap_file or []:
        item = rel_path(project_root, path)
        if item.exists():
            sources.append((str(item), item.read_bytes()))
    sitemap_urls = list(args.sitemap or [])
    if not sources and not sitemap_urls:
        domain = nested_get(cfg, "project.domain") or ""
        if domain:
            sitemap_urls = [f"https://{domain}/sitemaps.xml", f"https://{domain}/sitemap.xml"]
    for url in sitemap_urls:
        try:
            sources.append((url, fetch_url(url, args.user_agent, args.timeout)))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue
    urls: list[str] = []
    for source, content in sources:
        urls.extend(parse_sitemap(content, source, args.user_agent, args.timeout))
    return sorted(set(urls), key=urls.index)


def row_text(row: dict[str, Any]) -> str:
    return " ".join(str(value).lower() for value in row.values() if value is not None)


def discovered_rows(paths: list[str] | None, project_root: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_path in paths or []:
        path = rel_path(project_root, raw_path)
        if not path.exists():
            continue
        for row in load_table(path):
            url = url_from_row(row)
            if not url:
                continue
            text = row_text(row)
            status = "discovered_not_indexed" if any(marker in text for marker in DISCOVERED_MARKERS) else "provided_discovered_export"
            rows.append({**row, "url": url, "gsc_issue_status": status, "source_file": str(path)})
    return rows


def load_url_file(paths: list[str] | None, project_root: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_path in paths or []:
        path = rel_path(project_root, raw_path)
        if not path.exists():
            continue
        if path.suffix.lower() in {".csv", ".tsv", ".json", ".xlsx", ".xlsm"}:
            for row in load_table(path):
                url = url_from_row(row)
                if url:
                    rows.append({**row, "url": url, "gsc_issue_status": "manual_url_file", "source_file": str(path)})
        else:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                match = URL_RE.search(line)
                if match:
                    rows.append({"url": match.group(0), "gsc_issue_status": "manual_url_file", "source_file": str(path)})
    return rows


def load_woocommerce(paths: list[str] | None, project_root: pathlib.Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw_path in paths or []:
        path = rel_path(project_root, raw_path)
        if not path.exists():
            continue
        for row in load_table(path):
            url = url_from_row(row)
            if not url:
                continue
            key = canonical_key(url)
            raw_type = str(row.get("type") or row.get("Type") or row.get("post_type") or row.get("taxonomy") or "").lower()
            if "cat" in raw_type or "category" in raw_type or "product_cat" in raw_type:
                page_type = "woocommerce_category"
            elif "product" in raw_type or "/shop/" in urllib.parse.urlsplit(url).path:
                page_type = "woocommerce_product"
            else:
                page_type = "woocommerce"
            out[key] = {"type": page_type, "row": row, "source_file": str(path)}
    return out


def infer_page_type(url: str, woo: dict[str, Any] | None) -> str:
    if woo and woo.get("type"):
        return str(woo["type"])
    path = urllib.parse.urlsplit(url).path.lower()
    if "/shop/" in path:
        return "woocommerce_product"
    if "/product-category/" in path or path.count("/") <= 2 and any(token in path for token in ("material", "fanera", "uteplitel", "izolyac")):
        return "category"
    if "/blog/" in path:
        return "blog"
    if "/brand/" in path:
        return "brand"
    return "page"


def junk_reason(url: str, custom_patterns: list[str]) -> str:
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path.lower()
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid_url"
    for key in query:
        if key.lower() in JUNK_QUERY_KEYS:
            return f"blocked_query:{key}"
    for pattern in list(JUNK_PATTERNS) + custom_patterns:
        if re.search(pattern, path, re.I):
            return f"blocked_pattern:{pattern}"
    return ""


def technical_probe(url: str, user_agent: str, timeout: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unchecked",
        "http_status": None,
        "final_url": url,
        "canonical": "",
        "indexable": False,
        "blockers": [],
    }
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(180000).decode("utf-8", errors="replace")
            result["http_status"] = response.status
            result["final_url"] = response.geturl()
            x_robots = response.headers.get("X-Robots-Tag", "")
            canonical_match = CANONICAL_RE.search(body)
            if canonical_match:
                result["canonical"] = urllib.parse.urljoin(result["final_url"], canonical_match.group(1).strip())
            blockers: list[str] = []
            if not (200 <= response.status < 300):
                blockers.append(f"http_{response.status}")
            if canonical_key(str(result["final_url"])) != canonical_key(url):
                blockers.append("redirect_or_final_url_mismatch")
            if "noindex" in x_robots.lower() or NOINDEX_RE.search(body):
                blockers.append("noindex")
            if result["canonical"] and canonical_key(str(result["canonical"])) != canonical_key(url):
                blockers.append("canonical_to_other_url")
            result["blockers"] = blockers
            result["indexable"] = not blockers
            result["status"] = "indexable" if result["indexable"] else "blocked"
    except urllib.error.HTTPError as exc:
        result.update({"status": "blocked", "http_status": exc.code, "blockers": [f"http_{exc.code}"]})
    except Exception as exc:  # noqa: BLE001 - surfaced in report, not swallowed
        result.update({"status": "error", "blockers": ["probe_error"], "error": str(exc)[:300]})
    return result


def score_candidate(candidate: dict[str, Any]) -> tuple[int, str]:
    if candidate.get("exclude_reason"):
        return 0, "excluded"
    tech = candidate.get("technical") or {}
    if tech.get("status") in {"blocked", "error"}:
        return 0, "technical_blocked"
    score = 10
    if candidate.get("in_sitemap"):
        score += 25
    if candidate.get("gsc_issue_status") == "discovered_not_indexed":
        score += 10
    page_type = str(candidate.get("page_type") or "")
    if page_type == "woocommerce_category":
        score += 35
    elif page_type == "category":
        score += 30
    elif page_type == "woocommerce_product":
        score += 25
    elif page_type == "brand":
        score += 15
    elif page_type == "blog":
        score += 12
    impressions = numeric(candidate.get("impressions"))
    clicks = numeric(candidate.get("clicks"))
    if impressions:
        score += min(30, round(math.log1p(impressions) * 5))
    if clicks:
        score += min(15, round(math.log1p(clicks) * 5))
    if tech.get("status") == "indexable":
        score += 20
    elif tech.get("status") == "unchecked":
        score += 5
    if not candidate.get("in_sitemap") and not impressions and page_type == "page":
        score -= 15
    if score >= 80:
        priority = "P0"
    elif score >= 55:
        priority = "P1"
    else:
        priority = "P2"
    return max(score, 0), priority


def build_candidates(cfg_path: pathlib.Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    sitemap_urls = load_sitemap(args, cfg, project_root)
    sitemap_keys = {canonical_key(url) for url in sitemap_urls}
    rows = discovered_rows(args.gsc_discovered_file, project_root) + load_url_file(args.url_file, project_root)
    woo = load_woocommerce(args.woocommerce_file, project_root)
    metrics: dict[str, dict[str, float]] = {}
    for raw_path in args.gsc_performance_file or []:
        path = rel_path(project_root, raw_path)
        if path.exists():
            metrics.update(gsc_page_metrics(load_table(path)))
    custom_patterns = args.exclude_pattern or []
    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        url = normalize_url(str(row["url"]))
        key = canonical_key(url)
        if key in deduped:
            continue
        woo_row = woo.get(key)
        metric = metrics.get(key, {})
        page_type = infer_page_type(url, woo_row)
        candidate = {
            "url": url,
            "key": key,
            "gsc_issue_status": row.get("gsc_issue_status"),
            "page_type": page_type,
            "in_sitemap": key in sitemap_keys,
            "in_woocommerce": bool(woo_row),
            "clicks": metric.get("clicks", 0),
            "impressions": metric.get("impressions", 0),
            "position": metric.get("position", 0),
            "source_file": row.get("source_file", ""),
            "exclude_reason": junk_reason(url, custom_patterns),
            "technical": {"status": "unchecked", "indexable": None, "blockers": []},
        }
        deduped[key] = candidate
    candidates = list(deduped.values())
    checkable = [item for item in candidates if not item["exclude_reason"]]
    if args.technical_check:
        for item in checkable[: args.check_limit]:
            item["technical"] = technical_probe(item["url"], args.user_agent, args.timeout)
    for item in candidates:
        score, priority = score_candidate(item)
        item["priority_score"] = score
        item["priority"] = priority
        if item["technical"].get("status") in {"blocked", "error"} and not item["exclude_reason"]:
            item["exclude_reason"] = "technical:" + ",".join(item["technical"].get("blockers") or [item["technical"].get("status")])
    eligible = [item for item in candidates if not item.get("exclude_reason") and item.get("priority_score", 0) > 0]
    eligible.sort(key=lambda item: (-int(item.get("priority_score", 0)), str(item.get("url"))))
    excluded = [item for item in candidates if item.get("exclude_reason")]
    summary = {
        "domain": nested_get(cfg, "project.domain") or "",
        "mode": "gsc_indexing_queue",
        "discovered_input_rows": len(rows),
        "sitemap_urls": len(sitemap_urls),
        "woocommerce_urls": len(woo),
        "metrics_urls": len(metrics),
        "candidates": len(candidates),
        "eligible": len(eligible),
        "excluded": len(excluded),
        "technical_checked": len([item for item in candidates if item.get("technical", {}).get("status") != "unchecked"]),
        "top_limit": args.top,
    }
    return summary, eligible, excluded


def write_queue_csv(project_root: pathlib.Path, queue: list[dict[str, Any]], write: bool) -> dict[str, str]:
    paths = {
        "queue_csv": project_root / "seo" / "technical" / "gsc-indexing-request-queue.csv",
        "latest_queue_csv": project_root / "seo" / "technical" / "latest-gsc-indexing-request-queue.csv",
    }
    if write:
        header = [
            "priority",
            "priority_score",
            "url",
            "page_type",
            "in_sitemap",
            "in_woocommerce",
            "impressions",
            "clicks",
            "position",
            "technical_status",
            "technical_blockers",
            "gsc_issue_status",
        ]
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=header)
                writer.writeheader()
                for item in queue:
                    tech = item.get("technical") or {}
                    writer.writerow(
                        {
                            "priority": item.get("priority"),
                            "priority_score": item.get("priority_score"),
                            "url": item.get("url"),
                            "page_type": item.get("page_type"),
                            "in_sitemap": item.get("in_sitemap"),
                            "in_woocommerce": item.get("in_woocommerce"),
                            "impressions": item.get("impressions"),
                            "clicks": item.get("clicks"),
                            "position": item.get("position"),
                            "technical_status": tech.get("status"),
                            "technical_blockers": ",".join(tech.get("blockers") or []),
                            "gsc_issue_status": item.get("gsc_issue_status"),
                        }
                    )
    return {key: rel_display(project_root, value) for key, value in paths.items()}


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    summary, eligible, excluded = build_candidates(cfg_path, args)
    queue = eligible[: args.top]
    csv_paths = write_queue_csv(project_root, queue, args.write)
    findings: list[dict[str, Any]] = []
    if not summary["discovered_input_rows"]:
        findings.append(
            {
                "id": "gsc_discovered_export_missing",
                "severity": "high",
                "message": "No GSC discovered/not-indexed export or URL file was provided.",
                "evidence": "Export Search Console Pages issue examples or pass --url-file.",
            }
        )
    if not queue and summary["discovered_input_rows"]:
        findings.append(
            {
                "id": "indexing_queue_empty",
                "severity": "medium",
                "message": "No eligible URLs after sitemap/WooCommerce/technical filtering.",
                "evidence": {"excluded": len(excluded)},
            }
        )
    if excluded:
        findings.append(
            {
                "id": "indexing_junk_or_blocked_urls_filtered",
                "severity": "info",
                "message": f"{len(excluded)} URLs were filtered before GSC submission.",
                "evidence": [{"url": item["url"], "reason": item.get("exclude_reason")} for item in excluded[:15]],
            }
        )
    distillate = {
        "summary": summary,
        "queue": queue,
        "excluded_sample": excluded[:25],
        "queue_csv": csv_paths.get("queue_csv"),
        "citations": [
            "https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl",
            "https://support.google.com/webmasters/answer/9012289",
        ],
    }
    report = write_technical_report(
        project_root,
        slug="gsc-indexing-queue",
        provider="google_search_console",
        title="GSC Indexing Request Queue",
        status="ready" if queue else "needs_input",
        summary={**summary, "queue": len(queue), "p0": len([item for item in queue if item["priority"] == "P0"])},
        findings=findings,
        raw_payload={"eligible": eligible, "excluded": excluded},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-indexing-queue.py seo-cycle.yaml --gsc-discovered-file exports/discovered.csv --sitemap https://example.com/sitemap.xml --technical-check --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-request-indexing-browser.py seo-cycle.yaml --queue-file seo/technical/gsc-indexing-request-queue.csv --max 10 --auto-click --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-indexing-recheck.py seo-cycle.yaml --submitted-log seo/technical/gsc-indexing-submit.json --gsc-discovered-file exports/discovered-after-7d.csv --write",
        ],
        notes=[
            "Google does not provide a general public API to request indexing for ordinary pages; queue submission uses the Search Console UI helper.",
            "Repeated request indexing for the same URL does not make crawling faster; keep the queue small and start with P0.",
        ],
        cache_parts={"slug": "gsc-indexing-queue", "summary": summary, "queue": [item["url"] for item in queue]},
        extra_payload={"queue": queue, "excluded": excluded[:100], **csv_paths},
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--gsc-discovered-file", action="append", help="CSV/XLSX/JSON export from GSC Pages issue examples.")
    parser.add_argument("--gsc-performance-file", action="append", help="GSC performance export/API JSON with page metrics.")
    parser.add_argument("--woocommerce-file", action="append", help="WooCommerce product/category CSV/XLSX/JSON export with URLs.")
    parser.add_argument("--url-file", action="append", help="Plain URL list or table to seed the queue manually.")
    parser.add_argument("--sitemap", action="append", help="Sitemap URL. Repeatable.")
    parser.add_argument("--sitemap-file", action="append", help="Local sitemap XML file. Repeatable.")
    parser.add_argument("--exclude-pattern", action="append", help="Extra regex path pattern to filter out.")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--technical-check", action="store_true", help="Run live HTTP/canonical/noindex checks before queueing.")
    parser.add_argument("--check-limit", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()
    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    report = build_report(cfg_path, args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"GSC indexing queue status: {report['status']}")
        print(f"Queue: {report.get('queue_csv', 'not written')}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0 if report["status"] in {"ready", "needs_input"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
