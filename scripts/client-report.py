#!/usr/bin/env python3
"""Assemble a white-label client report from existing project artifacts (offline).

Pulls whatever exists — KPI contract, forecast, budget mix, content sync,
ads analytics, positions from seo.db — and renders a client-facing monthly
report in two formats: markdown and a self-contained HTML (inline CSS, no
external resources, print-to-PDF friendly). Sections without data are omitted
instead of showing empty tables.

Branding comes from the `agency` config section (name, contact, accent color,
footer note); the client name is the project name. Nothing is sent anywhere —
the report is a local file you review and share yourself.

Output: seo/reports/client-report-<YYYY-MM>.md/.html (+latest aliases) with --write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import sqlite3
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("client-report")

DEFAULT_ACCENT = "#0B57D0"


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def positions_summary(project_root: pathlib.Path, cfg: dict[str, Any]) -> dict[str, Any]:
    db_rel = nested_get(cfg, "data_store.path", "seo/seo.db") or "seo/seo.db"
    db_path = project_root / db_rel
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(db_path)
        dates = [row[0] for row in conn.execute(
            "SELECT DISTINCT snapshot_date FROM positions WHERE snapshot_date != '' ORDER BY snapshot_date"
        )]
        if not dates:
            conn.close()
            return {}
        latest = dates[-1]
        previous = dates[-2] if len(dates) > 1 else None

        def snapshot(date: str) -> dict[str, Any]:
            top10 = conn.execute(
                "SELECT COUNT(DISTINCT query) FROM positions WHERE snapshot_date=? AND position>0 AND position<=10",
                (date,)).fetchone()[0]
            top3 = conn.execute(
                "SELECT COUNT(DISTINCT query) FROM positions WHERE snapshot_date=? AND position>0 AND position<=3",
                (date,)).fetchone()[0]
            clicks = conn.execute(
                "SELECT COALESCE(SUM(clicks),0) FROM positions WHERE snapshot_date=?", (date,)).fetchone()[0]
            return {"date": date, "top10": int(top10), "top3": int(top3), "clicks": int(clicks or 0)}

        result = {"latest": snapshot(latest)}
        if previous:
            result["previous"] = snapshot(previous)
        conn.close()
        return result
    except sqlite3.Error:
        return {}


def collect(project_root: pathlib.Path, cfg: dict[str, Any]) -> dict[str, Any]:
    strategy = project_root / "seo" / "strategy"
    return {
        "kpi": load_json(strategy / "kpi-report.json"),
        "forecast": load_json(strategy / "seo-forecast.json"),
        "budget": load_json(strategy / "budget-mix.json"),
        "sync": load_json(project_root / "seo" / "content-mirror" / "sync-report.json"),
        "ads": load_json(project_root / "seo" / "ads" / "ads-analytics.json"),
        "positions": positions_summary(project_root, cfg),
    }


def build_report(project_root: pathlib.Path, cfg: dict[str, Any], period: str) -> dict[str, Any]:
    agency = cfg.get("agency") if isinstance(cfg.get("agency"), dict) else {}
    data = collect(project_root, cfg)
    sections: list[dict[str, Any]] = []

    positions = data["positions"]
    if positions:
        latest = positions["latest"]
        prev = positions.get("previous") or {}
        delta = {key: latest[key] - prev.get(key, latest[key]) for key in ("top10", "top3", "clicks")} if prev else {}
        sections.append({"id": "positions", "title": "Видимость в поиске", "data": {
            "latest": latest, "previous": prev, "delta": delta}})

    kpi = data["kpi"]
    if kpi.get("goals"):
        sections.append({"id": "kpi", "title": "KPI: план vs факт", "data": {
            "overall_status": kpi.get("overall_status"),
            "month": (kpi.get("contract") or {}).get("month"),
            "goals": kpi["goals"],
            "actions": kpi.get("corrective_actions") or []}})

    sync = data["sync"]
    if sync.get("counts"):
        sections.append({"id": "content", "title": "Контент за период", "data": sync["counts"]})

    ads = data["ads"]
    if (ads.get("summary") or {}).get("campaigns"):
        sections.append({"id": "ads", "title": "Платная реклама", "data": {
            "total_cost": ads["summary"].get("total_cost"),
            "total_conversions": ads["summary"].get("total_conversions"),
            "campaigns": (ads.get("campaigns") or [])[:8]}})

    forecast = data["forecast"]
    if forecast.get("scenarios"):
        sections.append({"id": "forecast", "title": "Прогноз и потенциал", "data": {
            "scenarios": forecast["scenarios"],
            "upside": (forecast.get("cluster_upside_top10") or [])[:5]}})

    budget = data["budget"]
    if budget.get("selected_lots"):
        sections.append({"id": "budget", "title": "Рекомендуемый бюджет-микс", "data": budget["mix"]})

    return {
        "audit_id": "client_report",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "period": period,
        "client": (cfg.get("project") or {}).get("name") or project_root.name,
        "domain": (cfg.get("project") or {}).get("domain") or "",
        "agency": {
            "name": agency.get("name") or "",
            "contact": agency.get("contact") or "",
            "accent_color": agency.get("accent_color") or DEFAULT_ACCENT,
            "footer_note": agency.get("footer_note") or "",
        },
        "sections": sections,
    }


def render_markdown(report: dict[str, Any]) -> str:
    agency = report["agency"]
    lines = [
        f"# Отчёт по продвижению — {report['client']}",
        "",
        f"- Период: {report['period']} · подготовлено: {report['generated_at'][:10]}",
        f"- Сайт: {report['domain']}",
    ]
    if agency["name"]:
        lines.append(f"- Агентство: {agency['name']}" + (f" · {agency['contact']}" if agency["contact"] else ""))
    for section in report["sections"]:
        lines.extend(["", f"## {section['title']}", ""])
        data = section["data"]
        if section["id"] == "positions":
            latest, delta = data["latest"], data.get("delta") or {}
            def fmt(key): return f"{latest[key]}" + (f" ({delta[key]:+d})" if delta else "")
            lines.append(f"- Запросов в топ-10: **{fmt('top10')}** · в топ-3: **{fmt('top3')}**"
                         f" · клики за срез: **{fmt('clicks')}** (срез {latest['date']})")
        elif section["id"] == "kpi":
            lines.append(f"- Статус месяца {data['month']}: **{data['overall_status']}**")
            lines.extend(["", "| Цель | План | Факт | Δ% | Статус |", "|---|---:|---:|---:|---|"])
            for row in data["goals"]:
                lines.append(f"| {row['goal']} | {row['plan_this_month']} | {row['fact']}"
                             f" | {row['delta_pct']} | {row['status']} |")
            if data["actions"]:
                lines.extend(["", "Что делаем для выправления:"])
                lines.extend(f"- {action}" for action in data["actions"][:5])
        elif section["id"] == "content":
            lines.append(f"- Страниц в зеркале: {data['mirrored']} · новых: {data['new']}"
                         f" · обновлено на сайте: {data['changed_on_site']}")
        elif section["id"] == "ads":
            lines.append(f"- Расход: {data['total_cost']} · конверсий: {data['total_conversions']}")
            for campaign in data["campaigns"][:5]:
                lines.append(f"  - {campaign['name'] or campaign['campaign_id']}: {campaign['cost']}"
                             f" · CPA {campaign['cpa'] if campaign['cpa'] is not None else '—'}")
        elif section["id"] == "forecast":
            for name, scenario in data["scenarios"].items():
                lines.append(f"- {name}: {scenario['monthly_clicks']} кликов/мес"
                             f" (~{scenario['monthly_leads']} лидов)")
            if data["upside"]:
                lines.append("- Наибольший потенциал: "
                             + ", ".join(f"{item['cluster']} (+{item['upside_clicks']})" for item in data["upside"]))
        elif section["id"] == "budget":
            lines.append(f"- SEO {data['seo_share_pct']}% / PPC {data['ppc_share_pct']}%"
                         f" → ожидание ~{data['expected_monthly_leads']} лидов/мес")
    if not report["sections"]:
        lines.extend(["", "_Данных за период пока нет — запустите forecast/kpi/sync/db-sync._"])
    if agency["footer_note"]:
        lines.extend(["", "---", "", agency["footer_note"]])
    return "\n".join(lines) + "\n"


def inline_html(text: str) -> str:
    """Escape + minimal markdown inline: **bold**."""
    escaped = html.escape(text)
    while "**" in escaped:
        escaped = escaped.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
    return escaped


def render_html(report: dict[str, Any], markdown_body: str) -> str:
    accent = html.escape(report["agency"]["accent_color"])
    out: list[str] = []
    lines = markdown_body.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            out.append("<table>")
            header_done = False
            for raw in table_lines:
                cells = [cell.strip() for cell in raw.strip("|").split("|")]
                if set("".join(cells)) <= {"-", ":", " "}:
                    continue
                tag = "td" if header_done else "th"
                header_done = True
                out.append("<tr>" + "".join(f"<{tag}>{inline_html(cell)}</{tag}>" for cell in cells) + "</tr>")
            out.append("</table>")
            continue
        if line.startswith("- "):
            out.append("<ul>")
            while index < len(lines) and lines[index].lstrip().startswith("- "):
                out.append(f"<li>{inline_html(lines[index].lstrip()[2:])}</li>")
                index += 1
            out.append("</ul>")
            continue
        if line.startswith("# "):
            out.append(f"<h1>{inline_html(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline_html(line[3:])}</h2>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{inline_html(line)}</p>")
        index += 1
    body = "\n".join(out)
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>{html.escape(report['client'])} — отчёт {html.escape(report['period'])}</title>
<style>
body{{font-family:-apple-system,'Segoe UI',Roboto,sans-serif;max-width:860px;margin:2rem auto;padding:0 1.5rem;color:#1a1a1a;line-height:1.55}}
h1{{color:{accent};border-bottom:3px solid {accent};padding-bottom:.4rem}}
h2{{color:{accent};margin-top:2rem}}
table{{border-collapse:collapse;width:100%;margin:.7rem 0}}
td,th{{border:1px solid #ddd;padding:.45rem .7rem;text-align:left;font-size:.95rem}}
li{{margin:.25rem 0}} strong{{color:{accent}}}
hr{{border:none;border-top:1px solid #ddd;margin:2rem 0}}
@media print{{body{{margin:0;max-width:none}}}}
</style></head><body>
{body}
</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--period", default=dt.date.today().strftime("%Y-%m"), help="Report period label (YYYY-MM)")
    parser.add_argument("--write", action="store_true", help="Write seo/reports/client-report-<period>.md/.html")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("client-report", project_root, cfg)

    report = build_report(project_root, cfg, args.period)
    markdown_body = render_markdown(report)
    if args.write:
        base = project_root / "seo" / "reports"
        write_text(base / f"client-report-{args.period}.md", markdown_body)
        write_text(base / f"client-report-{args.period}.html", render_html(report, markdown_body))
        write_text(base / "latest-client-report.md", markdown_body)
        write_text(base / "latest-client-report.html", render_html(report, markdown_body))
        log.info("client report written for %s (%s sections)", args.period, len(report["sections"]))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(markdown_body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
