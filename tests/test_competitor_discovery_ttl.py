#!/usr/bin/env python3
"""R2-4 (независимый гейт, круг 3): competitor-discovery.py не был заявлен в
таблице класса T-066, хотя ходит в тот же api.keys.so, что keyso-fetch.py и
keyso-save.py. `--ttl` был голым `type=float` — тот же дефект R-4, который
круг 2 уже закрыл у трёх других клиентов: `--ttl nan` проходит парсинг, и
условие свежести кэша `(now - mtime) / 86400 <= nan` всегда False, то есть
каждый прогон тратит квоту Keys.so заново вместо использования кэша.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("competitor_discovery", SCRIPTS / "competitor-discovery.py")
cd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cd)


class TtlArgWiringTest(unittest.TestCase):
    """Мутация: замени `type=ttl_arg` обратно на `type=float` в
    build_parser() — test_nan_is_rejected_by_real_parser обязан покраснеть."""

    def test_nan_is_rejected_by_real_parser(self) -> None:
        parser = cd.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["kw", "--ttl", "nan"])

    def test_inf_is_rejected_by_real_parser(self) -> None:
        parser = cd.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["kw", "--ttl", "inf"])

    def test_negative_is_rejected_by_real_parser(self) -> None:
        parser = cd.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["kw", "--ttl", "-1"])

    def test_ordinary_value_parses(self) -> None:
        parser = cd.build_parser()
        args = parser.parse_args(["kw", "--ttl", "60"])
        self.assertEqual(args.ttl, 60.0)


if __name__ == "__main__":
    unittest.main()
