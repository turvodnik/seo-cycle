#!/usr/bin/env python3
"""Smoke tests for the project spend/subscription guard."""

from __future__ import annotations

import datetime as dt
import json
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
TEMPLATE = ROOT / "config" / "project.template.yaml"
INTAKE = ROOT / "scripts" / "project-intake-wizard.py"
TOOL_STACK = ROOT / "scripts" / "tool-stack-recommender.py"
SPEND = ROOT / "scripts" / "spend-guard.py"


@unittest.skipIf(yaml is None, "PyYAML is required")
class SpendGuardTest(unittest.TestCase):
    def make_project(self, *, country: str, project_type: str, tuned_budget: bool = False) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cycle-spend-guard-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        cfg_path = tmp / "seo-cycle.yaml"
        cfg = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
        cfg["project"]["name"] = f"{country} {project_type}"
        cfg["project"]["domain"] = f"{country.lower()}-{project_type}.test"
        cfg["project_type"] = project_type
        cfg["locale"]["country"] = country
        cfg["locale"]["language"] = "ru" if country == "RU" else "en"
        cfg["locale"]["locale_iso"] = "ru-RU" if country == "RU" else "en-US"
        cfg["locale"]["google_gl"] = country.lower()
        cfg["locale"]["google_hl"] = cfg["locale"]["language"]
        cfg["region_profile"] = "ru" if country == "RU" else "us"
        if tuned_budget:
            cfg["governance"]["budget_policy"]["monthly_total_usd_cap"] = 20
            cfg["governance"]["budget_policy"]["monthly_paid_api_usd_cap"] = 5
            cfg["governance"]["budget_policy"]["monthly_llm_usd_cap"] = 10
            cfg["governance"]["subscriptions"]["neuronwriter"] = {
                "enabled": True,
                "plan": "Neuron-Yellow-Diamond",
                "monthly_content_writer_limit": 200,
                "monthly_ai_credit_limit": 105000,
                "reserve_content_writer": 5,
                "reserve_ai_credits": 1000,
            }
            cfg["governance"]["subscriptions"]["openai"] = {
                "enabled": True,
                "monthly_usd_cap": 10,
            }
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        for command in (
            [sys.executable, str(INTAKE), str(cfg_path), "--defaults", "--write"],
            [sys.executable, str(TOOL_STACK), str(cfg_path), "--write", "--format", "json"],
        ):
            subprocess.run(command, cwd=tmp, check=True, text=True, capture_output=True)
        return cfg_path

    def write_ledger(self, cfg_path: pathlib.Path) -> None:
        ledger = cfg_path.parent / "seo" / "usage" / "usage-ledger.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        month = dt.date.today().strftime("%Y-%m")
        rows = [
            {
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "month": month,
                "service": "neuronwriter",
                "category": "paid_api",
                "metrics": {"content_writer": 3, "ai_credits": 200},
                "task": "seed",
            },
            {
                "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
                "month": month,
                "service": "openai",
                "category": "llm",
                "metrics": {"usd": 1.5, "input_tokens": 1000, "output_tokens": 200},
                "task": "seed",
            },
        ]
        ledger.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

    def run_spend_guard(self, cfg_path: pathlib.Path) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SPEND), str(cfg_path), "--write", "--format", "json"],
            cwd=cfg_path.parent,
            check=True,
            text=True,
            capture_output=True,
        )
        return json.loads(proc.stdout)

    def test_default_ru_project_blocks_paid_spend_without_approval(self) -> None:
        cfg_path = self.make_project(country="RU", project_type="ecommerce")
        report = self.run_spend_guard(cfg_path)
        services = {row["service"]: row for row in report["service_guards"]}

        self.assertEqual(report["budget_contract"]["monthly_paid_api_usd_cap"], 0)
        self.assertFalse(services["google_cloud_nlp"]["allowed_now"])
        self.assertIn("paid_api_run", services["google_cloud_nlp"]["approval_gates"])
        self.assertFalse(services["openai"]["allowed_now"])
        self.assertIn("llm_token_spend", services["openai"]["approval_gates"])
        self.assertIn("raw_data_on_disk", report["token_guards"])
        self.assertIn("cache_first", report["token_guards"])
        self.assertIn("google_cloud_nlp", report["preflight_commands"])
        self.assertTrue((cfg_path.parent / "seo" / "setup" / "spend-guard.md").exists())
        self.assertTrue((cfg_path.parent / "seo" / "spend-guard.generated.yaml").exists())

    def test_configured_subscription_reports_remaining_limits_and_commands(self) -> None:
        cfg_path = self.make_project(country="US", project_type="local_business", tuned_budget=True)
        self.write_ledger(cfg_path)
        report = self.run_spend_guard(cfg_path)
        services = {row["service"]: row for row in report["service_guards"]}

        self.assertTrue(services["neuronwriter"]["allowed_now"])
        self.assertEqual(services["neuronwriter"]["limits"]["content_writer"]["remaining"], 192)
        self.assertEqual(services["neuronwriter"]["limits"]["ai_credits"]["remaining"], 103800)
        self.assertTrue(services["openai"]["allowed_now"])
        self.assertEqual(services["openai"]["limits"]["usd"]["remaining"], 8.5)
        self.assertIn("usage-ledger.py check", services["openai"]["preflight_command"])
        self.assertNotIn("=", "\n".join(report["env_names"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
