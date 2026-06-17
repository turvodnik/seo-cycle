"""Gate evaluation helpers for staged seo-cycle runs."""

from __future__ import annotations

import pathlib
from typing import Any, Callable

from .stages import StageContract


CommandRunner = Callable[[tuple[str, ...], pathlib.Path], dict[str, Any]]


def resolve_stage_path(cwd: pathlib.Path, raw: str) -> pathlib.Path:
    path = pathlib.Path(raw).expanduser()
    return path if path.is_absolute() else cwd / path


def missing_paths(cwd: pathlib.Path, paths: tuple[str, ...]) -> list[str]:
    return [raw for raw in paths if not resolve_stage_path(cwd, raw).exists()]


def evaluate_gate(contract: StageContract, cwd: pathlib.Path, runner: CommandRunner) -> dict[str, Any]:
    if contract.gate.command:
        command_result = runner(contract.gate.command, cwd)
        passed = int(command_result.get("exit_code", 1)) in contract.gate.pass_codes
        return {
            "passed": passed,
            "mode": "command",
            "command_result": command_result,
            "missing_outputs": missing_paths(cwd, contract.outputs),
        }

    missing_outputs = missing_paths(cwd, contract.outputs)
    return {
        "passed": not missing_outputs,
        "mode": "outputs",
        "command_result": None,
        "missing_outputs": missing_outputs,
    }
