#!/usr/bin/env python3
"""Tests for the scorecard self-assessment layer."""

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
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.scorecard import (  # noqa: E402
    clamp_score,
    load_history,
    load_latest,
    render_scorecards_markdown,
    score_from_findings,
    write_scorecard,
)


class ScoreMathTest(unittest.TestCase):
    def test_clean_run_is_ten(self) -> None:
        self.assertEqual(score_from_findings([]), 10.0)

    def test_severity_weights(self) -> None:
        findings = [
            {"severity": "critical"},   # -3
            {"severity": "error"},      # -2
            {"severity": "warning"},    # -0.75
            {"severity": "info"},       # -0.2
        ]
        self.assertEqual(score_from_findings(findings), 4.0)  # 10 - 5.95 = 4.05 → float round → 4.0

    def test_score_never_negative_and_clamped(self) -> None:
        findings = [{"severity": "critical"}] * 10
        self.assertEqual(score_from_findings(findings), 0.0)
        self.assertEqual(clamp_score(42), 10.0)
        self.assertEqual(clamp_score("junk"), 0.0)


class ScorecardStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-scorecard-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: score\n", encoding="utf-8")

    def test_write_appends_history_and_updates_latest(self) -> None:
        write_scorecard(self.tmp, "draft-writing", 7.5, missing=["нет ссылок"])
        write_scorecard(self.tmp, "draft-writing", 9.0, done=["ссылки добавлены"])
        write_scorecard(self.tmp, "loop:draft", 10, status="done")

        history = load_history(self.tmp, "draft-writing")
        self.assertEqual([entry["score"] for entry in history], [7.5, 9.0])
        latest = load_latest(self.tmp)
        self.assertEqual(latest["draft-writing"]["score"], 9.0)
        self.assertEqual(latest["loop:draft"]["score"], 10.0)
        markdown = render_scorecards_markdown(latest)
        self.assertIn("draft-writing", markdown)
        self.assertIn("🟢", markdown)

    def test_cli_record_and_show(self) -> None:
        record = subprocess.run(
            [sys.executable, str(SCRIPTS / "scorecard.py"), "record", "--tool", "audit",
             "--score", "6", "--missing", "hreflang", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(record.returncode, 0, record.stderr)
        entry = json.loads(record.stdout)
        self.assertEqual(entry["score"], 6.0)

        show = subprocess.run(
            [sys.executable, str(SCRIPTS / "scorecard.py"), "show", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(show.returncode, 0, show.stderr)
        self.assertIn("audit", json.loads(show.stdout))

    def test_cli_score_from_findings_json(self) -> None:
        report = self.tmp / "report.json"
        report.write_text(json.dumps({"findings": [{"severity": "error"}, {"severity": "error"}]}),
                          encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "scorecard.py"), "record", "--tool", "gate",
             "--findings-json", str(report), "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["score"], 6.0)


class LoopScorecardTest(unittest.TestCase):
    def test_loop_writes_scorecard_on_final_states(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-loop-score-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text("project:\n  name: loop\n", encoding="utf-8")
        import importlib.util

        spec = importlib.util.spec_from_file_location("loop_runner", SCRIPTS / "loop-runner.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        state = {
            "loop_id": "draft--x-abc123",
            "target": "draft",
            "status": "passed",
            "attempts": [{"n": 1, "check": {"findings": [{"severity": "warning", "id": "thin_section"}]}}],
        }
        module.write_loop_scorecard(state, tmp)
        latest = load_latest(tmp)
        self.assertIn("loop:draft", latest)
        self.assertEqual(latest["loop:draft"]["score"], 9.2)  # 10 - 0.75, rounded .1
        self.assertEqual(latest["loop:draft"]["status"], "done")


if __name__ == "__main__":
    unittest.main()
