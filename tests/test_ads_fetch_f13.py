#!/usr/bin/env python3
"""F-13 for the SECOND money stop (T-066 R-2): yandex-direct-fetch.py and
google-ads-fetch.py preflight through usage-ledger.py, make a live paid/quota
call, and only recorded the spend on the SUCCESS path — an exception from the
live call (`return 1` before `ledger_record()`) silently dropped the record
even though the quota-limited API call had already gone out. Reproduced and
fixed the same way as dataforseo-fetch.py/spyfu-fetch.py: the record must
happen on the failure branch too.
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

    def test_live_fetch_failure_still_records_the_attempt(self) -> None:
        recorded = []
        with mock.patch.object(yandex, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(yandex, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(yandex, "ledger_record", side_effect=lambda *a, **k: recorded.append(k)), \
             mock.patch.object(yandex, "live_fetch", side_effect=RuntimeError("Direct API 500")), \
             mock.patch.object(sys, "argv", ["yandex-direct-fetch.py", "--report", "campaigns", "--live"]):
            rc = yandex.main()
        self.assertEqual(rc, 1)
        self.assertTrue(recorded, "ledger_record() обязан быть вызван даже при провале live_fetch()")
        self.assertIn("FAILED", recorded[0].get("note", ""))

    def test_live_fetch_success_still_records_as_before(self) -> None:
        recorded = []
        with mock.patch.object(yandex, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(yandex, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(yandex, "ledger_record", side_effect=lambda *a, **k: recorded.append(k)), \
             mock.patch.object(yandex, "live_fetch", return_value={"ok": True}), \
             mock.patch.object(yandex, "save_raw", return_value={"dated": self.tmp / "d.json", "latest": self.tmp / "l.json"}), \
             mock.patch.object(sys, "argv", ["yandex-direct-fetch.py", "--report", "campaigns", "--live"]):
            yandex.main()
        self.assertTrue(recorded)
        self.assertNotIn("FAILED", recorded[0].get("note", ""))


class GoogleAdsF13Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-gads-f13-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")
        self._old_cwd = pathlib.Path.cwd()
        import os
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self._old_cwd)

    def test_gaql_search_failure_still_records_the_attempt(self) -> None:
        recorded = []
        with mock.patch.object(gads, "env_status", return_value={"present": True, "missing": []}), \
             mock.patch.object(gads, "ledger_preflight", return_value=(True, "ok")), \
             mock.patch.object(gads, "ledger_record", side_effect=lambda *a, **k: recorded.append(k)), \
             mock.patch.object(gads, "gaql_search", side_effect=KeyError("results")), \
             mock.patch.object(sys, "argv", ["google-ads-fetch.py", "--report", "campaigns", "--live"]):
            rc = gads.main()
        self.assertEqual(rc, 1)
        self.assertTrue(recorded, "ledger_record() обязан быть вызван даже при провале gaql_search()")
        self.assertIn("FAILED", recorded[0].get("note", ""))


if __name__ == "__main__":
    unittest.main()
