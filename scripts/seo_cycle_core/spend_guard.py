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
    `socket`/`socket.gethostbyname`/`gethostbyname_ex`) that runs IN A
    PROCESS WHERE THIS MODULE WAS IMPORTED cannot reach a `PAID_HOSTS`
    member without an active `armed_spend()` for that exact host, AS LONG
    AS IT WENT THROUGH ONE OF THE PATCHED NAMES (see the next bullet for
    the one that doesn't).
  - A client reusing an ALREADY-REGISTERED host needs zero code of its own
    referencing this module to be protected, AS LONG AS its own process
    imported anything from the `seo_cycle_core` package (see below —
    `seo_cycle_core/__init__.py` imports this module as a side effect of
    package import, not as something each client has to remember).
  - T-094 (F-2, the QA report's FOURTH independent run), PARTIALLY — read
    the next bullet in "Does NOT buy" too, this one overstated itself in
    round 1 and an independent gate caught it live: a `HTTP_PROXY`/
    `HTTPS_PROXY` env var set in the process, for an **HTTPS** target
    (`urllib`/`requests` both build a CONNECT tunnel for HTTPS-through-
    proxy). Previously a live gap, not named anywhere: with a proxy
    configured, `socket.getaddrinfo`/`socket.socket.connect` above only
    ever see the PROXY's host — the paid hostname travels inside the
    CONNECT tunnel request, built by `http.client.HTTPConnection.
    set_tunnel(host, ...)`. Not theoretical: `config/region-profiles/
    ru.yaml` recommends proxying DataForSEO for the RU region.
    `http.client.HTTPConnection.set_tunnel` is now patched the same way as
    the resolver functions above — `urllib.request` (`AbstractHTTPHandler.
    do_open` calls `h.set_tunnel(req._tunnel_host, ...)` directly) and
    `requests`/`urllib3` (`HTTPSConnectionPool._prepare_proxy` calls
    `conn.set_tunnel(...)`, whose own override ends in `super().
    set_tunnel(host, ...)` — the same patched base-class name) both funnel
    through this one function. T-094 round 2 (R-1, independent gate,
    2026-09-07): round 1 also missed that `req._tunnel_host`/the tunnel
    host arrive WITH an explicit port when the target URL spells one out
    (`https://api.dataforseo.com:443/...`) — `"api.dataforseo.com:443" in
    PAID_HOSTS` never matched the bare name. `_normalize_host` now strips
    a trailing `:port` (`_strip_port`, IPv6-bracket-aware) before the
    `PAID_HOSTS` comparison, closing that specific escape too — reproduced
    against a live local listener (no external byte), confirmed refused
    after the fix with the same harness.

Does NOT buy — this is the boundary, stated for the release notes, not
just this docstring:
  - **A `HTTP_PROXY`/`HTTPS_PROXY`-configured proxy AND a plain (unencrypted)
    `http://` target.** T-094 round 2 (R-1, independent gate, 2026-09-07):
    an HTTPS target through a proxy builds a CONNECT tunnel (gated above —
    `_guarded_set_tunnel`). A PLAIN `http://` target through a proxy does
    NOT: `urllib`/`requests` rewrite the request into an absolute-URI GET
    sent directly to the proxy (`GET http://api.dataforseo.com/v3/x
    HTTP/1.1`) — no `set_tunnel()` call happens at all, and
    `socket.getaddrinfo`/`connect` only ever see the proxy's own address.
    Reproduced live against a local listener (no external byte): the paid
    hostname arrived in the request line, unmatched by any patched call.
    Closing this would mean intercepting `http.client.HTTPConnection.
    putrequest`/the URI-rewrite step itself, a different (and larger)
    change than this ticket's one-line budget — not attempted here, named
    instead of silently left implied-closed by the CONNECT-tunnel fix
    above. Why this is 🟡, not 🔴, for THIS codebase specifically: every
    paid client shipped here (`dataforseo-fetch.py`, `spyfu-fetch.py`,
    `serpstat-fetch.py`, `serpstat-audit.py`, `keyso-save.py`,
    `yandex-direct-fetch.py`, `atp-fetch.py`) hardcodes an `https://` base
    URL with no port, and none of them read a proxy setting out of config
    (`grep -rn "proxies=\\|ProxyHandler\\|set_proxy" scripts/` minus this
    module — empty) — reaching this gap from code already in this repo
    would require a NEW client written to use plain HTTP for a paid host,
    which `tests/test_t089_closed_world_hosts.py` would catch as an
    unclassified/unguarded literal the moment it's written as one whole
    string. The risk is real for a proxy configured via environment
    variables on a hand-written or future ad hoc script, not for the
    shipped client set.
  - **A process that never imports anything from `seo_cycle_core` at all**
    is not gated at runtime. T-092 (F-2, the QA report's THIRD independent
    run to catch this claim overstating itself): this docstring used to say
    "every existing client uses shared seo_cycle_core helpers... so today
    this is not a live gap" — false as written: at the time it was
    checked (`for f in scripts/*.py; do grep -qE "urlopen|requests\\.(get|
    post|Session)" $f && ! grep -q seo_cycle_core $f && echo $f; done`),
    NINE network scripts imported nothing from this package, two of them
    (`serpstat-fetch.py`, `atp-fetch.py`) hitting hosts this codebase
    itself classifies as paid — a live gap, not a theoretical one. Both are
    now fixed (T-092: they import `seo_cycle_core` and call `armed_spend()`
    like every other paid client). Re-running the same command today still
    finds seven scripts with no `seo_cycle_core` import at all
    (`ai-bot-access-check.py`, `deindex-detect.py`, `google-suggest.py`,
    `metrika-fetch.py`, `psi-fetch.py`, `webmaster-fetch.py`,
    `yandex-suggest.py`) — checked by hand against `PAID_HOSTS`, none of
    them ever mentions a paid hostname, only free ones (Google/Yandex
    suggest, PSI, webmaster, deindex checks, bot-access probes), so this IS
    a live-gap-free state for THOSE SEVEN specifically, today — not a
    property of "every client" as a class, and not something to take on
    faith the next time a client is added here without re-running the
    command above. The compensating control for a genuinely uncovered case
    is NOT runtime: `tests/test_t089_closed_world_hosts.py` fails CI when a
    script contains a `PAID_HOSTS` hostname (or any unclassified one)
    written as ONE WHOLE STRING LITERAL, without importing `seo_cycle_core`
    and without the text `armed_spend(` anywhere in the file — a static,
    review-time check, not a runtime one, and textual, not semantic (it
    cannot verify `armed_spend(` is used correctly, or even that it isn't
    just a comment). Round-3 independent review (R3-3) found the actual
    limit narrower than this docstring previously claimed: a hostname
    assembled from pieces — string concatenation, an environment variable,
    `.format()`/an f-string built from a separate constant — is invisible
    to this scan for the SAME reason a whole new unclassified host already
    was (documented in that test's own docstring) — the regex only sees
    literal `http(s)://host` text. Combined with no `seo_cycle_core`
    import, such a file is caught by NEITHER half of this mechanism: not
    the runtime gate (never imported), not the static scan (no whole
    literal to match). Closing this fully would mean either full
    control-flow/string-flow static analysis (not attempted — expensive
    and still evadable one layer further) or truly universal runtime
    activation independent of what a file imports (attempted via
    `sitecustomize.py`-style auto-loading and abandoned — see the T-089
    packet's "Результат" for why: it only auto-activates when `PYTHONPATH`
    already includes the scripts directory at interpreter start, which is
    not how any of the ~97 commands here are actually invoked). This
    specific combination — split/constructed literal AND no shared import —
    is accepted as an open gap, not a closed one.
  - **A subprocess started via `subprocess`/`os.system`/a shell script**
    (this repo already has one: `scripts/nw-cli.sh` calls `curl` directly;
    T-092 names a second, paid one — `scripts/writerzen-browser-collect.py`
    drives `writerzen-browser-runner.mjs`, a Node.js/Playwright subprocess
    that dials `app.writerzen.net` in its OWN process) is a separate OS
    process with its own Python interpreter, a JS runtime, or no
    interpreter at all — nothing importable in THIS process reaches into
    that one. Same compensating control as above: the static scan covers
    `scripts/*.py` only (documented limitation, `tests/
    test_t089_closed_world_hosts.py`'s own docstring says so) — shell/curl
    call sites are not scanned by either half of this mechanism today.
    `app.writerzen.net`/`neuronwriter.com` are deliberately kept out of
    `PAID_HOSTS` for this exact reason (see `PAID_SERVICES_WITHOUT_HOST_GATE`
    above): putting a host this process never dials into `PAID_HOSTS` would
    not add protection, only a permanently-failing static-scan requirement
    on files that make a documentary-only mention of it.
  - **`config/project.template.yaml`'s `mcp_server: dataforseo` path.** The
    template documents TWO ways to reach DataForSEO: `helper_script`
    (`scripts/dataforseo-fetch.py`, gated — `armed_spend()`, write-ahead,
    `PAID_HOSTS`) and `mcp_server: dataforseo`, a Model Context Protocol
    server — a THIRD OS process, started and owned by whatever MCP client
    the user runs (Claude Code, an IDE, etc.), not by any script in this
    repo. This module's socket patch only ever affects the Python process
    that imports it; an MCP server process is never that process, by
    construction, the same reason a WriterZen subprocess is out of reach
    above. Accepted as a named, out-of-scope path (T-092, F-1's "sixth
    path") — not something a helper-script-level fix can close, and not
    claimed as covered anywhere in this file or the release notes.
  - **A raw socket connecting to an already-resolved numeric IP address**
    (no hostname anywhere in the call) cannot be matched against
    `PAID_HOSTS` — there is no name to compare. Nothing in this module (or
    a hostname-based list in general) can close this without shipping an
    IP-range registry instead, which was not asked for and brings its own
    staleness problem (cloud IPs rotate). Accepted as out of scope.
  - **`_socket.getaddrinfo` and other names on the C `_socket` extension
    module itself** (as opposed to the pure-Python `socket` module's
    re-exports, which ARE patched above) are not intercepted. Patching a
    C-extension module's own attributes is a different, more fragile kind
    of monkeypatch than reassigning a Python-level name, and no code in
    this repository calls `_socket.*` directly today — named as a boundary
    rather than closed (round-3 independent review, R3-2).
  - **Restoring the saved originals and calling them, or the un-patched
    primitive, directly.** `_real_getaddrinfo`/`_real_connect`/
    `_real_connect_ex`/`_real_gethostbyname`/`_real_gethostbyname_ex` are
    deliberately public module attributes (tests need to mock them, see
    their own docstring) — `socket.getaddrinfo =
    spend_guard._real_getaddrinfo` followed by a normal `urlopen()` call
    reaches the real resolver with no check at all (round-3 independent
    review, R3-1: this was claimed closed here in round 3 and was not —
    two of the review's probes did exactly this and reached a real DNS
    lookup for `api.dataforseo.com`, no further, before the review's own
    shim caught the egress). This is NOT fixable by hiding the names
    better: any code with write access to this module's namespace (or to
    `socket`'s) can equally do `importlib.reload(socket)` to get a
    completely fresh, unpatched module — undoing an in-process monkeypatch
    from within the same process is fundamentally not preventable by a
    monkeypatch, in this or any other shape. The actual boundary this
    module enforces is: code that does NOT deliberately try to undo the
    patch is gated; code that deliberately reaches for the saved original
    or reloads `socket` is a supply-chain/code-review question (would this
    line survive review?), not a runtime one this mechanism can answer.
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
    its network calls (checked, T-092: no `threading`/`concurrent.futures`/
    `asyncio` import in any of the clients calling `armed_spend()` — count
    verified by `grep -rl 'armed_spend(' scripts/*.py | grep -v
    seo_cycle_core | wc -l`, not carried by hand between releases) —
    parallel *processes* are unaffected (armed state lives per-process
    already, by construction) and are the actual concurrency model these
    CLI tools use.
"""

from __future__ import annotations

import contextvars
import http.client
import socket
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator

# T-092: single source of truth for "which billing service owns which
# host(s) this codebase's own Python process can actually reach". Every
# other place in the repo that needs a paid-service name -> host mapping
# (or the flat PAID_HOSTS set) derives it from THIS dict instead of keeping
# a second hand-maintained list (that was exactly F-1's self-contradiction:
# usage-ledger.py's PAID_API_SERVICES called serpstat/neuronwriter/
# answerthepublic paid while tests/test_t089_closed_world_hosts.py's
# FREE_HOSTS certified their hostnames as free).
#
# A service with NO entry here is either not paid, or paid but reached
# through a channel this Python-level socket gate structurally cannot see
# (a separate OS process — see PAID_SERVICES_WITHOUT_HOST_GATE below and the
# "Граница защиты" section of CHANGELOG.md for why (a) is impossible there).
PAID_SERVICE_HOSTS: "dict[str, frozenset[str]]" = {
    "dataforseo": frozenset({"api.dataforseo.com"}),
    "spyfu": frozenset({"api.spyfu.com"}),
    "yandex_direct": frozenset({"api.direct.yandex.com", "api-sandbox.direct.yandex.com"}),
    "google_ads": frozenset({"googleads.googleapis.com"}),
    "google_nlp": frozenset({"language.googleapis.com"}),
    "keyso": frozenset({"api.keys.so"}),
    "serpstat": frozenset({"api.serpstat.com"}),
    "answerthepublic": frozenset({"api.answerthepublic.com"}),
    "xmlriver": frozenset({"xmlriver.com"}),
}

# Paid services this repo bills/tracks (scripts/usage-ledger.py:PAID_API_SERVICES
# derives from this + PAID_SERVICE_HOSTS) but whose calls this Python-level
# socket gate cannot see, by construction — not an oversight, a documented
# known exception (path (b), T-092):
#   neuronwriter — no Python API client exists in scripts/*.py at all; usage
#     is imported from a manually-maintained seo/neuronwriter-limits.yaml
#     (see usage-ledger.py:imported_neuronwriter_limits), not a live call
#     this repo's process makes.
#   writerzen    — scripts/writerzen-browser-collect.py drives a *separate*
#     Node.js subprocess (writerzen-browser-runner.mjs, Playwright) that
#     makes its own outbound HTTPS connections in ITS OWN process; this
#     module's socket.getaddrinfo/socket.connect patch only affects the
#     Python process it is imported into, so it cannot gate a child
#     process's network stack. Rewriting WriterZen collection as a direct
#     HTTP client is out of scope here (no documented public API — this is
#     why it is scraped via a logged-in browser session in the first
#     place); flat subscription billing (like Keys.so), not per-call
#     $-metering, so a per-call write-ahead ledger entry would not mean
#     anything additional here either.
PAID_SERVICES_WITHOUT_HOST_GATE = frozenset({"neuronwriter", "writerzen"})

# Hosts that MUST NOT be contacted by this codebase's own outbound calls
# without an active armed_spend() naming that host. Keep in sync with
# tests/test_t089_closed_world_hosts.py (FREE_HOSTS there covers every other
# host any script in this repo actually references). Derived from
# PAID_SERVICE_HOSTS above — do not hand-maintain a second copy.
PAID_HOSTS = frozenset().union(*PAID_SERVICE_HOSTS.values())

_ARMED_HOSTS: "contextvars.ContextVar[frozenset[str]]" = contextvars.ContextVar(
    "seo_cycle_armed_hosts", default=frozenset()
)


class SpendNotArmedError(RuntimeError):
    """A paid host (`PAID_HOSTS`) was about to be resolved/connected to
    without an active `armed_spend()` naming that exact host — refused
    before any byte reached the network (round 3: caught at DNS resolution
    or raw socket connect, whichever happens first)."""


def _strip_port(host: str) -> str:
    """T-094 round 2 (R-1): `_guarded_set_tunnel` below can receive
    `req._tunnel_host` WITH an explicit port attached
    (`api.dataforseo.com:443`, from a URL that spells the port out —
    `AbstractHTTPHandler.do_open` passes `req._tunnel_host` as-is, it does
    not split it) — `"api.dataforseo.com:443" in PAID_HOSTS` never matches
    the bare hostname, an independent gate reproduced this live against a
    local listener. The socket-layer callers (`getaddrinfo`/`connect`/
    `connect_ex`/`gethostbyname*`) never pass a combined `host:port` string
    (address tuples always carry host and port as separate elements), so
    this only ever fires for the tunnel path in practice — kept host-only
    (no guessing a default port), applied unconditionally because it is a
    no-op for anything that isn't `host:port` shaped.

    IPv6-aware: a bracketed `[::1]:443` strips to `::1`; a bare `::1`
    (multiple colons, no brackets — never has a port attached, brackets are
    mandatory for that) is left untouched; the single-colon `host:port`
    shape is the only one stripped."""
    if host.startswith("[") and "]" in host:
        return host[1:host.index("]")]
    if host.count(":") == 1:
        left, _, maybe_port = host.rpartition(":")
        if maybe_port.isdigit():
            return left
    return host


def _normalize_host(host: Any) -> str:
    """`bytes`/`bytearray` (round-2 bypass 11: `_host_of()` used to `str()`
    a bytes URL and get `"b'https://...'"`, hostname `""`, silent pass) and
    a trailing dot (bypass 08: `api.dataforseo.com.` is a valid absolute DNS
    name PAID_HOSTS didn't match) are normalized once, here — the one place
    every caller (getaddrinfo, connect, connect_ex, gethostbyname*, the
    proxy tunnel) goes through. A trailing `:port` (T-094 round 2, R-1 —
    see `_strip_port`) is normalized here too, same reasoning."""
    if host is None:
        return ""
    if isinstance(host, (bytes, bytearray)):
        try:
            host = host.decode("idna")
        except (UnicodeError, UnicodeDecodeError):
            host = host.decode("utf-8", "replace")
    return _strip_port(str(host).strip().lower().rstrip("."))


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
    R2-5: a mutated/uninstalled gate must not silently let the test suite's
    own real network calls through; asserting this in setUp turns that into
    an immediate, obvious failure instead of a live DNS lookup)."""
    return (
        socket.getaddrinfo is _guarded_getaddrinfo
        and socket.socket.connect is _guarded_connect
        and socket.socket.connect_ex is _guarded_connect_ex
        and socket.gethostbyname is _guarded_gethostbyname
        and socket.gethostbyname_ex is _guarded_gethostbyname_ex
        and http.client.HTTPConnection.set_tunnel is _guarded_set_tunnel
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
_real_gethostbyname: Callable[..., Any] | None = None
_real_gethostbyname_ex: Callable[..., Any] | None = None
_real_set_tunnel: Callable[..., Any] | None = None


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


def _guarded_gethostbyname(host: Any) -> Any:
    # R3-2 (round-3 independent gate): `socket.gethostbyname`/`_ex` are the
    # same class of resolver as `getaddrinfo` — a hostname is present in the
    # call, and round 3 left it unpatched even though the same `_check_host`
    # already applies cleanly. `_socket.getaddrinfo` (the C extension module
    # underlying all of these) is NOT patched here — see the module
    # docstring's boundary statement for why that one is named, not closed.
    _check_host(_normalize_host(host))
    assert _real_gethostbyname is not None
    return _real_gethostbyname(host)


def _guarded_gethostbyname_ex(host: Any) -> Any:
    _check_host(_normalize_host(host))
    assert _real_gethostbyname_ex is not None
    return _real_gethostbyname_ex(host)


def _guarded_set_tunnel(
    self: "http.client.HTTPConnection", host: str, *args: Any, **kwargs: Any
) -> Any:
    # T-094 (F-2): the CONNECT-tunnel path. With an HTTP(S)_PROXY env var
    # set, socket.getaddrinfo/connect above only ever see the PROXY's host —
    # the paid hostname travels inside the CONNECT request's Host header,
    # built here by http.client.HTTPConnection.set_tunnel(host, ...), which
    # every proxied caller in this codebase's dependency tree funnels
    # through: urllib.request.AbstractHTTPHandler.do_open calls
    # `h.set_tunnel(req._tunnel_host, ...)` directly; urllib3's (requests')
    # HTTPSConnectionPool._prepare_proxy calls `conn.set_tunnel(...)`, whose
    # own set_tunnel override ends in `super().set_tunnel(host, ...)` —
    # i.e. THIS function, once patched on the base class. Checked here,
    # before the CONNECT request is written, closes the gap named in
    # CHANGELOG.md's money boundary section: a paid host reached only
    # through a set proxy env var used to bypass the gate entirely.
    _check_host(_normalize_host(host))
    assert _real_set_tunnel is not None
    return _real_set_tunnel(self, host, *args, **kwargs)


def _install() -> None:
    global _real_getaddrinfo, _real_connect, _real_connect_ex
    global _real_gethostbyname, _real_gethostbyname_ex, _real_set_tunnel
    if socket.getaddrinfo is not _guarded_getaddrinfo:
        _real_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = _guarded_getaddrinfo
    if socket.socket.connect is not _guarded_connect:
        _real_connect = socket.socket.connect
        socket.socket.connect = _guarded_connect  # type: ignore[method-assign,assignment]
    if socket.socket.connect_ex is not _guarded_connect_ex:
        _real_connect_ex = socket.socket.connect_ex
        socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign,assignment]
    if socket.gethostbyname is not _guarded_gethostbyname:
        _real_gethostbyname = socket.gethostbyname
        socket.gethostbyname = _guarded_gethostbyname
    if socket.gethostbyname_ex is not _guarded_gethostbyname_ex:
        _real_gethostbyname_ex = socket.gethostbyname_ex
        socket.gethostbyname_ex = _guarded_gethostbyname_ex
    if http.client.HTTPConnection.set_tunnel is not _guarded_set_tunnel:
        _real_set_tunnel = http.client.HTTPConnection.set_tunnel
        http.client.HTTPConnection.set_tunnel = _guarded_set_tunnel  # type: ignore[method-assign,assignment]


_install()
