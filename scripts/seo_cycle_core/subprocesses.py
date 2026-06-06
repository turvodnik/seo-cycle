"""Subprocess helpers that keep CLI scripts tolerant of degraded dependencies."""

from __future__ import annotations

import json
import pathlib
import subprocess
from typing import Any


def run_json(command: list[str], cwd: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or proc.stdout.strip(), "exit_code": proc.returncode}
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"error": "invalid json", "exit_code": proc.returncode}

