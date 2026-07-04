#!/usr/bin/env python3
"""Track brand citations in AI answers over time (the GEO scoreboard).

Appends observations «упомянул ли AI-движок бренд по запросу» into
seo/geo/citation-log.jsonl and renders the trend: citation share per engine
per month. Observations come from ai-brand-audit runs (--import-audit) or
manual checks (--record).

Usage:
  python3 scripts/geo-citation-log.py --record --engine perplexity \
      --query "лучшая вагонка" --cited --url https://site.ru/vagonka
  python3 scripts/geo-citation-log.py --record --engine yandex_alice --query "..." --not-cited
  python3 scripts/geo-citation-log.py --import-audit seo/geo/ai-brand-audit.json
  python3 scripts/geo-citation-log.py            # тренд по журналу
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, project_root_for
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("geo-citation-log")


def log_path(project_root: pathlib.Path) -> pathlib.Path:
    return project_root / "seo" / "geo" / "citation-log.jsonl"


def append_entries(project_root: pathlib.Path, entries: list[dict[str, Any]]) -> None:
    path = log_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_entries(project_root: pathlib.Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in
                log_path(project_root).read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def import_audit(path: pathlib.Path, when: str) -> list[dict[str, Any]]:
    """ai-brand-audit JSON → citation observations (best effort over known shapes)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("results") or data.get("queries") or data.get("checks") or []
    entries = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        query = row.get("query") or row.get("prompt") or ""
        engine = row.get("engine") or row.get("platform") or "unknown"
        cited = bool(row.get("cited") or row.get("brand_mentioned") or row.get("mentioned"))
        if query:
            entries.append({"at": when, "engine": str(engine), "query": str(query),
                            "cited": cited, "url": row.get("url") or "", "source": path.name})
    return entries


def trend(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_month: dict[str, dict[str, list[bool]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for entry in entries:
        month = str(entry.get("at", ""))[:7]
        if month:
            by_month[month][str(entry.get("engine", "?"))].append(bool(entry.get("cited")))
    months = []
    for month in sorted(by_month):
        engines = {}
        for engine, flags in sorted(by_month[month].items()):
            engines[engine] = {"checks": len(flags), "cited": sum(flags),
                               "share": round(sum(flags) / len(flags), 2)}
        months.append({"month": month, "engines": engines})
    return {"observations": len(entries), "months": months}


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Цитируемость бренда в AI-ответах", "",
             f"- Наблюдений в журнале: {report['observations']}", ""]
    if not report["months"]:
        lines.append("_Журнал пуст: добавьте наблюдения через --record или --import-audit._")
        return "\n".join(lines) + "\n"
    lines.extend(["| Месяц | Движок | Проверок | Цитирований | Доля |", "|---|---|---:|---:|---:|"])
    for month in report["months"]:
        for engine, stats in month["engines"].items():
            lines.append(f"| {month['month']} | {engine} | {stats['checks']}"
                         f" | {stats['cited']} | {int(stats['share'] * 100)}% |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--record", action="store_true", help="Append one manual observation")
    parser.add_argument("--engine", help="perplexity|chatgpt|ai_overview|yandex_alice|copilot|...")
    parser.add_argument("--query")
    parser.add_argument("--cited", dest="cited", action="store_true")
    parser.add_argument("--not-cited", dest="cited", action="store_false")
    parser.set_defaults(cited=None)
    parser.add_argument("--url", default="")
    parser.add_argument("--import-audit", help="Import observations from an ai-brand-audit JSON")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    cfg_path = find_config(pathlib.Path.cwd())
    if not cfg_path:
        print("ERROR: seo-cycle.yaml not found", file=sys.stderr)
        return 2
    project_root = project_root_for(cfg_path)
    now = dt.datetime.now().isoformat(timespec="seconds")

    if args.record:
        if not args.engine or not args.query or args.cited is None:
            print("ERROR: --record требует --engine, --query и --cited/--not-cited", file=sys.stderr)
            return 2
        append_entries(project_root, [{"at": now, "engine": args.engine, "query": args.query,
                                       "cited": args.cited, "url": args.url, "source": "manual"}])
        print("✓ записано", file=sys.stderr)
    if args.import_audit:
        entries = import_audit(pathlib.Path(args.import_audit).expanduser(), now)
        append_entries(project_root, entries)
        print(f"✓ импортировано наблюдений: {len(entries)}", file=sys.stderr)

    report = {"audit_id": "geo_citation_log", **trend(load_entries(project_root))}
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json"
          else render_markdown(report), end="" if args.format == "md" else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
