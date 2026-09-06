"""Shared money/quota-stop primitives for paid API clients (seo-cycle).

Third pass on this exact class of bug: T-046 and T-059 each fixed the stop in
`dataforseo-fetch.py` alone and declared the class closed; an independent
hostile QA run (2026-09-06, findings F-11/F-12/F-13) showed it was not — a
copy of the same stop in `spyfu-fetch.py` had none of the three fixes, and
`--budget` still accepted `nan`/`inf` in the "fixed" file. This module is the
one place the stop lives now; every paid client wires its own call/response
handling around these primitives instead of re-implementing them.

What one broken value used to do, per finding:
  F-11 — `argparse` with a bare `type=float` on `--budget` happily parses
         `nan`/`inf`/`-inf`; `min(nan, cap)` is `nan`, and `spent >= nan` is
         always False, so the stop silently never fires again.
  F-12 — a second client kept its own usage file with none of the guards:
         no value validation on read, a comparison that is always False for
         a non-numeric spend, an addition that poisons the file permanently,
         a non-atomic write that leaves a half-file on a crash, and no lock
         against concurrent runs racing on the same file.
  F-13 — spend is written only on the success path; an exit between "the
         paid call happened" and "the ledger was updated" (bad HTTP status,
         an unusable cost field) loses the ledger update even though the
         money was already spent.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import fcntl
import json
import math
import os
import pathlib
import re
import tempfile
from typing import Any, Iterator

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

DEFAULT_LEDGER_NAME = "_usage.json"


class ApiCallError(RuntimeError):
    """A paid/quota-limited API call failed AFTER being sent: HTTP error,
    network error, or a response body that isn't usable (not JSON, or valid
    JSON of the wrong shape — `null`, a bare list, a number).

    Every client's transport function should raise this instead of calling
    `sys.exit()` itself. From a billing point of view the request may already
    have been sent and even answered by the time parsing fails — the caller
    (which holds the usage-ledger lock) decides what to record before it
    decides whether to exit. Bypassing this (calling `sys.exit` inside the
    transport function) is exactly how F-13 reopened in round 2 of T-066:
    round-1 tests mocked the transport function itself, so the very layer
    that exited early was invisible to them."""


class UsageLedgerError(RuntimeError):
    """The usage-ledger file exists but cannot be trusted for money/quota
    arithmetic (corrupt JSON, wrong schema, garbled month, or a numeric field
    that fails `finite_nonneg`). MUST NOT be treated as "spent 0" by a
    caller — that is exactly how a budget stop gets silently disabled
    (T-059). The caller decides what to do: refuse by default, or an
    explicit `--force` to recompute the month from scratch."""


def finite_nonneg(x: object) -> bool:
    """True only for a value safe for money/counter arithmetic: a real
    number (not bool), not NaN/Infinity, not negative.

    `isinstance(x, (int, float))` alone is NOT enough: `json.loads` parses
    the bare literals `NaN`, `Infinity`, `-Infinity` into `float` by default,
    so they pass a type check but poison every comparison and addition that
    follows (`nan >= budget` is always False, `nan + cost` is `nan` forever).
    """
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def current_month() -> str:
    return datetime.date.today().strftime("%Y-%m")


def usage_file(out_dir: pathlib.Path, name: str = DEFAULT_LEDGER_NAME) -> pathlib.Path:
    return pathlib.Path(out_dir) / name


def load_usage(
    out_dir: pathlib.Path,
    numeric_fields: tuple[str, ...] = ("spent_usd",),
    *,
    name: str = DEFAULT_LEDGER_NAME,
) -> dict[str, Any]:
    """Read the monthly usage ledger.

    A missing file, or a file whose stored month is not the current one, is
    a legitimate empty state: `{"month": <current>, <field>: 0.0, ...}`.

    A PRESENT file that is unreadable, not a JSON object, has a garbled
    `month`, or any of `numeric_fields` failing `finite_nonneg` raises
    `UsageLedgerError` — never a silent zero.
    """
    f = usage_file(out_dir, name)
    month = current_month()
    empty: dict[str, Any] = {"month": month, **{field: 0.0 for field in numeric_fields}}
    if not f.exists():
        return dict(empty)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        raise UsageLedgerError(f"{f}: {e}") from e
    if not isinstance(data, dict):
        raise UsageLedgerError(f"{f}: ожидался JSON-объект, получено {type(data).__name__}")
    for field in numeric_fields:
        if field in data and not finite_nonneg(data[field]):
            raise UsageLedgerError(f"{f}: {field} непригоден для арифметики ({data[field]!r})")
    stored_month = data.get("month")
    if not isinstance(stored_month, str) or not MONTH_RE.match(stored_month):
        raise UsageLedgerError(f"{f}: поле month испорчено ({stored_month!r})")
    if stored_month != month:
        return dict(empty)
    merged = dict(empty)
    merged.update(data)
    return merged


def save_usage(out_dir: pathlib.Path, data: dict[str, Any], *, name: str = DEFAULT_LEDGER_NAME) -> None:
    """Atomic write: a temp file in the same directory, then `os.replace`.

    A reader never observes a half-written ledger on a crash mid-write —
    `os.replace` is atomic on the same filesystem, unlike a plain
    `write_text` which truncates the target before writing the new bytes.
    The temp file is removed if writing fails before the replace.
    """
    out_dir = pathlib.Path(out_dir)
    path = usage_file(out_dir, name)
    fd, tmp_name = tempfile.mkstemp(dir=out_dir, prefix=f".{name}-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


@contextlib.contextmanager
def usage_lock(out_dir: pathlib.Path, *, name: str = DEFAULT_LEDGER_NAME) -> Iterator[None]:
    """Exclusive file lock for the whole "read the ledger -> spend money ->
    write the ledger" critical section.

    Without it, two concurrent processes read the same stale ledger and the
    later write wins — the earlier process's spend is silently lost.
    """
    out_dir = pathlib.Path(out_dir)
    lock_path = out_dir / f"{name}.lock"
    with open(lock_path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def nonneg_finite_arg(flag_name: str):
    """Factory for an `argparse(type=...)` validator on any CLI number that
    feeds money/quota arithmetic downstream — not just `--budget`.

    R-3/R-4 (T-066, gate round 2): `--budget` was the only flag validated in
    round 1; `--cpm` and `--ttl` were left as bare `type=float`, so `--cpm nan`
    still poisoned `_usage.json` through `save_usage()` (the module built to
    stop exactly that), and `--ttl nan` made the on-disk cache always miss
    (`(now - mtime) / 86400 <= nan` is always False), turning every call
    paid. Any CLI flag whose value reaches money/quota math should use this,
    not a bare `type=float`.

    Rejects, at PARSE time, anything that would silently disable a
    downstream guard: non-numeric text, `nan`, `inf`, `-inf`, and negative
    numbers. Stock `argparse` with `type=float` accepts all of those —
    `float("nan")` and `float("inf")` are valid Python float literals.
    """
    def _validate(raw: str) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError) as e:
            raise argparse.ArgumentTypeError(f"{flag_name}: {raw!r} не число") from e
        if not finite_nonneg(value):
            raise argparse.ArgumentTypeError(
                f"{flag_name}: {raw!r} непригоден для денежной/количественной "
                f"арифметики (нужно конечное неотрицательное число)"
            )
        return value

    _validate.__name__ = f"nonneg_finite_arg_{flag_name.strip('-').replace('-', '_')}"
    return _validate


def budget_arg(raw: str) -> float:
    """`argparse(type=budget_arg)` for `--budget` specifically — kept as a
    named function (not just `nonneg_finite_arg("--budget")`) because it is
    imported and referenced directly by name in three clients and their
    tests; behavior is `nonneg_finite_arg("--budget")` (F-11)."""
    return nonneg_finite_arg("--budget")(raw)


def effective_budget(cli_budget: float, config_cap: object, *, cap_label: str = "конфиг") -> float:
    """`min(cli_budget, config_cap)`, guarding the config value the same way
    `budget_arg` guards the CLI one.

    `config_cap is None` (no cap configured, or no config found) falls back
    to `cli_budget` unchanged. A PRESENT but unusable cap value (wrong type,
    NaN, Infinity, negative) raises `ValueError` rather than silently
    falling back to `cli_budget` — a typo in the project config that quietly
    removes a human-lowered cap is exactly the class this module exists to
    close (T-059 review, red #1/#2: "the type check passes, the value is
    unusable for money").
    """
    if config_cap is None:
        return cli_budget
    if not finite_nonneg(config_cap):
        raise ValueError(f"{cap_label} непригоден для денежной арифметики ({config_cap!r})")
    cap_value: float = config_cap  # type: ignore[assignment]  # narrowed by finite_nonneg above
    return min(cli_budget, cap_value)
