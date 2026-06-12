#!/usr/bin/env python3
"""Smoke tests for project upgrade and access-key assistants."""

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
UPGRADE = ROOT / "scripts" / "project-upgrade-assistant.py"
UPGRADE_APPLY = ROOT / "scripts" / "project-upgrade-apply.py"
ACCESS = ROOT / "scripts" / "access-key-assistant.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class UpgradeAccessAssistantsTest(unittest.TestCase):
    def make_project(self) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-upgrade-access-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg_path = tmp / "seo-cycle.yaml"
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = "RU ecommerce"
        cfg["project"]["domain"] = "example.test"
        cfg["project_type"] = "ecommerce"
        cfg["locale"]["country"] = "RU"
        cfg["locale"]["language"] = "ru"
        cfg["locale"]["locale_iso"] = "ru-RU"
        cfg["locale"]["google_gl"] = "ru"
        cfg["locale"]["google_hl"] = "ru"
        cfg["region_profile"] = "ru"
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return cfg_path

    def test_upgrade_assistant_flags_missing_new_surface_without_editing_config(self) -> None:
        cfg_path = self.make_project()
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        for key in (
            "upgrade_assistant",
            "upgrade_assistant_json",
            "upgrade_questionnaire_csv",
            "latest_upgrade_assistant",
            "access_key_assistant",
            "access_key_assistant_json",
            "access_key_assistant_csv",
            "latest_access_key_assistant",
        ):
            cfg["policy_files"].pop(key, None)
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        before = cfg_path.read_text(encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(UPGRADE), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        feature_ids = {row["id"]: row for row in report["features"]}

        self.assertGreater(report["summary"]["review_needed"], 0)
        self.assertEqual(feature_ids["access_key_assistant"]["status"], "review_needed")
        self.assertIn("access_key_assistant", feature_ids["access_key_assistant"]["missing_policy_keys"])
        self.assertEqual(before, cfg_path.read_text(encoding="utf-8"))
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "upgrade-assistant.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "upgrade-questionnaire.csv").exists())

    def test_upgrade_apply_adds_reviewed_policy_keys_with_backup(self) -> None:
        cfg_path = self.make_project()
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        for key in (
            "project_journey_report",
            "project_journey_json",
            "project_journey_checklist",
            "latest_project_journey",
            "latest_project_journey_json",
            "project_upgrade_apply_report",
            "project_upgrade_apply_json",
            "project_upgrade_apply_csv",
            "latest_project_upgrade_apply",
            "latest_project_upgrade_apply_json",
        ):
            cfg["policy_files"].pop(key, None)
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        before = cfg_path.read_text(encoding="utf-8")

        subprocess.run(
            [sys.executable, str(UPGRADE), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        dry_run = subprocess.run(
            [sys.executable, str(UPGRADE_APPLY), str(cfg_path), "--write", "--use-defaults", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        dry_report = json.loads(dry_run.stdout)
        self.assertGreater(dry_report["summary"]["planned_changes"], 0)
        self.assertEqual(before, cfg_path.read_text(encoding="utf-8"))

        applied = subprocess.run(
            [sys.executable, str(UPGRADE_APPLY), str(cfg_path), "--write", "--apply", "--use-defaults", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(applied.stdout)
        updated = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

        self.assertGreater(report["summary"]["applied_changes"], 0)
        self.assertTrue(pathlib.Path(report["backup"]).exists())
        self.assertIn("project_journey_report", updated["policy_files"])
        self.assertIn("project_upgrade_apply_report", updated["policy_files"])
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "project-upgrade-apply.md").exists())
        self.assertNotIn("=", "\n".join(report["planned_policy_files"][0].values()))

    def test_access_key_assistant_is_project_specific_and_secret_free(self) -> None:
        cfg_path = self.make_project()
        setup_dir = cfg_path.parent / "seo" / "setup"
        setup_dir.mkdir(parents=True, exist_ok=True)
        (setup_dir / "tool-stack-report.json").write_text(
            json.dumps(
                {
                    "decisions": {
                        "google_search_console": {"decision": "enabled", "approval_gates": []},
                        "yandex_webmaster": {"decision": "enabled", "approval_gates": []},
                        "bing_webmaster": {"decision": "enabled", "approval_gates": []},
                        "neuronwriter": {"decision": "approval_required", "approval_gates": ["paid_api_run"]},
                        "xmlriver": {"decision": "approval_required", "approval_gates": ["paid_api_run"]},
                        "yandex_metrika": {"decision": "disabled", "approval_gates": []},
                        "gemini": {"decision": "disabled", "approval_gates": []},
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (cfg_path.parent / ".env").write_text(
            "\n".join(
                [
                    "SEO_RUNTIME=claude",
                    "SEO_SEARCH_RUNTIME=codex_external",
                    "YANDEX_OAUTH_TOKEN=placeholder-present-value",
                    "YANDEX_USER_ID=123456",
                    "BING_SITE_URL=https://example.test/",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        proc = subprocess.run(
            [sys.executable, str(ACCESS), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        task_ids = {task["id"]: task for task in report["tasks"]}
        rendered = (cfg_path.parent / "seo" / "setup" / "access-key-assistant.md").read_text(encoding="utf-8")

        self.assertEqual(report["runtime_contract"]["runtime"], "claude")
        self.assertEqual(report["runtime_contract"]["search_runtime"], "codex_external")
        self.assertIn("google_service_account", task_ids)
        self.assertIn("google_search_console", task_ids)
        self.assertIn("yandex_webmaster", task_ids)
        self.assertNotIn("yandex_metrika", task_ids)
        self.assertIn("bing_webmaster", task_ids)
        self.assertIn("neuronwriter", task_ids)
        self.assertIn("xmlriver", task_ids)
        self.assertEqual(task_ids["neuronwriter"]["missing_env"], ["NEURON_API_KEY"])
        self.assertEqual(task_ids["xmlriver"]["missing_env"], ["XMLRIVER_USER_ID", "XMLRIVER_API_KEY"])
        self.assertNotIn("placeholder-present-value", proc.stdout)
        self.assertNotIn("placeholder-present-value", rendered)
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "access-key-assistant.csv").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
