#!/usr/bin/env python3
"""Render a read-only panel from seo-cycle orchestrator run reports."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, project_root_for, rel_display, rel_path, write_text


BLOCKED_ACTIONS = [
    "paid_api",
    "browser_action",
    "publishing",
    "indexing_submission",
    "schedule_install",
    "secret_write",
]


def load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def resolve_project_root(raw: pathlib.Path | None) -> pathlib.Path:
    if raw:
        return raw.expanduser().resolve()
    found = find_config(pathlib.Path.cwd())
    return project_root_for(found.resolve()) if found else pathlib.Path.cwd().resolve()


def resolve_report_path(project_root: pathlib.Path, raw: str | pathlib.Path) -> pathlib.Path:
    return rel_path(project_root, raw)


def summarize_stage(stage: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    paths = stage.get("paths", {}) if isinstance(stage.get("paths"), dict) else {}
    summary = {
        "id": stage.get("id"),
        "title": stage.get("title"),
        "status": stage.get("status"),
        "gate_attempts": stage.get("gate_attempts", 0),
        "repair_attempts": stage.get("repair_attempts", 0),
        "missing_inputs": stage.get("missing_inputs", []) if isinstance(stage.get("missing_inputs"), list) else [],
        "missing_outputs": stage.get("missing_outputs", []) if isinstance(stage.get("missing_outputs"), list) else [],
        "stop_conditions": stage.get("stop_conditions", []) if isinstance(stage.get("stop_conditions"), list) else [],
        "next_stage": stage.get("next_stage"),
        "report_json": None,
        "report_markdown": None,
        "blocker_json": None,
        "blocker_markdown": None,
    }
    for key in ("report_json", "report_markdown", "blocker_json", "blocker_markdown"):
        if paths.get(key):
            summary[key] = rel_display(project_root, resolve_report_path(project_root, paths[key]))
    return summary


def blocker_path_for(stage: dict[str, Any], project_root: pathlib.Path) -> pathlib.Path:
    paths = stage.get("paths", {}) if isinstance(stage.get("paths"), dict) else {}
    if paths.get("blocker_json"):
        return resolve_report_path(project_root, paths["blocker_json"])
    return project_root / "seo" / "orchestrator" / f"{stage.get('id')}-blocker.json"


def summarize_blocker(stage: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    path = blocker_path_for(stage, project_root)
    blocker = load_json(path) if path.exists() else {}
    source = blocker or stage
    last_gate = source.get("last_gate", {}) if isinstance(source.get("last_gate"), dict) else {}
    return {
        "stage_id": source.get("stage_id") or source.get("id"),
        "title": source.get("title"),
        "status": source.get("status"),
        "repair_attempts": source.get("repair_attempts", 0),
        "gate_attempts": source.get("gate_attempts", 0),
        "missing_inputs": source.get("missing_inputs", []) if isinstance(source.get("missing_inputs"), list) else [],
        "missing_outputs": source.get("missing_outputs", []) if isinstance(source.get("missing_outputs"), list) else [],
        "stop_conditions": source.get("stop_conditions", []) if isinstance(source.get("stop_conditions"), list) else [],
        "last_gate_passed": last_gate.get("passed") if "passed" in last_gate else None,
        "path": rel_display(project_root, path),
    }


def stage_counts(stages: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"passed": 0, "blocked": 0, "approval_required": 0, "other": 0}
    for stage in stages:
        status = str(stage.get("status") or "")
        if status in counts:
            counts[status] += 1
        else:
            counts["other"] += 1
    return counts


def build_panel(project_root: pathlib.Path, run_json: pathlib.Path) -> dict[str, Any]:
    run = load_json(run_json)
    raw_stages = run.get("stages", []) if isinstance(run.get("stages"), list) else []
    stages = [summarize_stage(stage, project_root) for stage in raw_stages if isinstance(stage, dict)]
    current_stage = next((stage for stage in stages if stage.get("status") != "passed"), stages[-1] if stages else None)
    blocker_stages = [
        stage
        for stage in raw_stages
        if isinstance(stage, dict) and stage.get("status") in {"blocked", "approval_required"}
    ]
    counts = stage_counts(stages)
    return {
        "status": run.get("status"),
        "generated_at": run.get("generated_at"),
        "run_json": rel_display(project_root, run_json),
        "execution_enabled": False,
        "summary": {
            "completed": run.get("completed", counts["passed"]),
            "total": run.get("total", len(stages)),
            **counts,
        },
        "current_stage": current_stage,
        "stages": stages,
        "blockers": [summarize_blocker(stage, project_root) for stage in blocker_stages],
        "next_reads": next_reads(current_stage),
        "safety": {
            "mode": "read_only",
            "blocked_actions": BLOCKED_ACTIONS,
            "note": "This panel reads orchestrator reports only. Run stage commands through seo-cycle-run.py after reviewing gates.",
        },
    }


def next_reads(current_stage: dict[str, Any] | None) -> list[str]:
    if not current_stage:
        return ["seo/orchestrator/latest-run.json"]
    reads = ["seo/orchestrator/latest-run.json"]
    if current_stage.get("report_markdown"):
        reads.append(str(current_stage["report_markdown"]))
    if current_stage.get("blocker_markdown"):
        reads.append(str(current_stage["blocker_markdown"]))
    return reads


def render_markdown(panel: dict[str, Any]) -> str:
    summary = panel.get("summary", {})
    current = panel.get("current_stage") or {}
    lines = [
        "# seo-cycle orchestrator panel",
        "",
        f"- Status: `{panel.get('status')}`",
        f"- Completed: `{summary.get('completed')}` / `{summary.get('total')}`",
        f"- Generated: {panel.get('generated_at')}",
        "- Execution: read-only",
        f"- Current stage: `{current.get('id') or '-'}` ({current.get('status') or '-'})",
        "",
        "## Stages",
        "| Stage | Status | Gates | Repairs | Missing outputs |",
        "| --- | --- | --- | --- | --- |",
    ]
    for stage in panel.get("stages", []):
        missing = ", ".join(stage.get("missing_outputs", [])) or "-"
        lines.append(
            f"| `{stage.get('id')}` | `{stage.get('status')}` | "
            f"{stage.get('gate_attempts')} | {stage.get('repair_attempts')} | {missing} |"
        )
    lines.extend(["", "## Blockers"])
    blockers = panel.get("blockers", [])
    if blockers:
        for blocker in blockers:
            lines.append(f"- `{blocker.get('stage_id')}`: {', '.join(blocker.get('stop_conditions', [])) or 'review blocker report'}")
            if blocker.get("path"):
                lines.append(f"  - Report: `{blocker['path']}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Next Reads"])
    lines.extend(f"- `{item}`" for item in panel.get("next_reads", []))
    lines.extend(["", "## Safety"])
    lines.append("- This panel never executes stage commands.")
    lines.append(f"- Blocked actions: {', '.join(panel.get('safety', {}).get('blocked_actions', []))}")
    return "\n".join(lines) + "\n"


def write_panel(project_root: pathlib.Path, panel: dict[str, Any]) -> None:
    out_dir = project_root / "seo" / "orchestrator"
    write_text(out_dir / "panel.md", render_markdown(panel))
    write_text(out_dir / "panel.json", json.dumps(panel, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=pathlib.Path, help="Project root. Defaults to cwd/config root.")
    parser.add_argument("--run-json", type=pathlib.Path, help="Run report JSON. Defaults to seo/orchestrator/latest-run.json.")
    parser.add_argument("--write", action="store_true", help="Write seo/orchestrator/panel.md/json.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.project_root)
    run_json = resolve_report_path(project_root, args.run_json or "seo/orchestrator/latest-run.json")
    try:
        panel = build_panel(project_root, run_json)
    except FileNotFoundError:
        print(f"ERROR: orchestrator run report not found: {run_json}", file=sys.stderr)
        return 2
    if args.write:
        write_panel(project_root, panel)
    if args.format == "json":
        print(json.dumps(panel, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(panel), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
