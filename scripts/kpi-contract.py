#!/usr/bin/env python3
"""Check project KPI goals against tracked facts and escalate when off track.

The "guaranteed result" loop: goals live in the `kpi` config section
(monthly organic clicks / leads / keywords in top-10 with a start month and a
deadline), the plan for the current month is a linear ramp from the baseline
to the goal, and facts come from the latest position snapshot in seo.db
(db-sync.py). Statuses per goal:

  on_track  — fact >= plan × (1 − tolerance)
  at_risk   — fact >= plan × (1 − 2×tolerance)
  off_track — below that

When the contract is at risk the report pulls corrective actions from the
latest seo-forecast (biggest-upside clusters) plus the standard levers
(quality loop, refresh, triggers, ads analytics). `--escalate` opens a
`kpi_off_track` approval ticket and sends a Telegram alert for an off-track
month. Output: seo/strategy/kpi-report.md/json (+latest) with --write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sqlite3
import subprocess
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, numeric, project_root_for
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("kpi-contract")

GOAL_KEYS = ("monthly_organic_clicks", "monthly_leads", "keywords_in_top10")
STATUS_ORDER = {"on_track": 0, "at_risk": 1, "off_track": 2}


def scripts_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def parse_month(raw: Any, fallback: dt.date) -> dt.date:
    try:
        year, month = str(raw).strip().split("-")[:2]
        return dt.date(int(year), int(month), 1)
    except (ValueError, AttributeError):
        return fallback


def months_between(start: dt.date, end: dt.date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def load_facts(project_root: pathlib.Path, cfg: dict[str, Any]) -> dict[str, Any]:
    db_rel = nested_get(cfg, "data_store.path", "seo/seo.db") or "seo/seo.db"
    db_path = project_root / db_rel
    facts = {"monthly_organic_clicks": 0.0, "keywords_in_top10": 0, "snapshot_date": None}
    if not db_path.exists():
        return facts
    try:
        conn = sqlite3.connect(db_path)
        latest = conn.execute("SELECT MAX(snapshot_date) FROM positions").fetchone()[0]
        if latest:
            clicks = conn.execute(
                "SELECT COALESCE(SUM(clicks), 0) FROM positions WHERE snapshot_date = ?", (latest,)
            ).fetchone()[0]
            top10 = conn.execute(
                "SELECT COUNT(DISTINCT query) FROM positions WHERE snapshot_date = ?"
                " AND position > 0 AND position <= 10", (latest,)
            ).fetchone()[0]
            facts.update({"monthly_organic_clicks": float(clicks or 0),
                          "keywords_in_top10": int(top10 or 0), "snapshot_date": latest})
        conn.close()
    except sqlite3.Error:
        pass
    return facts


def plan_for_month(baseline: float, goal: float, start: dt.date, deadline: dt.date,
                   today: dt.date) -> float:
    total = max(1, months_between(start, deadline))
    elapsed = min(max(0, months_between(start, today)), total)
    return baseline + (goal - baseline) * (elapsed / total)


def goal_status(fact: float, plan: float, tolerance: float) -> str:
    if plan <= 0:
        return "on_track"
    if fact >= plan * (1 - tolerance):
        return "on_track"
    if fact >= plan * (1 - 2 * tolerance):
        return "at_risk"
    return "off_track"


def corrective_actions(project_root: pathlib.Path) -> list[str]:
    actions = []
    forecast_path = project_root / "seo" / "strategy" / "seo-forecast.json"
    try:
        forecast = json.loads(forecast_path.read_text(encoding="utf-8"))
        for item in (forecast.get("cluster_upside_top10") or [])[:3]:
            actions.append(
                f"Push cluster `{item['cluster']}` to top-10 (+{item['upside_clicks']} clicks/mo potential)"
            )
    except (OSError, json.JSONDecodeError):
        actions.append("Run `python3 scripts/seo-forecast.py --write` to see which clusters have the biggest upside.")
    actions.extend(
        [
            "Run the quality loop on the research package: `seo-cycle loop research-package seo/research-package`.",
            "Evaluate refresh triggers on decayed pages: `python3 scripts/triggers-eval.py` + refresh plan.",
            "Check paid overlap and wasted spend: `seo-cycle ads analytics --write` (if ads are enabled).",
            "Review lost keywords: `python3 scripts/lost-keywords.py`.",
        ]
    )
    return actions


def escalate(project_root: pathlib.Path, summary_line: str, report_path: str) -> str | None:
    create = subprocess.run(
        [
            sys.executable, str(scripts_dir() / "approval-gate.py"), "create",
            "--type", "kpi_off_track",
            "--title", summary_line,
            "--file", report_path,
            "--context", "KPI contract is off track this month; review corrective actions and re-plan.",
        ],
        cwd=project_root, text=True, capture_output=True, check=False,
    )
    ticket = create.stdout.strip().splitlines()[-1] if create.stdout.strip() else None
    subprocess.run(
        [sys.executable, str(scripts_dir() / "notify.py"),
         f"KPI contract off track: {summary_line}", "--title", "SEO KPI alert", "--level", "alert"],
        cwd=project_root, text=True, capture_output=True, check=False,
    )
    return ticket if create.returncode == 0 else None


def build_report(project_root: pathlib.Path, cfg: dict[str, Any]) -> dict[str, Any]:
    kpi = cfg.get("kpi") if isinstance(cfg.get("kpi"), dict) else {}
    today = dt.date.today().replace(day=1)
    start = parse_month(kpi.get("start"), today)
    deadline = parse_month(kpi.get("deadline"), today.replace(year=today.year + 1))
    tolerance = float(numeric(kpi.get("tolerance_pct"), 20)) / 100
    conversion = float(numeric(kpi.get("lead_conversion_rate"), 0.02))
    goals = kpi.get("goals") if isinstance(kpi.get("goals"), dict) else {}
    baseline = kpi.get("baseline") if isinstance(kpi.get("baseline"), dict) else {}

    facts = load_facts(project_root, cfg)
    facts["monthly_leads"] = round(facts["monthly_organic_clicks"] * conversion, 1)

    rows = []
    for key in GOAL_KEYS:
        goal_value = numeric(goals.get(key), 0)
        if goal_value <= 0:
            continue
        plan = plan_for_month(numeric(baseline.get(key), 0), goal_value, start, deadline, today)
        fact = float(facts.get(key) or 0)
        rows.append(
            {
                "goal": key,
                "target": round(goal_value, 1),
                "plan_this_month": round(plan, 1),
                "fact": round(fact, 1),
                "delta_pct": round((fact - plan) / plan * 100, 1) if plan else 0.0,
                "status": goal_status(fact, plan, tolerance),
            }
        )
    overall = max((row["status"] for row in rows), key=lambda s: STATUS_ORDER[s], default="no_goals")
    report = {
        "audit_id": "kpi_contract",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "enabled": bool(kpi.get("enabled")),
        "contract": {
            "start": start.strftime("%Y-%m"),
            "deadline": deadline.strftime("%Y-%m"),
            "month": today.strftime("%Y-%m"),
            "tolerance_pct": round(tolerance * 100),
            "lead_conversion_rate": conversion,
        },
        "facts": facts,
        "goals": rows,
        "overall_status": overall,
        "corrective_actions": corrective_actions(project_root) if overall in {"at_risk", "off_track"} else [],
        "escalation_ticket": None,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    contract = report["contract"]
    lines = [
        "# KPI Contract",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Contract: {contract['start']} → {contract['deadline']}"
        f" · month: {contract['month']} · tolerance: ±{contract['tolerance_pct']}%",
        f"- Facts snapshot: {report['facts'].get('snapshot_date') or 'no seo.db positions yet'}",
        f"- **Overall status: `{report['overall_status']}`**",
        "",
        "## Goals",
        "",
        "| Goal | Target | Plan (this month) | Fact | Δ% | Status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in report["goals"]:
        lines.append(
            f"| {row['goal']} | {row['target']} | {row['plan_this_month']} | {row['fact']}"
            f" | {row['delta_pct']} | {row['status']} |"
        )
    if not report["goals"]:
        lines.append("| — | — | — | — | — | no goals configured (`kpi.goals`) |")
    if report["corrective_actions"]:
        lines.extend(["", "## Corrective actions", ""])
        lines.extend(f"- {action}" for action in report["corrective_actions"])
    if report.get("escalation_ticket"):
        lines.extend(["", f"Escalation ticket: `{report['escalation_ticket']}`"])
    return "\n".join(lines) + "\n"


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "strategy"
    return {
        "markdown": base / "kpi-report.md",
        "json": base / "kpi-report.json",
        "latest_markdown": base / "latest-kpi-report.md",
        "latest_json": base / "latest-kpi-report.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write seo/strategy/kpi-report.* artifacts")
    parser.add_argument("--escalate", action="store_true",
                        help="Open a kpi_off_track approval ticket + Telegram alert when off track")
    parser.add_argument("--fail-on-off-track", action="store_true", help="Exit 1 when the contract is off track")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("kpi-contract", project_root, cfg)

    report = build_report(project_root, cfg)
    if not report["goals"]:
        print("No KPI goals configured — fill the `kpi` section in seo-cycle.yaml.", file=sys.stderr)

    if args.escalate and report["overall_status"] == "off_track":
        worst = min(report["goals"], key=lambda row: row["delta_pct"], default=None)
        summary_line = (f"{worst['goal']}: fact {worst['fact']} vs plan {worst['plan_this_month']}"
                        f" ({worst['delta_pct']}%)") if worst else "KPI off track"
        report["escalation_ticket"] = escalate(project_root, summary_line, "seo/strategy/kpi-report.md")

    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    log.info("kpi status=%s goals=%s", report["overall_status"], len(report["goals"]))
    return 1 if args.fail_on_off_track and report["overall_status"] == "off_track" else 0


if __name__ == "__main__":
    raise SystemExit(main())
