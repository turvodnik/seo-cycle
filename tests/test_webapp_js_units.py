#!/usr/bin/env python3
"""Runs the node-based unit tests for every dashboard renderer (DOM stubbed)."""

from __future__ import annotations

import importlib.util
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

NODE = shutil.which("node")


class DashboardJsUnitsTest(unittest.TestCase):
    @unittest.skipUnless(NODE, "node is not installed")
    def test_all_renderers_pass_unit_checks(self) -> None:
        spec = importlib.util.spec_from_file_location("webapp", SCRIPTS / "webapp.py")
        webapp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(webapp)
        match = re.search(r"<script>(.*)</script>", webapp.PAGE_HTML, re.S)
        self.assertIsNotNone(match)

        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-jsunit-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        page_js = tmp / "page.js"
        # indirect eval держит top-level let/const в собственной области —
        # для интроспекции из тестов переводим их в var (страница не меняется)
        unit_js = re.sub(r"^(?:let|const) ", "var ", match.group(1), flags=re.M)
        page_js.write_text(unit_js, encoding="utf-8")

        proc = subprocess.run(
            [NODE, str(ROOT / "tests" / "js" / "dashboard-units.mjs"), str(page_js)],
            text=True, capture_output=True, timeout=120, check=False,
        )
        self.assertEqual(proc.returncode, 0,
                         f"js units failed:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("PASS", proc.stdout)
        # каждый рендер обязан быть покрыт хотя бы одной проверкой
        for renderer in ("renderOverview", "renderProject", "renderApprovals",
                         "renderCommands", "renderReports", "renderAccess", "runCmd"):
            self.assertIn(renderer, proc.stdout)


if __name__ == "__main__":
    unittest.main()
