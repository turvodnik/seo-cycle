#!/usr/bin/env python3
"""Smoke tests for the per-project growth roadmap generator."""

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


@unittest.skipIf(yaml is None, "PyYAML is required")
class GrowthRoadmapTest(unittest.TestCase):
    def make_project(self, *, country: str, project_type: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-growth-roadmap-"))
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
        ):
            subprocess.run(command, cwd=tmp, check=True, text=True, capture_output=True)
        return cfg_path

    def run_roadmap(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(ROADMAP), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_ru_ecommerce_prioritizes_revenue_content_and_guarded_ai(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        report = self.run_roadmap(cfg_path)
        lanes = report["lanes"]
        actions = {item["id"]: item for item in report["actions"]}

        self.assertIn("technical_foundation", lanes)
        self.assertIn("ecommerce_revenue", lanes)
        self.assertIn("content_entity_growth", lanes)
        self.assertIn("ai_visibility", lanes)
        self.assertNotIn("foreign_tracking_install", actions)
        self.assertIn("rf_tracking_policy_guard", actions)
        self.assertIn("google_cloud_nlp", actions["entity_audit_priority_urls"]["tools"])
        self.assertIn("paid_api_run", actions["entity_audit_priority_urls"]["approval_gates"])
        self.assertLessEqual(len(report["actions"]), report["limits"]["max_actions"])
        self.assertTrue((cfg_path.parent / "seo" / "growth-roadmap.generated.yaml").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "growth-roadmap.md").exists())

    def test_us_local_prioritizes_local_and_bing_without_ecommerce_lane(self) -> None:
        cfg_path = self.make_project(country="US", project_type="local_business")
        report = self.run_roadmap(cfg_path)
        lanes = report["lanes"]
        actions = {item["id"]: item for item in report["actions"]}

        self.assertIn("technical_foundation", lanes)
        self.assertIn("local_dominance", lanes)
        self.assertNotIn("ecommerce_revenue", lanes)
        self.assertIn("bing_webmaster", actions["search_console_data_contract"]["tools"])
        self.assertIn("bing_places", actions["local_profile_dominance"]["tools"])
        self.assertIn("google_business_profile", actions["local_profile_dominance"]["tools"])
        self.assertNotIn("rf_tracking_policy_guard", actions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
