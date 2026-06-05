#!/usr/bin/env python3
"""
obsidian-sync.py — one-shot конвертер артефактов проекта в Obsidian vault.

Создаёт структурированный vault со всеми контентом проекта:
- Entities/ — каждая сущность из entities.yaml = отдельный .md
- Stock/{Brands,Categories,SKUs}/ — складские позиции из stock-inventory.yaml
- Content/{Articles,Categories,Brands,Pages}/ — копии всего user-facing контента
- Research/{Perplexity,ATP,LLM-CLI}/ — результаты исследований
- Cycles/<topic>-<quarter>/ — снапшоты SEO-циклов
- _Dashboards/ — Dataview-дашборды (Stock, Pipeline, Quality)
- _Inbox/ — пустое место для черновиков и заметок

Wiki-link enrichment: упоминания зарегистрированных сущностей в скопированных
файлах оборачиваются в [[wiki-links]] для построения графа в Obsidian.

Использование:
    # Из корня проекта (читает seo-cycle.yaml)
    python3 ~/.codex/skills/seo-cycle/scripts/obsidian-sync.py

    # С указанием конфига и vault
    python3 obsidian-sync.py --config ./seo-cycle.yaml --vault ./obsidian-vault

    # Только сухой прогон — показать что будет создано
    python3 obsidian-sync.py --dry-run

Опции:
    --rebuild      Удалить vault и создать с нуля (по умолчанию — incremental)
    --no-links     Не оборачивать упоминания сущностей в [[wiki-links]]
    --verbose      Показать каждый файл при копировании
"""

from __future__ import annotations
import argparse, os, pathlib, re, shutil, sys
from datetime import date

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. pip3 install pyyaml", file=sys.stderr)
    sys.exit(2)


def safe_filename(s: str) -> str:
    """Превращает строку в безопасное имя файла Obsidian."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    s = s.strip().strip(".")
    return s[:200] or "untitled"


def find_config(start: pathlib.Path) -> pathlib.Path | None:
    for rel in ("seo-cycle.yaml", ".seo-cycle.yaml", "seo/seo-cycle.yaml", ".claude/seo-cycle.yaml"):
        p = start / rel
        if p.exists():
            return p
    return None


def ensure_dir(p: pathlib.Path):
    p.mkdir(parents=True, exist_ok=True)


def write(p: pathlib.Path, content: str):
    ensure_dir(p.parent)
    p.write_text(content, encoding="utf-8")


def wrap_wiki_links(text: str, entity_names: list[str]) -> str:
    """Обворачивает упоминания зарегистрированных сущностей в [[wiki-links]].

    Не трогает уже существующие [[ссылки]], URL, code-блоки, frontmatter.
    """
    if not entity_names:
        return text

    # Защищённые зоны — заменяем на placeholder перед обработкой
    protected = []
    def protect(m):
        protected.append(m.group(0))
        return f"__PROTECTED_{len(protected)-1}__"

    patterns = [
        r'```.*?```',           # code fenced
        r'`[^`]+`',             # inline code
        r'\[\[[^\]]+\]\]',      # existing wiki-links
        r'\[[^\]]+\]\([^)]+\)', # markdown links
        r'https?://\S+',        # URLs
        r'^---\s*$.*?^---\s*$', # frontmatter
    ]
    flags = [re.DOTALL, 0, 0, 0, 0, re.MULTILINE | re.DOTALL]
    for pat, fl in zip(patterns, flags):
        text = re.sub(pat, protect, text, flags=fl)

    # Сортируем по длине (длинные сначала, чтобы избежать частичных совпадений)
    sorted_entities = sorted(set(entity_names), key=len, reverse=True)
    for ent in sorted_entities:
        if len(ent) < 4:  # пропускаем короткие — много шума
            continue
        # word boundary с unicode
        pattern = rf"(?u)(?<![\w\[]){re.escape(ent)}(?![\w\]])"
        text = re.sub(pattern, f"[[{ent}]]", text, count=2)  # max 2 раза на файл

    # Восстанавливаем protected зоны
    for i, p in enumerate(protected):
        text = text.replace(f"__PROTECTED_{i}__", p, 1)

    return text


def render_entity(slug: str, data: dict) -> str:
    """Рендерит одну сущность в Obsidian-friendly markdown."""
    name = data.get("name") or slug
    aliases = data.get("aliases", [])
    e_type = data.get("type", "unknown")
    desc = data.get("description", "")
    attrs = data.get("attributes", {})
    related = data.get("related", [])
    sources = data.get("sources", [])

    lines = [
        "---",
        f"aliases: {aliases}",
        f"type: {e_type}",
        f"updated: {date.today().isoformat()}",
        "tags: [entity]",
        "---",
        "",
        f"# {name}",
        "",
        f"**Тип:** {e_type}",
        "",
        f"## Описание",
        "",
        desc or "_TBD_",
        "",
    ]
    if attrs:
        lines.append("## Атрибуты")
        lines.append("")
        lines.append("| Атрибут | Значение |")
        lines.append("|---|---|")
        for k, v in attrs.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")
    if related:
        lines.append("## Связанные сущности")
        lines.append("")
        for r in related:
            lines.append(f"- [[{r}]]")
        lines.append("")
    if sources:
        lines.append("## Источники")
        lines.append("")
        for s in sources:
            lines.append(f"- {s}")
        lines.append("")
    return "\n".join(lines)


def render_stock_brand(brand: dict) -> str:
    name = brand.get("name_user_facing") or brand["slug"]
    role = brand.get("role", "primary")
    badge = "🟢 на складе" if role == "primary" else "🟡 secondary" if role == "secondary" else "⚫ discontinued"
    lines = [
        "---",
        f"slug: {brand['slug']}",
        f"role: {role}",
        f"manufacturer: {brand.get('manufacturer','')}",
        f"updated: {date.today().isoformat()}",
        "tags: [stock, brand]",
        "---",
        "",
        f"# {name}",
        "",
        f"**Статус:** {badge}",
        "",
        f"**Производитель:** {brand.get('manufacturer','—')}",
        f"**Страна:** {brand.get('country','—')}",
        "",
    ]
    if brand.get("description"):
        lines += ["## Описание", "", brand["description"], ""]
    if brand.get("key_features"):
        lines += ["## Ключевые характеристики", ""] + [f"- {f}" for f in brand["key_features"]] + [""]
    if brand.get("categories"):
        lines += ["## Категории каталога", ""]
        for c in brand["categories"]:
            lines.append(f"- [[{c}]]")
        lines.append("")
    if brand.get("competitors_for_context"):
        lines += ["## Конкуренты (только для контекста — не на складе)", ""]
        for c in brand["competitors_for_context"]:
            lines.append(f"- {c}")
        lines.append("")
    return "\n".join(lines)


def render_stock_category(cat: dict, brand_lookup: dict[str, dict]) -> str:
    lines = [
        "---",
        f"slug: {cat['slug']}",
        f"url: {cat.get('url','')}",
        f"updated: {date.today().isoformat()}",
        "tags: [stock, category]",
        "---",
        "",
        f"# {cat.get('name', cat['slug'])}",
        "",
        f"**URL:** {cat.get('url','—')}",
        "",
        "## Складские бренды (primary)",
        "",
    ]
    for bs in cat.get("primary_brands", []):
        brand = brand_lookup.get(bs, {})
        name = brand.get("name_user_facing", bs)
        lines.append(f"- 🟢 [[{name}]] — рекомендованный/основной")
    if cat.get("secondary_brands"):
        lines += ["", "## Складские бренды (secondary)", ""]
        for bs in cat["secondary_brands"]:
            brand = brand_lookup.get(bs, {})
            name = brand.get("name_user_facing", bs)
            lines.append(f"- 🟡 [[{name}]]")
    if cat.get("competitors_for_context"):
        lines += ["", "## Конкуренты (для сравнительного контекста)", ""]
        for c in cat["competitors_for_context"]:
            lines.append(f"- {c}")
    if cat.get("notes"):
        lines += ["", "## Заметки", "", cat["notes"]]
    return "\n".join(lines)


def render_dashboard_stock() -> str:
    return """---
tags: [dashboard]
---

# 📦 Stock Dashboard

## Бренды на складе (primary)

```dataview
TABLE manufacturer, role
FROM "Stock/Brands"
WHERE role = "primary"
SORT file.name ASC
```

## Все категории и их складские бренды

```dataview
TABLE without id
  file.link as Категория,
  url
FROM "Stock/Categories"
SORT file.name ASC
```

## Secondary / discontinued

```dataview
TABLE manufacturer, role
FROM "Stock/Brands"
WHERE role != "primary"
SORT role
```
"""


def render_dashboard_pipeline() -> str:
    return """---
tags: [dashboard]
---

# 🔄 Content Pipeline

## Категории — состояние публикации

```dataview
TABLE without id
  file.link as Категория,
  status
FROM "Content/Categories"
SORT status ASC
```

## Статьи блога — drafts vs published

```dataview
TABLE without id
  file.link as Статья,
  status,
  published_url
FROM "Content/Articles"
SORT status ASC, file.mtime DESC
```

## Entity Maps по статусу

```dataview
TABLE without id
  file.link as "Entity Map",
  status,
  last_fact_check
FROM "Cycles" AND #entity-map
SORT status ASC
```
"""


def render_dashboard_quality() -> str:
    return """---
tags: [dashboard]
---

# ✅ Quality Dashboard

## Страницы со старым fact-check (>6 мес)

```dataview
TABLE without id
  file.link as Страница,
  last_fact_check
WHERE last_fact_check AND date(last_fact_check) < date(today) - dur(6 months)
SORT last_fact_check ASC
```

## Страницы без fact_check_log (нарушают правило №11)

```dataview
LIST FROM "Content" WHERE !fact_check_log
```

## Низкий NW score (<65)

```dataview
TABLE neuronwriter.content_score, neuronwriter.last_evaluated
FROM "Content" OR "Cycles"
WHERE neuronwriter.content_score < 65
SORT neuronwriter.content_score ASC
```
"""


def copy_with_links(src: pathlib.Path, dst: pathlib.Path, entity_names: list[str], add_links: bool):
    try:
        text = src.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  ⚠ не могу прочитать {src}: {e}", file=sys.stderr)
        return
    if add_links and src.suffix in (".md", ".markdown"):
        text = wrap_wiki_links(text, entity_names)
    write(dst, text)


def collect_entity_names(entities: dict, stock: dict) -> list[str]:
    """Собирает все имена и алиасы для wiki-link wrapping."""
    names = []
    for slug, data in (entities or {}).items():
        if isinstance(data, dict):
            name = data.get("name") or slug
            names.append(name)
            for a in data.get("aliases", []) or []:
                names.append(a)
    for brand in (stock or {}).get("brands", []) or []:
        names.append(brand.get("name_user_facing") or brand["slug"])
        names.append(brand.get("name_en") or "")
    for cat in (stock or {}).get("categories", []) or []:
        names.append(cat.get("name") or "")
    return [n for n in set(names) if n and len(n) > 3]


def sync(project_root: pathlib.Path, vault_root: pathlib.Path, cfg: dict, args):
    if args.rebuild and vault_root.exists():
        # Safety: не удалять если vault_root содержит .obsidian/ (т.е. это сам vault, а не project-subfolder)
        if (vault_root / ".obsidian").exists():
            print(f"⛔ ОТМЕНА --rebuild: {vault_root} содержит .obsidian/", file=sys.stderr)
            print(f"   Это похоже на корень Obsidian vault, а не на subfolder проекта.", file=sys.stderr)
            print(f"   Для централизованного паттерна укажи project_subfolder в конфиге.", file=sys.stderr)
            sys.exit(2)
        # Safety: vault_root должен быть глубже project_root или быть централизованным с subfolder
        if vault_root == project_root or vault_root == pathlib.Path("/"):
            print(f"⛔ ОТМЕНА --rebuild: vault_root={vault_root} слишком близко к корню", file=sys.stderr)
            sys.exit(2)
        shutil.rmtree(vault_root)
        print(f"🗑  Removed existing project subfolder: {vault_root}")

    ensure_dir(vault_root)

    # Загружаем entities.yaml — поддерживаем два формата:
    # 1) Плоский: {slug1: {name, ...}, slug2: {name, ...}}
    # 2) Категоризованный: {materials: [{slug, name}, ...], brands: [...], ...}
    entities_path = pathlib.Path(cfg.get("artifacts", {}).get("entities_root", "./seo/entities")) / "entities.yaml"
    if not entities_path.is_absolute():
        entities_path = project_root / entities_path
    entities: dict = {}
    if entities_path.exists():
        try:
            raw = yaml.safe_load(entities_path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict) and "entities" in raw:
                raw = raw["entities"]
            if isinstance(raw, dict):
                meta_keys = ("meta", "_meta", "schema", "version")
                category_keys = ("materials", "brands", "constructions", "locations", "services",
                                 "products", "topics", "people", "organizations")
                # Категоризованный формат: top-key содержит либо list of entity-dicts,
                # либо dict-of-dicts (slug → entity-data).
                is_categorized = any(
                    k in raw and isinstance(raw[k], (list, dict)) and k not in meta_keys
                    and (isinstance(raw[k], list) or all(isinstance(v, dict) for v in raw[k].values()))
                    for k in category_keys
                )
                if is_categorized:
                    for cat, items in raw.items():
                        if cat in meta_keys:
                            continue
                        entity_type = cat[:-1] if cat.endswith("s") else cat
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict) and item.get("slug"):
                                    item.setdefault("type", entity_type)
                                    entities[item["slug"]] = item
                        elif isinstance(items, dict):
                            for slug, data in items.items():
                                if isinstance(data, dict):
                                    data.setdefault("type", entity_type)
                                    data.setdefault("name", data.get("name") or slug)
                                    entities[slug] = data
                else:
                    # Плоский формат
                    entities = {k: v for k, v in raw.items() if k not in meta_keys and isinstance(v, dict)}
        except Exception as e:
            print(f"⚠ entities.yaml: {e}", file=sys.stderr)

    # Загружаем stock-inventory.yaml
    stock_path = cfg.get("content_rules", {}).get("stock_first", {}).get("inventory_file", "./seo/stock-inventory.yaml")
    sp = pathlib.Path(stock_path)
    if not sp.is_absolute():
        sp = project_root / sp
    stock = {}
    if sp.exists():
        try:
            stock = yaml.safe_load(sp.read_text(encoding="utf-8")) or {}
        except Exception as e:
            print(f"⚠ stock-inventory.yaml: {e}", file=sys.stderr)

    entity_names = collect_entity_names(entities, stock)
    print(f"📚 Загружено {len(entities)} сущностей, {len((stock or {}).get('brands', []))} брендов, {len(entity_names)} имён для wiki-links")

    # Создаём базовую структуру
    for sub in ("_Inbox", "_Dashboards", "Entities", "Stock/Brands", "Stock/Categories", "Stock/SKUs",
                "Content/Articles", "Content/Categories", "Content/Brands", "Content/Pages",
                "Research/Perplexity", "Research/ATP", "Research/LLM-CLI", "Cycles"):
        ensure_dir(vault_root / sub)

    counts = {"entities": 0, "brands": 0, "categories_stock": 0, "skus": 0,
              "articles": 0, "categories_content": 0, "brand_pages": 0, "wp_pages": 0,
              "research": 0, "cycles": 0}

    # 1. Сущности
    for slug, data in entities.items() if isinstance(entities, dict) else []:
        if not isinstance(data, dict):
            continue
        name = safe_filename(data.get("name") or slug)
        path = vault_root / "Entities" / f"{name}.md"
        if not args.dry_run:
            write(path, render_entity(slug, data))
        counts["entities"] += 1

    # 2. Stock inventory
    brand_lookup = {b["slug"]: b for b in (stock.get("brands") or []) if isinstance(b, dict)}
    for brand in stock.get("brands", []) or []:
        if not isinstance(brand, dict):
            continue
        name = safe_filename(brand.get("name_user_facing") or brand["slug"])
        path = vault_root / "Stock/Brands" / f"{name}.md"
        if not args.dry_run:
            write(path, render_stock_brand(brand))
        counts["brands"] += 1

    for cat in stock.get("categories", []) or []:
        if not isinstance(cat, dict):
            continue
        name = safe_filename(cat.get("name") or cat["slug"])
        path = vault_root / "Stock/Categories" / f"{name}.md"
        if not args.dry_run:
            write(path, render_stock_category(cat, brand_lookup))
        counts["categories_stock"] += 1

    for sku in stock.get("skus", []) or []:
        if not isinstance(sku, dict):
            continue
        name = safe_filename(sku.get("name") or sku["sku"])
        path = vault_root / "Stock/SKUs" / f"{name}.md"
        if not args.dry_run:
            lines = ["---", f"sku: {sku['sku']}", f"brand_slug: {sku.get('brand_slug','')}",
                     f"category_slug: {sku.get('category_slug','')}",
                     f"wp_product_id: {sku.get('wp_product_id','')}",
                     "tags: [stock, sku]", "---", "", f"# {sku.get('name', sku['sku'])}", ""]
            if sku.get("specifications"):
                lines += ["## Характеристики", "", "| Параметр | Значение |", "|---|---|"]
                for k, v in sku["specifications"].items():
                    lines.append(f"| {k} | {v} |")
            if sku.get("price_indicator"):
                lines += ["", f"**Цена (ориентир):** {sku['price_indicator']}"]
            if sku.get("url"):
                lines += ["", f"**URL:** [{sku['url']}]({sku['url']})"]
            write(path, "\n".join(lines))
        counts["skus"] += 1

    # 3. Контент: blog/, categories/, pages-service/
    add_links = not args.no_links
    arts = cfg.get("artifacts", {})

    for src_dir, vault_sub, counter in [
        (pathlib.Path(arts.get("drafts_root", "./blog")), "Content/Articles", "articles"),
        (pathlib.Path(arts.get("categories_root", "./categories")), "Content/Categories", "categories_content"),
        (pathlib.Path("./pages-service"), "Content/Pages", "wp_pages"),
        (pathlib.Path("./brands"), "Content/Brands", "brand_pages"),
    ]:
        sd = src_dir if src_dir.is_absolute() else (project_root / src_dir)
        if not sd.exists():
            continue
        for f in sd.rglob("*.md"):
            rel = f.relative_to(sd)
            dst = vault_root / vault_sub / rel
            if not args.dry_run:
                copy_with_links(f, dst, entity_names, add_links)
            if args.verbose:
                print(f"  {vault_sub}/ ← {rel}")
            counts[counter] += 1

    # 4. Research результаты
    research_root = pathlib.Path(arts.get("research_root", "./seo/research"))
    rr = research_root if research_root.is_absolute() else (project_root / research_root)
    if rr.exists():
        for f in rr.rglob("*.md"):
            rel = f.relative_to(rr)
            # Разделяем по подкаталогам — Perplexity, ATP, LLM-CLI
            parts = rel.parts
            if parts and parts[0].lower() in ("perplexity", "atp", "llm-cli"):
                vault_sub = f"Research/{ {'perplexity':'Perplexity','atp':'ATP','llm-cli':'LLM-CLI'}[parts[0].lower()] }"
                dst = vault_root / vault_sub / pathlib.Path(*parts[1:])
            else:
                dst = vault_root / "Research" / rel
            if not args.dry_run:
                copy_with_links(f, dst, entity_names, add_links)
            counts["research"] += 1

    # 5. Cycles
    cycles_root = pathlib.Path(arts.get("cycles_root", "./seo/cycles"))
    cr = cycles_root if cycles_root.is_absolute() else (project_root / cycles_root)
    if cr.exists():
        for f in cr.rglob("*.md"):
            rel = f.relative_to(cr)
            dst = vault_root / "Cycles" / rel
            if not args.dry_run:
                copy_with_links(f, dst, entity_names, add_links)
            counts["cycles"] += 1

    # 6. Дашборды
    if not args.dry_run:
        write(vault_root / "_Dashboards" / "Stock.md", render_dashboard_stock())
        write(vault_root / "_Dashboards" / "Pipeline.md", render_dashboard_pipeline())
        write(vault_root / "_Dashboards" / "Quality.md", render_dashboard_quality())

    # 7. README vault
    if not args.dry_run:
        write(vault_root / "_README.md", f"""---
tags: [vault-readme]
---

# {cfg.get('project',{}).get('name','Project')} — Obsidian Vault

Зеркало контента проекта в формате Obsidian.

## Структура

- **Entities/** — реестр сущностей (из `entities.yaml`)
- **Stock/** — складские позиции (из `stock-inventory.yaml`) — **источник истины для Stock-First**
  - **Brands/** — бренды на складе (🟢 primary, 🟡 secondary, ⚫ discontinued)
  - **Categories/** — категории каталога со связкой к брендам
  - **SKUs/** — отдельные товары (опционально)
- **Content/** — копии user-facing текстов (статьи, категории, страницы)
- **Research/** — результаты Perplexity / ATP / LLM-CLI
- **Cycles/** — снапшоты SEO-циклов
- **_Dashboards/** — Dataview-дашборды
- **_Inbox/** — черновики и заметки

## Обновление

Vault создаётся скриптом и **обновляется по запросу**:
```
python3 ~/.codex/skills/seo-cycle/scripts/obsidian-sync.py
```

Источник истины — **файлы проекта**, не vault. Изменения вручную в vault
будут перезаписаны при следующем sync (если не --no-overwrite).

## Граф

Открой Graph View в Obsidian (Cmd+G) — увидишь связи между сущностями,
брендами, статьями и категориями через [[wiki-links]].

## Дашборды

Требуют плагин **Dataview** (Settings → Community plugins → Dataview).
""")

    print()
    print("=== Obsidian sync result ===")
    print(f"  Vault: {vault_root}")
    print(f"  {'[DRY RUN] ' if args.dry_run else ''}Created:")
    for k, v in counts.items():
        if v > 0:
            print(f"    {k}: {v}")
    if not args.dry_run:
        print(f"\n✓ Done. Открой vault в Obsidian: открыть папку как vault → {vault_root}")
        print(f"  Установи плагин Dataview для работы дашбордов.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="Путь к seo-cycle.yaml")
    ap.add_argument("--vault", help="Путь к vault (по умолчанию из конфига или ./obsidian-vault)")
    ap.add_argument("--rebuild", action="store_true", help="Удалить vault перед созданием")
    ap.add_argument("--no-links", action="store_true", help="Не оборачивать в [[wiki-links]]")
    ap.add_argument("--dry-run", action="store_true", help="Показать что будет создано без записи")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    if args.config:
        cfg_path = pathlib.Path(args.config).resolve()
    else:
        cfg_path = find_config(pathlib.Path.cwd())
        if not cfg_path:
            print(f"ERROR: seo-cycle.yaml не найден в {pathlib.Path.cwd()}", file=sys.stderr)
            sys.exit(2)

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    project_root = cfg_path.parent
    if cfg_path.name in (".seo-cycle.yaml", "seo-cycle.yaml"):
        project_root = cfg_path.parent
    elif "/seo/" in str(cfg_path) or "/.claude/" in str(cfg_path):
        project_root = cfg_path.parent.parent

    # Резолвим vault_root с поддержкой централизованного паттерна.
    # Приоритет:
    #   1. --vault CLI override
    #   2. obsidian.central_vault + obsidian.project_subfolder
    #   3. obsidian.vault_root
    #   4. ./obsidian-vault (fallback)
    obs_cfg = cfg.get("obsidian", {}) or {}
    if args.vault:
        vault_root = pathlib.Path(os.path.expanduser(args.vault))
    elif obs_cfg.get("central_vault"):
        central = pathlib.Path(os.path.expanduser(obs_cfg["central_vault"]))
        subfolder = obs_cfg.get("project_subfolder") or cfg.get("project", {}).get("brand_name_technical") or "project"
        vault_root = central / subfolder
        if not central.exists():
            print(f"⚠ central_vault не существует: {central}", file=sys.stderr)
            print(f"  Создаю папку. Убедись что родительский каталог настроен как Obsidian vault (есть .obsidian/).", file=sys.stderr)
    else:
        vault_root = pathlib.Path(os.path.expanduser(obs_cfg.get("vault_root", "./obsidian-vault")))
    if not vault_root.is_absolute():
        vault_root = project_root / vault_root

    sync(project_root, vault_root, cfg, args)


if __name__ == "__main__":
    main()
