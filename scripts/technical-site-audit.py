#!/usr/bin/env python3
"""Aggregate technical SEO evidence reports into one bounded rollup."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.technical_artifacts import severity_counts, write_technical_report


DEFAULT_SLUGS = [
    "link-audit",
    "redirect-map-audit",
    "lighthouse-audit",
    "gsc-url-inspection",
    "bing-url-inspection",
    "serpstat-audit",
    "labrika-source-pack",
    "labrika-health",
    "technical-mcp-health",
    "technical-guardrails-audit",
    "snippet-sitemap-audit",
    "ai-bot-access-check",
]


def load_report(project_root: pathlib.Path, slug: str) -> dict[str, Any] | None:
    base = project_root / "seo" / "technical"
    for path in (base / f"latest-{slug}.json", base / f"{slug}.json"):
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"audit_id": slug, "status": "invalid_json", "findings": [], "summary": {}, "path": str(path)}
            payload["path"] = str(path)
            return payload
    return None


def source_name(report: dict[str, Any]) -> str:
    return str(report.get("audit_id") or report.get("provider") or "technical-source")


def flatten_findings(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        source = source_name(report)
        for item in report.get("findings") or []:
            if not isinstance(item, dict):
                continue
            rows.append({**item, "source": source})
    return rows


def rollup_status(reports: list[dict[str, Any]], findings: list[dict[str, Any]]) -> str:
    if not reports:
        return "needs_input"
    counts = severity_counts(findings)
    if counts["critical"] or counts["high"]:
        return "attention_required"
    if counts["medium"]:
        return "review_recommended"
    return "ready"


def top_sources(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for report in reports:
        findings = report.get("findings") if isinstance(report.get("findings"), list) else []
        rows.append(
            {
                "audit_id": source_name(report),
                "provider": report.get("provider"),
                "status": report.get("status"),
                "severity_counts": report.get("severity_counts") or severity_counts(findings),
                "path": report.get("path"),
                "summary": report.get("summary") or {},
            }
        )
    return rows


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    slugs = args.source or DEFAULT_SLUGS
    reports = [report for slug in slugs if (report := load_report(project_root, slug))]
    missing = [slug for slug in slugs if not load_report(project_root, slug)]
    findings = flatten_findings(reports)
    counts = severity_counts(findings)
    status = rollup_status(reports, findings)
    domain = nested_get(cfg, "project.domain") or ""
    summary = {
        "domain": domain,
        "source_count": len(reports),
        "missing_sources": len(missing),
        "findings": len(findings),
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "mode": "technical_site_rollup",
    }

    rollup_findings: list[dict[str, Any]] = []
    if not reports:
        rollup_findings.append(
            {
                "id": "technical_sources_missing",
                "severity": "info",
                "message": "No technical source reports found. Run link-audit, Lighthouse, URL inspection or other technical collectors first.",
                "evidence": slugs,
            }
        )
    elif counts["critical"] or counts["high"]:
        rollup_findings.append(
            {
                "id": "technical_high_priority_findings_present",
                "severity": "high",
                "message": f"Technical evidence contains {counts['critical']} critical and {counts['high']} high findings.",
                "evidence": [item for item in findings if str(item.get("severity")).lower() in {"critical", "high"}][:12],
            }
        )
    if missing:
        rollup_findings.append(
            {
                "id": "technical_sources_not_collected",
                "severity": "low",
                "message": f"{len(missing)} optional technical sources have no latest report yet.",
                "evidence": missing[:20],
            }
        )

    source_rows = top_sources(reports)
    sources = [row["audit_id"] for row in source_rows]
    distillate = {
        "summary": summary,
        "sources": source_rows,
        "top_findings": findings[:30],
        "missing_sources": missing,
        "citations": [
            "https://developers.google.com/search/docs/fundamentals/seo-starter-guide",
            "https://www.bing.com/webmasters/help/webmaster-api-operations-0c9228b7",
            "https://github.com/JustinBeckwith/linkinator",
            "https://github.com/danielsogl/lighthouse-mcp-server",
        ],
    }
    report = write_technical_report(
        project_root,
        slug="technical-site-audit",
        provider="seo-cycle",
        title="Technical SEO Evidence Rollup",
        status=status,
        summary=summary,
        findings=rollup_findings,
        raw_payload={"reports": reports, "missing": missing},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/link-audit.py seo-cycle.yaml --input-json linkinator.json --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/lighthouse-audit.py seo-cycle.yaml --input-json lighthouse.json --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py seo-cycle.yaml --input-json gsc-url-inspection.json --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/bing-url-inspection.py seo-cycle.yaml --input-json bing-url-info.json --write",
        ],
        notes=["Aggregator is read-only and does not trigger live crawls/API calls."],
        cache_parts={"slug": "technical-site-audit", "sources": sources, "summary": summary},
        extra_payload={"sources": sources, "source_reports": source_rows, "missing_sources": missing},
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--source", action="append", help="Limit rollup to a specific audit slug; repeatable.")
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
        print(f"Technical site audit status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
