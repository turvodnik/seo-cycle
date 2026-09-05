#!/usr/bin/env python3
"""T-052 / I-060: monthly-dashboard.py must find the actual monitoring layout.

Bug: `load_latest_snapshot` searched a hardcoded `09-monitoring/` (v1 layout)
with the mask `*-snapshot.json`. v2 projects (emwoody, gsse, pifagorlab) keep
snapshots at `seo/monitoring/webmaster-snapshot-<date>.json` — the date comes
AFTER "snapshot", so the old mask never matched, and the dashboard always
printed "Snapshot не найден" even on a project with a snapshot from a minute
ago. Fixed: search dir comes from `monitoring.path` in seo-cycle.yaml
(falling back to `seo/monitoring`, then the v1 `seo/09-monitoring`), mask is
`*snapshot*.json`.
"""

from __future__ import annotations

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

spec = importlib.util.spec_from_file_location("monthly_dashboard", SCRIPTS / "monthly-dashboard.py")
dashboard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard)


def write_snapshot(path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "period": {"start": "2026-08-01", "end": "2026-09-01"},
        "sources": [{"source": "webmaster"}],
        "queries": [{"query": "a"}],
        "pages": [],
    }, ensure_ascii=False), encoding="utf-8")


class LoadLatestSnapshotUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dashboard-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_v2_layout_date_after_snapshot_word(self) -> None:
        write_snapshot(self.tmp / "seo" / "monitoring" / "webmaster-snapshot-2026-09-01.json")
        found = dashboard.load_latest_snapshot([self.tmp / "seo" / "monitoring"])
        self.assertIsNotNone(found)
        self.assertIn("webmaster-snapshot-2026-09-01.json", found["path"])

    def test_v1_layout_still_found_as_fallback(self) -> None:
        write_snapshot(self.tmp / "seo" / "09-monitoring" / "gsc-snapshot.json")
        found = dashboard.load_latest_snapshot(
            [self.tmp / "seo" / "monitoring", self.tmp / "seo" / "09-monitoring"])
        self.assertIsNotNone(found)
        self.assertIn("gsc-snapshot.json", found["path"])

    def test_empty_returns_none(self) -> None:
        found = dashboard.load_latest_snapshot([self.tmp / "seo" / "monitoring"])
        self.assertIsNone(found)

    def test_newest_wins_across_dirs(self) -> None:
        write_snapshot(self.tmp / "seo" / "09-monitoring" / "old-snapshot.json")
        newer = self.tmp / "seo" / "monitoring" / "webmaster-snapshot-2026-09-05.json"
        write_snapshot(newer)
        import os
        import time
        os.utime(newer, (time.time() + 10, time.time() + 10))
        found = dashboard.load_latest_snapshot(
            [self.tmp / "seo" / "monitoring", self.tmp / "seo" / "09-monitoring"])
        self.assertIn("webmaster-snapshot-2026-09-05.json", found["path"])


class DashboardEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dashboard-e2e-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def run_dashboard(self) -> str:
        out = self.tmp / "out.md"
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "monthly-dashboard.py"), "--output", str(out)],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return out.read_text(encoding="utf-8")

    def test_v2_project_shows_snapshot_not_not_found(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: v2\n", encoding="utf-8")
        write_snapshot(self.tmp / "seo" / "monitoring" / "webmaster-snapshot-2026-09-01.json")
        md = self.run_dashboard()
        self.assertNotIn("Snapshot не найден", md)
        self.assertIn("2026-08-01", md)  # период снапшота напечатан

    def test_v1_project_still_finds_snapshot(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: v1\n", encoding="utf-8")
        write_snapshot(self.tmp / "seo" / "09-monitoring" / "gsc-snapshot.json")
        md = self.run_dashboard()
        self.assertNotIn("Snapshot не найден", md)

    def test_honest_message_when_nothing_found_names_search_dirs(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: empty\n", encoding="utf-8")
        md = self.run_dashboard()
        self.assertIn("Snapshot не найден", md)
        self.assertIn("seo/monitoring", md)
        self.assertIn("seo/09-monitoring", md)

    def test_configured_monitoring_path_takes_priority(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: custom\nmonitoring:\n  path: seo/custom-monitoring\n", encoding="utf-8")
        write_snapshot(self.tmp / "seo" / "custom-monitoring" / "webmaster-snapshot-2026-09-01.json")
        md = self.run_dashboard()
        self.assertNotIn("Snapshot не найден", md)


if __name__ == "__main__":
    unittest.main()
