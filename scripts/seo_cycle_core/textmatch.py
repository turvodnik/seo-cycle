"""Light Russian-aware matching between core keywords and live search queries.

Exact string equality misses almost everything in Russian: живые запросы из
Вебмастера отличаются от ядра словоформой и порядком слов («купить минвату» vs
«минвата купить цена»). This module provides a conservative light stemmer and
a query index with three match levels:

  exact   — normalized strings are equal;
  stem    — the sorted stem-sets are equal (word order and inflection ignored);
  subset  — every stem of the keyword occurs in the query (только для ключей
            с ≥2 значимыми стемами). Позиция = МЕДИАНА по семейству
            кандидатов: min был бы позицией лучшего хвоста, а не ключа.

The stemmer trims only common nominal endings and keeps stems ≥3 chars, so
verbs («купить») and short terms («осп», «xps») pass through untouched.
False merges are possible («банк»/«банка») — accepted trade-off, документируется
потребителями в assumptions.
"""

from __future__ import annotations

import re
import statistics

TOKEN_RE = re.compile(r"[а-яёa-z0-9]+")
CYRILLIC_RE = re.compile(r"[а-яё]")

STOP_WORDS = frozenset(
    "в на с и для по из к от до у о за под над при про без же ли или а но как это".split()
)

# Nominal endings only, longest first; verbs and short words stay intact.
_SUFFIXES = (
    "иями", "ями", "ами", "иях", "иям", "ием", "ией",
    "ого", "его", "ому", "ему", "ыми", "ими",
    "ая", "яя", "ое", "ее", "ие", "ые", "ой", "ей", "ий", "ый",
    "ом", "ем", "ам", "ям", "ах", "ях", "ов", "ев", "ую", "юю",
    "а", "я", "о", "е", "и", "ы", "у", "ю", "ь",
)
_MIN_STEM = 3


def normalize_phrase(text: str) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def stem_token(token: str) -> str:
    if not CYRILLIC_RE.search(token):
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= _MIN_STEM:
            return token[: -len(suffix)]
    return token


def phrase_key(text: str) -> tuple[str, ...]:
    """Sorted unique stems of the significant words of a phrase."""
    tokens = TOKEN_RE.findall(normalize_phrase(text))
    significant = [token for token in tokens if token not in STOP_WORDS] or tokens
    return tuple(sorted({stem_token(token) for token in significant}))


def build_query_index(positions: dict[str, float]) -> dict[str, object]:
    """Index live query→position pairs for the three match levels."""
    exact: dict[str, float] = {}
    by_key: dict[tuple[str, ...], float] = {}
    by_stem: dict[str, set[tuple[str, ...]]] = {}
    for query, position in positions.items():
        normalized = normalize_phrase(query)
        if not normalized:
            continue
        if normalized not in exact or position < exact[normalized]:
            exact[normalized] = position
        key = phrase_key(normalized)
        if not key:
            continue
        if key not in by_key or position < by_key[key]:
            by_key[key] = position
        for stem in key:
            by_stem.setdefault(stem, set()).add(key)
    return {"exact": exact, "by_key": by_key, "by_stem": by_stem}


def match_position(keyword: str, index: dict[str, object]) -> tuple[float | None, str]:
    """Resolve a core keyword to a live position: (position, kind) or (None, '')."""
    exact: dict[str, float] = index["exact"]  # type: ignore[assignment]
    by_key: dict[tuple[str, ...], float] = index["by_key"]  # type: ignore[assignment]
    by_stem: dict[str, set[tuple[str, ...]]] = index["by_stem"]  # type: ignore[assignment]

    normalized = normalize_phrase(keyword)
    if normalized in exact:
        return exact[normalized], "exact"
    key = phrase_key(normalized)
    if not key:
        return None, ""
    if key in by_key:
        return by_key[key], "stem"
    if len(key) >= 2:
        candidate_sets = [by_stem.get(stem) for stem in key]
        if all(candidate_sets):
            candidates = set.intersection(*candidate_sets)  # type: ignore[arg-type]
            if candidates:
                return statistics.median(by_key[candidate] for candidate in candidates), "subset"
    return None, ""
