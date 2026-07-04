#!/usr/bin/env python3
"""Tests for wp-content-pull.py (site -> local mirror with change/drift detection)."""

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


def wp_item(item_id: int, slug: str, html: str, *, wp_type: str = "post",
            modified: str = "2026-07-01T10:00:00") -> dict:
    return {
        "id": item_id,
        "type": wp_type,
        "slug": slug,
        "link": f"https://example.com/{slug}/",
        "status": "publish",
        "modified": modified,
        "title": {"rendered": slug.replace("-", " ").title()},
        "content": {"rendered": html},
    }


class WpContentPullTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-wp-pull-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: wp-pull\n", encoding="utf-8")

    def run_pull(self, export: list[dict], *args: str) -> subprocess.CompletedProcess:
        export_path = self.tmp / "export.json"
        export_path.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
        env = {key: value for key, value in os.environ.items() if not key.startswith("WP_")}
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "wp-content-pull.py"),
             "--input-file", str(export_path), "--format", "json", *args],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def test_first_pull_mirrors_everything_as_new(self) -> None:
        proc = self.run_pull(
            [wp_item(1, "vagonka-kedr", "<p>Кедровая вагонка для бани.</p>"),
             wp_item(2, "about", "<p>О компании.</p>", wp_type="page")],
            "--write",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["counts"], {"mirrored": 2, "new": 2, "changed_on_site": 0,
                                            "deleted_on_site": 0, "draft_drift": 0})
        mirror_file = self.tmp / "seo" / "content-mirror" / "posts" / "vagonka-kedr.md"
        self.assertTrue(mirror_file.exists())
        body = mirror_file.read_text(encoding="utf-8")
        self.assertIn("Кедровая вагонка", body)
        self.assertIn("content_hash:", body)
        self.assertTrue((self.tmp / "seo" / "content-mirror" / "pages" / "about.md").exists())
        self.assertTrue((self.tmp / "seo" / "content-mirror" / "sync-report.md").exists())

    def test_second_pull_detects_changed_and_deleted(self) -> None:
        self.run_pull([wp_item(1, "vagonka-kedr", "<p>Старый текст.</p>"),
                       wp_item(2, "shtil", "<p>Штиль.</p>")], "--write")
        proc = self.run_pull([wp_item(1, "vagonka-kedr", "<p>Совсем новый текст на сайте.</p>")], "--write")
        report = json.loads(proc.stdout)
        self.assertEqual(report["counts"]["changed_on_site"], 1)
        self.assertEqual(report["counts"]["deleted_on_site"], 1)
        self.assertEqual(report["changed_on_site"][0]["key"], "posts/vagonka-kedr")
        self.assertIn("posts/shtil", report["deleted_on_site"])
        # mirror file for the deleted post is pruned
        self.assertFalse((self.tmp / "seo" / "content-mirror" / "posts" / "shtil.md").exists())

    def test_draft_drift_detected_by_slug(self) -> None:
        drafts = self.tmp / "seo" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "vagonka-kedr.md").write_text("# Вагонка\n\nЛокальный драфт с другим текстом.",
                                                encoding="utf-8")
        proc = self.run_pull([wp_item(1, "vagonka-kedr", "<p>Опубликованный текст, правленный на сайте.</p>")])
        report = json.loads(proc.stdout)
        self.assertEqual(report["counts"]["draft_drift"], 1)
        self.assertEqual(report["draft_drift"][0]["slug"], "vagonka-kedr")

    def test_no_input_is_graceful_hint(self) -> None:
        env = {key: value for key, value in os.environ.items() if not key.startswith("WP_")}
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "wp-content-pull.py")],
            cwd=self.tmp, text=True, capture_output=True, check=False, env=env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--input-file", proc.stderr)


if __name__ == "__main__":
    unittest.main()
