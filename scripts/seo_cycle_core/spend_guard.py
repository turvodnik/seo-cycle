"""Outbound-connection gate every paid client in this codebase relies on
(T-089 round 3).

## History (why this is the third shape of this module)

Round 1 put the refusal on a `@guarded_spend` decorator wrapping each
client's network function. Independent review (`optimize/reports/
2026-09-07-review-T-089.md`) broke it: `functools.wraps` left the original
reachable as `fn.__wrapped__`, and a brand-new client that never applied the
decorator (`keyso-fetch.py`, `competitor-discovery.py` — already in the
tree) was never checked at all.

Round 2 moved the check to `urllib.request.urlopen`/
`requests.sessions.Session.request`. A SECOND independent review
(`optimize/reports/2026-09-07-review-T-089-round2.md`) broke that too, with
seven reproducible in-process bypasses: early-imported `from urllib.request
import urlopen` (import-order binding), `build_opener().open()` (and via it
every redirect — `HTTPRedirectHandler` calls `parent.open`, not `urlopen`),
`http.client.HTTPSConnection` used directly, a raw `socket`, a `bytes` URL
(host parsing produced `""`), a trailing-dot hostname (`api.dataforseo.com.`,
a valid DNS name that string-equality against `PAID_HOSTS` doesn't match),
grabbing the saved "real" function back out of this module by name, and
`requests`' own `Session.send()`/`HTTPAdapter.send()` (only `Session.request`
was patched). All seven are real, working patterns already used elsewhere
in this same repository (see the report for exact file:line citations).

## Round 3's answer: go to the lowest practical layer

`urlopen`, `build_opener`, `http.client`, and `requests` all eventually ask
the OS to resolve a hostname and open a TCP connection. In CPython that
happens through exactly two module-level entry points:
`socket.getaddrinfo(host, ...)` (name resolution — called by
`socket.create_connection`, which `http.client.HTTPConnection.connect()`
uses, which is what `urlopen`/`build_opener`/`requests`/`urllib3` all ride
on) and `socket.socket.connect()`/`.connect_ex()` (raw sockets that skip
Python-level resolution because CPython's C-level `connect()` implementation
resolves without going through the Python `getaddrinfo` name — this is what
the raw-socket bypass exploited). Patching BOTH closes all seven
round-2 bypasses in two places instead of one per library, because none of
those libraries has its own private code path to the network stack — they
all funnel through the socket module eventually.

Host parsing is fixed at the point closest to where a hostname is actually a
Python value already: `bytes`/`bytearray` are decoded, a trailing dot is
stripped (a syntactically valid absolute DNS name), case is folded. This
happens once here, not once per library-specific URL-parsing helper.

## What this buys, and what it does not — read before assuming more than is
## claimed. Round 1 and round 2 were both returned for overstating this.

Buys:
  - Every network client in this codebase (urllib-based or requests-based,
    directly or via `build_opener`/redirects/raw `http.client`/raw
    `socket`) that runs IN A PROCESS WHERE THIS MODULE WAS IMPORTED cannot
    reach a `PAID_HOSTS` member without an active `armed_spend()` for that
    exact host. There is no per-client wrapper left anywhere to unwrap,
    restore, or call around — the two patched names ARE the only path to
    the network these libraries have.
  - A client reusing an ALREADY-REGISTERED host needs zero code of its own
    referencing this module to be protected, AS LONG AS its own process
    imported anything from the `seo_cycle_core` package (see below —
    `seo_cycle_core/__init__.py` imports this module as a side effect of
    package import, not as something each client has to remember).

Does NOT buy — this is the boundary, stated for the release notes, not
just this docstring:
  - **A process that never imports anything from `seo_cycle_core` at all**
    is not gated at runtime. Every existing client uses shared
    `seo_cycle_core` helpers (config, usage_ledger, ads) for reasons that
    have nothing to do with this ticket, so today this is not a live gap —
    but it is not a theorem either. The compensating control for this case
    is NOT runtime: it is `tests/test_t089_closed_world_hosts.py`, which
    fails CI the moment a script mentions a `PAID_HOSTS` (or any
    unclassified) hostname without importing `seo_cycle_core` and without
    calling `armed_spend(` — a static, review-time check, not a
    runtime one. It cannot stop a call the day unreviewed code ships; it
    can stop it from being merged unnoticed.
  - **A subprocess started via `subprocess`/`os.system`/a shell script**
    (this repo already has one: `scripts/nw-cli.sh` calls `curl` directly)
    is a separate OS process with its own Python interpreter or no
    interpreter at all — nothing importable in THIS process reaches into
    that one. Same compensating control as above: the static scan covers
    `scripts/*.py` only (documented limitation, `tests/
    test_t089_closed_world_hosts.py`'s own docstring says so) — shell/curl
    call sites are not scanned by either half of this mechanism today.
  - **A raw socket connecting to an already-resolved numeric IP address**
    (no hostname anywhere in the call) cannot be matched against
    `PAID_HOSTS` — there is no name to compare. Nothing in this module (or
    a hostname-based list in general) can close this without shipping an
    IP-range registry instead, which was not asked for and brings its own
    staleness problem (cloud IPs rotate). Accepted as out of scope.
  - **A browser-driven flow, an external binary that does its own network
    I/O (curl, another language's HTTP client), or `-S`/isolated Python
    interpreters that skip normal import machinery** are, by construction,
    outside anything a Python-level monkeypatch can reach. No claim is made
    about them.
  - `armed_spend(write_ahead, hosts)` trusts `write_ahead` to actually write
    before returning `True` — nothing here re-reads the file to verify
    (every REAL caller in this codebase does that itself, via
    `ledger_record()`/`save_usage()`'s bool contract, T-066 R3-3; a test
    arming with `lambda: True` is a documented, deliberate test convention,
    not a runtime guarantee).
  - Arming is scoped to a *host set*, not to a single call, for the
    duration of one `with armed_spend(write_ahead, hosts=X):` block — any
    number of calls to hosts in `X` are allowed inside it, calls to any
    other host are not. Deliberate: `ads-apply.py` legitimately records ONE
    write-ahead for a whole batch of operations (T-066 R3-4); one-shot
    arming would break that pattern. What must NOT happen — an arming for
    host A also covering host B — does not: `_check_host` compares the
    SPECIFIC contacted host against the SPECIFIC armed set.
  - `_ARMED_HOSTS` is a `contextvars.ContextVar`: it does not propagate into
    a new OS thread (a thread starts with a fresh context) or a new
    process. No paid client in this codebase currently spawns threads for
    its network calls (checked: no `threading`/`concurrent.futures`/
    `asyncio` import in any of the eight paid clients) — parallel
    *processes* are unaffected (armed state lives per-process already, by
    construction) and are the actual concurrency model these CLI tools use.
"""

from __future__ import annotations

import contextvars
import socket
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator

# Hosts that MUST NOT be contacted by this codebase's own outbound calls
# without an active armed_spend() naming that host. Keep in sync with
# tests/test_t089_closed_world_hosts.py (FREE_HOSTS there covers every other
# host any script in this repo actually references).
PAID_HOSTS = frozenset({
    "api.dataforseo.com",
    "api.spyfu.com",
    "api.direct.yandex.com",
    "api-sandbox.direct.yandex.com",
    "googleads.googleapis.com",
    "language.googleapis.com",
    "api.keys.so",
})

_ARMED_HOSTS: "contextvars.ContextVar[frozenset[str]]" = contextvars.ContextVar(
    "seo_cycle_armed_hosts", default=frozenset()
)


class SpendNotArmedError(RuntimeError):
    """A paid host (`PAID_HOSTS`) was about to be resolved/connected to
    without an active `armed_spend()` naming that exact host — refused
    before any byte reached the network (round 3: caught at DNS resolution
    or raw socket connect, whichever happens first)."""


def _normalize_host(host: Any) -> str:
    """`bytes`/`bytearray` (round-2 bypass 11: `_host_of()` used to `str()`
    a bytes URL and get `"b'https://...'"`, hostname `""`, silent pass) and
    a trailing dot (bypass 08: `api.dataforseo.com.` is a valid absolute DNS
    name PAID_HOSTS didn't match) are normalized once, here — the one place
    every caller (getaddrinfo, connect, connect_ex) goes through."""
    if host is None:
        return ""
    if isinstance(host, (bytes, bytearray)):
        try:
            host = host.decode("idna")
        except (UnicodeError, UnicodeDecodeError):
            host = host.decode("utf-8", "replace")
    return str(host).strip().lower().rstrip(".")


def _check_host(host: str) -> None:
    if host and host in PAID_HOSTS and host not in _ARMED_HOSTS.get():
        raise SpendNotArmedError(
            f"paid host {host!r} contacted outside armed_spend() for it — "
            "the write-ahead record for this call either was never made or "
            "does not cover this host (T-089 round 3: the refusal lives at "
            "DNS resolution / socket connect, the lowest layer every "
            "Python HTTP client in this codebase funnels through)."
        )


@contextmanager
def armed_spend(write_ahead: Callable[[], bool], hosts: str | Iterable[str]) -> Iterator[None]:
    """The only legal way to allow a connection to a `PAID_HOSTS` member.
    Runs `write_ahead()` FIRST; only a truthy result arms `hosts` for the
    duration of the `with` block — `write_ahead` is responsible for the
    actual disk write and for reporting truthfully whether it landed (the
    same bool contract `ledger_record()` already had, T-066 R3-3). `hosts`
    may be one hostname or several; every outbound connection to one of
    them inside the block is allowed, connections to any other host are
    not (see module docstring for what "allowed" does and does not cover)."""
    normalized = frozenset(_normalize_host(h) for h in ((hosts,) if isinstance(hosts, str) else hosts))
    if not normalized or not all(normalized):
        raise ValueError("armed_spend() requires at least one non-empty host")
    if not write_ahead():
        raise SpendNotArmedError(
            "write-ahead record did not land — refusing to arm any paid call."
        )
    token = _ARMED_HOSTS.set(_ARMED_HOSTS.get() | normalized)
    try:
        yield
    finally:
        _ARMED_HOSTS.reset(token)


def gate_installed() -> bool:
    """True iff both patches below are the currently active implementation
    of their target — used by tests to fail fast and loud (round-2 finding
    R2-5: a mutated/未installed gate must not silently let the test suite's
    own real network calls through; asserting this in setUp turns that into
    an immediate, obvious failure instead of a live DNS lookup)."""
    return (
        socket.getaddrinfo is _guarded_getaddrinfo
        and socket.socket.connect is _guarded_connect
        and socket.socket.connect_ex is _guarded_connect_ex
    )


# --- Install the gate. A normal package import is cached in sys.modules, so
# this body runs once per process regardless of how many client scripts
# import this module (directly, or transitively via
# seo_cycle_core/__init__.py — see there for why that matters). The
# identity checks in gate_installed()/_install() make re-installation and
# re-verification cheap and safe. ---

#: The real, unwrapped implementations, kept as MODULE-level names (not
#: closure variables) so a test can `mock.patch.object(spend_guard,
#: "_real_getaddrinfo", side_effect=AssertionError(...))` and get a hard
#: proof the actual resolver/socket call was never reached — the wrapper
#: functions look these up fresh on every call.
_real_getaddrinfo: Callable[..., Any] | None = None
_real_connect: Callable[..., Any] | None = None
_real_connect_ex: Callable[..., Any] | None = None


def _host_from_address(address: Any) -> str:
    # AF_INET: (host, port). AF_INET6: (host, port, flowinfo, scopeid).
    # AF_UNIX: a path string, not a tuple — no hostname, nothing to check.
    if isinstance(address, tuple) and address:
        return _normalize_host(address[0])
    return ""


def _guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    _check_host(_normalize_host(host))
    assert _real_getaddrinfo is not None
    return _real_getaddrinfo(host, *args, **kwargs)


def _guarded_connect(self: "socket.socket", address: Any) -> Any:
    _check_host(_host_from_address(address))
    assert _real_connect is not None
    return _real_connect(self, address)


def _guarded_connect_ex(self: "socket.socket", address: Any) -> Any:
    _check_host(_host_from_address(address))
    assert _real_connect_ex is not None
    return _real_connect_ex(self, address)


def _install() -> None:
    global _real_getaddrinfo, _real_connect, _real_connect_ex
    if socket.getaddrinfo is not _guarded_getaddrinfo:
        _real_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = _guarded_getaddrinfo
    if socket.socket.connect is not _guarded_connect:
        _real_connect = socket.socket.connect
        socket.socket.connect = _guarded_connect  # type: ignore[method-assign,assignment]
    if socket.socket.connect_ex is not _guarded_connect_ex:
        _real_connect_ex = socket.socket.connect_ex
        socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign,assignment]


_install()
