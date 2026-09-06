#!/usr/bin/env python3
"""T-066 R-2 (full class re-walk): serpstat-fetch.py's --min-credits was a
bare type=int — a negative value makes `left < min_credits` never fire
(remaining credits from a real API is always >= 0), disabling the stop the
same way F-11 disabled --budget elsewhere, just on a live-preflight stop
instead of a file-based one.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("serpstat_fetch", SCRIPTS / "serpstat-fetch.py")
serpstat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serpstat)


class MinCreditsArgTest(unittest.TestCase):
    def test_negative_is_rejected(self) -> None:
        with self.assertRaises(serpstat.argparse.ArgumentTypeError):
            serpstat.nonneg_int_arg("-1")

    def test_non_integer_is_rejected(self) -> None:
        with self.assertRaises(serpstat.argparse.ArgumentTypeError):
            serpstat.nonneg_int_arg("abc")

    def test_ordinary_value_parses(self) -> None:
        self.assertEqual(serpstat.nonneg_int_arg("50"), 50)

    def test_zero_is_allowed(self) -> None:
        self.assertEqual(serpstat.nonneg_int_arg("0"), 0)


if __name__ == "__main__":
    unittest.main()
