#!/usr/bin/env python3
"""Split a monthly budget between SEO content and PPC by expected leads per unit spent.

A transparent greedy model over "investment lots":
  SEO lot — one article for a biggest-upside cluster (from seo-forecast.json):
    cost = kpi.budget.cost_per_article; monthly clicks = cluster upside;
    value is amortized: clicks accrue along the forecast ramp, so the lot's
    monthly-lead figure uses ramp_share = (months_to_target+1)/(2*months_to_target)
    (average of a linear ramp) and pays off over seo_amortization_months.
  PPC lot — one budget step (kpi.budget.ppc_step) into the campaign with the
    best CPA (from ads-analytics.json); leads = step / CPA.

Lots are ranked by expected monthly leads per currency unit and greedily
packed into `--monthly-budget` (or kpi.budget.monthly_total). Every assumption
is printed. Offline-only: no API calls, no spend.

Output: seo/strategy/budget-mix.md/json (+latest) with --write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, numeric, project_root_for
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("budget-mix-planner")

DEFAULT_COST_PER_ARTICLE = 15000.0
DEFAULT_PPC_STEP = 10000.0
DEFAULT_AMORTIZATION_MONTHS = 12
MAX_PPC_LOTS_PER_CAMPAIGN = 5


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def seo_lots(forecast: dict[str, Any], *, cost_per_article: float, conversion: float,
             months_to_target: int) -> list[dict[str, Any]]:
    ramp_share = (months_to_target + 1) / (2 * months_to_target) if months_to_target else 1.0
    lots = []
    for cluster in forecast.get("cluster_upside_top10") or []:
        clicks = float(cluster.get("upside_clicks") or 0)
        if clicks <= 0:
            continue
        monthly_leads = clicks * conversion * ramp_share
        lots.append(
            {
                "channel": "seo",
                "lot": f"article: {cluster.get('cluster')}",
                "cost": cost_per_article,
                "expected_monthly_clicks": round(clicks * ramp_share, 1),
                "expected_monthly_leads": round(monthly_leads, 2),
                "leads_per_1000": round(monthly_leads / cost_per_article * 1000, 3) if cost_per_article else 0,
                "note": "one-time production cost; clicks persist and amortize over months",
            }
        )
    return lots


def ppc_lots(ads: dict[str, Any], *, ppc_step: float, conversion: float) -> list[dict[str, Any]]:
    lots = []
    for campaign in ads.get("campaigns") or []:
        cpa = campaign.get("cpa")
        if not cpa or float(cpa) <= 0:
            continue
        leads = ppc_step / float(cpa)
        for _ in range(MAX_PPC_LOTS_PER_CAMPAIGN):
            lots.append(
                {
                    "channel": "ppc",
                    "lot": f"budget step: {campaign.get('name') or campaign.get('campaign_id')}"
                           f" ({campaign.get('platform')})",
                    "cost": ppc_step,
                    "expected_monthly_clicks": round(leads / conversion, 1) if conversion else 0,
                    "expected_monthly_leads": round(leads, 2),
                    "leads_per_1000": round(leads / ppc_step * 1000, 3),
                    "note": f"recurring monthly spend at current CPA {cpa}",
                }
            )
    return lots


def build_report(project_root: pathlib.Path, cfg: dict[str, Any], monthly_budget: float) -> dict[str, Any]:
    strategy = project_root / "seo" / "strategy"
    forecast = load_json(strategy / "seo-forecast.json")
    ads = load_json(project_root / "seo" / "ads" / "ads-analytics.json")
    conversion = float(nested_get(cfg, "kpi.lead_conversion_rate", 0.02) or 0.02)
    months = max(1, int(nested_get(cfg, "kpi.months_to_target", 6) or 6))
    cost_per_article = float(numeric(nested_get(cfg, "kpi.budget.cost_per_article"), DEFAULT_COST_PER_ARTICLE))
    ppc_step = float(numeric(nested_get(cfg, "kpi.budget.ppc_step"), DEFAULT_PPC_STEP))
    budget = monthly_budget or float(numeric(nested_get(cfg, "kpi.budget.monthly_total"), 0))

    lots = seo_lots(forecast, cost_per_article=cost_per_article, conversion=conversion,
                    months_to_target=months) + ppc_lots(ads, ppc_step=ppc_step, conversion=conversion)
    lots.sort(key=lambda lot: lot["leads_per_1000"], reverse=True)

    selected: list[dict[str, Any]] = []
    remaining = budget
    for lot in lots:
        if lot["cost"] <= remaining:
            selected.append(lot)
            remaining -= lot["cost"]

    seo_spend = sum(lot["cost"] for lot in selected if lot["channel"] == "seo")
    ppc_spend = sum(lot["cost"] for lot in selected if lot["channel"] == "ppc")
    total_leads = sum(lot["expected_monthly_leads"] for lot in selected)
    return {
        "audit_id": "budget_mix",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "monthly_budget": budget,
            "cost_per_article": cost_per_article,
            "ppc_step": ppc_step,
            "lead_conversion_rate": conversion,
            "months_to_target": months,
            "forecast_available": bool(forecast),
            "ads_analytics_available": bool(ads.get("campaigns")),
            "candidate_lots": len(lots),
        },
        "mix": {
            "seo_spend": round(seo_spend, 2),
            "ppc_spend": round(ppc_spend, 2),
            "unallocated": round(remaining, 2),
            "seo_share_pct": round(seo_spend / budget * 100, 1) if budget else 0,
            "ppc_share_pct": round(ppc_spend / budget * 100, 1) if budget else 0,
            "expected_monthly_leads": round(total_leads, 1),
        },
        "selected_lots": selected,
        "skipped_top_lots": [lot for lot in lots if lot not in selected][:10],
        "assumptions": [
            "SEO lot value uses the average of a linear ramp to target and ignores seasonality.",
            "PPC lots assume current campaign CPA holds at higher spend (diminishing returns are NOT modeled).",
            f"PPC lots are capped at {MAX_PPC_LOTS_PER_CAMPAIGN} steps per campaign to limit that assumption.",
            "SEO production cost is one-time; PPC spend is recurring monthly — compare accordingly.",
            "Run seo-forecast.py and ads-analytics.py first; empty inputs shrink the lot pool.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    mix = report["mix"]
    inputs = report["inputs"]
    lines = [
        "# Budget Mix (SEO + PPC)",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Budget: {inputs['monthly_budget']} · SEO {mix['seo_spend']} ({mix['seo_share_pct']}%)"
        f" · PPC {mix['ppc_spend']} ({mix['ppc_share_pct']}%) · unallocated {mix['unallocated']}",
        f"- Expected monthly leads from the plan: **{mix['expected_monthly_leads']}**",
        "",
        "## Selected lots (ranked by leads per 1000)",
        "",
        "| # | Channel | Lot | Cost | Leads/mo | Leads per 1000 |",
        "|---|---|---|---:|---:|---:|",
    ]
    for index, lot in enumerate(report["selected_lots"], 1):
        lines.append(f"| {index} | {lot['channel']} | {lot['lot']} | {lot['cost']}"
                     f" | {lot['expected_monthly_leads']} | {lot['leads_per_1000']} |")
    if not report["selected_lots"]:
        lines.append("| — | — | no lots fit the budget (or inputs are empty) | — | — | — |")
    if report["skipped_top_lots"]:
        lines.extend(["", "## Next lots if the budget grows", ""])
        for lot in report["skipped_top_lots"][:5]:
            lines.append(f"- {lot['channel']}: {lot['lot']} — cost {lot['cost']},"
                         f" {lot['expected_monthly_leads']} leads/mo")
    lines.extend(["", "## Assumptions", ""])
    lines.extend(f"- {item}" for item in report["assumptions"])
    return "\n".join(lines) + "\n"


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "strategy"
    return {
        "markdown": base / "budget-mix.md",
        "json": base / "budget-mix.json",
        "latest_markdown": base / "latest-budget-mix.md",
        "latest_json": base / "latest-budget-mix.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--monthly-budget", type=float, default=0,
                        help="Monthly budget (overrides kpi.budget.monthly_total)")
    parser.add_argument("--write", action="store_true", help="Write seo/strategy/budget-mix.* artifacts")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("budget-mix-planner", project_root, cfg)

    report = build_report(project_root, cfg, args.monthly_budget)
    if not report["inputs"]["monthly_budget"]:
        print("No budget set: pass --monthly-budget or fill kpi.budget.monthly_total.", file=sys.stderr)
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
