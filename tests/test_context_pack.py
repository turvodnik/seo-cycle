#!/usr/bin/env python3
"""Smoke tests for the low-token context pack handoff."""

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
SETUP_CONTROL = ROOT / "scripts" / "setup-control-plane.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class ContextPackTest(unittest.TestCase):
    def make_project(self, *, country: str, project_type: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-context-pack-"))
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
            [sys.executable, str(SPEND), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(AUTOMATION), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(ROADMAP), str(cfg_path), "--write", "--format", "json"],
            [sys.executable, str(LAUNCH), str(cfg_path), "--write", "--format", "json"],
            [
                sys.executable,
                str(TASK_ROUTER),
                str(cfg_path),
                "--task",
                "аудит индексации, robots и Bricks preview",
                "--write",
            ],
        ):
            subprocess.run(command, cwd=tmp, check=True, text=True, capture_output=True)
        return cfg_path

    def run_context_pack(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [
                sys.executable,
                str(CONTEXT_PACK),
                str(cfg_path),
                "--task",
                "аудит индексации, robots и Bricks preview",
                "--write",
                "--format",
                "json",
            ],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_ru_ecommerce_context_pack_is_compact_and_guarded(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        report = self.run_context_pack(cfg_path)

        self.assertEqual(report["task"]["task_type"], "technical_audit")
        self.assertFalse(report["context_contract"]["raw_data_in_context"])
        self.assertLessEqual(report["rendered_chars"], report["context_contract"]["max_pack_chars"])
        self.assertIn("seo/setup/latest-task-route.md", report["read_order"])
        self.assertIn("seo/setup/setup-blueprint.md", report["read_order"])
        self.assertIn("seo/setup/upgrade-assistant.md", report["read_order"])
        self.assertIn("seo/setup/access-key-assistant.md", report["read_order"])
        self.assertIn("seo/setup/setup-gap-audit.md", report["read_order"])
        self.assertIn("seo/setup/setup-questionnaire.md", report["read_order"])
        self.assertIn("seo/setup/setup-answer-plan.md", report["read_order"])
        self.assertIn("seo/setup/launch-plan.md", report["read_order"])
        self.assertIn("seo/setup/spend-guard.md", report["read_order"])
        self.assertIn("raw API JSON", report["do_not_load_raw"])
        self.assertIn("context_manifest", report)
        self.assertIn("read_first", report["context_manifest"])
        self.assertIn("blocked_raw_artifacts", report["context_manifest"])
        self.assertIn("source_caps", report["context_manifest"])
        self.assertLessEqual(report["context_manifest"]["source_caps"]["distillate_max_lines"], report["context_contract"]["distillate_max_lines"])
        self.assertIn("seo/setup/context-pack.json", report["context_manifest"]["outputs"]["json"])
        self.assertIn("seo/setup/tool-stack-report.json", report["excluded_raw_artifacts"])
        self.assertIn("seo/setup/upgrade-assistant.json", report["excluded_raw_artifacts"])
        self.assertIn("seo/setup/access-key-assistant.json", report["excluded_raw_artifacts"])
        self.assertIn("seo/setup/context-pack.md", report["outputs"]["markdown"])
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "context-pack.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "context-pack.json").exists())
        self.assertNotIn("=", "\n".join(report["human_secret_env_names"]))

    def test_setup_control_plane_writes_context_pack(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        subprocess.run(
            [
                sys.executable,
                str(SETUP_CONTROL),
                str(cfg_path),
                "--write",
                "--task",
                "аудит индексации, robots и Bricks preview",
            ],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        setup = json.loads((cfg_path.parent / "seo" / "setup" / "setup-control-plane.json").read_text(encoding="utf-8"))
        self.assertGreater(setup["context_pack"]["rendered_chars"], 0)
        self.assertGreater(setup["setup_blueprint"]["rendered_chars"], 0)
        self.assertGreaterEqual(setup["upgrade_assistant"]["summary"]["features"], 1)
        self.assertGreaterEqual(setup["access_key_assistant"]["summary"]["tasks"], 1)
        self.assertGreater(len(setup["setup_blueprint"]["decision_matrix"]), 0)
        self.assertLess(setup["setup_gap_audit"]["score"], 100)
        self.assertGreater(setup["setup_gap_audit"]["questionnaire"]["row_count"], 0)
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "setup-gap-audit.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "setup-blueprint.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "setup-matrix.csv").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "upgrade-assistant.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "upgrade-questionnaire.csv").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "access-key-assistant.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "access-key-assistant.csv").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "setup-questionnaire.csv").exists())
        self.assertTrue(any("seo/setup/context-pack.md" in action for action in setup["next_actions"]))
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "latest-context-pack.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
