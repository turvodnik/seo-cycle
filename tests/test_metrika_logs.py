#!/usr/bin/env python3
"""Tests for metrika-logs-fetch.py (offline TSV ingestion and summaries)."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

VISITS_TSV = "\t".join(
    ["ym:s:visitID", "ym:s:date", "ym:s:startURL", "ym:s:lastTrafficSource",
     "ym:s:pageViews", "ym:s:visitDuration", "ym:s:isNewUser", "ym:s:goalsID"]
) + "\n" + "\n".join(
    [
        "1\t2026-07-01\thttps://example.com/\torganic\t3\t120\t1\t[]",
        "2\t2026-07-01\thttps://example.com/catalog/\torganic\t5\t300\t0\t[101]",
        "3\t2026-07-02\thttps://example.com/\tdirect\t1\t20\t1\t[]",
    ]
) + "\n"


class MetrikaLogsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-metrika-logs-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: logs\n", encoding="utf-8")

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items() if not key.startswith("YANDEX_")}
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "metrika-logs-fetch.py"), *args],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_ingests_visits_tsv_and_summarizes(self) -> None:
        tsv = self.tmp / "visits.tsv"
        tsv.write_text(VISITS_TSV, encoding="utf-8")
        proc = self.run_script("--input-file", str(tsv), "--write", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)["summary"]
        self.assertEqual(summary["rows"], 3)
        self.assertEqual(summary["date_range"], ["2026-07-01", "2026-07-02"])
        self.assertEqual(summary["by_traffic_source"]["organic"], 2)
        self.assertEqual(summary["visits_with_goals"], 1)
        self.assertAlmostEqual(summary["new_users_share"], 0.667, places=3)
        self.assertTrue((self.tmp / "seo" / "analytics" / "metrika-logs-summary.md").exists())

    def test_no_input_is_graceful_hint(self) -> None:
        proc = self.run_script()
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--input-file", proc.stderr)

    def test_live_without_env_fails_before_network(self) -> None:
        proc = self.run_script("--live")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("YANDEX_METRIKA_COUNTER_ID", proc.stderr)


if __name__ == "__main__":
    unittest.main()
