#!/usr/bin/env python3
"""R2-4 (независимый гейт, круг 3): api.keys.so квоту тратят ТРИ клиента
(keyso-fetch.py, competitor-discovery.py, keyso-save.py), но считал её
раньше только один. Эти тесты проверяют, что все три вызывают ОДИН и тот же
общий bump_counter() на один and тот же каталог — счётчик суммирует расход
по-настоящему, а не только вызовы через keyso-fetch.py.

Мутация: убери вызов bump_counter() в любом из трёх клиентов — тест этого
клиента обязан покраснеть (requests не растёт после его "запроса")."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(filename: str, modname: str):
    spec = importlib.util.spec_from_file_location(modname, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


keyso_fetch = load_module("keyso-fetch.py", "keyso_fetch_shared")
competitor_discovery = load_module("competitor-discovery.py", "competitor_discovery_shared")
keyso_save = load_module("keyso-save.py", "keyso_save_shared")


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


class SharedKeysoCounterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-keyso-shared-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self._old_cwd = pathlib.Path.cwd()
        import os
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, self._old_cwd)

    def _requests(self) -> int:
        f = self.tmp / "seo" / "research" / "keyso" / "_usage.json"
        if not f.exists():
            return 0
        return json.loads(f.read_text(encoding="utf-8")).get("requests", 0)

    def test_keyso_fetch_call_bumps_shared_counter(self) -> None:
        with mock.patch.object(keyso_fetch.urllib.request, "urlopen",
                               return_value=FakeResponse(b'{"data": []}')):
            keyso_fetch.call("token", "/report/simple/keyword_dashboard", {"keyword": "x", "base": "msk"})
        self.assertEqual(self._requests(), 1)

    def test_competitor_discovery_call_bumps_the_same_counter(self) -> None:
        with mock.patch.object(competitor_discovery.urllib.request, "urlopen",
                               return_value=FakeResponse(b'{"data": []}')):
            competitor_discovery.fetch_top("token", "kw", "msk", ttl=0)
        self.assertEqual(self._requests(), 1)

    def test_keyso_save_call_bumps_the_same_counter(self) -> None:
        with mock.patch.object(keyso_save.urllib.request, "urlopen",
                               return_value=FakeResponse(b'{"ok": true}')):
            keyso_save.post("token", "/report/group", {"domains": ["a.ru"]})
        self.assertEqual(self._requests(), 1)

    def test_all_three_accumulate_into_one_total(self) -> None:
        with mock.patch.object(keyso_fetch.urllib.request, "urlopen",
                               return_value=FakeResponse(b'{"data": []}')):
            keyso_fetch.call("token", "/x", {})
        with mock.patch.object(competitor_discovery.urllib.request, "urlopen",
                               return_value=FakeResponse(b'{"data": []}')):
            competitor_discovery.fetch_top("token", "kw2", "msk", ttl=0)
        with mock.patch.object(keyso_save.urllib.request, "urlopen",
                               return_value=FakeResponse(b'{"ok": true}')):
            keyso_save.post("token", "/report/group", {"domains": ["b.ru"]})
        self.assertEqual(self._requests(), 3, "все три клиента обязаны суммироваться в один общий счётчик")


if __name__ == "__main__":
    unittest.main()
