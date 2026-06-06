"""Context-manifest helpers for token-efficient SEO work."""

from __future__ import annotations

from typing import Any


RAW_PATTERNS = (
    "raw API JSON",
    "browser dumps",
    "full CSV exports",
    "full sitemap URL lists",
    "raw logs",
    "full transcripts",
)


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def build_context_manifest(
    *,
    read_first: list[str],
    do_not_load_raw: list[str],
    outputs: dict[str, str],
    caps: dict[str, Any],
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "read_first": unique(read_first),
        "blocked_raw_artifacts": unique(do_not_load_raw + list(RAW_PATTERNS)),
        "source_caps": {
            "raw_data_in_context": bool(caps.get("raw_data_in_context", False)),
            "cache_first": bool(caps.get("cache_first", True)),
            "max_raw_rows_loaded": int(caps.get("max_raw_rows_loaded", 200) or 200),
            "distillate_max_lines": int(caps.get("distillate_max_lines", 220) or 220),
            "browser_session_budget_minutes": int(caps.get("browser_session_budget_minutes", 20) or 20),
            "browser_pages_per_phase_cap": int(caps.get("browser_pages_per_phase_cap", 20) or 20),
        },
        "sources": sources or [],
        "outputs": outputs,
        "load_only": ["distillates", "top-N summaries", "specific rows/URLs required for the current task"],
    }

