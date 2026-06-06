#!/usr/bin/env python3
"""Tests for token waste reporting."""

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
SCRIPT = ROOT / "scripts" / "token-waste-audit.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class TokenWasteAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-token-waste-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = "Token Waste Test"
        cfg["project"]["domain"] = "token-waste.test"
        cfg["governance"]["token_policy"]["raw_data_in_context"] = False
        cfg["governance"]["token_policy"]["distillate_max_lines"] = 5
        cfg["governance"]["token_policy"]["max_output_tokens_per_artifact"] = 100
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        raw_dir = self.tmp / "seo" / "research" / "perplexity" / "raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "dump.json").write_text("x" * 20_000, encoding="utf-8")
        distillate = self.tmp / "seo" / "research" / "perplexity" / "distillates" / "summary.md"
        distillate.parent.mkdir(parents=True)
        distillate.write_text("\n".join(f"line {i}" for i in range(20)), encoding="utf-8")

    def test_token_waste_audit_flags_raw_and_long_distillates(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.cfg_path), "--write", "--format", "json"],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(proc.stdout)
        issue_ids = {row["id"] for row in report["findings"]}

        self.assertIn("raw_artifact_present", issue_ids)
        self.assertIn("distillate_too_long", issue_ids)
        self.assertEqual(report["status"], "needs_review")
        self.assertTrue((self.tmp / "seo" / "setup" / "token-waste-audit.md").exists())
        self.assertTrue((self.tmp / "seo" / "setup" / "latest-token-waste-audit.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
