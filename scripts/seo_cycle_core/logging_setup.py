"""File logging shared by seo-cycle scripts.

Contract: stdout stays reserved for data/reports (existing print contracts),
so loggers write to a per-day file under `seo/logs/` plus stderr for warnings.
Setup is idempotent and never raises: broken permissions or a disabled
`logging` config section degrade to a stderr-only logger.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import pathlib
import sys
from typing import Any

from .config import boolish, nested_get, rel_path

DEFAULT_LOG_DIR = "seo/logs"
DEFAULT_FILE_LEVEL = "INFO"
DEFAULT_STDERR_LEVEL = "WARNING"
_MARKER = "_seo_cycle_handler"


def _coerce_level(raw: Any, fallback: int) -> int:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        level = logging.getLevelName(raw.strip().upper())
        if isinstance(level, int):
            return level
    return fallback


def log_file_path(project_root: pathlib.Path, cfg: dict[str, Any] | None = None,
                  today: dt.date | None = None) -> pathlib.Path:
    log_dir = nested_get(cfg or {}, "logging.dir", DEFAULT_LOG_DIR) or DEFAULT_LOG_DIR
    day = (today or dt.date.today()).isoformat()
    return rel_path(project_root, log_dir) / f"seo-cycle-{day}.log"


def setup_logging(name: str, project_root: pathlib.Path | None = None,
                  cfg: dict[str, Any] | None = None) -> logging.Logger:
    """Return a configured logger; safe to call repeatedly and without a project."""
    cfg = cfg or {}
    logger = logging.getLogger(f"seo-cycle.{name}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if any(getattr(h, _MARKER, False) for h in logger.handlers):
        return logger

    env_level = os.environ.get("SEO_CYCLE_LOG_LEVEL", "").strip().lower()
    enabled = boolish(nested_get(cfg, "logging.enabled", True), True) and env_level != "off"

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(_coerce_level(nested_get(cfg, "logging.stderr_level", DEFAULT_STDERR_LEVEL),
                                          logging.WARNING))
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s :: %(message)s",
                                  datefmt="%Y-%m-%dT%H:%M:%S")
    stderr_handler.setFormatter(formatter)
    setattr(stderr_handler, _MARKER, True)
    logger.addHandler(stderr_handler)

    if enabled and project_root is not None:
        try:
            path = log_file_path(project_root, cfg)
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(path, encoding="utf-8")
            file_level = env_level.upper() if env_level and env_level != "off" else None
            file_handler.setLevel(_coerce_level(file_level or nested_get(cfg, "logging.level", DEFAULT_FILE_LEVEL),
                                                logging.INFO))
            file_handler.setFormatter(formatter)
            setattr(file_handler, _MARKER, True)
            logger.addHandler(file_handler)
        except OSError:
            logger.warning("logging: cannot write log file under project root, stderr only")
    return logger


def prune_logs(project_root: pathlib.Path, cfg: dict[str, Any] | None = None, days: int = 30) -> int:
    """Delete `seo-cycle-*.log` files older than `days`; returns count removed."""
    log_dir = log_file_path(project_root, cfg).parent
    if not log_dir.is_dir():
        return 0
    cutoff = dt.date.today() - dt.timedelta(days=days)
    removed = 0
    for path in log_dir.glob("seo-cycle-*.log"):
        stamp = path.stem.replace("seo-cycle-", "")
        try:
            if dt.date.fromisoformat(stamp) < cutoff:
                path.unlink()
                removed += 1
        except (ValueError, OSError):
            continue
    return removed
