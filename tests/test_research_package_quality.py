#!/usr/bin/env python3
"""Regression tests for research package quality gates and page-outline v2."""

from __future__ import annotations

import csv
import importlib.util
import json
import pathlib
import shutil
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
                },
                {
                    "keyword": "create a hairstyle analysis graphic using this portrait, show side-by-side hairstyles comparisons",
                    "dataforseo_serp_features": "",
                    "base_cluster": "virtual_hair_color_try_on",
                    "suggested_url": "/hair-color/old-url/",
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

    def test_page_outline_v2_generates_section_level_brief(self) -> None:
        outline = OUTLINE.build_outline(self.package, "/tools/virtual-hair-color-try-on/")

        self.assertEqual(outline["page"]["page_type"], "Tool")
        self.assertIn("WebApplication", outline["schema"])
        self.assertGreater(outline["computed_word_count"]["min"], 0)
        self.assertGreaterEqual(len(outline["sections"]), 5)
        section = outline["sections"][0]
        self.assertIn("copywriter_notes", section)
        self.assertIn("evidence_required", section)
        self.assertIn("no_fabricated_first_person", outline["eeat_guard"]["expert_author_mode"])
        self.assertTrue(any("Do not invent" in note for note in section["copywriter_notes"]))

    def test_page_outline_v2_batch_generates_all_mvp_briefs(self) -> None:
        outlines = OUTLINE.build_outlines(self.package, all_mvp=True)

        urls = {outline["page"]["url"] for outline in outlines}
        self.assertEqual(len(outlines), 2)
        self.assertIn("/tools/virtual-hair-color-try-on/", urls)
        self.assertIn("/tools/face-shape-detector/", urls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
