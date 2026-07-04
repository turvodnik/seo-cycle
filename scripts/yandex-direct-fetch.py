#!/usr/bin/env python3
"""Fetch Yandex Direct campaigns/keywords/stats/search queries (read-only, guarded).

Default mode is offline: parse --input-file (a saved API export) or reuse the
cached `seo/ads/raw/yandex_direct/<report>-latest.json` within the ads cache
TTL. Real API calls require --live and pass a usage-ledger preflight first.
Raw responses go to seo/ads/raw/yandex_direct/, a bounded distillate to
seo/ads/yandex-direct-summary.md/json. Secrets are never printed.

Reports: campaigns | keywords | stats | search_queries
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from seo_cycle_core.ads import (
    ads_config,
    env_status,
    ledger_preflight,
    ledger_record,
    load_latest_raw,
    require_enabled,
    save_raw,
    summary_paths,
)
from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

PLATFORM = "yandex_direct"
REPORTS = ("campaigns", "keywords", "stats", "search_queries")
API_HOST = "https://api.direct.yandex.com"
SANDBOX_HOST = "https://api-sandbox.direct.yandex.com"

log = setup_logging("yandex-direct-fetch")


def api_host(sandbox: bool) -> str:
    return SANDBOX_HOST if sandbox else API_HOST


def direct_request(host: str, service: str, payload: dict[str, Any], token: str,
                   client_login: str) -> dict[str, Any]:
    url = f"{host}/json/v5/{service}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }
    if client_login:
        headers["Client-Login"] = client_login
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_campaigns(host: str, token: str, client_login: str) -> dict[str, Any]:
    payload = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Name", "State", "Status", "Type", "DailyBudget", "Funds"],
        },
    }
    return direct_request(host, "campaigns", payload, token, client_login)


def fetch_keywords(host: str, token: str, client_login: str) -> dict[str, Any]:
    payload = {
        "method": "get",
        "params": {
            "SelectionCriteria": {},
            "FieldNames": ["Id", "Keyword", "State", "Status", "AdGroupId", "CampaignId", "Bid"],
            "Page": {"Limit": 10000},
        },
    }
    return direct_request(host, "keywords", payload, token, client_login)


def fetch_report(host: str, token: str, client_login: str, *, report_type: str,
                 field_names: list[str], days: int, report_name: str) -> list[dict[str, Any]]:
    """Reports API: TSV over POST with 201/202 offline handling."""
    date_to = dt.date.today()
    date_from = date_to - dt.timedelta(days=days)
    payload = {
        "params": {
            "SelectionCriteria": {"DateFrom": date_from.isoformat(), "DateTo": date_to.isoformat()},
            "FieldNames": field_names,
            "ReportName": f"{report_name}-{date_to.isoformat()}",
            "ReportType": report_type,
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "YES",
        }
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
        "processingMode": "auto",
        "returnMoneyInMicros": "false",
        "skipReportHeader": "true",
        "skipReportSummary": "true",
    }
    if client_login:
        headers["Client-Login"] = client_login
    url = f"{host}/json/v5/reports"
    request_body = json.dumps(payload).encode("utf-8")
    for attempt in range(8):
        req = urllib.request.Request(url, data=request_body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                if resp.status == 200:
                    return parse_tsv(resp.read().decode("utf-8"), field_names)
                retry_in = int(resp.headers.get("retryIn", "10") or "10")
        except urllib.error.HTTPError as exc:
            if exc.code in (201, 202):
                retry_in = int(exc.headers.get("retryIn", "10") or "10")
            else:
                raise
        log.info("reports offline mode: waiting %ss (attempt %s)", retry_in, attempt + 1)
        time.sleep(min(retry_in, 30))
    raise RuntimeError("Reports API did not return the report after 8 attempts")


def parse_tsv(text: str, field_names: list[str]) -> list[dict[str, Any]]:
    """First TSV line is the column header (skipReportHeader=true keeps it)."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = lines[0].split("\t")
    columns = header if set(header) & set(field_names) else field_names
    start = 1 if columns is header else 0
    return [dict(zip(columns, line.split("\t"), strict=False)) for line in lines[start:]]


def live_fetch(report: str, cfg: dict[str, Any], days: int) -> Any:
    token = os.environ.get("YANDEX_DIRECT_TOKEN", "")
    client_login = os.environ.get("YANDEX_DIRECT_CLIENT_LOGIN", "") or str(
        nested_get(cfg, "ads.yandex_direct.client_login", "") or ""
    )
    sandbox = bool(nested_get(cfg, "ads.yandex_direct.sandbox", False))
    host = api_host(sandbox)
    if report == "campaigns":
        return fetch_campaigns(host, token, client_login)
    if report == "keywords":
        return fetch_keywords(host, token, client_login)
    if report == "stats":
        return {
            "rows": fetch_report(
                host, token, client_login,
                report_type="CAMPAIGN_PERFORMANCE_REPORT",
                field_names=["Date", "CampaignId", "CampaignName", "Impressions", "Clicks", "Cost", "Conversions"],
                days=days,
                report_name="seo-cycle-stats",
            )
        }
    return {
        "rows": fetch_report(
            host, token, client_login,
            report_type="SEARCH_QUERY_PERFORMANCE_REPORT",
            field_names=["Query", "CampaignId", "AdGroupId", "Impressions", "Clicks", "Cost", "Conversions"],
            days=days,
            report_name="seo-cycle-search-queries",
        )
    }


def summarize(project_root: pathlib.Path, ttl_hours: float) -> dict[str, Any]:
    summary: dict[str, Any] = {"provider": PLATFORM, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "reports": {}}
    campaigns = load_latest_raw(project_root, PLATFORM, "campaigns") or {}
    rows = nested_get(campaigns, "result.Campaigns", []) or []
    summary["reports"]["campaigns"] = {
        "count": len(rows),
        "active": sum(1 for row in rows if row.get("State") == "ON"),
        "names": [row.get("Name") for row in rows[:15]],
    }
    stats = load_latest_raw(project_root, PLATFORM, "stats") or {}
    stat_rows = stats.get("rows") or []
    total_cost = sum(float(row.get("Cost") or 0) for row in stat_rows)
    total_clicks = sum(float(row.get("Clicks") or 0) for row in stat_rows)
    total_conversions = sum(float(row.get("Conversions") or 0) for row in stat_rows)
    summary["reports"]["stats"] = {
        "rows": len(stat_rows),
        "cost": round(total_cost, 2),
        "clicks": int(total_clicks),
        "conversions": int(total_conversions),
        "avg_cpc": round(total_cost / total_clicks, 2) if total_clicks else 0,
    }
    queries = load_latest_raw(project_root, PLATFORM, "search_queries") or {}
    summary["reports"]["search_queries"] = {"rows": len(queries.get("rows") or [])}
    keywords = load_latest_raw(project_root, PLATFORM, "keywords") or {}
    summary["reports"]["keywords"] = {"count": len(nested_get(keywords, "result.Keywords", []) or [])}
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    reports = summary["reports"]
    lines = [
        "# Yandex Direct Summary",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Campaigns: {reports['campaigns']['count']} (active: {reports['campaigns']['active']})",
        f"- Stats rows: {reports['stats']['rows']} · cost: {reports['stats']['cost']}"
        f" · clicks: {reports['stats']['clicks']} · conversions: {reports['stats']['conversions']}"
        f" · avg CPC: {reports['stats']['avg_cpc']}",
        f"- Search queries rows: {reports['search_queries']['rows']}",
        f"- Keywords: {reports['keywords']['count']}",
        "",
        "Raw exports: `seo/ads/raw/yandex_direct/` · next: `ads-analytics.py --write`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--report", choices=REPORTS, default="campaigns")
    parser.add_argument("--input-file", help="Saved API export (JSON) to ingest instead of a live call")
    parser.add_argument("--live", action="store_true", help="Make a real API call (requires env token + ledger preflight)")
    parser.add_argument("--days", type=int, default=30, help="Stats window for Reports API")
    parser.add_argument("--write", action="store_true", help="Write raw + summary artifacts")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("yandex-direct-fetch", project_root, cfg)
    ads = ads_config(cfg)

    error = require_enabled(cfg, PLATFORM)
    if error and (args.live or args.input_file):
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    payload: Any = None
    if args.input_file:
        payload = json.loads(pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8"))
    elif args.live:
        env = env_status(PLATFORM)
        if not env["present"]:
            print(f"ERROR: missing env: {', '.join(env['missing'])}", file=sys.stderr)
            return 2
        ok, message = ledger_preflight(project_root, PLATFORM, requests=1)
        if not ok:
            print(f"ERROR: usage-ledger preflight blocked the run: {message}", file=sys.stderr)
            return 2
        try:
            payload = live_fetch(args.report, cfg, args.days)
        except (urllib.error.URLError, RuntimeError, json.JSONDecodeError) as exc:
            print(f"ERROR: Direct API call failed: {exc}", file=sys.stderr)
            return 1
        ledger_record(project_root, PLATFORM, requests=1, note=f"fetch {args.report}")
    else:
        cached = load_latest_raw(project_root, PLATFORM, args.report, ttl_hours=float(ads.get("cache_ttl_hours", 24)))
        if cached is None:
            print(
                f"No fresh cache for `{args.report}`. Provide --input-file <export.json> or run with --live "
                "after checking `seo-cycle spend`.",
                file=sys.stderr,
            )
            return 0
        payload = cached

    if payload is not None and args.write and (args.input_file or args.live):
        save_raw(project_root, PLATFORM, args.report, payload)
    summary = summarize(project_root, float(ads.get("cache_ttl_hours", 24)))
    if args.write:
        write_report_bundle(summary_paths(cfg, project_root, PLATFORM), render_markdown(summary), summary)
    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
