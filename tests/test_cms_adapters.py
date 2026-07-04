#!/usr/bin/env python3
"""Tests for the Tilda/Bitrix mirror adapters over the shared mirror engine."""

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
SCRIPTS = ROOT / "scripts"


class CmsAdapterTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cms-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: cms\n", encoding="utf-8")

    def run_pull(self, script: str, export: object, *args: str) -> subprocess.CompletedProcess:
        export_path = self.tmp / "export.json"
        export_path.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("TILDA_", "BITRIX_"))}
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), "--input-file", str(export_path),
             "--format", "json", *args],
            cwd=self.tmp, text=True, capture_output=True, check=False, env=env,
        )


class TildaAdapterTest(CmsAdapterTestBase):
    EXPORT = [
        {"id": 101, "title": "Вагонка из кедра", "alias": "vagonka-kedr", "published": "1688000000",
         "date": "2026-06-01 10:00:00", "projectdomain": "example.com",
         "html": "<h1>Вагонка</h1><p>Кедровая вагонка для бани.</p>"},
        {"id": 102, "title": "Черновик", "alias": "draft-page", "published": "0",
         "date": "2026-06-02 10:00:00", "html": "<p>ещё не опубликовано</p>"},
    ]

    def test_pull_mirrors_pages_and_marks_status(self) -> None:
        proc = self.run_pull("tilda-content-pull.py", self.EXPORT, "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["source"], "tilda")
        self.assertEqual(report["counts"]["mirrored"], 2)
        mirror = self.tmp / "seo" / "content-mirror" / "pages" / "vagonka-kedr.md"
        body = mirror.read_text(encoding="utf-8")
        self.assertIn("Кедровая вагонка", body)
        self.assertIn("status: publish", body)
        self.assertIn("url: https://example.com/vagonka-kedr", body)

    def test_change_detection_between_pulls(self) -> None:
        self.run_pull("tilda-content-pull.py", self.EXPORT, "--write")
        changed = [dict(self.EXPORT[0], html="<p>Совсем другой текст на сайте.</p>"), self.EXPORT[1]]
        report = json.loads(self.run_pull("tilda-content-pull.py", changed, "--write").stdout)
        self.assertEqual(report["counts"]["changed_on_site"], 1)
        self.assertEqual(report["changed_on_site"][0]["key"], "pages/vagonka-kedr")

    def test_live_without_env_fails_clearly(self) -> None:
        env = {key: value for key, value in os.environ.items() if not key.startswith("TILDA_")}
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "tilda-content-pull.py"), "--live"],
            cwd=self.tmp, text=True, capture_output=True, check=False, env=env,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("TILDA_PUBLIC_KEY", proc.stderr)


class BitrixAdapterTest(CmsAdapterTestBase):
    EXPORT = [
        {"ID": 7, "CODE": "vagonka-kedr", "NAME": "Вагонка из кедра", "ACTIVE": "Y",
         "IBLOCK_CODE": "catalog", "DETAIL_PAGE_URL": "/catalog/vagonka-kedr/",
         "TIMESTAMP_X": "01.06.2026 10:00:00",
         "DETAIL_TEXT": "<p>Кедровая вагонка сорт Экстра.</p>"},
        {"ID": 8, "NAME": "Без кода", "ACTIVE": "N", "DETAIL_TEXT": "черновой элемент"},
    ]

    def test_pull_normalizes_bitrix_fields(self) -> None:
        proc = self.run_pull("bitrix-content-pull.py", self.EXPORT, "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["source"], "bitrix")
        self.assertEqual(report["counts"]["mirrored"], 2)
        mirror = self.tmp / "seo" / "content-mirror" / "catalog" / "vagonka-kedr.md"
        body = mirror.read_text(encoding="utf-8")
        self.assertIn("Кедровая вагонка сорт Экстра", body)
        self.assertIn("status: publish", body)
        fallback = self.tmp / "seo" / "content-mirror" / "elements" / "element-8.md"
        self.assertIn("status: inactive", fallback.read_text(encoding="utf-8"))

    def test_draft_drift_shared_engine(self) -> None:
        drafts = self.tmp / "seo" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "vagonka-kedr.md").write_text("# Вагонка\n\nЛокальный драфт, другой текст.",
                                                encoding="utf-8")
        report = json.loads(self.run_pull("bitrix-content-pull.py", self.EXPORT).stdout)
        self.assertEqual(report["counts"]["draft_drift"], 1)

    def test_live_without_url_fails_clearly(self) -> None:
        env = {key: value for key, value in os.environ.items() if not key.startswith("BITRIX_")}
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "bitrix-content-pull.py"), "--live"],
            cwd=self.tmp, text=True, capture_output=True, check=False, env=env,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("BITRIX_EXPORT_URL", proc.stderr)


if __name__ == "__main__":
    unittest.main()
