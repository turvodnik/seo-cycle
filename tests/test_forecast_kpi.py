#!/usr/bin/env python3
"""Tests for seo-forecast.py and kpi-contract.py."""

from __future__ import annotations

import datetime as dt
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


class StrategyTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-strategy-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.write_cfg()
        self.seed_core()
        self.seed_positions()

    def write_cfg(self, extra: str = "") -> None:
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: strategy\n" + extra, encoding="utf-8"
        )

    def seed_core(self) -> None:
        package = self.tmp / "seo" / "research-package"
        package.mkdir(parents=True, exist_ok=True)
        (package / "semantic-core.csv").write_text(
            "keyword,frequency,cluster_id,suggested_url\n"
            "купить вагонку,1000,vagonka,/catalog/vagonka/\n"
            "вагонка штиль,500,vagonka,/catalog/shtil/\n"
            "имитация бруса,800,brus,/catalog/brus/\n",
            encoding="utf-8",
        )

    def seed_positions(self, clicks: tuple[int, int] = (120, 30)) -> None:
        db = self.tmp / "seo" / "seo.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db)
        conn.execute("DROP TABLE IF EXISTS positions")
        conn.execute("""CREATE TABLE positions (snapshot_date TEXT, engine TEXT, query TEXT,
                        position REAL, clicks INTEGER, impressions INTEGER, url TEXT)""")
        conn.execute("INSERT INTO positions VALUES ('2026-07-01','yandex','купить вагонку',3.0,?,4000,'/catalog/vagonka/')",
                     (clicks[0],))
        conn.execute("INSERT INTO positions VALUES ('2026-07-01','yandex','вагонка штиль',15.0,?,900,'/catalog/shtil/')",
                     (clicks[1],))
        conn.commit()
        conn.close()

    def run_script(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args, "--format", "json"],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
        )


class ForecastTest(StrategyTestBase):
    def test_scenarios_ordered_and_upside_computed(self) -> None:
        proc = self.run_script("seo-forecast.py", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["inputs"]["keywords"], 3)
        self.assertEqual(report["inputs"]["keywords_ranked"], 2)
        current = report["scenarios"]["current"]["monthly_clicks"]
        top10 = report["scenarios"]["target_top10"]["monthly_clicks"]
        top3 = report["scenarios"]["target_top3"]["monthly_clicks"]
        self.assertLess(current, top10)
        self.assertLess(top10, top3)
        # current: 1000*0.10 (pos3) + 500*0.01 (pos15) + 800*0.002 (unranked) = 106.6 → 107
        self.assertEqual(current, 107)
        self.assertTrue(report["cluster_upside_top10"])
        self.assertEqual(len(report["monthly_ramp_to_top10"]), 6)
        self.assertTrue((self.tmp / "seo" / "strategy" / "seo-forecast.md").exists())

    def test_ctr_curve_override(self) -> None:
        self.write_cfg("kpi:\n  ctr_curve:\n    \"3\": 0.5\n")
        proc = self.run_script("seo-forecast.py")
        report = json.loads(proc.stdout)
        # 1000*0.5 + 500*0.01 + 800*0.002 = 506.6 → 507
        self.assertEqual(report["scenarios"]["current"]["monthly_clicks"], 507)


class KpiContractTest(StrategyTestBase):
    def kpi_cfg(self, clicks_goal: int) -> str:
        today = dt.date.today()
        start = f"{today.year - (1 if today.month == 1 else 0):04d}-{(today.month - 2) % 12 + 1:02d}"
        deadline_month = today.month + 2
        deadline = f"{today.year + (deadline_month - 1) // 12:04d}-{(deadline_month - 1) % 12 + 1:02d}"
        return (
            "kpi:\n"
            "  enabled: true\n"
            f"  start: \"{start}\"\n"
            f"  deadline: \"{deadline}\"\n"
            "  tolerance_pct: 20\n"
            "  lead_conversion_rate: 0.05\n"
            "  goals:\n"
            f"    monthly_organic_clicks: {clicks_goal}\n"
            "    keywords_in_top10: 1\n"
        )

    def test_on_track_when_fact_meets_ramped_plan(self) -> None:
        self.write_cfg(self.kpi_cfg(clicks_goal=200))
        proc = self.run_script("kpi-contract.py", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["facts"]["monthly_organic_clicks"], 150.0)
        self.assertEqual(report["facts"]["keywords_in_top10"], 1)
        statuses = {row["goal"]: row["status"] for row in report["goals"]}
        self.assertEqual(statuses["keywords_in_top10"], "on_track")
        self.assertIn(report["overall_status"], {"on_track", "at_risk"})
        self.assertTrue((self.tmp / "seo" / "strategy" / "kpi-report.md").exists())

    def test_off_track_escalates_with_ticket_and_actions(self) -> None:
        self.write_cfg(self.kpi_cfg(clicks_goal=5000))
        self.seed_positions(clicks=(10, 2))
        proc = self.run_script("kpi-contract.py", "--write", "--escalate", "--fail-on-off-track")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["overall_status"], "off_track")
        self.assertTrue(report["corrective_actions"])
        self.assertTrue(report["escalation_ticket"])
        approvals = (self.tmp / "seo" / "pending-approvals.md").read_text(encoding="utf-8")
        self.assertIn("type:kpi_off_track", approvals)

    def test_no_goals_is_graceful(self) -> None:
        proc = self.run_script("kpi-contract.py")
        self.assertEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        self.assertEqual(report["overall_status"], "no_goals")
        self.assertIn("kpi", proc.stderr)


if __name__ == "__main__":
    unittest.main()
