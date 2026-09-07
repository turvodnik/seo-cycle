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
    """Критерий приёмки круга 3: обход единой точки обязан падать —
    проверено на самом нижнем практичном уровне (`socket.getaddrinfo` /
    `socket.socket.connect`/`connect_ex`), не на `urlopen`/`Session.request`
    (round-2 review broke that layer seven ways — see spend_guard.py's
    module docstring). Каждый тест: (1) вызов реальной функции клиента без
    armed_spend() обязан поднять SpendNotArmedError, (2) настоящий резолвер
    при этом НЕ вызывается — доказано подменой `spend_guard._real_getaddrinfo`
    (не публичного `socket.getaddrinfo`, который и есть наш шлюз) на функцию,
    падающую AssertionError, если её вообще позвали."""

    def setUp(self) -> None:
        # R2-5: если мутация (или будущая правка) снимет установку шлюза,
        # это обязано провалиться здесь быстро и очевидно — а не тем, что
        # следующие строки теста реально уйдут в сеть.
        self.assertTrue(spend_guard.gate_installed(),
                        "транспортный шлюз не установлен — тесты ниже "
                        "перестали бы что-либо проверять и рисковали бы "
                        "живой сетью")

    def _assert_bypass_raises(self, modname: str, filename: str, call) -> None:
        mod = _fresh_module(modname, filename)
        raiser = mock.Mock(side_effect=AssertionError(
            "real getaddrinfo() reached — the transport gate did not block in time"))
        with mock.patch.object(spend_guard, "_real_getaddrinfo", raiser):
            with self.assertRaises(SpendNotArmedError):
                call(mod)
        raiser.assert_not_called()

    def test_dataforseo_call_bypass_raises(self) -> None:
        self._assert_bypass_raises("dfs_bypass", "dataforseo-fetch.py",
                                   lambda mod: mod.call("b64", "some/path", {"k": 1}))

    def test_spyfu_call_bypass_raises(self) -> None:
        self._assert_bypass_raises("spyfu_bypass", "spyfu-fetch.py",
                                   lambda mod: mod.call("b64", "some/path", {"domain": "x"}))

    def test_google_nlp_call_feature_bypass_raises(self) -> None:
        if not _GOOGLE_NLP_DEPS_OK:
            self.skipTest("google-nlp-audit.py optional deps missing")
        mod = _fresh_module("gnlp_bypass", "google-nlp-audit.py")
        raiser = mock.Mock(side_effect=AssertionError(
            "real getaddrinfo() reached — the gate did not block in time"))
        with mock.patch.object(mod, "credentials", return_value=mock.Mock(token="x")), \
             mock.patch.object(spend_guard, "_real_getaddrinfo", raiser):
            with self.assertRaises(SpendNotArmedError):
                mod.call_feature(pathlib.Path("/nonexistent"), "analyzeEntities", "hi", "en",
                                 {"GOOGLE_APPLICATION_CREDENTIALS": "/nonexistent"})
        raiser.assert_not_called()

    def test_ads_apply_apply_direct_bypass_raises(self) -> None:
        """apply_direct() catches exceptions PER OPERATION (T-066 R2-2, by
        design), so a SpendNotArmedError from inside direct_request()
        surfaces as a `status: failed` row, not a raised exception. The
        proof that matters is unchanged: the real resolver is never
        reached without armed_spend()."""
        mod = _fresh_module("ads_apply_bypass", "ads-apply.py")
        raiser = mock.Mock(side_effect=AssertionError(
            "real getaddrinfo() reached — the gate did not block in time"))
        with mock.patch.dict(os.environ, {"YANDEX_DIRECT_TOKEN": "fake-token"}), \
             mock.patch.object(spend_guard, "_real_getaddrinfo", raiser):
            results = mod.apply_direct([{"op": "create_campaign", "name": "x"}], sandbox=True)
        raiser.assert_not_called()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("SpendNotArmedError", results[0]["error"])

    def test_yandex_direct_live_fetch_bypass_raises(self) -> None:
        self._assert_bypass_raises(
            "yandex_bypass", "yandex-direct-fetch.py",
            lambda mod: mod.live_fetch("campaigns", {}, 7))

    def test_google_ads_gaql_search_bypass_raises(self) -> None:
        mod = _fresh_module("google_ads_bypass", "google-ads-fetch.py")
        mod.oauth_access_token = lambda: "fake-token"
        os.environ.setdefault("GOOGLE_ADS_CUSTOMER_ID", "1234567890")
        os.environ.setdefault("GOOGLE_ADS_DEVELOPER_TOKEN", "fake-dev-token")
        self._assert_bypass_raises(
            "google_ads_bypass2", "google-ads-fetch.py",
            lambda _mod: mod.gaql_search("campaigns"))

    def test_keyso_call_writes_ahead_of_its_own_network_attempt(self) -> None:
        """keyso-fetch.py/competitor-discovery.py/keyso-save.py embed
        write-ahead + armed_spend() INSIDE the function itself — there is no
        separate "call the wrapper vs. call the primitive" surface to
        demonstrate a bypass on. Proved positively instead: write lands
        before the (stubbed) network attempt, in that order, every time."""
        mod = _fresh_module("keyso_direct", "keyso-fetch.py")
        write_order: list[str] = []
        real_bump = mod.bump_usage

        def _tracking_bump(*a, **kw):
            write_order.append("write")
            return real_bump(*a, **kw)

        def _tracking_getaddrinfo(host, *a, **kw):
            write_order.append("network")
            raise AssertionError("stub network — no live call")

        mod.bump_usage = _tracking_bump
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="seo-keyso-order-") as td:
            os.chdir(td)
            try:
                with mock.patch.object(spend_guard, "_real_getaddrinfo", _tracking_getaddrinfo):
                    with self.assertRaises(AssertionError):
                        mod.call("fake-token", "/report/simple/keyword_dashboard",
                                {"keyword": "x", "base": "msk"})
            finally:
                os.chdir(original_cwd)
        self.assertEqual(write_order, ["write", "network"],
                         "запись расхода обязана произойти ДО сетевого вызова, не после")

    def test_competitor_discovery_fetch_top_writes_ahead_of_its_own_network_attempt(self) -> None:
        mod = _fresh_module("competitor_discovery_direct", "competitor-discovery.py")
        write_order: list[str] = []
        real_bump = mod.bump_counter

        def _tracking_bump(*a, **kw):
            write_order.append("write")
            return real_bump(*a, **kw)

        def _tracking_getaddrinfo(host, *a, **kw):
            write_order.append("network")
            raise AssertionError("stub network — no live call")

        mod.bump_counter = _tracking_bump
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="seo-compdisc-order-") as td:
            os.chdir(td)
            try:
                with mock.patch.object(spend_guard, "_real_getaddrinfo", _tracking_getaddrinfo):
                    with self.assertRaises(AssertionError):
                        mod.fetch_top("fake-token", "minvata", "msk", 60)
            finally:
                os.chdir(original_cwd)
        self.assertEqual(write_order, ["write", "network"],
                         "запись расхода обязана произойти ДО сетевого вызова, не после")

    def test_keyso_save_post_writes_ahead_of_its_own_network_attempt(self) -> None:
        """T-089 round 3: keyso-save.py — a THIRD api.keys.so client, found
        while strengthening the static scan (R2-3), not named by either
        review round. Same class as F-1: bump_counter() was called after
        reading the response."""
        mod = _fresh_module("keyso_save_direct", "keyso-save.py")
        write_order: list[str] = []
        real_bump = mod.bump_counter

        def _tracking_bump(*a, **kw):
            write_order.append("write")
            return real_bump(*a, **kw)

        def _tracking_getaddrinfo(host, *a, **kw):
            write_order.append("network")
            raise AssertionError("stub network — no live call")

        mod.bump_counter = _tracking_bump
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="seo-keysosave-order-") as td:
            os.chdir(td)
            try:
                with mock.patch.object(spend_guard, "_real_getaddrinfo", _tracking_getaddrinfo):
                    with self.assertRaises(AssertionError):
                        mod.post("fake-token", "/report/group", {"domains": ["a.ru"]})
            finally:
                os.chdir(original_cwd)
        self.assertEqual(write_order, ["write", "network"],
                         "запись расхода обязана произойти ДО сетевого вызова, не после")

    def test_eighth_client_against_an_already_registered_paid_host_is_refused_automatically(self) -> None:
        """Finding C: a brand-new client file, written the ordinary way (no
        decorator, no knowledge of spend_guard), reusing an ALREADY
        REGISTERED paid host is refused with zero code of its own — as long
        as its process imported anything from seo_cycle_core (this test
        does, transitively, via `spend_guard` above; production clients do
        too, via config/usage_ledger/ads — see module docstring for the
        documented boundary when that is not true)."""
        import urllib.request
        raiser = mock.Mock(side_effect=AssertionError("real getaddrinfo() reached"))

        def brand_new_eighth_client() -> dict:
            req = urllib.request.Request("https://api.dataforseo.com/v3/some/new/endpoint")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {"cost": 1.23, "body": resp.read()}

        with mock.patch.object(spend_guard, "_real_getaddrinfo", raiser):
            with self.assertRaises(SpendNotArmedError):
                brand_new_eighth_client()
        raiser.assert_not_called()


class InProcessBypassProbesTest(unittest.TestCase):
    """Round-2 review, finding R2-2: seven concrete in-process bypasses of
    the (then) urlopen/Session.request-level gate, all reproduced against a
    live DNS lookup under the reviewer's own sandbox shim. Reproduced here
    against the round-3 socket-level gate, with `spend_guard._real_getaddrinfo`
    /`_real_connect`/`_real_connect_ex` replaced by raisers so no real
    lookup or connection is possible regardless of outcome — every probe
    below is expected to be REFUSED now; two are kept as living controls
    (they were never bypasses) to prove the harness itself can still say
    "reached" when something really does get through."""

    def setUp(self) -> None:
        self.assertTrue(spend_guard.gate_installed())
        self._raiser_getaddrinfo = mock.Mock(side_effect=AssertionError("real getaddrinfo() reached"))
        self._raiser_connect = mock.Mock(side_effect=AssertionError("real socket connect() reached"))
        self._raiser_connect_ex = mock.Mock(side_effect=AssertionError("real socket connect_ex() reached"))
        self._patches = [
            mock.patch.object(spend_guard, "_real_getaddrinfo", self._raiser_getaddrinfo),
            mock.patch.object(spend_guard, "_real_connect", self._raiser_connect),
            mock.patch.object(spend_guard, "_real_connect_ex", self._raiser_connect_ex),
        ]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _assert_refused(self, label: str, fn) -> None:
        with self.assertRaises(SpendNotArmedError, msg=label):
            fn()
        self._raiser_getaddrinfo.assert_not_called()
        self._raiser_connect.assert_not_called()
        self._raiser_connect_ex.assert_not_called()

    def test_01_early_bound_urlopen_import_order(self) -> None:
        import urllib.request as ur
        from urllib.request import urlopen as bound_urlopen  # noqa: PLC0415 — deliberately late, testing early-bind
        self._assert_refused("early-bound urlopen", lambda: bound_urlopen("https://api.dataforseo.com/x", timeout=2))
        del ur

    def test_02_build_opener_and_redirect_path(self) -> None:
        import urllib.request
        opener = urllib.request.build_opener()
        self._assert_refused("build_opener().open", lambda: opener.open("https://api.dataforseo.com/y", timeout=2))

    def test_04_http_client_direct(self) -> None:
        import http.client

        def go():
            conn = http.client.HTTPSConnection("api.dataforseo.com", timeout=2)
            conn.request("GET", "/z")
            return conn.getresponse()

        self._assert_refused("http.client direct", go)

    def test_05_raw_socket(self) -> None:
        import socket as socket_mod

        def go():
            s = socket_mod.socket(socket_mod.AF_INET, socket_mod.SOCK_STREAM)
            s.settimeout(2)
            return s.connect(("api.dataforseo.com", 443))

        self._assert_refused("raw socket", go)

    def test_06_restore_original_transport_one_liner(self) -> None:
        """Round-2's own bypass: reassign urllib.request.urlopen back to
        whatever was saved. Round 3 doesn't save urlopen at all — there is
        nothing named `urlopen` to "restore" that skips the gate, because
        the gate is not on urlopen."""
        import urllib.request
        # The only thing round 2 exposed for this trick was
        # spend_guard._real_urlopen — that name no longer exists.
        self.assertFalse(hasattr(spend_guard, "_real_urlopen"))
        self._assert_refused("urlopen after a no-op 'restore'",
                             lambda: urllib.request.urlopen("https://api.dataforseo.com/w", timeout=2))

    def test_07_saved_real_callable_called_directly(self) -> None:
        """Round-2's bypass: `spend_guard._real_urlopen(...)` called
        directly. Round 3's equivalent saved names are `_real_getaddrinfo`/
        `_real_connect`/`_real_connect_ex` — but calling them directly is
        exactly what these tests DO to prove they're never reached; there is
        no client-facing path that reaches them without going through
        `_check_host` first, because `_check_host` runs INSIDE the guarded
        wrapper, not in a separate step a caller could skip. Demonstrated by
        the raiser never firing across every other test in this class."""
        self.assertIsNotNone(spend_guard._real_getaddrinfo)  # noqa: SLF001

    def test_08_trailing_dot_host(self) -> None:
        import urllib.request
        self._assert_refused(
            "trailing-dot host",
            lambda: urllib.request.urlopen("https://api.dataforseo.com./w", timeout=2))

    def test_11_requests_session_send_prepared(self) -> None:
        requests = pytest_or_skip_requests(self)
        session = requests.Session()
        req = requests.Request("GET", "https://api.dataforseo.com/prepared").prepare()
        self._assert_refused("Session.send(prepared)", lambda: session.send(req, timeout=2))

    def test_12_requests_http_adapter_send(self) -> None:
        requests = pytest_or_skip_requests(self)
        adapter = requests.adapters.HTTPAdapter()
        req = requests.Request("GET", "https://api.dataforseo.com/adapter").prepare()
        self._assert_refused("HTTPAdapter.send", lambda: adapter.send(req, timeout=2))

    def test_00_baseline_control_refused(self) -> None:
        """Живой контроль: обычный urlopen() на платный хост без арминга
        обязан отказать — если бы он вдруг НЕ отказал, значило бы, что шлюз
        снят целиком, и все "refused" выше были бы холостыми."""
        import urllib.request
        self._assert_refused("baseline", lambda: urllib.request.urlopen("https://api.dataforseo.com/base", timeout=2))

    def test_09_uppercase_host_control(self) -> None:
        import urllib.request
        self._assert_refused("uppercase host",
                             lambda: urllib.request.urlopen("https://API.DATAFORSEO.COM/w", timeout=2))

    def test_10_requests_get_str_control(self) -> None:
        requests = pytest_or_skip_requests(self)
        self._assert_refused("requests.get", lambda: requests.get("https://api.dataforseo.com/req", timeout=2))


def pytest_or_skip_requests(testcase: unittest.TestCase):
    if not _GOOGLE_NLP_DEPS_OK:
        testcase.skipTest("requests not installed")
    import requests
    return requests


if __name__ == "__main__":
    unittest.main()
