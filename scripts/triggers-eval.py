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
    triggers         Путь к triggers.yaml (default: config/triggers.yaml рядом со скриптом)
    --output PATH    Markdown файл (default: stdout)
    --project-yaml   Путь к seo-cycle.yaml проекта (для project-override triggers)
    --top N          Лимит на rule (default: 20 — топ N сработавших записей)

Условия в triggers.yaml — упрощённый DSL: имя_поля операторы число/строка
с поддержкой AND. Поддерживаются: <, <=, >, >=, ==, !=, contains,
older than N (days|months).

v2: перед оценкой queries[] обогащается вычисляемыми полями
(expected_ctr, ctr_gap, urls_for_query, potential — см. enrich_queries);
совпадения сортируются по potential ДО обрезки --top; записи, уже показанные
правилом более высокого приоритета, не дублируются в правилах ниже.
"""

from __future__ import annotations
import argparse, json, pathlib, re, sys
from datetime import date, datetime

try:
    import yaml  # noqa: F401 - presence check for the ImportError branch below
except ImportError:
    print("ERROR: PyYAML не установлен. pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from seo_cycle_core.config import numeric  # noqa: E402
from seo_cycle_core.ctr import expected_ctr  # noqa: E402


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

    try:
        # T-063 gate round 2: a non-numeric threshold in the trigger config
        # (config/triggers.yaml or a project's seo-triggers.yaml, keyed by
        # monitoring.triggers_file) leaves `expected_n` a raw string while
        # `actual_n` is a number — comparing them raises TypeError, which
        # crashed the whole triggers-eval run. A predicate that can't be
        # compared numerically just doesn't fire (False), same failure
        # shape as a field that resolves to None a few lines above.
        if op == "<":  return actual_n < expected_n
        if op == "<=": return actual_n <= expected_n
        if op == ">":  return actual_n > expected_n
        if op == ">=": return actual_n >= expected_n
        if op == "==": return actual_n == expected_n
        if op == "!=": return actual_n != expected_n
    except TypeError:
        return False
    return False


def eval_condition(item: dict, condition: str) -> bool:
    """Поддержка AND между предикатами."""
    parts = re.split(r"\s+AND\s+", condition, flags=re.IGNORECASE)
    return all(_eval_predicate(item, p) for p in parts)


# ----- Обогащение снапшота вычисляемыми полями ---------------------------

def enrich_queries(snapshot: dict) -> None:
    """Добавляет в queries[] вычисляемые поля (существующие значения не трогает):

    - expected_ctr   ожидаемый CTR для позиции (единая кривая seo_cycle_core.ctr)
    - ctr_gap        max(0, expected_ctr - ctr) — недобор CTR против кривой
    - urls_for_query число разных URL, ранжирующихся по этому запросу (каннибализация)
    - potential      impressions * ctr_gap — оценка недополученных кликов за окно среза
    """
    queries = snapshot.get("queries")
    if not isinstance(queries, list):
        return
    urls_by_query: dict[str, set] = {}
    for it in queries:
        if isinstance(it, dict) and it.get("query") and it.get("url"):
            urls_by_query.setdefault(str(it["query"]), set()).add(str(it["url"]))
    for it in queries:
        if not isinstance(it, dict):
            continue
        pos = numeric(it.get("position"))
        impressions = numeric(it.get("impressions"))
        ctr = numeric(it.get("ctr"))
        exp = expected_ctr(pos)
        gap = max(0.0, exp - ctr)
        it.setdefault("expected_ctr", round(exp, 4))
        it.setdefault("ctr_gap", round(gap, 4))
        it.setdefault("urls_for_query", len(urls_by_query.get(str(it.get("query") or ""), ())))
        it.setdefault("potential", round(impressions * gap, 1))


# ----- Применение правил к snapshot --------------------------------------

_PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}


def _match_sort_key(item: dict) -> tuple:
    return (numeric(item.get("potential")), numeric(item.get("impressions")), numeric(item.get("clicks")))


def _dedup_key(scope: str, item: dict):
    if scope == "queries" and item.get("query") is not None:
        return (scope, str(item.get("query")), str(item.get("url") or ""))
    if scope == "pages" and item.get("url"):
        return (scope, str(item["url"]))
    return None


def evaluate(snapshot: dict, triggers: list[dict], top: int = 20) -> dict:
    """Возвращает {trigger_id: {rule, matches, total, deduped}}.

    Правила применяются в порядке приоритета (P0 → P1 → P2, внутри — порядок
    конфига); совпадения сортируются по potential/impressions/clicks до обрезки
    `top`; запись, уже показанная правилом выше, в правилах ниже не повторяется
    (счётчик deduped). `total` — честное число совпадений до дедупа и обрезки.
    """
    enrich_queries(snapshot)
    results = {}
    claimed: set = set()
    ordered = sorted(enumerate(triggers),
                     key=lambda pair: (_PRIORITY_RANK.get(pair[1].get("priority", "P2"), 3), pair[0]))
    for _, rule in ordered:
        scope = rule.get("scope", "queries")
        condition = rule.get("when", "")
        items = snapshot.get(scope, [])
        if not isinstance(items, list):
            # для scope=cwv/behavior — это словарь, оборачиваем
            items = [items]
        matched = [it for it in items if isinstance(it, dict) and eval_condition(it, condition)]
        if not matched:
            continue
        matched.sort(key=_match_sort_key, reverse=True)
        fresh, deduped = [], 0
        for it in matched:
            key = _dedup_key(scope, it)
            if key is not None and key in claimed:
                deduped += 1
            else:
                fresh.append(it)
        if not fresh:
            continue
        shown = fresh[:top]
        for it in shown:
            key = _dedup_key(scope, it)
            if key is not None:
                claimed.add(key)
        results[rule["id"]] = {"rule": rule, "matches": shown,
                               "total": len(matched), "deduped": deduped}
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

    def _rule_potential(data: dict) -> float:
        return sum(numeric(it.get("potential")) for it in data["matches"])

    out.append("## Резюме")
    out.append("")
    out.append("| Приоритет | Правил сработало | Всего записей | Потенциал (клики за окно) |")
    out.append("|---|---|---|---|")
    for p in ["P0", "P1", "P2"]:
        if p in by_priority:
            total = sum(d["total"] for _, d in by_priority[p])
            pot = sum(_rule_potential(d) for _, d in by_priority[p])
            out.append(f"| **{p}** | {len(by_priority[p])} | {total} | ~{pot:.0f} |")
    out.append("")

    for p in ["P0", "P1", "P2"]:
        if p not in by_priority:
            continue
        out.append(f"## {p} — приоритет")
        out.append("")
        for tid, data in sorted(by_priority[p], key=lambda pair: _rule_potential(pair[1]), reverse=True):
            rule = data["rule"]
            out.append(f"### `{tid}` — {rule.get('action','')}")
            out.append("")
            if rule.get("delegate"):
                dedup_note = f" · перекрыто правилами выше: {data['deduped']}" if data.get("deduped") else ""
                out.append(f"**Делегат:** `{rule['delegate']}` · **Scope:** {rule.get('scope','?')} · "
                           f"**Всего:** {data['total']}{dedup_note}")
                out.append("")
            out.append(f"**Условие:** `{rule.get('when','')}`")
            out.append("")
            out.append(f"**Топ-{len(data['matches'])} записей (по потенциалу):**")
            out.append("")
            scope = rule.get("scope", "queries")
            for item in data["matches"]:
                if scope == "queries":
                    pot = numeric(item.get("potential"))
                    pot_note = f" potential=+{pot:.0f}" if pot else ""
                    cann = item.get("urls_for_query") or 0
                    cann_note = f" urls={cann}" if cann and cann > 1 else ""
                    out.append(f"- `{item.get('query','?')}` — "
                               f"impr={item.get('impressions','?')} clicks={item.get('clicks','?')} "
                               f"pos={numeric(item.get('position')):.1f} ctr={numeric(item.get('ctr')):.2%}"
                               f"{pot_note}{cann_note} · {item.get('url','')}")
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
                    default=SCRIPT_DIR.parent / "config" / "triggers.yaml")
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
    from seo_cycle_core.config import load_config, load_yaml_any
    # T-090 (F-8): triggers file is a top-level LIST-shaped or dict-with-
    # "triggers"-key file, not the project's main config — tolerant load.
    triggers_cfg = load_yaml_any(args.triggers)
    triggers = (triggers_cfg or {}).get("triggers", []) if isinstance(triggers_cfg, dict) else []

    # Project override (rules с тем же id перезаписывают/добавляют)
    if args.project_yaml and args.project_yaml.exists():
        proj = load_config(args.project_yaml)
        extra_triggers_path = proj.get("monitoring", {}).get("triggers_file")
        if extra_triggers_path:
            p = pathlib.Path(extra_triggers_path)
            if not p.is_absolute():
                p = args.project_yaml.parent / p
            if p.exists():
                extra_data = load_yaml_any(p)
                extra = extra_data.get("triggers", []) if isinstance(extra_data, dict) else []
                # merge by id
                by_id = {t["id"]: t for t in triggers}
                for t in extra:
                    by_id[t["id"]] = t
                triggers = list(by_id.values())
            else:
                print(f"⚠ monitoring.triggers_file указан, но не найден: {p}", file=sys.stderr)
        else:
            print("⚠ у проекта нет override-порогов (monitoring.triggers_file). Дефолтные "
                  "impressions-пороги рассчитаны на крупные сайты — на малом проекте движок "
                  "может молчать. Калибруй через <project>/seo-triggers.yaml (merge по id).",
                  file=sys.stderr)

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
