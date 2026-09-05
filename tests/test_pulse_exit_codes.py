#!/usr/bin/env python3
"""T-052: честные коды выхода pulse — успех/частичная деградация/полный отказ.

Регресс: `seo-cycle pulse` возвращал 0 даже когда ни один источник не ответил
(pifagorlab, журнал 2026-08-14) — launchd считал провальный прогон успешным.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("pulse_exit_codes", SCRIPTS / "pulse.py")
pulse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pulse)

BOTH_ENGINES_ENV = {
    "YANDEX_OAUTH_TOKEN": "t",
    "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/sa.json",
    "GSC_SITE_URL": "sc-domain:example.com",
}


def make_run_step(fail_scripts: set[str]):
    def fake(script: str, args: list[str], root: pathlib.Path, env: dict[str, str],
             timeout: int = 180):
        if script in fail_scripts:
            return 1, "", f"{script}: boom"
        return 0, "", ""
    return fake


class PulseExitCodeTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="seo-pulse-exit-")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        self.root = pathlib.Path(tmp)
        self.cfg: dict = {}

    def build(self, fail_scripts: set[str]) -> dict:
        with mock.patch.object(pulse, "run_step", make_run_step(fail_scripts)):
            return pulse.build_pulse(self.root, self.cfg, BOTH_ENGINES_ENV, 14, skip_fetch=False)

    def test_all_sources_ok_exit_0(self) -> None:
        report = self.build(fail_scripts=set())
        self.assertFalse(report["degraded"])
        self.assertFalse(report["total_failure"])
        self.assertIsNone(report["degraded_message"])

    def test_one_of_two_sources_fails_exit_1_and_says_partial(self) -> None:
        report = self.build(fail_scripts={"webmaster-fetch.py"})
        self.assertTrue(report["degraded"])
        self.assertFalse(report["total_failure"])
        self.assertIn("частично", report["degraded_message"])
        self.assertIn("webmaster", report["degraded_message"])
        # criterion: "частично" appears in the first 10 lines of rendered output
        rendered_lines = pulse.render_markdown(report).splitlines()
        self.assertTrue(any("частично" in line for line in rendered_lines[:10]),
                         rendered_lines[:10])

    def test_all_sources_fail_exit_2(self) -> None:
        report = self.build(fail_scripts={"webmaster-fetch.py", "gsc-fetch.py"})
        self.assertTrue(report["total_failure"])
        self.assertIn("всё упало", report["degraded_message"])

    def test_pulse_project_exit_code_mapping(self) -> None:
        cfg_path = self.root / "seo-cycle.yaml"
        cfg_path.write_text("project:\n  name: exit-code-test\n", encoding="utf-8")
        args = mock.Mock(days=0, skip_fetch=False)
        with mock.patch.object(pulse, "run_step", make_run_step(set())), \
             mock.patch.object(pulse, "env_chain", lambda root: BOTH_ENGINES_ENV):
            _, rc = pulse.pulse_project(cfg_path, args)
        self.assertEqual(rc, 0)

        with mock.patch.object(pulse, "run_step", make_run_step({"webmaster-fetch.py"})), \
             mock.patch.object(pulse, "env_chain", lambda root: BOTH_ENGINES_ENV):
            _, rc = pulse.pulse_project(cfg_path, args)
        self.assertEqual(rc, 1)

        with mock.patch.object(pulse, "run_step",
                                make_run_step({"webmaster-fetch.py", "gsc-fetch.py"})), \
             mock.patch.object(pulse, "env_chain", lambda root: BOTH_ENGINES_ENV):
            _, rc = pulse.pulse_project(cfg_path, args)
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
