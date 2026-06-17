"""Small staged orchestrator for seo-cycle v1.63."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import subprocess
from typing import Any, Callable

from .config import write_text
from .gates import evaluate_gate, missing_paths
from .repair import run_repair_commands
from .stages import Command, StageContract


CommandRunner = Callable[[Command, pathlib.Path], dict[str, Any]]

SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|password|secret|credential|authorization)(\s*[=:]\s*)([^\r\n]+)"
)


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact_text(value: str, *, max_chars: int = 4000) -> str:
    redacted = SECRET_PATTERN.sub(r"\1\2***", value or "")
    if len(redacted) <= max_chars:
        return redacted
    return redacted[:max_chars].rstrip() + "\n[truncated]"


def run_command(command: Command, cwd: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(list(command), cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": list(command),
        "exit_code": proc.returncode,
        "stdout": redact_text(proc.stdout),
        "stderr": redact_text(proc.stderr),
    }


def orchestrator_dir(cwd: pathlib.Path) -> pathlib.Path:
    return cwd / "seo" / "orchestrator"


def write_json_report(path: pathlib.Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def render_stage_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Stage: {result.get('title')}",
        "",
        f"- ID: `{result.get('id')}`",
        f"- Status: `{result.get('status')}`",
        f"- Gate attempts: `{result.get('gate_attempts')}`",
        f"- Repair attempts: `{result.get('repair_attempts')}`",
        f"- Generated: {result.get('generated_at')}",
        "",
        "## Stop Conditions",
    ]
    stop_conditions = result.get("stop_conditions") or []
    lines.extend(f"- {item}" for item in stop_conditions) if stop_conditions else lines.append("- none")
    lines.extend(["", "## Missing Inputs"])
    missing_inputs = result.get("missing_inputs") or []
    lines.extend(f"- `{item}`" for item in missing_inputs) if missing_inputs else lines.append("- none")
    lines.extend(["", "## Missing Outputs"])
    missing_outputs = result.get("missing_outputs") or []
    lines.extend(f"- `{item}`" for item in missing_outputs) if missing_outputs else lines.append("- none")
    return "\n".join(lines) + "\n"


def write_stage_reports(cwd: pathlib.Path, result: dict[str, Any]) -> dict[str, str]:
    out_dir = orchestrator_dir(cwd)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / f"{result['id']}-report.json"
    report_md = out_dir / f"{result['id']}-report.md"
    write_json_report(report_json, result)
    write_text(report_md, render_stage_markdown(result))
    paths = {"report_json": str(report_json), "report_markdown": str(report_md)}
    if result.get("status") == "blocked":
        blocker = {
            "stage_id": result["id"],
            "title": result["title"],
            "status": result["status"],
            "generated_at": result["generated_at"],
            "repair_attempts": result["repair_attempts"],
            "gate_attempts": result["gate_attempts"],
            "stop_conditions": result.get("stop_conditions", []),
            "missing_inputs": result.get("missing_inputs", []),
            "missing_outputs": result.get("missing_outputs", []),
            "last_gate": result.get("last_gate"),
        }
        blocker_json = out_dir / f"{result['id']}-blocker.json"
        blocker_md = out_dir / f"{result['id']}-blocker.md"
        write_json_report(blocker_json, blocker)
        write_text(blocker_md, render_stage_markdown({**result, "title": f"Blocker: {result['title']}"}))
        paths.update({"blocker_json": str(blocker_json), "blocker_markdown": str(blocker_md)})
    return paths


def approval_result(contract: StageContract, cwd: pathlib.Path, write_report: bool) -> dict[str, Any]:
    result = {
        "id": contract.id,
        "title": contract.title,
        "status": "approval_required",
        "generated_at": utc_now_iso(),
        "gate_attempts": 0,
        "repair_attempts": 0,
        "stage_runs": [],
        "repairs": [],
        "missing_inputs": [],
        "missing_outputs": [],
        "stop_conditions": list(contract.stop_conditions),
        "next_stage": contract.next_stage,
        "message": "Stage requires approval; rerun with approve=True after human review.",
    }
    if write_report:
        result = {**result, "paths": write_stage_reports(cwd, result)}
    return result


def missing_input_result(contract: StageContract, cwd: pathlib.Path, missing_inputs: list[str], write_report: bool) -> dict[str, Any]:
    result = {
        "id": contract.id,
        "title": contract.title,
        "status": "blocked",
        "generated_at": utc_now_iso(),
        "gate_attempts": 0,
        "repair_attempts": 0,
        "stage_runs": [],
        "repairs": [],
        "missing_inputs": missing_inputs,
        "missing_outputs": list(contract.outputs),
        "stop_conditions": list(contract.stop_conditions),
        "next_stage": contract.next_stage,
        "message": "Required stage inputs are missing.",
    }
    if write_report:
        result = {**result, "paths": write_stage_reports(cwd, result)}
    return result


def run_stage(
    contract: StageContract,
    *,
    cwd: pathlib.Path,
    runner: CommandRunner = run_command,
    write_report: bool = False,
    approve: bool = False,
) -> dict[str, Any]:
    cwd = cwd.resolve()
    if contract.approval_required and not approve:
        return approval_result(contract, cwd, write_report)

    missing_inputs = missing_paths(cwd, contract.required_inputs)
    if missing_inputs:
        return missing_input_result(contract, cwd, missing_inputs, write_report)

    stage_runs: list[list[dict[str, Any]]] = []
    repairs: list[list[dict[str, Any]]] = []
    gates: list[dict[str, Any]] = []

    for attempt in range(contract.max_attempts + 1):
        stage_runs.append([runner(command, cwd) for command in contract.commands])
        gate = evaluate_gate(contract, cwd, runner)
        gates.append(gate)
        if gate["passed"]:
            result = {
                "id": contract.id,
                "title": contract.title,
                "status": "passed",
                "generated_at": utc_now_iso(),
                "gate_attempts": len(gates),
                "repair_attempts": len(repairs),
                "stage_runs": stage_runs,
                "repairs": repairs,
                "gates": gates,
                "last_gate": gate,
                "missing_inputs": [],
                "missing_outputs": gate.get("missing_outputs", []),
                "stop_conditions": list(contract.stop_conditions),
                "next_stage": contract.next_stage,
            }
            if write_report:
                result = {**result, "paths": write_stage_reports(cwd, result)}
            return result
        if attempt >= contract.max_attempts:
            break
        repairs.append(run_repair_commands(contract.repair_commands, cwd, runner))

    last_gate = gates[-1] if gates else {}
    result = {
        "id": contract.id,
        "title": contract.title,
        "status": "blocked",
        "generated_at": utc_now_iso(),
        "gate_attempts": len(gates),
        "repair_attempts": len(repairs),
        "stage_runs": stage_runs,
        "repairs": repairs,
        "gates": gates,
        "last_gate": last_gate,
        "missing_inputs": [],
        "missing_outputs": last_gate.get("missing_outputs", list(contract.outputs)),
        "stop_conditions": list(contract.stop_conditions),
        "next_stage": contract.next_stage,
        "message": "Stage gate did not pass before repair attempts were exhausted.",
    }
    if write_report:
        result = {**result, "paths": write_stage_reports(cwd, result)}
    return result


def run_stages(
    contracts: tuple[StageContract, ...],
    *,
    cwd: pathlib.Path,
    write_report: bool = False,
    approve: bool = False,
) -> dict[str, Any]:
    results = []
    status = "passed"
    for contract in contracts:
        result = run_stage(contract, cwd=cwd, write_report=write_report, approve=approve)
        results.append(result)
        if result["status"] != "passed":
            status = result["status"]
            break
    report = {
        "status": status,
        "generated_at": utc_now_iso(),
        "stages": results,
        "completed": sum(1 for result in results if result["status"] == "passed"),
        "total": len(contracts),
    }
    if write_report:
        out_dir = orchestrator_dir(cwd)
        out_dir.mkdir(parents=True, exist_ok=True)
        latest_json = out_dir / "latest-run.json"
        latest_md = out_dir / "latest-run.md"
        write_json_report(latest_json, report)
        write_text(latest_md, render_run_markdown(report))
        report = {**report, "paths": {"latest_json": str(latest_json), "latest_markdown": str(latest_md)}}
    return report


def render_run_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# seo-cycle orchestrator run",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Completed: `{report.get('completed')}` / `{report.get('total')}`",
        f"- Generated: {report.get('generated_at')}",
        "",
        "## Stages",
        "| Stage | Status | Gate attempts | Repair attempts |",
        "| --- | --- | --- | --- |",
    ]
    for result in report.get("stages", []):
        lines.append(
            f"| `{result.get('id')}` | `{result.get('status')}` | "
            f"{result.get('gate_attempts')} | {result.get('repair_attempts')} |"
        )
    return "\n".join(lines) + "\n"
