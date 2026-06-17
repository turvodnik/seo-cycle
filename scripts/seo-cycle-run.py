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


def package_output(package: str, *parts: str) -> str:
    return str(pathlib.Path(package, *parts))


def research_package_contracts(package: str) -> tuple[StageContract, ...]:
    root = skill_root()
    return (
        StageContract.from_mapping(
            {
                "id": "research_quality_gate",
                "title": "Research package quality gate",
                "required_inputs": [
                    package_output(package, "semantic-core.csv"),
                    package_output(package, "content-plan.csv"),
                    package_output(package, "final-clusters.md"),
                    package_output(package, "semantic-architecture-final.json"),
                    package_output(package, "entity-map.md"),
                    package_output(package, "entity-map.yaml"),
                ],
                "commands": [
                    [
                        sys.executable,
                        str(root / "scripts/research-package-quality.py"),
                        package,
                        "--write",
                        "--format",
                        "json",
                    ],
                ],
                "outputs": [
                    package_output(package, "research-package-quality.json"),
                    package_output(package, "research-package-action-plan.md"),
                ],
                "gate": {
                    "command": [
                        sys.executable,
                        str(root / "scripts/research-package-quality.py"),
                        package,
                        "--format",
                        "json",
                    ],
                },
                "repair_commands": [
                    [
                        sys.executable,
                        str(root / "scripts/research-package-repair.py"),
                        package,
                        "--write",
                        "--format",
                        "json",
                    ],
                ],
                "max_attempts": 5,
                "stop_conditions": [
                    "research-package-quality.py still returns fail after the repair loop.",
                    "Reviewed SERP evidence or required research artifacts are still missing.",
                ],
                "next_stage": "deep_page_briefs_v3",
            }
        ),
        StageContract.from_mapping(
            {
                "id": "deep_page_briefs_v3",
                "title": "Deep page briefs v3",
                "required_inputs": [
                    package_output(package, "research-package-quality.json"),
                ],
                "commands": [
                    [
                        sys.executable,
                        str(root / "scripts/page-outline-v3.py"),
                        package,
                        "--all-mvp",
                        "--write",
                        "--format",
                        "json",
                    ],
                ],
                "outputs": [
                    package_output(package, "copywriter-ready"),
                    package_output(package, "page-outlines-v3"),
                    package_output(package, "vector/page_outline_triplets.jsonl"),
                ],
                "gate": {},
                "repair_commands": [],
                "max_attempts": 0,
                "stop_conditions": [
                    "page-outline-v3.py did not generate copywriter-ready briefs or vector triplets.",
                ],
                "next_stage": "page_outline_quality_v3",
            }
        ),
        StageContract.from_mapping(
            {
                "id": "page_outline_quality_v3",
                "title": "Page outline quality v3",
                "required_inputs": [
                    package_output(package, "page-outlines-v3"),
                    package_output(package, "vector/page_outline_triplets.jsonl"),
                ],
                "commands": [
                    [
                        sys.executable,
                        str(root / "scripts/page-outline-quality.py"),
                        package,
                        "--version",
                        "v3",
                        "--write",
                        "--format",
                        "json",
                    ],
                ],
                "outputs": [
                    package_output(package, "page-outline-quality.json"),
                ],
                "gate": {
                    "command": [
                        sys.executable,
                        str(root / "scripts/page-outline-quality.py"),
                        package,
                        "--version",
                        "v3",
                        "--format",
                        "json",
                    ],
                },
                "repair_commands": [
                    [
                        sys.executable,
                        str(root / "scripts/page-outline-v3.py"),
                        package,
                        "--all-mvp",
                        "--write",
                        "--format",
                        "json",
                    ],
                ],
                "max_attempts": 5,
                "stop_conditions": [
                    "page-outline-quality.py --version v3 still fails after regenerating v3 briefs.",
                ],
            }
        ),
    )


def template_contracts(template: str, package: str) -> tuple[StageContract, ...]:
    if template == "research-package":
        return research_package_contracts(package)
    raise SystemExit(f"ERROR: unknown stage template: {template}")


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
    parser.add_argument("--stage-template", choices=("research-package",), help="Built-in stage contract template.")
    parser.add_argument("--package", default="seo/research-package", help="Research package path for --stage-template research-package.")
    parser.add_argument("--goal", help="Build a small built-in route/journey stage plan from a task goal.")
    parser.add_argument("--project-root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--write", action="store_true", help="Execute commands and write seo/orchestrator reports.")
    parser.add_argument("--approve", action="store_true", help="Allow approval-required stages to run after human approval.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.stage_file:
        contracts = load_stage_contracts(args.stage_file.expanduser().resolve(), args.stage_id)
    elif args.stage_template:
        contracts = template_contracts(args.stage_template, args.package)
        if args.stage_id:
            contracts = tuple(contract for contract in contracts if contract.id == args.stage_id)
            if not contracts:
                raise SystemExit(f"ERROR: stage id not found: {args.stage_id}")
    elif args.goal:
        contracts = builtin_goal_contracts(args.goal)
    else:
        raise SystemExit("ERROR: provide --stage-file, --stage-template, or --goal")

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
