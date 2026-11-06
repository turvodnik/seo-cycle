#!/usr/bin/env python3
"""task-router classification (3.1.0).

Keywords match only at the start of a word: plain substring matching sent
«описание категории» to `ai_visibility` (the keyword «ии» inside
«категории») and let «write» match «rewrite».
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

_spec = importlib.util.spec_from_file_location("task_router_under_test", SCRIPTS / "task-router.py")
assert _spec and _spec.loader
router = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(router)


class KeywordMatchTest(unittest.TestCase):
    def test_keyword_matches_only_at_word_start(self) -> None:
        self.assertTrue(router.keyword_matches("стать", "написать статью"))
        self.assertTrue(router.keyword_matches("перепис", "переписать текст"))
        self.assertFalse(router.keyword_matches("ии", "описание категории"))
        self.assertFalse(router.keyword_matches("write", "rewrite the article"))
        self.assertFalse(router.keyword_matches("текст", "контекст проекта"))
        self.assertTrue(router.keyword_matches("content plan", "make a content plan"))

    def test_category_description_is_not_ai_visibility(self) -> None:
        self.assertNotEqual(router.classify_task("описание категории", None), "ai_visibility")

    def test_existing_routes_are_stable(self) -> None:
        cases = {
            "аудит индексации, robots и Bricks preview": "technical_audit",
            "семантическое ядро для минваты": "keyword_research",
            "rewrite the article about mineral wool": "content_refresh",
            "контент-план статей на квартал": "content_plan",
            "настрой ai visibility в chatgpt": "ai_visibility",
        }
        for task, expected in cases.items():
            with self.subTest(task=task):
                self.assertEqual(router.classify_task(task, None), expected)

    def test_explicit_type_wins(self) -> None:
        self.assertEqual(router.classify_task("что угодно", "publishing"), "publishing")


if __name__ == "__main__":
    unittest.main()
