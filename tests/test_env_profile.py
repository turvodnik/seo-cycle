#!/usr/bin/env python3
"""Tests for env profiles (read-side chain) and the CLI env merge."""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.env_profile import (  # noqa: E402
    env_chain,
    parse_env_file,
    upsert_env_var,
)


class EnvProfileCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-envprof-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.global_env = self.tmp / "env.global"
        os.environ["SEO_CYCLE_GLOBAL_ENV"] = str(self.global_env)
        self.addCleanup(lambda: os.environ.pop("SEO_CYCLE_GLOBAL_ENV", None))

    def test_parse_env_file_handles_comments_quotes_export(self) -> None:
        path = self.tmp / ".env"
        path.write_text(
            "# comment\nFOO=bar\nexport QUOTED='v a l'\nDOUBLE=\"x\"\nBROKEN LINE\nEMPTY=\n",
            encoding="utf-8",
        )
        data = parse_env_file(path)
        self.assertEqual(data["FOO"], "bar")
        self.assertEqual(data["QUOTED"], "v a l")
        self.assertEqual(data["DOUBLE"], "x")
        self.assertEqual(data["EMPTY"], "")
        self.assertNotIn("BROKEN", data)

    def test_chain_precedence_process_project_global(self) -> None:
        upsert_env_var(self.global_env, "TOKEN", "from-global")
        upsert_env_var(self.global_env, "ONLY_GLOBAL", "g")
        project = self.tmp / "proj"
        project.mkdir()
        upsert_env_var(project / ".env", "TOKEN", "from-project")
        merged = env_chain(project, base={"TOKEN": "from-process"})
        self.assertEqual(merged["TOKEN"], "from-process")
        self.assertEqual(merged["ONLY_GLOBAL"], "g")
        merged = env_chain(project, base={})
        self.assertEqual(merged["TOKEN"], "from-project")
        merged = env_chain(None, base={})
        self.assertEqual(merged["TOKEN"], "from-global")

    def test_upsert_replaces_in_place_and_chmods(self) -> None:
        path = self.tmp / ".env"
        path.write_text("# keep me\nFOO=old\nBAR=1\n", encoding="utf-8")
        upsert_env_var(path, "FOO", "new")
        body = path.read_text(encoding="utf-8")
        self.assertIn("# keep me", body)
        self.assertIn("FOO=new", body)
        self.assertNotIn("FOO=old", body)
        self.assertEqual(body.count("FOO="), 1)
        mode = stat.S_IMODE(path.stat().st_mode)
        self.assertEqual(mode, 0o600)


# `auth set`/`auth login`/`auth list` behaviour (values -> Keychain via the
# ai-secret broker, never a file) lives in tests/test_auth_secrets_canon.py
# against a stub broker on an isolated PATH (T-108).


class CliEnvChainTest(unittest.TestCase):
    def test_run_script_dispatch_merges_global_env(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cli-env-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text("project:\n  name: cli-env\n", encoding="utf-8")
        global_env = tmp / "env.global"
        global_env.write_text("SEO_CYCLE_TEST_MARKER=from-global\n", encoding="utf-8")
        (tmp / "probe.py").write_text(
            "import os, pathlib\n"
            "pathlib.Path('probe-out.txt').write_text(os.environ.get('SEO_CYCLE_TEST_MARKER', 'missing'))\n",
            encoding="utf-8",
        )
        os.environ["SEO_CYCLE_GLOBAL_ENV"] = str(global_env)
        self.addCleanup(lambda: os.environ.pop("SEO_CYCLE_GLOBAL_ENV", None))
        os.environ.pop("SEO_CYCLE_TEST_MARKER", None)

        import seo_cycle_cli

        original = seo_cycle_cli.SCRIPTS_DIR
        seo_cycle_cli.SCRIPTS_DIR = tmp
        try:
            rc = seo_cycle_cli.run_script("probe.py", [], tmp)
        finally:
            seo_cycle_cli.SCRIPTS_DIR = original
        self.assertEqual(rc, 0)
        self.assertEqual((tmp / "probe-out.txt").read_text(encoding="utf-8"), "from-global")


if __name__ == "__main__":
    unittest.main()
