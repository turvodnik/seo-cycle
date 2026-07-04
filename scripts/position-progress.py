#!/usr/bin/env python3
"""Track ranking progress across position snapshots — per project and portfolio-wide.

Answers «стало ли лучше после запусков»: compares the latest positions
snapshot in seo.db against the previous and the first one — top-3/10/30
buckets, average position, movers (improved/declined/new/lost queries) —
and folds in a quality-loops digest (attempts spent, findings resolved)
so content-quality progress is visible next to ranking progress.

Data source: the `positions` table filled by db-sync.py from monitoring
snapshots. Two snapshots minimum for deltas; one snapshot still gives the
current visibility picture.

Usage:
  python3 scripts/position-progress.py                     # markdown to stdout
  python3 scripts/position-progress.py --write --html      # seo/reports/position-progress.{md,json,html}
  python3 scripts/position-progress.py --engine yandex --limit-movers 15
  python3 scripts/position-progress.py --global            # portfolio over config/projects-registry.yaml
  python3 scripts/position-progress.py --format json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, write_text
from seo_cycle_core.html_report import bar, html_page, markdown_to_html_body
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("position-progress")

DEFAULT_REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "config" / "projects-registry.yaml"
GLOBAL_REPORTS_DIR = pathlib.Path.home() / ".seo-cycle" / "reports"


def db_path_for(project_root: pathlib.Path, cfg: dict[str, Any]) -> pathlib.Path:
    return project_root / (nested_get(cfg, "data_store.path", "seo/seo.db") or "seo/seo.db")


def snapshot_dates(conn: sqlite3.Connection, engine: str | None) -> list[str]:
    query = "SELECT DISTINCT snapshot_date FROM positions WHERE snapshot_date != ''"
    params: tuple[Any, ...] = ()
    if engine:
        query += " AND engine = ?"
        params = (engine,)
    return [row[0] for row in conn.execute(query + " ORDER BY snapshot_date", params)]


def snapshot_metrics(conn: sqlite3.Connection, date: str, engine: str | None) -> dict[str, Any]:
    where = "snapshot_date = ?"
    params: list[Any] = [date]
    if engine:
        where += " AND engine = ?"
        params.append(engine)
    row = conn.execute(
        f"""SELECT COUNT(DISTINCT query),
                   COUNT(DISTINCT CASE WHEN position > 0 AND position <= 3 THEN query END),
                   COUNT(DISTINCT CASE WHEN position > 0 AND position <= 10 THEN query END),
                   COUNT(DISTINCT CASE WHEN position > 0 AND position <= 30 THEN query END),
                   AVG(CASE WHEN position > 0 THEN position END),
                   COALESCE(SUM(clicks), 0), COALESCE(SUM(impressions), 0)
            FROM positions WHERE {where}""",
        params,
    ).fetchone()
    return {
        "date": date,
        "queries": int(row[0]),
        "top3": int(row[1]),
        "top10": int(row[2]),
        "top30": int(row[3]),
        "avg_position": round(row[4], 1) if row[4] is not None else None,
        "clicks": int(row[5]),
        "impressions": int(row[6]),
    }


def query_positions(conn: sqlite3.Connection, date: str, engine: str | None) -> dict[str, float]:
    where = "snapshot_date = ? AND position > 0"
    params: list[Any] = [date]
    if engine:
        where += " AND engine = ?"
        params.append(engine)
    result: dict[str, float] = {}
    for query, position in conn.execute(f"SELECT query, MIN(position) FROM positions WHERE {where} GROUP BY query", params):
        result[str(query)] = float(position)
    return result


def movers(conn: sqlite3.Connection, prev_date: str, latest_date: str, engine: str | None,
           limit: int) -> dict[str, list[dict[str, Any]]]:
    prev = query_positions(conn, prev_date, engine)
    curr = query_positions(conn, latest_date, engine)
    improved, declined = [], []
    for query in prev.keys() & curr.keys():
        delta = prev[query] - curr[query]  # positive = moved up
        entry = {"query": query, "from": prev[query], "to": curr[query], "delta": round(delta, 1)}
        if delta >= 1:
            improved.append(entry)
        elif delta <= -1:
            declined.append(entry)
    new = [{"query": query, "to": curr[query]} for query in sorted(curr.keys() - prev.keys())]
    lost = [{"query": query, "from": prev[query]} for query in sorted(prev.keys() - curr.keys())]
    improved.sort(key=lambda item: -item["delta"])
    declined.sort(key=lambda item: item["delta"])
    new.sort(key=lambda item: item["to"])
    return {
        "improved": improved[:limit],
        "declined": declined[:limit],
        "new": new[:limit],
        "lost": lost[:limit],
        "counts": {"improved": len(improved), "declined": len(declined), "new": len(new), "lost": len(lost)},
    }


def loops_digest(project_root: pathlib.Path) -> dict[str, Any]:
    loops_dir = project_root / "seo" / "loops"
    digest = {"loops": 0, "passed": 0, "escalated": 0, "attempts": 0, "findings_resolved": 0,
              "findings_open": 0}
    for path in sorted(loops_dir.glob("*.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        attempts = state.get("attempts") or []
        digest["loops"] += 1
        digest["attempts"] += len(attempts)
        if state.get("status") == "passed":
            digest["passed"] += 1
        elif state.get("status") == "escalated":
            digest["escalated"] += 1
        for attempt in attempts:
            digest["findings_resolved"] += len(((attempt.get("delta") or {}).get("resolved")) or [])
        if attempts:
            digest["findings_open"] += len(((attempts[-1].get("check") or {}).get("findings")) or [])
    return digest


def delta_block(latest: dict[str, Any], reference: dict[str, Any] | None) -> dict[str, Any]:
    if not reference:
        return {}
    delta: dict[str, Any] = {}
    for key in ("queries", "top3", "top10", "top30", "clicks", "impressions"):
        delta[key] = latest[key] - reference[key]
    if latest.get("avg_position") is not None and reference.get("avg_position") is not None:
        delta["avg_position"] = round(latest["avg_position"] - reference["avg_position"], 1)
    return delta


def collect_project(project_root: pathlib.Path, cfg: dict[str, Any], *, engine: str | None,
                    limit_movers: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "audit_id": "position_progress",
        "project": (cfg.get("project") or {}).get("name") or project_root.name,
        "domain": (cfg.get("project") or {}).get("domain") or "",
        "engine": engine or "all",
        "snapshots": [],
        "loops": loops_digest(project_root),
    }
    db_path = db_path_for(project_root, cfg)
    if not db_path.exists():
        report["status"] = "no_db"
        return report
    try:
        conn = sqlite3.connect(db_path)
        dates = snapshot_dates(conn, engine)
        if not dates:
            conn.close()
            report["status"] = "no_snapshots"
            return report
        trend = [snapshot_metrics(conn, date, engine) for date in dates[-12:]]
        latest = trend[-1]
        previous = trend[-2] if len(trend) > 1 else None
        first = trend[0] if len(trend) > 1 else None
        report.update({
            "status": "ok",
            "snapshots": trend,
            "latest": latest,
            "previous": previous,
            "first": first,
            "delta_vs_previous": delta_block(latest, previous),
            "delta_vs_first": delta_block(latest, first),
        })
        if previous:
            report["movers"] = movers(conn, previous["date"], latest["date"], engine, limit_movers)
        conn.close()
    except sqlite3.Error as exc:
        report["status"] = f"db_error: {exc}"
    return report


def fmt_delta(value: Any, invert: bool = False) -> str:
    if value in (None, ""):
        return ""
    good = value < 0 if invert else value > 0
    sign = f"{value:+g}"
    return f" ({sign}{'↑' if good else '↓' if value else ''})"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Прогресс позиций — {report['project']}", ""]
    if report.get("status") != "ok":
        hint = {"no_db": "нет seo.db — запустите `seo-cycle db`",
                "no_snapshots": "в seo.db нет снапшотов positions — добавьте мониторинг-снапшот и `seo-cycle db`"}
        lines.append(f"_Данных нет: {hint.get(report.get('status'), report.get('status'))}_")
        return "\n".join(lines) + "\n"
    latest, prev_delta, first_delta = report["latest"], report.get("delta_vs_previous") or {}, report.get("delta_vs_first") or {}
    lines.extend([
        f"- Срез: {latest['date']} · поисковик: {report['engine']} · запросов отслеживается: {latest['queries']}",
        f"- **Топ-3: {latest['top3']}{fmt_delta(prev_delta.get('top3'))}** · "
        f"**Топ-10: {latest['top10']}{fmt_delta(prev_delta.get('top10'))}** · "
        f"Топ-30: {latest['top30']}{fmt_delta(prev_delta.get('top30'))}",
        f"- Средняя позиция: {latest['avg_position']}{fmt_delta(prev_delta.get('avg_position'), invert=True)}"
        f" · клики: {latest['clicks']}{fmt_delta(prev_delta.get('clicks'))}"
        f" · показы: {latest['impressions']}{fmt_delta(prev_delta.get('impressions'))}",
    ])
    if first_delta:
        lines.append(f"- С первого среза ({report['first']['date']}): топ-10 {fmt_delta(first_delta.get('top10')) or '+0'},"
                     f" клики {fmt_delta(first_delta.get('clicks')) or '+0'}")
    if len(report.get("snapshots", [])) > 1:
        lines.extend(["", "## Динамика по срезам", "", "| Срез | Топ-3 | Топ-10 | Топ-30 | Ср. позиция | Клики |", "|---|---:|---:|---:|---:|---:|"])
        for snap in report["snapshots"]:
            lines.append(f"| {snap['date']} | {snap['top3']} | {snap['top10']} | {snap['top30']}"
                         f" | {snap['avg_position'] or '—'} | {snap['clicks']} |")
    for key, title, arrow in (("improved", "Выросли", "↑"), ("declined", "Просели", "↓")):
        rows = (report.get("movers") or {}).get(key) or []
        if rows:
            lines.extend(["", f"## {title} ({(report['movers']['counts'][key])})", ""])
            lines.extend(f"- {arrow} «{row['query']}»: {row['from']:g} → {row['to']:g}" for row in rows)
    movers_data = report.get("movers") or {}
    if movers_data.get("new") or movers_data.get("lost"):
        lines.extend(["", f"## Новые в выдаче: {movers_data['counts']['new']} · выпали: {movers_data['counts']['lost']}", ""])
        lines.extend(f"- new «{row['query']}» → {row['to']:g}" for row in movers_data.get("new", [])[:5])
        lines.extend(f"- lost «{row['query']}» (была {row['from']:g})" for row in movers_data.get("lost", [])[:5])
    loops = report.get("loops") or {}
    if loops.get("loops"):
        lines.extend(["", "## Циклы качества", "",
                      f"- Прогонов: {loops['loops']} (passed {loops['passed']}, эскалаций {loops['escalated']})"
                      f" · попыток всего: {loops['attempts']}",
                      f"- Findings устранено циклами: **{loops['findings_resolved']}** · осталось открытых: {loops['findings_open']}"])
    return "\n".join(lines) + "\n"


def render_html_report(report: dict[str, Any], markdown_body: str) -> str:
    extra = ""
    if report.get("status") == "ok" and len(report.get("snapshots", [])) > 1:
        max_top10 = max((snap["top10"] for snap in report["snapshots"]), default=0) or 1
        bars = "".join(
            bar(snap["top10"], max_top10, label=f"{snap['date']}: топ-10 = {snap['top10']}")
            for snap in report["snapshots"]
        )
        extra = f"<h2>Топ-10 по срезам</h2>{bars}"
    return html_page(
        f"Прогресс позиций — {report['project']}",
        markdown_to_html_body(markdown_body) + extra,
    )


# ----- Portfolio (--global) -------------------------------------------------

def load_registry(path: pathlib.Path) -> list[dict[str, Any]]:
    projects = (load_yaml(path).get("projects") or []) if path.exists() else []
    return [item for item in projects if isinstance(item, dict) and item.get("path")]


def collect_portfolio(registry_path: pathlib.Path, *, engine: str | None, limit_movers: int) -> dict[str, Any]:
    projects = []
    totals = {"projects": 0, "queries": 0, "top3": 0, "top10": 0, "clicks": 0,
              "delta_top10": 0, "delta_clicks": 0, "findings_resolved": 0}
    for item in load_registry(registry_path):
        root = pathlib.Path(str(item["path"])).expanduser()
        cfg_path = find_config(root)
        if not cfg_path:
            projects.append({"project": item.get("name") or root.name, "status": "no_config"})
            continue
        report = collect_project(project_root_for(cfg_path), load_yaml(cfg_path),
                                 engine=engine, limit_movers=limit_movers)
        if item.get("name"):
            report["project"] = str(item["name"])
        report["registry_status"] = item.get("status", "active")
        projects.append(report)
        if report.get("status") == "ok":
            totals["projects"] += 1
            totals["queries"] += report["latest"]["queries"]
            totals["top3"] += report["latest"]["top3"]
            totals["top10"] += report["latest"]["top10"]
            totals["clicks"] += report["latest"]["clicks"]
            totals["delta_top10"] += (report.get("delta_vs_previous") or {}).get("top10", 0) or 0
            totals["delta_clicks"] += (report.get("delta_vs_previous") or {}).get("clicks", 0) or 0
        totals["findings_resolved"] += (report.get("loops") or {}).get("findings_resolved", 0)
    return {"audit_id": "portfolio_progress", "engine": engine or "all",
            "projects": projects, "totals": totals}


def render_portfolio_markdown(portfolio: dict[str, Any]) -> str:
    totals = portfolio["totals"]
    lines = ["# Портфель: прогресс позиций по всем проектам", "",
             f"- Проектов с данными: {totals['projects']} · запросов: {totals['queries']}"
             f" · суммарно топ-10: **{totals['top10']}{fmt_delta(totals['delta_top10'])}**"
             f" · клики: {totals['clicks']}{fmt_delta(totals['delta_clicks'])}",
             f"- Findings устранено циклами качества: {totals['findings_resolved']}",
             "", "| Проект | Срез | Топ-3 | Топ-10 | Клики | Δ топ-10 | Циклы (resolved) |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for report in portfolio["projects"]:
        if report.get("status") != "ok":
            lines.append(f"| {report.get('project', '?')} | — | — | — | — | — | {report.get('status')} |")
            continue
        latest = report["latest"]
        delta = (report.get("delta_vs_previous") or {}).get("top10")
        loops = report.get("loops") or {}
        lines.append(f"| {report['project']} | {latest['date']} | {latest['top3']} | {latest['top10']}"
                     f" | {latest['clicks']} | {f'{delta:+d}' if isinstance(delta, int) else '—'}"
                     f" | {loops.get('findings_resolved', 0)} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--engine", help="Filter one engine (yandex|google|...)")
    parser.add_argument("--limit-movers", type=int, default=10)
    parser.add_argument("--global", dest="portfolio", action="store_true",
                        help="Aggregate all active projects from projects-registry.yaml")
    parser.add_argument("--registry", help="Registry path override (with --global)")
    parser.add_argument("--write", action="store_true", help="Write seo/reports/position-progress.{md,json}")
    parser.add_argument("--html", action="store_true", help="Also write .html (with --write)")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    if args.portfolio:
        registry = pathlib.Path(args.registry).expanduser() if args.registry else DEFAULT_REGISTRY
        portfolio = collect_portfolio(registry, engine=args.engine, limit_movers=args.limit_movers)
        markdown = render_portfolio_markdown(portfolio)
        if args.write:
            GLOBAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            write_text(GLOBAL_REPORTS_DIR / "portfolio-progress.md", markdown)
            write_text(GLOBAL_REPORTS_DIR / "portfolio-progress.json",
                       json.dumps(portfolio, ensure_ascii=False, indent=2) + "\n")
            if args.html:
                write_text(GLOBAL_REPORTS_DIR / "portfolio-progress.html",
                           html_page("Портфель — прогресс позиций", markdown_to_html_body(markdown)))
            print(f"✓ {GLOBAL_REPORTS_DIR}/portfolio-progress.md", file=sys.stderr)
        print(json.dumps(portfolio, ensure_ascii=False, indent=2) if args.format == "json" else markdown, end="" if args.format == "md" else "\n")
        return 0

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    global log
    log = setup_logging("position-progress", project_root, cfg)

    report = collect_project(project_root, cfg, engine=args.engine, limit_movers=args.limit_movers)
    markdown = render_markdown(report)
    if args.write:
        reports_dir = project_root / "seo" / "reports"
        write_text(reports_dir / "position-progress.md", markdown)
        write_text(reports_dir / "position-progress.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        if args.html:
            write_text(reports_dir / "position-progress.html", render_html_report(report, markdown))
        log.info("position-progress written status=%s", report.get("status"))
        print(f"✓ {reports_dir}/position-progress.md" + (" + .html" if args.html else ""), file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else markdown, end="" if args.format == "md" else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
