#!/usr/bin/env python3
"""Track and preflight SEO tool usage, tokens, credits, and spend.

The ledger is project-local, append-only, and secret-free. It combines manual
records in `seo/usage/usage-ledger.jsonl` with compatible local usage artifacts
from tools such as Keys.so, SpyFu, and Google NLP, then reports current-month
spend against `governance` and `seo/tool-budget.yaml` caps.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
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

COMMANDS = {"report", "check", "record"}
LLM_SERVICES = {"openai", "anthropic", "claude", "gemini", "deepseek", "perplexity", "llm_cli", "codex", "antigravity"}
ADS_SERVICES = {"google_ads", "yandex_direct", "microsoft_ads"}
PAID_API_SERVICES = {
    "neuronwriter",
    "google_cloud_nlp",
    "google_nlp",
    "keys_so",
    "keyso",
    "serpstat",
    "spyfu",
    "dataforseo",
    "answerthepublic",
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


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get(key, default))


def current_month() -> str:
    return dt.date.today().strftime("%Y-%m")


def infer_category(service: str, category: str | None = None) -> str:
    if category:
        return category
    service = service.lower()
    if service in LLM_SERVICES:
        return "llm"
    if service in ADS_SERVICES:
        return "ads"
    if service in PAID_API_SERVICES:
        return "paid_api"
    return "tool"


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def metric_payload(args: argparse.Namespace) -> dict[str, float]:
    raw = {
        "usd": args.usd,
        "input_tokens": args.input_tokens,
        "output_tokens": args.output_tokens,
        "requests": args.requests,
        "credits": args.credits,
        "units": args.units,
        "rows": args.rows,
        "browser_minutes": args.browser_minutes,
        "browser_pages": args.browser_pages,
        "content_writer": args.content_writer,
        "ai_credits": args.ai_credits,
    }
    return {key: numeric(value) for key, value in raw.items() if numeric(value) != 0}


def empty_totals() -> dict[str, Any]:
    return {
        "overall": {key: 0.0 for key in METRIC_KEYS},
        "categories": {},
        "services": {},
        "events": 0,
        "imported_events": 0,
    }


def add_metrics(target: dict[str, Any], service: str, category: str, metrics: dict[str, float], imported: bool = False) -> None:
    target["events"] += 0 if imported else 1
    target["imported_events"] += 1 if imported else 0
    for key, value in metrics.items():
        target["overall"][key] = target["overall"].get(key, 0.0) + value
        cat = target["categories"].setdefault(category, {metric: 0.0 for metric in METRIC_KEYS})
        cat[key] = cat.get(key, 0.0) + value
        svc = target["services"].setdefault(service, {"category": category, **{metric: 0.0 for metric in METRIC_KEYS}})
        svc[key] = svc.get(key, 0.0) + value


def read_ledger_events(path: pathlib.Path, month: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            rows.append({"_error": f"invalid json line {line_no}"})
            continue
        if row.get("month") == month:
            rows.append(row)
    return rows


def imported_usage_events(project_root: pathlib.Path, month: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for fp in glob.glob(str(project_root / "seo/research/*/_usage.json")):
        path = pathlib.Path(fp)
        data = load_json(path)
        if data.get("month") != month:
            continue
        service = path.parent.name
        metrics: dict[str, float] = {}
        if numeric(data.get("spent_usd")):
            metrics["usd"] = numeric(data.get("spent_usd"))
        if numeric(data.get("rows")):
            metrics["rows"] = numeric(data.get("rows"))
        if numeric(data.get("requests")):
            metrics["requests"] = numeric(data.get("requests"))
        if metrics:
            events.append(
                {
                    "timestamp": path.stat().st_mtime,
                    "month": month,
                    "service": service,
                    "category": infer_category(service),
                    "metrics": metrics,
                    "source": str(path),
                    "imported": True,
                }
            )

    for fp in glob.glob(str(project_root / "seo/**/usage-*.json"), recursive=True):
        path = pathlib.Path(fp)
        if f"usage-{month}.json" not in path.name:
            continue
        data = load_json(path)
        if data.get("month") != month:
            continue
        features = data.get("features", {}) if isinstance(data.get("features"), dict) else {}
        units = sum(numeric(value) for value in features.values())
        if units:
            events.append(
                {
                    "timestamp": path.stat().st_mtime,
                    "month": month,
                    "service": "google_cloud_nlp" if "google-nlp" in str(path) else path.parent.name,
                    "category": "paid_api",
                    "metrics": {"units": units},
                    "source": str(path),
                    "imported": True,
                }
            )
    return events


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    totals = empty_totals()
    errors = []
    for row in events:
        if row.get("_error"):
            errors.append(row["_error"])
            continue
        service = str(row.get("service") or "unknown")
        category = infer_category(service, row.get("category"))
        metrics = row.get("metrics", {}) if isinstance(row.get("metrics"), dict) else {}
        add_metrics(totals, service, category, {key: numeric(value) for key, value in metrics.items()}, bool(row.get("imported")))
    totals["errors"] = errors
    return totals


def service_caps(cfg: dict[str, Any], tool_budget: dict[str, Any]) -> dict[str, dict[str, float]]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    subscriptions = governance.get("subscriptions", {}) if isinstance(governance.get("subscriptions"), dict) else {}
    tool_subs = tool_budget.get("subscriptions", {}) if isinstance(tool_budget.get("subscriptions"), dict) else {}
    merged = {**tool_subs, **subscriptions}
    caps: dict[str, dict[str, float]] = {}

    for service, node in merged.items():
        if not isinstance(node, dict):
            continue
        caps.setdefault(service, {})
        if "monthly_usd_cap" in node:
            caps[service]["usd"] = numeric(node.get("monthly_usd_cap"))
        if "monthly_spend_cap" in node:
            caps[service]["usd"] = numeric(node.get("monthly_spend_cap"))
        if "monthly_budget_usd" in node:
            caps[service]["usd"] = numeric(node.get("monthly_budget_usd"))
        if "monthly_request_cap" in node:
            caps[service]["requests"] = numeric(node.get("monthly_request_cap"))
        if "monthly_credit_cap" in node:
            caps[service]["credits"] = numeric(node.get("monthly_credit_cap"))
        if "monthly_content_writer_limit" in node:
            caps[service]["content_writer"] = numeric(node.get("monthly_content_writer_limit"))
        if "monthly_ai_credit_limit" in node:
            caps[service]["ai_credits"] = numeric(node.get("monthly_ai_credit_limit"))
        if "reserve_credits" in node:
            caps[service]["reserve_credits"] = numeric(node.get("reserve_credits"))
        if "reserve_requests" in node:
            caps[service]["reserve_requests"] = numeric(node.get("reserve_requests"))

    # Normalize aliases used by tools and users.
    if "keys_so" in caps and "keyso" not in caps:
        caps["keyso"] = caps["keys_so"]
    if "google_nlp" in caps and "google_cloud_nlp" not in caps:
        caps["google_cloud_nlp"] = caps["google_nlp"]
    return caps


def global_caps(cfg: dict[str, Any], tool_budget: dict[str, Any]) -> dict[str, float]:
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    budget = governance.get("budget_policy", {}) if isinstance(governance.get("budget_policy"), dict) else {}
    token_policy = governance.get("token_policy", {}) if isinstance(governance.get("token_policy"), dict) else {}
    money = tool_budget.get("money_budget", {}) if isinstance(tool_budget.get("money_budget"), dict) else {}
    tokens = tool_budget.get("token_budget", {}) if isinstance(tool_budget.get("token_budget"), dict) else {}
    return {
        "monthly_total_usd_cap": numeric(budget.get("monthly_total_usd_cap", money.get("monthly_total_usd_cap", 0))),
        "monthly_paid_api_usd_cap": numeric(budget.get("monthly_paid_api_usd_cap", money.get("monthly_paid_api_usd_cap", 0))),
        "monthly_llm_usd_cap": numeric(budget.get("monthly_llm_usd_cap", money.get("monthly_llm_usd_cap", 0))),
        "monthly_ads_usd_cap": numeric(money.get("monthly_ads_usd_cap", 0)),
        "monthly_input_tokens_cap": numeric(token_policy.get("monthly_input_tokens_cap", tokens.get("monthly_input_tokens_cap", 0))),
        "monthly_output_tokens_cap": numeric(token_policy.get("monthly_output_tokens_cap", tokens.get("monthly_output_tokens_cap", 0))),
        "require_approval_over_usd": numeric(budget.get("require_approval_over_usd", money.get("require_approval_over_usd", 0))),
    }


def load_state(cfg_path: pathlib.Path, month: str) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    tool_budget_path = policy_path(cfg, project_root, "tool_budget", "seo/tool-budget.yaml")
    tool_budget = load_yaml(tool_budget_path)
    ledger_path = policy_path(cfg, project_root, "usage_ledger", "seo/usage/usage-ledger.jsonl")
    events = read_ledger_events(ledger_path, month) + imported_usage_events(project_root, month)
    return {
        "cfg": cfg,
        "project_root": project_root,
        "tool_budget": tool_budget,
        "tool_budget_path": tool_budget_path,
        "ledger_path": ledger_path,
        "month": month,
        "events": events,
        "totals": summarize(events),
        "global_caps": global_caps(cfg, tool_budget),
        "service_caps": service_caps(cfg, tool_budget),
    }


def cap_row(scope: str, metric: str, used: float, cap: float, reserve: float = 0.0, estimate: float = 0.0) -> dict[str, Any]:
    effective_cap = cap - reserve if cap > 0 else cap
    projected = used + estimate
    remaining = effective_cap - projected if effective_cap > 0 else None
    status = "uncapped"
    if effective_cap == 0 and projected > 0:
        status = "approval_required"
    elif effective_cap > 0 and projected > effective_cap:
        status = "blocked"
    elif effective_cap > 0 and remaining is not None and remaining <= max(effective_cap * 0.1, 1):
        status = "near_cap"
    elif effective_cap > 0:
        status = "ok"
    return {
        "scope": scope,
        "metric": metric,
        "used": round(used, 4),
        "estimate": round(estimate, 4),
        "projected": round(projected, 4),
        "cap": round(cap, 4),
        "reserve": round(reserve, 4),
        "effective_cap": round(effective_cap, 4),
        "remaining": round(remaining, 4) if remaining is not None else None,
        "status": status,
    }


def evaluate(state: dict[str, Any], estimate: dict[str, Any] | None = None) -> dict[str, Any]:
    estimate = estimate or {}
    totals = state["totals"]
    caps = state["global_caps"]
    svc_caps = state["service_caps"]
    rows: list[dict[str, Any]] = []

    estimate_service = estimate.get("service")
    estimate_category = estimate.get("category")
    estimate_metrics = estimate.get("metrics", {})
    category = infer_category(str(estimate_service or ""), estimate_category)

    total_usd_estimate = numeric(estimate_metrics.get("usd"))
    rows.append(cap_row("global", "usd", totals["overall"].get("usd", 0.0), caps["monthly_total_usd_cap"], estimate=total_usd_estimate))
    rows.append(cap_row("llm", "usd", totals["categories"].get("llm", {}).get("usd", 0.0), caps["monthly_llm_usd_cap"], estimate=total_usd_estimate if category == "llm" else 0.0))
    rows.append(cap_row("paid_api", "usd", totals["categories"].get("paid_api", {}).get("usd", 0.0), caps["monthly_paid_api_usd_cap"], estimate=total_usd_estimate if category == "paid_api" else 0.0))
    rows.append(cap_row("ads", "usd", totals["categories"].get("ads", {}).get("usd", 0.0), caps["monthly_ads_usd_cap"], estimate=total_usd_estimate if category == "ads" else 0.0))
    rows.append(cap_row("global", "input_tokens", totals["overall"].get("input_tokens", 0.0), caps["monthly_input_tokens_cap"], estimate=numeric(estimate_metrics.get("input_tokens"))))
    rows.append(cap_row("global", "output_tokens", totals["overall"].get("output_tokens", 0.0), caps["monthly_output_tokens_cap"], estimate=numeric(estimate_metrics.get("output_tokens"))))

    if estimate_service:
        service = str(estimate_service)
        service_used = totals["services"].get(service, {})
        service_cap = svc_caps.get(service, {})
        for metric, estimate_value in estimate_metrics.items():
            if metric not in service_cap:
                continue
            reserve = service_cap.get(f"reserve_{metric}", 0.0)
            if metric == "credits":
                reserve = service_cap.get("reserve_credits", reserve)
            if metric == "requests":
                reserve = service_cap.get("reserve_requests", reserve)
            rows.append(
                cap_row(
                    service,
                    metric,
                    numeric(service_used.get(metric)),
                    numeric(service_cap.get(metric)),
                    reserve=reserve,
                    estimate=numeric(estimate_value),
                )
            )

    statuses = {row["status"] for row in rows}
    approval_required = [row for row in rows if row["status"] == "approval_required"]
    blocked = [row for row in rows if row["status"] == "blocked"]
    near_cap = [row for row in rows if row["status"] == "near_cap"]
    return {
        "allowed": not blocked and not approval_required,
        "status": "blocked" if blocked else ("approval_required" if approval_required else ("near_cap" if near_cap else "ok")),
        "rows": rows,
        "blocked": blocked,
        "approval_required": approval_required,
        "near_cap": near_cap,
    }


def build_report(state: dict[str, Any], estimate: dict[str, Any] | None = None) -> dict[str, Any]:
    evaluation = evaluate(state, estimate)
    cfg = state["cfg"]
    return {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "project_root": str(state["project_root"]),
        "month": state["month"],
        "ledger_path": str(state["ledger_path"]),
        "tool_budget_path": str(state["tool_budget_path"]),
        "totals": state["totals"],
        "global_caps": state["global_caps"],
        "service_caps": state["service_caps"],
        "evaluation": evaluation,
        "estimate": estimate or {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    totals = report.get("totals", {})
    evaluation = report.get("evaluation", {})
    lines = [
        "# seo-cycle usage ledger",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Month: {report.get('month')}",
        f"- Ledger: `{report.get('ledger_path')}`",
        f"- Status: {evaluation.get('status')}",
        f"- Allowed without approval: {evaluation.get('allowed')}",
        f"- Events: {totals.get('events', 0)} manual, {totals.get('imported_events', 0)} imported",
        "",
        "## Totals",
        "| Scope | USD | Input tokens | Output tokens | Requests | Credits | Units | Rows | Browser min | Pages | Content writer | AI credits |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    scopes = {"overall": totals.get("overall", {})}
    scopes.update(totals.get("categories", {}))
    for scope, metrics in scopes.items():
        lines.append(
            f"| {scope} | {metrics.get('usd', 0):.4f} | {metrics.get('input_tokens', 0):.0f} | "
            f"{metrics.get('output_tokens', 0):.0f} | {metrics.get('requests', 0):.0f} | "
            f"{metrics.get('credits', 0):.0f} | {metrics.get('units', 0):.0f} | {metrics.get('rows', 0):.0f} | "
            f"{metrics.get('browser_minutes', 0):.1f} | {metrics.get('browser_pages', 0):.0f} | "
            f"{metrics.get('content_writer', 0):.0f} | {metrics.get('ai_credits', 0):.0f} |"
        )

    lines.extend(["", "## Cap Check", "| Scope | Metric | Used | Estimate | Cap | Reserve | Remaining | Status |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"])
    for row in evaluation.get("rows", []):
        remaining = row.get("remaining")
        remaining_text = "-" if remaining is None else f"{remaining:.4f}"
        lines.append(
            f"| {row['scope']} | {row['metric']} | {row['used']:.4f} | {row['estimate']:.4f} | "
            f"{row['cap']:.4f} | {row['reserve']:.4f} | {remaining_text} | {row['status']} |"
        )

    if totals.get("errors"):
        lines.extend(["", "## Ledger Errors"])
        lines.extend(f"- {item}" for item in totals["errors"])

    lines.extend(
        [
            "",
            "## Usage Commands",
            "- Check before spend: `python3 ~/.claude/skills/seo-cycle/scripts/usage-ledger.py check --service openai --category llm --usd 0.25 --input-tokens 5000 --output-tokens 1000`",
            "- Record after spend: `python3 ~/.claude/skills/seo-cycle/scripts/usage-ledger.py record --service openai --category llm --usd 0.25 --input-tokens 5000 --output-tokens 1000 --task \"brief\"`",
        ]
    )
    return "\n".join(lines) + "\n"


def write_report(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    out_dir = project_root / "seo" / "setup"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = pathlib.Path(report.get("ledger_path", ""))
    if str(ledger_path):
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.touch(exist_ok=True)
    md_path = out_dir / "latest-usage-ledger.md"
    json_path = out_dir / "latest-usage-ledger.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return md_path


def append_record(state: dict[str, Any], args: argparse.Namespace) -> pathlib.Path:
    metrics = metric_payload(args)
    if not metrics:
        raise SystemExit("ERROR: record requires at least one non-zero metric, e.g. --usd or --input-tokens")
    service = args.service
    if not service:
        raise SystemExit("ERROR: record requires --service")
    category = infer_category(service, args.category)
    record = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "month": state["month"],
        "service": service,
        "category": category,
        "task": args.task,
        "source": args.source,
        "note": args.note,
        "metrics": metrics,
    }
    path = state["ledger_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def parse_cli(argv: list[str]) -> tuple[str, str | None, argparse.Namespace]:
    raw = list(argv)
    command = "report"
    if raw and raw[0] in COMMANDS:
        command = raw.pop(0)
    config = None
    if raw and not raw[0].startswith("-"):
        config = raw.pop(0)

    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default=current_month(), help="YYYY-MM, default current month.")
    parser.add_argument("--write", action="store_true", help="Write latest usage report under seo/setup.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--fail-on-block", action="store_true", help="For check: exit 1 when blocked or approval is required.")
    parser.add_argument("--service", default="", help="Tool/service name, e.g. openai, keyso, spyfu, google_cloud_nlp.")
    parser.add_argument("--category", choices=("llm", "paid_api", "ads", "subscription", "browser", "tool"), help="Override service category.")
    parser.add_argument("--task", default="", help="Task/cycle label.")
    parser.add_argument("--source", default="", help="Source artifact or command.")
    parser.add_argument("--note", default="", help="Human-readable note, no secrets.")
    parser.add_argument("--usd", type=float, default=0)
    parser.add_argument("--input-tokens", type=float, default=0)
    parser.add_argument("--output-tokens", type=float, default=0)
    parser.add_argument("--requests", type=float, default=0)
    parser.add_argument("--credits", type=float, default=0)
    parser.add_argument("--units", type=float, default=0)
    parser.add_argument("--rows", type=float, default=0)
    parser.add_argument("--browser-minutes", type=float, default=0)
    parser.add_argument("--browser-pages", type=float, default=0)
    parser.add_argument("--content-writer", type=float, default=0)
    parser.add_argument("--ai-credits", type=float, default=0)
    return command, config, parser.parse_args(raw)


def main(argv: list[str] | None = None) -> int:
    command, config, args = parse_cli(argv or sys.argv[1:])
    if config:
        cfg_path = pathlib.Path(config).expanduser().resolve()
    else:
        found = find_config(pathlib.Path.cwd())
        if not found:
            print(f"ERROR: seo-cycle.yaml не найден в {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        cfg_path = found.resolve()
    if not cfg_path.exists():
        print(f"ERROR: {cfg_path} не найден", file=sys.stderr)
        return 2

    state = load_state(cfg_path, args.month)

    estimate = None
    if command in {"check", "record"}:
        metrics = metric_payload(args)
        if not args.service:
            print(f"ERROR: {command} requires --service", file=sys.stderr)
            return 2
        if not metrics:
            print(f"ERROR: {command} requires at least one estimate metric", file=sys.stderr)
            return 2
        estimate = {
            "service": args.service,
            "category": infer_category(args.service, args.category),
            "metrics": metrics,
            "task": args.task,
        }

    if command == "record":
        evaluation = evaluate(state, estimate)
        if evaluation["status"] in {"blocked", "approval_required"} and args.fail_on_block:
            print(json.dumps({"recorded": False, "evaluation": evaluation}, ensure_ascii=False, indent=2))
            return 1
        path = append_record(state, args)
        state = load_state(cfg_path, args.month)
        report = build_report(state)
        if args.write:
            write_report(state["project_root"], report)
        print(f"Recorded usage in {path}")
        return 0

    report = build_report(state, estimate)
    if args.write:
        out = write_report(state["project_root"], report)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"Wrote {out}")
    elif args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")

    if command == "check" and args.fail_on_block and report["evaluation"]["status"] in {"blocked", "approval_required"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
