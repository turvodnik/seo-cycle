#!/usr/bin/env python3
"""Contract tests for scripts/install-schedule.sh --scope/--dry-run (T-049, I-061)."""

from __future__ import annotations

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install-schedule.sh"


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

    def test_missing_scope_warns_but_still_generates_plist(self) -> None:
        proc = run("--dry-run")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("<plist", proc.stdout)
        self.assertIn("секреты не подмешаны", proc.stderr)
        self.assertNotIn("ai-secret run", proc.stdout)

    def test_dry_run_does_not_write_or_load_launchagent(self) -> None:
        target = pathlib.Path.home() / "Library" / "LaunchAgents" / "com.seo-cycle.daily-progress.plist"
        existed_before = target.exists()
        before = target.read_text(encoding="utf-8") if existed_before else None
        run("--scope", "emwoody", "--dry-run")
        if existed_before:
            self.assertEqual(target.read_text(encoding="utf-8"), before)
        else:
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
