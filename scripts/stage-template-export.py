#!/usr/bin/env python3
"""Write project-local seo-cycle stage contract templates."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - JSON is valid YAML fallback
    yaml = None

from seo_cycle_core.config import find_config, project_root_for, write_text


LOCAL_SCRIPT_ROOT = "./.codex/skills/seo-cycle/scripts"


def command(script: str, *args: str) -> list[str]:
    return ["python3", f"{LOCAL_SCRIPT_ROOT}/{script}", *args]


def setup_readiness_payload() -> dict[str, Any]:
    task = "first SEO setup"
    return {
        "stages": [
            {
                "id": "setup_control_plane",
                "title": "Setup control plane readiness",
                "required_inputs": ["seo-cycle.yaml"],
                "commands": [
                    command("setup-control-plane.py", "--task", task, "--write"),
                ],
                "outputs": [
                    "seo/setup/setup-control-plane.json",
                    "seo/setup/project-journey.json",
                    "seo/setup/setup-gap-audit.json",
                    "seo/setup/latest-task-route.json",
                ],
                "gate": {
                    "command": command(
                        "project-journey.py",
                        "--goal",
                        task,
                        "--format",
                        "json",
                        "--fail-on-blocker",
                    ),
                    "pass_codes": [0],
                },
                "repair_commands": [
                    command(
                        "setup-control-plane.py",
                        "--task",
                        task,
                        "--write",
                        "--skip-intake",
                        "--skip-automation",
                    ),
                ],
                "max_attempts": 1,
                "approval_required": False,
                "stop_conditions": [
                    "project-journey.py --fail-on-blocker still reports a blocked current stage after setup refresh.",
                    "Human setup questionnaire fields, missing access, or approval gates must be resolved manually.",
                ],
                "next_stage": "approved_task_route",
            }
        ]
    }


def research_package_payload() -> dict[str, Any]:
    package = "seo/research-package"
    return {
        "stages": [
            {
                "id": "research_quality_gate",
                "title": "Research package quality gate",
                "required_inputs": [
                    f"{package}/semantic-core.csv",
                    f"{package}/content-plan.csv",
                    f"{package}/final-clusters.md",
                    f"{package}/semantic-architecture-final.json",
                    f"{package}/entity-map.md",
                    f"{package}/entity-map.yaml",
                ],
                "commands": [
                    command("research-package-quality.py", package, "--write", "--format", "json"),
                ],
                "outputs": [
                    f"{package}/research-package-quality.json",
                    f"{package}/research-package-action-plan.md",
                ],
                "gate": {
                    "command": command("research-package-quality.py", package, "--format", "json"),
                    "pass_codes": [0],
                },
                "repair_commands": [
                    command("research-package-repair.py", package, "--write", "--format", "json"),
                ],
                "max_attempts": 5,
                "approval_required": False,
                "stop_conditions": [
                    "research-package-quality.py still returns fail after the repair loop.",
                    "Reviewed SERP evidence or required research artifacts are still missing.",
                ],
                "next_stage": "deep_page_briefs_v3",
            },
            {
                "id": "deep_page_briefs_v3",
                "title": "Deep page briefs v3",
                "required_inputs": [f"{package}/research-package-quality.json"],
                "commands": [
                    command("page-outline-v3.py", package, "--all-mvp", "--write", "--format", "json"),
                ],
                "outputs": [
                    f"{package}/copywriter-ready",
                    f"{package}/page-outlines-v3",
                    f"{package}/vector/page_outline_triplets.jsonl",
                ],
                "gate": {},
                "repair_commands": [],
                "max_attempts": 0,
                "approval_required": False,
                "stop_conditions": [
                    "page-outline-v3.py did not generate copywriter-ready briefs or vector triplets.",
                ],
                "next_stage": "page_outline_quality_v3",
            },
            {
                "id": "page_outline_quality_v3",
                "title": "Page outline quality v3",
                "required_inputs": [
                    f"{package}/page-outlines-v3",
                    f"{package}/vector/page_outline_triplets.jsonl",
                ],
                "commands": [
                    command("page-outline-quality.py", package, "--version", "v3", "--write", "--format", "json"),
                ],
                "outputs": [f"{package}/page-outline-quality.json"],
                "gate": {
                    "command": command("page-outline-quality.py", package, "--version", "v3", "--format", "json"),
                    "pass_codes": [0],
                },
                "repair_commands": [
                    command("page-outline-v3.py", package, "--all-mvp", "--write", "--format", "json"),
                ],
                "max_attempts": 5,
                "approval_required": False,
                "stop_conditions": [
                    "page-outline-quality.py --version v3 still fails after regenerating v3 briefs.",
                ],
                "next_stage": None,
            },
        ]
    }


def copywriting_payload() -> dict[str, Any]:
    draft = "seo/research-package/drafts/sample.md"
    outline = "seo/research-package/page-outlines-v3/sample.json"
    return {
        "stages": [
            {
                "id": "draft_quality_gate",
                "title": "Draft quality gate",
                "required_inputs": [draft, outline],
                "commands": [
                    command(
                        "draft-quality-gate.py",
                        draft,
                        "--outline",
                        outline,
                        "--write",
                        "--format",
                        "json",
                        "--fail-on-error",
                    ),
                ],
                "outputs": [
                    "seo/research-package/drafts/sample.draft-quality-gate.json",
                    "seo/research-package/drafts/sample.draft-quality-gate.md",
                ],
                "gate": {
                    "command": command(
                        "draft-quality-gate.py",
                        draft,
                        "--outline",
                        outline,
                        "--format",
                        "json",
                        "--fail-on-error",
                    ),
                    "pass_codes": [0],
                },
                "repair_commands": [],
                "max_attempts": 0,
                "approval_required": False,
                "stop_conditions": [
                    "draft-quality-gate.py found error/critical findings; revise the draft from copywriter-ready brief and rerun.",
                    "Draft and outline slug mapping is wrong; edit this template or use seo-cycle-run.py --stage-template copywriting --outline explicitly.",
                ],
                "next_stage": "project_journey",
            }
        ]
    }


def templates() -> list[dict[str, Any]]:
    return [
        {
            "id": "setup_readiness",
            "filename": "setup-readiness.yaml",
            "description": "Runnable setup control plane readiness contract.",
            "payload": setup_readiness_payload(),
        },
        {
            "id": "research_package",
            "filename": "research-package.yaml",
            "description": "Runnable research package quality/repair/v3 briefs contract.",
            "payload": research_package_payload(),
        },
        {
            "id": "copywriting_draft",
            "filename": "copywriting-draft.yaml",
            "description": "Editable sample draft quality gate contract; replace sample slug before use.",
            "payload": copywriting_payload(),
        },
    ]


def dump_yaml(data: dict[str, Any]) -> str:
    if yaml is not None:
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def resolve_project_root(config: str | None) -> pathlib.Path:
    if config:
        cfg_path = pathlib.Path(config).expanduser().resolve()
        if not cfg_path.exists():
            raise SystemExit(f"ERROR: {cfg_path} not found")
        return project_root_for(cfg_path)
    found = find_config(pathlib.Path.cwd())
    return project_root_for(found.resolve()) if found else pathlib.Path.cwd()


def build_report(project_root: pathlib.Path, write: bool, force: bool) -> dict[str, Any]:
    stage_dir = project_root / "seo" / "stages"
    rows: list[dict[str, Any]] = []
    for template in templates():
        path = stage_dir / template["filename"]
        existed_before = path.exists()
        action = "would_write"
        if write:
            if existed_before and not force:
                action = "kept_existing"
            else:
                write_text(path, dump_yaml(template["payload"]))
                action = "overwritten" if existed_before else "written"
        rows.append(
            {
                "id": template["id"],
                "description": template["description"],
                "path": str(path.relative_to(project_root)),
                "stage_ids": [stage["id"] for stage in template["payload"]["stages"]],
                "action": action,
                "exists": path.exists(),
            }
        )
    report = {
        "status": "ok",
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "project_root": str(project_root),
        "stage_dir": "seo/stages",
        "summary": {
            "templates": len(rows),
            "written": len([row for row in rows if row["action"] == "written"]),
            "overwritten": len([row for row in rows if row["action"] == "overwritten"]),
            "kept_existing": len([row for row in rows if row["action"] == "kept_existing"]),
        },
        "templates": rows,
        "usage": [
            "python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --stage-file seo/stages/setup-readiness.yaml --write",
            "python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --stage-file seo/stages/research-package.yaml --write",
            "Edit seo/stages/copywriting-draft.yaml for the real draft slug, then run it with --stage-file.",
        ],
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# seo-cycle stage templates",
        "",
        f"- Generated: {report['generated']}",
        f"- Stage dir: `{report['stage_dir']}`",
        f"- Templates: {report['summary']['templates']}",
        "",
        "## Templates",
        "| Template | Action | Stages | Path |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["templates"]:
        lines.append(f"| `{row['id']}` | `{row['action']}` | {', '.join(row['stage_ids'])} | `{row['path']}` |")
    lines.extend(["", "## Usage"])
    lines.extend(f"- `{item}`" for item in report["usage"])
    lines.extend(
        [
            "",
            "## Safety",
            "- Templates contain no secret values.",
            "- Existing YAML files are not overwritten unless `--force` is used.",
            "- Paid APIs, browser actions, publishing and indexing remain guarded by the wrapped scripts.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report(project_root: pathlib.Path, report: dict[str, Any]) -> None:
    stage_dir = project_root / "seo" / "stages"
    write_text(stage_dir / "stage-template-export.md", render_markdown(report))
    write_text(stage_dir / "stage-template-export.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml. Defaults to the config found from cwd.")
    parser.add_argument("--write", action="store_true", help="Write seo/stages/*.yaml and the export report.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing seo/stages/*.yaml files.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.config)
    report = build_report(project_root, write=args.write, force=args.force)
    if args.write:
        write_report(project_root, report)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
