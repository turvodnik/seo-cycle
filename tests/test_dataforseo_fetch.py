#!/usr/bin/env python3
"""Tests for dataforseo-fetch.py (auth, cache, budget guard, usage ledger, distill)."""

from __future__ import annotations

import base64
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
sys.path.insert(0, str(SCRIPTS))  # dataforseo-fetch.py импортирует seo_cycle_core.config

spec = importlib.util.spec_from_file_location("dfs_fetch", SCRIPTS / "dataforseo-fetch.py")
dfs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dfs)

_find_config_patcher: mock._patch | None = None


def setUpModule() -> None:
    """Герметичность (T-059): fetch() зовёт effective_budget() -> find_config(),
    который иначе ищет seo-cycle.yaml от реального cwd процесса unittest. Ни один
    тест в этом файле не должен зависеть от того, что лежит на диске снаружи —
    кроме ConfigBudgetTest, который явно переопределяет find_config() у себя
    (вложенный mock.patch.object корректно восстанавливает это значение на выходе)."""
    global _find_config_patcher
    _find_config_patcher = mock.patch.object(dfs, "find_config", return_value=None)
    _find_config_patcher.start()


def tearDownModule() -> None:
    if _find_config_patcher is not None:
        _find_config_patcher.stop()


def volume_response(cost: float = 0.05) -> dict:
    return {
        "status_code": 20000,
        "cost": cost,
        "tasks": [{
            "status_code": 20000,
            "result": [
                {"keyword": "vata", "search_volume": 1000, "competition": "LOW", "cpc": 0.4},
                {"keyword": "vata cena", "search_volume": 2000, "competition": "HIGH", "cpc": 0.9},
            ],
        }],
    }


def task_error_response(cost: float = 0.0) -> dict:
    """Конверт успешен (status_code 20000), но сама задача провалилась — так
    DataForSEO отвечает на невалидные параметры отдельной задачи в батче."""
    return {
        "status_code": 20000,
        "cost": cost,
        "tasks": [{
            "status_code": 40501,
            "status_message": "Invalid Field: 'keywords'.",
            "result": None,
        }],
    }


class AuthTest(unittest.TestCase):
    def test_ready_base64_wins(self) -> None:
        self.assertEqual(dfs.load_auth({"DATAFORSEO_API_KEY_BASE64": " abc "}), "abc")

    def test_login_password_are_encoded(self) -> None:
        got = dfs.load_auth({"DATAFORSEO_LOGIN": "u@example.com", "DATAFORSEO_PASSWORD": "p"})
        self.assertEqual(base64.b64decode(got).decode(), "u@example.com:p")

    def test_missing_credentials_exit(self) -> None:
        with mock.patch.object(pathlib.Path, "exists", return_value=False):
            with self.assertRaises(SystemExit):
                dfs.load_auth({})


class BudgetArgTest(unittest.TestCase):
    """F-11 (независимый прогон 2026-09-06): --budget объявлялся как голое
    `type=float`, и argparse штатно принимает nan/inf/-inf — дальше
    `min(nan, cap)` даёт nan, и бюджетный стоп отключается полностью. Проверка
    на уровне разбора аргументов (budget_arg), не внутри fetch()."""

    def test_nan_is_rejected_at_parse_time(self) -> None:
        with self.assertRaises(SystemExit):
            dfs.build_parser().parse_args(["--budget", "nan", "balance"])

    def test_inf_is_rejected_at_parse_time(self) -> None:
        with self.assertRaises(SystemExit):
            dfs.build_parser().parse_args(["--budget", "inf", "balance"])

    def test_negative_is_rejected_at_parse_time(self) -> None:
        with self.assertRaises(SystemExit):
            dfs.build_parser().parse_args(["--budget", "-1", "balance"])

    def test_ordinary_budget_still_parses(self) -> None:
        args = dfs.build_parser().parse_args(["--budget", "12.5", "balance"])
        self.assertEqual(args.budget, 12.5)


class TtlArgTest(unittest.TestCase):
    """R-4 (гейт круга 2): --ttl оставался голым type=float. --ttl nan делает
    `(now - mtime) / 86400 <= nan` вечно False — кэш никогда не используется,
    каждый вызов становится платным (F-11 называл --ttl прямо в тексте)."""

    def test_nan_is_rejected_at_parse_time(self) -> None:
        with self.assertRaises(SystemExit):
            dfs.build_parser().parse_args(["--ttl", "nan", "balance"])

    def test_inf_is_rejected_at_parse_time(self) -> None:
        with self.assertRaises(SystemExit):
            dfs.build_parser().parse_args(["--ttl", "inf", "balance"])

    def test_negative_is_rejected_at_parse_time(self) -> None:
        with self.assertRaises(SystemExit):
            dfs.build_parser().parse_args(["--ttl", "-1", "balance"])


class FetchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = dfs.build_parser().parse_args(
            ["--out", str(self.tmp), "volume", "vata"])

    def test_cost_is_accumulated_in_usage_ledger(self) -> None:
        with mock.patch.object(dfs, "call", return_value=volume_response(0.05)) as called:
            dfs.fetch("b64", "keywords_data/google_ads/search_volume/live", {"k": 1}, self.args)
            self.assertEqual(called.call_count, 1)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1)
        self.assertAlmostEqual(usage["spent_usd"], 0.05)

    def test_second_identical_call_is_served_from_cache(self) -> None:
        payload = {"k": 1}
        with mock.patch.object(dfs, "call", return_value=volume_response()) as called:
            dfs.fetch("b64", "some/path", payload, self.args)
            dfs.fetch("b64", "some/path", payload, self.args)
            self.assertEqual(called.call_count, 1, "второй одинаковый запрос должен идти из кэша")
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1)

    def test_budget_guard_stops_before_paid_call(self) -> None:
        dfs.save_usage(self.tmp, {"month": dfs.load_usage(self.tmp)["month"],
                                  "spent_usd": 99.0, "calls": 7})
        with mock.patch.object(dfs, "call") as called:
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "some/path", {"k": 2}, self.args)
            called.assert_not_called()

    def test_force_overrides_budget_guard(self) -> None:
        dfs.save_usage(self.tmp, {"month": dfs.load_usage(self.tmp)["month"],
                                  "spent_usd": 99.0, "calls": 7})
        self.args.force = True
        with mock.patch.object(dfs, "call", return_value=volume_response(0.01)):
            dfs.fetch("b64", "some/path", {"k": 3}, self.args)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(usage["spent_usd"], 99.01)

    def test_api_error_status_exits(self) -> None:
        bad = {"status_code": 40401, "status_message": "Not Found", "tasks": []}
        with mock.patch.object(dfs, "call", return_value=bad):
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "some/path", {"k": 4}, self.args)

    def test_api_error_status_still_records_the_paid_call(self) -> None:
        """F-13: выход по плохому status_code конверта раньше происходил ДО
        любой записи в _usage.json — платный вызов случился, а учёт о нём не
        узнавал (T-059 не трогал эту ветку). Теперь запись должна произойти
        первой, sys.exit — вторым."""
        bad = {"status_code": 40401, "status_message": "Not Found",
               "cost": 0.03, "tasks": []}
        with mock.patch.object(dfs, "call", return_value=bad):
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "some/path", {"k": 4}, self.args)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1)
        self.assertAlmostEqual(usage["spent_usd"], 0.03)

    def test_task_level_error_is_not_cached(self) -> None:
        """T-059: конверт status_code=20000, но tasks[0] провалился — раньше это
        всё равно писалось в кэш на --ttl (по умолчанию 30) дней."""
        payload = {"k": "err"}
        with mock.patch.object(dfs, "call", return_value=task_error_response()):
            resp = dfs.fetch("b64", "some/path", payload, self.args)
        self.assertEqual(resp["tasks"][0]["status_code"], 40501)
        cpath = dfs.cache_path(self.tmp, "some/path", payload)
        self.assertFalse(cpath.exists(), "ответ с ошибкой задачи не должен попадать в кэш")

    def test_successful_task_is_still_cached(self) -> None:
        """Контраст к предыдущему тесту: успешная задача кэшируется, как раньше —
        фикс не про «перестать кэшировать», а именно про ошибочные задачи."""
        payload = {"k": "ok"}
        with mock.patch.object(dfs, "call", return_value=volume_response(0.01)):
            dfs.fetch("b64", "some/path", payload, self.args)
        cpath = dfs.cache_path(self.tmp, "some/path", payload)
        self.assertTrue(cpath.exists())


class FetchThroughRealCallTest(unittest.TestCase):
    """Круг 2 независимого гейта: круг-1 тесты мокали `dfs.call` целиком —
    ровно тот слой, который сам делал sys.exit, так что F-13 в call() был
    невидим для тестов. Здесь мокается `urllib.request.urlopen` — на один
    уровень ниже, — и через fetch() идёт настоящий call() со всеми его
    ветками выхода. Каждый тест — одна ветка, каждый проверяет: _usage.json
    существует, calls == 1, ДО того, как проверяется SystemExit."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-realcall-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = dfs.build_parser().parse_args(["--out", str(self.tmp), "volume", "vata"])

    def _run_and_check_recorded(self, urlopen_kwargs) -> None:
        with mock.patch.object(dfs.urllib.request, "urlopen", **urlopen_kwargs):
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "keywords_data/google_ads/search_volume/live", {"k": 1}, self.args)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1, "платный вызов обязан быть учтён на этой ветке выхода")

    def test_http_error_records_before_exit(self) -> None:
        import io
        err = dfs.urllib.error.HTTPError("url", 500, "Internal Server Error", {}, io.BytesIO(b"boom"))
        self._run_and_check_recorded({"side_effect": err})

    def test_url_error_records_before_exit(self) -> None:
        self._run_and_check_recorded({"side_effect": dfs.urllib.error.URLError("no route to host")})

    def test_malformed_json_records_before_exit(self) -> None:
        self._run_and_check_recorded({"return_value": fake_response(b"{not valid json")})

    def test_json_null_body_records_before_exit(self) -> None:
        self._run_and_check_recorded({"return_value": fake_response(b"null")})

    def test_json_array_body_records_before_exit(self) -> None:
        self._run_and_check_recorded({"return_value": fake_response(b"[]")})

    def test_bad_envelope_status_records_before_exit(self) -> None:
        body = json.dumps({"status_code": 40401, "status_message": "Not Found"}).encode()
        self._run_and_check_recorded({"return_value": fake_response(body)})

    def test_unusable_cost_records_before_exit(self) -> None:
        body = json.dumps({"status_code": 20000, "cost": float("nan"),
                            "tasks": [{"status_code": 20000, "result": []}]}).encode()
        self._run_and_check_recorded({"return_value": fake_response(body)})

    def test_missing_cost_on_paid_path_records_before_exit(self) -> None:
        """R-5: платный метод без поля cost — тоже честный отказ, не 0."""
        body = json.dumps({"status_code": 20000,
                            "tasks": [{"status_code": 20000, "result": []}]}).encode()
        self._run_and_check_recorded({"return_value": fake_response(body)})

    # R2-2 (независимый гейт, круг 3): тело УЖЕ отправленного запроса может
    # порваться множеством способов, ни один из которых — HTTPError/URLError/
    # TimeoutError, которые круг 2 ловил перечнем. Каждый следующий тест — мок
    # `.read()`, поднимающий ровно такое исключение (запрос считается ушедшим).
    # Мутация: замени `except Exception as e:` обратно на перечень конкретных
    # типов в call() — все четыре теста ниже обязаны покраснеть.
    def _run_read_raises_and_check_recorded(self, exc: BaseException) -> None:
        class RaisingReadResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                raise exc

        with mock.patch.object(dfs.urllib.request, "urlopen", return_value=RaisingReadResponse()):
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "keywords_data/google_ads/search_volume/live", {"k": 1}, self.args)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1, "платный вызов обязан быть учтён даже при экзотическом обрыве чтения")

    def test_incomplete_read_records_before_exit(self) -> None:
        import http.client
        self._run_read_raises_and_check_recorded(http.client.IncompleteRead(b""))

    def test_connection_reset_records_before_exit(self) -> None:
        self._run_read_raises_and_check_recorded(ConnectionResetError("connection reset by peer"))

    def test_ssl_error_records_before_exit(self) -> None:
        import ssl
        self._run_read_raises_and_check_recorded(ssl.SSLError("decryption failed"))

    def test_memory_error_records_before_exit(self) -> None:
        self._run_read_raises_and_check_recorded(MemoryError())


class WriteAheadSurvivesBaseExceptionTest(unittest.TestCase):
    """R3-1 (независимый гейт, круг 4): круг 3 закрыл потерю расхода через
    `except Exception` в call() — но `except Exception` НЕ ловит
    KeyboardInterrupt/SystemExit/GeneratorExit (все — BaseException), и ни
    один except вообще не ловит SIGKILL. Правильный уровень — записать
    намерение потратить (write-ahead) ДО отправки запроса, а не пытаться
    перехватить после. Мутация: перенеси write-ahead (`u["calls"] += 1;
    u["cost_unknown_calls"] += 1; save_usage(...)`) обратно ПОСЛЕ call() —
    оба теста ниже обязаны покраснеть (usage.json не будет содержать запись,
    потому что KeyboardInterrupt улетит до save_usage())."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-baseexc-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = dfs.build_parser().parse_args(["--out", str(self.tmp), "volume", "vata"])

    def test_keyboard_interrupt_after_request_sent_is_already_recorded(self) -> None:
        with mock.patch.object(dfs.urllib.request, "urlopen", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                dfs.fetch("b64", "keywords_data/google_ads/search_volume/live", {"k": 1}, self.args)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1, "запрос ушёл — обязан быть учтён на диске ДО того как "
                                             "KeyboardInterrupt долетит до вызывающего кода")
        self.assertEqual(usage.get("cost_unknown_calls"), 1)

    def test_system_exit_after_request_sent_is_already_recorded(self) -> None:
        with mock.patch.object(dfs.urllib.request, "urlopen", side_effect=SystemExit(1)):
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "keywords_data/google_ads/search_volume/live", {"k": 1}, self.args)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1)
        self.assertEqual(usage.get("cost_unknown_calls"), 1)


class CostUnknownBlocksFurtherCallsTest(unittest.TestCase):
    """R2-3 (независимый гейт, круг 3): «сумма неизвестна» — не «сумма 0».
    Мутация: убери проверку `cost_unknown_calls` в fetch() — тест обязан
    показать, что 200 вызовов проходят при бюджете $1."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-costunknown-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = dfs.build_parser().parse_args(
            ["--out", str(self.tmp), "--budget", "1.0", "volume", "vata"])

    def test_first_cost_unknown_call_blocks_the_next(self) -> None:
        no_cost = {"status_code": 20000, "tasks": [{"status_code": 20000, "result": []}]}
        calls_made = 0
        with mock.patch.object(dfs, "call", return_value=no_cost):
            for _ in range(200):
                self.args.__dict__.pop("_cache_bust", None)
                payload = {"unique": calls_made}
                try:
                    dfs.fetch("b64", "keywords_data/google_ads/search_volume/live", payload, self.args)
                except SystemExit:
                    pass
                calls_made += 1
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1,
                          "после первого вызова с неизвестной суммой дальнейшие платные вызовы обязаны блокироваться")
        self.assertEqual(usage.get("cost_unknown_calls"), 1)

    def test_force_overrides_the_cost_unknown_block(self) -> None:
        no_cost = {"status_code": 20000, "tasks": [{"status_code": 20000, "result": []}]}
        self.args.force = True
        with mock.patch.object(dfs, "call", return_value=no_cost):
            for i in range(3):
                try:
                    dfs.fetch("b64", "keywords_data/google_ads/search_volume/live", {"unique": i}, self.args)
                except SystemExit:
                    pass
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 3, "--force обязан осознанно снимать этот стоп, как и денежный")


class LedgerCorruptionTest(unittest.TestCase):
    """T-059: битый/нечитаемый _usage.json — это отказ, а не «потрачено 0»."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-corrupt-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = dfs.build_parser().parse_args(["--out", str(self.tmp), "volume", "vata"])

    def test_corrupt_json_raises_ledger_error(self) -> None:
        (self.tmp / "_usage.json").write_text("{ не json вообще", encoding="utf-8")
        with self.assertRaises(dfs.UsageLedgerError):
            dfs.load_usage(self.tmp)

    def test_wrong_schema_is_also_treated_as_corrupt(self) -> None:
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": "2099-01", "spent_usd": "много"}), encoding="utf-8")
        with self.assertRaises(dfs.UsageLedgerError):
            dfs.load_usage(self.tmp)

    def test_old_month_is_not_treated_as_corrupt(self) -> None:
        """Регрессия: смена месяца — легитимный сброс, а не порча файла."""
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": "2000-01", "spent_usd": 42.0, "calls": 9}), encoding="utf-8")
        u = dfs.load_usage(self.tmp)
        self.assertEqual(u["spent_usd"], 0.0)
        self.assertEqual(u["calls"], 0)

    def test_corrupt_usage_file_blocks_paid_call_without_force(self) -> None:
        (self.tmp / "_usage.json").write_text("совсем не json", encoding="utf-8")
        with mock.patch.object(dfs, "call") as called:
            with self.assertRaises(SystemExit) as ctx:
                dfs.fetch("b64", "some/path", {"k": 1}, self.args)
            called.assert_not_called()
        self.assertTrue(ctx.exception.code, "sys.exit должен нести непустое сообщение — "
                                             "это гарантирует ненулевой код выхода процесса")

    def test_corrupt_usage_file_with_force_resets_and_proceeds(self) -> None:
        (self.tmp / "_usage.json").write_text("{ битый файл", encoding="utf-8")
        self.args.force = True
        with mock.patch.object(dfs, "call", return_value=volume_response(0.02)):
            dfs.fetch("b64", "some/path", {"k": 1}, self.args)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(usage["spent_usd"], 0.02, msg="--force считает месяц заново, "
                                                              "а не наследует битые данные")

    def test_nan_spent_usd_is_treated_as_corrupt(self) -> None:
        """Гейт T-059 (красный №1): json.loads штатно парсит литерал NaN в
        float('nan'), который проходит isinstance(x, (int, float)) — тип один,
        пригодность для арифметики другая. NaN >= budget всегда ложно, NaN + cost
        снова NaN — бюджетный стоп молча отключается навсегда."""
        (self.tmp / "_usage.json").write_text(
            '{"month": "2099-01", "spent_usd": NaN, "calls": 0}', encoding="utf-8")
        with self.assertRaises(dfs.UsageLedgerError):
            dfs.load_usage(self.tmp)

    def test_infinity_spent_usd_is_treated_as_corrupt(self) -> None:
        (self.tmp / "_usage.json").write_text(
            '{"month": "2099-01", "spent_usd": Infinity, "calls": 0}', encoding="utf-8")
        with self.assertRaises(dfs.UsageLedgerError):
            dfs.load_usage(self.tmp)

    def test_negative_spent_usd_is_treated_as_corrupt(self) -> None:
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": "2099-01", "spent_usd": -5.0, "calls": 0}), encoding="utf-8")
        with self.assertRaises(dfs.UsageLedgerError):
            dfs.load_usage(self.tmp)

    def test_non_numeric_calls_is_treated_as_corrupt(self) -> None:
        """Гейт T-059 (красный №2): раньше платный вызов уходил, потом на
        `u.get("calls", 0) + 1` падал TypeError, и save_usage() не успевал
        выполниться — деньги потрачены и не учтены, причём при каждом запуске.
        Проверка теперь идёт вместе с spent_usd, до платного вызова."""
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": "2099-01", "spent_usd": 1.0, "calls": "много"}), encoding="utf-8")
        with self.assertRaises(dfs.UsageLedgerError):
            dfs.load_usage(self.tmp)

    def test_corrupted_month_type_is_treated_as_corrupt(self) -> None:
        """Жёлтый T-059: раньше любое не-строковое/неформатное значение month
        просто не совпадало с текущим месяцем по `!=` и тихо трактовалось как
        легитимная смена месяца — то есть снова «потрачено 0» под видом нормы."""
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": 12345, "spent_usd": 1.0, "calls": 0}), encoding="utf-8")
        with self.assertRaises(dfs.UsageLedgerError):
            dfs.load_usage(self.tmp)

    def test_nan_spent_usd_blocks_paid_call_without_force(self) -> None:
        (self.tmp / "_usage.json").write_text(
            '{"month": "2099-01", "spent_usd": NaN, "calls": 0}', encoding="utf-8")
        with mock.patch.object(dfs, "call") as called:
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "some/path", {"k": 1}, self.args)
            called.assert_not_called()

    def test_non_numeric_calls_blocks_paid_call_without_force(self) -> None:
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": "2099-01", "spent_usd": 1.0, "calls": "много"}), encoding="utf-8")
        with mock.patch.object(dfs, "call") as called:
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "some/path", {"k": 1}, self.args)
            called.assert_not_called()


class SaveUsageAtomicityTest(unittest.TestCase):
    """T-059: атомарность (temp-файл + os.replace) не была покрыта ни одним тестом —
    единственная из мутаций ревью, которая ничего не уронила. Проверяем поведение,
    а не реализацию: настоящий файл не портится и не остаётся мусора, если запись
    оборвалась на середине."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-atomic-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_real_file_untouched_if_write_fails_midway(self) -> None:
        good = {"month": "2000-01", "spent_usd": 1.23, "calls": 4}
        dfs.usage_file(self.tmp).write_text(json.dumps(good), encoding="utf-8")
        with mock.patch.object(dfs.json, "dump", side_effect=RuntimeError("диск кончился")):
            with self.assertRaises(RuntimeError):
                dfs.save_usage(self.tmp, {"month": "2099-01", "spent_usd": 999.0, "calls": 1})
        on_disk = json.loads(dfs.usage_file(self.tmp).read_text(encoding="utf-8"))
        self.assertEqual(on_disk, good, "os.replace не должен был выполниться — "
                                         "старые данные обязаны остаться нетронутыми")

    def test_no_leftover_temp_file_after_write_failure(self) -> None:
        with mock.patch.object(dfs.json, "dump", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                dfs.save_usage(self.tmp, {"month": "2099-01", "spent_usd": 1.0, "calls": 1})
        leftovers = list(self.tmp.glob(".usage-*"))
        self.assertEqual(leftovers, [], f"временный файл должен удаляться при сбое: {leftovers}")

    def test_successful_write_leaves_no_temp_file_either(self) -> None:
        dfs.save_usage(self.tmp, {"month": "2099-01", "spent_usd": 1.0, "calls": 1})
        leftovers = list(self.tmp.glob(".usage-*"))
        self.assertEqual(leftovers, [])
        self.assertTrue(dfs.usage_file(self.tmp).exists())


class ConfigBudgetTest(unittest.TestCase):
    """T-059: governance.subscriptions.dataforseo.monthly_usd_cap проекта берётся
    как минимум с --budget; конфиг без секции не меняет поведение. Путь —
    установленная конвенция схемы (тот же читают scripts/spend-guard.py и
    scripts/usage-ledger.py для всех платных подписок проекта), НЕ придуман для
    этого тикета — см. test_effective_budget_reads_real_project_template ниже,
    который сверяется с настоящим config/project.template.yaml."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-cfg-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = dfs.build_parser().parse_args(["--out", str(self.tmp), "volume", "vata"])
        self.fake_cfg_path = self.tmp / "seo-cycle.yaml"  # файл не обязан существовать — load_yaml замокан

    def test_no_config_found_keeps_cli_budget_as_before(self) -> None:
        with mock.patch.object(dfs, "find_config", return_value=None):
            self.assertEqual(dfs.effective_budget(self.args), self.args.budget)

    def test_config_without_dataforseo_section_keeps_cli_budget(self) -> None:
        with mock.patch.object(dfs, "find_config", return_value=self.fake_cfg_path), \
             mock.patch.object(dfs, "load_yaml",
                               return_value={"governance": {"subscriptions":
                                             {"keys_so": {"monthly_request_cap": 100}}}}):
            self.assertEqual(dfs.effective_budget(self.args), self.args.budget)

    def test_config_cap_lower_than_cli_budget_wins(self) -> None:
        with mock.patch.object(dfs, "find_config", return_value=self.fake_cfg_path), \
             mock.patch.object(dfs, "load_yaml",
                               return_value={"governance": {"subscriptions":
                                             {"dataforseo": {"monthly_usd_cap": 0.02}}}}):
            self.assertEqual(dfs.effective_budget(self.args), 0.02)

    def test_config_cap_never_raises_cli_budget(self) -> None:
        """min(), не max(): конфиг может только сузить лимит, не расширить его
        сверх того, что человек явно попросил флагом."""
        self.args.budget = 0.5
        with mock.patch.object(dfs, "find_config", return_value=self.fake_cfg_path), \
             mock.patch.object(dfs, "load_yaml",
                               return_value={"governance": {"subscriptions":
                                             {"dataforseo": {"monthly_usd_cap": 999}}}}):
            self.assertEqual(dfs.effective_budget(self.args), 0.5)

    def test_config_cap_triggers_stop_before_paid_call(self) -> None:
        dfs.save_usage(self.tmp, {"month": dfs.load_usage(self.tmp)["month"], "spent_usd": 0.02, "calls": 1})
        with mock.patch.object(dfs, "find_config", return_value=self.fake_cfg_path), \
             mock.patch.object(dfs, "load_yaml",
                               return_value={"governance": {"subscriptions":
                                             {"dataforseo": {"monthly_usd_cap": 0.01}}}}):
            with mock.patch.object(dfs, "call") as called:
                with self.assertRaises(SystemExit):
                    dfs.fetch("b64", "some/path", {"k": 1}, self.args)
                called.assert_not_called()

    def test_effective_budget_reads_real_project_template(self) -> None:
        """Контракт-тест: config/project.template.yaml реально определяет
        governance.subscriptions.dataforseo.monthly_usd_cap (значение 5, совпадает
        с DEFAULT_BUDGET_USD). Ловит будущий дрейф пути между кодом и шаблоном —
        именно такой дрейф допустил первый вариант этого фикса (cost_controls.*,
        путь, которого в шаблоне не существует)."""
        template = ROOT / "config" / "project.template.yaml"
        self.assertTrue(template.exists(), template)
        with mock.patch.object(dfs, "find_config", return_value=template):
            self.args.budget = 999.0
            self.assertEqual(dfs.effective_budget(self.args), 5.0)

    def test_same_spend_without_config_does_not_trigger_guard(self) -> None:
        """Негативный контроль к предыдущему тесту: тот же расход (0.02) и тот же
        --budget (5.0 по умолчанию), но БЕЗ конфига вызов проходит — разницу даёт
        именно конфиг-лимит, а не что-то ещё."""
        dfs.save_usage(self.tmp, {"month": dfs.load_usage(self.tmp)["month"], "spent_usd": 0.02, "calls": 1})
        with mock.patch.object(dfs, "find_config", return_value=None):
            with mock.patch.object(dfs, "call", return_value=volume_response(0.01)) as called:
                dfs.fetch("b64", "some/path", {"k": 1}, self.args)
                called.assert_called_once()

    def test_non_numeric_cap_is_honest_failure_not_silent_fallback(self) -> None:
        """Гейт T-059 (жёлтый): раньше мусор в monthly_usd_cap молча откатывался на
        --budget — опечатка в конфиге («unlimited» вместо числа) тихо снимала лимит,
        который человек специально понижал. Теперь — честный sys.exit."""
        with mock.patch.object(dfs, "find_config", return_value=self.fake_cfg_path), \
             mock.patch.object(dfs, "load_yaml",
                               return_value={"governance": {"subscriptions":
                                             {"dataforseo": {"monthly_usd_cap": "unlimited"}}}}):
            with self.assertRaises(SystemExit) as ctx:
                dfs.effective_budget(self.args)
        self.assertTrue(ctx.exception.code)

    def test_negative_cap_is_honest_failure(self) -> None:
        with mock.patch.object(dfs, "find_config", return_value=self.fake_cfg_path), \
             mock.patch.object(dfs, "load_yaml",
                               return_value={"governance": {"subscriptions":
                                             {"dataforseo": {"monthly_usd_cap": -1}}}}):
            with self.assertRaises(SystemExit):
                dfs.effective_budget(self.args)

    def test_nan_cap_is_honest_failure(self) -> None:
        with mock.patch.object(dfs, "find_config", return_value=self.fake_cfg_path), \
             mock.patch.object(dfs, "load_yaml",
                               return_value={"governance": {"subscriptions":
                                             {"dataforseo": {"monthly_usd_cap": float("nan")}}}}):
            with self.assertRaises(SystemExit):
                dfs.effective_budget(self.args)

    def test_malformed_yaml_gives_clean_exit_not_traceback(self) -> None:
        """Жёлтый T-059: битый YAML раньше давал необработанный yaml.YAMLError."""
        self.fake_cfg_path.write_text("governance:\n  subscriptions: [это не словарь\n",
                                       encoding="utf-8")
        with mock.patch.object(dfs, "find_config", return_value=self.fake_cfg_path):
            with self.assertRaises(SystemExit) as ctx:
                dfs.effective_budget(self.args)
        self.assertTrue(ctx.exception.code)


class ConcurrencyTest(unittest.TestCase):
    """T-059: «проверка бюджета -> вызов -> запись» под файловой блокировкой —
    два параллельных fetch() не должны терять расход друг друга."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-lock-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_parallel_fetch_does_not_lose_either_spend(self) -> None:
        entered_first = threading.Event()
        release_first = threading.Event()
        call_count = {"n": 0}
        count_lock = threading.Lock()

        def shared_call(_b64, _path, _payload):
            with count_lock:
                call_count["n"] += 1
                is_first = call_count["n"] == 1
            if is_first:
                entered_first.set()
                # держим блокировку занятой — второй поток должен встать в очередь
                # на flock(), а не прочитать тот же «старый» _usage.json.
                release_first.wait(timeout=2)
            return volume_response(0.05)

        original_call = dfs.call
        dfs.call = shared_call
        self.addCleanup(setattr, dfs, "call", original_call)

        errors: list[BaseException] = []

        def worker(idx: int) -> None:
            try:
                args = dfs.build_parser().parse_args(["--out", str(self.tmp), "volume", f"kw{idx}"])
                dfs.fetch("b64", "keywords_data/google_ads/search_volume/live", {"k": idx}, args)
            except BaseException as e:  # noqa: BLE001 - тест должен увидеть любую ошибку потока
                errors.append(e)

        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))
        t1.start()
        self.assertTrue(entered_first.wait(timeout=2), "поток 1 должен войти в call() до старта потока 2")
        t2.start()
        time.sleep(0.15)  # дать потоку 2 реальный шанс упереться в блокировку
        release_first.set()
        t1.join(timeout=3)
        t2.join(timeout=3)

        self.assertFalse(errors, f"потоки упали: {errors}")
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(usage["spent_usd"], 0.10, msg="без блокировки один из двух "
                                                              "расходов $0.05 был бы потерян")
        self.assertEqual(usage["calls"], 2)


class IdeasPayloadTest(unittest.TestCase):
    """T-059: dataforseo_labs/google/keyword_ideas/live требует `keywords` (массив),
    а не `keyword` (строка) — контракт проверен по docs.dataforseo.com."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-ideas-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.ok_resp = {"tasks": [{"status_code": 20000, "result": [{"items": []}]}]}

    def test_ideas_sends_keywords_as_array(self) -> None:
        args = dfs.build_parser().parse_args(["--out", str(self.tmp), "ideas", "минеральная вата"])
        with mock.patch.object(dfs, "fetch", return_value=self.ok_resp) as fetched:
            dfs.cmd_ideas("b64", args)
        payload = fetched.call_args.args[2]
        self.assertEqual(payload["keywords"], ["минеральная вата"])
        self.assertNotIn("keyword", payload)

    def test_related_still_sends_singular_keyword(self) -> None:
        args = dfs.build_parser().parse_args(["--out", str(self.tmp), "related", "минеральная вата"])
        with mock.patch.object(dfs, "fetch", return_value=self.ok_resp) as fetched:
            dfs.cmd_related("b64", args)
        payload = fetched.call_args.args[2]
        self.assertEqual(payload["keyword"], "минеральная вата")
        self.assertNotIn("keywords", payload)


def fake_response(body: bytes):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def read(self):
            return body

    return FakeResponse()


class NetworkErrorTest(unittest.TestCase):
    """T-059/F-13 (круг 2): сетевые ошибки и битый JSON поднимают ApiCallError
    (не sys.exit) из call() — так fetch() может записать расход до выхода."""

    def test_url_error_raises_api_call_error(self) -> None:
        with mock.patch.object(dfs.urllib.request, "urlopen",
                               side_effect=dfs.urllib.error.URLError("no route to host")):
            with self.assertRaises(dfs.ApiCallError):
                dfs.call("b64", "some/path", {"k": 1})

    def test_timeout_raises_api_call_error(self) -> None:
        with mock.patch.object(dfs.urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(dfs.ApiCallError):
                dfs.call("b64", "some/path", {"k": 1})

    def test_http_error_raises_api_call_error(self) -> None:
        import io
        err = dfs.urllib.error.HTTPError("url", 500, "Internal Server Error", {}, io.BytesIO(b"boom"))
        with mock.patch.object(dfs.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(dfs.ApiCallError):
                dfs.call("b64", "some/path", {"k": 1})

    def test_malformed_json_response_raises_api_call_error(self) -> None:
        with mock.patch.object(dfs.urllib.request, "urlopen", return_value=fake_response(b"{not valid json")):
            with self.assertRaises(dfs.ApiCallError):
                dfs.call("b64", "some/path", {"k": 1})

    def test_json_null_body_raises_api_call_error(self) -> None:
        """Гейт круга 2: валидный JSON, но не объект (`null`) — раньше это
        не было исключением вообще, а падало дальше в response_cost()
        голым AttributeError мимо перехвата."""
        with mock.patch.object(dfs.urllib.request, "urlopen", return_value=fake_response(b"null")):
            with self.assertRaises(dfs.ApiCallError):
                dfs.call("b64", "some/path", {"k": 1})

    def test_json_array_body_raises_api_call_error(self) -> None:
        with mock.patch.object(dfs.urllib.request, "urlopen", return_value=fake_response(b"[]")):
            with self.assertRaises(dfs.ApiCallError):
                dfs.call("b64", "some/path", {"k": 1})


class ResponseCostTest(unittest.TestCase):
    """T-059 (доп. находка после второго круга гейта): `response_cost()` не была
    затронута первым проходом value-level hardening — поле `cost` из ответа API
    подвержено ровно тому же классу риска (NaN/Infinity/отрицательное проходит
    isinstance-эквивалент `float(...)` без ошибки и портит spent_usd) до того,
    как что-либо попадёт в load_usage()/save_usage()."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-cost-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.args = dfs.build_parser().parse_args(["--out", str(self.tmp), "volume", "vata"])

    def test_missing_cost_field_is_honest_failure_not_free(self) -> None:
        """R-5 (независимый гейт, круг 2): response_cost() обслуживает только
        платные методы (вызывается исключительно из fetch()) — единственный
        бесплатный метод, `balance`, идёт через call() напрямую и никогда не
        доходит до response_cost(). Поэтому «нет поля cost» здесь — не
        легитимный бесплатный случай, а сюрприз в контракте API, и он обязан
        падать так же честно, как NaN/Infinity/отрицательное."""
        with self.assertRaises(ValueError):
            dfs.response_cost({"status_code": 20000})

    def test_normal_cost_passes_through(self) -> None:
        self.assertEqual(dfs.response_cost({"cost": 0.05}), 0.05)

    def test_nan_cost_is_honest_failure_not_silent_zero(self) -> None:
        with self.assertRaises(ValueError):
            dfs.response_cost({"cost": float("nan")})

    def test_negative_cost_is_honest_failure(self) -> None:
        with self.assertRaises(ValueError):
            dfs.response_cost({"cost": -1.0})

    def test_non_numeric_cost_is_honest_failure(self) -> None:
        with self.assertRaises(ValueError):
            dfs.response_cost({"cost": "много"})

    def test_poisoned_api_cost_still_exits_without_corrupting_spent_usd(self) -> None:
        """F-13 (независимый прогон 2026-09-06): NaN в cost всё ещё поднимает
        SystemExit (спорную сумму не заносим), но сам платный вызов теперь
        обязан остаться в учёте — деньги списаны фактом вызова, а не фактом
        валидного ответа. Раньше (T-059) fetch() падал ДО save_usage() и
        _usage.json не появлялся вовсе — ровно так вызов терялся из истории."""
        bad = {"status_code": 20000, "cost": float("nan"),
               "tasks": [{"status_code": 20000, "result": [{"keyword": "x"}]}]}
        with mock.patch.object(dfs, "call", return_value=bad):
            with self.assertRaises(SystemExit):
                dfs.fetch("b64", "some/path", {"k": 1}, self.args)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["calls"], 1, "платный вызов обязан быть учтён, даже если сумма неизвестна")
        self.assertEqual(usage["spent_usd"], 0.0, "неизвестную сумму не приплюсовываем — NaN не проходит арифметику")
        self.assertEqual(usage.get("cost_unknown_calls"), 1, "непригодность cost отражена отдельным полем")


class DistillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-dfs-md-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_volume_md_is_sorted_by_search_volume(self) -> None:
        args = dfs.build_parser().parse_args(
            ["--out", str(self.tmp), "--md", "volume", "vata", "vata cena"])
        with mock.patch.object(dfs, "call", return_value=volume_response()):
            with mock.patch("builtins.print") as printed:
                dfs.cmd_volume("b64", args)
        table = "\n".join(str(c.args[0]) for c in printed.call_args_list if c.args)
        self.assertIn("| ключ | частотность | конкуренция | CPC |", table)
        self.assertLess(table.index("vata cena"), table.index("| vata |"),
                        "строки должны идти по убыванию частотности")


if __name__ == "__main__":
    unittest.main()
