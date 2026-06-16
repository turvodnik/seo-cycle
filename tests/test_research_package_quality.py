#!/usr/bin/env python3
"""Regression tests for research package quality gates and page-outline v2."""

from __future__ import annotations

import csv
import importlib.util
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
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_script(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QUALITY = load_script(SCRIPTS / "research-package-quality.py", "research_package_quality")
OUTLINE = load_script(SCRIPTS / "page-outline-v2.py", "page_outline_v2")
OUTLINE_QUALITY = load_script(SCRIPTS / "page-outline-quality.py", "page_outline_quality")
OUTLINE_V3_PATH = SCRIPTS / "page-outline-v3.py"


class ResearchPackageQualityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-research-package-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.package = self.tmp / "package"
        self.package.mkdir()
        self.write_package()

    def write_csv(self, name: str, rows: list[dict[str, str]]) -> None:
        path = self.package / name
        fields = list(rows[0]) if rows else ["keyword"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def write_package(self) -> None:
        architecture = {
            "metadata": {
                "sources": {
                    "dataforseo_serp_validation_keywords": ["virtual hair color try on", "face shape detector"],
                    "google_nlp": {
                        "status": "ok",
                        "entities": [
                            {"name": "hair color", "salience": 0.1},
                            {"name": "hair color", "salience": 0.05},
                            {"name": "hair color", "salience": 0.02},
                        ],
                    },
                }
            },
            "clusters": [
                {
                    "id": "virtual_hair_color_try_on",
                    "name": "Virtual Hair Color Try-On",
                    "primary_keyword": "virtual hair color try on",
                    "secondary_keywords": ["virtual hair color try on free", "hair color simulator"],
                    "intent": "Do",
                    "funnel_stage": "Consideration",
                    "page_type": "Tool",
                    "content_format": "Interactive virtual try-on tool, supporting guide",
                    "suggested_url": "/tools/virtual-hair-color-try-on/",
                    "priority": "P1",
                    "mvp": True,
                    "internal_links": ["/hair-color/by-skin-tone/", "/guides/face-shapes/"],
                },
                {
                    "id": "face_shape_detector",
                    "name": "Face Shape Detector",
                    "primary_keyword": "face shape detector",
                    "secondary_keywords": ["what is my face shape"],
                    "intent": "Do",
                    "funnel_stage": "Consideration",
                    "page_type": "Tool",
                    "content_format": "Interactive face shape detector",
                    "suggested_url": "/tools/face-shape-detector/",
                    "priority": "P1",
                    "mvp": True,
                    "internal_links": ["/hairstyles/by-face-shape/"],
                },
            ],
            "dataforseo_serp_validation": {
                "virtual hair color try on": {"features": ["organic"], "top_urls": ["https://example.com/tool"]},
                "face shape detector": {"features": [], "top_urls": []},
            },
        }
        (self.package / "semantic-architecture-final.json").write_text(json.dumps(architecture), encoding="utf-8")
        self.write_csv(
            "semantic-core.csv",
            [
                {
                    "keyword": "virtual hair color try on",
                    "dataforseo_serp_features": "organic|ai_overview",
                    "base_cluster": "virtual_hair_color_try_on",
                    "suggested_url": "/tools/virtual-hair-color-try-on/",
                    "impressions": "1200",
                    "clicks": "40",
                    "volume": "9900",
                    "priority_score": "91.5",
                },
                {
                    "keyword": "hair color simulator",
                    "dataforseo_serp_features": "organic",
                    "base_cluster": "virtual_hair_color_try_on",
                    "suggested_url": "/tools/virtual-hair-color-try-on/",
                    "impressions": "400",
                    "clicks": "12",
                    "volume": "2400",
                    "priority_score": "77",
                },
                {
                    "keyword": "create a hairstyle analysis graphic using this portrait, show side-by-side hairstyles comparisons",
                    "dataforseo_serp_features": "",
                    "base_cluster": "virtual_hair_color_try_on",
                    "suggested_url": "/hair-color/old-url/",
                    "impressions": "3",
                    "clicks": "0",
                    "volume": "0",
                    "priority_score": "0",
                },
            ],
        )
        self.write_csv(
            "content-plan.csv",
            [
                {
                    "priority": "P1",
                    "mvp": "True",
                    "url": "/tools/virtual-hair-color-try-on/",
                    "page_title": "Virtual Hair Color Try-On",
                    "primary_keyword": "virtual hair color try on",
                    "page_type": "Tool",
                    "intent": "Do",
                    "funnel_stage": "Consideration",
                    "content_format": "Interactive virtual try-on tool",
                    "supporting_keywords": "hair color simulator",
                    "internal_links": "/hair-color/by-skin-tone/",
                    "source_cluster": "virtual_hair_color_try_on",
                }
            ],
        )
        self.write_csv(
            "dataforseo-keyword-expansion.csv",
            [
                {
                    "keyword": "haircuts for oval face shape",
                    "source": "dataforseo",
                    "seed": "face shape detector",
                    "volume": "18100",
                    "cpc": "0.51",
                    "competition": "0.01",
                    "serp_features": "organic|ai_overview",
                    "status": "ok",
                    "note": "",
                }
            ],
        )
        (self.package / "final-clusters.md").write_text("# Final clusters\n", encoding="utf-8")
        duplicate = "# MVP Page Briefs\n\n### SEO Requirements\nSame generic block.\n"
        (self.package / "mvp-page-briefs.md").write_text(duplicate, encoding="utf-8")
        (self.package / "page-briefs.md").write_text(duplicate, encoding="utf-8")
        (self.package / "technical-spec.md").write_text("# Technical spec\nNo AI visibility requirements.\n", encoding="utf-8")
        (self.package / "site-structure.md").write_text("- Child pages: `/guides/face-shapes/`\n", encoding="utf-8")
        entity_yaml = {
            "entities": [
                {
                    "id": "hair_colors",
                    "name": "Hair Colors",
                    "coverage_priority": "P1",
                    "attributes": ["Blonde", "Brunette", "Copper"],
                    "target_clusters": ["virtual_hair_color_try_on"],
                }
            ]
        }
        if yaml is not None:
            (self.package / "entity-map.yaml").write_text(yaml.safe_dump(entity_yaml, sort_keys=False), encoding="utf-8")
        else:
            (self.package / "entity-map.yaml").write_text("entities: []\n", encoding="utf-8")
        (self.package / "entity-map.md").write_text("### Hair Colors\n\n- Attributes: Blonde, Brunette\n", encoding="utf-8")

    def test_quality_gate_flags_external_audit_failure_modes(self) -> None:
        report = QUALITY.audit_package(self.package)
        ids = {finding["id"] for finding in report["findings"]}

        self.assertEqual(report["status"], "fail")
        self.assertIn("serp_validation_incomplete", ids)
        self.assertIn("semantic_core_url_drift", ids)
        self.assertIn("dirty_semantic_core_queries", ids)
        self.assertIn("duplicate_page_briefs", ids)
        self.assertIn("orphan_internal_urls", ids)
        self.assertIn("google_nlp_not_aggregated", ids)
        self.assertIn("ai_overview_signals_unused", ids)
        self.assertIn("page_briefs_too_shallow", ids)
        self.assertIn("eeat_evidence_missing", ids)
        if yaml is not None:
            self.assertIn("entity_map_md_yaml_drift", ids)
        self.assertEqual(len(report["scorecard"]), 10)
        self.assertTrue(report["remediation_plan"])
        self.assertTrue(report["launch_action_plan"])
        self.assertLess(
            next(item["score"] for item in report["scorecard"] if item["id"] == "content_brief_depth"),
            10,
        )

    def test_launch_action_plan_routes_clean_package_to_source_lock_when_required(self) -> None:
        report = {
            "findings": [],
            "source_lock_gate": {
                "status": "required_before_final_draft",
                "plan": "seo/research-package/source-lock-plan.md",
                "queue": "seo/research-package/source-lock-queue.csv",
            },
        }

        plan = QUALITY.launch_action_plan(report)

        self.assertEqual(plan[0]["action"], "Complete source-lock before final drafting.")
        self.assertIn("source-lock-queue.csv", plan[0]["command"])
        self.assertIn("page-outline-v3.py", plan[1]["command"])

    def test_page_outline_v2_generates_section_level_brief(self) -> None:
        outline = OUTLINE.build_outline(self.package, "/tools/virtual-hair-color-try-on/")

        self.assertEqual(outline["page"]["page_type"], "Tool")
        self.assertIn("WebApplication", outline["schema"])
        self.assertGreater(outline["computed_word_count"]["min"], 0)
        self.assertGreaterEqual(len(outline["sections"]), 5)
        section = outline["sections"][0]
        self.assertIn("copywriter_notes", section)
        self.assertIn("evidence_required", section)
        self.assertIn("seo_meta", outline)
        self.assertIn("title_tag", outline["seo_meta"])
        self.assertIn("meta_description", outline["seo_meta"])
        self.assertGreaterEqual(len(outline["key_takeaways"]), 4)
        self.assertGreaterEqual(len(outline["faq"]), 3)
        self.assertGreaterEqual(len(outline["visual_plan"]), 2)
        self.assertIn("writer_handoff", outline)
        self.assertGreaterEqual(len(outline["writer_handoff"]["fact_check_queue"]), 3)
        self.assertIn("copywriting_playbook", outline)
        self.assertGreaterEqual(len(outline["copywriting_playbook"]["revision_checklist"]), 6)
        self.assertIn("tone_contract", outline["copywriting_playbook"])
        self.assertIn("writer_prompt_packet", outline)
        self.assertGreaterEqual(len(outline["writer_prompt_packet"]["forbidden_actions"]), 3)
        self.assertIn("starter_prompt", outline["writer_prompt_packet"])
        self.assertGreaterEqual(len(outline["trust_limitations"]), 3)
        self.assertGreaterEqual(len(outline["synthetic_prompts"]), 3)
        self.assertIn("coverage_weight", outline["entities"][0])
        self.assertIn("intro_brief", outline)
        self.assertIn("conclusion_brief", outline)
        self.assertIn("bridge", section)
        self.assertGreaterEqual(len(section["h3_subsections"]), 2)
        self.assertEqual(
            sum(item["word_count_min"] for item in section["h3_subsections"]),
            section["word_count_min"],
        )
        self.assertEqual(
            sum(item["word_count_max"] for item in section["h3_subsections"]),
            section["word_count_max"],
        )
        self.assertIn("copywriting_details", section)
        self.assertGreaterEqual(len(section["copywriting_details"]["source_slots"]), 2)
        self.assertGreaterEqual(len(section["copywriting_details"]["acceptance_criteria"]), 3)
        self.assertIn("metrics_rollup", outline)
        self.assertEqual(outline["metrics_rollup"]["impressions"], 1600.0)
        self.assertEqual(outline["metrics_rollup"]["clicks"], 52.0)
        self.assertEqual(outline["metrics_rollup"]["volume"], 12300.0)
        self.assertEqual(outline["metrics_rollup"]["max_priority_score"], 91.5)
        self.assertIn("hair color simulator", [item["keyword"] for item in outline["metrics_rollup"]["top_supporting_keywords"]])
        self.assertIn("no_fabricated_first_person", outline["eeat_guard"]["expert_author_mode"])
        self.assertTrue(any("Do not invent" in note for note in section["copywriter_notes"]))

    def test_page_outline_quality_gate_passes_generated_outline(self) -> None:
        outline = OUTLINE.build_outline(self.package, "/tools/virtual-hair-color-try-on/")
        OUTLINE.write_outline(self.package, outline)

        report = OUTLINE_QUALITY.audit(self.package)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["ten_point_score"], 10.0)
        self.assertEqual(len(report["scorecard"]), 10)
        self.assertFalse(report["findings"])

    def test_page_outline_quality_gate_flags_unsafe_shallow_outline(self) -> None:
        outline_dir = self.package / "page-outlines-v2"
        outline_dir.mkdir()
        bad_outline = {
            "outline_id": "page_outline_v2",
            "page": {
                "title": "Bad outline",
                "url": "/bad/",
                "primary_keyword": "bad outline",
                "page_type": "Guide",
            },
            "computed_word_count": {"min": 900, "max": 1100},
            "sections": [
                {
                    "level": 2,
                    "title": "Intro",
                    "summary": "Thin intro.",
                    "word_count_min": 50,
                    "word_count_max": 80,
                    "copywriter_notes": ["In my years working with clients, this always works."],
                    "entities_to_cover": [],
                    "entity_connections": [],
                    "evidence_required": [],
                    "visual_elements": "",
                    "answer_unit": {"required": False},
                }
            ],
            "entities": [{"name": "Orphan Entity"}],
            "schema": [],
            "internal_links": [],
            "geo_requirements": [],
            "eeat_guard": {"expert_author_mode": "no_fabricated_first_person"},
        }
        (outline_dir / "bad.json").write_text(json.dumps(bad_outline), encoding="utf-8")

        report = OUTLINE_QUALITY.audit(self.package)
        ids = {finding["id"] for finding in report["findings"]}

        self.assertEqual(report["status"], "fail")
        self.assertIn("word_count_mismatch", ids)
        self.assertIn("missing_page_context", ids)
        self.assertIn("missing_intro_conclusion", ids)
        self.assertIn("missing_seo_meta", ids)
        self.assertIn("missing_schema", ids)
        self.assertIn("missing_internal_links", ids)
        self.assertIn("missing_answer_units", ids)
        self.assertIn("missing_key_takeaways", ids)
        self.assertIn("missing_faq_assets", ids)
        self.assertIn("missing_writer_handoff", ids)
        self.assertIn("missing_copywriting_playbook", ids)
        self.assertIn("missing_revision_checklist", ids)
        self.assertIn("missing_writer_prompt_packet", ids)
        self.assertIn("missing_fact_check_queue", ids)
        self.assertIn("unsafe_first_person_expertise", ids)
        self.assertIn("orphan_entities", ids)
        self.assertIn("missing_section_bridges", ids)
        self.assertIn("missing_h3_subsections", ids)
        self.assertIn("weak_copywriting_details", ids)
        self.assertIn("missing_source_slots", ids)
        self.assertIn("missing_acceptance_criteria", ids)
        self.assertIn("missing_visual_guidance", ids)
        self.assertIn("weak_visual_plan", ids)
        self.assertIn("missing_trust_limitations", ids)
        self.assertIn("missing_synthetic_prompts", ids)
        self.assertLess(report["ten_point_score"], 10)

    def test_page_outline_v2_batch_generates_all_mvp_briefs(self) -> None:
        outlines = OUTLINE.build_outlines(self.package, all_mvp=True)

        urls = {outline["page"]["url"] for outline in outlines}
        self.assertEqual(len(outlines), 2)
        self.assertIn("/tools/virtual-hair-color-try-on/", urls)
        self.assertIn("/tools/face-shape-detector/", urls)

    def test_page_outline_v2_can_archive_duplicate_legacy_briefs_after_successful_write(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "page-outline-v2.py"),
                str(self.package),
                "--all-mvp",
                "--write",
                "--archive-legacy-briefs",
                "--format",
                "json",
            ],
            cwd=self.package,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(proc.stdout)
        archive_dir = self.package / "archive" / "legacy-briefs"

        self.assertEqual(payload["legacy_briefs_archive"]["archived_files"], 2)
        self.assertFalse((self.package / "page-briefs.md").exists())
        self.assertFalse((self.package / "mvp-page-briefs.md").exists())
        self.assertTrue(any(path.name.startswith("page-briefs.") for path in archive_dir.iterdir()))
        self.assertTrue(any(path.name.startswith("mvp-page-briefs.") for path in archive_dir.iterdir()))

    def test_page_outline_v3_generates_tool_first_copywriter_ready_and_triplets(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(OUTLINE_V3_PATH),
                str(self.package),
                "--page",
                "/tools/virtual-hair-color-try-on/",
                "--write",
                "--format",
                "json",
            ],
            cwd=self.package,
            text=True,
            capture_output=True,
            check=True,
        )
        outline = json.loads(proc.stdout)
        copywriter_path = pathlib.Path(outline["paths"]["copywriter_ready"])
        triplets_path = self.package / "vector" / "page_outline_triplets.jsonl"

        self.assertEqual(outline["outline_id"], "page_outline_v3")
        self.assertEqual(outline["version"], "v3")
        self.assertEqual(outline["serp_safe_layout"]["order"][0], "tool_ux_above_the_fold")
        self.assertEqual(outline["sections"][0]["section_role"], "tool_ux_above_the_fold")
        self.assertTrue(copywriter_path.exists())
        self.assertTrue(triplets_path.exists())
        self.assertIn("Copywriter Ready Brief", copywriter_path.read_text(encoding="utf-8"))
        self.assertIn("FAQ Answer Guidelines", copywriter_path.read_text(encoding="utf-8"))
        self.assertNotIn("open semantic-core.csv", copywriter_path.read_text(encoding="utf-8").lower())
        self.assertGreaterEqual(len(outline["visual_inventory"]), 6)

        for section in outline["sections"]:
            for key in (
                "word_count",
                "entities_to_cover",
                "keywords",
                "summary",
                "visual_elements",
                "copywriter_notes",
                "entity_connections",
                "answer_unit",
                "source_slots",
                "acceptance_criteria",
            ):
                self.assertIn(key, section)
            self.assertGreaterEqual(len(section["h3_subsections"]), 2)
            for subsection in section["h3_subsections"]:
                for key in (
                    "word_count",
                    "entities_to_cover",
                    "keywords",
                    "summary",
                    "visual_elements",
                    "copywriter_notes",
                    "entity_connections",
                    "answer_unit",
                    "source_slots",
                    "acceptance_criteria",
                ):
                    self.assertIn(key, subsection)

    def test_page_outline_v3_quality_gate_blocks_non_tool_first_and_fake_expertise(self) -> None:
        outline_dir = self.package / "page-outlines-v3"
        outline_dir.mkdir()
        bad = OUTLINE.build_outline(self.package, "/tools/virtual-hair-color-try-on/")
        bad["outline_id"] = "page_outline_v3"
        bad["version"] = "v3"
        bad["serp_safe_layout"] = {"order": ["supporting_longform", "tool_ux_above_the_fold"]}
        bad["sections"][0]["section_role"] = "supporting_longform"
        bad["sections"][0]["copywriter_notes"].append("In my years working with clients, this always works.")
        bad["visual_inventory"] = []
        (outline_dir / "bad.json").write_text(json.dumps(bad), encoding="utf-8")

        report = OUTLINE_QUALITY.audit(self.package, version="v3")
        ids = {finding["id"] for finding in report["findings"]}

        self.assertEqual(report["status"], "fail")
        self.assertIn("tool_first_order_violation", ids)
        self.assertIn("unsafe_first_person_expertise", ids)
        self.assertIn("weak_visual_inventory", ids)
        self.assertTrue(any(item["id"] == "serp_safe_ux" for item in report["scorecard"]))

    def test_page_outline_quality_cli_accepts_version_v3(self) -> None:
        subprocess.run(
            [
                sys.executable,
                str(OUTLINE_V3_PATH),
                str(self.package),
                "--page",
                "/tools/virtual-hair-color-try-on/",
                "--write",
                "--format",
                "json",
            ],
            cwd=self.package,
            text=True,
            capture_output=True,
            check=True,
        )

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "page-outline-quality.py"),
                str(self.package),
                "--version",
                "v3",
                "--write",
                "--format",
                "json",
            ],
            cwd=self.package,
            text=True,
            capture_output=True,
            check=True,
        )
        report = json.loads(proc.stdout)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["outline_version"], "v3")
        self.assertTrue((self.package / "page-outline-quality.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
