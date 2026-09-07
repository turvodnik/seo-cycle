"""Single choke point every paid API call must pass through (T-089).

Context: T-066 spent six rounds turning "write-ahead the spend before the paid
call" into a per-client habit, verified case-by-case (dataforseo-fetch.py,
spyfu-fetch.py, ads-apply.py, yandex-direct-fetch.py, google-ads-fetch.py).
The hostile QA round for 2.2.0 (F-1) found a sixth paid client,
google-nlp-audit.py, that never got the memo: the *value* guard (numeric
fields checked structurally, not by name — T-066 R4-1) had moved from an
enumerated list to a trait, but the *write-ahead* guard was still hand-placed
per file, so a client could exist without it and nothing would notice.

This module makes "paid call without a preceding, successful write-ahead
record" a structural impossibility instead of a code-review habit:

- `@guarded_spend` decorates the function that actually performs the paid
  network call (`call()`, `call_feature()`, `apply_direct()`,
  `live_fetch()`, `gaql_search()`, ...). Calling it directly raises
  `SpendNotArmedError` — there is no successful path that skips the guard.
- `armed_spend(write_ahead)` is the only way to arm it. It runs
  `write_ahead()` FIRST; only if that returns a truthy value does it allow a
  `@guarded_spend` call inside the `with` block. `write_ahead` must itself do
  the actual disk write (increment + save the usage/ledger file) and return
  whether it landed — the same contract `ledger_record()` already had
  (T-066 R3-3).

An eighth client (or a ninth) that adds a paid call by defining a plain
function and calling it does not opt out of this by omission: forgetting the
decorator only means the new call is unguarded (a code-review problem, same
as before), but a client that reuses `@guarded_spend` and reuses a paid call
under `armed_spend()` cannot go out to the network before the write lands —
and calling the decorated function outside `armed_spend()` (accidentally, or
via a hostile bypass that skips the ledger write and calls the network
function straight) raises immediately, loudly, before doing anything.
"""

from __future__ import annotations

import contextvars
import functools
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

_ARMED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "seo_cycle_spend_armed", default=False
)

F = TypeVar("F", bound=Callable[..., Any])


class SpendNotArmedError(RuntimeError):
    """A @guarded_spend function ran (or was about to run) outside
    armed_spend(), or armed_spend()'s write-ahead callback refused to arm.
    Either way: no paid call happens without a landed write-ahead record."""


def guarded_spend(fn: F) -> F:
    """Wrap a paid-call function so it refuses to run unless a write-ahead
    record has already landed via armed_spend() in the current control flow
    (contextvars propagate into the same thread's nested calls, not across
    threads/tasks — the paid clients here are single-threaded per process)."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not _ARMED.get():
            raise SpendNotArmedError(
                f"{fn.__module__}.{fn.__qualname__}: paid call attempted "
                "outside armed_spend() — a write-ahead ledger record must "
                "land BEFORE this call, not after (T-066/T-089). This is a "
                "structural refusal, not a warning."
            )
        return fn(*args, **kwargs)

    wrapper.__wrapped_paid_call__ = True  # type: ignore[attr-defined]
    return wrapper  # type: ignore[return-value]


@contextmanager
def armed_spend(write_ahead: Callable[[], bool]) -> Iterator[None]:
    """Run `write_ahead()`; only a truthy result arms the guard for the
    duration of the `with` block. `write_ahead` is expected to perform the
    actual disk write itself and report whether it landed (mirrors
    ledger_record()'s existing bool contract) — this context manager does
    not know how to write any client's usage file, on purpose: that stays
    client-specific, only the ordering and the refusal are shared."""
    if not write_ahead():
        raise SpendNotArmedError(
            "write-ahead record did not land — refusing the paid call "
            "instead of proceeding without evidence of the spend."
        )
    token = _ARMED.set(True)
    try:
        yield
    finally:
        _ARMED.reset(token)
