"""Subprocess helpers that keep CLI scripts tolerant of degraded dependencies."""

from __future__ import annotations

import json
import pathlib
import subprocess
from typing import Any


def run_command_step(name: str, command: list[str], cwd: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "name": name,
        "command": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def json_from_step(step: dict[str, Any]) -> dict[str, Any]:
    if step.get("exit_code") != 0:
        return {}
    try:
        data = json.loads(step.get("stdout") or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def run_json(command: list[str], cwd: pathlib.Path) -> dict[str, Any]:
    step = run_command_step("json command", command, cwd)
    if step["exit_code"] != 0:
        return {"error": step["stderr"].strip() or step["stdout"].strip(), "exit_code": step["exit_code"]}
    try:
        data = json.loads(step["stdout"] or "{}")
    except json.JSONDecodeError:
        return {"error": "invalid json", "exit_code": step["exit_code"]}
    return data if isinstance(data, dict) else {"error": "invalid json", "exit_code": step["exit_code"]}
