#!/usr/bin/env python3
"""Run seo-cycle stage contracts with gate/repair/rerun control."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - JSON stage files still work
    yaml = None

from seo_cycle_core.orchestrator import run_stages
from seo_cycle_core.stages import StageContract


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def load_stage_payload(path: pathlib.Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        if yaml is None:
            raise SystemExit("ERROR: PyYAML is required for non-JSON stage files")
        data = yaml.safe_load(text)
    if isinstance(data, list):
        return {"stages": data}
    if not isinstance(data, dict):
        raise SystemExit("ERROR: stage file must contain a mapping or a list")
    return data


def load_stage_contracts(path: pathlib.Path, stage_id: str | None) -> tuple[StageContract, ...]:
    payload = load_stage_payload(path)
    raw_stages = payload.get("stages", [])
    if not isinstance(raw_stages, list):
        raise SystemExit("ERROR: stage file key `stages` must be a list")
    contracts = tuple(StageContract.from_mapping(row) for row in raw_stages)
    if stage_id:
        contracts = tuple(contract for contract in contracts if contract.id == stage_id)
        if not contracts:
            raise SystemExit(f"ERROR: stage id not found: {stage_id}")
    return contracts


def builtin_goal_contracts(goal: str) -> tuple[StageContract, ...]:
    root = skill_root()
    return (
        StageContract.from_mapping(
            {
                "id": "task_route",
                "title": "Task route",
                "commands": [
                    [sys.executable, str(root / "scripts/task-router.py"), "--task", goal, "--write"],
                ],
                "outputs": ["seo/setup/latest-task-route.json"],
                "gate": {},
                "repair_commands": [],
                "max_attempts": 0,
                "next_stage": "project_journey",
            }
        ),
        StageContract.from_mapping(
            {
                "id": "project_journey",
                "title": "Project journey",
                "commands": [
                    [
                        sys.executable,
                        str(root / "scripts/project-journey.py"),
                        "--goal",
                        goal,
                        "--write",
                        "--format",
                        "json",
                    ],
                ],
                "outputs": ["seo/setup/project-journey.json"],
                "gate": {
                    "command": [
                        sys.executable,
                        str(root / "scripts/project-journey.py"),
                        "--goal",
                        goal,
                        "--format",
                        "json",
                        "--fail-on-blocker",
                    ]
                },
                "repair_commands": [
                    [
                        sys.executable,
                        str(root / "scripts/setup-control-plane.py"),
                        "--task",
                        goal,
                        "--write",
                        "--skip-intake",
                    ],
                ],
                "max_attempts": 1,
                "stop_conditions": ["Current project journey stage remains blocked after setup-control-plane refresh."],
            }
        ),
    )


def planned_report(contracts: tuple[StageContract, ...]) -> dict[str, Any]:
    return {
        "status": "planned",
        "write_required": True,
        "stages": [contract.to_mapping() for contract in contracts],
    }


def render_planned(report: dict[str, Any]) -> str:
    lines = [
        "# seo-cycle orchestrator plan",
        "",
        "- Status: `planned`",
        "- Run with `--write` to execute stage commands.",
        "",
        "## Stages",
    ]
    for stage in report.get("stages", []):
        lines.append(f"- `{stage['id']}`: {stage['title']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-file", type=pathlib.Path, help="JSON/YAML stage contract file.")
    parser.add_argument("--stage-id", help="Run only one stage from --stage-file.")
    parser.add_argument("--goal", help="Build a small built-in route/journey stage plan from a task goal.")
    parser.add_argument("--project-root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--write", action="store_true", help="Execute commands and write seo/orchestrator reports.")
    parser.add_argument("--approve", action="store_true", help="Allow approval-required stages to run after human approval.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.stage_file:
        contracts = load_stage_contracts(args.stage_file.expanduser().resolve(), args.stage_id)
    elif args.goal:
        contracts = builtin_goal_contracts(args.goal)
    else:
        raise SystemExit("ERROR: provide --stage-file or --goal")

    cwd = args.project_root.expanduser().resolve()
    if not args.write:
        report = planned_report(contracts)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render_planned(report), end="")
        return 0

    report = run_stages(contracts, cwd=cwd, write_report=True, approve=args.approve)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        from seo_cycle_core.orchestrator import render_run_markdown

        print(render_run_markdown(report), end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
