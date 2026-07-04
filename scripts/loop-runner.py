#!/usr/bin/env python3
"""Run a quality gate in a bounded check -> repair -> re-check loop.

Targets:
  research-package  gate: research-package-quality.py, repair: research-package-repair.py (machine)
  page-outline      gate: page-outline-quality.py, repair: LLM regeneration (exit 3 protocol)
  draft             gate: draft-quality-gate.py (needs --outline), repair: LLM rewrite (exit 3 protocol)

The loop stops on: pass (exit 0), attempt budget spent or no progress between
attempts (escalation ticket + Telegram alert, exit 1), or when an LLM repair
step is required (machine-readable `action_required` JSON on stdout, exit 3 —
perform the instructions, then rerun with --resume).

Attempt journal lives in `seo/loops/<loop-id>.json` (+ `.md` for humans) and is
picked up by project-journey.py.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, package_project_root, write_text
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.loop import (
    TARGETS,
    decide_next,
    llm_action_payload,
    load_state,
    new_state,
    record_attempt,
    render_state_markdown,
    state_path,
    target_config,
)
from seo_cycle_core.loop import no_progress as loop_no_progress
from seo_cycle_core.scorecard import score_from_findings, write_scorecard

log = setup_logging("loop-runner")

EXIT_PASSED = 0
EXIT_ESCALATED = 1
EXIT_CONFIG_ERROR = 2
EXIT_AWAITING_LLM = 3


def scripts_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def run_check(target: str, path: pathlib.Path, outline: pathlib.Path | None, project_root: pathlib.Path) -> dict[str, Any]:
    spec = TARGETS[target]
    command = [sys.executable, str(scripts_dir() / spec["check_script"]), str(path)]
    if target == "draft":
        command += ["--outline", str(outline)]
    command += spec["check_args"]
    proc = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
    log.info("loop check %s rc=%s", spec["check_script"], proc.returncode)
    report = read_check_report(target, path, proc.stdout)
    if not report:
        raise RuntimeError(
            f"check produced no readable report (rc={proc.returncode}); stderr: {proc.stderr[-500:]}"
        )
    return report


def read_check_report(target: str, path: pathlib.Path, stdout: str) -> dict[str, Any]:
    spec = TARGETS[target]
    if target == "draft":
        report_path = path.with_suffix(".draft-quality-gate.json")
    else:
        base = path if path.is_dir() else path.parent
        report_path = base / spec["report_name"]
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    try:
        data = json.loads(stdout)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def run_repair(target: str, path: pathlib.Path, project_root: pathlib.Path) -> dict[str, Any]:
    spec = TARGETS[target]
    command = [sys.executable, str(scripts_dir() / spec["repair_script"]), str(path), *spec["repair_args"]]
    proc = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
    log.info("loop repair %s rc=%s", spec["repair_script"], proc.returncode)
    summary: dict[str, Any] = {}
    try:
        parsed = json.loads(proc.stdout)
        summary = parsed.get("summary", {}) if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    return {
        "kind": "machine",
        "script": spec["repair_script"],
        "returncode": proc.returncode,
        "status": "ok" if proc.returncode == 0 else "failed",
        "summary": summary,
    }


def escalate(state: dict[str, Any], reason: str, project_root: pathlib.Path, md_path: pathlib.Path,
             escalate_enabled: bool) -> None:
    state["status"] = "escalated"
    top = ", ".join(
        f"{item['severity']}:{item['id']}" for item in state["attempts"][-1]["check"]["findings"][:5]
    ) or "no findings parsed"
    escalation: dict[str, Any] = {"reason": reason, "top_findings": top, "ticket_id": None, "notified": False}
    if escalate_enabled:
        create = subprocess.run(
            [
                sys.executable,
                str(scripts_dir() / "approval-gate.py"),
                "create",
                "--type",
                "loop_escalation",
                "--title",
                f"{state['target']} loop stopped after {len(state['attempts'])} attempts ({reason})",
                "--file",
                str(md_path),
                "--context",
                f"Top findings: {top}",
            ],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )
        ticket_id = create.stdout.strip().splitlines()[-1] if create.stdout.strip() else None
        escalation["ticket_id"] = ticket_id if create.returncode == 0 else None
        notify = subprocess.run(
            [
                sys.executable,
                str(scripts_dir() / "notify.py"),
                f"Quality loop escalated: {state['loop_id']}\nReason: {reason}\nTop findings: {top}",
                "--title",
                "SEO loop escalation",
                "--level",
                "alert",
            ],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )
        escalation["notified"] = notify.returncode == 0
    state["escalation"] = escalation
    log.warning("loop %s escalated: %s", state["loop_id"], reason)


def save_state(state: dict[str, Any], json_path: pathlib.Path) -> None:
    write_text(json_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    write_text(json_path.with_suffix(".md"), render_state_markdown(state))


def write_loop_scorecard(state: dict[str, Any], project_root: pathlib.Path) -> None:
    """Auto-grade the loop outcome so progress is visible in journey/dashboards."""
    attempts = state.get("attempts", [])
    findings = attempts[-1]["check"]["findings"] if attempts else []
    try:
        write_scorecard(
            project_root,
            f"loop:{state.get('target', '?')}",
            score_from_findings(findings),
            status="done" if state.get("status") == "passed" else "failed",
            done=[f"{len(attempts)} попыток, статус {state.get('status')}"],
            missing=[f"{item.get('severity')}:{item.get('id')}" for item in findings[:5]],
            meta={"loop_id": state.get("loop_id"), "attempts": len(attempts)},
        )
    except OSError as exc:
        log.warning("scorecard write failed: %s", exc)


def mark_phase_passed(phase: str, cycle_dir: str | None, project_root: pathlib.Path) -> None:
    command = [sys.executable, str(scripts_dir() / "cycle-state.py"), "set", phase, "--status", "done", "--gate-passed"]
    if cycle_dir:
        command += ["--dir", cycle_dir]
    proc = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
    log.info("cycle-state set %s rc=%s", phase, proc.returncode)


def resume_command(args: argparse.Namespace) -> str:
    parts = [f"python3 scripts/loop-runner.py {args.target} {args.path} --resume"]
    if args.outline:
        parts.append(f"--outline {args.outline}")
    if args.phase:
        parts.append(f"--phase {args.phase}")
    if args.cycle_dir:
        parts.append(f"--cycle-dir {args.cycle_dir}")
    return " ".join(parts)


def print_state(state: dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(render_state_markdown(state), end="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", choices=sorted(TARGETS.keys()))
    parser.add_argument("path", help="Research package dir, outline dir/file, or draft markdown file")
    parser.add_argument("--outline", help="page-outline JSON (required for target=draft)")
    parser.add_argument("--max-attempts", type=int, help="Override governance.loop max attempts")
    parser.add_argument("--resume", action="store_true", help="Continue an existing loop after an LLM repair step")
    parser.add_argument("--status", action="store_true", help="Print current loop state and exit")
    parser.add_argument("--reset", action="store_true", help="Discard previous loop state and start fresh")
    parser.add_argument("--phase", help="cycle-state phase to mark done+gate-passed on success")
    parser.add_argument("--cycle-dir", help="Cycle dir for cycle-state.py set")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    path = pathlib.Path(args.path).expanduser().resolve()
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    if args.target == "draft":
        if not args.outline:
            print("ERROR: target=draft requires --outline <page-outline.json>", file=sys.stderr)
            return EXIT_CONFIG_ERROR
        outline = pathlib.Path(args.outline).expanduser().resolve()
        if not outline.exists():
            print(f"ERROR: outline {outline} not found", file=sys.stderr)
            return EXIT_CONFIG_ERROR
    else:
        outline = None

    project_root = package_project_root(path if path.is_dir() else path.parent)
    cfg_path = find_config(project_root)
    cfg = load_yaml(cfg_path) if cfg_path else {}
    global log
    log = setup_logging("loop-runner", project_root, cfg)

    limits = target_config(cfg, args.target)
    if args.max_attempts:
        limits["max_attempts"] = max(1, args.max_attempts)
    if not limits["enabled"]:
        print("governance.loop.enabled is false — run the gate/repair scripts directly.", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    json_path = state_path(project_root, args.target, path)
    state = load_state(json_path)
    if args.status:
        if not state:
            print(f"No loop state at {json_path}", file=sys.stderr)
            return EXIT_CONFIG_ERROR
        print_state(state, args.format)
        return EXIT_PASSED
    if state.get("status") == "escalated" and args.resume:
        print("Loop already escalated — review the ticket, then start over with --reset.", file=sys.stderr)
        print_state(state, args.format)
        return EXIT_ESCALATED
    if args.reset or not state or state.get("status") in {"passed", "escalated"}:
        state = new_state(args.target, path, limits)
    state["max_attempts"] = limits["max_attempts"]
    state["no_progress_after"] = limits["no_progress_after"]
    state["status"] = "running"

    while True:
        try:
            report = run_check(args.target, path, outline, project_root)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return EXIT_CONFIG_ERROR
        attempt = record_attempt(state, report, args.target)
        decision = decide_next(state, args.target)
        log.info("loop %s attempt %s decision=%s", state["loop_id"], attempt["n"], decision)

        if decision == "passed":
            state["status"] = "passed"
            save_state(state, json_path)
            write_loop_scorecard(state, project_root)
            if args.phase:
                mark_phase_passed(args.phase, args.cycle_dir, project_root)
            print_state(state, args.format)
            return EXIT_PASSED

        if decision == "escalate":
            reason = "no progress between attempts" if loop_no_progress(state) else "attempt budget spent"
            escalate(state, reason, project_root, json_path.with_suffix(".md"), limits["escalate"])
            save_state(state, json_path)
            write_loop_scorecard(state, project_root)
            print_state(state, args.format)
            return EXIT_ESCALATED

        if decision == "await_llm":
            state["status"] = "awaiting_llm"
            attempt["repair"] = {"kind": "llm", "completed": False, "requested_at": attempt["started_at"]}
            save_state(state, json_path)
            print(json.dumps(llm_action_payload(state, args.target, resume_command(args)), ensure_ascii=False, indent=2))
            return EXIT_AWAITING_LLM

        # decision == run_repair (machine)
        attempt["repair"] = run_repair(args.target, path, project_root)
        save_state(state, json_path)


if __name__ == "__main__":
    raise SystemExit(main())
