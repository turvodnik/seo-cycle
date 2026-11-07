#!/usr/bin/env python3
"""seo_cycle_core.placeholders (3.1.0): template example values left in a project config."""

from __future__ import annotations

import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_cycle_core.config import load_yaml  # noqa: E402
from seo_cycle_core.placeholders import (  # noqa: E402
    PLACEHOLDER_FIELDS,
    checked_paths,
    find_placeholders,
    is_placeholder,
    template_value,
)

TEMPLATE = load_yaml(ROOT / "config" / "project.template.yaml")


class PlaceholderDetectionTest(unittest.TestCase):
    def test_raw_template_flags_every_curated_path_it_fills(self) -> None:
        found = {hit["path"] for hit in find_placeholders(TEMPLATE)}
        self.assertIn("project.name", found)
        self.assertIn("project.domain", found)
        self.assertIn("business_profile.telephone", found)
        self.assertIn("business_profile.address.street", found)
        self.assertIn("industry.primary_categories", found)
        self.assertIn("content_rules.local_signals.examples", found)
        self.assertIn("tone.description", found)
        for hit in find_placeholders(TEMPLATE):
            self.assertTrue(hit["question"])

    def test_real_values_are_not_flagged(self) -> None:
        cfg = copy.deepcopy(TEMPLATE)
        cfg["project"]["name"] = "Строймаркет Север"
        cfg["project"]["domain"] = "stroy-sever.ru"
        cfg["business_profile"]["telephone"] = "+7 812 555-01-02"
        cfg["industry"]["primary_categories"] = ["Кровля", "Фасад"]
        cfg["content_rules"]["local_signals"]["examples"] = ["Санкт-Петербург", "Ленобласть"]
        found = {hit["path"] for hit in find_placeholders(cfg)}
        for path in ("project.name", "project.domain", "business_profile.telephone",
                     "industry.primary_categories", "content_rules.local_signals.examples"):
            self.assertNotIn(path, found)

    def test_list_overlap_counts_as_placeholder(self) -> None:
        sample = template_value("content_rules.local_signals.examples")
        self.assertTrue(is_placeholder("content_rules.local_signals.examples", ["Казань", sample[-1]]))
        self.assertFalse(is_placeholder("content_rules.local_signals.examples", ["Казань"]))

    def test_whitespace_and_case_do_not_hide_a_placeholder(self) -> None:
        description = template_value("tone.description")
        self.assertTrue(is_placeholder("tone.description", "  " + description.upper().replace(" ", "   ")))

    def test_wizard_defaults_and_example_domains(self) -> None:
        self.assertTrue(is_placeholder("project.name", "MyProject"))
        self.assertTrue(is_placeholder("project.domain", "example.com"))
        self.assertTrue(is_placeholder("business_profile.url", "https://www.example.org/"))
        self.assertFalse(is_placeholder("project.domain", "stroy-sever.ru"))

    def test_empty_and_missing_values_are_not_placeholders(self) -> None:
        self.assertFalse(is_placeholder("project.name", ""))
        self.assertFalse(is_placeholder("project.name", None))
        self.assertFalse(is_placeholder("business_profile.knows_about", []))
        self.assertEqual(find_placeholders({}), [])
        self.assertEqual(find_placeholders("not a dict"), [])  # type: ignore[arg-type]

    def test_non_scalar_mismatch_is_not_a_placeholder(self) -> None:
        self.assertFalse(is_placeholder("project.name", {"nested": "Example Shop"}))
        self.assertFalse(is_placeholder("industry.primary_categories", "Минеральная вата, Кровля"))

    def test_checked_paths_lists_only_present_fields(self) -> None:
        self.assertEqual(checked_paths({}), [])
        self.assertEqual(checked_paths({"project": {"name": "X"}}), ["project.name"])
        self.assertLessEqual(len(checked_paths(TEMPLATE)), len(PLACEHOLDER_FIELDS))


if __name__ == "__main__":
    unittest.main()
