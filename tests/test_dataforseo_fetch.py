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


class NetworkErrorTest(unittest.TestCase):
    """T-059: сетевые ошибки и битый JSON — управляемый sys.exit, не голый traceback."""

    def test_url_error_gives_clean_exit(self) -> None:
        with mock.patch.object(dfs.urllib.request, "urlopen",
                               side_effect=dfs.urllib.error.URLError("no route to host")):
            with self.assertRaises(SystemExit) as ctx:
                dfs.call("b64", "some/path", {"k": 1})
        self.assertTrue(ctx.exception.code)

    def test_timeout_gives_clean_exit(self) -> None:
        with mock.patch.object(dfs.urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaises(SystemExit) as ctx:
                dfs.call("b64", "some/path", {"k": 1})
        self.assertTrue(ctx.exception.code)

    def test_malformed_json_response_gives_clean_exit(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return False

            def read(self):
                return b"{not valid json"

        with mock.patch.object(dfs.urllib.request, "urlopen", return_value=FakeResponse()):
            with self.assertRaises(SystemExit) as ctx:
                dfs.call("b64", "some/path", {"k": 1})
        self.assertTrue(ctx.exception.code)


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
