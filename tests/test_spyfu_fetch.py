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


class CpmAndTtlArgTest(unittest.TestCase):
    """R-3/R-4 (гейт круга 2): --cpm и --ttl оставались голым type=float —
    --cpm nan травит _usage.json через cost=rows/1000*cpm, --ttl nan делает
    кэш вечным промахом (F-11 называл --ttl прямо)."""

    def test_cpm_nan_is_rejected_at_parse_time(self) -> None:
        with mock.patch.object(sys, "argv", ["spyfu-fetch.py", "raw", "some/path", "--cpm", "nan"]):
            with self.assertRaises(SystemExit):
                spyfu.main()

    def test_cpm_negative_is_rejected_at_parse_time(self) -> None:
        with mock.patch.object(sys, "argv", ["spyfu-fetch.py", "raw", "some/path", "--cpm", "-1"]):
            with self.assertRaises(SystemExit):
                spyfu.main()

    def test_ttl_nan_is_rejected_at_parse_time(self) -> None:
        with mock.patch.object(sys, "argv", ["spyfu-fetch.py", "usage", "--ttl", "nan"]):
            with self.assertRaises(SystemExit):
                spyfu.main()

    def test_ttl_inf_is_rejected_at_parse_time(self) -> None:
        with mock.patch.object(sys, "argv", ["spyfu-fetch.py", "usage", "--ttl", "inf"]):
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


def fake_response(body: bytes):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def read(self):
            return body

    return FakeResponse()


class CallErrorTest(unittest.TestCase):
    """F-13, гейт круга 2: call() раньше пропускала HTTPError/URLError/битый
    JSON наружу необработанными — вызывающая сторона (run()) их не ловила
    вовсе, запись расхода не происходила. Теперь call() поднимает
    ApiCallError; здесь — прямые тесты транспортного слоя."""

    def test_http_error_raises_api_call_error(self) -> None:
        import io
        err = spyfu.urllib.error.HTTPError("url", 500, "Internal Server Error", {}, io.BytesIO(b"boom"))
        with mock.patch.object(spyfu.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(spyfu.ApiCallError):
                with spyfu.armed_spend(lambda: True, hosts="api.spyfu.com"):
                    spyfu.call("b64", "some/path", {"domain": "x"})

    def test_url_error_raises_api_call_error(self) -> None:
        with mock.patch.object(spyfu.urllib.request, "urlopen",
                               side_effect=spyfu.urllib.error.URLError("no route to host")):
            with self.assertRaises(spyfu.ApiCallError):
                with spyfu.armed_spend(lambda: True, hosts="api.spyfu.com"):
                    spyfu.call("b64", "some/path", {"domain": "x"})

    def test_malformed_json_raises_api_call_error(self) -> None:
        with mock.patch.object(spyfu.urllib.request, "urlopen", return_value=fake_response(b"{not valid")):
            with self.assertRaises(spyfu.ApiCallError):
                with spyfu.armed_spend(lambda: True, hosts="api.spyfu.com"):
                    spyfu.call("b64", "some/path", {"domain": "x"})


class RunThroughRealCallTest(unittest.TestCase):
    """Тот же принцип, что в test_dataforseo_fetch.FetchThroughRealCallTest:
    мокается urlopen, а не spyfu.call — так видна ровно та ветка, которую
    круг 1 не тестировал (call() сама пробрасывала исключение наружу)."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-spyfu-realcall-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = argparse_namespace(out=str(self.tmp), budget=40.0, ttl=30.0, force=False)

    def _run_and_check_recorded(self, urlopen_kwargs) -> None:
        with mock.patch.object(spyfu.urllib.request, "urlopen", **urlopen_kwargs):
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage.get("failed_calls"), 1, "неуспешная попытка обязана остаться в учёте")

    def test_http_error_records_before_exit(self) -> None:
        import io
        err = spyfu.urllib.error.HTTPError("url", 500, "Internal Server Error", {}, io.BytesIO(b"boom"))
        self._run_and_check_recorded({"side_effect": err})

    def test_url_error_records_before_exit(self) -> None:
        self._run_and_check_recorded({"side_effect": spyfu.urllib.error.URLError("no route to host")})

    def test_malformed_json_records_before_exit(self) -> None:
        self._run_and_check_recorded({"return_value": fake_response(b"{not valid")})

    # R2-2 (независимый гейт, круг 3): обрыв тела уже отправленного запроса
    # экзотическим типом (не HTTPError/URLError/TimeoutError). Мутация: замени
    # `except Exception as e:` в call() обратно на перечень типов — все три
    # теста ниже обязаны покраснеть.
    def _run_read_raises_and_check_recorded(self, exc: BaseException) -> None:
        class RaisingReadResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                raise exc

        with mock.patch.object(spyfu.urllib.request, "urlopen", return_value=RaisingReadResponse()):
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage.get("failed_calls"), 1, "неуспешная попытка обязана остаться в учёте")

    def test_incomplete_read_records_before_exit(self) -> None:
        import http.client
        self._run_read_raises_and_check_recorded(http.client.IncompleteRead(b""))

    def test_connection_reset_records_before_exit(self) -> None:
        self._run_read_raises_and_check_recorded(ConnectionResetError("connection reset by peer"))

    def test_ssl_error_records_before_exit(self) -> None:
        import ssl
        self._run_read_raises_and_check_recorded(ssl.SSLError("decryption failed"))


class WriteAheadSurvivesBaseExceptionTest(unittest.TestCase):
    """R3-1 (независимый гейт, круг 4): те же основания, что в
    test_dataforseo_fetch.WriteAheadSurvivesBaseExceptionTest — `except
    Exception` не ловит KeyboardInterrupt/SystemExit (BaseException), и ни
    один except не ловит SIGKILL. Write-ahead (`cost_unknown_calls`
    инкрементируется и save_usage() вызывается ДО call()) переживает всё это.
    Мутация: перенеси write-ahead после call() — тест обязан покраснеть."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-spyfu-baseexc-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = argparse_namespace(out=str(self.tmp), budget=40.0, ttl=30.0, force=False)

    def test_keyboard_interrupt_after_request_sent_is_already_recorded(self) -> None:
        with mock.patch.object(spyfu.urllib.request, "urlopen", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage.get("cost_unknown_calls"), 1, "запрос ушёл — обязан быть учтён на диске "
                                                              "ДО того как KeyboardInterrupt долетит до caller")

    def test_system_exit_after_request_sent_is_already_recorded(self) -> None:
        with mock.patch.object(spyfu.urllib.request, "urlopen", side_effect=SystemExit(1)):
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage.get("cost_unknown_calls"), 1)


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


class PoisonedCostUnknownCallsTest(unittest.TestCase):
    """R4-1/R4-2 (независимый гейт, круг 4→5): у `spyfu-fetch.py` этот стоп
    был единственным во всём диффе круга 4, не покрытым НИ ОДНИМ из 832
    тестов (гейт круга 4 показал: удалить строку целиком — ничего не
    краснеет). `cost_unknown_calls` не входит в `USAGE_FIELDS =
    ("spent_usd", "rows")`, поэтому старая `load_usage()` (проверка только по
    имени из списка) пропускала его отравленное значение молча — F-11 в
    шестой раз. Свой тест на КАЖДОГО клиента отдельно (не «раз соседа
    покрыли — и этот защищён»): дыра здесь была именно потому, что покрытие
    жило только у dataforseo."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-spyfu-cuc-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = argparse_namespace(out=str(self.tmp), budget=40.0, ttl=30.0, force=False)

    def _write(self, **fields) -> None:
        payload = {"month": spyfu.current_month(), "spent_usd": 0.0, "rows": 0}
        payload.update(fields)
        (self.tmp / "_usage.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_negative_cost_unknown_calls_blocks_paid_call(self) -> None:
        """Самое опасное значение: `-5 + 1 - 1 = -5`, стоп `> 0` не
        сработает больше НИКОГДА (самоподдерживающаяся дыра, R4-1)."""
        self._write(cost_unknown_calls=-5)
        with mock.patch.object(spyfu, "call") as called:
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
            called.assert_not_called()

    def test_nan_cost_unknown_calls_blocks_paid_call(self) -> None:
        (self.tmp / "_usage.json").write_text(
            '{"month": "%s", "spent_usd": 0.0, "rows": 0, "cost_unknown_calls": NaN}'
            % spyfu.current_month(), encoding="utf-8")
        with mock.patch.object(spyfu, "call") as called:
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
            called.assert_not_called()

    def test_infinity_failed_calls_is_treated_as_corrupt(self) -> None:
        """`failed_calls` — второй новый счётчик круга 4, тоже вне
        `USAGE_FIELDS`. Не сам по себе денежный стоп, но проходит через ту же
        `load_usage()` — если бы проверка осталась по имени из списка, эта
        отрава читалась бы молча в память процесса вместе со `spent_usd`."""
        (self.tmp / "_usage.json").write_text(
            '{"month": "%s", "spent_usd": 0.0, "rows": 0, "failed_calls": Infinity}'
            % spyfu.current_month(), encoding="utf-8")
        with self.assertRaises(spyfu.UsageLedgerError):
            spyfu.load_usage(self.tmp)

    def test_legitimate_positive_value_still_blocks_as_designed(self) -> None:
        """Положительный контроль: значение 1 обязано блокировать (сам стоп
        R3-1 не сломан этим фиксом)."""
        self._write(cost_unknown_calls=1)
        with mock.patch.object(spyfu, "call") as called:
            with self.assertRaises(SystemExit):
                spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
            called.assert_not_called()

    def test_zero_value_lets_the_paid_call_through(self) -> None:
        """Контроль в другую сторону: легитимный ноль обязан пропускать
        вызов — иначе стенд ловит сломанный тест, не дыру."""
        self._write(cost_unknown_calls=0)
        with mock.patch.object(spyfu, "call", return_value=domain_stats_response(1)):
            spyfu.run("b64", "some/path", 0.50, {"domain": "x"}, self.args, lambda r: None)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["cost_unknown_calls"], 0)


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
