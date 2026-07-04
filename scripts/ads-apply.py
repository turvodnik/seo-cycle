#!/usr/bin/env python3
"""Apply an approved ads draft to a platform. The ONLY script that writes to ad platforms.

Six safeguards, all mandatory:
  1. --ticket <id> must be an APPROVED `ads_campaign_draft`/`ads_bid_change` ticket.
  2. usage-ledger preflight for the platform must allow the spend.
  3. Both --live and --allow-write flags are required for any real API call.
  4. Per-run operation cap (`ads.apply.max_changes_per_run`, default 20); budgets
     are only ever set when `ads.apply.max_daily_budget > 0`.
  5. Default mode is dry-run: prints the operation plan and exits.
  6. Every applied run is recorded in the usage ledger and announced via notify.py.

V1 scope: Yandex Direct apply (campaigns/adgroups/keywords via API v5, sandbox
supported). Google Ads apply stays behind `ads.google_ads.apply_enabled` and is
не реализован — use the Google Ads Editor CSV export from ads-draft-builder.py.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

from seo_cycle_core.ads import (
    ads_config,
    env_status,
    ledger_preflight,
    ledger_record,
    require_enabled,
)
from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("ads-apply")

API_HOST = "https://api.direct.yandex.com"
SANDBOX_HOST = "https://api-sandbox.direct.yandex.com"


def scripts_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def ticket_status(project_root: pathlib.Path, ticket_id: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(scripts_dir() / "approval-gate.py"), "status", ticket_id],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.stdout.strip().splitlines()[-1].strip() if proc.stdout.strip() else f"rc={proc.returncode}"


def build_operations(draft: dict[str, Any], max_daily_budget: float) -> list[dict[str, Any]]:
    """Flatten the draft into an ordered operation plan."""
    operations: list[dict[str, Any]] = []
    for campaign in draft.get("campaigns") or []:
        if str(campaign.get("channel") or "search") != "search":
            operations.append({"op": "skip_campaign", "name": campaign.get("name"),
                               "reason": "non-search channel: create manually after review (v1)"})
            continue
        budget = float(campaign.get("budget_daily") or 0)
        operations.append(
            {
                "op": "create_campaign",
                "name": campaign.get("name"),
                "budget_daily": budget if 0 < budget <= max_daily_budget else 0,
                "budget_skipped": bool(budget) and not (0 < budget <= max_daily_budget),
            }
        )
        for group in campaign.get("ad_groups") or []:
            operations.append({"op": "create_ad_group", "campaign": campaign.get("name"),
                               "name": group.get("name")})
            for keyword in group.get("keywords") or []:
                operations.append({"op": "add_keyword", "ad_group": group.get("name"),
                                   "text": keyword.get("text"), "match_type": keyword.get("match_type")})
            for ad in group.get("ads") or []:
                operations.append({"op": "add_ad", "ad_group": group.get("name"),
                                   "final_url": ad.get("final_url")})
        for negative in campaign.get("negatives") or []:
            operations.append({"op": "add_negative", "campaign": campaign.get("name"), "text": negative})
    return operations


def direct_request(host: str, service: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {os.environ['YANDEX_DIRECT_TOKEN']}",
        "Accept-Language": "ru",
        "Content-Type": "application/json; charset=utf-8",
    }
    client_login = os.environ.get("YANDEX_DIRECT_CLIENT_LOGIN", "")
    if client_login:
        headers["Client-Login"] = client_login
    req = urllib.request.Request(f"{host}/json/v5/{service}",
                                 data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def apply_direct(operations: list[dict[str, Any]], sandbox: bool) -> list[dict[str, Any]]:
    """Create campaigns/groups/keywords in Yandex Direct following the plan order."""
    host = SANDBOX_HOST if sandbox else API_HOST
    campaign_ids: dict[str, int] = {}
    group_ids: dict[str, int] = {}
    results = []
    for operation in operations:
        try:
            if operation["op"] == "create_campaign":
                payload = {
                    "method": "add",
                    "params": {
                        "Campaigns": [
                            {
                                "Name": operation["name"],
                                "StartDate": "2030-01-01",  # paused-by-future-date safety net
                                "TextCampaign": {
                                    "BiddingStrategy": {
                                        "Search": {"BiddingStrategyType": "HIGHEST_POSITION"},
                                        "Network": {"BiddingStrategyType": "SERVING_OFF"},
                                    }
                                },
                            }
                        ]
                    },
                }
                data = direct_request(host, "campaigns", payload)
                new_id = nested_get(data, "result.AddResults", [{}])[0].get("Id")
                campaign_ids[operation["name"]] = new_id
                results.append({**operation, "status": "ok", "id": new_id})
            elif operation["op"] == "create_ad_group":
                campaign_id = campaign_ids.get(operation["campaign"])
                if not campaign_id:
                    results.append({**operation, "status": "skipped", "reason": "campaign missing"})
                    continue
                payload = {"method": "add", "params": {"AdGroups": [{
                    "Name": operation["name"], "CampaignId": campaign_id, "RegionIds": [225]}]}}
                data = direct_request(host, "adgroups", payload)
                new_id = nested_get(data, "result.AddResults", [{}])[0].get("Id")
                group_ids[operation["name"]] = new_id
                results.append({**operation, "status": "ok", "id": new_id})
            elif operation["op"] == "add_keyword":
                group_id = group_ids.get(operation["ad_group"])
                if not group_id:
                    results.append({**operation, "status": "skipped", "reason": "ad group missing"})
                    continue
                payload = {"method": "add", "params": {"Keywords": [{
                    "Keyword": operation["text"], "AdGroupId": group_id}]}}
                data = direct_request(host, "keywords", payload)
                results.append({**operation, "status": "ok",
                                "id": nested_get(data, "result.AddResults", [{}])[0].get("Id")})
            else:
                results.append({**operation, "status": "skipped", "reason": "not in v1 apply scope"})
        except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
            results.append({**operation, "status": "failed", "error": str(exc)[:200]})
    return results


def notify(project_root: pathlib.Path, text: str) -> None:
    subprocess.run(
        [sys.executable, str(scripts_dir() / "notify.py"), text, "--title", "Ads apply", "--level", "warn"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--draft", required=True, help="Draft JSON from ads-draft-builder.py")
    parser.add_argument("--ticket", help="Approved approval-gate ticket id (required for --live)")
    parser.add_argument("--live", action="store_true", help="Talk to the real API")
    parser.add_argument("--allow-write", action="store_true", help="Second explicit write consent")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    draft_path = pathlib.Path(args.draft).expanduser().resolve()
    if not draft_path.exists():
        print(f"ERROR: draft {draft_path} not found", file=sys.stderr)
        return 2
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    platform = str(draft.get("platform") or "")

    cfg_path = find_config(pathlib.Path.cwd())
    if not cfg_path:
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("ads-apply", project_root, cfg)
    ads = ads_config(cfg)

    error = require_enabled(cfg, platform)
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if str(ads.get("policy")) == "report_only":
        print("ERROR: ads.policy is report_only — apply is blocked by project policy", file=sys.stderr)
        return 2

    max_changes = int(nested_get(ads, "apply.max_changes_per_run", 20) or 20)
    max_daily_budget = float(nested_get(ads, "apply.max_daily_budget", 0) or 0)
    operations = build_operations(draft, max_daily_budget)

    if len(operations) > max_changes:
        print(
            f"ERROR: draft expands to {len(operations)} operations, over ads.apply.max_changes_per_run={max_changes}. "
            "Split the draft or raise the cap after review.",
            file=sys.stderr,
        )
        return 2

    dry_run = not (args.live and args.allow_write)
    if dry_run:
        plan = {"mode": "dry_run", "platform": platform, "operations": operations,
                "note": "no API calls made; add --live --allow-write with an approved --ticket to apply"}
        print(json.dumps(plan, ensure_ascii=False, indent=2) if args.format == "json"
              else "\n".join([f"# Ads apply dry-run — {platform}", "",
                              *[f"- {op['op']}: {op.get('name') or op.get('text') or op.get('final_url') or ''}"
                                for op in operations],
                              "", plan["note"]]))
        return 0

    # --- live path safeguards -------------------------------------------------
    if not args.ticket:
        print("ERROR: --live requires --ticket <approved id>", file=sys.stderr)
        return 2
    status = ticket_status(project_root, args.ticket)
    if status != "approved":
        print(f"ERROR: ticket {args.ticket} is `{status}`, not approved — apply refused", file=sys.stderr)
        return 2
    if platform == "google_ads" and not nested_get(ads, "google_ads.apply_enabled", False):
        print(
            "ERROR: ads.google_ads.apply_enabled is false. Import the Google Ads Editor CSV instead "
            "(seo/ads/drafts/*-google-ads-editor.csv) or enable apply after review.",
            file=sys.stderr,
        )
        return 2
    if platform != "yandex_direct":
        print(f"ERROR: live apply for `{platform}` is not implemented in v1", file=sys.stderr)
        return 2
    env = env_status(platform)
    if not env["present"]:
        print(f"ERROR: missing env: {', '.join(env['missing'])}", file=sys.stderr)
        return 2
    ok, message = ledger_preflight(project_root, platform, requests=len(operations))
    if not ok:
        print(f"ERROR: usage-ledger preflight blocked apply: {message}", file=sys.stderr)
        return 2

    sandbox = bool(nested_get(ads, "yandex_direct.sandbox", False))
    log.warning("APPLY start: %s operations to %s (sandbox=%s) ticket=%s",
                len(operations), platform, sandbox, args.ticket)
    results = apply_direct(operations, sandbox)
    applied = sum(1 for row in results if row["status"] == "ok")
    failed = sum(1 for row in results if row["status"] == "failed")
    ledger_record(project_root, platform, requests=len(operations),
                  note=f"apply ticket {args.ticket}: {applied} ok, {failed} failed")
    notify(project_root,
           f"Ads apply ({platform}{', sandbox' if sandbox else ''}): {applied} ok, {failed} failed,"
           f" ticket {args.ticket}")

    report = {"mode": "applied", "platform": platform, "sandbox": sandbox,
              "ticket": args.ticket, "applied": applied, "failed": failed, "results": results}
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json"
          else f"applied: {applied}, failed: {failed} (ticket {args.ticket}, sandbox={sandbox})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
