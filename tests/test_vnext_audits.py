#!/usr/bin/env python3
"""Smoke tests for SEO/AEO/GEO vNext report generators."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "project.template.yaml"
SCRIPTS = ROOT / "scripts"

SCRIPT_NAMES = [
    "ai-brand-audit.py",
    "answer-units-audit.py",
    "eeat-evidence-map.py",
    "geo-kpi-model.py",
    "log-bot-audit.py",
    "technical-guardrails-audit.py",
    "snippet-sitemap-audit.py",
    "traffic-drop-diagnostics.py",
    "cannibalization-audit.py",
    "ru-commerce-readiness.py",
    "offpage-risk-audit.py",
    "conversion-sxo-audit.py",
    "expert-source-pack.py",
]


@unittest.skipIf(yaml is None, "PyYAML is required")
class VNextAuditsTest(unittest.TestCase):
    def make_project(self) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-vnext-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = "VNext Shop"
        cfg["project"]["domain"] = "vnext.test"
        cfg_path = tmp / "seo-cycle.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return cfg_path

    def run_script(self, script: str, cfg_path: pathlib.Path, *extra: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / script), str(cfg_path), "--write", "--format", "json", *extra],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_all_vnext_scripts_write_report_only_outputs(self) -> None:
        cfg_path = self.make_project()

        for script in SCRIPT_NAMES:
            with self.subTest(script=script):
                report = self.run_script(script, cfg_path)
                self.assertIn(report["status"], {"ready", "needs_input"})
                self.assertFalse(report["config"]["paid_api_required"])
                self.assertFalse(report["config"]["writes_to_site"])
                self.assertTrue(report["output_records"])
                self.assertTrue((cfg_path.parent / report["paths"]["markdown"]).exists())
                self.assertTrue((cfg_path.parent / report["paths"]["json"]).exists())

    def test_technical_guardrails_flags_robots_noindex(self) -> None:
        cfg_path = self.make_project()
        robots = cfg_path.parent / "robots.txt"
        robots.write_text("User-agent: *\nDisallow: /tmp/\nNoindex: /private/\n", encoding="utf-8")

        report = self.run_script("technical-guardrails-audit.py", cfg_path, "--robots", str(robots))

        issue_ids = {row["id"] for row in report["findings"]}
        self.assertIn("robots_noindex_unsupported", issue_ids)
        self.assertEqual(report["evidence"]["robots_summary"]["groups"], 1)

    def test_log_bot_audit_counts_search_and_ai_bots(self) -> None:
        cfg_path = self.make_project()
        log = cfg_path.parent / "access.log"
        log.write_text(
            '\n'.join(
                [
                    '127.0.0.1 - - [06/Jun/2026:10:00:00 +0000] "GET /shop/?filter=x HTTP/1.1" 200 123 "-" "Googlebot"',
                    '127.0.0.1 - - [06/Jun/2026:10:01:00 +0000] "GET /missing HTTP/1.1" 404 0 "-" "GPTBot"',
                    '127.0.0.1 - - [06/Jun/2026:10:02:00 +0000] "GET / HTTP/1.1" 200 100 "-" "ClaudeBot"',
                ]
            ),
            encoding="utf-8",
        )

        report = self.run_script("log-bot-audit.py", cfg_path, "--log", str(log))

        summary = report["evidence"]["log_summary"]
        self.assertEqual(summary["bot_requests"]["googlebot"], 1)
        self.assertEqual(summary["ai_bot_requests"], 2)
        self.assertEqual(summary["faceted_or_parameter_requests"], 1)
        self.assertIn("bot_or_crawl_errors_present", {row["id"] for row in report["findings"]})

    def test_csv_diagnostics_parse_traffic_and_cannibalization(self) -> None:
        cfg_path = self.make_project()
        traffic = cfg_path.parent / "traffic.csv"
        traffic.write_text("url,query,clicks_before,clicks_after\n/a,осп,100,40\n/b,фанера,10,12\n", encoding="utf-8")
        cannibal = cfg_path.parent / "cannibal.csv"
        cannibal.write_text("query,url\nосп,/a\nосп,/b\nфанера,/c\n", encoding="utf-8")

        traffic_report = self.run_script("traffic-drop-diagnostics.py", cfg_path, "--input", str(traffic))
        cannibal_report = self.run_script("cannibalization-audit.py", cfg_path, "--input", str(cannibal))

        self.assertEqual(traffic_report["evidence"]["traffic_summary"]["drop_count"], 1)
        self.assertEqual(cannibal_report["evidence"]["cannibalization_summary"]["conflict_count"], 1)

    def test_upgrade_assistant_surfaces_vnext_feature(self) -> None:
        cfg_path = self.make_project()
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "project-upgrade-assistant.py"), str(cfg_path), "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertIn("seo_aeo_geo_vnext", {row["id"] for row in report["features"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
