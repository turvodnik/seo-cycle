#!/usr/bin/env python3
"""Run the full research-package repair layer and write an aggregate report."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from typing import Any

from research_package_repair_core import print_report, resolve_package, write_json, write_text
from seo_cycle_core.config import find_config, load_yaml, package_project_root
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("research-package-repair")


REPAIR_STEPS = (
    {
        "id": "semantic_core_clean",
        "script": "semantic-core-clean.py",
        "outputs": ["semantic-core.cleaned.csv", "semantic-core.rejected.csv"],
        "purpose": "Separate prompt/spam-like GSC rows from usable search queries.",
    },
    {
        "id": "semantic_core_resync",
        "script": "semantic-core-resync.py",
        "outputs": ["semantic-core.resynced.csv"],
        "purpose": "Align semantic-core cluster IDs and URLs with final architecture.",
    },
    {
        "id": "entity_map_sync",
        "script": "entity-map-sync.py",
        "outputs": ["entity-map.md"],
        "purpose": "Render entity-map.md from the canonical structured entity map.",
    },
    {
        "id": "google_nlp_aggregate",
        "script": "google-nlp-aggregate.py",
        "outputs": ["entity_coverage.jsonl"],
        "purpose": "Deduplicate and aggregate raw Google NLP entity output.",
    },
    {
        "id": "orphan_url_resolver",
        "script": "orphan-url-resolver.py",
        "outputs": ["content-plan.orphan-backlog.csv"],
        "purpose": "Turn referenced orphan URLs into backlog/remove-link decisions.",
    },
    {
        "id": "serp_validation_plan",
        "script": "serp-validation-plan.py",
        "outputs": ["serp-validation-plan.csv"],
        "purpose": "List missing SERP validation queries and decision fields.",
    },
    {
        "id": "spoke_opportunity_audit",
        "script": "spoke-opportunity-audit.py",
        "outputs": ["spoke-opportunities.csv"],
        "purpose": "Promote measured long-tail demand into phase-2 spokes.",
    },
    {
        "id": "entity_graph_quality",
        "script": "entity-graph-quality.py",
        "outputs": ["entity-graph-quality.json", "entity-graph-quality.md"],
        "purpose": "Check duplicate/orphan triplets and entity weight provenance.",
    },
)


def scripts_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def run_step(package: pathlib.Path, step: dict[str, Any], write: bool) -> dict[str, Any]:
    command = [sys.executable, str(scripts_dir() / step["script"]), str(package), "--format", "json"]
    if write:
        command.insert(-2, "--write")
    proc = subprocess.run(command, cwd=package, text=True, capture_output=True, check=False)
    log.info("repair step %s rc=%s", step["id"], proc.returncode)
    if proc.returncode != 0 and proc.stderr:
        log.warning("repair step %s stderr: %s", step["id"], proc.stderr[-500:])
    parsed: dict[str, Any] = {}
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            parsed = {"raw_stdout": proc.stdout[-2000:]}
    outputs = step.get("outputs", [])
    return {
        "id": step["id"],
        "script": step["script"],
        "purpose": step["purpose"],
        "command": " ".join(command),
        "returncode": proc.returncode,
        "status": "ok" if proc.returncode == 0 else "failed",
        "summary": parsed.get("summary", {}),
        "outputs": {name: (package / name).exists() for name in outputs},
        "stderr": proc.stderr[-4000:] if proc.stderr else "",
    }


def build_report(package: pathlib.Path, write: bool) -> dict[str, Any]:
    steps = [run_step(package, step, write) for step in REPAIR_STEPS]
    failed = [step for step in steps if step["status"] != "ok"]
    return {
        "script": "research-package-repair",
        "package": str(package),
        "summary": {
            "steps": len(steps),
            "completed_steps": len(steps) - len(failed),
            "failed_steps": len(failed),
        },
        "steps": steps,
        "outputs": {
            "json": "research-package-repair.json",
            "markdown": "research-package-repair.md",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Research Package Repair",
        "",
        f"- Package: `{report['package']}`",
        f"- Steps: `{report['summary']['steps']}`",
        f"- Completed: `{report['summary']['completed_steps']}`",
        f"- Failed: `{report['summary']['failed_steps']}`",
        "",
        "## Steps",
        "",
    ]
    for step in report["steps"]:
        lines.extend(
            [
                f"### {step['id']}",
                "",
                f"- Status: `{step['status']}`",
                f"- Script: `{step['script']}`",
                f"- Purpose: {step['purpose']}",
                f"- Command: `{step['command']}`",
                f"- Summary: `{json.dumps(step.get('summary', {}), ensure_ascii=False)}`",
                "",
            ]
        )
        if step.get("stderr"):
            lines.extend(["```text", step["stderr"], "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    write_json(package / "research-package-repair.json", report)
    write_text(package / "research-package-repair.md", render_markdown(report))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--write", action="store_true", help="Write repair artifacts and aggregate report")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    args = parser.parse_args()

    package = resolve_package(args.package)
    project_root = package_project_root(package)
    cfg_path = find_config(project_root)
    global log
    log = setup_logging("research-package-repair", project_root, load_yaml(cfg_path) if cfg_path else {})
    report = build_report(package, args.write)
    if args.write:
        write_outputs(package, report)
    print_report(report, args.format, render_markdown(report))
    return 1 if report["summary"]["failed_steps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
