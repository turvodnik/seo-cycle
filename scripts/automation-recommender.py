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

AUTOMATION_DEFAULTS: dict[str, dict[str, Any]] = {
    "usage_budget_watch": {
        "cadence": "weekly",
        "cron": "0 7 * * 1",
        "mode": "report_only",
        "actions": ["usage_ledger_report", "budget_cap_watch", "approval_queue_summary"],
    },
    "weekly_read_only_health": {
        "cadence": "weekly",
        "cron": "0 8 * * 1",
        "mode": "report_only",
        "actions": ["robots_sitemap_check", "public_pagespeed_check", "read_only_index_status", "cache_usage_report"],
    },
    "monthly_keyword_refresh": {
        "cadence": "monthly",
        "cron": "0 10 1 * *",
        "mode": "approval_only",
        "actions": ["cached_fetch", "keyword_gap_report", "content_refresh_candidates"],
    },
    "monthly_ai_visibility": {
        "cadence": "monthly",
        "cron": "0 11 2 * *",
        "mode": "report_only",
        "actions": ["ai_visibility_prompts_check", "cited_competitors_report"],
    },
    "ecommerce_feed_quality": {
        "cadence": "weekly",
        "cron": "0 8 * * 2",
        "mode": "approval_only",
        "actions": ["merchant_feed_errors_report", "product_schema_mismatch_report"],
    },
    "local_seo_reputation": {
        "cadence": "weekly",
        "cron": "0 8 * * 4",
        "mode": "report_only",
        "actions": ["maps_profile_check", "reviews_velocity_report"],
    },
}


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


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get(key, default))


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


def recommendation(task_id: str, enabled: bool, reason: str, mode: str | None = None) -> dict[str, Any]:
    base = copy.deepcopy(AUTOMATION_DEFAULTS[task_id])
    if mode:
        base["mode"] = mode
    base["enabled"] = enabled
    base["reason"] = reason
    return base


def build_recommendations(cfg: dict[str, Any], intake: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
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
        "weekly_read_only_health": recommendation(
            "weekly_read_only_health",
            True,
            "Always recommended: read-only technical health checks do not mutate the site.",
            "report_only",
        ),
        "monthly_keyword_refresh": recommendation(
            "monthly_keyword_refresh",
            organic_enabled and bool(search_engines),
            "Recommended when organic SEO is enabled and at least one search engine is active.",
            keyword_mode,
        ),
        "monthly_ai_visibility": recommendation(
            "monthly_ai_visibility",
            bool(ai_visibility_tools) and (content_enabled or organic_enabled),
            "Recommended when AI visibility tools/prompts are configured for content/organic work.",
            "report_only",
        ),
        "ecommerce_feed_quality": recommendation(
            "ecommerce_feed_quality",
            ecommerce_enabled,
            "Recommended for ecommerce or merchant-feed projects; remains approval-only for feed changes.",
            "approval_only",
        ),
        "local_seo_reputation": recommendation(
            "local_seo_reputation",
            local_enabled,
            "Recommended for local SEO, maps, NAP, and review velocity monitoring.",
            "report_only",
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
        "| Task | Recommended | Current | Cadence | Mode | Reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for task_id, node in planned.items():
        lines.append(
            f"| {task_id} | {node.get('enabled')} | {node.get('current_enabled')} | "
            f"{node.get('cadence')} | {node.get('mode')} | {node.get('reason')} |"
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
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "automation-recommendations.md").write_text(render_markdown(report), encoding="utf-8")
    (out_dir / "automation-recommendations.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    overlay_path = project_root / "seo" / "automation-policy.generated.yaml"
    overlay_path.write_text(dump_yaml(report["policy_overlay"]), encoding="utf-8")
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
        for key in ("enabled", "cadence", "cron", "mode", "actions", "reason"):
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
    report = build_recommendations(cfg, intake, policy)

    if args.write or args.apply:
        out = write_outputs(project_root, report)
        print(f"Wrote {out}")
    if args.apply:
        backup = apply_recommendations(automation_path, report, args.allow_schedules)
        print(f"Applied recommendations to {automation_path}; backup: {backup}")
    elif args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not args.write:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
