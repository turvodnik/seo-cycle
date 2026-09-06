#!/usr/bin/env python3
"""Direct tests for scripts/seo_cycle_core/usage_ledger.py — the shared
money/quota-stop module all paid clients (T-066) now wire around.

These test the primitives themselves, independent of any one client, so a
regression here is caught before it reaches every client that imports it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core import usage_ledger as ul  # noqa: E402


class FiniteNonnegTest(unittest.TestCase):
    def test_normal_float_is_ok(self) -> None:
        self.assertTrue(ul.finite_nonneg(1.5))

    def test_zero_is_ok(self) -> None:
        self.assertTrue(ul.finite_nonneg(0))

    def test_nan_is_rejected(self) -> None:
        self.assertFalse(ul.finite_nonneg(float("nan")))

    def test_inf_is_rejected(self) -> None:
        self.assertFalse(ul.finite_nonneg(float("inf")))

    def test_negative_inf_is_rejected(self) -> None:
        self.assertFalse(ul.finite_nonneg(float("-inf")))

    def test_negative_number_is_rejected(self) -> None:
        self.assertFalse(ul.finite_nonneg(-0.01))

    def test_bool_is_rejected(self) -> None:
        """`isinstance(True, int)` is True in Python — must not silently pass."""
        self.assertFalse(ul.finite_nonneg(True))

    def test_string_is_rejected(self) -> None:
        self.assertFalse(ul.finite_nonneg("1.0"))

    def test_none_is_rejected(self) -> None:
        self.assertFalse(ul.finite_nonneg(None))


class BudgetArgTest(unittest.TestCase):
    def test_ordinary_value_parses(self) -> None:
        self.assertEqual(ul.budget_arg("12.5"), 12.5)

    def test_zero_is_allowed(self) -> None:
        self.assertEqual(ul.budget_arg("0"), 0.0)

    def test_nan_is_rejected(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            ul.budget_arg("nan")

    def test_inf_is_rejected(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            ul.budget_arg("inf")

    def test_negative_inf_is_rejected(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            ul.budget_arg("-inf")

    def test_negative_is_rejected(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            ul.budget_arg("-1")

    def test_non_numeric_is_rejected(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            ul.budget_arg("много")


class EffectiveBudgetTest(unittest.TestCase):
    def test_no_cap_returns_cli_budget(self) -> None:
        self.assertEqual(ul.effective_budget(5.0, None), 5.0)

    def test_lower_cap_wins(self) -> None:
        self.assertEqual(ul.effective_budget(5.0, 2.0), 2.0)

    def test_higher_cap_does_not_raise_cli_budget(self) -> None:
        self.assertEqual(ul.effective_budget(5.0, 100.0), 5.0)

    def test_nan_cap_raises_value_error(self) -> None:
        """F-11's config-side counterpart: a cap that passed a type check but
        cannot do money arithmetic must not silently fall back to cli_budget
        (that would look identical to "no cap configured")."""
        with self.assertRaises(ValueError):
            ul.effective_budget(5.0, float("nan"))

    def test_negative_cap_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            ul.effective_budget(5.0, -1.0)


class LoadSaveUsageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-ul-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_missing_file_is_empty_state(self) -> None:
        u = ul.load_usage(self.tmp, ("spent_usd",))
        self.assertEqual(u["spent_usd"], 0.0)
        self.assertEqual(u["month"], ul.current_month())

    def test_round_trip(self) -> None:
        data = {"month": ul.current_month(), "spent_usd": 3.5}
        ul.save_usage(self.tmp, data)
        got = ul.load_usage(self.tmp, ("spent_usd",))
        self.assertEqual(got["spent_usd"], 3.5)

    def test_stale_month_resets_to_empty(self) -> None:
        ul.save_usage(self.tmp, {"month": "2000-01", "spent_usd": 42.0})
        got = ul.load_usage(self.tmp, ("spent_usd",))
        self.assertEqual(got["spent_usd"], 0.0)

    def test_nan_field_raises_ledger_error(self) -> None:
        ul.save_usage(self.tmp, {"month": ul.current_month(), "spent_usd": float("nan")})
        with self.assertRaises(ul.UsageLedgerError):
            ul.load_usage(self.tmp, ("spent_usd",))

    def test_corrupt_json_raises_ledger_error(self) -> None:
        (self.tmp / "_usage.json").write_text("{ не json", encoding="utf-8")
        with self.assertRaises(ul.UsageLedgerError):
            ul.load_usage(self.tmp, ("spent_usd",))

    def test_garbled_month_raises_ledger_error(self) -> None:
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": "not-a-month", "spent_usd": 1.0}), encoding="utf-8")
        with self.assertRaises(ul.UsageLedgerError):
            ul.load_usage(self.tmp, ("spent_usd",))

    def test_write_failure_removes_temp_file(self) -> None:
        from unittest import mock
        with mock.patch("json.dump", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                ul.save_usage(self.tmp, {"month": ul.current_month(), "spent_usd": 1.0})
        leftovers = list(self.tmp.iterdir())
        self.assertEqual(leftovers, [], "временный файл должен быть удалён при ошибке записи")

    def test_write_is_all_or_nothing_visible_to_a_reader(self) -> None:
        """Атомарность: пока идёт запись временного файла, целевой файл,
        который видит наблюдатель, остаётся старым и целым — не пустым, не
        усечённым, а новое значение появляется только после os.replace."""
        ul.save_usage(self.tmp, {"month": ul.current_month(), "spent_usd": 1.0})
        from unittest import mock

        seen_during_write = []
        real_json_dump = json.dump

        def spy_dump(obj, fh, **kwargs):
            # в момент записи временного файла целевой файл ещё старый и цел
            seen_during_write.append(json.loads((self.tmp / "_usage.json").read_text()))
            return real_json_dump(obj, fh, **kwargs)

        with mock.patch("json.dump", side_effect=spy_dump):
            ul.save_usage(self.tmp, {"month": ul.current_month(), "spent_usd": 2.0})
        self.assertEqual(seen_during_write[0]["spent_usd"], 1.0,
                          "во время записи временного файла целевой файл должен оставаться старым")
        final = json.loads((self.tmp / "_usage.json").read_text())
        self.assertEqual(final["spent_usd"], 2.0)


if __name__ == "__main__":
    unittest.main()
