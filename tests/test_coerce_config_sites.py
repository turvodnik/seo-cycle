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

import importlib.util
import io
import json
import math
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

from seo_cycle_core.config import coerce_float  # noqa: E402
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


class SeoForecastCtrCurveTest(unittest.TestCase):
    """scripts/seo-forecast.py::load_ctr_curve() — `kpi.ctr_curve` override
    entries. T-063 gate round 2: `curve[int(key)] = float(value)` alone
    never raised on `.inf` (YAML parses it straight into the Python float
    `inf`, no string involved) — the poisoned CTR then propagates through
    `scenario_clicks()`'s running total and crashes a LATER bare
    `round(total)` in `build_report()`, nowhere near this function. Found
    by tracing data flow (not grepping for the literal call), per the
    gate's own direction."""

    def test_infinite_override_value_is_skipped_not_stored(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            curve = seo_forecast.load_ctr_curve({"kpi": {"ctr_curve": {1: float("inf")}}})
        # Malformed entries are SKIPPED (pre-existing "can't parse -> ignore
        # this one entry" semantics), not substituted with a default value —
        # the default curve's own bucket-1 CTR must survive untouched.
        self.assertTrue(math.isfinite(curve[1]))
        self.assertEqual(curve[1], seo_forecast.DEFAULT_CTR_CURVE[1])

    def test_nan_override_value_is_skipped(self) -> None:
        curve = seo_forecast.load_ctr_curve({"kpi": {"ctr_curve": {1: float("nan")}}})
        self.assertTrue(math.isfinite(curve[1]))

    def test_garbage_override_value_is_skipped(self) -> None:
        curve = seo_forecast.load_ctr_curve({"kpi": {"ctr_curve": {1: "garbage"}}})
        self.assertTrue(math.isfinite(curve[1]))

    def test_infinite_ctr_curve_does_not_crash_build_report(self) -> None:
        """End-to-end: the reviewer's own reproduction shape — a poisoned
        CTR curve entry must not crash `build_report()`'s later
        `round(total)` calls."""
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        package = root / "seo" / "research-package"
        package.mkdir(parents=True)
        (package / "semantic-core.csv").write_text(
            "keyword,frequency,cluster_id\nкупить вагонку,1000,vagonka\n", encoding="utf-8",
        )
        cfg = {"kpi": {"ctr_curve": {1: float("inf")}}}
        report = seo_forecast.build_report(root, cfg)
        self.assertIsInstance(report["scenarios"]["current"]["monthly_clicks"], (int, float))
        self.assertTrue(math.isfinite(report["scenarios"]["current"]["monthly_clicks"]))


class KpiContractToleranceTest(unittest.TestCase):
    """scripts/kpi-contract.py:181-182 — `kpi.tolerance_pct` and
    `kpi.lead_conversion_rate`. T-063 gate round 2, 15th/5th-file finding:
    `numeric()` alone never raises, but `tolerance` feeds a later BARE
    `round(tolerance * 100)` (no ndigits) when building the report
    `contract` — that raises `OverflowError` on `.inf` (parsed by YAML
    straight into the Python float `inf`, no string involved) and
    `ValueError` on `.nan`, arbitrarily far downstream from where the
    garbage config value entered. Closed by switching to `coerce_float()`,
    which (as of this same gate round) rejects non-finite RESULTS too, not
    just non-numeric inputs — see `CoerceFloatNonFiniteTest` below."""

    def test_infinite_tolerance_pct_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"tolerance_pct": float("inf")}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = kpi_contract.build_report(root, cfg)
        self.assertEqual(report["contract"]["tolerance_pct"], 20)
        self.assertIn("kpi.tolerance_pct", stderr.getvalue())

    def test_nan_tolerance_pct_does_not_raise(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg = {"kpi": {"tolerance_pct": float("nan")}}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            report = kpi_contract.build_report(root, cfg)
        self.assertEqual(report["contract"]["tolerance_pct"], 20)
        self.assertIn("kpi.tolerance_pct", stderr.getvalue())

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


class CoerceFloatNonFiniteTest(unittest.TestCase):
    """T-063 gate round 2: `coerce_float()` must reject `inf`/`-inf`/`nan`
    RESULTS as garbage too, not just non-numeric inputs — `float("inf")`
    itself never raises, but a caller doing further arithmetic and then a
    bare `round(...)`/`int(...)` (not going through `coerce_int()`) on the
    result crashes anyway, arbitrarily far from this coercion point
    (`kpi-contract.py`'s `round(tolerance * 100)` is the reviewer's own
    reproduction — see `KpiContractToleranceTest` above)."""

    def test_positive_infinity_is_rejected(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = coerce_float(float("inf"), 5, name="kpi.tolerance_pct")
        self.assertEqual(result, 5)
        self.assertIn("kpi.tolerance_pct", stderr.getvalue())

    def test_negative_infinity_is_rejected(self) -> None:
        result = coerce_float(float("-inf"), 5)
        self.assertEqual(result, 5)

    def test_nan_is_rejected(self) -> None:
        result = coerce_float(float("nan"), 5)
        self.assertEqual(result, 5)

    def test_infinity_is_rejected_with_falsy_to_default_false(self) -> None:
        result = coerce_float(float("inf"), 5, falsy_to_default=False)
        self.assertEqual(result, 5)

    def test_finite_values_still_pass_through(self) -> None:
        self.assertEqual(coerce_float(3.5, 5), 3.5)
        self.assertEqual(coerce_float(0, 5, falsy_to_default=False), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
