#!/usr/bin/env python3
"""Recheck a submitted GSC indexing queue after 3-7 days.

Inputs can be fresh Search Console issue exports, indexed-page exports and/or
Search Analytics data. The output tells whether submitted URLs disappeared from
the discovered-not-indexed issue, gained search data, are indexed in an export,
or still need content/internal-link/technical work.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
import urllib.parse
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, rel_display, rel_path
from seo_cycle_core.technical_artifacts import write_technical_report


URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
DISCOVERED_MARKERS = ("discovered", "currently not indexed", "обнаружена", "не проиндексирована")


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urllib.parse.urlunsplit(((parsed.scheme or "https").lower(), parsed.netloc.lower(), path, "", ""))


def url_from_row(row: dict[str, Any]) -> str:
    for key in ("url", "URL", "page", "Page", "inspection_url", "link", "loc"):
        value = row.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value.strip()
    text = " ".join(str(value) for value in row.values() if value is not None)
    match = URL_RE.search(text)
    return match.group(0) if match else ""


def load_table(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            if isinstance(data.get("results"), list):
                return [item for item in data["results"] if isinstance(item, dict)]
            if isinstance(data.get("queue"), list):
                return [item for item in data["queue"] if isinstance(item, dict)]
            if isinstance(data.get("rows"), list):
                return [item for item in data["rows"] if isinstance(item, dict)]
            distillate = data.get("distillate")
            if isinstance(distillate, dict) and isinstance(distillate.get("results"), list):
                return [item for item in distillate["results"] if isinstance(item, dict)]
            raw = data.get("browser")
            if isinstance(raw, dict) and isinstance(raw.get("results"), list):
                return [item for item in raw["results"] if isinstance(item, dict)]
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_url_set(paths: list[str] | None, project_root: pathlib.Path, *, discovered_only: bool = False) -> set[str]:
    urls: set[str] = set()
    for raw_path in paths or []:
        path = rel_path(project_root, raw_path)
        for row in load_table(path):
            text = " ".join(str(value).lower() for value in row.values() if value is not None)
            if discovered_only and not any(marker in text for marker in DISCOVERED_MARKERS):
                # If a file is explicitly an issue export, the URL can still be accepted
                # when no status column exists. Rows with marker mismatch are rare.
                if any(key.lower() in {"status", "reason", "issue"} for key in row):
                    continue
            url = url_from_row(row)
            if url:
                urls.add(normalize_url(url))
    return urls


def numeric(value: Any) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def load_metrics(paths: list[str] | None, project_root: pathlib.Path) -> dict[str, dict[str, float]]:
    metrics: dict[str, dict[str, float]] = {}
    for raw_path in paths or []:
        path = rel_path(project_root, raw_path)
        for row in load_table(path):
            url = url_from_row(row)
            keys = row.get("keys") if isinstance(row.get("keys"), list) else []
            if not url:
                for item in keys:
                    if isinstance(item, str) and item.startswith(("http://", "https://")):
                        url = item
                        break
            if not url:
                continue
            key = normalize_url(url)
            current = metrics.setdefault(key, {"clicks": 0.0, "impressions": 0.0})
            current["clicks"] += numeric(row.get("clicks") or row.get("Clicks") or row.get("Клики"))
            current["impressions"] += numeric(row.get("impressions") or row.get("Impressions") or row.get("Показы"))
    return metrics


def load_submitted(path: pathlib.Path) -> list[dict[str, Any]]:
    rows = load_table(path)
    out: list[dict[str, Any]] = []
    for row in rows:
        url = url_from_row(row)
        if url:
            out.append({**row, "url": url})
    return out


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    submitted_path = rel_path(project_root, args.submitted_log)
    submitted = load_submitted(submitted_path)
    discovered = load_url_set(args.gsc_discovered_file, project_root, discovered_only=True)
    indexed = load_url_set(args.indexed_file, project_root)
    metrics = load_metrics(args.gsc_performance_file, project_root)
    rows: list[dict[str, Any]] = []
    counts = {"indexed": 0, "has_search_data": 0, "still_discovered_not_indexed": 0, "unknown": 0}
    for row in submitted:
        key = normalize_url(row["url"])
        metric = metrics.get(key, {})
        if key in indexed:
            status = "indexed"
        elif metric.get("impressions") or metric.get("clicks"):
            status = "has_search_data"
        elif key in discovered:
            status = "still_discovered_not_indexed"
        else:
            status = "unknown"
        counts[status] += 1
        rows.append(
            {
                "url": row["url"],
                "previous_status": row.get("status", ""),
                "recheck_status": status,
                "impressions": metric.get("impressions", 0),
                "clicks": metric.get("clicks", 0),
                "next_action": "wait_or_inspect" if status == "unknown" else "improve_content_internal_links_then_requeue" if status == "still_discovered_not_indexed" else "done",
            }
        )
    summary = {
        "domain": nested_get(cfg, "project.domain") or "",
        "mode": "gsc_indexing_recheck",
        "submitted": len(submitted),
        "indexed": counts["indexed"],
        "has_search_data": counts["has_search_data"],
        "still_discovered_not_indexed": counts["still_discovered_not_indexed"],
        "unknown": counts["unknown"],
        "submitted_log": rel_display(project_root, submitted_path),
    }
    findings: list[dict[str, Any]] = []
    if counts["still_discovered_not_indexed"]:
        findings.append(
            {
                "id": "gsc_submitted_urls_still_not_indexed",
                "severity": "medium",
                "message": f"{counts['still_discovered_not_indexed']} submitted URLs are still in discovered/not-indexed exports.",
                "evidence": [item for item in rows if item["recheck_status"] == "still_discovered_not_indexed"][:15],
            }
        )
    if counts["unknown"]:
        findings.append(
            {
                "id": "gsc_submitted_urls_need_url_inspection",
                "severity": "info",
                "message": "Some URLs are no longer in the issue export but have no indexed/export/search-performance proof yet.",
                "evidence": [item for item in rows if item["recheck_status"] == "unknown"][:15],
            }
        )
    distillate = {
        "summary": summary,
        "rows": rows,
        "citations": [
            "https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl",
            "https://support.google.com/webmasters/answer/9012289",
        ],
    }
    return write_technical_report(
        project_root,
        slug="gsc-indexing-recheck",
        provider="google_search_console",
        title="GSC Indexing Recheck",
        status="attention_required" if counts["still_discovered_not_indexed"] else "ready",
        summary=summary,
        findings=findings,
        raw_payload={"submitted": submitted, "rows": rows},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py seo-cycle.yaml --url https://example.com/page/ --live --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-indexing-queue.py seo-cycle.yaml --gsc-discovered-file exports/discovered-after-7d.csv --technical-check --write",
        ],
        notes=["Run this 3-7 days after the browser submission using fresh GSC exports."],
        cache_parts={"slug": "gsc-indexing-recheck", "summary": summary, "rows": rows},
        extra_payload={"rows": rows},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--submitted-log", default="seo/technical/gsc-indexing-submit.json", help="Browser submission report JSON/CSV.")
    parser.add_argument("--gsc-discovered-file", action="append", help="Fresh discovered/not-indexed export after 3-7 days.")
    parser.add_argument("--indexed-file", action="append", help="Fresh indexed pages export, if available.")
    parser.add_argument("--gsc-performance-file", action="append", help="Fresh GSC performance export/API JSON.")
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
        print(f"GSC indexing recheck status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
