#!/usr/bin/env python3
"""
triggers-eval.py — оценщик triggers.yaml по snapshot.json (Phase 10 движок).

Загружает snapshot.json (от snapshot-build.py) + triggers.yaml (декларативные
правила) → выводит markdown action list по приоритетам (P0/P1/P2) с указанием
конкретных URL, запросов и рекомендуемых делегатов.

Использование:
    python3 triggers-eval.py <snapshot.json> [<triggers.yaml>] [--output FILE]

Опции:
    snapshot         Путь к snapshot.json (Phase 9 output)
    triggers         Путь к triggers.yaml (default: ~/.codex/skills/seo-cycle/config/triggers.yaml)
    --output PATH    Markdown файл (default: stdout)
    --project-yaml   Путь к seo-cycle.yaml проекта (для project-override triggers)
    --top N          Лимит на rule (default: 20 — топ N сработавших записей)

Условия в triggers.yaml — упрощённый DSL: имя_поля операторы число/строка
с поддержкой AND. Поддерживаются: <, <=, >, >=, ==, !=, contains,
older than N (days|months).
"""

from __future__ import annotations
import argparse, json, pathlib, re, sys
from datetime import date, datetime

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)


# ----- Парсер условий ----------------------------------------------------

OP_RE = re.compile(
    r"(?P<field>[\w\.]+)\s*"
    r"(?P<op><=|>=|==|!=|<|>|contains|older\s+than)\s*"
    r"(?P<value>'[^']*'|\"[^\"]*\"|[\w\.\-+]+(?:\s+(?:days?|months?|years?))?)"
)


def _resolve(obj: dict, path: str):
    """Достаём вложенное поле по 'a.b.c'. Возвращаем None если нет."""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _coerce(v):
    if isinstance(v, str):
        s = v.strip("'\"")
        try: return int(s)
        except ValueError:
            try: return float(s)
            except ValueError: return s
    return v


def _eval_predicate(item: dict, pred: str) -> bool:
    """Применяем одну сравнительную предикат-операцию к item."""
    m = OP_RE.match(pred.strip())
    if not m:
        return False
    field = m["field"]
    op = m["op"].lower()
    raw_value = m["value"].strip()

    actual = _resolve(item, field)

    if op == "older than":
        # raw_value: "6 months" / "30 days"
        parts = raw_value.split()
        if len(parts) < 2:
            return False
        try:
            n = int(parts[0])
        except ValueError:
            return False
        unit = parts[1].lower().rstrip("s")
        days = {"day": 1, "month": 30, "year": 365}.get(unit, 1) * n
        if not actual:
            return False
        try:
            dt = datetime.fromisoformat(str(actual)).date() if "-" in str(actual) else None
        except ValueError:
            return False
        if not dt:
            return False
        return (date.today() - dt).days >= days

    if op == "contains":
        if actual is None:
            return False
        return str(_coerce(raw_value)) in str(actual)

    if actual is None:
        return False

    expected = _coerce(raw_value)
    try:
        actual_n = float(actual)
        expected_n = float(expected) if not isinstance(expected, str) else expected
    except (TypeError, ValueError):
        actual_n, expected_n = actual, expected

    if op == "<":  return actual_n < expected_n
    if op == "<=": return actual_n <= expected_n
    if op == ">":  return actual_n > expected_n
    if op == ">=": return actual_n >= expected_n
    if op == "==": return actual_n == expected_n
    if op == "!=": return actual_n != expected_n
    return False


def eval_condition(item: dict, condition: str) -> bool:
    """Поддержка AND между предикатами."""
    parts = re.split(r"\s+AND\s+", condition, flags=re.IGNORECASE)
    return all(_eval_predicate(item, p) for p in parts)


# ----- Применение правил к snapshot --------------------------------------

def evaluate(snapshot: dict, triggers: list[dict], top: int = 20) -> dict:
    """Возвращает {trigger_id: {rule, matches: [items]}}."""
    results = {}
    for rule in triggers:
        scope = rule.get("scope", "queries")
        condition = rule.get("when", "")
        items = snapshot.get(scope, [])
        if not isinstance(items, list):
            # для scope=cwv/behavior — это словарь, оборачиваем
            items = [items]
        matched = [it for it in items if isinstance(it, dict) and eval_condition(it, condition)]
        if matched:
            results[rule["id"]] = {"rule": rule, "matches": matched[:top], "total": len(matched)}
    return results


# ----- Рендер markdown -------------------------------------------------

def render_markdown(snapshot: dict, results: dict, top: int) -> str:
    today = date.today().isoformat()
    out = [f"# Triggers eval — {today}", ""]
    out.append(f"> Snapshot: `{snapshot.get('snapshot_date','?')}`, "
               f"period `{snapshot.get('period',{}).get('start','?')} → {snapshot.get('period',{}).get('end','?')}`")
    out.append(f"> Sources: {', '.join(s.get('source','?') for s in snapshot.get('sources', []))}")
    out.append("")

    if not results:
        out.append("✅ Ни одно правило не сработало. Снапшот в зелёной зоне.")
        return "\n".join(out)

    # Группировка по приоритету
    by_priority: dict[str, list] = {}
    for tid, data in results.items():
        p = data["rule"].get("priority", "P2")
        by_priority.setdefault(p, []).append((tid, data))

    out.append("## Резюме")
    out.append("")
    out.append("| Приоритет | Правил сработало | Всего записей |")
    out.append("|---|---|---|")
    for p in ["P0", "P1", "P2"]:
        if p in by_priority:
            total = sum(d["total"] for _, d in by_priority[p])
            out.append(f"| **{p}** | {len(by_priority[p])} | {total} |")
    out.append("")

    for p in ["P0", "P1", "P2"]:
        if p not in by_priority:
            continue
        out.append(f"## {p} — приоритет")
        out.append("")
        for tid, data in by_priority[p]:
            rule = data["rule"]
            out.append(f"### `{tid}` — {rule.get('action','')}")
            out.append("")
            if rule.get("delegate"):
                out.append(f"**Делегат:** `{rule['delegate']}` · **Scope:** {rule.get('scope','?')} · "
                           f"**Всего:** {data['total']}")
                out.append("")
            out.append(f"**Условие:** `{rule.get('when','')}`")
            out.append("")
            out.append(f"**Топ-{min(top, data['total'])} записей:**")
            out.append("")
            scope = rule.get("scope", "queries")
            for item in data["matches"]:
                if scope == "queries":
                    out.append(f"- `{item.get('query','?')}` — "
                               f"impr={item.get('impressions','?')} clicks={item.get('clicks','?')} "
                               f"pos={item.get('position','?'):.1f} ctr={item.get('ctr',0):.2%} · "
                               f"{item.get('url','')}")
                elif scope == "pages":
                    behav = item.get("behavior", {})
                    out.append(f"- {item.get('url','?')} — impr={item.get('impressions','?')} "
                               f"sessions={item.get('sessions','?')} bounce={behav.get('bounce','?')}")
                else:
                    out.append(f"- {json.dumps(item, ensure_ascii=False)[:140]}")
            out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("snapshot", type=pathlib.Path, help="snapshot.json")
    ap.add_argument("triggers", nargs="?", type=pathlib.Path,
                    default=pathlib.Path.home() / ".claude/skills/seo-cycle/config/triggers.yaml")
    ap.add_argument("--output", type=pathlib.Path)
    ap.add_argument("--project-yaml", type=pathlib.Path,
                    help="Путь к seo-cycle.yaml для overrides (опц.)")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    if not args.snapshot.exists():
        print(f"ERROR: snapshot not found: {args.snapshot}", file=sys.stderr)
        sys.exit(2)
    if not args.triggers.exists():
        print(f"ERROR: triggers not found: {args.triggers}", file=sys.stderr)
        sys.exit(2)

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    triggers_cfg = yaml.safe_load(args.triggers.read_text(encoding="utf-8"))
    triggers = triggers_cfg.get("triggers", [])

    # Project override (rules с тем же id перезаписывают/добавляют)
    if args.project_yaml and args.project_yaml.exists():
        proj = yaml.safe_load(args.project_yaml.read_text(encoding="utf-8")) or {}
        extra_triggers_path = proj.get("monitoring", {}).get("triggers_file")
        if extra_triggers_path:
            p = pathlib.Path(extra_triggers_path)
            if p.exists():
                extra = yaml.safe_load(p.read_text(encoding="utf-8")).get("triggers", [])
                # merge by id
                by_id = {t["id"]: t for t in triggers}
                for t in extra:
                    by_id[t["id"]] = t
                triggers = list(by_id.values())

    results = evaluate(snapshot, triggers, top=args.top)
    md = render_markdown(snapshot, results, args.top)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
        print(f"✓ {len(results)} правил сработало → {args.output}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
