#!/usr/bin/env python3
"""Smoke tests for the low-token project setup blueprint."""

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
ONBOARDING = ROOT / "scripts" / "setup-onboarding.py"
LAUNCH = ROOT / "scripts" / "launch-plan.py"
GAP_AUDIT = ROOT / "scripts" / "setup-gap-audit.py"
BLUEPRINT = ROOT / "scripts" / "setup-blueprint.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class SetupBlueprintTest(unittest.TestCase):
    def make_project(self, *, country: str, project_type: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-blueprint-"))
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
            [sys.executable, str(ONBOARDING), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(LAUNCH), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(GAP_AUDIT), str(cfg_path), "--write", "--format", "json"],
        ):
            subprocess.run(command, cwd=tmp, check=True, text=True, capture_output=True)
        return cfg_path

    def run_blueprint(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(BLUEPRINT), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_ru_ecommerce_blueprint_is_compact_and_gated(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        report = self.run_blueprint(cfg_path)

        self.assertEqual(report["market_axes"]["country"], "RU")
        self.assertIn("yandex", report["market_axes"]["search_engines"])
        self.assertTrue(report["business_axes"]["ecommerce"])
        self.assertFalse(report["context_contract"]["raw_data_in_context"])
        self.assertLessEqual(report["rendered_chars"], report["context_contract"]["max_blueprint_chars"])
        self.assertEqual(report["context_contract"]["first_read"][0], "seo/setup/setup-blueprint.md")
        self.assertIn("rf_foreign_tracking_guard", report["guardrails"])
        self.assertIn("paid_api_approval_guard", report["guardrails"])
        axes = {row["axis"] for row in report["decision_matrix"]}
        for axis in ("market.search_engines", "business.project_type", "marketing.paid_ads", "tools.guarded_paid_or_quota", "budget.monthly_caps", "automation.planned"):
            self.assertIn(axis, axes)
        self.assertIn("google_cloud_nlp", report["tool_axes"]["guarded_paid_or_quota"])
        self.assertGreater(report["setup_readiness"]["missing_count"], 0)
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "setup-blueprint.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "setup-matrix.csv").exists())

    def test_us_local_blueprint_enables_local_bing_without_rf_guard(self) -> None:
        cfg_path = self.make_project(country="US", project_type="local_business")
        report = self.run_blueprint(cfg_path)

        self.assertEqual(report["market_axes"]["country"], "US")
        self.assertIn("bing", report["market_axes"]["search_engines"])
        self.assertTrue(report["business_axes"]["local"])
        self.assertIn("bing_places", report["business_axes"]["local_platforms"])
        self.assertIn("bing_webmaster", report["tool_axes"]["free_first"])
        self.assertIn("BING_WEBMASTER_API_KEY", report["human_inputs"]["env_names"])
        self.assertNotIn("=", "\n".join(report["human_inputs"]["env_names"]))
        self.assertNotIn("rf_foreign_tracking_guard", report["guardrails"])
        local_pack = next(row for row in report["action_packs"] if row["id"] == "local_profiles")
        self.assertTrue(local_pack["enabled"])
        self.assertIn("seo/setup/setup-blueprint.md", report["context_contract"]["first_read"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
