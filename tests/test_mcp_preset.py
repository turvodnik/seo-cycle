#!/usr/bin/env python3
"""Tests for mcp-preset.py (curated project-local ecosystem MCP block)."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class McpPresetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-mcp-preset-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: mcp\n", encoding="utf-8")

    def run_preset(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "mcp-preset.py"), *args],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )

    def toml(self) -> str:
        return (self.tmp / ".codex" / "config.toml").read_text(encoding="utf-8")

    def test_list_shows_presets(self) -> None:
        proc = self.run_preset("--list")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for name in ("chrome-devtools", "perplexity", "google-analytics"):
            self.assertIn(name, proc.stdout)

    def test_enable_writes_managed_block_with_env_guard(self) -> None:
        proc = self.run_preset("--enable", "perplexity", "--enable", "chrome-devtools", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        body = self.toml()
        self.assertIn("BEGIN seo-cycle managed ecosystem MCP", body)
        self.assertIn("[mcp_servers.seo-cycle-perplexity]", body)
        self.assertIn("PERPLEXITY_API_KEY missing in project .env", body)
        self.assertIn("[mcp_servers.seo-cycle-chrome-devtools]", body)
        self.assertIn("chrome-devtools-mcp@latest", body)

    def test_disable_removes_server_and_preserves_foreign_content(self) -> None:
        (self.tmp / ".codex").mkdir()
        (self.tmp / ".codex" / "config.toml").write_text(
            "[mcp_servers.custom]\ncommand = \"echo\"\n", encoding="utf-8"
        )
        self.run_preset("--enable", "perplexity", "--write")
        self.run_preset("--disable", "perplexity", "--write")
        body = self.toml()
        self.assertIn("[mcp_servers.custom]", body)  # чужой блок не тронут
        self.assertNotIn("seo-cycle-perplexity", body)
        self.assertIn("BEGIN seo-cycle managed ecosystem MCP", body)  # пустой managed-блок остаётся

    def test_state_survives_between_runs(self) -> None:
        self.run_preset("--enable", "google-analytics", "--write")
        proc = self.run_preset("--list")
        self.assertRegex(proc.stdout, r"\[enabled\]\s+google-analytics")


if __name__ == "__main__":
    unittest.main()
