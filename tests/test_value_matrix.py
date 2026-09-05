#!/usr/bin/env python3
"""T-063 gate round 2 (🟡C): the acceptance criterion the gate replaced
"grep for the pattern" with, in the gate's own words:

    Матрица значений `0, "", None, "abc", [1], {}, "2.5", 1e3, .inf, -.inf,
    .nan, 10**400, True` прогоняется на каждом числовом ключе конфига,
    поведение сравнивается с базовой версией. Расхождение допустимо ТОЛЬКО
    там, где базовая версия падала. Любое сужение приёма на здоровом
    конфиге — дефект.

Both regressions this ticket introduced (🔴A: `coerce_float()` rejecting a
legitimate `.inf` result; 🔴B: `coerce_int()` narrowing `int(numeric(x,d))`'s
float-first parse) would have been caught immediately by this test, because
both silently changed the OUTPUT for an input the historical code accepted
without raising — which is exactly what this file checks, for every shape
of call site `coerce_int()`/`coerce_float()` replaced.

Rather than re-invoking 45 individual scripts against a BASE git worktree
(slow, and duplicates what `tests/test_coerce_config_sites.py` already
proves per-site), this models each ORIGINAL expression `coerce_int()`/
`coerce_float()` replaced as a plain Python reference function — precisely
what was at each call site on `origin/main`, reconstructed from the diff —
and asserts: for every matrix value, if the ORIGINAL expression did not
raise, `coerce_int()`/`coerce_float()` must return the IDENTICAL value
(bit-for-bit; NaN compared via `math.isnan` since `nan != nan`). Where the
original DID raise, any non-raising HEAD behavior is accepted (that's the
whole point of the ticket).

The three call-site SHAPES below cover all 44 `coerce_int`/`coerce_float`
call sites in the tree (see the AST-count command in CHANGELOG.md) — every
site is either:
  (a) `int(value or default)` / `float(value or default)` — the majority
      shape, `falsy_to_default=True` (default);
  (b) a bare `int(value)` / `float(value)` where the ORIGINAL had no
      `or default` (value already resolved via `.get(key, default)` or
      `nested_get(..., default)`, so only an explicit `None` needs the
      default) — `falsy_to_default=False`;
  (c) `int(numeric(value, default))` — `numeric()` parses via `float()`
      first, so a numeric-looking STRING works — `falsy_to_default=False,
      via_float=True` (the shape spend-guard.py/launch-plan.py needed).
"""

from __future__ import annotations

import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.config import coerce_float, coerce_int  # noqa: E402

MATRIX = [0, "", None, "abc", [1], {}, "2.5", 1e3, float("inf"), float("-inf"), float("nan"), 10**400, True]


def _same(a: object, b: object) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b and type(a) is type(b)


# ---- Reference implementations of the ORIGINAL (pre-T-063) expressions ----

def orig_int_or_default(value: object, default: int) -> int:
    """`int(value or default)` — shape (a), e.g.
    `int(nested_get(cfg, "kpi.months_to_target", 6) or 6)`."""
    return int(value or default)  # type: ignore[arg-type]


def orig_float_or_default(value: object, default: float) -> float:
    """`float(value or default)` — shape (a), e.g.
    `float(nested_get(cfg, "kpi.lead_conversion_rate", 0.02) or 0.02)`."""
    return float(value or default)  # type: ignore[arg-type]


def orig_bare_int(value: object, default: int) -> int:
    """`int(value)` on an ALREADY-`.get(key, default)`-resolved value —
    shape (b), e.g. `int(caps.get("max_raw_rows_loaded", 200))`. Only an
    explicit `None` in the config needs the Python-level default; a
    present-but-falsy `0` was never touched by `or` here."""
    return int(default if value is None else value)  # type: ignore[arg-type]


def orig_bare_float(value: object, default: float) -> float:
    """`float(value)` on an already-resolved value — shape (b), e.g.
    `float(ads.get("cache_ttl_hours", 24))`."""
    return float(default if value is None else value)  # type: ignore[arg-type]


def orig_numeric(value: object, default: float) -> float:
    """The shared `numeric()` helper (T-052/T-053), reference copy: never
    raises, parses via `float()`."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return default


def orig_int_via_numeric(value: object, default: int) -> int:
    """`int(numeric(value, default))` — shape (c), spend-guard.py/
    launch-plan.py's original (before T-063 touched it, and again before
    the gate's 🔴B fix restored this exact parse order)."""
    return int(orig_numeric(value, default))


class ValueMatrixTest(unittest.TestCase):
    """One (shape, default-int-or-float) pair per subTest axis; every
    matrix value run through both the original reference and the current
    `coerce_int()`/`coerce_float()` call with matching flags."""

    def _check(self, orig_fn, coerce_fn, default, **coerce_kwargs) -> None:
        for value in MATRIX:
            with self.subTest(shape=orig_fn.__name__, value=value):
                try:
                    original = orig_fn(value, default)
                    original_raised = False
                except (TypeError, ValueError, OverflowError):
                    original_raised = True

                # coerce_int()/coerce_float() must NEVER raise — that's the
                # ticket's core, unconditional guarantee.
                result = coerce_fn(value, default, **coerce_kwargs)

                if not original_raised:
                    self.assertTrue(
                        _same(result, original),
                        f"{orig_fn.__name__}({value!r}, {default!r}): "
                        f"original={original!r} ({type(original).__name__}) but "
                        f"coerce={result!r} ({type(result).__name__}) — "
                        f"narrowed/changed accepted-input behavior",
                    )
                # else: original crashed on this input — any non-raising
                # HEAD behavior is a fix, not a regression. Nothing to
                # assert beyond "coerce_fn didn't raise" above.

    def test_shape_a_int_or_default(self) -> None:
        """falsy_to_default=True (default) — e.g. `kpi.months_to_target`,
        `rag.chunk_chars`, `pulse.stale_after_days`."""
        self._check(orig_int_or_default, coerce_int, 6)

    def test_shape_a_float_or_default(self) -> None:
        """e.g. `kpi.lead_conversion_rate`, `pulse.drop_alert_pct`."""
        self._check(orig_float_or_default, coerce_float, 0.02)

    def test_shape_b_bare_int_falsy_to_default_false(self) -> None:
        """e.g. `context-pack.py`/`context.py`/`token-waste-audit.py`'s
        `governance.token_policy.*` caps, `ads.apply.max_changes_per_run`."""
        self._check(orig_bare_int, coerce_int, 200, falsy_to_default=False)

    def test_shape_b_bare_float_falsy_to_default_false(self) -> None:
        """e.g. `ads.cache_ttl_hours`, `ads.apply.max_daily_budget`."""
        self._check(orig_bare_float, coerce_float, 24, falsy_to_default=False)

    def test_shape_c_int_via_numeric_falsy_to_default_false(self) -> None:
        """e.g. `spend-guard.py`/`launch-plan.py`'s six
        `governance.token_policy.*` keys — the 🔴B regression's exact shape."""
        self._check(orig_int_via_numeric, coerce_int, 200, falsy_to_default=False, via_float=True)


class NonCoerceCrashSiteMatrixTest(unittest.TestCase):
    """Places the class-closing fix does NOT go through `coerce_int()`/
    `coerce_float()` at all (a helper consolidation, a downstream
    `safe_round()`, or a narrow try/except widening) — same matrix,
    checked against the actual function, not a reference model, since
    there's no single reusable "shape" to abstract."""

    def test_numeric_never_raises_across_the_matrix(self) -> None:
        """The canonical `numeric()` (now also used by
        validate-config.py/growth-roadmap.py/triggers-eval.py after
        consolidation) must never raise, for any matrix value."""
        from seo_cycle_core.config import numeric
        for value in MATRIX:
            with self.subTest(value=value):
                numeric(value, 0)  # must not raise

    def test_safe_round_never_raises_across_the_matrix(self) -> None:
        from seo_cycle_core.config import safe_round
        for value in MATRIX:
            with self.subTest(value=value):
                try:
                    numeric_value = float(value) if not isinstance(value, (list, dict)) else float("nan")
                except (TypeError, ValueError, OverflowError):
                    continue
                safe_round(numeric_value)  # must not raise
                safe_round(numeric_value, 1)  # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
