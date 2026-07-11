#!/usr/bin/env python3
"""Regression: snapshot-build must accept webmaster-fetch's raw API v4 format."""

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

RAW_V4 = {
    "count": 2,
    "date_from": "2026-06-27",
    "date_to": "2026-07-09",
    "queries": [
        {"query_id": "a1", "query_text": "как затирать швы",
         "indicators": {"TOTAL_SHOWS": 177.0, "TOTAL_CLICKS": 2.0,
                        "AVG_SHOW_POSITION": 5.2}},
        {"query_id": "b2", "query_text": "затирка для плитки",
         "indicators": {"TOTAL_SHOWS": 90.0, "TOTAL_CLICKS": 5.0,
                        "AVG_SHOW_POSITION": 3.0}},
        # боевой gsse-кейс: у молодого хоста API отдаёт null-индикаторы
        {"query_id": "c3", "query_text": "новый запрос без данных",
         "indicators": {"TOTAL_SHOWS": None, "TOTAL_CLICKS": None,
                        "AVG_SHOW_POSITION": None}},
    ],
}


class SnapshotWebmasterTest(unittest.TestCase):
    def test_raw_api_v4_and_flat_formats(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-snapshot-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "raw.json").write_text(json.dumps(RAW_V4, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "snapshot-build.py"), "--source", "webmaster",
             "--input", "raw.json", "--output", "snap.json"],
            cwd=tmp, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        snap = json.loads((tmp / "snap.json").read_text(encoding="utf-8"))
        queries = {q["query"]: q for q in snap["queries"]}
        self.assertEqual(len(queries), 3)
        self.assertEqual(queries["новый запрос без данных"]["impressions"], 0)
        self.assertEqual(queries["новый запрос без данных"]["position"], 0.0)
        self.assertEqual(queries["как затирать швы"]["impressions"], 177)
        self.assertEqual(queries["как затирать швы"]["clicks"], 2)
        self.assertAlmostEqual(queries["как затирать швы"]["position"], 5.2)
        # окно выборки из raw echo — без него kpi-contract не нормирует клики к месяцу
        self.assertEqual(snap["period"], {"start": "2026-06-27", "end": "2026-07-09"})
        # плоский формат по-прежнему работает
        flat = {"rows": [{"query": "флэт", "shows": 10, "clicks": 1, "position": 4.0}]}
        (tmp / "flat.json").write_text(json.dumps(flat, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "snapshot-build.py"), "--source", "webmaster",
             "--input", "flat.json", "--output", "snap2.json"],
            cwd=tmp, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        snap2 = json.loads((tmp / "snap2.json").read_text(encoding="utf-8"))
        self.assertEqual(snap2["queries"][0]["query"], "флэт")


if __name__ == "__main__":
    unittest.main()
