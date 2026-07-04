#!/usr/bin/env python3
"""Build review/comparison cluster candidates from real project inventory.

Inspired by the multi-page review-site framework, but guarded for seo-cycle:
no review page is recommended unless it can link to real categories, brands,
products, and evidence requirements. Projects can override seeds through
`seo/knowledge/review-cluster-seeds.json`.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from wiki_common import PROJECT_BRAND, WIKI_ROOT, ensure_wiki_tree, read_json, slugify, utc_now, write_json, write_jsonl


STOP_TOKENS = {
    "catalog",
    "category",
    "shop",
    "html",
    "page",
    "stranica",
    "товары",
    "купить",
    "каталог",
    "материалы",
    "раздел",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_cluster_seeds() -> list[dict[str, Any]]:
    custom = read_json(WIKI_ROOT.parent / "review-cluster-seeds.json", [])
    if isinstance(custom, list) and custom:
        return custom
    return []


def seed_tokens(*values: Any, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    text = " ".join(str(value or "") for value in values)
    for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9-]{3,}", text.lower()):
        token = token.strip("-")
        if not token or token in STOP_TOKENS or token in seen:
            continue
        seen.add(token)
        result.append(token)
        if len(result) >= limit:
            break
    return result


def build_auto_seeds(categories: list[dict[str, Any]], products: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for category in categories:
        title = category.get("title") or category.get("name") or category.get("slug") or ""
        tokens = seed_tokens(title, category.get("slug"), category.get("url"))
        if not title or not tokens:
            continue
        product_hits = select_rows(products, tokens, 30)
        if len(product_hits) < 2:
            continue
        seeds.append(
            {
                "id": f"auto-{slugify(str(title))}",
                "title": f"{title}: как выбрать под задачу и чем отличаются варианты",
                "category_tokens": tokens,
                "category_include_tokens": tokens,
                "brand_tokens": [],
                "intent": "choice/comparison",
                "page_type": "commercial_guide",
                "mandatory_angle": (
                    "сравнивать только реальные товары, категории и подтверждённые характеристики; "
                    "если упоминаются внешние аналоги, отделять их от ассортимента проекта и не писать голословное 'лучше'"
                ),
            }
        )
        if len(seeds) >= limit:
            break
    return seeds


def token_match(text: str, tokens: list[str]) -> bool:
    blob = text.lower()
    return any(token.lower() in blob for token in tokens)


def row_blob(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(key, "")) for key in ["title", "slug", "url", "sku", "h1"] + ["categories", "brands"])


def select_rows(rows: list[dict[str, Any]], tokens: list[str], limit: int) -> list[dict[str, Any]]:
    selected = [row for row in rows if token_match(row_blob(row), tokens)]
    return selected[:limit]


def select_categories(categories: list[dict[str, Any]], seed: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    include_tokens = seed.get("category_include_tokens") or seed.get("category_tokens", [])
    exclude_tokens = seed.get("exclude_category_tokens", [])
    selected: list[dict[str, Any]] = []
    for row in categories:
        blob = row_blob(row)
        if exclude_tokens and token_match(blob, exclude_tokens):
            continue
        if include_tokens and token_match(blob, include_tokens):
            selected.append(row)
    return selected[:limit]


def select_products(products: list[dict[str, Any]], seed: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    category_tokens = seed.get("category_tokens", [])
    brand_tokens = seed.get("brand_tokens", [])
    exclude_tokens = seed.get("exclude_product_tokens", [])
    for row in products:
        blob = row_blob(row)
        if exclude_tokens and token_match(blob, exclude_tokens):
            continue
        category_hit = token_match(blob, category_tokens)
        brand_hit = token_match(blob, brand_tokens) if brand_tokens else True
        if category_hit and brand_hit:
            selected.append(row)
    return selected[:limit]


def candidate(seed: dict[str, Any], categories: list[dict], brands: list[dict], products: list[dict], articles: list[dict]) -> dict[str, Any]:
    cats = select_categories(categories, seed, 8)
    prods = select_products(products, seed, 20)
    brs = select_rows(brands, seed.get("brand_tokens", []), 8)
    arts = select_rows(articles, seed["category_tokens"] + seed.get("brand_tokens", []), 8)
    evidence_ready = bool(cats and (brs or prods))
    missing = []
    if not cats:
        missing.append("category")
    if not brs:
        missing.append("brand")
    if not prods:
        missing.append("product")
    priority = "P0" if evidence_ready and len(prods) >= 3 else "P1" if evidence_ready else "blocked"
    return {
        "id": seed["id"],
        "title": seed["title"],
        "slug": slugify(seed["title"]),
        "priority": priority,
        "intent": seed["intent"],
        "page_type": seed["page_type"],
        "mandatory_angle": seed["mandatory_angle"],
        "categories": [{"title": row.get("title"), "url": row.get("url"), "slug": row.get("slug")} for row in cats],
        "brands": [{"title": row.get("title"), "url": row.get("url"), "slug": row.get("slug")} for row in brs],
        "products": [{"title": row.get("title"), "url": row.get("url"), "sku": row.get("sku")} for row in prods],
        "existing_articles": [{"title": row.get("title"), "url": row.get("url"), "slug": row.get("slug")} for row in arts],
        "external_analogs": seed.get("external_analog_tokens", []),
        "evidence_requirements": [
            f"карточки и категории {PROJECT_BRAND}",
            "инструкции/документы производителя для технических claims",
            "GSC/Яндекс/Keyword source для спроса",
            "link-gate перед публикацией",
            "content-taste-gate перед публикацией",
        ],
        "blocked_if_missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    ensure_wiki_tree()
    articles = read_jsonl(WIKI_ROOT / "state" / "articles.jsonl")
    categories = read_jsonl(WIKI_ROOT / "state" / "categories.jsonl")
    brands = read_jsonl(WIKI_ROOT / "state" / "brands.jsonl")
    products = read_jsonl(WIKI_ROOT / "state" / "products.jsonl")
    seeds = load_cluster_seeds()
    seed_source = "project_override" if seeds else "auto_inventory"
    if not seeds:
        seeds = build_auto_seeds(categories, products)
    rows = [candidate(seed, categories, brands, products, articles) for seed in seeds]
    payload = {
        "generated_at": utc_now(),
        "source_inspiration": "Teletype review-site framework adapted to real project inventory",
        "seed_source": seed_source,
        "policy": f"No comparison page without real {PROJECT_BRAND} inventory, source facts, link gate, and content taste gate.",
        "candidates": rows,
    }
    if args.write:
        out_json = WIKI_ROOT / "frameworks" / "review-clusters.json"
        out_jsonl = WIKI_ROOT / "frameworks" / "review-clusters.jsonl"
        write_json(out_json, payload)
        write_jsonl(out_jsonl, rows)
        lines = [
            "# Review / Comparison Cluster Plan",
            "",
            f"- Generated: `{payload['generated_at']}`",
            f"- Source: Teletype review-site approach, adapted for {PROJECT_BRAND}.",
            "- Rule: no page without real products/categories and source-backed facts.",
            "",
            "| Priority | Candidate | Type | Real products | Existing articles | Missing |",
            "|---|---|---|---:|---:|---|",
        ]
        for row in rows:
            lines.append(
                f"| {row['priority']} | {row['title']} | {row['page_type']} | {len(row['products'])} | {len(row['existing_articles'])} | {', '.join(row['blocked_if_missing']) or 'нет'} |"
            )
        lines.extend([
            "",
            "## Control Gates",
            "- `wiki-preflight.py` before writing.",
            "- `content-taste-gate.py` before publish.",
            "- `pre-publish-gate.py` before WordPress draft/update.",
            "- `wiki-decision-log.py` after decision or update.",
        ])
        (WIKI_ROOT / "frameworks" / "review-cluster-plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
