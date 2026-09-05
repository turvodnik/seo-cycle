#!/usr/bin/env python3
"""T-063: closes the "unguarded int()/float() on a config value" class for
every remaining site found by a fresh, sweeping search of the tree (T-052
and T-053 fixed two, then a third; T-053's own reviewer found five more and
rolled them back as out-of-scope; this ticket re-finds and fixes all of
them, plus a float twin the T-053 reviewer found at `scripts/pulse.py:234`).

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

import datetime as dt
import importlib.util
import io
import json
import math
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.config import coerce_float, numeric, safe_round  # noqa: E402
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
setup_gap_audit = load_hyphenated("setup-gap-audit")
research_package_quality = load_hyphenated("research-package-quality")
spend_guard = load_hyphenated("spend-guard")
launch_plan = load_hyphenated("launch-plan")
kpi_contract = load_hyphenated("kpi-contract")
validate_config = load_hyphenated("validate-config")
growth_roadmap = load_hyphenated("growth-roadmap")
triggers_eval = load_hyphenated("triggers-eval")


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

    # NOTE (T-063 review): `governance.loop.no_progress_after`'s call site
    # also passes `falsy_to_default=False` (original had no `or default`),
    # but the outer `max(2, ...)` floor happens to equal
    # `DEFAULT_NO_PROGRESS_AFTER` (both 2), so an explicit `0` produces the
    # same final `2` under either flag value — there is no black-box
    # assertion on `target_config()`'s return value that distinguishes
    # them. The flag's own semantics are proven directly in
    # `CoerceIntFalsyToDefaultFlagTest` (tests/test_coerce_int.py); the
    # wiring at this specific call site is confirmed by code review and by
    # `mutate.py`'s mutation-kill run (see the ticket's «Результат»).


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

    def test_explicit_zero_survives_at_every_key(self) -> None:
        """T-063 review: the ORIGINAL `int(a.get(k, b.get(k, c.get(k, d))))`
        chain had no `or default` anywhere — an explicit `0` (e.g.
        `max_raw_rows_loaded: 0` = "load nothing") was already a legitimate
        value distinct from the default and must keep surviving as `0`,
        not get silently replaced by `coerce_int()`'s historical
        `value or default` idiom. Covers all 5 keys in one pass."""
        keys = (
            "max_context_input_tokens_per_phase", "max_raw_rows_loaded", "distillate_max_lines",
            "browser_session_budget_minutes", "browser_pages_per_phase_cap",
        )
        for key in keys:
            with self.subTest(key=key):
                contract, err = self._contract(key, 0)
                self.assertEqual(contract[key], 0)
                self.assertNotIn("WARNING", err)


class AdsCacheTtlHoursTest(unittest.TestCase):
    """scripts/yandex-direct-fetch.py:272,285 and scripts/google-ads-fetch.py:220
    — `ads.cache_ttl_hours`, read inline in `main()`. Runs end-to-end
    (default/non---live mode) against a project with a fresh (same-second)
    raw cache dump, so both the cache-freshness check (first coercion) AND
    `summarize()` (second coercion, yandex-direct-fetch.py only) execute."""

    def setUp(self) -> None:
        self.tmp = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self._write_cfg('"garbage"')

    def _write_cfg(self, ttl_value: str) -> None:
        (self.tmp / "seo-cycle.yaml").write_text(
            f"project: {{name: cache-ttl-test}}\nads:\n  cache_ttl_hours: {ttl_value}\n", encoding="utf-8"
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

    def test_yandex_direct_fetch_explicit_zero_ttl_is_not_silently_replaced(self) -> None:
        """T-063 review: `float(ads.get("cache_ttl_hours", 24))` had no
        `or default` — `cache_ttl_hours: 0` legitimately means "never trust
        the cache" and must NOT become the 24h default. Proven behaviorally
        (not just via the no-warning signal): with ttl=0, a cache file
        written moments ago is already older than the (zero) TTL, so
        yandex-direct-fetch.py must report "no fresh cache" instead of
        silently accepting it as if TTL were the 24h default."""
        self._write_cfg("0")
        self._seed_raw("yandex_direct", "stats", {"rows": []})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "yandex-direct-fetch.py"), "--report", "stats", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)
        self.assertNotIn("WARNING", proc.stderr)
        self.assertIn("No fresh cache", proc.stderr)

    def test_google_ads_fetch_explicit_zero_ttl_is_not_silently_replaced(self) -> None:
        """Same as above, for `scripts/google-ads-fetch.py:220` — its own,
        separate `coerce_float(..., falsy_to_default=False)` call site."""
        self._write_cfg("0")
        self._seed_raw("google_ads", "search_terms", {"results": []})
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "google-ads-fetch.py"), "--report", "search_terms", "--format", "json"],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)
        self.assertNotIn("WARNING", proc.stderr)
        self.assertIn("No fresh cache", proc.stderr)


class CoerceFloatUnitTest(unittest.TestCase):
    """`coerce_float()` itself — the float twin of `coerce_int()`,
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


class SetupGapAuditBudgetCapTest(unittest.TestCase):
    """scripts/setup-gap-audit.py:369 — `governance.budget_policy.
    monthly_paid_api_usd_cap`. T-063 gate round 2 finding; `build_report()`
    reads straight from a config path (missing tool-stack/spend-guard/etc.
    reports all gracefully degrade to {})."""

    def test_garbage_monthly_paid_api_usd_cap_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg_path = root / "seo-cycle.yaml"
        cfg_path.write_text(
            "project: {name: gap-audit-test}\n"
            "governance:\n"
            "  budget_policy:\n"
            "    monthly_paid_api_usd_cap: not-a-number\n",
            encoding="utf-8",
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = setup_gap_audit.build_report(cfg_path)
        self.assertIsInstance(report, dict)
        self.assertIn("governance.budget_policy.monthly_paid_api_usd_cap", stderr.getvalue())


class ResearchPackageQualityMinBytesTest(unittest.TestCase):
    """scripts/research-package-quality.py:235 —
    `quality_gates.required_research_sources[*].min_bytes`. T-063 gate
    round 2 finding; reviewer's own repro used a LIST value (TypeError, not
    ValueError) — covered here alongside a plain garbage string."""

    def test_list_value_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"quality_gates": {"required_research_sources": [
            {"id": "serp", "min_bytes": [1, 2, 3], "path": "does-not-exist.json"},
        ]}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            missing = research_package_quality.check_required_research_sources(root, cfg)
        self.assertIsInstance(missing, list)
        self.assertIn("quality_gates.required_research_sources[serp].min_bytes", stderr.getvalue())

    def test_garbage_string_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"quality_gates": {"required_research_sources": [
            {"id": "serp", "min_bytes": "lots", "path": "does-not-exist.json"},
        ]}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            research_package_quality.check_required_research_sources(root, cfg)
        self.assertIn("quality_gates.required_research_sources[serp].min_bytes", stderr.getvalue())


class SpendGuardLaunchPlanTokenContractTest(unittest.TestCase):
    """scripts/spend-guard.py:200-206 and scripts/launch-plan.py:260-266 —
    T-063 gate round 2 finding: BOTH files carry their own private copy of
    `numeric()` (never imported from `seo_cycle_core.config`), and BOTH
    wrapped its result in a bare `int(...)` for the same six
    `governance.token_policy.*` keys already closed in `context-pack.py`.
    `numeric()` itself never raises (T-052/T-053 already-fixed contract),
    so the crash was invisible to any test exercising `numeric()` alone —
    only the outer, unprotected `int(...)` truncation could raise, and only
    on the read that never happened in the original suite: `.inf`."""

    KEYS = (
        "max_context_input_tokens_per_phase", "max_output_tokens_per_artifact", "max_raw_rows_loaded",
        "distillate_max_lines", "browser_session_budget_minutes", "browser_pages_per_phase_cap",
    )

    def _cfg(self, key: str, value: object) -> dict:
        return {"governance": {"token_policy": {key: value}}}

    def test_spend_guard_garbage_and_infinite_values_do_not_raise(self) -> None:
        for key in self.KEYS:
            with self.subTest(module="spend-guard", key=key, value="garbage"):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    contract = spend_guard.token_contract(self._cfg(key, "garbage"))
                self.assertIn("governance.token_policy." + key, stderr.getvalue())
                self.assertIsInstance(contract[key], int)
            with self.subTest(module="spend-guard", key=key, value="inf"):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    spend_guard.token_contract(self._cfg(key, float("inf")))
                self.assertIn("governance.token_policy." + key, stderr.getvalue())

    def test_launch_plan_garbage_and_infinite_values_do_not_raise(self) -> None:
        for key in self.KEYS:
            with self.subTest(module="launch-plan", key=key, value="garbage"):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    contract = launch_plan.token_contract(self._cfg(key, "garbage"))
                self.assertIn("governance.token_policy." + key, stderr.getvalue())
                self.assertIsInstance(contract[key], int)
            with self.subTest(module="launch-plan", key=key, value="inf"):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    launch_plan.token_contract(self._cfg(key, float("inf")))
                self.assertIn("governance.token_policy." + key, stderr.getvalue())

    def test_explicit_zero_survives_at_every_key_both_modules(self) -> None:
        for module in (spend_guard, launch_plan):
            for key in self.KEYS:
                with self.subTest(module=module.__name__, key=key):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        contract = module.token_contract(self._cfg(key, 0))
                    self.assertEqual(contract[key], 0)
                    self.assertNotIn("WARNING", stderr.getvalue())

    def test_quoted_float_string_still_parses_via_float_first_both_modules(self) -> None:
        """T-063 gate round 2 (🔴B): the ORIGINAL code here was
        `int(numeric(value, default))` — `numeric()` parses through
        `float()` first, so a quoted `"2.5"`/`"1e3"` worked on
        `origin/main` (became `2`/`1000`). The first fix replaced the whole
        expression with a bare `coerce_int(value, default)`, which parses
        via `int()` directly — `int("2.5")` raises `ValueError`, so the
        value silently became the DEFAULT instead, with rc=0 and no
        warning. `via_float=True` restores the float-first parse."""
        for module in (spend_guard, launch_plan):
            for key in self.KEYS:
                with self.subTest(module=module.__name__, key=key, value="'2.5'"):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        contract = module.token_contract(self._cfg(key, "2.5"))
                    self.assertEqual(contract[key], 2)
                    self.assertEqual(stderr.getvalue(), "")
                with self.subTest(module=module.__name__, key=key, value="'1e3'"):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        contract = module.token_contract(self._cfg(key, "1e3"))
                    self.assertEqual(contract[key], 1000)
                    self.assertEqual(stderr.getvalue(), "")


class SeoForecastCtrCurveTest(unittest.TestCase):
    """scripts/seo-forecast.py::load_ctr_curve() — `kpi.ctr_curve` override
    entries.

    T-063 gate round 2 (1st pass): `curve[int(key)] = float(value)` alone
    never raised on `.inf` (YAML parses it straight into the Python float
    `inf`, no string involved) — the poisoned CTR then propagates through
    `scenario_clicks()`'s running total and crashes a LATER bare
    `round(total)` in `build_report()`, nowhere near this function.

    T-063 gate round 2 (2nd pass, 🔴A): the FIRST fix for that (skip a
    non-finite override value, same as a genuinely malformed one) was
    itself a regression — `.inf`/`.nan` in `kpi.ctr_curve` was a legitimate
    value on `origin/main` (accepted right here, `float()` never raises on
    it), and skipping it silently narrowed accepted config. The actual fix
    moved downstream: `build_report()` guards its own bare `round(...)`
    calls with `safe_round()` instead of this function refusing the value
    (see `SeoForecastSafeRoundTest` below). `load_ctr_curve()` itself now
    matches `origin/main` again — `.inf`/`.nan` overrides are STORED, only
    genuinely unparseable ones (bad TYPE, or a key that itself overflows
    `int()`) are skipped."""

    def test_infinite_override_value_is_stored_not_skipped(self) -> None:
        """Matches `origin/main`: `float(inf)` never raises, so the value
        is stored as-is — NOT silently replaced by the default curve."""
        curve = seo_forecast.load_ctr_curve({"kpi": {"ctr_curve": {1: float("inf")}}})
        self.assertEqual(curve[1], float("inf"))

    def test_nan_override_value_is_stored_not_skipped(self) -> None:
        curve = seo_forecast.load_ctr_curve({"kpi": {"ctr_curve": {1: float("nan")}}})
        self.assertTrue(math.isnan(curve[1]))

    def test_garbage_override_value_is_skipped(self) -> None:
        """A genuinely unparseable value (not a number at all) still can't
        be stored — same "can't parse it -> ignore this one entry"
        semantics `origin/main` already had."""
        curve = seo_forecast.load_ctr_curve({"kpi": {"ctr_curve": {1: "garbage"}}})
        self.assertEqual(curve[1], seo_forecast.DEFAULT_CTR_CURVE[1])

    def test_infinite_override_key_does_not_raise(self) -> None:
        """`.inf` as the OVERRIDE KEY (not value) DOES crash `int(key)` on
        `origin/main` (`OverflowError`) — that's a genuine crash-class site,
        guarded right here since it never worked in the first place."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            curve = seo_forecast.load_ctr_curve({"kpi": {"ctr_curve": {float("inf"): 0.5}}})
        self.assertEqual(curve, seo_forecast.DEFAULT_CTR_CURVE)

    def test_infinite_ctr_curve_does_not_crash_build_report(self) -> None:
        """End-to-end: the reviewer's own reproduction shape — a poisoned
        CTR curve entry must not crash `build_report()`'s later
        `round(total)` calls, and the value survives (not silently
        replaced) when it actually gets used (position 1 tracked)."""
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        package = root / "seo" / "research-package"
        package.mkdir(parents=True)
        (package / "semantic-core.csv").write_text(
            "keyword,frequency,cluster_id\nкупить вагонку,1000,vagonka\n", encoding="utf-8",
        )
        db = root / "seo" / "seo.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE positions (snapshot_date TEXT, engine TEXT, query TEXT,"
            " position REAL, clicks INTEGER, impressions INTEGER, url TEXT)"
        )
        conn.execute("INSERT INTO positions VALUES ('2026-09-01','yandex','купить вагонку',1.0,10,100,'/x')")
        conn.commit()
        conn.close()
        cfg = {"kpi": {"ctr_curve": {1: float("inf")}}}
        report = seo_forecast.build_report(root, cfg)
        self.assertEqual(report["scenarios"]["current"]["monthly_clicks"], float("inf"))


class KpiContractToleranceTest(unittest.TestCase):
    """scripts/kpi-contract.py:181-182 — `kpi.tolerance_pct` and
    `kpi.lead_conversion_rate`.

    T-063 gate round 2 (1st pass): `numeric()` alone never raises, but
    `tolerance` feeds a later BARE `round(tolerance * 100)` (no ndigits)
    when building the report `contract` — that raises `OverflowError` on
    `.inf` and `ValueError` on `.nan`, arbitrarily far downstream from
    where the garbage config value entered.

    T-063 gate round 2 (2nd pass, 🔴A): rejecting `.inf`/`.nan` AT
    `coerce_float()` (the first fix) was itself a regression — `.inf` is a
    legitimate value at other `coerce_float()` sites, and a blanket rule in
    the shared helper silently narrowed accepted config everywhere. Fixed
    at the actual crash point instead: `"tolerance_pct": safe_round(...)`
    — `tolerance_pct` in the report now correctly SURVIVES as `inf`/`nan`
    (matching what a value-preserving fix should do), it just doesn't
    crash getting there."""

    def test_infinite_tolerance_pct_survives_without_raising(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"tolerance_pct": float("inf")}}
        report = kpi_contract.build_report(root, cfg)
        self.assertEqual(report["contract"]["tolerance_pct"], float("inf"))

    def test_nan_tolerance_pct_survives_without_raising(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"tolerance_pct": float("nan")}}
        report = kpi_contract.build_report(root, cfg)
        self.assertTrue(math.isnan(report["contract"]["tolerance_pct"]))

    def test_garbage_string_tolerance_pct_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"tolerance_pct": "loose"}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = kpi_contract.build_report(root, cfg)
        self.assertEqual(report["contract"]["tolerance_pct"], 20)
        self.assertIn("kpi.tolerance_pct", stderr.getvalue())

    def test_garbage_lead_conversion_rate_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"lead_conversion_rate": "garbage"}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = kpi_contract.build_report(root, cfg)
        self.assertEqual(report["contract"]["lead_conversion_rate"], 0.02)
        self.assertIn("kpi.lead_conversion_rate", stderr.getvalue())

    def test_explicit_zero_survives_at_both_keys(self) -> None:
        """`numeric(value, default)`'s bare `float(value)` (no `or default`)
        already preserved an explicit `0` — must still, via
        `falsy_to_default=False`."""
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"tolerance_pct": 0, "lead_conversion_rate": 0}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = kpi_contract.build_report(root, cfg)
        self.assertEqual(report["contract"]["tolerance_pct"], 0)
        self.assertEqual(report["contract"]["lead_conversion_rate"], 0)
        self.assertNotIn("WARNING", stderr.getvalue())


class CoerceFloatAcceptsInfiniteResultTest(unittest.TestCase):
    """T-063 gate round 2 (🔴A): `coerce_float()` must NOT reject
    `inf`/`-inf`/`nan` as a result — an earlier version of this fix did,
    and the gate proved it was a regression: `.inf` is a legitimate value
    at 11 of the 13 `coerce_float()` call sites in the tree
    (`ads.cache_ttl_hours` = "never expire the cache",
    `ads.analytics.wasted_spend_min_cost` = "never alert", etc.) — all of
    them accepted `.inf` on `origin/main` without raising. `coerce_float()`
    only guards against genuinely non-numeric/type-mismatched input
    (`TypeError`/`ValueError`/`OverflowError` from the `float()` call
    itself), never against a value that parsed fine but happens to be
    infinite."""

    def test_positive_infinity_passes_through(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = coerce_float(float("inf"), 5, name="ads.cache_ttl_hours")
        self.assertEqual(result, float("inf"))
        self.assertEqual(stderr.getvalue(), "")

    def test_negative_infinity_passes_through(self) -> None:
        self.assertEqual(coerce_float(float("-inf"), 5), float("-inf"))

    def test_nan_passes_through(self) -> None:
        self.assertTrue(math.isnan(coerce_float(float("nan"), 5)))

    def test_infinity_passes_through_with_falsy_to_default_false(self) -> None:
        self.assertEqual(coerce_float(float("inf"), 5, falsy_to_default=False), float("inf"))

    def test_finite_values_still_pass_through(self) -> None:
        self.assertEqual(coerce_float(3.5, 5), 3.5)
        self.assertEqual(coerce_float(0, 5, falsy_to_default=False), 0)

    def test_garbage_string_still_falls_back(self) -> None:
        """Only genuinely unparseable input is garbage — `coerce_float()`'s
        original job, unaffected by the inf/nan reversal."""
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = coerce_float("not-a-number", 5, name="ads.cache_ttl_hours")
        self.assertEqual(result, 5)
        self.assertIn("ads.cache_ttl_hours", stderr.getvalue())


class SafeRoundTest(unittest.TestCase):
    """`safe_round()` (T-063 gate round 2, 🔴A fix) — a bare `round(x)`/
    `round(x, n)` that never raises on `inf`/`-inf`/`nan`, returning the
    value unrounded instead. This is how the ticket now guards a
    downstream truncation point WITHOUT rejecting an upstream value that
    was never garbage (see `coerce_float()`'s docstring)."""

    def test_finite_value_rounds_normally(self) -> None:
        self.assertEqual(safe_round(3.7), 4)
        self.assertEqual(safe_round(3.456, 2), 3.46)

    def test_positive_infinity_returns_unrounded(self) -> None:
        self.assertEqual(safe_round(float("inf")), float("inf"))

    def test_negative_infinity_returns_unrounded(self) -> None:
        self.assertEqual(safe_round(float("-inf")), float("-inf"))

    def test_nan_returns_unrounded(self) -> None:
        self.assertTrue(math.isnan(safe_round(float("nan"))))

    def test_infinity_with_ndigits_returns_unrounded(self) -> None:
        # round(inf, n) actually doesn't raise on its own — safe_round is a
        # no-op passthrough for it either way, covered for completeness.
        self.assertEqual(safe_round(float("inf"), 1), float("inf"))


class ConsolidatedNumericOverflowTest(unittest.TestCase):
    """T-063 gate round 2 (2nd pass, 🔴C): three files carried their own
    private copy of `numeric()`/`numeric_value()`, none catching
    `OverflowError` — `validate-config.py:249` (`numeric_value`),
    `growth-roadmap.py:140` (`numeric`), `triggers-eval.py:141` (`_num`).
    `10**400` (a Python int too large to represent as `float`) crashed all
    three with a traceback, on `origin/main` and still after T-063's first
    round (which only patched `coerce_int`/`coerce_float`/the shared
    `numeric()`, not these three independent copies — "по адресам, а не по
    классу", again). Fixed by DELETING the three copies and importing the
    shared, already-`OverflowError`-safe `seo_cycle_core.config.numeric()`
    instead — closes the class instead of patching a fourth copy."""

    def test_validate_config_check_governance_survives_overflow(self) -> None:
        cfg = {"governance": {"token_policy": {"max_context_input_tokens_per_phase": 10**400}}}
        checklist: list = []
        warnings: list = []
        # Must not raise; the specific outcome (warned or not) isn't the point.
        validate_config.check_governance(cfg, pathlib.Path("."), checklist, warnings)

    def test_growth_roadmap_governance_caps_survives_overflow(self) -> None:
        cfg = {"governance": {"budget_policy": {"monthly_paid_api_usd_cap": 10**400}}}
        caps = growth_roadmap.governance_caps(cfg, {})
        self.assertEqual(caps["monthly_paid_api_usd_cap"], 0)  # numeric()'s own default

    def test_triggers_eval_no_longer_has_a_private_numeric_copy(self) -> None:
        """Structural check for the consolidation itself, not just the
        symptom: `numeric` in this module must BE the canonical one, not a
        same-named local redefinition that happens to also work."""
        self.assertIs(triggers_eval.numeric, numeric)

    def test_triggers_eval_enrich_queries_survives_overflow(self) -> None:
        snapshot = {"queries": [{"query": "q", "url": "/x", "position": 10**400, "impressions": 100, "ctr": 0.1}]}
        triggers_eval.enrich_queries(snapshot)  # must not raise


class TriggersEvalTypeMismatchTest(unittest.TestCase):
    """scripts/triggers-eval.py — comparing a numeric `actual` against a
    non-numeric `expected` threshold (T-063 gate round 2, 🔴C): a
    non-numeric threshold in the trigger config (`config/triggers.yaml` or
    a project's `seo-triggers.yaml`, via `monitoring.triggers_file`) left
    `expected_n` a raw string while `actual_n` was a float — comparing them
    with `<`/`>`/etc. raised `TypeError`, crashing the whole run."""

    def test_numeric_actual_vs_non_numeric_threshold_does_not_raise(self) -> None:
        # `!=` is excluded on purpose: Python's `!=` never raises TypeError
        # for mismatched types (it falls back to "not equal" => True) — the
        # crash this test targets is specific to ordering operators.
        for op in ("<", "<=", ">", ">="):
            with self.subTest(op=op):
                result = triggers_eval.eval_condition({"clicks": 50}, f"clicks {op} unknown_value")
                self.assertFalse(result)

    def test_equality_still_works_normally(self) -> None:
        self.assertTrue(triggers_eval.eval_condition({"clicks": 50}, "clicks == 50"))
        self.assertFalse(triggers_eval.eval_condition({"clicks": 50}, "clicks == 51"))

    def test_numeric_comparison_still_works_normally(self) -> None:
        self.assertTrue(triggers_eval.eval_condition({"clicks": 50}, "clicks < 100"))
        self.assertFalse(triggers_eval.eval_condition({"clicks": 50}, "clicks > 100"))


class BudgetMixPlannerZeroStepTest(unittest.TestCase):
    """scripts/budget-mix-planner.py:94 — `kpi.budget.ppc_step: 0` (a
    plausible human config value; the sibling `cost_per_article` two lines
    above already guards the same way) divided by zero building the PPC
    lot table (T-063 gate round 2, 🔴C)."""

    def test_zero_ppc_step_does_not_raise(self) -> None:
        ads = {"campaigns": [{"campaign_id": "1", "name": "c1", "platform": "yandex", "cpa": 100}]}
        lots = budget_mix_planner.ppc_lots(ads, ppc_step=0, conversion=0.02, diminishing_factor=0.85)
        self.assertTrue(all(lot["leads_per_1000"] == 0 for lot in lots))


class KpiContractHugeYearTest(unittest.TestCase):
    """scripts/kpi-contract.py::parse_month() — `dt.date()` takes a C
    `long` for the year; `int(year)` itself never raises on a huge literal
    (Python ints are arbitrary precision), but `dt.date(huge, ...)` does
    (T-063 gate round 2, 🔴C: `kpi.start: "99999999999999-01"`)."""

    def test_huge_year_falls_back_to_default(self) -> None:
        fallback = dt.date(2026, 1, 1)
        result = kpi_contract.parse_month("99999999999999-01", fallback)
        self.assertEqual(result, fallback)

    def test_normal_month_still_parses(self) -> None:
        fallback = dt.date(2026, 1, 1)
        result = kpi_contract.parse_month("2027-03", fallback)
        self.assertEqual(result, dt.date(2027, 3, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
