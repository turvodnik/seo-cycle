"""Quality-loop engine: check -> repair -> re-check with a bounded attempt budget.

Pure logic shared by `scripts/loop-runner.py`. The loop wraps the existing
quality gates (research-package-quality, page-outline-quality,
draft-quality-gate) and the machine repair layer. Findings are compared
between attempts so the loop can prove progress, stop early when repair no
longer changes anything, and escalate to a human approval ticket once the
attempt budget is spent.

Self-check classes:
- quality  — structural gate findings (coverage, drift, briefs, schema, ...)
- evidence — honesty/factual-integrity findings (missing proof, unsafe claims,
  unvalidated SERP data); tracked separately so escalations show whether the
  package is merely incomplete or actually untrustworthy.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
from typing import Any

from .config import nested_get

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_NO_PROGRESS_AFTER = 2
LOOPS_DIR = "seo/loops"

# Findings that speak to truthfulness/evidence rather than structure.
EVIDENCE_FINDING_IDS = {
    # research-package-quality
    "eeat_evidence_missing",
    "serp_validation_incomplete",
    "ai_overview_signals_unused",
    # page-outline-quality
    "missing_evidence_requirements",
    "missing_fact_check_queue",
    "missing_source_slots",
    "missing_trust_limitations",
    # draft-quality-gate
    "missing_proof_slot",
    "unsafe_first_person_expertise",
}

# Severities that block a target from passing its gate.
BLOCKING_SEVERITIES = {
    "research-package": {"critical"},
    "page-outline": {"critical"},
    "draft": {"critical", "error"},
}

TARGETS: dict[str, dict[str, Any]] = {
    "research-package": {
        "config_key": "research_package",
        "check_script": "research-package-quality.py",
        "check_args": ["--write", "--format", "json"],
        "report_name": "research-package-quality.json",
        "repair_kind": "machine",
        "repair_script": "research-package-repair.py",
        "repair_args": ["--write", "--format", "json"],
        "default_max_attempts": 5,
        "llm_instructions": [],
    },
    "page-outline": {
        "config_key": "page_outline",
        "check_script": "page-outline-quality.py",
        "check_args": ["--version", "auto", "--write", "--format", "json"],
        "report_name": "page-outline-quality.json",
        "repair_kind": "llm",
        "default_max_attempts": 3,
        "llm_instructions": [
            "Regenerate the failing page outlines with page-outline-v3.py (or edit the outline JSON) so every finding below is resolved.",
            "Keep SERP-safe ordering, entity connections, Answer Units, evidence/source slots, and acceptance criteria intact.",
        ],
    },
    "draft": {
        "config_key": "draft",
        "check_script": "draft-quality-gate.py",
        "check_args": ["--write", "--format", "json"],
        "repair_kind": "llm",
        "default_max_attempts": 3,
        "llm_instructions": [
            "Rewrite the draft so every finding below is resolved: restore missing H2/H3 from the outline, add required internal links, FAQ answers, and proof/citation markers.",
            "Never invent first-person expertise or fabricated sources; use the research package evidence layer.",
        ],
    },
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings = report.get("findings")
    if not isinstance(findings, list):
        return []
    normalized = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "id": str(item.get("id") or "unknown"),
                "severity": str(item.get("severity") or "medium").lower(),
                "title": str(item.get("title") or item.get("message") or ""),
            }
        )
    return normalized


def finding_keys(findings: list[dict[str, Any]]) -> list[str]:
    return sorted(f"{item['severity']}:{item['id']}" for item in findings)


def finding_fingerprint(findings: list[dict[str, Any]]) -> str:
    return hashlib.sha1("\n".join(finding_keys(findings)).encode("utf-8")).hexdigest()[:12]


def finding_delta(prev: list[dict[str, Any]], curr: list[dict[str, Any]]) -> dict[str, list[str]]:
    prev_keys = set(finding_keys(prev))
    curr_keys = set(finding_keys(curr))
    return {
        "resolved": sorted(prev_keys - curr_keys),
        "new": sorted(curr_keys - prev_keys),
        "unchanged": sorted(prev_keys & curr_keys),
    }


def classify_findings(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"quality": 0, "evidence": 0}
    for item in findings:
        counts["evidence" if item["id"] in EVIDENCE_FINDING_IDS else "quality"] += 1
    return counts


def severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in findings:
        counts[item["severity"]] = counts.get(item["severity"], 0) + 1
    return counts


def is_passed(target: str, report: dict[str, Any]) -> bool:
    status = str(report.get("status") or "").lower()
    if status:
        return status != "fail"
    blocking = BLOCKING_SEVERITIES.get(target, {"critical", "error"})
    return not any(item["severity"] in blocking for item in normalize_findings(report))


def target_config(cfg: dict[str, Any], target: str) -> dict[str, Any]:
    spec = TARGETS[target]
    loop_cfg = nested_get(cfg, "governance.loop", {}) or {}
    per_target = nested_get(loop_cfg, f"targets.{spec['config_key']}", {}) or {}
    max_attempts = per_target.get("max_attempts", loop_cfg.get("max_attempts", spec["default_max_attempts"]))
    return {
        "enabled": bool(loop_cfg.get("enabled", True)),
        "max_attempts": max(1, int(max_attempts or spec["default_max_attempts"])),
        "no_progress_after": max(2, int(loop_cfg.get("no_progress_after", DEFAULT_NO_PROGRESS_AFTER))),
        "escalate": bool(loop_cfg.get("escalate", True)),
    }


def loop_slug(target: str, path: pathlib.Path) -> str:
    name = path.stem if path.suffix else path.name
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:6]
    return f"{target}--{name}-{digest}"


def state_path(project_root: pathlib.Path, target: str, path: pathlib.Path) -> pathlib.Path:
    return project_root / LOOPS_DIR / f"{loop_slug(target, path)}.json"


def load_state(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def new_state(target: str, path: pathlib.Path, limits: dict[str, Any]) -> dict[str, Any]:
    return {
        "loop_id": loop_slug(target, path),
        "target": target,
        "path": str(path),
        "max_attempts": limits["max_attempts"],
        "no_progress_after": limits["no_progress_after"],
        "status": "running",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "attempts": [],
        "escalation": None,
    }


def record_attempt(state: dict[str, Any], report: dict[str, Any], target: str) -> dict[str, Any]:
    findings = normalize_findings(report)
    prev_findings = state["attempts"][-1]["check"]["findings"] if state["attempts"] else []
    attempt = {
        "n": len(state["attempts"]) + 1,
        "started_at": utc_now(),
        "check": {
            "status": str(report.get("status") or ("pass" if is_passed(target, report) else "fail")),
            "passed": is_passed(target, report),
            "severities": severity_counts(findings),
            "classes": classify_findings(findings),
            "fingerprint": finding_fingerprint(findings),
            "findings": findings,
        },
        "delta": finding_delta(prev_findings, findings),
        "repair": None,
    }
    state["attempts"].append(attempt)
    state["updated_at"] = utc_now()
    return attempt


def no_progress(state: dict[str, Any]) -> bool:
    window = int(state.get("no_progress_after", DEFAULT_NO_PROGRESS_AFTER))
    attempts = state.get("attempts", [])
    if len(attempts) < window:
        return False
    fingerprints = [attempt["check"]["fingerprint"] for attempt in attempts[-window:]]
    return len(set(fingerprints)) == 1 and bool(attempts[-1]["check"]["findings"])


def decide_next(state: dict[str, Any], target: str) -> str:
    attempts = state.get("attempts", [])
    if not attempts:
        return "run_check"
    last = attempts[-1]
    if last["check"]["passed"]:
        return "passed"
    if no_progress(state):
        return "escalate"
    if len(attempts) >= int(state.get("max_attempts", DEFAULT_MAX_ATTEMPTS)):
        return "escalate"
    return "run_repair" if TARGETS[target]["repair_kind"] == "machine" else "await_llm"


def llm_action_payload(state: dict[str, Any], target: str, resume_command: str) -> dict[str, Any]:
    spec = TARGETS[target]
    last = state["attempts"][-1]
    return {
        "action_required": "llm_repair",
        "loop_id": state["loop_id"],
        "target": target,
        "path": state["path"],
        "attempt": last["n"],
        "max_attempts": state["max_attempts"],
        "findings": last["check"]["findings"],
        "classes": last["check"]["classes"],
        "instructions": [*spec["llm_instructions"], f"When done, rerun: {resume_command}"],
    }


def render_state_markdown(state: dict[str, Any]) -> str:
    lines = [
        "# Quality Loop",
        "",
        f"- Loop: `{state['loop_id']}`",
        f"- Target: `{state['target']}`",
        f"- Path: `{state['path']}`",
        f"- Status: `{state['status']}`",
        f"- Attempts: `{len(state['attempts'])}/{state['max_attempts']}`",
        f"- Updated: {state['updated_at']}",
        "",
        "## Attempts",
        "",
    ]
    for attempt in state["attempts"]:
        check = attempt["check"]
        lines.extend(
            [
                f"### Attempt {attempt['n']}",
                "",
                f"- Check: `{check['status']}` (passed: {check['passed']})",
                f"- Findings: `{json.dumps(check['severities'], ensure_ascii=False)}`"
                f" · classes: `{json.dumps(check['classes'], ensure_ascii=False)}`",
                f"- Fingerprint: `{check['fingerprint']}`",
                f"- Delta: resolved {len(attempt['delta']['resolved'])}, new {len(attempt['delta']['new'])},"
                f" unchanged {len(attempt['delta']['unchanged'])}",
            ]
        )
        repair = attempt.get("repair")
        if repair:
            lines.append(f"- Repair: `{repair.get('kind')}` → {repair.get('summary', repair.get('status', ''))}")
        lines.append("")
    escalation = state.get("escalation")
    if escalation:
        lines.extend(
            [
                "## Escalation",
                "",
                f"- Ticket: `{escalation.get('ticket_id', 'n/a')}`",
                f"- Reason: {escalation.get('reason', '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
