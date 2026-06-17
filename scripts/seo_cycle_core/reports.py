"""Report IO helpers for markdown/json/latest artifact bundles."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping
from typing import Any

from .config import write_text


def stringify_paths(paths: Mapping[str, pathlib.Path]) -> dict[str, str]:
    return {key: str(path) for key, path in paths.items()}


def write_artifacts(
    *,
    text_files: Mapping[pathlib.Path, str] | None = None,
    json_files: Mapping[pathlib.Path, Any] | None = None,
) -> None:
    for path, text in (text_files or {}).items():
        write_text(path, text)
    for path, payload in (json_files or {}).items():
        write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_report_bundle(paths: dict[str, pathlib.Path], markdown: str, payload: dict[str, Any]) -> None:
    write_artifacts(
        text_files={
            paths["markdown"]: markdown,
            paths["latest_markdown"]: markdown,
        },
        json_files={
            paths["json"]: payload,
            paths["latest_json"]: payload,
        },
    )
