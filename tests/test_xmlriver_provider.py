#!/usr/bin/env python3
"""Tests for XMLRiver guarded SERP/Wordstat source packs."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
XMLRIVER_SOURCE_PACK = ROOT / "scripts" / "xmlriver-source-pack.py"


class XMLRiverProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-xmlriver-provider-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(
            """
project:
  name: XMLRiver Test
  domain: xmlriver.test
locale:
  country: RU
  language: ru
  yandex_lr: 213
  google_gl: ru
  google_hl: ru
engines:
  - name: yandex
  - name: google
project_type: ecommerce
""",
            encoding="utf-8",
        )

    def run_source_pack(self, *args: str, env: dict[str, str] | None = None) -> dict:
        proc = subprocess.run(
            [sys.executable, str(XMLRIVER_SOURCE_PACK), str(self.cfg_path), *args, "--format", "json"],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
        return json.loads(proc.stdout)

    def test_serp_xml_ingests_organic_features_and_vector_record(self) -> None:
        serp_xml = self.tmp / "xmlriver-yandex.xml"
        serp_xml.write_text(
            """<?xml version="1.0" encoding="utf-8"?>
<yandexsearch>
  <response>
    <results>
      <grouping>
        <group>
          <doc>
            <url>https://example.com/osb-9mm</url>
            <title>ОСП плита 9 мм купить</title>
            <passages><passage>Влагостойкая OSB плита для кровли и пола.</passage></passages>
          </doc>
        </group>
        <group>
          <doc>
            <url>https://example.org/osb-guide</url>
            <title>Как выбрать ОСП</title>
            <extendedpassage>Толщина, класс, применение и цены.</extendedpassage>
          </doc>
        </group>
      </grouping>
    </results>
    <addresults>
      <zeroposition>
        <title>Что такое плита ОСП</title>
        <url>https://example.net/answer</url>
      </zeroposition>
      <relatedQuestions>
        <item><text>Чем отличается OSB 3 от OSB 4?</text></item>
      </relatedQuestions>
      <knowledge_graph>
        <title>OSB</title>
      </knowledge_graph>
    </addresults>
  </response>
</yandexsearch>
""",
            encoding="utf-8",
        )

        report = self.run_source_pack(
            "--query",
            "Плита ОСП",
            "--engine",
            "yandex",
            "--input-file",
            str(serp_xml),
            "--input-format",
            "xml",
            "--write",
        )

        self.assertEqual(report["provider"], "xmlriver")
        self.assertEqual(report["status"], "ready")
        self.assertFalse(report["paid_api_used"])
        self.assertEqual(report["distillate"]["engine"], "yandex")
        self.assertEqual(len(report["distillate"]["organic_results"]), 2)
        self.assertIn("related_questions", report["distillate"]["serp_features"])
        self.assertIn("zero_position", report["distillate"]["serp_features"])
        self.assertIn("knowledge_graph", report["distillate"]["serp_features"])
        self.assertTrue(pathlib.Path(report["paths"]["raw"]).exists())
        self.assertTrue((self.tmp / "seo" / "research" / "vector" / "source_pack.jsonl").exists())

    def test_wordstat_json_ingests_popular_associations_and_history(self) -> None:
        wordstat_json = self.tmp / "xmlriver-wordstat.json"
        wordstat_json.write_text(
            json.dumps(
                {
                    "query": "плита осп",
                    "associations": [
                        {"text": "осп плита купить", "value": 9100},
                        {"text": "осп 9 мм", "value": 4200},
                    ],
                    "popular": [
                        {"text": "osb плита цена", "value": 7600},
                    ],
                    "totalValue": 18400,
                    "timeSeries": [{"period": "2026-05", "value": 18400}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        report = self.run_source_pack(
            "--query",
            "Плита ОСП",
            "--engine",
            "wordstat",
            "--input-file",
            str(wordstat_json),
            "--input-format",
            "json",
            "--write",
        )

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["distillate"]["engine"], "wordstat")
        self.assertEqual(report["distillate"]["wordstat"]["total_value"], 18400)
        groups = {row["source_group"] for row in report["distillate"]["wordstat"]["queries"]}
        self.assertEqual(groups, {"associations", "popular"})
        self.assertEqual(report["distillate"]["wordstat"]["history_points"], 1)

    def test_without_input_writes_guarded_plan_and_does_not_expose_secrets(self) -> None:
        env = os.environ.copy()
        env.update({"XMLRIVER_USER_ID": "12345", "XMLRIVER_API_KEY": "secret-key-value"})

        proc = subprocess.run(
            [
                sys.executable,
                str(XMLRIVER_SOURCE_PACK),
                str(self.cfg_path),
                "--query",
                "Плита ОСП",
                "--engine",
                "google",
                "--additional",
                "rq,rs,knowledge_graph",
                "--ai",
                "--ads",
                "--write",
                "--format",
                "json",
            ],
            cwd=self.tmp,
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
        self.assertNotIn("secret-key-value", proc.stdout)
        report = json.loads(proc.stdout)

        self.assertEqual(report["status"], "planned")
        self.assertFalse(report["paid_api_used"])
        self.assertTrue(report["request_plan"]["credentials_present"])
        self.assertIn("XMLRIVER_USER_ID", report["request_plan"]["env_names"])
        self.assertIn("XMLRIVER_API_KEY", report["request_plan"]["env_names"])
        self.assertIn("{XMLRIVER_API_KEY}", report["request_plan"]["url_template"])
        self.assertNotIn("secret-key-value", json.dumps(report, ensure_ascii=False))
        self.assertIn("paid_api_run", report["approval_gates"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
