#!/usr/bin/env python3
"""seo_cycle_core.wordpress against a local fake WordPress (3.2.0)."""

from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "helpers"))

from fake_wordpress import FakeWordPress  # noqa: E402
from seo_cycle_core import wordpress as wp  # noqa: E402


class WordPressClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeWordPress().start()
        self.addCleanup(self.fake.stop)
        self.client = wp.WPClient.from_env(self.fake.env(), timeout=10)

    def test_credentials_and_meta_mapping(self) -> None:
        self.assertEqual(wp.missing_credentials({}), list(wp.ENV_NAMES))
        self.assertEqual(wp.missing_credentials(self.fake.env()), [])
        self.assertEqual(wp.credentials({"WP_APP_PASSWORD": "a b c", "WP_BASE_URL": "https://x.example.com/"}),
                         {"base_url": "https://x.example.com", "user": "", "app_password": "abc"})
        self.assertEqual(wp.seo_meta("Yoast", "T", "D"), {"_yoast_wpseo_title": "T", "_yoast_wpseo_metadesc": "D"})
        self.assertEqual(wp.seo_meta("seopress", "T", ""), {"_seopress_titles_title": "T"})
        self.assertEqual(wp.seo_meta("rankmath", "", "D"), {"rank_math_description": "D"})
        self.assertEqual(wp.seo_meta("none", "T", "D"), {})
        with self.assertRaises(wp.WPError):
            wp.WPClient("")

    def test_upsert_find_get_and_list(self) -> None:
        created = self.client.upsert("posts", {"title": "A", "slug": "a", "status": "draft", "content": "x"})
        self.assertEqual(self.client.find_by_slug("posts", "a")["id"], created["id"])
        self.assertIsNone(self.client.find_by_slug("posts", "nope"))
        updated = self.client.upsert("posts", {"title": "A2", "status": "publish"}, created["id"])
        self.assertEqual(updated["id"], created["id"])
        self.assertEqual(self.client.get_item("posts", created["id"])["status"], "publish")
        self.assertIsNone(self.client.get_item("posts", 999))
        for index in range(3):
            self.client.upsert("posts", {"title": f"P{index}", "slug": f"p{index}", "status": "publish"})
        listed = self.client.list_items("posts", status="publish", max_pages=5)
        self.assertEqual(len(listed), 4)

    def test_media_upload_sets_alt_and_caption(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="wp-media-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        image = tmp / "плита.webp"
        image.write_bytes(b"RIFF....WEBP")
        media = self.client.upload_media(image, alt="Плита в разрезе", caption="Подпись")
        self.assertTrue(media["source_url"].endswith("/uploads/плита.webp"))
        self.assertEqual(self.fake.items["media"][media["id"]]["alt_text"], "Плита в разрезе")

    def test_errors_are_one_line_messages(self) -> None:
        bad = wp.WPClient(self.fake.base_url, "editor", "wrong", timeout=10)
        with self.assertRaises(wp.WPError) as ctx:
            bad.upsert("posts", {"title": "x"})
        self.assertEqual(ctx.exception.status, 401)
        self.assertIn("Application Password", str(ctx.exception))
        with self.assertRaises(wp.WPError) as ctx:
            self.client.get("wp/v2/unknown")
        self.assertIn("REST API недоступен", str(ctx.exception))
        dead = wp.WPClient("http://127.0.0.1:9", "u", "p", timeout=2)
        with self.assertRaises(wp.WPError) as ctx:
            dead.get("wp/v2/posts")
        self.assertIn("недоступен", str(ctx.exception))
        self.assertIn("403", wp._describe(403, "{}", "u"))
        self.assertIn("не найден", wp._describe(404, '{"code":"x","message":"m"}', "u"))
        self.assertIn("boom", wp._describe(500, "boom", "u"))

    def test_fetch_public_page(self) -> None:
        post = self.client.upsert("posts", {"title": "Видимый", "slug": "vidimyi", "status": "publish", "content": "<p>t</p>"})
        self.assertIn("<h1>Видимый</h1>", self.client.fetch_page(post["link"]))
        with self.assertRaises(wp.WPError):
            self.client.fetch_page(self.fake.base_url + "/missing/")


if __name__ == "__main__":
    unittest.main()
