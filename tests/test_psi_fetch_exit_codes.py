#!/usr/bin/env python3
"""T-052: psi-fetch.py batch mode used to `continue` past a failed URL silently
and always exit 0 — a broken PSI API key/network made every run look clean
even when zero pages were actually collected."""

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

spec = importlib.util.spec_from_file_location("psi_fetch", SCRIPTS / "psi-fetch.py")
psi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(psi)


class PsiFetchExitCodeTest(unittest.TestCase):
    def run_main(self, argv: list[str], fetch_results: list):
        calls = iter(fetch_results)

        def fake_fetch(url, strategy, api_key):
            result = next(calls)
            if isinstance(result, Exception):
                raise result
            return result

        with mock.patch.object(sys, "argv", ["psi-fetch.py", *argv]), \
             mock.patch.object(psi, "fetch", fake_fetch), \
             mock.patch.object(psi.time, "sleep", lambda *_: None):
            return psi.main()

    def test_all_urls_ok_exit_0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            urls_file = pathlib.Path(tmp) / "urls.txt"
            urls_file.write_text("https://a.example\nhttps://b.example\n", encoding="utf-8")
            out_dir = pathlib.Path(tmp) / "out"
            rc = self.run_main(["--urls-file", str(urls_file), "--output-dir", str(out_dir)],
                                fetch_results=[{"ok": 1}, {"ok": 2}])
        self.assertEqual(rc, 0)

    def test_some_urls_fail_exit_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            urls_file = pathlib.Path(tmp) / "urls.txt"
            urls_file.write_text("https://a.example\nhttps://b.example\n", encoding="utf-8")
            out_dir = pathlib.Path(tmp) / "out"
            rc = self.run_main(["--urls-file", str(urls_file), "--output-dir", str(out_dir)],
                                fetch_results=[{"ok": 1}, RuntimeError("boom")])
        self.assertEqual(rc, 1)

    def test_all_urls_fail_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            urls_file = pathlib.Path(tmp) / "urls.txt"
            urls_file.write_text("https://a.example\nhttps://b.example\n", encoding="utf-8")
            out_dir = pathlib.Path(tmp) / "out"
            rc = self.run_main(["--urls-file", str(urls_file), "--output-dir", str(out_dir)],
                                fetch_results=[RuntimeError("boom"), RuntimeError("boom")])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
