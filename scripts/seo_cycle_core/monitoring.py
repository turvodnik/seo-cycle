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
