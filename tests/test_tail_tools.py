#!/usr/bin/env python3
"""Tests for v1.86 tail: woo YML feed, РСЯ drafts, forecast intervals, token age."""

from __future__ import annotations

import datetime as dt
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

WOO_PRODUCTS = [
    {"id": 11, "name": "Вагонка штиль 14x121", "permalink": "https://shop.ru/vagonka-shtil/",
     "price": "980", "sku": "VS-14", "stock_status": "instock",
     "categories": [{"id": 5, "name": "Вагонка"}],
     "images": [{"src": "https://shop.ru/img/vs.jpg"}],
     "short_description": "<p>Лиственница, сорт <b>Экстра</b></p>"},
    {"id": 12, "name": "Планкен", "permalink": "https://shop.ru/planken/",
     "price": "1450", "stock_status": "outofstock",
     "categories": [{"id": 6, "name": "Планкен"}], "images": []},
    {"id": 13, "name": "Без цены", "permalink": "https://shop.ru/x/", "price": ""},
]


class WooYmlFeedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-woo-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: Магазин\n  url: https://shop.ru\n", encoding="utf-8")
        (self.tmp / "products.json").write_text(json.dumps(WOO_PRODUCTS), encoding="utf-8")

    def test_feed_from_input_file(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "woo-yml-feed.py"),
             "--input-file", "products.json", "--write"],
            cwd=self.tmp, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        feed = (self.tmp / "seo" / "feeds" / "yml-feed.xml").read_text(encoding="utf-8")
        self.assertIn("<yml_catalog", feed)
        self.assertIn('<offer id="11" available="true">', feed)
        self.assertIn('<offer id="12" available="false">', feed)
        self.assertNotIn("Без цены", feed)                       # без цены пропущен
        self.assertIn("<price>980</price>", feed)
        self.assertIn('<category id="5">Вагонка</category>', feed)
        self.assertIn("<vendorCode>VS-14</vendorCode>", feed)
        self.assertIn("Лиственница, сорт Экстра", feed)          # html вычищен
        self.assertIn("пропущено без цены/URL: 1", proc.stderr)

    def test_network_off_by_default(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "woo-yml-feed.py")],
            cwd=self.tmp, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--live", proc.stderr)


def seed_ads_package(root: pathlib.Path) -> pathlib.Path:
    package = root / "seo" / "research-package"
    package.mkdir(parents=True)
    (package / "semantic-architecture-final.json").write_text(json.dumps({
        "clusters": [{"id": "vagonka", "name": "Вагонка", "mvp": True, "priority": "P0",
                      "primary_keyword": "купить вагонку", "suggested_url": "/vagonka/"}],
    }, ensure_ascii=False), encoding="utf-8")
    (package / "semantic-core.csv").write_text(
        "keyword,cluster_id,frequency\nкупить вагонку,vagonka,1000\n", encoding="utf-8")
    return package


class NetworkDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-rsya-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: ads\n  url: https://shop.ru\nregion_profile: ru\nads:\n  enabled: true\n",
            encoding="utf-8")
        seed_ads_package(self.tmp)

    def build(self, *args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "ads-draft-builder.py"), "seo/research-package",
             *args, "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_networks_flag_adds_rsya_campaign(self) -> None:
        draft = self.build("--networks")
        channels = {c["channel"] for c in draft["campaigns"]}
        self.assertEqual(channels, {"search", "network"})
        network = next(c for c in draft["campaigns"] if c["channel"] == "network")
        ad = network["ad_groups"][0]["ads"][0]
        self.assertLessEqual(len(ad["headlines"][0]), 56)
        self.assertLessEqual(len(ad["descriptions"][0]), 81)
        self.assertIn("TODO", ad["image"])
        self.assertEqual(network["ad_groups"][0]["keywords"][0]["match_type"], "broad")

    def test_default_stays_search_only(self) -> None:
        draft = self.build()
        self.assertEqual({c["channel"] for c in draft["campaigns"]}, {"search"})

    def test_apply_skips_network_campaigns(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        import importlib.util

        spec = importlib.util.spec_from_file_location("ads_apply", SCRIPTS / "ads-apply.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        draft = self.build("--networks")
        operations = module.build_operations(draft, max_daily_budget=0)
        skip_operations = [op for op in operations if op["op"] == "skip_campaign"]
        self.assertEqual(len(skip_operations), 1)
        self.assertIn("network", skip_operations[0]["name"])
        created = [op["name"] for op in operations if op["op"] == "create_campaign"]
        self.assertTrue(all("network" not in name for name in created))


class ForecastIntervalTest(unittest.TestCase):
    def test_confidence_percentiles_present_and_ordered(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-fc-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text("project:\n  name: f\n", encoding="utf-8")
        package = tmp / "seo" / "research-package"
        package.mkdir(parents=True)
        (package / "semantic-core.csv").write_text(
            "keyword,cluster_id,frequency\nкупить вагонку,vagonka,1000\nвагонка цена,vagonka,500\n",
            encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "seo-forecast.py"), "--format", "json"],
            cwd=tmp, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        for scenario in report["scenarios"].values():
            confidence = scenario["confidence"]
            self.assertLessEqual(confidence["p10"], confidence["p50"])
            self.assertLessEqual(confidence["p50"], confidence["p90"])
            self.assertIn("monthly_leads_confidence", scenario)
        # детерминизм: одинаковый вход → одинаковые интервалы
        proc2 = subprocess.run(
            [sys.executable, str(SCRIPTS / "seo-forecast.py"), "--format", "json"],
            cwd=tmp, text=True, capture_output=True, check=False)
        report2 = json.loads(proc2.stdout)
        self.assertEqual(report["scenarios"]["current"]["confidence"],
                         report2["scenarios"]["current"]["confidence"])


class TokenAgeTest(unittest.TestCase):
    def test_gbp_minted_warning_after_six_days(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-tokenage-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text("project:\n  name: t\n", encoding="utf-8")
        old = (dt.date.today() - dt.timedelta(days=6)).isoformat()
        (tmp / ".env").write_text(f"GBP_TOKEN_MINTED_AT={old}\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GBP")}
        env["SEO_CYCLE_GLOBAL_ENV"] = str(tmp / "env.global")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "auth-assistant.py"), "list", "--format", "json"],
            cwd=tmp, env=env, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertIn("умирает на 7-й день", report["gbp"]["warning"])


if __name__ == "__main__":
    unittest.main()
