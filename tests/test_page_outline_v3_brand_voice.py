#!/usr/bin/env python3
"""page-outline-v3 carries the project's brand voice profile into the brief (3.1.0)."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))

import test_research_package_quality as rpq  # noqa: E402  (fixture builder only)
from seo_cycle_core import brand_voice as bv  # noqa: E402
from seo_cycle_core.config import dump_yaml, load_yaml, parse_yaml_text  # noqa: E402

V3 = SCRIPTS / "page-outline-v3.py"
QUALITY = SCRIPTS / "page-outline-quality.py"
PAGE = "/tools/virtual-hair-color-try-on/"


class OutlineBrandVoiceTest(unittest.TestCase):
    write_package = rpq.ResearchPackageQualityTest.write_package
    write_csv = rpq.ResearchPackageQualityTest.write_csv

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="outline-voice-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.package = self.tmp / "seo" / "research-package"
        self.package.mkdir(parents=True)
        self.write_package()
        cfg = load_yaml(ROOT / "config" / "project.template.yaml")
        cfg["project"]["name"] = "Hair Lab"
        cfg["project"]["brand_name_user_facing"] = "Hair Lab"
        cfg["project"]["domain"] = "hairlab.test"
        cfg["locale"]["language"] = "en"
        (self.tmp / "seo-cycle.yaml").write_text(dump_yaml(cfg), encoding="utf-8")
        self.cfg = cfg

    def write_profile(self, **changes: object) -> dict:
        profile = parse_yaml_text(bv.render_init(self.cfg))
        profile["voice"]["summary"] = "Plain-spoken stylist: short answers, then proof."
        profile["lexicon"]["preferred"] = {"hair dye": "hair color"}
        profile.update(changes)
        path = self.tmp / "seo" / "brand" / "voice.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump_yaml(profile), encoding="utf-8")
        return profile

    def outline(self) -> dict:
        proc = subprocess.run(
            [sys.executable, str(V3), str(self.package), "--page", PAGE, "--write", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=True,
        )
        return json.loads(proc.stdout)

    def test_profile_reaches_outline_and_copywriter_brief(self) -> None:
        self.write_profile()
        outline = self.outline()
        block = outline["brand_voice"]
        self.assertEqual(block["profile"], "seo/brand/voice.yaml")
        self.assertEqual(block["method"]["page_type"], "tool")
        self.assertEqual(block["method"]["structure"][0], "tool_first")
        self.assertEqual(block["address"], "you")
        brief = pathlib.Path(outline["paths"]["copywriter_ready"]).read_text(encoding="utf-8")
        self.assertIn("## Tone Rules", brief)  # old section kept
        self.assertIn("## Brand voice and method", brief)
        self.assertIn("Plain-spoken stylist", brief)
        self.assertIn("«hair color»", brief)
        markdown = pathlib.Path(outline["paths"]["markdown"]).read_text(encoding="utf-8")
        self.assertIn("## v3 Brand Voice", markdown)
        # the brief with a profile still passes the outline gate
        proc = subprocess.run(
            [sys.executable, str(QUALITY), str(self.package), "--version", "v3", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=True,
        )
        self.assertEqual(json.loads(proc.stdout)["status"], "pass")

    def test_real_author_in_profile_allows_expert_first_person(self) -> None:
        self.write_profile(authors=[{"name": "Ann Lee", "role": "colorist", "proof_url": "https://example.com/ann"}],
                           first_person_allowed=True)
        outline = self.outline()
        self.assertEqual(outline["eeat_guard"]["expert_author_mode"], "real_expert_allowed")
        self.assertTrue(outline["brand_voice"]["first_person_allowed"])

    def test_without_profile_outline_has_no_voice_block(self) -> None:
        outline = self.outline()
        self.assertNotIn("brand_voice", outline)
        self.assertEqual(outline["eeat_guard"]["expert_author_mode"], "no_fabricated_first_person")

    def test_broken_profile_is_a_note_not_a_failure(self) -> None:
        path = self.tmp / "seo" / "brand" / "voice.yaml"
        path.parent.mkdir(parents=True)
        path.write_text("voice: [oops\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(V3), str(self.package), "--page", PAGE, "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("NOTE: профиль голоса не подключён", proc.stderr)
        self.assertNotIn("brand_voice", json.loads(proc.stdout))


if __name__ == "__main__":
    unittest.main()
