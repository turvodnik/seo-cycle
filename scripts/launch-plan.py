#!/usr/bin/env python3
"""Build a compact per-project launch contract for seo-cycle.

The launch plan is the one-screen installer handoff: market, business model,
tool decisions, token/budget/subscription controls, approvals, human-secret
inputs, automations, and the first execution order. It never stores secret
values; only env variable names and artifact paths are emitted.
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

from seo_cycle_core.reports import write_artifacts

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

FREE_COSTS = {"free", "free_or_manual", "free_or_cabinet", "free_or_quota"}
GUARDED_COSTS = {"paid_api", "subscription_quota", "subscription_or_paid", "llm_tokens", "free_quota_then_paid"}
DEFAULT_MAX_EXECUTION_STEPS = 12


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


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "enabled", "да", "д"}
    return bool(value)


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


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


def load_tool_stack(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    report = load_policy_json(cfg, project_root, "tool_stack_report", "seo/setup/tool-stack-report.json")
    return report or run_json_script("tool-stack-recommender.py", cfg_path, project_root)


def load_growth_roadmap(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    report = load_policy_json(cfg, project_root, "growth_roadmap_report", "seo/setup/growth-roadmap.json")
    return report or run_json_script("growth-roadmap.py", cfg_path, project_root)


def load_onboarding(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    report = load_policy_json(cfg, project_root, "onboarding_playbook", "seo/setup/onboarding-playbook.json")
    return report or run_json_script("setup-onboarding.py", cfg_path, project_root)


def load_spend_guard(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    report = load_policy_json(cfg, project_root, "spend_guard_report", "seo/setup/spend-guard.json")
    return report or run_json_script("spend-guard.py", cfg_path, project_root)


def load_automation(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    report = load_policy_json(cfg, project_root, "automation_recommendations", "seo/automations/automation-recommendations.json")
    return report or run_json_script("automation-recommender.py", cfg_path, project_root)


def country(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    locale = cfg.get("locale", {}) if isinstance(cfg.get("locale"), dict) else {}
    return str(markets.get("primary_country") or locale.get("country") or "").upper()


def active_engines(cfg: dict[str, Any], intake: dict[str, Any]) -> list[str]:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    configured = markets.get("search_engines", {}) if isinstance(markets.get("search_engines"), dict) else {}
    if configured:
        return sorted(str(name) for name, enabled in configured.items() if boolish(enabled))
    return [
        str(engine.get("name"))
        for engine in cfg.get("engines", [])
        if isinstance(engine, dict) and engine.get("name")
    ]


def project_type(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    business = intake.get("business", {}) if isinstance(intake.get("business"), dict) else {}
    return str(business.get("project_type") or cfg.get("project_type") or "")


def business_flags(cfg: dict[str, Any], intake: dict[str, Any]) -> dict[str, bool]:
    pt = project_type(cfg, intake)
    marketing = intake.get("marketing", {}) if isinstance(intake.get("marketing"), dict) else {}
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    local_platforms = markets.get("local_platforms", {}) if isinstance(markets.get("local_platforms"), dict) else {}
    business_profile = cfg.get("business_profile", {}) if isinstance(cfg.get("business_profile"), dict) else {}
    has_address = isinstance(business_profile.get("address"), dict) and any(business_profile.get("address", {}).values())
    return {
        "ecommerce": pt == "ecommerce" or boolish(marketing.get("ecommerce_feeds")),
        "local": pt == "local_business" or boolish(marketing.get("local_seo")) or any(boolish(v) for v in local_platforms.values()) or has_address,
        "organic": boolish(marketing.get("organic_seo", True)),
        "content": boolish(marketing.get("content_marketing", True)),
        "video": boolish(marketing.get("video_youtube", False)),
    }


def market_matrix(cfg: dict[str, Any], intake: dict[str, Any]) -> dict[str, Any]:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    locale = cfg.get("locale", {}) if isinstance(cfg.get("locale"), dict) else {}
    return {
        "country": country(cfg, intake),
        "region_profile": cfg.get("region_profile"),
        "region": markets.get("primary_region") or locale.get("region"),
        "city": markets.get("primary_city") or locale.get("city"),
        "languages": markets.get("languages") or [locale.get("language")],
        "search_engines": active_engines(cfg, intake),
        "yandex_region_code": locale.get("yandex_region_code"),
        "google_gl": locale.get("google_gl"),
        "google_hl": locale.get("google_hl"),
        "timezone": locale.get("timezone"),
    }


def business_matrix(cfg: dict[str, Any], intake: dict[str, Any]) -> dict[str, Any]:
    business = intake.get("business", {}) if isinstance(intake.get("business"), dict) else {}
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    marketing = intake.get("marketing", {}) if isinstance(intake.get("marketing"), dict) else {}
    return {
        "project_type": project_type(cfg, intake),
        "business_model": business.get("business_model") or cfg.get("business_model", []),
        "sales_channels": business.get("sales_channels") or cfg.get("sales_channels", []),
        "target_audiences": business.get("target_audiences") or cfg.get("target_audiences", []),
        "conversion_goals": business.get("conversion_goals", []),
        "local_platforms": markets.get("local_platforms", {}),
        "marketing": {
            "organic_seo": boolish(marketing.get("organic_seo", True)),
            "content_marketing": boolish(marketing.get("content_marketing", True)),
            "local_seo": boolish(marketing.get("local_seo", False)),
            "ecommerce_feeds": boolish(marketing.get("ecommerce_feeds", False)),
            "email_or_messenger": boolish(marketing.get("email_or_messenger", False)),
            "video_youtube": boolish(marketing.get("video_youtube", False)),
            "paid_ads": marketing.get("paid_ads", {}),
            "analytics_tags": marketing.get("analytics_tags", {}),
        },
        **business_flags(cfg, intake),
    }


def token_contract(cfg: dict[str, Any]) -> dict[str, Any]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    token = governance.get("token_policy", {}) if isinstance(governance.get("token_policy"), dict) else {}
    return {
        "raw_data_in_context": boolish(token.get("raw_data_in_context", False)),
        "progressive_disclosure": boolish(token.get("progressive_disclosure", True)),
        "require_distillate_before_synthesis": boolish(token.get("require_distillate_before_synthesis", True)),
        "max_context_input_tokens_per_phase": int(numeric(token.get("max_context_input_tokens_per_phase", 45000), 45000)),
        "max_output_tokens_per_artifact": int(numeric(token.get("max_output_tokens_per_artifact", 7000), 7000)),
        "max_raw_rows_loaded": int(numeric(token.get("max_raw_rows_loaded", 200), 200)),
        "distillate_max_lines": int(numeric(token.get("distillate_max_lines", 220), 220)),
        "cache_first": boolish(token.get("cache_first", True)),
        "browser_session_budget_minutes": int(numeric(token.get("browser_session_budget_minutes", 20), 20)),
        "browser_pages_per_phase_cap": int(numeric(token.get("browser_pages_per_phase_cap", 20), 20)),
    }


def budget_contract(cfg: dict[str, Any], tool_budget: dict[str, Any]) -> dict[str, Any]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    budget = governance.get("budget_policy", {}) if isinstance(governance.get("budget_policy"), dict) else {}
    money = tool_budget.get("money_budget", {}) if isinstance(tool_budget.get("money_budget"), dict) else {}
    return {
        "monthly_total_usd_cap": numeric(money.get("monthly_total_usd_cap", budget.get("monthly_total_usd_cap", 0))),
        "monthly_paid_api_usd_cap": numeric(money.get("monthly_paid_api_usd_cap", budget.get("monthly_paid_api_usd_cap", 0))),
        "monthly_llm_usd_cap": numeric(money.get("monthly_llm_usd_cap", budget.get("monthly_llm_usd_cap", 0))),
        "monthly_ads_usd_cap": numeric(money.get("monthly_ads_usd_cap", 0)),
        "require_approval_over_usd": numeric(money.get("require_approval_over_usd", budget.get("require_approval_over_usd", 0))),
        "cloud_budget_alert_usd": numeric(money.get("cloud_budget_alert_usd", budget.get("cloud_budget_alert_usd", 5)), 5),
        "ads_spend_enabled": boolish(money.get("ads_spend_enabled", budget.get("ads_spend_enabled", False))),
        "paid_tools_default": str(budget.get("paid_tools_default") or "approval_only"),
    }


def subscription_controls(cfg: dict[str, Any], tool_budget: dict[str, Any]) -> dict[str, Any]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    cfg_subs = governance.get("subscriptions", {}) if isinstance(governance.get("subscriptions"), dict) else {}
    tb_subs = tool_budget.get("subscriptions", {}) if isinstance(tool_budget.get("subscriptions"), dict) else {}
    names = sorted(set(cfg_subs) | set(tb_subs))
    result: dict[str, Any] = {}
    for name in names:
        node: dict[str, Any] = {}
        if isinstance(cfg_subs.get(name), dict):
            node.update(cfg_subs[name])
        if isinstance(tb_subs.get(name), dict):
            node.update(tb_subs[name])
        result[name] = node
    return result


def decisions(tool_stack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return tool_stack.get("decisions", {}) if isinstance(tool_stack.get("decisions"), dict) else {}


def tools_by(decisions_by_tool: dict[str, dict[str, Any]], *, category: str | None = None, costs: set[str] | None = None, values: set[str] | None = None) -> list[str]:
    rows = []
    for tool_id, row in decisions_by_tool.items():
        if not isinstance(row, dict):
            continue
        if category and row.get("category") != category:
            continue
        if costs and str(row.get("cost")) not in costs:
            continue
        if values and row.get("decision") not in values:
            continue
        rows.append(tool_id)
    return sorted(rows)


def tool_contract(tool_stack: dict[str, Any]) -> dict[str, Any]:
    by_tool = decisions(tool_stack)
    active_values = {"enabled", "report_only", "approval_required"}
    disabled_values = {"disabled", "not_applicable"}
    return {
        "free_first": tools_by(by_tool, costs=FREE_COSTS, values=active_values),
        "search_consoles": tools_by(by_tool, category="search_console", values=active_values),
        "keyword_sources": tools_by(by_tool, category="keyword_research", values=active_values),
        "local_profiles": tools_by(by_tool, category="local_seo", values=active_values),
        "merchant_feeds": tools_by(by_tool, category="merchant", values=active_values),
        "ai_visibility": tools_by(by_tool, category="ai_visibility", values=active_values),
        "ads_planning_or_approval": tools_by(by_tool, category="ads", values=active_values),
        "tracking_approval": tools_by(by_tool, category="analytics", values={"approval_required"}),
        "guarded_paid_or_quota": tools_by(by_tool, costs=GUARDED_COSTS, values=active_values),
        "forbidden_or_disabled": tools_by(by_tool, values=disabled_values),
    }


def env_names_from(tool_stack: dict[str, Any], onboarding: dict[str, Any]) -> list[str]:
    names: set[str] = set()
    for name in onboarding.get("secret_env_names", []):
        if isinstance(name, str) and name and "=" not in name:
            names.add(name)
    for row in decisions(tool_stack).values():
        if not isinstance(row, dict):
            continue
        if row.get("decision") not in {"enabled", "report_only", "approval_required"}:
            continue
        for name in row.get("env", []):
            if isinstance(name, str) and name and "=" not in name:
                names.add(name)
    return sorted(names)


def approval_gates_from(tool_stack: dict[str, Any], growth_roadmap: dict[str, Any], onboarding: dict[str, Any]) -> list[str]:
    gates: set[str] = set()
    for row in decisions(tool_stack).values():
        if isinstance(row, dict):
            gates.update(str(gate) for gate in row.get("approval_gates", []) if gate)
    gates.update(str(gate) for gate in growth_roadmap.get("approval_gates", []) if gate)
    gates.update(str(gate) for gate in onboarding.get("approval_gates", []) if gate)
    return sorted(gates)


def policy_guards(cfg: dict[str, Any], market: dict[str, Any], token: dict[str, Any], budget: dict[str, Any], gates: list[str]) -> list[str]:
    guards = ["cache_first" if token.get("cache_first") else "cache_review_required"]
    if not token.get("raw_data_in_context"):
        guards.append("raw_data_on_disk")
    if token.get("require_distillate_before_synthesis"):
        guards.append("distillate_before_llm")
    if market.get("country") == "RU":
        guards.append("rf_foreign_tracking_guard")
    if budget.get("monthly_paid_api_usd_cap", 0) <= 0:
        guards.append("paid_api_approval_guard")
    if budget.get("monthly_llm_usd_cap", 0) <= 0:
        guards.append("llm_spend_approval_guard")
    if not budget.get("ads_spend_enabled"):
        guards.append("ads_spend_disabled")
    guards.extend(f"approval:{gate}" for gate in gates)
    return sorted(set(guards))


def automation_contract(automation: dict[str, Any]) -> dict[str, Any]:
    overlay = automation.get("policy_overlay", {}) if isinstance(automation.get("policy_overlay"), dict) else {}
    planned = overlay.get("planned_automations", {}) if isinstance(overlay.get("planned_automations"), dict) else {}
    enabled = sorted(task_id for task_id, row in planned.items() if isinstance(row, dict) and row.get("enabled"))
    report_only = sorted(task_id for task_id, row in planned.items() if isinstance(row, dict) and row.get("enabled") and row.get("mode") == "report_only")
    approval_only = sorted(task_id for task_id, row in planned.items() if isinstance(row, dict) and row.get("enabled") and row.get("mode") == "approval_only")
    return {
        "default_mode": overlay.get("default_mode"),
        "create_schedules": boolish(overlay.get("create_schedules", False)),
        "planned_count": len(planned),
        "enabled": enabled,
        "report_only": report_only,
        "approval_only": approval_only,
    }


def spend_contract(spend_guard: dict[str, Any]) -> dict[str, Any]:
    rows = spend_guard.get("service_guards", []) if isinstance(spend_guard.get("service_guards"), list) else []
    allowed = sorted(row.get("service") for row in rows if isinstance(row, dict) and row.get("allowed_now") and row.get("service"))
    blocked_or_approval = sorted(
        row.get("service")
        for row in rows
        if isinstance(row, dict) and row.get("service") and not row.get("allowed_now") and row.get("status") in {"blocked", "approval_required"}
    )
    return {
        "month": spend_guard.get("month"),
        "service_count": len(rows),
        "allowed_now": allowed,
        "blocked_or_approval": blocked_or_approval,
        "token_guards": spend_guard.get("token_guards", []),
        "preflight_commands": spend_guard.get("preflight_commands", {}),
    }


def execution_order(report: dict[str, Any], max_steps: int) -> list[str]:
    order = [
        "review seo/project-intake.yaml and seo/setup/launch-plan.md",
        "run project-profile.py --write; apply only after review",
        "run tool-stack-recommender.py --write; approve gated tools only as needed",
        "run spend-guard.py --write before paid/API/LLM/subscription usage",
        "fill human-secret env names in .env/provider consoles",
        "run setup-onboarding.py --write and complete human/approval steps",
        "run setup-control-plane.py --write before first SEO cycle",
        "start from seo/setup/growth-roadmap.md top approved action",
        "route selected action with task-router.py --write",
        "run usage-ledger.py check before paid/API/LLM/browser spend",
        "generate automation-plan.py --write --include-disabled; install schedules only after policy approval",
    ]
    if report.get("business_matrix", {}).get("ecommerce"):
        order.insert(6, "review merchant/feed diagnostics before product SEO changes")
    if report.get("business_matrix", {}).get("local"):
        order.insert(6, "review local profiles/NAP/maps before local SEO changes")
    return order[:max_steps]


def build_report(cfg_path: pathlib.Path, max_execution_steps: int = DEFAULT_MAX_EXECUTION_STEPS) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    intake = load_yaml(policy_path(cfg, project_root, "project_intake", "seo/project-intake.yaml"))
    tool_budget = load_yaml(policy_path(cfg, project_root, "tool_budget", "seo/tool-budget.yaml"))
    tool_stack = load_tool_stack(cfg_path, cfg, project_root)
    growth_roadmap = load_growth_roadmap(cfg_path, cfg, project_root)
    onboarding = load_onboarding(cfg_path, cfg, project_root)
    spend_guard = load_spend_guard(cfg_path, cfg, project_root)
    automation = load_automation(cfg_path, cfg, project_root)
    market = market_matrix(cfg, intake)
    business = business_matrix(cfg, intake)
    token = token_contract(cfg)
    budget = budget_contract(cfg, tool_budget)
    gates = approval_gates_from(tool_stack, growth_roadmap, onboarding)
    report: dict[str, Any] = {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "market_matrix": market,
        "business_matrix": business,
        "token_contract": token,
        "budget_contract": budget,
        "subscription_controls": subscription_controls(cfg, tool_budget),
        "spend_contract": spend_contract(spend_guard),
        "tool_contract": tool_contract(tool_stack),
        "automation_contract": automation_contract(automation),
        "human_inputs": {
            "env_names": env_names_from(tool_stack, onboarding),
            "owner_summary": onboarding.get("owner_summary", {}),
        },
        "approval_gates": gates,
        "policy_guards": policy_guards(cfg, market, token, budget, gates),
        "limits": {
            "max_execution_steps": max_execution_steps,
            "raw_rows_loaded_cap": token.get("max_raw_rows_loaded"),
            "distillate_max_lines": token.get("distillate_max_lines"),
        },
    }
    report["execution_order"] = execution_order(report, max_execution_steps)
    report["next_actions"] = [
        "Use this launch plan as the first project screen; load detailed artifacts only when a row requires it.",
        "Keep secrets in `.env` or provider consoles; this file lists env names only.",
        "Do not run paid, tracking, ads, index-submission, publishing, or schedules until approval gates are cleared.",
    ]
    return report


def generated_yaml(report: dict[str, Any]) -> str:
    payload = {
        "version": report["version"],
        "generated": report["generated"],
        "project": report.get("project", {}),
        "market_matrix": report.get("market_matrix", {}),
        "business_matrix": report.get("business_matrix", {}),
        "token_contract": report.get("token_contract", {}),
        "budget_contract": report.get("budget_contract", {}),
        "spend_contract": report.get("spend_contract", {}),
        "tool_contract": report.get("tool_contract", {}),
        "automation_contract": report.get("automation_contract", {}),
        "human_inputs": report.get("human_inputs", {}),
        "approval_gates": report.get("approval_gates", []),
        "policy_guards": report.get("policy_guards", []),
        "execution_order": report.get("execution_order", []),
        "next_actions": report.get("next_actions", []),
    }
    return dump_yaml(payload)


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    market = report.get("market_matrix", {})
    business = report.get("business_matrix", {})
    token = report.get("token_contract", {})
    budget = report.get("budget_contract", {})
    tools = report.get("tool_contract", {})
    spend = report.get("spend_contract", {})
    automation = report.get("automation_contract", {})
    lines = [
        "# seo-cycle launch plan",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Market: {market.get('country')} / {market.get('region')} / {market.get('city')}",
        f"- Search engines: {', '.join(market.get('search_engines', [])) or '-'}",
        f"- Project type: {business.get('project_type')}",
        f"- Ecommerce/local/content: {business.get('ecommerce')} / {business.get('local')} / {business.get('content')}",
        "",
        "## Low-Token Contract",
        f"- Raw data in context: {token.get('raw_data_in_context')}",
        f"- Cache-first: {token.get('cache_first')}",
        f"- Distillate before synthesis: {token.get('require_distillate_before_synthesis')}",
        f"- Max raw rows loaded: {token.get('max_raw_rows_loaded')}",
        f"- Distillate max lines: {token.get('distillate_max_lines')}",
        "",
        "## Budget Contract",
        f"- Monthly total USD cap: ${budget.get('monthly_total_usd_cap')}",
        f"- Monthly paid API USD cap: ${budget.get('monthly_paid_api_usd_cap')}",
        f"- Monthly LLM USD cap: ${budget.get('monthly_llm_usd_cap')}",
        f"- Monthly ads USD cap: ${budget.get('monthly_ads_usd_cap')}",
        f"- Cloud budget alert USD: ${budget.get('cloud_budget_alert_usd')}",
        f"- Spend guard services: {spend.get('service_count')}",
        f"- Spend blocked/approval: {', '.join(spend.get('blocked_or_approval', [])) or '-'}",
        "",
        "## Tools",
        f"- Free-first: {', '.join(tools.get('free_first', [])) or '-'}",
        f"- Search consoles: {', '.join(tools.get('search_consoles', [])) or '-'}",
        f"- Local profiles: {', '.join(tools.get('local_profiles', [])) or '-'}",
        f"- Merchant feeds: {', '.join(tools.get('merchant_feeds', [])) or '-'}",
        f"- Guarded paid/quota: {', '.join(tools.get('guarded_paid_or_quota', [])) or '-'}",
        f"- Disabled/not applicable: {', '.join(tools.get('forbidden_or_disabled', [])) or '-'}",
        "",
        "## Human Inputs",
    ]
    for name in report.get("human_inputs", {}).get("env_names", []):
        lines.append(f"- `{name}`")
    lines.extend(["", "## Approval Gates"])
    for gate in report.get("approval_gates", []):
        lines.append(f"- {gate}")
    lines.extend(
        [
            "",
            "## Automations",
            f"- Default mode: {automation.get('default_mode')}",
            f"- Create schedules: {automation.get('create_schedules')}",
            f"- Enabled: {', '.join(automation.get('enabled', [])) or '-'}",
            "",
            "## Execution Order",
        ]
    )
    for idx, item in enumerate(report.get("execution_order", []), start=1):
        lines.append(f"{idx}. {item}")
    lines.extend(["", "## Next Actions"])
    for item in report.get("next_actions", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Rules",
            "- This launch plan is secret-free: env variable names only, never values.",
            "- Load detailed reports only when this contract points to them.",
            "- Approval gates block paid tools, tracking tags, ads, publishing, indexing mutation, and schedule installs.",
        ]
    )
    return "\n".join(lines) + "\n"


def checklist_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["section", "item", "value"])
    writer.writeheader()
    for key, value in report.get("market_matrix", {}).items():
        writer.writerow({"section": "market", "item": key, "value": json.dumps(value, ensure_ascii=False)})
    for key, value in report.get("budget_contract", {}).items():
        writer.writerow({"section": "budget", "item": key, "value": value})
    for key, values in report.get("tool_contract", {}).items():
        writer.writerow({"section": "tools", "item": key, "value": ", ".join(values)})
    for name in report.get("human_inputs", {}).get("env_names", []):
        writer.writerow({"section": "human_inputs", "item": "env_name", "value": name})
    for gate in report.get("approval_gates", []):
        writer.writerow({"section": "approval_gates", "item": "gate", "value": gate})
    for idx, item in enumerate(report.get("execution_order", []), start=1):
        writer.writerow({"section": "execution_order", "item": str(idx), "value": item})
    return buffer.getvalue()


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    setup_dir = project_root / "seo" / "setup"
    markdown = render_markdown(report)
    write_artifacts(
        text_files={
            project_root / "seo" / "launch-plan.generated.yaml": generated_yaml(report),
            setup_dir / "launch-plan.md": markdown,
            setup_dir / "latest-launch-plan.md": markdown,
            setup_dir / "launch-checklist.csv": checklist_csv(report),
        },
        json_files={
            setup_dir / "launch-plan.json": report,
            setup_dir / "latest-launch-plan.json": report,
        },
    )
    return setup_dir / "launch-plan.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write launch plan artifacts under seo/setup.")
    parser.add_argument("--max-execution-steps", type=int, default=DEFAULT_MAX_EXECUTION_STEPS)
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
    report = build_report(cfg_path, max_execution_steps=args.max_execution_steps)
    if args.write:
        write_outputs(project_root, report)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
