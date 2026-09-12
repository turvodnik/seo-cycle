"""Shared monitoring-snapshot conventions (T-052 R1/R3, mask hardening).

Before this module `pulse.py` (writer), `seo_cycle_cli.py` doctor/status and
`monthly-dashboard.py` (readers) each hardcoded their own snapshot directory
and their own "newest file" pick. That silently diverged (R3: a config key
that only one of the three consumers actually read) and was fooled by two
separate bugs:

- **R1** — picking the newest file by mtime alone. After a `git clone` or a
  plain directory copy every file's mtime collapses to roughly the same
  instant, so the wrong (older-dated) snapshot could win.
- **mask hardening** — the glob `*snapshot*.json` matches ANY file with the
  word "snapshot" in its name, including unrelated service files (observed
  live: a neighbouring session's `triggers-snapshot-<date>.json`, which is
  not a monitoring-data snapshot at all). doctor/status then reported "ok"
  freshness off a file that has nothing to do with actual Webmaster/GSC data
  — exactly the "tool is optimistic by default" bug this ticket exists to
  close.

Fix: rank candidates by the date ENCODED IN THE FILENAME first, mtime only
as a tie-breaker, and only accept filenames that actually look like
snapshot-build.py's own output naming for a known source.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

from .config import rel_path

# Источники, которые реально пишет snapshot-build.py --source <name> (см. его
# докстринг). Любой другой префикс перед "-snapshot" — не срез мониторинга,
# даже если в имени есть слово "snapshot".
KNOWN_SOURCES = ("gsc", "ga4", "metrika", "webmaster", "psi")

_DATE_RE = r"\d{4}-\d{2}-\d{2}"
_SNAPSHOT_NAME_RE = re.compile(
    rf"^(?P<prefix>[a-z0-9_-]+?)-snapshot(?:-(?P<date>{_DATE_RE}))?\.json$",
    re.IGNORECASE,
)


def is_snapshot_filename(name: str) -> bool:
    """True for `<source>-snapshot[-<date>].json` (v2, <source> — известный
    источник snapshot-build.py) или `<date>-snapshot.json` (v1-дефолт без
    префикса источника). Всё остальное — не срез мониторинга, даже если в
    имени есть слово "snapshot" (например `triggers-snapshot-<date>.json`)."""
    m = _SNAPSHOT_NAME_RE.match(name)
    if not m:
        return False
    prefix = m.group("prefix").lower()
    if prefix in KNOWN_SOURCES:
        return True
    return bool(re.fullmatch(_DATE_RE, prefix))


def monitoring_dir(cfg: dict[str, Any], project_root: pathlib.Path) -> pathlib.Path:
    """`monitoring.path` в seo-cycle.yaml, дефолт `seo/monitoring` (T-052 R3).
    Единственное место, где это читают — pulse.py (пишет сюда), doctor/status
    и дашборд (читают отсюда), чтобы ключ не работал тихо только для одного
    из трёх."""
    monitoring_cfg = cfg.get("monitoring") if isinstance(cfg.get("monitoring"), dict) else {}
    raw = (monitoring_cfg or {}).get("path") or "seo/monitoring"
    return rel_path(project_root, raw)


def find_latest_snapshot(search_dirs: list[pathlib.Path]) -> pathlib.Path | None:
    """Самый свежий срез мониторинга среди всех каталогов-кандидатов.

    Ранжирование: сначала дата, зашитая В ИМЕНИ файла (mtime после
    `git clone`/копирования каталога ненадёжен — T-052 R1), mtime — только
    тай-брейк при равных/отсутствующих датах. Файлы, не похожие по имени на
    реальный срез мониторинга, в кандидаты не попадают (T-052, mask
    hardening) — см. `is_snapshot_filename`.
    """
    candidates: list[tuple[str, float, pathlib.Path]] = []
    for d in search_dirs:
        if not d.exists():
            continue
        for p in d.glob("*snapshot*.json"):
            if "quarantine" in p.parts or "invalid" in p.parts:
                continue
            if not is_snapshot_filename(p.name):
                continue
            date_match = re.search(_DATE_RE, p.name)
            date_key = date_match.group(0) if date_match else ""  # "" сортируется раньше любой даты
            try:
                mtime = p.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((date_key, mtime, p))
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c[0], c[1]))[2]


# ----- Sample boundary (T-096) ----------------------------------------------
#
# A monitoring snapshot is a SAMPLE of the site's queries — Webmaster "popular
# queries" caps at the top-500 by impressions, GSC at `--row-limit` rows — not
# the whole site. `positions` in seo.db carries no trace of that, so every
# consumer (pulse / position-progress / kpi-contract / seo-forecast) used to
# print sample-derived numbers as if they were site-wide. The helpers below
# read the sample metadata back from the snapshot files themselves (the same
# lookup `kpi-contract.snapshot_window_days` already does for the period), so
# all reports print one and the same "выборка N из M" line.

SAMPLE_LINE_UNKNOWN = "M неизвестно"


def _snapshot_files(cfg: dict[str, Any], project_root: pathlib.Path) -> list[pathlib.Path]:
    """Every file db-sync.py would feed into `positions`, minus the ones that
    do not look like a monitoring snapshot (`is_snapshot_filename`): the
    configured monitoring dir (recursively) plus the v1 cycle layout."""
    dirs = [monitoring_dir(cfg, project_root)]
    dirs.extend(project_root.glob("seo/cycles/**/09-monitoring"))
    seen: set[pathlib.Path] = set()
    out: list[pathlib.Path] = []
    for d in dirs:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*snapshot*.json")):
            if "quarantine" in p.parts or "invalid" in p.parts:
                continue
            if not is_snapshot_filename(p.name):
                continue
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
    return out


def _snapshot_file_date(path: pathlib.Path, data: dict[str, Any]) -> str:
    """The date db-sync.py stamps on the rows of this file: `date` field,
    else the date encoded in the filename (mirrors `sync_positions`)."""
    explicit = data.get("date")
    if explicit:
        return str(explicit)
    m = re.search(_DATE_RE, path.name)
    return m.group(0) if m else str(data.get("snapshot_date") or "")


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _sample_block(holder: Any) -> dict[str, Any]:
    """`sample` dict of a snapshot (or of one `source_metadata` entry), {} if absent/garbage."""
    if not isinstance(holder, dict):
        return {}
    sample = holder.get("sample")
    return dict(sample) if isinstance(sample, dict) else {}


def _source_samples(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-source sample descriptors of one snapshot file.

    `loaded` = rows the source actually returned (`sample.loaded_rows`,
    else the length of `queries` — pre-T-096 files and v1 snapshots carry no
    `sample` block at all); `available` = total the source reported
    (`sample.available_rows`) or None when the source does not report one
    (GSC never does; old files never recorded it).
    """
    queries = data.get("queries") or (data.get("merged") or {}).get("queries") or []
    n_queries = len(queries) if isinstance(queries, list) else 0
    per_source = data.get("source_metadata") if isinstance(data.get("source_metadata"), dict) else {}
    if per_source:
        out = []
        for name, meta in per_source.items():
            meta_sample = _sample_block(meta)
            loaded = _as_int(meta_sample.get("loaded_rows"))
            out.append({
                "source": str(name),
                "loaded": loaded if loaded is not None else (n_queries if len(per_source) == 1 else 0),
                "available": _as_int(meta_sample.get("available_rows")),
            })
        return out
    top_sample = _sample_block(data)
    sources = data.get("sources") if isinstance(data.get("sources"), list) else []
    name = ""
    if sources and isinstance(sources[0], dict):
        name = str(sources[0].get("source") or "")
    name = name or str(data.get("source") or "unknown")
    loaded = _as_int(top_sample.get("loaded_rows"))
    return [{
        "source": name,
        "loaded": loaded if loaded is not None else n_queries,
        "available": _as_int(top_sample.get("available_rows")),
    }]


def snapshot_sample(cfg: dict[str, Any], project_root: pathlib.Path, snapshot_date: str,
                    engine: str | None = None) -> dict[str, Any]:
    """Sample boundary of the positions rows dated `snapshot_date`.

    Returns {"loaded": N|None, "available": M|None, "sources": [...], "files": k}.
    N sums `loaded` over every matching snapshot file; M sums `available` and
    is None as soon as ANY contributing source does not report a total —
    a partially known M would read as a site total it is not. No matching
    file → loaded None (the caller falls back to what it counted in seo.db).
    """
    sources: list[dict[str, Any]] = []
    files = 0
    for path in _snapshot_files(cfg, project_root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if _snapshot_file_date(path, data) != str(snapshot_date):
            continue
        if engine:
            engines = {str(s.get("engine") or "").lower()
                       for s in (data.get("sources") or []) if isinstance(s, dict)}
            if data.get("engine"):
                engines.add(str(data["engine"]).lower())
            if engines and engine.lower() not in engines:
                continue
        files += 1
        sources.extend(_source_samples(data))
    if not files:
        return {"loaded": None, "available": None, "sources": [], "files": 0}
    loaded = sum(int(s["loaded"] or 0) for s in sources)
    totals = [s["available"] for s in sources]
    available: int | None = sum(int(t) for t in totals) if all(t is not None for t in totals) else None
    return {"loaded": loaded, "available": available, "sources": sources, "files": files}


def sample_line(sample: dict[str, Any] | None, fallback_loaded: int | None = None) -> str:
    """The one honest sentence every report prints about its sample:
    «выборка N из M запросов сайта» or «выборка N из M запросов сайта (M неизвестно)»."""
    sample = sample or {}
    loaded = sample.get("loaded")
    if loaded is None:
        loaded = fallback_loaded
    n = str(loaded) if loaded is not None else "?"
    available = sample.get("available")
    if available is None:
        return f"выборка {n} из M запросов сайта ({SAMPLE_LINE_UNKNOWN})"
    return f"выборка {n} из {available} запросов сайта"
