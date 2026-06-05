#!/usr/bin/env python3
"""Build a low-token per-project setup blueprint.

The blueprint is the compact installer/control matrix for a project: markets,
engines, regions, business type, marketing/ads/tracking policy, tools, budgets,
subscriptions, automations, guardrails, and first-read files. It is secret-free
and writes only review artifacts, not project config changes.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
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

MAX_BLUEPRINT_CHARS = 9000


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


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get(key, default))


def load_policy_json(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> dict[str, Any]:
    path = policy_path(cfg, project_root, key, default)
    candidates = [path]
    if path.suffix == ".md":
        candidates.append(path.with_suffix(".json"))
    for candidate in candidates:
        report = load_json(candidate)
        if report:
            return report
    return {}


def run_json_script(script: str, cfg_path: pathlib.Path, project_root: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(skill_root() / "scripts" / script), str(cfg_path), "--format", "json"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "enabled", "да", "д"}
    return bool(value)


def scalar(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item))
    if isinstance(value, dict):
        active = [str(key) for key, enabled in value.items() if boolish(enabled)]
        return ", ".join(active) if active else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, dict):
        return [str(key) for key, enabled in value.items() if boolish(enabled)]
    if isinstance(value, str) and value:
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def compact(items: list[str], limit: int = 12) -> list[str]:
    return items[:limit]


def load_reports(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, dict[str, Any]]:
    return {
        "launch": load_policy_json(cfg, project_root, "launch_plan_report", "seo/setup/launch-plan.md")
        or run_json_script("launch-plan.py", cfg_path, project_root),
        "gap": load_policy_json(cfg, project_root, "setup_gap_audit_report", "seo/setup/setup-gap-audit.md")
        or run_json_script("setup-gap-audit.py", cfg_path, project_root),
        "tool_stack": load_policy_json(cfg, project_root, "tool_stack_report", "seo/setup/tool-stack-report.md")
        or run_json_script("tool-stack-recommender.py", cfg_path, project_root),
        "spend": load_policy_json(cfg, project_root, "spend_guard_report", "seo/setup/spend-guard.md")
        or run_json_script("spend-guard.py", cfg_path, project_root),
        "automation": load_policy_json(cfg, project_root, "automation_recommendations", "seo/automations/automation-recommendations.md")
        or run_json_script("automation-recommender.py", cfg_path, project_root),
        "growth": load_policy_json(cfg, project_root, "growth_roadmap_report", "seo/setup/growth-roadmap.md")
        or run_json_script("growth-roadmap.py", cfg_path, project_root),
        "onboarding": load_policy_json(cfg, project_root, "onboarding_playbook", "seo/setup/onboarding-playbook.md")
        or run_json_script("setup-onboarding.py", cfg_path, project_root),
    }


def decision(axis: str, current: Any, target: str, owner: str, artifact: str, guard: str, command: str) -> dict[str, str]:
    return {
        "axis": axis,
        "current": scalar(current),
        "target": target,
        "owner": owner,
        "target_artifact": artifact,
        "guard": guard,
        "next_command": command,
    }


def decision_matrix(report: dict[str, Any]) -> list[dict[str, str]]:
    market = report["market_axes"]
    business = report["business_axes"]
    budget = report["budget_caps"]
    tools = report["tool_axes"]
    automation = report["automation_axes"]
    return [
        decision("market.country", market.get("country"), "confirm primary promotion country", "human", "seo/project-intake.yaml", "none", "project-intake-wizard.py --interactive --write"),
        decision("market.region", [market.get("region"), market.get("city")], "confirm exact region/city and local modifiers", "human", "seo/project-intake.yaml", "none", "project-intake-wizard.py --interactive --write"),
        decision("market.search_engines", market.get("search_engines", []), "enable only target engines", "agent", "seo/project-intake.yaml; seo/setup/tool-stack-report.md", "source_scope", "tool-stack-recommender.py --write"),
        decision("business.project_type", business.get("project_type"), "select project type and workflows", "human", "seo/project-intake.yaml", "none", "project-intake-wizard.py --interactive --write"),
        decision("business.local", business.get("local_platforms", []), "connect only relevant local profile sources", "human_secret", "seo/access-setup-runbook.md", "tracking_policy", "setup-onboarding.py --write"),
        decision("business.ecommerce", business.get("ecommerce"), "review merchant/feed/product evidence if ecommerce", "agent", "seo/access-setup-runbook.md", "merchant_approval", "tool-stack-recommender.py --write"),
        decision("marketing.organic_content", business.get("marketing", {}), "set organic/content/video/local/ecommerce channel scope", "human", "seo/project-intake.yaml", "none", "project-intake-wizard.py --interactive --write"),
        decision("marketing.paid_ads", business.get("paid_ads", {}), "keep ads planning separate from spend", "approval", "seo/project-intake.yaml; seo/tool-budget.yaml", "ads_spend_disabled", "spend-guard.py --write"),
        decision("marketing.analytics_tags", business.get("analytics_tags", {}), "respect RF/region tracking policy before tags", "approval", "seo/seo-data-collection-map.md", "tracking_tag_install", "tool-stack-recommender.py --write"),
        decision("tools.free_first", tools.get("free_first", []), "use free/read-only tools first", "agent", "seo/setup/tool-stack-report.md", "cache_first", "tool-stack-recommender.py --write"),
        decision("tools.guarded_paid_or_quota", tools.get("guarded_paid_or_quota", []), "run only through spend guard and usage ledger", "approval", "seo/setup/spend-guard.md", "paid_api_run", "spend-guard.py --write"),
        decision("budget.monthly_caps", budget, "confirm monthly caps before any paid/LLM/ads work", "human", "seo/tool-budget.yaml", "usage_ledger", "usage-ledger.py report --write"),
        decision("automation.planned", automation.get("enabled", []), "keep schedules report-only until policy approval", "approval", "seo/automations/automation-recommendations.md", "schedule_install", "automation-plan.py --write --include-disabled"),
    ]


def action_pack(
    pack_id: str,
    enabled: bool,
    read_first: list[str],
    tools: list[str],
    guards: list[str],
    command: str,
) -> dict[str, Any]:
    return {
        "id": pack_id,
        "enabled": enabled,
        "read_first": compact(read_first, 6),
        "tools": compact(tools, 10),
        "guards": compact(guards, 8),
        "command": command,
    }


def action_packs(report: dict[str, Any]) -> list[dict[str, Any]]:
    business = report["business_axes"]
    tools = report["tool_axes"]
    guards = report["guardrails"]
    return [
        action_pack("technical_readiness", True, ["seo/setup/context-pack.md", "seo/setup/latest-task-route.md", "seo/setup/setup-gap-audit.md"], tools.get("search_consoles", []), guards, "task-router.py --task \"technical audit\" --write"),
        action_pack("search_evidence", bool(report["market_axes"].get("search_engines")), ["seo/setup/tool-stack-report.md", "seo/setup/growth-roadmap.md"], tools.get("keyword_sources", []), guards, "growth-roadmap.py --write"),
        action_pack("ecommerce_feeds", boolish(business.get("ecommerce")), ["seo/access-setup-runbook.md", "seo/setup/tool-stack-report.md"], tools.get("merchant_feeds", []), guards, "tool-stack-recommender.py --write"),
        action_pack("local_profiles", boolish(business.get("local")), ["seo/access-setup-runbook.md", "seo/setup/tool-stack-report.md"], tools.get("local_profiles", []), guards, "setup-onboarding.py --write"),
        action_pack("content_entities", boolish(business.get("content")), ["seo/setup/growth-roadmap.md", "seo/entities/google-nlp-policy.yaml"], tools.get("ai_visibility", []), guards, "growth-roadmap.py --write"),
        action_pack("ads_tracking", bool(business.get("paid_ads") or business.get("analytics_tags")), ["seo/seo-data-collection-map.md", "seo/setup/spend-guard.md"], tools.get("ads_planning_or_approval", []) + tools.get("tracking_approval", []), guards, "spend-guard.py --write"),
        action_pack("automations", True, ["seo/automations/automation-recommendations.md", "seo/automations/automation-plan.md"], report["automation_axes"].get("enabled", []), guards, "automation-plan.py --write --include-disabled"),
    ]


def context_contract(launch: dict[str, Any]) -> dict[str, Any]:
    token = launch.get("token_contract", {}) if isinstance(launch.get("token_contract"), dict) else {}
    return {
        "max_blueprint_chars": MAX_BLUEPRINT_CHARS,
        "raw_data_in_context": boolish(token.get("raw_data_in_context", False)),
        "cache_first": boolish(token.get("cache_first", True)),
        "require_distillate_before_synthesis": boolish(token.get("require_distillate_before_synthesis", True)),
        "first_read": [
            "seo/setup/setup-blueprint.md",
            "seo/setup/context-pack.md",
            "seo/setup/latest-task-route.md",
            "seo/setup/launch-plan.md",
            "seo/setup/spend-guard.md",
            "seo/setup/setup-gap-audit.md",
            "seo/setup/tool-stack-report.md",
            "seo/setup/growth-roadmap.md",
        ],
        "do_not_load_raw": [
            "seo/setup/*.json",
            "seo/usage/usage-ledger.jsonl",
            "raw crawl/browser/API exports under seo/",
        ],
    }


def setup_readiness(gap: dict[str, Any]) -> dict[str, Any]:
    summary = gap.get("summary", {}) if isinstance(gap.get("summary"), dict) else {}
    missing_fields = gap.get("missing_fields", []) if isinstance(gap.get("missing_fields"), list) else []
    return {
        "score": gap.get("score"),
        "missing_count": int(summary.get("missing") or len(missing_fields)),
        "missing_fields": compact([str(field) for field in missing_fields], 12),
        "questionnaire_csv": "seo/setup/setup-questionnaire.csv",
        "answer_plan": "seo/setup/setup-answer-plan.md",
    }


def build_report(cfg_path: pathlib.Path) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    reports = load_reports(cfg_path, cfg, project_root)
    launch = reports["launch"]
    market = launch.get("market_matrix", {}) if isinstance(launch.get("market_matrix"), dict) else {}
    business_raw = launch.get("business_matrix", {}) if isinstance(launch.get("business_matrix"), dict) else {}
    business = {
        "project_type": business_raw.get("project_type") or cfg.get("project_type"),
        "business_model": list_value(business_raw.get("business_model")),
        "sales_channels": list_value(business_raw.get("sales_channels")),
        "local": boolish(business_raw.get("local")),
        "ecommerce": boolish(business_raw.get("ecommerce")),
        "organic": boolish(business_raw.get("organic")),
        "content": boolish(business_raw.get("content")),
        "video": boolish(business_raw.get("video")),
        "local_platforms": list_value(business_raw.get("local_platforms")),
        "paid_ads": business_raw.get("marketing", {}).get("paid_ads", {}) if isinstance(business_raw.get("marketing"), dict) else {},
        "analytics_tags": business_raw.get("marketing", {}).get("analytics_tags", {}) if isinstance(business_raw.get("marketing"), dict) else {},
        "marketing": business_raw.get("marketing", {}),
    }
    tool_axes = launch.get("tool_contract", {}) if isinstance(launch.get("tool_contract"), dict) else {}
    automation = launch.get("automation_contract", {}) if isinstance(launch.get("automation_contract"), dict) else {}
    human = launch.get("human_inputs", {}) if isinstance(launch.get("human_inputs"), dict) else {}
    guardrails = sorted(set(launch.get("policy_guards", []) + launch.get("approval_gates", [])))
    report: dict[str, Any] = {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "market_axes": {
            "country": market.get("country"),
            "region_profile": market.get("region_profile"),
            "region": market.get("region"),
            "city": market.get("city"),
            "languages": list_value(market.get("languages")),
            "search_engines": list_value(market.get("search_engines")),
            "yandex_region_code": market.get("yandex_region_code"),
            "google_gl": market.get("google_gl"),
            "google_hl": market.get("google_hl"),
            "timezone": market.get("timezone"),
        },
        "business_axes": business,
        "tool_axes": {key: list_value(value) for key, value in tool_axes.items()},
        "budget_caps": launch.get("budget_contract", {}),
        "subscription_controls": launch.get("subscription_controls", {}),
        "spend_axes": launch.get("spend_contract", {}),
        "automation_axes": automation,
        "human_inputs": {
            "env_names": sorted(name for name in human.get("env_names", []) if isinstance(name, str) and "=" not in name),
            "owner_summary": human.get("owner_summary", {}),
        },
        "guardrails": guardrails,
        "context_contract": context_contract(launch),
        "setup_readiness": setup_readiness(reports["gap"]),
        "source_reports": {
            "launch_plan": "seo/setup/launch-plan.md",
            "tool_stack": "seo/setup/tool-stack-report.md",
            "spend_guard": "seo/setup/spend-guard.md",
            "setup_gap_audit": "seo/setup/setup-gap-audit.md",
            "automation_recommendations": "seo/automations/automation-recommendations.md",
        },
    }
    report["decision_matrix"] = decision_matrix(report)
    report["action_packs"] = action_packs(report)
    report["next_commands"] = [
        "python3 ~/.codex/skills/seo-cycle/scripts/setup-blueprint.py --write",
        "python3 ~/.codex/skills/seo-cycle/scripts/context-pack.py --task \"<task>\" --write",
        "python3 ~/.codex/skills/seo-cycle/scripts/setup-gap-audit.py --write",
        "python3 ~/.codex/skills/seo-cycle/scripts/spend-guard.py --write",
        "python3 ~/.codex/skills/seo-cycle/scripts/task-router.py --task \"<approved roadmap action>\" --write",
    ]
    markdown = render_markdown(report)
    report["rendered_chars"] = len(markdown)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    market = report.get("market_axes", {})
    business = report.get("business_axes", {})
    budget = report.get("budget_caps", {})
    readiness = report.get("setup_readiness", {})
    lines = [
        "# seo-cycle setup blueprint",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Market: {market.get('country')} / {market.get('region')} / {market.get('city')}",
        f"- Engines: {', '.join(market.get('search_engines', [])) or '-'}",
        f"- Type/local/ecommerce: {business.get('project_type')} / {business.get('local')} / {business.get('ecommerce')}",
        f"- Missing setup fields: {readiness.get('missing_count')} / score={readiness.get('score')}",
        f"- Paid API/LLM/ads caps: ${budget.get('monthly_paid_api_usd_cap')} / ${budget.get('monthly_llm_usd_cap')} / ${budget.get('monthly_ads_usd_cap')}",
        "",
        "## First Read",
    ]
    for path in report.get("context_contract", {}).get("first_read", []):
        lines.append(f"- `{path}`")
    lines.extend(["", "## Decision Matrix", "| Axis | Current | Target | Owner | Guard |", "| --- | --- | --- | --- | --- |"])
    for row in report.get("decision_matrix", []):
        lines.append(f"| `{row['axis']}` | {row['current']} | {row['target']} | {row['owner']} | `{row['guard']}` |")
    lines.extend(["", "## Action Packs", "| Pack | Enabled | Tools | Guards | Command |", "| --- | --- | --- | --- | --- |"])
    for row in report.get("action_packs", []):
        lines.append(
            f"| `{row['id']}` | {row['enabled']} | {', '.join(row.get('tools', [])) or '-'} | "
            f"{', '.join(row.get('guards', [])) or '-'} | `{row['command']}` |"
        )
    lines.extend(["", "## Human Env Names"])
    for name in report.get("human_inputs", {}).get("env_names", []):
        lines.append(f"- `{name}`")
    lines.extend(["", "## Guardrails"])
    for guard in report.get("guardrails", []):
        lines.append(f"- `{guard}`")
    lines.extend(["", "## Next Commands"])
    for command in report.get("next_commands", []):
        lines.append(f"- `{command}`")
    return "\n".join(lines) + "\n"


def matrix_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    fieldnames = ["axis", "current", "target", "owner", "target_artifact", "guard", "next_command"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in report.get("decision_matrix", []):
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return buffer.getvalue()


def generated_yaml(report: dict[str, Any]) -> str:
    payload = {
        "version": report["version"],
        "generated": report["generated"],
        "project": report.get("project", {}),
        "market_axes": report.get("market_axes", {}),
        "business_axes": report.get("business_axes", {}),
        "budget_caps": report.get("budget_caps", {}),
        "tool_axes": report.get("tool_axes", {}),
        "automation_axes": report.get("automation_axes", {}),
        "guardrails": report.get("guardrails", []),
        "context_contract": report.get("context_contract", {}),
        "decision_matrix": report.get("decision_matrix", []),
        "action_packs": report.get("action_packs", []),
    }
    return dump_yaml(payload)


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    setup_dir = project_root / "seo" / "setup"
    write_text(project_root / "seo" / "setup-blueprint.generated.yaml", generated_yaml(report))
    write_text(setup_dir / "setup-blueprint.md", render_markdown(report))
    write_text(setup_dir / "setup-blueprint.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_text(setup_dir / "latest-setup-blueprint.md", render_markdown(report))
    write_text(setup_dir / "latest-setup-blueprint.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_text(setup_dir / "setup-matrix.csv", matrix_csv(report))
    return setup_dir / "setup-blueprint.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write setup blueprint artifacts under seo/setup.")
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
    report = build_report(cfg_path)
    if args.write:
        write_outputs(project_root, report)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
