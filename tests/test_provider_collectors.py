#!/usr/bin/env python3
"""Tests for provider evidence collectors."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PERPLEXITY_COLLECT = ROOT / "scripts" / "perplexity-collect.py"
NOTEBOOKLM_SOURCE_PACK = ROOT / "scripts" / "notebooklm-source-pack.py"


class ProviderCollectorsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-provider-collectors-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(
            """
project:
  name: Collector Test
  domain: collector.test
locale:
  country: RU
  language: ru
engines:
  - name: yandex
project_type: ecommerce
expert_sources:
  notebooklm_url: https://notebooklm.google.com/notebook/test
""",
            encoding="utf-8",
        )

    def test_perplexity_raw_file_writes_cache_distillate_and_vector_once(self) -> None:
        raw = self.tmp / "perplexity-response.md"
        raw.write_text(
            "Summary: OSB плиты ищут по толщине, влагостойкости и применению.\n"
            "Source: https://example.com/osb-guide\n",
            encoding="utf-8",
        )
        command = [
            sys.executable,
            str(PERPLEXITY_COLLECT),
            str(self.cfg_path),
            "--topic",
            "Плита ОСП",
            "--region",
            "RU",
            "--raw-file",
            str(raw),
            "--write",
            "--format",
            "json",
        ]
        first = subprocess.run(command, cwd=self.tmp, check=True, text=True, capture_output=True)
        first_report = json.loads(first.stdout)
        self.assertEqual(first_report["status"], "ready")
        self.assertTrue(pathlib.Path(first_report["paths"]["raw"]).exists())
        self.assertTrue(pathlib.Path(first_report["paths"]["distillate_markdown"]).exists())
        self.assertIn("https://example.com/osb-guide", first_report["distillate"]["citations"])

        second = subprocess.run(command, cwd=self.tmp, check=True, text=True, capture_output=True)
        second_report = json.loads(second.stdout)
        self.assertEqual(second_report["status"], "cache_hit")

        vector_path = self.tmp / "seo" / "research" / "vector" / "source_pack.jsonl"
        self.assertEqual(len(vector_path.read_text(encoding="utf-8").splitlines()), 1)

    def test_perplexity_without_raw_writes_degraded_prompt_packet(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(PERPLEXITY_COLLECT),
                str(self.cfg_path),
                "--topic",
                "Плита ОСП",
                "--region",
                "RU",
                "--app-path",
                str(self.tmp / "Missing.app"),
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
        self.assertEqual(report["status"], "degraded_source")
        self.assertIn("prompt_packet", report["distillate"])
        self.assertFalse(report["paid_api_used"])
        self.assertTrue((self.tmp / "seo" / "research" / "distillates" / "perplexity" / "latest-summary.md").exists())

    def test_notebooklm_export_file_writes_curated_source_pack(self) -> None:
        export = self.tmp / "notebooklm-export.md"
        export.write_text(
            "# SEO expert notes\n"
            "OSB pages need answer blocks, entity triples, price evidence, and crawlable commercial factors.\n"
            "Reference: https://example.com/notebook-source\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(NOTEBOOKLM_SOURCE_PACK),
                str(self.cfg_path),
                "--topic",
                "Плита ОСП",
                "--source-id",
                "seo-notebook",
                "--export-file",
                str(export),
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
        self.assertTrue(report["not_ranking_signal"])
        self.assertIn("https://example.com/notebook-source", report["distillate"]["citations"])
        self.assertIn("SEO expert notes", report["distillate"]["headings"])
        self.assertTrue(pathlib.Path(report["paths"]["raw"]).exists())
        self.assertTrue((self.tmp / "seo" / "research" / "vector" / "source_pack.jsonl").exists())

    def test_notebooklm_without_export_writes_fallback_packet(self) -> None:
        codex_config = self.tmp / "config.toml"
        codex_config.write_text("[mcp_servers.notebooklm]\ncommand = \"npx\"\n", encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                str(NOTEBOOKLM_SOURCE_PACK),
                str(self.cfg_path),
                "--topic",
                "Плита ОСП",
                "--codex-config",
                str(codex_config),
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
        self.assertEqual(report["status"], "fallback_required")
        self.assertEqual(report["health"]["access_mode"], "browser_export")
        self.assertTrue(report["not_ranking_signal"])
        self.assertTrue((self.tmp / "seo" / "research" / "distillates" / "notebooklm" / "latest-summary.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
