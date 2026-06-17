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

from seo_cycle_core.config import boolish, find_config, find_config_upwards, nested_get, numeric, policy_path, project_root_for, rel_path
from seo_cycle_core.providers import notebooklm_health, perplexity_health
from seo_cycle_core.reports import stringify_paths, write_artifacts, write_json_file, write_jsonl_file, write_report_bundle, write_sorted_json_file
from seo_cycle_core.source_artifacts import (
    make_vector_record,
    read_cached_distillate,
    stable_cache_key,
    utc_now_iso,
    write_source_artifacts,
)
from seo_cycle_core.subprocesses import json_from_step, run_command_step, run_json


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

    def test_config_helper_finds_config_upwards(self) -> None:
        cfg_path = self.tmp / "seo-cycle.yaml"
        nested = self.tmp / "seo" / "cycles" / "draft"
        nested.mkdir(parents=True)
        cfg_path.write_text("project: {}\n", encoding="utf-8")

        self.assertEqual(find_config_upwards(nested), cfg_path)

    def test_parsing_helpers_are_consistent(self) -> None:
        self.assertTrue(boolish("yes"))
        self.assertTrue(boolish("да"))
        self.assertFalse(boolish("no"))
        self.assertEqual(numeric("12.5", 1), 12.5)
        self.assertEqual(numeric("bad", 7), 7)
        self.assertEqual(nested_get({"a": {"b": 3}}, "a.b"), 3)
        self.assertIsNone(nested_get({"a": {}}, "a.b"))

    def test_utc_now_iso_is_python39_compatible(self) -> None:
        value = utc_now_iso()

        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

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

    def test_report_bundle_can_write_sorted_json_keys_when_requested(self) -> None:
        paths = {
            "markdown": self.tmp / "seo/sorted-report.md",
            "json": self.tmp / "seo/sorted-report.json",
            "latest_markdown": self.tmp / "seo/latest-sorted-report.md",
            "latest_json": self.tmp / "seo/latest-sorted-report.json",
        }

        write_report_bundle(paths, "# Report\n", {"z": 1, "a": 2}, sort_keys=True)

        json_text = paths["json"].read_text(encoding="utf-8")
        self.assertLess(json_text.index('"a"'), json_text.index('"z"'))

    def test_report_artifact_helpers_write_text_json_and_string_paths(self) -> None:
        paths = {
            "markdown": self.tmp / "seo/setup/report.md",
            "json": self.tmp / "seo/setup/report.json",
            "csv": self.tmp / "seo/setup/report.csv",
        }

        write_artifacts(
            text_files={
                paths["markdown"]: "# Report\n",
                paths["csv"]: "name,status\nsetup,ok\n",
            },
            json_files={
                paths["json"]: {"status": "ok"},
            },
        )

        self.assertEqual(paths["markdown"].read_text(encoding="utf-8"), "# Report\n")
        self.assertEqual(json.loads(paths["json"].read_text(encoding="utf-8"))["status"], "ok")
        self.assertEqual(paths["csv"].read_text(encoding="utf-8").splitlines()[1], "setup,ok")
        self.assertEqual(stringify_paths(paths), {key: str(path) for key, path in paths.items()})

    def test_report_helpers_write_json_and_jsonl_files(self) -> None:
        unsorted_path = self.tmp / "reports" / "unsorted.json"
        sorted_path = self.tmp / "reports" / "sorted.json"
        jsonl_path = self.tmp / "reports" / "rows.jsonl"

        write_json_file(unsorted_path, {"z": 1, "a": 2})
        write_sorted_json_file(sorted_path, {"z": 1, "a": 2})
        write_jsonl_file(jsonl_path, [{"b": 2, "a": 1}, {"c": 3}])

        self.assertLess(unsorted_path.read_text(encoding="utf-8").index('"z"'), unsorted_path.read_text(encoding="utf-8").index('"a"'))
        self.assertLess(sorted_path.read_text(encoding="utf-8").index('"a"'), sorted_path.read_text(encoding="utf-8").index('"z"'))
        self.assertEqual(len(jsonl_path.read_text(encoding="utf-8").splitlines()), 2)
        self.assertIn('{"a": 1, "b": 2}', jsonl_path.read_text(encoding="utf-8").splitlines()[0])

    def test_setup_blueprint_uses_shared_artifact_writer(self) -> None:
        source = (ROOT / "scripts/setup-blueprint.py").read_text(encoding="utf-8")

        self.assertIn("from seo_cycle_core.reports import write_artifacts", source)
        self.assertIn("write_artifacts(", source)

    def test_launch_plan_uses_shared_artifact_writer(self) -> None:
        source = (ROOT / "scripts/launch-plan.py").read_text(encoding="utf-8")

        self.assertIn("from seo_cycle_core.reports import write_artifacts", source)
        self.assertIn("write_artifacts(", source)

    def test_setup_surface_scripts_use_shared_artifact_writer(self) -> None:
        scripts = [
            "spend-guard.py",
            "tool-stack-recommender.py",
            "setup-onboarding.py",
            "growth-roadmap.py",
        ]

        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn("from seo_cycle_core.reports import write_artifacts", source)
                self.assertIn("write_artifacts(", source)

    def test_setup_assistant_scripts_use_shared_artifact_writer(self) -> None:
        scripts = [
            "project-upgrade-assistant.py",
            "access-key-assistant.py",
            "setup-answer-plan.py",
            "setup-gap-audit.py",
        ]

        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn("from seo_cycle_core.reports import write_artifacts", source)
                self.assertIn("write_artifacts(", source)

    def test_remaining_report_scripts_use_shared_artifact_writer(self) -> None:
        scripts = [
            "context-pack.py",
            "project-upgrade-apply.py",
            "automation-recommender.py",
            "stage-template-export.py",
        ]

        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn("from seo_cycle_core.reports import write_artifacts", source)
                self.assertIn("write_artifacts(", source)

    def test_runtime_report_scripts_use_shared_artifact_writer(self) -> None:
        scripts = [
            "usage-ledger.py",
            "orchestrator-panel.py",
            "automation-plan.py",
        ]

        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn("from seo_cycle_core.reports import write_artifacts", source)
                self.assertIn("write_artifacts(", source)

    def test_vnext_report_scripts_use_shared_report_bundle(self) -> None:
        scripts = [
            "vnext_audit_core.py",
            "ai-bot-access-check.py",
        ]

        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn("from seo_cycle_core.reports import write_report_bundle", source)
                self.assertIn("write_report_bundle(", source)

    def test_research_quality_scripts_use_shared_report_writers(self) -> None:
        artifact_scripts = [
            "research-package-quality.py",
            "draft-quality-gate.py",
        ]

        for script in artifact_scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn("from seo_cycle_core.reports import write_artifacts", source)
                self.assertIn("write_artifacts(", source)

        bundle_source = (ROOT / "scripts/page-outline-quality.py").read_text(encoding="utf-8")
        self.assertIn("from seo_cycle_core.reports import write_report_bundle", bundle_source)
        self.assertIn("write_report_bundle(", bundle_source)

    def test_research_repair_scripts_use_shared_artifact_writer(self) -> None:
        scripts = [
            "semantic-core-clean.py",
            "semantic-core-resync.py",
            "entity-map-sync.py",
            "google-nlp-aggregate.py",
            "orphan-url-resolver.py",
            "serp-validation-plan.py",
            "serp-validation-import.py",
            "spoke-opportunity-audit.py",
            "entity-graph-quality.py",
            "research-package-repair.py",
        ]

        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn("from seo_cycle_core.reports import write_artifacts", source)
                self.assertIn("write_artifacts(", source)

    def test_setup_input_scripts_use_shared_report_writers(self) -> None:
        intake_source = (ROOT / "scripts/project-intake-wizard.py").read_text(encoding="utf-8")
        self.assertIn("from seo_cycle_core.reports import write_artifacts", intake_source)
        self.assertIn("write_artifacts(", intake_source)

        writerzen_source = (ROOT / "scripts/writerzen-browser-collect.py").read_text(encoding="utf-8")
        self.assertIn("from seo_cycle_core.reports import write_report_bundle", writerzen_source)
        self.assertIn("write_report_bundle(", writerzen_source)
        self.assertIn("sort_keys=True", writerzen_source)

    def test_project_intake_wizard_uses_shared_config_helpers(self) -> None:
        source = (ROOT / "scripts/project-intake-wizard.py").read_text(encoding="utf-8")

        self.assertIn("from seo_cycle_core.config import find_config, load_yaml, project_root_for, rel_path", source)
        self.assertNotIn("def find_config", source)
        self.assertNotIn("def project_root_for", source)
        self.assertNotIn("def rel_path", source)
        self.assertNotIn("def load_yaml", source)
        self.assertNotIn("CONFIG_SEARCH_PATHS = [", source)

    def test_setup_surface_scripts_use_shared_config_helpers(self) -> None:
        scripts = [
            "setup-blueprint.py",
            "launch-plan.py",
            "spend-guard.py",
            "setup-onboarding.py",
            "growth-roadmap.py",
            "setup-answer-plan.py",
            "setup-gap-audit.py",
        ]

        expected_import = "from seo_cycle_core.config import find_config, load_yaml, policy_path, project_root_for, rel_path"
        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn(expected_import, source)
                self.assertNotIn("def find_config", source)
                self.assertNotIn("def project_root_for", source)
                self.assertNotIn("def rel_path", source)
                self.assertNotIn("def load_yaml", source)
                self.assertNotIn("def policy_path", source)
                self.assertNotIn("CONFIG_SEARCH_PATHS = [", source)

    def test_runtime_control_scripts_use_shared_config_helpers(self) -> None:
        scripts = [
            "automation-plan.py",
            "automation-recommender.py",
            "usage-ledger.py",
            "tool-stack-recommender.py",
        ]

        expected_import = "from seo_cycle_core.config import find_config, load_yaml, policy_path, project_root_for, rel_path"
        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn(expected_import, source)
                self.assertNotIn("def find_config(", source)
                self.assertNotIn("def project_root_for(", source)
                self.assertNotIn("def rel_path(", source)
                self.assertNotIn("def load_yaml(", source)
                self.assertNotIn("def policy_path(", source)
                self.assertNotIn("CONFIG_SEARCH_PATHS = [", source)

    def test_legacy_setup_scripts_use_shared_config_helpers(self) -> None:
        scripts = [
            "governance-report.py",
            "project-profile.py",
            "project-upgrade-assistant.py",
            "access-key-assistant.py",
        ]

        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn("from seo_cycle_core.config import", source)
                self.assertNotIn("def find_config(", source)
                self.assertNotIn("def project_root_for(", source)
                self.assertNotIn("def rel_path(", source)
                self.assertNotIn("def load_yaml(", source)
                self.assertNotIn("def policy_path(", source)
                self.assertNotIn("CONFIG_SEARCH_PATHS = [", source)

    def test_technical_discovery_scripts_use_shared_config_helpers(self) -> None:
        scripts = [
            "validate-config.py",
            "resolve-sources.py",
            "schema-org-build.py",
            "wp-photo-image.py",
        ]

        for script in scripts:
            with self.subTest(script=script):
                source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
                self.assertIn("from seo_cycle_core.config import", source)
                self.assertNotIn("CONFIG_SEARCH_PATHS", source)
                self.assertNotIn("def find_config", source)
                self.assertNotIn("def load_yaml", source)

    def test_obsidian_sync_uses_shared_config_helpers(self) -> None:
        source = (ROOT / "scripts/obsidian-sync.py").read_text(encoding="utf-8")

        self.assertIn("from seo_cycle_core.config import find_config_upwards, load_yaml, project_root_for", source)
        self.assertNotIn("def find_config(", source)
        self.assertNotIn("yaml.safe_load", source)

    def test_json_writer_modules_use_shared_report_helpers(self) -> None:
        repair_source = (ROOT / "scripts/research_package_repair_core.py").read_text(encoding="utf-8")
        wiki_source = (ROOT / "scripts/knowledge/wiki_common.py").read_text(encoding="utf-8")
        wp_obsidian_source = (ROOT / "scripts/knowledge/wp-blog-to-obsidian.py").read_text(encoding="utf-8")

        self.assertIn("from seo_cycle_core.reports import write_json_file as write_json, write_jsonl_file as write_jsonl", repair_source)
        self.assertIn("from seo_cycle_core.reports import write_jsonl_file as write_jsonl, write_sorted_json_file as write_json", wiki_source)
        self.assertIn("from seo_cycle_core.reports import write_jsonl_file as write_jsonl", wp_obsidian_source)
        self.assertNotIn("def write_json(", repair_source)
        self.assertNotIn("def write_jsonl(", repair_source)
        self.assertNotIn("def write_json(", wiki_source)
        self.assertNotIn("def write_jsonl(", wiki_source)
        self.assertNotIn("def write_jsonl(", wp_obsidian_source)

    def test_source_artifacts_write_raw_distillate_latest_and_vector(self) -> None:
        cache_key = stable_cache_key({"topic": "Плита ОСП", "region": "RU", "mode": "manual_browser"})
        vector = make_vector_record(
            provider="perplexity",
            cache_key=cache_key,
            topic="Плита ОСП",
            region="RU",
            mode="manual_browser",
            status="ready",
            summary="OSB page evidence",
            citations=["https://example.com/osb"],
        )
        paths = write_source_artifacts(
            self.tmp,
            "perplexity",
            cache_key,
            raw_payload={"response": "raw stays out of context"},
            distillate_markdown="# Distillate\n",
            distillate_payload={"summary": "OSB page evidence"},
            vector_record=vector,
        )

        self.assertTrue(pathlib.Path(paths["raw"]).exists())
        self.assertTrue(pathlib.Path(paths["distillate_markdown"]).exists())
        self.assertTrue(pathlib.Path(paths["latest_markdown"]).exists())
        cached = read_cached_distillate(self.tmp, "perplexity", cache_key)
        self.assertEqual(cached["summary"], "OSB page evidence")
        vector_lines = pathlib.Path(paths["vector_jsonl"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(vector_lines), 1)
        self.assertEqual(json.loads(vector_lines[0])["provider"], "perplexity")

    def test_run_json_reports_invalid_json_without_raising(self) -> None:
        result = run_json([sys.executable, "-c", "print('not-json')"], self.tmp)
        self.assertEqual(result["error"], "invalid json")
        self.assertEqual(result["exit_code"], 0)

    def test_command_step_helpers_capture_output_and_parse_json(self) -> None:
        step = run_command_step("demo", [sys.executable, "-c", "import json; print(json.dumps({'ok': True}))"], self.tmp)

        self.assertEqual(step["name"], "demo")
        self.assertEqual(step["exit_code"], 0)
        self.assertEqual(json_from_step(step), {"ok": True})
        self.assertEqual(json_from_step({**step, "stdout": "not-json"}), {})
        self.assertEqual(json_from_step({**step, "exit_code": 1}), {})

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
