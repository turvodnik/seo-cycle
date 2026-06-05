#!/usr/bin/env python3
"""Build a low-token execution route for one SEO/marketing task.

The router is read-only by default. It reads `seo-cycle.yaml`, local intake,
governance, and resolved sources, then returns a compact plan: which phases to
run, which artifacts to read, which sources are allowed, which gates require
approval, and the context/token limits for the task.
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

PAID_OR_QUOTA_SOURCES = {
    "neuronwriter",
    "google_cloud_nlp",
    "keys_so",
    "keyso",
    "serpstat",
    "spyfu",
    "dataforseo",
    "google_ads",
    "yandex_direct",
    "microsoft_ads",
    "answerthepublic",
    "perplexity",
}

TASKS: dict[str, dict[str, Any]] = {
    "setup": {
        "keywords": ["setup", "install", "onboarding", "настрой", "установ", "запуск", "подключ"],
        "phases": ["phase0_setup"],
        "sources": ["robots_sitemap", "schema_crawl"],
        "safe_actions": ["validate_config", "setup_control_plane", "governance_report", "project_intake"],
        "approval": [],
        "automation": "none",
    },
    "technical_audit": {
        "keywords": ["audit", "crawl", "robots", "sitemap", "canonical", "index", "индекс", "аудит", "ошибк", "noindex", "bricks"],
        "phases": ["phase1_site_audit"],
        "sources": ["google_search_console", "yandex_webmaster_history", "bing_webmaster", "pagespeed_crux", "schema_crawl"],
        "safe_actions": ["robots_sitemap_check", "public_pagespeed_check", "read_only_index_status"],
        "approval": ["index_submission", "destructive_indexing_change", "bulk_noindex_or_robots_change"],
        "automation": "weekly_read_only_health",
    },
    "keyword_research": {
        "keywords": ["keyword", "semantic", "cluster", "wordstat", "keys", "семантик", "ключ", "кластер", "ядро"],
        "phases": ["phase2_keyword_research", "phase3_cluster_intent"],
        "sources": [
            "yandex_wordstat",
            "yandex_wordstat_deep",
            "yandex_suggest",
            "google_suggest",
            "google_trends",
            "google_search_console",
            "keyso",
            "serpstat",
            "answerthepublic",
            "llm_cli",
            "perplexity",
        ],
        "safe_actions": ["cache_check", "source_resolution", "distillate_merge"],
        "approval": ["paid_api_run", "browser_mass_collection"],
        "automation": "monthly_keyword_refresh",
    },
    "content_plan": {
        "keywords": ["content plan", "brief", "контент", "бриф", "план", "темы", "стать"],
        "phases": ["phase3_cluster_intent", "phase4_entity_map", "phase5_content_plan"],
        "sources": ["neuronwriter", "google_cloud_nlp", "llm_cli", "perplexity", "google_search_console", "yandex_webmaster_history"],
        "safe_actions": ["cache_check", "entity_map", "content_brief"],
        "approval": ["paid_api_run"],
        "automation": "monthly_keyword_refresh",
    },
    "entity_audit": {
        "keywords": ["entity", "nlp", "сущност", "google nlp", "schema", "structured data", "schema.org"],
        "phases": ["phase4_entity_map", "phase8_schema"],
        "sources": ["google_cloud_nlp", "neuronwriter", "schema_crawl", "llm_cli"],
        "safe_actions": ["cached_entity_audit", "schema_validation"],
        "approval": ["paid_api_run", "schema_change", "whole_site_paid_nlp"],
        "automation": "none",
    },
    "content_refresh": {
        "keywords": ["refresh", "rewrite", "обнов", "перепис", "улучш", "rescue", "description", "title", "h1"],
        "phases": ["phase1_site_audit", "phase4_entity_map", "phase6_writing", "phase10_iteration"],
        "sources": ["google_search_console", "yandex_webmaster_history", "neuronwriter", "google_cloud_nlp", "llm_cli", "perplexity"],
        "safe_actions": ["content_refresh_candidates", "fact_check", "stop_words_check"],
        "approval": ["content_rewrite", "paid_api_run", "publishing"],
        "automation": "monthly_keyword_refresh",
    },
    "publishing": {
        "keywords": ["publish", "wordpress", "woocommerce", "опубли", "залей", "cms", "wp"],
        "phases": ["phase6_writing", "phase7_publishing", "phase8_schema"],
        "sources": ["wordpress", "woocommerce", "schema_crawl", "indexnow"],
        "safe_actions": ["dry_run_publish", "schema_validation"],
        "approval": ["publishing", "index_submission", "schema_change"],
        "automation": "none",
    },
    "ecommerce_feed": {
        "keywords": ["merchant", "feed", "товар", "фид", "woocommerce", "price", "availability", "yml"],
        "phases": ["phase1_site_audit", "phase8_schema", "phase9_monitoring"],
        "sources": ["google_merchant", "yandex_merchant", "woocommerce", "schema_crawl"],
        "safe_actions": ["merchant_feed_errors_report", "product_schema_mismatch_report"],
        "approval": ["merchant_feed_change", "publishing"],
        "automation": "ecommerce_feed_quality",
    },
    "local_seo": {
        "keywords": ["local", "maps", "карты", "яндекс бизнес", "google business", "2gis", "отзывы", "nap"],
        "phases": ["phase1_site_audit", "phase5_content_plan", "phase9_monitoring"],
        "sources": ["yandex_business_maps", "google_business_profile", "bing_places", "2gis", "review_velocity"],
        "safe_actions": ["maps_profile_check", "reviews_velocity_report"],
        "approval": ["local_business_profile_change", "publishing"],
        "automation": "local_seo_reputation",
    },
    "ads": {
        "keywords": ["ads", "ppc", "direct", "реклама", "директ", "google ads", "microsoft ads", "кампан"],
        "phases": ["marketing_strategy", "paid_search_plan"],
        "sources": ["google_ads", "yandex_direct", "microsoft_ads", "spyfu", "serpstat"],
        "safe_actions": ["roi_projection", "keyword_gap_report"],
        "approval": ["paid_ads_launch", "paid_api_run"],
        "automation": "none",
    },
    "analytics": {
        "keywords": ["analytics", "ga4", "metrika", "tag", "gtm", "clarity", "метрик", "аналитик", "счетчик", "пиксел"],
        "phases": ["measurement_plan", "phase9_monitoring"],
        "sources": ["google_search_console", "yandex_webmaster_history", "bing_webmaster", "yandex_metrika", "ga4"],
        "safe_actions": ["read_only_index_status", "measurement_plan"],
        "approval": ["tracking_tag_install"],
        "automation": "weekly_read_only_health",
    },
    "ai_visibility": {
        "keywords": ["ai overview", "copilot", "perplexity", "chatgpt", "claude", "gemini", "deepseek", "ai visibility", "аi", "ии", "видимость"],
        "phases": ["ai_visibility_audit", "phase4_entity_map", "phase10_iteration"],
        "sources": ["google_ai_overview", "bing_copilot", "perplexity", "openai_chatgpt", "claude", "gemini", "deepseek"],
        "safe_actions": ["ai_visibility_prompts_check", "cited_competitors_report"],
        "approval": ["browser_mass_collection", "paid_api_run"],
        "automation": "monthly_ai_visibility",
    },
    "automation": {
        "keywords": ["automation", "cron", "schedule", "автомат", "распис", "monitor", "монитор"],
        "phases": ["automation_planning"],
        "sources": ["automation_policy", "governance"],
        "safe_actions": ["automation_plan_review"],
        "approval": ["schedule_install"],
        "automation": "review_all",
    },
}


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


def run_json(command: list[str], cwd: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or proc.stdout.strip(), "exit_code": proc.returncode}
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"error": "invalid json", "exit_code": proc.returncode}


def classify_task(task: str, explicit: str | None) -> str:
    if explicit:
        if explicit not in TASKS:
            raise SystemExit(f"ERROR: unknown task type `{explicit}`. Available: {', '.join(sorted(TASKS))}")
        return explicit

    normalized = task.lower()
    scores: dict[str, int] = {}
    for task_type, meta in TASKS.items():
        score = 0
        for keyword in meta["keywords"]:
            if keyword.lower() in normalized:
                score += 2 if len(keyword) > 4 else 1
        scores[task_type] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "technical_audit"


def intake_tool_enabled(intake: dict[str, Any], source: str) -> bool:
    tools = intake.get("tools", {}) if isinstance(intake.get("tools"), dict) else {}
    for key in ("free_first", "paid_or_quota_guarded", "ai_visibility"):
        values = tools.get(key, []) if isinstance(tools.get(key), list) else []
        if source in values:
            return True
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    local_platforms = markets.get("local_platforms", {}) if isinstance(markets.get("local_platforms"), dict) else {}
    aliases = {
        "2gis": "two_gis",
        "google_business_profile": "google_business_profile",
        "yandex_business_maps": "yandex_business",
        "bing_places": "bing_places",
    }
    alias = aliases.get(source)
    return bool(alias and local_platforms.get(alias))


def source_enabled(cfg: dict[str, Any], intake: dict[str, Any], source: str, active: dict[str, Any]) -> bool:
    if source in {"robots_sitemap", "schema_crawl", "pagespeed_crux", "wordpress", "woocommerce", "review_velocity", "automation_policy", "governance"}:
        return True
    if intake_tool_enabled(intake, source):
        return True
    if source in active:
        return True
    node = (cfg.get("sources", {}) or {}).get(source)
    return isinstance(node, dict) and bool(node.get("enabled"))


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get(key, default))


def load_project_policies(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    intake = load_yaml(policy_path(cfg, project_root, "project_intake", "seo/project-intake.yaml"))
    tool_budget = load_yaml(policy_path(cfg, project_root, "tool_budget", "seo/tool-budget.yaml"))
    automation_policy = load_yaml(policy_path(cfg, project_root, "automation_policy", "seo/automation-policy.yaml"))
    return {"intake": intake, "tool_budget": tool_budget, "automation_policy": automation_policy}


def governance_caps(cfg: dict[str, Any], tool_budget: dict[str, Any]) -> dict[str, Any]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    token_policy = governance.get("token_policy", {}) if isinstance(governance.get("token_policy"), dict) else {}
    budget_policy = governance.get("budget_policy", {}) if isinstance(governance.get("budget_policy"), dict) else {}
    tool_tokens = tool_budget.get("token_budget", {}) if isinstance(tool_budget.get("token_budget"), dict) else {}
    tool_money = tool_budget.get("money_budget", {}) if isinstance(tool_budget.get("money_budget"), dict) else {}
    return {
        "raw_data_in_context": token_policy.get("raw_data_in_context", tool_tokens.get("raw_data_in_context", False)),
        "cache_first": token_policy.get("cache_first", tool_tokens.get("cache_first", True)),
        "progressive_disclosure": token_policy.get("progressive_disclosure", tool_tokens.get("progressive_disclosure", True)),
        "max_context_input_tokens_per_phase": token_policy.get("max_context_input_tokens_per_phase", tool_tokens.get("max_context_input_tokens_per_phase", 45000)),
        "max_output_tokens_per_artifact": token_policy.get("max_output_tokens_per_artifact", tool_tokens.get("max_output_tokens_per_artifact", 7000)),
        "max_raw_rows_loaded": token_policy.get("max_raw_rows_loaded", tool_tokens.get("max_raw_rows_loaded", 200)),
        "distillate_max_lines": token_policy.get("distillate_max_lines", tool_tokens.get("distillate_max_lines", 220)),
        "browser_session_budget_minutes": token_policy.get("browser_session_budget_minutes", tool_tokens.get("browser_session_budget_minutes", 20)),
        "browser_pages_per_phase_cap": token_policy.get("browser_pages_per_phase_cap", tool_tokens.get("browser_pages_per_phase_cap", 20)),
        "monthly_total_usd_cap": budget_policy.get("monthly_total_usd_cap", tool_money.get("monthly_total_usd_cap", 0)),
        "monthly_paid_api_usd_cap": budget_policy.get("monthly_paid_api_usd_cap", tool_money.get("monthly_paid_api_usd_cap", 0)),
        "monthly_llm_usd_cap": budget_policy.get("monthly_llm_usd_cap", tool_money.get("monthly_llm_usd_cap", 0)),
        "require_approval_over_usd": budget_policy.get("require_approval_over_usd", tool_money.get("require_approval_over_usd", 0)),
        "ads_spend_enabled": budget_policy.get("ads_spend_enabled", tool_money.get("ads_spend_enabled", False)),
    }


def country(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    locale = cfg.get("locale", {}) if isinstance(cfg.get("locale"), dict) else {}
    return str(markets.get("primary_country") or locale.get("country") or "").upper()


def automation_status(route_automation: str, automation_policy: dict[str, Any]) -> dict[str, Any]:
    if route_automation in {"none", ""}:
        return {"recommended": None, "enabled": False, "mode": None}
    if route_automation == "review_all":
        return {
            "recommended": "review_all",
            "enabled": bool(automation_policy.get("create_schedules")),
            "mode": automation_policy.get("default_mode", "approval_only"),
        }
    planned = automation_policy.get("planned_automations", {}) if isinstance(automation_policy.get("planned_automations"), dict) else {}
    node = planned.get(route_automation, {}) if isinstance(planned.get(route_automation), dict) else {}
    return {
        "recommended": route_automation,
        "enabled": bool(node.get("enabled")),
        "mode": node.get("mode", automation_policy.get("default_mode", "approval_only")),
        "cadence": node.get("cadence"),
    }


def build_route(cfg_path: pathlib.Path, task: str, explicit_type: str | None = None) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    policies = load_project_policies(cfg, project_root)
    intake = policies["intake"]
    caps = governance_caps(cfg, policies["tool_budget"])
    sources_report = run_json([sys.executable, str(skill_root() / "scripts/resolve-sources.py"), str(cfg_path), "--json"], project_root)
    usage_report = run_json([sys.executable, str(skill_root() / "scripts/usage-ledger.py"), "report", str(cfg_path), "--format", "json"], project_root)
    active_sources = sources_report.get("active", {}) if isinstance(sources_report.get("active"), dict) else {}
    task_type = classify_task(task, explicit_type)
    meta = TASKS[task_type]
    is_rf = country(cfg, intake) == "RU"

    source_rows = []
    approval_gates = set(meta.get("approval", []))
    for source in meta.get("sources", []):
        enabled = source_enabled(cfg, intake, source, active_sources)
        paid_or_quota = source in PAID_OR_QUOTA_SOURCES
        status = "enabled" if enabled else "not_enabled"
        reason = "active source or built-in safe check" if enabled else "not active for current profile/config"
        if paid_or_quota and enabled and caps.get("monthly_paid_api_usd_cap", 0) == 0:
            status = "approval_required"
            reason = "paid/quota source with zero paid API cap"
            approval_gates.add("paid_api_run")
        source_rows.append(
            {
                "source": source,
                "status": status,
                "paid_or_quota": paid_or_quota,
                "reason": reason,
            }
        )

    blocked: list[str] = []
    if task_type == "ads" and not caps.get("ads_spend_enabled"):
        blocked.append("Ads spend is disabled by budget policy; only planning/ROI work is allowed.")
    if task_type == "analytics" and is_rf:
        setup = intake.get("setup_decisions", {}) if isinstance(intake.get("setup_decisions"), dict) else {}
        if not setup.get("allow_foreign_tracking_tags_for_rf_project", False):
            blocked.append("RF project: foreign tracking tags/pixels require explicit local policy approval.")
    if caps.get("raw_data_in_context") is True:
        approval_gates.add("raw_data_context_exception")

    read_first = [
        str(policy_path(cfg, project_root, "setup_control_plane", "seo/setup/setup-control-plane.md")),
        str(policy_path(cfg, project_root, "upgrade_assistant", "seo/setup/upgrade-assistant.md")),
        str(policy_path(cfg, project_root, "setup_blueprint", "seo/setup/setup-blueprint.md")),
        str(policy_path(cfg, project_root, "access_key_assistant", "seo/setup/access-key-assistant.md")),
        str(policy_path(cfg, project_root, "setup_gap_audit_report", "seo/setup/setup-gap-audit.md")),
        str(policy_path(cfg, project_root, "setup_questionnaire", "seo/setup/setup-questionnaire.md")),
        str(policy_path(cfg, project_root, "setup_answer_plan", "seo/setup/setup-answer-plan.md")),
        str(policy_path(cfg, project_root, "tool_budget", "seo/tool-budget.yaml")),
        str(policy_path(cfg, project_root, "latest_usage_report", "seo/setup/latest-usage-ledger.md")),
        str(policy_path(cfg, project_root, "automation_policy", "seo/automation-policy.yaml")),
        str(policy_path(cfg, project_root, "project_intake", "seo/project-intake.yaml")),
    ]
    if task_type in {"content_plan", "entity_audit", "content_refresh", "ai_visibility"}:
        read_first.append(str(policy_path(cfg, project_root, "ai_visibility_prompts", "seo/ai-visibility-prompts.csv")))
        read_first.append(str(policy_path(cfg, project_root, "google_nlp_policy", "seo/entities/google-nlp-policy.yaml")))

    return {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "task": task,
        "task_type": task_type,
        "project": cfg.get("project", {}),
        "region_profile": cfg.get("region_profile"),
        "country": country(cfg, intake),
        "phases": meta["phases"],
        "safe_actions": meta["safe_actions"],
        "sources": source_rows,
        "approval_gates": sorted(approval_gates),
        "blocked_actions": blocked,
        "usage_ledger": {
            "status": usage_report.get("evaluation", {}).get("status"),
            "allowed": usage_report.get("evaluation", {}).get("allowed"),
            "month": usage_report.get("month"),
            "ledger_path": usage_report.get("ledger_path"),
        },
        "automation": automation_status(meta.get("automation"), policies["automation_policy"]),
        "context_contract": {
            "read_first": read_first,
            "do_not_load_raw": [
                "large CSV exports",
                "raw API JSON",
                "browser dumps",
                "full sitemap URL lists",
            ],
            "load_only": [
                "latest setup/governance/source reports",
                "distillates/top-N summaries",
                "specific URLs or rows needed for this task",
            ],
            "caps": caps,
        },
        "commands": [
            "python3 ~/.codex/skills/seo-cycle/scripts/setup-control-plane.py --write --skip-intake",
            f"python3 ~/.codex/skills/seo-cycle/scripts/task-router.py --task {json.dumps(task, ensure_ascii=False)} --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py report --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/governance-report.py --format md",
        ],
    }


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", text.strip()).strip("-").lower()
    return cleaned[:64] or "task"


def render_markdown(route: dict[str, Any]) -> str:
    project = route.get("project", {})
    caps = route.get("context_contract", {}).get("caps", {})
    lines = [
        "# seo-cycle task route",
        "",
        f"- Generated: {route.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Task: {route.get('task')}",
        f"- Task type: {route.get('task_type')}",
        f"- Region profile: {route.get('region_profile')} / country: {route.get('country')}",
        "",
        "## Phases",
    ]
    lines.extend(f"- {phase}" for phase in route.get("phases", []))

    lines.extend(["", "## Sources", "| Source | Status | Paid/quota | Reason |", "| --- | --- | --- | --- |"])
    for row in route.get("sources", []):
        lines.append(f"| {row['source']} | {row['status']} | {row['paid_or_quota']} | {row['reason']} |")

    lines.extend(["", "## Approval Gates"])
    gates = route.get("approval_gates", [])
    lines.append(", ".join(gates) if gates else "No approval gates for this route.")

    lines.extend(["", "## Blocked Actions"])
    blocked = route.get("blocked_actions", [])
    lines.extend(f"- {item}" for item in blocked) if blocked else lines.append("No blocked actions detected.")

    usage = route.get("usage_ledger", {})
    lines.extend(
        [
            "",
            "## Usage Ledger",
            f"- Status: {usage.get('status')}",
            f"- Allowed without approval: {usage.get('allowed')}",
            f"- Month: {usage.get('month')}",
            f"- Ledger: `{usage.get('ledger_path')}`",
        ]
    )

    automation = route.get("automation", {})
    lines.extend(
        [
            "",
            "## Automation",
            f"- Recommended: {automation.get('recommended')}",
            f"- Enabled: {automation.get('enabled')}",
            f"- Mode: {automation.get('mode')}",
            f"- Cadence: {automation.get('cadence')}",
            "",
            "## Context Contract",
            f"- raw_data_in_context: {caps.get('raw_data_in_context')}",
            f"- cache_first: {caps.get('cache_first')}",
            f"- max_context_input_tokens_per_phase: {caps.get('max_context_input_tokens_per_phase')}",
            f"- max_output_tokens_per_artifact: {caps.get('max_output_tokens_per_artifact')}",
            f"- max_raw_rows_loaded: {caps.get('max_raw_rows_loaded')}",
            f"- distillate_max_lines: {caps.get('distillate_max_lines')}",
            f"- browser_session_budget_minutes: {caps.get('browser_session_budget_minutes')}",
            f"- browser_pages_per_phase_cap: {caps.get('browser_pages_per_phase_cap')}",
            "",
            "## Read First",
        ]
    )
    for path in route.get("context_contract", {}).get("read_first", []):
        lines.append(f"- `{path}`")

    lines.extend(["", "## Do Not Load Raw"])
    for item in route.get("context_contract", {}).get("do_not_load_raw", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Safe Actions"])
    for action in route.get("safe_actions", []):
        lines.append(f"- {action}")

    return "\n".join(lines) + "\n"


def write_route(project_root: pathlib.Path, route: dict[str, Any]) -> pathlib.Path:
    out_dir = project_root / "seo" / "setup"
    routes_dir = out_dir / "task-routes"
    routes_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(f"{route['task_type']}-{route['task']}")
    md = render_markdown(route)
    json_text = json.dumps(route, ensure_ascii=False, indent=2) + "\n"
    (out_dir / "latest-task-route.md").write_text(md, encoding="utf-8")
    (out_dir / "latest-task-route.json").write_text(json_text, encoding="utf-8")
    (routes_dir / f"{slug}.md").write_text(md, encoding="utf-8")
    (routes_dir / f"{slug}.json").write_text(json_text, encoding="utf-8")
    return out_dir / "latest-task-route.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--task", default="first SEO cycle setup", help="Task text to classify and route.")
    parser.add_argument("--task-type", choices=sorted(TASKS), help="Override automatic task classification.")
    parser.add_argument("--write", action="store_true", help="Write seo/setup/latest-task-route.md/json and archived route.")
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

    route = build_route(cfg_path, args.task, args.task_type)
    if args.write:
        out = write_route(pathlib.Path(route["project_root"]), route)
        print(f"Wrote {out}")
    elif args.format == "json":
        print(json.dumps(route, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(route), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
