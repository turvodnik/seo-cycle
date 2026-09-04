#!/usr/bin/env python3
"""Contract tests for scripts/install-schedule.sh --scope/--dry-run (T-049, I-061).

macOS writes launchd plists; Linux (CI) prints a crontab block instead — both
must honor --scope (ai-secret wrapper) and --dry-run (no side effects).

R1/R2 regression: --scope must wrap EVERY generated job, including the two
that start with `cd '<project>' && …` (daily-progress, monthly-runner) — an
earlier revision silently dropped the ai-secret/PATH wrapper for exactly
those two because /usr/bin/env cannot exec the shell builtin `cd`. A test
that only checks "ai-secret" appears SOMEWHERE in stdout stays green even
when two of three jobs are broken (weekly-portfolio has no `cd` and was
fine) — so this file extracts each job's command separately and actually
runs it through a fake ai-secret + fake seo-cycle launcher to prove the
secret wrapper, PATH and working directory all reach the real command.
"""

from __future__ import annotations

import pathlib
import platform
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install-schedule.sh"
REAL_LAUNCHER = str(ROOT / "bin" / "seo-cycle")
IS_DARWIN = platform.system() == "Darwin"


def run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    import os

    full_env = {**os.environ, **(env or {})}
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=full_env,
    )


def extract_plist_commands(stdout: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for block in re.findall(r"<plist.*?</plist>", stdout, re.S):
        label = re.search(r"<string>(com\.seo-cycle\.[^<]+)</string>", block).group(1)
        strs = re.findall(r"<string>(.*?)</string>", block, re.S)
        out[label] = strs[3].replace("&amp;", "&")
    return out


def extract_crontab_commands(stdout: str) -> dict[str, str]:
    out: dict[str, str] = {}
    lines = [line for line in stdout.splitlines() if line and line[0].isdigit()]
    schedules = ["daily-progress", "weekly-portfolio", "monthly-runner"]
    for name, line in zip(schedules, lines, strict=False):
        # "<5 cron fields>  <command>" — split off the first 5 whitespace fields.
        parts = line.split(None, 5)
        out[name] = parts[5]
    return out


@unittest.skipUnless(pathlib.Path("/bin/bash").exists(), "bash required")
class InstallScheduleTest(unittest.TestCase):
    def test_scope_dry_run_wraps_with_ai_secret(self) -> None:
        proc = run("--scope", "emwoody", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ai-secret", proc.stdout)
        self.assertIn("run emwoody", proc.stdout)
        self.assertNotIn("секреты не подмешаны", proc.stderr)

    def test_missing_scope_warns_but_still_generates_schedule(self) -> None:
        proc = run("--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        marker = "<plist" if IS_DARWIN else "crontab"
        self.assertIn(marker, proc.stdout)
        self.assertIn("секреты не подмешаны", proc.stderr)
        self.assertNotIn("ai-secret run", proc.stdout)

    @unittest.skipUnless(IS_DARWIN, "launchd only exists on macOS")
    def test_dry_run_does_not_write_or_load_launchagent(self) -> None:
        target = pathlib.Path.home() / "Library" / "LaunchAgents" / "com.seo-cycle.daily-progress.plist"
        existed_before = target.exists()
        before = target.read_text(encoding="utf-8") if existed_before else None
        run("--scope", "emwoody", "--dry-run")
        if existed_before:
            self.assertEqual(target.read_text(encoding="utf-8"), before)
        else:
            self.assertFalse(target.exists())

    @unittest.skipIf(IS_DARWIN, "Linux crontab path only")
    def test_linux_dry_run_prints_crontab_block(self) -> None:
        proc = run("--scope", "emwoody", "--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("crontab", proc.stdout)


@unittest.skipUnless(pathlib.Path("/bin/bash").exists(), "bash required")
class EveryJobIsWrappedTest(unittest.TestCase):
    """R1/R2: each of the three jobs, executed for real through a fake
    ai-secret, must actually receive the secret wrapper — not just contain
    the substring "ai-secret" somewhere in the whole dry-run output."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-schedule-контракт-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

        self.home = self.tmp / "home"
        (self.home / ".local" / "bin").mkdir(parents=True)
        ai_secret = self.home / ".local" / "bin" / "ai-secret"
        ai_secret.write_text(
            "#!/usr/bin/env bash\n"
            'echo "AI-SECRET:$1:$2" >&2\n'  # $1=run $2=<scope>
            "shift 3\n"  # drop run <scope> --
            'exec "$@"\n',
            encoding="utf-8",
        )
        ai_secret.chmod(0o755)

        # The launcher writes its cwd to a sentinel FILE rather than stdout —
        # comparing file content sidesteps any CI log-masking of paths and
        # keeps the assertion strictly about the value the process actually
        # saw, not about what a terminal chose to render.
        self.pwd_sentinel = self.tmp / "launcher-pwd.txt"
        self.fake_launcher = self.tmp / "fakebin" / "seo-cycle"
        self.fake_launcher.parent.mkdir(parents=True)
        self.fake_launcher.write_text(
            "#!/usr/bin/env bash\n"
            'echo "CALLED:$*"\n'
            f'pwd > "{self.pwd_sentinel}"\n',
            encoding="utf-8",
        )
        self.fake_launcher.chmod(0o755)

        self.project = self.tmp / "проект с пробелом"
        self.project.mkdir()

    def _run_job(self, cmd: str) -> subprocess.CompletedProcess:
        cmd = cmd.replace(REAL_LAUNCHER, str(self.fake_launcher))
        return subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)

    def test_all_three_jobs_reach_ai_secret_and_the_launcher(self) -> None:
        import os

        env = {**os.environ, "HOME": str(self.home)}
        proc = run(
            "--project", str(self.project), "--scope", "emwoody",
            "--with-monthly", "--dry-run", env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

        commands = (
            extract_plist_commands(proc.stdout) if IS_DARWIN
            else extract_crontab_commands(proc.stdout)
        )
        expect_keys = (
            {"com.seo-cycle.daily-progress", "com.seo-cycle.weekly-portfolio", "com.seo-cycle.monthly-runner"}
            if IS_DARWIN else
            {"daily-progress", "weekly-portfolio", "monthly-runner"}
        )
        self.assertEqual(set(commands), expect_keys)

        for name, cmd in commands.items():
            self.pwd_sentinel.unlink(missing_ok=True)
            result = self._run_job(cmd)
            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")
            self.assertIn(
                "AI-SECRET:run:emwoody", result.stderr,
                f"{name}: ai-secret wrapper never ran — {result.stderr!r}",
            )
            self.assertIn(
                "CALLED:", result.stdout,
                f"{name}: the real launcher never ran — {result.stdout!r}",
            )
            # monthly-runner always `cd`s into the project on both
            # platforms; daily-progress only does on macOS (the Linux
            # crontab form of that job has never `cd`'d — pulse --global
            # doesn't need project cwd there; pre-existing platform
            # asymmetry, out of scope here — this test only proves the
            # jobs that DO cd still land in the right directory).
            job_should_cd = "monthly-runner" in name or (IS_DARWIN and "daily-progress" in name)
            if job_should_cd:
                self.assertTrue(
                    self.pwd_sentinel.exists(),
                    f"{name}: the launcher never wrote its cwd sentinel",
                )
                seen_pwd = self.pwd_sentinel.read_text(encoding="utf-8").strip()
                self.assertEqual(
                    pathlib.Path(seen_pwd).resolve(), self.project.resolve(),
                    f"{name}: cd into the project did not survive the ai-secret/env wrapper",
                )


if __name__ == "__main__":
    unittest.main()
