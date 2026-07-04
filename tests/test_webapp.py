#!/usr/bin/env python3
"""Tests for the local web dashboard (webapp.py): auth, API, safety rails."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("webapp", SCRIPTS / "webapp.py")
webapp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webapp)


class WebappTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-webapp-"))
        (cls.tmp / "seo-cycle.yaml").write_text("project:\n  name: webapp-test\n", encoding="utf-8")
        db = cls.tmp / "seo" / "seo.db"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE positions (snapshot_date TEXT, engine TEXT, query TEXT,
                        position REAL, clicks INTEGER, impressions INTEGER, url TEXT)""")
        conn.execute("INSERT INTO positions VALUES ('2026-07-01','yandex','тест',5.0,10,100,'/t/')")
        conn.commit()
        conn.close()
        (cls.tmp / "seo" / "reports").mkdir()
        (cls.tmp / "seo" / "reports" / "sample.md").write_text("# отчёт\n", encoding="utf-8")
        (cls.tmp / "secret.key").write_text("TOP-SECRET", encoding="utf-8")

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), webapp.DashboardHandler)
        cls.server.dashboard_state = {
            "token": "test-token-123",
            "password": "",
            "projects": [{"name": "webapp-test", "path": str(cls.tmp)}],
        }
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def request(self, path: str, *, token: str | None = "test-token-123",
                body: dict | None = None) -> tuple[int, dict | list]:
        req = urllib.request.Request(self.base + path)
        if token:
            req.add_header("X-Auth-Token", token)
        if body is not None:
            req.data = json.dumps(body).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode("utf-8"))

    def test_index_serves_page_without_token(self) -> None:
        with urllib.request.urlopen(self.base + "/", timeout=30) as resp:
            body = resp.read().decode("utf-8")
        self.assertIn("SEO Cycle", body)
        self.assertIn("renderOverview", body)
        self.assertNotIn("test-token-123", body)  # токен не вшит в страницу

    def test_api_requires_token(self) -> None:
        status, payload = self.request("/api/projects", token=None)
        self.assertEqual(status, 401)
        status, payload = self.request("/api/projects", token="wrong")
        self.assertEqual(status, 401)
        status, payload = self.request("/api/projects")
        self.assertEqual(status, 200)
        self.assertEqual(payload[0]["name"], "webapp-test")

    def test_login_without_password_returns_token(self) -> None:
        status, payload = self.request("/api/login", token=None, body={})
        self.assertEqual(status, 200)
        self.assertEqual(payload["token"], "test-token-123")

    def test_login_with_password(self) -> None:
        self.server.dashboard_state["password"] = "s3cret"
        try:
            status, payload = self.request("/api/login", token=None, body={"password": "nope"})
            self.assertEqual(status, 401)
            status, payload = self.request("/api/login", token=None, body={"password": "s3cret"})
            self.assertEqual(status, 200)
            self.assertEqual(payload["token"], "test-token-123")
        finally:
            self.server.dashboard_state["password"] = ""

    def test_summary_composite(self) -> None:
        status, payload = self.request("/api/summary?project=" + urllib.parse.quote(str(self.tmp)))
        self.assertEqual(status, 200)
        self.assertEqual(payload["progress"]["status"], "ok")
        self.assertEqual(payload["progress"]["latest"]["top10"], 1)
        self.assertIn("journey", payload)
        self.assertIn("scorecards", payload)

    def test_run_whitelisted_command(self) -> None:
        status, payload = self.request("/api/run", body={"project": str(self.tmp), "command": "validate"})
        self.assertEqual(status, 200)
        self.assertIn("rc", payload)
        status, payload = self.request("/api/run", body={"project": str(self.tmp), "command": "rm -rf"})
        self.assertEqual(status, 400)

    def test_run_rejects_unknown_project(self) -> None:
        status, payload = self.request("/api/run", body={"project": "/etc", "command": "validate"})
        self.assertEqual(status, 400)

    def test_files_serves_reports_and_blocks_traversal(self) -> None:
        quoted = urllib.parse.quote(str(self.tmp))
        req = urllib.request.Request(
            f"{self.base}/files?project={quoted}&file=seo/reports/sample.md&token=test-token-123")
        with urllib.request.urlopen(req, timeout=30) as resp:
            self.assertIn("отчёт", resp.read().decode("utf-8"))
        status, _ = self.request(f"/files?project={quoted}&file=../../../etc/passwd")
        self.assertIn(status, (403, 404))
        status, _ = self.request(f"/files?project={quoted}&file=secret.key")
        self.assertEqual(status, 404)  # расширение вне whitelist

    def test_ticket_validates_input(self) -> None:
        status, _ = self.request("/api/ticket", body={"project": str(self.tmp), "id": "abc; rm", "action": "approve"})
        self.assertEqual(status, 400)
        status, _ = self.request("/api/ticket", body={"project": str(self.tmp), "id": "abc123", "action": "explode"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
