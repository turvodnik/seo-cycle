#!/usr/bin/env python3
"""Smoke tests for the project journey gate."""

from __future__ import annotations

import json
import os
import pathlib
import re
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
SCRIPTS = ROOT / "scripts"
LAUNCHER = ROOT / "bin" / "seo-cycle"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from seo_cycle_cli import (  # noqa: E402
    COMMANDS,
    EXTRA_COMMANDS,
    _format_stage_line,
    _pick_next_command,
)


def seed_first_four_stages(project_root: pathlib.Path) -> None:
    """Artifacts for stages 1-4 (setup_foundation .. technical_baseline) —
    shared by `ProjectJourneyTest.seed_ready_project()` (which also seeds a
    local research package) and the T-105 `--research-package` test below
    (which deliberately does NOT seed a local package, so only an explicit
    `--research-package <external dir>` can move the journey past stage 5)."""
    setup = project_root / "seo" / "setup"
    vnext = project_root / "seo" / "vnext"
    tech = project_root / "seo" / "technical"
    for directory in (setup, vnext, tech):
        directory.mkdir(parents=True, exist_ok=True)

    (project_root / "seo" / "project-intake.yaml").write_text("project: {}\n", encoding="utf-8")
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


def make_bare_project(case: unittest.TestCase) -> pathlib.Path:
    """A minimal `seo-cycle.yaml` with no artifacts (T-105 status-header
    tests) — the project is at stage 1 (setup_foundation), no snapshot yet."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-status-"))
    case.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
    cfg_path = tmp / "seo-cycle.yaml"
    cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    cfg["project"]["name"] = "Status Header Test"
    cfg["project"]["domain"] = "status-header.test"
    cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return cfg_path


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
        package = root / "seo" / "research-package"
        package.mkdir(parents=True, exist_ok=True)
        seed_first_four_stages(root)

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
        self.assertIn("seo-cycle control-plane --write", report["action_plan"][0]["command"])
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
        self.assertTrue(any("seo-cycle repair" in command for command in report["current_stage"]["next_commands"]))
        self.assertTrue(any("seo-cycle run script serp-validation-plan" in command for command in report["current_stage"]["next_commands"]))
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
        self.assertTrue(any("seo-cycle run script research-package-quality" in command for command in report["current_stage"]["next_commands"]))

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
        self.assertTrue(any("seo-cycle run script page-outline-quality" in command for command in report["current_stage"]["next_commands"]))

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
        self.assertTrue(any("seo-cycle run script page-outline-v3" in command for command in report["current_stage"]["next_commands"]))
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

    def seed_passing_v3_brief(self, package: pathlib.Path) -> None:
        outline_dir = package / "page-outlines-v3"
        copywriter_dir = package / "copywriter-ready"
        outline_dir.mkdir(exist_ok=True)
        copywriter_dir.mkdir(exist_ok=True)
        (outline_dir / "sample.json").write_text(
            json.dumps(
                {
                    "outline_id": "page_outline_v3",
                    "version": "v3",
                    "page": {"url": "/sample/", "primary_keyword": "sample keyword"},
                }
            ),
            encoding="utf-8",
        )
        (copywriter_dir / "sample.md").write_text("# Copywriter Ready Brief\n", encoding="utf-8")
        (package / "page-outline-quality.json").write_text(
            json.dumps(
                {
                    "status": "pass",
                    "outline_version": "v3",
                    "ten_point_score": 10,
                    "counts": {"critical_findings": 0, "high_findings": 0},
                    "findings": [],
                }
            ),
            encoding="utf-8",
        )

    def test_content_draft_gate_blocks_after_v3_until_draft_and_quality_pass(self) -> None:
        cfg_path = self.make_project()
        package = self.seed_ready_project(cfg_path)
        self.seed_passing_v3_brief(package)

        report = self.run_journey(cfg_path)

        self.assertEqual(report["status"], "needs_work")
        self.assertEqual(report["current_stage"]["id"], "content_draft_gate")
        self.assertIn("seo/research-package/drafts/*.md", report["missing_for_next_step"])
        self.assertTrue(any("seo-cycle ledger check --service neuronwriter" in command for command in report["current_stage"]["next_commands"]))
        self.assertTrue(any("seo-cycle loop draft" in command for command in report["current_stage"]["next_commands"]))

    def test_content_draft_gate_requires_draft_quality_report(self) -> None:
        cfg_path = self.make_project()
        package = self.seed_ready_project(cfg_path)
        self.seed_passing_v3_brief(package)
        drafts = package / "drafts"
        drafts.mkdir()
        (drafts / "sample.md").write_text("# Sample\n\nDraft text.\n", encoding="utf-8")

        report = self.run_journey(cfg_path)

        self.assertEqual(report["status"], "needs_work")
        self.assertEqual(report["current_stage"]["id"], "content_draft_gate")
        self.assertTrue(any("draft-quality-gate.json" in item for item in report["missing_for_next_step"]))

    def test_content_draft_gate_blocks_error_findings_before_implementation(self) -> None:
        cfg_path = self.make_project()
        package = self.seed_ready_project(cfg_path)
        self.seed_passing_v3_brief(package)
        drafts = package / "drafts"
        drafts.mkdir()
        draft = drafts / "sample.md"
        draft.write_text("# Sample\n\nIn my years working with clients...\n", encoding="utf-8")
        draft.with_suffix(".draft-quality-gate.json").write_text(
            json.dumps(
                {
                    "script": "draft-quality-gate",
                    "summary": {"findings": 1},
                    "findings": [
                        {
                            "id": "unsafe_first_person_expertise",
                            "severity": "error",
                            "message": "Draft uses unsupported first-person claims.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        report = self.run_journey(cfg_path)

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["current_stage"]["id"], "content_draft_gate")
        self.assertTrue(any("unsafe_first_person_expertise" in item for item in report["missing_for_next_step"]))

    def test_content_draft_gate_passes_to_monitoring_after_clean_draft_gate(self) -> None:
        cfg_path = self.make_project()
        package = self.seed_ready_project(cfg_path)
        self.seed_passing_v3_brief(package)
        drafts = package / "drafts"
        drafts.mkdir()
        draft = drafts / "sample.md"
        draft.write_text("# Sample\n\nClean draft.\n", encoding="utf-8")
        draft.with_suffix(".draft-quality-gate.json").write_text(
            json.dumps({"script": "draft-quality-gate", "summary": {"findings": 0}, "findings": []}),
            encoding="utf-8",
        )

        report = self.run_journey(cfg_path)

        draft_stage = next(stage for stage in report["stages"] if stage["id"] == "content_draft_gate")
        self.assertEqual(draft_stage["status"], "done")
        self.assertEqual(report["current_stage"]["id"], "monitoring_iteration")


@unittest.skipIf(yaml is None, "PyYAML is required")
class StageTitlesAreRussianTest(unittest.TestCase):
    """T-105 acceptance criterion 2/3: stage titles/objectives are Russian
    text (data field, used both in `--format json` and in the printed
    markdown) — the machine-facing `id` stays English on purpose."""

    ALLOWED_LATIN_TOKENS = ("NeuronWriter",)

    def test_titles_have_no_stray_latin_characters(self) -> None:
        cfg_path = make_bare_project(self)
        proc = subprocess.run(
            [sys.executable, str(JOURNEY), str(cfg_path), "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        stages = report["stages"]
        self.assertEqual(len(stages), 12)
        for stage in stages:
            title = stage["title"]
            stripped = title
            for token in self.ALLOWED_LATIN_TOKENS:
                stripped = stripped.replace(token, "")
            self.assertIsNone(
                re.search(r"[A-Za-z]", stripped),
                f"stage {stage['id']!r} title still has Latin text: {title!r}",
            )

    def test_default_markdown_output_has_no_old_english_stage_titles(self) -> None:
        # Acceptance criterion 2 (grep-based change check): the two titles
        # named in the ticket must not appear in the default `md` output.
        cfg_path = make_bare_project(self)
        proc = subprocess.run(
            [sys.executable, str(JOURNEY), str(cfg_path)],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        for leftover in ("Setup foundation", "Technical baseline"):
            self.assertNotIn(leftover, proc.stdout)


@unittest.skipIf(yaml is None, "PyYAML is required")
class StatusHeaderTest(unittest.TestCase):
    """T-105: `seo-cycle status` prints a three-line Russian header —
    snapshot freshness, current journey stage, and the single next command —
    before the previous detailed output (unchanged below it)."""

    def run_status(self, cfg_path: pathlib.Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(LAUNCHER), "status"],
            cwd=cfg_path.parent,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_header_is_the_first_three_lines(self) -> None:
        cfg_path = make_bare_project(self)
        proc = self.run_status(cfg_path)
        lines = proc.stdout.splitlines()
        self.assertGreaterEqual(len(lines), 3, proc.stdout)
        self.assertTrue(lines[0].startswith("Срез:"), lines[:5])
        self.assertTrue(lines[1].startswith("Стадия:"), lines[:5])
        self.assertTrue(lines[2].startswith("Дальше:"), lines[:5])

    def test_next_command_exists_in_cli_commands(self) -> None:
        cfg_path = make_bare_project(self)
        proc = self.run_status(cfg_path)
        next_line = next(line for line in proc.stdout.splitlines() if line.startswith("Дальше:"))
        command = next_line.removeprefix("Дальше:").strip()
        self.assertTrue(command.startswith("seo-cycle "), command)
        name = command.split()[1]
        known = set(COMMANDS) | {item[0] for item in EXTRA_COMMANDS}
        self.assertIn(name, known, f"{name!r} from {command!r} is not a known seo-cycle command")

    def test_freshness_and_stage_stay_on_separate_lines(self) -> None:
        # Criterion 2: snapshot freshness and setup-stage readiness answer
        # different questions and must not be merged into one assessment.
        cfg_path = make_bare_project(self)
        proc = self.run_status(cfg_path)
        lines = proc.stdout.splitlines()
        self.assertNotIn("Стадия", lines[0])
        self.assertNotIn("Срез", lines[1])

    def test_stage_one_header_lines_match_exactly(self) -> None:
        # T-105 review round 1, 🟡-1: an exact `assertEqual` on stage 1 (not
        # just "starts with") — a mutation that always falls back (M5) or
        # swaps order/total (M7) changes this line's content, not just its
        # prefix.
        cfg_path = make_bare_project(self)
        proc = self.run_status(cfg_path)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[1], "Стадия: Основа проекта (1 из 12)")
        self.assertEqual(lines[2], "Дальше: seo-cycle control-plane --write")

    def test_research_package_flag_reaches_the_header_not_just_the_body(self) -> None:
        # T-105 review round 1, 🟡-2: `--research-package <path outside the
        # project>` used to reach `project-journey.py`'s own argparse (the
        # body, via the delegated subprocess) but not the in-process header
        # call, which kept autodetecting (and failing to find anything
        # under the project root) — one `status` output naming two
        # different current stages. `package_state()` only checks that the
        # six required files exist, so placeholder content is enough to
        # move the package past `research_architecture` (order 5) to
        # `research_quality_gate` (order 6, no quality.json yet) — a stage
        # the plain-autodetect header would never reach.
        cfg_path = make_bare_project(self)
        seed_first_four_stages(cfg_path.parent)
        external = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-external-package-"))
        self.addCleanup(lambda: shutil.rmtree(external, ignore_errors=True))
        for name in (
            "semantic-core.csv",
            "content-plan.csv",
            "final-clusters.md",
            "semantic-architecture-final.json",
            "entity-map.md",
            "entity-map.yaml",
        ):
            (external / name).write_text("placeholder\n", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), "status", "--research-package", str(external)],
            cwd=cfg_path.parent,
            text=True,
            capture_output=True,
            check=False,
        )
        lines = proc.stdout.splitlines()
        stage_line = next(line for line in lines if line.startswith("Стадия:"))
        body_line = next(line for line in lines if line.startswith("- Current stage:"))
        header_title = stage_line.removeprefix("Стадия: ").rsplit(" (", 1)[0]
        body_title = body_line.rsplit("` ", 1)[-1].strip()
        self.assertEqual(
            header_title, body_title, f"header and body disagree: {stage_line!r} vs {body_line!r}"
        )
        # Negative control on the assertion itself: a fresh project (no
        # --research-package) starts at setup_foundation, not the quality
        # gate — if this failed too, the test would be vacuously true.
        self.assertNotEqual(header_title, "Основа проекта")


class HeaderSelectorUnitTest(unittest.TestCase):
    """T-105 review round 1, 🟡-1: call `seo_cycle_cli`'s real
    `_pick_next_command()`/`_format_stage_line()` against every stage of one
    report, instead of re-implementing their rule inside the test.
    `test_next_command_exists_in_cli_commands` (`StatusHeaderTest`) only
    ever observes stage 1 (a fresh project starts at `setup_foundation`);
    `research_architecture` (order 5) is the one stage where neither
    `next_commands` entry is `seo-cycle `-shaped, so the fallback is only
    exercised there."""

    def _report(self) -> dict:
        cfg_path = make_bare_project(self)
        proc = subprocess.run(
            [sys.executable, str(JOURNEY), str(cfg_path), "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_pick_next_command_is_a_known_cli_command_or_the_documented_fallback(self) -> None:
        report = self._report()
        known = set(COMMANDS) | {item[0] for item in EXTRA_COMMANDS}
        stage_by_id = {stage["id"]: stage for stage in report["stages"]}

        setup = stage_by_id["setup_foundation"]
        self.assertEqual(_pick_next_command(setup, []), "seo-cycle control-plane --write")

        research = stage_by_id["research_architecture"]
        self.assertTrue(all(not c.startswith("seo-cycle ") for c in research["next_commands"]), research["next_commands"])
        self.assertEqual(_pick_next_command(research, []), "seo-cycle journey")

        for stage in report["stages"]:
            command = _pick_next_command(stage, [])
            name = command.split()[1]
            self.assertIn(name, known, f"stage {stage['id']!r}: {name!r} from {command!r} is unknown")

    def test_format_stage_line_uses_order_not_total(self) -> None:
        report = self._report()
        total = len(report["stages"])
        research = next(stage for stage in report["stages"] if stage["id"] == "research_architecture")
        self.assertNotEqual(research["order"], total)  # otherwise an order/total swap wouldn't show here
        self.assertEqual(
            _format_stage_line(research, total),
            f"Стадия: {research['title']} ({research['order']} из {total})",
        )
        setup = next(stage for stage in report["stages"] if stage["id"] == "setup_foundation")
        self.assertEqual(_format_stage_line(setup, total), f"Стадия: Основа проекта (1 из {total})")


if __name__ == "__main__":
    unittest.main(verbosity=2)
