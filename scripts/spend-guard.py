#!/usr/bin/env python3
"""Create a spend/subscription guard report for one seo-cycle project.

This is the operational budget screen: token policy, monthly caps, subscription
limits, current usage, per-service allow/approval/block status, and exact
usage-ledger preflight commands. It is local-only and never stores secret values.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
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


GUARDED_COSTS = {"paid_api", "subscription_quota", "subscription_or_paid", "llm_tokens", "free_quota_then_paid", "ads_spend"}
DEFAULT_LLM_SERVICES = {
    "openai": ["OPENAI_API_KEY"],
    "claude": ["ANTHROPIC_API_KEY"],
    "gemini": ["GEMINI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
}
METRIC_KEYS = [
    "usd",
    "input_tokens",
    "output_tokens",
    "requests",
    "credits",
    "units",
    "rows",
    "browser_minutes",
    "browser_pages",
    "content_writer",
    "ai_credits",
]


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
        return value.strip().lower() in {"true", "yes", "y", "1", "enabled", "да", "д"}
    return bool(value)


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def current_month() -> str:
    return dt.date.today().strftime("%Y-%m")


def infer_category(service: str, fallback: str | None = None) -> str:
    if fallback:
        return fallback
    if service in DEFAULT_LLM_SERVICES:
        return "llm"
    if service in {"google_ads", "yandex_direct", "microsoft_ads"}:
        return "ads"
    return "paid_api"


def ledger_path(cfg: dict[str, Any], project_root: pathlib.Path) -> pathlib.Path:
    return policy_path(cfg, project_root, "usage_ledger", "seo/usage/usage-ledger.jsonl")


def read_ledger(path: pathlib.Path, month: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("month") == month:
            rows.append(row)
    return rows


def empty_metrics() -> dict[str, float]:
    return {key: 0.0 for key in METRIC_KEYS}


def usage_totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    services: dict[str, dict[str, float]] = {}
    categories: dict[str, dict[str, float]] = {}
    overall = empty_metrics()
    for row in rows:
        service = str(row.get("service") or "unknown")
        category = infer_category(service, row.get("category"))
        metrics = row.get("metrics", {}) if isinstance(row.get("metrics"), dict) else {}
        svc = services.setdefault(service, empty_metrics())
        cat = categories.setdefault(category, empty_metrics())
        for key, value in metrics.items():
            if key not in METRIC_KEYS:
                continue
            amount = numeric(value)
            svc[key] = svc.get(key, 0.0) + amount
            cat[key] = cat.get(key, 0.0) + amount
            overall[key] = overall.get(key, 0.0) + amount
    return {"overall": overall, "categories": categories, "services": services, "events": len(rows)}


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


def merged_subscriptions(cfg: dict[str, Any], tool_budget: dict[str, Any]) -> dict[str, dict[str, Any]]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    cfg_subs = governance.get("subscriptions", {}) if isinstance(governance.get("subscriptions"), dict) else {}
    tb_subs = tool_budget.get("subscriptions", {}) if isinstance(tool_budget.get("subscriptions"), dict) else {}
    names = sorted(set(cfg_subs) | set(tb_subs))
    result: dict[str, dict[str, Any]] = {}
    for name in names:
        node: dict[str, Any] = {}
        if isinstance(cfg_subs.get(name), dict):
            node.update(cfg_subs[name])
        if isinstance(tb_subs.get(name), dict):
            node.update(tb_subs[name])
        result[name] = node
    return result


def subscription_enabled(node: dict[str, Any]) -> bool:
    state = str(node.get("status") or node.get("plan") or "").lower()
    if node.get("enabled") is True:
        return True
    return state not in {"", "not_configured", "disabled", "disabled_until_budget_approval", "disabled_until_budget_and_local_guards"}


def subscription_metric_caps(node: dict[str, Any]) -> dict[str, dict[str, float]]:
    mapping = {
        "monthly_usd_cap": "usd",
        "monthly_spend_cap": "usd",
        "monthly_budget_usd": "usd",
        "monthly_request_cap": "requests",
        "monthly_credit_cap": "credits",
        "monthly_content_writer_limit": "content_writer",
        "monthly_ai_credit_limit": "ai_credits",
        "monthly_unit_cap": "units",
    }
    reserve_mapping = {
        "reserve_requests": "requests",
        "reserve_credits": "credits",
        "reserve_content_writer": "content_writer",
        "reserve_ai_credits": "ai_credits",
        "reserve_units": "units",
        "reserve_usd": "usd",
    }
    limits: dict[str, dict[str, float]] = {}
    for raw_key, metric in mapping.items():
        if raw_key in node:
            limits.setdefault(metric, {})["cap"] = numeric(node.get(raw_key))
    for raw_key, metric in reserve_mapping.items():
        if raw_key in node:
            limits.setdefault(metric, {})["reserve"] = numeric(node.get(raw_key))
    return limits


def decisions(tool_stack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return tool_stack.get("decisions", {}) if isinstance(tool_stack.get("decisions"), dict) else {}


def service_catalog(tool_stack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for service, env in DEFAULT_LLM_SERVICES.items():
        catalog[service] = {
            "service": service,
            "category": "llm",
            "cost": "llm_tokens",
            "decision": "approval_required",
            "env": env,
            "approval_gates": ["llm_token_spend"],
        }
    for tool_id, row in decisions(tool_stack).items():
        if not isinstance(row, dict):
            continue
        cost = str(row.get("cost") or "")
        if cost not in GUARDED_COSTS and not row.get("approval_gates"):
            continue
        if cost == "llm_tokens":
            category = "llm"
        elif cost == "ads_spend":
            category = "ads"
        elif cost in {"paid_api", "subscription_quota", "subscription_or_paid", "free_quota_then_paid"}:
            category = "paid_api"
        else:
            category = infer_category(tool_id, row.get("category"))
        existing = catalog.get(tool_id, {})
        env = row.get("env", []) or existing.get("env", [])
        catalog[tool_id] = {
            "service": tool_id,
            "category": category,
            "cost": cost,
            "decision": row.get("decision"),
            "env": env,
            "approval_gates": row.get("approval_gates", []),
        }
    return catalog


def token_guards(token: dict[str, Any]) -> list[str]:
    guards = []
    if token.get("cache_first"):
        guards.append("cache_first")
    if not token.get("raw_data_in_context"):
        guards.append("raw_data_on_disk")
    if token.get("require_distillate_before_synthesis"):
        guards.append("distillate_before_llm")
    if token.get("progressive_disclosure"):
        guards.append("progressive_disclosure")
    return guards


def global_limit_for(service: str, category: str, metric: str, budget: dict[str, Any]) -> dict[str, float]:
    if metric != "usd":
        return {}
    if category == "llm":
        return {"cap": numeric(budget.get("monthly_llm_usd_cap", 0))}
    if category == "ads":
        return {"cap": numeric(budget.get("monthly_ads_usd_cap", 0))}
    if category == "paid_api":
        return {"cap": numeric(budget.get("monthly_paid_api_usd_cap", 0))}
    return {"cap": numeric(budget.get("monthly_total_usd_cap", 0))}


def limit_row(metric: str, used: float, cap: float, reserve: float = 0.0) -> dict[str, Any]:
    effective = cap - reserve if cap > 0 else cap
    remaining = effective - used if effective > 0 else None
    status = "uncapped"
    if effective == 0:
        status = "approval_required"
    elif used > effective:
        status = "blocked"
    elif remaining is not None and remaining <= max(effective * 0.1, 1):
        status = "near_cap"
    elif effective > 0:
        status = "ok"
    return {
        "metric": metric,
        "used": round(used, 4),
        "cap": round(cap, 4),
        "reserve": round(reserve, 4),
        "effective_cap": round(effective, 4),
        "remaining": round(remaining, 4) if remaining is not None else None,
        "status": status,
    }


def service_limits(
    service: str,
    category: str,
    budget: dict[str, Any],
    subscription: dict[str, Any],
    totals: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    service_used = totals.get("services", {}).get(service, empty_metrics())
    category_used = totals.get("categories", {}).get(category, empty_metrics())
    limits: dict[str, dict[str, Any]] = {}
    raw_limits = subscription_metric_caps(subscription)
    if "usd" not in raw_limits:
        raw_limits["usd"] = global_limit_for(service, category, "usd", budget)
    for metric, node in raw_limits.items():
        cap = numeric(node.get("cap", 0))
        reserve = numeric(node.get("reserve", 0))
        used = service_used.get(metric, 0.0)
        if metric == "usd" and not service_used.get(metric):
            used = category_used.get(metric, 0.0) if service in DEFAULT_LLM_SERVICES else service_used.get(metric, 0.0)
        limits[metric] = limit_row(metric, numeric(used), cap, reserve)
    return limits


def allowed_from(service: str, node: dict[str, Any], limits: dict[str, dict[str, Any]], subscription: dict[str, Any], budget: dict[str, Any]) -> tuple[bool, str]:
    decision = node.get("decision")
    if decision in {"disabled", "not_applicable"}:
        return False, "disabled"
    if node.get("category") == "ads" and not budget.get("ads_spend_enabled"):
        return False, "approval_required"
    if not limits:
        return subscription_enabled(subscription), "ok" if subscription_enabled(subscription) else "approval_required"
    statuses = {row.get("status") for row in limits.values()}
    if "blocked" in statuses:
        return False, "blocked"
    if "approval_required" in statuses and not subscription_enabled(subscription):
        return False, "approval_required"
    if "near_cap" in statuses:
        return True, "near_cap"
    if decision == "approval_required" and not subscription_enabled(subscription) and any(row.get("cap", 0) <= 0 for row in limits.values()):
        return False, "approval_required"
    return True, "ok"


def preflight_command(service: str, category: str, limits: dict[str, dict[str, Any]]) -> str:
    parts = [
        "python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py check",
        "--service",
        service,
        "--category",
        category,
    ]
    if "usd" in limits:
        parts.extend(["--usd", "0.01"])
    if category == "llm":
        parts.extend(["--input-tokens", "1000", "--output-tokens", "200"])
    if "content_writer" in limits:
        parts.extend(["--content-writer", "1"])
    if "ai_credits" in limits:
        parts.extend(["--ai-credits", "100"])
    if "requests" in limits:
        parts.extend(["--requests", "1"])
    if "credits" in limits:
        parts.extend(["--credits", "1"])
    if "units" in limits:
        parts.extend(["--units", "1"])
    parts.append("--fail-on-block")
    return " ".join(parts)


def build_report(cfg_path: pathlib.Path) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    tool_budget = load_yaml(policy_path(cfg, project_root, "tool_budget", "seo/tool-budget.yaml"))
    tool_stack = load_policy_json(cfg, project_root, "tool_stack_report", "seo/setup/tool-stack-report.json")
    month = current_month()
    rows = read_ledger(ledger_path(cfg, project_root), month)
    totals = usage_totals(rows)
    token = token_contract(cfg)
    budget = budget_contract(cfg, tool_budget)
    subs = merged_subscriptions(cfg, tool_budget)
    catalog = service_catalog(tool_stack)
    service_guards = []
    env_names: set[str] = set()
    preflight_commands: dict[str, str] = {}
    for service, node in sorted(catalog.items()):
        for name in node.get("env", []):
            if isinstance(name, str) and name and "=" not in name:
                env_names.add(name)
        subscription = subs.get(service, {})
        limits = service_limits(service, node["category"], budget, subscription, totals)
        allowed, status = allowed_from(service, node, limits, subscription, budget)
        command = preflight_command(service, node["category"], limits)
        preflight_commands[service] = command
        service_guards.append(
            {
                "service": service,
                "category": node["category"],
                "cost": node.get("cost"),
                "decision": node.get("decision"),
                "subscription_enabled": subscription_enabled(subscription),
                "allowed_now": allowed,
                "status": status,
                "limits": limits,
                "approval_gates": sorted(set(str(gate) for gate in node.get("approval_gates", []) if gate)),
                "env_names": sorted(name for name in node.get("env", []) if isinstance(name, str) and "=" not in name),
                "preflight_command": command,
            }
        )

    return {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "month": month,
        "project": cfg.get("project", {}),
        "budget_contract": budget,
        "token_contract": token,
        "token_guards": token_guards(token),
        "usage_totals": totals,
        "subscription_controls": subs,
        "service_guards": service_guards,
        "env_names": sorted(env_names),
        "preflight_commands": preflight_commands,
        "next_actions": [
            "Run the listed usage-ledger preflight command before any paid/API/LLM/ads/subscription spend.",
            "Record real usage with usage-ledger.py record immediately after the run.",
            "Keep secret values in `.env` or provider consoles; this report lists env names only.",
        ],
    }


def generated_yaml(report: dict[str, Any]) -> str:
    payload = {
        "version": report["version"],
        "generated": report["generated"],
        "month": report["month"],
        "budget_contract": report.get("budget_contract", {}),
        "token_guards": report.get("token_guards", []),
        "service_guards": report.get("service_guards", []),
        "env_names": report.get("env_names", []),
        "preflight_commands": report.get("preflight_commands", {}),
        "next_actions": report.get("next_actions", []),
    }
    return dump_yaml(payload)


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    budget = report.get("budget_contract", {})
    lines = [
        "# seo-cycle spend guard",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Month: {report.get('month')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        "",
        "## Budget Contract",
        f"- Monthly total USD cap: ${budget.get('monthly_total_usd_cap')}",
        f"- Paid API USD cap: ${budget.get('monthly_paid_api_usd_cap')}",
        f"- LLM USD cap: ${budget.get('monthly_llm_usd_cap')}",
        f"- Ads USD cap: ${budget.get('monthly_ads_usd_cap')}",
        "",
        "## Token Guards",
    ]
    for guard in report.get("token_guards", []):
        lines.append(f"- {guard}")
    lines.extend(
        [
            "",
            "## Service Guards",
            "| Service | Category | Allowed | Status | Gates | Preflight |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.get("service_guards", []):
        lines.append(
            f"| {row['service']} | {row['category']} | {row['allowed_now']} | {row['status']} | "
            f"{', '.join(row.get('approval_gates', [])) or '-'} | `{row['preflight_command']}` |"
        )
    lines.extend(["", "## Env Names"])
    for name in report.get("env_names", []):
        lines.append(f"- `{name}`")
    lines.extend(["", "## Next Actions"])
    for item in report.get("next_actions", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Rules",
            "- No secret values belong in this report, git, prompts, or chat.",
            "- A service with `allowed=false` or `status=approval_required` needs human approval and/or policy caps before use.",
            "- Preflight estimates are intentionally tiny placeholders; replace them with the real planned spend before running a tool.",
        ]
    )
    return "\n".join(lines) + "\n"


def checklist_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["service", "category", "allowed_now", "status", "metric", "used", "cap", "remaining", "preflight_command"])
    writer.writeheader()
    for row in report.get("service_guards", []):
        limits = row.get("limits", {})
        if not limits:
            writer.writerow(
                {
                    "service": row["service"],
                    "category": row["category"],
                    "allowed_now": row["allowed_now"],
                    "status": row["status"],
                    "preflight_command": row["preflight_command"],
                }
            )
            continue
        for metric, limit in limits.items():
            writer.writerow(
                {
                    "service": row["service"],
                    "category": row["category"],
                    "allowed_now": row["allowed_now"],
                    "status": row["status"],
                    "metric": metric,
                    "used": limit.get("used"),
                    "cap": limit.get("cap"),
                    "remaining": limit.get("remaining"),
                    "preflight_command": row["preflight_command"],
                }
            )
    return buffer.getvalue()


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    setup_dir = project_root / "seo" / "setup"
    markdown = render_markdown(report)
    write_artifacts(
        text_files={
            project_root / "seo" / "spend-guard.generated.yaml": generated_yaml(report),
            setup_dir / "spend-guard.md": markdown,
            setup_dir / "latest-spend-guard.md": markdown,
            setup_dir / "spend-checklist.csv": checklist_csv(report),
        },
        json_files={
            setup_dir / "spend-guard.json": report,
            setup_dir / "latest-spend-guard.json": report,
        },
    )
    return setup_dir / "spend-guard.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write spend guard artifacts under seo/setup.")
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
