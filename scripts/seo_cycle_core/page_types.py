"""One vocabulary of page types for the draft gate and the brand-voice profile (3.1.0).

Outlines carry free-form `page_type` values from the research package
(«Guide», «Category», «Сравнение», «Tool/App», …). The draft gate needs them
for `quality_gates.word_count_min.{blog_post,category,landing}`, and the
brand-voice profile keys its writing methods and visual types by page type.
"""

from __future__ import annotations

from typing import Any

PAGE_TYPES = ("article", "category", "product", "landing", "comparison", "howto", "tool")

# Ordered: the first rule whose marker occurs in the lowercased value wins
# («product category» is a category page, «how to compare» is a comparison).
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Value is padded with spaces, so " app " is the whole word «app».
    ("tool", (" tool", "tool/", "/tool", " app ", "app/", "/app", "quiz", "analyzer", "webapplication",
              "calculator", "калькулятор")),
    ("category", ("categor", "категор", "catalog", "каталог", "collection", "listing", "раздел")),
    ("comparison", ("compar", "сравн", " vs", "vs.", "versus", "alternative", "альтернатив", "рейтинг", "top-", "топ-")),
    ("product", ("product", "товар", "карточк", "sku")),
    ("landing", ("landing", "лендинг", "посадочн", "service", "услуг", "homepage", "главн", "pricing", "тариф")),
    ("howto", ("how-to", "howto", "how to", "инструкц", "пошаг", "как сделать", "tutorial")),
)

# Word-count buckets of `quality_gates.word_count_min` in the config template.
_BUCKETS = {
    "category": "category",
    "product": "category",
    "landing": "landing",
    "tool": "landing",
}


def normalize_page_type(raw: Any) -> str:
    """Map a free-form page type onto PAGE_TYPES; anything else is an article."""
    value = f" {str(raw or '').strip().lower()} "
    if value.strip() in PAGE_TYPES:
        return value.strip()
    for page_type, markers in _RULES:
        if any(marker in value for marker in markers):
            return page_type
    return "article"


def word_count_bucket(page_type: Any) -> str:
    """`blog_post` | `category` | `landing` — the keys of `quality_gates.word_count_min`."""
    return _BUCKETS.get(normalize_page_type(page_type), "blog_post")


def is_article_like(page_type: Any) -> bool:
    """Pages where `images.inline_min_per_post` applies (posts, guides, how-tos, comparisons)."""
    return normalize_page_type(page_type) in {"article", "howto", "comparison"}
