#!/usr/bin/env python3
"""Smoke tests for the live AI bot access checker."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "project.template.yaml"
SCRIPT = ROOT / "scripts" / "ai-bot-access-check.py"


class BotAccessHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        user_agent = self.headers.get("User-Agent", "")
        if self.path == "/robots.txt":
            body = "User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if "ClaudeBot" in user_agent:
            body = "blocked by edge"
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        body = "ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - stdlib API
        return


@unittest.skipIf(yaml is None, "PyYAML is required")
class AiBotAccessCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-ai-bot-access-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = "Bot Access Test"
        cfg["project"]["domain"] = "127.0.0.1"
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), BotAccessHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def run_check(self) -> dict:
        url = f"http://127.0.0.1:{self.server.server_port}/"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(self.cfg_path),
                "--url",
                url,
                "--bots",
                "GPTBot,ClaudeBot,OAI-SearchBot,Googlebot",
                "--timeout",
                "2",
                "--write",
                "--format",
                "json",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_detects_robots_block_and_waf_block(self) -> None:
        report = self.run_check()
        by_name = {row["name"]: row for row in report["results"]}

        self.assertEqual(by_name["GPTBot"]["outcome"], "robots_block")
        self.assertEqual(by_name["ClaudeBot"]["outcome"], "waf_block")
        self.assertEqual(by_name["OAI-SearchBot"]["outcome"], "available")
        self.assertEqual(by_name["Googlebot"]["outcome"], "available")
        self.assertEqual(report["summary"]["robots_block"], 1)
        self.assertEqual(report["summary"]["waf_block"], 1)
        self.assertTrue((self.tmp / "seo" / "vnext" / "ai-bot-access-check.md").exists())
        self.assertTrue((self.tmp / "seo" / "vnext" / "latest-ai-bot-access-check.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
