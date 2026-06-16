#!/usr/bin/env python3
"""Tests for IndexNow and Yandex Webmaster recrawl submitters."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer


ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEXNOW = ROOT / "scripts" / "indexnow-submit.py"
YANDEX = ROOT / "scripts" / "yandex-recrawl-submit.py"


class CaptureHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"raw": body}
        self.__class__.requests.append({"method": "POST", "path": self.path, "headers": dict(self.headers), "body": parsed})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self) -> None:  # noqa: N802
        self.__class__.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers), "body": {}})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"tasks":[{"url":"https://example.com/shop/osb/","status":"IN_PROGRESS"}]}')

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


class TestServer:
    def __enter__(self) -> "TestServer":
        CaptureHandler.requests = []
        self.server = HTTPServer(("127.0.0.1", 0), CaptureHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    @property
    def requests(self) -> list[dict]:
        return CaptureHandler.requests


class BingYandexIndexingSubmitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-bing-yandex-submit-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(
            """
project:
  name: Submit Test
  domain: example.com
locale:
  country: RU
  language: ru
engines:
  - name: yandex
  - name: bing
project_type: ecommerce
""",
            encoding="utf-8",
        )
        queue = self.tmp / "seo" / "technical" / "gsc-indexing-request-queue.csv"
        queue.parent.mkdir(parents=True)
        queue.write_text(
            "priority,priority_score,url,page_type\n"
            "P0,100,https://example.com/shop/osb/,woocommerce_category\n"
            "P1,80,https://example.com/blog/osb-guide/,blog\n"
            "P2,20,https://example.com/low-priority/,blog\n",
            encoding="utf-8",
        )

    def test_indexnow_live_submits_queue_without_leaking_key(self) -> None:
        with TestServer() as server:
            env = {
                "INDEXNOW_KEY": "fixture-indexnow-key-123456",
                "INDEXNOW_KEY_LOCATION": "https://example.com/indexnow-key.txt",
            }
            proc = subprocess.run(
                [
                    sys.executable,
                    str(INDEXNOW),
                    str(self.cfg_path),
                    "--endpoint",
                    f"{server.url}/indexnow",
                    "--queue-file",
                    "seo/technical/gsc-indexing-request-queue.csv",
                    "--priority",
                    "P0,P1",
                    "--max",
                    "2",
                    "--batch-size",
                    "2",
                    "--live",
                    "--write",
                    "--format",
                    "json",
                ],
                cwd=self.tmp,
                env={**__import__("os").environ, **env},
                check=True,
                text=True,
                capture_output=True,
            )
        report = json.loads(proc.stdout)

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["summary"]["submitted"], 2)
        self.assertEqual(len(server.requests), 1)
        self.assertEqual(server.requests[0]["body"]["host"], "example.com")
        self.assertEqual(server.requests[0]["body"]["key"], "fixture-indexnow-key-123456")
        self.assertNotIn("fixture-indexnow-key-123456", proc.stdout)
        self.assertTrue((self.tmp / "seo" / "technical" / "indexnow-submit-log.csv").exists())

    def test_yandex_recrawl_live_submits_and_status_without_leaking_token(self) -> None:
        with TestServer() as server:
            env = {
                "YANDEX_OAUTH_TOKEN": "fixture-yandex-token-123456",
                "YANDEX_USER_ID": "123",
                "YANDEX_WEBMASTER_HOST_ID": "https:example.com:443",
            }
            submit = subprocess.run(
                [
                    sys.executable,
                    str(YANDEX),
                    str(self.cfg_path),
                    "--api-base",
                    f"{server.url}/v4",
                    "--queue-file",
                    "seo/technical/gsc-indexing-request-queue.csv",
                    "--priority",
                    "P0",
                    "--max",
                    "1",
                    "--live",
                    "--write",
                    "--format",
                    "json",
                ],
                cwd=self.tmp,
                env={**__import__("os").environ, **env},
                check=True,
                text=True,
                capture_output=True,
            )
            status = subprocess.run(
                [
                    sys.executable,
                    str(YANDEX),
                    str(self.cfg_path),
                    "--api-base",
                    f"{server.url}/v4",
                    "--mode",
                    "status",
                    "--live",
                    "--write",
                    "--format",
                    "json",
                ],
                cwd=self.tmp,
                env={**__import__("os").environ, **env},
                check=True,
                text=True,
                capture_output=True,
            )
        submit_report = json.loads(submit.stdout)
        status_report = json.loads(status.stdout)

        self.assertEqual(submit_report["status"], "ready")
        self.assertEqual(submit_report["summary"]["submitted"], 1)
        self.assertEqual(status_report["status"], "ready")
        self.assertEqual(status_report["summary"]["queue_rows"], 1)
        self.assertEqual(server.requests[0]["body"]["url"], "https://example.com/shop/osb/")
        self.assertIn("OAuth fixture-yandex-token-123456", server.requests[0]["headers"]["Authorization"])
        self.assertNotIn("fixture-yandex-token-123456", submit.stdout)
        self.assertNotIn("fixture-yandex-token-123456", status.stdout)
        self.assertTrue((self.tmp / "seo" / "technical" / "yandex-recrawl-submit.csv").exists())
        self.assertTrue((self.tmp / "seo" / "technical" / "yandex-recrawl-status.csv").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
