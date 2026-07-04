"""Self-assessment scorecards: every tool run can grade its own result 0-10.

The score is honest, not decorative: when quality-gate findings exist they
drive it via score_from_findings() — a clean run is a 10 and every unresolved
finding subtracts weight by severity. Agents record manual scores through
`scripts/scorecard.py record` after finishing a task.

Storage: seo/scorecards/scorecards.jsonl (append-only history) plus
seo/scorecards/latest.json (one entry per tool) so project-journey and
dashboards can show current grades without scanning history.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime
from typing import Any

from .config import write_text

SEVERITY_WEIGHTS = {"critical": 3.0, "error": 2.0, "warning": 0.75, "info": 0.2}
DEFAULT_WEIGHT = 0.5
STATUSES = ("done", "partial", "failed")


def clamp_score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(min(10.0, max(0.0, number)), 1)


def score_from_findings(findings: list[dict[str, Any]]) -> float:
    penalty = sum(
        SEVERITY_WEIGHTS.get(str(item.get("severity", "info")).lower(), DEFAULT_WEIGHT)
        for item in findings
    )
    return clamp_score(10.0 - penalty)


def scorecards_dir(project_root: pathlib.Path) -> pathlib.Path:
    return project_root / "seo" / "scorecards"


def write_scorecard(
    project_root: pathlib.Path,
    tool: str,
    score: Any,
    *,
    status: str = "done",
    done: list[str] | None = None,
    missing: list[str] | None = None,
    notes: str = "",
    meta: dict[str, Any] | None = None,
    when: str | None = None,
) -> dict[str, Any]:
    entry = {
        "at": when or datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "score": clamp_score(score),
        "status": status if status in STATUSES else "done",
        "done": [str(item) for item in (done or []) if str(item).strip()],
        "missing": [str(item) for item in (missing or []) if str(item).strip()],
        "notes": str(notes or ""),
        "meta": meta or {},
    }
    directory = scorecards_dir(project_root)
    history = directory / "scorecards.jsonl"
    directory.mkdir(parents=True, exist_ok=True)
    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    latest = load_latest(project_root)
    latest[tool] = entry
    write_text(directory / "latest.json", json.dumps(latest, ensure_ascii=False, indent=2) + "\n")
    return entry


def load_latest(project_root: pathlib.Path) -> dict[str, dict[str, Any]]:
    path = scorecards_dir(project_root) / "latest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_history(project_root: pathlib.Path, tool: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    path = scorecards_dir(project_root) / "scorecards.jsonl"
    entries: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and (tool is None or item.get("tool") == tool):
                entries.append(item)
    except OSError:
        return []
    return entries[-limit:]


def score_badge(score: float) -> str:
    if score >= 8.0:
        return "🟢"
    if score >= 5.0:
        return "🟡"
    return "🔴"


def render_scorecards_markdown(latest: dict[str, dict[str, Any]], limit: int = 20) -> str:
    if not latest:
        return "_Самооценок пока нет — они появляются после запусков loop/гейтов или `seo-cycle score record`._\n"
    rows = sorted(latest.values(), key=lambda item: item.get("at", ""), reverse=True)[:limit]
    lines = ["| Оценка | Инструмент | Статус | Когда | Не хватает |", "|---|---|---|---|---|"]
    for entry in rows:
        score = clamp_score(entry.get("score"))
        missing = "; ".join(entry.get("missing", [])[:2]) or "—"
        lines.append(
            f"| {score_badge(score)} {score}/10 | {entry.get('tool', '?')} | {entry.get('status', '?')} "
            f"| {str(entry.get('at', ''))[:16]} | {missing} |"
        )
    return "\n".join(lines) + "\n"
