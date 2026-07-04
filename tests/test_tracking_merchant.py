#!/usr/bin/env python3
"""Tests for gtm-audit.py, merchant-health/fetch, and yml-feed-audit.py."""

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

GTM_EXPORT = {
    "exportFormatVersion": 2,
    "containerVersion": {
        "container": {"name": "Site", "publicId": "GTM-TEST123", "usageContext": ["WEB"]},
        "tag": [
            {"tagId": "1", "name": "GA4 Config", "type": "gaawc", "firingTriggerId": ["10"],
             "parameter": [{"key": "measurementIdOverride", "value": "G-AAA111"}]},
            {"tagId": "2", "name": "GA4 Config COPY", "type": "gaawc", "firingTriggerId": ["10"],
             "parameter": [{"key": "measurementIdOverride", "value": "G-AAA111"}]},
            {"tagId": "3", "name": "Old promo pixel", "type": "html", "paused": True,
             "parameter": [{"key": "html", "value": "<script>old()</script>"}]},
            {"tagId": "4", "name": "Orphan event", "type": "gaawe",
             "parameter": [{"key": "eventName", "value": "lead"},
                           {"key": "measurementIdOverride", "value": "{{GA4 ID}}"}]},
        ],
        "trigger": [
            {"triggerId": "10", "name": "All Pages", "type": "pageview"},
            {"triggerId": "11", "name": "Unused trigger", "type": "click"},
        ],
        "variable": [
            {"variableId": "20", "name": "GA4 ID", "type": "c"},
            {"variableId": "21", "name": "Dead variable", "type": "c"},
        ],
    },
}

VALID_YML = """<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog date="2026-07-04">
<shop>
  <name>Shop</name><company>Shop LLC</company><url>https://example.com</url>
  <currencies><currency id="RUR" rate="1"/></currencies>
  <categories><category id="1">Вагонка</category></categories>
  <offers>
    <offer id="101" available="true">
      <name>Вагонка кедр 96x14</name><url>https://example.com/p/101</url>
      <price>1200</price><currencyId>RUR</currencyId><categoryId>1</categoryId>
      <picture>https://example.com/i/101.jpg</picture>
    </offer>
  </offers>
</shop>
</yml_catalog>
"""

BROKEN_YML = """<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog date="2026-07-04">
<shop>
  <name>Shop</name><company>Shop LLC</company><url>https://example.com</url>
  <categories><category id="1">Вагонка</category></categories>
  <offers>
    <offer id="101"><url>http://example.com/p/101</url><price>0</price>
      <currencyId>RUR</currencyId><categoryId>99</categoryId></offer>
    <offer id="101" available="true"><name>Дубль</name><url>https://example.com/p/2</url>
      <price>10</price><currencyId>RUR</currencyId><categoryId>1</categoryId>
      <picture>https://example.com/i/2.jpg</picture></offer>
  </offers>
</shop>
</yml_catalog>
"""


class ScriptTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-w2-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: w2\nregion_profile: ru\n", encoding="utf-8"
        )

    def run_script(self, script: str, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("GTM_", "GOOGLE_MERCHANT", "GOOGLE_APPLICATION"))}
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )


class GtmAuditTest(ScriptTestBase):
    def test_audit_finds_hygiene_issues_from_export(self) -> None:
        export = self.tmp / "gtm-export.json"
        export.write_text(json.dumps(GTM_EXPORT), encoding="utf-8")
        proc = self.run_script("gtm-audit.py", "--input-file", str(export), "--write", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        ids = {finding["id"] for finding in report["findings"]}
        self.assertIn("duplicate_tags", ids)
        self.assertIn("multiple_ga4_config_tags", ids)
        self.assertIn("paused_tags", ids)
        self.assertIn("tags_without_triggers", ids)      # Orphan event has no trigger
        self.assertIn("orphan_triggers", ids)            # Unused trigger
        self.assertIn("orphan_variables", ids)
        orphan_vars = next(f for f in report["findings"] if f["id"] == "orphan_variables")
        self.assertEqual(orphan_vars["evidence"], ["Dead variable"])  # GA4 ID is referenced via {{...}}
        self.assertIn("no_consent_settings", ids)
        self.assertEqual(report["counts"]["tags"], 4)
        self.assertTrue((self.tmp / "seo" / "tracking" / "gtm-audit.md").exists())

    def test_no_input_is_graceful_hint(self) -> None:
        proc = self.run_script("gtm-audit.py")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Export Container", proc.stderr)

    def test_broken_export_fails_clearly(self) -> None:
        bad = self.tmp / "bad.json"
        bad.write_text("{}", encoding="utf-8")
        proc = self.run_script("gtm-audit.py", "--input-file", str(bad))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("containerVersion", proc.stderr)


class MerchantTest(ScriptTestBase):
    def test_health_is_region_limited_for_ru(self) -> None:
        proc = self.run_script("merchant-health.py", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "region_limited")
        self.assertIn("yml-feed-audit", report["region_note"])

    def test_fetch_ingests_productstatuses_export(self) -> None:
        export = self.tmp / "productstatuses.json"
        export.write_text(
            json.dumps({"kind": "productstatuses", "resources": [
                {"productId": "online:ru:RU:101", "title": "Вагонка",
                 "destinationStatuses": [{"destination": "Shopping", "status": "disapproved"}],
                 "itemLevelIssues": [{"code": "image_link_broken", "servability": "disapproved",
                                      "description": "Invalid image", "attributeName": "image_link"}]},
                {"productId": "online:ru:RU:102", "title": "Вагонка 2",
                 "destinationStatuses": [{"destination": "Shopping", "status": "approved"}],
                 "itemLevelIssues": []},
            ]}),
            encoding="utf-8",
        )
        proc = self.run_script("merchant-fetch.py", "--input-file", str(export), "--write", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)["reports"]["productstatuses"]
        self.assertEqual(summary["products"], 2)
        self.assertEqual(summary["disapproved_issue_count"], 1)
        self.assertEqual(summary["top_issue_reasons"][0][0], "Invalid image")
        self.assertTrue((self.tmp / "seo" / "merchant" / "raw" / "productstatuses-latest.json").exists())

    def test_fetch_without_input_is_graceful(self) -> None:
        proc = self.run_script("merchant-fetch.py")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--input-file", proc.stderr)


class YmlFeedAuditTest(ScriptTestBase):
    def test_valid_feed_passes(self) -> None:
        feed = self.tmp / "feed.yml"
        feed.write_text(VALID_YML, encoding="utf-8")
        proc = self.run_script("yml-feed-audit.py", "--file", str(feed), "--write", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["counts"]["offers"], 1)

    def test_broken_feed_fails_with_specific_findings(self) -> None:
        feed = self.tmp / "feed.yml"
        feed.write_text(BROKEN_YML, encoding="utf-8")
        proc = self.run_script("yml-feed-audit.py", "--file", str(feed), "--format", "json")
        self.assertEqual(proc.returncode, 1)
        report = json.loads(proc.stdout)
        ids = {finding["id"] for finding in report["findings"]}
        for expected in ("duplicate_offer_ids", "non_positive_price", "unknown_category_id",
                         "missing_picture", "missing_availability", "insecure_offer_urls", "missing_name"):
            self.assertIn(expected, ids, f"missing finding {expected}")
        self.assertEqual(report["status"], "fail")

    def test_not_xml_is_critical(self) -> None:
        feed = self.tmp / "feed.yml"
        feed.write_text("not xml at all", encoding="utf-8")
        proc = self.run_script("yml-feed-audit.py", "--file", str(feed), "--format", "json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["findings"][0]["id"], "xml_parse_error")

    def test_url_without_live_refused(self) -> None:
        proc = self.run_script("yml-feed-audit.py", "--url", "https://example.com/feed.yml")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--live", proc.stderr)


if __name__ == "__main__":
    unittest.main()
