#!/usr/bin/env python3
"""Smoke tests for the per-project launch plan contract."""

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
AUTOMATION = ROOT / "scripts" / "automation-recommender.py"
ROADMAP = ROOT / "scripts" / "growth-roadmap.py"
ONBOARDING = ROOT / "scripts" / "setup-onboarding.py"
LAUNCH = ROOT / "scripts" / "launch-plan.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class LaunchPlanTest(unittest.TestCase):
    def make_project(self, *, country: str, project_type: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-launch-plan-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg_path = tmp / "seo-cycle.yaml"
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = f"{country} {project_type}"
        cfg["project"]["domain"] = f"{country.lower()}-{project_type}.test"
        cfg["project_type"] = project_type
        cfg["locale"]["country"] = country
        cfg["locale"]["region"] = "Moscow" if country == "RU" else "California"
        cfg["locale"]["city"] = "Moscow" if country == "RU" else "San Francisco"
        cfg["locale"]["language"] = "ru" if country == "RU" else "en"
        cfg["locale"]["locale_iso"] = "ru-RU" if country == "RU" else "en-US"
        cfg["locale"]["google_gl"] = country.lower()
        cfg["locale"]["google_hl"] = cfg["locale"]["language"]
        cfg["region_profile"] = "ru" if country == "RU" else "us"
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        for command in (
            [sys.executable, str(INTAKE), str(cfg_path), "--defaults", "--write"],
            [sys.executable, str(TOOL_STACK), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(AUTOMATION), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(ROADMAP), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(ONBOARDING), str(cfg_path), "--write", "--format", "json"],
        ):
            subprocess.run(command, cwd=tmp, check=True, text=True, capture_output=True)
        return cfg_path

    def run_launch_plan(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(LAUNCH), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_ru_ecommerce_launch_contract_guards_budget_tracking_and_ai_tools(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        report = self.run_launch_plan(cfg_path)

        self.assertEqual(report["market_matrix"]["country"], "RU")
        self.assertIn("yandex", report["market_matrix"]["search_engines"])
        self.assertEqual(report["business_matrix"]["project_type"], "ecommerce")
        self.assertFalse(report["token_contract"]["raw_data_in_context"])
        self.assertTrue(report["token_contract"]["cache_first"])
        self.assertIn("google_cloud_nlp", report["tool_contract"]["guarded_paid_or_quota"])
        self.assertIn("neuronwriter", report["tool_contract"]["guarded_paid_or_quota"])
        self.assertIn("google_analytics_4", report["tool_contract"]["forbidden_or_disabled"])
        self.assertIn("tracking_tag_install", report["approval_gates"])
        self.assertIn("paid_api_run", report["approval_gates"])
        self.assertIn("GOOGLE_APPLICATION_CREDENTIALS", report["human_inputs"]["env_names"])
        self.assertNotIn("=", "\n".join(report["human_inputs"]["env_names"]))
        self.assertFalse(report["automation_contract"]["create_schedules"])
        self.assertIn("setup-control-plane", " ".join(report["execution_order"]))
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "launch-plan.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "launch-plan.generated.yaml").exists())

    def test_us_local_launch_contract_enables_bing_and_local_without_rf_guard(self) -> None:
        cfg_path = self.make_project(country="US", project_type="local_business")
        report = self.run_launch_plan(cfg_path)

        self.assertEqual(report["market_matrix"]["country"], "US")
        self.assertIn("bing", report["market_matrix"]["search_engines"])
        self.assertIn("bing_webmaster", report["tool_contract"]["free_first"])
        self.assertIn("bing_places", report["tool_contract"]["local_profiles"])
        self.assertIn("google_business_profile", report["tool_contract"]["local_profiles"])
        self.assertIn("BING_WEBMASTER_API_KEY", report["human_inputs"]["env_names"])
        self.assertIn("GOOGLE_BUSINESS_ACCOUNT_ID", report["human_inputs"]["env_names"])
        self.assertNotIn("rf_foreign_tracking_guard", report["policy_guards"])
        self.assertLessEqual(len(report["execution_order"]), report["limits"]["max_execution_steps"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
