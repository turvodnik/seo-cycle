#!/usr/bin/env python3
"""Schema contract smoke tests for low-token reports."""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seo_cycle_core.context import build_context_manifest
from seo_cycle_core.providers import notebooklm_health, perplexity_health


def load_script(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TOKEN_WASTE = load_script(ROOT / "scripts" / "token-waste-audit.py", "token_waste_audit")


class SchemaContractsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-schema-contracts-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.cfg_path = self.tmp / "seo-cycle.yaml"
        self.cfg_path.write_text(
            """
project:
  name: Schema Test
  domain: schema.test
locale:
  country: RU
engines:
  - name: yandex
project_type: ecommerce
governance:
  token_policy:
    raw_data_in_context: false
    distillate_max_lines: 20
    max_output_tokens_per_artifact: 1000
""",
            encoding="utf-8",
        )

    def test_context_manifest_contract_keys_are_stable(self) -> None:
        manifest = build_context_manifest(
            read_first=["seo/setup/context-pack.md"],
            do_not_load_raw=["raw API JSON"],
            outputs={"markdown": "seo/setup/context-pack.md", "json": "seo/setup/context-pack.json"},
            caps={"raw_data_in_context": False, "distillate_max_lines": 20},
            sources=[{"source": "gsc", "status": "enabled"}],
        )

        self.assertEqual(
            set(manifest),
            {"version", "read_first", "blocked_raw_artifacts", "source_caps", "sources", "outputs", "load_only"},
        )

    def test_token_waste_report_contract_keys_are_stable(self) -> None:
        report = TOKEN_WASTE.build_report(self.cfg_path)

        self.assertEqual(
            set(report),
            {"audit_id", "title", "generated_at", "config", "project_root", "status", "token_policy", "findings", "actions", "paths"},
        )

    def test_provider_health_contract_keys_are_stable(self) -> None:
        perplexity = perplexity_health(app_paths=[self.tmp / "Missing.app"], browser_available=False, env={})
        notebook = notebooklm_health(self.tmp / "missing.toml", tools_exposed=False)

        self.assertEqual(
            set(perplexity),
            {"provider", "status", "app_detected", "browser_available", "api_optional", "preferred_mode", "fallback_mode", "modes", "stores_password"},
        )
        self.assertEqual(
            set(notebook),
            {"provider", "configured", "tools_exposed", "status", "access_mode", "disabled_tools", "notebook_url", "ranking_signal", "allowed_use"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
