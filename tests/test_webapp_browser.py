#!/usr/bin/env python3
"""JS-level tests for the dashboard: syntax check via node, e2e render via headless Chrome.

The page JS previously had zero automated coverage. Two layers here:
  1. `node --check` on the extracted <script> — catches syntax errors on every CI run;
  2. headless Chrome `--dump-dom` against a live server — boots the real page,
     runs auto-login + renderOverview, and asserts the rendered DOM.
Both skip cleanly when the binary is unavailable.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("webapp", SCRIPTS / "webapp.py")
webapp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webapp)

report_spec = importlib.util.spec_from_file_location("client_report", SCRIPTS / "client-report.py")
client_report = importlib.util.module_from_spec(report_spec)
report_spec.loader.exec_module(client_report)

CHROME = client_report.find_chrome()
NODE = shutil.which("node")


def extract_script() -> str:
    match = re.search(r"<script>(.*)</script>", webapp.PAGE_HTML, re.S)
    if not match:
        raise AssertionError("PAGE_HTML has no <script> block")
    return match.group(1)


class DashboardJsTest(unittest.TestCase):
    @unittest.skipUnless(NODE, "node is not installed")
    def test_page_script_is_valid_javascript(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-js-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        script = tmp / "page.js"
        script.write_text(extract_script(), encoding="utf-8")
        proc = subprocess.run([NODE, "--check", str(script)], text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, f"JS syntax error: {proc.stderr}")

    def test_script_defines_all_tab_renderers(self) -> None:
        script = extract_script()
        for renderer in ("renderOverview", "renderProject", "renderApprovals",
                         "renderCommands", "renderReports", "renderAccess"):
            self.assertIn(f"async function {renderer}", script)
        for tab in ("overview", "project", "approvals", "commands", "reports", "access"):
            self.assertIn(f'"{tab}"', script)

    @unittest.skipUnless(CHROME, "no Chrome/Chromium found")
    def test_headless_chrome_boots_page_and_renders_overview(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-chrome-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text("project:\n  name: browser-test\n", encoding="utf-8")

        server = ThreadingHTTPServer(("127.0.0.1", 0), webapp.DashboardHandler)
        server.dashboard_state = {"token": "browser-token", "password": "",
                                  "projects": [{"name": "browser-test", "path": str(tmp)}]}
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/"

        proc = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--virtual-time-budget=10000", "--dump-dom", url],
            text=True, capture_output=True, timeout=120, check=False,
        )
        dom = proc.stdout
        self.assertIn("SEO", dom)
        # автологин прошёл и приложение показано (не форма пароля)
        self.assertIn('id="app"', dom)
        self.assertNotIn('id="app" class="hidden"', dom)
        # вкладки отрисованы реальным JS
        for label in ("Портфель", "Проект", "Approvals", "Команды", "Отчёты", "Доступы"):
            self.assertIn(label, dom)
        # renderOverview дошёл до карточек (данных нет — но каркас честный)
        self.assertIn("проектов с данными", dom)


if __name__ == "__main__":
    unittest.main()
