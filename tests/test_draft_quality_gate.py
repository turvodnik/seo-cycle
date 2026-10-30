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

    def test_loop_does_not_trust_stale_report_when_gate_returns_2(self) -> None:
        # Outline exists but is broken, and an old passing report is on disk:
        # the gate's rc 2 must win over the stale report.
        self.outline.write_text("{bad", encoding="utf-8")
        stale = self.draft.with_suffix(".draft-quality-gate.json")
        stale.write_text(json.dumps({"status": "pass", "summary": {"errors": 0, "warnings": 0}, "findings": []}),
                         encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "loop-runner.py"), "draft", str(self.draft),
             "--outline", str(self.outline), "--reset"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("passed", proc.stdout.lower())
        self.assertIn("outline не разобран", proc.stderr)

    def test_loop_precheck_rejects_missing_outline(self) -> None:
        # Covers loop-runner's own pre-check (outline missing), not the gate.
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "loop-runner.py"), "draft", str(self.draft),
             "--outline", str(self.tmp / "nope.json")],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


    # -- QA 3.0.1 Y3: outline of the wrong shape / undecodable outline ----------

    def test_outline_of_wrong_shape_is_a_call_error(self) -> None:
        shapes = ["[]", '"x"', "null", "42", '{"sections": [1, null, "a"]}', '{"sections": "x"}',
                  '{"internal_links": 5}', '{"faq": {"q": 1}}', '{"sections": [{"h3_subsections": 3}]}']
        for text in shapes:
            with self.subTest(outline=text):
                self.outline.write_text(text, encoding="utf-8")
                self.assert_clean_exit2(self.run_gate(self.draft, self.outline), "outline")

    def test_undecodable_outline_names_the_outline(self) -> None:
        self.outline.write_bytes(b"\xff\xfe\x00bad")
        proc = self.run_gate(self.draft, self.outline)
        self.assert_clean_exit2(proc, str(self.outline))
        self.assertNotIn(str(self.draft), proc.stderr)

    def test_unwritable_report_is_a_call_error(self) -> None:
        for suffix in (".draft-quality-gate.json", ".draft-quality-gate.md"):
            path = self.draft.with_suffix(suffix)
            path.write_text("{}", encoding="utf-8")
            path.chmod(0o444)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.draft), "--outline", str(self.outline), "--write"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assert_clean_exit2(proc, "отчёт не записан")

    def test_lone_surrogate_in_outline_is_a_call_error_and_leaves_no_report(self) -> None:
        """QA3 3.0.1 #1 / Д6: JSON lets `"\\ud800"` through; the gate used to
        crash with UnicodeEncodeError while writing and leave a 0-byte report
        that the journey counted as a passed gate."""
        self.outline.write_text('{"sections":[{"title":"Раздел \\ud800","level":2}]}', encoding="utf-8")
        for extra in ([], ["--write"]):
            with self.subTest(args=extra):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT), str(self.draft), "--outline", str(self.outline), *extra],
                    cwd=self.tmp, text=True, capture_output=True, check=False,
                )
                self.assert_clean_exit2(proc, str(self.outline))
                for suffix in (".draft-quality-gate.json", ".draft-quality-gate.md"):
                    self.assertFalse(self.draft.with_suffix(suffix).exists(), suffix)


class LoopRunnerFreshReportTest(unittest.TestCase):
    """QA 3.0.1 R2: a check that crashes (rc 1, no JSON on stdout) must never be
    read as the stale report left on disk by an earlier run."""

    def setUp(self) -> None:
        import importlib.util

        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="loop-fresh-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(lambda: sys.path.remove(str(SCRIPTS)))
        spec = importlib.util.spec_from_file_location("loop_runner_under_test", SCRIPTS / "loop-runner.py")
        assert spec and spec.loader
        self.lr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.lr)
        self.fake_dir = self.tmp / "fake-scripts"
        self.fake_dir.mkdir()
        self.lr.scripts_dir = lambda: self.fake_dir
        self.draft = self.tmp / "draft.md"
        self.draft.write_text("# Unrelated\n", encoding="utf-8")
        self.outline = self.tmp / "outline.json"
        self.outline.write_text("{}", encoding="utf-8")
        self.passed = {"status": "pass", "summary": {"errors": 0, "warnings": 0}, "findings": []}
        stale = self.draft.with_suffix(".draft-quality-gate.json")
        stale.write_text(json.dumps(self.passed), encoding="utf-8")
        old = 1_000_000_000
        import os

        os.utime(stale, (old, old))

    def fake_check(self, body: str) -> None:
        (self.fake_dir / "draft-quality-gate.py").write_text(body, encoding="utf-8")

    def test_crash_with_rc1_does_not_read_stale_report(self) -> None:
        self.fake_check("import sys\nraise AttributeError('boom')\n")
        with self.assertRaises(RuntimeError):
            self.lr.run_check("draft", self.draft, self.outline, self.tmp)

    def test_unexpected_rc_is_an_error(self) -> None:
        self.fake_check("import json, sys\nprint(json.dumps({'status': 'pass', 'findings': []}))\nsys.exit(5)\n")
        with self.assertRaises(RuntimeError):
            self.lr.run_check("draft", self.draft, self.outline, self.tmp)

    def test_fresh_stdout_report_wins_over_stale_disk(self) -> None:
        fail = {"status": "fail", "summary": {"errors": 1}, "findings": [{"id": "x", "severity": "error"}]}
        self.fake_check(f"import json, sys\nprint(json.dumps({fail!r}))\nsys.exit(1)\n")
        report = self.lr.run_check("draft", self.draft, self.outline, self.tmp)
        self.assertEqual(report["status"], "fail")

    def test_report_rewritten_during_the_run_is_accepted(self) -> None:
        # No JSON on stdout, but the check rewrote the report: the fresh file counts.
        self.fake_check(
            "import json, pathlib, sys\n"
            f"pathlib.Path({str(self.draft.with_suffix('.draft-quality-gate.json'))!r}).write_text("
            "json.dumps({'status': 'fail', 'findings': []}))\nsys.exit(1)\n"
        )
        report = self.lr.run_check("draft", self.draft, self.outline, self.tmp)
        self.assertEqual(report["status"], "fail")

    def _future_stale(self, report_path: pathlib.Path) -> None:
        import os
        import time

        report_path.write_text(json.dumps(self.passed), encoding="utf-8")
        future = time.time() + 10 * 365 * 86400  # a clock running ahead / a synced file
        os.utime(report_path, (future, future))

    def test_stale_report_with_future_mtime_is_not_a_verdict(self) -> None:
        """QA2 3.0.1 #2: an old report whose mtime is after the run start (clock
        skew, sync) is still not this run's report — for every target."""
        self._future_stale(self.draft.with_suffix(".draft-quality-gate.json"))
        self.fake_check("import sys\nraise AttributeError('boom')\n")
        with self.assertRaises(RuntimeError):
            self.lr.run_check("draft", self.draft, self.outline, self.tmp)

        pkg = self.tmp / "pkg"
        pkg.mkdir()
        self._future_stale(pkg / "research-package-quality.json")
        (self.fake_dir / "research-package-quality.py").write_text(
            "import sys\nraise AttributeError('boom')\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.lr.run_check("research-package", pkg, None, self.tmp)

    def test_future_mtime_report_rewritten_during_the_run_is_accepted(self) -> None:
        report_path = self.draft.with_suffix(".draft-quality-gate.json")
        self._future_stale(report_path)
        self.fake_check(
            "import json, pathlib, sys\n"
            f"pathlib.Path({str(report_path)!r}).write_text("
            "json.dumps({'status': 'fail', 'findings': []}))\nsys.exit(1)\n"
        )
        report = self.lr.run_check("draft", self.draft, self.outline, self.tmp)
        self.assertEqual(report["status"], "fail")

    # QA3 3.0.1 #3: the pre-run identity read the old report whole and followed
    # symlinks (`-> /dev/zero` ate memory without bound). A report output that
    # is not a regular file, or is over the size cap, is refused before the
    # check runs — so the check never writes through a planted link either.

    def _marker_check(self) -> pathlib.Path:
        marker = self.tmp / "check-ran"
        self.fake_check(
            "import json, pathlib, sys\n"
            f"pathlib.Path({str(marker)!r}).write_text('ran')\n"
            "print(json.dumps({'status': 'pass', 'findings': []}))\n"
        )
        return marker

    def test_symlinked_report_is_refused_before_the_check(self) -> None:
        report_path = self.draft.with_suffix(".draft-quality-gate.json")
        target = self.tmp / "elsewhere.json"
        target.write_text(json.dumps(self.passed), encoding="utf-8")
        report_path.unlink()
        report_path.symlink_to(target)
        marker = self._marker_check()
        with self.assertRaises(RuntimeError) as ctx:
            self.lr.run_check("draft", self.draft, self.outline, self.tmp)
        self.assertIn(str(report_path), str(ctx.exception))
        self.assertFalse(marker.exists(), "the check must not run over a symlinked report")
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.passed)

    def test_symlinked_markdown_output_is_refused_before_the_check(self) -> None:
        # The check also writes `<report>.md`; a link there would let it
        # overwrite any file the user can write (e.g. the project's AGENTS.md).
        pkg = self.tmp / "pkg"
        pkg.mkdir()
        victim = self.tmp / "AGENTS.md"
        victim.write_text("# rules\n", encoding="utf-8")
        (pkg / "research-package-quality.md").symlink_to(victim)
        marker = self.tmp / "check-ran"
        (self.fake_dir / "research-package-quality.py").write_text(
            "import json, pathlib\n"
            f"pathlib.Path({str(marker)!r}).write_text('ran')\n"
            f"pathlib.Path({str(pkg / 'research-package-quality.md')!r}).write_text('# overwritten')\n"
            "print(json.dumps({'status': 'pass', 'findings': []}))\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.lr.run_check("research-package", pkg, None, self.tmp)
        self.assertFalse(marker.exists())
        self.assertEqual(victim.read_text(encoding="utf-8"), "# rules\n")

    def test_oversized_report_is_refused_without_reading_it(self) -> None:
        self.lr.MAX_REPORT_BYTES = 8
        marker = self._marker_check()
        with self.assertRaises(RuntimeError) as ctx:
            self.lr.run_check("draft", self.draft, self.outline, self.tmp)
        self.assertIn("8", str(ctx.exception))
        self.assertFalse(marker.exists())

    def test_regular_report_still_works_after_the_guard(self) -> None:
        # The guard must not turn the normal path into a refusal.
        marker = self._marker_check()
        report = self.lr.run_check("draft", self.draft, self.outline, self.tmp)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(marker.exists())


class LoopRefusesPlantedLinkCliTest(unittest.TestCase):
    """QA3 3.0.1 (out of diff): a symlink planted in a research package made
    `seo-cycle loop research-package` overwrite the link target with the
    quality report. The real CLI now stops with rc 2 and one line."""

    def test_loop_does_not_write_through_a_planted_link(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="loop-link-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text(
            (ROOT / "config" / "project.template.yaml").read_text(encoding="utf-8"), encoding="utf-8")
        pkg = tmp / "seo" / "research-package"
        pkg.mkdir(parents=True)
        for name in ("semantic-core.csv", "content-plan.csv", "final-clusters.md", "entity-map.md", "entity-map.yaml"):
            (pkg / name).write_text("x\n", encoding="utf-8")
        (pkg / "semantic-architecture-final.json").write_text('{"clusters":[]}', encoding="utf-8")
        agents = tmp / "AGENTS.md"
        agents.write_text("# AGENTS.md\nproject rules\n", encoding="utf-8")
        (pkg / "research-package-quality.md").symlink_to(pathlib.Path("../../AGENTS.md"))
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "loop-runner.py"), "research-package", str(pkg)],
            cwd=tmp, text=True, capture_output=True, check=False, timeout=120,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(agents.read_text(encoding="utf-8"), "# AGENTS.md\nproject rules\n")
        self.assertTrue((pkg / "research-package-quality.md").is_symlink())
        self.assertEqual(len([ln for ln in proc.stderr.splitlines() if ln.startswith("ERROR")]), 1, proc.stderr)


if __name__ == "__main__":
    unittest.main()
