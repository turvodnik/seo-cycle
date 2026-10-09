#!/usr/bin/env python3
"""Tests for scripts/draft-quality-gate.py exit code contract (T-102).

The gate must report pass/warn/fail the same way page-outline-quality.py and
research-package-quality.py do: exit 0 for pass/warn, exit 1 only when an
error-severity finding is present. Invoked as a subprocess (not imported) so
the test exercises the real CLI/exit-code path, same as loop-runner does.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "draft-quality-gate.py"


class DraftQualityGateExitCodeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="draft-quality-gate-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.outline = self.tmp / "outline.json"
        self.outline.write_text(
            json.dumps({"sections": [], "internal_links": [], "faq": []}),
            encoding="utf-8",
        )

    def run_gate(self, draft_text: str, *extra_args: str) -> subprocess.CompletedProcess:
        draft = self.tmp / "draft.md"
        draft.write_text(draft_text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(draft), "--outline", str(self.outline), "--format", "json", *extra_args],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_clean_draft_exits_zero(self) -> None:
        proc = self.run_gate("# Пост\n\nТекст. Source: https://example.com\n")
        report = json.loads(proc.stdout)
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["status"], "pass")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_draft_with_error_finding_exits_nonzero(self) -> None:
        # No source/proof marker AND unsafe first-person expertise claim -> at
        # least one error-severity finding (unsafe_first_person_expertise).
        proc = self.run_gate("# Пост\n\nIn my years working with clients I have seen a lot.\n")
        report = json.loads(proc.stdout)
        finding_ids = {f["id"] for f in report["findings"]}
        self.assertIn("unsafe_first_person_expertise", finding_ids)
        self.assertEqual(report["status"], "fail")
        self.assertNotEqual(proc.returncode, 0)

    def test_warning_only_findings_still_exit_zero(self) -> None:
        # Missing proof slot is a warning, not an error -> gate still passes.
        proc = self.run_gate("# Пост\n\nОбычный текст без ссылок и без правок.\n")
        report = json.loads(proc.stdout)
        finding_ids = {f["id"] for f in report["findings"]}
        self.assertIn("missing_proof_slot", finding_ids)
        self.assertTrue(all(f["severity"] != "error" for f in report["findings"]))
        self.assertEqual(report["status"], "warn")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_help_documents_exit_code_scale(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("error-severity finding", proc.stdout.lower())

    def test_negative_control_error_severity_threshold(self) -> None:
        """Sanity check that the test actually distinguishes error from warning.

        If the status/exit-code logic were inverted (warn=fail instead of
        error=fail) this test would fail — proving test_warning_only_findings
        and test_draft_with_error_finding are not accidentally both green.
        """
        warn_proc = self.run_gate("# Пост\n\nОбычный текст без ссылок и без правок.\n")
        error_proc = self.run_gate("# Пост\n\nIn my years working with clients I have seen a lot.\n")
        self.assertEqual(warn_proc.returncode, 0)
        self.assertEqual(error_proc.returncode, 1)
        self.assertNotEqual(warn_proc.returncode, error_proc.returncode)


class DraftQualityGateCallErrorTest(unittest.TestCase):
    """T-182 F12: bad call/config input is exit 2 + one line, never a traceback."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="draft-gate-err-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.draft = self.tmp / "draft.md"
        self.draft.write_text("# Пост\n", encoding="utf-8")
        self.outline = self.tmp / "outline.json"
        self.outline.write_text("{}", encoding="utf-8")

    def run_gate(self, draft: pathlib.Path, outline: pathlib.Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(draft), "--outline", str(outline)],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )

    def assert_clean_exit2(self, proc: subprocess.CompletedProcess, needle: str) -> None:
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stderr)
        self.assertEqual(len(proc.stderr.strip().splitlines()), 1, proc.stderr)

    def test_missing_draft(self) -> None:
        self.assert_clean_exit2(self.run_gate(self.tmp / "nope.md", self.outline), "файл не найден")

    def test_missing_outline(self) -> None:
        self.assert_clean_exit2(self.run_gate(self.draft, self.tmp / "nope.json"), "файл не найден")

    def test_broken_outline_json(self) -> None:
        self.outline.write_text("{bad", encoding="utf-8")
        self.assert_clean_exit2(self.run_gate(self.draft, self.outline), "outline не разобран")

    def test_loop_runner_treats_gate_call_error_as_config_error(self) -> None:
        # loop-runner exit 2 = "config error", not 1 = "escalated".
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "loop-runner.py"), "draft", str(self.draft),
             "--outline", str(self.tmp / "nope.json")],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
