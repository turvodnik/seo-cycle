#!/usr/bin/env python3
"""Build a compact, task-scoped context pack for one seo-cycle project.

The pack is the first file an agent should read after project setup. It distills
launch plan, latest task route, spend guard, tool stack, roadmap, automation, and
usage posture into one bounded artifact. It never includes secret values or raw
API/browser data.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
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


def rel_display(project_root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get(key, default))


def load_policy_json(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> dict[str, Any]:
    path = policy_path(cfg, project_root, key, default)
    candidates = [path]
    if path.suffix == ".md":
        candidates.append(path.with_suffix(".json"))
    if path.name.startswith("latest-"):
        candidates.append(path.with_name(path.name.removeprefix("latest-")).with_suffix(".json"))
    for candidate in candidates:
        data = load_json(candidate)
        if data:
            return data
    return {}


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "enabled", "да"}
    return bool(value)


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def limit(values: list[Any], count: int) -> list[Any]:
    return values[:count]


def run_task_router(cfg_path: pathlib.Path, project_root: pathlib.Path, task: str) -> None:
    subprocess.run(
        [sys.executable, str(skill_root() / "scripts/task-router.py"), str(cfg_path), "--task", task, "--write"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )


def token_contract(cfg: dict[str, Any], route: dict[str, Any], launch_plan: dict[str, Any]) -> dict[str, Any]:
    route_caps = (route.get("context_contract") or {}).get("caps", {}) if isinstance(route.get("context_contract"), dict) else {}
    launch_caps = launch_plan.get("token_contract", {}) if isinstance(launch_plan.get("token_contract"), dict) else {}
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    token = governance.get("token_policy", {}) if isinstance(governance.get("token_policy"), dict) else {}
    return {
        "raw_data_in_context": boolish(route_caps.get("raw_data_in_context", launch_caps.get("raw_data_in_context", token.get("raw_data_in_context", False)))),
        "cache_first": boolish(route_caps.get("cache_first", launch_caps.get("cache_first", token.get("cache_first", True)))),
        "progressive_disclosure": boolish(route_caps.get("progressive_disclosure", token.get("progressive_disclosure", True))),
        "require_distillate_before_synthesis": boolish(launch_caps.get("require_distillate_before_synthesis", token.get("require_distillate_before_synthesis", True))),
        "max_context_input_tokens_per_phase": int(route_caps.get("max_context_input_tokens_per_phase", launch_caps.get("max_context_input_tokens_per_phase", token.get("max_context_input_tokens_per_phase", 45000)))),
        "max_raw_rows_loaded": int(route_caps.get("max_raw_rows_loaded", launch_caps.get("max_raw_rows_loaded", token.get("max_raw_rows_loaded", 200)))),
        "distillate_max_lines": int(route_caps.get("distillate_max_lines", launch_caps.get("distillate_max_lines", token.get("distillate_max_lines", 220)))),
        "browser_session_budget_minutes": int(route_caps.get("browser_session_budget_minutes", launch_caps.get("browser_session_budget_minutes", token.get("browser_session_budget_minutes", 20)))),
        "browser_pages_per_phase_cap": int(route_caps.get("browser_pages_per_phase_cap", launch_caps.get("browser_pages_per_phase_cap", token.get("browser_pages_per_phase_cap", 20)))),
    }


def env_names(tool_stack: dict[str, Any], launch_plan: dict[str, Any]) -> list[str]:
    names: list[str] = []
    human_inputs = launch_plan.get("human_inputs", {}) if isinstance(launch_plan.get("human_inputs"), dict) else {}
    names.extend(str(name) for name in human_inputs.get("env_names", []) if isinstance(name, str))
    for row in (tool_stack.get("decisions") or {}).values():
        if not isinstance(row, dict):
            continue
        names.extend(str(name) for name in row.get("env", []) if isinstance(name, str))
    return sorted(unique([name for name in names if "=" not in name]))


def tool_summary(tool_stack: dict[str, Any]) -> dict[str, Any]:
    decisions = tool_stack.get("decisions", {}) if isinstance(tool_stack.get("decisions"), dict) else {}
    by_decision: dict[str, list[str]] = {}
    for tool_id, row in decisions.items():
        if not isinstance(row, dict):
            continue
        by_decision.setdefault(str(row.get("decision", "unknown")), []).append(str(tool_id))
    return {
        "enabled": sorted(by_decision.get("enabled", [])),
        "report_only": sorted(by_decision.get("report_only", [])),
        "approval_required": sorted(by_decision.get("approval_required", [])),
        "disabled": sorted(by_decision.get("disabled", [])),
    }


def spend_summary(spend_guard: dict[str, Any]) -> dict[str, Any]:
    blocked: list[str] = []
    approval: list[str] = []
    allowed: list[str] = []
    for row in spend_guard.get("service_guards", []):
        if not isinstance(row, dict):
            continue
        service = str(row.get("service") or "")
        status = row.get("status")
        if status == "blocked":
            blocked.append(service)
        elif status == "approval_required":
            approval.append(service)
        elif row.get("allowed_now"):
            allowed.append(service)
    return {
        "blocked": sorted([item for item in blocked if item]),
        "approval_required": sorted([item for item in approval if item]),
        "allowed_now": sorted([item for item in allowed if item]),
    }


def roadmap_actions(growth_roadmap: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for row in growth_roadmap.get("actions", []):
        if not isinstance(row, dict):
            continue
        actions.append(
            {
                "id": row.get("id"),
                "lane": row.get("lane"),
                "title": row.get("title") or row.get("action"),
                "approval_gates": row.get("approval_gates", []),
                "tools": row.get("tools", []),
            }
        )
    return actions


def automation_summary(automation: dict[str, Any]) -> list[dict[str, Any]]:
    overlay = automation.get("policy_overlay", {}) if isinstance(automation.get("policy_overlay"), dict) else {}
    planned = overlay.get("planned_automations", {}) if isinstance(overlay.get("planned_automations"), dict) else {}
    rows: list[dict[str, Any]] = []
    for task_id, node in planned.items():
        if not isinstance(node, dict) or not node.get("enabled"):
            continue
        rows.append(
            {
                "task": task_id,
                "cadence": node.get("cadence"),
                "mode": node.get("mode"),
                "tools": node.get("tools", []),
                "approval_gates": node.get("approval_gates", []),
            }
        )
    return rows


def read_order(project_root: pathlib.Path, cfg: dict[str, Any], route: dict[str, Any]) -> list[str]:
    explicit = [
        "seo/setup/context-pack.md",
        "seo/setup/setup-gap-audit.md",
        "seo/setup/setup-questionnaire.md",
        "seo/setup/setup-answer-plan.md",
        "seo/setup/latest-task-route.md",
        "seo/setup/launch-plan.md",
        "seo/setup/spend-guard.md",
        "seo/setup/latest-usage-ledger.md",
        "seo/setup/tool-stack-report.md",
        "seo/setup/growth-roadmap.md",
        "seo/automations/automation-recommendations.md",
        "seo/project-intake.yaml",
        "seo/tool-budget.yaml",
    ]
    route_first = []
    if isinstance(route.get("context_contract"), dict):
        route_first = [rel_display(project_root, pathlib.Path(path)) for path in route["context_contract"].get("read_first", [])]
    return unique(explicit + route_first)


def excluded_raw_artifacts() -> list[str]:
    return [
        "seo/setup/tool-stack-report.json",
        "seo/setup/spend-guard.json",
        "seo/setup/growth-roadmap.json",
        "seo/setup/launch-plan.json",
        "seo/setup/setup-gap-audit.json",
        "seo/setup/latest-setup-gap-audit.json",
        "seo/setup/setup-questionnaire.json",
        "seo/setup/latest-setup-questionnaire.json",
        "seo/setup/setup-answer-plan.json",
        "seo/setup/latest-setup-answer-plan.json",
        "seo/setup/latest-task-route.json",
        "seo/automations/automation-recommendations.json",
        "seo/setup/setup-control-plane.json",
        "seo/usage/usage-ledger.jsonl",
        "raw crawl exports under seo/cycles/",
        "raw browser dumps under seo/",
    ]


def build_pack(cfg_path: pathlib.Path, task: str, max_chars: int, refresh_route: bool) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    if task and refresh_route:
        run_task_router(cfg_path, project_root, task)

    route = load_policy_json(cfg, project_root, "latest_task_route", "seo/setup/latest-task-route.md")
    launch_plan = load_policy_json(cfg, project_root, "launch_plan_report", "seo/setup/launch-plan.md")
    tool_stack = load_policy_json(cfg, project_root, "tool_stack_report", "seo/setup/tool-stack-report.md")
    spend_guard = load_policy_json(cfg, project_root, "spend_guard_report", "seo/setup/spend-guard.md")
    growth_roadmap = load_policy_json(cfg, project_root, "growth_roadmap_report", "seo/setup/growth-roadmap.md")
    automation = load_policy_json(cfg, project_root, "automation_recommendations", "seo/automations/automation-recommendations.md")
    usage = load_policy_json(cfg, project_root, "latest_usage_report", "seo/setup/latest-usage-ledger.md")
    token = token_contract(cfg, route, launch_plan)
    tools = tool_summary(tool_stack)
    spend = spend_summary(spend_guard)
    route_contract = route.get("context_contract", {}) if isinstance(route.get("context_contract"), dict) else {}

    report = {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": {
            "name": (cfg.get("project") or {}).get("name"),
            "domain": (cfg.get("project") or {}).get("domain"),
            "project_type": cfg.get("project_type"),
            "region_profile": cfg.get("region_profile"),
            "country": (cfg.get("locale") or {}).get("country"),
            "language": (cfg.get("locale") or {}).get("language"),
        },
        "task": {
            "text": route.get("task") or task,
            "task_type": route.get("task_type"),
            "phases": route.get("phases", []),
            "safe_actions": route.get("safe_actions", []),
            "approval_gates": route.get("approval_gates", []),
            "blocked_actions": route.get("blocked_actions", []),
            "automation": route.get("automation", {}),
        },
        "context_contract": {
            **token,
            "max_pack_chars": max_chars,
            "load_only": route_contract.get("load_only", ["distillates/top-N summaries", "specific URLs or rows needed for this task"]),
        },
        "read_order": read_order(project_root, cfg, route),
        "do_not_load_raw": unique(route_contract.get("do_not_load_raw", []) + ["raw API JSON", "browser dumps", "full CSV exports", "full sitemap URL lists"]),
        "excluded_raw_artifacts": excluded_raw_artifacts(),
        "usage": {
            "status": (usage.get("evaluation") or {}).get("status"),
            "allowed": (usage.get("evaluation") or {}).get("allowed"),
            "month": usage.get("month"),
        },
        "spend": {
            "blocked": limit(spend["blocked"], 12),
            "approval_required": limit(spend["approval_required"], 12),
            "allowed_now_count": len(spend["allowed_now"]),
        },
        "tools": {
            "enabled": limit(tools["enabled"], 20),
            "report_only": limit(tools["report_only"], 20),
            "approval_required": limit(tools["approval_required"], 20),
            "disabled_count": len(tools["disabled"]),
        },
        "roadmap_top_actions": limit(roadmap_actions(growth_roadmap), 6),
        "enabled_automations": limit(automation_summary(automation), 12),
        "human_secret_env_names": limit(env_names(tool_stack, launch_plan), 50),
        "next_commands": [
            "python3 ~/.claude/skills/seo-cycle/scripts/context-pack.py --task \"<current task>\" --write",
            "python3 ~/.claude/skills/seo-cycle/scripts/task-router.py --task \"<current task>\" --write",
            "python3 ~/.claude/skills/seo-cycle/scripts/spend-guard.py --write",
            "python3 ~/.claude/skills/seo-cycle/scripts/usage-ledger.py report --write",
        ],
    }
    md = render_markdown(report)
    if len(md) > max_chars:
        report["roadmap_top_actions"] = limit(report["roadmap_top_actions"], 3)
        report["enabled_automations"] = limit(report["enabled_automations"], 6)
        report["human_secret_env_names"] = limit(report["human_secret_env_names"], 25)
        md = render_markdown(report)
    report["rendered_chars"] = len(md)
    report["outputs"] = {
        "markdown": "seo/setup/context-pack.md",
        "json": "seo/setup/context-pack.json",
        "latest_markdown": "seo/setup/latest-context-pack.md",
        "latest_json": "seo/setup/latest-context-pack.json",
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    task = report.get("task", {})
    contract = report.get("context_contract", {})
    lines = [
        "# seo-cycle context pack",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name')} ({project.get('domain')})",
        f"- Type/market: {project.get('project_type')} / {project.get('region_profile')} / {project.get('country')} / {project.get('language')}",
        f"- Task: {task.get('text')}",
        f"- Task type: {task.get('task_type')}",
        f"- Max pack chars: {contract.get('max_pack_chars')}",
        "",
        "## Read First",
    ]
    lines.extend(f"- `{path}`" for path in report.get("read_order", []))

    lines.extend(
        [
            "",
            "## Context Contract",
            f"- raw_data_in_context: {contract.get('raw_data_in_context')}",
            f"- cache_first: {contract.get('cache_first')}",
            f"- progressive_disclosure: {contract.get('progressive_disclosure')}",
            f"- require_distillate_before_synthesis: {contract.get('require_distillate_before_synthesis')}",
            f"- max_raw_rows_loaded: {contract.get('max_raw_rows_loaded')}",
            f"- distillate_max_lines: {contract.get('distillate_max_lines')}",
            f"- browser budget: {contract.get('browser_session_budget_minutes')} min / {contract.get('browser_pages_per_phase_cap')} pages",
            "",
            "## Task Route",
        ]
    )
    lines.extend(f"- Phase: {phase}" for phase in task.get("phases", []))
    if task.get("safe_actions"):
        lines.append("- Safe actions: " + ", ".join(task["safe_actions"]))
    if task.get("approval_gates"):
        lines.append("- Approval gates: " + ", ".join(task["approval_gates"]))
    if task.get("blocked_actions"):
        lines.append("- Blocked: " + " | ".join(task["blocked_actions"]))
    automation = task.get("automation", {}) if isinstance(task.get("automation"), dict) else {}
    lines.append(f"- Automation: {automation.get('recommended')} / enabled={automation.get('enabled')} / mode={automation.get('mode')}")

    usage = report.get("usage", {})
    spend = report.get("spend", {})
    lines.extend(
        [
            "",
            "## Spend And Usage",
            f"- Usage: status={usage.get('status')} allowed={usage.get('allowed')} month={usage.get('month')}",
            f"- Spend blocked: {', '.join(spend.get('blocked', [])) or '-'}",
            f"- Spend approval required: {', '.join(spend.get('approval_required', [])) or '-'}",
            f"- Spend allowed count: {spend.get('allowed_now_count')}",
            "",
            "## Tools",
        ]
    )
    tools = report.get("tools", {})
    lines.append(f"- Enabled: {', '.join(tools.get('enabled', [])) or '-'}")
    lines.append(f"- Report-only: {', '.join(tools.get('report_only', [])) or '-'}")
    lines.append(f"- Approval-required: {', '.join(tools.get('approval_required', [])) or '-'}")
    lines.append(f"- Disabled count: {tools.get('disabled_count')}")

    lines.extend(["", "## Top Roadmap Actions"])
    for action in report.get("roadmap_top_actions", []):
        lines.append(
            f"- {action.get('id')}: {action.get('title')} "
            f"[lane={action.get('lane')}; gates={','.join(action.get('approval_gates', [])) or '-'}]"
        )

    lines.extend(["", "## Enabled Automations"])
    for row in report.get("enabled_automations", []):
        lines.append(f"- {row.get('task')}: {row.get('cadence')} / {row.get('mode')} / tools={','.join(row.get('tools', [])) or '-'}")

    lines.extend(["", "## Human Secret Env Names"])
    lines.extend(f"- `{name}`" for name in report.get("human_secret_env_names", []))

    lines.extend(["", "## Do Not Load Raw"])
    lines.extend(f"- {item}" for item in report.get("do_not_load_raw", []))

    lines.extend(["", "## Excluded Raw Artifacts"])
    lines.extend(f"- `{item}`" for item in report.get("excluded_raw_artifacts", []))

    lines.extend(["", "## Next Commands"])
    lines.extend(f"- `{command}`" for command in report.get("next_commands", []))

    return "\n".join(lines) + "\n"


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    out_dir = project_root / "seo" / "setup"
    out_dir.mkdir(parents=True, exist_ok=True)
    md = render_markdown(report)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    for name in ("context-pack.md", "latest-context-pack.md"):
        (out_dir / name).write_text(md, encoding="utf-8")
    for name in ("context-pack.json", "latest-context-pack.json"):
        (out_dir / name).write_text(json_text, encoding="utf-8")
    return out_dir / "context-pack.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--task", default="first SEO cycle setup", help="Task text for context routing.")
    parser.add_argument("--max-chars", type=int, default=18000, help="Maximum intended markdown pack size.")
    parser.add_argument("--write", action="store_true", help="Write seo/setup/context-pack.md/json.")
    parser.add_argument("--no-refresh-route", action="store_true", help="Do not refresh latest-task-route before building the pack.")
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

    project_root = project_root_for(cfg_path)
    report = build_pack(cfg_path, args.task, args.max_chars, not args.no_refresh_route)
    if args.write:
        out = write_outputs(project_root, report)
        if args.format == "json":
            print(f"Wrote {out}", file=sys.stderr)
        else:
            print(f"Wrote {out}")
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not args.write:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
