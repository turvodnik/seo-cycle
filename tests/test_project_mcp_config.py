#!/usr/bin/env python3
"""Tests for project-local MCP config generation."""

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
PROJECT_MCP = ROOT / "scripts" / "project-mcp-config.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class ProjectMcpConfigTest(unittest.TestCase):
    def make_project(self, cms: str = "wordpress") -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-project-mcp-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["cms"] = cms
        cfg["publishing"]["cms"] = cms
        cfg_path = tmp / "seo-cycle.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (tmp / ".env.example").write_text("# project env\n", encoding="utf-8")
        (tmp / ".codex").mkdir()
        (tmp / ".codex" / "config.toml").write_text(
            '[mcp_servers.keep]\ncommand = "echo"\n',
            encoding="utf-8",
        )
        return cfg_path

    def test_wordpress_mcp_is_project_local_and_secret_free(self) -> None:
        cfg_path = self.make_project()
        proc = subprocess.run(
            [sys.executable, str(PROJECT_MCP), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "ready")
        self.assertFalse(report["secrets_written"])

        rendered = (cfg_path.parent / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.keep]", rendered)
        self.assertIn("[mcp_servers.novamira-wordpress]", rendered)
        self.assertIn("@automattic/mcp-wordpress-remote@latest", rendered)
        self.assertIn(". ./.env", rendered)
        self.assertIn("WP_API_URL missing in project .env", rendered)
        self.assertNotIn("WP_API_PASSWORD = ", rendered)
        self.assertNotIn("xxxx", rendered)

        env_example = (cfg_path.parent / ".env.example").read_text(encoding="utf-8")
        self.assertIn("WP_API_URL=https://example.com/wp-json/mcp/novamira", env_example)
        self.assertIn("WP_API_USERNAME=", env_example)
        self.assertIn("WP_API_PASSWORD=", env_example)

    def test_non_wordpress_project_is_skipped(self) -> None:
        cfg_path = self.make_project(cms="static")
        proc = subprocess.run(
            [sys.executable, str(PROJECT_MCP), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "skipped_non_wordpress")
        rendered = (cfg_path.parent / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertNotIn("novamira-wordpress", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
