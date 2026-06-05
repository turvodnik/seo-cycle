#!/usr/bin/env python3
"""Smoke tests for setup questionnaire answer planning."""

from __future__ import annotations

import csv
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "project.template.yaml"
INTAKE = ROOT / "scripts" / "project-intake-wizard.py"
TOOL_STACK = ROOT / "scripts" / "tool-stack-recommender.py"
SPEND = ROOT / "scripts" / "spend-guard.py"
AUTOMATION = ROOT / "scripts" / "automation-recommender.py"
ROADMAP = ROOT / "scripts" / "growth-roadmap.py"
LAUNCH = ROOT / "scripts" / "launch-plan.py"
TASK_ROUTER = ROOT / "scripts" / "task-router.py"
CONTEXT_PACK = ROOT / "scripts" / "context-pack.py"
GAP_AUDIT = ROOT / "scripts" / "setup-gap-audit.py"
ANSWER_PLAN = ROOT / "scripts" / "setup-answer-plan.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class SetupAnswerPlanTest(unittest.TestCase):
    def make_project(self) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-answer-plan-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg_path = tmp / "seo-cycle.yaml"
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = "RU ecommerce"
        cfg["project"]["domain"] = "ru-ecommerce.test"
        cfg["project_type"] = "ecommerce"
        cfg["locale"]["country"] = "RU"
        cfg["locale"]["region"] = "Moscow"
        cfg["locale"]["city"] = "Moscow"
        cfg["locale"]["language"] = "ru"
        cfg["locale"]["locale_iso"] = "ru-RU"
        cfg["locale"]["google_gl"] = "ru"
        cfg["locale"]["google_hl"] = "ru"
        cfg["region_profile"] = "ru"
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        for command in (
            [sys.executable, str(INTAKE), str(cfg_path), "--defaults", "--write"],
            [sys.executable, str(TOOL_STACK), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(SPEND), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(AUTOMATION), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(ROADMAP), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(LAUNCH), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(TASK_ROUTER), str(cfg_path), "--task", "first SEO setup", "--write"],
            [sys.executable, str(CONTEXT_PACK), str(cfg_path), "--task", "first SEO setup", "--write", "--format", "json"],
            [sys.executable, str(GAP_AUDIT), str(cfg_path), "--write", "--format", "json"],
        ):
            subprocess.run(command, cwd=tmp, check=True, text=True, capture_output=True)
        return cfg_path

    def fill_answers(self, cfg_path: pathlib.Path, answers: dict[str, str]) -> None:
        questionnaire = cfg_path.parent / "seo" / "setup" / "setup-questionnaire.csv"
        with questionnaire.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        for row in rows:
            if row["field"] in answers:
                row["answer"] = answers[row["field"]]
        with questionnaire.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def run_answer_plan(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(ANSWER_PLAN), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_answer_plan_turns_filled_questionnaire_into_manual_change_plan(self) -> None:
        cfg_path = self.make_project()
        self.fill_answers(
            cfg_path,
            {
                "business.priority_products_or_services": "Минеральная вата; Фанера ФК; Цемент",
                "budget.monthly_paid_api_usd_cap": "5",
            },
        )

        report = self.run_answer_plan(cfg_path)

        self.assertEqual(report["accepted_count"], 2)
        self.assertEqual(report["rejected_count"], 0)
        self.assertIn("business.priority_products_or_services", report["answered_fields"])
        self.assertIn("budget.monthly_paid_api_usd_cap", report["answered_fields"])
        target_paths = {row["target_path"] for row in report["changes"]}
        self.assertIn("business.priority_products_or_services", target_paths)
        self.assertIn("governance.budget_policy.monthly_paid_api_usd_cap", target_paths)
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "setup-answer-plan.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "setup-answer-plan.json").exists())

    def test_answer_plan_rejects_secret_like_answers(self) -> None:
        cfg_path = self.make_project()
        self.fill_answers(cfg_path, {"business.priority_products_or_services": "api_key=not-a-real-value"})

        report = self.run_answer_plan(cfg_path)

        self.assertEqual(report["accepted_count"], 0)
        self.assertEqual(report["rejected_count"], 1)
        self.assertIn("secret_like_answer", {row["reason"] for row in report["rejected"]})
        self.assertNotIn("not-a-real-value", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
