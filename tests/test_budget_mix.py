#!/usr/bin/env python3
"""Tests for budget-mix-planner.py."""

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

CFG = """project:
  name: budget-mix
kpi:
  lead_conversion_rate: 0.05
  months_to_target: 5
  budget:
    cost_per_article: 10000
    ppc_step: 10000
"""

FORECAST = {
    "cluster_upside_top10": [
        {"cluster": "vagonka", "upside_clicks": 900},   # 900*0.05*0.6=27 leads → 2.7/1000
        {"cluster": "brus", "upside_clicks": 300},      # 9 leads → 0.9/1000
    ]
}
ADS = {
    "campaigns": [
        {"platform": "yandex_direct", "campaign_id": "1", "name": "Search P1", "cpa": 500.0},  # 20 leads → 2.0/1000
        {"platform": "yandex_direct", "campaign_id": "2", "name": "Generic", "cpa": None},
    ]
}


class BudgetMixTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-budget-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")
        strategy = self.tmp / "seo" / "strategy"
        strategy.mkdir(parents=True)
        (strategy / "seo-forecast.json").write_text(json.dumps(FORECAST), encoding="utf-8")
        ads = self.tmp / "seo" / "ads"
        ads.mkdir(parents=True)
        (ads / "ads-analytics.json").write_text(json.dumps(ADS), encoding="utf-8")

    def run_planner(self, *args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "budget-mix-planner.py"), *args, "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_greedy_mix_ranks_by_leads_per_unit_and_respects_budget(self) -> None:
        report = self.run_planner("--monthly-budget", "30000", "--write")
        mix = report["mix"]
        # best lots: seo vagonka (2.7), ppc step (2.0) x2 → 10k+10k+10k = 30k
        self.assertEqual(mix["seo_spend"] + mix["ppc_spend"], 30000)
        self.assertEqual(mix["unallocated"], 0)
        self.assertEqual(report["selected_lots"][0]["lot"], "article: vagonka")
        self.assertEqual(report["selected_lots"][0]["channel"], "seo")
        self.assertTrue(all(lot["channel"] == "ppc" for lot in report["selected_lots"][1:3]))
        # leads: 27 + 20 + 20 = 67
        self.assertAlmostEqual(mix["expected_monthly_leads"], 67.0, places=1)
        # ranking is monotonic
        ranks = [lot["leads_per_1000"] for lot in report["selected_lots"]]
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        self.assertTrue((self.tmp / "seo" / "strategy" / "budget-mix.md").exists())

    def test_campaigns_without_cpa_are_excluded(self) -> None:
        report = self.run_planner("--monthly-budget", "200000")
        self.assertFalse(any("Generic" in lot["lot"] for lot in report["selected_lots"]))

    def test_empty_inputs_are_graceful(self) -> None:
        empty = pathlib.Path(tempfile.mkdtemp(prefix="seo-budget-empty-"))
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))
        (empty / "seo-cycle.yaml").write_text("project:\n  name: empty\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "budget-mix-planner.py"), "--format", "json"],
            cwd=empty, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["selected_lots"], [])
        self.assertIn("monthly_budget", proc.stderr.lower().replace("-", "_") or "monthly_budget")


if __name__ == "__main__":
    unittest.main()
