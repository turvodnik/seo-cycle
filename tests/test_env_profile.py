#!/usr/bin/env python3
"""Tests for env profiles (project/global chain) and auth-assistant."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import stat
import subprocess
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


class AuthAssistantCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-auth-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: auth\n", encoding="utf-8")
        self.global_env = self.tmp / "env.global"

    def run_auth(self, *args: str) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items() if not key.startswith(("PERPLEXITY", "GBP_"))}
        env["SEO_CYCLE_GLOBAL_ENV"] = str(self.global_env)
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "auth-assistant.py"), *args],
            cwd=self.tmp, env=env, text=True, capture_output=True, check=False,
        )

    def test_set_writes_project_env_by_default(self) -> None:
        proc = self.run_auth("set", "PERPLEXITY_API_KEY", "--value", "sk-test")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PERPLEXITY_API_KEY=sk-test", (self.tmp / ".env").read_text(encoding="utf-8"))
        self.assertNotIn("sk-test", proc.stdout + proc.stderr.replace("PERPLEXITY_API_KEY", ""))

    def test_set_global_writes_global_env(self) -> None:
        proc = self.run_auth("set", "TELEGRAM_BOT_TOKEN", "--global", "--value", "123:abc")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("TELEGRAM_BOT_TOKEN=123:abc", self.global_env.read_text(encoding="utf-8"))
        self.assertFalse((self.tmp / ".env").exists())

    def test_list_shows_sources(self) -> None:
        self.run_auth("set", "PERPLEXITY_API_KEY", "--value", "sk-1")
        self.run_auth("set", "TELEGRAM_BOT_TOKEN", "--global", "--value", "t-1")
        proc = self.run_auth("list", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        perplexity = {row["var"]: row for row in report["perplexity"]["vars"]}
        self.assertEqual(perplexity["PERPLEXITY_API_KEY"]["source"], "project")
        self.assertEqual(report["perplexity"]["state"], "ready")
        telegram = {row["var"]: row for row in report["telegram"]["vars"]}
        self.assertEqual(telegram["TELEGRAM_BOT_TOKEN"]["source"], "global")
        self.assertEqual(report["gbp"]["state"], "not_configured")
        # значения секретов не должны попадать в вывод
        self.assertNotIn("sk-1", proc.stdout)
        self.assertNotIn("t-1", proc.stdout)

    def test_login_unknown_provider_fails(self) -> None:
        proc = self.run_auth("login", "nosuch")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("неизвестный провайдер", proc.stderr)


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
