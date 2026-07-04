"""Shared project-journey helpers: stage records, package/loop state readers.

Extracted from scripts/project-journey.py so the script keeps only the stage
definitions and report assembly. Used by the journey CLI and available to
other orchestrator scripts that need package or loop state.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
from typing import Any

from .config import policy_path, rel_display

def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}




def artifact_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    return policy_path(cfg, project_root, key, default)


def artifact_exists(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> tuple[str, bool]:
    path = artifact_path(cfg, project_root, key, default)
    return rel_display(project_root, path), path.exists()


def unique_paths(paths: list[pathlib.Path]) -> list[pathlib.Path]:
    seen: set[str] = set()
    result = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return sorted(result)


def stage(
    *,
    stage_id: str,
    order: int,
    title: str,
    objective: str,
    evidence: list[str],
    missing: list[str] | None = None,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
    commands: list[str] | None = None,
    exit_criteria: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": stage_id,
        "order": order,
        "title": title,
        "objective": objective,
        "status": "pending",
        "evidence": evidence,
        "missing_artifacts": missing or [],
        "blockers": blockers or [],
        "warnings": warnings or [],
        "next_commands": commands or [],
        "exit_criteria": exit_criteria or [],
    }


def detect_research_package(project_root: pathlib.Path, raw: str | None) -> pathlib.Path | None:
    if raw:
        path = pathlib.Path(raw).expanduser().resolve()
        return path.parent if path.is_file() else path
    candidates = [
        project_root / "seo" / "research-package",
        project_root / "research-package",
        project_root / "seo" / "research",
    ]
    for candidate in candidates:
        if (candidate / "semantic-architecture-final.json").exists():
            return candidate
    for base in (project_root / "seo", project_root):
        if not base.exists():
            continue
        for architecture in base.glob("*/semantic-architecture-final.json"):
            return architecture.parent
    return None


def loop_states(project_root: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Latest quality-loop state per target from seo/loops/*.json (loop-runner.py)."""
    loops_dir = project_root / "seo" / "loops"
    latest: dict[str, dict[str, Any]] = {}
    if not loops_dir.is_dir():
        return latest
    for path in sorted(loops_dir.glob("*.json")):
        data = read_json(path)
        target = str(data.get("target") or "")
        if not target:
            continue
        escalation = data.get("escalation") if isinstance(data.get("escalation"), dict) else {}
        row = {
            "loop_id": data.get("loop_id"),
            "status": data.get("status"),
            "attempts_used": len(data.get("attempts") or []),
            "max_attempts": data.get("max_attempts"),
            "updated_at": data.get("updated_at"),
            "escalation_ticket": escalation.get("ticket_id"),
            "state_file": rel_display(project_root, path),
        }
        prev = latest.get(target)
        if not prev or str(row.get("updated_at") or "") > str(prev.get("updated_at") or ""):
            latest[target] = row
    return latest


def loop_evidence_line(loop_info: dict[str, Any] | None) -> str | None:
    if not loop_info:
        return None
    return (
        f"loop: {loop_info.get('status')}, attempt {loop_info.get('attempts_used')}/{loop_info.get('max_attempts')}"
        f" ({loop_info.get('state_file')})"
    )


def package_state(project_root: pathlib.Path, package: pathlib.Path | None) -> dict[str, Any]:
    required = [
        "semantic-core.csv",
        "content-plan.csv",
        "final-clusters.md",
        "semantic-architecture-final.json",
        "entity-map.md",
        "entity-map.yaml",
    ]
    if not package:
        return {
            "package_dir": None,
            "exists": False,
            "required": {name: False for name in required},
            "missing_required": required,
            "quality": {},
            "quality_exists": False,
            "outline_quality": {},
            "outline_quality_exists": False,
            "outline_count": 0,
            "outline_v3_count": 0,
            "copywriter_ready_count": 0,
            "draft_count": 0,
            "draft_quality_count": 0,
            "draft_quality_errors": 0,
            "draft_quality_warnings": 0,
            "draft_quality_missing": [],
            "draft_quality_findings": [],
            "loops": loop_states(project_root),
        }
    required_status = {name: (package / name).exists() for name in required}
    quality_path = package / "research-package-quality.json"
    repair_path = package / "research-package-repair.json"
    quality_mtime = quality_path.stat().st_mtime if quality_path.exists() else None
    repair_mtime = repair_path.stat().st_mtime if repair_path.exists() else None
    outline_quality_path = package / "page-outline-quality.json"
    outline_dir = package / "page-outlines-v2"
    outline_v3_dir = package / "page-outlines-v3"
    copywriter_ready_dir = package / "copywriter-ready"
    outline_count = len(list(outline_dir.glob("*.json"))) if outline_dir.exists() else 0
    outline_v3_count = len(list(outline_v3_dir.glob("*.json"))) if outline_v3_dir.exists() else 0
    copywriter_ready_count = len(list(copywriter_ready_dir.glob("*.md"))) if copywriter_ready_dir.exists() else 0
    draft_paths = unique_paths(
        [
            *list((package / "drafts").glob("*.md")),
            *list((package / "06-drafts").glob("*.md")),
            *list((project_root / "seo" / "drafts").glob("*.md")),
            *list((project_root / "06-drafts").glob("*.md")),
        ]
    )
    draft_paths = [path for path in draft_paths if ".draft-quality-gate" not in path.name]
    draft_quality_missing = []
    draft_quality_findings: list[dict[str, Any]] = []
    draft_quality_count = 0
    draft_quality_errors = 0
    draft_quality_warnings = 0
    for draft_path in draft_paths:
        gate_path = draft_path.with_suffix(".draft-quality-gate.json")
        if not gate_path.exists():
            draft_quality_missing.append(rel_display(project_root, gate_path))
            continue
        draft_quality_count += 1
        report = read_json(gate_path)
        for finding in report.get("findings", []) if isinstance(report.get("findings"), list) else []:
            if not isinstance(finding, dict):
                continue
            severity = str(finding.get("severity") or "").lower()
            row = {
                "draft": rel_display(project_root, draft_path),
                "id": finding.get("id"),
                "severity": severity,
                "message": finding.get("message") or finding.get("title"),
            }
            draft_quality_findings.append(row)
            if severity in {"error", "critical"}:
                draft_quality_errors += 1
            elif severity in {"warning", "warn", "high", "medium", "low"}:
                draft_quality_warnings += 1
    return {
        "package_dir": rel_display(project_root, package),
        "exists": package.exists(),
        "required": required_status,
        "missing_required": [name for name, exists in required_status.items() if not exists],
        "quality": read_json(quality_path),
        "quality_exists": quality_path.exists(),
        "quality_mtime": quality_mtime,
        "repair": read_json(repair_path),
        "repair_exists": repair_path.exists(),
        "repair_mtime": repair_mtime,
        "quality_stale_after_repair": bool(
            quality_mtime is not None and repair_mtime is not None and repair_mtime > quality_mtime
        ),
        "outline_quality": read_json(outline_quality_path),
        "outline_quality_exists": outline_quality_path.exists(),
        "outline_count": outline_count,
        "outline_v3_count": outline_v3_count,
        "copywriter_ready_count": copywriter_ready_count,
        "draft_count": len(draft_paths),
        "draft_paths": [rel_display(project_root, path) for path in draft_paths],
        "draft_quality_count": draft_quality_count,
        "draft_quality_errors": draft_quality_errors,
        "draft_quality_warnings": draft_quality_warnings,
        "draft_quality_missing": draft_quality_missing,
        "draft_quality_findings": draft_quality_findings,
        "loops": loop_states(project_root),
    }


def json_summary(path: pathlib.Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {}
