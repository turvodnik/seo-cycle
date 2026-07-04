#!/usr/bin/env python3
"""Tests for site-crawl, structure-map, link-liveness, content-repurpose."""

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

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

PAGES = {
    "/": "<title>Главная</title><h1>Дом</h1><meta name='description' content='x'>"
         "<a href='/catalog/'>каталог</a><a href='/about'>о нас</a><a href='/dead'>битая</a>",
    "/catalog/": "<title>Каталог</title><h1>Каталог</h1><a href='/catalog/vagonka'>вагонка</a>",
    "/catalog/vagonka": "<title>Каталог</title><h1>Вагонка</h1>",  # дубль title с /catalog/... нет: тот же title → дубль
    "/about": "<h1>О нас</h1>",  # нет title и description
}


class SiteHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/robots.txt":
            self.send_response(404); self.end_headers(); return
        body = PAGES.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        payload = f"<html><head></head><body>{body}</body></html>".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_HEAD(self):  # noqa: N802
        status = 200 if self.path in PAGES else 404
        self.send_response(status)
        self.end_headers()

    def log_message(self, *args):
        return


class CrawlToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SiteHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-crawl-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: crawl\n", encoding="utf-8")

    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / name), *args],
                              cwd=self.tmp, text=True, capture_output=True, check=False)

    def test_crawl_live_collects_findings(self) -> None:
        proc = self.run_script("site-crawl.py", "--live", "--start", self.base + "/",
                               "--delay", "0", "--write", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertGreaterEqual(report["crawl"]["crawled"], 4)
        ids = {f["id"] for f in report["findings"]}
        self.assertIn("broken_internal", ids)      # /dead → 404
        self.assertIn("missing_title", ids)        # /about
        self.assertIn("duplicate_title", ids)      # /catalog/ и /catalog/vagonka
        self.assertIn("links_to_broken", ids)      # главная ссылается на /dead
        self.assertTrue((self.tmp / "seo" / "crawl" / "site-crawl.json").exists())

    def test_crawl_requires_live_or_input(self) -> None:
        proc = self.run_script("site-crawl.py")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--live", proc.stderr)

    def test_structure_map_from_crawl(self) -> None:
        self.run_script("site-crawl.py", "--live", "--start", self.base + "/", "--delay", "0", "--write")
        proc = self.run_script("structure-map.py", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("/catalog", proc.stdout)
        html_body = (self.tmp / "seo" / "crawl" / "structure-map.html").read_text(encoding="utf-8")
        self.assertIn("<details", html_body)
        self.assertIn("catalog", html_body)

    def test_link_liveness_flags_dead_sources(self) -> None:
        drafts = self.tmp / "seo" / "research-package" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "a.md").write_text(
            f"# Статья\nисточник ({self.base}/catalog/) и мёртвый ({self.base}/dead)\n",
            encoding="utf-8")
        proc = self.run_script("link-liveness.py", "--live", "--write", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["links_found"], 2)
        self.assertEqual(report["alive"], 1)
        self.assertEqual(len(report["dead"]), 1)
        self.assertIn("/dead", report["dead"][0]["url"])
        # повторный прогон без сети использует кэш
        proc2 = self.run_script("link-liveness.py", "--format", "json")
        self.assertEqual(json.loads(proc2.stdout)["alive"], 1)

    def test_repurpose_builds_skeletons(self) -> None:
        drafts = self.tmp / "seo" / "research-package" / "drafts"
        drafts.mkdir(parents=True)
        draft = drafts / "vagonka.md"
        draft.write_text(
            "# Вагонка штиль: как выбрать\n\nЛид-абзац о выборе вагонки за 90 секунд.\n\n"
            "## Сорта и цены\n\nЦена за м2 от 900 рублей в 2026 году.\n\n"
            "## Монтаж\n\nШаг обрешётки 50 см.\n\n### Сколько сохнет вагонка?\n\nОколо 14 дней.\n",
            encoding="utf-8")
        proc = self.run_script("content-repurpose.py", str(draft), "--write", "--url", "https://x.ru/vagonka")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = (self.tmp / "seo" / "research-package" / "repurpose" / "vagonka.md").read_text(encoding="utf-8")
        for marker in ("Telegram-пост", "Видео-скрипт", "Email-дайджест",
                       "900 рублей", "https://x.ru/vagonka", "Сколько сохнет вагонка?"):
            self.assertIn(marker, out)
        self.assertIn("[TODO", out)  # каркас, а не готовый текст


if __name__ == "__main__":
    unittest.main()
