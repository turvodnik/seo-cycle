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

    def run_install_without(self, needle: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        """Genuine mutation run: strip `needle` out of install.sh's own
        source, run the mutated copy with the SAME args/env a positive test
        uses, and return its result. A real negative control asserts the
        mutated run's behaviour actually reverts (not just that some string
        is present in the source) — see revert_guard_reintroduces_the_bug
        assertions below."""
        source = INSTALL.read_text(encoding="utf-8")
        assert needle in source, f"мутация не нашла удаляемый фрагмент: {needle!r}"
        mutated = source.replace(needle, "", 1)
        mutated_path = self.tmp / "install.mutated.sh"
        mutated_path.write_text(mutated, encoding="utf-8")
        full_env = {
            **os.environ,
            "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            **(env or {}),
        }
        return subprocess.run(
            ["bash", str(mutated_path), *args],
            env=full_env, capture_output=True, text=True,
        )


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


class UpgradeAllHonestyTest(InstallerFixture):
    """R7: fixing R3 (no network in --sync) must not silently disable the
    origin/SHA check for --upgrade-all, which reuses --sync's code path
    (SYNC_ONLY=1) internally but — unlike a real --sync — already has
    network (it just ran ensure_store) and is exactly what T-055 runs
    against four live sites. NETWORK_ALLOWED, not SYNC_ONLY, must gate the
    origin check in ensure_worktree()."""

    def test_upgrade_all_rejects_a_tag_diverged_from_origin(self) -> None:
        # A real attach registers the project (registry_update) and writes
        # the honest, origin-verified commit to the lock.
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        original_commit = self.read_lock()["external"]["seo-cycle"]["commit"]

        # Diverge CORE's v1.0.0 locally without ever pushing — origin still
        # has the ORIGINAL commit under that tag name (same setup as the
        # same-named-tag test above, R6).
        (self.core / "VERSION").write_text("1.0.0-upgrade-all-drift\n", encoding="utf-8")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "local drift")
        _git(self.core, "tag", "-f", "v1.0.0")

        proc2 = self.run_install("--upgrade-all", "--pin", "v1.0.0")
        self.assertNotEqual(
            proc2.returncode, 0,
            "upgrade-all обязан отказать на разошедшемся с origin теге, а не "
            f"переписать лок — stdout/stderr: {proc2.stdout + proc2.stderr!r}",
        )
        self.assertEqual(
            self.read_lock()["external"]["seo-cycle"]["commit"], original_commit,
            "upgrade-all не должен переписывать лок расходящимся с origin коммитом",
        )


class UpgradeAllRejectsSyncTest(InstallerFixture):
    """O1: `--upgrade-all --sync` is undocumented and silently bypassed the
    origin/SHA check (NETWORK_ALLOWED stays 0 from the user's --sync and is
    never reset by upgrade_all()'s internal SYNC_ONLY=1 reuse of
    attach_project()). Must be refused outright — a diverged tag must not
    get written to the lock with exit code 0 (the scenario the T-049 review
    accepted with a SINGLE-REVIEWER caveat)."""

    def test_upgrade_all_with_sync_and_diverged_tag_is_rejected_and_lock_untouched(self) -> None:
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        lock_before = self.lock_path().read_bytes()
        import hashlib
        md5_before = hashlib.md5(lock_before).hexdigest()

        # Diverge CORE's v1.0.0 locally without ever pushing (same setup as
        # UpgradeAllHonestyTest) — a --sync run must not silently accept it.
        (self.core / "VERSION").write_text("1.0.0-upgrade-all-sync-drift\n", encoding="utf-8")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "local drift")
        _git(self.core, "tag", "-f", "v1.0.0")

        proc2 = self.run_install("--upgrade-all", "--sync", "--pin", "v1.0.0")
        self.assertNotEqual(
            proc2.returncode, 0,
            f"--upgrade-all --sync обязан отказать, а не молча переписать лок — {proc2.stdout + proc2.stderr!r}",
        )
        md5_after = hashlib.md5(self.lock_path().read_bytes()).hexdigest()
        self.assertEqual(md5_before, md5_after, "лок не должен быть переписан")

    def test_reverting_the_guard_reintroduces_the_bug(self) -> None:
        """Genuine mutation, not a string grep: run the SAME diverged-tag
        scenario against install.sh with the O1 guard block physically
        removed. If the guard is what's protecting the lock, its removal
        must reproduce the original bug (exit 0, lock rewritten) — proving
        this test class actually exercises the fix."""
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        original_commit = self.read_lock()["external"]["seo-cycle"]["commit"]

        (self.core / "VERSION").write_text("1.0.0-mutation-drift\n", encoding="utf-8")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "local drift")
        _git(self.core, "tag", "-f", "v1.0.0")

        guard = (
            'if [ "$MODE" = "upgrade-all" ] && [ "$SYNC_ONLY" = "1" ]; then\n'
            '    echo "ERROR: --upgrade-all не принимает --sync — эта комбинация обходит сверку origin/SHA (O1). '
            'Используй install.sh --upgrade-all [--pin T]." >&2\n'
            '    exit 2\n'
            'fi\n'
        )
        mutated_proc = self.run_install_without(guard, "--upgrade-all", "--sync", "--pin", "v1.0.0")
        self.assertEqual(
            mutated_proc.returncode, 0,
            f"без O1-guard'а комбинация должна была снова пройти (это и доказывает, что guard — единственная защита) — {mutated_proc.stdout + mutated_proc.stderr!r}",
        )
        self.assertNotEqual(
            self.read_lock()["external"]["seo-cycle"]["commit"], original_commit,
            "без guard'а мутированный прогон обязан переписать лок расходящимся коммитом — иначе тест не проверяет то, что должен",
        )


class SyncNoLockNoNetworkTest(InstallerFixture):
    """O2: latest_tag() must not make network calls under --sync even when
    a project has no lock entry yet and falls back to it for a pin."""

    def test_sync_on_unpinned_project_makes_zero_network_calls_and_refuses(self) -> None:
        """O2, per the ticket's own two options ('take it from the lock, or
        refuse honestly'): a project with no lock entry and --sync (no
        network) must NOT silently pin to an origin-unverified local tag —
        it must refuse, same as attach_project()'s existing 'could not
        resolve a version' path, while still making zero network calls."""
        real_git = shutil.which("git")
        spy_dir = self.tmp / "git-spy-o2"
        spy_dir.mkdir()
        spy_log = self.tmp / "git-spy-o2.log"
        (spy_dir / "git").write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$*" >> "{spy_log}"\n'
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8",
        )
        (spy_dir / "git").chmod(0o755)

        # No prior --project run: this project has no lock entry at all, so
        # attach_project() would otherwise fall back to latest_tag("$CORE").
        proc = self.run_install(
            "--project", str(self.project), "--sync", "--skip-init", "--no-migrate-old-global",
            env={"PATH": f"{spy_dir}:{os.environ['PATH']}"},
        )
        log_text = spy_log.read_text(encoding="utf-8") if spy_log.exists() else ""
        network_calls = [line for line in log_text.splitlines() if "ls-remote" in line or " fetch" in line]
        self.assertEqual(
            network_calls, [],
            f"--sync без лока сделал сетевые вызовы git: {network_calls!r} (stdout/stderr: {proc.stdout + proc.stderr!r})",
        )
        self.assertNotEqual(
            proc.returncode, 0,
            f"--sync без лока и без сети обязан отказать, а не молча взять непроверенный локальный тег — {proc.stdout + proc.stderr!r}",
        )
        self.assertFalse(
            self.lock_path().exists(),
            "лок не должен создаваться, когда пин взят из непроверенного локального тега",
        )

    def test_reverting_the_gate_reintroduces_the_ls_remote_call(self) -> None:
        """Genuine mutation: strip the NETWORK_ALLOWED gate out of
        latest_tag() and re-run the exact same scenario — the ls-remote
        call and the silent pin must both come back, proving the gate (not
        something else) is what the positive test is checking."""
        real_git = shutil.which("git")
        spy_dir = self.tmp / "git-spy-o2-mutant"
        spy_dir.mkdir()
        spy_log = self.tmp / "git-spy-o2-mutant.log"
        (spy_dir / "git").write_text(
            "#!/usr/bin/env bash\n"
            f'echo "$*" >> "{spy_log}"\n'
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8",
        )
        (spy_dir / "git").chmod(0o755)

        guard = (
            'if [ "$NETWORK_ALLOWED" != "1" ]; then\n'
            '        warn "--sync: сеть отключена — версию беру только из лока/--pin, локальные теги без сверки с origin не использую (O2)" >&2\n'
            '        return 0\n'
            '    fi\n'
        )
        mutated_proc = self.run_install_without(
            guard, "--project", str(self.project), "--sync", "--skip-init", "--no-migrate-old-global",
            env={"PATH": f"{spy_dir}:{os.environ['PATH']}"},
        )
        log_text = spy_log.read_text(encoding="utf-8") if spy_log.exists() else ""
        network_calls = [line for line in log_text.splitlines() if "ls-remote" in line]
        self.assertTrue(
            network_calls,
            f"без O2-guard'а latest_tag() должна была снова сделать ls-remote — {mutated_proc.stdout + mutated_proc.stderr!r}",
        )


class WorktreeNotClonedOverTest(unittest.TestCase):
    """O3: install.sh must not mistake a git worktree (linked working tree,
    `.git` is a FILE) for "not a git repo" and clone fresh over it — the
    live incident during a T-051 run that destroyed uncommitted work and,
    as a side effect, re-pointed ~/.local/bin/seo-cycle."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-o3-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

        self.origin = self.tmp / "origin.git"
        _git(self.tmp, "init", "--bare", "-q", str(self.origin))
        self.seed = self.tmp / "seed"
        _git(self.tmp, "clone", "-q", str(self.origin), str(self.seed))
        (self.seed / "README.md").write_text("seed\n", encoding="utf-8")
        _git(self.seed, "checkout", "-q", "-B", "main")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "seed")
        _git(self.seed, "push", "-q", "origin", "main")
        _git(self.origin, "symbolic-ref", "HEAD", "refs/heads/main")

        # The would-be CORE path is a real git *worktree* off the seed clone
        # — .git there is a file, not a directory — with an uncommitted
        # change and a branch never pushed anywhere, exactly the shape of
        # the T-051 incident.
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.shared = self.home / ".codex" / "vendor"
        self.shared.mkdir(parents=True)
        self.core = self.shared / "seo-cycle"
        _git(self.seed, "worktree", "add", "-q", "-b", "feature/uncommitted-work", str(self.core))
        (self.core / "WORK_IN_PROGRESS.txt").write_text("не закоммичено\n", encoding="utf-8")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "uncommitted branch work")

        self.local_bin = self.home / ".local" / "bin"
        self.local_bin.mkdir(parents=True)
        self.shim = self.local_bin / "seo-cycle"
        self.shim_target = self.tmp / "previous-shim-target"
        self.shim_target.write_text("previous version marker\n", encoding="utf-8")
        self.shim.symlink_to(self.shim_target)

    def _git_log(self, cwd: pathlib.Path) -> str:
        return subprocess.run(
            ["git", "-C", str(cwd), "log", "--oneline"],
            capture_output=True, text=True, check=True,
        ).stdout

    def test_installer_refuses_instead_of_cloning_over_the_worktree(self) -> None:
        log_before = self._git_log(self.core)
        branch_before = subprocess.run(
            ["git", "-C", str(self.core), "branch", "--show-current"],
            capture_output=True, text=True, check=True,
        ).stdout
        status_before = subprocess.run(
            ["git", "-C", str(self.core), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout
        shim_target_before = os.readlink(self.shim)

        proc = subprocess.run(
            ["bash", str(INSTALL)],
            env={
                **os.environ,
                "HOME": str(self.home),
                "SEO_CYCLE_SHARED_DIR": str(self.shared),
                "SEO_CYCLE_CORE": str(self.core),
                "SEO_CYCLE_REPO": str(self.origin),
            },
            capture_output=True, text=True,
        )

        self.assertNotEqual(
            proc.returncode, 0,
            f"установщик обязан отказать на worktree, а не клонировать поверх — {proc.stdout + proc.stderr!r}",
        )
        self.assertEqual(log_before, self._git_log(self.core), "git log в worktree не должен измениться")
        self.assertEqual(
            branch_before,
            subprocess.run(
                ["git", "-C", str(self.core), "branch", "--show-current"],
                capture_output=True, text=True, check=True,
            ).stdout,
            "ветка worktree должна остаться той же",
        )
        self.assertEqual(
            status_before,
            subprocess.run(
                ["git", "-C", str(self.core), "status", "--porcelain"],
                capture_output=True, text=True, check=True,
            ).stdout,
            "git status в worktree не должен измениться",
        )
        self.assertTrue(self.core.is_dir(), "каталог worktree должен остаться на месте")
        self.assertTrue((self.core / "WORK_IN_PROGRESS.txt").exists(), "несохранённая работа должна остаться нетронутой")
        self.assertEqual(os.readlink(self.shim), shim_target_before, "шим ~/.local/bin/seo-cycle не должен быть переписан")

    def test_reverting_the_guard_reintroduces_the_clone_over_incident(self) -> None:
        """Genuine mutation: strip the O3 refusal branch out of
        install_or_update_repo() and re-run on the exact same worktree. The
        original incident (backup + fresh clone over it) must come back —
        proving the guard, not something else, is what stops it."""
        source = INSTALL.read_text(encoding="utf-8")
        guard = (
            '    if is_git_worktree_checkout "$dest"; then\n'
            "        # O3 (live incident during a T-051 run): the old `test -d .git` check\n"
            "        # saw a worktree's gitfile-not-a-directory .git and treated the\n"
            "        # worktree as an empty/foreign directory, backing it up and cloning\n"
            "        # fresh over it — silently relocating someone's uncommitted branch\n"
            "        # and, as a side effect, re-pointing ~/.local/bin/seo-cycle at the\n"
            "        # freshly cloned store. Refuse instead of guessing: this is either a\n"
            "        # misconfigured SEO_CYCLE_CORE/SEO_KEYWORDS_CORE, or a real working\n"
            "        # copy that must not be touched by an installer.\n"
            '        echo "ERROR: $dest — это git worktree (рабочая копия с несохранённой работой), а не место для клона $label. Установщик отказывается клонировать/переносить его (O3). Укажи корректный путь для хранилища или убери этот worktree вручную." >&2\n'
            "        exit 1\n"
            "    fi\n"
        )
        assert guard in source, "мутация не нашла O3 guard-блок в install.sh"
        mutated = source.replace(guard, "", 1)
        mutated_path = self.tmp / "install.mutated.sh"
        mutated_path.write_text(mutated, encoding="utf-8")

        log_before = self._git_log(self.core)
        proc = subprocess.run(
            ["bash", str(mutated_path)],
            env={
                **os.environ,
                "HOME": str(self.home),
                "SEO_CYCLE_SHARED_DIR": str(self.shared),
                "SEO_CYCLE_CORE": str(self.core),
                "SEO_CYCLE_REPO": str(self.origin),
            },
            capture_output=True, text=True,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"без O3-guard'а установщик должен был снова 'успешно' клонировать поверх worktree — {proc.stdout + proc.stderr!r}",
        )
        self.assertIn(
            "клонирую", proc.stdout + proc.stderr,
            "без guard'а должен воспроизвестись исходный инцидент — backup + git clone поверх",
        )
        self.assertNotEqual(
            log_before, self._git_log(self.core),
            "без guard'а git log в CORE обязан был измениться (worktree подменён свежим клоном) — иначе мутация ничего не тестирует",
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


class NoSilentDefaultPinsTest(unittest.TestCase):
    """Static guard for R4: a mutation that reintroduces the old
    kw_pin="HEAD" default (D5 renamed rather than fixed) must be caught even
    without running the slower git-fixture tests above. Mirrors the
    pin="main" acceptance check from the original ticket."""

    def test_no_silent_head_or_main_default_for_any_tool_pin(self) -> None:
        source = INSTALL.read_text(encoding="utf-8")
        self.assertNotIn(
            'kw_pin="HEAD"', source,
            "seo-keywords не должен молча подставлять HEAD как псевдо-пин (R4/D5)",
        )
        self.assertNotIn(
            'pin="main"', source,
            "ни один тег не должен молча откатываться на main (D5)",
        )


if __name__ == "__main__":
    unittest.main()
