#!/usr/bin/env python3
"""Tests for technical SEO collectors and guarded external adapters."""

from __future__ import annotations

import csv
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class TechnicalCollectorsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-technical-collectors-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(
            """
project:
  name: Technical Test
  domain: technical.test
locale:
  country: RU
  language: ru
engines:
  - name: yandex
project_type: ecommerce
""",
            encoding="utf-8",
        )

    def run_script(self, script: str, *extra: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / script), str(self.cfg_path), *extra, "--write", "--format", "json"],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_link_audit_ingests_linkinator_json_and_writes_artifacts(self) -> None:
        payload = {
            "links": [
                {"url": "https://technical.test/", "status": 200, "parent": "https://technical.test/catalog/"},
                {"url": "https://technical.test/missing", "status": 404, "parent": "https://technical.test/catalog/"},
                {
                    "url": "http://technical.test/old",
                    "status": 301,
                    "parent": "https://technical.test/catalog/",
                    "redirected": True,
                },
                {"url": "https://technical.test/catalog/#missing-anchor", "status": 404, "parent": "https://technical.test/catalog/"},
                {"url": "https://external.example/", "status": 500, "parent": "https://technical.test/catalog/"},
            ]
        }
        input_path = self.tmp / "linkinator.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")

        report = self.run_script("link-audit.py", "--input-json", str(input_path), "--url", "https://technical.test/")

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["total_links"], 5)
        self.assertEqual(report["summary"]["broken_links"], 3)
        self.assertEqual(report["summary"]["redirect_links"], 1)
        self.assertEqual(report["summary"]["broken_anchors"], 1)
        self.assertIn("broken_links_present", {row["id"] for row in report["findings"]})
        self.assertIn("broken_anchors_present", {row["id"] for row in report["findings"]})
        self.assertTrue((self.tmp / "seo" / "technical" / "link-audit.md").exists())
        self.assertTrue(pathlib.Path(report["source_paths"]["raw"]).exists())
        self.assertTrue((self.tmp / "seo" / "research" / "vector" / "source_pack.jsonl").exists())

    def test_redirect_map_audit_detects_chain_loop_and_missing_targets(self) -> None:
        csv_path = self.tmp / "redirects.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["old_url", "new_url"])
            writer.writeheader()
            writer.writerow({"old_url": "/a", "new_url": "/b"})
            writer.writerow({"old_url": "/b", "new_url": "/c"})
            writer.writerow({"old_url": "/loop-a", "new_url": "/loop-b"})
            writer.writerow({"old_url": "/loop-b", "new_url": "/loop-a"})
            writer.writerow({"old_url": "/missing", "new_url": ""})

        report = self.run_script("redirect-map-audit.py", "--input", str(csv_path), "--base-url", "https://technical.test")

        self.assertEqual(report["summary"]["rules"], 5)
        self.assertEqual(report["summary"]["chains"], 1)
        self.assertEqual(report["summary"]["loops"], 1)
        self.assertEqual(report["summary"]["missing_targets"], 1)
        self.assertIn("redirect_loops_present", {row["id"] for row in report["findings"]})
        self.assertTrue((self.tmp / "seo" / "technical" / "redirect-map-audit.json").exists())

    def test_lighthouse_audit_distills_local_lighthouse_json(self) -> None:
        payload = {
            "requestedUrl": "https://technical.test/",
            "finalUrl": "https://technical.test/",
            "categories": {
                "performance": {"score": 0.58},
                "seo": {"score": 0.91},
                "accessibility": {"score": 0.82},
                "best-practices": {"score": 0.74},
            },
            "audits": {
                "largest-contentful-paint": {"numericValue": 3200, "displayValue": "3.2 s"},
                "cumulative-layout-shift": {"numericValue": 0.18, "displayValue": "0.18"},
                "total-blocking-time": {"numericValue": 410, "displayValue": "410 ms"},
                "uses-optimized-images": {"score": 0.2, "title": "Efficiently encode images"},
            },
        }
        input_path = self.tmp / "lighthouse.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")

        report = self.run_script("lighthouse-audit.py", "--input-json", str(input_path), "--url", "https://technical.test/")

        self.assertEqual(report["status"], "ready")
        self.assertLess(report["summary"]["scores"]["performance"], 0.7)
        self.assertIn("core_web_vitals_risk", {row["id"] for row in report["findings"]})
        self.assertTrue((self.tmp / "seo" / "technical" / "lighthouse-audit.md").exists())

    def test_serpstat_without_live_or_token_is_guarded_plan(self) -> None:
        report = self.run_script("serpstat-audit.py", "--action", "basic-info", "--report-id", "123456")

        self.assertEqual(report["status"], "guarded")
        self.assertFalse(report["live_api_used"])
        self.assertIn("SERPSTAT_API_KEY", report["env_required"])
        self.assertIn("AuditSite.getBasicInfo", report["planned_request"]["method"])

    def test_serpstat_input_json_distills_basic_info_and_categories(self) -> None:
        payload = {
            "basic_info": {
                "result": {
                    "reportId": 123456,
                    "sdo": 79,
                    "highCount": 3,
                    "mediumCount": 7,
                    "lowCount": 5,
                    "progress": 100,
                    "redirectCount": 4,
                    "checkedPageCount": 50,
                }
            },
            "categories": {
                "result": [
                    {"category": "pages_status", "highCount": 2, "mediumCount": 0, "lowCount": 0},
                    {"category": "meta_tags", "highCount": 1, "mediumCount": 7, "lowCount": 3},
                ]
            },
        }
        input_path = self.tmp / "serpstat.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")

        report = self.run_script("serpstat-audit.py", "--input-json", str(input_path), "--report-id", "123456")

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["sdo"], 79)
        self.assertEqual(report["summary"]["high_count"], 3)
        self.assertIn("serpstat_high_priority_errors", {row["id"] for row in report["findings"]})

    def test_serpstat_extended_actions_are_guarded_and_source_backed(self) -> None:
        settings_path = self.tmp / "serpstat-settings.json"
        settings_path.write_text(json.dumps({"scanType": "domain", "pagesLimit": 100}), encoding="utf-8")

        set_settings = self.run_script(
            "serpstat-audit.py",
            "--action",
            "set-settings",
            "--project-id",
            "777",
            "--settings-json",
            str(settings_path),
        )
        issue_report = self.run_script("serpstat-audit.py", "--action", "issue-report", "--report-id", "123456")
        export_report = self.run_script("serpstat-audit.py", "--action", "export", "--report-id", "123456")

        self.assertEqual(set_settings["status"], "guarded")
        self.assertEqual(set_settings["planned_request"]["method"], "AuditSite.setSettings")
        self.assertEqual(set_settings["planned_request"]["params"]["projectId"], 777)
        self.assertEqual(issue_report["planned_request"]["method"], "AuditSite.getReportWithoutDetails")
        self.assertEqual(export_report["planned_request"]["method"], "AuditSite.export")
        self.assertIn("https://serpstat.com/blog/how-to-automate-searching-for-technical-issues-leave-all-your-work-to-our-api/", set_settings["distillate"]["citations"])

    def test_gsc_url_inspection_distills_local_api_export(self) -> None:
        payload = {
            "inspectionResult": {
                "inspectionResultLink": "https://search.google.com/search-console/inspect?resource_id=sc-domain:technical.test&id=https://technical.test/",
                "indexStatusResult": {
                    "verdict": "PASS",
                    "coverageState": "Submitted and indexed",
                    "robotsTxtState": "ALLOWED",
                    "indexingState": "INDEXING_ALLOWED",
                    "pageFetchState": "SUCCESSFUL",
                    "googleCanonical": "https://technical.test/",
                    "userCanonical": "https://technical.test/",
                    "lastCrawlTime": "2026-06-05T10:00:00Z",
                },
                "mobileUsabilityResult": {"verdict": "PASS"},
                "richResultsResult": {"verdict": "PASS", "detectedItems": [{"richResultType": "Product snippets"}]},
            }
        }
        input_path = self.tmp / "gsc-url-inspection.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")

        report = self.run_script(
            "gsc-url-inspection.py",
            "--input-json",
            str(input_path),
            "--url",
            "https://technical.test/",
            "--site-url",
            "sc-domain:technical.test",
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["coverage_state"], "Submitted and indexed")
        self.assertEqual(report["summary"]["index_verdict"], "PASS")
        self.assertTrue((self.tmp / "seo" / "technical" / "gsc-url-inspection.json").exists())

    def test_gsc_url_inspection_without_token_is_guarded_plan(self) -> None:
        report = self.run_script(
            "gsc-url-inspection.py",
            "--url",
            "https://technical.test/",
            "--site-url",
            "sc-domain:technical.test",
        )

        self.assertEqual(report["status"], "guarded")
        self.assertFalse(report["live_api_used"])
        self.assertEqual(report["planned_request"]["endpoint"], "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect")
        self.assertIn("GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", report["env_required"])

    def test_bing_url_inspection_distills_get_url_info_export(self) -> None:
        payload = {
            "d": {
                "Url": "https://technical.test/",
                "HttpStatus": 200,
                "IsPage": True,
                "AnchorCount": 50,
                "DocumentSize": 12345,
                "LastCrawledDate": "/Date(1764948000000+0000)/",
                "TotalChildUrlCount": 100,
            }
        }
        input_path = self.tmp / "bing-url-info.json"
        input_path.write_text(json.dumps(payload), encoding="utf-8")

        report = self.run_script(
            "bing-url-inspection.py",
            "--input-json",
            str(input_path),
            "--url",
            "https://technical.test/",
            "--site-url",
            "https://technical.test/",
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["http_status"], 200)
        self.assertTrue(report["summary"]["is_page"])
        self.assertTrue((self.tmp / "seo" / "technical" / "bing-url-inspection.md").exists())

    def test_bing_url_inspection_without_key_is_guarded_plan(self) -> None:
        report = self.run_script(
            "bing-url-inspection.py",
            "--url",
            "https://technical.test/",
            "--site-url",
            "https://technical.test/",
        )

        self.assertEqual(report["status"], "guarded")
        self.assertFalse(report["live_api_used"])
        self.assertIn("/webmaster/api.svc/json/GetUrlInfo", report["planned_request"]["endpoint"])
        self.assertIn("BING_WEBMASTER_API_KEY", report["env_required"])

    def test_labrika_source_pack_ingests_manual_export(self) -> None:
        export = self.tmp / "labrika.md"
        export.write_text(
            "# Labrika audit\n"
            "Critical: broken links, duplicate titles, redirect chains.\n"
            "Source: https://labrika.com/seo-auditor\n",
            encoding="utf-8",
        )

        report = self.run_script("labrika-source-pack.py", "--export-file", str(export), "--domain", "technical.test")

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["source_type"], "manual_export")
        self.assertIn("https://labrika.com/seo-auditor", report["distillate"]["citations"])
        self.assertTrue(pathlib.Path(report["paths"]["raw"]).exists())

    def test_labrika_health_is_manual_until_public_api_is_confirmed(self) -> None:
        report = self.run_script("labrika-health.py", "--domain", "technical.test")

        self.assertEqual(report["status"], "needs_input")
        self.assertEqual(report["summary"]["api_status"], "not_confirmed")
        self.assertIn("labrika_api_not_confirmed", {row["id"] for row in report["findings"]})

    def test_technical_mcp_health_reports_missing_optional_mcp_servers(self) -> None:
        report = self.run_script("technical-mcp-health.py")

        self.assertEqual(report["status"], "needs_input")
        self.assertFalse(report["summary"]["mcp_gsc_configured"])
        self.assertFalse(report["summary"]["ga_mcp_configured"])
        self.assertFalse(report["summary"]["lighthouse_mcp_configured"])
        self.assertIn("technical_mcp_servers_not_configured", {row["id"] for row in report["findings"]})

    def test_technical_site_audit_aggregates_latest_reports(self) -> None:
        payload = {
            "links": [
                {"url": "https://technical.test/", "status": 200, "parent": "https://technical.test/catalog/"},
                {"url": "https://technical.test/missing", "status": 404, "parent": "https://technical.test/catalog/"},
            ]
        }
        links_path = self.tmp / "linkinator.json"
        links_path.write_text(json.dumps(payload), encoding="utf-8")
        self.run_script("link-audit.py", "--input-json", str(links_path), "--url", "https://technical.test/")

        lighthouse = {
            "categories": {"performance": {"score": 0.55}, "seo": {"score": 0.9}},
            "audits": {"largest-contentful-paint": {"numericValue": 4100}, "cumulative-layout-shift": {"numericValue": 0.21}},
        }
        lighthouse_path = self.tmp / "lighthouse.json"
        lighthouse_path.write_text(json.dumps(lighthouse), encoding="utf-8")
        self.run_script("lighthouse-audit.py", "--input-json", str(lighthouse_path), "--url", "https://technical.test/")

        vnext_dir = self.tmp / "seo" / "vnext"
        vnext_dir.mkdir(parents=True, exist_ok=True)
        (vnext_dir / "ai-bot-access-check.json").write_text(
            json.dumps(
                {
                    "audit_id": "ai_bot_access_check",
                    "status": "attention_required",
                    "summary": {"unreachable": 1},
                    "findings": [
                        {
                            "id": "llm_crawlers_blocked",
                            "severity": "high",
                            "message": "1 LLM crawler is blocked or unavailable.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        report = self.run_script("technical-site-audit.py")

        self.assertEqual(report["status"], "attention_required")
        self.assertGreaterEqual(report["summary"]["source_count"], 2)
        self.assertIn("link-audit", report["sources"])
        self.assertIn("lighthouse-audit", report["sources"])
        self.assertIn("ai_bot_access_check", report["sources"])
        self.assertTrue((self.tmp / "seo" / "technical" / "technical-site-audit.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
