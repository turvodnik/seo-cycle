#!/usr/bin/env python3
"""Fetch raw visit/hit logs from Yandex Metrika Logs API (guarded, read-only).

The Logs API returns unsampled per-visit/per-hit TSV — the foundation for deep
behavior analytics beyond the aggregated Stats API (metrika-fetch.py). One-shot
--live flow: evaluate → create request → poll until processed → download parts
→ clean up the server-side request. Offline mode ingests a previously
downloaded TSV via --input-file.

Env: YANDEX_OAUTH_TOKEN + YANDEX_METRIKA_COUNTER_ID (same as metrika-fetch).
Raw TSV → seo/analytics/raw/metrika-logs/<source>-<date-range>.tsv,
summary → seo/analytics/metrika-logs-summary.md/json (+latest) with --write.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("metrika-logs-fetch")

API_BASE = "https://api-metrika.yandex.net/management/v1/counter"
DEFAULT_VISIT_FIELDS = ",".join(
    [
        "ym:s:visitID",
        "ym:s:date",
        "ym:s:startURL",
        "ym:s:lastTrafficSource",
        "ym:s:lastSearchEngine",
        "ym:s:pageViews",
        "ym:s:visitDuration",
        "ym:s:isNewUser",
        "ym:s:goalsID",
    ]
)
DEFAULT_HIT_FIELDS = ",".join(["ym:pv:watchID", "ym:pv:date", "ym:pv:URL", "ym:pv:title", "ym:pv:isPageView"])
POLL_SECONDS = 15
POLL_ATTEMPTS = 40  # up to 10 minutes


def api_call(counter: str, token: str, path: str, *, method: str = "GET",
             params: dict[str, Any] | None = None) -> Any:
    url = f"{API_BASE}/{counter}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method=method, headers={
        "Authorization": f"OAuth {token}",
        "User-Agent": "seo-cycle metrika-logs-fetch",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read()
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace")


def live_fetch(counter: str, token: str, *, source: str, fields: str,
               date_from: str, date_to: str) -> str:
    params = {"date1": date_from, "date2": date_to, "source": source, "fields": fields}
    evaluation = api_call(counter, token, "/logrequests/evaluate", params=params)
    possible = (evaluation.get("log_request_evaluation") or {}).get("possible")
    if not possible:
        raise RuntimeError(
            "Logs API evaluate says the request is not possible for this window; "
            "reduce --days or the field list"
        )
    created = api_call(counter, token, "/logrequests", method="POST", params=params)
    request_id = (created.get("log_request") or {}).get("request_id")
    if not request_id:
        raise RuntimeError(f"unexpected create response: {str(created)[:300]}")
    log.info("logs request %s created (%s..%s)", request_id, date_from, date_to)

    parts: list[dict[str, Any]] = []
    for _attempt in range(POLL_ATTEMPTS):
        status = api_call(counter, token, f"/logrequest/{request_id}")
        request_status = (status.get("log_request") or {}).get("status")
        if request_status == "processed":
            parts = (status.get("log_request") or {}).get("parts") or []
            break
        if request_status in {"processing_failed", "canceled"}:
            raise RuntimeError(f"logs request {request_id} ended with status {request_status}")
        time.sleep(POLL_SECONDS)
    else:
        raise RuntimeError(f"logs request {request_id} still not processed after "
                           f"{POLL_ATTEMPTS * POLL_SECONDS}s; retry later with the same window")

    chunks = []
    for part in parts:
        part_number = part.get("part_number", 0)
        chunk = api_call(counter, token, f"/logrequest/{request_id}/part/{part_number}/download")
        chunks.append(chunk if isinstance(chunk, str) else "")
    api_call(counter, token, f"/logrequest/{request_id}/clean", method="POST")
    log.info("logs request %s downloaded (%s parts) and cleaned", request_id, len(parts))

    if not chunks:
        return ""
    header, *rest = chunks
    merged = [header.rstrip("\n")]
    for chunk in rest:
        lines = chunk.splitlines()
        merged.extend(lines[1:] if lines else [])
    return "\n".join(merged) + "\n"


def summarize(tsv_text: str, source: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    rows = list(reader)
    summary: dict[str, Any] = {"rows": len(rows), "source": source, "fields": reader.fieldnames or []}
    if not rows:
        return summary
    date_field = next((f for f in summary["fields"] if f.endswith(":date")), None)
    if date_field:
        dates = sorted(row.get(date_field, "") for row in rows if row.get(date_field))
        summary["date_range"] = [dates[0], dates[-1]] if dates else []
    if source == "visits":
        traffic = Counter(row.get("ym:s:lastTrafficSource", "") for row in rows)
        summary["by_traffic_source"] = dict(traffic.most_common(10))
        pages = Counter(row.get("ym:s:startURL", "") for row in rows)
        summary["top_landing_pages"] = pages.most_common(10)
        durations = [int(row.get("ym:s:visitDuration") or 0) for row in rows]
        summary["avg_visit_duration_sec"] = round(sum(durations) / len(durations), 1) if durations else 0
        summary["visits_with_goals"] = sum(1 for row in rows if (row.get("ym:s:goalsID") or "[]") not in ("[]", ""))
        summary["new_users_share"] = round(
            sum(1 for row in rows if row.get("ym:s:isNewUser") == "1") / len(rows), 3
        )
    else:
        pages = Counter(row.get("ym:pv:URL", "") for row in rows)
        summary["top_pages"] = pages.most_common(15)
    return summary


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Metrika Logs Summary",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Source: `{summary.get('source')}` · rows: {summary.get('rows')}"
        f" · dates: {summary.get('date_range', [])}",
    ]
    if summary.get("by_traffic_source"):
        lines.extend(["", "## Traffic sources", ""])
        for source, count in summary["by_traffic_source"].items():
            lines.append(f"- {source or '—'}: {count}")
        lines.append("")
        lines.append(f"- Avg visit duration: {summary.get('avg_visit_duration_sec')}s"
                     f" · visits with goals: {summary.get('visits_with_goals')}"
                     f" · new users share: {summary.get('new_users_share')}")
    for key, title in (("top_landing_pages", "Top landing pages"), ("top_pages", "Top pages")):
        if summary.get(key):
            lines.extend(["", f"## {title}", ""])
            for url, count in summary[key][:10]:
                lines.append(f"- {count}× {url}")
    lines.extend(["", "Raw TSV: `seo/analytics/raw/metrika-logs/` — не грузи в контекст целиком."])
    return "\n".join(lines) + "\n"


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "analytics"
    return {
        "markdown": base / "metrika-logs-summary.md",
        "json": base / "metrika-logs-summary.json",
        "latest_markdown": base / "latest-metrika-logs-summary.md",
        "latest_json": base / "latest-metrika-logs-summary.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--source", choices=("visits", "hits"), default="visits")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--fields", help="Override the Logs API field list")
    parser.add_argument("--input-file", help="Previously downloaded Logs API TSV")
    parser.add_argument("--live", action="store_true", help="Create/download a real Logs API request")
    parser.add_argument("--write", action="store_true", help="Write raw TSV + summary artifacts")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("metrika-logs-fetch", project_root, cfg)

    date_to = dt.date.today() - dt.timedelta(days=1)
    date_from = date_to - dt.timedelta(days=max(1, args.days) - 1)

    if args.input_file:
        tsv_text = pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8", errors="replace")
    elif args.live:
        counter = os.environ.get("YANDEX_METRIKA_COUNTER_ID", "")
        token = os.environ.get("YANDEX_OAUTH_TOKEN", "")
        if not counter or not token:
            print("ERROR: set YANDEX_METRIKA_COUNTER_ID and YANDEX_OAUTH_TOKEN env", file=sys.stderr)
            return 2
        fields = args.fields or (DEFAULT_VISIT_FIELDS if args.source == "visits" else DEFAULT_HIT_FIELDS)
        try:
            tsv_text = live_fetch(counter, token, source=args.source, fields=fields,
                                  date_from=date_from.isoformat(), date_to=date_to.isoformat())
        except (RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"ERROR: Logs API failed: {exc}", file=sys.stderr)
            return 1
    else:
        print("Provide --input-file <logs.tsv> or --live (creates a Logs API request via OAuth).",
              file=sys.stderr)
        return 0

    if args.write and tsv_text.strip():
        raw_path = (project_root / "seo" / "analytics" / "raw" / "metrika-logs"
                    / f"{args.source}-{date_from.isoformat()}-{date_to.isoformat()}.tsv")
        write_text(raw_path, tsv_text)

    report = {
        "audit_id": "metrika_logs",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "summary": summarize(tsv_text, args.source),
    }
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
