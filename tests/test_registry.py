#!/usr/bin/env python3
"""Tests for the machine-local project registry (T-061 gate fix-up).

T-061 first moved the real registry out of git tracking but left it at its
traditional in-tree location (``<skill_root>/config/projects-registry.yaml``).
The gate returned it for two regressions that a fresh worktree can't show but
a real install does:

1. A project pinned to a read-only version snapshot (T-049) — writing to the
   in-tree path there fails with "permission denied" and, under `set -e`,
   aborts the whole `init-project.sh` wizard.
2. A writable clone that already had the file tracked — `git pull` deletes a
   tracked-turned-untracked path, and the wizard silently recreates an empty
   registry with just the project currently being initialised. A
   portfolio-wide command then reports success having quietly dropped every
   other project.

The fix moves the default location out of the tool tree entirely
(``~/.seo-cycle/projects-registry.yaml``, mirroring env_profile.py's
``global_env_path()``), overridable via ``SEO_CYCLE_REGISTRY``, with
automatic (copy, never move/delete) migration of a legacy in-tree file.
This file covers exactly the four checks the gate asked for, plus the unit
building blocks in ``seo_cycle_core.registry``.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.registry import default_registry_path, legacy_registry_path, registry_path  # noqa: E402

INIT_PROJECT = SCRIPTS / "init-project.sh"
MONTHLY_RUNNER = SCRIPTS / "monthly-runner.sh"


def _force_rmtree(path: pathlib.Path) -> None:
    """Undo a read-only tree (chmod everything back to writable) before
    ``shutil.rmtree`` — a plain rmtree on a read-only-simulated snapshot
    directory fails the same way a real one would."""
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                (pathlib.Path(root) / name).chmod(0o700)
            except OSError:
                pass
    try:
        path.chmod(0o700)
    except OSError:
        pass
    shutil.rmtree(path, ignore_errors=True)


def _make_readonly(path: pathlib.Path) -> None:
    for root, dirs, files in os.walk(path):
        for name in files + dirs:
            p = pathlib.Path(root) / name
            p.chmod(p.stat().st_mode & ~0o222)
    path.chmod(path.stat().st_mode & ~0o222)


class RegistryPathResolutionTest(unittest.TestCase):
    """Unit-level: seo_cycle_core.registry building blocks."""

    def setUp(self) -> None:
        self._old_registry_env = os.environ.pop("SEO_CYCLE_REGISTRY", None)
        self.addCleanup(self._restore_registry_env)
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="seo-registry-home-"))
        self.addCleanup(lambda: shutil.rmtree(self.home, ignore_errors=True))
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self.addCleanup(self._restore_home)

    def _restore_registry_env(self) -> None:
        if self._old_registry_env is not None:
            os.environ["SEO_CYCLE_REGISTRY"] = self._old_registry_env
        else:
            os.environ.pop("SEO_CYCLE_REGISTRY", None)

    def _restore_home(self) -> None:
        if self._old_home is not None:
            os.environ["HOME"] = self._old_home
        else:
            os.environ.pop("HOME", None)

    def test_default_path_lives_outside_any_tool_tree(self) -> None:
        self.assertEqual(registry_path(None), self.home / ".seo-cycle" / "projects-registry.yaml")
        self.assertEqual(default_registry_path(), self.home / ".seo-cycle" / "projects-registry.yaml")

    def test_env_override_wins_over_default(self) -> None:
        custom = self.home / "custom-dir" / "reg.yaml"
        os.environ["SEO_CYCLE_REGISTRY"] = str(custom)
        self.assertEqual(registry_path(None), custom)

    def test_legacy_in_tree_file_is_migrated_not_ignored(self) -> None:
        skill_root = pathlib.Path(tempfile.mkdtemp(prefix="seo-registry-tool-"))
        self.addCleanup(lambda: shutil.rmtree(skill_root, ignore_errors=True))
        legacy = legacy_registry_path(skill_root)
        legacy.parent.mkdir(parents=True)
        legacy_content = "projects:\n  - name: Legacy\n    path: /some/path\n"
        legacy.write_text(legacy_content, encoding="utf-8")

        target = registry_path(skill_root)

        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(encoding="utf-8"), legacy_content)
        self.assertTrue(legacy.exists(), "legacy file must be copied, never deleted")

    def test_migrated_file_is_writable_even_when_legacy_was_readonly(self) -> None:
        """A version snapshot (T-049) ships its whole tree read-only —
        migrating out of it must not carry the read-only bit along, or the
        very next write (appending a project) fails the same way."""
        skill_root = pathlib.Path(tempfile.mkdtemp(prefix="seo-registry-ro-tool-"))
        legacy = legacy_registry_path(skill_root)
        legacy.parent.mkdir(parents=True)
        legacy.write_text("projects: []\n", encoding="utf-8")
        legacy.chmod(0o444)
        self.addCleanup(lambda: _force_rmtree(skill_root))

        target = registry_path(skill_root)

        self.assertTrue(os.access(target, os.W_OK), "migrated registry must be writable")
        with target.open("a", encoding="utf-8") as fh:
            fh.write("# appended without raising\n")

    def test_existing_target_wins_legacy_is_not_reapplied(self) -> None:
        skill_root = pathlib.Path(tempfile.mkdtemp(prefix="seo-registry-tool2-"))
        self.addCleanup(lambda: shutil.rmtree(skill_root, ignore_errors=True))
        legacy = legacy_registry_path(skill_root)
        legacy.parent.mkdir(parents=True)
        legacy.write_text("projects:\n  - name: Legacy\n", encoding="utf-8")

        target = default_registry_path()
        target.parent.mkdir(parents=True)
        target.write_text("projects:\n  - name: Real\n", encoding="utf-8")

        resolved = registry_path(skill_root)
        content = resolved.read_text(encoding="utf-8")
        self.assertIn("Real", content)
        self.assertNotIn("Legacy", content)


@unittest.skipIf(yaml is None, "PyYAML is required")
class RegistryBootstrapIntegrationTest(unittest.TestCase):
    """Subprocess-level: the actual bash entry points, the ones the gate
    caught regressing. Neither scenario sets SEO_CYCLE_SKIP_REGISTRY=1 —
    the whole point is to exercise the registry write path for real, unlike
    tests/test_init_project.py's two existing tests."""

    def setUp(self) -> None:
        self.home = pathlib.Path(tempfile.mkdtemp(prefix="seo-registry-int-home-"))
        self.addCleanup(lambda: shutil.rmtree(self.home, ignore_errors=True))

    def test_readonly_version_snapshot_does_not_abort_the_wizard(self) -> None:
        snapshot = pathlib.Path(tempfile.mkdtemp(prefix="seo-registry-snapshot-"))
        self.addCleanup(lambda: _force_rmtree(snapshot))
        shutil.copytree(SCRIPTS, snapshot / "scripts")
        shutil.copytree(ROOT / "config", snapshot / "config")
        (snapshot / "config" / "projects-registry.yaml").write_text(
            "projects:\n"
            "  - name: \"Legacy\"\n"
            "    path: \"/path/to/legacy-project\"\n"
            "    region_profile: ru\n"
            "    cms: wordpress\n"
            "    status: active\n"
            "    monthly_automation: true\n",
            encoding="utf-8",
        )
        _make_readonly(snapshot)

        project = pathlib.Path(tempfile.mkdtemp(prefix="seo-registry-newproj-"))
        self.addCleanup(lambda: shutil.rmtree(project, ignore_errors=True))

        proc = subprocess.run(
            ["bash", str(snapshot / "scripts" / "init-project.sh"), "--non-interactive"],
            cwd=project,
            env={**os.environ, "HOME": str(self.home), "SEO_CYCLE_NON_INTERACTIVE": "1"},
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, "wizard aborted:\n" + proc.stdout + proc.stderr)

        registry = self.home / ".seo-cycle" / "projects-registry.yaml"
        self.assertTrue(registry.exists(), "registry was not created in the machine-local location")
        data = yaml.safe_load(registry.read_text(encoding="utf-8"))
        names = {p["name"] for p in data["projects"]}
        self.assertIn("Legacy", names, "pre-existing (migrated) project lost")
        self.assertIn("MyProject", names, "newly-initialised project not appended")

        # Nothing was ever written into the read-only snapshot:
        self.assertTrue((snapshot / "config" / "projects-registry.yaml").exists())

    def test_monthly_runner_all_sees_the_full_portfolio_after_a_pull(self) -> None:
        """Simulates the surviving state after a `git pull` on a writable
        clone that used to track the registry: the file already sits at the
        new machine-local location (as it would once the owner has adopted
        this fix), untouched by anything happening inside the git tree."""
        registry = self.home / ".seo-cycle" / "projects-registry.yaml"
        registry.parent.mkdir(parents=True)
        entries = "".join(
            f"  - name: \"{n}\"\n"
            f"    path: \"/tmp/seo-registry-nonexistent-{n}\"\n"
            "    region_profile: ru\n"
            "    cms: wordpress\n"
            "    status: active\n"
            "    monthly_automation: true\n"
            for n in ("A", "B", "C")
        )
        registry.write_text(f"projects:\n{entries}", encoding="utf-8")

        proc = subprocess.run(
            ["bash", str(MONTHLY_RUNNER), "all"],
            cwd=ROOT,
            env={**os.environ, "HOME": str(self.home)},
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for name in ("A", "B", "C"):
            self.assertIn(f"/tmp/seo-registry-nonexistent-{name}", proc.stdout,
                          f"project {name} missing from the portfolio run — dropped to fewer than 3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
