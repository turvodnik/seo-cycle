#!/usr/bin/env python3
"""Tests for the v1.63 staged orchestrator core."""

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
SEO_CYCLE_RUN = SCRIPTS / "seo-cycle-run.py"
PYTHONPATH = f"{SCRIPTS}"

sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.orchestrator import redact_text, run_stage
from seo_cycle_core.stages import StageContract


def py_command(code: str) -> list[str]:
    return [sys.executable, "-c", code]


class OrchestratorCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-orchestrator-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_stage_contract_defaults_to_five_repair_attempts(self) -> None:
        contract = StageContract.from_mapping(
            {
                "id": "quality_gate",
                "title": "Quality gate",
                "required_inputs": [],
                "commands": [],
                "outputs": ["quality.json"],
                "gate": {"command": py_command("raise SystemExit(0)")},
                "repair_commands": [],
                "approval_required": False,
                "stop_conditions": [],
                "next_stage": "next",
            }
        )

        self.assertEqual(contract.max_attempts, 5)
        self.assertEqual(contract.id, "quality_gate")
        self.assertEqual(contract.next_stage, "next")
        self.assertEqual(tuple(contract.outputs), ("quality.json",))

    def test_redaction_covers_authorization_bearer_values(self) -> None:
        text = "Authorization: Bearer should-not-leak\napi_key=also-hidden\nsafe line"

        redacted = redact_text(text)

        self.assertNotIn("should-not-leak", redacted)
        self.assertNotIn("also-hidden", redacted)
        self.assertIn("Authorization: ***", redacted)
        self.assertIn("api_key=***", redacted)
        self.assertIn("safe line", redacted)

    def test_orchestrator_repairs_then_reruns_stage_until_gate_passes(self) -> None:
        log_path = self.tmp / "run.log"
        ready_path = self.tmp / "ready.txt"
        contract = StageContract.from_mapping(
            {
                "id": "repairable",
                "title": "Repairable stage",
                "commands": [
                    py_command(
                        "import pathlib; "
                        f"pathlib.Path({str(log_path)!r}).open('a').write('stage\\n')"
                    )
                ],
                "outputs": [str(ready_path)],
                "gate": {
                    "command": py_command(
                        "import pathlib, sys; "
                        f"raise SystemExit(0 if pathlib.Path({str(ready_path)!r}).exists() else 1)"
                    )
                },
                "repair_commands": [
                    py_command(
                        "import pathlib; "
                        f"pathlib.Path({str(log_path)!r}).open('a').write('repair\\n'); "
                        f"pathlib.Path({str(ready_path)!r}).write_text('ok', encoding='utf-8')"
                    )
                ],
                "max_attempts": 5,
            }
        )

        result = run_stage(contract, cwd=self.tmp, write_report=True)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["repair_attempts"], 1)
        self.assertEqual(result["gate_attempts"], 2)
        self.assertEqual(log_path.read_text(encoding="utf-8").splitlines(), ["stage", "repair", "stage"])
        self.assertTrue((self.tmp / "seo" / "orchestrator" / "repairable-report.json").exists())

    def test_orchestrator_writes_blocker_after_repair_attempt_limit(self) -> None:
        log_path = self.tmp / "run.log"
        contract = StageContract.from_mapping(
            {
                "id": "blocked",
                "title": "Blocked stage",
                "commands": [
                    py_command(
                        "import pathlib; "
                        f"pathlib.Path({str(log_path)!r}).open('a').write('stage\\n')"
                    )
                ],
                "gate": {"command": py_command("raise SystemExit(2)")},
                "repair_commands": [
                    py_command(
                        "import pathlib; "
                        f"pathlib.Path({str(log_path)!r}).open('a').write('repair\\n')"
                    )
                ],
                "max_attempts": 2,
                "stop_conditions": ["manual source review required"],
            }
        )

        result = run_stage(contract, cwd=self.tmp, write_report=True)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["repair_attempts"], 2)
        self.assertEqual(result["gate_attempts"], 3)
        self.assertEqual(
            log_path.read_text(encoding="utf-8").splitlines(),
            ["stage", "repair", "stage", "repair", "stage"],
        )
        blocker = json.loads((self.tmp / "seo" / "orchestrator" / "blocked-blocker.json").read_text(encoding="utf-8"))
        self.assertEqual(blocker["stage_id"], "blocked")
        self.assertEqual(blocker["repair_attempts"], 2)
        self.assertIn("manual source review required", blocker["stop_conditions"])

    def test_seo_cycle_run_executes_stage_file_and_returns_json(self) -> None:
        ready_path = self.tmp / "ready.txt"
        stage_file = self.tmp / "stage.json"
        stage_file.write_text(
            json.dumps(
                {
                    "stages": [
                        {
                            "id": "cli_stage",
                            "title": "CLI stage",
                            "commands": [
                                py_command(
                                    "import pathlib; "
                                    f"pathlib.Path({str(ready_path)!r}).write_text('ok', encoding='utf-8')"
                                )
                            ],
                            "outputs": [str(ready_path)],
                            "gate": {
                                "command": py_command(
                                    "import pathlib; "
                                    f"raise SystemExit(0 if pathlib.Path({str(ready_path)!r}).exists() else 1)"
                                )
                            },
                            "repair_commands": [],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        proc = subprocess.run(
            [sys.executable, str(SEO_CYCLE_RUN), "--stage-file", str(stage_file), "--write", "--format", "json"],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
            env={"PYTHONPATH": PYTHONPATH},
        )
        report = json.loads(proc.stdout)

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["stages"][0]["id"], "cli_stage")
        self.assertTrue((self.tmp / "seo" / "orchestrator" / "cli_stage-report.json").exists())

    def test_seo_cycle_run_renders_research_package_template_plan(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(SEO_CYCLE_RUN),
                "--stage-template",
                "research-package",
                "--package",
                "seo/research-package",
                "--format",
                "json",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
            env={"PYTHONPATH": PYTHONPATH},
        )
        report = json.loads(proc.stdout)
        stages = report["stages"]

        self.assertEqual(report["status"], "planned")
        self.assertEqual(
            [stage["id"] for stage in stages],
            ["research_quality_gate", "deep_page_briefs_v3", "page_outline_quality_v3"],
        )
        self.assertEqual(stages[0]["max_attempts"], 5)
        self.assertIn("seo/research-package/research-package-quality.json", stages[0]["outputs"])
        self.assertTrue(any("research-package-repair.py" in part for part in stages[0]["repair_commands"][0]))
        self.assertTrue(any("page-outline-v3.py" in part for part in stages[1]["commands"][0]))
        self.assertIn("--all-mvp", stages[1]["commands"][0])
        self.assertTrue(any("page-outline-quality.py" in part for part in stages[2]["gate"]["command"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
