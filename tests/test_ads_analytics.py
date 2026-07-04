#!/usr/bin/env python3
"""Tests for ads-analytics.py cross-channel rules and db-sync ads tables."""

from __future__ import annotations

import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

CFG = """project:
  name: ads-analytics-test
region_profile: ru
ads:
  enabled: true
  analytics:
    top_position_threshold: 3
    wasted_spend_min_cost: 100
"""


class AdsAnalyticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-ads-analytics-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")
        self.seed_positions()
        self.seed_core()
        self.seed_raw()

    def seed_positions(self) -> None:
        db = self.tmp / "seo" / "seo.db"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE positions (snapshot_date TEXT, engine TEXT, query TEXT,
                        position REAL, clicks INTEGER, impressions INTEGER, url TEXT)""")
        conn.execute("INSERT INTO positions VALUES ('2026-07-01','yandex','купить вагонку',2.0,50,1000,'/catalog/vagonka/')")
        conn.execute("INSERT INTO positions VALUES ('2026-07-01','yandex','вагонка штиль',15.0,5,300,'/catalog/shtil/')")
        conn.commit()
        conn.close()

    def seed_core(self) -> None:
        package = self.tmp / "seo" / "research-package"
        package.mkdir(parents=True)
        (package / "semantic-core.csv").write_text(
            "keyword,cluster_id\nкупить вагонку,vagonka\nвагонка штиль,vagonka\n", encoding="utf-8"
        )

    def seed_raw(self) -> None:
        raw = self.tmp / "seo" / "ads" / "raw" / "yandex_direct"
        raw.mkdir(parents=True)
        (raw / "search_queries-latest.json").write_text(
            json.dumps({"rows": [
                # rule 1: organic top-2 + paid clicks → overlap
                {"Query": "купить вагонку", "CampaignId": "1", "Clicks": "30", "Cost": "900", "Conversions": "3"},
                # rule 2: converting term missing from the core → candidate
                {"Query": "вагонка из кедра цена", "CampaignId": "1", "Clicks": "12", "Cost": "400", "Conversions": "2"},
                # rule 4: wasted spend, no conversions
                {"Query": "вагонка бесплатно скачать", "CampaignId": "2", "Clicks": "40", "Cost": "500", "Conversions": "0"},
                # below wasted threshold → ignored
                {"Query": "вагонка мелочь", "CampaignId": "2", "Clicks": "1", "Cost": "20", "Conversions": "0"},
            ]}),
            encoding="utf-8",
        )
        (raw / "stats-latest.json").write_text(
            json.dumps({"rows": [
                {"Date": "2026-07-01", "CampaignId": "1", "CampaignName": "Search P1",
                 "Impressions": "5000", "Clicks": "42", "Cost": "1300", "Conversions": "5"},
                {"Date": "2026-07-01", "CampaignId": "2", "CampaignName": "Generic",
                 "Impressions": "8000", "Clicks": "41", "Cost": "520", "Conversions": "0"},
            ]}),
            encoding="utf-8",
        )
        (raw / "campaigns-latest.json").write_text(
            json.dumps({"result": {"Campaigns": [
                {"Id": 1, "Name": "Search P1", "State": "ON",
                 "DailyBudget": {"Amount": 300000000}},
                {"Id": 2, "Name": "Generic", "State": "ON"},
            ]}}),
            encoding="utf-8",
        )

    def run_analytics(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "ads-analytics.py"), *args, "--format", "json"],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_all_four_rules_fire(self) -> None:
        proc = self.run_analytics("--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)

        overlap = report["organic_overlap"]
        self.assertEqual(len(overlap), 1)
        self.assertEqual(overlap[0]["query"], "купить вагонку")
        self.assertEqual(overlap[0]["organic_position"], 2.0)

        candidates = report["keyword_candidates"]
        self.assertEqual([row["query"] for row in candidates], ["вагонка из кедра цена"])

        wasted = report["wasted_spend"]
        self.assertEqual([row["query"] for row in wasted], ["вагонка бесплатно скачать"])

        campaigns = {row["campaign_id"]: row for row in report["campaigns"]}
        self.assertEqual(campaigns["1"]["cpa"], 260.0)  # 1300 / 5
        self.assertIsNone(campaigns["2"]["cpa"])

        self.assertTrue((self.tmp / "seo" / "ads" / "ads-analytics.md").exists())
        candidates_csv = (self.tmp / "seo" / "ads" / "keyword-candidates.csv").read_text(encoding="utf-8")
        self.assertIn("вагонка из кедра цена", candidates_csv)
        negatives_csv = (self.tmp / "seo" / "ads" / "negative-candidates.csv").read_text(encoding="utf-8")
        self.assertIn("вагонка бесплатно скачать", negatives_csv)

    def test_wasted_ngrams_aggregate_subthreshold_terms(self) -> None:
        raw = self.tmp / "seo" / "ads" / "raw" / "yandex_direct"
        (raw / "search_queries-latest.json").write_text(
            json.dumps({"rows": [
                # каждый терм ниже порога 100 сам по себе, но токен «бесплатно» суммарно 180
                {"Query": "вагонка бесплатно скачать", "CampaignId": "2", "Clicks": "9",
                 "Cost": "90", "Conversions": "0"},
                {"Query": "вагонка бесплатно чертежи", "CampaignId": "2", "Clicks": "9",
                 "Cost": "90", "Conversions": "0"},
                {"Query": "купить вагонку", "CampaignId": "1", "Clicks": "30",
                 "Cost": "900", "Conversions": "3"},
            ]}),
            encoding="utf-8",
        )
        report = json.loads(self.run_analytics().stdout)
        self.assertEqual(report["wasted_spend"], [])  # ни один терм не прошёл порог сам
        ngrams = {row["ngram"]: row for row in report["wasted_ngrams"]}
        self.assertIn("бесплатно", ngrams)
        self.assertEqual(ngrams["бесплатно"]["cost"], 180.0)
        self.assertEqual(ngrams["бесплатно"]["terms"], 2)
        self.assertIn("вагонка бесплатно", ngrams)  # биграмма тоже
        self.assertNotIn("купить", ngrams)  # конверсионные термы не участвуют

    def test_runs_without_db_or_raw(self) -> None:
        empty = pathlib.Path(tempfile.mkdtemp(prefix="seo-ads-empty-"))
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))
        (empty / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "ads-analytics.py"), "--format", "json"],
            cwd=empty,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["summary"]["campaigns"], 0)


class DbSyncAdsTest(AdsAnalyticsTest):
    def test_db_sync_builds_ads_tables(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "db-sync.py"), "--root", str(self.tmp)],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        conn = sqlite3.connect(self.tmp / "seo" / "seo.db")
        campaigns = conn.execute("SELECT platform, name, budget FROM ads_campaigns ORDER BY name").fetchall()
        self.assertEqual(len(campaigns), 2)
        self.assertEqual(campaigns[1][1], "Search P1")
        self.assertEqual(campaigns[1][2], 300.0)  # micros → units
        stats = conn.execute("SELECT SUM(cost) FROM ads_stats").fetchone()[0]
        self.assertEqual(stats, 1820.0)
        terms = conn.execute("SELECT COUNT(*) FROM ads_search_terms").fetchone()[0]
        self.assertEqual(terms, 4)
        conn.close()


if __name__ == "__main__":
    unittest.main()
