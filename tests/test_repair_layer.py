#!/usr/bin/env python3
"""Regression tests for research-package repair layer scripts."""

from __future__ import annotations

import csv
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


class RepairLayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-repair-layer-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.package = self.tmp / "research-package"
        self.package.mkdir()
        self.write_package()

    def write_csv(self, name: str, rows: list[dict[str, str]]) -> None:
        path = self.package / name
        fields = list(rows[0]) if rows else ["keyword"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def read_csv(self, path: pathlib.Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def run_script(self, script: str, *args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / script), str(self.package), "--write", "--format", "json", *args],
            cwd=self.package,
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(proc.stdout)

    def run_script_allow_fail(self, script: str, *args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / script), str(self.package), "--write", "--format", "json", *args],
            cwd=self.package,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode not in {0, 1}:
            self.fail(f"{script} failed unexpectedly: {proc.stderr}")
        return json.loads(proc.stdout)

    def write_package(self) -> None:
        architecture = {
            "metadata": {
                "sources": {
                    "dataforseo_serp_validation_keywords": [
                        "virtual hair color try on",
                        "hair color analysis",
                        "face shape detector",
                    ],
                    "google_nlp": {
                        "status": "ok",
                        "entities": [
                            {"name": "Hair Color", "type": "OTHER", "salience": 0.18},
                            {"name": "hair color", "type": "CONSUMER_GOOD", "salience": 0.11},
                            {"name": "hair color hair color", "type": "OTHER", "salience": 0.04},
                            {"name": "Diamond Face Shape Face Shape", "type": "PERSON", "salience": 0.06},
                        ],
                    },
                }
            },
            "clusters": [
                {
                    "id": "virtual_hair_color_try_on",
                    "name": "Virtual Hair Color Try-On",
                    "primary_keyword": "virtual hair color try on",
                    "page_type": "Tool",
                    "suggested_url": "/tools/virtual-hair-color-try-on/",
                    "priority": "P1",
                    "mvp": True,
                    "internal_links": ["/hair-color/by-skin-tone/", "/guides/face-shapes/"],
                },
                {
                    "id": "seasonal_color_analysis",
                    "name": "Seasonal Color Analysis",
                    "primary_keyword": "seasonal color analysis",
                    "page_type": "Guide",
                    "suggested_url": "/hair-color/seasonal-analysis/",
                    "priority": "P2",
                    "mvp": False,
                    "internal_links": ["/hair-color/cool-summer-hair-colors/"],
                    "legacy_ids": ["hair_color_by_season"],
                    "legacy_urls": ["/hair-color/seasons/"],
                },
                {
                    "id": "hair_color_by_skin_tone",
                    "name": "Hair Color by Skin Tone",
                    "primary_keyword": "hair color for skin tone",
                    "page_type": "Guide",
                    "suggested_url": "/hair-color/by-skin-tone/",
                    "priority": "P1",
                    "mvp": True,
                    "internal_links": [],
                },
            ],
            "dataforseo_serp_validation": {
                "virtual hair color try on": {
                    "features": ["organic"],
                    "top_urls": ["https://example.com/tool"],
                    "top_titles": ["Example tool"],
                },
                "hair color analysis": {"features": [], "top_urls": [], "top_titles": []},
            },
        }
        (self.package / "semantic-architecture-final.json").write_text(json.dumps(architecture), encoding="utf-8")
        self.write_csv(
            "semantic-core.csv",
            [
                {
                    "keyword": "virtual hair color try on",
                    "base_cluster": "virtual_hair_color_try_on",
                    "cluster_id": "virtual_hair_color_try_on",
                    "suggested_url": "/tools/virtual-hair-color-try-on/",
                    "impressions": "1200",
                    "clicks": "40",
                    "position": "4.2",
                    "dataforseo_serp_features": "organic|ai_overview",
                },
                {
                    "keyword": "create a hairstyle analysis graphic using this portrait, show side-by-side hairstyles comparisons",
                    "base_cluster": "virtual_hair_color_try_on",
                    "cluster_id": "virtual_hair_color_try_on",
                    "suggested_url": "/hair-color/old-url/",
                    "impressions": "4",
                    "clicks": "0",
                    "position": "60",
                    "dataforseo_serp_features": "",
                },
                {
                    "keyword": "cool summer hair colors",
                    "base_cluster": "hair_color_by_season",
                    "cluster_id": "hair_color_by_season",
                    "suggested_url": "/hair-color/seasons/",
                    "impressions": "934",
                    "clicks": "21",
                    "position": "6.69",
                    "dataforseo_serp_features": "organic|ai_overview",
                },
                {
                    "keyword": "cool winter hair colors",
                    "base_cluster": "hair_color_by_season",
                    "cluster_id": "hair_color_by_season",
                    "suggested_url": "/hair-color/seasons/",
                    "impressions": "620",
                    "clicks": "10",
                    "position": "8.1",
                    "dataforseo_serp_features": "organic",
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
                    "source_cluster": "virtual_hair_color_try_on",
                    "internal_links": "/hair-color/by-skin-tone/|/guides/face-shapes/",
                },
                {
                    "priority": "P2",
                    "mvp": "False",
                    "url": "/hair-color/seasonal-analysis/",
                    "page_title": "Seasonal Color Analysis",
                    "primary_keyword": "seasonal color analysis",
                    "page_type": "Guide",
                    "source_cluster": "seasonal_color_analysis",
                    "internal_links": "/hair-color/cool-summer-hair-colors/",
                },
                {
                    "priority": "P1",
                    "mvp": "True",
                    "url": "/hair-color/by-skin-tone/",
                    "page_title": "Hair Color by Skin Tone",
                    "primary_keyword": "hair color for skin tone",
                    "page_type": "Guide",
                    "source_cluster": "hair_color_by_skin_tone",
                    "internal_links": "",
                },
            ],
        )
        if yaml is not None:
            (self.package / "entity-map.yaml").write_text(
                yaml.safe_dump(
                    {
                        "entities": [
                            {
                                "id": "seasonal_color_analysis",
                                "name": "Seasonal Color Analysis",
                                "coverage_priority": "P1",
                                "attributes": ["Cool Summer", "Clear Winter", "Deep Winter"],
                                "related_entities": ["Hair Color", "Skin Tone"],
                                "target_clusters": ["seasonal_color_analysis"],
                            }
                        ]
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
        else:
            (self.package / "entity-map.yaml").write_text("entities: []\n", encoding="utf-8")
        (self.package / "entity-map.md").write_text("### Seasonal Color Analysis\n\n- Attributes: Cool Summer\n", encoding="utf-8")
        (self.package / "site-structure.md").write_text("- Guides: `/guides/face-shapes/`\n", encoding="utf-8")
        outline_dir = self.package / "page-outlines-v2"
        outline_dir.mkdir()
        outline = {
            "outline_id": "page_outline_v2",
            "page": {
                "title": "Virtual Hair Color Try-On",
                "url": "/tools/virtual-hair-color-try-on/",
                "primary_keyword": "virtual hair color try on",
                "intent": "Do",
                "page_type": "Tool",
            },
            "computed_word_count": {"min": 300, "max": 420},
            "entities": [
                {"name": "Hair Color", "coverage_weight": 9, "weight_source": "entity-map priority"},
                {"name": "Orphan Entity", "coverage_weight": 3},
            ],
            "internal_links": ["/hair-color/by-skin-tone/"],
            "schema": ["WebApplication", "FAQPage"],
            "faq": [{"question": "Is it free?", "answer_guidance": "Answer first."}],
            "sections": [
                {
                    "level": 2,
                    "title": "What This Tool Does",
                    "word_count_min": 120,
                    "word_count_max": 180,
                    "h3_subsections": [{"title": "Plain Answer"}, {"title": "Why It Matters"}],
                    "entity_connections": [
                        "Hair Color -> supports_intent -> virtual hair color try on",
                        "Hair Color -> supports_intent -> virtual hair color try on",
                    ],
                    "entities_to_cover": ["Hair Color"],
                    "answer_unit": {"required": True, "formula": "thesis -> proof"},
                },
                {
                    "level": 2,
                    "title": "Frequently Asked Questions",
                    "word_count_min": 180,
                    "word_count_max": 240,
                    "h3_subsections": [{"title": "Is it free?"}],
                    "entity_connections": ["Unknown Brand -> compares_with -> Hair Color"],
                    "entities_to_cover": ["Hair Color"],
                    "answer_unit": {"required": True, "formula": "thesis -> proof"},
                },
            ],
        }
        (outline_dir / "try-on.json").write_text(json.dumps(outline), encoding="utf-8")
        (self.package / "draft.md").write_text(
            "# Virtual Hair Color Try-On\n\n"
            "## What This Tool Does\n\n"
            "In my years working with clients, this tool is always accurate.\n\n"
            "## Frequently Asked Questions\n\n"
            "### Is it free?\n\n"
            "Yes.\n",
            encoding="utf-8",
        )

    def test_semantic_core_clean_and_resync_write_repair_artifacts(self) -> None:
        clean = self.run_script("semantic-core-clean.py")
        self.assertEqual(clean["summary"]["rejected_rows"], 1)
        self.assertTrue((self.package / "semantic-core.cleaned.csv").exists())
        rejected = self.read_csv(self.package / "semantic-core.rejected.csv")
        self.assertIn("prompt_like_query", rejected[0]["rejection_reasons"])

        resync = self.run_script("semantic-core-resync.py")
        self.assertGreaterEqual(resync["summary"]["changed_rows"], 2)
        rows = self.read_csv(self.package / "semantic-core.resynced.csv")
        summer = next(row for row in rows if row["keyword"] == "cool summer hair colors")
        self.assertEqual(summer["base_cluster"], "seasonal_color_analysis")
        self.assertEqual(summer["suggested_url"], "/hair-color/seasonal-analysis/")

    def test_entity_map_sync_and_google_nlp_aggregate_write_canonical_outputs(self) -> None:
        if yaml is None:
            self.skipTest("PyYAML is required")
        sync = self.run_script("entity-map-sync.py")
        self.assertEqual(sync["summary"]["entities"], 1)
        synced = (self.package / "entity-map.md").read_text(encoding="utf-8")
        self.assertIn("Clear Winter", synced)
        self.assertIn("Deep Winter", synced)

        aggregate = self.run_script("google-nlp-aggregate.py")
        self.assertEqual(aggregate["summary"]["unique_entities"], 2)
        lines = [json.loads(line) for line in (self.package / "entity_coverage.jsonl").read_text(encoding="utf-8").splitlines()]
        hair = next(row for row in lines if row["entity"] == "hair color")
        self.assertEqual(hair["mentions"], 3)
        self.assertGreater(hair["salience_sum"], 0.3)
        self.assertNotIn("hair color hair color", {row["entity"] for row in lines})

    def test_orphan_serp_and_spoke_repair_plans_are_actionable(self) -> None:
        orphan = self.run_script("orphan-url-resolver.py")
        self.assertEqual(orphan["summary"]["orphan_urls"], 2)
        backlog = self.read_csv(self.package / "content-plan.orphan-backlog.csv")
        self.assertIn("/guides/face-shapes/", {row["url"] for row in backlog})

        serp = self.run_script("serp-validation-plan.py")
        self.assertGreaterEqual(serp["summary"]["planned_queries"], 2)
        serp_rows = self.read_csv(self.package / "serp-validation-plan.csv")
        self.assertIn("hair color analysis", {row["keyword"] for row in serp_rows})
        self.assertIn("face shape detector", {row["keyword"] for row in serp_rows})
        self.assertIn("page_type_decision_fields", serp_rows[0])

        spokes = self.run_script("spoke-opportunity-audit.py")
        self.assertGreaterEqual(spokes["summary"]["opportunities"], 2)
        spoke_rows = self.read_csv(self.package / "spoke-opportunities.csv")
        self.assertIn("cool summer hair colors", {row["keyword"] for row in spoke_rows})
        self.assertTrue(all(row["phase"] == "phase_2" for row in spoke_rows))

    def test_serp_validation_import_updates_architecture_from_guarded_export(self) -> None:
        export_path = self.package / "serp-export.json"
        export_path.write_text(
            json.dumps(
                [
                    {
                        "keyword": "hair color analysis",
                        "provider": "manual",
                        "country": "US",
                        "language": "en",
                        "device": "desktop",
                        "features": ["organic", "people_also_ask"],
                        "top_urls": ["https://example.com/hair-color-analysis"],
                        "top_titles": ["Hair Color Analysis Guide"],
                        "dominant_page_type": "Guide",
                        "notes": "SERP mixes guides and quiz-style tools.",
                    }
                ]
            ),
            encoding="utf-8",
        )

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "serp-validation-import.py"),
                str(self.package),
                "--input-json",
                str(export_path),
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
        architecture = json.loads((self.package / "semantic-architecture-final.json").read_text(encoding="utf-8"))
        imported = architecture["dataforseo_serp_validation"]["hair color analysis"]

        self.assertEqual(report["summary"]["imported_queries"], 1)
        self.assertEqual(imported["provider"], "manual")
        self.assertEqual(imported["dominant_page_type"], "Guide")
        self.assertIn("https://example.com/hair-color-analysis", imported["top_urls"])
        self.assertTrue((self.package / "serp-validation-import.md").exists())

    def test_entity_graph_and_draft_quality_gates_find_concrete_failures(self) -> None:
        graph = self.run_script("entity-graph-quality.py")
        ids = {finding["id"] for finding in graph["findings"]}
        self.assertIn("duplicate_relation", ids)
        self.assertIn("missing_weight_source", ids)
        self.assertIn("orphan_relation_endpoint", ids)
        self.assertIn("relation_coverage", graph)

        draft = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "draft-quality-gate.py"),
                str(self.package / "draft.md"),
                "--outline",
                str(self.package / "page-outlines-v2" / "try-on.json"),
                "--write",
                "--format",
                "json",
            ],
            cwd=self.package,
            text=True,
            capture_output=True,
            check=True,
        )
        report = json.loads(draft.stdout)
        finding_ids = {finding["id"] for finding in report["findings"]}
        self.assertIn("missing_h3_heading", finding_ids)
        self.assertIn("unsafe_first_person_expertise", finding_ids)
        self.assertIn("missing_internal_link", finding_ids)
        self.assertIn("missing_proof_slot", finding_ids)

    def test_research_quality_action_plan_points_to_exact_repair_commands(self) -> None:
        quality = self.run_script_allow_fail("research-package-quality.py")
        commands = "\n".join(item["command"] for item in quality["remediation_plan"])
        launch_commands = "\n".join(item["command"] for item in quality["launch_action_plan"])

        self.assertIn("semantic-core-clean.py <package> --write", commands)
        self.assertIn("semantic-core-resync.py <package> --write", commands)
        self.assertIn("entity-map-sync.py <package> --write", commands)
        self.assertIn("google-nlp-aggregate.py <package> --write", commands)
        self.assertIn("orphan-url-resolver.py <package> --write", commands)
        self.assertIn("serp-validation-plan.py <package> --write", commands)
        self.assertIn("research-package-repair.py <package> --write", launch_commands)

    def test_research_package_repair_runs_all_repair_scripts(self) -> None:
        repair = self.run_script("research-package-repair.py")
        self.assertEqual(repair["summary"]["failed_steps"], 0)
        self.assertGreaterEqual(repair["summary"]["completed_steps"], 8)
        self.assertTrue((self.package / "research-package-repair.json").exists())
        self.assertTrue((self.package / "semantic-core.cleaned.csv").exists())
        self.assertTrue((self.package / "semantic-core.resynced.csv").exists())
        self.assertTrue((self.package / "entity_coverage.jsonl").exists())
        self.assertTrue((self.package / "serp-validation-plan.csv").exists())
        self.assertTrue((self.package / "spoke-opportunities.csv").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
