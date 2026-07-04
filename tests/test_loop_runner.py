#!/usr/bin/env python3
"""Tests for the bounded quality loop (seo_cycle_core/loop.py + loop-runner.py)."""

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

from seo_cycle_core.loop import (  # noqa: E402
    classify_findings,
    decide_next,
    finding_delta,
    finding_fingerprint,
    is_passed,
    new_state,
    no_progress,
    record_attempt,
    target_config,
)

FINDINGS_A = [
    {"id": "dirty_semantic_core_queries", "severity": "high", "title": "dirty"},
    {"id": "eeat_evidence_missing", "severity": "medium", "title": "evidence"},
]
FINDINGS_B = [
    {"id": "eeat_evidence_missing", "severity": "medium", "title": "evidence"},
]


class LoopCoreTest(unittest.TestCase):
    def test_fingerprint_is_order_independent_and_stable(self) -> None:
        self.assertEqual(finding_fingerprint(FINDINGS_A), finding_fingerprint(list(reversed(FINDINGS_A))))
        self.assertNotEqual(finding_fingerprint(FINDINGS_A), finding_fingerprint(FINDINGS_B))

    def test_delta_resolved_new_unchanged(self) -> None:
        delta = finding_delta(FINDINGS_A, FINDINGS_B)
        self.assertEqual(delta["resolved"], ["high:dirty_semantic_core_queries"])
        self.assertEqual(delta["new"], [])
        self.assertEqual(delta["unchanged"], ["medium:eeat_evidence_missing"])

    def test_classify_splits_quality_and_evidence(self) -> None:
        classes = classify_findings(FINDINGS_A)
        self.assertEqual(classes, {"quality": 1, "evidence": 1})

    def test_is_passed_by_status_and_by_severity(self) -> None:
        self.assertTrue(is_passed("research-package", {"status": "warn", "findings": []}))
        self.assertFalse(is_passed("research-package", {"status": "fail", "findings": []}))
        # draft has no status: error findings block, warnings do not
        self.assertFalse(is_passed("draft", {"findings": [{"id": "x", "severity": "error"}]}))
        self.assertTrue(is_passed("draft", {"findings": [{"id": "x", "severity": "warning"}]}))

    def test_decide_next_flow(self) -> None:
        limits = {"max_attempts": 2, "no_progress_after": 2, "enabled": True, "escalate": True}
        state = new_state("research-package", pathlib.Path("/tmp/pkg"), limits)
        self.assertEqual(decide_next(state, "research-package"), "run_check")
        record_attempt(state, {"status": "fail", "findings": FINDINGS_A}, "research-package")
        self.assertEqual(decide_next(state, "research-package"), "run_repair")
        record_attempt(state, {"status": "fail", "findings": FINDINGS_B}, "research-package")
        self.assertEqual(decide_next(state, "research-package"), "escalate")  # budget spent
        state2 = new_state("draft", pathlib.Path("/tmp/d.md"), {"max_attempts": 5, "no_progress_after": 2})
        record_attempt(state2, {"findings": [{"id": "x", "severity": "error"}]}, "draft")
        self.assertEqual(decide_next(state2, "draft"), "await_llm")
        record_attempt(state2, {"findings": []}, "draft")
        self.assertEqual(decide_next(state2, "draft"), "passed")

    def test_no_progress_detects_identical_fingerprints(self) -> None:
        errors = [{"id": "missing_h2_heading", "severity": "error", "title": "missing"}]
        state = new_state("draft", pathlib.Path("/tmp/d.md"), {"max_attempts": 5, "no_progress_after": 2})
        record_attempt(state, {"findings": errors}, "draft")
        self.assertFalse(no_progress(state))
        record_attempt(state, {"findings": errors}, "draft")
        self.assertTrue(no_progress(state))
        self.assertEqual(decide_next(state, "draft"), "escalate")

    def test_target_config_defaults_and_overrides(self) -> None:
        defaults = target_config({}, "research-package")
        self.assertEqual(defaults["max_attempts"], 5)
        self.assertTrue(defaults["enabled"])
        cfg = {"governance": {"loop": {"max_attempts": 4, "targets": {"draft": {"max_attempts": 2}}}}}
        self.assertEqual(target_config(cfg, "draft")["max_attempts"], 2)
        self.assertEqual(target_config(cfg, "page-outline")["max_attempts"], 4)


class LoopRunnerDraftE2ETest(unittest.TestCase):
    """End-to-end LLM-protocol loop on the draft target."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-loop-runner-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: loop-test\ngovernance:\n  loop:\n    max_attempts: 5\n    no_progress_after: 2\n",
            encoding="utf-8",
        )
        (self.tmp / "seo").mkdir()
        self.drafts = self.tmp / "drafts"
        self.drafts.mkdir()
        self.outline = self.tmp / "outline.json"
        self.outline.write_text(
            json.dumps(
                {
                    "sections": [{"level": 2, "title": "Как выбрать вагонку"}],
                    "internal_links": [],
                    "faq": [],
                }
            ),
            encoding="utf-8",
        )
        self.draft = self.drafts / "vagonka.md"
        self.write_bad_draft()

    def write_bad_draft(self) -> None:
        self.draft.write_text("# Вагонка\n\nТекст без нужного H2 и без источников.\n", encoding="utf-8")

    def write_good_draft(self) -> None:
        self.draft.write_text(
            "# Вагонка\n\n## Как выбрать вагонку\n\nТекст с доказательствами. Source: https://example.com/spec\n",
            encoding="utf-8",
        )

    def run_loop(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "loop-runner.py"),
                "draft",
                str(self.draft),
                "--outline",
                str(self.outline),
                "--format",
                "json",
                *args,
            ],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
        )

    def state_file(self) -> pathlib.Path:
        loops = list((self.tmp / "seo" / "loops").glob("draft--*.json"))
        self.assertEqual(len(loops), 1, f"expected one loop state, got {loops}")
        return loops[0]

    def test_llm_protocol_then_pass(self) -> None:
        first = self.run_loop()
        self.assertEqual(first.returncode, 3, first.stderr)
        payload = json.loads(first.stdout)
        self.assertEqual(payload["action_required"], "llm_repair")
        self.assertTrue(any(f["id"] == "missing_h2_heading" for f in payload["findings"]))
        self.assertTrue(any("--resume" in step for step in payload["instructions"]))
        state = json.loads(self.state_file().read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "awaiting_llm")
        self.assertEqual(len(state["attempts"]), 1)
        self.assertTrue(self.state_file().with_suffix(".md").exists())

        self.write_good_draft()
        second = self.run_loop("--resume")
        self.assertEqual(second.returncode, 0, second.stderr)
        state = json.loads(self.state_file().read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "passed")
        self.assertEqual(len(state["attempts"]), 2)
        delta = state["attempts"][-1]["delta"]
        self.assertIn("error:missing_h2_heading", delta["resolved"])

    def test_no_progress_escalates_early_with_ticket(self) -> None:
        first = self.run_loop()
        self.assertEqual(first.returncode, 3)
        # No draft changes: same findings -> early escalation on attempt 2 of 5.
        second = self.run_loop("--resume")
        self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
        state = json.loads(self.state_file().read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "escalated")
        self.assertEqual(len(state["attempts"]), 2)
        self.assertIn("no progress", state["escalation"]["reason"])
        approvals = self.tmp / "seo" / "pending-approvals.md"
        self.assertTrue(approvals.exists())
        body = approvals.read_text(encoding="utf-8")
        self.assertIn("type:loop_escalation", body)
        self.assertEqual(state["escalation"]["ticket_id"] is not None, True)

    def test_status_mode_reports_without_running(self) -> None:
        self.run_loop()
        status = self.run_loop("--status")
        self.assertEqual(status.returncode, 0)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["target"], "draft")
        self.assertEqual(payload["status"], "awaiting_llm")

    def test_max_attempts_budget_escalates(self) -> None:
        # Alternate findings each attempt so no-progress never fires; budget of 2 is spent.
        first = self.run_loop("--max-attempts", "2")
        self.assertEqual(first.returncode, 3)
        self.draft.write_text("# Вагонка\n\nЕщё вариант без H2. Source: https://example.com\n", encoding="utf-8")
        second = self.run_loop("--resume", "--max-attempts", "2")
        self.assertEqual(second.returncode, 1)
        state = json.loads(self.state_file().read_text(encoding="utf-8"))
        self.assertEqual(state["escalation"]["reason"], "attempt budget spent")


if __name__ == "__main__":
    unittest.main()
