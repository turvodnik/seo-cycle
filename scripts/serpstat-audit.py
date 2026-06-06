#!/usr/bin/env python3
"""Guarded Serpstat Site Audit/API adapter.

By default this script does not call Serpstat. Live calls require --live and
SERPSTAT_API_KEY because project creation consumes project credits and audit
start consumes checked-page credits.
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


SERPSTAT_ENDPOINT = "https://api.serpstat.com/v4/"
ENV_NAME = "SERPSTAT_API_KEY"


def load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(pathlib.Path(path).expanduser().read_text(encoding="utf-8"))


def int_or_zero(value: str | int | None) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def planned_request(args: argparse.Namespace, cfg: dict[str, Any]) -> dict[str, Any]:
    domain = args.domain or nested_get(cfg, "project.domain")
    if args.action == "projects":
        return {"method": "ProjectProcedure.getProjects", "params": {"page": args.page, "size": args.size}}
    if args.action == "create-project":
        groups = [{"name": args.group}] if args.group else []
        return {"method": "ProjectProcedure.createProject", "params": {"domain": domain, "name": args.project_name or domain, "groups": groups}}
    if args.action == "start":
        return {"method": "AuditSite.start", "params": {"projectId": int_or_zero(args.project_id)}}
    if args.action == "stop":
        return {"method": "AuditSite.stop", "params": {"projectId": int_or_zero(args.project_id)}}
    if args.action in {"list", "poll"}:
        return {"method": "AuditSite.getList", "params": {"projectId": int_or_zero(args.project_id), "page": args.page, "size": args.size}}
    if args.action == "default-settings":
        return {"method": "AuditSite.getDefaultSettings", "params": {}}
    if args.action == "settings":
        return {"method": "AuditSite.getSettings", "params": {"projectId": int_or_zero(args.project_id)}}
    if args.action == "set-settings":
        settings = load_json(args.settings_json) or {}
        return {"method": "AuditSite.setSettings", "params": {"projectId": int_or_zero(args.project_id), "settings": settings}}
    if args.action == "categories":
        return {"method": "AuditSite.getCategoriesStatistic", "params": {"reportId": int_or_zero(args.report_id)}}
    if args.action == "scan-urls":
        return {"method": "AuditSite.getScanUserUrlList", "params": {"projectId": int_or_zero(args.project_id)}}
    if args.action == "issue-report":
        return {"method": "AuditSite.getReportWithoutDetails", "params": {"reportId": int_or_zero(args.report_id)}}
    if args.action == "error-elements":
        params: dict[str, Any] = {"reportId": int_or_zero(args.report_id)}
        if args.issue_type:
            params["type"] = args.issue_type
        return {"method": "AuditSite.getErrorElements", "params": params}
    if args.action == "sub-elements":
        return {"method": "AuditSite.getSubElementsByCrc", "params": {"reportId": int_or_zero(args.report_id), "crc": args.crc or ""}}
    if args.action == "history-errors":
        return {"method": "AuditSite.getHistoryByCountError", "params": {"projectId": int_or_zero(args.project_id)}}
    if args.action == "export":
        return {"method": "AuditSite.export", "params": {"reportId": int_or_zero(args.report_id), "format": args.export_format}}
    return {"method": "AuditSite.getBasicInfo", "params": {"reportId": int_or_zero(args.report_id)}}


def request_warnings(request: dict[str, Any], action: str) -> list[str]:
    warnings: list[str] = []
    params = request.get("params") or {}
    if action == "create-project":
        warnings.append("Project creation requires 1 Serpstat project credit.")
        if not params.get("domain"):
            warnings.append("domain is required for project creation.")
    if action in {"start", "stop", "list", "poll", "settings", "set-settings", "scan-urls", "history-errors"}:
        if action == "start":
            warnings.append("Audit start consumes audit credits equal to checked pages.")
        if not params.get("projectId"):
            warnings.append(f"projectId is required for {action}.")
    if action == "set-settings" and not params.get("settings"):
        warnings.append("settings-json is required for set-settings.")
    if action in {"basic-info", "categories", "issue-report", "error-elements", "sub-elements", "export"} and not params.get("reportId"):
        warnings.append("reportId is required for audit report retrieval.")
    if action == "sub-elements" and not params.get("crc"):
        warnings.append("crc is required for sub-elements retrieval.")
    return warnings


def call_serpstat(token: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    url = f"{SERPSTAT_ENDPOINT}?token={token}"
    body = json.dumps({"id": 1, "method": method, "params": params, "jsonrpc": "2.0"}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"error": {"code": exc.code, "message": text[:1000]}}
        return payload


def result_node(payload: dict[str, Any], key: str) -> dict[str, Any]:
    node = payload.get(key, payload)
    if isinstance(node, dict):
        result = node.get("result", node)
        return result if isinstance(result, dict) else {"items": result}
    return {}


def category_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    node = payload.get("categories", payload)
    if isinstance(node, dict):
        rows = node.get("result", [])
        return rows if isinstance(rows, list) else []
    return []


def distill_serpstat(payload: dict[str, Any], action: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    basic = result_node(payload, "basic_info")
    categories = category_rows(payload)
    summary = {
        "action": action,
        "report_id": basic.get("reportId"),
        "sdo": basic.get("sdo"),
        "progress": basic.get("progress"),
        "checked_pages": basic.get("checkedPageCount"),
        "total_checked_urls": basic.get("totalCheckedPageCount"),
        "redirect_count": basic.get("redirectCount"),
        "high_count": basic.get("highCount", 0),
        "medium_count": basic.get("mediumCount", 0),
        "low_count": basic.get("lowCount", 0),
        "mode": "serpstat_api",
    }
    findings: list[dict[str, Any]] = []
    if int(summary.get("high_count") or 0) > 0:
        findings.append(
            {
                "id": "serpstat_high_priority_errors",
                "severity": "high",
                "message": f"Serpstat reports {summary['high_count']} high-priority technical errors.",
                "evidence": basic,
            }
        )
    if int(summary.get("redirect_count") or 0) > 0:
        findings.append(
            {
                "id": "serpstat_redirects_present",
                "severity": "medium",
                "message": f"Serpstat detected {summary['redirect_count']} redirects during crawl.",
                "evidence": {"redirectCount": summary["redirect_count"]},
            }
        )
    risky_categories = [
        row
        for row in categories
        if int(row.get("highCount") or 0) > 0 or int(row.get("mediumCount") or 0) > 0
    ]
    if risky_categories:
        findings.append(
            {
                "id": "serpstat_issue_categories_present",
                "severity": "medium",
                "message": f"{len(risky_categories)} Serpstat issue categories contain high/medium problems.",
                "evidence": risky_categories[:12],
            }
        )
    distillate = {
        "summary": summary,
        "categories": categories[:50],
        "top_findings": findings[:10],
        "citations": [
            "https://serpstat.com/api/project-creation/",
            "https://serpstat.com/api/510-audit-start-auditsitestart/",
            "https://serpstat.com/api/516-audit-basic-information-getbasicinfo/",
            "https://serpstat.com/api/534-issue-categories-statistics-getcategoriesstatistic/",
            "https://serpstat.com/blog/how-to-automate-searching-for-technical-issues-leave-all-your-work-to-our-api/",
        ],
    }
    return summary, findings, distillate


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    request = planned_request(args, cfg)
    warnings = request_warnings(request, args.action)
    raw_payload = load_json(args.input_json)
    token = os.environ.get(ENV_NAME, "")
    live_api_used = False

    if raw_payload is None and args.live and token and not warnings:
        response = call_serpstat(token, request["method"], request["params"])
        live_api_used = True
        raw_payload = {"response": response, "planned_request": request}
        if args.action == "basic-info" and args.with_categories and args.report_id:
            categories = call_serpstat(token, "AuditSite.getCategoriesStatistic", {"reportId": int(args.report_id)})
            raw_payload = {"basic_info": response, "categories": categories, "planned_request": request}

    if raw_payload is None:
        status = "guarded"
        summary = {"action": args.action, "mode": "guarded", "live_api_used": False, "warnings": len(warnings)}
        findings = [
            {
                "id": "serpstat_live_guard",
                "severity": "info",
                "message": "Live Serpstat API call skipped. Use --live with SERPSTAT_API_KEY after checking credits/budget.",
                "evidence": warnings or request,
            }
        ]
        distillate = {
            "summary": summary,
            "planned_request": request,
            "env_required": [ENV_NAME],
            "credit_policy": "Project creation consumes 1 project credit; audit start consumes checked-page credits.",
            "citations": [
                "https://serpstat.com/api/project-creation/",
                "https://serpstat.com/api/510-audit-start-auditsitestart/",
                "https://serpstat.com/api/516-audit-basic-information-getbasicinfo/",
                "https://serpstat.com/blog/how-to-automate-searching-for-technical-issues-leave-all-your-work-to-our-api/",
            ],
        }
        raw_payload = {"planned_request": request, "warnings": warnings, "token_present": bool(token)}
    else:
        status = "ready"
        summary, findings, distillate = distill_serpstat(raw_payload, args.action)

    report = write_technical_report(
        project_root,
        slug="serpstat-audit",
        provider="serpstat",
        title="Serpstat Technical Site Audit Adapter",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload=raw_payload,
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "SERPSTAT_API_KEY=*** python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action projects --live --write",
            "SERPSTAT_API_KEY=*** python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action start --project-id 123 --live --write",
            "SERPSTAT_API_KEY=*** python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action set-settings --project-id 123 --settings-json serpstat-settings.json --live --write",
            "SERPSTAT_API_KEY=*** python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action issue-report --report-id 456 --live --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --input-json serpstat-basic-info.json --write",
        ],
        notes=["No API token value is written to reports. Live calls require explicit --live."],
        cache_parts={"slug": "serpstat-audit", "action": args.action, "request": request, "payload": raw_payload},
        paid_api_used=live_api_used,
    )
    report["live_api_used"] = live_api_used
    report["paid_api_used"] = live_api_used
    report["env_required"] = [ENV_NAME]
    report["planned_request"] = request
    report["warnings"] = warnings
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument(
        "--action",
        choices=(
            "projects",
            "create-project",
            "start",
            "stop",
            "list",
            "poll",
            "default-settings",
            "settings",
            "set-settings",
            "basic-info",
            "categories",
            "scan-urls",
            "issue-report",
            "error-elements",
            "sub-elements",
            "history-errors",
            "export",
        ),
        default="basic-info",
    )
    parser.add_argument("--input-json", help="Previously exported Serpstat JSON payload.")
    parser.add_argument("--live", action="store_true", help="Call Serpstat API. Requires SERPSTAT_API_KEY and may spend credits.")
    parser.add_argument("--domain", help="Domain for create-project.")
    parser.add_argument("--project-name", help="Project name for create-project.")
    parser.add_argument("--group", help="Project group name for create-project.")
    parser.add_argument("--project-id", help="Serpstat project id for audit actions.")
    parser.add_argument("--report-id", help="Serpstat report id for report actions.")
    parser.add_argument("--settings-json", help="JSON settings payload for AuditSite.setSettings.")
    parser.add_argument("--issue-type", help="Issue/check type for AuditSite.getErrorElements.")
    parser.add_argument("--crc", help="CRC identifier for AuditSite.getSubElementsByCrc.")
    parser.add_argument("--export-format", default="csv", choices=("csv", "xls", "xlsx"), help="Export format for AuditSite.export.")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--with-categories", action="store_true", help="For basic-info live calls, also fetch category statistics.")
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
        print(f"Serpstat audit status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
