#!/usr/bin/env python3
"""T-089 round 2: client x signal write-ahead matrix, plus proof that the
transport-level gate (`seo_cycle_core.spend_guard`) is structural, not a
per-client convention.

Round 1 put the refusal on a `@guarded_spend` decorator wrapping each
client's own network function. An independent second gate
(`optimize/reports/2026-09-07-review-T-089.md`) broke that in three ways
that share one root cause — the check lived on a per-client wrapper, not on
the shared thing every client actually calls to leave the process:

  A. `functools.wraps` leaves the undecorated original reachable as
     `fn.__wrapped__` — one attribute access away from the real network call
     with zero write-ahead.
  C. A brand-new paid client that never applies the decorator is never
     checked at all — nothing in the tree notices.
  H. C was not hypothetical: `keyso-fetch.py` and `competitor-discovery.py`
     were ALREADY in the tree, already hitting a paid host
     (`api.keys.so`), already writing their usage counter AFTER the call,
     already unlisted anywhere in the money line.

Round 2's fix moves the check onto `urllib.request.urlopen` and
`requests.sessions.Session.request` themselves (patched once, in place, at
import of `seo_cycle_core.spend_guard`) — there is no client-level wrapper
left to unwrap, and a client reusing an already-registered paid host
(`spend_guard.PAID_HOSTS`) is refused automatically with zero code of its
own. What this does NOT buy — a genuinely new, unregistered paid host — is
covered separately by `tests/test_t089_closed_world_hosts.py`, a static
scan that fails the build the moment an unclassified host shows up in
`scripts/*.py`; see `spend_guard.py`'s module docstring for the full
boundary statement.

Every signal scenario below still runs the REAL client code in a separate
OS process with a real `os.kill()` — not a mocked exception standing in for
a signal."""

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
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
HARNESS = pathlib.Path(__file__).resolve().parent / "helpers" / "t089_signal_target.py"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core import spend_guard  # noqa: E402 (sys.path must be set first)
from seo_cycle_core.spend_guard import SpendNotArmedError  # noqa: E402

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
    honest about eight genuinely different implementations, T-066/T-089)."""
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
    if client in ("keyso", "competitor_discovery"):
        p = out_dir / "seo" / "research" / "keyso" / "_usage.json"
        return p.exists() and json.loads(p.read_text()).get("requests", 0) >= 1
    raise AssertionError(client)


class WriteAheadSignalMatrixTest(unittest.TestCase):
    """Матрица «клиент × сигнал» (F-1, F-H): расход обязан быть записан на
    диске ДО того, как сигнал успевает прервать выполнение — для всех восьми
    известных платных клиентов (шесть из T-066/T-089-круг-1 плюс два,
    найденные вторым гейтом: keyso-fetch.py, competitor-discovery.py)."""

    CLIENTS = ["dataforseo", "spyfu", "google_nlp", "ads_apply", "yandex_direct",
               "google_ads", "keyso", "competitor_discovery"]
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
    первой версии QA-стенда на Ctrl-C), или (b) он никогда не находит
    запись, даже когда клиент честно её оставил. Обе стороны проверены
    здесь напрямую, а не только предположением "раз матрица выше зелёная —
    значит стенд исправен"."""

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
        проверка на настоящих файлах всех восьми форматов."""
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

        for client in ("keyso", "competitor_discovery"):
            d = self.tmp / client
            (d / "seo" / "research" / "keyso").mkdir(parents=True)
            (d / "seo" / "research" / "keyso" / "_usage.json").write_text(
                json.dumps({"requests": 1}), encoding="utf-8")
            self.assertTrue(_spend_recorded(d, client))

    def test_positive_control_correctly_says_false_when_nothing_was_written(self) -> None:
        """И симметрично: пустой каталог обязан читаться как "расход не
        записан" для всех восьми форматов — иначе детектор всегда говорит
        True и матрица выше зелёная просто потому, что ничего не проверяет."""
        for client in WriteAheadSignalMatrixTest.CLIENTS:
            d = self.tmp / f"empty-{client}"
            d.mkdir()
            self.assertFalse(_spend_recorded(d, client), f"{client}: ложно-положительный на пустом каталоге")


def _fresh_module(modname: str, filename: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(modname, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TransportGateBypassTest(unittest.TestCase):
    """Критерий приёмки круга 2: обход единой точки обязан падать —
    проверено на транспорте (`urllib.request.urlopen` /
    `requests.Session.request`), а не на декораторе клиента (которого
    больше нет, review finding A). Для каждого клиента: (1) вызов реальной
    функции без armed_spend() обязан поднять SpendNotArmedError, (2)
    настоящий транспорт при этом НЕ вызывается — доказано подменой
    `spend_guard._real_urlopen`/`_real_session_request` (не публичного
    `urlopen`/`Session.request`, которые и есть наш собственный шлюз) на
    функцию, которая падает AssertionError, если её вообще позвали
    (review finding B: раньше закоммиченные тесты держали живые вызовы,
    потому что мокали не тот слой)."""

    def _assert_urllib_bypass_raises(self, modname: str, filename: str, call) -> None:
        mod = _fresh_module(modname, filename)
        raiser = mock.Mock(side_effect=AssertionError(
            "real urlopen() reached — the transport gate did not block in time"))
        with mock.patch.object(spend_guard, "_real_urlopen", raiser):
            with self.assertRaises(SpendNotArmedError):
                call(mod)
        raiser.assert_not_called()

    def test_dataforseo_call_bypass_raises(self) -> None:
        self._assert_urllib_bypass_raises("dfs_bypass", "dataforseo-fetch.py",
                                          lambda mod: mod.call("b64", "some/path", {"k": 1}))

    def test_spyfu_call_bypass_raises(self) -> None:
        self._assert_urllib_bypass_raises("spyfu_bypass", "spyfu-fetch.py",
                                          lambda mod: mod.call("b64", "some/path", {"domain": "x"}))

    def test_google_nlp_call_feature_bypass_raises(self) -> None:
        if not _GOOGLE_NLP_DEPS_OK:
            self.skipTest("google-nlp-audit.py optional deps missing")
        mod = _fresh_module("gnlp_bypass", "google-nlp-audit.py")
        raiser = mock.Mock(side_effect=AssertionError(
            "real requests transport reached — the gate did not block in time"))
        with mock.patch.object(mod, "credentials", return_value=mock.Mock(token="x")), \
             mock.patch.object(spend_guard, "_real_session_request", raiser):
            with self.assertRaises(SpendNotArmedError):
                mod.call_feature(pathlib.Path("/nonexistent"), "analyzeEntities", "hi", "en",
                                 {"GOOGLE_APPLICATION_CREDENTIALS": "/nonexistent"})
        raiser.assert_not_called()

    def test_ads_apply_apply_direct_bypass_raises(self) -> None:
        """apply_direct() catches exceptions PER OPERATION (T-066 R2-2, by
        design — one operation failing must not lose the ones after it), so
        a SpendNotArmedError raised by urlopen() inside direct_request()
        surfaces as a `status: failed` row, not a raised exception. The
        proof that matters is unchanged: the real transport is never
        reached without armed_spend()."""
        mod = _fresh_module("ads_apply_bypass", "ads-apply.py")
        raiser = mock.Mock(side_effect=AssertionError(
            "real urlopen() reached — the transport gate did not block in time"))
        with mock.patch.dict(os.environ, {"YANDEX_DIRECT_TOKEN": "fake-token"}), \
             mock.patch.object(spend_guard, "_real_urlopen", raiser):
            results = mod.apply_direct([{"op": "create_campaign", "name": "x"}], sandbox=True)
        raiser.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("SpendNotArmedError", results[0]["error"])

    def test_yandex_direct_live_fetch_bypass_raises(self) -> None:
        self._assert_urllib_bypass_raises(
            "yandex_bypass", "yandex-direct-fetch.py",
            lambda mod: mod.live_fetch("campaigns", {}, 7))

    def test_google_ads_gaql_search_bypass_raises(self) -> None:
        mod = _fresh_module("google_ads_bypass", "google-ads-fetch.py")
        mod.oauth_access_token = lambda: "fake-token"
        os.environ.setdefault("GOOGLE_ADS_CUSTOMER_ID", "1234567890")
        os.environ.setdefault("GOOGLE_ADS_DEVELOPER_TOKEN", "fake-dev-token")
        self._assert_urllib_bypass_raises(
            "google_ads_bypass2", "google-ads-fetch.py",
            lambda _mod: mod.gaql_search("campaigns"))

    def test_keyso_call_cannot_be_invoked_without_its_own_write_ahead(self) -> None:
        """keyso-fetch.py and competitor-discovery.py (finding H) embed the
        write-ahead + armed_spend() INSIDE call()/fetch_top() itself, not in
        an outer caller — unlike the other six clients there is no separate
        "bypass the wrapper, call the primitive directly" surface to
        demonstrate: calling call() at all always writes ahead first. This
        test proves that positively instead of via a non-existent bypass:
        the real transport is reached (mocked here only to avoid a live
        request), and the usage file is written BEFORE it is."""
        mod = _fresh_module("keyso_direct", "keyso-fetch.py")
        write_order: list[str] = []
        real_bump = mod.bump_usage

        def _tracking_bump(*a, **kw):
            write_order.append("write")
            return real_bump(*a, **kw)

        def _tracking_urlopen(*_a, **_kw):
            write_order.append("network")
            raise AssertionError("stub network — no live call")

        mod.bump_usage = _tracking_bump
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="seo-keyso-order-") as td:
            os.chdir(td)
            try:
                with mock.patch.object(spend_guard, "_real_urlopen", _tracking_urlopen):
                    with self.assertRaises(AssertionError):
                        mod.call("fake-token", "/report/simple/keyword_dashboard",
                                {"keyword": "x", "base": "msk"})
            finally:
                os.chdir(original_cwd)
        self.assertEqual(write_order, ["write", "network"],
                         "запись расхода обязана произойти ДО сетевого вызова, не после")

    def test_competitor_discovery_fetch_top_cannot_be_invoked_without_its_own_write_ahead(self) -> None:
        mod = _fresh_module("competitor_discovery_direct", "competitor-discovery.py")
        write_order: list[str] = []
        real_bump = mod.bump_counter

        def _tracking_bump(*a, **kw):
            write_order.append("write")
            return real_bump(*a, **kw)

        def _tracking_urlopen(*_a, **_kw):
            write_order.append("network")
            raise AssertionError("stub network — no live call")

        mod.bump_counter = _tracking_bump
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="seo-compdisc-order-") as td:
            os.chdir(td)
            try:
                with mock.patch.object(spend_guard, "_real_urlopen", _tracking_urlopen):
                    with self.assertRaises(AssertionError):
                        mod.fetch_top("fake-token", "minvata", "msk", 60)
            finally:
                os.chdir(original_cwd)
        self.assertEqual(write_order, ["write", "network"],
                         "запись расхода обязана произойти ДО сетевого вызова, не после")

    def test_eighth_client_against_an_already_registered_paid_host_is_refused_automatically(self) -> None:
        """Review finding C, closed for the case that matters in practice:
        a brand-new client file, written the ordinary way (no decorator, no
        knowledge of spend_guard at all), that reuses an ALREADY REGISTERED
        paid host is refused with zero code of its own — the gate lives on
        urlopen(), not on anything this new file has to opt into."""
        import urllib.request
        raiser = mock.Mock(side_effect=AssertionError("real urlopen() reached"))

        def brand_new_eighth_client() -> dict:
            # No import of spend_guard, no decorator, no armed_spend — this
            # is exactly what an unaware author would write.
            req = urllib.request.Request("https://api.dataforseo.com/v3/some/new/endpoint")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {"cost": 1.23, "body": resp.read()}

        with mock.patch.object(spend_guard, "_real_urlopen", raiser):
            with self.assertRaises(SpendNotArmedError):
                brand_new_eighth_client()
        raiser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
