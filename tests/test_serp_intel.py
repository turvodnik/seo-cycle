#!/usr/bin/env python3
"""Tests for serp-intel.py (overlap clusters, features, entity candidates)."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def seed(package: pathlib.Path) -> None:
    package.mkdir(parents=True)
    validation = {
        "купить вагонку": {"features": ["Featured snippet", "PAA"],
                           "top_urls": [f"https://a.ru/{i}" for i in range(8)] + ["https://x.ru/1", "https://y.ru/1"],
                           "top_titles": ["Купить вагонку штиль из лиственницы", "Вагонка лиственница цена"],
                           "dominant_page_type": "category"},
        "вагонка цена": {"features": ["AI Overview"],
                         "top_urls": [f"https://a.ru/{i}" for i in range(8)] + ["https://z.ru/1", "https://w.ru/1"],
                         "top_titles": ["Вагонка штиль лиственница купить", "Вагонка из лиственницы"],
                         "dominant_page_type": "category"},
        "монтаж вагонки": {"features": ["Video"],
                           "top_urls": [f"https://b{i}.ru/guide" for i in range(10)],
                           "top_titles": ["Монтаж вагонки своими руками", "Крепление вагонки кляймерами"],
                           "dominant_page_type": "guide"},
    }
    (package / "semantic-architecture-final.json").write_text(
        json.dumps({"dataforseo_serp_validation": validation}, ensure_ascii=False), encoding="utf-8")
    (package / "semantic-core.csv").write_text(
        "keyword,cluster_id\nкупить вагонку,vagonka\nвагонка цена,ceny\nмонтаж вагонки,ceny\n",
        encoding="utf-8")
    (package / "entity-map-final.json").write_text(
        json.dumps({"entities": ["вагонка", "лиственницы"]}, ensure_ascii=False), encoding="utf-8")


class SerpIntelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-serpintel-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: intel\n", encoding="utf-8")
        seed(self.tmp / "seo" / "research-package")

    def run_intel(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "serp-intel.py"), *args, "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False)

    def test_overlap_merge_and_split_candidates(self) -> None:
        proc = self.run_intel()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        clusters = report["clusters"]
        # «купить вагонку» и «вагонка цена» делят 8/12 URL → одна SERP-группа
        self.assertEqual(len(clusters["serp_clusters"]), 1)
        self.assertIn("купить вагонку", clusters["serp_clusters"][0])
        # они в разных кластерах ядра → merge-кандидат
        self.assertEqual(len(clusters["merge_candidates"]), 1)
        self.assertEqual({clusters["merge_candidates"][0]["cluster_a"],
                          clusters["merge_candidates"][0]["cluster_b"]}, {"vagonka", "ceny"})
        # «вагонка цена» и «монтаж вагонки» в одном кластере ядра, SERP не пересекаются → split
        self.assertTrue(any(c["cluster"] == "ceny" for c in clusters["split_candidates"]))

    def test_features_and_aeo_priority(self) -> None:
        report = json.loads(self.run_intel("--features").stdout)
        shares = report["features"]["shares"]
        self.assertEqual(shares["featured_snippet"]["count"], 1)
        self.assertEqual(shares["ai_overview"]["count"], 1)
        self.assertIn("купить вагонку", report["features"]["aeo_priority_keywords"])
        self.assertNotIn("clusters", report)

    def test_entity_candidates_exclude_known(self) -> None:
        report = json.loads(self.run_intel("--entities", "--min-mentions", "2").stdout)
        candidates = {item["candidate"] for item in report["entities"]}
        self.assertIn("штиль", candidates)          # 3 упоминания в титулах
        self.assertNotIn("вагонка", candidates)     # уже в entity map
        self.assertNotIn("купить", candidates)      # интент-стоп-слово

    def test_graceful_without_serp_data(self) -> None:
        empty = pathlib.Path(tempfile.mkdtemp(prefix="seo-serpintel-empty-"))
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))
        (empty / "seo-cycle.yaml").write_text("project:\n  name: e\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, str(SCRIPTS / "serp-intel.py")],
                              cwd=empty, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("serp-validation-import", proc.stderr)


if __name__ == "__main__":
    unittest.main()
