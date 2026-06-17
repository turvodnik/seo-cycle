"""Report IO helpers for markdown/json/latest artifact bundles."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable, Mapping
from typing import Any

from .config import write_text


def stringify_paths(paths: Mapping[str, pathlib.Path]) -> dict[str, str]:
    return {key: str(path) for key, path in paths.items()}


def write_json_file(path: pathlib.Path, payload: Any, *, sort_keys: bool = False) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n")


def write_sorted_json_file(path: pathlib.Path, payload: Any) -> None:
    write_json_file(path, payload, sort_keys=True)


def write_jsonl_file(path: pathlib.Path, rows: Iterable[Mapping[str, Any]], *, sort_keys: bool = True) -> None:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=sort_keys) for row in rows]
    write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def write_artifacts(
    *,
    text_files: Mapping[pathlib.Path, str] | None = None,
    json_files: Mapping[pathlib.Path, Any] | None = None,
    sort_keys: bool = False,
) -> None:
    for path, text in (text_files or {}).items():
        write_text(path, text)
    for path, payload in (json_files or {}).items():
        write_json_file(path, payload, sort_keys=sort_keys)


def write_report_bundle(paths: dict[str, pathlib.Path], markdown: str, payload: dict[str, Any], *, sort_keys: bool = False) -> None:
    write_artifacts(
        text_files={
            paths["markdown"]: markdown,
            paths["latest_markdown"]: markdown,
        },
        json_files={
            paths["json"]: payload,
            paths["latest_json"]: payload,
        },
        sort_keys=sort_keys,
    )
