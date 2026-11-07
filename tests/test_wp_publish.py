#!/usr/bin/env python3
"""seo-cycle publish (scripts/wp-publish.py) against a local fake WordPress (3.2.0)."""

from __future__ import annotations

import csv
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PUBLISH = SCRIPTS / "wp-publish.py"
TEMPLATE = ROOT / "config" / "project.template.yaml"
sys.path.insert(0, str(ROOT / "tests" / "helpers"))
sys.path.insert(0, str(ROOT / "tests"))

from fake_wordpress import FakeWordPress  # noqa: E402
from test_draft_gate_config_checks import BAD_DRAFT, clean_draft  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@unittest.skipIf(yaml is None, "PyYAML is required")
class WpPublishTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeWordPress().start()
        self.addCleanup(self.fake.stop)
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="wp-publish-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        self.cfg["project"]["name"] = "Строймаркет Север"
        self.cfg["project"]["domain"] = "stroy-sever.test"
        self.cfg["publishing"]["enabled"] = True
        self.cfg["publishing"]["post_types"]["blog"] = "post"
        self.cfg["publishing"]["seo_plugin"] = "yoast"
        self.write_config()
        drafts = self.tmp / "seo" / "research-package" / "drafts"
        drafts.mkdir(parents=True)
        for name in ("cut.webp", "frame.webp", "layers.webp"):
            (self.tmp / "img").mkdir(exist_ok=True)
            (self.tmp / "img" / name).write_bytes(PNG + name.encode())
        self.draft = drafts / "kak-vybrat-minvatu.publish.md"
        text = clean_draft().replace("page_type: Guide\n", "page_type: Guide\nmeta_title: Как выбрать минвату — гайд\nmeta_description: Плотность, толщина, монтаж.\n")
        self.draft.write_text(text, encoding="utf-8")
        self.outline = self.tmp / "outline.json"
        self.outline.write_text(json.dumps({"page": {"page_type": "Guide"}, "sections": [], "internal_links": [], "faq": []}),
                                encoding="utf-8")

    def write_config(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text(yaml.safe_dump(self.cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def publish(self, *extra: str, env: dict | None = None, draft: pathlib.Path | None = None) -> tuple[int, dict, str]:
        base = {k: v for k, v in os.environ.items() if not k.startswith("WP_")}
        proc = subprocess.run(
            [sys.executable, str(PUBLISH), str(draft or self.draft), "--outline", str(self.outline), "--format", "json", *extra],
            cwd=self.tmp, text=True, capture_output=True, check=False, env={**base, **(env or {})}, timeout=120,
        )
        report = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
        return proc.returncode, report, proc.stderr

    def test_plan_without_live_sends_nothing(self) -> None:
        rc, report, stderr = self.publish(env=self.fake.env())
        self.assertEqual(rc, 0, stderr)
        self.assertEqual(report["status"], "plan")
        plan = report["plan"]
        self.assertEqual(plan["rest_base"], "posts")
        self.assertEqual(plan["slug"], "kak-vybrat-minvatu")
        self.assertEqual(plan["meta"]["_yoast_wpseo_title"], "Как выбрать минвату — гайд")
        self.assertEqual(plan["featured"]["src"], "/img/cut.webp")
        self.assertTrue(plan["sources_block"])
        self.assertEqual(self.fake.requests, [])
        self.assertTrue(self.draft.with_suffix(".publish-plan.json").exists())

    def test_gate_failure_refuses(self) -> None:
        bad = self.draft.with_name("bad.publish.md")
        bad.write_text(BAD_DRAFT, encoding="utf-8")
        rc, report, _ = self.publish("--live", env=self.fake.env(), draft=bad)
        self.assertEqual(rc, 1)
        self.assertEqual(report["status"], "refused_by_gate")
        self.assertTrue(any("stop_words_found" in item for item in report["errors"]))
        self.assertIn("seo-cycle loop draft", report["next"][0])
        self.assertEqual(self.fake.requests, [])

    def test_live_create_then_update_same_post(self) -> None:
        rc, report, stderr = self.publish("--live", env=self.fake.env())
        self.assertEqual(rc, 0, (report, stderr))
        self.assertEqual((report["status"], report["action"]), ("published", "create"))
        self.assertEqual(report["verify"], "ok")
        wp_id = report["wp_id"]
        post = self.fake.items["posts"][wp_id]
        self.assertEqual(post["status"], "publish")
        self.assertEqual(post["meta"]["_yoast_wpseo_metadesc"], "Плотность, толщина, монтаж.")
        self.assertIn("<figcaption>Плиту ставят враспор между стойками.</figcaption>", post["content"])
        self.assertIn('class="fact-sources"', post["content"])
        self.assertIn("/uploads/frame.webp", post["content"])
        self.assertNotIn("/img/frame.webp", post["content"])
        self.assertEqual(post["featured_media"], next(m["id"] for m in self.fake.items["media"].values()
                                                      if m["source_url"].endswith("cut.webp")))
        self.assertEqual(len(self.fake.items["media"]), 3)
        # frontmatter written back, publish log appended
        front = self.draft.read_text(encoding="utf-8")
        self.assertIn(f"wp_id: {wp_id}\n", front)
        self.assertIn("wp_url:", front)
        with (self.tmp / "seo" / "publish-log.csv").open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[-1]["status"], "publish")
        self.assertIn(f"wp_id={wp_id}", rows[-1]["notes"])
        self.assertTrue(self.draft.with_suffix(".publish-report.json").exists())
        # second run: same post updated, media not re-uploaded
        media_uploads = len(self.fake.writes("/wp-json/wp/v2/media"))
        rc, report, stderr = self.publish("--live", env=self.fake.env())
        self.assertEqual(rc, 0, stderr)
        self.assertEqual((report["action"], report["wp_id"]), ("update", wp_id))
        self.assertEqual(len(self.fake.items["posts"]), 1)
        self.assertEqual(len(self.fake.writes("/wp-json/wp/v2/media")), media_uploads)

    def test_existing_post_is_found_by_slug(self) -> None:
        self.fake.items["posts"][7] = {"id": 7, "slug": "kak-vybrat-minvatu", "status": "draft",
                                       "link": f"{self.fake.base_url}/kak-vybrat-minvatu/"}
        rc, report, stderr = self.publish("--live", "--status", "draft", env=self.fake.env())
        self.assertEqual(rc, 0, stderr)
        self.assertEqual((report["action"], report["wp_id"], report["status"]), ("update", 7, "saved"))
        self.assertNotIn("verify", report)  # drafts are not public

    def test_unregistered_seo_meta_is_a_warning(self) -> None:
        self.fake.drop_meta = True
        rc, report, _ = self.publish("--live", env=self.fake.env())
        self.assertEqual(rc, 0)
        self.assertTrue(any("SEO-мета не записалась" in item for item in report["warnings"]))

    def test_verify_catches_stripped_alt(self) -> None:
        self.fake.page_html_override = "<html><h1>Как выбрать минвату для каркасной стены</h1><img src='/x.webp'></html>"
        rc, report, _ = self.publish("--live", env=self.fake.env())
        self.assertEqual(rc, 3)
        self.assertEqual(report["verify"], "failed")
        self.assertTrue(any("без alt" in item for item in report["warnings"]))
        self.assertTrue(any("подписей" in item for item in report["warnings"]))

    def test_refusals_and_config_errors(self) -> None:
        rc, _, stderr = self.publish("--live")
        self.assertEqual(rc, 2)
        self.assertIn("seo-cycle auth login wordpress", stderr)
        bad_env = {**self.fake.env(), "WP_APP_PASSWORD": "wrong"}
        rc, report, stderr = self.publish("--live", env=bad_env)
        self.assertEqual(rc, 1)
        self.assertNotIn("Traceback", stderr)
        self.assertIn("Application Password", report["errors"][0])
        self.cfg["publishing"]["enabled"] = False
        self.write_config()
        rc, _, stderr = self.publish("--live", env=self.fake.env())
        self.assertEqual(rc, 2)
        self.assertIn("publishing.enabled", stderr)
        rc, _, stderr = self.publish("--live", "--outline-missing", env=self.fake.env())
        self.assertEqual(rc, 2)

    def test_missing_image_file_refuses_before_any_write(self) -> None:
        (self.tmp / "img" / "frame.webp").unlink()
        rc, report, _ = self.publish("--live", env=self.fake.env())
        self.assertEqual(rc, 1)
        self.assertIn("frame.webp", report["errors"][0])
        self.assertEqual(self.fake.writes("/wp-json"), [])

    def test_require_approval_needs_an_approved_content_publish_ticket(self) -> None:
        self.cfg["publishing"]["require_approval"] = True
        self.write_config()
        rc, _, stderr = self.publish("--live", env=self.fake.env())
        self.assertEqual(rc, 1)
        self.assertIn("--ticket", stderr)
        gate = SCRIPTS / "approval-gate.py"
        created = subprocess.run([sys.executable, str(gate), "create", "--type", "content_publish",
                                  "--title", "Пост", "--file", str(self.draft)],
                                 cwd=self.tmp, text=True, capture_output=True, check=True)
        ticket = created.stdout.strip().split()[-1]
        rc, _, stderr = self.publish("--live", "--ticket", ticket, env=self.fake.env())
        self.assertEqual(rc, 1)
        self.assertIn("pending", stderr)
        subprocess.run([sys.executable, str(gate), "approve", ticket], cwd=self.tmp, check=True, capture_output=True)
        rc, report, stderr = self.publish("--live", "--ticket", ticket, env=self.fake.env())
        self.assertEqual(rc, 0, stderr)
        self.assertEqual(report["status"], "published")

    def test_cycle_dir_gets_07_published(self) -> None:
        rc, report, _ = self.publish("--live", "--cycle-dir", "seo/cycles/minvata", env=self.fake.env())
        self.assertEqual(rc, 0)
        published = (self.tmp / "seo" / "cycles" / "minvata" / "07-published.md").read_text(encoding="utf-8")
        self.assertIn(report["url"], published)


if __name__ == "__main__":
    unittest.main()
