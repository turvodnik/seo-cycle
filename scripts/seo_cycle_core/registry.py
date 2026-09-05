"""Machine-local project registry — location, not just content (T-061 fix-up).

`config/projects-registry.yaml` lists this machine's projects: absolute
paths, domains, which ones run monthly automation. That is per-machine
state, never tool content, for exactly the same reason `env_profile.py`
keeps credential files out of the repo tree: whatever lives inside the tool
directory can end up in two places it must not be writable in.

T-061 first tried to fix the resulting public-repo leak (real registry
committed to a public repo) by keeping the file's traditional location
(``<skill_root>/config/projects-registry.yaml``) but removing it from git
tracking. That broke two things that only show up once the fix actually
ships to real installs, not on a fresh worktree:

- **Read-only version snapshots (T-049).** A project can be pinned to
  ``~/.codex/vendor/versions/seo-cycle/vX.Y.Z`` — a read-only git worktree.
  Any code that still writes ``<skill_root>/config/projects-registry.yaml``
  there (``init-project.sh``'s registry bootstrap, in particular) hits
  "permission denied" and — because these scripts use ``set -euo
  pipefail`` — aborts the whole wizard.
- **A writable clone that already had the file tracked.** The tracked→
  untracked transition this fix performs means a plain ``git pull`` DELETES
  the working-tree file (ordinary git behaviour, not a bug in git). The next
  wizard run then silently recreates an empty one with just the project
  being initialised, and a portfolio-wide command (``monthly-runner.sh
  all``, ``pulse --global``, ``rag-index.py --global``) reports success
  having quietly dropped every other project — the exact silent-degradation
  failure mode this project's governance work (T-052 and friends) exists to
  catch, self-inflicted by this fix.

Fix: the registry never lives inside the tool tree at all, by default —
mirroring ``env_profile.global_env_path()``, which already solved this
exact problem for credentials, and ``install.sh``'s own
``attached-projects.yaml`` (line ~42: "machine-local registry ... kept
outside the store/snapshot tree").

Resolution, ``SEO_CYCLE_REGISTRY`` overrides everything:
  1. ``SEO_CYCLE_REGISTRY`` env var, if set (absolute or ``~``-relative).
  2. ``~/.seo-cycle/projects-registry.yaml``.

Migration: a registry already sitting at the legacy in-tree location
(``<skill_root>/config/projects-registry.yaml``, pre-T-061-fixup) is picked
up automatically — copied (never moved: the legacy path may be read-only,
and leaving it in place costs nothing) to the new location the first time
any reader resolves the path through this module, provided the new location
doesn't already have one. A registry is never silently ignored just because
it is sitting where the tool used to look for it.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys


def registry_path(skill_root: pathlib.Path | None = None) -> pathlib.Path:
    """Resolve the machine-local registry path and migrate a legacy
    in-tree file into it if needed (see module docstring). ``skill_root`` —
    the tool tree to check for a legacy file; pass ``None`` to skip
    migration (e.g. tests that only care about the resolved path)."""
    override = os.environ.get("SEO_CYCLE_REGISTRY")
    target = pathlib.Path(override).expanduser() if override else default_registry_path()
    _migrate_legacy(target, skill_root)
    return target


def default_registry_path() -> pathlib.Path:
    return pathlib.Path.home() / ".seo-cycle" / "projects-registry.yaml"


def legacy_registry_path(skill_root: pathlib.Path) -> pathlib.Path:
    return skill_root / "config" / "projects-registry.yaml"


def _migrate_legacy(target: pathlib.Path, skill_root: pathlib.Path | None) -> None:
    if target.exists() or skill_root is None:
        return
    legacy = legacy_registry_path(skill_root)
    if not legacy.is_file():
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, target)
        # `copy2` preserves the source's permission bits too — a version
        # snapshot (T-049) ships its tree read-only, so a straight copy
        # would leave the new machine-local file read-only as well, and the
        # very next write to it (appending a project) would fail the same
        # way the migration exists to prevent. This file is meant to be
        # writable machine state from here on, regardless of where it came
        # from. 0o600 (owner read/write only), not 0o644: the file holds
        # real machine paths and domains — the same sensitivity class as
        # `env_profile.global_env_path()`, which uses 0o600 for exactly this
        # reason (gate review, T-061 fix-up round 3: the two shell
        # duplicates below only added the owner-write bit onto whatever
        # mode the source had, which could leave group/other read bits
        # intact — all three implementations now agree on 0o600).
        target.chmod(0o600)
        print(
            f"реестр перенесён: {legacy} → {target}",
            file=sys.stderr,
        )
    except OSError:
        pass  # best-effort — caller treats a still-missing target as "no registry yet"
