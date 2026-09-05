#!/usr/bin/env python3
"""T-052 review (R1, R3, mask hardening) — seo_cycle_core.monitoring.

Single source of truth for the monitoring snapshot directory and the "which
snapshot is newest" pick, shared by pulse.py (writer), seo_cycle_cli.py
doctor/status and monthly-dashboard.py (readers). Regression coverage for
the three review findings:

- R1: ranking must use the DATE ENCODED IN THE FILENAME first, not mtime —
  after a `git clone`/directory copy every file's mtime collapses to nearly
  the same instant, so mtime-only ranking can pick the wrong (older) file.
- mask hardening: a file that merely contains the word "snapshot" in its
  name (e.g. a neighbouring `triggers-snapshot-<date>.json`, observed live
  on gsse.ru) must NOT be mistaken for a monitoring-data snapshot.
- R3: `monitoring.path` is resolved in exactly one place, consumed by every
  caller — this file tests that place directly.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.monitoring import (  # noqa: E402
    find_latest_snapshot,
    is_snapshot_filename,
    monitoring_dir,
)


class IsSnapshotFilenameTest(unittest.TestCase):
    def test_v2_source_prefixed_names_accepted(self) -> None:
        for name in ("webmaster-snapshot-2026-09-01.json", "gsc-snapshot-2026-01-05.json",
                     "ga4-snapshot-2026-12-31.json", "metrika-snapshot-2026-06-15.json",
                     "psi-snapshot-2026-02-02.json"):
            self.assertTrue(is_snapshot_filename(name), name)

    def test_v1_date_prefixed_name_accepted(self) -> None:
        self.assertTrue(is_snapshot_filename("2026-07-04-snapshot.json"))

    def test_v1_source_only_name_accepted(self) -> None:
        self.assertTrue(is_snapshot_filename("gsc-snapshot.json"))

    def test_unrelated_service_file_rejected(self) -> None:
        # Живой случай (gsse.ru, 05.09): соседняя сессия оставила
        # triggers-snapshot-2026-09-05.json рядом с реальными срезами —
        # он не имеет отношения к данным мониторинга.
        self.assertFalse(is_snapshot_filename("triggers-snapshot-2026-09-05.json"))

    def test_random_word_before_snapshot_rejected(self) -> None:
        self.assertFalse(is_snapshot_filename("backup-snapshot-2026-09-05.json"))
        self.assertFalse(is_snapshot_filename("db-snapshot.json"))

    def test_not_a_snapshot_name_at_all_rejected(self) -> None:
        self.assertFalse(is_snapshot_filename("webmaster-raw-2026-09-01.json"))
        self.assertFalse(is_snapshot_filename("snapshot.json"))


class MonitoringDirTest(unittest.TestCase):
    def test_default_is_seo_monitoring(self) -> None:
        root = pathlib.Path("/tmp/does-not-need-to-exist")
        self.assertEqual(monitoring_dir({}, root), root / "seo" / "monitoring")

    def test_configured_path_wins(self) -> None:
        root = pathlib.Path("/tmp/does-not-need-to-exist")
        cfg = {"monitoring": {"path": "custom/mon"}}
        self.assertEqual(monitoring_dir(cfg, root), root / "custom" / "mon")


class FindLatestSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-monitoring-picker-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def touch(self, name: str, mtime: float | None = None) -> pathlib.Path:
        p = self.tmp / name
        p.write_text("{}", encoding="utf-8")
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def test_prefers_date_in_name_over_mtime_after_simulated_clone(self) -> None:
        # R1: fixture must actually DISCRIMINATE date-based ranking from
        # mtime-based ranking, not just happen to agree with it. Equal mtimes
        # (the original "simulated git clone" fixture) left both the deciding
        # line (`key=(date, mtime)` -> `key=mtime`) and the date-extraction
        # line (`date_key = ...` -> `""`) green: with a tie, `max()` returns
        # the first candidate in iteration order, which happened to be the
        # right file by luck of glob() ordering — the test passed by
        # coincidence, not because it exercised the ranking (review, круг 3).
        # Fix: give the OLDER-dated file the NEWER mtime and vice versa, so a
        # date-blind (mtime-only) pick provably returns the WRONG file.
        now = time.time()
        older_by_date_but_newer_mtime = self.touch("webmaster-snapshot-2026-07-01.json", mtime=now)
        newer = self.touch("webmaster-snapshot-2026-09-01.json", mtime=now - 100_000)
        found = find_latest_snapshot([self.tmp])
        self.assertEqual(found, newer)
        self.assertNotEqual(found, older_by_date_but_newer_mtime)

    def test_mtime_is_only_a_tiebreak_for_equal_dates(self) -> None:
        now = time.time()
        older_write = self.touch("webmaster-snapshot-2026-09-01.json", mtime=now - 100)
        newer_write = self.touch("gsc-snapshot-2026-09-01.json", mtime=now)
        found = find_latest_snapshot([self.tmp])
        self.assertEqual(found, newer_write)
        self.assertNotEqual(found, older_write)

    def test_ignores_unrelated_snapshot_named_file_even_if_newest(self) -> None:
        # Живой баг: triggers-snapshot-<дата более новая>.json не должен
        # побеждать настоящий срез Вебмастера только потому что он "свежее".
        real = self.touch("webmaster-snapshot-2026-08-28.json", mtime=time.time() - 700000)
        self.touch("triggers-snapshot-2026-09-05.json", mtime=time.time())
        found = find_latest_snapshot([self.tmp])
        self.assertEqual(found, real)

    def test_falls_back_to_date_less_file_when_alone(self) -> None:
        only = self.touch("gsc-snapshot.json")
        found = find_latest_snapshot([self.tmp])
        self.assertEqual(found, only)

    def test_empty_dir_returns_none(self) -> None:
        self.assertIsNone(find_latest_snapshot([self.tmp]))

    def test_quarantine_and_invalid_dirs_excluded(self) -> None:
        self.touch("webmaster-snapshot-2026-09-01.json")
        quarantine_dir = self.tmp / "quarantine"
        quarantine_dir.mkdir()
        (quarantine_dir / "webmaster-snapshot-2026-12-31.json").write_text("{}", encoding="utf-8")
        found = find_latest_snapshot([self.tmp, quarantine_dir])
        self.assertEqual(found.name, "webmaster-snapshot-2026-09-01.json")


if __name__ == "__main__":
    unittest.main()
