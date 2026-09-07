"""Single physical transport every paid client's outbound call passes
through (T-089 round 2).

Round 1's mistake (independent gate, `optimize/reports/2026-09-07-review-T-089.md`,
findings A/C/D/H): the gate lived on a `@guarded_spend` decorator wrapped
around each client's own network function. That is a per-client convention,
not a structural barrier — `functools.wraps` leaves the original reachable
as `fn.__wrapped__` (finding A: `dataforseo.call.__wrapped__(...)` reaches
the real network layer with zero write-ahead), and a brand-new eighth client
that never applies the decorator at all is simply never checked (finding C;
finding H showed this was not hypothetical — `keyso-fetch.py` and
`competitor-discovery.py` were already in the tree, already hitting a paid
host, already unguarded).

This version moves the check down one layer, onto the two primitives every
client in this codebase actually uses to leave the process:
`urllib.request.urlopen` and (if installed) `requests.sessions.Session.request`
(which `requests.get/post/put/...` all call internally). Both are patched
ONCE, at import time of this module, in place — not per client, not behind
a decorator a client file can choose to skip. A call to either primitive
against a host in `PAID_HOSTS` is refused with `SpendNotArmedError` unless
the calling context is currently inside `armed_spend()` for that exact host.

What this buys, precisely:
  - No `__wrapped__`-style escape exists — there is no per-client wrapper
    function to unwrap. Calling a client's "guarded" function directly, its
    `__wrapped__`, a copy of its body pasted into a new file, or a brand-new
    client that never heard of this module — all of them still call
    `urllib.request.urlopen`/`requests...` in the end, and all of them hit
    the SAME check, because the check lives on the primitive, not on them.
  - A brand-new (eighth, ninth, ...) client that reuses an ALREADY-REGISTERED
    paid host (copy-pasted boilerplate against DataForSEO, SpyFu, Yandex
    Direct, Google Ads, Google NLP or Keys.so) is refused automatically,
    with zero code written in the new file.

What this does NOT buy — stated plainly, per the review's own instruction
that an honest boundary beats an overstated guarantee:
  - `PAID_HOSTS` is still a list, and a genuinely NEW host (a new paid
    provider nobody has registered yet) is not stopped by this runtime
    check — nothing here can know a host is "paid" without being told.
    That gap is covered by a SEPARATE, static safety net:
    `tests/test_t089_closed_world_hosts.py` scans every string literal in
    `scripts/*.py` for URLs and fails the build the moment an unclassified
    host shows up anywhere in the tree (paid or free — every host must be
    consciously sorted into one list or the other). That is a review-time
    gate, not a runtime one: it cannot stop a live call the day the code
    ships, but it cannot let a new host go unnoticed at merge time either.
  - `armed_spend(write_ahead, hosts)` trusts `write_ahead` to actually write
    before returning `True` — nothing here can verify that a callback which
    CLAIMS to have written a ledger record actually did (short of running
    it and re-reading the file back, which every real caller in this
    codebase already does via `ledger_record()`/`save_usage()`'s own
    True/False contract, T-066 R3-3). A test that arms with `lambda: True`
    is exercising something else on purpose (isolating `call()` from the
    ledger) — that remains a documented convention for tests, not something
    this module can rule out structurally.
  - Arming is scoped to a *host set*, not to a single call: everything
    inside one `with armed_spend(write_ahead, hosts=X):` block may make any
    number of calls to hosts in `X` (not to any other host). This is
    deliberate, not an oversight (round-1 finding D) — `ads-apply.py`
    legitimately records ONE write-ahead for a whole batch of operations
    and then performs many calls to fulfil it; making arming single-shot
    would break that batch write-ahead pattern the same review already
    verified as intentional (T-066 R3-4). What round-1 actually got wrong
    was allowing an arming for host A to also cover host B — that cross-host
    leak is what host-scoping removes.
"""

from __future__ import annotations

import contextvars
import urllib.parse
import urllib.request
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
    """A paid host (`PAID_HOSTS`) was contacted through
    `urllib.request.urlopen`/`requests` without an active `armed_spend()`
    naming that exact host — refused before any byte reached the network."""


def _host_of(url: Any) -> str:
    if hasattr(url, "get_full_url"):
        url = url.get_full_url()
    elif hasattr(url, "full_url"):
        url = url.full_url
    return (urllib.parse.urlsplit(str(url)).hostname or "").lower()


def _check_host(host: str) -> None:
    if host and host in PAID_HOSTS and host not in _ARMED_HOSTS.get():
        raise SpendNotArmedError(
            f"paid host {host!r} contacted outside armed_spend() for it — "
            "the write-ahead record for this call either was never made or "
            "does not cover this host (T-089 round 2: the refusal lives on "
            "the transport itself, there is no per-client wrapper to bypass)."
        )


@contextmanager
def armed_spend(write_ahead: Callable[[], bool], hosts: str | Iterable[str]) -> Iterator[None]:
    """The only legal way to allow a call to a `PAID_HOSTS` member. Runs
    `write_ahead()` FIRST; only a truthy result arms `hosts` for the
    duration of the `with` block — `write_ahead` is responsible for the
    actual disk write and for reporting truthfully whether it landed (the
    same bool contract `ledger_record()` already had, T-066 R3-3). `hosts`
    may be one hostname or several; every outbound call to one of them
    inside the block is allowed, calls to any other host are not."""
    normalized = frozenset(h.lower() for h in ((hosts,) if isinstance(hosts, str) else hosts))
    if not normalized:
        raise ValueError("armed_spend() requires at least one host")
    if not write_ahead():
        raise SpendNotArmedError(
            "write-ahead record did not land — refusing to arm any paid call."
        )
    token = _ARMED_HOSTS.set(_ARMED_HOSTS.get() | normalized)
    try:
        yield
    finally:
        _ARMED_HOSTS.reset(token)


# --- Install the transport-level gate. Runs once, at first import of this
# module (a normal package import is cached in sys.modules, so this body
# executes exactly once per process regardless of how many client scripts
# `from seo_cycle_core.spend_guard import ...`) — but the marker attribute
# below makes re-installation a no-op anyway, in case a future test or tool
# reloads this module explicitly. ---

#: The real, unwrapped implementations, kept as MODULE-level names (not
#: closure variables) so a test can `mock.patch.object(spend_guard,
#: "_real_urlopen", side_effect=AssertionError(...))` and get a hard proof
#: that the gate function below never reached them — the wrapper functions
#: look these up fresh on every call, not once at install time (round-2
#: review finding B: a bypass test must not just assert on the exception
#: type, it must be able to show the actual network primitive was never
#: touched).
_real_urlopen: Callable[..., Any] | None = None
_real_session_request: Callable[..., Any] | None = None


def _guarded_urlopen(url: Any, *args: Any, **kwargs: Any) -> Any:
    _check_host(_host_of(url))
    assert _real_urlopen is not None
    return _real_urlopen(url, *args, **kwargs)


def _guarded_session_request(self: Any, method: str, url: Any, *args: Any, **kwargs: Any) -> Any:
    _check_host(_host_of(url))
    assert _real_session_request is not None
    return _real_session_request(self, method, url, *args, **kwargs)


def _install_urllib_gate() -> None:
    global _real_urlopen
    current = urllib.request.urlopen
    if current is _guarded_urlopen:
        return
    _real_urlopen = current
    urllib.request.urlopen = _guarded_urlopen


def _install_requests_gate() -> None:
    global _real_session_request
    try:
        import requests.sessions
    except ImportError:
        return
    current = requests.sessions.Session.request
    if current is _guarded_session_request:
        return
    _real_session_request = current
    requests.sessions.Session.request = _guarded_session_request  # type: ignore[method-assign]


_install_urllib_gate()
_install_requests_gate()
