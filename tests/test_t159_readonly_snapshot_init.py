#!/usr/bin/env python3
"""T-159 / QA v3.0.0 F1: a project initialised from a READ-ONLY version
snapshot must get owner-writable files.

install.sh ensure_worktree() runs `chmod -R a-w` on every version snapshot;
init-project.sh copied templates out of it with plain `cp`, which carries the
0444 mode, so `seo-cycle.yaml`, `.env.example` and the seo/* policies came out
read-only and the documented `--write`/`--apply` paths died with
PermissionError. The author's tests ran init from the writable dev clone and
never saw it — this test runs it from a read-only copy of the tool tree.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

FILES = ("seo-cycle.yaml", ".env.example", "seo/project-intake.yaml", "seo/tool-budget.yaml")


def make_writable(path: pathlib.Path) -> None:
    for dirpath, dirnames, filenames in os.walk(path):
        for name in [*dirnames, *filenames]:
            p = pathlib.Path(dirpath) / name
            if not p.is_symlink():
                p.chmod(p.stat().st_mode | stat.S_IWUSR)
    path.chmod(path.stat().st_mode | stat.S_IWUSR)


class ReadOnlySnapshotInitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="t159-f1-"))
        cls.snapshot = cls.tmp / "versions" / "seo-cycle" / "v0.0.0"
        shutil.copytree(ROOT, cls.snapshot, symlinks=True,
                        ignore=shutil.ignore_patterns(".git", ".claude", "tests", "__pycache__", "*.pyc"))
        # same as install.sh ensure_worktree(): the snapshot is read-only
        subprocess.run(["chmod", "-R", "a-w", str(cls.snapshot)], check=True)
        cls.project = cls.tmp / "proj"
        cls.project.mkdir()
        cls.env = {**os.environ, "SEO_CYCLE_SKIP_REGISTRY": "1", "HOME": str(cls.tmp / "home")}
        (cls.tmp / "home").mkdir()
        cls.init = subprocess.run(
            ["bash", str(cls.snapshot / "scripts" / "init-project.sh")],
            cwd=cls.project, input="", text=True, capture_output=True, env=cls.env, timeout=300,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        make_writable(cls.tmp)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_snapshot_really_is_read_only(self) -> None:
        mode = (self.snapshot / "config" / "project.template.yaml").stat().st_mode
        self.assertFalse(mode & stat.S_IWUSR, "fixture must reproduce the a-w snapshot")

    def test_generated_project_files_are_owner_writable(self) -> None:
        self.assertEqual(self.init.returncode, 0, self.init.stdout[-2000:] + self.init.stderr[-2000:])
        for rel in FILES:
            path = self.project / rel
            self.assertTrue(path.is_file(), f"{rel} not created")
            self.assertTrue(path.stat().st_mode & stat.S_IWUSR,
                            f"{rel} is read-only ({oct(path.stat().st_mode & 0o777)})")

    def test_documented_intake_write_succeeds(self) -> None:
        self.assertEqual(self.init.returncode, 0, self.init.stderr[-2000:])
        proc = subprocess.run(
            [sys.executable, str(self.snapshot / "scripts" / "project-intake-wizard.py"),
             "seo-cycle.yaml", "--defaults", "--write"],
            cwd=self.project, capture_output=True, text=True, env=self.env, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout[-1500:] + proc.stderr[-1500:])
        self.assertNotIn("PermissionError", proc.stderr)


if __name__ == "__main__":
    unittest.main()
