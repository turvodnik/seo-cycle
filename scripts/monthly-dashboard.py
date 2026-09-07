#!/usr/bin/env python3
"""
monthly-dashboard.py — генератор статус-дашборда для Step 10 automation.

Собирает данные из:
- keyword-queue.csv — глубина очереди, по статусам
- pending-approvals.md — все pending tickets
- 09-monitoring/*-snapshot.json — последний снапшот метрик
- seo/cycles/audit-*/01-audit.md — последний audit (если есть)
- seo/cycles/refresh-*/refresh-plan.md — последний refresh (если есть)
- seo/research/deindex/*.md — deindex кейсы (если есть)

Output: seo/monthly-dashboard.md — человекочитаемый отчёт.

Использование:
    cd <project-root>
    python3 monthly-dashboard.py                          # output: seo/monthly-dashboard.md
    python3 monthly-dashboard.py --output dashboard.md
    python3 monthly-dashboard.py --json                   # JSON для дальнейшей обработки

Cross-platform: pure Python 3, only optional yaml.
"""

from __future__ import annotations
import argparse, csv, json, pathlib, re, sys
from datetime import date, timedelta

from seo_cycle_core.config import require_config, require_section
from seo_cycle_core.monitoring import find_latest_snapshot as _find_latest_snapshot_file
from seo_cycle_core.monitoring import monitoring_dir

try:
    import yaml
except ImportError:
    yaml = None


# ----- Загрузчики --------------------------------------------------------

def load_queue(path: pathlib.Path) -> dict:
    if not path.exists():
        return {"total": 0, "by_status": {}, "by_cluster": {}, "rows": []}
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    by_status: dict[str, int] = {}
    by_cluster: dict[str, int] = {}
    for r in rows:
        s = r.get("status", "")
        by_status[s] = by_status.get(s, 0) + 1
        c = r.get("cluster", "") or "(none)"
        by_cluster[c] = by_cluster.get(c, 0) + 1
    return {"total": len(rows), "by_status": by_status, "by_cluster": by_cluster, "rows": rows}


def load_approvals(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    tickets = []
    for m in re.finditer(
        r"<!--\s*ticket\s+id:(?P<id>[a-f0-9]+)\s+"
        r"type:(?P<type>\w+)\s+"
        r"status:(?P<status>\w+)\s+"
        r"created:(?P<created>[\d-]+)"
        r"(?:\s+approved:(?P<approved>[\d-]+))?"
        r"(?:\s+by:(?P<by>[^\s]+))?"
        r"\s*-->",
        text,
        re.IGNORECASE,
    ):
        # Извлечь title строки из markdown
        m_title = re.search(rf"<!--[^>]+id:{m['id']}[^>]+-->\s*\n###\s+([^\n]+)", text)
        title = m_title.group(1).strip() if m_title else ""
        tickets.append({**m.groupdict(), "title": title})
    return tickets


def find_latest_snapshot_file(search_dirs: list[pathlib.Path]) -> pathlib.Path | None:
    """Newest snapshot across every candidate dir (v2 `seo/monitoring/`, v1
    fallback `seo/09-monitoring/`). Раскладка v2 кладёт дату ПОСЛЕ слова
    snapshot (`webmaster-snapshot-2026-09-01.json`) — маска `*-snapshot.json`
    её не находит (I-060). Ранжирование по дате-в-имени (не mtime — T-052 R1)
    и валидация имени файла (T-052, mask hardening: посторонний файл вроде
    `triggers-snapshot-<дата>.json` не проходит) — в `seo_cycle_core.monitoring`,
    общем для pulse.py (пишет) и doctor/status (тоже читают этот же список)."""
    return _find_latest_snapshot_file(search_dirs)


def load_latest_snapshot(search_dirs: list[pathlib.Path]) -> dict | None:
    latest = find_latest_snapshot_file(search_dirs)
    if latest is None:
        return None
    try:
        return {"path": str(latest), "data": json.loads(latest.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"⚠ snapshot найден, но не разобран: {latest} ({exc})", file=sys.stderr)
        return None


def load_latest_audit(cycles_dir: pathlib.Path) -> dict | None:
    if not cycles_dir.exists():
        return None
    audit_dirs = sorted(cycles_dir.glob("audit-*"))
    if not audit_dirs:
        return None
    latest = audit_dirs[-1]
    audit_md = latest / "01-audit.md"
    if not audit_md.exists():
        return None
    text = audit_md.read_text(encoding="utf-8")
    # Quick metrics из markdown
    p0_count = len(re.findall(r"## P0[- —]", text))
    p1_count = len(re.findall(r"## P1[- —]", text))
    return {
        "path": str(audit_md),
        "audit_date": latest.name.replace("audit-", ""),
        "p0_count": p0_count,
        "p1_count": p1_count,
    }


def load_latest_refresh(cycles_dir: pathlib.Path) -> dict | None:
    if not cycles_dir.exists():
        return None
    rdirs = sorted(cycles_dir.glob("refresh-*"))
    if not rdirs:
        return None
    latest = rdirs[-1]
    plan = latest / "refresh-plan.md"
    if not plan.exists():
        return None
    text = plan.read_text(encoding="utf-8")
    page_count = len(re.findall(r"^## Page \d+:", text, re.MULTILINE))
    return {
        "path": str(plan),
        "refresh_date": latest.name.replace("refresh-", ""),
        "page_count": page_count,
    }


def load_deindex_cases(deindex_dir: pathlib.Path) -> list[dict]:
    if not deindex_dir.exists():
        return []
    cases = []
    for md in sorted(deindex_dir.glob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
            # Frontmatter parse
            fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
            fm = {}
            if fm_match:
                for line in fm_match.group(1).splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        fm[k.strip()] = v.strip()
            cases.append({"file": str(md), **fm})
        except Exception:
            continue
    return cases


def load_publish_log(path: pathlib.Path, this_month_only: bool = True) -> list[dict]:
    """seo/publish-log.csv если ведётся."""
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if this_month_only:
        month_prefix = date.today().strftime("%Y-%m")
        rows = [r for r in rows if r.get("published_date", "").startswith(month_prefix)]
    return rows


# ----- Renderer ----------------------------------------------------------

def render_markdown(data: dict, project_name: str) -> str:
    today = date.today().isoformat()
    month_label = date.today().strftime("%B %Y")
    lines = [
        "---",
        f"dashboard_date: {today}",
        f"month: {month_label}",
        f"project: {project_name}",
        "tags: [dashboard, monthly-status]",
        "---",
        "",
        f"# Monthly Dashboard — {project_name} — {month_label}",
        "",
        f"_Сгенерировано: {today}_",
        "",
        "## TL;DR",
        "",
    ]

    # TL;DR
    queue = data["queue"]
    approved_count = queue["by_status"].get("approved", 0)
    pending_appr = len([t for t in data["approvals"] if t.get("status") == "pending"])
    published_this_month = len(data.get("published_log", []))

    lines.append(f"- 📝 Опубликовано в {month_label}: **{published_this_month}** постов")
    lines.append(f"- 🔑 Approved keywords в очереди: **{approved_count}** (готовы к публикации)")
    lines.append(f"- ⏸ Pending approval tickets: **{pending_appr}**")
    if data["audit"]:
        lines.append(f"- 🔧 Последний audit ({data['audit']['audit_date']}): "
                     f"**{data['audit']['p0_count']}** P0, **{data['audit']['p1_count']}** P1")
    if data["refresh"]:
        lines.append(f"- ♻️  Последний refresh plan ({data['refresh']['refresh_date']}): "
                     f"**{data['refresh']['page_count']}** страниц")
    deindex_pending = len([d for d in data["deindex_cases"] if d.get("rewrite_plan_status") == "pending_approval"])
    if deindex_pending:
        lines.append(f"- 🚨 Deindex кейсов на review: **{deindex_pending}**")
    lines.append("")

    # Pending approvals
    lines.append("## ⏸ Pending Approvals")
    lines.append("")
    pending = [t for t in data["approvals"] if t.get("status") == "pending"]
    if not pending:
        lines.append("_Нет pending tickets_ ✅")
    else:
        lines.append("| ID | Type | Title | Created |")
        lines.append("|---|---|---|---|")
        for t in pending:
            title = (t.get("title") or "")[:60]
            lines.append(f"| `{t['id']}` | {t['type']} | {title} | {t.get('created','')} |")
        lines.append("")
        lines.append("Approve: `seo-cycle run script approval-gate approve <id>`")
    lines.append("")

    # Keyword queue
    lines.append("## 🔑 Keyword Queue")
    lines.append("")
    if queue["total"] == 0:
        lines.append("_Очередь пуста — запусти seo-keyword-queue-manager_ ⚠️")
    else:
        lines.append(f"**Всего:** {queue['total']}")
        lines.append("")
        lines.append("| Status | Count |")
        lines.append("|---|---|")
        for status, count in sorted(queue["by_status"].items(), key=lambda x: -x[1]):
            lines.append(f"| {status} | {count} |")
        if queue["by_cluster"]:
            lines.append("")
            lines.append("**By cluster:**")
            for cluster, count in sorted(queue["by_cluster"].items(), key=lambda x: -x[1])[:10]:
                lines.append(f"- {cluster}: {count}")
    lines.append("")

    # Published this month
    lines.append(f"## 📝 Published в {month_label}")
    lines.append("")
    pub = data.get("published_log", [])
    if not pub:
        lines.append("_(нет публикаций в этом месяце или publish-log.csv не ведётся)_")
    else:
        lines.append("| Date | Keyword | URL |")
        lines.append("|---|---|---|")
        for r in pub[:20]:
            lines.append(f"| {r.get('published_date','')} | {r.get('keyword','')[:40]} | {r.get('url','')} |")
    lines.append("")

    # Last monitoring snapshot
    lines.append("## 📊 Последний Monitoring Snapshot")
    lines.append("")
    snap = data["latest_snapshot"]
    if not snap:
        searched = ", ".join(f"`{d}`" for d in data.get("monitoring_search_dirs", []))
        lines.append(f"_Snapshot не найден (искали: {searched}) — запусти Phase 9"
                     " (claude-seo:seo-google + yandex-seo-specialist)_ ⚠️")
    else:
        sd = snap["data"]
        period = sd.get("period", {})
        sources = ", ".join(s.get("source", "?") for s in sd.get("sources", []))
        lines.append(f"**Файл:** `{snap['path']}`")
        lines.append(f"**Период:** {period.get('start','?')} → {period.get('end','?')}")
        lines.append(f"**Sources:** {sources}")
        lines.append(f"**Queries:** {len(sd.get('queries', []))}, **Pages:** {len(sd.get('pages', []))}")
        cwv = sd.get("cwv", {})
        if cwv:
            status = cwv.get("status", "?")
            emoji = {"good":"🟢","needs_improvement":"🟡","poor":"🔴"}.get(status, "⚪")
            lines.append(f"**CWV:** {emoji} {status} (LCP={cwv.get('lcp_p75','?')}, INP={cwv.get('inp_p75','?')}, CLS={cwv.get('cls_p75','?')})")
    lines.append("")

    # Last audit
    if data["audit"]:
        lines.append("## 🔧 Last Site Audit")
        lines.append("")
        lines.append(f"**Дата:** {data['audit']['audit_date']}")
        lines.append(f"**P0 issues:** {data['audit']['p0_count']}, **P1 issues:** {data['audit']['p1_count']}")
        lines.append(f"**Report:** `{data['audit']['path']}`")
        lines.append("")

    # Last refresh
    if data["refresh"]:
        lines.append("## ♻️  Last Refresh Plan")
        lines.append("")
        lines.append(f"**Дата:** {data['refresh']['refresh_date']}")
        lines.append(f"**Pages в плане:** {data['refresh']['page_count']}")
        lines.append(f"**File:** `{data['refresh']['path']}`")
        lines.append("")

    # Deindex
    if data["deindex_cases"]:
        lines.append("## 🚨 Deindex Cases")
        lines.append("")
        lines.append("| URL | Diagnosed | Cause | Status |")
        lines.append("|---|---|---|---|")
        for c in data["deindex_cases"][:20]:
            lines.append(f"| {c.get('url','')[:50]} | {c.get('diagnosed_date','')} | "
                         f"{c.get('primary_cause','?')} | {c.get('rewrite_plan_status','?')} |")
        lines.append("")

    # Next scheduled
    lines.append("## 📅 Next Scheduled Operations")
    lines.append("")
    today_d = date.today()
    next_monday = today_d + timedelta(days=(7 - today_d.weekday()) % 7 or 7)
    lines.append(f"- **Next Monday ({next_monday}):** Content writer → next keyword из очереди")
    week = (today_d.day - 1) // 7 + 1
    lines.append(f"- **Текущая неделя месяца:** {week}")
    if week == 1:
        lines.append("  - Wed ничего; Week 2 будет audit")
    elif week == 2:
        lines.append("  - **Wed: Site Audit** (если не запускался)")
    elif week == 3:
        lines.append("  - **Wed: Refresh Recommendation** (если не запускался)")
    elif week == 4:
        lines.append("  - **Fri: Keyword Replenish + Deindex Check** (если не запускался)")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("_Generated by `seo-cycle dashboard`. Обновлять по запросу или включить в cron._")
    return "\n".join(lines)


# ----- Main --------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=pathlib.Path,
                    default=pathlib.Path("seo/monthly-dashboard.md"))
    ap.add_argument("--json", action="store_true", help="JSON output вместо markdown")
    ap.add_argument("--config", type=pathlib.Path, default=pathlib.Path("seo-cycle.yaml"))
    args = ap.parse_args()

    # T-067 (F-37): a missing/unreadable config used to fall back to `{}`
    # silently and still print a green "✓ Dashboard → ..." over a project
    # that plainly doesn't have one — the tool's own health/status commands
    # already refuse this (`seo_cycle_cli.cmd_status`), the dashboard just
    # never learned the rule.
    if yaml is None:
        print("ERROR: PyYAML не установлен — установи: pip3 install pyyaml", file=sys.stderr)
        sys.exit(2)
    # require_config() itself refuses (stderr + exit 2) when the path doesn't
    # exist, and load_yaml()'s own form/parse checks (F-35) still apply once
    # it does — this command's whole output is meaningless without a real
    # project config, unlike a setup wizard's legitimate empty fallback.
    cfg = require_config(args.config if args.config.exists() else None, where=pathlib.Path.cwd())
    # T-090 (F-7): `config_section()` is a soft helper — `project: null`
    # used to sail through it as a silent `{}`, same green "✓ Dashboard →
    # ..." F-37/T-067 already fixed for a missing FILE, just reached via a
    # present-but-null section instead. `require_section()` refuses.
    project_name = require_section(cfg, "project", args.config).get("name") or "Project"

    # Путь мониторинга — из конфига (monitoring.path, T-052 R3: тот же ключ,
    # тем же способом, что pulse.py и doctor/status — seo_cycle_core.monitoring),
    # дефолт v2 seo/monitoring; v1-раскладка seo/09-monitoring/ остаётся
    # fallback-кандидатом всегда, чтобы старые проекты без monitoring.path
    # продолжали находить срезы.
    cwd = pathlib.Path.cwd()
    configured_dir = monitoring_dir(cfg, cwd)
    search_dirs = [configured_dir]
    for fallback in (cwd / "seo" / "monitoring", cwd / "seo" / "09-monitoring", cwd / "09-monitoring"):
        if fallback not in search_dirs:
            search_dirs.append(fallback)

    data = {
        "queue": load_queue(pathlib.Path("seo/keyword-queue.csv")),
        "approvals": load_approvals(pathlib.Path("seo/pending-approvals.md")),
        "latest_snapshot": load_latest_snapshot(search_dirs),
        "monitoring_search_dirs": [str(d) for d in search_dirs],
        "audit": load_latest_audit(pathlib.Path("seo/cycles")),
        "refresh": load_latest_refresh(pathlib.Path("seo/cycles")),
        "deindex_cases": load_deindex_cases(pathlib.Path("seo/research/deindex")),
        "published_log": load_publish_log(pathlib.Path("seo/publish-log.csv")),
    }

    if args.json:
        # Уберём raw rows для компактности
        compact = {**data, "queue": {k:v for k,v in data["queue"].items() if k != "rows"}}
        print(json.dumps(compact, ensure_ascii=False, indent=2, default=str))
        return

    md = render_markdown(data, project_name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md, encoding="utf-8")
    print(f"✓ Dashboard → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
