#!/usr/bin/env python3
"""Smoke tests for the detailed project setup onboarding playbook."""

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


@unittest.skipIf(yaml is None, "PyYAML is required")
class SetupOnboardingTest(unittest.TestCase):
    def make_project(self, *, country: str, project_type: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-onboarding-"))
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
            [sys.executable, str(AUTOMATION), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(ROADMAP), str(cfg_path), "--write", "--format", "json"],
        ):
            subprocess.run(command, cwd=tmp, check=True, text=True, capture_output=True)
        return cfg_path

    def run_onboarding(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(ONBOARDING), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_ru_ecommerce_has_human_secret_and_policy_steps(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        report = self.run_onboarding(cfg_path)
        steps = {step["id"]: step for step in report["steps"]}
        owners = {step["owner"] for step in report["steps"]}

        self.assertIn("human_secret", owners)
        self.assertIn("approval", owners)
        self.assertIn("rf_tracking_policy_review", steps)
        self.assertIn("google_cloud_nlp_budget_guard", steps)
        self.assertIn("run_spend_guard", steps)
        self.assertIn("spend_guard_report", steps["run_spend_guard"]["proofs"])
        self.assertIn("run_setup_control_plane", steps)
        self.assertIn("setup_control_plane", steps["run_setup_control_plane"]["proofs"])
        self.assertIn("GOOGLE_APPLICATION_CREDENTIALS", report["secret_env_names"])
        self.assertIn("NEURON_API_KEY", report["secret_env_names"])
        self.assertNotIn("=", "\n".join(report["secret_env_names"]))
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "onboarding-playbook.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "onboarding-checklist.csv").exists())

    def test_us_local_has_local_and_bing_setup_without_rf_guard(self) -> None:
        cfg_path = self.make_project(country="US", project_type="local_business")
        report = self.run_onboarding(cfg_path)
        steps = {step["id"]: step for step in report["steps"]}

        self.assertIn("connect_bing_webmaster", steps)
        self.assertIn("connect_local_profiles", steps)
        self.assertNotIn("rf_tracking_policy_review", steps)
        self.assertIn("BING_WEBMASTER_API_KEY", report["secret_env_names"])
        self.assertIn("GOOGLE_BUSINESS_ACCOUNT_ID", report["secret_env_names"])
        self.assertLessEqual(len(report["steps"]), report["limits"]["max_steps"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
