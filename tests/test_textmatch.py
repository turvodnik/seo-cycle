#!/usr/bin/env python3
"""Tests for seo_cycle_core.textmatch — light stemming and query matching."""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_cycle_core.textmatch import (  # noqa: E402
    build_query_index,
    match_position,
    normalize_phrase,
    phrase_key,
    stem_token,
)


class StemTest(unittest.TestCase):
    def test_nominal_forms_collapse(self) -> None:
        for forms in (("вагонка", "вагонку", "вагонки"),
                      ("минеральная", "минеральной"),
                      ("плита", "плиты"),
                      ("пароизоляция", "пароизоляции"),
                      ("фанера", "фанеру", "фанеры")):
            stems = {stem_token(form) for form in forms}
            self.assertEqual(len(stems), 1, forms)

    def test_close_terms_stay_apart(self) -> None:
        self.assertNotEqual(stem_token("плита"), stem_token("плитка"))

    def test_soft_sign_trim_keeps_verbs_consistent(self) -> None:
        # «ь» срезается ради «утеплитель/утеплителя»; инфинитив от этого
        # стабилен с обеих сторон матчинга
        self.assertEqual(stem_token("купить"), stem_token("купить"))
        self.assertEqual(stem_token("утеплитель"), stem_token("утеплителя"))

    def test_short_and_latin_untouched(self) -> None:
        self.assertEqual(stem_token("осп"), "осп")
        self.assertEqual(stem_token("xps"), "xps")
        self.assertEqual(stem_token("250"), "250")

    def test_normalize_collapses_spaces_and_yo(self) -> None:
        self.assertEqual(normalize_phrase("  Клеёный   Брус "), "клееный брус")

    def test_phrase_key_ignores_order_and_stops(self) -> None:
        self.assertEqual(phrase_key("купить вагонку в москве"),
                         phrase_key("вагонка купить москва"))


class MatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.index = build_query_index({
            "купить вагонку": 3.0,
            "осп плита 9 мм цена": 5.0,
            "минеральная вата для стен": 7.0,
            "осп": 12.0,
        })

    def test_exact_wins(self) -> None:
        self.assertEqual(match_position("купить вагонку", self.index), (3.0, "exact"))

    def test_stem_set_matches_order_and_inflection(self) -> None:
        position, kind = match_position("вагонку купить", self.index)
        self.assertEqual((position, kind), (3.0, "stem"))
        position, kind = match_position("вата минеральная для стены", self.index)
        self.assertEqual((position, kind), (7.0, "stem"))

    def test_subset_needs_two_stems(self) -> None:
        position, kind = match_position("осп плита 9 мм", self.index)
        self.assertEqual((position, kind), (5.0, "subset"))
        # одиночный стем не матчится подмножеством — только exact/stem
        self.assertEqual(match_position("плита", self.index), (None, ""))

    def test_subset_takes_family_median_not_best_tail(self) -> None:
        index = build_query_index({
            "осб плита на пол 9мм": 3.0,
            "осб плита купить москва": 9.0,
            "осб плита размеры и цены": 15.0,
        })
        position, kind = match_position("осб плита", index)
        self.assertEqual((position, kind), (9.0, "subset"))

    def test_no_match(self) -> None:
        self.assertEqual(match_position("шумоизоляция потолка", self.index), (None, ""))


if __name__ == "__main__":
    unittest.main()
