#!/usr/bin/env python3
"""Tests for the optional Pydantic config schema and validate-config --strict."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.config_schema import PYDANTIC_AVAILABLE, schema_errors  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

VALID_CFG = {
    "project": {"name": "Тест", "domain": "example.com"},
    "locale": {"language": "ru", "country": "RU"},
    "engines": [{"name": "yandex", "priority": 1}],
    "project_type": "ecommerce",
    "governance": {"loop": {"max_attempts": 5}},
    "ads": {"enabled": False},
    "rag": {"embedding": {"mode": "auto"}},
}


@unittest.skipUnless(PYDANTIC_AVAILABLE, "pydantic not installed")
class SchemaTest(unittest.TestCase):
    def test_valid_config_has_no_errors(self) -> None:
        self.assertEqual(schema_errors(VALID_CFG), [])

    def test_template_passes_the_schema(self) -> None:
        if yaml is None:
            self.skipTest("PyYAML not installed")
        cfg = yaml.safe_load((ROOT / "config" / "project.template.yaml").read_text(encoding="utf-8"))
        self.assertEqual(schema_errors(cfg), [])

    def test_missing_project_name_is_reported(self) -> None:
        errors = schema_errors({"project": {"domain": "example.com"}})
        self.assertTrue(any("project.name" in error for error in errors), errors)

    def test_out_of_range_loop_attempts(self) -> None:
        cfg = dict(VALID_CFG, governance={"loop": {"max_attempts": 99}})
        errors = schema_errors(cfg)
        self.assertTrue(any("max_attempts" in error for error in errors), errors)

    def test_bad_ads_policy_and_rag_mode(self) -> None:
        cfg = dict(VALID_CFG, ads={"policy": "yolo"}, rag={"embedding": {"mode": "sometimes"}})
        errors = schema_errors(cfg)
        self.assertTrue(any("ads.policy" in error for error in errors), errors)
        self.assertTrue(any("rag.embedding.mode" in error for error in errors), errors)

    def test_unknown_keys_are_allowed(self) -> None:
        cfg = dict(VALID_CFG, totally_new_section={"whatever": 1})
        self.assertEqual(schema_errors(cfg), [])


class StrictCliTest(unittest.TestCase):
    def test_strict_flag_reports_schema_errors(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-strict-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text(
            "project:\n  domain: example.com\nlocale:\n  language: ru\n  country: RU\n"
            "engines:\n  - name: yandex\nproject_type: blog\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate-config.py"), str(tmp / "seo-cycle.yaml"), "--strict"],
            cwd=tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 1)
        if PYDANTIC_AVAILABLE:
            self.assertIn("schema: project.name", proc.stdout)
        else:
            self.assertIn("pip3 install pydantic", proc.stdout)


if __name__ == "__main__":
    unittest.main()
