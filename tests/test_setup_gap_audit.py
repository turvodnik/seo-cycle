#!/usr/bin/env python3
"""Smoke tests for detailed first-run setup gap auditing."""

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
ROADMAP = ROOT / "scripts" / "growth-roadmap.py"
LAUNCH = ROOT / "scripts" / "launch-plan.py"
TASK_ROUTER = ROOT / "scripts" / "task-router.py"
CONTEXT_PACK = ROOT / "scripts" / "context-pack.py"
GAP_AUDIT = ROOT / "scripts" / "setup-gap-audit.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class SetupGapAuditTest(unittest.TestCase):
    def make_project(self, *, country: str, project_type: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-setup-gap-"))
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
            [sys.executable, str(SPEND), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(AUTOMATION), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(ROADMAP), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(LAUNCH), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(TASK_ROUTER), str(cfg_path), "--task", "first SEO setup", "--write"],
            [sys.executable, str(CONTEXT_PACK), str(cfg_path), "--task", "first SEO setup", "--write", "--format", "json"],
        ):
            subprocess.run(command, cwd=tmp, check=True, text=True, capture_output=True)
        return cfg_path

    def run_gap_audit(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(GAP_AUDIT), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_ru_ecommerce_gap_audit_surfaces_missing_business_and_budget_details(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        report = self.run_gap_audit(cfg_path)

        self.assertLess(report["score"], 100)
        self.assertEqual(report["categories"]["market"]["status"], "complete")
        self.assertEqual(report["categories"]["business"]["status"], "needs_input")
        self.assertIn("business.priority_products_or_services", report["missing_fields"])
        self.assertIn("budget.monthly_paid_api_usd_cap", report["missing_fields"])
        self.assertIn("automation.recommendations", report["evidence"])
        self.assertIn("seo/setup/context-pack.md", report["read_first"])
        self.assertTrue(report["recommended_questions"])
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "setup-gap-audit.md").exists())

    def test_us_local_gap_audit_checks_local_profiles_without_ecommerce_feed_requirement(self) -> None:
        cfg_path = self.make_project(country="US", project_type="local_business")
        report = self.run_gap_audit(cfg_path)

        self.assertEqual(report["categories"]["market"]["status"], "complete")
        self.assertEqual(report["categories"]["local"]["status"], "needs_input")
        self.assertIn("local.business_profile_urls", report["missing_fields"])
        self.assertNotIn("ecommerce.feed_policy", report["missing_fields"])
        self.assertIn("bing_places", report["signals"]["local_platforms"])
        self.assertIn("google_business_profile", report["signals"]["local_platforms"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
