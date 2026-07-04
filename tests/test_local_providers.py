#!/usr/bin/env python3
"""Tests for gbp-health.py, gbp-fetch.py, yandex-business-health.py."""

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


class LocalProvidersTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-local-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: local\nregion_profile: ru\n"
            "business_profile:\n  gbp_url: https://maps.google.com/?cid=42\n",
            encoding="utf-8",
        )

    def run_script(self, script: str, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("GBP_", "GOOGLE_BUSINESS", "YANDEX_MERCHANT"))}
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args, "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False, env=env,
        )


class GbpHealthTest(LocalProvidersTestBase):
    def test_without_oauth_is_needs_oauth_verification(self) -> None:
        proc = self.run_script("gbp-health.py")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "needs_oauth_verification")
        self.assertIn("browser", report["verification_note"].lower())
        self.assertEqual(report["gbp_url"], "https://maps.google.com/?cid=42")

    def test_with_full_env_is_available(self) -> None:
        env = {"GBP_OAUTH_CLIENT_ID": "x", "GBP_OAUTH_CLIENT_SECRET": "y",
               "GBP_OAUTH_REFRESH_TOKEN": "z", "GOOGLE_BUSINESS_ACCOUNT_ID": "1",
               "GOOGLE_BUSINESS_LOCATION_ID": "2"}
        report = json.loads(self.run_script("gbp-health.py", env_extra=env).stdout)
        self.assertEqual(report["status"], "available")


class GbpFetchTest(LocalProvidersTestBase):
    def test_reviews_summary_from_export(self) -> None:
        export = self.tmp / "reviews.json"
        export.write_text(
            json.dumps({"reviews": [
                {"starRating": "FIVE", "createTime": "2026-06-20T10:00:00Z",
                 "reviewReply": {"comment": "Спасибо!"}},
                {"starRating": "FIVE", "createTime": "2026-07-01T10:00:00Z"},
                {"starRating": "TWO", "createTime": "2026-05-01T10:00:00Z"},
            ]}),
            encoding="utf-8",
        )
        proc = self.run_script("gbp-fetch.py", "--report", "reviews", "--input-file", str(export), "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)["reports"]["reviews"]
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["average_rating"], 4.0)
        self.assertEqual(summary["unanswered"], 2)
        self.assertEqual(summary["newest"], "2026-07-01")
        self.assertEqual(summary["rating_distribution"]["5"], 2)
        self.assertTrue((self.tmp / "seo" / "local" / "gbp-summary.md").exists())
        self.assertTrue((self.tmp / "seo" / "local" / "raw" / "gbp-reviews-latest.json").exists())

    def test_locations_summary_from_export(self) -> None:
        export = self.tmp / "locations.json"
        export.write_text(
            json.dumps({"locations": [
                {"title": "Салон на Ленина", "websiteUri": "https://example.com",
                 "phoneNumbers": {"primaryPhone": "+7 900 000-00-00"},
                 "categories": {"primaryCategory": {"displayName": "Магазин пиломатериалов"}},
                 "storefrontAddress": {"locality": "Казань"}},
                {"title": "Склад", "categories": {}},
            ]}),
            encoding="utf-8",
        )
        summary = json.loads(self.run_script("gbp-fetch.py", "--report", "locations",
                                             "--input-file", str(export)).stdout)["reports"]["locations"]
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["missing_website"], 1)
        self.assertEqual(summary["missing_phone"], 1)

    def test_live_without_env_fails_with_hint(self) -> None:
        proc = self.run_script("gbp-fetch.py", "--live")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("browser workflow", proc.stderr)


class YandexBusinessHealthTest(LocalProvidersTestBase):
    def test_status_is_partner_limited_with_working_paths(self) -> None:
        proc = self.run_script("yandex-business-health.py", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "partner_limited")
        self.assertTrue(any("yandex-maps.md" in path for path in report["working_paths"]))
        self.assertTrue(any("2ГИС" in path for path in report["working_paths"]))
        self.assertTrue((self.tmp / "seo" / "setup" / "yandex-business-health.md").exists())


if __name__ == "__main__":
    unittest.main()
