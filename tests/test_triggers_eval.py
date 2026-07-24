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
                        query("как затирать швы", 4.3, 30, 2)],
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
