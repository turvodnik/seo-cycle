"""Credential profiles: where a variable comes from and the ai-secret bridge.

One canon (T-108): secret VALUES live in the macOS Keychain and reach a
process only through `ai-secret run <scope> -- <command>` (global policy §5:
a `.env` with real values is forbidden, silently falling back to a weaker
store is forbidden). This module never writes a credential to disk.

Read-side precedence, highest first (`env_chain`):
  1. process environment — what `ai-secret run` injects, or CI/cron exports
  2. project .env             (legacy, read-only: names or non-secret markers)
  3. ~/.seo-cycle/env.global  (legacy, read-only; override: SEO_CYCLE_GLOBAL_ENV)

Legacy files are still READ so that an existing installation keeps working
until its values are migrated (`ai-secret import <scope> .env`); nothing in
this package writes secret values into them any more — `upsert_env_var` is
kept for non-secret markers only (see its docstring).

Write side (`store_secret`): the value is handed to `ai-secret set` through
stdin — never argv, never a file, never printed. `find_ai_secret` resolves
the binary at its canonical install path `~/.local/bin/ai-secret` — never
through PATH (the broker receives secret values, so a directory earlier in
PATH must not be able to substitute it; policy §5 treats PATH as untrusted).
Another location is honoured only through the explicit `SEO_CYCLE_AI_SECRET`
variable. A public installation without the broker gets an honest error
(`AI_SECRET_MISSING`) instead of a quiet write somewhere weaker.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess

# Set by bin/seo-cycle on the process it re-executes under `ai-secret run`;
# the only purpose is to break the re-exec loop. It is NOT proof that keys
# are present — `ai-secret run` itself sets no marker (checked in its source).
SECRETS_MARKER = "SEO_CYCLE_SECRETS_INJECTED"

# Keys that make `pulse` fetch fresh data (mirrors WEBMASTER_TOKEN_VARS and
# GSC_CRED_VARS in scripts/pulse.py). If none of them is in the environment,
# the run is going to degrade to the previous snapshot — that is the I-061
# "keys exist, snapshot is stale" case the launcher must not stay silent on.
PULSE_KEY_NAMES: tuple[str, ...] = (
    "YANDEX_OAUTH_TOKEN",
    "YANDEX_WEBMASTER_OAUTH_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
)

# Scope rules of the ai-secret broker (KeychainBroker.isValidScope): lowercase
# letters, digits, "-", "_", ".", 1..64 bytes. `global` is the shared scope.
SCOPE_RE = re.compile(r"^[a-z0-9._-]{1,64}$")
GLOBAL_SCOPE = "global"

# Canonical location of the broker. PATH is deliberately NOT consulted:
# `auth set`/`gbp-oauth-helper` hand secret values to this binary over stdin
# and the launcher execs it, so a look-up through PATH would let any earlier
# directory substitute the receiver of those values. The only other place
# that is honoured is the explicit override variable below (tests point it
# at their stub broker; a non-standard install points it at its binary).
AI_SECRET_DEFAULT = pathlib.Path("~/.local/bin/ai-secret")
AI_SECRET_ENV = "SEO_CYCLE_AI_SECRET"

AI_SECRET_MISSING = (
    f"секреты не подключены: не найден `ai-secret` по пути `{AI_SECRET_DEFAULT}` "
    f"(другой путь — только через переменную {AI_SECRET_ENV}; PATH не используется). Установи ai-secret "
    "(значения ключей живут в macOS Keychain, доступ — `ai-secret run <scope> -- <команда>`) "
    "или экспортируй нужные переменные в окружение сессии. В файлы значения не записываются (§5)."
)


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
    """Set KEY=value in an env file — NON-SECRET markers only.

    The sole remaining caller is gbp-oauth-helper writing the token mint DATE
    (`GBP_TOKEN_MINTED_AT`) so `auth list` can warn about the 7-day expiry.
    Never call this with a credential: secret values go to the Keychain via
    `store_secret` (T-108, policy §5). Test fixtures may use it to build
    legacy files for the read-side tests.
    """
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


def find_ai_secret() -> str | None:
    """Path to the `ai-secret` broker, or None (secrets not wired).

    `SEO_CYCLE_AI_SECRET` set → that path and nothing else (an override that
    points nowhere is an honest "not wired", never a fallback to the default
    or to PATH). Unset → `~/.local/bin/ai-secret`. PATH is never searched —
    see the module docstring for why.
    """
    override = os.environ.get(AI_SECRET_ENV, "").strip()
    candidate = pathlib.Path(override).expanduser() if override else AI_SECRET_DEFAULT.expanduser()
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def secret_scope(cfg: dict | None) -> str | None:
    """Keychain scope of a project = `project.brand_name_technical` (latin slug).

    Matches how live scopes are named on the reference machine (gsse, emwoody,
    pifagorlab, kiyokmag). Returns None when the field is absent or does not
    satisfy the broker's scope rules — callers must then ask for `--scope`
    rather than guess from the domain or the human-readable name.
    """
    if not isinstance(cfg, dict):
        return None
    project = cfg.get("project")
    if not isinstance(project, dict):
        return None
    raw = str(project.get("brand_name_technical") or "").strip()
    return raw if SCOPE_RE.match(raw) else None


def keychain_names(binary: str, scope: str) -> list[str] | None:
    """Names (never values) registered in the Keychain for `scope`.

    Wraps `ai-secret list <scope>` whose output is `scope: X`, `keys: N`, then
    one name per line. None = the broker could not answer (locked keychain,
    invalid scope, missing binary) — distinct from "no keys".
    """
    try:
        proc = subprocess.run(
            [binary, "list", scope], text=True, capture_output=True, check=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    names: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith(("scope:", "keys:")):
            continue
        names.append(line)
    return names


def store_secret(binary: str, scope: str, name: str, value: str) -> tuple[int, str]:
    """Hand one value to `ai-secret set <scope> <name>` through stdin.

    The value travels only over the pipe: not argv (visible in `ps` and the
    dispatcher log), not a file. Returns (rc, broker message) — the broker
    prints names and outcomes only, never values.
    """
    try:
        proc = subprocess.run(
            [binary, "set", scope, name],
            input=value + "\n",
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"ai-secret set failed: {exc.__class__.__name__}"
    message = (proc.stdout + proc.stderr).strip()
    return proc.returncode, message
