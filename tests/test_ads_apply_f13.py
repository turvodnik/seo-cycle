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


if __name__ == "__main__":
    unittest.main()
