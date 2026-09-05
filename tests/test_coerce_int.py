#!/usr/bin/env python3
"""T-053: `coerce_int()` must not let a garbage config value crash the tool.

T-052 reviewer (round 3) flagged an unguarded `int(...)` on an unvalidated
config value at two sites introduced/touched by T-052:
`scripts/seo_cycle_cli.py:170` (`monitoring.snapshot_max_age_days`) and
`scripts/pulse.py:309` (`pulse.days`, pre-existing). Before this fix, a
config like `pulse: {days: "soon"}` raised `ValueError` with a full
traceback instead of falling back to the default. This test proves the
negative control: garbage in, no crash, sane fallback, warning on stderr —
at the shared helper AND at both call sites end-to-end via `doctor`.

T-053 review round 1 found a THIRD instance of the same pattern in the same
call chain (`pulse_project` -> `build_pulse`), 77 lines above the one
already fixed: `scripts/pulse.py:232` (`pulse.stale_after_days`) — the
`coerce_int` warning at line 309 printed fine and `pulse` still died with a
traceback four lines later. `PulseSurvivesBadStaleAfterConfigTest` below is
the reviewer's own reproduction, end-to-end through the real script.
"""

from __future__ import annotations

import io
import pathlib
import subprocess
import sys
import unittest
from contextlib import redirect_stderr

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.config import coerce_int  # noqa: E402


class CoerceIntUnitTest(unittest.TestCase):
    def test_valid_string_int(self) -> None:
        self.assertEqual(coerce_int("7", 14), 7)

    def test_valid_native_int(self) -> None:
        self.assertEqual(coerce_int(3, 14), 3)

    def test_none_falls_back_to_default(self) -> None:
        self.assertEqual(coerce_int(None, 14), 14)

    def test_falsy_zero_falls_back_to_default(self) -> None:
        # Preserves the pre-existing `int(value or default)` semantics at
        # both original call sites — 0 was already treated as "unset", not
        # as a valid override. Not introduced by this fix; not to be
        # "corrected" without a human decision (T-053 §Ограничения: no
        # silent behavior changes beyond what the ticket asks for).
        self.assertEqual(coerce_int(0, 14), 14)

    def test_garbage_string_does_not_raise_and_warns(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = coerce_int("soon", 14, name="pulse.days")
        self.assertEqual(result, 14)
        self.assertIn("pulse.days", stderr.getvalue())
        self.assertIn("soon", stderr.getvalue())

    def test_garbage_type_does_not_raise(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = coerce_int({"nested": "dict"}, 7, name="monitoring.snapshot_max_age_days")
        self.assertEqual(result, 7)
        self.assertIn("monitoring.snapshot_max_age_days", stderr.getvalue())


class CoerceIntFalsyToDefaultFlagTest(unittest.TestCase):
    """T-063 review: `int(value or default)` is only correct where the
    ORIGINAL call site also had `or default` — 9 of the 19 T-063 sites
    didn't, and there an explicit `0` was already a legitimate,
    meaningfully-different-from-default value (e.g. `max_raw_rows_loaded: 0`
    = "load nothing") that must keep surviving as `0`. `falsy_to_default`
    is the switch: default `True` keeps the historical coerce_int()
    behavior (this class's sibling test above), `False` preserves the
    no-`or` original."""

    def test_default_true_still_treats_zero_as_unset(self) -> None:
        self.assertEqual(coerce_int(0, 14), 14)

    def test_false_preserves_explicit_zero(self) -> None:
        self.assertEqual(coerce_int(0, 14, falsy_to_default=False), 0)

    def test_false_still_falls_back_on_none(self) -> None:
        self.assertEqual(coerce_int(None, 14, falsy_to_default=False), 14)

    def test_false_still_warns_and_falls_back_on_garbage(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = coerce_int("garbage", 14, name="ads.cache_ttl_hours", falsy_to_default=False)
        self.assertEqual(result, 14)
        self.assertIn("ads.cache_ttl_hours", stderr.getvalue())


class DoctorSurvivesBadMaxAgeConfigTest(unittest.TestCase):
    """End-to-end: `seo-cycle doctor` (via seo_cycle_cli.py status/doctor)
    must not crash when `monitoring.snapshot_max_age_days` is garbage."""

    def test_status_does_not_crash_on_garbage_max_age(self) -> None:
        import shutil
        import tempfile

        tmp = pathlib.Path(tempfile.mkdtemp(prefix="coerce-int-doctor-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: X\n  domain: x.test\nmonitoring:\n  snapshot_max_age_days: not-a-number\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "seo_cycle_cli.py"), "--project", str(tmp), "status"],
            cwd=tmp, text=True, capture_output=True, check=False,
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stderr)


class PulseSurvivesBadStaleAfterConfigTest(unittest.TestCase):
    """Reviewer's own reproduction for the third occurrence
    (`pulse.stale_after_days`, `scripts/pulse.py:232`) — garbage values that
    must be rejected without a traceback, and two that must pass through as
    valid (`true` == 1, a numeric-looking string with whitespace)."""

    def _run_pulse(self, stale_after_value: str) -> subprocess.CompletedProcess:
        import shutil
        import tempfile

        tmp = pathlib.Path(tempfile.mkdtemp(prefix="coerce-int-pulse-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text(
            "project: {name: X, domain: x.test}\n"
            "region_profile: ru\n"
            "pulse:\n"
            "  days: 14\n"
            f"  stale_after_days: {stale_after_value}\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "pulse.py"), str(tmp / "seo-cycle.yaml"), "--skip-fetch"],
            cwd=tmp, text=True, capture_output=True, check=False,
        )

    def test_garbage_values_do_not_raise(self) -> None:
        for bad in ("not-a-number", '"3.5"', "[1]", "{a: 1}"):
            with self.subTest(value=bad):
                proc = self._run_pulse(bad)
                self.assertNotIn("Traceback (most recent call last)", proc.stderr)
                self.assertIn("WARNING: bad integer config value (pulse.stale_after_days)", proc.stderr)

    def test_valid_looking_values_pass_through(self) -> None:
        for ok in ("true", '" 12 "'):
            with self.subTest(value=ok):
                proc = self._run_pulse(ok)
                self.assertNotIn("Traceback (most recent call last)", proc.stderr)
                self.assertNotIn("WARNING: bad integer config value", proc.stderr)


class PulseSurvivesBadDropAlertConfigTest(unittest.TestCase):
    """T-063: `scripts/pulse.py:234`, `pulse.drop_alert_pct` — the float
    twin of `pulse.stale_after_days` above, found by the T-053 reviewer
    (of T-063's predecessor ticket) sweeping the tree for BOTH `int(` and
    `float(` conversions of config values, not just the integer half."""

    def _run_pulse(self, drop_alert_value: str) -> subprocess.CompletedProcess:
        import shutil
        import tempfile

        tmp = pathlib.Path(tempfile.mkdtemp(prefix="coerce-float-pulse-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text(
            "project: {name: X, domain: x.test}\n"
            "region_profile: ru\n"
            "pulse:\n"
            "  days: 14\n"
            f"  drop_alert_pct: {drop_alert_value}\n",
            encoding="utf-8",
        )
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "pulse.py"), str(tmp / "seo-cycle.yaml"), "--skip-fetch"],
            cwd=tmp, text=True, capture_output=True, check=False,
        )

    def test_garbage_values_do_not_raise(self) -> None:
        for bad in ("not-a-number", '"soon"', "[1]", "{a: 1}"):
            with self.subTest(value=bad):
                proc = self._run_pulse(bad)
                self.assertNotIn("Traceback (most recent call last)", proc.stderr)
                self.assertIn("WARNING: bad numeric config value (pulse.drop_alert_pct)", proc.stderr)

    def test_valid_looking_values_pass_through(self) -> None:
        for ok in ("7.5", '" 12 "'):
            with self.subTest(value=ok):
                proc = self._run_pulse(ok)
                self.assertNotIn("Traceback (most recent call last)", proc.stderr)
                self.assertNotIn("WARNING: bad numeric config value", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
