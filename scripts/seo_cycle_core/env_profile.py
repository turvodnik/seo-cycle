"""Credential profiles: per-project .env with a global fallback.

An agency runs many projects. Some providers are authorized once for the
whole machine (a personal Perplexity key, the agency Yandex OAuth token) —
those live in ~/.seo-cycle/env.global. Others need a separate client account
per project — those live in the project's .env and win over the global file.

Precedence, highest first:
  1. process environment (never overridden — CI/cron stay in control)
  2. project .env
  3. global env file (~/.seo-cycle/env.global, override via SEO_CYCLE_GLOBAL_ENV)

The `seo-cycle` CLI merges this chain into every dispatched script, so a
login done once globally works in every project until a project overrides it.
Secrets never leave the env files: helpers write values with 0600 perms and
print variable names only.
"""

from __future__ import annotations

import os
import pathlib


def global_env_path() -> pathlib.Path:
    override = os.environ.get("SEO_CYCLE_GLOBAL_ENV")
    if override:
        return pathlib.Path(override).expanduser()
    return pathlib.Path.home() / ".seo-cycle" / "env.global"


def project_env_path(project_root: pathlib.Path) -> pathlib.Path:
    return project_root / ".env"


def parse_env_file(path: pathlib.Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    data: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key:
            data[key] = value
    return data


def env_chain(project_root: pathlib.Path | None = None, *, base: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(parse_env_file(global_env_path()))
    if project_root is not None:
        merged.update(parse_env_file(project_env_path(project_root)))
    merged.update(os.environ if base is None else base)
    return merged


def env_source(project_root: pathlib.Path | None, key: str) -> str | None:
    """Where a variable currently comes from: process | project | global | None."""
    if key in os.environ:
        return "process"
    if project_root is not None and key in parse_env_file(project_env_path(project_root)):
        return "project"
    if key in parse_env_file(global_env_path()):
        return "global"
    return None


def upsert_env_var(path: pathlib.Path, key: str, value: str) -> pathlib.Path:
    """Set KEY=value in an env file, replacing an existing assignment in place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    assignment = f"{key}={value}"
    replaced = False
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        head = stripped[len("export "):] if stripped.startswith("export ") else stripped
        if head.startswith(f"{key}="):
            lines[index] = assignment
            replaced = True
            break
    if not replaced:
        lines.append(assignment)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path
