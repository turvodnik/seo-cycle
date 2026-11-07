#!/usr/bin/env python3
"""In-process tests of the 3.1.0 draft-gate core (counted by the coverage job).

seo_cycle_core.stop_words / frontmatter / page_types / draft_checks and the
non-exiting YAML helpers of seo_cycle_core.config.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_cycle_core import draft_checks as dc  # noqa: E402
from seo_cycle_core.config import find_project_config, load_yaml_safe, parse_yaml_text_safe  # noqa: E402
from seo_cycle_core.frontmatter import split_frontmatter  # noqa: E402
from seo_cycle_core.page_types import is_article_like, normalize_page_type, word_count_bucket  # noqa: E402
from seo_cycle_core.stop_words import extra_rules, find_violations, patterns_for, resolve_lang, strip_ignored  # noqa: E402

CHECK = ROOT / "scripts" / "check-stop-words.py"


class StopWordsCoreTest(unittest.TestCase):
    def test_line_numbers_survive_frontmatter_and_code(self) -> None:
        text = "---\ntitle: x\nitems:\n  - a\n---\n\n```\nлучший в коде\n```\nЭто лучший текст.\n"
        self.assertEqual(find_violations(text, patterns_for("ru"), []),
                         [(10, "эпитет", "лучший", "Это лучший текст.")])

    def test_horizontal_rules_do_not_swallow_text(self) -> None:
        text = "Intro\n\n---\n\nЭто лучший абзац\n\n---\n\nEnd\n"
        self.assertEqual([hit[0] for hit in find_violations(text, patterns_for("ru"), [])], [5])

    def test_apostrophes_are_not_quotes(self) -> None:
        text = "It's fine.\nЭто лучший.\nDon't.\n"
        self.assertEqual([hit[0] for hit in find_violations(text, patterns_for("ru"), [])], [2])

    def test_quotes_and_inline_code_are_ignored(self) -> None:
        text = "Цитата «лучший», \"лучший\", 'лучший' и `лучший`.\n"
        self.assertEqual(find_violations(text, patterns_for("ru"), []), [])

    def test_strip_keeps_length_and_newlines(self) -> None:
        text = "---\na: 1\n---\nтекст `код` «цитата»\n"
        clean = strip_ignored(text)
        self.assertEqual(len(clean), len(text))
        self.assertEqual(clean.count("\n"), text.count("\n"))

    def test_builtin_and_extra_word_hit_once(self) -> None:
        hits = find_violations("Самый лучший товар.\n", patterns_for("ru"), ["лучший", "самый"])
        self.assertEqual(sorted(hit[2].lower() for hit in hits), ["лучший", "самый"])

    def test_phrase_extra_words_and_english(self) -> None:
        hits = find_violations("We are the best, a world-class team.\n", patterns_for("en"), ["dream team"])
        self.assertEqual({hit[2].lower() for hit in hits}, {"the best", "world-class"})
        hits = find_violations("Наша dream team.\n", [], ["dream team"])
        self.assertEqual(hits[0][1], "extra")

    def test_broken_regex_is_skipped(self) -> None:
        self.assertEqual(find_violations("лучший\n", [("custom-regex", "(")], []), [])

    def test_extra_rules_and_lang_are_shape_tolerant(self) -> None:
        self.assertEqual(extra_rules({"tone": {"stop_words_extra": "лучший", "stop_words_regex_extra": [r"\bтоп\b", {"x": 1}]}}),
                         (["лучший"], [r"\bтоп\b"]))
        self.assertEqual(extra_rules({"tone": None}), ([], []))
        self.assertEqual(extra_rules([]), ([], []))
        self.assertEqual(resolve_lang("auto", {"locale": {"language": "EN"}}), "en")
        self.assertEqual(resolve_lang("auto", {"locale": None}), "ru")
        self.assertEqual(resolve_lang("both", {}), "both")
        self.assertEqual(patterns_for("de"), [])


class CheckStopWordsCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="stop-words-cli-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CHECK), *args], cwd=self.tmp, text=True,
                              capture_output=True, check=False)

    def test_exit_codes(self) -> None:
        clean = self.tmp / "clean.md"
        clean.write_text("Плита 50 мм.\n", encoding="utf-8")
        dirty = self.tmp / "dirty.md"
        dirty.write_text("---\na: 1\n---\nЛучший выбор.\n", encoding="utf-8")
        self.assertEqual(self.run_cli(str(clean)).returncode, 0)
        proc = self.run_cli(str(dirty))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("L4 [эпитет] «Лучший» → Лучший выбор.", proc.stdout)
        missing = self.run_cli(str(self.tmp / "nope.md"))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("не существует", missing.stderr)

    def test_config_extra_words_and_broken_config(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text("tone:\n  stop_words_extra: [нереальный]\n", encoding="utf-8")
        draft = self.tmp / "d.md"
        draft.write_text("Нереальный эффект.\n", encoding="utf-8")
        self.assertEqual(self.run_cli(str(draft)).returncode, 1)
        (self.tmp / "seo-cycle.yaml").write_text("tone: [oops\n", encoding="utf-8")
        proc = self.run_cli(str(draft))
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)


class FrontmatterCoreTest(unittest.TestCase):
    def test_split_and_dates_become_strings(self) -> None:
        front = split_frontmatter("---\nchecked: 2026-05-28\nlist: [1, 2]\n---\n# Body\n")
        self.assertTrue(front.present)
        self.assertEqual(front.data, {"checked": "2026-05-28", "list": [1, 2]})
        self.assertEqual(front.body, "# Body\n")
        self.assertEqual(front.body_start_line, 5)

    def test_no_frontmatter_and_unclosed_rule(self) -> None:
        self.assertFalse(split_frontmatter("# Title\n").present)
        front = split_frontmatter("---\nне закрыто\n")
        self.assertFalse(front.present)
        self.assertEqual(front.body, "---\nне закрыто\n")

    def test_broken_and_non_dict(self) -> None:
        broken = split_frontmatter("---\na: [oops\n---\nbody\n")
        self.assertTrue(broken.error and broken.error.startswith("frontmatter:"))
        self.assertEqual(broken.body, "body\n")
        listy = split_frontmatter("---\n- a\n---\nbody\n")
        self.assertIn("словарь", listy.error or "")
        empty = split_frontmatter("---\n---\nbody\n")
        self.assertEqual((empty.data, empty.error), ({}, None))


class PageTypesTest(unittest.TestCase):
    def test_normalize(self) -> None:
        cases = {
            "Guide": "article", "": "article", None: "article", "Category": "category",
            "product category": "category", "Карточка товара": "product", "Сравнение": "comparison",
            "X vs Y": "comparison", "Landing": "landing", "Услуги": "landing", "How-to": "howto",
            "Tool/App": "tool", "app": "tool", "Approach guide": "article", "howto": "howto",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_page_type(raw), expected)

    def test_buckets(self) -> None:
        self.assertEqual(word_count_bucket("Category"), "category")
        self.assertEqual(word_count_bucket("product"), "category")
        self.assertEqual(word_count_bucket("Tool"), "landing")
        self.assertEqual(word_count_bucket("Guide"), "blog_post")
        self.assertTrue(is_article_like("Сравнение"))
        self.assertFalse(is_article_like("category"))


class DraftChecksHelpersTest(unittest.TestCase):
    def test_images_and_captions(self) -> None:
        text = ("![](a.webp)\n*Подпись*\n\n![Плита](b.webp \"hero\")\n\n"
                "<img src=\"c.webp\" alt=\"Слои стены\">\n<figcaption>Пирог</figcaption>\n"
                "<img src=\"d.webp\" class=\"decorative\">\n```\n![](code.webp)\n```\n")
        images = dc.find_images(text)
        self.assertEqual([(img.line, img.kind) for img in images], [(1, ""), (4, "hero"), (6, ""), (8, "decorative")])
        lines = text.splitlines()
        self.assertTrue(dc._caption_follows(lines, 1, False))
        self.assertTrue(dc._caption_follows(lines, 6, True))
        self.assertFalse(dc._caption_follows(["![x](y.webp)", "", "обычный текст"], 1, False))
        self.assertTrue(dc._caption_follows(["![x](y.webp) *Подпись рядом*"], 1, False))

    def test_generic_alt(self) -> None:
        self.assertTrue(dc._is_generic_alt("Фото", "x.webp"))
        self.assertTrue(dc._is_generic_alt("IMG_1234", "IMG_1234.jpg"))
        self.assertTrue(dc._is_generic_alt("photo", "/a/photo.webp"))
        self.assertFalse(dc._is_generic_alt("Монтаж плиты в каркас", "x.webp"))

    def test_counts(self) -> None:
        body = "Слово раз два.\n```\nкод не считается\n```\n[ссылка](/a/) https://example.com/x `код`\n"
        self.assertEqual(dc.count_words(body), 4)
        links = "[a](/catalog/) [b](/catalog/#x) [c](https://www.shop.test/blog/) [d](https://other.test/) ![i](/img.webp) [e](//cdn.test/x)"
        self.assertEqual(dc.count_internal_links(links, "shop.test"), 2)
        self.assertEqual(dc.count_local_signals("Склад в Москве, доставка по Московской области и Москве.",
                                                ["Москва", "Московская область", "Уфа"]), 3)
        self.assertEqual(dc.count_local_signals("Уфе и Уфа", ["Уфа"]), 1)  # short stems: exact form

    def test_domain(self) -> None:
        self.assertEqual(dc._domain({"project": {"domain": "https://www.Shop.test/"}}), "shop.test")
        self.assertEqual(dc._domain({"project": {"domain": 42}}), "")


class RunConfigChecksTest(unittest.TestCase):
    """run_config_checks in-process (the gate CLI tests run it as a subprocess)."""

    def cfg(self) -> dict:
        import copy

        from seo_cycle_core.config import load_yaml

        cfg = copy.deepcopy(load_yaml(ROOT / "config" / "project.template.yaml"))
        cfg["project"]["domain"] = "shop.test"
        cfg["content_rules"]["local_signals"]["examples"] = ["Казань"]
        return cfg

    def run_checks(self, text: str, cfg: dict, page_type: str = "article") -> dc.CheckResult:
        return dc.run_config_checks(text, split_frontmatter(text), cfg, page_type, "d.md")

    def test_bad_draft(self) -> None:
        text = ("---\nfeatured_image: /a.webp\nfact_check_log:\n  - claim: x\n    verdict: спорно\n---\n"
                "# Т\n\nЛучший выбор, лучший сервис.\n\n![](/b.webp)\n\n![фото](/c.webp)\n")
        result = self.run_checks(text, self.cfg())
        ids = [f["id"] for f in result.findings]
        self.assertEqual(ids.count("stop_words_found"), 1)  # one finding per distinct word
        self.assertIn("(строки 9)", next(f for f in result.findings if f["id"] == "stop_words_found")["message"])
        for expected in ("fact_check_log_incomplete", "fact_check_claim_disputed", "image_missing_alt",
                         "image_generic_alt", "image_missing_caption", "word_count_below_min",
                         "internal_links_below_min", "local_signals_below_min"):
            self.assertIn(expected, ids)
        self.assertEqual(sum(1 for i in ids if i == "image_missing_alt"), 2)  # body image + featured_image
        self.assertIn("local_signals", result.checks_run)

    def test_page_type_scopes_article_only_rules(self) -> None:
        result = self.run_checks("# Т\n\nТекст.\n", self.cfg(), page_type="category")
        self.assertNotIn("inline_images_min", result.checks_run)
        self.assertNotIn("internal_links_min", result.checks_run)
        words = next(f for f in result.findings if f["id"] == "word_count_below_min")
        self.assertIn("category", words["message"])

    def test_bad_shapes_do_not_crash(self) -> None:
        cfg = {"quality_gates": {"stop_words_check": "yes", "word_count_min": {"enabled": True, "blog_post": "много"}},
               "images": None, "content_rules": {"local_signals": {"min_per_page": 2, "examples": "Москва"}}}
        result = self.run_checks("# Т\n\nлучший\n", cfg)
        self.assertEqual(result.findings, [])
        self.assertEqual(self.run_checks("# Т\n", {}).checks_run, [])

    def test_fail_on_match_false_and_stop_word_cap(self) -> None:
        cfg = self.cfg()
        cfg["quality_gates"]["stop_words_check"]["fail_on_match"] = False
        cfg["tone"]["stop_words_extra"] = [f"слово{i}" for i in range(60)]
        text = "# Т\n\n" + " ".join(f"слово{i}" for i in range(60)) + "\n"
        stop = [f for f in self.run_checks(text, cfg).findings if f["id"] == "stop_words_found"]
        self.assertEqual(len(stop), dc.MAX_STOP_WORD_FINDINGS)
        self.assertEqual({f["severity"] for f in stop}, {"warning"})


class SafeYamlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="safe-yaml-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_parse_text_safe(self) -> None:
        self.assertEqual(parse_yaml_text_safe("a: 1\n"), ({"a": 1}, None))
        data, error = parse_yaml_text_safe("a: [1\n")
        self.assertIsNone(data)
        self.assertIn("строка", error or "")

    def test_load_yaml_safe(self) -> None:
        path = self.tmp / "x.yaml"
        self.assertEqual(load_yaml_safe(path), (None, None))
        path.write_text("", encoding="utf-8")
        self.assertEqual(load_yaml_safe(path), ({}, None))
        path.write_text("a: 1\n", encoding="utf-8")
        self.assertEqual(load_yaml_safe(path), ({"a": 1}, None))
        path.write_text("- a\n", encoding="utf-8")
        self.assertIn("словарём", load_yaml_safe(path)[1] or "")
        path.write_bytes("a: \xff".encode("latin-1"))
        self.assertIn("UTF-8", load_yaml_safe(path)[1] or "")
        path.write_text("a: [\n", encoding="utf-8")
        self.assertIsNone(load_yaml_safe(path)[0])

    def test_find_project_config_walks_up_all_search_paths(self) -> None:
        project = self.tmp / "project"
        deep = project / "seo" / "research-package" / "drafts"
        deep.mkdir(parents=True)
        self.assertIsNone(find_project_config(deep))
        (project / ".claude").mkdir()
        cfg = project / ".claude" / "seo-cycle.yaml"
        cfg.write_text("project:\n  name: x\n", encoding="utf-8")
        self.assertEqual(find_project_config(deep), cfg.resolve())
        draft = deep / "d.md"
        draft.write_text("x", encoding="utf-8")
        self.assertEqual(find_project_config(draft), cfg.resolve())
        nearer = project / "seo" / "seo-cycle.yaml"
        nearer.write_text("project:\n  name: y\n", encoding="utf-8")
        # the nearest level wins: <project>/seo/seo-cycle.yaml is found from
        # <project>/seo/research-package before <project>/.claude/
        self.assertEqual(find_project_config(deep).name, "seo-cycle.yaml")

    def test_project_root_for_nested_configs(self) -> None:
        from seo_cycle_core.config import project_root_for

        project = self.tmp / "shop"
        (project / ".claude").mkdir(parents=True)
        self.assertEqual(project_root_for(project / ".claude" / "seo-cycle.yaml"), project)
        (project / "seo").mkdir()
        self.assertEqual(project_root_for(project / "seo" / "seo-cycle.yaml"), project)
        self.assertEqual(project_root_for(project / "seo-cycle.yaml"), project)
        self.assertEqual(project_root_for(project / ".seo-cycle.yaml"), project)
        # a project folder that is itself named «seo» and already has its seo/ tree
        named_seo = self.tmp / "seo"
        (named_seo / "seo").mkdir(parents=True)
        self.assertEqual(project_root_for(named_seo / "seo-cycle.yaml"), named_seo)


if __name__ == "__main__":
    unittest.main()
