#!/usr/bin/env python3
"""Tests for shared seo_cycle_core helpers."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_cycle_core.config import boolish, find_config, nested_get, numeric, policy_path, project_root_for, rel_path
from seo_cycle_core.providers import notebooklm_health, perplexity_health
from seo_cycle_core.reports import write_report_bundle
from seo_cycle_core.subprocesses import run_json


class SeoCycleCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-core-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_config_helpers_resolve_project_and_policy_paths(self) -> None:
        cfg_path = self.tmp / "seo-cycle.yaml"
        cfg_path.write_text("policy_files:\n  context_pack: seo/setup/context-pack.md\n", encoding="utf-8")

        self.assertEqual(find_config(self.tmp), cfg_path)
        self.assertEqual(project_root_for(cfg_path), self.tmp)
        self.assertEqual(rel_path(self.tmp, "seo/setup/context-pack.md"), self.tmp / "seo/setup/context-pack.md")
        self.assertEqual(policy_path({"policy_files": {"foo": "seo/foo.md"}}, self.tmp, "foo", "fallback.md"), self.tmp / "seo/foo.md")
        self.assertEqual(policy_path({}, self.tmp, "foo", "fallback.md"), self.tmp / "fallback.md")

    def test_parsing_helpers_are_consistent(self) -> None:
        self.assertTrue(boolish("yes"))
        self.assertTrue(boolish("да"))
        self.assertFalse(boolish("no"))
        self.assertEqual(numeric("12.5", 1), 12.5)
        self.assertEqual(numeric("bad", 7), 7)
        self.assertEqual(nested_get({"a": {"b": 3}}, "a.b"), 3)
        self.assertIsNone(nested_get({"a": {}}, "a.b"))

    def test_report_bundle_writes_stable_markdown_json_and_latest_files(self) -> None:
        paths = {
            "markdown": self.tmp / "seo/report.md",
            "json": self.tmp / "seo/report.json",
            "latest_markdown": self.tmp / "seo/latest-report.md",
            "latest_json": self.tmp / "seo/latest-report.json",
        }
        write_report_bundle(paths, "# Report\n", {"status": "ok"})

        self.assertEqual((self.tmp / "seo/report.md").read_text(encoding="utf-8"), "# Report\n")
        self.assertEqual(json.loads((self.tmp / "seo/report.json").read_text(encoding="utf-8"))["status"], "ok")
        self.assertTrue((self.tmp / "seo/latest-report.md").exists())
        self.assertTrue((self.tmp / "seo/latest-report.json").exists())

    def test_run_json_reports_invalid_json_without_raising(self) -> None:
        result = run_json([sys.executable, "-c", "print('not-json')"], self.tmp)
        self.assertEqual(result["error"], "invalid json")
        self.assertEqual(result["exit_code"], 0)

    def test_perplexity_health_uses_persistent_app_without_password_storage(self) -> None:
        app = self.tmp / "Perplexity.app"
        app.mkdir()
        health = perplexity_health(app_paths=[app], browser_available=True, env={})

        self.assertEqual(health["status"], "available")
        self.assertTrue(health["app_detected"])
        self.assertEqual(health["preferred_mode"], "persistent_browser")
        self.assertFalse(health["stores_password"])

    def test_perplexity_health_degrades_without_available_surface(self) -> None:
        health = perplexity_health(app_paths=[self.tmp / "Missing.app"], browser_available=False, env={})

        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["fallback_mode"], "manual_browser")

    def test_notebooklm_health_prefers_mcp_when_tools_are_exposed(self) -> None:
        config = self.tmp / "config.toml"
        config.write_text(
            """
[mcp_servers.notebooklm]
command = "npx"
args = ["notebooklm-mcp@latest"]

[mcp_servers.notebooklm.env]
NOTEBOOKLM_DISABLED_TOOLS = "cleanup_data,re_auth,add_source"
""",
            encoding="utf-8",
        )

        health = notebooklm_health(config, tools_exposed=True, notebook_url="https://notebooklm.google.com/notebook/test")

        self.assertEqual(health["status"], "available")
        self.assertEqual(health["access_mode"], "mcp")
        self.assertIn("cleanup_data", health["disabled_tools"])
        self.assertEqual(health["notebook_url"], "https://notebooklm.google.com/notebook/test")

    def test_notebooklm_health_falls_back_when_tools_are_not_exposed(self) -> None:
        config = self.tmp / "config.toml"
        config.write_text("[mcp_servers.notebooklm]\ncommand = \"npx\"\n", encoding="utf-8")

        health = notebooklm_health(config, tools_exposed=False)

        self.assertEqual(health["status"], "fallback_required")
        self.assertEqual(health["access_mode"], "browser_export")
        self.assertTrue(health["configured"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
