"""Stage contract primitives for the seo-cycle orchestrator."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any


Command = tuple[str, ...]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def normalize_command(raw: Any) -> Command:
    if isinstance(raw, str):
        parts = tuple(shlex.split(raw))
    elif isinstance(raw, (list, tuple)) and all(isinstance(item, (str, int, float)) for item in raw):
        parts = tuple(str(item) for item in raw)
    else:
        raise ValueError(f"Invalid command spec: {raw!r}")
    if not parts:
        raise ValueError("Command spec cannot be empty")
    return parts


def normalize_command_list(raw: Any) -> tuple[Command, ...]:
    if raw in (None, "", []):
        return ()
    if isinstance(raw, str):
        return (normalize_command(raw),)
    if isinstance(raw, (list, tuple)):
        if all(isinstance(item, (str, int, float)) for item in raw):
            return (normalize_command(raw),)
        return tuple(normalize_command(item) for item in raw)
    raise ValueError(f"Invalid command list: {raw!r}")


def normalize_strings(raw: Any) -> tuple[str, ...]:
    if raw in (None, "", []):
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, (list, tuple)):
        return tuple(str(item) for item in raw)
    raise ValueError(f"Invalid string list: {raw!r}")


@dataclass(frozen=True)
class GateContract:
    command: Command | None = None
    pass_codes: tuple[int, ...] = (0,)

    @classmethod
    def from_mapping(cls, raw: Any) -> "GateContract":
        if raw in (None, "", {}):
            return cls()
        if isinstance(raw, (str, list, tuple)):
            return cls(command=normalize_command(raw))
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid gate contract: {raw!r}")
        command = raw.get("command")
        pass_codes_raw = raw.get("pass_codes", (0,))
        if isinstance(pass_codes_raw, int):
            pass_codes = (pass_codes_raw,)
        else:
            pass_codes = tuple(int(code) for code in pass_codes_raw)
        return cls(command=normalize_command(command) if command else None, pass_codes=pass_codes or (0,))

    def to_mapping(self) -> dict[str, Any]:
        return {
            "command": list(self.command) if self.command else None,
            "pass_codes": list(self.pass_codes),
        }


@dataclass(frozen=True)
class StageContract:
    id: str
    title: str
    required_inputs: tuple[str, ...]
    commands: tuple[Command, ...]
    outputs: tuple[str, ...]
    gate: GateContract
    repair_commands: tuple[Command, ...]
    max_attempts: int
    approval_required: bool
    stop_conditions: tuple[str, ...]
    next_stage: str | None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "StageContract":
        if not isinstance(raw, dict):
            raise ValueError("Stage contract must be a mapping")
        stage_id = str(raw.get("id") or "").strip()
        if not stage_id:
            raise ValueError("Stage contract requires id")
        title = str(raw.get("title") or stage_id).strip()
        max_attempts = int(raw.get("max_attempts", 5))
        if max_attempts < 0:
            raise ValueError("max_attempts must be >= 0")
        next_stage_raw = raw.get("next_stage")
        return cls(
            id=stage_id,
            title=title,
            required_inputs=normalize_strings(raw.get("required_inputs")),
            commands=normalize_command_list(raw.get("commands")),
            outputs=normalize_strings(raw.get("outputs")),
            gate=GateContract.from_mapping(raw.get("gate")),
            repair_commands=normalize_command_list(raw.get("repair_commands")),
            max_attempts=max_attempts,
            approval_required=_as_bool(raw.get("approval_required", False)),
            stop_conditions=normalize_strings(raw.get("stop_conditions")),
            next_stage=str(next_stage_raw) if next_stage_raw not in (None, "") else None,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "required_inputs": list(self.required_inputs),
            "commands": [list(command) for command in self.commands],
            "outputs": list(self.outputs),
            "gate": self.gate.to_mapping(),
            "repair_commands": [list(command) for command in self.repair_commands],
            "max_attempts": self.max_attempts,
            "approval_required": self.approval_required,
            "stop_conditions": list(self.stop_conditions),
            "next_stage": self.next_stage,
        }
