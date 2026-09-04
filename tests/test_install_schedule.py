#!/usr/bin/env python3
"""Contract tests for scripts/install-schedule.sh --scope/--dry-run (T-049, I-061).

macOS writes launchd plists; Linux (CI) prints a crontab block instead — both
must honor --scope (ai-secret wrapper) and --dry-run (no side effects).
"""

from __future__ import annotations

import pathlib
import platform
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install-schedule.sh"
IS_DARWIN = platform.system() == "Darwin"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True,
    )


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


if __name__ == "__main__":
    unittest.main()
