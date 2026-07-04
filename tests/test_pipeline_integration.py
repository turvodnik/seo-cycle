#!/usr/bin/env python3
"""Integration: fetch-format → snapshot-build → db-sync → position-progress.

Covers the seam class that bit us in v1.86.1 (raw provider formats silently
collapsing before they reach seo.db): the whole chain runs on real scripts
against a tmp project, no network.
"""

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

WEBMASTER_RAW_V4 = {
    "count": 3,
    "queries": [
        {"query_id": "a", "query_text": "купить вагонку",
         "indicators": {"TOTAL_SHOWS": 1000.0, "TOTAL_CLICKS": 40.0, "AVG_SHOW_POSITION": 3.4}},
        {"query_id": "b", "query_text": "вагонка штиль",
         "indicators": {"TOTAL_SHOWS": 300.0, "TOTAL_CLICKS": 5.0, "AVG_SHOW_POSITION": 12.0}},
        {"query_id": "c", "query_text": "вагонка цена",
         "indicators": {"TOTAL_SHOWS": 500.0, "TOTAL_CLICKS": 9.0, "AVG_SHOW_POSITION": 7.7}},
    ],
}

GSC_EXPORT = {
    "rows": [
        {"keys": ["купить вагонку"], "clicks": 12, "impressions": 400, "position": 6.1},
        {"keys": ["монтаж вагонки"], "clicks": 3, "impressions": 90, "position": 15.5},
    ],
}


class PipelineIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-pipe-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: pipe\n", encoding="utf-8")
        raw_dir = self.tmp / "seo" / "monitoring" / "raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "webmaster.json").write_text(json.dumps(WEBMASTER_RAW_V4, ensure_ascii=False),
                                                encoding="utf-8")
        (raw_dir / "gsc.json").write_text(json.dumps(GSC_EXPORT, ensure_ascii=False), encoding="utf-8")

    def run_step(self, name: str, *args: str) -> subprocess.CompletedProcess:
        proc = subprocess.run([sys.executable, str(SCRIPTS / name), *args],
                              cwd=self.tmp, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, f"{name} failed: {proc.stderr[-500:]}")
        return proc

    def test_webmaster_and_gsc_reach_progress(self) -> None:
        # 1. снапшоты из двух разных провайдерских форматов
        self.run_step("snapshot-build.py", "--source", "webmaster",
                      "--input", "seo/monitoring/raw/webmaster.json",
                      "--output", "seo/monitoring/webmaster-snapshot-2026-07-04.json")
        self.run_step("snapshot-build.py", "--source", "gsc",
                      "--input", "seo/monitoring/raw/gsc.json",
                      "--output", "seo/monitoring/gsc-snapshot-2026-07-04.json")
        # 2. db-sync собирает оба в positions
        self.run_step("db-sync.py")
        conn = sqlite3.connect(self.tmp / "seo" / "seo.db")
        rows = conn.execute("SELECT engine, COUNT(*) FROM positions GROUP BY engine ORDER BY engine").fetchall()
        conn.close()
        self.assertEqual(dict(rows), {"google": 2, "yandex": 3})
        # 3. position-progress видит агрегат и не падает
        proc = self.run_step("position-progress.py", "--format", "json")
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["latest"]["queries"], 4)      # 5 строк, 4 уникальных запроса
        self.assertEqual(report["latest"]["clicks"], 69)      # 40+5+9+12+3
        # per-engine фильтр работает от того же снапшота
        yandex = json.loads(self.run_step("position-progress.py", "--engine", "yandex",
                                          "--format", "json").stdout)
        self.assertEqual(yandex["latest"]["queries"], 3)


if __name__ == "__main__":
    unittest.main()
