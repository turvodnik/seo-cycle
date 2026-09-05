#!/usr/bin/env python3
"""T-053: `coerce_int()` must not let a garbage config value crash the tool.

T-052 reviewer (round 3) flagged an unguarded `int(...)` on an unvalidated
config value at two sites introduced/touched by T-052:
`scripts/seo_cycle_cli.py:170` (`monitoring.snapshot_max_age_days`) and
`scripts/pulse.py:307` (`pulse.days`, pre-existing). Before this fix, a
config like `pulse: {days: "soon"}` raised `ValueError` with a full
traceback instead of falling back to the default. This test proves the
negative control: garbage in, no crash, sane fallback, warning on stderr —
at the shared helper AND at both call sites end-to-end via `doctor`.
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
