#!/usr/bin/env python3
"""Regression tests for the project init wizard."""

from __future__ import annotations

import pathlib
import os
import shutil
import subprocess
import tempfile
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = pathlib.Path(__file__).resolve().parents[1]
INIT_PROJECT = ROOT / "scripts" / "init-project.sh"


@unittest.skipIf(yaml is None, "PyYAML is required")
class InitProjectTest(unittest.TestCase):
    def test_pipe_stdin_does_not_pollute_generated_config(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-init-project-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))

        fake_bootstrap_tail = '\n'.join(
            [
                'echo "Project: $PROJECT_DIR"',
                'echo "  ✓ Codex bootstrap finished"',
                'echo "Core: $CORE"',
                "",
            ]
        )
        proc = subprocess.run(
            ["bash", str(INIT_PROJECT)],
            cwd=tmp,
            input=fake_bootstrap_tail,
            text=True,
            capture_output=True,
            env={**os.environ, "SEO_CYCLE_SKIP_REGISTRY": "1"},
            check=True,
        )

        self.assertIn("safe defaults", proc.stdout)
        cfg = yaml.safe_load((tmp / "seo-cycle.yaml").read_text(encoding="utf-8"))
        self.assertEqual(cfg["project"]["name"], "MyProject")
        self.assertEqual(cfg["project"]["domain"], "example.com")
        self.assertEqual(cfg["locale"]["language"], "ru")
        self.assertTrue((tmp / "seo" / "setup" / "setup-control-plane.md").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
