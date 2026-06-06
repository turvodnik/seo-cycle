#!/usr/bin/env python3
"""Report-only readiness check for optional technical SEO MCP servers."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.technical_artifacts import write_technical_report


MCP_TARGETS = {
    "mcp_gsc": {
        "names": ["mcp-gsc", "gsc", "google_search_console", "search-console"],
        "label": "Google Search Console MCP",
        "purpose": "read-only GSC/URL inspection question answering",
        "env": ["GOOGLE_APPLICATION_CREDENTIALS", "GSC_SITE_URL"],
        "citation": "https://github.com/AminForou/mcp-gsc",
    },
    "ga_mcp": {
        "names": ["google-analytics", "google_analytics", "analyticsdata", "ga4"],
        "label": "Google Analytics MCP",
        "purpose": "read-only GA4 reporting where policy allows analytics",
        "env": ["GOOGLE_APPLICATION_CREDENTIALS", "GA4_PROPERTY_ID"],
        "citation": "https://developers.google.com/analytics/devguides/MCP",
    },
    "lighthouse_mcp": {
        "names": ["lighthouse-mcp", "lighthouse_mcp", "lighthouse"],
        "label": "Lighthouse MCP",
        "purpose": "local Lighthouse performance/CWV audits via MCP",
        "env": [],
        "citation": "https://github.com/danielsogl/lighthouse-mcp-server",
    },
}


def candidate_configs(project_root: pathlib.Path) -> list[pathlib.Path]:
    home = pathlib.Path.home()
    paths = [
        project_root / ".codex" / "config.toml",
        project_root / "codex.toml",
        home / ".codex" / "config.toml",
        home / ".config" / "codex" / "config.toml",
    ]
    return [path for path in paths if path.exists()]


def read_configs(paths: list[pathlib.Path]) -> dict[str, str]:
    contents: dict[str, str] = {}
    for path in paths:
        try:
            contents[str(path)] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            contents[str(path)] = ""
    return contents


def configured(target: dict[str, Any], contents: dict[str, str]) -> bool:
    haystack = "\n".join(contents.values()).lower()
    return any(name.lower() in haystack for name in target["names"])


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    contents = read_configs(candidate_configs(project_root))
    checks: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    for key, target in MCP_TARGETS.items():
        is_configured = configured(target, contents)
        checks[key] = {
            "configured": is_configured,
            "label": target["label"],
            "purpose": target["purpose"],
            "env": target["env"],
            "citation": target["citation"],
        }
        if not is_configured:
            findings.append(
                {
                    "id": f"{key}_not_configured",
                    "severity": "info",
                    "message": f"{target['label']} is not detected in Codex MCP config. This is optional; use JSON/export/CLI fallback until configured.",
                    "evidence": {"expected_names": target["names"], "env": target["env"]},
                }
            )
    if findings:
        findings.insert(
            0,
            {
                "id": "technical_mcp_servers_not_configured",
                "severity": "info",
                "message": "One or more optional technical SEO MCP servers are not configured; CLI/export adapters remain the default safe path.",
                "evidence": list(checks.keys()),
            },
        )
    summary = {
        "domain": nested_get(cfg, "project.domain") or "",
        "mcp_gsc_configured": checks["mcp_gsc"]["configured"],
        "ga_mcp_configured": checks["ga_mcp"]["configured"],
        "lighthouse_mcp_configured": checks["lighthouse_mcp"]["configured"],
        "configured_count": sum(1 for row in checks.values() if row["configured"]),
        "checked_config_files": len(contents),
        "mode": "technical_mcp_health",
    }
    status = "ready" if summary["configured_count"] == len(MCP_TARGETS) else "needs_input"
    distillate = {
        "summary": summary,
        "checks": checks,
        "top_findings": findings[:10],
        "fallbacks": [
            "gsc-url-inspection.py --input-json ...",
            "lighthouse-audit.py --input-json ...",
            "GA4 remains policy-gated; do not install foreign counters for RF projects unless explicitly allowed.",
        ],
        "citations": [target["citation"] for target in MCP_TARGETS.values()],
    }
    report = write_technical_report(
        project_root,
        slug="technical-mcp-health",
        provider="codex_mcp",
        title="Technical SEO MCP Health",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload={"config_files": list(contents.keys()), "checks": checks},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py seo-cycle.yaml --input-json gsc-url-inspection.json --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/lighthouse-audit.py seo-cycle.yaml --input-json lighthouse.json --write",
        ],
        notes=["This check does not install MCP servers and does not read or write secret values."],
        cache_parts={"slug": "technical-mcp-health", "checks": checks},
        paid_api_used=False,
    )
    report["mcp_checks"] = checks
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
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
        print(f"Technical MCP health status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
