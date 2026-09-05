"""Context-manifest helpers for token-efficient SEO work."""

from __future__ import annotations

from typing import Any

from .config import coerce_int


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
            "max_raw_rows_loaded": coerce_int(
                caps.get("max_raw_rows_loaded", 200), 200, name="context_contract.caps.max_raw_rows_loaded"
            ),
            "distillate_max_lines": coerce_int(
                caps.get("distillate_max_lines", 220), 220, name="context_contract.caps.distillate_max_lines"
            ),
            "browser_session_budget_minutes": coerce_int(
                caps.get("browser_session_budget_minutes", 20), 20,
                name="context_contract.caps.browser_session_budget_minutes",
            ),
            "browser_pages_per_phase_cap": coerce_int(
                caps.get("browser_pages_per_phase_cap", 20), 20,
                name="context_contract.caps.browser_pages_per_phase_cap",
            ),
        },
        "sources": sources or [],
        "outputs": outputs,
        "load_only": ["distillates", "top-N summaries", "specific rows/URLs required for the current task"],
    }

