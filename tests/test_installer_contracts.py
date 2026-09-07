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


_REAL_HOME = pathlib.Path(os.path.expanduser("~")).resolve()


def _assert_sandboxed_home(env: dict) -> None:
    """Hard gate before every install.sh invocation in this file (T-064
    incident, round 2): a sequencing mistake once ran the installer with an
    unoverridden real HOME and rewrote all four live projects' locks. `env`
    must carry a HOME that is (a) explicitly set, (b) not the real one, and
    (c) actually inside this test's own tempdir — never trust "it's probably
    fine", assert it every single time, mirroring the reviewer's lib.sh."""
    home = env.get("HOME")
    assert home, "install.sh invoked without an explicit HOME override"
    home_path = pathlib.Path(home).resolve()
    assert home_path != _REAL_HOME, f"REFUSING to run install.sh against the real HOME: {home_path}"
    tmp_root = pathlib.Path(tempfile.gettempdir()).resolve()
    assert str(home_path).startswith(str(tmp_root)), \
        f"HOME does not look like a sandbox tempdir ({tmp_root}): {home_path}"


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
            # T-091 (F-18): without this, ensure_python_deps() installed
            # pyyaml/requests/pillow/beautifulsoup4/google-auth into the
            # machine running the test suite (the SYSTEM python, with
            # --break-system-packages on the third fallback) and made real
            # PyPI network calls on every test that reaches ensure_store().
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
            **(env or {}),
        }
        _assert_sandboxed_home(full_env)
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
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
            **(env or {}),
        }
        _assert_sandboxed_home(full_env)
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
        """R6/D3, adapted for T-091: a tag existing on origin BY NAME is not
        enough. T-091's force-fetch (F-12/13) now SELF-HEALS a local-only
        repoint on every plain (non-`--sync`) attach — that fetch runs
        before this scenario's pin is even resolved and force-rewrites the
        local tag back to match origin, which is exactly the fix this
        ticket exists to make (see UpdateStoreForceTagsTest for that path
        tested directly). The surviving case where a diverged local tag is
        NOT auto-corrected is `--sync`, which makes zero network calls by
        design (F-14's whole reason for existing) — a local-only repoint of
        an ALREADY-confirmed tag, done without a fresh fetch, must still be
        rejected there rather than silently trusted from local `git tag`
        state alone."""
        # A real attach first — this fetches and confirms v1.0.0 against
        # origin, writing the origin-tags manifest T-091 introduced.
        proc0 = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc0.returncode, 0, proc0.stdout + proc0.stderr)
        good_commit = self.read_lock()["external"]["seo-cycle"]["commit"]

        # Diverge local core's v1.0.0 from what's on origin, without ever
        # pushing the change or re-fetching — origin still has the
        # ORIGINAL commit under that tag name, and so does the manifest.
        (self.core / "VERSION").write_text("1.0.0-local-drift\n", encoding="utf-8")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "local drift")
        _git(self.core, "tag", "-f", "v1.0.0")  # local-only repoint, never pushed/fetched

        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0", "--sync",
            "--no-migrate-old-global",
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(
            self.read_lock()["external"]["seo-cycle"]["commit"], good_commit,
            "лок не должен быть переписан расходящимся с origin коммитом",
        )


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
        """Adapted for T-091 (F-12/13): `--upgrade-all` runs `ensure_store`
        FIRST, and ensure_store's fetch is now the same force+prune-tags
        fetch as everywhere else — it self-heals a purely-local repoint of
        v1.0.0 back to origin's commit before upgrade_all() ever resolves
        the pin, instead of leaving the drift for ensure_worktree's
        ls-remote check to catch (the old, narrower fix). The assertion
        that actually matters is unchanged: the drifted commit must never
        reach the lock — only now it's because it gets corrected upstream,
        not rejected downstream, so upgrade-all is expected to SUCCEED with
        the lock back at origin's true commit, not fail."""
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
        self.assertEqual(
            proc2.returncode, 0,
            "upgrade-all обязан САМОСТОЯТЕЛЬНО исправить разошедшийся тег через "
            f"force-fetch (T-091), а не остаться на локальном дрейфе — {proc2.stdout + proc2.stderr!r}",
        )
        self.assertEqual(
            self.read_lock()["external"]["seo-cycle"]["commit"], original_commit,
            "upgrade-all не должен записывать в лок расходящийся с origin коммит "
            "(должен либо исправить тег, либо отказать — но никогда не довериться дрейфу)",
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

    def test_reverting_the_guard_alone_no_longer_reintroduces_the_bug(self) -> None:
        """T-091 update: this used to be a single-mutation revert test ("O1
        alone is the only thing protecting the lock"). It no longer is —
        T-091's force-fetch (F-12/13) runs unconditionally inside
        ensure_store() on EVERY --upgrade-all invocation (SYNC_ONLY/
        NETWORK_ALLOWED don't gate it), so even with the O1 guard stripped
        the locally-diverged tag gets healed back to origin's commit before
        upgrade_all() ever reuses SYNC_ONLY. This is defense-in-depth, not a
        broken test: it IS the "explicit failed bypass attempt" the ticket
        asks for — proving O1 is no longer the only thing standing between
        this combination and a corrupted lock. See the sibling test below
        for the mutation that strips BOTH layers and does reproduce the
        original incident."""
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
        # Bypass ATTEMPT succeeds in the sense that O1 no longer blocks the
        # combination outright — but the lock still ends up correct (either
        # self-healed to origin's true commit, or untouched), never on the
        # drifted one. That is the negative proof the ticket asks for: this
        # specific single-guard bypass does NOT reach a corrupted lock.
        self.assertEqual(
            self.read_lock()["external"]["seo-cycle"]["commit"], original_commit,
            f"обход одного лишь O1-guard'а не должен доходить до порчи лока (T-091 закрывает класс раньше) — {mutated_proc.stdout + mutated_proc.stderr!r}",
        )

    def test_reverting_all_three_guards_reintroduces_the_bug(self) -> None:
        """The genuine multi-layer mutation: this combination is now
        defended by THREE independent things — the O1 static guard, T-091's
        force-fetch (which would otherwise just self-heal the drift before
        anyone even asks), and T-091's origin-tags manifest check (F-14,
        which would otherwise reject an explicit --pin whose commit doesn't
        match the last confirmed fetch). Strip all three — O1's exit,
        fetch_tags_or_report()'s force flags (back to a plain `--tags` that
        genuinely fails to overwrite a diverged tag, per T-068's own
        finding), its enforcement of that failure, AND the manifest check —
        to simulate the exact world before any of these fixes existed. THAT
        reproduces the original incident (exit 0, lock silently kept on a
        commit that was never verified against origin), proving these
        layers together, not any one of them, are what this combination
        needs to defeat."""
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        original_commit = self.read_lock()["external"]["seo-cycle"]["commit"]

        (self.core / "VERSION").write_text("1.0.0-mutation-drift-2\n", encoding="utf-8")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "local drift")
        _git(self.core, "tag", "-f", "v1.0.0")

        source = INSTALL.read_text(encoding="utf-8")
        guard = (
            'if [ "$MODE" = "upgrade-all" ] && [ "$SYNC_ONLY" = "1" ]; then\n'
            '    echo "ERROR: --upgrade-all не принимает --sync — эта комбинация обходит сверку origin/SHA (O1). '
            'Используй install.sh --upgrade-all [--pin T]." >&2\n'
            '    exit 2\n'
            'fi\n'
        )
        force_fetch = 'fetch origin --tags --force --prune --prune-tags --quiet'
        plain_fetch = 'fetch --tags --quiet'
        store_gate = (
            '        if ! fetch_tags_or_report "$dest" "$label"; then\n'
            '            return 1\n'
            '        fi\n'
        )
        store_gate_neutered = '        fetch_tags_or_report "$dest" "$label" || true\n'
        manifest_check = 'verify_tag_against_manifest "$repo_dir" "$tag" "$tag_commit" || return 1'
        manifest_check_neutered = 'verify_tag_against_manifest "$repo_dir" "$tag" "$tag_commit" || true'
        for needle in (guard, force_fetch, store_gate, manifest_check):
            assert needle in source, f"мутация не нашла фрагмент: {needle!r}"
        mutated = (
            source.replace(guard, "", 1)
            .replace(force_fetch, plain_fetch, 1)
            .replace(store_gate, store_gate_neutered, 1)
            .replace(manifest_check, manifest_check_neutered, 1)
        )
        mutated_path = self.tmp / "install.mutated2.sh"
        mutated_path.write_text(mutated, encoding="utf-8")
        full_env = {
            **os.environ, "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
        }
        _assert_sandboxed_home(full_env)
        mutated_proc = subprocess.run(
            ["bash", str(mutated_path), "--upgrade-all", "--sync", "--pin", "v1.0.0"],
            env=full_env, capture_output=True, text=True,
        )
        self.assertEqual(
            mutated_proc.returncode, 0,
            f"со всеми тремя guard'ами снятыми комбинация должна была снова пройти — {mutated_proc.stdout + mutated_proc.stderr!r}",
        )
        self.assertNotEqual(
            self.read_lock()["external"]["seo-cycle"]["commit"], original_commit,
            "со всеми тремя guard'ами снятыми мутированный прогон обязан переписать лок расходящимся коммитом — иначе тест не проверяет то, что должен",
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

        env = {
            **os.environ,
            "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
        }
        _assert_sandboxed_home(env)
        proc = subprocess.run(
            ["bash", str(INSTALL)],
            env=env,
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
        env = {
            **os.environ,
            "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
        }
        _assert_sandboxed_home(env)
        proc = subprocess.run(
            ["bash", str(mutated_path)],
            env=env,
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


class UpgradeAllOfflineRefusesTest(InstallerFixture):
    """T-064: --upgrade-all is the exact command T-055 uses to re-pin four
    live sites onto a published tag. With origin completely unreachable it
    used to fall back to a local-only tag, rewrite every registered
    project's lock and exit 0 — an outage indistinguishable from a real
    successful re-pin. Reproduces the gate T-060 finding (offline.sh) with
    the fixture pattern already used in this file."""

    def setUp(self) -> None:
        super().setUp()
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_offline_upgrade_all_refuses_and_leaves_lock_untouched(self) -> None:
        import hashlib
        md5_before = hashlib.md5(self.lock_path().read_bytes()).hexdigest()

        offline = self.origin.with_name(self.origin.name + ".OFFLINE")
        self.origin.rename(offline)
        try:
            proc = self.run_install("--upgrade-all", "--pin", "v1.0.0")
        finally:
            offline.rename(self.origin)

        self.assertNotEqual(
            proc.returncode, 0,
            "--upgrade-all с недоступным origin обязан отказать, а не рапортовать "
            f"успех — {proc.stdout + proc.stderr!r}",
        )
        combined = proc.stdout + proc.stderr
        self.assertIn(
            "origin недоступен", combined,
            f"сообщение должно называть причину отказа — {combined!r}",
        )
        md5_after = hashlib.md5(self.lock_path().read_bytes()).hexdigest()
        self.assertEqual(
            md5_before, md5_after,
            "лок не должен быть переписан ни одним байтом при недоступном origin",
        )

    def test_reverting_the_offline_guard_alone_no_longer_reintroduces_the_bug(self) -> None:
        """T-091 update: this used to prove the T-064 `return 1` in
        ensure_worktree() was the ONLY thing standing between an offline
        origin and a silently rewritten lock. It no longer is: T-091
        (F-12/13) made ensure_store()'s own fetch (which --upgrade-all runs
        BEFORE upgrade_all() ever reaches ensure_worktree()) fail loudly on
        an unreachable origin too — so removing just the ensure_worktree
        guard no longer reintroduces the incident; the earlier gate catches
        it first. That is itself the "failed bypass attempt" this ticket
        asks to demonstrate. See the sibling test below for the mutation
        that strips BOTH layers and does reproduce the original bug."""
        source = INSTALL.read_text(encoding="utf-8")
        old = (
            '            # T-064: this second ls-remote also failing means origin is\n'
            '            # unreachable, not just missing this tag. NETWORK_ALLOWED=1\n'
            '            # means the caller (a real --sync sets it to 0 and returns\n'
            '            # before this block) wants a network-verified pin — silently\n'
            '            # trusting the local tag here let --upgrade-all re-pin all\n'
            '            # registered projects onto an unverified tag with exit code 0\n'
            '            # whenever the connection dropped mid-run (the incident this\n'
            '            # SPEC exists to fix). Refuse instead of guessing.\n'
            '            warn "origin недоступен, проверить тег $tag невозможно — перепин отменён (T-064)"\n'
            '            return 1\n'
        )
        assert old in source, "мутация не нашла T-064 offline-guard в ensure_worktree()"
        mutated = source.replace(old, "", 1)
        mutated_path = self.tmp / "install.mutated.sh"
        mutated_path.write_text(mutated, encoding="utf-8")

        import hashlib
        md5_before = hashlib.md5(self.lock_path().read_bytes()).hexdigest()

        offline = self.origin.with_name(self.origin.name + ".OFFLINE")
        self.origin.rename(offline)
        try:
            full_env = {
                **os.environ, "HOME": str(self.home),
                "SEO_CYCLE_SHARED_DIR": str(self.shared),
                "SEO_CYCLE_CORE": str(self.core),
                "SEO_CYCLE_REPO": str(self.origin),
                "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
            }
            proc = subprocess.run(
                ["bash", str(mutated_path), "--upgrade-all", "--pin", "v1.0.0"],
                env=full_env, capture_output=True, text=True,
            )
        finally:
            offline.rename(self.origin)

        # Bypass attempt: the ensure_worktree guard is gone, but the run
        # must still refuse (T-091's earlier gate) — not silently succeed.
        self.assertNotEqual(
            proc.returncode, 0,
            f"обход одного лишь ensure_worktree-guard'а не должен доходить до тихого успеха (T-091 закрывает класс раньше) — {proc.stdout + proc.stderr!r}",
        )
        md5_after = hashlib.md5(self.lock_path().read_bytes()).hexdigest()
        self.assertEqual(
            md5_before, md5_after,
            "лок не должен быть переписан ни при недоступном origin, ни при снятом ensure_worktree-guard'е",
        )

    def test_reverting_both_the_store_gate_and_the_offline_guard_reintroduces_the_bug(self) -> None:
        """The genuine two-layer mutation: strip the T-064 ensure_worktree
        guard AND neuter T-091's own ensure_store-level enforcement (make
        the mandatory repo's fetch failure non-fatal, `|| true`, same as the
        optional repo already is) — i.e. simulate the world before EITHER
        fix existed. THAT reproduces the original incident (exit 0, lock
        silently kept/rewritten from an unverified state) with origin
        offline, proving both mutations together, not just one, are what
        this scenario now needs to defeat."""
        source = INSTALL.read_text(encoding="utf-8")
        worktree_guard = (
            '            # T-064: this second ls-remote also failing means origin is\n'
            '            # unreachable, not just missing this tag. NETWORK_ALLOWED=1\n'
            '            # means the caller (a real --sync sets it to 0 and returns\n'
            '            # before this block) wants a network-verified pin — silently\n'
            '            # trusting the local tag here let --upgrade-all re-pin all\n'
            '            # registered projects onto an unverified tag with exit code 0\n'
            '            # whenever the connection dropped mid-run (the incident this\n'
            '            # SPEC exists to fix). Refuse instead of guessing.\n'
            '            warn "origin недоступен, проверить тег $tag невозможно — перепин отменён (T-064)"\n'
            '            return 1\n'
        )
        store_gate = (
            '        if ! fetch_tags_or_report "$dest" "$label"; then\n'
            '            return 1\n'
            '        fi\n'
        )
        store_gate_neutered = '        fetch_tags_or_report "$dest" "$label" || true\n'
        assert worktree_guard in source, "мутация не нашла T-064 offline-guard в ensure_worktree()"
        assert store_gate in source, "мутация не нашла T-091 store-level enforcement в install_or_update_repo()"
        mutated = source.replace(worktree_guard, "", 1).replace(store_gate, store_gate_neutered, 1)
        mutated_path = self.tmp / "install.mutated3.sh"
        mutated_path.write_text(mutated, encoding="utf-8")

        import hashlib
        md5_before = hashlib.md5(self.lock_path().read_bytes()).hexdigest()

        offline = self.origin.with_name(self.origin.name + ".OFFLINE")
        self.origin.rename(offline)
        try:
            full_env = {
                **os.environ, "HOME": str(self.home),
                "SEO_CYCLE_SHARED_DIR": str(self.shared),
                "SEO_CYCLE_CORE": str(self.core),
                "SEO_CYCLE_REPO": str(self.origin),
                "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
            }
            proc = subprocess.run(
                ["bash", str(mutated_path), "--upgrade-all", "--pin", "v1.0.0"],
                env=full_env, capture_output=True, text=True,
            )
        finally:
            offline.rename(self.origin)

        self.assertEqual(
            proc.returncode, 0,
            "с обоими guard'ами снятыми --upgrade-all с недоступным origin должен был снова "
            f"'успешно' завершиться — {proc.stdout + proc.stderr!r}",
        )
        md5_after = hashlib.md5(self.lock_path().read_bytes()).hexdigest()
        self.assertNotEqual(
            md5_before, md5_after,
            "с обоими guard'ами снятыми лок обязан был быть переписан — иначе мутация ничего не проверяет",
        )


class UpgradeAllPartialFailureReportedTest(InstallerFixture):
    """T-064 (defect 2, 🟡 partial re-pin): attach_project() fails via a hard
    `exit`, not `return` — without isolation, one project failing mid-registry
    used to kill --upgrade-all's whole loop, leaving no summary and an
    undiscoverable mixed portfolio state (reviewer's live 3-project run:
    first re-pinned, second failed, third never touched, no report at all).
    Chosen fix: isolate each project's attach — `set +e` / bare subshell with
    `set -e` restored INSIDE it / `rc=$?` / `set -e` restored here — and
    print an explicit 'перепинено / не тронуто / упало' report with a
    non-zero exit, preferred over two-phase atomicity because it needs no
    extra network round-trip and cannot itself have a distinct failure mode.

    A first version wrote `( set -e; attach_project "$p" ) || rc=$?` — the
    subshell is the LEFT operand of `||`, so bash's errexit-exemption for a
    command tested by if/&&/|| applies to it (and propagates into everything
    it calls): the inner `set -e` was inert on the gate's own system bash
    (3.2.57), and a project that failed on an unguarded command (e.g. `ln -s`
    inside replace_with_symlink) was silently counted as a success with its
    lock rewritten and its symlink left on the old version. The three tests
    below isolate the two independent things that fix depends on — one
    mutation, one behavioural difference, one test each."""

    def setUp(self) -> None:
        super().setUp()
        self.project_b = self.tmp / "project-b"
        self.project_b.mkdir()
        for proj in (self.project, self.project_b):
            proc = self.run_install(
                "--project", str(proj), "--pin", "v1.0.0",
                "--skip-init", "--no-migrate-old-global",
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _break_project_b_mkdir(self) -> None:
        # Force attach_project()'s guarded `mkdir -p ".../external"` to fail
        # for project_b only, deterministically and with zero network —
        # the directory is removed first so mkdir must actually try (and
        # fail) to create it. This failure is caught by an explicit
        # `|| exit 1` guard, independent of whether `set -e` is live.
        ext = self.project_b / ".agents" / "external"
        if ext.exists():
            shutil.rmtree(ext)
        (self.project_b / ".agents").chmod(0o500)
        self.addCleanup(lambda: (self.project_b / ".agents").chmod(0o700))

    def _break_project_b_symlink_only(self) -> None:
        # Chmod the "external" dir AFTER it already exists (from setUp's
        # successful attach): `mkdir -p` on an EXISTING directory only needs
        # to stat it, not write to it, so the guarded mkdir call SUCCEEDS
        # here — the mkdir guard never fires. Only the unguarded `rm`/`ln -s`
        # inside replace_with_symlink() need write access to the directory
        # to replace the existing symlink, and THOSE fail — a failure with
        # no explicit guard at all, caught only by `set -e` being genuinely
        # live. This isolates the inner `set -e` from the mkdir guard.
        ext = self.project_b / ".agents" / "external"
        assert (ext / "seo-cycle").is_symlink(), "setUp должен был создать симлинк до порчи прав"
        ext.chmod(0o500)
        self.addCleanup(lambda: ext.chmod(0o700))

    def test_one_project_failing_is_reported_not_silently_swallowed(self) -> None:
        self._break_project_b_mkdir()
        proc = self.run_install("--upgrade-all", "--pin", "v1.0.0")
        self.assertNotEqual(
            proc.returncode, 0,
            f"падение одного проекта из реестра обязано дать ненулевой код — {proc.stdout + proc.stderr!r}",
        )
        combined = proc.stdout + proc.stderr
        self.assertIn(str(self.project), combined, "успешный проект должен быть назван в отчёте")
        self.assertIn(str(self.project_b), combined, "упавший проект должен быть назван в отчёте")
        self.assertIn(
            "СМЕШАННОМ", combined,
            f"должен быть явный отчёт о смешанном состоянии портфеля — {combined!r}",
        )

    def test_symlink_break_on_clean_installer_reports_failure_and_keeps_lock_link_consistent(self) -> None:
        """Round-2 gate finding: the two mutation-revert tests below prove
        their point by re-inserting a REMOVED source string and asserting
        `assert old in source` — a textual anchor check, not a behavioural
        one (confirmed live: mutation C, the exact round-1 regression form
        `( set -e; … ) || rc=$?`, only trips the anchor in
        `test_reverting_all_isolation_kills_the_whole_run_silently`, not
        `test_reverting_just_the_inner_set_e_reports_a_false_success` — the
        regression that cost a whole gate round was, in effect, guarded by
        one string match and zero behavioural assertions).

        This test runs the CLEAN, unmutated install.sh (no mutation at all)
        and breaks project_b the same way — `_break_project_b_symlink_only()`
        — then asserts observable behaviour: a failing exit code, "упало" in
        the report, and — the actual point of the whole ticket — that the
        REAL symlink and the LOCK's recorded version for project_b still
        agree with each other. Under the round-1 regression (mutation C) or
        the inner-`set -e`-only regression (mutation B), this specific
        assertion is what fails: the lock gets silently rewritten to the new
        pin while the symlink is left on the old one — divergence, not mere
        'unchanged'."""
        self._break_project_b_symlink_only()
        proc = self.run_install("--upgrade-all", "--pin", "v1.0.0")

        self.assertNotEqual(
            proc.returncode, 0,
            f"поломанный project_b обязан дать ненулевой код на чистом install.sh — {proc.stdout + proc.stderr!r}",
        )
        combined = proc.stdout + proc.stderr
        self.assertIn(
            "упало", combined,
            f"поломанный project_b должен быть назван в разделе 'упало' — {combined!r}",
        )

        lock_path = self.project_b / ".agents" / "external-skills.lock.yaml"
        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8")) or {}
        recorded_version = ((lock.get("external") or {}).get("seo-cycle") or {}).get("version")
        symlink_path = self.project_b / ".agents" / "external" / "seo-cycle"
        actual_target_version = pathlib.Path(os.readlink(symlink_path)).name
        self.assertEqual(
            recorded_version, actual_target_version,
            f"лок ({recorded_version!r}) и реальная ссылка ({actual_target_version!r}) "
            "обязаны совпадать — их расхождение и есть дефект, который стоил круга гейта",
        )

    def _run_mutated(self, mutated_source: str, *args: str) -> subprocess.CompletedProcess:
        mutated_path = self.tmp / "install.mutated.sh"
        mutated_path.write_text(mutated_source, encoding="utf-8")
        full_env = {
            **os.environ, "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
        }
        _assert_sandboxed_home(full_env)
        return subprocess.run(
            ["bash", str(mutated_path), *args],
            env=full_env, capture_output=True, text=True,
        )

    def test_reverting_all_isolation_kills_the_whole_run_silently(self) -> None:
        """Mutation #1, isolating ONE thing: remove the isolation wrapper
        entirely (no subshell, no set +e/-e at all) — attach_project() runs
        directly in upgrade_all()'s own shell. project_b's guarded mkdir
        failure calls `exit 1` unconditionally, which now kills the WHOLE
        script (not just project_b's turn): no summary is printed, and even
        the first (successful) project is never reported."""
        source = INSTALL.read_text(encoding="utf-8")
        old = (
            '            set +e\n'
            '            ( set -e; PIN="$pin" SYNC_ONLY=1 RUN_INIT=0 DETACH=0 attach_project "$p" )\n'
            '            rc=$?\n'
            '            set -e\n'
        )
        new = (
            '            PIN="$pin" SYNC_ONLY=1 RUN_INIT=0 DETACH=0 attach_project "$p"\n'
            '            rc=$?\n'
        )
        assert old in source, "мутация не нашла isolation-обёртку в upgrade_all()"
        mutated = source.replace(old, new, 1)

        self._break_project_b_mkdir()
        proc = self._run_mutated(mutated, "--upgrade-all", "--pin", "v1.0.0")
        combined = proc.stdout + proc.stderr
        self.assertNotIn(
            "Итог --upgrade-all", combined,
            f"без изоляции итоговый отчёт вообще не должен успеть напечататься — {combined!r}",
        )

    def test_reverting_just_the_inner_set_e_reports_a_false_success(self) -> None:
        """Mutation #2, isolating the OTHER thing: keep the exact `set +e` /
        subshell / `rc=$?` / `set -e` shape, strip ONLY the inner `set -e;`
        inside the subshell. Break project_b via the symlink-only path (the
        guarded mkdir succeeds — the directory already exists — so this
        exercises solely the unguarded `rm`/`ln -s` inside
        replace_with_symlink()). Without `set -e` genuinely live inside the
        subshell, that failure is swallowed, attach_project() reaches
        write_lock_entry() anyway, and the subshell's own exit status is 0
        — project_b is wrongly counted as 'перепинено' with its lock
        rewritten and its symlink left on the old version (the exact defect
        the gate found live on bash 3.2.57)."""
        source = INSTALL.read_text(encoding="utf-8")
        old = '( set -e; PIN="$pin" SYNC_ONLY=1 RUN_INIT=0 DETACH=0 attach_project "$p" )'
        new = '( PIN="$pin" SYNC_ONLY=1 RUN_INIT=0 DETACH=0 attach_project "$p" )'
        assert old in source, "мутация не нашла inner set -e в upgrade_all()"
        mutated = source.replace(old, new, 1)

        self._break_project_b_symlink_only()
        old_symlink_target = os.readlink(self.project_b / ".agents" / "external" / "seo-cycle")
        proc = self._run_mutated(mutated, "--upgrade-all", "--pin", "v1.0.0")
        combined = proc.stdout + proc.stderr

        self.assertEqual(
            proc.returncode, 0,
            f"без inner set -e весь прогон обязан был ложно завершиться успехом — {combined!r}",
        )
        self.assertIn(
            str(self.project_b), combined,
            f"project_b должен быть в отчёте — ложно, в 'перепинено' — {combined!r}",
        )
        self.assertNotIn(
            "упало", combined,
            f"без inner set -e падение project_b не должно быть даже замечено — {combined!r}",
        )
        new_symlink_target = os.readlink(self.project_b / ".agents" / "external" / "seo-cycle")
        self.assertEqual(
            old_symlink_target, new_symlink_target,
            "симлинк должен остаться на СТАРОЙ версии несмотря на 'успешный' лок — "
            "это и есть расхождение лока и ссылки, которое ловит этот тест",
        )


class OptionalKeywordsOutageDoesNotBlockSeoCycleTest(InstallerFixture):
    """T-064 (defect 3, 🟡 sузилось): seo-keywords is documented as an
    OPTIONAL sibling (R4/D5, attach_project()'s own comment) — its origin
    being unreachable must not block the MANDATORY seo-cycle pin. The
    base install.sh degraded gracefully here (latest_tag() always returned
    0 with the ORIGINAL, pre-T-064 fallback). Fixing the mandatory path's
    honesty (latest_tag() now returns 1 when origin is unreachable) turned a
    bare `kw_pin="$(latest_tag "$KW_CORE")"` assignment into a hard abort
    of the WHOLE attach — under `set -e`, a failing command substitution
    inside a bare variable assignment DOES trip errexit (unlike the same
    substitution used as a plain argument), so seo-keywords' own outage
    started refusing seo-cycle too (caught live: gate064's kwint.sh).

    This class wires its OWN local seo-keywords origin (InstallerFixture
    does not — a real seo-keywords is cloned from GitHub in those tests,
    which cannot be made "unreachable" from a unit test)."""

    def setUp(self) -> None:
        super().setUp()
        self.kw_origin = self.tmp / "kw-origin.git"
        _git(self.tmp, "init", "--bare", "-q", str(self.kw_origin))
        kw_seed = self.tmp / "kw-seed"
        _git(self.tmp, "clone", "-q", str(self.kw_origin), str(kw_seed))
        (kw_seed / "SKILL.md").write_text("# fake seo-keywords\n", encoding="utf-8")
        _git(kw_seed, "checkout", "-q", "-B", "main")
        _git(kw_seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(kw_seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "seed")
        _git(kw_seed, "tag", "v1.3.0")
        _git(kw_seed, "push", "-q", "origin", "main", "--tags")
        _git(self.kw_origin, "symbolic-ref", "HEAD", "refs/heads/main")
        self.kw_core = self.shared / "seo-keywords"

    def run_install_with_kw(self, *args: str) -> subprocess.CompletedProcess:
        return self.run_install(*args, env={"SEO_KEYWORDS_REPO": str(self.kw_origin)})

    def test_seo_keywords_origin_down_does_not_block_seo_cycle(self) -> None:
        proc = self.run_install_with_kw(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(self.kw_core.is_dir(), "seo-keywords должен был клонироваться локально")

        kw_offline = self.kw_origin.with_name(self.kw_origin.name + ".OFFLINE")
        self.kw_origin.rename(kw_offline)
        try:
            proc2 = self.run_install_with_kw("--upgrade-all", "--pin", "v1.0.0")
        finally:
            kw_offline.rename(self.kw_origin)

        combined = proc2.stdout + proc2.stderr
        self.assertEqual(
            proc2.returncode, 0,
            f"недоступность НЕОБЯЗАТЕЛЬНОГО seo-keywords не должна блокировать "
            f"обязательный seo-cycle — {combined!r}",
        )
        self.assertIn(
            "перепинено (1)", combined,
            f"seo-cycle обязан быть перепинен несмотря на недоступный seo-keywords — {combined!r}",
        )
        lock = self.read_lock()
        self.assertEqual(lock["external"]["seo-cycle"]["version"], "v1.0.0")

    def test_reverting_the_kw_pin_fallback_blocks_seo_cycle_too(self) -> None:
        """Genuine mutation: strip the `|| kw_pin=""` fallback and re-run the
        exact same seo-keywords-outage scenario. Without it, latest_tag()'s
        honest refusal (T-064's OTHER fix, both needed together) propagates
        through the bare assignment and kills the whole attach — seo-cycle,
        which had nothing wrong with it, gets refused too."""
        source = INSTALL.read_text(encoding="utf-8")
        old = 'kw_pin="$(latest_tag "$KW_CORE")" || kw_pin=""'
        new = 'kw_pin="$(latest_tag "$KW_CORE")"'
        assert old in source, "мутация не нашла kw_pin fallback в attach_project()"
        mutated = source.replace(old, new, 1)
        mutated_path = self.tmp / "install.mutated.sh"
        mutated_path.write_text(mutated, encoding="utf-8")

        proc = self.run_install_with_kw(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        kw_offline = self.kw_origin.with_name(self.kw_origin.name + ".OFFLINE")
        self.kw_origin.rename(kw_offline)
        try:
            full_env = {
                **os.environ, "HOME": str(self.home),
                "SEO_CYCLE_SHARED_DIR": str(self.shared),
                "SEO_CYCLE_CORE": str(self.core),
                "SEO_CYCLE_REPO": str(self.origin),
                "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
                "SEO_KEYWORDS_REPO": str(self.kw_origin),
            }
            proc2 = subprocess.run(
                ["bash", str(mutated_path), "--upgrade-all", "--pin", "v1.0.0"],
                env=full_env, capture_output=True, text=True,
            )
        finally:
            kw_offline.rename(self.kw_origin)

        self.assertNotEqual(
            proc2.returncode, 0,
            "без fallback'а seo-keywords outage обязан был снова заблокировать "
            f"seo-cycle — {proc2.stdout + proc2.stderr!r}",
        )


class OrphanedWorktreeRefusesTest(unittest.TestCase):
    """T-064 (defect 3, 🟡 orphaned worktree): the O3 detector
    (is_git_worktree_checkout) required `git rev-parse --is-inside-work-tree`
    to succeed — but that call fails once the worktree's MAIN repo has been
    deleted, so an orphaned worktree slipped through undetected and the
    installer backed it up and cloned fresh over it, one step removed from
    the original O3 incident (main repo gone instead of merely a worktree)."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-orphan-"))
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

        self.home = self.tmp / "home"
        self.home.mkdir()
        self.shared = self.home / ".codex" / "vendor"
        self.shared.mkdir(parents=True)
        self.core = self.shared / "seo-cycle"
        _git(self.seed, "worktree", "add", "-q", "-b", "feature/orphan", str(self.core))
        (self.core / "WORK_IN_PROGRESS.txt").write_text("не закоммичено\n", encoding="utf-8")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.core, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "uncommitted branch work")

        self.local_bin = self.home / ".local" / "bin"
        self.local_bin.mkdir(parents=True)
        self.shim = self.local_bin / "seo-cycle"
        self.shim_target = self.tmp / "previous-shim-target"
        self.shim_target.write_text("previous version marker\n", encoding="utf-8")
        self.shim.symlink_to(self.shim_target)

        # Orphan the worktree: delete its main repo entirely. The linked
        # worktree's .git FILE (with the gitdir: pointer) is untouched, but
        # any git command run *inside* the worktree now fails because the
        # pointer's target is gone — exactly the shape that broke the old
        # O3 detector's `rev-parse --is-inside-work-tree` check.
        shutil.rmtree(self.seed)

    def test_installer_refuses_instead_of_cloning_over_the_orphan(self) -> None:
        git_file_before = (self.core / ".git").read_text(encoding="utf-8")
        files_before = sorted(p.name for p in self.core.iterdir())
        shim_target_before = os.readlink(self.shim)

        env = {
            **os.environ, "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
        }
        _assert_sandboxed_home(env)
        proc = subprocess.run(
            ["bash", str(INSTALL)],
            env=env,
            capture_output=True, text=True,
        )

        self.assertNotEqual(
            proc.returncode, 0,
            f"установщик обязан отказать на осиротевшем worktree — {proc.stdout + proc.stderr!r}",
        )
        self.assertTrue(self.core.is_dir(), "каталог worktree должен остаться на месте")
        self.assertEqual(
            (self.core / ".git").read_text(encoding="utf-8"), git_file_before,
            "gitdir-указатель worktree не должен измениться",
        )
        self.assertEqual(
            sorted(p.name for p in self.core.iterdir()), files_before,
            "содержимое каталога worktree не должно измениться",
        )
        backups = list(self.shared.glob("seo-cycle.backup.*"))
        self.assertEqual(backups, [], f"резервная копия не должна создаваться — {backups}")
        self.assertEqual(
            os.readlink(self.shim), shim_target_before,
            "шим ~/.local/bin/seo-cycle не должен быть перевешен",
        )

    def test_reverting_the_gitdir_check_reintroduces_the_orphan_incident(self) -> None:
        """Genuine mutation: restore the old rev-parse-based detector (which
        requires the worktree's main repo to still exist) and re-run against
        the exact same orphaned worktree. The original incident (backup +
        fresh clone over it) must come back."""
        source = INSTALL.read_text(encoding="utf-8")
        old = '[ -f "$1/.git" ] && grep -q \'^gitdir:\' "$1/.git" 2>/dev/null'
        new = '[ -f "$1/.git" ] && git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1'
        assert old in source, "мутация не нашла T-064 gitdir-детектор в is_git_worktree_checkout()"
        mutated = source.replace(old, new, 1)
        mutated_path = self.tmp / "install.mutated.sh"
        mutated_path.write_text(mutated, encoding="utf-8")

        env = {
            **os.environ, "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
        }
        _assert_sandboxed_home(env)
        proc = subprocess.run(
            ["bash", str(mutated_path)],
            env=env,
            capture_output=True, text=True,
        )
        self.assertEqual(
            proc.returncode, 0,
            f"без фикса установщик снова 'успешно' клонирует поверх осиротевшего worktree — {proc.stdout + proc.stderr!r}",
        )
        self.assertIn(
            "клонирую", proc.stdout + proc.stderr,
            "без фикса должен воспроизвестись исходный инцидент — backup + git clone поверх",
        )


class UpdateStoreForceTagsTest(InstallerFixture):
    """T-068 / F-10: --update must FORCE-rewrite a tag that moved on origin
    (a plain `git fetch --tags` silently refuses to do that, exit code 0 —
    the exact mechanism that let the phantom v2.1.0 tag stand undetected,
    2026-09-03 audit) and PRUNE a tag deleted on origin, reporting both."""

    def test_moved_tag_is_force_updated_and_reported(self) -> None:
        old_commit = _git(self.core, "rev-parse", "refs/tags/v1.0.0").stdout.strip()

        # Move the tag on origin via a second clone (self.seed already
        # tracks the same origin) — a re-tagged release.
        (self.seed / "VERSION").write_text("1.0.1\n", encoding="utf-8")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "retag")
        _git(self.seed, "tag", "-f", "v1.0.0")
        _git(self.seed, "push", "-q", "-f", "origin", "main", "--tags")
        new_commit = _git(self.seed, "rev-parse", "refs/tags/v1.0.0").stdout.strip()
        self.assertNotEqual(old_commit, new_commit)

        # Sanity: a PLAIN `git fetch --tags` (this git's pre-fix behaviour,
        # verified empirically — some git versions do this silently with
        # exit 0, this one refuses loudly with a non-zero exit) really does
        # NOT rewrite the local tag either way — proves the scenario
        # actually exercises the class of bug this ticket fixes (a moved
        # tag left stale), not a no-op.
        plain = subprocess.run(
            ["git", "-C", str(self.core), "fetch", "--tags", "--quiet"],
            capture_output=True, text=True,
        )
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(self.core), "rev-parse", "--verify", "-q", "refs/tags/v1.0.0"],
                capture_output=True, text=True,
            ).stdout.strip(),
            old_commit,
            f"плоский fetch --tags не должен был переписать тег (rc={plain.returncode}) — "
            "иначе сценарий не воспроизводит F-10",
        )

        proc = self.run_install("--update")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn(old_commit[:8], combined, combined)
        self.assertIn(new_commit[:8], combined, combined)
        self.assertIn("переехал", combined, combined)

        self.assertEqual(
            _git(self.core, "rev-parse", "refs/tags/v1.0.0").stdout.strip(),
            new_commit,
            "локальный тег обязан указывать на новый коммит после --update",
        )

    def test_deleted_tag_is_pruned_locally(self) -> None:
        self.assertTrue((self.core / ".git").exists())
        _git(self.core, "rev-parse", "refs/tags/v1.0.0")  # exists before

        _git(self.seed, "push", "-q", "origin", "--delete", "v1.0.0")

        proc = self.run_install("--update")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("отсутствует на origin", proc.stdout + proc.stderr)

        removed = subprocess.run(
            ["git", "-C", str(self.core), "rev-parse", "refs/tags/v1.0.0"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(removed.returncode, 0, "тег, удалённый на origin, обязан исчезнуть локально")

    def test_unreachable_origin_fails_loudly_not_silently(self) -> None:
        """T-064 sibling scenario for --update specifically: origin dropping
        mid-run must produce a non-zero exit, not a quiet 'success'."""
        offline = self.origin.with_name(self.origin.name + ".OFFLINE")
        self.origin.rename(offline)
        try:
            proc = self.run_install("--update")
        finally:
            offline.rename(self.origin)

        self.assertNotEqual(
            proc.returncode, 0,
            f"--update с недоступным origin обязан отказать, а не рапортовать успех — {proc.stdout + proc.stderr!r}",
        )
        self.assertIn("не удался", proc.stdout + proc.stderr)

    def test_reverting_the_force_flags_reintroduces_the_silent_stale_tag(self) -> None:
        """Genuine mutation: strip --force --prune --prune-tags back to a
        plain `fetch --tags` and re-run the exact moved-tag scenario. The
        original F-10 incident — the local tag left stale and unreported —
        must come back, whatever exit code this git version's plain fetch
        happens to return (review found: some versions exit 0 silently,
        this one exits 1 loudly; either way the tag itself stays stale
        without these flags, which is the actual incident) — proving these
        flags, not something else, are what fix it."""
        old_commit = _git(self.core, "rev-parse", "refs/tags/v1.0.0").stdout.strip()
        (self.seed / "VERSION").write_text("1.0.1\n", encoding="utf-8")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "retag")
        _git(self.seed, "tag", "-f", "v1.0.0")
        _git(self.seed, "push", "-q", "-f", "origin", "main", "--tags")

        proc = self.run_install_without(
            "--force --prune --prune-tags ", "--update",
        )
        # Whichever way this git's plain `fetch --tags` fails on a moved tag
        # (some versions: silent exit 0; this one: loud exit 1), the tag
        # itself must stay stale without --force — that stale, unnoticed
        # local tag is the actual F-10 incident.
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(self.core), "rev-parse", "--verify", "-q", "refs/tags/v1.0.0"],
                capture_output=True, text=True,
            ).stdout.strip(),
            old_commit,
            f"без --force тег обязан остаться устаревшим (rc={proc.returncode}) — "
            f"воспроизводит исходный инцидент F-10: {proc.stdout + proc.stderr!r}",
        )

    def test_prune_reports_a_tag_outside_the_release_mask_too(self) -> None:
        """Review finding: the before-snapshot used to be masked to `v*`
        (release tags), so a local-only marker tag OUTSIDE that mask (e.g.
        a scratch tag someone made by hand) got silently pruned by
        --prune-tags with zero report. The snapshot must now cover every
        local tag, not just release-shaped ones."""
        _git(self.core, "tag", "local-marker")  # never pushed, not v*-shaped
        proc = self.run_install("--update")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(
            "local-marker", proc.stdout + proc.stderr,
            "тег вне маски v*, убранный --prune-tags, обязан быть в отчёте",
        )
        removed = subprocess.run(
            ["git", "-C", str(self.core), "rev-parse", "--verify", "-q", "refs/tags/local-marker"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(removed.returncode, 0)

    def test_local_only_tag_is_not_falsely_reported_as_removed_from_origin(self) -> None:
        """Review finding: a tag that never existed on origin (local-only)
        getting pruned must not claim a removal EVENT happened on origin —
        this run only ever observes origin's current state (absent), never
        its history, so the wording states the present-tense fact instead
        of an unprovable past event."""
        _git(self.core, "tag", "v9.9.9-local-only")  # never pushed
        proc = self.run_install("--update")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("v9.9.9-local-only", combined)
        self.assertNotIn(
            "удалён на origin", combined,
            f"это утверждение о событии на origin, которого установщик не наблюдал — {combined!r}",
        )
        self.assertIn("отсутствует на origin", combined)

    def test_deleted_tag_then_sync_does_not_destroy_the_live_snapshot(self) -> None:
        """Review finding (the actual 🟡): before this fix, `rev-parse`
        without --verify on an unresolvable ref echoed the literal ref
        string back on stdout instead of failing empty. That made
        ensure_worktree()'s `[ -z "$tag_commit" ]` guard blind: a tag
        --update just pruned (routine after this ticket) looked "found"
        with garbage as its commit, and the reconciliation path deleted the
        project's live read-only snapshot trying to rebuild it — then
        failed to recreate it, leaving dangling symlinks in the project.
        This test pins a project to v1.0.0, prunes the tag via --update
        after it's deleted on origin, then re-syncs and asserts the live
        snapshot survives untouched."""
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        snapshot = self.shared / "versions" / "seo-cycle" / "v1.0.0"
        self.assertTrue((snapshot / "VERSION").exists())

        _git(self.seed, "push", "-q", "origin", "--delete", "v1.0.0")
        proc2 = self.run_install("--update")
        self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
        self.assertFalse(
            subprocess.run(
                ["git", "-C", str(self.core), "rev-parse", "--verify", "-q", "refs/tags/v1.0.0"],
                capture_output=True, text=True,
            ).returncode == 0,
        )

        proc3 = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--sync", "--no-migrate-old-global",
        )
        combined3 = proc3.stdout + proc3.stderr
        self.assertTrue(
            (snapshot / "VERSION").exists(),
            f"живой снапшот версии не должен исчезать из-за мусорного tag_commit — {combined3!r}",
        )
        self.assertIn("не найден", combined3, combined3)

    def test_reverting_the_verify_guard_alone_no_longer_reintroduces_the_snapshot_destruction(self) -> None:
        """T-091 update: this used to prove the `--verify -q` fix alone was
        the only thing standing between a locally-pruned tag and a
        destroyed live snapshot under --sync. It no longer is: T-091's
        origin-tags manifest (F-14) independently rejects an explicit --pin
        whose commit doesn't match what the last confirmed fetch/clone saw
        — the deleted tag's garbled `tag_commit` (this mutation's whole
        point) simply fails that comparison instead of reaching the
        destructive worktree-rebuild path at all. This IS the "failed
        bypass attempt" the ticket asks for. See the sibling test below for
        the mutation that strips BOTH guards and does reproduce the
        original incident."""
        old_commit = _git(self.core, "rev-parse", "refs/tags/v1.0.0").stdout.strip()
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        snapshot = self.shared / "versions" / "seo-cycle" / "v1.0.0"
        self.assertTrue((snapshot / "VERSION").exists())

        _git(self.seed, "push", "-q", "origin", "--delete", "v1.0.0")
        _git(self.core, "fetch", "origin", "--tags", "--force", "--prune", "--prune-tags", "--quiet")
        self.assertNotEqual(
            subprocess.run(
                ["git", "-C", str(self.core), "rev-parse", "--verify", "-q", "refs/tags/v1.0.0"],
                capture_output=True, text=True,
            ).returncode,
            0,
        )

        proc3 = self.run_install_without(
            'rev-parse --verify -q "refs/tags/$tag^{commit}"',
            "--project", str(self.project), "--pin", "v1.0.0",
            "--sync", "--no-migrate-old-global",
        )
        self.assertTrue(
            (snapshot / "VERSION").exists(),
            f"обход одного лишь --verify -q не должен доходить до разрушения снапшота "
            f"(T-091 закрывает класс раньше, через манифест F-14) — "
            f"{proc3.stdout + proc3.stderr!r}, старый коммит был {old_commit[:8]}",
        )

    def test_reverting_both_the_manifest_check_and_the_verify_guard_reintroduces_the_snapshot_destruction(self) -> None:
        """The genuine two-layer mutation: strip `--verify -q` back out of
        ensure_worktree() AND neuter T-091's manifest check
        (verify_tag_against_manifest call site) — i.e. simulate the world
        before EITHER fix existed. THAT reproduces the original incident
        (live snapshot destroyed by a bogus tag_commit under --sync),
        proving both mutations together, not just one, are what this
        scenario now needs to defeat."""
        old_commit = _git(self.core, "rev-parse", "refs/tags/v1.0.0").stdout.strip()
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        snapshot = self.shared / "versions" / "seo-cycle" / "v1.0.0"
        self.assertTrue((snapshot / "VERSION").exists())

        _git(self.seed, "push", "-q", "origin", "--delete", "v1.0.0")
        _git(self.core, "fetch", "origin", "--tags", "--force", "--prune", "--prune-tags", "--quiet")
        self.assertNotEqual(
            subprocess.run(
                ["git", "-C", str(self.core), "rev-parse", "--verify", "-q", "refs/tags/v1.0.0"],
                capture_output=True, text=True,
            ).returncode,
            0,
        )

        source = INSTALL.read_text(encoding="utf-8")
        verify_needle = 'rev-parse --verify -q "refs/tags/$tag^{commit}"'
        manifest_needle = 'verify_tag_against_manifest "$repo_dir" "$tag" "$tag_commit" || return 1'
        assert verify_needle in source, "мутация не нашла --verify -q"
        assert manifest_needle in source, "мутация не нашла вызов verify_tag_against_manifest"
        mutated = source.replace(verify_needle, "", 1).replace(
            manifest_needle, 'verify_tag_against_manifest "$repo_dir" "$tag" "$tag_commit" || true', 1,
        )
        mutated_path = self.tmp / "install.mutated4.sh"
        mutated_path.write_text(mutated, encoding="utf-8")
        full_env = {
            **os.environ, "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
        }
        _assert_sandboxed_home(full_env)
        proc3 = subprocess.run(
            ["bash", str(mutated_path), "--project", str(self.project), "--pin", "v1.0.0",
             "--sync", "--no-migrate-old-global"],
            env=full_env, capture_output=True, text=True,
        )
        self.assertFalse(
            (snapshot / "VERSION").exists(),
            f"с обоими guard'ами снятыми снапшот должен быть разрушен (воспроизводит инцидент) — "
            f"{proc3.stdout + proc3.stderr!r}, старый коммит был {old_commit[:8]}",
        )


class PlainAttachForceFetchTest(InstallerFixture):
    """T-091 (F-12/F-13): update_store_only() was fixed by T-068, but
    install_or_update_repo() — the function EVERY plain `install.sh` /
    `--project` attach runs through ensure_store(), the most common
    invocation and the one T-055 uses on four live sites — kept the exact
    pre-T-068 construction (`fetch --tags`, no --force/--prune-tags, `||
    warn "...(offline?)"` swallowing the real cause). These tests exercise
    THAT path directly, not update_store_only()."""

    def test_plain_attach_force_updates_a_moved_tag(self) -> None:
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # Move the tag on origin WITHOUT running install.sh at all — the
        # local store's v1.0.0 stays exactly where it was.
        (self.seed / "VERSION").write_text("1.0.1\n", encoding="utf-8")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "retag")
        _git(self.seed, "tag", "-f", "v1.0.0")
        _git(self.seed, "push", "-q", "-f", "origin", "main", "--tags")
        stale_local = _git(self.core, "rev-parse", "v1.0.0").stdout.strip()
        origin_now = _git(self.seed, "rev-parse", "v1.0.0").stdout.strip()
        self.assertNotEqual(stale_local, origin_now)

        # A PLAIN attach to a DIFFERENT project — no --update anywhere in
        # this test. If install_or_update_repo() still used a bare
        # `fetch --tags`, this would silently keep the stale tag (F-12).
        project2 = self.tmp / "project2"
        project2.mkdir()
        proc2 = self.run_install(
            "--project", str(project2), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
        combined = proc2.stdout + proc2.stderr
        self.assertIn("переехал", combined, combined)
        self.assertIn(stale_local[:8], combined, combined)
        self.assertIn(origin_now[:8], combined, combined)
        new_local = _git(self.core, "rev-parse", "v1.0.0").stdout.strip()
        self.assertEqual(new_local, origin_now, "тег в хранилище обязан обновиться на плейн-запуске, без --update")

    def test_plain_attach_reports_the_real_cause_not_a_guessed_offline(self) -> None:
        """F-12's second half: the old code's `|| warn "...(offline?)"`
        printed a GUESSED cause regardless of what actually failed. Force a
        REAL non-offline fetch rejection (a tag that would be clobbered)
        and confirm the message doesn't lie about the network being the
        problem when it demonstrably isn't (this whole repro never leaves
        localhost)."""
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        offline = self.origin.with_name(self.origin.name + ".OFFLINE")
        self.origin.rename(offline)
        try:
            proc2 = self.run_install(
                "--project", str(self.tmp / "project3"), "--pin", "v1.0.0",
                "--skip-init", "--no-migrate-old-global",
            )
        finally:
            offline.rename(self.origin)
        # This IS the genuinely offline case — rc must be non-zero and the
        # store must not silently claim to be updated.
        self.assertNotEqual(proc2.returncode, 0, proc2.stdout + proc2.stderr)
        combined = proc2.stdout + proc2.stderr
        self.assertIn("не удался", combined, combined)

    def test_reverting_the_force_fetch_in_plain_attach_reintroduces_the_stale_tag(self) -> None:
        """Genuine mutation: revert fetch_tags_or_report()'s fetch to the
        pre-T-091 plain `--tags` and re-run the moved-tag scenario above
        through a PLAIN attach (no --update). The stale tag must come back
        — proving the shared choke point, not something else, is what
        fixed install_or_update_repo() specifically."""
        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        (self.seed / "VERSION").write_text("1.0.1\n", encoding="utf-8")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A")
        _git(self.seed, "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-q", "-m", "retag")
        _git(self.seed, "tag", "-f", "v1.0.0")
        _git(self.seed, "push", "-q", "-f", "origin", "main", "--tags")
        stale_local = _git(self.core, "rev-parse", "v1.0.0").stdout.strip()

        project2 = self.tmp / "project2-mutated"
        project2.mkdir()
        mutated_proc = self.run_install_without(
            "--force --prune --prune-tags",
            "--project", str(project2), "--pin", "v1.0.0",
            "--skip-init", "--no-migrate-old-global",
        )
        # Without --force, a plain `fetch --tags` refuses to overwrite —
        # the local tag stays stale, exactly the F-12 incident.
        new_local = _git(self.core, "rev-parse", "v1.0.0").stdout.strip()
        self.assertEqual(
            new_local, stale_local,
            f"без --force тег обязан был остаться протухшим — {mutated_proc.stdout + mutated_proc.stderr!r}",
        )


class SyncManifestRejectsUnfetchedTagTest(InstallerFixture):
    """T-091 (F-14): `--pin <tag> --sync` used to accept a tag that was
    NEVER on origin at all — NETWORK_ALLOWED=0 (a real --sync) skipped
    ensure_worktree()'s ls-remote check entirely, and a purely local `git
    tag -f` is indistinguishable from a fetched one by `rev-parse` alone.
    The fix is the origin-tags manifest: an explicit --pin under --sync is
    now checked against what the most recent fetch/clone actually
    confirmed, instead of being trusted from local git state alone."""

    def test_pin_sync_rejects_a_tag_that_was_never_on_origin(self) -> None:
        # Confirm v1.0.0 into the manifest first (a real --update), THEN
        # create the never-pushed tag — this is the exact F-14 repro shape:
        # a manifest exists, it just never saw THIS tag.
        proc0 = self.run_install("--update")
        self.assertEqual(proc0.returncode, 0, proc0.stdout + proc0.stderr)
        _git(self.core, "tag", "-f", "v9.9.9", "HEAD")  # never pushed, ever

        proc = self.run_install(
            "--project", str(self.project), "--pin", "v9.9.9", "--sync",
            "--no-migrate-old-global",
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("F-14", combined, combined)
        self.assertFalse(self.lock_path().exists(), "лок не должен создаваться при отказе")

    def test_pin_sync_rejects_a_tag_with_no_manifest_at_all(self) -> None:
        """The other half of the same defect: a store that has NEVER run a
        fetch/clone through install.sh's own choke point (no manifest file
        exists yet) must also refuse an explicit --pin under --sync, not
        treat "no data" as "trusted"."""
        _git(self.core, "tag", "-f", "v9.9.9", "HEAD")

        proc = self.run_install(
            "--project", str(self.project), "--pin", "v9.9.9", "--sync",
            "--no-migrate-old-global",
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(self.lock_path().exists(), "лок не должен создаваться при отказе")

    def test_pin_sync_accepts_a_tag_confirmed_by_a_prior_update(self) -> None:
        """The safe, documented two-step sequence (INSTALL.md) must keep
        working: `--update` (network) confirms the tag into the manifest,
        then `--pin ... --sync` (no network) trusts it."""
        proc0 = self.run_install("--update")
        self.assertEqual(proc0.returncode, 0, proc0.stdout + proc0.stderr)

        proc = self.run_install(
            "--project", str(self.project), "--pin", "v1.0.0", "--sync",
            "--no-migrate-old-global",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_reverting_the_manifest_check_reintroduces_the_unverified_pin(self) -> None:
        """Genuine mutation: neuter verify_tag_against_manifest()'s call
        site and re-run the local-only-tag scenario above. The unverified
        tag must sail through again (exit 0, lock written) — proving this
        check, not something else, is what stops it."""
        proc0 = self.run_install("--update")
        self.assertEqual(proc0.returncode, 0, proc0.stdout + proc0.stderr)
        _git(self.core, "tag", "-f", "v9.9.9", "HEAD")

        source = INSTALL.read_text(encoding="utf-8")
        needle = 'verify_tag_against_manifest "$repo_dir" "$tag" "$tag_commit" || return 1'
        neutered = 'verify_tag_against_manifest "$repo_dir" "$tag" "$tag_commit" || true'
        assert needle in source, "мутация не нашла вызов verify_tag_against_manifest"
        mutated_path = self.tmp / "install.mutated5.sh"
        mutated_path.write_text(source.replace(needle, neutered, 1), encoding="utf-8")
        full_env = {
            **os.environ, "HOME": str(self.home),
            "SEO_CYCLE_SHARED_DIR": str(self.shared),
            "SEO_CYCLE_CORE": str(self.core),
            "SEO_CYCLE_REPO": str(self.origin),
            "SEO_CYCLE_SKIP_PYTHON_DEPS": "1",
        }
        _assert_sandboxed_home(full_env)
        mutated_proc = subprocess.run(
            ["bash", str(mutated_path), "--project", str(self.project), "--pin", "v9.9.9",
             "--sync", "--no-migrate-old-global"],
            env=full_env, capture_output=True, text=True,
        )
        self.assertEqual(
            mutated_proc.returncode, 0,
            f"без manifest-проверки тег должен был снова пройти — {mutated_proc.stdout + mutated_proc.stderr!r}",
        )
        self.assertTrue(self.lock_path().exists())


if __name__ == "__main__":
    unittest.main()
