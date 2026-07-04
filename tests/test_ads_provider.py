#!/usr/bin/env python3
"""Tests for the guarded ads layer: health, fetch offline modes, draft builder, apply safeguards."""

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
SCRIPTS = ROOT / "scripts"

FAKE_TOKEN = "fake-direct-token-a1b2c3"

ADS_ENABLED_CFG = """project:
  name: ads-test
  url: https://example.com
region_profile: ru
ads:
  enabled: true
  yandex_direct:
    enabled: true
    sandbox: true
  google_ads:
    enabled: true
"""


class AdsTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-ads-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo").mkdir()
        self.write_cfg(ADS_ENABLED_CFG)

    def write_cfg(self, text: str) -> None:
        (self.tmp / "seo-cycle.yaml").write_text(text, encoding="utf-8")

    def run_script(self, script: str, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("YANDEX_DIRECT", "GOOGLE_ADS"))}
        env.update(env_extra or {})
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )


class AdsHealthTest(AdsTestBase):
    def test_direct_health_without_env_is_needs_credentials(self) -> None:
        proc = self.run_script("yandex-direct-health.py", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "needs_credentials")
        self.assertEqual(report["primary_platform"], "yandex_direct")

    def test_google_ads_health_is_region_limited_for_ru(self) -> None:
        proc = self.run_script("google-ads-health.py", "--format", "json")
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "region_limited")
        self.assertTrue(report["region_note"])

    def test_direct_health_with_token_is_available_and_never_prints_secret(self) -> None:
        proc = self.run_script("yandex-direct-health.py", "--format", "json",
                               env_extra={"YANDEX_DIRECT_TOKEN": FAKE_TOKEN})
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "available")
        self.assertNotIn(FAKE_TOKEN, proc.stdout)
        self.assertNotIn(FAKE_TOKEN, proc.stderr)


class AdsFetchOfflineTest(AdsTestBase):
    def test_fetch_without_cache_or_live_is_graceful_noop(self) -> None:
        proc = self.run_script("yandex-direct-fetch.py", "--report", "campaigns")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("No fresh cache", proc.stderr)

    def test_fetch_ingests_input_file_and_writes_raw_plus_summary(self) -> None:
        export = self.tmp / "campaigns-export.json"
        export.write_text(
            json.dumps({"result": {"Campaigns": [
                {"Id": 1, "Name": "Brand", "State": "ON"},
                {"Id": 2, "Name": "Generic", "State": "SUSPENDED"},
            ]}}),
            encoding="utf-8",
        )
        proc = self.run_script("yandex-direct-fetch.py", "--report", "campaigns",
                               "--input-file", str(export), "--write", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        raw = self.tmp / "seo" / "ads" / "raw" / "yandex_direct" / "campaigns-latest.json"
        self.assertTrue(raw.exists())
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["reports"]["campaigns"]["count"], 2)
        self.assertEqual(summary["reports"]["campaigns"]["active"], 1)
        self.assertTrue((self.tmp / "seo" / "ads" / "yandex-direct-summary.md").exists())

    def test_fetch_live_without_env_fails_before_any_network(self) -> None:
        proc = self.run_script("yandex-direct-fetch.py", "--report", "campaigns", "--live")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("missing env", proc.stderr)

    def test_fetch_disabled_layer_blocks_ingest(self) -> None:
        self.write_cfg("project:\n  name: ads-off\nregion_profile: ru\n")
        export = self.tmp / "x.json"
        export.write_text("{}", encoding="utf-8")
        proc = self.run_script("yandex-direct-fetch.py", "--input-file", str(export))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("disabled", proc.stderr)

    def test_google_fetch_ingests_gaql_export(self) -> None:
        export = self.tmp / "gaql.json"
        export.write_text(
            json.dumps({"results": [
                {"campaign": {"id": "11", "name": "Search RU", "status": "ENABLED"}},
            ]}),
            encoding="utf-8",
        )
        proc = self.run_script("google-ads-fetch.py", "--report", "campaigns",
                               "--input-file", str(export), "--write", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["reports"]["campaigns"]["count"], 1)


class AdsDraftBuilderTest(AdsTestBase):
    def seed_package(self) -> pathlib.Path:
        package = self.tmp / "seo" / "research-package"
        package.mkdir(parents=True)
        (package / "semantic-architecture-final.json").write_text(
            json.dumps({"clusters": [
                {"id": "vagonka", "name": "Вагонка", "primary_keyword": "купить вагонку",
                 "suggested_url": "/catalog/vagonka/", "priority": "P1", "mvp": True},
                {"id": "later", "name": "Later", "primary_keyword": "later kw",
                 "suggested_url": "/later/", "priority": "P3", "mvp": False},
            ]}),
            encoding="utf-8",
        )
        (package / "semantic-core.csv").write_text(
            "keyword,cluster_id,frequency\n"
            "купить вагонку,vagonka,1000\n"
            "вагонка цена,vagonka,500\n",
            encoding="utf-8",
        )
        return package

    def test_draft_builder_creates_reviewable_draft_without_applying(self) -> None:
        package = self.seed_package()
        proc = self.run_script("ads-draft-builder.py", str(package), "--write", "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        draft = json.loads(proc.stdout)
        self.assertEqual(draft["platform"], "yandex_direct")  # ru → primary auto
        self.assertTrue(draft["applies_nothing"])
        self.assertEqual(draft["summary"]["campaigns"], 1)  # P3/non-mvp excluded
        self.assertEqual(draft["summary"]["keywords"], 2)
        group = draft["campaigns"][0]["ad_groups"][0]
        self.assertEqual(group["final_url"], "https://example.com/catalog/vagonka/")
        drafts = list((self.tmp / "seo" / "ads" / "drafts").glob("*-yandex-direct-draft.json"))
        self.assertEqual(len(drafts), 1)

    def test_draft_builder_ticket_creates_approval(self) -> None:
        package = self.seed_package()
        proc = self.run_script("ads-draft-builder.py", str(package), "--write", "--create-ticket")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        approvals = (self.tmp / "seo" / "pending-approvals.md").read_text(encoding="utf-8")
        self.assertIn("type:ads_campaign_draft", approvals)


class AdsApplySafeguardsTest(AdsTestBase):
    def write_draft(self, keywords: int = 2) -> pathlib.Path:
        draft = {
            "draft_id": "yandex_direct-test",
            "platform": "yandex_direct",
            "campaigns": [{
                "name": "seo-cycle P1 search",
                "budget_daily": 0,
                "negatives": [],
                "ad_groups": [{
                    "name": "Вагонка",
                    "final_url": "https://example.com/catalog/vagonka/",
                    "keywords": [{"text": f"kw {index}", "match_type": "phrase"} for index in range(keywords)],
                    "ads": [{"final_url": "https://example.com/catalog/vagonka/"}],
                }],
            }],
        }
        path = self.tmp / "draft.json"
        path.write_text(json.dumps(draft), encoding="utf-8")
        return path

    def test_default_is_dry_run_plan(self) -> None:
        draft = self.write_draft()
        proc = self.run_script("ads-apply.py", "--draft", str(draft), "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        plan = json.loads(proc.stdout)
        self.assertEqual(plan["mode"], "dry_run")
        self.assertTrue(any(op["op"] == "create_campaign" for op in plan["operations"]))

    def test_live_without_ticket_refused(self) -> None:
        draft = self.write_draft()
        proc = self.run_script("ads-apply.py", "--draft", str(draft), "--live", "--allow-write")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--ticket", proc.stderr)

    def test_live_with_pending_ticket_refused(self) -> None:
        draft = self.write_draft()
        create = self.run_script("approval-gate.py", "create", "--type", "ads_campaign_draft",
                                 "--title", "test draft")
        ticket = create.stdout.strip().splitlines()[-1]
        proc = self.run_script("ads-apply.py", "--draft", str(draft), "--ticket", ticket,
                               "--live", "--allow-write")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("not approved", proc.stderr)

    def test_operation_cap_blocks_oversized_draft(self) -> None:
        draft = self.write_draft(keywords=40)  # 40 kw + campaign + group + ad > 20 cap
        proc = self.run_script("ads-apply.py", "--draft", str(draft))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("max_changes_per_run", proc.stderr)

    def test_report_only_policy_blocks_apply(self) -> None:
        self.write_cfg(ADS_ENABLED_CFG.replace("ads:\n  enabled: true",
                                               "ads:\n  enabled: true\n  policy: report_only"))
        draft = self.write_draft()
        proc = self.run_script("ads-apply.py", "--draft", str(draft))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("report_only", proc.stderr)


if __name__ == "__main__":
    unittest.main()
