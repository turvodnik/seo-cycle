#!/usr/bin/env python3
"""T-091 round 3 (2026-09-07 round-2 review §5, 🟡): `gsc-indexing-export-
browser.py` and `gsc-request-indexing-browser.py` blocked without surfacing
WHY — the human saw only `"browser_status": "blocked"` with zero findings,
because `browser["error"]` was set to the bare status code
(`runtime.get("status")`, e.g. "missing") instead of
`ensure_browser_runtime()`'s actual explanatory message, and neither script
added a `findings` entry for a `blocked` status at all. `writerzen-browser-
collect.py` already did this correctly (it prints the full hint via
`next_actions`) — these two scripts are brought to the same standard.

Real (not mocked) CLI runs: a fresh sandboxed HOME with no playwright-core
installed and no --install-browser-runtime flag, so the scripts hit their
real "missing browser runtime" code path end to end.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GSC_EXPORT = ROOT / "scripts" / "gsc-indexing-export-browser.py"
GSC_REQUEST = ROOT / "scripts" / "gsc-request-indexing-browser.py"

_CONFIG = """
project:
  name: GSC Browser Test
  domain: gsc-browser.test
locale:
  country: RU
  language: ru
engines:
  - name: yandex
project_type: ecommerce
"""


class GscBrowserBlockedReasonSurfacesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-gsc-browser-blocked-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(_CONFIG, encoding="utf-8")
        # Fresh sandboxed HOME: no playwright-core anywhere, so
        # ensure_browser_runtime() reports "missing" (not --install-browser-
        # runtime, no npm-installed cache).
        self.home = self.tmp / "home"
        self.home.mkdir()

    def _env(self) -> dict:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        return env

    def test_gsc_indexing_export_surfaces_the_actual_reason(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(GSC_EXPORT), str(self.cfg_path),
             "--site-url", "sc-domain:example.com", "--format", "json"],
            cwd=self.tmp, env=self._env(), capture_output=True, text=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report.get("status"), "blocked")
        findings = report.get("findings") or []
        self.assertTrue(
            findings,
            f"заблокированный прогон не оставил ни одного finding'а — причина потеряна: {report!r}",
        )
        joined = " ".join(f.get("message", "") for f in findings)
        self.assertIn(
            "install-browser-runtime", joined,
            f"findings не содержат подсказку про --install-browser-runtime: {findings!r}",
        )

    def test_gsc_request_indexing_surfaces_the_actual_reason(self) -> None:
        queue = self.tmp / "queue.csv"
        # --priority defaults to "P0,P1" — a row with no priority column
        # (or a priority outside that set) is silently filtered out before
        # targets are even counted, which is unrelated to what this test
        # checks; give it a priority that survives the default filter.
        queue.write_text("url,priority,priority_score\nhttps://example.com/a,P0,10\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(GSC_REQUEST), str(self.cfg_path),
             "--site-url", "sc-domain:example.com", "--queue-file", str(queue),
             "--format", "json"],
            cwd=self.tmp, env=self._env(), capture_output=True, text=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report.get("status"), "blocked")
        findings = report.get("findings") or []
        self.assertTrue(
            findings,
            f"заблокированный прогон не оставил ни одного finding'а — причина потеряна: {report!r}",
        )
        joined = " ".join(f.get("message", "") for f in findings)
        self.assertIn(
            "install-browser-runtime", joined,
            f"findings не содержат подсказку про --install-browser-runtime: {findings!r}",
        )


if __name__ == "__main__":
    unittest.main()
