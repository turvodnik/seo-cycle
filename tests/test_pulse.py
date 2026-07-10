#!/usr/bin/env python3
"""Tests for pulse.py — the daily data pipeline with freshness findings."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("pulse", SCRIPTS / "pulse.py")
pulse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pulse)


class PulseUnitTest(unittest.TestCase):
    def test_webmaster_ready_requires_all_three(self) -> None:
        env = {"YANDEX_OAUTH_TOKEN": "t", "YANDEX_HOST_ID": "https:x.ru:443"}
        self.assertFalse(pulse.webmaster_ready(env))
        env["YANDEX_WEBMASTER_USER_ID"] = "42"
        self.assertTrue(pulse.webmaster_ready(env))

    def test_freshness_gradation(self) -> None:
        today = dt.date(2026, 7, 10)
        self.assertEqual(pulse.freshness_findings("2026-07-10", today, 3), [])
        self.assertEqual(pulse.freshness_findings("2026-07-08", today, 3), [])
        warning = pulse.freshness_findings("2026-07-05", today, 3)
        self.assertEqual([f["severity"] for f in warning], ["warning"])
        error = pulse.freshness_findings("2026-06-20", today, 3)
        self.assertEqual([f["severity"] for f in error], ["error"])
        empty = pulse.freshness_findings("", today, 3)
        self.assertEqual([f["id"] for f in empty], ["no_snapshots"])

    def test_drop_finding_threshold(self) -> None:
        report = {"latest": {"top10": 90}, "delta_vs_previous": {"top10": -10}}
        finding = pulse.drop_finding(report, 5.0)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["severity"], "critical")
        self.assertIn("10.0%", finding["message"])
        small = {"latest": {"top10": 98}, "delta_vs_previous": {"top10": -2}}
        self.assertIsNone(pulse.drop_finding(small, 5.0))
        growth = {"latest": {"top10": 105}, "delta_vs_previous": {"top10": 5}}
        self.assertIsNone(pulse.drop_finding(growth, 5.0))
        first_snapshot = {"latest": {"top10": 100}, "delta_vs_previous": {}}
        self.assertIsNone(pulse.drop_finding(first_snapshot, 5.0))


class PulseE2ETest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-pulse-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: pulse-test\n", encoding="utf-8")

    def write_snapshot(self, date: str) -> None:
        path = self.tmp / "seo" / "monitoring" / f"webmaster-snapshot-{date}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "snapshot_date": date,
            "period": {"start": None, "end": date},
            "sources": [{"source": "webmaster", "engine": "yandex"}],
            "queries": [
                {"query": "купить вагонку", "engine": "yandex", "position": 3.0,
                 "clicks": 20, "impressions": 400, "url": "/catalog/vagonka/"},
                {"query": "осп плита", "engine": "yandex", "position": 8.0,
                 "clicks": 5, "impressions": 300, "url": "/catalog/osp/"},
            ],
        }, ensure_ascii=False), encoding="utf-8")

    def run_pulse(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "pulse.py"), "--skip-fetch", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )

    def test_fresh_snapshot_pipeline_scores_clean(self) -> None:
        self.write_snapshot(dt.date.today().isoformat())
        proc = self.run_pulse()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        steps = {step["step"]: step["ok"] for step in report["steps"]}
        self.assertTrue(steps["db-sync"])
        self.assertTrue(steps["progress"])
        self.assertEqual(report["latest"]["top10"], 2)
        self.assertNotIn("stale_snapshot", [f["id"] for f in report["findings"]])
        self.assertEqual(report["score"], 10.0)
        latest = json.loads((self.tmp / "seo" / "scorecards" / "latest.json").read_text(encoding="utf-8"))
        self.assertIn("pulse", latest)
        self.assertTrue((self.tmp / "seo" / "reports" / "position-progress.html").exists())

    def test_stale_snapshot_flagged_but_not_fatal(self) -> None:
        self.write_snapshot((dt.date.today() - dt.timedelta(days=20)).isoformat())
        proc = self.run_pulse()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        by_id = {f["id"]: f["severity"] for f in report["findings"]}
        self.assertEqual(by_id.get("stale_snapshot"), "error")
        self.assertLess(report["score"], 10.0)

    def test_empty_project_reports_no_snapshots(self) -> None:
        proc = self.run_pulse()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertIn("no_snapshots", [f["id"] for f in report["findings"]])


if __name__ == "__main__":
    unittest.main()
