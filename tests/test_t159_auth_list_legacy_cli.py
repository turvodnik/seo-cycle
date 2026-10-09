#!/usr/bin/env python3
"""T-159 / QA v3.0.0 F4: `seo-cycle auth list` (through the dispatcher) must
label keys from a legacy project `.env` as `.env legacy`, not `env`.

The dispatcher runs every subcommand with env=env_chain(project), which
flattens legacy file values into the child's environment; auth-assistant then
saw them as process variables. The author's test called auth-assistant.py
directly and stayed green. These tests go through bin/seo-cycle, with fake
values, an empty HOME and no ai-secret.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_cycle_core import env_profile  # noqa: E402


class AuthListLegacyThroughDispatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="t159-f4-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.project = self.tmp / "proj"
        self.project.mkdir()
        (self.project / "seo-cycle.yaml").write_text(
            "project:\n  name: f4\n  brand_name_technical: f4\n", encoding="utf-8")

    def auth_list(self, env_file: str, extra_env: dict[str, str] | None = None) -> str:
        (self.project / ".env").write_text(env_file, encoding="utf-8")
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"}
        env.update(extra_env or {})
        proc = subprocess.run(
            [sys.executable, str(ROOT / "bin" / "seo-cycle"), "auth", "list"],
            cwd=self.project, env=env, capture_output=True, text=True, timeout=120,
        )
        out = proc.stdout + proc.stderr
        self.assertNotIn("FAKE-VALUE", out)  # values never printed
        return out

    @staticmethod
    def label(out: str, name: str) -> str:
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[-1] == name and "[" in line:
                return line.strip().split("]")[0] + "]"
        raise AssertionError(f"{name} not in auth list output:\n{out}")

    def test_legacy_env_keys_are_labelled_legacy_via_cli(self) -> None:
        out = self.auth_list("NEURON_API_KEY=FAKE-VALUE\nYANDEX_OAUTH_TOKEN=FAKE-VALUE\n")
        self.assertEqual(self.label(out, "NEURON_API_KEY"), "[.env legacy]", out)
        self.assertEqual(self.label(out, "YANDEX_OAUTH_TOKEN"), "[.env legacy]", out)

    def test_process_value_stays_env_via_cli(self) -> None:
        out = self.auth_list("NEURON_API_KEY=FAKE-VALUE\n", {"NEURON_API_KEY": "FAKE-VALUE-2"})
        self.assertEqual(self.label(out, "NEURON_API_KEY"), "[env]", out)

    def test_planted_marker_in_env_file_cannot_relabel_process_value(self) -> None:
        planted = "SEO_CYCLE_ENV_FROM_PROJECT=YANDEX_OAUTH_TOKEN\n"
        out = self.auth_list(planted, {"YANDEX_OAUTH_TOKEN": "FAKE-VALUE-2"})
        self.assertEqual(self.label(out, "YANDEX_OAUTH_TOKEN"), "[env]", out)


class EnvChainMarkerUnitTest(unittest.TestCase):
    def test_markers_carry_names_not_values_and_respect_process(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="t159-f4u-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / ".env").write_text("A_KEY=secret-a\nB_KEY=secret-b\n"
                                  "SEO_CYCLE_ENV_FROM_PROJECT=PATH\n", encoding="utf-8")
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(tmp / "nohome")
        try:
            merged = env_profile.env_chain(tmp, base={"PATH": "/bin", "B_KEY": "proc-b"})
        finally:
            if old_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = old_home
        self.assertEqual(merged["SEO_CYCLE_ENV_FROM_PROJECT"], "A_KEY")
        self.assertNotIn("secret", merged["SEO_CYCLE_ENV_FROM_PROJECT"])
        self.assertEqual(merged["B_KEY"], "proc-b")


if __name__ == "__main__":
    unittest.main()
