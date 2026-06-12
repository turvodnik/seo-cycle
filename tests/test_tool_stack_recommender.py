#!/usr/bin/env python3
"""Smoke tests for the generated tool-stack recommendation layer."""

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
SCRIPT = ROOT / "scripts" / "tool-stack-recommender.py"
INTAKE = ROOT / "scripts" / "project-intake-wizard.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class ToolStackRecommenderTest(unittest.TestCase):
    def make_project(self, *, country: str, project_type: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-tool-stack-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg_path = tmp / "seo-cycle.yaml"
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = f"{country} test"
        cfg["project"]["domain"] = f"{country.lower()}-example.test"
        cfg["project_type"] = project_type
        cfg["locale"]["country"] = country
        cfg["locale"]["language"] = "ru" if country == "RU" else "en"
        cfg["locale"]["locale_iso"] = "ru-RU" if country == "RU" else "en-US"
        cfg["locale"]["google_gl"] = country.lower()
        cfg["locale"]["google_hl"] = cfg["locale"]["language"]
        cfg["region_profile"] = "ru" if country == "RU" else "us"
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        subprocess.run(
            [sys.executable, str(INTAKE), str(cfg_path), "--defaults", "--write"],
            cwd=tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        return cfg_path

    def run_recommender(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_ru_ecommerce_guards_paid_and_tracking_tools(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        report = self.run_recommender(cfg_path)
        decisions = report["decisions"]

        self.assertEqual(decisions["yandex_webmaster"]["decision"], "enabled")
        self.assertEqual(decisions["google_search_console"]["decision"], "enabled")
        self.assertEqual(decisions["google_cloud_nlp"]["decision"], "approval_required")
        self.assertEqual(decisions["neuronwriter"]["decision"], "approval_required")
        self.assertEqual(decisions["xmlriver"]["decision"], "approval_required")
        self.assertIn("paid_api_run", decisions["xmlriver"]["approval_gates"])
        self.assertEqual(decisions["google_analytics_4"]["decision"], "disabled")
        self.assertEqual(decisions["microsoft_clarity"]["decision"], "disabled")
        self.assertIn(decisions["yandex_merchant"]["decision"], {"enabled", "report_only"})

        generated = cfg_path.parent / "seo" / "tool-stack.generated.yaml"
        self.assertTrue(generated.exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "tool-stack-report.md").exists())

    def test_us_local_recommends_bing_places_and_disables_yandex_stack(self) -> None:
        cfg_path = self.make_project(country="US", project_type="local_business")
        report = self.run_recommender(cfg_path)
        decisions = report["decisions"]

        self.assertEqual(decisions["google_search_console"]["decision"], "enabled")
        self.assertEqual(decisions["bing_webmaster"]["decision"], "enabled")
        self.assertEqual(decisions["bing_places"]["decision"], "enabled")
        self.assertEqual(decisions["google_business_profile"]["decision"], "enabled")
        self.assertEqual(decisions["yandex_wordstat"]["decision"], "not_applicable")
        self.assertEqual(decisions["xmlriver"]["decision"], "approval_required")
        self.assertIn("paid_api_run", decisions["xmlriver"]["approval_gates"])
        self.assertEqual(decisions["yandex_merchant"]["decision"], "not_applicable")
        self.assertEqual(decisions["google_merchant"]["decision"], "not_applicable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
