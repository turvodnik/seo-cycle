"""Source artifact helpers for raw/distillate/vector research records."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
from typing import Any

from .config import write_text


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: Any, *, fallback: str = "item", max_length: int = 64) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"https?://", "", raw)
    raw = re.sub(r"[^a-z0-9а-яё]+", "-", raw, flags=re.IGNORECASE)
    raw = raw.strip("-")
    if not raw:
        raw = fallback
    return raw[:max_length].strip("-") or fallback


def stable_cache_key(parts: dict[str, Any] | list[Any] | tuple[Any, ...], *, label: str | None = None) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    if label is None:
        if isinstance(parts, dict):
            label = str(parts.get("topic") or parts.get("query") or parts.get("notebook_url") or "source")
        elif parts:
            label = str(parts[0])
        else:
            label = "source"
    return f"{slugify(label, fallback='source', max_length=48)}-{digest}"


def extract_urls(text: str, limit: int = 20) -> list[str]:
    urls = re.findall(r"https?://[^\s)\]>\"']+", text)
    deduped: list[str] = []
    for url in urls:
        cleaned = url.rstrip(".,;:")
        if cleaned not in deduped:
            deduped.append(cleaned)
        if len(deduped) >= limit:
            break
    return deduped


def compact_text(text: str, *, max_chars: int = 6000) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").splitlines()]
    cleaned = "\n".join(line for line in lines if line.strip())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "\n\n[truncated]"


def source_artifact_paths(project_root: pathlib.Path, provider: str, cache_key: str) -> dict[str, pathlib.Path]:
    safe_provider = slugify(provider, fallback="provider")
    safe_key = slugify(cache_key, fallback="source", max_length=96)
    base = project_root / "seo" / "research"
    return {
        "raw": base / "raw" / safe_provider / f"{safe_key}.json",
        "distillate_markdown": base / "distillates" / safe_provider / f"{safe_key}.md",
        "distillate_json": base / "distillates" / safe_provider / f"{safe_key}.json",
        "latest_markdown": base / "distillates" / safe_provider / "latest-summary.md",
        "latest_json": base / "distillates" / safe_provider / "latest-summary.json",
        "vector_jsonl": base / "vector" / "source_pack.jsonl",
    }


def read_cached_distillate(project_root: pathlib.Path, provider: str, cache_key: str) -> dict[str, Any] | None:
    path = source_artifact_paths(project_root, provider, cache_key)["distillate_json"]
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def append_jsonl(path: pathlib.Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def write_source_artifacts(
    project_root: pathlib.Path,
    provider: str,
    cache_key: str,
    *,
    raw_payload: dict[str, Any],
    distillate_markdown: str,
    distillate_payload: dict[str, Any],
    vector_record: dict[str, Any] | None = None,
) -> dict[str, str]:
    paths = source_artifact_paths(project_root, provider, cache_key)
    raw_text = json.dumps(raw_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    distillate_text = json.dumps(distillate_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    write_text(paths["raw"], raw_text)
    write_text(paths["distillate_markdown"], distillate_markdown)
    write_text(paths["distillate_json"], distillate_text)
    write_text(paths["latest_markdown"], distillate_markdown)
    write_text(paths["latest_json"], distillate_text)

    if vector_record is not None:
        append_jsonl(paths["vector_jsonl"], vector_record)

    return {key: str(path) for key, path in paths.items()}


def make_vector_record(
    *,
    provider: str,
    cache_key: str,
    topic: str,
    region: str,
    mode: str,
    status: str,
    summary: str,
    citations: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "record_type": "source_pack",
        "provider": provider,
        "cache_key": cache_key,
        "topic": topic,
        "region": region,
        "mode": mode,
        "status": status,
        "summary": summary,
        "citations": citations or [],
        "metadata": metadata or {},
        "created_at": utc_now_iso(),
    }
