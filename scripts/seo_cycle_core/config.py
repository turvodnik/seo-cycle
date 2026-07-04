"""Config, path, and parsing helpers shared by seo-cycle scripts."""

from __future__ import annotations

import pathlib
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - callers surface this during CLI startup
    yaml = None


CONFIG_SEARCH_PATHS = (
    "seo-cycle.yaml",
    ".seo-cycle.yaml",
    "seo/seo-cycle.yaml",
    ".claude/seo-cycle.yaml",
)


def skill_root(current_file: str | pathlib.Path | None = None) -> pathlib.Path:
    if current_file:
        return pathlib.Path(current_file).resolve().parent.parent
    return pathlib.Path(__file__).resolve().parents[2]


def find_config(start_dir: pathlib.Path) -> pathlib.Path | None:
    for rel in CONFIG_SEARCH_PATHS:
        path = start_dir / rel
        if path.exists():
            return path
    return None


def project_root_for(cfg_path: pathlib.Path) -> pathlib.Path:
    if cfg_path.name in (".seo-cycle.yaml", "seo-cycle.yaml"):
        return cfg_path.parent
    if "/seo/" in str(cfg_path) or "/.claude/" in str(cfg_path):
        return cfg_path.parent.parent
    return cfg_path.parent


def package_project_root(package_dir: pathlib.Path) -> pathlib.Path:
    for candidate in [package_dir, *package_dir.parents]:
        if (candidate / "seo-cycle.yaml").exists():
            return candidate
    return package_dir.parent


def rel_path(project_root: pathlib.Path, raw: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path


def rel_display(project_root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def boolish(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "enabled", "да", "д", "on"}
    return bool(value)


def numeric(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def nested_get(data: dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get(key, default))

