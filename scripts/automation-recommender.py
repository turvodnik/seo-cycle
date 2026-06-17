#!/usr/bin/env python3
"""Recommend safe scheduled automations for one seo-cycle project.

Reads `seo-cycle.yaml`, `seo/project-intake.yaml`, current automation policy,
and usage/budget posture. Default mode is non-destructive: write generated
recommendations and a policy overlay. Use `--apply` only after review; it creates
a backup of `seo/automation-policy.yaml` and never enables schedule installation
unless `--allow-schedules` is explicitly passed.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, policy_path, project_root_for, rel_path
from seo_cycle_core.reports import write_artifacts

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. `pip3 install pyyaml`", file=sys.stderr)
    sys.exit(2)


AUTOMATION_DEFAULTS: dict[str, dict[str, Any]] = {
    "usage_budget_watch": {
        "cadence": "weekly",
        "cron": "0 7 * * 1",
        "mode": "report_only",
        "actions": ["usage_ledger_report", "budget_cap_watch", "approval_queue_summary"],
        "tools": ["usage-ledger", "governance-report"],
    },
    "spend_guard_watch": {
        "cadence": "weekly",
        "cron": "15 7 * * 1",
        "mode": "report_only",
        "actions": ["spend_guard_report", "subscription_remaining_limits", "preflight_command_review"],
        "tools": ["spend-guard", "usage-ledger"],
    },
    "weekly_read_only_health": {
        "cadence": "weekly",
        "cron": "0 8 * * 1",
        "mode": "report_only",
        "actions": ["robots_sitemap_check", "public_pagespeed_check", "read_only_index_status", "cache_usage_report"],
        "tools": ["validate-config", "resolve-sources", "pagespeed_crux"],
    },
    "technical_indexability_watch": {
        "cadence": "weekly",
        "cron": "30 8 * * 1",
        "mode": "report_only",
        "actions": ["robots_sitemap_check", "canonical_noindex_audit", "sitemap_coverage_diff", "editor_preview_url_check"],
        "tools": ["robots_sitemap", "schema_crawl"],
    },
    "search_console_index_watch": {
        "cadence": "weekly",
        "cron": "0 9 * * 1",
        "mode": "report_only",
        "actions": ["index_status", "crawl_errors", "sitemap_status", "query_delta", "gsc_indexing_queue_recheck", "indexnow_submit_plan", "yandex_recrawl_status"],
        "tools": ["indexnow", "yandex_webmaster"],
    },
    "bing_index_watch": {
        "cadence": "weekly",
        "cron": "30 9 * * 1",
        "mode": "report_only",
        "actions": ["bing_index_status", "bing_crawl_errors", "bing_keywords", "bing_backlinks"],
        "tools": ["bing_webmaster"],
    },
    "schema_cwv_watch": {
        "cadence": "weekly",
        "cron": "0 8 * * 3",
        "mode": "report_only",
        "actions": ["schema_validate", "product_schema_mismatch_report", "core_web_vitals_report", "pagespeed_check"],
        "tools": ["schema_crawl", "pagespeed_crux"],
    },
    "monthly_keyword_refresh": {
        "cadence": "monthly",
        "cron": "0 10 1 * *",
        "mode": "approval_only",
        "actions": ["cached_fetch", "keyword_gap_report", "content_refresh_candidates"],
        "tools": [],
        "approval_gates": ["browser_mass_collection"],
    },
    "content_decay_refresh_queue": {
        "cadence": "monthly",
        "cron": "0 10 3 * *",
        "mode": "approval_only",
        "actions": ["content_decay_candidates", "entity_gap_queue", "refresh_brief_queue", "content_rewrite_queue"],
        "tools": ["neuronwriter", "google_cloud_nlp", "growth-roadmap"],
        "approval_gates": ["paid_api_run", "content_rewrite"],
    },
    "monthly_ai_visibility": {
        "cadence": "monthly",
        "cron": "0 11 2 * *",
        "mode": "report_only",
        "actions": ["ai_visibility_prompts_check", "cited_competitors_report"],
        "tools": ["perplexity", "openai_chatgpt", "claude", "gemini", "deepseek"],
    },
    "ecommerce_feed_quality": {
        "cadence": "weekly",
        "cron": "0 8 * * 2",
        "mode": "approval_only",
        "actions": ["merchant_feed_errors_report", "product_schema_mismatch_report"],
        "tools": ["google_merchant", "yandex_merchant"],
        "approval_gates": ["merchant_feed_change"],
    },
    "local_seo_reputation": {
        "cadence": "weekly",
        "cron": "0 8 * * 4",
        "mode": "report_only",
        "actions": ["maps_profile_check", "reviews_velocity_report"],
        "tools": ["google_business_profile", "bing_places", "yandex_business_maps"],
    },
}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


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
        return value.strip().lower() in {"true", "yes", "y", "1", "enabled", "да"}
    return bool(value)


def task_enabled(policy: dict[str, Any], task_id: str) -> bool:
    planned = policy.get("planned_automations", {}) if isinstance(policy.get("planned_automations"), dict) else {}
    node = planned.get(task_id, {}) if isinstance(planned.get(task_id), dict) else {}
    return bool(node.get("enabled"))


def country(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    locale = cfg.get("locale", {}) if isinstance(cfg.get("locale"), dict) else {}
    return str(markets.get("primary_country") or locale.get("country") or "").upper()


def engines(intake: dict[str, Any], cfg: dict[str, Any]) -> set[str]:
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


def recommendation(
    task_id: str,
    enabled: bool,
    reason: str,
    mode: str | None = None,
    tools: list[str] | None = None,
    approval_gates: list[str] | None = None,
) -> dict[str, Any]:
    base = copy.deepcopy(AUTOMATION_DEFAULTS[task_id])
    if mode:
        base["mode"] = mode
    if tools is not None:
        base["tools"] = tools
    if approval_gates is not None:
        base["approval_gates"] = approval_gates
    base.setdefault("tools", [])
    base.setdefault("approval_gates", [])
    base["enabled"] = enabled
    base["reason"] = reason
    return base


def enabled_tools(tool_stack: dict[str, Any]) -> set[str]:
    decisions = tool_stack.get("decisions", {}) if isinstance(tool_stack.get("decisions"), dict) else {}
    return {
        str(tool_id)
        for tool_id, row in decisions.items()
        if isinstance(row, dict) and row.get("decision") in {"enabled", "report_only", "approval_required"}
    }


def tools_present(candidates: list[str], active_tools: set[str]) -> list[str]:
    return [tool for tool in candidates if tool in active_tools]


def build_recommendations(
    cfg: dict[str, Any],
    intake: dict[str, Any],
    policy: dict[str, Any],
    tool_stack: dict[str, Any] | None = None,
    spend_guard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    business = intake.get("business", {}) if isinstance(intake.get("business"), dict) else {}
    marketing = intake.get("marketing", {}) if isinstance(intake.get("marketing"), dict) else {}
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    tools = intake.get("tools", {}) if isinstance(intake.get("tools"), dict) else {}
    project_type = str(business.get("project_type") or cfg.get("project_type") or "")
    search_engines = engines(intake, cfg)
    local_platforms = markets.get("local_platforms", {}) if isinstance(markets.get("local_platforms"), dict) else {}
    ai_visibility_tools = tools.get("ai_visibility", []) if isinstance(tools.get("ai_visibility"), list) else []
    organic_enabled = boolish(marketing.get("organic_seo", True))
    content_enabled = boolish(marketing.get("content_marketing", True))
    ecommerce_enabled = project_type == "ecommerce" or boolish(marketing.get("ecommerce_feeds"))
    local_enabled = project_type == "local_business" or boolish(marketing.get("local_seo")) or has_any(local_platforms)
    active_tools = enabled_tools(tool_stack or {})
    search_console_tools = tools_present(["google_search_console", "yandex_webmaster", "bing_webmaster"], active_tools)
    merchant_tools = tools_present(["google_merchant", "yandex_merchant"], active_tools)
    local_tools = tools_present(["google_business_profile", "bing_places", "yandex_business_maps"], active_tools)
    ai_tools = tools_present(["perplexity", "openai_chatgpt", "claude", "gemini", "deepseek"], active_tools)
    spend_blocked = [
        row.get("service")
        for row in (spend_guard or {}).get("service_guards", [])
        if isinstance(row, dict) and row.get("status") in {"blocked", "approval_required"} and not row.get("allowed_now")
    ]

    default_mode = policy.get("default_mode", "approval_only")
    safe_default_mode = default_mode if default_mode in {"report_only", "approval_only", "auto_with_caps"} else "approval_only"
    keyword_mode = "approval_only" if safe_default_mode != "auto_with_caps" else "auto_with_caps"

    planned = {
        "usage_budget_watch": recommendation(
            "usage_budget_watch",
            True,
            "Always recommended: watches token/API/ad spend and creates a weekly usage report.",
            "report_only",
        ),
        "spend_guard_watch": recommendation(
            "spend_guard_watch",
            True,
            "Always recommended: watches subscription limits, approval-only services, and preflight commands.",
            "report_only",
            approval_gates=["paid_api_run", "llm_token_spend"] if spend_blocked else [],
        ),
        "weekly_read_only_health": recommendation(
            "weekly_read_only_health",
            True,
            "Always recommended: read-only technical health checks do not mutate the site.",
            "report_only",
        ),
        "technical_indexability_watch": recommendation(
            "technical_indexability_watch",
            True,
            "Always recommended: catches robots, sitemap, canonical, noindex, and editor-preview drift.",
            "report_only",
        ),
        "search_console_index_watch": recommendation(
            "search_console_index_watch",
            bool(search_console_tools),
            "Recommended when at least one search console source is active.",
            "report_only",
            tools=search_console_tools,
        ),
        "bing_index_watch": recommendation(
            "bing_index_watch",
            "bing" in search_engines or "bing_webmaster" in active_tools,
            "Recommended when Bing is an active search engine or Bing Webmaster is available.",
            "report_only",
            tools=["bing_webmaster"] if "bing" in search_engines or "bing_webmaster" in active_tools else [],
        ),
        "schema_cwv_watch": recommendation(
            "schema_cwv_watch",
            True,
            "Always recommended: schema and Core Web Vitals are low-risk quality signals.",
            "report_only",
        ),
        "monthly_keyword_refresh": recommendation(
            "monthly_keyword_refresh",
            organic_enabled and bool(search_engines),
            "Recommended when organic SEO is enabled and at least one search engine is active.",
            keyword_mode,
        ),
        "content_decay_refresh_queue": recommendation(
            "content_decay_refresh_queue",
            content_enabled or organic_enabled,
            "Recommended for ongoing content/entity gap and refresh queues; rewriting remains approval-only.",
            "approval_only",
            tools=tools_present(["neuronwriter", "google_cloud_nlp"], active_tools) or ["growth-roadmap"],
            approval_gates=["paid_api_run", "content_rewrite"],
        ),
        "monthly_ai_visibility": recommendation(
            "monthly_ai_visibility",
            bool(ai_visibility_tools) and (content_enabled or organic_enabled),
            "Recommended when AI visibility tools/prompts are configured for content/organic work.",
            "report_only",
            tools=ai_tools or ai_visibility_tools,
        ),
        "ecommerce_feed_quality": recommendation(
            "ecommerce_feed_quality",
            ecommerce_enabled,
            "Recommended for ecommerce or merchant-feed projects; remains approval-only for feed changes.",
            "approval_only",
            tools=merchant_tools or ["merchant_feed"],
        ),
        "local_seo_reputation": recommendation(
            "local_seo_reputation",
            local_enabled,
            "Recommended for local SEO, maps, NAP, and review velocity monitoring.",
            "report_only",
            tools=local_tools or [name for name, enabled in local_platforms.items() if boolish(enabled)],
        ),
    }

    for task_id, current_enabled in {
        task_id: task_enabled(policy, task_id) for task_id in planned
    }.items():
        planned[task_id]["current_enabled"] = current_enabled

    return {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "market": {
            "country": country(cfg, intake),
            "search_engines": sorted(search_engines),
        },
        "business": {
            "project_type": project_type,
            "ecommerce": ecommerce_enabled,
            "local": local_enabled,
            "organic": organic_enabled,
            "content": content_enabled,
        },
        "signals": {
            "active_tools": sorted(active_tools),
            "spend_blocked_or_approval": sorted(str(item) for item in spend_blocked if item),
            "recommended_task_count": len(planned),
            "enabled_task_count": sum(1 for node in planned.values() if node.get("enabled")),
        },
        "policy_overlay": {
            "default_mode": safe_default_mode,
            "create_schedules": False,
            "planned_automations": planned,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    overlay = report.get("policy_overlay", {})
    market = report.get("market", {})
    business = report.get("business", {})
    planned = overlay.get("planned_automations", {})
    lines = [
        "# seo-cycle automation recommendations",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Country: {market.get('country')}",
        f"- Search engines: {', '.join(market.get('search_engines', [])) or '-'}",
        f"- Project type: {business.get('project_type')}",
        f"- Default mode: {overlay.get('default_mode')}",
        f"- Create schedules in overlay: {overlay.get('create_schedules')}",
        "",
        "## Recommendations",
        "| Task | Recommended | Current | Cadence | Mode | Tools | Gates | Reason |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for task_id, node in planned.items():
        lines.append(
            f"| {task_id} | {node.get('enabled')} | {node.get('current_enabled')} | "
            f"{node.get('cadence')} | {node.get('mode')} | {', '.join(node.get('tools', [])) or '-'} | "
            f"{', '.join(node.get('approval_gates', [])) or '-'} | {node.get('reason')} |"
        )
    lines.extend(
        [
            "",
            "## Apply",
            "- Review `seo/automations/automation-recommendations.md` first.",
            "- Apply planned automation flags with `automation-recommender.py --apply`.",
            "- Real schedule installation still requires governance + automation-policy `create_schedules: true` and `SEO_CYCLE_ALLOW_SCHEDULE_INSTALL=1`.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    out_dir = project_root / "seo" / "automations"
    write_artifacts(
        text_files={
            out_dir / "automation-recommendations.md": render_markdown(report),
            project_root / "seo" / "automation-policy.generated.yaml": dump_yaml(report["policy_overlay"]),
        },
        json_files={
            out_dir / "automation-recommendations.json": report,
        },
    )
    return out_dir / "automation-recommendations.md"


def apply_recommendations(policy_path: pathlib.Path, report: dict[str, Any], allow_schedules: bool) -> pathlib.Path:
    policy = load_yaml(policy_path)
    backup = policy_path.with_suffix(policy_path.suffix + f".bak-{dt.datetime.now():%Y%m%d%H%M%S}")
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    if policy_path.exists():
        backup.write_text(policy_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        backup.write_text("", encoding="utf-8")

    next_policy = copy.deepcopy(policy)
    overlay = report["policy_overlay"]
    next_policy["default_mode"] = overlay.get("default_mode", next_policy.get("default_mode", "approval_only"))
    if allow_schedules:
        next_policy["create_schedules"] = True
    else:
        next_policy["create_schedules"] = bool(next_policy.get("create_schedules", False))
    planned = next_policy.setdefault("planned_automations", {})
    for task_id, node in overlay.get("planned_automations", {}).items():
        current = planned.get(task_id, {}) if isinstance(planned.get(task_id), dict) else {}
        next_node = copy.deepcopy(current)
        for key in ("enabled", "cadence", "cron", "mode", "actions", "tools", "approval_gates", "reason"):
            next_node[key] = node.get(key)
        planned[task_id] = next_node
    policy_path.write_text(dump_yaml(next_policy), encoding="utf-8")
    return backup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write generated recommendations and policy overlay.")
    parser.add_argument("--apply", action="store_true", help="Apply recommendations to seo/automation-policy.yaml with backup.")
    parser.add_argument("--allow-schedules", action="store_true", help="When applying, also set create_schedules: true.")
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

    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    intake = load_yaml(policy_path(cfg, project_root, "project_intake", "seo/project-intake.yaml"))
    automation_path = policy_path(cfg, project_root, "automation_policy", "seo/automation-policy.yaml")
    policy = load_yaml(automation_path)
    tool_stack = load_policy_json(cfg, project_root, "tool_stack_report", "seo/setup/tool-stack-report.json")
    spend_guard = load_policy_json(cfg, project_root, "spend_guard_report", "seo/setup/spend-guard.json")
    report = build_recommendations(cfg, intake, policy, tool_stack, spend_guard)

    if args.write or args.apply:
        out = write_outputs(project_root, report)
        if args.format != "json":
            print(f"Wrote {out}")
        else:
            print(f"Wrote {out}", file=sys.stderr)
    if args.apply:
        backup = apply_recommendations(automation_path, report, args.allow_schedules)
        message = f"Applied recommendations to {automation_path}; backup: {backup}"
        if args.format == "json":
            print(message, file=sys.stderr)
        else:
            print(message)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not args.write:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
