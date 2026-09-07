#!/usr/bin/env python3
"""Tests for keyso-fetch.py's usage counter (T-066: third candidate found while
migrating the money-stop class onto scripts/seo_cycle_core/usage_ledger.py).

Keys.so is a flat-subscription API (no per-call $ cost), so there is no
budget/stop to migrate here — only a request-count ledger with the exact same
corruption-swallowing (`except Exception: pass`), non-atomic write, and no
concurrency lock that F-12 found in spyfu-fetch.py. These tests cover that.
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

spec = importlib.util.spec_from_file_location("keyso_fetch", SCRIPTS / "keyso-fetch.py")
keyso = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keyso)

from seo_cycle_core import usage_ledger as _usage_ledger_module  # noqa: E402


class TtlArgTest(unittest.TestCase):
    """R-4 (гейт круга 2): --ttl оставался голым type=float у всех трёх
    клиентов, включая этот."""

    def test_nan_is_rejected_at_parse_time(self) -> None:
        with mock.patch.object(sys, "argv", ["keyso-fetch.py", "keyword-info", "x", "--ttl", "nan"]):
            with self.assertRaises(SystemExit):
                keyso.main()

    def test_negative_is_rejected_at_parse_time(self) -> None:
        with mock.patch.object(sys, "argv", ["keyso-fetch.py", "keyword-info", "x", "--ttl", "-1"]):
            with self.assertRaises(SystemExit):
                keyso.main()


class BumpUsageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-keyso-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_first_bump_creates_ledger(self) -> None:
        n = keyso.bump_usage(self.tmp, 1)
        self.assertEqual(n, 1)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["requests"], 1)

    def test_bumps_accumulate_within_month(self) -> None:
        keyso.bump_usage(self.tmp, 1)
        n = keyso.bump_usage(self.tmp, 1)
        self.assertEqual(n, 2)

    def test_stale_month_resets_counter(self) -> None:
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": "2000-01", "requests": 999}), encoding="utf-8")
        n = keyso.bump_usage(self.tmp, 1)
        self.assertEqual(n, 1, "смена месяца — легитимный сброс, а не порча файла")

    def test_corrupt_json_does_not_crash_and_resets(self) -> None:
        """Раньше `except Exception: pass` тихо проглатывал ЛЮБУЮ порчу и
        трактовал как «0 запросов» без единого слова в stderr. Теперь — то же
        поведение (счётчик не блокирует работу), но с явным предупреждением."""
        (self.tmp / "_usage.json").write_text("{ не json вообще", encoding="utf-8")
        with mock.patch("sys.stderr") as fake_stderr:
            n = keyso.bump_usage(self.tmp, 1)
        self.assertEqual(n, 1)
        printed = "".join(str(c) for c in fake_stderr.write.call_args_list)
        self.assertIn("повреждён", printed, "порча файла обязана быть видимой, не тихой")

    def test_nan_requests_is_treated_as_corrupt_and_reset(self) -> None:
        (self.tmp / "_usage.json").write_text(
            json.dumps({"month": keyso.current_month(), "requests": float("nan")}),
            encoding="utf-8")
        n = keyso.bump_usage(self.tmp, 1)
        self.assertEqual(n, 1, "NaN в requests не должен складываться дальше (NaN+1=NaN)")

    def test_write_failure_leaves_no_half_file(self) -> None:
        keyso.bump_usage(self.tmp, 1)
        with mock.patch("json.dump", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                keyso.bump_usage(self.tmp, 1)
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["requests"], 1, "старый файл не должен быть тронут при обрыве записи")
        leftovers = [p for p in self.tmp.iterdir() if p.name.startswith(".")]
        self.assertEqual(leftovers, [], "временный файл должен быть удалён при ошибке записи")

    def test_parallel_bumps_do_not_lose_either_increment(self) -> None:
        """Раньше запись была прямым write_text без блокировки — два
        параллельных процесса читают один и тот же старый файл, и последняя
        запись побеждает, теряя чужой инкремент."""
        entered_first = threading.Event()
        release_first = threading.Event()
        call_count = {"n": 0}
        count_lock = threading.Lock()

        # R2-4 (независимый гейт, круг 3): bump_usage() теперь делегирует в
        # общий bump_counter() (seo_cycle_core.usage_ledger), который вызывает
        # СВОЙ модульный load_usage — патч на keyso._shared_load_usage больше
        # не перехватывает этот путь, патчим на уровне общего модуля.
        real_shared_load = _usage_ledger_module.load_usage

        def patched_load(out_dir, fields, **kwargs):
            with count_lock:
                call_count["n"] += 1
                is_first = call_count["n"] == 1
            # Читаем СЕЙЧАС (пока файл ещё старый), а блокируем уже держа
            # прочитанное значение — так без внешней блокировки (usage_lock)
            # второй поток успевает прочитать тот же старый файл и потерять
            # инкремент первого при перезаписи; с блокировкой второй поток
            # вообще не доходит до этого вызова, пока первый не завершит save.
            result = real_shared_load(out_dir, fields, **kwargs)
            if is_first:
                entered_first.set()
                release_first.wait(timeout=2)
            return result

        errors: list[BaseException] = []

        def worker() -> None:
            try:
                keyso.bump_usage(self.tmp, 1)
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        # Оба потока используют один и тот же патч через замыкание — общий
        # call_count достаточно, чтобы первый вошедший держал flock() занятым.
        with mock.patch.object(_usage_ledger_module, "load_usage", side_effect=patched_load):
            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)
            t1.start()
            self.assertTrue(entered_first.wait(timeout=2))
            t2.start()
            time.sleep(0.15)
            release_first.set()
            t1.join(timeout=3)
            t2.join(timeout=3)

        self.assertFalse(errors, f"потоки упали: {errors}")
        usage = json.loads((self.tmp / "_usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["requests"], 2, "без блокировки один из двух "
                                                 "инкрементов был бы потерян")


if __name__ == "__main__":
    unittest.main()
