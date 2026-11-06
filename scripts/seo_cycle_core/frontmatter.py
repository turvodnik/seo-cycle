"""Split a markdown draft into YAML frontmatter and body without exiting (3.1.0).

Frontmatter is recognised only at the very start of the file: a `---` line,
the YAML, and the next `---` (or `...`) line. A broken frontmatter is returned
as an error string so the draft gate can report it as a finding the quality
loop can repair; `eeat-render.py` keeps its strict path (exit 2).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

from .config import parse_yaml_text_safe


@dataclasses.dataclass(frozen=True)
class Frontmatter:
    data: dict[str, Any]
    body: str
    # 1-based line number of the first body line in the original text, so a
    # finding computed on the body can point at the right line of the file.
    body_start_line: int
    present: bool
    error: str | None = None


def _plain(value: Any) -> Any:
    """Dates and other YAML scalars become JSON-safe strings (reports are JSON)."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def split_frontmatter(text: str) -> Frontmatter:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return Frontmatter({}, text, 1, False)
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            block = "".join(lines[1:index])
            body = "".join(lines[index + 1:])
            start = index + 2
            data, error = parse_yaml_text_safe(block)
            if error:
                return Frontmatter({}, body, start, True, f"frontmatter: {error}")
            if data is None:
                return Frontmatter({}, body, start, True)
            if not isinstance(data, dict):
                return Frontmatter({}, body, start, True,
                                   f"frontmatter: ожидался словарь, получено {type(data).__name__}")
            return Frontmatter(_plain(data), body, start, True)
    # An opening `---` without a closing line is not frontmatter — it is a
    # horizontal rule at the top of the text.
    return Frontmatter({}, text, 1, False)
