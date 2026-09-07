#!/usr/bin/env python3
"""T-089 (F-1): client x signal write-ahead matrix, plus the structural
single-choke-point guard (seo_cycle_core.spend_guard).

Context: the 2.2.0 hostile QA round found that `google-nlp-audit.py` was the
sixth paid client and the only one still recording spend AFTER the paid
call, not before — so SIGINT/SIGTERM/SIGKILL during the call lost the spend
entirely, with no second line of defence either. The fix here is two-layered:

1. Give google-nlp-audit.py the same write-ahead ordering the other five
   clients already had (T-066).
2. Make "a paid call exists without a preceding, successful write-ahead
   record" a structural impossibility (`seo_cycle_core.spend_guard`), so a
   future SEVENTH gap does not depend on someone remembering to check.

Every signal scenario below runs the REAL client code in a separate OS
process — not a mocked exception standing in for a signal — so the outbound
network primitive is replaced (the only thing patched), but the exact code
that runs write-ahead-then-network runs for real, and the interrupt is a
real `os.kill()`, exactly the QA round's repro. `t089_signal_target.py`
explicitly resets SIGINT to its default disposition first (the QA round's
own stand had a false-positive here: a backgrounded shell inherits
SIGINT=SIG_IGN, so `kill -INT` silently does nothing and every client looks
protected)."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
HARNESS = pathlib.Path(__file__).resolve().parent / "helpers" / "t089_signal_target.py"

try:
    import requests  # noqa: F401
    import bs4  # noqa: F401
    from google.oauth2 import service_account  # noqa: F401
    _GOOGLE_NLP_DEPS_OK = True
except ImportError:
    _GOOGLE_NLP_DEPS_OK = False


def _spend_recorded(out_dir: pathlib.Path, client: str) -> bool:
    """True iff the write-ahead record for `client` is on disk. Each client
    keeps its own ledger shape — this reads whichever one applies, the same
    way its own script/tests do (no shared assumption to keep the matrix
    honest about six genuinely different implementations, T-066/T-089)."""
    if client == "dataforseo":
        p = out_dir / "_usage.json"
        return p.exists() and json.loads(p.read_text())["calls"] >= 1
    if client == "spyfu":
        p = out_dir / "_usage.json"
        return p.exists() and json.loads(p.read_text()).get("cost_unknown_calls", 0) >= 1
    if client == "google_nlp":
        files = list(out_dir.glob("usage-*.json"))
        if not files:
            return False
        data = json.loads(files[0].read_text())
        return data.get("features", {}).get("analyzeEntities", 0) >= 1
    if client in ("ads_apply", "yandex_direct", "google_ads"):
        p = out_dir / "seo" / "usage" / "usage-ledger.jsonl"
        return p.exists() and len(p.read_text().splitlines()) >= 1
    raise AssertionError(client)


class WriteAheadSignalMatrixTest(unittest.TestCase):
    """Матрица «клиент × сигнал» (F-1 T-089): расход обязан быть записан на
    диске ДО того, как сигнал успевает прервать выполнение — для всех шести
    известных платных клиентов, не только для пяти, что были закрыты T-066."""

    CLIENTS = ["dataforseo", "spyfu", "google_nlp", "ads_apply", "yandex_direct", "google_ads"]
    SIGNALS = [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-t089-matrix-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def _run_and_kill(self, client: str, out_dir: pathlib.Path, sig: int) -> None:
        proc = subprocess.Popen(
            [sys.executable, str(HARNESS), client, str(out_dir)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            deadline = time.time() + 15
            line = ""
            while time.time() < deadline:
                line = proc.stdout.readline()
                if line.strip() == "STARTED":
                    break
            else:
                proc.kill()
                proc.wait(timeout=5)
                self.fail(f"{client}: target never printed STARTED "
                          f"(stderr: {proc.stderr.read()!r})")
            # The write-ahead record is guaranteed on disk by the time
            # STARTED is printed (the mocked network primitive prints it as
            # its first action, after armed_spend()'s write_ahead() has
            # already run and returned True) — the sleep below is slack for
            # process scheduling, not part of the correctness argument.
            os.kill(proc.pid, sig)
            proc.wait(timeout=10)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()

    def _check_one(self, client: str, sig: int) -> None:
        if client == "google_nlp" and not _GOOGLE_NLP_DEPS_OK:
            self.skipTest("google-nlp-audit.py optional deps missing (requests/bs4/google-auth)")
        out_dir = self.tmp / f"{client}-{sig}"
        out_dir.mkdir()
        self._run_and_kill(client, out_dir, sig)
        self.assertTrue(
            _spend_recorded(out_dir, client),
            f"{client}: spend NOT recorded after signal {signal.Signals(sig).name} — "
            f"write-ahead did not survive the interrupt (F-1 class)",
        )


def _add_matrix_tests() -> None:
    for client in WriteAheadSignalMatrixTest.CLIENTS:
        for sig in WriteAheadSignalMatrixTest.SIGNALS:
            def _test(self, client=client, sig=sig) -> None:
                self._check_one(client, sig)
            _test.__name__ = f"test_{client}_{signal.Signals(sig).name.lower()}"
            setattr(WriteAheadSignalMatrixTest, _test.__name__, _test)


_add_matrix_tests()


class PositiveControlTest(unittest.TestCase):
    """Стенд может лгать двумя способами: (a) он всегда пишет "защищено",
    даже когда клиент незащищён (ложно-положительный — ровно то, что было в
    первой версии QA-стенда на Ctrl-C, T-089 контекст пакета), или (b) он
    никогда не находит запись, даже когда клиент честно её оставил. Обе
    стороны проверены здесь напрямую, а не только предположением "раз матрица
    выше зелёная — значит стенд исправен"."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-t089-control-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_sigint_is_not_silently_ignored_by_the_harness(self) -> None:
        """Ровно репро отчёта: SIGINT, посланный процессу, который его не
        игнорирует, обязан реально прерывать sleep() внутри _hang(). Если бы
        харнесс наследовал SIG_IGN (как первая версия стенда в отчёте),
        процесс НЕ упал бы за отведённое время — этот тест ловит именно это,
        отдельно от матрицы выше."""
        out_dir = self.tmp / "sigint-liveness"
        out_dir.mkdir()
        proc = subprocess.Popen(
            [sys.executable, str(HARNESS), "dataforseo", str(out_dir)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            deadline = time.time() + 15
            while time.time() < deadline and proc.stdout.readline().strip() != "STARTED":
                pass
            os.kill(proc.pid, signal.SIGINT)
            rc = proc.wait(timeout=5)
            self.assertNotEqual(rc, 0, "SIGINT обязан реально прервать процесс, а не быть проигнорирован")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            proc.stdout.close()
            proc.stderr.close()

    def test_positive_control_finds_a_record_when_one_genuinely_exists(self) -> None:
        """Обратная сторона: если файл учёта реально содержит расход, детектор
        _spend_recorded() обязан сказать True — не только "никогда не находит
        ничего" (стенд, который всегда говорит False, тоже прошёл бы матрицу
        выше "по умолчанию красным", но не был бы информативным). Прямая
        проверка на настоящих файлах всех шести форматов."""
        (self.tmp / "_usage.json").write_text(json.dumps({"calls": 1}), encoding="utf-8")
        self.assertTrue(_spend_recorded(self.tmp, "dataforseo"))

        spyfu_dir = self.tmp / "spyfu"
        spyfu_dir.mkdir()
        (spyfu_dir / "_usage.json").write_text(json.dumps({"cost_unknown_calls": 1}), encoding="utf-8")
        self.assertTrue(_spend_recorded(spyfu_dir, "spyfu"))

        nlp_dir = self.tmp / "nlp"
        nlp_dir.mkdir()
        (nlp_dir / "usage-2026-09.json").write_text(
            json.dumps({"features": {"analyzeEntities": 1}}), encoding="utf-8")
        self.assertTrue(_spend_recorded(nlp_dir, "google_nlp"))

        for client in ("ads_apply", "yandex_direct", "google_ads"):
            d = self.tmp / client
            (d / "seo" / "usage").mkdir(parents=True)
            (d / "seo" / "usage" / "usage-ledger.jsonl").write_text('{"service": "x"}\n', encoding="utf-8")
            self.assertTrue(_spend_recorded(d, client))

    def test_positive_control_correctly_says_false_when_nothing_was_written(self) -> None:
        """И симметрично: пустой каталог обязан читаться как "расход не
        записан" для всех шести форматов — иначе детектор всегда говорит
        True и матрица выше зелёная просто потому, что ничего не проверяет."""
        for client in WriteAheadSignalMatrixTest.CLIENTS:
            d = self.tmp / f"empty-{client}"
            d.mkdir()
            self.assertFalse(_spend_recorded(d, client), f"{client}: ложно-положительный на пустом каталоге")


class GuardedSpendBypassTest(unittest.TestCase):
    """Критерий приёмки: попытка выполнить платный вызов МИМО единой точки
    (armed_spend()) обязана падать, а не тихо уходить в сеть. Нарочно
    написанный обход — прямой вызов декорированной функции без write-ahead —
    на каждом из шести клиентов."""

    def _assert_bypass_raises(self, module_import_name: str, filename: str, attr: str, call) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(module_import_name, SCRIPTS / filename)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except ImportError as e:
            self.skipTest(f"{filename} optional deps missing: {e}")
        from seo_cycle_core.spend_guard import SpendNotArmedError
        fn = getattr(mod, attr)
        with self.assertRaises(SpendNotArmedError):
            call(mod, fn)

    def test_dataforseo_call_bypass_raises(self) -> None:
        self._assert_bypass_raises("dfs_bypass", "dataforseo-fetch.py", "call",
                                   lambda mod, fn: fn("b64", "some/path", {"k": 1}))

    def test_spyfu_call_bypass_raises(self) -> None:
        self._assert_bypass_raises("spyfu_bypass", "spyfu-fetch.py", "call",
                                   lambda mod, fn: fn("b64", "some/path", {"domain": "x"}))

    def test_google_nlp_call_feature_bypass_raises(self) -> None:
        if not _GOOGLE_NLP_DEPS_OK:
            self.skipTest("google-nlp-audit.py optional deps missing")
        self._assert_bypass_raises(
            "gnlp_bypass", "google-nlp-audit.py", "call_feature",
            lambda mod, fn: fn(pathlib.Path("/nonexistent"), "analyzeEntities", "hi", "en",
                               {"GOOGLE_APPLICATION_CREDENTIALS": "/nonexistent"}))

    def test_ads_apply_apply_direct_bypass_raises(self) -> None:
        self._assert_bypass_raises("ads_apply_bypass", "ads-apply.py", "apply_direct",
                                   lambda mod, fn: fn([{"op": "create_campaign", "name": "x"}], sandbox=True))

    def test_yandex_direct_live_fetch_bypass_raises(self) -> None:
        self._assert_bypass_raises("yandex_bypass", "yandex-direct-fetch.py", "live_fetch",
                                   lambda mod, fn: fn("campaigns", {}, 7))

    def test_google_ads_gaql_search_bypass_raises(self) -> None:
        self._assert_bypass_raises("google_ads_bypass", "google-ads-fetch.py", "gaql_search",
                                   lambda mod, fn: fn("campaigns"))


if __name__ == "__main__":
    unittest.main()
