#!/usr/bin/env python3
"""Audit project artifacts that can waste agent context tokens."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, policy_path, project_root_for, rel_path
from seo_cycle_core.reports import write_report_bundle


RAW_DIR_NAMES = {"raw", "browser-dumps", "browser_dumps", "logs", "transcripts"}
DISTILLATE_MARKERS = {"distillate", "distillates", "summary", "summaries"}


def token_policy(cfg: dict[str, Any]) -> dict[str, Any]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    policy = governance.get("token_policy", {}) if isinstance(governance.get("token_policy"), dict) else {}
    return {
        "raw_data_in_context": bool(policy.get("raw_data_in_context", False)),
        "distillate_max_lines": int(policy.get("distillate_max_lines", 220) or 220),
        "max_output_tokens_per_artifact": int(policy.get("max_output_tokens_per_artifact", 7000) or 7000),
        "max_raw_rows_loaded": int(policy.get("max_raw_rows_loaded", 200) or 200),
    }


def output_paths(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    return {
        "markdown": policy_path(cfg, project_root, "token_waste_audit_report", "seo/setup/token-waste-audit.md"),
        "json": policy_path(cfg, project_root, "token_waste_audit_json", "seo/setup/token-waste-audit.json"),
        "latest_markdown": policy_path(cfg, project_root, "latest_token_waste_audit", "seo/setup/latest-token-waste-audit.md"),
        "latest_json": policy_path(cfg, project_root, "latest_token_waste_audit_json", "seo/setup/latest-token-waste-audit.json"),
    }


def is_raw_path(path: pathlib.Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return bool(parts & RAW_DIR_NAMES)


def is_distillate_path(path: pathlib.Path) -> bool:
    lowered = "/".join(part.lower() for part in path.parts)
    return any(marker in lowered for marker in DISTILLATE_MARKERS)


def scan_project(project_root: pathlib.Path, policy: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seo_root = project_root / "seo"
    if not seo_root.exists():
        return findings
    max_distillate_lines = int(policy["distillate_max_lines"])
    max_artifact_chars = int(policy["max_output_tokens_per_artifact"]) * 4
    for path in seo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(project_root))
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if is_raw_path(path) and not policy["raw_data_in_context"] and size > 1024:
            findings.append(
                {
                    "id": "raw_artifact_present",
                    "severity": "medium",
                    "status": "needs_review",
                    "path": rel,
                    "bytes": size,
                    "message": "Raw artifact exists; keep it on disk and route agents to a distillate instead.",
                }
            )
        if is_distillate_path(path) and path.suffix.lower() in {".md", ".txt", ".csv"}:
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            if len(lines) > max_distillate_lines:
                findings.append(
                    {
                        "id": "distillate_too_long",
                        "severity": "medium",
                        "status": "needs_review",
                        "path": rel,
                        "lines": len(lines),
                        "message": f"Distillate exceeds {max_distillate_lines} lines; create top-N/latest-summary artifacts.",
                    }
                )
        if size > max_artifact_chars and not is_raw_path(path):
            findings.append(
                {
                    "id": "large_context_candidate",
                    "severity": "low",
                    "status": "observe",
                    "path": rel,
                    "bytes": size,
                    "message": "Large artifact may need a summary before loading into context.",
                }
            )
    return findings


def build_report(cfg_path: pathlib.Path) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    policy = token_policy(cfg)
    findings = scan_project(project_root, policy)
    return {
        "audit_id": "token_waste_audit",
        "title": "Token Waste Audit",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "token_policy": policy,
        "status": "needs_review" if findings else "ready",
        "findings": findings,
        "actions": [
            "Keep raw exports/logs/transcripts on disk and load only distillates into agent context.",
            "Create latest-summary.md/json for long distillates before downstream prompts.",
            "Prefer vector/JSONL records and top-N tables over full raw CSV/JSON payloads.",
        ],
        "paths": {key: str(path.relative_to(project_root)) for key, path in output_paths(cfg, project_root).items()},
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Token Waste Audit",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- raw_data_in_context: `{report['token_policy']['raw_data_in_context']}`",
        f"- distillate_max_lines: `{report['token_policy']['distillate_max_lines']}`",
        "",
        "## Findings",
    ]
    if report["findings"]:
        for finding in report["findings"]:
            lines.append(f"- `{finding['severity']}` `{finding['id']}` `{finding['path']}`: {finding['message']}")
    else:
        lines.append("- No token-waste findings in scanned project artifacts.")
    lines.extend(["", "## Actions"])
    lines.extend(f"- {action}" for action in report["actions"])
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], cfg_path: pathlib.Path) -> None:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    paths = {key: rel_path(project_root, path) for key, path in report["paths"].items()}
    write_report_bundle(paths, render_markdown(report), report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Report raw/large artifacts that can waste agent context tokens.")
    parser.add_argument("config", nargs="?", type=pathlib.Path, help="Path to seo-cycle.yaml. If omitted, search cwd.")
    parser.add_argument("--write", action="store_true", help="Write markdown/json reports under seo/setup.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()
    cfg_path = args.config or find_config(pathlib.Path.cwd())
    if not cfg_path:
        print("ERROR: seo-cycle.yaml not found", file=sys.stderr)
        return 2
    cfg_path = cfg_path.resolve()
    report = build_report(cfg_path)
    if args.write:
        write_report(report, cfg_path)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
