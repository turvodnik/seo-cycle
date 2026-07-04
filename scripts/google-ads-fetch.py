#!/usr/bin/env python3
"""Fetch Google Ads campaigns/keywords/search terms/stats/recommendations (read-only, guarded).

Default mode is offline: parse --input-file (a saved GAQL export) or reuse the
cached `seo/ads/raw/google_ads/<report>-latest.json` within the ads cache TTL.
Real API calls require --live, full OAuth env, and a usage-ledger preflight.
For `region_profile: ru` a missing setup is expected (`region_limited`) — use
Yandex Direct as the primary channel.

Reports: campaigns | keywords | search_terms | stats | recommendations
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
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

PLATFORM = "google_ads"
REPORTS = ("campaigns", "keywords", "search_terms", "stats", "recommendations")
DEFAULT_API_VERSION = "v19"
TOKEN_URL = "https://oauth2.googleapis.com/token"

GAQL = {
    "campaigns": (
        "SELECT campaign.id, campaign.name, campaign.status, campaign_budget.amount_micros "
        "FROM campaign WHERE campaign.status != 'REMOVED'"
    ),
    "keywords": (
        "SELECT campaign.id, ad_group.id, ad_group_criterion.keyword.text, "
        "ad_group_criterion.keyword.match_type, ad_group_criterion.status, metrics.average_cpc "
        "FROM keyword_view WHERE segments.date DURING LAST_30_DAYS"
    ),
    "search_terms": (
        "SELECT campaign.id, search_term_view.search_term, metrics.clicks, metrics.impressions, "
        "metrics.cost_micros, metrics.conversions "
        "FROM search_term_view WHERE segments.date DURING LAST_30_DAYS"
    ),
    "stats": (
        "SELECT segments.date, campaign.id, campaign.name, metrics.clicks, metrics.impressions, "
        "metrics.cost_micros, metrics.conversions "
        "FROM campaign WHERE segments.date DURING LAST_30_DAYS"
    ),
    "recommendations": (
        "SELECT recommendation.type, recommendation.resource_name, recommendation.dismissed "
        "FROM recommendation"
    ),
}

log = setup_logging("google-ads-fetch")


def oauth_access_token() -> str:
    body = urllib.parse.urlencode(
        {
            "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def gaql_search(report: str) -> dict[str, Any]:
    version = os.environ.get("GOOGLE_ADS_API_VERSION", DEFAULT_API_VERSION)
    customer_id = os.environ["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")
    url = f"https://googleads.googleapis.com/{version}/customers/{customer_id}/googleAds:search"
    headers = {
        "Authorization": f"Bearer {oauth_access_token()}",
        "developer-token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "Content-Type": "application/json",
    }
    login_customer = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "")
    if login_customer:
        headers["login-customer-id"] = login_customer
    results: list[dict[str, Any]] = []
    page_token = ""
    for _ in range(20):  # hard page cap per run
        body: dict[str, Any] = {"query": GAQL[report]}
        if page_token:
            body["pageToken"] = page_token
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results.extend(data.get("results") or [])
        page_token = data.get("nextPageToken") or ""
        if not page_token:
            break
    return {"results": results, "query": GAQL[report]}


def micros(value: Any) -> float:
    try:
        return float(value) / 1_000_000
    except (TypeError, ValueError):
        return 0.0


def summarize(project_root: pathlib.Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "provider": PLATFORM,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "reports": {},
    }
    campaigns = (load_latest_raw(project_root, PLATFORM, "campaigns") or {}).get("results") or []
    summary["reports"]["campaigns"] = {
        "count": len(campaigns),
        "enabled": sum(1 for row in campaigns if nested_get(row, "campaign.status") == "ENABLED"),
        "names": [nested_get(row, "campaign.name") for row in campaigns[:15]],
    }
    stats = (load_latest_raw(project_root, PLATFORM, "stats") or {}).get("results") or []
    cost = sum(micros(nested_get(row, "metrics.costMicros")) for row in stats)
    clicks = sum(float(nested_get(row, "metrics.clicks", 0) or 0) for row in stats)
    conversions = sum(float(nested_get(row, "metrics.conversions", 0) or 0) for row in stats)
    summary["reports"]["stats"] = {
        "rows": len(stats),
        "cost": round(cost, 2),
        "clicks": int(clicks),
        "conversions": round(conversions, 1),
        "avg_cpc": round(cost / clicks, 2) if clicks else 0,
    }
    terms = (load_latest_raw(project_root, PLATFORM, "search_terms") or {}).get("results") or []
    summary["reports"]["search_terms"] = {"rows": len(terms)}
    recs = (load_latest_raw(project_root, PLATFORM, "recommendations") or {}).get("results") or []
    summary["reports"]["recommendations"] = {"count": len(recs)}
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    reports = summary["reports"]
    lines = [
        "# Google Ads Summary",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Campaigns: {reports['campaigns']['count']} (enabled: {reports['campaigns']['enabled']})",
        f"- Stats rows: {reports['stats']['rows']} · cost: {reports['stats']['cost']}"
        f" · clicks: {reports['stats']['clicks']} · conversions: {reports['stats']['conversions']}"
        f" · avg CPC: {reports['stats']['avg_cpc']}",
        f"- Search terms rows: {reports['search_terms']['rows']}",
        f"- Recommendations: {reports['recommendations']['count']}",
        "",
        "Raw exports: `seo/ads/raw/google_ads/` · next: `ads-analytics.py --write`",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--report", choices=REPORTS, default="campaigns")
    parser.add_argument("--input-file", help="Saved GAQL export (JSON) to ingest instead of a live call")
    parser.add_argument("--live", action="store_true", help="Make a real API call (requires OAuth env + ledger preflight)")
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
    log = setup_logging("google-ads-fetch", project_root, cfg)
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
            print(
                f"ERROR: missing env: {', '.join(env['missing'])}. "
                "For region_profile: ru this is expected — use yandex-direct-fetch.py.",
                file=sys.stderr,
            )
            return 2
        ok, message = ledger_preflight(project_root, PLATFORM, requests=1)
        if not ok:
            print(f"ERROR: usage-ledger preflight blocked the run: {message}", file=sys.stderr)
            return 2
        try:
            payload = gaql_search(args.report)
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
            print(f"ERROR: Google Ads API call failed: {exc}", file=sys.stderr)
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
    summary = summarize(project_root)
    if args.write:
        write_report_bundle(summary_paths(cfg, project_root, PLATFORM), render_markdown(summary), summary)
    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
