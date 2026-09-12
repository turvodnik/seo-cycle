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
    def test_webmaster_ready_needs_only_token(self) -> None:
        # user_id/host_id выводятся из API — токена достаточно (zero-config проекты)
        self.assertFalse(pulse.webmaster_ready({}))
        self.assertFalse(pulse.webmaster_ready({"YANDEX_WEBMASTER_USER_ID": "42"}))
        self.assertTrue(pulse.webmaster_ready({"YANDEX_OAUTH_TOKEN": "t"}))

    def test_gsc_ready_needs_credentials_and_site(self) -> None:
        self.assertFalse(pulse.gsc_ready({"GOOGLE_APPLICATION_CREDENTIALS": "/sa.json"}))
        self.assertFalse(pulse.gsc_ready({"GSC_SITE_URL": "sc-domain:x.eu"}))
        self.assertTrue(pulse.gsc_ready({"GOOGLE_APPLICATION_CREDENTIALS": "/sa.json",
                                         "GSC_SITE_URL": "sc-domain:x.eu"}))

    def test_configured_sources_covers_both_engines(self) -> None:
        env = {"YANDEX_OAUTH_TOKEN": "t",
               "GOOGLE_APPLICATION_CREDENTIALS": "/sa.json", "GSC_SITE_URL": "sc-domain:x.eu"}
        sources = pulse.configured_sources(env, "x.ru", 14)
        self.assertEqual([s[0] for s in sources], ["webmaster", "gsc"])
        self.assertIn("--domain", sources[0][2])   # webmaster получает домен для авто-host
        self.assertEqual(sources[1][1], "gsc-fetch.py")
        self.assertEqual(pulse.configured_sources({}, "x.ru", 14), [])
        gsc_only = pulse.configured_sources(
            {"GOOGLE_APPLICATION_CREDENTIALS": "/sa.json", "GSC_SITE_URL": "sc-domain:x.eu"},
            "", 28)
        self.assertEqual([s[0] for s in gsc_only], ["gsc"])

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
        # T-096: the alert reads ONLY the intersection block of position-progress
        def report(prev_top10: int, delta: int, raw_delta: int | None = None) -> dict:
            return {"latest": {"top10": prev_top10 + delta},
                    "delta_vs_previous": {"top10": raw_delta if raw_delta is not None else delta},
                    "overlap_vs_previous": {"queries": 480, "prev_top10": prev_top10,
                                            "top10": prev_top10 + delta, "delta_top10": delta}}
        finding = pulse.drop_finding(report(100, -10), 5.0)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["severity"], "critical")
        self.assertIn("10.0%", finding["message"])
        self.assertIn("по пересечению выборок (480 запросов)", finding["message"])
        self.assertIsNone(pulse.drop_finding(report(100, -2), 5.0))
        self.assertIsNone(pulse.drop_finding(report(100, 5), 5.0))
        first_snapshot = {"latest": {"top10": 100}, "delta_vs_previous": {}}
        self.assertIsNone(pulse.drop_finding(first_snapshot, 5.0))

    def test_drop_finding_ignores_sample_composition_change(self) -> None:
        # gsse.ru 2026-08-28: raw top-10 −8 was queries leaving the top-500 by
        # impressions, positions inside the intersection did not move → no alert
        composition_only = {"latest": {"top10": 92},
                            "delta_vs_previous": {"top10": -8},
                            "overlap_vs_previous": {"queries": 470, "prev_top10": 90,
                                                    "top10": 90, "delta_top10": 0}}
        self.assertIsNone(pulse.drop_finding(composition_only, 5.0))
        # a pre-T-096 progress.json (no overlap block) must not page either
        legacy = {"latest": {"top10": 90}, "delta_vs_previous": {"top10": -10}}
        self.assertIsNone(pulse.drop_finding(legacy, 5.0))

    def test_sample_size_from_config_reaches_fetchers(self) -> None:
        env = {"YANDEX_OAUTH_TOKEN": "t",
               "GOOGLE_APPLICATION_CREDENTIALS": "/sa.json", "GSC_SITE_URL": "sc-domain:x.eu"}
        # default: webmaster gets the explicit 500, gsc keeps its own row-limit
        self.assertEqual(pulse.sample_size({}), (500, False))
        default = pulse.configured_sources(env, "x.ru", 14, None, pulse.sample_size({}))
        self.assertIn("--limit", default[0][2])
        self.assertEqual(default[0][2][default[0][2].index("--limit") + 1], "500")
        self.assertNotIn("--row-limit", default[1][2])
        # explicit config: both fetchers obey it
        cfg = {"monitoring": {"sample": {"size": 300}}}
        self.assertEqual(pulse.sample_size(cfg), (300, True))
        explicit = pulse.configured_sources(env, "x.ru", 14, None, pulse.sample_size(cfg))
        self.assertEqual(explicit[0][2][explicit[0][2].index("--limit") + 1], "300")
        self.assertEqual(explicit[1][2][explicit[1][2].index("--row-limit") + 1], "300")
        # garbage falls back to the default, never to 0
        self.assertEqual(pulse.sample_size({"monitoring": {"sample": {"size": "loose"}}})[0], 500)
        self.assertEqual(pulse.sample_size({"monitoring": {"sample": {"size": -5}}})[0], 500)


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

    def test_global_walks_registry_and_skips_missing(self) -> None:
        # портфельный daily-джоб: два active-проекта + paused + битый путь
        self.write_snapshot(dt.date.today().isoformat())
        second = self.tmp / "second"
        second.mkdir()
        (second / "seo-cycle.yaml").write_text("project:\n  name: second\n", encoding="utf-8")
        registry = self.tmp / "registry.yaml"
        registry.write_text(json.dumps({"projects": [
            {"name": "pulse-test", "path": str(self.tmp), "status": "active"},
            {"name": "second", "path": str(second), "status": "active"},
            {"name": "paused", "path": str(self.tmp), "status": "paused"},
            {"name": "ghost", "path": str(self.tmp / "nope"), "status": "active"},
        ]}), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "pulse.py"), "--global", "--registry", str(registry),
             "--skip-fetch", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        reports = json.loads(proc.stdout)
        self.assertEqual([r["project"] for r in reports], ["pulse-test", "second"])
        self.assertIn("ghost", proc.stderr)  # пропуск честно объявлен
        # у пустого second — findings, у живого — свежий срез
        self.assertEqual(reports[0]["latest"]["top10"], 2)
        self.assertIn("no_snapshots", [f["id"] for f in reports[1]["findings"]])


if __name__ == "__main__":
    unittest.main()


class PulseEngineScopeTest(unittest.TestCase):
    """Источник опрашивается только если его движок включён в конфиге проекта.

    Регресс кросс-проектной утечки (2026-07-12): глобальный OAuth-токен агентства
    делал Вебмастер «настроенным» для любого проекта, включая eu-проект без Яндекса,
    и в его мониторинг попадали чужие яндексовые срезы.
    """

    ENV = {
        "YANDEX_OAUTH_TOKEN": "t",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/sa.json",
        "GSC_SITE_URL": "sc-domain:example.com",
    }

    def _names(self, engines):
        return [s[0] for s in pulse.configured_sources(self.ENV, "example.com", 14, engines)]

    def test_google_only_project_does_not_fetch_webmaster(self):
        self.assertEqual(self._names(["google", "bing"]), ["gsc"])

    def test_yandex_only_project_does_not_fetch_gsc(self):
        self.assertEqual(self._names(["yandex"]), ["webmaster"])

    def test_both_engines_keep_both_sources(self):
        self.assertEqual(self._names(["yandex", "google"]), ["webmaster", "gsc"])

    def test_no_engine_list_keeps_legacy_behaviour(self):
        self.assertEqual(self._names(None), ["webmaster", "gsc"])
