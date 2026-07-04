#!/usr/bin/env python3
"""Shared helpers for research-package repair scripts."""

from __future__ import annotations

import csv
import json
import pathlib
import re
from collections import Counter
from typing import Any, Iterable


def resolve_package(path: str | pathlib.Path) -> pathlib.Path:
    package = pathlib.Path(path).expanduser().resolve()
    if not package.exists() or not package.is_dir():
        raise SystemExit(f"ERROR: package directory not found: {package}")
    return package


def read_json(path: pathlib.Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, restkey="_extra_fields")
        rows: list[dict[str, str]] = []
        for row in reader:
            clean: dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                if key == "_extra_fields":
                    clean[key] = "|".join(str(item) for item in (value or []))
                else:
                    clean[str(key)] = normalize_space(value)
            rows.append(clean)
        return rows


def write_csv(path: pathlib.Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        ordered: list[str] = []
        for row in rows:
            for key in row:
                if key not in ordered:
                    ordered.append(key)
        fieldnames = ordered or ["status"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def normalize_space(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "|".join(normalize_space(item) for item in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", " ", normalize_space(value).lower()).strip()


def normalize_url(value: Any) -> str:
    text = normalize_space(value)
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        text = re.sub(r"^https?://[^/]+", "", text)
    if not text.startswith("/"):
        return text
    text = "/" + text.strip("/")
    return text + "/"


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [normalize_space(item) for item in value if normalize_space(item)]
    if isinstance(value, tuple):
        return [normalize_space(item) for item in value if normalize_space(item)]
    text = normalize_space(value)
    if not text:
        return []
    parts = re.split(r"\s*[|,]\s*", text)
    return [part for part in parts if part]


def to_float(value: Any, default: float = 0.0) -> float:
    text = normalize_space(value).replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return normalize_space(value).lower() in {"1", "true", "yes", "y", "да"}


def architecture_path(package: pathlib.Path) -> pathlib.Path:
    return package / "semantic-architecture-final.json"


def load_architecture(package: pathlib.Path) -> dict[str, Any]:
    return read_json(architecture_path(package), {}) or {}


def clusters_from_architecture(architecture: dict[str, Any]) -> list[dict[str, Any]]:
    clusters = architecture.get("clusters") or []
    if isinstance(clusters, dict):
        return [dict(value, id=key) if isinstance(value, dict) and "id" not in value else value for key, value in clusters.items()]
    return [cluster for cluster in clusters if isinstance(cluster, dict)]


def cluster_lookup(architecture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for cluster in clusters_from_architecture(architecture):
        aliases = [
            cluster.get("id"),
            cluster.get("name"),
            cluster.get("primary_keyword"),
            cluster.get("suggested_url"),
            cluster.get("url"),
        ]
        aliases.extend(as_list(cluster.get("legacy_ids")))
        aliases.extend(as_list(cluster.get("legacy_urls")))
        for alias in aliases:
            for key in {normalize_key(alias), normalize_url(alias)}:
                if key:
                    lookup[key] = cluster
    return lookup


def preferred_semantic_core(package: pathlib.Path) -> pathlib.Path:
    for name in ("semantic-core.resynced.csv", "semantic-core.cleaned.csv", "semantic-core.csv"):
        path = package / name
        if path.exists():
            return path
    return package / "semantic-core.csv"


def extract_urls(text: str) -> list[str]:
    pattern = r"(?<![A-Za-z0-9])/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+"
    urls = []
    for match in re.findall(pattern, text or ""):
        url = match.strip("`),.;")
        if url.startswith("//"):
            continue
        urls.append(normalize_url(url))
    return sorted(set(urls))


def slugify(value: str) -> str:
    value = normalize_key(value)
    value = re.sub(r"\s+", "-", value)
    return value.strip("-") or "untitled"


def print_report(report: dict[str, Any], output_format: str, markdown: str) -> None:
    if output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(markdown, end="" if markdown.endswith("\n") else "\n")


def write_jsonl(path: pathlib.Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def repeated_phrase_clean(value: str) -> str:
    text = normalize_key(value)
    words = text.split()
    changed = True
    while changed and len(words) > 1:
        changed = False
        for size in range(1, len(words) // 2 + 1):
            if words[-size:] == words[-2 * size : -size]:
                words = words[:-size]
                changed = True
                break
    half = len(words) // 2
    if half and len(words) % 2 == 0 and words[:half] == words[half:]:
        words = words[:half]
    return " ".join(words)


def relation_parts(value: str) -> tuple[str, str, str] | None:
    parts = [normalize_space(part) for part in str(value).split("->")]
    if len(parts) != 3 or not all(parts):
        return None
    return parts[0], parts[1], parts[2]


def counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def markdown_findings(title: str, summary: dict[str, Any], findings: list[dict[str, Any]] | None = None) -> str:
    lines = [f"# {title}", ""]
    lines.append("## Summary")
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    if findings:
        lines.extend(["", "## Findings"])
        for finding in findings:
            location = f" ({finding.get('location')})" if finding.get("location") else ""
            lines.append(f"- {finding.get('severity', 'info').upper()} `{finding.get('id')}`{location}: {finding.get('message', '')}")
    lines.append("")
    return "\n".join(lines)
