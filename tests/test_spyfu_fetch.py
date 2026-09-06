#!/usr/bin/env python3
"""Tests for spyfu-fetch.py (F-12/F-13, T-066: migration onto the shared
scripts/seo_cycle_core/usage_ledger.py money stop).

Before this ticket, spyfu-fetch.py kept its own, unguarded copy of the same
usage ledger dataforseo-fetch.py has: no value validation on read, a compare
and an addition that a NaN/Infinity/negative spend makes meaningless or
permanently poisons, a non-atomic write, no lock against concurrent runs, and
--budget not validated at all. Every test here targets one of those places
with a real mutation, not a description of the source.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("spyfu_fetch", SCRIPTS / "spyfu-fetch.py")
spyfu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spyfu)

_find_config_patcher: mock._patch | None = None


def setUpModule() -> None:
    """Герметичность: effective_budget() зовёт find_config(), который иначе
    ищет seo-cycle.yaml от реального cwd процесса unittest."""
    global _find_config_patcher
    _find_config_patcher = mock.patch.object(spyfu, "find_config", return_value=None)
    _find_config_patcher.start()


def tearDownModule() -> None:
    if _find_config_patcher is not None:
        _find_config_patcher.stop()


def domain_stats_response(n_rows: int = 1) -> dict:
    return {"domain": "example.com", "results": [{"searchYear": 2026, "searchMonth": 1}] * n_rows}


def error_response() -> dict:
    return {"status": 400, "errors": "bad request"}


class BudgetArgTest(unittest.TestCase):
    """F-11/F-12: --budget был голым type=float здесь тоже — nan/inf/-1
    отключали стоп ровно как в dataforseo-fetch.py до T-059."""

    def test_nan_is_rejected_at_parse_time(self) -> None:
        with mock.patch.object(sys, "argv", ["spyfu-fetch.py", "usage", "--budget", "nan"]):
            with self.assertRaises(SystemExit):
                spyfu.main()

    def test_inf_is_rejected_at_parse_time(self) -> None:
        with mock.patch.object(sys, "argv", ["spyfu-fetch.py", "usage", "--budget", "inf"]):
            with self.assertRaises(SystemExit):
                spyfu.main()

    def test_negative_is_rejected_at_parse_time(self) -> None:
        with mock.patch.object(sys, "argv", ["spyfu-fetch.py", "usage", "--budget", "-1"]):
            with self.assertRaises(SystemExit):
                spyfu.main()


class RunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-spyfu-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = argparse_namespace(out=str(self.tmp), budget=40.0, ttl=30.0, force=False)

    def test_cost_is_accumulated_in_usage_ledger(self) -> None:
        with mock.patch.object(spyfu, "call", return_value=domain_stats_response(2)):
            spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["rows"], 2)
        self.assertAlmostEqual(usage["spent_usd"], 2 / 1000.0 * 0.50)

    def test_second_identical_call_is_served_from_cache(self) -> None:
        params = {"domain": "x"}
        with mock.patch.object(spyfu, "call", return_value=domain_stats_response(1)) as called:
            spyfu.run("b64", "some/path", 0.50, params, self.args, lambda r: None)
            spyfu.run("b64", "some/path", 0.50, params, self.args, lambda r: None)
            self.assertEqual(called.call_count, 1)

    def test_budget_guard_stops_before_paid_call(self) -> None:
        spyfu.save_usage(self.tmp, {"month": spyfu.load_usage(self.tmp)["month"],
                                     "spent_usd": 99.0, "rows": 1000})
        with mock.patch.object(spyfu, "call") as called:
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "y"}, self.args, lambda r: None)
            called.assert_not_called()

    def test_force_overrides_budget_guard(self) -> None:
        spyfu.save_usage(self.tmp, {"month": spyfu.load_usage(self.tmp)["month"],
                                     "spent_usd": 99.0, "rows": 1000})
        self.args.force = True
        with mock.patch.object(spyfu, "call", return_value=domain_stats_response(1)):
            spyfu.run("b64", "some/path", 0.50, {"domain": "y"}, self.args, lambda r: None)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertGreater(usage["spent_usd"], 99.0)

    def test_api_error_status_exits(self) -> None:
        with mock.patch.object(spyfu, "call", return_value=error_response()):
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "z"}, self.args, lambda r: None)

    def test_api_error_status_still_records_the_call_in_ledger(self) -> None:
        """F-13: раньше запись расхода была только на успешном пути; теперь она
        происходит в любом случае, прежде чем run() выйдет через sys.exit."""
        with mock.patch.object(spyfu, "call", return_value=error_response()):
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "z"}, self.args, lambda r: None)
        self.assertTrue((self.tmp / "_usage.json").exists(),
                         "запись должна произойти до sys.exit, а не после")


class LedgerCorruptionTest(unittest.TestCase):
    """F-12: голое чтение файла учёта без проверки значения — NaN/Infinity/
    отрицательный spend раньше проходили молча."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-spyfu-corrupt-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = argparse_namespace(out=str(self.tmp), budget=40.0, ttl=30.0, force=False)

    def test_nan_spent_usd_raises_ledger_error(self) -> None:
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": spyfu.current_month(), "spent_usd": float("nan"), "rows": 1}),
            encoding="utf-8")
        with self.assertRaises(spyfu.UsageLedgerError):
            spyfu.load_usage(self.tmp)

    def test_nan_spent_usd_blocks_paid_call_without_force(self) -> None:
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": spyfu.current_month(), "spent_usd": float("nan"), "rows": 1}),
            encoding="utf-8")
        with mock.patch.object(spyfu, "call") as called:
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
            called.assert_not_called()

    def test_corrupt_json_raises_ledger_error(self) -> None:
        (self.tmp / "_usage.json").write_text("{ не json", encoding="utf-8")
        with self.assertRaises(spyfu.UsageLedgerError):
            spyfu.load_usage(self.tmp)

    def test_corrupt_usage_file_with_force_resets_and_proceeds(self) -> None:
        (self.tmp / "_usage.json").write_text("{ битый файл", encoding="utf-8")
        self.args.force = True
        with mock.patch.object(spyfu, "call", return_value=domain_stats_response(1)):
            spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(usage["spent_usd"], 1 / 1000.0 * 0.50)


class SaveUsageAtomicityTest(unittest.TestCase):
    """F-12: старая запись была `write_text` напрямую в целевой файл — обрыв
    процесса на середине записи оставляет полуфайл. Теперь — общий модуль
    (temp + os.replace)."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-spyfu-atomic-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_write_failure_leaves_no_half_file(self) -> None:
        spyfu.save_usage(self.tmp, {"month": spyfu.current_month(), "spent_usd": 1.0, "rows": 1})
        with mock.patch("json.dump", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                spyfu.save_usage(self.tmp, {"month": spyfu.current_month(), "spent_usd": 2.0, "rows": 2})
        # исходный файл не тронут (os.replace ни разу не вызывался)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["spent_usd"], 1.0)
        leftovers = [p for p in self.tmp.iterdir() if p.name.startswith(".")]
        self.assertEqual(leftovers, [], "временный файл должен быть удалён при ошибке записи")


class ConcurrencyTest(unittest.TestCase):
    """F-12: без блокировки два параллельных run() читают один и тот же старый
    _usage.json, и последняя запись побеждает, теряя чужой расход. Мутация
    «убрать usage_lock» должна ронять именно этот тест, не пройти его случайно —
    поэтому оба потока реально пересекаются внутри call(), а не идут по очереди."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-spyfu-lock-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_parallel_run_does_not_lose_either_spend(self) -> None:
        entered_first = threading.Event()
        release_first = threading.Event()
        call_count = {"n": 0}
        count_lock = threading.Lock()

        def shared_call(_b64, _path, _params):
            with count_lock:
                call_count["n"] += 1
                is_first = call_count["n"] == 1
            if is_first:
                entered_first.set()
                # держим поток внутри критической секции — второй поток должен
                # встать в очередь на flock(), а не прочитать тот же старый файл.
                release_first.wait(timeout=2)
            return domain_stats_response(1)

        original_call = spyfu.call
        spyfu.call = shared_call
        self.addCleanup(setattr, spyfu, "call", original_call)

        errors: list[BaseException] = []

        def worker(idx: int) -> None:
            try:
                args = argparse_namespace(out=str(self.tmp), budget=40.0, ttl=30.0, force=False)
                spyfu.run("b64", "some/path", 0.50, {"domain": f"d{idx}"}, args, lambda r: None)
            except BaseException as e:  # noqa: BLE001 - тест должен увидеть любую ошибку потока
                errors.append(e)

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))
        t1.start()
        self.assertTrue(entered_first.wait(timeout=2), "поток 1 должен войти в call() до старта потока 2")
        t2.start()
        time.sleep(0.15)
        release_first.set()
        t1.join(timeout=3)
        t2.join(timeout=3)

        self.assertFalse(errors, f"потоки упали: {errors}")
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["rows"], 2, "без блокировки один из двух расходов "
                                            "был бы потерян — победила бы последняя запись")


def argparse_namespace(**kwargs):
    import argparse
    return argparse.Namespace(**kwargs)


if __name__ == "__main__":
    unittest.main()
