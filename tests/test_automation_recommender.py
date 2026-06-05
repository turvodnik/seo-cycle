#!/usr/bin/env python3
"""Smoke tests for the expanded per-project automation recommender."""

from __future__ import annotations

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
AUTOMATION_PLAN = ROOT / "scripts" / "automation-plan.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class AutomationRecommenderTest(unittest.TestCase):
    def make_project(self, *, country: str, project_type: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-automation-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg_path = tmp / "seo-cycle.yaml"
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = f"{country} {project_type}"
        cfg["project"]["domain"] = f"{country.lower()}-{project_type}.test"
        cfg["project_type"] = project_type
        cfg["locale"]["country"] = country
        cfg["locale"]["language"] = "ru" if country == "RU" else "en"
        cfg["locale"]["locale_iso"] = "ru-RU" if country == "RU" else "en-US"
        cfg["locale"]["google_gl"] = country.lower()
        cfg["locale"]["google_hl"] = cfg["locale"]["language"]
        cfg["region_profile"] = "ru" if country == "RU" else "us"
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        for command in (
            [sys.executable, str(INTAKE), str(cfg_path), "--defaults", "--write"],
            [sys.executable, str(TOOL_STACK), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(SPEND), str(cfg_path), "--write", "--format", "json"],
        ):
            subprocess.run(command, cwd=tmp, check=True, text=True, capture_output=True)
        return cfg_path

    def run_automation(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(AUTOMATION), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_ru_ecommerce_gets_full_guarded_automation_matrix(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        report = self.run_automation(cfg_path)
        planned = report["policy_overlay"]["planned_automations"]

        for task_id in (
            "usage_budget_watch",
            "spend_guard_watch",
            "technical_indexability_watch",
            "search_console_index_watch",
            "schema_cwv_watch",
            "content_decay_refresh_queue",
            "monthly_ai_visibility",
            "ecommerce_feed_quality",
        ):
            self.assertIn(task_id, planned)
            self.assertTrue(planned[task_id]["enabled"], task_id)

        self.assertEqual(planned["ecommerce_feed_quality"]["mode"], "approval_only")
        self.assertIn("merchant_feed_errors_report", planned["ecommerce_feed_quality"]["actions"])
        self.assertIn("paid_api_run", planned["content_decay_refresh_queue"]["approval_gates"])
        self.assertFalse(report["policy_overlay"]["create_schedules"])
        self.assertTrue((cfg_path.parent / "seo" / "automations" / "automation-recommendations.md").exists())

    def test_us_local_gets_bing_local_without_ecommerce_feed(self) -> None:
        cfg_path = self.make_project(country="US", project_type="local_business")
        report = self.run_automation(cfg_path)
        planned = report["policy_overlay"]["planned_automations"]

        self.assertTrue(planned["local_seo_reputation"]["enabled"])
        self.assertTrue(planned["bing_index_watch"]["enabled"])
        self.assertTrue(planned["schema_cwv_watch"]["enabled"])
        self.assertFalse(planned["ecommerce_feed_quality"]["enabled"])
        self.assertIn("bing_webmaster", planned["bing_index_watch"]["tools"])
        self.assertEqual(planned["local_seo_reputation"]["mode"], "report_only")

    def test_apply_preserves_tools_gates_and_plan_commands(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        proc = subprocess.run(
            [sys.executable, str(AUTOMATION), str(cfg_path), "--apply", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertTrue(report["policy_overlay"]["planned_automations"]["content_decay_refresh_queue"]["enabled"])

        policy = yaml.safe_load((cfg_path.parent / "seo" / "automation-policy.yaml").read_text(encoding="utf-8"))
        content_decay = policy["planned_automations"]["content_decay_refresh_queue"]
        self.assertIn("paid_api_run", content_decay["approval_gates"])
        self.assertTrue(content_decay["tools"])

        subprocess.run(
            [sys.executable, str(AUTOMATION_PLAN), str(cfg_path), "--write", "--include-disabled"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        plan = json.loads((cfg_path.parent / "seo" / "automations" / "automation-plan.json").read_text(encoding="utf-8"))
        commands = {task["task_id"]: task["command"] for task in plan["tasks"]}
        self.assertIn("spend-guard.py", commands["spend_guard_watch"])
        self.assertIn("gsc-fetch.py", commands["search_console_index_watch"])
        self.assertIn("schema-validate.py", commands["schema_cwv_watch"])
        self.assertIn("monthly-runner.sh", commands["content_decay_refresh_queue"])
        self.assertIn("refresh --dry-run", commands["content_decay_refresh_queue"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
