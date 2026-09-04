#!/usr/bin/env python3
"""Contract tests for install.sh (T-049): honest tags, snapshot/SHA
reconciliation, honest detach, offline --sync, project-pinned shim.

All fixtures live under a temporary HOME so the real machine's
~/.codex/vendor, ~/.local/bin/seo-cycle and ~/.agents are never touched.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"


def _git(cwd: pathlib.Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=full_env,
        capture_output=True, text=True, check=True,
    )


class InstallerFixture(unittest.TestCase):
    """Builds an isolated origin+CORE pair and an isolated HOME per test."""

    def setUp(self) -> None:
        if yaml is None:
            self.skipTest("PyYAML is required")
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-installer-контракты-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

        self.origin = self.tmp / "origin.git"
        _git(self.tmp, "init", "--bare", "-q", str(self.origin))

        self.seed = self.tmp / "seed"
        _git(self.tmp, "clone", "-q", str(self.origin), str(self.seed))
        (self.seed / "SKILL.md").write_text("# fake seo-cycle\n", encoding="utf-8")
        (self.seed / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        bin_dir = self.seed / "bin"
        bin_dir.mkdir()
        (bin_dir / "seo-cycle").write_text(
            "#!/usr/bin/env bash\necho pin:$(cat \"$(dirname \"$0\")/../VERSION\")\n",
            encoding="utf-8",
        )
        (bin_dir / "seo-cycle").chmod(0o755)
        _git(self.seed, "checkout", "-q", "-B", "main")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "seed")
        _git(self.seed, "tag", "v1.0.0")
        _git(self.seed, "push", "-q", "origin", "main", "--tags")
        # A bare repo's default branch follows the runner's git config
        # (init.defaultBranch); pin origin's HEAD symref to "main" explicitly
        # so a clone always checks out a real branch regardless of that default.
        _git(self.origin, "symbolic-ref", "HEAD", "refs/heads/main")

        # Isolated HOME: nothing this test does can touch the real machine's
        # ~/.local/bin, ~/.codex or ~/.agents.
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.shared = self.home / ".codex" / "vendor"
        self.core = self.shared / "seo-cycle"
        _git(self.tmp, "clone", "-q", str(self.origin), str(self.core))

        self.project = self.tmp / "проект с пробелом"
        self.project.mkdir()

    def run_install(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        full_env = {
            **os.environ,
            "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            **(env or {}),
        }
        return subprocess.run(
            ["bash", str(INSTALL), *args],
            env=full_env, capture_output=True, text=True,
        )

    def lock_path(self) -> pathlib.Path:
        return self.project / ".agents" / "external-skills.lock.yaml"

    def read_lock(self) -> dict:
        p = self.lock_path()
        if not p.exists():
            return {}
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


class TagNotOnOriginTest(InstallerFixture):
    def test_local_only_tag_is_rejected(self) -> None:
        _git(self.core, "tag", "v9.9.9-local-only")  # never pushed

        proc = self.run_install(
            "--project", str(self.project), "--pin", "v9.9.9-local-only",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(self.lock_path().exists(), "лок не должен создаваться при отказе")

    def test_same_named_tag_pointing_at_a_different_commit_is_rejected(self) -> None:
        """R6/D3: a tag existing on origin BY NAME is not enough — if the
        local repo's same-named tag points at a different commit (stale
        local clone, or the tag was re-pointed only locally), attaching it
        must fail rather than silently accept an unverifiable commit."""
        # Diverge local core's v1.0.0 from what's on origin, without ever
        # pushing the change — origin still has the ORIGINAL commit under
        # that tag name.
        (self.core / "VERSION").write_text("1.0.0-local-drift\n", encoding="utf-8")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "local drift")
        _git(self.core, "tag", "-f", "v1.0.0")  # local-only repoint, never pushed

        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(self.lock_path().exists(), "лок не должен создаваться при расхождении SHA с origin")


class SnapshotSHAReconciliationTest(InstallerFixture):
    def test_moved_tag_rebuilds_snapshot_and_lock(self) -> None:
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        old_commit = self.read_lock()["external"]["seo-cycle"]["commit"]

        # Move the tag to a new commit (a re-tagged release).
        (self.core / "VERSION").write_text("1.0.1\n", encoding="utf-8")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "retag")
        _git(self.core, "tag", "-f", "v1.0.0")
        _git(self.core, "push", "-q", "-f", "origin", "main", "--tags")

        proc2 = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
        self.assertIn("пересобран", proc2.stdout + proc2.stderr)
        new_commit = self.read_lock()["external"]["seo-cycle"]["commit"]
        self.assertNotEqual(old_commit, new_commit)

        snapshot = self.shared / "versions" / "seo-cycle" / "v1.0.0"
        self.assertEqual(
            subprocess.run(["git", "-C", str(snapshot), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip(),
            new_commit,
        )


class DetachHonestTest(InstallerFixture):
    def test_detach_cleans_lock_and_does_not_create_missing_path(self) -> None:
        self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertIn("seo-cycle", self.read_lock().get("external", {}))

        proc = self.run_install("--project", str(self.project), "--detach")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("seo-cycle", self.read_lock().get("external", {}))

    def test_detach_on_typo_path_is_an_error_not_a_silent_success(self) -> None:
        typo = self.tmp / "проект-с-опечаткой"
        self.assertFalse(typo.exists())
        proc = self.run_install("--project", str(typo), "--detach")
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(typo.exists(), "detach не должен создавать каталог по опечатке")


class SyncOfflineTest(InstallerFixture):
    def test_sync_works_when_the_transport_is_blocked(self) -> None:
        self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        proc = self.run_install(
            "--project", str(self.project), "--sync",
            env={"GIT_ALLOW_PROTOCOL": ""},
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("seo-cycle", self.read_lock().get("external", {}))

    def test_sync_makes_zero_ls_remote_calls(self) -> None:
        """R3 negative control: GIT_ALLOW_PROTOCOL= only proves --sync
        survives an instantly-refused transport, not that it never tried —
        on a genuinely dead network each blocked ls-remote can hang tens of
        seconds instead of failing fast. A git spy that logs every
        invocation is the actual proof --sync makes no network calls."""
        self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )

        real_git = shutil.which("git")
        spy_dir = self.tmp / "git-spy"
        spy_dir.mkdir()
        spy_log = self.tmp / "git-spy.log"
        (spy_dir / "git").write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$*" >> "{spy_log}"\n'
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8",
        )
        (spy_dir / "git").chmod(0o755)

        proc = self.run_install(
            "--project", str(self.project), "--sync",
            env={"PATH": f"{spy_dir}:{os.environ['PATH']}"},
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        log_text = spy_log.read_text(encoding="utf-8") if spy_log.exists() else ""
        network_calls = [line for line in log_text.splitlines() if "ls-remote" in line or " fetch" in line]
        self.assertEqual(
            network_calls, [],
            f"--sync сделал сетевые вызовы git: {network_calls!r}",
        )


class ShimPinSelectionTest(unittest.TestCase):
    """Exercises bin/seo-cycle's own upward-search redirect (D7) directly,
    independent of install.sh — two fake SKILL_ROOTs, one is the project pin."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-shim-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

        real_launcher = (ROOT / "bin" / "seo-cycle").read_text(encoding="utf-8")

        def make_root(label: str) -> pathlib.Path:
            root = self.tmp / label
            (root / "bin").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "bin" / "seo-cycle").write_text(real_launcher, encoding="utf-8")
            (root / "scripts" / "seo_cycle_cli.py").write_text(
                f'def main():\n    print("{label}")\n    return 0\n', encoding="utf-8"
            )
            return root

        self.store_head = make_root("store-head")
        self.pinned = make_root("project-pin")

        self.project = self.tmp / "проект с пробелом"
        (self.project / ".agents" / "external").mkdir(parents=True)
        # symlink, same as install.sh's ensure_surfaces/attach_project would create
        (self.project / ".agents" / "external" / "seo-cycle").symlink_to(self.pinned, target_is_directory=True)

    def test_global_shim_run_from_project_redirects_to_pin(self) -> None:
        proc = subprocess.run(
            ["python3", str(self.store_head / "bin" / "seo-cycle")],
            cwd=str(self.project), capture_output=True, text=True,
        )
        self.assertEqual(proc.stdout.strip(), "project-pin", proc.stdout + proc.stderr)

    def test_shim_run_outside_any_project_uses_own_root_and_warns(self) -> None:
        outside = self.tmp  # no .agents/external/seo-cycle above this
        proc = subprocess.run(
            ["python3", str(self.store_head / "bin" / "seo-cycle")],
            cwd=str(outside), capture_output=True, text=True,
        )
        self.assertEqual(proc.stdout.strip(), "store-head", proc.stdout + proc.stderr)
        self.assertIn("версия хранилища, не пин проекта", proc.stderr)


if __name__ == "__main__":
    unittest.main()
