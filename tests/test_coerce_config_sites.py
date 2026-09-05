#!/usr/bin/env python3
"""T-063: closes the "unguarded int()/float() on a config value" class for
every remaining site found by a fresh, sweeping search of the tree (T-052
and T-053 fixed two, then a third; T-053's own reviewer found five more and
rolled them back as out-of-scope; this ticket re-finds and fixes all of
them, plus a dobified twin the T-063 reviewer of the previous ticket found
at `scripts/pulse.py:234`).

One test per fixed site, each calling the REAL function that contains the
fix with a garbage value for the exact config key that site reads. Per the
ticket's explicit requirement: not one shared test for all sites — a
mutation that reverts protection at ONE site must fail ONLY the test(s)
for that site, never the others. Every test also asserts the warning names
the offending config key (T-063 criterion 4 — "человек должен узнать, какой
ключ конфига испорчен").

Sites NOT touched here (recorded, not fixed, per ticket scope discipline):
- `nested_get(row, "metrics...")` conversions in ads-analytics.py /
  google-ads-fetch.py: these coerce API RESPONSE data, not project config —
  a different, already-tracked risk class (see T-059, `response_cost()`).
- `google-nlp-audit.py::env_int()`: already guards with its own
  try/except ValueError and never crashes; left as is to avoid pulling an
  isolated, dependency-free script into the seo_cycle_core coupling graph
  for a site that was never actually unguarded.
- `seo_cycle_core/loop.py::no_progress()` / `decide_next()` reading
  `state.get("no_progress_after"/"max_attempts")`: `state` is our OWN
  generated loop-state JSON (already sanitized on write by the
  `target_config()` fix below), not user-editable project config — out of
  the "конфиг или переменная окружения" class this ticket targets.
"""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.config import coerce_float, coerce_int  # noqa: E402
from seo_cycle_core.context import build_context_manifest  # noqa: E402
from seo_cycle_core.loop import target_config  # noqa: E402
from seo_cycle_core.rag import iter_project_documents  # noqa: E402


def load_hyphenated(name: str) -> "object":
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ads_analytics = load_hyphenated("ads-analytics")
seo_forecast = load_hyphenated("seo-forecast")
budget_mix_planner = load_hyphenated("budget-mix-planner")
token_waste_audit = load_hyphenated("token-waste-audit")
context_pack = load_hyphenated("context-pack")


def tmp_dir() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp(prefix="seo-coerce-sites-"))


class AdsAnalyticsThresholdsTest(unittest.TestCase):
    """scripts/ads-analytics.py:170-171 — `ads.analytics.top_position_threshold`
    and `ads.analytics.wasted_spend_min_cost`. An empty project (no db, no
    raw dumps) exercises `build_report()`'s early coercions without needing
    the full fixture used by test_ads_analytics.py — both functions it
    calls gracefully return {}/[] on missing files, so the ONLY thing that
    can raise here is an unguarded float() on the garbage config value."""

    def test_garbage_top_position_threshold_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"ads": {"analytics": {"top_position_threshold": "garbage", "wasted_spend_min_cost": 100}}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = ads_analytics.build_report(root, cfg)
        self.assertIsInstance(report, dict)
        self.assertIn("ads.analytics.top_position_threshold", stderr.getvalue())

    def test_garbage_wasted_spend_min_cost_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"ads": {"analytics": {"top_position_threshold": 3, "wasted_spend_min_cost": "garbage"}}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = ads_analytics.build_report(root, cfg)
        self.assertIsInstance(report, dict)
        self.assertIn("ads.analytics.wasted_spend_min_cost", stderr.getvalue())


class SeoForecastKpiTest(unittest.TestCase):
    """scripts/seo-forecast.py:174-175 — `kpi.lead_conversion_rate` and
    `kpi.months_to_target`."""

    def test_garbage_lead_conversion_rate_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"lead_conversion_rate": "garbage", "months_to_target": 6}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = seo_forecast.build_report(root, cfg)
        self.assertIsInstance(report, dict)
        self.assertIn("kpi.lead_conversion_rate", stderr.getvalue())

    def test_garbage_months_to_target_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"lead_conversion_rate": 0.02, "months_to_target": "garbage"}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = seo_forecast.build_report(root, cfg)
        self.assertIsInstance(report, dict)
        self.assertIn("kpi.months_to_target", stderr.getvalue())


class BudgetMixPlannerKpiTest(unittest.TestCase):
    """scripts/budget-mix-planner.py:106-107 — same two `kpi.*` keys, second
    call site (the `kpi.budget.*` ones two lines below already go through
    `numeric()`, which never raises — not touched, not tested here)."""

    def test_garbage_lead_conversion_rate_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"lead_conversion_rate": "garbage", "months_to_target": 6}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = budget_mix_planner.build_report(root, cfg, 0)
        self.assertIsInstance(report, dict)
        self.assertIn("kpi.lead_conversion_rate", stderr.getvalue())

    def test_garbage_months_to_target_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"lead_conversion_rate": 0.02, "months_to_target": "garbage"}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = budget_mix_planner.build_report(root, cfg, 0)
        self.assertIsInstance(report, dict)
        self.assertIn("kpi.months_to_target", stderr.getvalue())


class AdsApplyLimitsTest(unittest.TestCase):
    """scripts/ads-apply.py:209-210 — `ads.apply.max_changes_per_run` and
    `ads.apply.max_daily_budget`. Both are read inline in `main()`, so this
    goes end-to-end via subprocess in dry-run mode (no --live/--allow-write,
    so no real API call and no ticket requirement)."""

    def setUp(self) -> None:
        self.tmp = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "draft.json").write_text(
            json.dumps({"platform": "yandex_direct", "campaigns": []}), encoding="utf-8"
        )

    def write_cfg(self, max_changes: object, max_daily_budget: object) -> None:
        (self.tmp / "seo-cycle.yaml").write_text(
            "project: {name: ads-apply-test}\n"
            "ads:\n"
            "  enabled: true\n"
            "  yandex_direct: {enabled: true}\n"
            "  apply:\n"
            f"    max_changes_per_run: {max_changes}\n"
            f"    max_daily_budget: {max_daily_budget}\n",
            encoding="utf-8",
        )

    def run_apply(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "ads-apply.py"), "--draft", "draft.json", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )

    def test_garbage_max_changes_per_run_does_not_raise(self) -> None:
        self.write_cfg('"garbage"', 0)
        proc = self.run_apply()
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ads.apply.max_changes_per_run", proc.stderr)

    def test_garbage_max_daily_budget_does_not_raise(self) -> None:
        self.write_cfg(20, '"garbage"')
        proc = self.run_apply()
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ads.apply.max_daily_budget", proc.stderr)


class RagChunkingTest(unittest.TestCase):
    """scripts/seo_cycle_core/rag.py:166-167 — `rag.chunk_chars` and
    `rag.chunk_overlap`. `iter_project_documents` is a generator: the
    coercions run before the first `yield`, so `list(...)` on an empty
    project (no source files -> empty result, never raises on its own)
    forces them without needing any fixture."""

    def test_garbage_chunk_chars_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"rag": {"chunk_chars": "garbage", "chunk_overlap": 200}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            docs = list(iter_project_documents(root, cfg))
        self.assertEqual(docs, [])
        self.assertIn("rag.chunk_chars", stderr.getvalue())

    def test_garbage_chunk_overlap_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"rag": {"chunk_chars": 1200, "chunk_overlap": "garbage"}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            docs = list(iter_project_documents(root, cfg))
        self.assertEqual(docs, [])
        self.assertIn("rag.chunk_overlap", stderr.getvalue())


class LoopTargetConfigTest(unittest.TestCase):
    """scripts/seo_cycle_core/loop.py:161-162 (via `target_config()`) —
    per-target `max_attempts` and governance-wide `no_progress_after`."""

    def test_garbage_max_attempts_does_not_raise(self) -> None:
        cfg = {"governance": {"loop": {
            "targets": {"research_package": {"max_attempts": "garbage"}},
            "no_progress_after": 3,
        }}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            limits = target_config(cfg, "research-package")
        self.assertEqual(limits["max_attempts"], 5)  # spec's default_max_attempts
        self.assertIn("governance.loop.targets.research_package.max_attempts", stderr.getvalue())

    def test_garbage_no_progress_after_does_not_raise(self) -> None:
        cfg = {"governance": {"loop": {"no_progress_after": "garbage"}}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            limits = target_config(cfg, "research-package")
        self.assertGreaterEqual(limits["no_progress_after"], 2)
        self.assertIn("governance.loop.no_progress_after", stderr.getvalue())


class TokenWasteAuditPolicyTest(unittest.TestCase):
    """scripts/token-waste-audit.py:26-28 — the three
    `governance.token_policy.*` line counts/caps, read directly via
    `token_policy()` (pure function, no fixture needed)."""

    def test_garbage_distillate_max_lines_does_not_raise(self) -> None:
        cfg = {"governance": {"token_policy": {"distillate_max_lines": "garbage"}}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            policy = token_waste_audit.token_policy(cfg)
        self.assertEqual(policy["distillate_max_lines"], 220)
        self.assertIn("governance.token_policy.distillate_max_lines", stderr.getvalue())

    def test_garbage_max_output_tokens_per_artifact_does_not_raise(self) -> None:
        cfg = {"governance": {"token_policy": {"max_output_tokens_per_artifact": "garbage"}}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            policy = token_waste_audit.token_policy(cfg)
        self.assertEqual(policy["max_output_tokens_per_artifact"], 7000)
        self.assertIn("governance.token_policy.max_output_tokens_per_artifact", stderr.getvalue())

    def test_garbage_max_raw_rows_loaded_does_not_raise(self) -> None:
        cfg = {"governance": {"token_policy": {"max_raw_rows_loaded": "garbage"}}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            policy = token_waste_audit.token_policy(cfg)
        self.assertEqual(policy["max_raw_rows_loaded"], 200)
        self.assertIn("governance.token_policy.max_raw_rows_loaded", stderr.getvalue())


class ContextManifestCapsTest(unittest.TestCase):
    """scripts/seo_cycle_core/context.py:44-47 (`build_context_manifest`) —
    reached with UNCONVERTED raw config values via
    `task-router.py::governance_caps()`, which merely passes `cfg` values
    through without ever coercing them itself."""

    def _caps(self, **overrides: object) -> dict[str, object]:
        base = {
            "max_raw_rows_loaded": 200, "distillate_max_lines": 220,
            "browser_session_budget_minutes": 20, "browser_pages_per_phase_cap": 20,
        }
        base.update(overrides)
        return base

    def _manifest(self, caps: dict[str, object]) -> tuple[dict, str]:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            manifest = build_context_manifest(
                read_first=[], do_not_load_raw=[], outputs={}, caps=caps,
            )
        return manifest, stderr.getvalue()

    def test_garbage_max_raw_rows_loaded_does_not_raise(self) -> None:
        manifest, err = self._manifest(self._caps(max_raw_rows_loaded="garbage"))
        self.assertEqual(manifest["source_caps"]["max_raw_rows_loaded"], 200)
        self.assertIn("context_contract.caps.max_raw_rows_loaded", err)

    def test_garbage_distillate_max_lines_does_not_raise(self) -> None:
        manifest, err = self._manifest(self._caps(distillate_max_lines="garbage"))
        self.assertEqual(manifest["source_caps"]["distillate_max_lines"], 220)
        self.assertIn("context_contract.caps.distillate_max_lines", err)

    def test_garbage_browser_session_budget_minutes_does_not_raise(self) -> None:
        manifest, err = self._manifest(self._caps(browser_session_budget_minutes="garbage"))
        self.assertEqual(manifest["source_caps"]["browser_session_budget_minutes"], 20)
        self.assertIn("context_contract.caps.browser_session_budget_minutes", err)

    def test_garbage_browser_pages_per_phase_cap_does_not_raise(self) -> None:
        manifest, err = self._manifest(self._caps(browser_pages_per_phase_cap="garbage"))
        self.assertEqual(manifest["source_caps"]["browser_pages_per_phase_cap"], 20)
        self.assertIn("context_contract.caps.browser_pages_per_phase_cap", err)


class ContextPackTokenContractTest(unittest.TestCase):
    """scripts/context-pack.py:82-86 (`token_contract`) — the five
    `governance.token_policy.*` fallback-chain reads, with `route`/
    `launch_plan` both empty so the raw config value is what reaches the
    conversion."""

    def _contract(self, key: str, value: object) -> tuple[dict, str]:
        cfg = {"governance": {"token_policy": {key: value}}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            contract = context_pack.token_contract(cfg, {}, {})
        return contract, stderr.getvalue()

    def test_garbage_max_context_input_tokens_per_phase_does_not_raise(self) -> None:
        contract, err = self._contract("max_context_input_tokens_per_phase", "garbage")
        self.assertEqual(contract["max_context_input_tokens_per_phase"], 45000)
        self.assertIn("governance.token_policy.max_context_input_tokens_per_phase", err)

    def test_garbage_max_raw_rows_loaded_does_not_raise(self) -> None:
        contract, err = self._contract("max_raw_rows_loaded", "garbage")
        self.assertEqual(contract["max_raw_rows_loaded"], 200)
        self.assertIn("governance.token_policy.max_raw_rows_loaded", err)

    def test_garbage_distillate_max_lines_does_not_raise(self) -> None:
        contract, err = self._contract("distillate_max_lines", "garbage")
        self.assertEqual(contract["distillate_max_lines"], 220)
        self.assertIn("governance.token_policy.distillate_max_lines", err)

    def test_garbage_browser_session_budget_minutes_does_not_raise(self) -> None:
        contract, err = self._contract("browser_session_budget_minutes", "garbage")
        self.assertEqual(contract["browser_session_budget_minutes"], 20)
        self.assertIn("governance.token_policy.browser_session_budget_minutes", err)

    def test_garbage_browser_pages_per_phase_cap_does_not_raise(self) -> None:
        contract, err = self._contract("browser_pages_per_phase_cap", "garbage")
        self.assertEqual(contract["browser_pages_per_phase_cap"], 20)
        self.assertIn("governance.token_policy.browser_pages_per_phase_cap", err)


class AdsCacheTtlHoursTest(unittest.TestCase):
    """scripts/yandex-direct-fetch.py:272,285 and scripts/google-ads-fetch.py:220
    — `ads.cache_ttl_hours`, read inline in `main()`. Runs end-to-end
    (default/non---live mode) against a project with a fresh (same-second)
    raw cache dump, so both the cache-freshness check (first coercion) AND
    `summarize()` (second coercion, yandex-direct-fetch.py only) execute."""

    def setUp(self) -> None:
        self.tmp = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(
            "project: {name: cache-ttl-test}\nads:\n  cache_ttl_hours: \"garbage\"\n", encoding="utf-8"
        )

    def _seed_raw(self, platform: str, report: str, payload: dict) -> None:
        raw = self.tmp / "seo" / "ads" / "raw" / platform
        raw.mkdir(parents=True, exist_ok=True)
        (raw / f"{report}-latest.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_yandex_direct_fetch_garbage_ttl_does_not_raise(self) -> None:
        self._seed_raw("yandex_direct", "stats", {"rows": []})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "yandex-direct-fetch.py"), "--report", "stats", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)
        self.assertIn("ads.cache_ttl_hours", proc.stderr)

    def test_google_ads_fetch_garbage_ttl_does_not_raise(self) -> None:
        self._seed_raw("google_ads", "search_terms", {"results": []})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "google-ads-fetch.py"), "--report", "search_terms", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)
        self.assertIn("ads.cache_ttl_hours", proc.stderr)


class CoerceFloatUnitTest(unittest.TestCase):
    """`coerce_float()` itself — the dial-in twin of `coerce_int()`,
    same negative-control shape as `CoerceIntUnitTest` in
    tests/test_coerce_int.py."""

    def test_valid_string_float(self) -> None:
        self.assertEqual(coerce_float("2.5", 5), 2.5)

    def test_valid_native_float(self) -> None:
        self.assertEqual(coerce_float(3.5, 5), 3.5)

    def test_none_falls_back_to_default(self) -> None:
        self.assertEqual(coerce_float(None, 5), 5)

    def test_falsy_zero_falls_back_to_default(self) -> None:
        self.assertEqual(coerce_float(0, 5), 5)

    def test_garbage_string_does_not_raise_and_warns(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = coerce_float("soon", 5, name="pulse.drop_alert_pct")
        self.assertEqual(result, 5)
        self.assertIn("pulse.drop_alert_pct", stderr.getvalue())
        self.assertIn("soon", stderr.getvalue())

    def test_garbage_type_does_not_raise(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = coerce_float({"nested": "dict"}, 7, name="kpi.lead_conversion_rate")
        self.assertEqual(result, 7)
        self.assertIn("kpi.lead_conversion_rate", stderr.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
