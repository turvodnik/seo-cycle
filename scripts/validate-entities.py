#!/usr/bin/env python3
"""
validate-entities.py — универсальный валидатор реестра сущностей seo-cycle.

Проверяет entities.yaml:
1. YAML парсится и имеет корректную структуру (категоризованный dict-of-dicts
   или list-of-dicts, либо плоский dict).
2. Каждая сущность имеет минимальный набор полей (default: name).
3. Cross-references (related, competitors, brands, applications, subtypes,
   produces, parent, primary_materials, primary_brands, secondary_brands)
   указывают на существующие slug-и.
4. URL-ы похожи на URL (если есть поля url, target_url).
5. Пути к файлам (entity_map, category_file, brand_file) существуют на диске
   (опционально, через --check-files).

Поддерживает два формата:
- Плоский: {slug: {name, type, ...}, ...}
- Категоризованный: {materials: {slug: {...}, ...}, brands: {...}, ...}

Использование:
    python3 validate-entities.py [path/to/entities.yaml]
    python3 validate-entities.py --strict        # warnings → errors
    python3 validate-entities.py --check-files   # проверять пути к файлам

Exit: 0 — чисто; 1 — есть ошибки; 2 — ошибка вызова.
"""

from __future__ import annotations
import argparse, pathlib, re, sys

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)


META_KEYS = {"meta", "_meta", "schema", "version"}
CATEGORY_KEYS = {"materials", "brands", "constructions", "locations", "services",
                 "products", "topics", "people", "organizations"}

# Поля которые могут содержать ссылки на другие slug-и
# synonyms НЕ здесь — это альтернативные имена самой сущности, не cross-ref
CROSS_REF_FIELDS = {
    "related", "competitors", "brands", "applications", "subtypes",
    "produces", "parent", "primary_materials", "primary_brands",
    "secondary_brands",
}

# Поля-пути к файлам — проверяются если --check-files
FILE_PATH_FIELDS = {"entity_map", "category_file", "brand_file"}

URL_RE = re.compile(r"^https?://", re.I)


def flatten_entities(raw: dict) -> dict[str, dict]:
    """Разворачивает категоризованную структуру в плоский {slug: entity}."""
    if not isinstance(raw, dict):
        return {}
    if "entities" in raw and isinstance(raw["entities"], dict):
        raw = raw["entities"]

    flat: dict[str, dict] = {}

    # Категоризованный формат (materials, brands, ...)
    is_categorized = any(
        k in raw and isinstance(raw[k], (dict, list)) and k not in META_KEYS
        for k in CATEGORY_KEYS
    )

    if is_categorized:
        for cat, items in raw.items():
            if cat in META_KEYS:
                continue
            entity_type = cat[:-1] if cat.endswith("s") else cat
            if isinstance(items, dict):
                for slug, data in items.items():
                    if not isinstance(data, dict):
                        continue
                    data.setdefault("type", entity_type)
                    data.setdefault("name", data.get("name") or slug)
                    flat[slug] = data
            elif isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("slug"):
                        item.setdefault("type", entity_type)
                        item.setdefault("name", item.get("name") or item["slug"])
                        flat[item["slug"]] = item
    else:
        flat = {k: v for k, v in raw.items() if k not in META_KEYS and isinstance(v, dict)}

    return flat


def validate_entity(slug: str, entity: dict, all_slugs: set[str],
                    project_root: pathlib.Path | None, check_files: bool,
                    errors: list, warnings: list):
    if not isinstance(entity, dict):
        errors.append(f"[{slug}] not a mapping (got {type(entity).__name__})")
        return

    # Обязательное поле name
    if not entity.get("name"):
        errors.append(f"[{slug}] missing required field: name")

    # Cross-references
    for field in CROSS_REF_FIELDS:
        if field not in entity:
            continue
        value = entity[field]
        refs = []
        if isinstance(value, list):
            refs = [v for v in value if isinstance(v, str)]
        elif isinstance(value, str):
            refs = [value]
        for ref in refs:
            if ref and ref not in all_slugs:
                warnings.append(f"[{slug}] {field} → {ref!r} — slug not found in registry")

    # URL fields
    for field in ("url", "target_url"):
        if field in entity and entity[field]:
            if not URL_RE.match(str(entity[field])):
                warnings.append(f"[{slug}] {field}={entity[field]!r} — does not look like URL")

    # File paths
    if check_files and project_root:
        for field in FILE_PATH_FIELDS:
            if field in entity and entity[field]:
                p = pathlib.Path(entity[field])
                if not p.is_absolute():
                    p = project_root / p
                if not p.exists():
                    warnings.append(f"[{slug}] {field}={entity[field]} — file does not exist")


def find_entities_file(start: pathlib.Path) -> pathlib.Path | None:
    candidates = [
        start / "entities.yaml",
        start / "seo/entities/entities.yaml",
        start / "seo/entities.yaml",
        start / ".claude/entities.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", type=pathlib.Path,
                    help="Путь к entities.yaml (default: автопоиск)")
    ap.add_argument("--strict", action="store_true", help="warnings → errors")
    ap.add_argument("--check-files", action="store_true", help="Проверять FILE_PATH_FIELDS на disk")
    args = ap.parse_args()

    if args.path:
        path = args.path.resolve()
    else:
        path = find_entities_file(pathlib.Path.cwd())
        if not path:
            print("ERROR: entities.yaml не найден. Передай путь явно.", file=sys.stderr)
            print("  Ожидаемые места: ./entities.yaml, ./seo/entities/entities.yaml", file=sys.stderr)
            sys.exit(2)

    if not path.exists():
        print(f"ERROR: {path} не существует", file=sys.stderr)
        sys.exit(2)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse error: {e}", file=sys.stderr)
        sys.exit(2)

    entities = flatten_entities(raw)
    if not entities:
        print(f"⚠ {path}: 0 entities loaded. Проверь формат файла.", file=sys.stderr)
        sys.exit(1)

    all_slugs = set(entities.keys())
    project_root = path.parent
    while project_root.parent != project_root and not (project_root / ".env").exists() \
          and not (project_root / "seo-cycle.yaml").exists():
        if project_root == project_root.parent:
            break
        project_root = project_root.parent

    errors: list[str] = []
    warnings: list[str] = []

    for slug, entity in entities.items():
        validate_entity(slug, entity, all_slugs, project_root, args.check_files, errors, warnings)

    # Дубликаты slug-ов невозможны в dict, но проверим имена
    name_to_slugs: dict[str, list[str]] = {}
    for slug, entity in entities.items():
        name = entity.get("name", "").strip().lower()
        if name:
            name_to_slugs.setdefault(name, []).append(slug)
    for name, slugs in name_to_slugs.items():
        if len(slugs) > 1:
            warnings.append(f"Duplicate name {name!r} → slugs: {slugs}")

    print(f"== entity validation ==")
    print(f"  File: {path}")
    print(f"  Entities loaded: {len(entities)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print()

    if errors:
        print("❌ ERRORS:")
        for e in errors:
            print(f"  - {e}")
        print()
    if warnings:
        print("⚠  WARNINGS:")
        for w in warnings[:50]:
            print(f"  - {w}")
        if len(warnings) > 50:
            print(f"  ... +{len(warnings)-50} more")
        print()

    if not errors and not warnings:
        print("✓ Реестр чист.")

    exit_code = 1 if errors or (args.strict and warnings) else 0
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
