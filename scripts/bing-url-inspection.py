#!/usr/bin/env python3
"""Guarded Bing Webmaster URL information adapter.

Uses Bing Webmaster GetUrlInfo as the read-only technical URL inspection layer.
Default mode writes a planned request only; live calls require --live and
BING_WEBMASTER_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.technical_artifacts import write_technical_report


BASE_ENDPOINT = "https://ssl.bing.com/webmaster/api.svc/json/GetUrlInfo"
ENV_NAME = "BING_WEBMASTER_API_KEY"


def load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(pathlib.Path(path).expanduser().read_text(encoding="utf-8"))


def planned_request(args: argparse.Namespace, cfg: dict[str, Any]) -> dict[str, Any]:
    domain = nested_get(cfg, "project.domain") or ""
    url = args.url or (f"https://{domain}/" if domain else "")
    site_url = args.site_url or (f"https://{domain}/" if domain else "")
    public_query = urllib.parse.urlencode({"siteUrl": site_url, "url": url, "apikey": "***"})
    return {
        "method": "GET",
        "endpoint": f"{BASE_ENDPOINT}?{public_query}",
        "params": {"siteUrl": site_url, "url": url},
    }


def request_warnings(request_plan: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    params = request_plan.get("params") or {}
    if not params.get("url"):
        warnings.append("url is required for Bing GetUrlInfo.")
    if not params.get("siteUrl"):
        warnings.append("site-url is required and must match a verified Bing Webmaster site.")
    return warnings


def call_bing(api_key: str, request_plan: dict[str, Any]) -> dict[str, Any]:
    params = dict(request_plan.get("params") or {})
    params["apikey"] = api_key
    endpoint = f"{BASE_ENDPOINT}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(endpoint, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": {"code": exc.code, "message": text[:1000]}}


def url_info(payload: dict[str, Any]) -> dict[str, Any]:
    node = payload.get("d", payload)
    if isinstance(node, dict) and isinstance(node.get("GetUrlInfoResult"), dict):
        return node["GetUrlInfoResult"]
    return node if isinstance(node, dict) else {}


def int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def distill(payload: dict[str, Any], request_plan: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    info = url_info(payload)
    status = int_value(info.get("HttpStatus") or info.get("httpStatus"))
    params = request_plan.get("params") or {}
    summary = {
        "url": info.get("Url") or params.get("url"),
        "site_url": params.get("siteUrl"),
        "http_status": status,
        "is_page": bool(info.get("IsPage")) if info.get("IsPage") is not None else None,
        "anchor_count": int_value(info.get("AnchorCount")),
        "document_size": int_value(info.get("DocumentSize")),
        "last_crawled": info.get("LastCrawledDate"),
        "total_child_url_count": int_value(info.get("TotalChildUrlCount")),
        "mode": "bing_get_url_info",
    }
    findings: list[dict[str, Any]] = []
    if status is None:
        findings.append(
            {
                "id": "bing_http_status_missing",
                "severity": "medium",
                "message": "Bing URL info did not include HTTP status. Check API response or site verification.",
                "evidence": info,
            }
        )
    elif status >= 400:
        findings.append(
            {
                "id": "bing_url_returns_error",
                "severity": "high",
                "message": f"Bing reports HTTP {status} for the inspected URL.",
                "evidence": info,
            }
        )
    elif 300 <= status < 400:
        findings.append(
            {
                "id": "bing_url_redirects",
                "severity": "medium",
                "message": f"Bing reports HTTP {status}; replace internal links with final URLs where possible.",
                "evidence": info,
            }
        )
    if summary["is_page"] is False:
        findings.append(
            {
                "id": "bing_url_not_page",
                "severity": "medium",
                "message": "Bing does not classify this URL as a page.",
                "evidence": info,
            }
        )
    if not summary["last_crawled"]:
        findings.append(
            {
                "id": "bing_last_crawl_missing",
                "severity": "low",
                "message": "Bing response has no last crawl date. Check crawl discovery and sitemap inclusion.",
                "evidence": info,
            }
        )
    distillate = {
        "summary": summary,
        "top_findings": findings[:10],
        "url_info": info,
        "citations": [
            "https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi.geturlinfo",
            "https://www.bing.com/webmasters/help/webmaster-api-operations-0c9228b7",
        ],
    }
    return summary, findings, distillate


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    request_plan = planned_request(args, cfg)
    warnings = request_warnings(request_plan)
    raw_payload = load_json(args.input_json)
    api_key = os.environ.get(args.api_key_env or ENV_NAME, "")
    live_api_used = False

    if raw_payload is None and args.live and api_key and not warnings:
        raw_payload = {"response": call_bing(api_key, request_plan), "planned_request": request_plan}
        live_api_used = True

    if raw_payload is None:
        status = "guarded"
        summary = {"mode": "guarded", "live_api_used": False, "warnings": len(warnings), **(request_plan.get("params") or {})}
        findings = [
            {
                "id": "bing_url_inspection_live_guard",
                "severity": "info",
                "message": "Live Bing Webmaster GetUrlInfo skipped. Use --live with BING_WEBMASTER_API_KEY after confirming site access.",
                "evidence": warnings or request_plan,
            }
        ]
        distillate = {
            "summary": summary,
            "planned_request": request_plan,
            "env_required": [args.api_key_env or ENV_NAME],
            "citations": ["https://learn.microsoft.com/en-us/dotnet/api/microsoft.bing.webmaster.api.interfaces.iwebmasterapi.geturlinfo"],
        }
        raw_payload = {"planned_request": request_plan, "warnings": warnings, "api_key_present": bool(api_key)}
    else:
        status = "ready"
        summary, findings, distillate = distill(raw_payload, request_plan)

    report = write_technical_report(
        project_root,
        slug="bing-url-inspection",
        provider="bing_webmaster",
        title="Bing Webmaster URL Inspection Audit",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload=raw_payload,
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "BING_WEBMASTER_API_KEY=*** python3 ~/.codex/skills/seo-cycle/scripts/bing-url-inspection.py seo-cycle.yaml --url https://example.com/ --site-url https://example.com/ --live --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/bing-url-inspection.py seo-cycle.yaml --input-json bing-url-info.json --write",
        ],
        notes=["Read-only Bing Webmaster source. Does not submit or change URLs."],
        cache_parts={"slug": "bing-url-inspection", "request": request_plan, "payload": raw_payload},
        paid_api_used=False,
    )
    report["live_api_used"] = live_api_used
    report["paid_api_used"] = False
    report["env_required"] = [args.api_key_env or ENV_NAME]
    report["planned_request"] = request_plan
    report["warnings"] = warnings
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--url", help="URL to inspect.")
    parser.add_argument("--site-url", help="Verified Bing Webmaster site URL.")
    parser.add_argument("--input-json", help="Previously exported Bing GetUrlInfo JSON payload.")
    parser.add_argument("--live", action="store_true", help="Call Bing Webmaster API. Requires BING_WEBMASTER_API_KEY.")
    parser.add_argument("--api-key-env", default=ENV_NAME)
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
        print(f"Bing URL inspection status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
