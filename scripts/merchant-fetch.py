#!/usr/bin/env python3
"""Fetch Google Merchant Center diagnostics (read-only, guarded).

Default mode is offline: parse --input-file (a saved Content API statuses
export). --live reads accountstatuses/productstatuses via Content API v2.1
(service account via GOOGLE_APPLICATION_CREDENTIALS, env
GOOGLE_MERCHANT_ACCOUNT_ID). Nothing is ever written to the account.

Output: seo/merchant/merchant-summary.md/json (+latest) — issue counters by
severity/reason and top disapproved products; raw payload lands in
seo/merchant/raw/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("merchant-fetch")

SCOPE = "https://www.googleapis.com/auth/content"
API_BASE = "https://shoppingcontent.googleapis.com/content/v2.1"
REPORTS = ("accountstatuses", "productstatuses")


def live_fetch(report: str, max_pages: int = 5) -> dict[str, Any]:
    try:
        from google.auth import default as adc_default
        from google.auth.transport.requests import Request as AuthRequest
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("google-auth is required for --live: pip3 install google-auth") from exc
    merchant_id = os.environ.get("GOOGLE_MERCHANT_ACCOUNT_ID", "").replace("-", "")
    if not merchant_id:
        raise RuntimeError("set GOOGLE_MERCHANT_ACCOUNT_ID env")
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and pathlib.Path(creds_path).expanduser().exists():
        creds = service_account.Credentials.from_service_account_file(creds_path, scopes=[SCOPE])
    else:
        creds, _ = adc_default(scopes=[SCOPE])
    creds.refresh(AuthRequest())

    resources = []
    page_token = ""
    for _ in range(max_pages):
        url = f"{API_BASE}/{merchant_id}/{report}?maxResults=250"
        if page_token:
            url += f"&pageToken={page_token}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {creds.token}"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        resources.extend(data.get("resources") or [])
        page_token = data.get("nextPageToken") or ""
        if not page_token:
            break
    return {"kind": report, "resources": resources}


def summarize(report_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    resources = payload.get("resources") or []
    if report_name == "accountstatuses":
        issues = []
        for account in resources:
            for issue in account.get("accountLevelIssues") or []:
                issues.append({"id": issue.get("id"), "severity": issue.get("severity"),
                               "title": issue.get("title"), "country": issue.get("country")})
        return {"accounts": len(resources), "account_issues": issues[:50],
                "issue_count": len(issues),
                "by_severity": dict(Counter(str(item.get("severity")) for item in issues))}

    reasons: Counter = Counter()
    disapproved = []
    statuses: Counter = Counter()
    for product in resources:
        for destination in product.get("destinationStatuses") or []:
            statuses[str(destination.get("status"))] += 1
        for issue in product.get("itemLevelIssues") or []:
            reasons[str(issue.get("description") or issue.get("code"))] += 1
            if str(issue.get("servability")) == "disapproved":
                disapproved.append({"product": product.get("productId") or product.get("title"),
                                    "issue": issue.get("description") or issue.get("code"),
                                    "attribute": issue.get("attributeName")})
    return {"products": len(resources),
            "destination_statuses": dict(statuses),
            "top_issue_reasons": reasons.most_common(15),
            "disapproved_examples": disapproved[:20],
            "disapproved_issue_count": len(disapproved)}


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Google Merchant Summary",
        "",
        f"- Generated: {summary['generated_at']}",
    ]
    account = summary["reports"].get("accountstatuses")
    if account:
        lines.append(f"- Account issues: {account['issue_count']} (severity: {account['by_severity']})")
        for issue in account["account_issues"][:8]:
            lines.append(f"  - **{issue['severity']}** {issue['title']} ({issue['country']})")
    products = summary["reports"].get("productstatuses")
    if products:
        lines.extend(
            [
                f"- Products in export: {products['products']}"
                f" · destination statuses: {products['destination_statuses']}",
                f"- Disapproved item issues: {products['disapproved_issue_count']}",
                "",
                "## Top issue reasons",
                "",
            ]
        )
        for reason, count in products["top_issue_reasons"]:
            lines.append(f"- {count}× {reason}")
        if products["disapproved_examples"]:
            lines.extend(["", "## Disapproved examples", ""])
            for row in products["disapproved_examples"][:10]:
                lines.append(f"- `{row['product']}`: {row['issue']} (attribute: {row['attribute'] or '—'})")
    if not summary["reports"]:
        lines.append("- No data yet: run with --input-file <statuses.json> or --live.")
    return "\n".join(lines) + "\n"


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "merchant"
    return {
        "markdown": base / "merchant-summary.md",
        "json": base / "merchant-summary.json",
        "latest_markdown": base / "latest-merchant-summary.md",
        "latest_json": base / "latest-merchant-summary.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--report", choices=REPORTS, default="productstatuses")
    parser.add_argument("--input-file", help="Saved Content API statuses export (JSON)")
    parser.add_argument("--live", action="store_true", help="Read statuses via Content API v2.1 (read-only)")
    parser.add_argument("--write", action="store_true", help="Write seo/merchant artifacts")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("merchant-fetch", project_root, cfg)

    if args.input_file:
        payload = json.loads(pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8"))
        report_name = args.report if "resources" in payload else str(payload.get("kind") or args.report)
        if "resources" not in payload:
            payload = {"resources": payload.get("resources") or payload.get("items") or []}
    elif args.live:
        try:
            payload = live_fetch(args.report)
        except (RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"ERROR: Merchant API read failed: {exc}. "
                  "For region_profile: ru this is expected — use yml-feed-audit.py.", file=sys.stderr)
            return 1
        report_name = args.report
    else:
        print("Provide --input-file <statuses.json> or --live (read-only Content API).", file=sys.stderr)
        return 0

    if args.write:
        raw_path = project_root / "seo" / "merchant" / "raw" / f"{report_name}-latest.json"
        write_text(raw_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    summary = {
        "audit_id": "merchant_summary",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "reports": {report_name: summarize(report_name, payload)},
    }
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(summary), summary)
    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
