#!/usr/bin/env python3
"""Guarded Google Search Console URL Inspection adapter.

Default mode is report-only. Live calls require --live and an OAuth access
token in GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN. Token values are never written to
reports.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.technical_artifacts import write_technical_report


ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
ENV_NAME = "GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN"


def load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(pathlib.Path(path).expanduser().read_text(encoding="utf-8"))


def planned_request(args: argparse.Namespace, cfg: dict[str, Any]) -> dict[str, Any]:
    domain = nested_get(cfg, "project.domain") or ""
    url = args.url or (f"https://{domain}/" if domain else "")
    site_url = args.site_url or (f"sc-domain:{domain}" if domain else "")
    body = {"inspectionUrl": url, "siteUrl": site_url}
    if args.language_code:
        body["languageCode"] = args.language_code
    return {"method": "POST", "endpoint": ENDPOINT, "body": body}


def request_warnings(request: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    body = request.get("body") or {}
    if not body.get("inspectionUrl"):
        warnings.append("url is required for URL Inspection.")
    if not body.get("siteUrl"):
        warnings.append("site-url is required and must match a verified Search Console property.")
    return warnings


def call_gsc(token: str, request_plan: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(request_plan["body"], ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        request_plan["endpoint"],
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": {"code": exc.code, "message": text[:1000]}}


def inspection_result(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("inspectionResult"), dict):
        return payload["inspectionResult"]
    response = payload.get("response")
    if isinstance(response, dict) and isinstance(response.get("inspectionResult"), dict):
        return response["inspectionResult"]
    return {}


def distill(payload: dict[str, Any], request_plan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    result = inspection_result(payload)
    index = result.get("indexStatusResult") or {}
    mobile = result.get("mobileUsabilityResult") or {}
    rich = result.get("richResultsResult") or {}
    rich_items = rich.get("detectedItems") or []
    body = request_plan.get("body") or {}
    summary = {
        "url": body.get("inspectionUrl"),
        "site_url": body.get("siteUrl"),
        "index_verdict": index.get("verdict"),
        "coverage_state": index.get("coverageState"),
        "robots_txt_state": index.get("robotsTxtState"),
        "indexing_state": index.get("indexingState"),
        "page_fetch_state": index.get("pageFetchState"),
        "google_canonical": index.get("googleCanonical"),
        "user_canonical": index.get("userCanonical"),
        "last_crawl_time": index.get("lastCrawlTime"),
        "mobile_verdict": mobile.get("verdict"),
        "rich_results_verdict": rich.get("verdict"),
        "rich_results_items": len(rich_items) if isinstance(rich_items, list) else 0,
        "mode": "gsc_url_inspection",
    }
    findings: list[dict[str, Any]] = []
    if summary["index_verdict"] and summary["index_verdict"] != "PASS":
        findings.append(
            {
                "id": "gsc_index_verdict_not_pass",
                "severity": "high",
                "message": f"Google URL Inspection verdict is {summary['index_verdict']}. Check coverage, robots and canonical signals.",
                "evidence": index,
            }
        )
    if summary["robots_txt_state"] and summary["robots_txt_state"] != "ALLOWED":
        findings.append(
            {
                "id": "gsc_robots_blocks_google",
                "severity": "high",
                "message": f"Google reports robots.txt state {summary['robots_txt_state']}.",
                "evidence": index,
            }
        )
    if summary["page_fetch_state"] and summary["page_fetch_state"] not in {"SUCCESSFUL", "PAGE_FETCH_STATE_UNSPECIFIED"}:
        findings.append(
            {
                "id": "gsc_page_fetch_not_successful",
                "severity": "high",
                "message": f"Google page fetch state is {summary['page_fetch_state']}.",
                "evidence": index,
            }
        )
    if summary["google_canonical"] and summary["user_canonical"] and summary["google_canonical"] != summary["user_canonical"]:
        findings.append(
            {
                "id": "gsc_canonical_mismatch",
                "severity": "medium",
                "message": "Google-selected canonical differs from user canonical.",
                "evidence": {"google": summary["google_canonical"], "user": summary["user_canonical"]},
            }
        )
    if summary["mobile_verdict"] and summary["mobile_verdict"] != "PASS":
        findings.append(
            {
                "id": "gsc_mobile_usability_not_pass",
                "severity": "medium",
                "message": f"Google mobile usability verdict is {summary['mobile_verdict']}.",
                "evidence": mobile,
            }
        )
    distillate = {
        "summary": summary,
        "top_findings": findings[:10],
        "inspection_result_link": result.get("inspectionResultLink"),
        "rich_results_items": rich_items[:20] if isinstance(rich_items, list) else [],
        "citations": [
            "https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect",
        ],
    }
    return summary, findings, distillate


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    request_plan = planned_request(args, cfg)
    warnings = request_warnings(request_plan)
    raw_payload = load_json(args.input_json)
    token = os.environ.get(args.access_token_env or ENV_NAME, "")
    live_api_used = False

    if raw_payload is None and args.live and token and not warnings:
        raw_payload = {"response": call_gsc(token, request_plan), "planned_request": request_plan}
        live_api_used = True

    if raw_payload is None:
        status = "guarded"
        summary = {"mode": "guarded", "live_api_used": False, "warnings": len(warnings), **request_plan["body"]}
        findings = [
            {
                "id": "gsc_url_inspection_live_guard",
                "severity": "info",
                "message": "Live Google URL Inspection skipped. Use --live with GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN after confirming property access.",
                "evidence": warnings or request_plan,
            }
        ]
        distillate = {
            "summary": summary,
            "planned_request": request_plan,
            "env_required": [args.access_token_env or ENV_NAME],
            "citations": ["https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect"],
        }
        raw_payload = {"planned_request": request_plan, "warnings": warnings, "token_present": bool(token)}
    else:
        status = "ready"
        summary, findings, distillate = distill(raw_payload, request_plan)

    report = write_technical_report(
        project_root,
        slug="gsc-url-inspection",
        provider="google_search_console",
        title="Google URL Inspection Audit",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload=raw_payload,
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN=*** python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py seo-cycle.yaml --url https://example.com/ --site-url sc-domain:example.com --live --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py seo-cycle.yaml --input-json gsc-url-inspection.json --write",
        ],
        notes=["Read-only. Does not request indexing or publish anything."],
        cache_parts={"slug": "gsc-url-inspection", "request": request_plan, "payload": raw_payload},
        paid_api_used=False,
    )
    report["live_api_used"] = live_api_used
    report["paid_api_used"] = False
    report["env_required"] = [args.access_token_env or ENV_NAME]
    report["planned_request"] = request_plan
    report["warnings"] = warnings
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--url", help="URL to inspect.")
    parser.add_argument("--site-url", help="Verified Search Console property, e.g. sc-domain:example.com or https://example.com/.")
    parser.add_argument("--language-code", default="en-US")
    parser.add_argument("--input-json", help="Previously exported URL Inspection JSON payload.")
    parser.add_argument("--live", action="store_true", help="Call Google URL Inspection API. Requires OAuth token.")
    parser.add_argument("--access-token-env", default=ENV_NAME)
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
        print(f"GSC URL Inspection status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
