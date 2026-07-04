#!/usr/bin/env python3
"""
approval-gate.py — file-based approval ticket система.

Workflow:
1. Subagent создаёт ticket: approval-gate.py create --type content_publish --file <path>
   → пишется в seo/pending-approvals.md как markdown checkbox
2. Человек проверяет: approval-gate.py list
3. Approve: approval-gate.py approve <ticket_id> [--note "..."]
4. Subagent проверяет: approval-gate.py status <ticket_id> → approved | pending | rejected
5. Если approved — продолжает workflow

Без approval ничего не публикуется и не применяется. Это safety brake для
monthly automation.

Типы tickets:
    keyword_research     — Phase 2 результаты для review (5 min)
    content_publish      — draft статьи перед публикацией (2 min/post)
    audit_fixes          — критические fixes от seo-monthly-auditor (30 min)
    refresh_plan         — список страниц для refresh (10 min)
    deindex_rewrite      — список «потерянных» страниц для переписывания (5 min)

Storage: один markdown файл `seo/pending-approvals.md` (человекочитаемый).

Использование:
    # Создать (subagent)
    python3 approval-gate.py create \\
        --type content_publish \\
        --title "Пост: Как выбрать минвату" \\
        --file blog/2026-06-03-vybor-minvaty.publish.md \\
        --review-cmd "head -50 blog/2026-06-03-vybor-minvaty.publish.md"

    # Список pending (человек)
    python3 approval-gate.py list

    # Approve (человек)
    python3 approval-gate.py approve <ticket_id>

    # Reject
    python3 approval-gate.py reject <ticket_id> --reason "пересмотри H1"

    # Проверить статус (subagent)
    python3 approval-gate.py status <ticket_id>

    # Cleanup approved/rejected старше N дней
    python3 approval-gate.py prune --days 30

Cross-platform: pure Python. Работает в Claude Code, Codex, plain bash.
"""

from __future__ import annotations
import argparse, hashlib, json, pathlib, re, sys
from datetime import date, datetime, timedelta


TICKET_TYPES = {
    "keyword_research": "🔑 Keyword Research",
    "content_publish": "📝 Content Publish",
    "audit_fixes": "🔧 Audit Fixes",
    "refresh_plan": "♻️  Refresh Plan",
    "deindex_rewrite": "🚨 Deindex Rewrite",
    "loop_escalation": "🔁 Loop Escalation",
    "ads_campaign_draft": "📣 Ads Campaign Draft",
    "ads_bid_change": "💰 Ads Bid Change",
    "kpi_off_track": "📉 KPI Off Track",
    "custom": "⏸  Custom",
}
STATUSES = ("pending", "approved", "rejected")


def find_approvals_file(start: pathlib.Path) -> pathlib.Path:
    for rel in ("seo/pending-approvals.md", "pending-approvals.md", ".seo/pending-approvals.md"):
        p = start / rel
        if p.exists():
            return p
    return start / "seo/pending-approvals.md"


# ----- Парсинг markdown с тикетами ---------------------------------------

TICKET_RE = re.compile(
    r"<!--\s*ticket\s*"
    r"id:(?P<id>[a-f0-9]+)\s+"
    r"type:(?P<type>\w+)\s+"
    r"status:(?P<status>\w+)\s+"
    r"created:(?P<created>[\d-]+)"
    r"(?:\s+approved:(?P<approved>[\d-]+))?"
    r"(?:\s+by:(?P<by>[^\s]+))?"
    r"\s*-->",
    re.IGNORECASE,
)


def load_tickets(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    tickets = []
    for m in TICKET_RE.finditer(text):
        tickets.append({
            "id": m["id"],
            "type": m["type"],
            "status": m["status"],
            "created": m["created"],
            "approved": m["approved"],
            "by": m["by"],
            "raw_block": _extract_ticket_block(text, m.start()),
        })
    return tickets


def _extract_ticket_block(text: str, start: int) -> str:
    """Извлекает весь markdown блок тикета (от <!-- ticket --> до следующего ---)."""
    # Find end: next "---" separator or next "<!-- ticket" or EOF
    end_sep = text.find("\n---\n", start)
    end_next = text.find("<!-- ticket ", start + 10)
    candidates = [c for c in (end_sep, end_next) if c > 0]
    end = min(candidates) if candidates else len(text)
    return text[start:end].strip()


def _ticket_id(ticket_type: str, title: str, payload: str) -> str:
    return hashlib.sha1(f"{ticket_type}|{title}|{payload}".encode()).hexdigest()[:8]


def write_tickets(path: pathlib.Path, tickets: list[dict], header: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [header.strip(), ""] if header else ["# Pending approvals", ""]
    lines.append(f"_Обновлено: {date.today().isoformat()}_")
    lines.append("")
    pending = [t for t in tickets if t["status"] == "pending"]
    if pending:
        lines.append(f"## ⏸ Pending ({len(pending)})")
        lines.append("")
        for t in pending:
            lines.append(t["raw_block"])
            lines.append("")
            lines.append("---")
            lines.append("")
    resolved = [t for t in tickets if t["status"] in ("approved", "rejected")]
    if resolved:
        lines.append(f"## ✅ Resolved ({len(resolved)})")
        lines.append("")
        for t in sorted(resolved, key=lambda r: r.get("approved") or "", reverse=True)[:50]:
            lines.append(t["raw_block"])
            lines.append("")
            lines.append("---")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ----- Команды -----------------------------------------------------------

def cmd_create(args, path: pathlib.Path):
    today = date.today().isoformat()
    payload = json.dumps({
        "title": args.title, "file": args.file or "",
        "review_cmd": args.review_cmd or "",
        "context": args.context or "",
    }, sort_keys=True)
    tid = _ticket_id(args.type, args.title, payload)

    type_label = TICKET_TYPES.get(args.type, args.type)

    block = f"""<!-- ticket id:{tid} type:{args.type} status:pending created:{today} -->
### {type_label}: {args.title}

- **ID:** `{tid}`
- **Type:** `{args.type}`
- **Created:** {today}"""

    if args.file:
        block += f"\n- **File:** `{args.file}`"
    if args.review_cmd:
        block += f"\n- **Review:** `{args.review_cmd}`"
    if args.context:
        block += f"\n- **Context:** {args.context}"

    block += f"""

**Actions:**
- Approve: `python3 ~/.codex/skills/seo-cycle/scripts/approval-gate.py approve {tid}`
- Reject:  `python3 ~/.codex/skills/seo-cycle/scripts/approval-gate.py reject {tid} --reason "..."`
"""

    tickets = load_tickets(path)
    # Дедуп по id
    if any(t["id"] == tid for t in tickets):
        print(f"⚠ Ticket {tid} уже существует — skip", file=sys.stderr)
        return tid
    tickets.append({
        "id": tid, "type": args.type, "status": "pending",
        "created": today, "approved": None, "by": None,
        "raw_block": block,
    })
    write_tickets(path, tickets)
    print(f"✓ Ticket created: {tid}", file=sys.stderr)
    print(f"  Type: {args.type}, Title: {args.title}", file=sys.stderr)
    print(f"  See: {path}", file=sys.stderr)
    _notify(f"Новый approval-тикет: <b>{type_label}</b>\n{args.title}\nID: {tid}",
            title="SEO: нужно решение", level="warn")
    print(tid)
    return tid


def _notify(text: str, title: str = "", level: str = "info"):
    """Best-effort уведомление через notify.py. Никогда не ломает основной поток."""
    import subprocess
    notify = pathlib.Path(__file__).resolve().parent / "notify.py"
    if not notify.exists():
        return
    try:
        cmd = [sys.executable, str(notify), text, "--level", level]
        if title:
            cmd += ["--title", title]
        subprocess.run(cmd, timeout=25, capture_output=True)
    except Exception:
        pass


def cmd_list(args, path: pathlib.Path):
    tickets = load_tickets(path)
    filtered = tickets
    if args.status:
        filtered = [t for t in tickets if t["status"] == args.status]
    if args.type:
        filtered = [t for t in filtered if t["type"] == args.type]
    if not filtered:
        print("(нет tickets)")
        return
    if args.json:
        # Без raw_block для компактности
        compact = [{k: v for k, v in t.items() if k != "raw_block"} for t in filtered]
        print(json.dumps(compact, ensure_ascii=False, indent=2))
        return
    print(f"{'ID':<10} {'TYPE':<20} {'STATUS':<10} {'CREATED':<12} {'BY':<15}")
    print("-" * 75)
    for t in filtered:
        print(f"{t['id']:<10} {t['type']:<20} {t['status']:<10} {t.get('created',''):<12} {(t.get('by') or '-'):<15}")


def _update_ticket_status(tickets: list[dict], tid: str, new_status: str,
                          by: str, note: str = ""):
    for t in tickets:
        if t["id"] == tid:
            t["status"] = new_status
            t["approved"] = date.today().isoformat()
            t["by"] = by
            # Append note в raw_block
            note_line = f"\n**Resolution ({new_status} by {by} {date.today().isoformat()}):** {note}".strip()
            # Заменить ticket header status
            t["raw_block"] = re.sub(
                r"(<!-- ticket id:\w+ type:\w+) status:\w+",
                rf"\1 status:{new_status}",
                t["raw_block"]
            )
            # Добавить approved/by в header если ещё нет
            if "approved:" not in t["raw_block"]:
                t["raw_block"] = re.sub(
                    r"(<!-- ticket [^>]+) -->",
                    rf"\1 approved:{t['approved']} by:{by} -->",
                    t["raw_block"]
                )
            t["raw_block"] += note_line
            return True
    return False


def cmd_approve(args, path: pathlib.Path):
    tickets = load_tickets(path)
    by = args.by or "human"
    if not _update_ticket_status(tickets, args.ticket_id, "approved", by, args.note or ""):
        print(f"⚠ Ticket {args.ticket_id} не найден", file=sys.stderr)
        sys.exit(1)
    write_tickets(path, tickets)
    print(f"✓ Approved: {args.ticket_id}", file=sys.stderr)


def cmd_reject(args, path: pathlib.Path):
    tickets = load_tickets(path)
    by = args.by or "human"
    if not _update_ticket_status(tickets, args.ticket_id, "rejected", by, args.reason or ""):
        print(f"⚠ Ticket {args.ticket_id} не найден", file=sys.stderr)
        sys.exit(1)
    write_tickets(path, tickets)
    print(f"✓ Rejected: {args.ticket_id}", file=sys.stderr)


def cmd_status(args, path: pathlib.Path):
    tickets = load_tickets(path)
    for t in tickets:
        if t["id"] == args.ticket_id:
            print(t["status"])
            sys.exit(0 if t["status"] == "approved" else 1 if t["status"] == "pending" else 2)
    print("not_found", file=sys.stderr)
    sys.exit(3)


def cmd_prune(args, path: pathlib.Path):
    tickets = load_tickets(path)
    cutoff = (date.today() - timedelta(days=args.days)).isoformat()
    keep = []
    pruned = 0
    for t in tickets:
        if t["status"] == "pending":
            keep.append(t)
        else:
            approved = t.get("approved") or t.get("created", "")
            if approved >= cutoff:
                keep.append(t)
            else:
                pruned += 1
    write_tickets(path, keep)
    print(f"✓ Pruned: {pruned} tickets старше {args.days} дней", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", "-f", type=pathlib.Path, dest="approvals_file",
                    help="Путь к pending-approvals.md (default: автопоиск)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Создать ticket")
    p_create.add_argument("--type", required=True, choices=list(TICKET_TYPES.keys()))
    p_create.add_argument("--title", required=True)
    p_create.add_argument("--file", help="Путь к ресурсу для review (статья, отчёт и т.д.)")
    p_create.add_argument("--review-cmd", help="Команда для удобного просмотра")
    p_create.add_argument("--context", help="Доп. описание")

    p_list = sub.add_parser("list", help="Список tickets")
    p_list.add_argument("--status", choices=STATUSES)
    p_list.add_argument("--type", choices=list(TICKET_TYPES.keys()))
    p_list.add_argument("--json", action="store_true")

    p_appr = sub.add_parser("approve", help="Approve ticket")
    p_appr.add_argument("ticket_id")
    p_appr.add_argument("--by")
    p_appr.add_argument("--note")

    p_rej = sub.add_parser("reject", help="Reject ticket")
    p_rej.add_argument("ticket_id")
    p_rej.add_argument("--by")
    p_rej.add_argument("--reason")

    p_st = sub.add_parser("status", help="Получить status ticket")
    p_st.add_argument("ticket_id")

    p_pr = sub.add_parser("prune", help="Удалить старые resolved tickets")
    p_pr.add_argument("--days", type=int, default=30)

    args = ap.parse_args()
    path = args.approvals_file or find_approvals_file(pathlib.Path.cwd())

    if args.cmd == "create":
        cmd_create(args, path)
    elif args.cmd == "list":
        cmd_list(args, path)
    elif args.cmd == "approve":
        cmd_approve(args, path)
    elif args.cmd == "reject":
        cmd_reject(args, path)
    elif args.cmd == "status":
        cmd_status(args, path)
    elif args.cmd == "prune":
        cmd_prune(args, path)


if __name__ == "__main__":
    main()
