#!/usr/bin/env python3
"""Traffic/lead forecast from the semantic core, current positions, and a CTR curve.

An honest, simple model — every assumption is printed in the report:
  clicks(keyword) = monthly_frequency × CTR(position)
Scenarios: `current` (positions as tracked today), `target_top10` (every
ranked keyword reaches at least position 8), `target_top3` (position 3).
Pessimistic/optimistic bounds are ±40% by default. A linear ramp over
`kpi.months_to_target` months (default 6) turns the target into a month-by-
month plan that kpi-contract.py checks facts against.

Inputs: research-package semantic core (frequency per keyword), `positions`
from seo.db (db-sync.py) or a GSC snapshot already merged there.
Output: seo/strategy/seo-forecast.md/json (+latest) with --write.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import sqlite3
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, numeric, project_root_for
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("seo-forecast")

DEFAULT_CTR_CURVE = {1: 0.28, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05, 6: 0.04, 7: 0.03,
                     8: 0.025, 9: 0.02, 10: 0.018}
CTR_11_20 = 0.01
CTR_BEYOND = 0.002
UNRANKED_POSITION = 40.0
BOUNDS = (0.6, 1.4)  # pessimistic / optimistic multipliers


def ctr_for(position: float, curve: dict[int, float]) -> float:
    if position <= 0:
        return CTR_BEYOND
    bucket = int(round(position))
    if bucket in curve:
        return curve[bucket]
    if bucket <= 20:
        return CTR_11_20
    return CTR_BEYOND


def load_ctr_curve(cfg: dict[str, Any]) -> dict[int, float]:
    curve = dict(DEFAULT_CTR_CURVE)
    override = nested_get(cfg, "kpi.ctr_curve", {}) or {}
    if isinstance(override, dict):
        for key, value in override.items():
            try:
                curve[int(key)] = float(value)
            except (TypeError, ValueError):
                continue
    return curve


def load_core(project_root: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in ("semantic-core.cleaned.csv", "semantic-core.csv"):
        path = project_root / "seo" / "research-package" / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                keyword = " ".join(str(row.get("keyword") or row.get("query") or "").lower().split())
                if not keyword:
                    continue
                frequency = 0.0
                for field in ("frequency", "volume", "impressions"):
                    frequency = numeric(row.get(field), 0)
                    if frequency:
                        break
                rows.append({"keyword": keyword, "frequency": frequency,
                             "cluster": row.get("cluster_id") or row.get("base_cluster") or "",
                             "url": row.get("suggested_url") or ""})
        break
    return rows


def load_positions(project_root: pathlib.Path, cfg: dict[str, Any]) -> dict[str, float]:
    db_rel = nested_get(cfg, "data_store.path", "seo/seo.db") or "seo/seo.db"
    db_path = project_root / db_rel
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT query, MIN(position) FROM positions WHERE position > 0 GROUP BY query").fetchall()
        conn.close()
    except sqlite3.Error:
        return {}
    return {" ".join(str(query).lower().split()): float(position) for query, position in rows if position}


def scenario_clicks(core: list[dict[str, Any]], positions: dict[str, float],
                    curve: dict[int, float], scenario: str) -> tuple[float, list[dict[str, Any]]]:
    total = 0.0
    per_cluster: dict[str, float] = {}
    for row in core:
        position = positions.get(row["keyword"], UNRANKED_POSITION)
        if scenario == "target_top10":
            position = min(position, 8.0)
        elif scenario == "target_top3":
            position = min(position, 3.0)
        clicks = row["frequency"] * ctr_for(position, curve)
        total += clicks
        per_cluster[row["cluster"] or "—"] = per_cluster.get(row["cluster"] or "—", 0.0) + clicks
    clusters = sorted(({"cluster": name, "clicks": round(value, 1)} for name, value in per_cluster.items()),
                      key=lambda item: item["clicks"], reverse=True)
    return total, clusters


def build_report(project_root: pathlib.Path, cfg: dict[str, Any]) -> dict[str, Any]:
    curve = load_ctr_curve(cfg)
    core = load_core(project_root)
    positions = load_positions(project_root, cfg)
    conversion = float(nested_get(cfg, "kpi.lead_conversion_rate", 0.02) or 0.02)
    months = max(1, int(nested_get(cfg, "kpi.months_to_target", 6) or 6))

    scenarios: dict[str, Any] = {}
    cluster_upside: list[dict[str, Any]] = []
    current_total = 0.0
    for scenario in ("current", "target_top10", "target_top3"):
        total, clusters = scenario_clicks(core, positions, curve, scenario)
        scenarios[scenario] = {
            "monthly_clicks": round(total),
            "monthly_clicks_range": [round(total * BOUNDS[0]), round(total * BOUNDS[1])],
            "monthly_leads": round(total * conversion, 1),
            "top_clusters": clusters[:10],
        }
        if scenario == "current":
            current_total = total
            current_clusters = {item["cluster"]: item["clicks"] for item in clusters}
        elif scenario == "target_top10":
            for item in clusters:
                upside = item["clicks"] - current_clusters.get(item["cluster"], 0.0)
                if upside > 0:
                    cluster_upside.append({"cluster": item["cluster"], "upside_clicks": round(upside, 1)})

    cluster_upside.sort(key=lambda item: item["upside_clicks"], reverse=True)
    target_total = scenarios["target_top10"]["monthly_clicks"]
    start = dt.date.today().replace(day=1)
    ramp = []
    for month_index in range(1, months + 1):
        month = (start.month - 1 + month_index) % 12 + 1
        year = start.year + (start.month - 1 + month_index) // 12
        share = month_index / months
        ramp.append({"month": f"{year:04d}-{month:02d}",
                     "planned_clicks": round(current_total + (target_total - current_total) * share)})

    ranked = sum(1 for row in core if row["keyword"] in positions)
    return {
        "audit_id": "seo_forecast",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "assumptions": {
            "model": "clicks = monthly_frequency × CTR(position); no seasonality, no SERP-feature adjustments",
            "ctr_curve": {str(key): value for key, value in sorted(curve.items())},
            "ctr_11_20": CTR_11_20,
            "ctr_beyond_20": CTR_BEYOND,
            "unranked_position": UNRANKED_POSITION,
            "bounds_multipliers": list(BOUNDS),
            "lead_conversion_rate": conversion,
            "months_to_target": months,
        },
        "inputs": {
            "keywords": len(core),
            "keywords_with_frequency": sum(1 for row in core if row["frequency"]),
            "keywords_ranked": ranked,
            "positions_tracked": len(positions),
        },
        "scenarios": scenarios,
        "cluster_upside_top10": cluster_upside[:10],
        "monthly_ramp_to_top10": ramp,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SEO Forecast",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Inputs: {report['inputs']['keywords']} keywords"
        f" ({report['inputs']['keywords_ranked']} ranked, {report['inputs']['positions_tracked']} tracked positions)",
        "",
        "## Scenarios (monthly)",
        "",
        "| Scenario | Clicks | Range | Leads |",
        "|---|---:|---|---:|",
    ]
    for name, data in report["scenarios"].items():
        lines.append(f"| {name} | {data['monthly_clicks']} | {data['monthly_clicks_range'][0]}–"
                     f"{data['monthly_clicks_range'][1]} | {data['monthly_leads']} |")
    lines.extend(["", "## Biggest upside clusters (to top-10)", ""])
    for item in report["cluster_upside_top10"]:
        lines.append(f"- {item['cluster']}: +{item['upside_clicks']} clicks/mo")
    lines.extend(["", "## Ramp to top-10 target", "", "| Month | Planned clicks |", "|---|---:|"])
    for row in report["monthly_ramp_to_top10"]:
        lines.append(f"| {row['month']} | {row['planned_clicks']} |")
    lines.extend(["", "## Assumptions", ""])
    for key, value in report["assumptions"].items():
        if key != "ctr_curve":
            lines.append(f"- {key}: {value}")
    lines.append("- CTR curve (pos → CTR): "
                 + ", ".join(f"{k}:{v}" for k, v in report["assumptions"]["ctr_curve"].items()))
    return "\n".join(lines) + "\n"


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "strategy"
    return {
        "markdown": base / "seo-forecast.md",
        "json": base / "seo-forecast.json",
        "latest_markdown": base / "latest-seo-forecast.md",
        "latest_json": base / "latest-seo-forecast.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write seo/strategy/seo-forecast.* artifacts")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("seo-forecast", project_root, cfg)

    report = build_report(project_root, cfg)
    if not report["inputs"]["keywords"]:
        print("No semantic core found (seo/research-package/semantic-core*.csv) — forecast is empty.",
              file=sys.stderr)
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
