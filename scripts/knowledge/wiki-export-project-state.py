#!/usr/bin/env python3
"""Export current project state into seo/knowledge/wiki.

Read-only against WordPress. Writes local wiki snapshots:
  - articles, categories, brands, products
  - project manifest
  - link graph
  - compact state summary
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from wiki_common import (
    CONFIG,
    PROJECT_DOMAIN,
    PROJECT_BRAND,
    PROJECT_NAME,
    PROJECT_SLUG,
    OBSIDIAN_ROOT,
    WIKI_ROOT,
    canonical_url,
    clean_text,
    ensure_wiki_tree,
    frontmatter,
    load_env,
    parse_html,
    public_content_from_record,
    slugify,
    title_from_record,
    utc_now,
    wp_config,
    wp_get_all,
    write_json,
    write_jsonl,
)


PROJECT_RULES = [
    f"Публичное написание бренда: {PROJECT_BRAND}.",
    "Не писать про наличие, остатки и цены как постоянный факт.",
    "Не трогать визуальный builder-контент, если проектная политика разрешает только meta/ACF/SEO-поля.",
    "Страницы с трафиком не переписывать полностью без refresh brief с аналитикой, источниками и рисками.",
    "У категорий разделять H1, краткое описание, SEO-текст, FAQ и CTA; не смешивать служебные инструкции с публичным текстом.",
    "FAQ и CTA хранить в тех полях CMS, которые заданы в проектной политике.",
    "Старую проиндексированную статью не переписывать полностью без brief с GSC/Яндекс/источниками и рисками.",
    "Внутренние ссылки должны быть анкорными, без видимых URL/slug в тексте.",
    "Публичный текст не должен содержать служебные слова: интент, семантика, SEO-текст, source-lock, карточка товара.",
]


def record_html(record: dict[str, Any]) -> str:
    content = record.get("content")
    if isinstance(content, dict):
        return content.get("rendered") or content.get("raw") or ""
    return str(content or "")


def term_html(term: dict[str, Any]) -> str:
    acf = term.get("acf") if isinstance(term.get("acf"), dict) else {}
    return "\n".join(
        str(value or "")
        for value in [
            term.get("description", ""),
            acf.get("product_category_description", ""),
            acf.get("cta_text_category_product", ""),
            json.dumps(acf.get("faq_product_category", []), ensure_ascii=False),
        ]
    )


def summarize_page(record: dict[str, Any], entity_type: str) -> dict[str, Any]:
    html_value = record_html(record)
    parser = parse_html(html_value)
    acf = record.get("acf") if isinstance(record.get("acf"), dict) else {}
    return {
        "type": entity_type,
        "wp_id": record.get("id"),
        "slug": record.get("slug"),
        "status": record.get("status", ""),
        "title": title_from_record(record),
        "url": canonical_url(record.get("link", "")),
        "modified": record.get("modified", ""),
        "word_count": len(re.findall(r"\w+", parser.text, flags=re.U)),
        "heading_count": len(parser.headings),
        "link_count": len(parser.links),
        "image_count": len(parser.images),
        "faq_count": len(acf.get("faq_v_postah") or []) if entity_type == "blog" else 0,
        "cta_present": bool(acf.get("cta_text_post") or acf.get("cta_text_category_product")),
        "headings": parser.headings,
        "links": parser.links,
        "images": parser.images,
    }


def summarize_term(term: dict[str, Any], taxonomy: str) -> dict[str, Any]:
    html_value = term_html(term)
    parser = parse_html(html_value)
    acf = term.get("acf") if isinstance(term.get("acf"), dict) else {}
    faq = acf.get("faq_product_category")
    return {
        "type": taxonomy,
        "wp_id": term.get("id"),
        "slug": term.get("slug"),
        "title": term.get("name", ""),
        "url": canonical_url(term.get("link", "")),
        "count": term.get("count", 0),
        "description_chars": len(clean_text(term.get("description", ""))),
        "seo_text_chars": len(clean_text(acf.get("product_category_description", ""))),
        "faq_count": len(faq) if isinstance(faq, list) else 0,
        "cta_present": bool(acf.get("cta_text_category_product")),
        "h1": acf.get("h1_title_category_product", ""),
        "links": parser.links,
        "headings": parser.headings,
    }


def write_entity_note(folder: Path, entity: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    slug = str(entity.get("slug") or slugify(entity.get("url", "")))
    fm = frontmatter(
        {
            "type": entity.get("type"),
            "wp_id": entity.get("wp_id"),
            "slug": slug,
            "url": entity.get("url", ""),
            "status": entity.get("status", ""),
            "updated": utc_now(),
        }
    )
    headings = "\n".join(f"- {h.get('level')}: {h.get('text')}" for h in entity.get("headings", [])) or "- нет"
    links = "\n".join(f"- [{l.get('anchor') or l.get('href')}]({l.get('href')})" for l in entity.get("links", [])) or "- нет"
    body = f"""{fm}
# {entity.get('title') or slug}

## Snapshot
- URL: {entity.get('url', '')}
- WordPress ID: `{entity.get('wp_id')}`
- Type: `{entity.get('type')}`
- Status: `{entity.get('status', '')}`
- Words: `{entity.get('word_count', 0)}`
- FAQ count: `{entity.get('faq_count', 0)}`
- CTA present: `{entity.get('cta_present', False)}`

## Headings
{headings}

## Links
{links}
"""
    (folder / f"{slug}.md").write_text(body, encoding="utf-8")


def write_rules() -> None:
    rules_md = WIKI_ROOT / "rules" / "project-rules.md"
    lines = [
        f"# Правила проекта {PROJECT_NAME}",
        "",
        "Эти правила являются preflight-источником перед публикацией, обновлением статьи, категории, бренда или страницы.",
        "",
    ]
    lines.extend(f"- {rule}" for rule in PROJECT_RULES)
    rules_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    (WIKI_ROOT / "rules" / "lean-engineering.md").write_text(
        """# Lean Engineering Guardrail

Правило из Ponytail-подхода: сначала проверяем, нужен ли новый код вообще.

Перед добавлением нового скрипта или интеграции:
- можно ли решить существующим скриптом;
- можно ли использовать стандартную библиотеку;
- можно ли использовать уже подключенный API/экспорт;
- не дублирует ли новая функция `seo-cycle` или WordPress REST;
- есть ли clear upgrade path, если сейчас делаем минимальный вариант.

Безопасность, сохранность данных, бэкапы, права доступа и качество текста не урезаются ради краткости.
""",
        encoding="utf-8",
    )

    (WIKI_ROOT / "rules" / "content-taste.md").write_text(
        """# Content Taste Gate

Публичный текст должен звучать как работа редактора и специалиста по строительным материалам, а не как служебный SEO-brief.

Запрещено в публичном тексте:
- интент, семантика, сущности, SEO-текст, source-lock;
- служебные пояснения о том, что и зачем мы оптимизируем;
- голые URL и slug вместо анкорных ссылок;
- постоянные утверждения о наличии, остатках и ценах;
- голословное сравнение "лучше конкурента" без фактов.

Нужно:
- практические применения;
- аккуратные ограничения;
- факты, ГОСТ/классы/инструкции производителя только когда подтверждены;
- таблицы и FAQ там, где они реально помогают выбору;
- CTA по задаче пользователя, а не шаблонная продажа.
""",
        encoding="utf-8",
    )


def main() -> int:
    ensure_wiki_tree()
    env = load_env()
    generated_at = utc_now()
    try:
        base, auth = wp_config(env)
    except SystemExit:
        base, auth = "", None

    if base:
        blogs = wp_get_all(base, "blog", auth, {"context": "edit", "status": "any"})
        categories = wp_get_all(base, "product_cat", auth, {"context": "edit"})
        brands = wp_get_all(base, "product_brand", auth, {"context": "edit"})
        products = wp_get_all(base, "product", auth, {"context": "edit", "status": "any"})
    else:
        blogs, categories, brands, products = [], [], [], []

    article_rows = [summarize_page(record, "blog") for record in blogs]
    category_rows = [summarize_term(record, "product_cat") for record in categories]
    brand_rows = [summarize_term(record, "product_brand") for record in brands]
    product_rows = [
        {
            "type": "product",
            "wp_id": product.get("id"),
            "slug": product.get("slug"),
            "status": product.get("status", ""),
            "title": title_from_record(product),
            "url": canonical_url(product.get("permalink") or product.get("link", "")),
            "sku": product.get("sku", ""),
            "catalog_visibility": product.get("catalog_visibility", ""),
            "categories": [item.get("name") for item in product.get("categories", [])],
            "brands": [item.get("name") for item in product.get("brands", [])] if isinstance(product.get("brands"), list) else [],
        }
        for product in products
    ]

    for row in article_rows:
        write_entity_note(WIKI_ROOT / "articles", row)
    for row in category_rows:
        write_entity_note(WIKI_ROOT / "categories", row)
    for row in brand_rows:
        write_entity_note(WIKI_ROOT / "brands", row)

    write_jsonl(WIKI_ROOT / "state" / "articles.jsonl", article_rows)
    write_jsonl(WIKI_ROOT / "state" / "categories.jsonl", category_rows)
    write_jsonl(WIKI_ROOT / "state" / "brands.jsonl", brand_rows)
    write_jsonl(WIKI_ROOT / "state" / "products.jsonl", product_rows)

    link_rows = []
    for source in article_rows + category_rows + brand_rows:
        for link in source.get("links", []):
            href = link.get("href", "")
            if href.startswith("/") or PROJECT_DOMAIN in urlparse_safe(href):
                link_rows.append(
                    {
                        "source_type": source.get("type"),
                        "source_slug": source.get("slug"),
                        "source_url": source.get("url"),
                        "anchor": link.get("anchor", ""),
                        "target": canonical_url(href),
                    }
                )
    write_jsonl(WIKI_ROOT / "state" / "internal-links.jsonl", link_rows)

    status_counter = Counter(row.get("status") for row in article_rows)
    manifest = {
        "project": PROJECT_SLUG,
        "project_name": PROJECT_NAME,
        "brand": PROJECT_BRAND,
        "domain": PROJECT_DOMAIN,
        "generated_at": generated_at,
        "source": "WordPress REST + local SEO artifacts" if base else "local SEO artifacts; WordPress REST not configured",
        "counts": {
            "blog_articles": len(article_rows),
            "blog_status": dict(status_counter),
            "product_categories": len(category_rows),
            "product_brands": len(brand_rows),
            "products": len(product_rows),
            "internal_links": len(link_rows),
        },
        "rules": PROJECT_RULES,
        "paths": {
            "wiki": str(WIKI_ROOT),
            "obsidian": str(OBSIDIAN_ROOT),
            "state": str(WIKI_ROOT / "state"),
            "reports": str(WIKI_ROOT / "reports"),
        },
    }
    write_json(WIKI_ROOT / "project-manifest.json", manifest)
    write_rules()

    index_lines = [
        f"# {PROJECT_NAME} SEO Knowledge Wiki",
        "",
        f"- Generated: `{generated_at}`",
        f"- Blog articles: `{len(article_rows)}`",
        f"- Categories: `{len(category_rows)}`",
        f"- Brands: `{len(brand_rows)}`",
        f"- Products: `{len(product_rows)}`",
        "",
        "## Быстрые входы",
        "- [Правила проекта](rules/project-rules.md)",
        "- [Content Taste Gate](rules/content-taste.md)",
        "- [Lean Engineering Guardrail](rules/lean-engineering.md)",
        "- [State summary](state/latest-summary.md)",
        "- [Reports](reports/)",
        "- [Preflight](preflight/)",
        "- [Graphify comparison](frameworks/graphify-comparison.md)",
        "- [Review cluster plan](frameworks/review-cluster-plan.md)",
        "- [Knowledge Hub implementation plan](frameworks/knowledge-hub-implementation-plan.md)",
        "- [Taste Skill adaptation](frameworks/taste-skill-adaptation.md)",
        "- [LLM Wiki workflow](frameworks/llm-wiki-workflow.md)",
        "- [zvec pilot](frameworks/zvec-pilot.md)",
        "- [API catalog](api-catalog/README.md)",
        "- [Not yet implemented](backlog/not-yet-implemented.md)",
        "",
        "## Knowledge Flow",
        "",
        "1. `bash ./.codex/skills/seo-cycle/scripts/knowledge/wiki-refresh-all.sh` — обновляет wiki из WordPress и локальных отчётов.",
        "2. `python3 ./.codex/skills/seo-cycle/scripts/knowledge/wiki-preflight.py` — проверяет дубли, правила проекта и риски перед правкой.",
        "3. `python3 ./.codex/skills/seo-cycle/scripts/knowledge/wiki-context-pack.py` — даёт компактный контекст вместо чтения raw-артефактов.",
        "4. `python3 ./.codex/skills/seo-cycle/scripts/knowledge/review-cluster-plan.py --write` — строит comparison/review-кандидаты только по реальным товарам и категориям.",
        "5. `python3 ./.codex/skills/seo-cycle/scripts/knowledge/zvec-hybrid-index.py --build --write` — обновляет локальный hybrid/FTS индекс для поиска по wiki/vector.",
        "6. `bash ./.codex/skills/seo-cycle/scripts/knowledge/graphify-refresh.sh` — собирает curated corpus и строит Graphify-граф автоматически.",
        "",
        "## Graphify Auto Refresh",
        "",
        "Одна штатная команда:",
        "",
        "```bash",
        "cd /path/to/project",
        "bash ./.codex/skills/seo-cycle/scripts/knowledge/graphify-refresh.sh",
        "```",
        "",
        "Что она делает сама:",
        "",
        "1. обновляет wiki из WordPress и локальных SEO-артефактов;",
        "2. собирает безопасный curated corpus в `seo/knowledge/graph-corpus/`;",
        "3. проверяет `agy` и, если Antigravity CLI авторизован, строит semantic overlay через OAuth без API-ключа;",
        "4. если `agy` недоступен, пробует старый `gemini` CLI;",
        "5. если CLI недоступны, пробует API backend из env;",
        "6. если нет ни CLI, ни API, строит локальный wiki/vector graph без LLM;",
        "7. после успешной сборки обновляет `graph.json`, `GRAPH_REPORT.md`, `GRAPH_TREE.html` и `graphify-status.json`.",
        "",
        "По умолчанию Antigravity-режим берёт 35 приоритетных файлов. Для полного semantic-прогона:",
        "",
        "```bash",
        "GRAPHIFY_ANTIGRAVITY_ARGS=\"--max-files 0 --max-chars 26000 --per-file-chars 5000 --timeout 150\" bash ./.codex/skills/seo-cycle/scripts/knowledge/graphify-refresh.sh",
        "```",
        "",
        "Graphify не запускается по корню проекта. Используется только curated corpus: `seo/knowledge/graph-corpus/`.",
        "",
    ]
    (WIKI_ROOT / "README.md").write_text("\n".join(index_lines), encoding="utf-8")

    summary_lines = [
        "# Latest State Summary",
        "",
        f"- Generated: `{generated_at}`",
        f"- Blog articles: `{len(article_rows)}`",
        f"- Published blog articles: `{status_counter.get('publish', 0)}`",
        f"- Draft blog articles: `{status_counter.get('draft', 0)}`",
        f"- Product categories: `{len(category_rows)}`",
        f"- Product brands: `{len(brand_rows)}`",
        f"- Products: `{len(product_rows)}`",
        f"- Internal links captured: `{len(link_rows)}`",
        "",
        "## Next Use",
        "- перед обновлением статьи: `wiki-preflight.py --url <url>`",
        "- перед публикацией: `wiki-context-pack.py --topic <topic>`",
        "- перед публикацией через WP: `pre-publish-gate.py <file> --write`",
        "- для графа связей: `graphify-refresh.sh`",
        "- после отчёта: `wiki-ingest-report.py <path>`",
    ]
    (WIKI_ROOT / "state" / "latest-summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(json.dumps({"status": "ok", "wiki": str(WIKI_ROOT), "manifest": manifest["counts"]}, ensure_ascii=False, indent=2))
    return 0


def urlparse_safe(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
