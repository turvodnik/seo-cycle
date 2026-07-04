#!/usr/bin/env python3
"""Tests for install-desktop-app.sh and the interactive menu guard."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DesktopLauncherTest(unittest.TestCase):
    def test_installer_creates_command_file(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-desktop-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        proc = subprocess.run(
            ["bash", str(ROOT / "scripts" / "install-desktop-app.sh"), "--desktop-dir", str(tmp)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        command = tmp / "SEO Cycle.command"
        self.assertTrue(command.exists())
        self.assertTrue(os.access(command, os.X_OK))
        body = command.read_text(encoding="utf-8")
        self.assertIn("seo-cycle", body)
        self.assertIn("web --open", body)  # двойной клик открывает веб-дашборд
        if sys.platform == "darwin" and shutil.which("osacompile"):
            self.assertTrue((tmp / "SEO Cycle.app").exists())

    def test_menu_refuses_non_tty(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "seo_cycle_cli.py"), "menu"],
            stdin=subprocess.DEVNULL, text=True, capture_output=True, check=False,
            cwd=ROOT,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("интерактивный терминал", proc.stderr)


if __name__ == "__main__":
    unittest.main()
