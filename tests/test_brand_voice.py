#!/usr/bin/env python3
"""Brand voice / writing methods / image types profile (3.1.0).

seo_cycle_core.brand_voice in-process (counted by the coverage job) and the
`scripts/brand-voice.py` CLI (`seo-cycle voice …`) as a subprocess.
"""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_cycle_core import brand_voice as bv  # noqa: E402
from seo_cycle_core.config import dump_yaml, load_yaml, parse_yaml_text  # noqa: E402

CLI = ROOT / "scripts" / "brand-voice.py"
TEMPLATE_CFG = load_yaml(ROOT / "config" / "project.template.yaml")


def project_cfg() -> dict:
    cfg = copy.deepcopy(TEMPLATE_CFG)
    cfg["project"]["name"] = "Строймаркет Север"
    cfg["project"]["brand_name_user_facing"] = "Строймаркет Север"
    cfg["project"]["domain"] = "stroy-sever.test"
    return cfg


def filled_profile() -> dict:
    profile = parse_yaml_text(bv.render_init(project_cfg()))
    profile["identity"]["who_we_are"] = "Склад кровли и утеплителя в Петербурге."
    profile["identity"]["audiences"] = [{"name": "Частный застройщик", "task": "утеплить дом", "pains": ["переплата"]}]
    profile["voice"]["summary"] = "Говорим как прораб-консультант: коротко и по делу."
    profile["lexicon"]["preferred"] = {"минвата": "минеральная вата"}
    profile["lexicon"]["forbidden"] = ["дешёвый"]
    return profile


class ProfileCoreTest(unittest.TestCase):
    def test_render_init_is_valid_and_carries_config_values(self) -> None:
        profile = parse_yaml_text(bv.render_init(project_cfg()))
        self.assertEqual(bv.validate_profile(profile), [])
        self.assertEqual(profile["language"], "ru")
        self.assertEqual(profile["identity"]["brand_name"], "Строймаркет Север")
        self.assertEqual(profile["voice"]["formality"], 2)
        self.assertEqual(profile["voice"]["address"], "vy")
        self.assertEqual([a["be"] for a in profile["voice"]["attributes"]], ["factual", "concrete", "local"])
        self.assertEqual(profile["visuals"]["types"]["inline_photo"]["min_per_page"], 2)
        self.assertEqual(profile["visuals"]["types"]["inline_photo"]["caption"], "required")
        # template examples are not carried over as if they were the owner's answers
        self.assertEqual(profile["voice"]["summary"], "")
        self.assertEqual(profile["identity"]["audiences"], [])
        fields = {row["field"] for row in bv.unanswered_fields(profile)}
        self.assertEqual(fields, {"identity.who_we_are", "identity.audiences", "voice.summary"})

    def test_render_init_keeps_emoji_and_real_values(self) -> None:
        cfg = project_cfg()
        cfg["tone"]["description"] = "Дружелюбно 😀 и по делу"
        cfg["target_audiences"] = ["кровельщики"]
        cfg["locale"]["language"] = "en"
        text = bv.render_init(cfg)
        text.encode("utf-8")  # no lone surrogates
        profile = parse_yaml_text(text)
        self.assertEqual(profile["voice"]["summary"], "Дружелюбно 😀 и по делу")
        self.assertEqual(profile["identity"]["audiences"][0]["name"], "кровельщики")
        self.assertEqual(profile["voice"]["address"], "you")

    def test_validate_reports_types_enums_and_references(self) -> None:
        profile = filled_profile()
        profile["voice"]["formality"] = 9
        profile["voice"]["address"] = "sir"
        profile["lexicon"]["preferred"] = ["not", "a", "dict"]
        profile["lexicon"]["forbidden_regex"] = ["("]
        profile["style"]["sentence_max_words"] = -1
        profile["methods"]["default"] = "essay"
        profile["visuals"]["types"]["hero"]["source"] = "painting"
        profile["visuals"]["per_page_type"]["article"] = ["hero", "unicorn"]
        profile["authors"] = [{"role": "без имени"}]
        errors = "\n".join(bv.validate_profile(profile))
        for marker in ("voice.formality", "voice.address", "lexicon.preferred", "forbidden_regex[0]",
                       "style.sentence_max_words", "methods.default", "visuals.types.hero.source",
                       "«unicorn»", "authors[0]"):
            self.assertIn(marker, errors)
        self.assertEqual(bv.validate_profile(["list"]), ["профиль должен быть словарём, получено list"])

    def test_methods_visuals_and_aliases(self) -> None:
        profile = filled_profile()
        self.assertEqual(bv.method_for(profile, "Guide")["page_type"], "article")
        self.assertEqual(bv.method_for(profile, "Сравнение")["structure"][0], "verdict_first")
        profile["methods"]["aliases"] = {"Обзор": "comparison"}
        self.assertEqual(bv.method_for(profile, "Обзор")["page_type"], "comparison")
        self.assertEqual(bv.method_for(profile, None)["page_type"], "article")
        del profile["methods"]["page_types"]["category"]
        self.assertEqual(bv.method_for(profile, "category")["page_type"], "article")  # falls back to default
        self.assertEqual([slot["type"] for slot in bv.visuals_for(profile, "howto")], ["hero", "inline_photo", "diagram"])
        self.assertEqual(bv.visuals_for({}, "article"), [])

    def test_brief_block_and_markdown_in_both_languages(self) -> None:
        profile = filled_profile()
        block = bv.brief_block(profile, "Guide", "seo/brand/voice.yaml")
        self.assertFalse(block["first_person_allowed"])
        ru = "\n".join(bv.render_brief_markdown(block))
        for marker in ("## Голос бренда и метод", "на «вы»", "минеральная вата", "Частный застройщик",
                       "### Изображения по профилю", "`hero`"):
            self.assertIn(marker, ru)
        self.assertNotIn("<", ru.replace("<!--", ""))  # no HTML in briefs (page-outline-quality)
        profile["language"] = "en"
        profile["authors"] = [{"name": "Иван Петров", "role": "прораб", "proof_url": "https://example.com/ivan"}]
        profile["first_person_allowed"] = True
        profile["examples"] = {"good": ["seo/brand/examples/good-1.md"], "bad": []}
        profile["disclaimers"] = ["Цены — на дату публикации."]
        en = "\n".join(bv.render_brief_markdown(bv.brief_block(profile, "Guide"), heading_level=3))
        self.assertIn("### Brand voice and method", en)
        self.assertIn("allowed (real author: Иван Петров)", en)
        self.assertIn("good-1.md", en)
        self.assertIn("Цены — на дату публикации.", en)
        self.assertTrue(bv.has_real_author(profile))
        profile["authors"] = [{"name": "Без пруфа"}]
        self.assertFalse(bv.has_real_author(profile))

    def test_settings_and_loading(self) -> None:
        self.assertEqual(bv.settings({}), {"enabled": True, "enforce": "warn", "require_review": False})
        self.assertEqual(bv.settings({"brand_voice": {"enforce": "loud"}})["enforce"], "warn")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bv-load-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        self.assertEqual(bv.load_profile({}, tmp, strict=False), (None, None))
        path = tmp / "seo" / "brand" / "voice.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(dump_yaml(filled_profile()), encoding="utf-8")
        profile, error = bv.load_profile({}, tmp, strict=False)
        self.assertIsNone(error)
        self.assertEqual(profile["language"], "ru")
        self.assertEqual(bv.load_profile({"brand_voice": {"enabled": False}}, tmp, strict=False), (None, None))
        path.write_text("voice: [oops\n", encoding="utf-8")
        profile, error = bv.load_profile({}, tmp, strict=False)
        self.assertIsNone(profile)
        self.assertIn("voice.yaml", error or "")


class CheckDraftTest(unittest.TestCase):
    def check(self, text: str, profile: dict | None = None, cfg: dict | None = None, page_type: str = "Guide",
              frontmatter: dict | None = None, already: frozenset = frozenset()) -> list[dict]:
        return bv.check_draft(text, profile or filled_profile(), page_type=page_type, frontmatter=frontmatter or {},
                              cfg=cfg or {}, location="d.md", already_checked=already)

    def ids(self, findings: list[dict]) -> set[str]:
        return {f["id"] for f in findings}

    def test_voice_findings(self) -> None:
        text = ('# Минвата\n\nЕсли ты строишь дом, тебе нужна минвата - это база. Назовём её "основа" '
                'и не возьмём дешёвый вариант.\n')
        findings = self.check(text)
        ids = self.ids(findings)
        for expected in ("voice_forbidden_term", "voice_preferred_term", "voice_address_mismatch",
                         "voice_typography_quotes", "voice_typography_dash", "visual_required_missing",
                         "inline_images_below_min"):
            self.assertIn(expected, ids)
        severity = {f["id"]: f["severity"] for f in findings}
        self.assertEqual(severity["voice_forbidden_term"], "error")
        self.assertEqual(severity["voice_address_mismatch"], "warning")
        self.assertTrue(any("строки 3" in f["message"] for f in findings if f["id"] == "voice_address_mismatch"))

    def test_clean_text_with_required_visuals(self) -> None:
        text = ('# Минеральная вата\n\n![Плита в разрезе](/a.webp "hero")\n\n'
                'Вы выбираете плиту по плотности — 35 кг/м³ для стен.\n\n'
                '![Монтаж](/b.webp)\n*Подпись*\n\n![Слои](/c.webp)\n*Подпись*\n')
        self.assertEqual(self.check(text), [])

    def test_structural_markup_is_not_typography(self) -> None:
        text = ('# Заголовок - с дефисом\n\n- пункт списка\n| a - b | c |\n|---|---|\n'
                '[ссылка](/x "title") и `code "x"` <a href="/y">тег</a>\n\n```\nfoo - "bar"\n```\n')
        ids = self.ids(self.check(text, page_type="landing"))
        self.assertNotIn("voice_typography_quotes", ids)
        self.assertNotIn("voice_typography_dash", ids)

    def test_long_sentences_and_paragraphs(self) -> None:
        long_sentence = "Слово " + " ".join(["слово"] * 29) + "."
        text = "# T\n\n" + " ".join([long_sentence] * 4) + " " + " ".join(["Коротко."] * 3) + "\n"
        ids = self.ids(self.check(text, page_type="landing"))
        self.assertIn("voice_long_sentences", ids)
        self.assertIn("voice_long_paragraphs", ids)

    def test_address_variants_and_brand_mentions(self) -> None:
        profile = filled_profile()
        profile["voice"]["address"] = "ty"
        self.assertIn("voice_address_mismatch", self.ids(self.check("# T\n\nВам подойдёт плита.\n", profile, page_type="landing")))
        profile["voice"]["address"] = "impersonal"
        many = "# T\n\n" + "\n".join(["Вы выбираете, вам нужно."] * 4) + "\n"
        self.assertIn("voice_address_mismatch", self.ids(self.check(many, profile, page_type="landing")))
        profile["language"] = "en"
        self.assertIn("voice_address_mismatch",
                      self.ids(self.check("# T\n\n" + "\n".join(["You pick your board."] * 4) + "\n", profile, page_type="landing")))
        profile = filled_profile()
        spam = "# T\n\n" + "Строймаркет Север везёт. " * 6 + "\n"
        self.assertIn("voice_brand_mentions_excess", self.ids(self.check(spam, profile, page_type="landing")))

    def test_comparison_table_and_featured_image(self) -> None:
        ids = self.ids(self.check("# T\n\nТекст.\n", page_type="comparison", frontmatter={"featured_image": "/a.webp"}))
        self.assertIn("visual_required_missing", ids)  # the table
        findings = self.check("# T\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", page_type="comparison",
                              frontmatter={"featured_image": "/a.webp"})
        self.assertNotIn("visual_required_missing", self.ids(findings))

    def test_enforce_error_and_review(self) -> None:
        text = "# T\n\nЕсли ты строишь дом.\n"
        cfg = {"brand_voice": {"enforce": "error", "require_review": True}}
        findings = self.check(text, cfg=cfg, page_type="landing")
        self.assertEqual({f["severity"] for f in findings}, {"error"})
        self.assertIn("voice_review_missing", self.ids(findings))
        findings = self.check("# T\n\nТекст.\n", cfg=cfg, page_type="landing", frontmatter={"voice_review": {"verdict": "needs_work"}})
        self.assertIn("voice_review_needs_work", self.ids(findings))
        findings = self.check("# T\n\nТекст.\n", cfg=cfg, page_type="landing", frontmatter={"voice_review": {"verdict": "pass"}})
        self.assertNotIn("voice_review_missing", self.ids(findings))

    def test_inline_minimum_not_doubled_when_config_checked_it(self) -> None:
        findings = self.check('# T\n\n![h](/a.webp "hero")\n\nТекст.\n', already=frozenset({"inline_images_min"}))
        self.assertNotIn("inline_images_below_min", self.ids(findings))


class BrandVoiceCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bv-cli-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(dump_yaml(project_cfg()), encoding="utf-8")

    def run_cli(self, *args: str, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CLI), *args], cwd=cwd or self.tmp, text=True,
                              capture_output=True, check=False)

    def test_help_without_project(self) -> None:
        empty = pathlib.Path(tempfile.mkdtemp(prefix="bv-empty-"))
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))
        proc = self.run_cli("--help", cwd=empty)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("init", proc.stdout)
        proc = self.run_cli("validate", cwd=empty)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("seo-cycle.yaml не найден", proc.stderr)

    def test_init_validate_show_check_cycle(self) -> None:
        profile_file = self.tmp / "seo" / "brand" / "voice.yaml"
        dry = self.run_cli("init")
        self.assertEqual(dry.returncode, 0)
        self.assertIn("version: 1", dry.stdout)
        self.assertFalse(profile_file.exists())
        self.assertEqual(self.run_cli("validate").returncode, 1)  # no profile yet
        made = self.run_cli("init", "--write")
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertIn("✓ профиль голоса создан", made.stdout)
        self.assertIn("voice.summary", made.stdout)
        again = self.run_cli("init", "--write")
        self.assertEqual(again.returncode, 0)
        self.assertIn("ℹ профиль уже есть", again.stdout)
        report = json.loads(self.run_cli("validate", "--format", "json").stdout)
        self.assertEqual(report["status"], "incomplete")
        shown = json.loads(self.run_cli("show", "--page-type", "howto", "--format", "json").stdout)
        self.assertEqual(shown["method"]["page_type"], "howto")
        self.assertIn("## Голос бренда и метод", self.run_cli("show").stdout)
        draft = self.tmp / "d.md"
        draft.write_text("# T\n\nЕсли ты строишь дом - бери плиту.\n", encoding="utf-8")
        proc = self.run_cli("check", str(draft))
        self.assertEqual(proc.returncode, 0)  # warnings only
        self.assertIn("voice_address_mismatch", proc.stdout)
        profile_file.write_text(profile_file.read_text(encoding="utf-8").replace("forbidden: []", 'forbidden: ["плиту"]'),
                                encoding="utf-8")
        proc = self.run_cli("check", str(draft), "--format", "json")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)["status"], "fail")
        forced = self.run_cli("init", "--write", "--force")
        self.assertEqual(forced.returncode, 0)
        self.assertNotIn('"плиту"', profile_file.read_text(encoding="utf-8"))

    def test_broken_profile_and_disabled(self) -> None:
        profile_file = self.tmp / "seo" / "brand" / "voice.yaml"
        profile_file.parent.mkdir(parents=True)
        profile_file.write_text("voice:\n  address: sir\n", encoding="utf-8")
        proc = self.run_cli("validate")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("voice.address", proc.stdout)
        self.assertEqual(self.run_cli("show").returncode, 1)
        self.assertEqual(self.run_cli("check", str(profile_file)).returncode, 2)
        cfg = project_cfg()
        cfg["brand_voice"]["enabled"] = False
        (self.tmp / "seo-cycle.yaml").write_text(dump_yaml(cfg), encoding="utf-8")
        proc = self.run_cli("validate")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("выключен", proc.stderr)

    def test_extract_prompt(self) -> None:
        texts = self.tmp / "published"
        texts.mkdir()
        (texts / "a.md").write_text("---\ntitle: x\n---\nМы везём кровлю по городу за день.\n", encoding="utf-8")
        (texts / "b.html").write_text("<html><script>x</script><p>Вы выбираете профнастил.</p></html>", encoding="utf-8")
        proc = self.run_cli("extract-prompt", "--from", str(texts))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Мы везём кровлю", proc.stdout)
        self.assertIn("Вы выбираете профнастил", proc.stdout)
        self.assertNotIn("<script>", proc.stdout)
        self.assertIn("```yaml", proc.stdout)
        self.assertEqual(self.run_cli("extract-prompt", "--from", str(self.tmp / "nope")).returncode, 2)


if __name__ == "__main__":
    unittest.main()
