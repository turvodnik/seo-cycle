"""Report IO helpers for markdown/json/latest artifact bundles."""

from __future__ import annotations

import json
import pathlib
from typing import Any

from .config import write_text


def write_report_bundle(paths: dict[str, pathlib.Path], markdown: str, payload: dict[str, Any]) -> None:
    json_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    write_text(paths["markdown"], markdown)
    write_text(paths["json"], json_text)
    write_text(paths["latest_markdown"], markdown)
    write_text(paths["latest_json"], json_text)

