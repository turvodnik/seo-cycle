#!/usr/bin/env python3
"""F-13 for the SECOND money stop (T-066 R-2): yandex-direct-fetch.py and
google-ads-fetch.py preflight through usage-ledger.py, make a live paid/quota
call, and only recorded the spend on the SUCCESS path — an exception from the
live call (`return 1` before `ledger_record()`) silently dropped the record
even though the quota-limited API call had already gone out. Reproduced and
fixed the same way as dataforseo-fetch.py/spyfu-fetch.py: the record must
happen BEFORE the live call (write-ahead), not after.

R3-3 (round-4 independent gate): write-ahead only protects the spend if the
record actually landed. `ledger_record()` returns `bool` for exactly this —
these callers must refuse the paid call when it returns `False`, not just
proceed with an unrecorded call and exit 0.

R3-4 (round-4 gate): round 3 promised a second "clarifying" record with
`requests=0` on failure — it never fired (`usage-ledger.py record` refuses
with zero metrics) and was dead code disagreeing with the CHANGELOG. There is
now only ONE record call (write-ahead, before the live call); a failure of
the live call itself only logs a warning, no second ledger write.
"""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

CFG = """project:
  name: ads-f13-test
  url: https://example.com
region_profile: ru
ads:
  enabled: true
  yandex_direct:
    enabled: true
    sandbox: true
  google_ads:
    enabled: true
"""


def load_module(filename: str, modname: str):
    spec = importlib.util.spec_from_file_location(modname, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


yandex = load_module("yandex-direct-fetch.py", "yandex_direct_fetch_f13")
gads = load_module("google-ads-fetch.py", "google_ads_fetch_f13")


class YandexDirectF13Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-yandex-f13-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")
        self._old_cwd = pathlib.Path.cwd()
        import os
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self._old_cwd)

    def test_live_fetch_failure_still_recorded_before_the_call(self) -> None:
        recorded = []
        with mock.patch.object(yandex, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(yandex, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(yandex, "ledger_record",
                               side_effect=lambda *a, **k: recorded.append(k) or True), \
             mock.patch.object(yandex, "live_fetch", side_effect=RuntimeError("Direct API 500")), \
             mock.patch.object(sys, "argv", ["yandex-direct-fetch.py", "--report", "campaigns", "--live"]):
            rc = yandex.main()
        self.assertEqual(rc, 1)
        self.assertTrue(recorded, "ledger_record() обязан быть вызван до live_fetch()")
        self.assertEqual(len(recorded), 1, "R3-4: второй (уточняющей) записи при неудаче быть не должно")
        self.assertEqual(recorded[0].get("requests"), 1, "попытка обязана быть записана ДО live_fetch()")

    def test_ledger_write_ahead_precedes_live_fetch_call(self) -> None:
        """R2-2 (круг 3): запись обязана произойти ДО live_fetch(), а не
        только после провала — иначе SIGKILL/os._exit ровно между вызовом и
        функцией fetch всё ещё теряет попытку. Мутация: перенеси
        ledger_record() после live_fetch() — этот тест обязан покраснеть
        (order будет ["live_fetch"] без предшествующего "record")."""
        order = []
        with mock.patch.object(yandex, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(yandex, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(yandex, "ledger_record",
                               side_effect=lambda *a, **k: order.append("record") or True), \
             mock.patch.object(yandex, "live_fetch", side_effect=lambda *a, **k: order.append("live_fetch") or {"ok": True}), \
             mock.patch.object(yandex, "save_raw", return_value={"dated": self.tmp / "d.json", "latest": self.tmp / "l.json"}), \
             mock.patch.object(sys, "argv", ["yandex-direct-fetch.py", "--report", "campaigns", "--live"]):
            yandex.main()
        self.assertEqual(order[0], "record", "запись в леджер обязана произойти ДО live_fetch()")

    def test_live_fetch_success_still_records_as_before(self) -> None:
        recorded = []
        with mock.patch.object(yandex, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(yandex, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(yandex, "ledger_record",
                               side_effect=lambda *a, **k: recorded.append(k) or True), \
             mock.patch.object(yandex, "live_fetch", return_value={"ok": True}), \
             mock.patch.object(yandex, "save_raw", return_value={"dated": self.tmp / "d.json", "latest": self.tmp / "l.json"}), \
             mock.patch.object(sys, "argv", ["yandex-direct-fetch.py", "--report", "campaigns", "--live"]):
            yandex.main()
        self.assertTrue(recorded)

    def test_ledger_record_false_refuses_the_paid_call(self) -> None:
        """R3-3 (независимый гейт, круг 4): запись расхода не удалась (диск
        только на чтение, нет места и т.п.) — раньше это только печатало
        WARNING внутри ledger_record() и live_fetch() всё равно вызывался.
        Теперь False обязан остановить выполнение ДО live_fetch()."""
        live_fetch_calls = []
        with mock.patch.object(yandex, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(yandex, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(yandex, "ledger_record", return_value=False), \
             mock.patch.object(yandex, "live_fetch", side_effect=lambda *a, **k: live_fetch_calls.append(1) or {"ok": True}), \
             mock.patch.object(sys, "argv", ["yandex-direct-fetch.py", "--report", "campaigns", "--live"]):
            rc = yandex.main()
        self.assertNotEqual(rc, 0)
        self.assertFalse(live_fetch_calls, "запись не удалась — платный вызов обязан быть отказан")


class GoogleAdsF13Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-gads-f13-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")
        self._old_cwd = pathlib.Path.cwd()
        import os
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self._old_cwd)

    def test_gaql_search_failure_still_recorded_before_the_call(self) -> None:
        recorded = []
        with mock.patch.object(gads, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(gads, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(gads, "ledger_record",
                               side_effect=lambda *a, **k: recorded.append(k) or True), \
             mock.patch.object(gads, "gaql_search", side_effect=KeyError("results")), \
             mock.patch.object(sys, "argv", ["google-ads-fetch.py", "--report", "campaigns", "--live"]):
            rc = gads.main()
        self.assertEqual(rc, 1)
        self.assertTrue(recorded, "ledger_record() обязан быть вызван до gaql_search()")
        self.assertEqual(len(recorded), 1, "R3-4: второй (уточняющей) записи при неудаче быть не должно")
        self.assertEqual(recorded[0].get("requests"), 1, "попытка обязана быть записана ДО gaql_search()")

    def test_ledger_write_ahead_precedes_gaql_search_call(self) -> None:
        order = []
        with mock.patch.object(gads, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(gads, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(gads, "ledger_record",
                               side_effect=lambda *a, **k: order.append("record") or True), \
             mock.patch.object(gads, "gaql_search", side_effect=lambda *a, **k: order.append("gaql_search") or {"ok": True}), \
             mock.patch.object(sys, "argv", ["google-ads-fetch.py", "--report", "campaigns", "--live"]):
            gads.main()
        self.assertEqual(order[0], "record", "запись в леджер обязана произойти ДО gaql_search()")

    def test_ledger_record_false_refuses_the_paid_call(self) -> None:
        gaql_search_calls = []
        with mock.patch.object(gads, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(gads, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(gads, "ledger_record", return_value=False), \
             mock.patch.object(gads, "gaql_search", side_effect=lambda *a, **k: gaql_search_calls.append(1) or {"ok": True}), \
             mock.patch.object(sys, "argv", ["google-ads-fetch.py", "--report", "campaigns", "--live"]):
            rc = gads.main()
        self.assertNotEqual(rc, 0)
        self.assertFalse(gaql_search_calls, "запись не удалась — платный вызов обязан быть отказан")


if __name__ == "__main__":
    unittest.main()
