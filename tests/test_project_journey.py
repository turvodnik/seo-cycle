#!/usr/bin/env python3
"""Smoke tests for the project journey gate."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "project.template.yaml"
JOURNEY = ROOT / "scripts" / "project-journey.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class ProjectJourneyTest(unittest.TestCase):
    def make_project(self) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-journey-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg_path = tmp / "seo-cycle.yaml"
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = "Journey Test"
        cfg["project"]["domain"] = "journey.test"
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return cfg_path

    def run_journey(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(JOURNEY), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def seed_ready_project(self, cfg_path: pathlib.Path, *, research_quality: dict | None = None) -> pathlib.Path:
        root = cfg_path.parent
        setup = root / "seo" / "setup"
        vnext = root / "seo" / "vnext"
        tech = root / "seo" / "technical"
        package = root / "seo" / "research-package"
        for directory in (setup, vnext, tech, package):
            directory.mkdir(parents=True, exist_ok=True)

        (root / "seo" / "project-intake.yaml").write_text("project: {}\n", encoding="utf-8")
        (setup / "setup-blueprint.md").write_text("# blueprint\n", encoding="utf-8")
        (setup / "setup-gap-audit.json").write_text(json.dumps({"summary": {"missing": 0}, "score": 100}), encoding="utf-8")
        (setup / "setup-control-plane.md").write_text("# control\n", encoding="utf-8")
        (setup / "tool-stack-report.md").write_text("# tools\n", encoding="utf-8")
        (setup / "access-key-assistant.md").write_text("# access\n", encoding="utf-8")
        (setup / "access-key-assistant.json").write_text(json.dumps({"summary": {"tasks": 0, "approval_required": 0}}), encoding="utf-8")
        (setup / "spend-guard.md").write_text("# spend\n", encoding="utf-8")
        (setup / "launch-plan.md").write_text("# launch\n", encoding="utf-8")
        (setup / "latest-launch-plan.json").write_text(json.dumps({"approval_gates": []}), encoding="utf-8")
        (setup / "perplexity-health.md").write_text("# perplexity\n", encoding="utf-8")
        (setup / "perplexity-health.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")
        (setup / "notebooklm-health.md").write_text("# notebook\n", encoding="utf-8")
        (setup / "notebooklm-health.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")
        (vnext / "expert-source-pack.md").write_text("# sources\n", encoding="utf-8")
        (tech / "technical-site-audit.md").write_text("# technical\n", encoding="utf-8")
        (tech / "link-audit.md").write_text("# links\n", encoding="utf-8")
        (tech / "redirect-map-audit.md").write_text("# redirects\n", encoding="utf-8")

        for name in (
            "semantic-core.csv",
            "content-plan.csv",
            "final-clusters.md",
            "semantic-architecture-final.json",
            "entity-map.md",
            "entity-map.yaml",
        ):
            (package / name).write_text("{}\n" if name.endswith(".json") else "ok\n", encoding="utf-8")
        (package / "research-package-quality.json").write_text(
            json.dumps(
                research_quality
                or {
                    "status": "pass",
                    "ten_point_score": 10,
                    "counts": {"critical_findings": 0, "high_findings": 0},
                    "findings": [],
                }
            ),
            encoding="utf-8",
        )
        return package

    def test_new_project_starts_at_setup_foundation_with_next_command(self) -> None:
        cfg_path = self.make_project()
        report = self.run_journey(cfg_path)

        self.assertEqual(report["status"], "needs_work")
        self.assertEqual(report["current_stage"]["id"], "setup_foundation")
        self.assertIn("setup-control-plane.py --write", report["action_plan"][0]["command"])
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "project-journey.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "project-journey-checklist.csv").exists())

    def test_failed_research_quality_routes_to_repair_layer_before_deep_briefs(self) -> None:
        cfg_path = self.make_project()
        self.seed_ready_project(
            cfg_path,
            research_quality={
                "status": "fail",
                "ten_point_score": 5.2,
                "counts": {"critical_findings": 1, "high_findings": 0},
                "findings": [
                    {
                        "id": "serp_validation_incomplete",
                        "severity": "critical",
                        "title": "SERP validation is empty.",
                    }
                ],
            },
        )

        report = self.run_journey(cfg_path)

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["current_stage"]["id"], "research_package_repair")
        self.assertTrue(any("serp_validation_incomplete" in item for item in report["missing_for_next_step"]))
        self.assertTrue(any("research-package-repair.py" in command for command in report["current_stage"]["next_commands"]))
        self.assertTrue(any("serp-validation-plan.py" in command for command in report["current_stage"]["next_commands"]))
        deep = next(stage for stage in report["stages"] if stage["id"] == "deep_page_briefs")
        self.assertEqual(deep["status"], "pending")

    def test_repair_newer_than_quality_requires_quality_rerun(self) -> None:
        cfg_path = self.make_project()
        package = self.seed_ready_project(cfg_path)
        quality_path = package / "research-package-quality.json"
        repair_path = package / "research-package-repair.json"
        repair_path.write_text(json.dumps({"summary": {"failed_steps": 0}}), encoding="utf-8")
        now = time.time()
        os.utime(quality_path, (now, now))
        os.utime(repair_path, (now + 10, now + 10))

        report = self.run_journey(cfg_path)

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["current_stage"]["id"], "research_quality_gate")
        self.assertTrue(any("rerun" in item.lower() for item in report["missing_for_next_step"]))
        self.assertTrue(any("research-package-quality.py" in command for command in report["current_stage"]["next_commands"]))

    def test_page_outline_quality_is_required_before_implementation(self) -> None:
        cfg_path = self.make_project()
        package = self.seed_ready_project(cfg_path)
        outline_dir = package / "page-outlines-v2"
        outline_dir.mkdir()
        (outline_dir / "sample.json").write_text(json.dumps({"outline_id": "page_outline_v2"}), encoding="utf-8")

        report = self.run_journey(cfg_path)

        self.assertEqual(report["status"], "needs_work")
        self.assertEqual(report["current_stage"]["id"], "deep_page_briefs")
        self.assertIn("seo/research-package/page-outline-quality.json", report["missing_for_next_step"])
        self.assertTrue(any("page-outline-quality.py" in command for command in report["current_stage"]["next_commands"]))

        (package / "page-outline-quality.json").write_text(
            json.dumps(
                {
                    "status": "fail",
                    "ten_point_score": 6.4,
                    "counts": {"critical_findings": 1, "high_findings": 2},
                    "findings": [
                        {
                            "id": "unsafe_first_person_expertise",
                            "severity": "critical",
                            "title": "Outline asks for fake expertise.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        blocked = self.run_journey(cfg_path)

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["current_stage"]["id"], "deep_page_briefs")
        self.assertTrue(any("unsafe_first_person_expertise" in item for item in blocked["missing_for_next_step"]))

    def test_v3_copywriter_briefs_are_required_before_draft_stage(self) -> None:
        cfg_path = self.make_project()
        package = self.seed_ready_project(cfg_path)
        outline_dir = package / "page-outlines-v3"
        outline_dir.mkdir()
        (outline_dir / "sample.json").write_text(
            json.dumps({"outline_id": "page_outline_v3", "version": "v3"}),
            encoding="utf-8",
        )

        report = self.run_journey(cfg_path)

        self.assertEqual(report["status"], "needs_work")
        self.assertEqual(report["current_stage"]["id"], "deep_page_briefs_v3")
        self.assertIn("seo/research-package/page-outline-quality.json", report["missing_for_next_step"])
        self.assertTrue(any("page-outline-v3.py" in command for command in report["current_stage"]["next_commands"]))
        self.assertTrue(any("--version v3" in command for command in report["current_stage"]["next_commands"]))

        (package / "page-outline-quality.json").write_text(
            json.dumps(
                {
                    "status": "fail",
                    "outline_version": "v3",
                    "ten_point_score": 7.0,
                    "counts": {"critical_findings": 1, "high_findings": 1},
                    "findings": [
                        {
                            "id": "tool_first_order_violation",
                            "severity": "critical",
                            "title": "Tool/app page does not put tool UX first.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        blocked = self.run_journey(cfg_path)

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["current_stage"]["id"], "deep_page_briefs_v3")
        self.assertTrue(any("tool_first_order_violation" in item for item in blocked["missing_for_next_step"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
