#!/usr/bin/env python3
"""
programmatic-template-gen.py — генератор страниц по шаблону и dataset.

Для mode: programmatic — массовая генерация N страниц на основе:
- Markdown template с {{placeholder}} подстановками
- Dataset (CSV или JSON) — каждая строка = одна страница

Применение: «город × услуга», «бренд × категория», «размер × материал»,
matrix-страницы каталога, локальные landing pages, etc.

Использование:
    python3 programmatic-template-gen.py \\
        --template templates/programmatic-page.template.md \\
        --dataset data/cities-services.csv \\
        --output-dir generated/

    # JSON dataset
    python3 programmatic-template-gen.py \\
        --template page.md --dataset data.json --output-dir out/

    # Кастомное имя файла (по placeholders)
    python3 programmatic-template-gen.py \\
        --template t.md --dataset d.csv --output-dir out/ \\
        --filename-pattern "{slug}-{city_slug}.md"

Опции:
    --template PATH         Markdown с {{placeholder}} (см. templates/programmatic-page.template.md)
    --dataset PATH          CSV или JSON. Колонки/keys = названия placeholders
    --output-dir DIR        Куда писать generated/
    --filename-pattern STR  Шаблон имени файла (default: {slug}.md). Можно использовать любые поля dataset
    --dry-run               Показать список планируемых файлов без записи
    --limit N               Лимит на количество файлов (default: без лимита)
    --filter EXPR           Фильтр строк (например "stock_status == 'instock'")

Безопасность: при перезаписи существующего файла спрашивает подтверждение
(или используй --force).
"""

from __future__ import annotations
import argparse, csv, json, pathlib, re, sys


PLACEHOLDER_RE = re.compile(r"\{\{\s*([\w\.]+)\s*\}\}")


def load_dataset(path: pathlib.Path) -> list[dict]:
    """Загружает CSV/JSON в список словарей."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # объект {items: [...]} либо {key1: {...}, key2: {...}}
            for key in ("items", "data", "rows", "records"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # dict-of-dicts: ключи становятся slug-ами
            out = []
            for k, v in data.items():
                if isinstance(v, dict):
                    v.setdefault("slug", k)
                    out.append(v)
            return out
        return []
    raise ValueError(f"Unsupported dataset format: {suffix}. Use .csv or .json")


def render_template(template: str, row: dict) -> str:
    """Подставляет {{placeholder}} → row['placeholder']. Пустые поля → '_'.

    Поддерживает dotted path: {{address.city}} → row['address']['city'].
    """
    def resolve(match):
        path = match.group(1)
        value = row
        for part in path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return f"{{{{MISSING:{path}}}}}"
        return str(value) if value is not None else ""

    return PLACEHOLDER_RE.sub(resolve, template)


def render_filename(pattern: str, row: dict) -> str:
    """Рендерит имя файла. Использует .format() с row keys как kwargs."""
    try:
        return pattern.format(**row)
    except KeyError as e:
        return pattern.replace(f"{{{e.args[0]}}}", "missing")


def apply_filter(rows: list[dict], expr: str) -> list[dict]:
    """Простой фильтр: 'field operator value', например 'stock == in_stock'.

    Поддерживает: ==, !=, >, <, >=, <=. Значения — строки или числа.
    """
    if not expr:
        return rows
    m = re.match(r"(\w+)\s*(==|!=|>=|<=|>|<)\s*['\"]?([^'\"]+)['\"]?", expr.strip())
    if not m:
        print(f"⚠ Ignoring filter (parse error): {expr}", file=sys.stderr)
        return rows
    field, op, raw_val = m.group(1), m.group(2), m.group(3)

    def cast(v):
        try: return float(v)
        except ValueError: return v

    val = cast(raw_val)
    out = []
    for r in rows:
        actual = r.get(field)
        actual_n = cast(str(actual)) if actual is not None else None
        try:
            if op == "==": match = actual_n == val
            elif op == "!=": match = actual_n != val
            elif op == ">":  match = actual_n > val
            elif op == "<":  match = actual_n < val
            elif op == ">=": match = actual_n >= val
            elif op == "<=": match = actual_n <= val
            else: match = False
        except TypeError:
            match = False
        if match:
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", required=True, type=pathlib.Path)
    ap.add_argument("--dataset", required=True, type=pathlib.Path)
    ap.add_argument("--output-dir", required=True, type=pathlib.Path)
    ap.add_argument("--filename-pattern", default="{slug}.md")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--filter")
    ap.add_argument("--force", action="store_true", help="Перезаписывать существующие файлы без вопроса")
    args = ap.parse_args()

    if not args.template.exists():
        ap.error(f"Template not found: {args.template}")
    if not args.dataset.exists():
        ap.error(f"Dataset not found: {args.dataset}")

    template = args.template.read_text(encoding="utf-8")
    rows = load_dataset(args.dataset)
    print(f"Loaded {len(rows)} rows from {args.dataset}", file=sys.stderr)

    if args.filter:
        rows = apply_filter(rows, args.filter)
        print(f"After filter: {len(rows)} rows", file=sys.stderr)

    if args.limit:
        rows = rows[:args.limit]

    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    generated, skipped, missing_placeholders = 0, 0, 0
    for row in rows:
        filename = render_filename(args.filename_pattern, row)
        target = args.output_dir / filename
        rendered = render_template(template, row)

        # Подсчёт missing placeholders
        if "MISSING:" in rendered:
            missing_placeholders += 1

        if args.dry_run:
            print(f"  [DRY] {target}")
            generated += 1
            continue

        if target.exists() and not args.force:
            print(f"  skip (exists, use --force): {target}", file=sys.stderr)
            skipped += 1
            continue

        target.write_text(rendered, encoding="utf-8")
        generated += 1

    print(f"\n✓ Generated: {generated}, skipped: {skipped}, with missing placeholders: {missing_placeholders}",
          file=sys.stderr)
    if missing_placeholders:
        print(f"  Tip: проверь generated файлы на {{{{MISSING:fieldname}}}} маркеры", file=sys.stderr)


if __name__ == "__main__":
    main()
