#!/usr/bin/env python3
"""Phase 10 triggers: DSL-оценка, дефолтные правила и project-override.

Мотивация из боевого прогона (Эмвуди, 2026-07-24): дефолтные пороги
рассчитаны на крупные сайты, и на срезе с десятками показов на запрос
срабатывало одно правило из семнадцати — движок молчал, хотя сотни
запросов стояли на дожимаемых позициях.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
DEFAULT_TRIGGERS = ROOT / "config" / "triggers.yaml"

spec = importlib.util.spec_from_file_location("triggers_eval", SCRIPTS / "triggers-eval.py")
te = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(te)

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def query(q: str, position: float, impressions: int, clicks: int = 0) -> dict:
    ctr = (clicks / impressions) if impressions else 0.0
    return {"query": q, "position": position, "impressions": impressions,
            "clicks": clicks, "ctr": ctr}


class ConditionDslTest(unittest.TestCase):
    def test_range_and_comparison_operators(self) -> None:
        item = query("затирка швов", position=4.3, impressions=268, clicks=13)
        self.assertTrue(te.eval_condition(item, "position >= 4 AND position <= 10"))
        self.assertTrue(te.eval_condition(item, "impressions > 20"))
        self.assertFalse(te.eval_condition(item, "position < 4"))
        self.assertFalse(te.eval_condition(item, "position >= 4 AND impressions > 1000"))

    def test_ctr_and_equality(self) -> None:
        silent = query("затирка", position=9.6, impressions=48, clicks=0)
        self.assertTrue(te.eval_condition(silent, "clicks == 0"))
        self.assertTrue(te.eval_condition(silent, "ctr < 0.02 AND impressions > 10"))
        clicked = query("расход клея", position=4.9, impressions=120, clicks=6)
        self.assertFalse(te.eval_condition(clicked, "clicks == 0"))


class EvaluateTest(unittest.TestCase):
    SNAPSHOT = {
        "snapshot_date": "2026-07-17",
        "queries": [
            query("как затирать швы на плитке", 4.3, 268, 13),   # дожим до топ-3
            query("затирка швов на плитке своими руками", 4.6, 103, 0),  # сниппет
            query("затирка швов плитки", 11.0, 56, 0),           # striking distance
            query("хвост без показов", 8.0, 2, 0),               # ниже любого порога
        ],
    }

    def test_matches_are_capped_but_total_is_honest(self) -> None:
        rule = {"id": "push_to_top3", "scope": "queries",
                "when": "position >= 4 AND position <= 10 AND impressions > 20"}
        results = te.evaluate(self.SNAPSHOT, [rule], top=1)
        self.assertEqual(results["push_to_top3"]["total"], 2)
        self.assertEqual(len(results["push_to_top3"]["matches"]), 1)

    def test_rule_without_matches_is_absent(self) -> None:
        rule = {"id": "nothing", "scope": "queries", "when": "impressions > 100000"}
        self.assertEqual(te.evaluate(self.SNAPSHOT, [rule]), {})

    def test_low_volume_site_is_invisible_at_default_thresholds(self) -> None:
        # регрессия боевого случая: пороги крупного сайта => движок молчит
        loud = {"id": "striking_distance", "scope": "queries",
                "when": "position >= 11 AND position <= 20 AND impressions > 50"}
        quiet = {"id": "striking_distance", "scope": "queries",
                 "when": "position >= 11 AND position <= 20 AND impressions > 5"}
        small_site = {"queries": [query("затирка швов плитки", 12.0, 26, 0)]}
        self.assertEqual(te.evaluate(small_site, [loud]), {})
        self.assertEqual(te.evaluate(small_site, [quiet])["striking_distance"]["total"], 1)


class PotentialRankingTest(unittest.TestCase):
    """v2: сортировка по потенциалу до обрезки, дедуп между приоритетами, derived-поля."""

    def test_matches_sorted_by_potential_before_cap(self) -> None:
        # раньше [:top] резал в порядке снапшота — ценная запись могла не попасть в топ
        small = query("мелкий", 5.0, impressions=30, clicks=0)      # potential = 30*0.05
        big = query("крупный", 5.0, impressions=800, clicks=0)      # potential = 800*0.05
        rule = {"id": "push", "scope": "queries", "priority": "P0",
                "when": "position >= 4 AND position <= 10 AND impressions > 20"}
        results = te.evaluate({"queries": [small, big]}, [rule], top=1)
        self.assertEqual(results["push"]["matches"][0]["query"], "крупный")
        self.assertEqual(results["push"]["total"], 2)

    def test_lower_priority_rule_does_not_repeat_claimed_items(self) -> None:
        item = query("дубль", 6.0, impressions=200, clicks=0)
        p0 = {"id": "p0_rule", "scope": "queries", "priority": "P0",
              "when": "position >= 4 AND position <= 10 AND impressions > 20"}
        p1 = {"id": "p1_rule", "scope": "queries", "priority": "P1",
              "when": "ctr < 0.02 AND impressions > 100"}
        results = te.evaluate({"queries": [item]}, [p1, p0], top=20)
        self.assertIn("p0_rule", results)
        self.assertNotIn("p1_rule", results)  # полностью перекрыто правилом выше

    def test_derived_fields_and_cannibalization(self) -> None:
        q1 = dict(query("затирка для плитки", 3.0, 400, 4), url="https://s.ru/a")
        q2 = dict(query("затирка для плитки", 7.0, 90, 0), url="https://s.ru/b")
        snapshot = {"queries": [q1, q2]}
        rule = {"id": "cannibalization", "scope": "queries", "priority": "P1",
                "when": "urls_for_query >= 2 AND impressions > 30"}
        results = te.evaluate(snapshot, [rule])
        self.assertEqual(results["cannibalization"]["total"], 2)
        self.assertEqual(q1["urls_for_query"], 2)
        self.assertAlmostEqual(q1["expected_ctr"], 0.10)
        self.assertGreater(q1["potential"], 0)

    def test_top4_zero_ctr_now_fires_default_rule(self) -> None:
        # слепая зона v1: позиция 1-4 с CTR 0% не попадала ни под одно правило
        if yaml is None:
            self.skipTest("PyYAML is required")
        rules = yaml.safe_load(DEFAULT_TRIGGERS.read_text(encoding="utf-8"))["triggers"]
        snapshot = {"queries": [query("сильная позиция без кликов", 2.0, 300, 0)]}
        results = te.evaluate(snapshot, rules)
        self.assertIn("low_ctr_top4", results)
        self.assertEqual(results["low_ctr_top4"]["rule"]["priority"], "P0")


@unittest.skipUnless(yaml, "PyYAML is required")
class DefaultRulesTest(unittest.TestCase):
    def test_push_to_top3_ships_by_default(self) -> None:
        rules = yaml.safe_load(DEFAULT_TRIGGERS.read_text(encoding="utf-8"))["triggers"]
        by_id = {r["id"]: r for r in rules}
        self.assertIn("push_to_top3", by_id)
        self.assertEqual(by_id["push_to_top3"]["priority"], "P0")
        # правило обязано покрывать «в топ-10, но не в топ-3»
        item = query("дожимаемый запрос", 5.0, 100, 1)
        self.assertTrue(te.eval_condition(item, by_id["push_to_top3"]["when"]))

    def test_every_rule_has_id_scope_action_and_parsable_condition(self) -> None:
        rules = yaml.safe_load(DEFAULT_TRIGGERS.read_text(encoding="utf-8"))["triggers"]
        self.assertGreater(len(rules), 10)
        probe = query("проба", 7.0, 60, 1)
        for rule in rules:
            for field in ("id", "when", "scope", "action", "priority"):
                self.assertIn(field, rule, f"{rule.get('id')} без поля {field}")
            if rule["scope"] == "queries":
                te.eval_condition(probe, rule["when"])  # не должно бросать


@unittest.skipUnless(yaml, "PyYAML is required")
class ProjectOverrideTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-triggers-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_override_replaces_threshold_by_id_and_adds_new_rules(self) -> None:
        snapshot = self.tmp / "snap.json"
        snapshot.write_text(json.dumps({
            "snapshot_date": "2026-07-17",
            "period": {"start": "2026-07-03", "end": "2026-07-17"},
            "sources": [{"source": "webmaster", "engine": "yandex"}],
            "queries": [query("затирка швов плитки", 12.0, 26, 0),
                        query("как затирать швы", 4.3, 30, 2),
                        # ловится ТОЛЬКО проектным правилом (v2-дедуп не даёт
                        # правилам ниже повторять записи, показанные выше)
                        query("бренд-запрос", 2.0, 15, 0)],
        }), encoding="utf-8")
        override = self.tmp / "seo-triggers.yaml"
        override.write_text(yaml.safe_dump({"triggers": [
            {"id": "striking_distance", "scope": "queries",
             "when": "position >= 11 AND position <= 20 AND impressions > 5",
             "action": "calibrated", "priority": "P0", "delegate": "content_strategist"},
            {"id": "project_only_rule", "scope": "queries",
             "when": "position <= 5 AND impressions > 10",
             "action": "project rule", "priority": "P1", "delegate": "content_strategist"},
        ]}, allow_unicode=True), encoding="utf-8")
        cfg = self.tmp / "seo-cycle.yaml"
        cfg.write_text(yaml.safe_dump({
            "project": {"name": "override-test"},
            "monitoring": {"triggers_file": str(override)},
        }, allow_unicode=True), encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "triggers-eval.py"), str(snapshot),
             str(DEFAULT_TRIGGERS), "--project-yaml", str(cfg)],
            cwd=self.tmp, text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # калиброванный порог сработал там, где дефолтный молчал
        self.assertIn("striking_distance", proc.stdout)
        self.assertIn("calibrated", proc.stdout)
        # правило, которого нет в дефолте, добавилось
        self.assertIn("project_only_rule", proc.stdout)


if __name__ == "__main__":
    unittest.main()
