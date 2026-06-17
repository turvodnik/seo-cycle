"""Repair loop helpers for the seo-cycle orchestrator."""

from __future__ import annotations

import pathlib
from typing import Any, Callable

from .stages import Command


CommandRunner = Callable[[Command, pathlib.Path], dict[str, Any]]


def run_repair_commands(commands: tuple[Command, ...], cwd: pathlib.Path, runner: CommandRunner) -> list[dict[str, Any]]:
    return [runner(command, cwd) for command in commands]
