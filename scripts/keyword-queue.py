#!/usr/bin/env python3
"""
keyword-queue.py — FIFO очередь ключевых слов для monthly automation.

CSV-based queue с status workflow:
    pending → approved → in_production → published

Поля CSV:
    keyword, cluster, intent, nw_query_id, page_type, status,
    added_date, approved_date, approved_by, published_date, published_url,
    source, notes

Использование:
    # Список pending для approval
    python3 keyword-queue.py list --status pending

    # Добавить ключ (обычно делает keyword-researcher после Phase 2)
    python3 keyword-queue.py add "минвата для бани" --cluster minvata --intent commercial

    # Approve (5 min работа человека)
    python3 keyword-queue.py approve "минвата для бани"
    python3 keyword-queue.py approve --all-pending          # массовый

    # Pop следующий approved (для weekly-publisher)
    python3 keyword-queue.py pop                            # FIFO: oldest approved

    # Mark как published
    python3 keyword-queue.py publish "минвата для бани" --url https://example.com/...

    # Глубина очереди (для триггера replenish)
    python3 keyword-queue.py depth                          # выводит JSON: {approved, in_production, total}

    # Полный статус
    python3 keyword-queue.py status

Конфиг: путь к queue файлу через --queue-file или из seo-cycle.yaml
        (monthly_automation.keyword_queue.file).

Cross-platform: pure Python, no platform-specific calls. Работает в Claude
Code, Codex CLI, plain bash.
"""

from __future__ import annotations
import argparse, csv, json, os, pathlib, sys
from datetime import date


COLUMNS = [
    "keyword", "cluster", "intent", "nw_query_id", "page_type", "status",
    "added_date", "approved_date", "approved_by", "published_date", "published_url",
    "source", "notes",
]
STATUSES = ("pending", "approved", "in_production", "published", "rejected")


def find_queue_file(start: pathlib.Path) -> pathlib.Path | None:
    for rel in ("seo/keyword-queue.csv", "keyword-queue.csv", ".seo/keyword-queue.csv"):
        p = start / rel
        if p.exists():
            return p
    return None


def load(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save(path: pathlib.Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            full = {c: r.get(c, "") for c in COLUMNS}
            w.writerow(full)


def find_by_keyword(rows: list[dict], keyword: str) -> dict | None:
    target = keyword.strip().lower()
    for r in rows:
        if r.get("keyword", "").strip().lower() == target:
            return r
    return None


def cmd_add(rows: list[dict], args) -> bool:
    if find_by_keyword(rows, args.keyword):
        print(f"⚠ Уже в очереди: {args.keyword!r}", file=sys.stderr)
        return False
    rows.append({
        "keyword": args.keyword,
        "cluster": args.cluster or "",
        "intent": args.intent or "",
        "nw_query_id": args.nw_query_id or "",
        "page_type": args.page_type or "",
        "status": "pending",
        "added_date": date.today().isoformat(),
        "source": args.source or "manual",
        "notes": args.notes or "",
    })
    print(f"✓ Added: {args.keyword!r} (status=pending)", file=sys.stderr)
    return True


def cmd_approve(rows: list[dict], args) -> int:
    """Approve один или все pending. Возвращает количество approved."""
    count = 0
    by = args.by or os.environ.get("USER", "human")
    today = date.today().isoformat()
    targets = []
    if args.all_pending:
        targets = [r for r in rows if r.get("status") == "pending"]
    elif args.keyword:
        r = find_by_keyword(rows, args.keyword)
        if not r:
            print(f"⚠ Не найдено: {args.keyword!r}", file=sys.stderr)
            return 0
        if r.get("status") != "pending":
            print(f"⚠ Status уже {r.get('status')!r}, не pending", file=sys.stderr)
            return 0
        targets = [r]
    else:
        print("Укажи keyword или --all-pending", file=sys.stderr)
        return 0
    for r in targets:
        r["status"] = "approved"
        r["approved_date"] = today
        r["approved_by"] = by
        count += 1
        print(f"  ✓ approved: {r['keyword']}", file=sys.stderr)
    return count


def cmd_reject(rows: list[dict], args) -> bool:
    r = find_by_keyword(rows, args.keyword)
    if not r:
        print(f"⚠ Не найдено: {args.keyword!r}", file=sys.stderr)
        return False
    r["status"] = "rejected"
    r["notes"] = (r.get("notes", "") + " | rejected: " + (args.reason or "")).strip(" |")
    print(f"  ✓ rejected: {args.keyword}", file=sys.stderr)
    return True


def cmd_pop(rows: list[dict]) -> dict | None:
    """FIFO: oldest approved. Помечаем in_production, возвращаем dict."""
    approved = sorted(
        [r for r in rows if r.get("status") == "approved"],
        key=lambda r: r.get("approved_date", "")
    )
    if not approved:
        return None
    nxt = approved[0]
    nxt["status"] = "in_production"
    return nxt


def cmd_publish(rows: list[dict], args) -> bool:
    r = find_by_keyword(rows, args.keyword)
    if not r:
        print(f"⚠ Не найдено: {args.keyword!r}", file=sys.stderr)
        return False
    r["status"] = "published"
    r["published_date"] = date.today().isoformat()
    r["published_url"] = args.url or ""
    print(f"  ✓ published: {args.keyword} → {args.url or '(no url)'}", file=sys.stderr)
    return True


def cmd_list(rows: list[dict], args):
    filtered = rows
    if args.status:
        filtered = [r for r in rows if r.get("status") == args.status]
    if args.cluster:
        filtered = [r for r in filtered if r.get("cluster") == args.cluster]
    if args.json:
        print(json.dumps(filtered, ensure_ascii=False, indent=2))
        return
    if not filtered:
        print("(пусто)")
        return
    print(f"{'KEYWORD':<50} {'CLUSTER':<20} {'INTENT':<12} {'STATUS':<14} {'ADDED':<12}")
    print("-" * 110)
    for r in filtered:
        print(f"{r.get('keyword','')[:50]:<50} {r.get('cluster','')[:20]:<20} "
              f"{r.get('intent','')[:12]:<12} {r.get('status',''):<14} {r.get('added_date','')[:12]:<12}")


def cmd_depth(rows: list[dict]) -> dict:
    by_status = {}
    for s in STATUSES:
        by_status[s] = sum(1 for r in rows if r.get("status") == s)
    by_status["total"] = len(rows)
    return by_status


def cmd_status(rows: list[dict]):
    depth = cmd_depth(rows)
    print("== Keyword Queue ==")
    print(f"  Total: {depth['total']}")
    for s in STATUSES:
        print(f"  {s:<14}: {depth.get(s, 0)}")
    # Cluster breakdown
    clusters: dict[str, int] = {}
    for r in rows:
        c = r.get("cluster") or "(none)"
        clusters[c] = clusters.get(c, 0) + 1
    if clusters:
        print(f"\nBy cluster:")
        for c, n in sorted(clusters.items(), key=lambda x: -x[1]):
            print(f"  {c:<25}: {n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queue-file", type=pathlib.Path,
                    help="Путь к queue.csv (default: автопоиск)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Краткая сводка")

    p_depth = sub.add_parser("depth", help="JSON: counts по статусам")
    p_depth.add_argument("--json", action="store_true", default=True)

    p_list = sub.add_parser("list", help="Список (фильтр по status/cluster)")
    p_list.add_argument("--status", choices=STATUSES)
    p_list.add_argument("--cluster")
    p_list.add_argument("--json", action="store_true")

    p_add = sub.add_parser("add", help="Добавить keyword (status=pending)")
    p_add.add_argument("keyword")
    p_add.add_argument("--cluster")
    p_add.add_argument("--intent", choices=("commercial","informational","navigational","transactional"))
    p_add.add_argument("--nw-query-id")
    p_add.add_argument("--page-type", choices=("hub","spoke","category","brand","page"))
    p_add.add_argument("--source")
    p_add.add_argument("--notes")

    p_appr = sub.add_parser("approve", help="Approve keyword(s)")
    p_appr.add_argument("keyword", nargs="?")
    p_appr.add_argument("--all-pending", action="store_true")
    p_appr.add_argument("--by", help="Approver (default: $USER)")

    p_rej = sub.add_parser("reject", help="Reject keyword")
    p_rej.add_argument("keyword")
    p_rej.add_argument("--reason")

    p_pop = sub.add_parser("pop", help="Pop next approved (mark as in_production)")
    p_pop.add_argument("--peek", action="store_true", help="Не менять status, только показать next")

    p_pub = sub.add_parser("publish", help="Mark как published")
    p_pub.add_argument("keyword")
    p_pub.add_argument("--url")

    args = ap.parse_args()

    queue_file = args.queue_file or find_queue_file(pathlib.Path.cwd())
    if not queue_file:
        queue_file = pathlib.Path("seo/keyword-queue.csv")
        if args.cmd != "add":
            print(f"⚠ Queue не найден. Создам новый: {queue_file}", file=sys.stderr)

    rows = load(queue_file)
    dirty = False

    if args.cmd == "status":
        cmd_status(rows)
    elif args.cmd == "depth":
        print(json.dumps(cmd_depth(rows), indent=2))
    elif args.cmd == "list":
        cmd_list(rows, args)
    elif args.cmd == "add":
        dirty = cmd_add(rows, args)
    elif args.cmd == "approve":
        count = cmd_approve(rows, args)
        dirty = count > 0
        if dirty:
            print(f"\n✓ Approved: {count}", file=sys.stderr)
    elif args.cmd == "reject":
        dirty = cmd_reject(rows, args)
    elif args.cmd == "pop":
        nxt = cmd_pop(rows) if not args.peek else next(
            iter(sorted([r for r in rows if r.get("status")=="approved"], key=lambda r: r.get("approved_date",""))),
            None
        )
        if nxt:
            print(json.dumps(nxt, ensure_ascii=False, indent=2))
            if not args.peek:
                dirty = True
        else:
            print("⚠ Нет approved ключей в очереди.", file=sys.stderr)
            sys.exit(1)
    elif args.cmd == "publish":
        dirty = cmd_publish(rows, args)

    if dirty:
        save(queue_file, rows)
        print(f"✓ Saved: {queue_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
