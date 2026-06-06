#!/usr/bin/env python3
"""Labrika readiness/health check.

Labrika is useful as a third-party technical audit source, but public API
automation is not assumed. This health check records the safe workflow and the
support questions needed before enabling live API collection.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.technical_artifacts import write_technical_report


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    domain = args.domain or nested_get(cfg, "project.domain") or ""
    summary = {
        "domain": domain,
        "api_status": "not_confirmed",
        "supported_mode": "manual_or_browser_export",
        "live_api_used": False,
        "mode": "labrika_health",
    }
    findings: list[dict[str, Any]] = [
        {
            "id": "labrika_api_not_confirmed",
            "severity": "info",
            "message": "No confirmed public Labrika API contract is configured. Use manual/browser export ingestion until Labrika support confirms API/export/webhook details.",
            "evidence": {
                "support_questions": [
                    "Is there a public API for creating projects?",
                    "Is there a public API for starting scheduled audits?",
                    "Can technical issue reports be exported via API/webhook?",
                    "What are rate limits, paid limits, and authentication format?",
                ]
            },
        }
    ]
    distillate = {
        "summary": summary,
        "top_findings": findings,
        "next_commands": [
            "python3 ~/.codex/skills/seo-cycle/scripts/labrika-source-pack.py seo-cycle.yaml --export-file labrika-export.md --write",
        ],
        "citations": ["https://labrika.com/seo-auditor"],
        "support_questions": findings[0]["evidence"]["support_questions"],
    }
    report = write_technical_report(
        project_root,
        slug="labrika-health",
        provider="labrika",
        title="Labrika Health and API Readiness",
        status="needs_input",
        summary=summary,
        findings=findings,
        raw_payload={"provider": "labrika", "domain": domain, "api_status": "not_confirmed"},
        distillate_payload=distillate,
        write=args.write,
        commands=distillate["next_commands"],
        notes=["This script intentionally does not perform live Labrika calls."],
        cache_parts={"slug": "labrika-health", "domain": domain},
        paid_api_used=False,
    )
    report["api_status"] = "not_confirmed"
    report["live_api_used"] = False
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--domain", help="Domain to include in support/readiness notes.")
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
        print(f"Labrika health status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
