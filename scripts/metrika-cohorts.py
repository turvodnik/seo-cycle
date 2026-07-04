#!/usr/bin/env python3
"""Cohort analysis over Метрика Logs API visits (offline, TSV in — insight out).

Groups visitors by the week of their first visit in the dataset and tracks
each cohort forward: size, share who returned (>1 visit), share who reached
any goal, share that came from organic. Answers «качество трафика по
когортам растёт или падает?» without leaving the terminal.

Input: a visits TSV from metrika-logs-fetch.py (needs ym:s:clientID,
ym:s:date; ym:s:goalsID and ym:s:lastTrafficSource enrich the result).

Usage:
  python3 scripts/metrika-cohorts.py --input-file seo/analytics/raw/visits.tsv --write
  python3 scripts/metrika-cohorts.py            # найдёт свежий *.tsv в seo/analytics
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

from seo_cycle_core.config import find_config, load_yaml, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("metrika-cohorts")


def find_default_tsv(project_root: pathlib.Path) -> pathlib.Path | None:
    candidates = sorted(
        [*(project_root / "seo" / "analytics").rglob("*.tsv"),
         *(project_root / "seo" / "metrika").rglob("*.tsv")],
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    return candidates[0] if candidates else None


def week_of(date_text: str) -> str:
    try:
        day = dt.date.fromisoformat(date_text.strip())
    except ValueError:
        return ""
    monday = day - dt.timedelta(days=day.weekday())
    return monday.isoformat()


def build_cohorts(tsv_text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(tsv_text), delimiter="\t")
    fields = reader.fieldnames or []
    client_field = next((f for f in fields if f.endswith(":clientID")), None)
    date_field = next((f for f in fields if f.endswith(":date")), None)
    goals_field = next((f for f in fields if f.endswith(":goalsID")), None)
    source_field = next((f for f in fields if f.endswith(":lastTrafficSource")), None)
    if not client_field or not date_field:
        return {"error": f"TSV must contain clientID and date fields, got: {fields}"}

    clients: dict[str, dict[str, Any]] = {}
    total_rows = 0
    for row in reader:
        total_rows += 1
        client = row.get(client_field) or ""
        date = row.get(date_field) or ""
        if not client or not date:
            continue
        entry = clients.setdefault(client, {"visits": 0, "first": date, "goal": False, "organic": False})
        entry["visits"] += 1
        if date < entry["first"]:
            entry["first"] = date
        if goals_field and (row.get(goals_field) or "[]") not in ("[]", ""):
            entry["goal"] = True
        if source_field and row.get(source_field, "") == "organic":
            entry["organic"] = True

    cohorts: dict[str, dict[str, Any]] = {}
    for entry in clients.values():
        week = week_of(entry["first"])
        if not week:
            continue
        cohort = cohorts.setdefault(week, {"clients": 0, "returned": 0, "converted": 0, "organic": 0})
        cohort["clients"] += 1
        cohort["returned"] += 1 if entry["visits"] > 1 else 0
        cohort["converted"] += 1 if entry["goal"] else 0
        cohort["organic"] += 1 if entry["organic"] else 0

    rows = []
    for week in sorted(cohorts):
        cohort = cohorts[week]
        size = cohort["clients"] or 1
        rows.append({
            "cohort_week": week,
            "clients": cohort["clients"],
            "returned_share": round(cohort["returned"] / size, 2),
            "converted_share": round(cohort["converted"] / size, 2),
            "organic_share": round(cohort["organic"] / size, 2),
        })
    return {"rows_in_tsv": total_rows, "unique_clients": len(clients), "cohorts": rows,
            "has_goals": bool(goals_field), "has_source": bool(source_field)}


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Когорты по неделе первого визита", "",
             f"- Визитов в выгрузке: {report['rows_in_tsv']} · уникальных клиентов: {report['unique_clients']}",
             "", "| Когорта (нед.) | Клиентов | Вернулись | Конверсия | Органика |",
             "|---|---:|---:|---:|---:|"]
    for row in report["cohorts"]:
        lines.append(f"| {row['cohort_week']} | {row['clients']} | {int(row['returned_share'] * 100)}%"
                     f" | {int(row['converted_share'] * 100)}% | {int(row['organic_share'] * 100)}% |")
    if len(report["cohorts"]) >= 2:
        first, last = report["cohorts"][0], report["cohorts"][-1]
        trend = "растёт" if last["converted_share"] > first["converted_share"] else \
            "падает" if last["converted_share"] < first["converted_share"] else "стабильна"
        lines.extend(["", f"Конверсия по когортам {trend}: "
                      f"{int(first['converted_share'] * 100)}% → {int(last['converted_share'] * 100)}%"])
    if not report.get("has_goals"):
        lines.extend(["", "_В выгрузке нет ym:s:goalsID — конверсия недоступна; добавьте поле в fields._"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-file", help="Visits TSV (default: newest *.tsv in seo/analytics|seo/metrika)")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    cfg_path = find_config(pathlib.Path.cwd())
    project_root = project_root_for(cfg_path) if cfg_path else pathlib.Path.cwd()
    global log
    log = setup_logging("metrika-cohorts", project_root, load_yaml(cfg_path) if cfg_path else {})

    tsv_path = pathlib.Path(args.input_file).expanduser() if args.input_file else find_default_tsv(project_root)
    if not tsv_path or not tsv_path.exists():
        print("Нет visits TSV: запустите metrika-logs-fetch.py --live --write "
              "или передайте --input-file.", file=sys.stderr)
        return 0
    report = build_cohorts(tsv_path.read_text(encoding="utf-8"))
    if report.get("error"):
        print(f"ERROR: {report['error']}", file=sys.stderr)
        return 2
    report = {"audit_id": "metrika_cohorts", "input": str(tsv_path), **report}
    markdown = render_markdown(report)
    if args.write:
        base = project_root / "seo" / "analytics"
        write_text(base / "metrika-cohorts.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        write_text(base / "metrika-cohorts.md", markdown)
        print(f"✓ {base}/metrika-cohorts.md", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else markdown,
          end="" if args.format == "md" else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
