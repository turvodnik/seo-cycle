#!/usr/bin/env python3
"""T-096 — the sample boundary: top-N by impressions is not the site.

Three facts every report must state and one lie none may tell:
  * «выборка N из M запросов сайта» (M from the source summary, else
    «M неизвестно») in position-progress / pulse / kpi-contract;
  * top-N deltas and the pulse alert only inside the intersection of two
    samples — a query that left the top-N is «выбыл из выборки», not a loss;
  * pre-T-096 snapshots (no `sample` block) still load, M unknown.
"""

from __future__ import annotations

import datetime as dt
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

from seo_cycle_core.monitoring import sample_line, snapshot_sample  # noqa: E402

CFG = "project:\n  name: sample-test\n  domain: example.ru\n"

# Same positions, different composition: «C» left the top-N (impressions fell
# below the cut), «D» entered at 25. Raw top-10 arithmetic says 3 → 2 (−33 %);
# inside the intersection {A, B} nothing moved.
PREV = [("вагонка купить", 3.0, 40, 900), ("вагонка штиль", 5.0, 20, 500), ("вагонка цена", 8.0, 10, 300)]
CURR = [("вагонка купить", 3.0, 42, 910), ("вагонка штиль", 5.0, 21, 520), ("вагонка кедр", 25.0, 1, 90)]


def write_snapshot(root: pathlib.Path, date: str, rows: list[tuple], *, available: int | None,
                   legacy: bool = False) -> pathlib.Path:
    path = root / "seo" / "monitoring" / f"webmaster-snapshot-{date}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "snapshot_date": date,
        "period": {"start": (dt.date.fromisoformat(date) - dt.timedelta(days=14)).isoformat(), "end": date},
        "sources": [{"source": "webmaster", "engine": "yandex"}],
        "queries": [{"query": q, "engine": "yandex", "position": pos, "clicks": clicks,
                     "impressions": imp, "url": "/x/"} for q, pos, clicks, imp in rows],
    }
    if not legacy:
        data.update({"metric_scope": "query_sample", "sitewide": False,
                     "sample": {"loaded_rows": len(rows), "available_rows": available}})
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def run(script: str, cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          cwd=cwd, text=True, capture_output=True, check=False)


class SampleHelperTest(unittest.TestCase):
    """In-process (coverage-core counts it), the helper every report shares."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-sample-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_known_total_and_unknown_total(self) -> None:
        write_snapshot(self.tmp, "2026-08-28", PREV, available=2160)
        write_snapshot(self.tmp, "2026-07-11", PREV, available=None, legacy=True)
        known = snapshot_sample({}, self.tmp, "2026-08-28")
        self.assertEqual((known["loaded"], known["available"], known["files"]), (3, 2160, 1))
        self.assertEqual(sample_line(known), "выборка 3 из 2160 запросов сайта")
        legacy = snapshot_sample({}, self.tmp, "2026-07-11")
        self.assertEqual((legacy["loaded"], legacy["available"]), (3, None))
        self.assertEqual(sample_line(legacy), "выборка 3 из M запросов сайта (M неизвестно)")
        missing = snapshot_sample({}, self.tmp, "2000-01-01")
        self.assertEqual(missing, {"loaded": None, "available": None, "sources": [], "files": 0})
        self.assertEqual(sample_line(missing, 500), "выборка 500 из M запросов сайта (M неизвестно)")

    def test_merged_sources_sum_loaded_but_total_needs_every_source(self) -> None:
        # gsc never reports a total → M unknown for the date as a whole
        write_snapshot(self.tmp, "2026-09-01", PREV, available=2000)
        gsc = self.tmp / "seo" / "monitoring" / "gsc-snapshot-2026-09-01.json"
        gsc.write_text(json.dumps({
            "snapshot_date": "2026-09-01", "sources": [{"source": "gsc", "engine": "google"}],
            "metric_scope": "query_sample", "sitewide": False,
            "sample": {"loaded_rows": 2, "available_rows": None},
            "queries": [{"query": "a", "engine": "google", "position": 4.0},
                        {"query": "b", "engine": "google", "position": 9.0}],
        }), encoding="utf-8")
        both = snapshot_sample({}, self.tmp, "2026-09-01")
        self.assertEqual((both["loaded"], both["available"], both["files"]), (5, None, 2))
        yandex_only = snapshot_sample({}, self.tmp, "2026-09-01", engine="yandex")
        self.assertEqual((yandex_only["loaded"], yandex_only["available"]), (3, 2000))

    def test_non_snapshot_files_and_quarantine_are_ignored(self) -> None:
        write_snapshot(self.tmp, "2026-09-01", PREV, available=2000)
        stray = self.tmp / "seo" / "monitoring" / "triggers-snapshot-2026-09-01.json"
        stray.write_text(json.dumps({"snapshot_date": "2026-09-01", "queries": [{}] * 29000,
                                     "sample": {"loaded_rows": 29000, "available_rows": 29000}}),
                         encoding="utf-8")
        q = self.tmp / "seo" / "monitoring" / "quarantine" / "webmaster-snapshot-2026-09-01.json"
        q.parent.mkdir(parents=True)
        q.write_text(json.dumps({"snapshot_date": "2026-09-01", "queries": [{}] * 7}), encoding="utf-8")
        sample = snapshot_sample({}, self.tmp, "2026-09-01")
        self.assertEqual((sample["loaded"], sample["available"], sample["files"]), (3, 2000, 1))

    def test_gsc_normalizer_marks_the_sample(self) -> None:
        raw = self.tmp / "gsc.json"
        raw.write_text(json.dumps({"rows": [{"keys": ["a", "/p/"], "clicks": 1, "impressions": 10,
                                             "ctr": 0.1, "position": 3.2}]}), encoding="utf-8")
        out = self.tmp / "gsc-snapshot-2026-09-01.json"
        proc = run("snapshot-build.py", self.tmp, "--source", "gsc", "--input", str(raw), "--output", str(out))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        snap = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(snap["metric_scope"], "query_sample")
        self.assertFalse(snap["sitewide"])
        self.assertEqual(snap["sample"], {"loaded_rows": 1, "available_rows": None})


class CompositionChangeTest(unittest.TestCase):
    """The fixture from the ticket: same positions, different top-N composition."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-composition-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")
        self.today = dt.date.today()
        self.prev_date = (self.today - dt.timedelta(days=7)).isoformat()
        write_snapshot(self.tmp, self.prev_date, PREV, available=2400)
        write_snapshot(self.tmp, self.today.isoformat(), CURR, available=2416)
        proc = run("db-sync.py", self.tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_progress_reports_zero_loss_and_prints_intersection(self) -> None:
        proc = run("position-progress.py", self.tmp, "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        # raw arithmetic still says −1 (kept for compatibility, labelled as composition)
        self.assertEqual(report["delta_vs_previous"]["top10"], -1)
        overlap = report["overlap_vs_previous"]
        self.assertEqual(overlap["queries"], 2)
        self.assertEqual((overlap["prev_top10"], overlap["top10"], overlap["delta_top10"]), (2, 2, 0))
        self.assertEqual((overlap["prev_only"], overlap["curr_only"]), (1, 1))
        self.assertEqual(report["sample"]["available"], 2416)
        self.assertEqual(report["sample_line"], "выборка 3 из 2416 запросов сайта")

        md = run("position-progress.py", self.tmp).stdout
        top_line = next(line for line in md.splitlines() if line.startswith("- **Топ-3"))
        self.assertNotIn("↓", top_line, top_line)
        self.assertIn("дельты по пересечению выборок: 2 запросов", top_line)
        self.assertIn("выборка 3 из 2416 запросов сайта", md)
        self.assertIn("сырая разница топ-10 -1 (состав выборки, не позиции)", md)
        self.assertIn("выбыли из выборки: 1", md)
        self.assertIn("выбыл из выборки «вагонка цена»", md)
        self.assertNotIn("lost «", md)

    def test_pulse_does_not_alert_and_prints_sample(self) -> None:
        proc = run("pulse.py", self.tmp, "--skip-fetch", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertNotIn("top10_drop", [f["id"] for f in report["findings"]])
        self.assertEqual(report["overlap_vs_previous"]["delta_top10"], 0)
        self.assertEqual(report["sample_line"], "выборка 3 из 2416 запросов сайта")
        md = run("pulse.py", self.tmp, "--skip-fetch").stdout
        self.assertIn("выборка 3 из 2416 запросов сайта", md)

    def test_pulse_still_alerts_on_a_real_drop_inside_the_intersection(self) -> None:
        # control: the same two queries stay in the sample but fall out of top-10
        fallen = [("вагонка купить", 14.0, 4, 900), ("вагонка штиль", 12.0, 2, 520), ("вагонка кедр", 25.0, 1, 90)]
        write_snapshot(self.tmp, self.today.isoformat(), fallen, available=2416)
        proc = run("pulse.py", self.tmp, "--skip-fetch", "--format", "json")
        self.assertEqual(proc.returncode, 1, proc.stderr)
        report = json.loads(proc.stdout)
        drop = next(f for f in report["findings"] if f["id"] == "top10_drop")
        self.assertIn("2 запросов из 2 (100.0%) по пересечению выборок (2 запросов)", drop["message"])

    def test_kpi_prints_sample_boundary(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text(
            CFG + "kpi:\n  enabled: true\n  goals:\n    keywords_in_top10: 10\n", encoding="utf-8")
        proc = run("kpi-contract.py", self.tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("выборка 3 из 2416 запросов сайта", proc.stdout)
        self.assertIn("Fact (по выборке топ-N)", proc.stdout)
        as_json = json.loads(run("kpi-contract.py", self.tmp, "--format", "json").stdout)
        self.assertEqual(as_json["facts"]["metric_scope"], "query_sample")
        self.assertEqual(as_json["facts"]["sample"]["available"], 2416)


class LegacySnapshotTest(unittest.TestCase):
    """Old `gsc-snapshot-*.json` / `webmaster-snapshot-*.json` without a `sample` block."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-legacy-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")
        write_snapshot(self.tmp, dt.date.today().isoformat(), PREV, available=None, legacy=True)
        self.assertEqual(run("db-sync.py", self.tmp).returncode, 0)

    def test_every_report_says_m_unknown(self) -> None:
        expected = "выборка 3 из M запросов сайта (M неизвестно)"
        self.assertIn(expected, run("position-progress.py", self.tmp).stdout)
        self.assertIn(expected, run("pulse.py", self.tmp, "--skip-fetch").stdout)
        (self.tmp / "seo-cycle.yaml").write_text(
            CFG + "kpi:\n  enabled: true\n  goals:\n    keywords_in_top10: 10\n", encoding="utf-8")
        self.assertIn(expected, run("kpi-contract.py", self.tmp).stdout)
        forecast = run("seo-forecast.py", self.tmp).stdout
        self.assertIn(expected, forecast)


if __name__ == "__main__":
    unittest.main()
