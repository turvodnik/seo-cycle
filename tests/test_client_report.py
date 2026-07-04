#!/usr/bin/env python3
"""Tests for client-report.py (white-label monthly report)."""

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
  name: "Эмвуди"
  domain: emwoody.ru
agency:
  name: "Kometa Media"
  contact: "hello@kometa.media"
  accent_color: "#8B5E3C"
  footer_note: "Отчёт подготовлен автоматически и проверен специалистом."
kpi:
  goals:
    monthly_organic_clicks: 100
"""


class ClientReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-client-report-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")

    def seed_artifacts(self) -> None:
        strategy = self.tmp / "seo" / "strategy"
        strategy.mkdir(parents=True)
        (strategy / "kpi-report.json").write_text(json.dumps({
            "overall_status": "on_track",
            "contract": {"month": "2026-07"},
            "goals": [{"goal": "monthly_organic_clicks", "target": 100, "plan_this_month": 50,
                       "fact": 60.0, "delta_pct": 20.0, "status": "on_track"}],
            "corrective_actions": [],
        }), encoding="utf-8")
        (strategy / "seo-forecast.json").write_text(json.dumps({
            "scenarios": {"current": {"monthly_clicks": 107, "monthly_leads": 2.1},
                          "target_top10": {"monthly_clicks": 240, "monthly_leads": 4.8}},
            "cluster_upside_top10": [{"cluster": "vagonka", "upside_clicks": 90.0}],
        }), encoding="utf-8")
        db = self.tmp / "seo" / "seo.db"
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE positions (snapshot_date TEXT, engine TEXT, query TEXT,
                        position REAL, clicks INTEGER, impressions INTEGER, url TEXT)""")
        conn.execute("INSERT INTO positions VALUES ('2026-06-01','yandex','купить вагонку',6.0,40,900,'/a/')")
        conn.execute("INSERT INTO positions VALUES ('2026-07-01','yandex','купить вагонку',3.0,60,1000,'/a/')")
        conn.execute("INSERT INTO positions VALUES ('2026-07-01','yandex','вагонка штиль',9.0,10,300,'/b/')")
        conn.commit()
        conn.close()

    def run_report(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "client-report.py"), "--period", "2026-07", *args],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )

    def test_report_renders_sections_and_branding(self) -> None:
        self.seed_artifacts()
        proc = self.run_report("--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        markdown = proc.stdout
        self.assertIn("Эмвуди", markdown)
        self.assertIn("Kometa Media", markdown)
        self.assertIn("Видимость в поиске", markdown)
        self.assertIn("топ-10: **2 (+1)**", markdown)
        self.assertIn("KPI: план vs факт", markdown)
        self.assertIn("on_track", markdown)
        self.assertIn("Прогноз и потенциал", markdown)
        self.assertIn("Отчёт подготовлен автоматически", markdown)

        html_path = self.tmp / "seo" / "reports" / "client-report-2026-07.html"
        self.assertTrue(html_path.exists())
        html_body = html_path.read_text(encoding="utf-8")
        self.assertIn("#8B5E3C", html_body)
        self.assertIn("<table>", html_body)
        self.assertIn("</table>", html_body)
        self.assertIn("<h2>KPI: план vs факт</h2>", html_body)
        self.assertNotIn("**", html_body)  # bold converted, not leaked
        self.assertTrue((self.tmp / "seo" / "reports" / "latest-client-report.html").exists())

    def test_empty_project_omits_sections_gracefully(self) -> None:
        proc = self.run_report()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Данных за период пока нет", proc.stdout)
        self.assertNotIn("KPI: план vs факт", proc.stdout)

    def test_json_format_lists_sections(self) -> None:
        self.seed_artifacts()
        proc = self.run_report("--format", "json")
        report = json.loads(proc.stdout)
        ids = [section["id"] for section in report["sections"]]
        self.assertEqual(ids[0], "positions")
        self.assertIn("kpi", ids)
        self.assertIn("forecast", ids)


if __name__ == "__main__":
    unittest.main()
