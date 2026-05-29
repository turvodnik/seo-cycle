#!/usr/bin/env python3
"""
schema-validate.py — JSON-LD валидатор для Phase 8.

Извлекает все <script type="application/ld+json"> блоки из HTML/markdown
файла и проверяет:
1. JSON валиден
2. Есть @context (schema.org или с подменой)
3. Есть @type
4. Для популярных типов (Product, Article, LocalBusiness, FAQPage, Service,
   Organization, BreadcrumbList, VideoObject) — наличие обязательных полей
   по требованиям Google Rich Results.

Использование:
    python3 schema-validate.py page.html
    python3 schema-validate.py drafts/*.md --strict
    python3 schema-validate.py --json-only schema.json    # валидировать сам JSON

Опции:
    files                   Файлы для проверки (HTML, MD с inline JSON-LD)
    --strict                Warnings → errors
    --json-only             Считать input чистым JSON-LD (без HTML wrapper)
    --type TYPE             Валидировать только заданный @type (Product, Article, ...)

Exit 0 — чисто; 1 — есть ошибки; 2 — invalid invocation.
"""

from __future__ import annotations
import argparse, json, pathlib, re, sys


JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

REQUIRED_FIELDS = {
    "Product": {"name", "image", "description"},
    "Article": {"headline", "author", "datePublished"},
    "NewsArticle": {"headline", "author", "datePublished"},
    "BlogPosting": {"headline", "author", "datePublished"},
    "LocalBusiness": {"name", "address"},
    "Restaurant": {"name", "address"},
    "FAQPage": {"mainEntity"},
    "Service": {"name", "provider"},
    "Organization": {"name", "url"},
    "BreadcrumbList": {"itemListElement"},
    "VideoObject": {"name", "description", "thumbnailUrl", "uploadDate"},
    "HowTo": {"name", "step"},
    "Event": {"name", "startDate", "location"},
    "Recipe": {"name", "recipeIngredient", "recipeInstructions"},
    "Course": {"name", "description", "provider"},
}

RECOMMENDED_FIELDS = {
    "Product": {"sku", "brand", "offers", "aggregateRating", "review"},
    "Article": {"image", "publisher", "dateModified", "mainEntityOfPage"},
    "LocalBusiness": {"telephone", "openingHours", "geo", "priceRange"},
    "Service": {"areaServed", "description", "offers"},
    "VideoObject": {"duration", "contentUrl", "embedUrl"},
}


def extract_jsonld(text: str) -> list[tuple[int, str]]:
    """Возвращает [(line_number, json_text)] для каждого блока."""
    blocks = []
    for m in JSONLD_RE.finditer(text):
        # Считаем строки до начала блока
        line_num = text[:m.start()].count("\n") + 1
        blocks.append((line_num, m.group(1).strip()))
    return blocks


def validate_block(json_text: str, type_filter: str | None,
                   errors: list, warnings: list, source: str = ""):
    """Валидирует один JSON-LD блок."""
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        errors.append(f"{source}: JSON parse error: {e}")
        return

    # Может быть массив или single
    items = data if isinstance(data, list) else [data]

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            warnings.append(f"{source}[{idx}]: not a dict")
            continue

        ctx = item.get("@context")
        if not ctx:
            errors.append(f"{source}[{idx}]: missing @context")
        elif "schema.org" not in str(ctx):
            warnings.append(f"{source}[{idx}]: @context={ctx!r} (ожидаем schema.org)")

        item_type = item.get("@type")
        if not item_type:
            errors.append(f"{source}[{idx}]: missing @type")
            continue

        types = item_type if isinstance(item_type, list) else [item_type]
        for t in types:
            if type_filter and t != type_filter:
                continue
            required = REQUIRED_FIELDS.get(t, set())
            missing = required - set(item.keys())
            if missing:
                errors.append(f"{source}[{idx}] {t}: missing required: {sorted(missing)}")
            recommended = RECOMMENDED_FIELDS.get(t, set())
            rec_missing = recommended - set(item.keys())
            if rec_missing:
                warnings.append(f"{source}[{idx}] {t}: missing recommended: {sorted(rec_missing)}")

        # AggregateRating с фейковыми значениями
        if "aggregateRating" in item:
            ar = item["aggregateRating"]
            if isinstance(ar, dict):
                rv = ar.get("ratingValue")
                rc = ar.get("reviewCount") or ar.get("ratingCount")
                if rv and not rc:
                    warnings.append(f"{source}[{idx}]: aggregateRating без reviewCount/ratingCount — Google requires это")
                if rc and int(str(rc) or 0) < 1:
                    errors.append(f"{source}[{idx}]: aggregateRating.reviewCount={rc} (нужно >0; запрет фейков!)")

        # Обязательное reviewCount для Product
        if "Product" in types and "review" in item:
            review = item["review"]
            if isinstance(review, dict) and not review.get("reviewBody"):
                warnings.append(f"{source}[{idx}] Product.review: рекомендуется reviewBody")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=pathlib.Path)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--type")
    args = ap.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    blocks_total = 0

    for f in args.files:
        if not f.exists():
            print(f"⚠ {f}: не существует", file=sys.stderr)
            continue
        text = f.read_text(encoding="utf-8")
        if args.json_only:
            blocks_total += 1
            validate_block(text, args.type, errors, warnings, source=str(f))
        else:
            blocks = extract_jsonld(text)
            blocks_total += len(blocks)
            if not blocks:
                warnings.append(f"{f}: 0 JSON-LD блоков найдено")
            for line_num, body in blocks:
                validate_block(body, args.type, errors, warnings, source=f"{f}:L{line_num}")

    print(f"== schema-validate ==")
    print(f"  Files: {len(args.files)}")
    print(f"  JSON-LD blocks: {blocks_total}")
    print(f"  Errors: {len(errors)}, Warnings: {len(warnings)}")
    print()
    if errors:
        print("❌ ERRORS:")
        for e in errors:
            print(f"  - {e}")
        print()
    if warnings:
        print("⚠  WARNINGS:")
        for w in warnings[:30]:
            print(f"  - {w}")
        if len(warnings) > 30:
            print(f"  ... +{len(warnings)-30} more")
        print()
    if not errors and not warnings:
        print("✓ Все JSON-LD блоки валидны.")
    sys.exit(1 if errors or (args.strict and warnings) else 0)


if __name__ == "__main__":
    main()
