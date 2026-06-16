#!/usr/bin/env python3
"""Tests for the guarded Google indexing queue/browser/recheck workflow."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
QUEUE = ROOT / "scripts" / "gsc-indexing-queue.py"
BROWSER = ROOT / "scripts" / "gsc-request-indexing-browser.py"
EXPORT_BROWSER = ROOT / "scripts" / "gsc-indexing-export-browser.py"
RECHECK = ROOT / "scripts" / "gsc-indexing-recheck.py"


class GscIndexingWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-gsc-indexing-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(
            """
project:
  name: GSC Indexing Test
  domain: example.com
locale:
  country: RU
  language: ru
engines:
  - name: google
project_type: ecommerce
""",
            encoding="utf-8",
        )
        (self.tmp / "exports").mkdir()

    def write_fixture_exports(self) -> dict[str, pathlib.Path]:
        sitemap = self.tmp / "exports" / "sitemap.xml"
        sitemap.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/shop/fanera/osb-12-mm/</loc></url>
  <url><loc>https://example.com/izolyacionnye-materialy/</loc></url>
  <url><loc>https://example.com/blog/kak-vybrat-osp/</loc></url>
</urlset>
""",
            encoding="utf-8",
        )
        discovered = self.tmp / "exports" / "discovered.csv"
        discovered.write_text(
            "URL,Status\n"
            "https://example.com/shop/fanera/osb-12-mm/,Обнаружена, не проиндексирована\n"
            "https://example.com/wp-json/wp/v2/product/123,Обнаружена, не проиндексирована\n"
            "https://example.com/izolyacionnye-materialy/,Обнаружена, не проиндексирована\n"
            "https://example.com/?bricks=run,Обнаружена, не проиндексирована\n",
            encoding="utf-8",
        )
        woo = self.tmp / "exports" / "woo.csv"
        woo.write_text(
            "url,type\n"
            "https://example.com/shop/fanera/osb-12-mm/,product\n"
            "https://example.com/izolyacionnye-materialy/,product_cat\n",
            encoding="utf-8",
        )
        performance = self.tmp / "exports" / "gsc-performance.json"
        performance.write_text(
            json.dumps(
                {
                    "rows": [
                        {"keys": ["осп 12 мм", "https://example.com/shop/fanera/osb-12-mm/"], "impressions": 120, "clicks": 4, "position": 12.5},
                        {"keys": ["изоляционные материалы", "https://example.com/izolyacionnye-materialy/"], "impressions": 80, "clicks": 1, "position": 9.0},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {"sitemap": sitemap, "discovered": discovered, "woo": woo, "performance": performance}

    def test_queue_crosses_gsc_sitemap_woocommerce_metrics_and_filters_junk(self) -> None:
        files = self.write_fixture_exports()
        proc = subprocess.run(
            [
                sys.executable,
                str(QUEUE),
                str(self.cfg_path),
                "--gsc-discovered-file",
                str(files["discovered"]),
                "--gsc-performance-file",
                str(files["performance"]),
                "--woocommerce-file",
                str(files["woo"]),
                "--sitemap-file",
                str(files["sitemap"]),
                "--top",
                "20",
                "--write",
                "--format",
                "json",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["candidates"], 4)
        self.assertEqual(report["summary"]["eligible"], 2)
        self.assertEqual(report["summary"]["excluded"], 2)
        self.assertEqual(report["queue"][0]["url"], "https://example.com/izolyacionnye-materialy/")
        self.assertIn(report["queue"][0]["priority"], {"P0", "P1"})
        self.assertTrue((self.tmp / "seo" / "technical" / "gsc-indexing-request-queue.csv").exists())
        excluded_reasons = {item["exclude_reason"] for item in report["excluded"]}
        self.assertTrue(any("wp-json" in reason for reason in excluded_reasons))
        self.assertTrue(any("bricks" in reason for reason in excluded_reasons))

    def test_browser_helper_dry_run_uses_queue_without_password_storage(self) -> None:
        files = self.write_fixture_exports()
        subprocess.run(
            [
                sys.executable,
                str(QUEUE),
                str(self.cfg_path),
                "--gsc-discovered-file",
                str(files["discovered"]),
                "--gsc-performance-file",
                str(files["performance"]),
                "--woocommerce-file",
                str(files["woo"]),
                "--sitemap-file",
                str(files["sitemap"]),
                "--write",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(BROWSER),
                str(self.cfg_path),
                "--queue-file",
                "seo/technical/gsc-indexing-request-queue.csv",
                "--max",
                "2",
                "--auto-click",
                "--dry-run",
                "--write",
                "--format",
                "json",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)

        self.assertEqual(report["status"], "planned")
        self.assertEqual(report["summary"]["targets"], 2)
        self.assertTrue(report["summary"]["auto_click"])
        self.assertNotIn("password", json.dumps(report).lower())
        self.assertTrue((self.tmp / "seo" / "technical" / "gsc-indexing-submit.json").exists())

    def test_export_browser_dry_run_can_plan_capture_and_queue_build(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(EXPORT_BROWSER),
                str(self.cfg_path),
                "--issue-url",
                "https://search.google.com/search-console/index/drilldown?resource_id=sc-domain%3Aexample.com",
                "--manual-fallback-seconds",
                "30",
                "--build-queue",
                "--dry-run",
                "--write",
                "--format",
                "json",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)

        self.assertEqual(report["status"], "planned")
        self.assertEqual(report["summary"]["mode"], "gsc_indexing_export_browser")
        self.assertTrue(report["summary"]["build_queue"])
        self.assertFalse(report["summary"]["stores_password"])
        self.assertTrue((self.tmp / "seo" / "technical" / "gsc-indexing-export.json").exists())

    def test_recheck_marks_still_discovered_and_search_data_rows(self) -> None:
        submitted = self.tmp / "seo" / "technical" / "gsc-indexing-submit.json"
        submitted.parent.mkdir(parents=True, exist_ok=True)
        submitted.write_text(
            json.dumps(
                {
                    "browser": {
                        "results": [
                            {"url": "https://example.com/shop/fanera/osb-12-mm/", "status": "submitted_or_requested"},
                            {"url": "https://example.com/izolyacionnye-materialy/", "status": "submitted_or_requested"},
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        discovered_after = self.tmp / "exports" / "discovered-after.csv"
        discovered_after.write_text(
            "URL,Status\nhttps://example.com/shop/fanera/osb-12-mm/,Обнаружена, не проиндексирована\n",
            encoding="utf-8",
        )
        perf_after = self.tmp / "exports" / "perf-after.json"
        perf_after.write_text(
            json.dumps({"rows": [{"keys": ["изоляция", "https://example.com/izolyacionnye-materialy/"], "impressions": 10, "clicks": 0}]}),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(RECHECK),
                str(self.cfg_path),
                "--submitted-log",
                str(submitted),
                "--gsc-discovered-file",
                str(discovered_after),
                "--gsc-performance-file",
                str(perf_after),
                "--write",
                "--format",
                "json",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        statuses = {row["url"]: row["recheck_status"] for row in report["rows"]}

        self.assertEqual(report["status"], "attention_required")
        self.assertEqual(statuses["https://example.com/shop/fanera/osb-12-mm/"], "still_discovered_not_indexed")
        self.assertEqual(statuses["https://example.com/izolyacionnye-materialy/"], "has_search_data")


if __name__ == "__main__":
    unittest.main(verbosity=2)
