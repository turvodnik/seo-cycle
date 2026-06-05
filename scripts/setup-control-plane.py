#!/usr/bin/env python3
"""Run the seo-cycle first-run control plane for one project.

This is the low-token "one screen" setup surface: it refreshes or inspects
intake, profile, source resolution, governance, validation, and automation
artifacts plus the latest task route, then writes a compact report with the
next safe actions.

Default mode is read-only. Use `--write` to refresh generated artifacts under
`seo/`. Use `--apply-profile` only when you want the generated profile applied
to `seo-cycle.yaml` with the normal backup behavior.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. `pip3 install pyyaml`", file=sys.stderr)
    sys.exit(2)


CONFIG_SEARCH_PATHS = [
    "seo-cycle.yaml",
    ".seo-cycle.yaml",
    "seo/seo-cycle.yaml",
    ".claude/seo-cycle.yaml",
]


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def find_config(start_dir: pathlib.Path) -> pathlib.Path | None:
    for rel in CONFIG_SEARCH_PATHS:
        path = start_dir / rel
        if path.exists():
            return path
    return None


def project_root_for(cfg_path: pathlib.Path) -> pathlib.Path:
    if cfg_path.name in (".seo-cycle.yaml", "seo-cycle.yaml"):
        return cfg_path.parent
    if "/seo/" in str(cfg_path) or "/.claude/" in str(cfg_path):
        return cfg_path.parent.parent
    return cfg_path.parent


def rel_path(project_root: pathlib.Path, raw: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def run_step(name: str, command: list[str], cwd: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "name": name,
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def parse_count(label: str, text: str) -> int:
    match = re.search(rf"{re.escape(label)}\s*\((\d+)\)", text)
    return int(match.group(1)) if match else 0


def parse_validation(step: dict[str, Any]) -> dict[str, int]:
    text = f"{step.get('stdout', '')}\n{step.get('stderr', '')}"
    return {
        "errors": parse_count("ERRORS", text),
        "warnings": parse_count("WARNINGS", text),
        "checklist": parse_count("ЧЕК-ЛИСТ что подключить", text),
    }


def load_json_output(step: dict[str, Any]) -> dict[str, Any]:
    if step.get("exit_code") != 0:
        return {}
    try:
        return json.loads(step.get("stdout") or "{}")
    except json.JSONDecodeError:
        return {}


def artifact_status(project_root: pathlib.Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = {
        "project_intake": "seo/project-intake.yaml",
        "project_intake_report": "seo/project-intake-report.md",
        "project_profile": "seo/project-profile.generated.yaml",
        "project_profile_report": "seo/project-profile-report.md",
        "setup_control_plane": "seo/setup/setup-control-plane.md",
        "governance_latest": "seo/setup/latest-governance.json",
        "validation_latest": "seo/setup/latest-validation.txt",
        "active_sources_latest": "seo/setup/latest-sources.json",
        "usage_ledger": "seo/usage/usage-ledger.jsonl",
        "latest_usage_report": "seo/setup/latest-usage-ledger.md",
        "spend_guard_generated": "seo/spend-guard.generated.yaml",
        "spend_guard_report": "seo/setup/spend-guard.md",
        "spend_checklist": "seo/setup/spend-checklist.csv",
        "latest_spend_guard": "seo/setup/latest-spend-guard.md",
        "tool_stack_generated": "seo/tool-stack.generated.yaml",
        "tool_stack_report": "seo/setup/tool-stack-report.md",
        "latest_tool_stack": "seo/setup/latest-tool-stack.md",
        "growth_roadmap_generated": "seo/growth-roadmap.generated.yaml",
        "growth_roadmap_report": "seo/setup/growth-roadmap.md",
        "latest_growth_roadmap": "seo/setup/latest-growth-roadmap.md",
        "onboarding_generated": "seo/onboarding.generated.yaml",
        "onboarding_playbook": "seo/setup/onboarding-playbook.md",
        "onboarding_checklist": "seo/setup/onboarding-checklist.csv",
        "latest_onboarding_playbook": "seo/setup/latest-onboarding-playbook.md",
        "launch_plan_generated": "seo/launch-plan.generated.yaml",
        "launch_plan_report": "seo/setup/launch-plan.md",
        "launch_checklist": "seo/setup/launch-checklist.csv",
        "latest_launch_plan": "seo/setup/latest-launch-plan.md",
        "context_pack_report": "seo/setup/context-pack.md",
        "context_pack_json": "seo/setup/context-pack.json",
        "latest_context_pack": "seo/setup/latest-context-pack.md",
        "automation_recommendations": "seo/automations/automation-recommendations.md",
        "automation_policy_generated": "seo/automation-policy.generated.yaml",
        "automation_plan": "seo/automations/automation-plan.md",
        "automation_plan_json": "seo/automations/automation-plan.json",
        "automation_crontab": "seo/automations/crontab.txt",
        "latest_task_route": "seo/setup/latest-task-route.md",
    }
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    rows = []
    for key, default in defaults.items():
        raw_path = policy_files.get(key, default) if key in policy_files else default
        path = rel_path(project_root, raw_path)
        rows.append({"key": key, "path": raw_path, "exists": path.exists()})
    return rows


def enabled_paid_missing_env(governance: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in governance.get("paid_or_quota_sources", []):
        if row.get("enabled") and row.get("env_missing"):
            rows.append(
                {
                    "source": row.get("source"),
                    "env_missing": row.get("env_missing", []),
                }
            )
    return rows


def next_actions(
    validation: dict[str, int],
    governance: dict[str, Any],
    sources: dict[str, Any],
    tool_stack: dict[str, Any],
    growth_roadmap: dict[str, Any],
    onboarding: dict[str, Any],
    launch_plan: dict[str, Any],
    context_pack: dict[str, Any],
    spend_guard: dict[str, Any],
    automation: dict[str, Any],
    artifacts: list[dict[str, Any]],
    apply_profile: bool,
) -> list[str]:
    actions: list[str] = []
    if validation.get("errors", 0) > 0:
        actions.append("Fix validation errors before running any SEO cycle.")
    if validation.get("checklist", 0) > 0:
        actions.append("Review `seo/setup/latest-validation.txt` and fill required env/policy items.")

    artifact_by_key = {row["key"]: row for row in artifacts}
    missing_policy = []
    for row in governance.get("policy_files", []):
        if row.get("exists"):
            continue
        current_artifact = artifact_by_key.get(row["key"])
        if current_artifact and current_artifact.get("exists"):
            continue
        missing_policy.append(row["key"])
    if missing_policy:
        actions.append(f"Create missing policy files: {', '.join(missing_policy)}.")

    paid_missing = enabled_paid_missing_env(governance)
    if paid_missing:
        names = ", ".join(f"{row['source']} ({', '.join(row['env_missing'])})" for row in paid_missing)
        actions.append(f"Either add env vars or disable paid/quota sources: {names}.")

    if sources and not sources.get("active"):
        actions.append("Resolve active sources: region profile and source overrides currently produce no active source.")

    approval_tools = [
        tool_id
        for tool_id, row in (tool_stack.get("decisions") or {}).items()
        if isinstance(row, dict) and row.get("decision") == "approval_required"
    ]
    if approval_tools:
        actions.append(f"Review tool-stack approval gates before use: {', '.join(sorted(approval_tools))}.")

    if growth_roadmap.get("approval_gates"):
        actions.append(f"Start from `seo/setup/growth-roadmap.md`; approval gates present: {', '.join(growth_roadmap['approval_gates'])}.")

    if onboarding.get("owner_summary"):
        human_steps = onboarding["owner_summary"].get("human_secret", 0)
        approval_steps = onboarding["owner_summary"].get("approval", 0)
        if human_steps or approval_steps:
            actions.append(f"Use `seo/setup/onboarding-playbook.md` before first run: human_secret={human_steps}, approval={approval_steps}.")

    if launch_plan.get("approval_gates"):
        actions.append(f"Open `seo/setup/launch-plan.md` as the first project screen; launch gates={len(launch_plan['approval_gates'])}.")

    if context_pack.get("rendered_chars"):
        actions.insert(0, f"Start each session from `seo/setup/context-pack.md` ({context_pack['rendered_chars']} chars) before opening larger setup reports.")

    blocked_spend = [
        row["service"]
        for row in spend_guard.get("service_guards", [])
        if isinstance(row, dict) and row.get("status") in {"blocked", "approval_required"} and not row.get("allowed_now")
    ]
    if blocked_spend:
        actions.append(f"Review `seo/setup/spend-guard.md` before paid/LLM/subscription use: {', '.join(blocked_spend[:8])}.")

    if automation.get("blockers"):
        actions.append("Automation files were generated for review; install remains blocked until policy gates allow schedules.")

    missing_artifacts = [row["key"] for row in artifacts if not row.get("exists")]
    if missing_artifacts:
        actions.append(f"Generate/review missing setup artifacts: {', '.join(missing_artifacts)}.")

    if not apply_profile:
        actions.append("Review `seo/project-profile.generated.yaml`; run `project-profile.py --apply` only after confirming the overlay.")

    if not actions:
        actions.append("Setup control plane is green; start the SEO cycle with cached/raw-on-disk, distillates-in-context mode.")
    return actions


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    validation = report.get("validation", {})
    governance = report.get("governance", {})
    sources = report.get("sources", {})
    automation = report.get("automation", {})
    automation_recommendations = report.get("automation_recommendations", {})
    tool_stack = report.get("tool_stack", {})
    growth_roadmap = report.get("growth_roadmap", {})
    onboarding = report.get("onboarding", {})
    launch_plan = report.get("launch_plan", {})
    context_pack = report.get("context_pack", {})
    spend_guard = report.get("spend_guard", {})
    task_route = report.get("task_route", {})
    usage = report.get("usage_ledger", {})
    tool_summary = tool_stack.get("summary", {}).get("by_decision", {}) if isinstance(tool_stack.get("summary"), dict) else {}
    lines = [
        "# seo-cycle setup control plane",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Config: {report.get('config')}",
        f"- Project root: {report.get('project_root')}",
        f"- Region profile: {report.get('region_profile')}",
        f"- Runtime: {report.get('runtime')}",
        "",
        "## Readiness",
        f"- Validation: errors={validation.get('errors', 0)}, warnings={validation.get('warnings', 0)}, checklist={validation.get('checklist', 0)}",
        f"- Active sources: {len(sources.get('active', {}))}",
        f"- Skipped sources: {len(sources.get('skipped', {}))}",
        f"- Paid/quota sources needing env: {len(report.get('paid_missing_env', []))}",
        f"- Usage ledger status: {usage.get('evaluation', {}).get('status')}",
        f"- Usage ledger allowed: {usage.get('evaluation', {}).get('allowed')}",
        f"- Spend guard services: {len(spend_guard.get('service_guards', []))}",
        f"- Spend guard blocked/approval: {len([row for row in spend_guard.get('service_guards', []) if isinstance(row, dict) and row.get('status') in {'blocked', 'approval_required'} and not row.get('allowed_now')])}",
        f"- Tool stack enabled/report-only/approval: {tool_summary.get('enabled', 0)}/{tool_summary.get('report_only', 0)}/{tool_summary.get('approval_required', 0)}",
        f"- Growth roadmap lanes/actions: {len(growth_roadmap.get('lanes', {}))}/{len(growth_roadmap.get('actions', []))}",
        f"- Onboarding steps: {onboarding.get('limits', {}).get('emitted_steps')}",
        f"- Onboarding human-secret steps: {onboarding.get('owner_summary', {}).get('human_secret', 0)}",
        f"- Launch plan execution steps: {len(launch_plan.get('execution_order', []))}",
        f"- Launch plan env names: {len((launch_plan.get('human_inputs') or {}).get('env_names', []))}",
        f"- Context pack chars: {context_pack.get('rendered_chars')}",
        f"- Recommended automations: {len((automation_recommendations.get('policy_overlay') or {}).get('planned_automations', {}))}",
        f"- Automation install allowed: {automation.get('allowed')}",
    ]
    if automation.get("blockers"):
        lines.append(f"- Automation blockers: {', '.join(automation['blockers'])}")

    if task_route:
        lines.extend(
            [
                f"- Latest task route: {task_route.get('task_type')} ({len(task_route.get('phases', []))} phases)",
                f"- Latest task approval gates: {', '.join(task_route.get('approval_gates', [])) or 'none'}",
            ]
        )

    lines.extend(["", "## Artifacts", "| Key | Exists | Path |", "| --- | --- | --- |"])
    for row in report.get("artifacts", []):
        lines.append(f"| {row['key']} | {'yes' if row['exists'] else 'no'} | `{row['path']}` |")

    lines.extend(["", "## Step Results", "| Step | Exit |", "| --- | --- |"])
    for step in report.get("steps", []):
        lines.append(f"| {step['name']} | {step['exit_code']} |")

    lines.extend(["", "## Next Actions"])
    for item in report.get("next_actions", []):
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Low-Token Contract",
            "- Start from `seo/setup/context-pack.md` for task-scoped handoff before opening larger reports.",
            "- Keep raw API/browser output on disk under `seo/`; load only distillates/top-N into model context.",
            "- Run expensive sources only after cache checks and budget policy review.",
            "- Do not install tracking tags, launch ads, submit indexes, or publish content without the relevant approval gates.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_report(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    out_dir = project_root / "seo" / "setup"
    out_dir.mkdir(parents=True, exist_ok=True)
    write_text(out_dir / "setup-control-plane.md", render_markdown(report))
    write_text(out_dir / "setup-control-plane.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Refresh setup artifacts and write seo/setup reports.")
    parser.add_argument("--apply-profile", action="store_true", help="Apply generated project profile to seo-cycle.yaml with backup.")
    parser.add_argument("--skip-intake", action="store_true", help="Do not refresh project-intake defaults.")
    parser.add_argument("--skip-automation", action="store_true", help="Do not generate automation plan artifacts.")
    parser.add_argument("--task", default="first SEO cycle setup", help="Task text for the low-token task router.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.config:
        cfg_path = pathlib.Path(args.config).expanduser().resolve()
    else:
        found = find_config(pathlib.Path.cwd())
        if not found:
            print(f"ERROR: seo-cycle.yaml не найден в {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        cfg_path = found.resolve()
    if not cfg_path.exists():
        print(f"ERROR: {cfg_path} не найден", file=sys.stderr)
        return 2

    root = skill_root()
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    setup_dir = project_root / "seo" / "setup"
    steps: list[dict[str, Any]] = []

    if args.write:
        write_text(
            setup_dir / "setup-control-plane.md",
            "# seo-cycle setup control plane\n\nGeneration in progress. Re-run `setup-control-plane.py --write` if this remains.\n",
        )

    if args.write and not args.skip_intake:
        steps.append(
            run_step(
                "project-intake defaults",
                [sys.executable, str(root / "scripts/project-intake-wizard.py"), str(cfg_path), "--defaults", "--write"],
                project_root,
            )
        )

    profile_command = [sys.executable, str(root / "scripts/project-profile.py"), str(cfg_path)]
    if args.apply_profile:
        profile_command.append("--apply")
    elif args.write:
        profile_command.append("--write")
    else:
        profile_command.extend(["--format", "json"])
    steps.append(run_step("project profile", profile_command, project_root))

    sources_step = run_step("resolve sources", [sys.executable, str(root / "scripts/resolve-sources.py"), str(cfg_path), "--json"], project_root)
    steps.append(sources_step)

    governance_step = run_step("governance report", [sys.executable, str(root / "scripts/governance-report.py"), str(cfg_path), "--format", "json"], project_root)
    steps.append(governance_step)

    if args.write and not args.skip_automation:
        steps.append(
            run_step(
                "automation plan",
                [sys.executable, str(root / "scripts/automation-plan.py"), str(cfg_path), "--write", "--include-disabled"],
                project_root,
            )
        )
    else:
        steps.append(
            run_step(
                "automation plan",
                [sys.executable, str(root / "scripts/automation-plan.py"), str(cfg_path), "--format", "json", "--include-disabled"],
                project_root,
            )
        )

    task_router_command = [sys.executable, str(root / "scripts/task-router.py"), str(cfg_path), "--task", args.task]
    if args.write:
        task_router_command.append("--write")
    else:
        task_router_command.extend(["--format", "json"])
    steps.append(run_step("task router", task_router_command, project_root))

    usage_command = [sys.executable, str(root / "scripts/usage-ledger.py"), "report", str(cfg_path)]
    if args.write:
        usage_command.append("--write")
    else:
        usage_command.extend(["--format", "json"])
    steps.append(run_step("usage ledger", usage_command, project_root))

    automation_recommender_command = [sys.executable, str(root / "scripts/automation-recommender.py"), str(cfg_path)]
    if args.write:
        automation_recommender_command.append("--write")
    else:
        automation_recommender_command.extend(["--format", "json"])
    steps.append(run_step("automation recommender", automation_recommender_command, project_root))

    tool_stack_command = [sys.executable, str(root / "scripts/tool-stack-recommender.py"), str(cfg_path)]
    if args.write:
        tool_stack_command.append("--write")
    else:
        tool_stack_command.extend(["--format", "json"])
    steps.append(run_step("tool stack recommender", tool_stack_command, project_root))

    spend_guard_command = [sys.executable, str(root / "scripts/spend-guard.py"), str(cfg_path)]
    if args.write:
        spend_guard_command.append("--write")
    else:
        spend_guard_command.extend(["--format", "json"])
    steps.append(run_step("spend guard", spend_guard_command, project_root))

    growth_roadmap_command = [sys.executable, str(root / "scripts/growth-roadmap.py"), str(cfg_path)]
    if args.write:
        growth_roadmap_command.append("--write")
    else:
        growth_roadmap_command.extend(["--format", "json"])
    steps.append(run_step("growth roadmap", growth_roadmap_command, project_root))

    onboarding_command = [sys.executable, str(root / "scripts/setup-onboarding.py"), str(cfg_path)]
    if args.write:
        onboarding_command.append("--write")
    else:
        onboarding_command.extend(["--format", "json"])
    steps.append(run_step("setup onboarding", onboarding_command, project_root))

    launch_plan_command = [sys.executable, str(root / "scripts/launch-plan.py"), str(cfg_path)]
    if args.write:
        launch_plan_command.append("--write")
    else:
        launch_plan_command.extend(["--format", "json"])
    steps.append(run_step("launch plan", launch_plan_command, project_root))

    context_pack_command = [sys.executable, str(root / "scripts/context-pack.py"), str(cfg_path), "--task", args.task]
    if args.write:
        context_pack_command.append("--write")
    else:
        context_pack_command.extend(["--format", "json"])
    steps.append(run_step("context pack", context_pack_command, project_root))

    validation_step = run_step("validate config", [sys.executable, str(root / "scripts/validate-config.py"), str(cfg_path)], project_root)
    steps.append(validation_step)

    if args.write:
        write_text(setup_dir / "latest-validation.txt", validation_step.get("stdout", "") + validation_step.get("stderr", ""))
        write_text(setup_dir / "latest-governance.json", governance_step.get("stdout", ""))
        write_text(setup_dir / "latest-sources.json", sources_step.get("stdout", ""))

    cfg = load_yaml(cfg_path)
    governance = load_json_output(governance_step)
    sources = load_json_output(sources_step)
    automation_step = next((step for step in steps if step["name"] == "automation plan"), {})
    automation = load_json_output(automation_step)
    if not automation:
        automation = json.loads((project_root / "seo" / "automations" / "automation-plan.json").read_text(encoding="utf-8")) if (project_root / "seo" / "automations" / "automation-plan.json").exists() else {}
    if "allowed" not in automation and "schedule_install_allowed" in automation:
        automation["allowed"] = automation.get("schedule_install_allowed")
    task_router_step = next((step for step in steps if step["name"] == "task router"), {})
    task_route = load_json_output(task_router_step)
    task_route_file = project_root / "seo" / "setup" / "latest-task-route.json"
    if not task_route and task_route_file.exists():
        task_route = json.loads(task_route_file.read_text(encoding="utf-8"))
    usage_step = next((step for step in steps if step["name"] == "usage ledger"), {})
    usage_ledger = load_json_output(usage_step)
    usage_file = project_root / "seo" / "setup" / "latest-usage-ledger.json"
    if not usage_ledger and usage_file.exists():
        usage_ledger = json.loads(usage_file.read_text(encoding="utf-8"))
    automation_recommender_step = next((step for step in steps if step["name"] == "automation recommender"), {})
    automation_recommendations = load_json_output(automation_recommender_step)
    automation_recommendations_file = project_root / "seo" / "automations" / "automation-recommendations.json"
    if not automation_recommendations and automation_recommendations_file.exists():
        automation_recommendations = json.loads(automation_recommendations_file.read_text(encoding="utf-8"))
    tool_stack_step = next((step for step in steps if step["name"] == "tool stack recommender"), {})
    tool_stack = load_json_output(tool_stack_step)
    tool_stack_file = project_root / "seo" / "setup" / "tool-stack-report.json"
    if not tool_stack and tool_stack_file.exists():
        tool_stack = json.loads(tool_stack_file.read_text(encoding="utf-8"))
    spend_guard_step = next((step for step in steps if step["name"] == "spend guard"), {})
    spend_guard = load_json_output(spend_guard_step)
    spend_guard_file = project_root / "seo" / "setup" / "spend-guard.json"
    if not spend_guard and spend_guard_file.exists():
        spend_guard = json.loads(spend_guard_file.read_text(encoding="utf-8"))
    growth_roadmap_step = next((step for step in steps if step["name"] == "growth roadmap"), {})
    growth_roadmap = load_json_output(growth_roadmap_step)
    growth_roadmap_file = project_root / "seo" / "setup" / "growth-roadmap.json"
    if not growth_roadmap and growth_roadmap_file.exists():
        growth_roadmap = json.loads(growth_roadmap_file.read_text(encoding="utf-8"))
    onboarding_step = next((step for step in steps if step["name"] == "setup onboarding"), {})
    onboarding = load_json_output(onboarding_step)
    onboarding_file = project_root / "seo" / "setup" / "onboarding-playbook.json"
    if not onboarding and onboarding_file.exists():
        onboarding = json.loads(onboarding_file.read_text(encoding="utf-8"))
    launch_plan_step = next((step for step in steps if step["name"] == "launch plan"), {})
    launch_plan = load_json_output(launch_plan_step)
    launch_plan_file = project_root / "seo" / "setup" / "launch-plan.json"
    if not launch_plan and launch_plan_file.exists():
        launch_plan = json.loads(launch_plan_file.read_text(encoding="utf-8"))
    context_pack_step = next((step for step in steps if step["name"] == "context pack"), {})
    context_pack = load_json_output(context_pack_step)
    context_pack_file = project_root / "seo" / "setup" / "context-pack.json"
    if not context_pack and context_pack_file.exists():
        context_pack = json.loads(context_pack_file.read_text(encoding="utf-8"))
    validation = parse_validation(validation_step)
    artifacts = artifact_status(project_root, cfg)
    paid_missing = enabled_paid_missing_env(governance)

    report = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "runtime": cfg.get("runtime", "auto"),
        "region_profile": cfg.get("region_profile"),
        "validation": validation,
        "governance": governance,
        "sources": sources,
        "automation": automation,
        "task_route": task_route,
        "usage_ledger": usage_ledger,
        "automation_recommendations": automation_recommendations,
        "tool_stack": tool_stack,
        "spend_guard": spend_guard,
        "growth_roadmap": growth_roadmap,
        "onboarding": onboarding,
        "launch_plan": launch_plan,
        "context_pack": context_pack,
        "paid_missing_env": paid_missing,
        "artifacts": artifacts,
        "steps": [
            {
                "name": step["name"],
                "exit_code": step["exit_code"],
                "stderr": step["stderr"][:2000],
            }
            for step in steps
        ],
    }
    report["next_actions"] = next_actions(validation, governance, sources, tool_stack, growth_roadmap, onboarding, launch_plan, context_pack, spend_guard, automation, artifacts, args.apply_profile)

    if args.write:
        out_dir = write_report(project_root, report)
        print(f"Wrote {out_dir}")
    elif args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")

    blocking_exit_codes = [step for step in steps if step["exit_code"] not in (0,)]
    validation_errors = validation.get("errors", 0)
    return 1 if validation_errors or any(step["name"] not in {"validate config"} for step in blocking_exit_codes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
