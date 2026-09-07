#!/usr/bin/env python3
"""T-094 (F-3): `client-report.py` used to exit 0 and write four files to a
client-facing report with the CWD's directory name substituted for the
project name when `project.name: null` (the `project` section itself is a
non-empty mapping, so `require_section()` did not catch it — only the
`name` field inside it was missing). This is a document meant to leave the
codebase and reach a human; a silently-guessed identity in it must be a
refusal, not a report.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "client-report.py"


class ClientReportNullNameTest(unittest.TestCase):
    def test_null_project_name_refuses_and_writes_nothing(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            work = pathlib.Path(td)
            (work / "c.yaml").write_text("project:\n  name: null\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "c.yaml", "--write"],
                cwd=work, capture_output=True, text=True,
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            written = list((work / "seo").rglob("*")) if (work / "seo").exists() else []
            self.assertEqual(written, [], f"expected zero files written, got: {written}")

    def test_real_project_name_still_writes_the_report(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            work = pathlib.Path(td)
            (work / "c.yaml").write_text("project:\n  name: Acme\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "c.yaml", "--write"],
                cwd=work, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((work / "seo" / "reports" / "latest-client-report.md").exists())


if __name__ == "__main__":
    unittest.main()
