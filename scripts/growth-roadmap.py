#!/usr/bin/env python3
"""Generate a low-token SEO + marketing growth roadmap for one project.

The roadmap is a deterministic "next best actions" layer. It reads the project
config, intake, generated tool stack, automation recommendations, and budget
posture, then writes a compact prioritized backlog across technical SEO,
content/entities, local/ecommerce, AI visibility, CRO/marketing, and safe
automation. It never fetches external data and never prints secrets.
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

DEFAULT_MAX_ACTIONS = 12


LANE_META: dict[str, dict[str, Any]] = {
    "technical_foundation": {
        "title": "Technical SEO foundation",
        "why": "Indexability, robots, sitemap, schema, CWV, and CMS/editor noise must be clean before scaling.",
    },
    "search_evidence": {
        "title": "Search console evidence",
        "why": "Query, index, crawl, and sitemap data should guide priorities before broad generation.",
    },
    "ecommerce_revenue": {
        "title": "Ecommerce revenue pages",
        "why": "Feeds, category pages, product schema, and weak product/category pages drive commercial upside.",
    },
    "local_dominance": {
        "title": "Local and maps dominance",
        "why": "NAP, map categories, reviews, photos, and posts shape local-pack visibility.",
    },
    "content_entity_growth": {
        "title": "Content and entity growth",
        "why": "Entity coverage, SERP terms, internal links, and refresh queues improve topical relevance.",
    },
    "ai_visibility": {
        "title": "AI answer visibility",
        "why": "Prompt evidence across AI surfaces finds where brand/products are absent or misrepresented.",
    },
    "marketing_cro": {
        "title": "Marketing and CRO bridge",
        "why": "SEO needs conversion paths, offers, lead/order goals, and channel economics to turn traffic into results.",
    },
    "automation_control": {
        "title": "Automation control",
        "why": "Recurring checks should be report-only or approval-gated until policy, budgets, and evidence are stable.",
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


def country(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    locale = cfg.get("locale", {}) if isinstance(cfg.get("locale"), dict) else {}
    return str(markets.get("primary_country") or locale.get("country") or "").upper()


def project_type(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    business = intake.get("business", {}) if isinstance(intake.get("business"), dict) else {}
    return str(business.get("project_type") or cfg.get("project_type") or "")


def engines(cfg: dict[str, Any], intake: dict[str, Any]) -> set[str]:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    configured = markets.get("search_engines", {}) if isinstance(markets.get("search_engines"), dict) else {}
    if configured:
        return {str(name) for name, enabled in configured.items() if boolish(enabled)}
    return {
        str(engine.get("name"))
        for engine in cfg.get("engines", [])
        if isinstance(engine, dict) and engine.get("name")
    }


def has_any(values: Any) -> bool:
    if isinstance(values, dict):
        return any(boolish(value) for value in values.values())
    if isinstance(values, list):
        return bool(values)
    return boolish(values)


def business_flags(cfg: dict[str, Any], intake: dict[str, Any]) -> dict[str, bool]:
    pt = project_type(cfg, intake)
    marketing = intake.get("marketing", {}) if isinstance(intake.get("marketing"), dict) else {}
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    local_platforms = markets.get("local_platforms", {}) if isinstance(markets.get("local_platforms"), dict) else {}
    business_profile = cfg.get("business_profile", {}) if isinstance(cfg.get("business_profile"), dict) else {}
    has_address = isinstance(business_profile.get("address"), dict) and any(business_profile.get("address", {}).values())
    return {
        "ecommerce": pt == "ecommerce" or boolish(marketing.get("ecommerce_feeds")),
        "local": pt == "local_business" or boolish(marketing.get("local_seo")) or has_any(local_platforms) or has_address,
        "organic": boolish(marketing.get("organic_seo", True)),
        "content": boolish(marketing.get("content_marketing", True)),
    }


def governance_caps(cfg: dict[str, Any], tool_budget: dict[str, Any]) -> dict[str, Any]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    budget = governance.get("budget_policy", {}) if isinstance(governance.get("budget_policy"), dict) else {}
    token = governance.get("token_policy", {}) if isinstance(governance.get("token_policy"), dict) else {}
    tb_money = tool_budget.get("money_budget", {}) if isinstance(tool_budget.get("money_budget"), dict) else {}
    return {
        "monthly_total_usd_cap": numeric(tb_money.get("monthly_total_usd_cap", budget.get("monthly_total_usd_cap"))),
        "monthly_paid_api_usd_cap": numeric(tb_money.get("monthly_paid_api_usd_cap", budget.get("monthly_paid_api_usd_cap"))),
        "monthly_llm_usd_cap": numeric(tb_money.get("monthly_llm_usd_cap", budget.get("monthly_llm_usd_cap"))),
        "monthly_ads_usd_cap": numeric(tb_money.get("monthly_ads_usd_cap", 0)),
        "raw_data_in_context": boolish(token.get("raw_data_in_context", False)),
        "cache_first": boolish(token.get("cache_first", True)),
        "max_context_input_tokens_per_phase": numeric(token.get("max_context_input_tokens_per_phase", 45000), 45000),
        "distillate_max_lines": numeric(token.get("distillate_max_lines", 220), 220),
    }


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
    path = policy_path(cfg, project_root, "tool_stack_report", "seo/setup/tool-stack-report.json")
    report = load_json(path)
    if report:
        return report
    return run_json_script("tool-stack-recommender.py", cfg_path, project_root)


def load_automation(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    path = policy_path(cfg, project_root, "automation_recommendations", "seo/automations/automation-recommendations.json")
    report = load_json(path)
    if report:
        return report
    return run_json_script("automation-recommender.py", cfg_path, project_root)


def load_usage(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    path = policy_path(cfg, project_root, "latest_usage_report", "seo/setup/latest-usage-ledger.json")
    report = load_json(path)
    if report:
        return report
    return run_json_script("usage-ledger.py", cfg_path, project_root)


def tool_decisions(tool_stack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return tool_stack.get("decisions", {}) if isinstance(tool_stack.get("decisions"), dict) else {}


def usable_tool(decisions: dict[str, dict[str, Any]], tool_id: str) -> bool:
    row = decisions.get(tool_id, {})
    return row.get("decision") in {"enabled", "report_only", "approval_required"}


def tools_by_category(decisions: dict[str, dict[str, Any]], category: str) -> list[str]:
    return sorted(
        tool_id
        for tool_id, row in decisions.items()
        if isinstance(row, dict) and row.get("category") == category and row.get("decision") in {"enabled", "report_only", "approval_required"}
    )


def tool_gates(decisions: dict[str, dict[str, Any]], tools: list[str]) -> list[str]:
    gates: set[str] = set()
    for tool_id in tools:
        row = decisions.get(tool_id, {})
        gates.update(str(gate) for gate in row.get("approval_gates", []) if gate)
    return sorted(gates)


def action(
    action_id: str,
    lane: str,
    title: str,
    why: str,
    tools: list[str],
    approval_gates: list[str],
    impact: int,
    confidence: int,
    ease: int,
    next_step: str,
    evidence: list[str],
    mode: str = "report_only",
) -> dict[str, Any]:
    score = impact * confidence * ease
    return {
        "id": action_id,
        "lane": lane,
        "title": title,
        "mode": mode,
        "priority_score": score,
        "ice": {"impact": impact, "confidence": confidence, "ease": ease},
        "tools": sorted(set(tools)),
        "approval_gates": sorted(set(approval_gates)),
        "why": why,
        "next_step": next_step,
        "evidence": evidence,
    }


def build_actions(
    cfg: dict[str, Any],
    intake: dict[str, Any],
    tool_stack: dict[str, Any],
    automation: dict[str, Any],
    usage: dict[str, Any],
) -> list[dict[str, Any]]:
    cty = country(cfg, intake)
    flags = business_flags(cfg, intake)
    decisions = tool_decisions(tool_stack)
    actions: list[dict[str, Any]] = []

    technical_tools = [tool for tool in ("robots_sitemap", "schema_crawl", "pagespeed_crux", "robots_ai_content_signals") if usable_tool(decisions, tool)]
    actions.append(
        action(
            "technical_indexability_baseline",
            "technical_foundation",
            "Clean public indexability baseline",
            "Robots, sitemap, canonicals, schema, CWV, and editor/preview noise block scale if left unresolved.",
            technical_tools,
            tool_gates(decisions, technical_tools),
            9,
            9,
            8,
            "Run robots/sitemap/canonical/schema/PageSpeed checks and write a P0/P1/P2 issue list before content scale.",
            ["seo-cycle.yaml", "seo/setup/tool-stack-report.md"],
        )
    )

    console_tools = tools_by_category(decisions, "search_console")
    if console_tools:
        actions.append(
            action(
                "search_console_data_contract",
                "search_evidence",
                "Connect and normalize search-console evidence",
                "Real query, index, crawl, and sitemap evidence should steer all later priorities.",
                console_tools,
                tool_gates(decisions, console_tools),
                9,
                8,
                7,
                "Create a source-by-source pull checklist for GSC/Yandex/Bing and keep only top-N distillates in context.",
                ["seo/setup/tool-stack-report.md", "seo/setup/latest-sources.json"],
            )
        )

    if cty == "RU":
        actions.append(
            action(
                "rf_tracking_policy_guard",
                "technical_foundation",
                "Keep RF foreign tracking disabled unless policy allows it",
                "For RF projects, Google Analytics, Clarity, and similar foreign tags require explicit project policy approval.",
                ["google_analytics_4", "microsoft_clarity", "seo-data-collection-map"],
                ["tracking_tag_install"],
                8,
                9,
                9,
                "Use Search Console/Webmaster/Bing/PageSpeed/off-site audits first; document any tracking exception before tag work.",
                ["seo/seo-data-collection-map.md", "seo/setup/tool-stack-report.md"],
            )
        )

    if flags["ecommerce"]:
        merchant_tools = tools_by_category(decisions, "merchant")
        actions.append(
            action(
                "merchant_feed_quality_loop",
                "ecommerce_revenue",
                "Create merchant/feed quality loop",
                "Feed/product errors and weak product schema reduce commercial visibility and free listing quality.",
                merchant_tools or ["schema_crawl"],
                tool_gates(decisions, merchant_tools),
                9,
                8,
                6,
                "Audit top categories/products, feed errors, Product schema, availability, descriptions, and sitemap inclusion.",
                ["seo/setup/tool-stack-report.md", "seo/project-intake.yaml"],
                "approval_only" if tool_gates(decisions, merchant_tools) else "report_only",
            )
        )
        actions.append(
            action(
                "category_revenue_rescue_queue",
                "ecommerce_revenue",
                "Prioritize category/product pages that need index or content rescue",
                "Ecommerce gains usually come from important category and product pages that are thin, duplicated, or under-indexed.",
                console_tools + technical_tools,
                tool_gates(decisions, console_tools + technical_tools),
                10,
                7,
                6,
                "Build a bounded queue: revenue category pages, products with impressions/low CTR, 404/rest API noise, and missing meta/schema.",
                ["seo/setup/latest-task-route.md", "seo/setup/tool-stack-report.md"],
            )
        )

    if flags["local"]:
        local_tools = tools_by_category(decisions, "local_seo")
        actions.append(
            action(
                "local_profile_dominance",
                "local_dominance",
                "Build maps/local dominance checklist",
                "Map profiles, categories, NAP, photos, posts, and review velocity influence local demand capture.",
                local_tools,
                tool_gates(decisions, local_tools),
                9,
                8,
                6,
                "Compare top local competitors across enabled map ecosystems and generate category/review/photo/post catch-up tasks.",
                ["seo/project-intake.yaml", "business_profile"],
                "approval_only" if tool_gates(decisions, local_tools) else "report_only",
            )
        )

    entity_tools = [tool for tool in ("google_cloud_nlp", "neuronwriter", "keyso", "serpstat") if usable_tool(decisions, tool)]
    if flags["content"] or flags["organic"]:
        actions.append(
            action(
                "entity_audit_priority_urls",
                "content_entity_growth",
                "Run entity audit only for priority URLs",
                "Entity/NLP tools are useful but should be cached and restricted to important pages, not whole-site runs.",
                entity_tools,
                tool_gates(decisions, entity_tools),
                8,
                8,
                5,
                "Select home, top categories, weak indexed pages, and pages with title/H1/schema/text mismatch; cache every result.",
                ["seo/entities/google-nlp-policy.yaml", "seo/neuronwriter-limits.yaml", "seo/tool-budget.yaml"],
                "approval_only" if tool_gates(decisions, entity_tools) else "report_only",
            )
        )
        actions.append(
            action(
                "content_refresh_and_internal_links",
                "content_entity_growth",
                "Create refresh and internal-link queue",
                "A small evidence-backed refresh queue beats broad generation and keeps token spend low.",
                technical_tools + console_tools,
                tool_gates(decisions, technical_tools + console_tools),
                8,
                7,
                7,
                "Generate top 20 refresh candidates from index/query/schema/entity gaps and assign hub/category/internal-link targets.",
                ["seo/setup/latest-task-route.md", "seo/setup/latest-usage-ledger.md"],
            )
        )

    ai_tools = tools_by_category(decisions, "ai_visibility") + ["robots_ai_content_signals"]
    ai_tools = [tool for tool in ai_tools if usable_tool(decisions, tool)]
    if ai_tools:
        actions.append(
            action(
                "ai_answer_visibility_monitor",
                "ai_visibility",
                "Monitor AI-answer visibility with evidence fields",
                "AI answer tools help find missing brand/product/entity mentions, but prompts and evidence must be bounded.",
                ai_tools,
                tool_gates(decisions, ai_tools),
                7,
                7,
                6,
                "Use `seo/ai-visibility-prompts.csv`; collect only answer, cited URLs, competitors, entities, and confidence notes.",
                ["seo/ai-visibility-prompts.csv", "seo/setup/tool-stack-report.md"],
                "approval_only" if tool_gates(decisions, ai_tools) else "report_only",
            )
        )

    ads_tools = tools_by_category(decisions, "ads")
    actions.append(
        action(
            "marketing_cro_measurement_bridge",
            "marketing_cro",
            "Connect SEO work to conversion and channel economics",
            "Technical and content wins need order/lead goals, funnel notes, and channel economics to become business results.",
            ads_tools + console_tools,
            tool_gates(decisions, ads_tools),
            8,
            6,
            7,
            "Create a lightweight CRO/ROI worksheet: target pages, conversion goal, lead/order value, channel role, and no-spend ads planning if allowed.",
            ["prompts/marketing-strategy.md", "scripts/roi-calc.py", "seo/project-intake.yaml"],
            "approval_only" if ads_tools else "report_only",
        )
    )

    planned = automation.get("policy_overlay", {}).get("planned_automations", {}) if isinstance(automation.get("policy_overlay"), dict) else {}
    enabled_automation = [name for name, node in planned.items() if isinstance(node, dict) and node.get("enabled")]
    if enabled_automation:
        actions.append(
            action(
                "automation_backlog_activation",
                "automation_control",
                "Turn recommended automations into reviewed report-only routines",
                "Automations should first produce reports and approval tickets before they mutate content, tags, schedules, or indexes.",
                enabled_automation,
                ["schedule_install"] if any((planned.get(name) or {}).get("mode") != "report_only" for name in enabled_automation) else [],
                7,
                8,
                6,
                "Review generated automation policy, keep schedules disabled until governance and automation-policy explicitly allow install.",
                ["seo/automations/automation-recommendations.md", "seo/automation-policy.generated.yaml"],
                "approval_only",
            )
        )

    if usage:
        status = usage.get("evaluation", {}).get("status")
        allowed = usage.get("evaluation", {}).get("allowed")
        if status and allowed is False:
            actions.append(
                action(
                    "budget_recovery_before_spend",
                    "automation_control",
                    "Resolve budget/usage blockers before paid work",
                    "Usage ledger is blocking or approval-gating spend; do not run paid tools until caps are updated.",
                    ["usage-ledger"],
                    ["paid_api_run", "llm_token_spend"],
                    9,
                    9,
                    8,
                    "Review `seo/setup/latest-usage-ledger.md`, adjust caps or scope, then record any approved spend.",
                    ["seo/setup/latest-usage-ledger.md"],
                    "approval_only",
                )
            )

    return actions


def trim_actions(actions: list[dict[str, Any]], max_actions: int) -> list[dict[str, Any]]:
    ranked = sorted(actions, key=lambda row: (-int(row["priority_score"]), row["lane"], row["id"]))
    return ranked[:max_actions]


def build_lanes(actions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lanes: dict[str, dict[str, Any]] = {}
    for row in actions:
        lane_id = row["lane"]
        meta = LANE_META.get(lane_id, {"title": lane_id, "why": ""})
        lane = lanes.setdefault(lane_id, {"title": meta["title"], "why": meta["why"], "actions": []})
        lane["actions"].append(row["id"])
    return lanes


def build_report(cfg_path: pathlib.Path, max_actions: int = DEFAULT_MAX_ACTIONS) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    intake = load_yaml(policy_path(cfg, project_root, "project_intake", "seo/project-intake.yaml"))
    tool_budget = load_yaml(policy_path(cfg, project_root, "tool_budget", "seo/tool-budget.yaml"))
    tool_stack = load_tool_stack(cfg_path, cfg, project_root)
    automation = load_automation(cfg_path, cfg, project_root)
    usage = load_usage(cfg_path, cfg, project_root)
    caps = governance_caps(cfg, tool_budget)
    actions = trim_actions(build_actions(cfg, intake, tool_stack, automation, usage), max_actions)
    lanes = build_lanes(actions)
    gates = sorted({gate for row in actions for gate in row.get("approval_gates", [])})
    return {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "market": {
            "country": country(cfg, intake),
            "region_profile": cfg.get("region_profile"),
            "engines": sorted(engines(cfg, intake)),
        },
        "business": {
            "project_type": project_type(cfg, intake),
            **business_flags(cfg, intake),
        },
        "limits": {
            "max_actions": max_actions,
            "raw_data_in_context": caps["raw_data_in_context"],
            "cache_first": caps["cache_first"],
            "max_context_input_tokens_per_phase": caps["max_context_input_tokens_per_phase"],
            "distillate_max_lines": caps["distillate_max_lines"],
            "monthly_paid_api_usd_cap": caps["monthly_paid_api_usd_cap"],
            "monthly_llm_usd_cap": caps["monthly_llm_usd_cap"],
            "monthly_ads_usd_cap": caps["monthly_ads_usd_cap"],
        },
        "lanes": lanes,
        "actions": actions,
        "approval_gates": gates,
        "source_reports": {
            "tool_stack": "seo/setup/tool-stack-report.md",
            "automation_recommendations": "seo/automations/automation-recommendations.md",
            "usage_ledger": "seo/setup/latest-usage-ledger.md",
        },
        "next_actions": [
            "Review the top action per lane before starting broad collection or content work.",
            "Run `task-router.py --task \"<chosen roadmap action>\" --write` before execution.",
            "Use `usage-ledger.py check` before any paid/quota/LLM/ads action and record spend after use.",
        ],
    }


def generated_yaml(report: dict[str, Any]) -> str:
    payload = {
        "version": report["version"],
        "generated": report["generated"],
        "project": report.get("project", {}),
        "market": report.get("market", {}),
        "business": report.get("business", {}),
        "limits": report.get("limits", {}),
        "lanes": report.get("lanes", {}),
        "actions": report.get("actions", []),
        "approval_gates": report.get("approval_gates", []),
        "next_actions": report.get("next_actions", []),
    }
    return dump_yaml(payload)


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    market = report.get("market", {})
    business = report.get("business", {})
    limits = report.get("limits", {})
    lines = [
        "# seo-cycle growth roadmap",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Country/profile: {market.get('country')} / {market.get('region_profile')}",
        f"- Engines: {', '.join(market.get('engines', [])) or '-'}",
        f"- Project type: {business.get('project_type')}",
        f"- Ecommerce/local: {business.get('ecommerce')} / {business.get('local')}",
        f"- Max actions: {limits.get('max_actions')}",
        f"- Paid API / LLM / Ads caps: ${limits.get('monthly_paid_api_usd_cap')} / ${limits.get('monthly_llm_usd_cap')} / ${limits.get('monthly_ads_usd_cap')}",
        "",
        "## Lanes",
    ]
    for lane_id, lane in report.get("lanes", {}).items():
        lines.append(f"- {lane_id}: {lane.get('title')} ({len(lane.get('actions', []))} actions)")

    lines.extend(
        [
            "",
            "## Prioritized Actions",
            "| Score | Action | Lane | Mode | Tools | Gates | Next step |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.get("actions", []):
        lines.append(
            f"| {row.get('priority_score')} | {row.get('id')} | {row.get('lane')} | {row.get('mode')} | "
            f"{', '.join(row.get('tools', [])) or '-'} | {', '.join(row.get('approval_gates', [])) or '-'} | {row.get('next_step')} |"
        )

    lines.extend(["", "## Next Actions"])
    for item in report.get("next_actions", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Low-Token Rules",
            "- Do not load raw crawls, API exports, browser HTML, or full CSVs into context; keep raw data under `seo/` and use distillates/top-N.",
            "- Roadmap actions are planning artifacts, not approval to publish, submit URLs, install tags, launch ads, or run paid whole-site jobs.",
            "- Paid/quota/LLM/ads actions require `usage-ledger.py check` and a recorded usage event after approved work.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_reports(project_root: pathlib.Path, report: dict[str, Any]) -> None:
    write_text(project_root / "seo" / "growth-roadmap.generated.yaml", generated_yaml(report))
    markdown = render_markdown(report)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    write_text(project_root / "seo" / "setup" / "growth-roadmap.md", markdown)
    write_text(project_root / "seo" / "setup" / "growth-roadmap.json", json_text)
    write_text(project_root / "seo" / "setup" / "latest-growth-roadmap.md", markdown)
    write_text(project_root / "seo" / "setup" / "latest-growth-roadmap.json", json_text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write generated roadmap artifacts under seo/.")
    parser.add_argument("--max-actions", type=int, default=DEFAULT_MAX_ACTIONS, help="Maximum roadmap actions to emit.")
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
    report = build_report(cfg_path, max_actions=max(1, args.max_actions))
    if args.write:
        write_reports(project_root, report)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
