#!/usr/bin/env python3
"""CLI smoke tests for provider health reports."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PERPLEXITY = ROOT / "scripts" / "perplexity-health.py"
NOTEBOOKLM = ROOT / "scripts" / "notebooklm-health.py"


class ProviderHealthCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-provider-health-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(
            """
project:
  name: Provider Test
  domain: provider.test
locale:
  country: RU
engines:
  - name: yandex
project_type: ecommerce
expert_sources:
  notebooklm_url: https://notebooklm.google.com/notebook/test
""",
            encoding="utf-8",
        )

    def test_perplexity_write_degrades_without_app_or_browser(self) -> None:
        subprocess.run(
            [
                sys.executable,
                str(PERPLEXITY),
                str(self.cfg_path),
                "--app-path",
                str(self.tmp / "Missing.app"),
                "--write",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads((self.tmp / "seo" / "setup" / "perplexity-health.json").read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "degraded_source")
        self.assertFalse(report["stores_password"])
        self.assertTrue((self.tmp / "seo" / "setup" / "latest-perplexity-health.md").exists())

    def test_notebooklm_write_falls_back_when_tools_are_missing(self) -> None:
        codex_config = self.tmp / "config.toml"
        codex_config.write_text("[mcp_servers.notebooklm]\ncommand = \"npx\"\n", encoding="utf-8")

        subprocess.run(
            [
                sys.executable,
                str(NOTEBOOKLM),
                str(self.cfg_path),
                "--codex-config",
                str(codex_config),
                "--write",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads((self.tmp / "seo" / "setup" / "notebooklm-health.json").read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "fallback_required")
        self.assertEqual(report["health"]["access_mode"], "browser_export")
        self.assertTrue(report["not_ranking_signal"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
