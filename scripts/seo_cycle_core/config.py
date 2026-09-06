"""Config, path, and parsing helpers shared by seo-cycle scripts."""

from __future__ import annotations

import pathlib
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - callers surface this during CLI startup
    yaml = None


CONFIG_SEARCH_PATHS = (
    "seo-cycle.yaml",
    ".seo-cycle.yaml",
    "seo/seo-cycle.yaml",
    ".claude/seo-cycle.yaml",
)


def skill_root(current_file: str | pathlib.Path | None = None) -> pathlib.Path:
    if current_file:
        return pathlib.Path(current_file).resolve().parent.parent
    return pathlib.Path(__file__).resolve().parents[2]


def find_config(start_dir: pathlib.Path) -> pathlib.Path | None:
    for rel in CONFIG_SEARCH_PATHS:
        path = start_dir / rel
        if path.exists():
            return path
    return None


def project_root_for(cfg_path: pathlib.Path) -> pathlib.Path:
    if cfg_path.name in (".seo-cycle.yaml", "seo-cycle.yaml"):
        return cfg_path.parent
    if "/seo/" in str(cfg_path) or "/.claude/" in str(cfg_path):
        return cfg_path.parent.parent
    return cfg_path.parent


def package_project_root(package_dir: pathlib.Path) -> pathlib.Path:
    for candidate in [package_dir, *package_dir.parents]:
        if (candidate / "seo-cycle.yaml").exists():
            return candidate
    return package_dir.parent


def rel_path(project_root: pathlib.Path, raw: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path


def rel_display(project_root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    """Load a YAML file as a dict, or refuse to hand back garbage.

    T-067 (F-35/F-26/F-36): every one of the ~100 call sites across
    `scripts/` treats the return value as "a dict, safe to `.get()`" — that
    was true only for a well-formed file. A tab in the indent, a top-level
    value that is a string/list/number instead of a mapping, or a file that
    isn't valid UTF-8 all used to reach here and either blow up with a raw
    `yaml.scanner.ScannerError` traceback two frames below the caller's own
    code, or silently hand back a non-dict that crashed on the NEXT
    `.get()` call with an unrelated-looking `AttributeError` (exactly the
    F-26/F-36 class this ticket also closes). Every caller of this
    function is a CLI entrypoint's `main()` — none of them has a reason to
    "keep going" on an unparseable config, and asking every one of the ~100
    call sites to add its own try/except would reopen the class at any
    site someone forgets (the same failure mode T-052/T-063 called out for
    per-callsite fixes) — so the fix lives here, once: print a short,
    coordinate-bearing message to stderr and exit(2) instead of returning.
    This is deliberately NOT "raise and let the caller decide" — there is
    no caller in this tree for which continuing past an unparseable config
    is correct.

    A MISSING file is not an error here (unchanged behavior) — some
    callers legitimately run with no config yet (setup/onboarding wizards,
    multi-project scans). That case still returns `{}`.
    """
    if yaml is None:
        return {}
    # `.exists()` follows symlinks and reports "missing" for a broken link
    # (F-42) — `.is_symlink()` catches that case so it isn't confused with
    # "no config yet".
    if not path.exists() and not path.is_symlink():
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"ERROR: {path}: не удалось прочитать конфиг: {exc}", file=sys.stderr)
        sys.exit(2)
    try:
        data = yaml.safe_load(text)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        where = f"строка {mark.line + 1}, столбец {mark.column + 1}" if mark else "неизвестное место"
        problem = exc.problem or exc.context or str(exc)
        print(f"ERROR: {path}: {where}: {problem}", file=sys.stderr)
        sys.exit(2)
    except yaml.YAMLError as exc:
        print(f"ERROR: {path}: ошибка разбора YAML: {exc}", file=sys.stderr)
        sys.exit(2)
    if data is None:
        return {}
    if not isinstance(data, dict):
        print(
            f"ERROR: {path}: верхний уровень конфига должен быть словарём (получено {type(data).__name__})",
            file=sys.stderr,
        )
        sys.exit(2)
    return data


def config_section(cfg: dict[str, Any], key: str) -> dict[str, Any]:
    """The `X.get("section", {}) if isinstance(X.get("section"), dict) else {}`
    idiom already used at `db-sync.py:180` and `config.py`'s own
    `policy_path()`, lifted into one place (T-067, F-26/F-36): a config
    section written as a string/list/number by hand (`project: "имя"`
    instead of a nested block) must not raise `AttributeError` two calls
    later just because the caller trusted the section's shape without
    checking it — the same class as the unparseable-file case `load_yaml`
    now guards against, one level down.

    T-067 review round 2: silently returning `{}` on a wrong-shaped section
    is not "a clear message" (the ticket's own criterion 2) — it is F-26/
    F-36 traded for a quieter instance of F-37 (a report built over a
    silently-ignored section, no signal at all). A warning to stderr naming
    the key and the shape found is the minimum the QA report asked for at
    `load_yaml` itself ("вместо тихого `{}` печатать в stderr")."""
    value = cfg.get(key)
    if value is not None and not isinstance(value, dict):
        print(
            f"WARNING: конфиг: раздел {key!r} задан как {type(value).__name__}, "
            "ожидался блок (мэппинг) — использую пустой раздел",
            file=sys.stderr,
        )
        return {}
    return value if isinstance(value, dict) else {}


def require_config(cfg_path: pathlib.Path | None, *, where: pathlib.Path | None = None) -> dict[str, Any]:
    """Load a config that a command cannot meaningfully run without.

    T-067 (F-37): several report/sync commands treated "no config found"
    as equivalent to "config is `{}`" and happily printed a green `✓ ...`
    over a project that plainly doesn't exist yet (`monthly-dashboard.py`,
    `db-sync.py`). Use this ONLY at a command whose whole output is
    meaningless without a real project config — NOT at a command with a
    legitimate empty-config fallback (setup/onboarding wizards, a
    multi-project scan driven by a registry file instead of a single
    project's config, `seo-cycle doctor`'s aggregator, which must keep
    running so it can report the missing-config step as a failure rather
    than aborting the whole health check).
    """
    if cfg_path is None:
        location = f" in {where}" if where else ""
        print(f"ERROR: seo-cycle.yaml not found{location} — nothing to do", file=sys.stderr)
        sys.exit(2)
    return load_yaml(cfg_path)


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def boolish(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "enabled", "да", "д", "on"}
    return bool(value)


def numeric(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def coerce_int(
    value: Any, default: int, *, name: str = "", falsy_to_default: bool = True, via_float: bool = False,
) -> int:
    """Like `numeric()`, but for config values that gate integer arithmetic
    (day counts, thresholds). A garbage non-numeric value must not crash the
    tool with a traceback — warn once (naming the config key) and fall back
    instead (T-052 review: unguarded `int(...)` on an unvalidated config
    value at seo_cycle_cli.py:170 and pulse.py:307).

    `falsy_to_default=True` (default) preserves the pre-existing
    `int(value or default)` idiom found at MOST of the call sites this
    replaces (0/""/None all mean "use default" there, and always did —
    changing that would be its own, separate behavior change this ticket
    does not make). Pass `falsy_to_default=False` at the handful of sites
    whose ORIGINAL code had no `or default` — there `0` was already a
    legitimate, meaningfully different-from-default value (e.g.
    `cache_ttl_hours: 0` = "never trust the cache", `max_raw_rows_loaded: 0`
    = "load nothing") that must keep surviving as `0`, not silently become
    the default (T-063 review: reusing the `... or default` idiom
    everywhere would have quietly changed accepted-input behavior at those
    sites, which the ticket's own «Ограничения» forbids).

    Catches `OverflowError` too, not just `TypeError`/`ValueError` (T-063
    gate round 2): YAML parses a bare `.inf`/`-.inf` config value straight
    into the Python float `inf` (no string involved, so `int(value)` never
    raises `ValueError`) — `int(float("inf"))` raises `OverflowError`
    instead, which the original two-exception catch let straight through
    with a traceback. This is the same crash class the whole ticket exists
    to close; missing this one exception type would have re-opened it at
    EVERY site that now calls `coerce_int()`.

    `via_float=False` (default) does a direct `int(candidate)` — correct
    for the majority of call sites, whose ORIGINAL code was a bare
    `int(value)`/`int(value or default)` (a numeric-looking STRING like
    `"2.5"` or `"1e3"` never worked there either; `int("2.5")` itself
    raises `ValueError` on `origin/main` same as here). Pass
    `via_float=True` at a site whose original code was `int(numeric(value,
    default))` instead (T-063 gate round 2, second finding): `numeric()`
    parses through `float()` first, so `"2.5"`/`"1e3"` DID work there on
    `origin/main` (`numeric()` never raises; the bare `int()` truncation
    around it is what could crash, e.g. on `.inf`) — replacing that whole
    expression with a direct `coerce_int(value, default)` silently
    narrowed accepted input (a quoted `"2.5"` started becoming `default`
    instead of `2`), which is exactly the kind of regression the ticket's
    own «Ограничения» forbid. `via_float=True` restores the float-first
    parse (so `"2.5"`/`"1e3"` keep working) while still catching the
    `OverflowError`/`ValueError` a `.inf`/`.nan` intermediate produces at
    the final `int(...)` truncation — the crash `int(numeric(...))` always
    had on `origin/main` and this ticket exists to close."""
    try:
        candidate = (value or default) if falsy_to_default else (default if value is None else value)
        if via_float:
            candidate = float(candidate)
        return int(candidate)
    except (TypeError, ValueError, OverflowError):
        label = f" ({name})" if name else ""
        print(f"WARNING: bad integer config value{label}: {value!r} — using default {default}", file=sys.stderr)
        return default


def coerce_float(value: Any, default: float, *, name: str = "", falsy_to_default: bool = True) -> float:
    """Like `coerce_int()`, but for config values that gate float arithmetic
    (percentages, budgets, thresholds) — same `falsy_to_default` contract
    (see `coerce_int()`'s docstring): True preserves the pre-existing
    `float(value or default)` idiom, False preserves an original call site
    that never had `or default` and where `0` is a legitimate value. Never
    crashes the tool on a garbage value — warns once (naming the key) and
    falls back instead. T-063: the float twin of `coerce_int()` for the
    `float(nested_get(...))` occurrences of the same unguarded-conversion
    class (found sweeping the tree for `scripts/pulse.py:234`,
    `pulse.drop_alert_pct`, and several others).

    Does NOT reject `inf`/`-inf` as a result (T-063 gate round 2, reverted
    after the SAME round's gate found it was itself a regression):
    `ads.cache_ttl_hours: .inf` ("never expire the cache"),
    `ads.analytics.wasted_spend_min_cost: .inf` ("never alert"), and several
    other keys legitimately accepted an infinite override on `origin/main`
    before this ticket touched them — an earlier version of this docstring
    claimed no call site ever worked with `.inf`, which the gate proved
    false on 11 of 13 `coerce_float()` sites. Rejecting non-finite results
    HERE, in the shared helper, silently narrowed accepted input on a
    healthy config — exactly what the ticket's own «Ограничения» forbid.
    Where a specific caller's LATER bare `round(...)`/`int(...)` (not going
    through `coerce_int()`) cannot survive an infinite intermediate value,
    that caller must guard its own truncation point (see `safe_round()`
    below and its use in `kpi-contract.py`/`seo-forecast.py`) instead of
    this function refusing a value that was never garbage to begin with."""
    try:
        candidate = (value or default) if falsy_to_default else (default if value is None else value)
        return float(candidate)
    except (TypeError, ValueError, OverflowError):
        # OverflowError: a Python `int` too large to represent as `float`
        # (e.g. a huge literal in the config) — `float("inf")` itself never
        # raises, but this keeps the two coercers' exception sets identical
        # so neither one is the "safe" one only by accident.
        label = f" ({name})" if name else ""
        print(f"WARNING: bad numeric config value{label}: {value!r} — using default {default}", file=sys.stderr)
        return default


def safe_round(value: float, ndigits: int | None = None) -> float:
    """`round()` that never raises on `inf`/`-inf`/`nan` — returns the
    value UNROUNDED in that case, rather than crashing (T-063 gate round
    2): `round(x)` with no `ndigits` truncates to an `int`, which raises
    `OverflowError` on `inf` and `ValueError` on `nan`; `round(x, n)` with
    an explicit `ndigits` returns a `float` and tolerates `inf`/`nan` fine
    on its own, so `safe_round` is really only needed at bare, no-`ndigits`
    `round(...)` calls fed by an intermediate value this ticket's fixes
    deliberately let stay infinite/NaN (e.g. `kpi.tolerance_pct: .inf`,
    `kpi.ctr_curve` overrides) rather than rejecting it at the coercion
    point — rejecting there was itself a regression the gate found (see
    `coerce_float()`'s docstring). A caller doesn't need this for any
    `round(x, n)` call — only for a bare `round(x)`."""
    try:
        return round(value, ndigits) if ndigits is not None else round(value)
    except (OverflowError, ValueError):
        return value


def nested_get(data: dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = config_section(cfg, "policy_files")
    return rel_path(project_root, policy_files.get(key, default))

