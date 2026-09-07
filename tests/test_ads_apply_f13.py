#!/usr/bin/env python3
"""R2-2 (независимый гейт, круг 3): ads-apply.py объявлялся исполнителем
«проверен прогоном — уже безопасен» без единого прогона этой ветки. Гейт
показал обратное: `apply_direct()` ловил исключения ПЕРЕЧНЕМ типов
(URLError/KeyError/JSONDecodeError) — ConnectionResetError/TimeoutError/
ValueError и всё остальное, что может прилететь при чтении тела уже
отправленного запроса, уходили из apply_direct() ЦЕЛИКОМ голым traceback'ом,
а операции ПОСЛЕ упавшей не выполнялись и не попадали в results вовсе.

Эти тесты проверяют apply_direct() напрямую (без --live main(), которому
нужен полный approval-gate/env), потому что именно эта функция — место
дефекта."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("ads_apply_f13", SCRIPTS / "ads-apply.py")
apply_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply_mod)


OPERATIONS = [
    {"op": "create_campaign", "name": "camp-1"},
    {"op": "create_ad_group", "campaign": "camp-1", "name": "group-1"},
    {"op": "add_keyword", "ad_group": "group-1", "text": "kw1"},
]


class ApplyDirectExoticExceptionTest(unittest.TestCase):
    """Мутация: замени `except Exception as exc:` обратно на перечень типов
    (URLError, KeyError, JSONDecodeError) — каждый тест ниже обязан
    покраснеть (apply_direct() поднимет исключение вместо возврата results)."""

    def _run_with_second_call_raising(self, exc: BaseException) -> list:
        calls = {"n": 0}

        def fake_direct_request(host, service, payload):
            calls["n"] += 1
            if calls["n"] == 2:
                raise exc
            return {"result": {"AddResults": [{"Id": 111}]}}

        with mock.patch.object(apply_mod, "direct_request", side_effect=fake_direct_request):
            return apply_mod.apply_direct(OPERATIONS, sandbox=True)

    def test_connection_reset_marks_op_failed_and_continues(self) -> None:
        results = self._run_with_second_call_raising(ConnectionResetError("connection reset by peer"))
        self.assertEqual(len(results), 3, "все три операции обязаны попасть в results, включая упавшую и следующую")
        self.assertEqual(results[0]["status"], "ok")
        self.assertEqual(results[1]["status"], "failed")
        self.assertIn("ConnectionResetError", results[1]["error"])
        # третья операция (add_keyword) зависит от group_id, которого не будет —
        # но она обязана хотя бы ПОПАСТЬ в results, а не пропасть вместе с процессом.
        self.assertIn(results[2]["status"], ("skipped", "failed"))

    def test_timeout_error_marks_op_failed_and_continues(self) -> None:
        results = self._run_with_second_call_raising(TimeoutError("timed out"))
        self.assertEqual(len(results), 3)
        self.assertEqual(results[1]["status"], "failed")
        self.assertIn("TimeoutError", results[1]["error"])

    def test_value_error_marks_op_failed_and_continues(self) -> None:
        results = self._run_with_second_call_raising(ValueError("bad value"))
        self.assertEqual(len(results), 3)
        self.assertEqual(results[1]["status"], "failed")
        self.assertIn("ValueError", results[1]["error"])


class WriteAheadBeforeApplyLoopTest(unittest.TestCase):
    """R3-1 (независимый гейт, круг 4): круг 3 писало расход `ledger_record()`
    ПОСЛЕ цикла `apply_direct()` целиком (`requests=len(operations)`) — любое
    исключение внутри цикла (в т.ч. KeyboardInterrupt/SystemExit, которые не
    ловит НИ ОДИН except) уносило выполнение мимо записи навсегда, теряя ВСЕ
    уже выполненные (и оплаченные) операции прогона, не только последнюю.
    Фикс — write-ahead: запись на всю пачку операций ДО цикла.

    Мутация: перенеси `ledger_record(...)` обратно после `apply_direct(...)`
    — оба теста ниже обязаны покраснеть (recorded будет пуст, потому что
    apply_direct подменён на исключение и main() никогда не дойдёт до записи)."""

    def setUp(self) -> None:
        import shutil
        import tempfile
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-ads-apply-f13-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: ads-apply-f13\n  url: https://example.com\n"
            "region_profile: ru\nads:\n  enabled: true\n  policy: approval_only\n"
            "  yandex_direct:\n    enabled: true\n    sandbox: true\n",
            encoding="utf-8",
        )
        draft = {"platform": "yandex_direct", "campaigns": [
            {"name": "camp-1", "channel": "search", "budget_daily": 0, "ad_groups": [
                {"name": "group-1", "keywords": [{"text": "kw1", "match_type": "phrase"}], "ads": []}
            ], "negatives": []},
        ]}
        self.draft_path = self.tmp / "draft.json"
        self.draft_path.write_text(json.dumps(draft), encoding="utf-8")
        self._old_cwd = pathlib.Path.cwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self._old_cwd)

    def _run_live_with_apply_direct_raising(self, exc: BaseException) -> list:
        recorded = []
        argv = ["ads-apply.py", "--draft", str(self.draft_path), "--ticket", "T-1",
                "--live", "--allow-write"]
        with mock.patch.object(apply_mod, "ticket_status", return_value="approved"), \
             mock.patch.object(apply_mod, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(apply_mod, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(apply_mod, "ledger_record",
                               side_effect=lambda *a, **k: recorded.append(k) or True), \
             mock.patch.object(apply_mod, "apply_direct", side_effect=exc), \
             mock.patch.object(apply_mod, "notify"), \
             mock.patch.object(sys, "argv", argv):
            with self.assertRaises(type(exc)):
                apply_mod.main()
        return recorded

    def test_keyboard_interrupt_during_apply_loop_is_already_recorded(self) -> None:
        recorded = self._run_live_with_apply_direct_raising(KeyboardInterrupt())
        self.assertTrue(recorded, "запись расхода на всю пачку операций обязана произойти ДО цикла apply_direct()")
        self.assertEqual(recorded[0].get("requests"), 3, "вся пачка операций (3), а не только успевшие")

    def test_system_exit_during_apply_loop_is_already_recorded(self) -> None:
        recorded = self._run_live_with_apply_direct_raising(SystemExit(1))
        self.assertTrue(recorded)
        self.assertEqual(recorded[0].get("requests"), 3)

    def test_ledger_record_false_refuses_the_apply(self) -> None:
        """R3-3: отказ записи обязан остановить apply ДО первой операции."""
        apply_direct_calls = []
        argv = ["ads-apply.py", "--draft", str(self.draft_path), "--ticket", "T-1",
                "--live", "--allow-write"]
        with mock.patch.object(apply_mod, "ticket_status", return_value="approved"), \
             mock.patch.object(apply_mod, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(apply_mod, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(apply_mod, "ledger_record", return_value=False), \
             mock.patch.object(apply_mod, "apply_direct",
                               side_effect=lambda *a, **k: apply_direct_calls.append(1) or []), \
             mock.patch.object(sys, "argv", argv):
            rc = apply_mod.main()
        self.assertNotEqual(rc, 0)
        self.assertFalse(apply_direct_calls, "запись не удалась — apply обязан быть отказан ДО первой операции")


if __name__ == "__main__":
    unittest.main()
