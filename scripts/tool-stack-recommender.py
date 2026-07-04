#!/usr/bin/env python3
"""Recommend a safe per-project SEO tool stack.

This is the source/tool control plane for new projects. It reads the project
config, detailed intake, budget policy, and usage posture, then writes a
secret-free report that says which tools are enabled, approval-gated, disabled,
or not applicable.

Default mode is non-destructive. Use `--apply` only after review; it creates a
backup of `seo-cycle.yaml` and only applies conservative source flags.
"""

from __future__ import annotations

import argparse
import copy
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

from seo_cycle_core.config import (  # noqa: E402
    boolish,
    find_config,
    load_yaml,
    numeric,
    policy_path,
    project_root_for,
    rel_path,
    skill_root,
    write_text,
)


from seo_cycle_core.tool_catalog import DECISION_ORDER, TOOL_CATALOG


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def country(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    locale = cfg.get("locale", {}) if isinstance(cfg.get("locale"), dict) else {}
    return str(markets.get("primary_country") or locale.get("country") or "").upper()


def project_type(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    business = intake.get("business", {}) if isinstance(intake.get("business"), dict) else {}
    return str(business.get("project_type") or cfg.get("project_type") or "")


def active_engines(cfg: dict[str, Any], intake: dict[str, Any]) -> set[str]:
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
    ecommerce = pt == "ecommerce" or boolish(marketing.get("ecommerce_feeds"))
    local = (
        pt == "local_business"
        or boolish(marketing.get("local_seo"))
        or has_any(local_platforms)
        or has_address
    )
    return {
        "ecommerce": ecommerce,
        "local": local,
        "organic": boolish(marketing.get("organic_seo", True)),
        "content": boolish(marketing.get("content_marketing", True)),
    }


def governance_caps(cfg: dict[str, Any], tool_budget: dict[str, Any]) -> dict[str, Any]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    budget = governance.get("budget_policy", {}) if isinstance(governance.get("budget_policy"), dict) else {}
    tb_money = tool_budget.get("money_budget", {}) if isinstance(tool_budget.get("money_budget"), dict) else {}
    setup = tool_budget.get("run_guards", {}) if isinstance(tool_budget.get("run_guards"), dict) else {}
    token = governance.get("token_policy", {}) if isinstance(governance.get("token_policy"), dict) else {}
    return {
        "monthly_total_usd_cap": numeric(tb_money.get("monthly_total_usd_cap", budget.get("monthly_total_usd_cap"))),
        "monthly_paid_api_usd_cap": numeric(tb_money.get("monthly_paid_api_usd_cap", budget.get("monthly_paid_api_usd_cap"))),
        "monthly_llm_usd_cap": numeric(tb_money.get("monthly_llm_usd_cap", budget.get("monthly_llm_usd_cap"))),
        "monthly_ads_usd_cap": numeric(tb_money.get("monthly_ads_usd_cap", 0)),
        "cloud_budget_alert_usd": numeric(tb_money.get("cloud_budget_alert_usd", budget.get("cloud_budget_alert_usd", 5)), 5),
        "require_approval_over_usd": numeric(tb_money.get("require_approval_over_usd", budget.get("require_approval_over_usd", 0))),
        "ads_spend_enabled": boolish(tb_money.get("ads_spend_enabled", budget.get("ads_spend_enabled", False))),
        "paid_tools_default": str(budget.get("paid_tools_default") or "approval_only"),
        "raw_data_in_context": boolish(token.get("raw_data_in_context", False)),
        "cache_first": boolish(token.get("cache_first", True)),
        "require_human_approval_before": setup.get("require_human_approval_before", []),
    }


def subscription_status(cfg: dict[str, Any], tool_budget: dict[str, Any], tool_id: str) -> dict[str, Any]:
    aliases = {
        "google_cloud_nlp": ["google_cloud_nlp", "google_nlp"],
        "keyso": ["keyso", "keys_so"],
    }
    names = aliases.get(tool_id, [tool_id])
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    cfg_subs = governance.get("subscriptions", {}) if isinstance(governance.get("subscriptions"), dict) else {}
    tb_subs = tool_budget.get("subscriptions", {}) if isinstance(tool_budget.get("subscriptions"), dict) else {}
    merged: dict[str, Any] = {}
    for name in names:
        node = tb_subs.get(name)
        if isinstance(node, dict):
            merged.update(node)
        node = cfg_subs.get(name)
        if isinstance(node, dict):
            merged.update(node)
    return merged


def subscription_enabled(status: dict[str, Any]) -> bool:
    state = str(status.get("status") or status.get("plan") or "").lower()
    if status.get("enabled") is True:
        return True
    return state not in {"", "not_configured", "disabled", "disabled_until_budget_approval", "disabled_until_budget_and_local_guards"}


def env_names(project_root: pathlib.Path) -> set[str]:
    names = set()
    env_file = project_root / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            names.add(line.split("=", 1)[0].strip())
    return names


def resolve_sources(cfg_path: pathlib.Path, project_root: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(skill_root() / "scripts" / "resolve-sources.py"), str(cfg_path), "--json"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"active": {}, "skipped": {}, "error": proc.stderr.strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"active": {}, "skipped": {}, "error": "resolve-sources returned invalid JSON"}


def marketing_status(intake: dict[str, Any], tool_id: str) -> str | None:
    marketing = intake.get("marketing", {}) if isinstance(intake.get("marketing"), dict) else {}
    paid_ads = marketing.get("paid_ads", {}) if isinstance(marketing.get("paid_ads"), dict) else {}
    analytics_tags = marketing.get("analytics_tags", {}) if isinstance(marketing.get("analytics_tags"), dict) else {}
    mapping = {
        "google_ads": ("paid_ads", "google_ads"),
        "yandex_direct": ("paid_ads", "yandex_direct"),
        "microsoft_ads": ("paid_ads", "microsoft_ads"),
        "google_analytics_4": ("analytics_tags", "google_analytics"),
        "microsoft_clarity": ("analytics_tags", "microsoft_clarity"),
        "yandex_metrika": ("analytics_tags", "yandex_metrika"),
    }
    if tool_id not in mapping:
        return None
    group, key = mapping[tool_id]
    node = paid_ads if group == "paid_ads" else analytics_tags
    value = node.get(key)
    return str(value) if value is not None else None


def decision(
    tool_id: str,
    meta: dict[str, Any],
    cfg: dict[str, Any],
    intake: dict[str, Any],
    tool_budget: dict[str, Any],
    resolved: dict[str, Any],
    present_env: set[str],
) -> dict[str, Any]:
    cty = country(cfg, intake)
    engines = active_engines(cfg, intake)
    flags = business_flags(cfg, intake)
    caps = governance_caps(cfg, tool_budget)
    reasons: list[str] = []
    gates: list[str] = []
    next_actions: list[str] = []

    countries = set(meta.get("countries", []))
    if countries and cty not in countries:
        return make_decision(tool_id, meta, "not_applicable", [f"Country {cty or '?'} is outside {sorted(countries)}."], [], [])
    excluded = set(meta.get("countries_exclude", []))
    if cty in excluded:
        return make_decision(tool_id, meta, "not_applicable", [f"Country {cty} is explicitly excluded for this tool."], [], [])

    required_engines = set(meta.get("engines", []))
    if required_engines and not (engines & required_engines):
        return make_decision(
            tool_id,
            meta,
            "not_applicable",
            [f"No active search engine from {sorted(required_engines)}."],
            [],
            [],
        )

    allowed_project_types = set(meta.get("project_types", []))
    pt = project_type(cfg, intake)
    if allowed_project_types and pt not in allowed_project_types:
        return make_decision(tool_id, meta, "not_applicable", [f"Project type {pt or '?'} is outside {sorted(allowed_project_types)}."], [], [])
    if meta.get("requires_ecommerce") and not flags["ecommerce"]:
        return make_decision(tool_id, meta, "not_applicable", ["Not an ecommerce/feed project."], [], [])
    if meta.get("requires_local") and not flags["local"]:
        return make_decision(tool_id, meta, "not_applicable", ["No local SEO/business profile need is enabled."], [], [])

    source = meta.get("source")
    source_active = source in (resolved.get("active") or {})
    source_skipped = (resolved.get("skipped") or {}).get(source) if source else None

    env_required = meta.get("env", [])
    missing_env = [name for name in env_required if name not in present_env]
    if missing_env:
        next_actions.append(f"Add env when API mode is needed: {', '.join(missing_env)}.")

    cost = str(meta.get("cost", "free"))
    status = subscription_status(cfg, tool_budget, tool_id)
    sub_enabled = subscription_enabled(status)

    if meta.get("tracking_tag"):
        status_text = marketing_status(intake, tool_id)
        if cty == "RU" and meta.get("ecosystem") in {"google", "microsoft"}:
            reasons.append("RF project: foreign analytics/recording tags stay disabled unless the project policy explicitly allows them.")
            gates.append("tracking_tag_install")
            return make_decision(tool_id, meta, "disabled", reasons, gates, next_actions)
        reasons.append(meta["default_reason"])
        gates.append("tracking_tag_install")
        if status_text in {"disabled", "False", "false"}:
            return make_decision(tool_id, meta, "disabled", [f"Intake analytics policy is {status_text}."], gates, next_actions)
        return make_decision(tool_id, meta, "approval_required", reasons, gates, next_actions)

    if meta.get("ads"):
        status_text = marketing_status(intake, tool_id)
        gates.append("ads_launch")
        if status_text in {"disabled", "skipped_if_billing_required"}:
            return make_decision(tool_id, meta, "disabled", [f"Intake ads policy is {status_text}."], gates, next_actions)
        if not caps["ads_spend_enabled"] or caps["monthly_ads_usd_cap"] <= 0:
            reasons.append("Ads spend is disabled or monthly ads cap is 0; keep planning/audit approval-gated.")
            return make_decision(tool_id, meta, "approval_required", reasons, gates, next_actions)
        reasons.append("Ads budget exists; keep launch and spend behind approval gates.")
        return make_decision(tool_id, meta, "approval_required", reasons, gates, next_actions)

    if meta.get("mutating"):
        reasons.append(meta["default_reason"])
        gates.append("index_submission")
        return make_decision(tool_id, meta, "approval_required", reasons, gates, next_actions)

    if cost in {"paid_api", "subscription_quota", "subscription_or_paid", "llm_tokens", "free_quota_then_paid"}:
        gate = "paid_api_run" if cost != "llm_tokens" else "llm_token_spend"
        gates.append(gate)
        if cost == "llm_tokens" and caps["monthly_llm_usd_cap"] <= 0:
            reasons.append("LLM monthly cap is 0; use only after explicit task-level approval or subscription confirmation.")
            return make_decision(tool_id, meta, "approval_required", reasons, gates, next_actions)
        if tool_id == "google_cloud_nlp":
            nlp_policy = policy_path(cfg, project_root_for_context(cfg), "google_nlp_policy", "seo/entities/google-nlp-policy.yaml")
            if not nlp_policy.exists():
                next_actions.append("Create seo/entities/google-nlp-policy.yaml before enabling Google NLP.")
            if caps["monthly_paid_api_usd_cap"] <= 0 and not sub_enabled:
                reasons.append(f"Requires billing guard; default local cap is 0 and Cloud budget alert target is ${caps['cloud_budget_alert_usd']:.0f}.")
                return make_decision(tool_id, meta, "approval_required", reasons, gates, next_actions)
        if caps["monthly_paid_api_usd_cap"] <= 0 and not sub_enabled:
            reasons.append("Paid/quota source without approved monthly paid API cap or configured subscription.")
            return make_decision(tool_id, meta, "approval_required", reasons, gates, next_actions)
        reasons.append(meta["default_reason"])
        next_actions.append("Run usage-ledger.py check before each paid/quota call.")
        return make_decision(tool_id, meta, "enabled", reasons, gates, next_actions)

    if source_skipped and not source_active:
        # Region profile says off, but the catalog may still keep a logical tool useful.
        if any(phrase in str(source_skipped) for phrase in ("недоступно", "не входит")):
            return make_decision(tool_id, meta, "not_applicable", [str(source_skipped)], [], next_actions)

    reasons.append(meta.get("default_reason", "Applicable free/read-only tool."))
    if cost in {"free_or_cabinet", "free_or_manual"}:
        next_actions.append("Use cabinet/manual/browser mode when API credentials are unavailable.")
    return make_decision(tool_id, meta, "enabled", reasons, gates, next_actions)


def project_root_for_context(cfg: dict[str, Any]) -> pathlib.Path:
    # Filled by build_report before decision calls. Kept as a tiny escape hatch so
    # decision() stays side-effect free for callers.
    raw = cfg.get("_project_root_for_tool_stack")
    return pathlib.Path(str(raw)) if raw else pathlib.Path.cwd()


def make_decision(
    tool_id: str,
    meta: dict[str, Any],
    value: str,
    reasons: list[str],
    gates: list[str],
    next_actions: list[str],
) -> dict[str, Any]:
    return {
        "tool": tool_id,
        "label": meta.get("label", tool_id),
        "category": meta.get("category", "other"),
        "ecosystem": meta.get("ecosystem"),
        "decision": value,
        "cost": meta.get("cost", "free"),
        "source": meta.get("source"),
        "env": meta.get("env", []),
        "approval_gates": sorted(set(gates)),
        "reason": " ".join(reasons).strip(),
        "next_actions": next_actions,
    }


def source_overlay(decisions: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    enable: set[str] = set()
    disable: set[str] = set()
    approval_only: set[str] = set()
    for row in decisions.values():
        source = row.get("source")
        if not source:
            continue
        cost = str(row.get("cost"))
        value = row.get("decision")
        if value == "enabled" and cost in {"free", "free_or_manual", "free_or_cabinet", "free_or_quota"}:
            enable.add(str(source))
        elif value in {"disabled", "not_applicable"}:
            disable.add(str(source))
        elif value == "approval_required":
            approval_only.add(str(source))
    return {
        "safe_enable": sorted(enable - disable),
        "safe_disable": sorted(disable),
        "leave_review_only": sorted(approval_only - disable),
    }


def summarize_decisions(decisions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_decision = {name: 0 for name in DECISION_ORDER}
    by_category: dict[str, int] = {}
    for row in decisions.values():
        by_decision[row["decision"]] = by_decision.get(row["decision"], 0) + 1
        by_category[row["category"]] = by_category.get(row["category"], 0) + 1
    return {"by_decision": by_decision, "by_category": dict(sorted(by_category.items()))}


def next_actions(report: dict[str, Any]) -> list[str]:
    actions = []
    overlay = report.get("source_overlay", {})
    if overlay.get("leave_review_only"):
        actions.append(f"Review approval-only sources before enabling: {', '.join(overlay['leave_review_only'])}.")
    if report.get("guardrails", {}).get("rf_foreign_tracking_blocked"):
        actions.append("For RF projects, do not install GA4/Clarity or other foreign tracking tags without a written policy exception.")
    if any(row["decision"] == "approval_required" for row in report.get("decisions", {}).values()):
        actions.append("Run `usage-ledger.py check` and get human approval before paid/quota/LLM/index-submission actions.")
    actions.append("Keep this generated report in project docs; credentials stay in `.env` or provider consoles, never in the report.")
    return actions


def build_report(cfg_path: pathlib.Path) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    cfg["_project_root_for_tool_stack"] = str(project_root)
    intake = load_yaml(policy_path(cfg, project_root, "project_intake", "seo/project-intake.yaml"))
    tool_budget = load_yaml(policy_path(cfg, project_root, "tool_budget", "seo/tool-budget.yaml"))
    resolved = resolve_sources(cfg_path, project_root)
    present_env = env_names(project_root)
    decisions = {
        tool_id: decision(tool_id, meta, cfg, intake, tool_budget, resolved, present_env)
        for tool_id, meta in TOOL_CATALOG.items()
    }
    caps = governance_caps(cfg, tool_budget)
    cty = country(cfg, intake)
    report = {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "market": {
            "country": cty,
            "region_profile": cfg.get("region_profile"),
            "engines": sorted(active_engines(cfg, intake)),
        },
        "business": {
            "project_type": project_type(cfg, intake),
            **business_flags(cfg, intake),
        },
        "guardrails": {
            "monthly_paid_api_usd_cap": caps["monthly_paid_api_usd_cap"],
            "monthly_llm_usd_cap": caps["monthly_llm_usd_cap"],
            "monthly_ads_usd_cap": caps["monthly_ads_usd_cap"],
            "cloud_budget_alert_usd": caps["cloud_budget_alert_usd"],
            "cache_first": caps["cache_first"],
            "raw_data_in_context": caps["raw_data_in_context"],
            "rf_foreign_tracking_blocked": cty == "RU",
        },
        "resolved_sources": {
            "active": sorted((resolved.get("active") or {}).keys()),
            "skipped": resolved.get("skipped", {}),
            "error": resolved.get("error"),
        },
        "decisions": decisions,
        "summary": summarize_decisions(decisions),
        "source_overlay": source_overlay(decisions),
    }
    report["next_actions"] = next_actions(report)
    return report


def generated_yaml(report: dict[str, Any]) -> str:
    payload = {
        "version": report["version"],
        "generated": report["generated"],
        "project": report.get("project", {}),
        "market": report.get("market", {}),
        "business": report.get("business", {}),
        "guardrails": report.get("guardrails", {}),
        "source_overlay": report.get("source_overlay", {}),
        "decisions": report.get("decisions", {}),
        "next_actions": report.get("next_actions", []),
    }
    return dump_yaml(payload)


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    market = report.get("market", {})
    business = report.get("business", {})
    guardrails = report.get("guardrails", {})
    summary = report.get("summary", {})
    overlay = report.get("source_overlay", {})
    lines = [
        "# seo-cycle tool stack recommendations",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Country/profile: {market.get('country')} / {market.get('region_profile')}",
        f"- Engines: {', '.join(market.get('engines', [])) or '-'}",
        f"- Project type: {business.get('project_type')}",
        f"- Ecommerce/local: {business.get('ecommerce')} / {business.get('local')}",
        f"- Paid API cap: ${guardrails.get('monthly_paid_api_usd_cap')}",
        f"- LLM cap: ${guardrails.get('monthly_llm_usd_cap')}",
        f"- Ads cap: ${guardrails.get('monthly_ads_usd_cap')}",
        f"- Cloud budget alert target: ${guardrails.get('cloud_budget_alert_usd')}",
        "",
        "## Summary",
    ]
    for key, value in summary.get("by_decision", {}).items():
        lines.append(f"- {key}: {value}")

    lines.extend(
        [
            "",
            "## Source Overlay",
            f"- Safe enable: {', '.join(overlay.get('safe_enable', [])) or '-'}",
            f"- Safe disable: {', '.join(overlay.get('safe_disable', [])) or '-'}",
            f"- Leave review-only: {', '.join(overlay.get('leave_review_only', [])) or '-'}",
            "",
            "## Decisions",
            "| Tool | Decision | Category | Cost | Gates | Reason |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for tool_id, row in sorted(report.get("decisions", {}).items()):
        lines.append(
            f"| {tool_id} | {row.get('decision')} | {row.get('category')} | {row.get('cost')} | "
            f"{', '.join(row.get('approval_gates', [])) or '-'} | {row.get('reason')} |"
        )
    lines.extend(["", "## Next Actions"])
    for item in report.get("next_actions", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Rules",
            "- This report contains no secrets and must not store API keys.",
            "- Apply source flags only after review; paid, tracking, ads, publishing, and index-submission actions stay approval-gated.",
            "- Google Cloud NLP is an audit tool, not a ranking-signal submission channel; use cache and important URL selection.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_reports(project_root: pathlib.Path, report: dict[str, Any]) -> None:
    write_text(project_root / "seo" / "tool-stack.generated.yaml", generated_yaml(report))
    write_text(project_root / "seo" / "setup" / "tool-stack-report.md", render_markdown(report))
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    write_text(project_root / "seo" / "setup" / "tool-stack-report.json", json_text)
    write_text(project_root / "seo" / "setup" / "latest-tool-stack.md", render_markdown(report))
    write_text(project_root / "seo" / "setup" / "latest-tool-stack.json", json_text)


def apply_overlay(cfg_path: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    cfg = load_yaml(cfg_path)
    cfg.pop("_project_root_for_tool_stack", None)
    sources = cfg.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = {}
        cfg["sources"] = sources
    overlay = report.get("source_overlay", {})
    touched: set[str] = set()
    for source in overlay.get("safe_enable", []):
        if source not in sources:
            continue
        node = sources.get(source, {})
        if isinstance(node, dict):
            node["enabled"] = True
            touched.add(source)
    for source in overlay.get("safe_disable", []):
        if source not in sources:
            continue
        node = sources.get(source, {})
        if isinstance(node, dict):
            node["enabled"] = False
            touched.add(source)
    backup = cfg_path.with_suffix(cfg_path.suffix + f".bak-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}")
    backup.write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    cfg_path.write_text(dump_yaml(cfg), encoding="utf-8")
    report["applied"] = {"backup": str(backup), "touched_sources": sorted(touched)}
    return backup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write seo/tool-stack.generated.yaml and setup reports.")
    parser.add_argument("--apply", action="store_true", help="Apply conservative source enable/disable overlay to seo-cycle.yaml.")
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
    if args.apply:
        backup = apply_overlay(cfg_path, report)
        report["applied"] = {"backup": str(backup), **report.get("applied", {})}
        report = build_report(cfg_path)
        report["applied"] = {"backup": str(backup)}
    if args.write or args.apply:
        write_reports(project_root, report)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
