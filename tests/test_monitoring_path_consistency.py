#!/usr/bin/env python3
"""T-052 review R3: `monitoring.path` must be honored by all three consumers.

Before this fix `monthly-dashboard.py` was the only reader of the config key;
`pulse.py` always wrote into the hardcoded `seo/monitoring`, and
`seo_cycle_cli.py` doctor/status always measured freshness there too — so a
project that set `monitoring.path` got a setting that silently worked for
one out of three tools. This test proves the three now agree: pulse writes
a snapshot at the CONFIGURED path, and doctor/dashboard find it there (not
at the default `seo/monitoring`, which stays empty).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

pulse_spec = importlib.util.spec_from_file_location("monitoring_consistency_pulse", SCRIPTS / "pulse.py")
pulse = importlib.util.module_from_spec(pulse_spec)
pulse_spec.loader.exec_module(pulse)

cli_spec = importlib.util.spec_from_file_location("monitoring_consistency_cli", SCRIPTS / "seo_cycle_cli.py")
cli = importlib.util.module_from_spec(cli_spec)
cli_spec.loader.exec_module(cli)

dashboard_spec = importlib.util.spec_from_file_location(
    "monitoring_consistency_dashboard", SCRIPTS / "monthly-dashboard.py")
dashboard = importlib.util.module_from_spec(dashboard_spec)
dashboard_spec.loader.exec_module(dashboard)

FAKE_SOURCES = [("webmaster", "webmaster-fetch.py", ["--days", "14"])]


def make_fake_run_step(root: pathlib.Path):
    """Simulates a real fetch+snapshot-build run: writes an actual snapshot
    JSON at whatever --output path pulse.py passes, so the file really lands
    under monitoring_dir(cfg, root)."""
    def fake_run_step(script, args, cwd, env, timeout=180):
        if "--output" in args:
            out = pathlib.Path(args[args.index("--output") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({
                "period": {"start": "2026-09-01", "end": "2026-09-01"},
                "sources": [{"source": "webmaster"}], "queries": [], "pages": [],
            }), encoding="utf-8")
        return 0, "", ""
    return fake_run_step


class MonitoringPathConsistencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-monitoring-consistency-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: consistency-test\nmonitoring:\n  path: custom/mon\n", encoding="utf-8")

    def test_pulse_writes_and_doctor_dashboard_find_it_at_configured_path(self) -> None:
        cfg_path = self.tmp / "seo-cycle.yaml"
        cfg = cli.load_yaml(cfg_path)

        with mock.patch.object(pulse, "configured_sources", return_value=FAKE_SOURCES), \
             mock.patch.object(pulse, "run_step", make_fake_run_step(self.tmp)):
            report, rc = pulse.pulse_project(cfg_path, _Args(days=0, skip_fetch=False))
        self.assertEqual(rc, 0, report)

        # Не в дефолтном seo/monitoring — только в настроенном custom/mon.
        self.assertFalse((self.tmp / "seo" / "monitoring").exists()
                         and any((self.tmp / "seo" / "monitoring").glob("*snapshot*.json")))
        written = list((self.tmp / "custom" / "mon").glob("*snapshot*.json"))
        self.assertEqual(len(written), 1, written)

        snap, age = cli.newest_snapshot(self.tmp, cfg)
        self.assertIsNotNone(snap)
        self.assertEqual(snap.parent, self.tmp / "custom" / "mon")

        found = dashboard.load_latest_snapshot(
            [dashboard.monitoring_dir(cfg, self.tmp), self.tmp / "seo" / "09-monitoring"])
        self.assertIsNotNone(found)
        self.assertEqual(pathlib.Path(found["path"]).parent, self.tmp / "custom" / "mon")


class _Args:
    def __init__(self, days: int, skip_fetch: bool) -> None:
        self.days = days
        self.skip_fetch = skip_fetch


if __name__ == "__main__":
    unittest.main()
