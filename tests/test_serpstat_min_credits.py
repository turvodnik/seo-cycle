#!/usr/bin/env python3
"""T-066 R-2 (full class re-walk): serpstat-fetch.py's --min-credits was a
bare type=int — a negative value makes `left < min_credits` never fire
(remaining credits from a real API is always >= 0), disabling the stop the
same way F-11 disabled --budget elsewhere, just on a live-preflight stop
instead of a file-based one.

R2-6 (независимый гейт, круг 3): предыдущая версия этого файла вызывала
`serpstat.nonneg_int_arg(...)` НАПРЯМУЮ — отцепление валидатора от флага
(`type=int` вместо `type=nonneg_int_arg` в build_parser()) оставляло сюиту
зелёной, потому что ни один тест не проходил через реальный argparse.
Теперь — только через `build_parser().parse_args([...])`.
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


class MinCreditsWiringTest(unittest.TestCase):
    """Мутация: замени `type=nonneg_int_arg` на `type=int` в build_parser()
    (реальный код) — test_negative_is_rejected_by_real_parser обязан
    покраснеть (argparse примет -1 без вопросов)."""

    def test_negative_is_rejected_by_real_parser(self) -> None:
        parser = serpstat.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["stats", "--min-credits", "-1"])

    def test_non_integer_is_rejected_by_real_parser(self) -> None:
        parser = serpstat.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["stats", "--min-credits", "abc"])

    def test_ordinary_value_parses_through_real_parser(self) -> None:
        parser = serpstat.build_parser()
        args = parser.parse_args(["stats", "--min-credits", "50"])
        self.assertEqual(args.min_credits, 50)

    def test_zero_is_allowed_through_real_parser(self) -> None:
        parser = serpstat.build_parser()
        args = parser.parse_args(["stats", "--min-credits", "0"])
        self.assertEqual(args.min_credits, 0)

    def test_default_value_is_50(self) -> None:
        parser = serpstat.build_parser()
        args = parser.parse_args(["stats"])
        self.assertEqual(args.min_credits, 50)


class NonnegIntArgUnitTest(unittest.TestCase):
    """Прямые тесты чистой функции — полезны, но НЕ доказывают, что флаг ей
    пользуется (см. класс выше)."""

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
