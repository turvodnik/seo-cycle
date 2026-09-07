"""Config, path, and parsing helpers shared by seo-cycle scripts.

T-090 (F-8/F-7/F-7b): this module is now the ONLY place in `scripts/` that
is allowed to construct a PyYAML Loader. `_install_yaml_bypass_guard()`
below wraps every Loader class's `__init__` so that any code outside this
file that tries to build a Loader (directly, or transitively via
`yaml.safe_load`/`yaml.load`/etc., which all just construct one of these
classes internally) blows up with a clear `RuntimeError` instead of
quietly parsing YAML the old, unguarded way.

T-090 round 2 (independent gate 2026-09-07, 🟡4): the previous version of
this docstring called a bypass "structurally impossible". That overstated
what a per-process runtime guard can do — it only protects a Python
process that has ALREADY imported `seo_cycle_core.config` (true today for
every one of the ~86 `scripts/*.py` files that read a config, since they
all import this module for `find_config`/`project_root_for`/etc. before
they'd have any reason to touch YAML at all). A brand-new `scripts/foo.py`
that reads YAML WITHOUT ever importing this module runs in a process where
the guard was never installed, and nothing here can reach into that
process from the outside.

What actually closes the class is the PAIR: this runtime guard (catches
any file that DOES import `seo_cycle_core` — directly or transitively —
and then tries to build a Loader some other way) plus the static AST
sweep in `tests/test_no_yaml_bypass.py`, which runs in CI on every PR and
fails the build if ANY `scripts/*.py` file other than this one so much as
imports `yaml` (not just uses a specific loader function — the bare
import itself is now the violation). A future `scripts/whatever.py` that
writes `import yaml` either gets caught by that CI test before merge, or —
if it also imports `seo_cycle_core` and calls `yaml.safe_load` at runtime
— crashes immediately with a message naming the right call. Only a file
that (a) skips `seo_cycle_core` entirely AND (b) somehow lands on `main`
without the AST test running (a broken/bypassed CI) gets through — that
residual risk is real and is a CI-configuration risk, not a Python one.
"""

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


_GUARD_INSTALLED = False
# T-090 round 2 (independent gate 2026-09-07, 🟡4): this used to be a plain
# module-level `_GUARD_ENABLED = True` — any code that could do
# `from seo_cycle_core import config; config._GUARD_ENABLED = False` turned
# the guard off for the rest of the process with one line, and the AST
# bypass test didn't look for that assignment at all. A closure-local flag
# plus a narrow, stack-checked setter closes both gaps: the flag itself
# isn't a module attribute anyone can poke, and the only way to flip it is
# `_testing_disable_guard()`/`_testing_enable_guard()`, which refuse to run
# unless the CALLER is a file under `tests/` (same stack-walk technique the
# guard itself uses below).
_guard_state = {"enabled": True}


def _this_file() -> str:
    return pathlib.Path(__file__).resolve().as_posix()


def _tests_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2] / "tests"


def _require_test_caller(fn_name: str) -> None:
    frame = sys._getframe(2)  # caller of the _testing_* wrapper
    caller = pathlib.Path(frame.f_code.co_filename).resolve()
    tests_dir = _tests_dir()
    if tests_dir != caller and tests_dir not in caller.parents:
        raise RuntimeError(
            f"seo-cycle: {fn_name}() может вызываться только из tests/ "
            f"(вызов из {caller})"
        )


def _testing_disable_guard() -> None:
    """Turn the runtime YAML-bypass guard off — ONLY callable from a file
    under `tests/`, so a test that needs to construct a Loader directly
    (to test config.py's own internals) can, without handing every
    `scripts/*.py` file a one-line way to disable the guard on itself."""
    _require_test_caller("_testing_disable_guard")
    _guard_state["enabled"] = False


def _testing_enable_guard() -> None:
    """Restore the runtime YAML-bypass guard — same access rule as
    `_testing_disable_guard()`."""
    _require_test_caller("_testing_enable_guard")
    _guard_state["enabled"] = True


def _install_yaml_bypass_guard() -> None:
    """Wrap PyYAML's Loader constructors so a Loader can only be built from
    inside this module (or from inside the `yaml` package's own code, which
    legitimately constructs Loaders as part of `yaml.load`/`safe_load`
    themselves).

    Uses `sys._getframe` (not `inspect.stack`, which stat()s source files
    for every frame — too slow to run on every single YAML document parsed
    across ~100 CLI entrypoints) to walk the call stack, skip frames that
    belong to the `yaml` package itself, and look at the first frame
    outside of it. If that frame isn't this file, someone is constructing a
    Loader without going through `seo_cycle_core.config` — refuse.
    """
    if yaml is None:
        return
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    _GUARD_INSTALLED = True

    this_file = _this_file()
    # T-090 scope: the guard protects the `scripts/` tree this module ships
    # in — the AST bypass test (`tests/test_no_yaml_bypass.py`) has the same
    # scope. Code OUTSIDE `scripts/` (test fixtures under `tests/`, any
    # other tooling on the machine) legitimately constructs YAML Loaders
    # for its own reasons unrelated to "read the project's config" and is
    # not this guard's concern — only a `scripts/*.py` file other than this
    # one bypassing `seo_cycle_core.config` is.
    scripts_dir = str(pathlib.Path(__file__).resolve().parent.parent) + "/"
    try:
        yaml_pkg_dir = str(pathlib.Path(yaml.__file__).resolve().parent)
    except Exception:  # pragma: no cover - defensive
        yaml_pkg_dir = ""

    loader_names = ["SafeLoader", "Loader", "FullLoader", "UnsafeLoader", "BaseLoader"]
    if getattr(yaml, "__with_libyaml__", False):
        loader_names += ["CSafeLoader", "CLoader", "CFullLoader", "CUnsafeLoader", "CBaseLoader"]

    for name in loader_names:
        cls = getattr(yaml, name, None)
        if cls is None:
            continue
        original_init = cls.__init__

        def make_wrapped(original_init):
            def wrapped_init(self, *args, **kwargs):
                if _guard_state["enabled"]:
                    frame = sys._getframe(1)
                    depth = 0
                    while frame is not None and depth < 50:
                        filename = pathlib.Path(frame.f_code.co_filename).resolve().as_posix()
                        if yaml_pkg_dir and filename.startswith(yaml_pkg_dir):
                            frame = frame.f_back
                            depth += 1
                            continue
                        if filename == this_file:
                            break
                        if not filename.startswith(scripts_dir):
                            # Outside the protected tree entirely (tests/,
                            # unrelated tooling) — not this guard's job.
                            break
                        raise RuntimeError(
                            "seo-cycle: прямой вызов PyYAML Loader запрещён — "
                            "читай YAML только через seo_cycle_core.config "
                            "(load_config/load_yaml_any/parse_yaml_text), "
                            f"а не напрямую (вызов из {filename}:{frame.f_lineno})"
                        )
                    # frame is None or depth exceeded: be conservative and
                    # allow (better a missed edge case than a false crash
                    # inside a legitimate deep call chain).
                return original_init(self, *args, **kwargs)

            return wrapped_init

        cls.__init__ = make_wrapped(original_init)


_install_yaml_bypass_guard()


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


def _read_yaml_mapping(path: pathlib.Path) -> tuple[bool, dict[str, Any] | None]:
    """Shared body of `load_yaml`/`load_config`: read+decode+parse a YAML
    file that is expected to be a mapping (dict) at the top level.

    Returns `(existed, data)`:
    - `existed=False` means the path does not exist (and isn't a broken
      symlink either, per F-42 — see `load_yaml`'s docstring); callers
      treat that as "no config yet", not an error.
    - `existed=True, data=None` means the file IS there but parsed to
      nothing — empty, comment-only, or a bare `---\\nnull\\n` document
      (T-090, F-7b). Whether that is an error is the CALLER's call:
      `load_yaml` says no (some readers legitimately treat "empty file" as
      "empty config"), `load_config` says yes (a command that treats its
      config as authoritative cannot tell "no project yet" from "project
      config that got truncated to zero bytes" any other way).
    - `existed=True, data={...}` is the normal case.

    Read errors, encoding errors, YAML syntax errors, and "top level isn't
    a mapping" are NOT ambiguous for either caller — this function exits
    the process on all three exactly as `load_yaml` always has.
    """
    if yaml is None:
        return False, None
    # `.exists()` follows symlinks and reports "missing" for a broken link
    # (F-42) — `.is_symlink()` catches that case so it isn't confused with
    # "no config yet".
    existed = path.exists() or path.is_symlink()
    if not existed:
        return False, None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        print(f"ERROR: {path}: не удалось прочитать конфиг: {exc}", file=sys.stderr)
        sys.exit(2)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        # T-067 round 3 (second independent gate): an earlier version of
        # this function used `errors="replace"` here, which turned a non-
        # UTF-8 file (e.g. saved by an editor in cp1251 — not exotic for a
        # Russian-language config) into MOJIBAKE that parsed "successfully"
        # instead of failing — trading a loud F-35 crash for a silent F-37
        # "✓ ..." over corrupted data, on 25 of 42 commands. The original
        # QA report named `UnicodeDecodeError` explicitly among the F-35
        # inputs; this function's own docstring above already promised
        # exit(2) for "a file that isn't valid UTF-8" — this is that
        # promise, finally kept.
        print(
            f"ERROR: {path}: файл не в кодировке UTF-8 "
            f"(байт {exc.object[exc.start]:#04x} в позиции {exc.start}) — пересохрани в UTF-8",
            file=sys.stderr,
        )
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
        return True, None
    if not isinstance(data, dict):
        print(
            f"ERROR: {path}: верхний уровень конфига должен быть словарём (получено {type(data).__name__})",
            file=sys.stderr,
        )
        sys.exit(2)
    return True, data


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

    T-090 round 2 (F-7b): this function stays deliberately LENIENT about
    an EXISTING-but-empty file too (still returns `{}`, not an error) —
    it is the shared helper for callers that read supplementary/optional
    YAML (policy overlays, multi-project scan targets) where "empty file"
    legitimately means "no overrides", same as "file absent". A command
    whose OWN main project config being empty is meaningless must call
    `load_config()` instead, which draws that exact line.
    """
    _existed, data = _read_yaml_mapping(path)
    return data if data is not None else {}


def load_config(path: pathlib.Path) -> dict[str, Any]:
    """Like `load_yaml()`, but for the ONE file a command treats as *the*
    project config it cannot meaningfully run without.

    T-090 round 2 (F-7b, independent gate 2026-09-07): before this split,
    `load_config` was a bare alias for `load_yaml` — so a config file that
    EXISTS but is empty (0 bytes, comment-only, a bare `---\\nnull\\n`
    document, or `{}`) parsed to `{}` exactly like a MISSING file, and
    every caller that only checked "did I get a dict back" printed a green
    report over nothing (`Project: ? (?)`, generated timestamps, the
    works) instead of refusing. `require_config()` already drew this line
    correctly for its own 13 callers; this function draws the SAME line at
    the read function itself, so every caller that already spells
    `load_config(cfg_path)` for its main config — not just the ones that
    additionally call `require_config`/`require_section` — gets it for
    free, without an code review having to catch each site by hand.

    A MISSING file is still not an error here (a caller may want to fall
    through to its own "no project yet" branch, or call `require_config`
    itself for a exit(2)-with-a-specific-message version) — this only
    closes the "file is there but semantically empty" gap `load_yaml`
    deliberately leaves open for OTHER callers (see `load_yaml`'s own
    docstring) but that is wrong for a file this call site is treating as
    authoritative.
    """
    existed, data = _read_yaml_mapping(path)
    if existed and not data:
        # `not data` covers both `data is None` (empty file/comment-only/
        # bare `---\nnull\n`) AND `data == {}` (an explicit empty mapping,
        # e.g. a file containing just `{}`) — both are "nothing to work
        # with" the same way a missing file would be, for a caller that
        # treats this file as its one authoritative project config.
        print(f"ERROR: {path}: конфиг пуст — нечего использовать", file=sys.stderr)
        sys.exit(2)
    return data if data is not None else {}


def load_yaml_any(path: pathlib.Path) -> Any:
    """Load ANY YAML file — not necessarily the project config, not
    necessarily a dict (T-090, F-8). Same hard guarantees as `load_config`
    (non-UTF-8 → clear error + exit(2); unparseable YAML → coordinate +
    exit(2); a missing file → the caller's own "not found" branch, not this
    function's problem), but deliberately WITHOUT `load_config`'s "top
    level must be a dict" rule and WITHOUT any "this is the project's
    config" semantics.

    Use this for policy files, entity maps, manifests, triggers files,
    stock-inventory, region-profiles — anything that is legitimately a
    list, or legitimately absent-means-empty, at the top level. Forcing
    those through `load_config`'s dict-or-die rule would be a regression
    on healthy, working files — exactly the class of over-tightening T-090
    is not allowed to introduce.
    """
    if yaml is None:
        return None
    if not path.exists() and not path.is_symlink():
        return None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        print(f"ERROR: {path}: не удалось прочитать файл: {exc}", file=sys.stderr)
        sys.exit(2)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(
            f"ERROR: {path}: файл не в кодировке UTF-8 "
            f"(байт {exc.object[exc.start]:#04x} в позиции {exc.start}) — пересохрани в UTF-8",
            file=sys.stderr,
        )
        sys.exit(2)
    return parse_yaml_text(text, source=path)


def parse_yaml_text(text: str, *, source: str | pathlib.Path = "<string>") -> Any:
    """Parse a YAML DOCUMENT that is already in memory — not a file on disk
    (T-090, F-8): frontmatter blocks (`eeat-render.py`), embedded YAML
    fragments, etc. Same parse-error guarantee as `load_yaml_any` (a
    `MarkedYAMLError`'s line/column reported, then `exit(2)`) but obviously
    no file-read/encoding step, since there is no file.
    """
    if yaml is None:
        return None
    try:
        return yaml.safe_load(text)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        where = f"строка {mark.line + 1}, столбец {mark.column + 1}" if mark else "неизвестное место"
        problem = exc.problem or exc.context or str(exc)
        print(f"ERROR: {source}: {where}: {problem}", file=sys.stderr)
        sys.exit(2)
    except yaml.YAMLError as exc:
        print(f"ERROR: {source}: ошибка разбора YAML: {exc}", file=sys.stderr)
        sys.exit(2)


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
    if key not in cfg:
        return {}
    value = cfg[key]
    if not isinstance(value, dict):
        print(
            f"WARNING: конфиг: раздел {key!r} задан как {type(value).__name__}, "
            "ожидался блок (мэппинг) — использую пустой раздел",
            file=sys.stderr,
        )
        return {}
    return value


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
    cfg = load_config(cfg_path)
    if not cfg:
        # T-090 round 2: `load_config` itself now exits(2) on an existing-
        # but-empty file, so this branch is a defensive backstop (an
        # existing `{}` document, `project: {}`-shaped edge cases) rather
        # than the primary defense it used to be. Kept for clarity and to
        # cover any future `load_config` caller that relaxes that rule.
        #
        # T-067 round 3 (second independent gate, §6): an existing-but-empty
        # file (empty, comment-only, a bare `---\nnull\n` document) used to
        # pass this function's "exists" check and come back as `{}` — same
        # green "✓ ..." over nothing this function exists to stop, just
        # reached through the file existing instead of being absent.
        print(f"ERROR: {cfg_path}: конфиг пуст — нечего использовать", file=sys.stderr)
        sys.exit(2)
    return cfg


def require_section(cfg: dict[str, Any], key: str, cfg_path: pathlib.Path | str) -> dict[str, Any]:
    """Like `require_config()`, one level down (T-090, F-7): a command that
    cannot run without section `key` being a real, non-empty mapping.

    Closes the exact gap `config_section()` deliberately leaves open:
    `config_section()` is a soft helper (missing/wrong-shaped section →
    `{}` + at most a warning) because MOST sections are optional with a
    sane empty default. But `monthly-dashboard.py`/`db-sync.py` read
    `project` to answer "which project is this a report for" — a `project:
    null` config (or no `project:` key, or `project: "имя"` as a bare
    string) makes their whole output meaningless, the same way a missing
    config file does for `require_config()`. Before this, `config_section`
    swallowed exactly that case silently (see its own docstring) and both
    commands printed a green `✓ ...` for a project that doesn't exist.
    """
    value = cfg.get(key)
    if not isinstance(value, dict) or not value:
        shape = "null" if value is None else (type(value).__name__ if not isinstance(value, dict) else "пустой блок")
        print(
            f"ERROR: {cfg_path}: раздел '{key}' обязателен и не может быть пустым/null "
            f"(получено: {shape})",
            file=sys.stderr,
        )
        sys.exit(2)
    return value


def yaml_available() -> bool:
    """Is PyYAML importable at all? A handful of callers check this before
    deciding whether to attempt a YAML-dependent code path (e.g. skip an
    optional YAML sidecar file gracefully instead of calling into
    `load_yaml_any`/`load_config`, which already degrade to `{}`/`None` on
    their own when PyYAML is missing, but the CALLER wants to know that
    BEFORE doing other work).

    T-090 round 2 (independent gate 2026-09-07, 🟡4): exists so those
    callers don't need their own `try: import yaml / except ImportError:
    yaml = None` — that `import yaml` is exactly what the AST bypass test
    now bans outside this module, regardless of what the import is used
    for.
    """
    return yaml is not None


def dump_yaml(data: Any) -> str:
    """Serialize `data` back to a YAML string — `yaml.safe_dump(data,
    allow_unicode=True, sort_keys=False)`, the one call shape every writer
    across `scripts/` already used.

    T-090 round 2 (independent gate 2026-09-07, 🟡4): the AST bypass test
    now bans a bare `import yaml` anywhere outside this module, full stop
    — not just Loader construction — because a per-attribute allowlist is
    exactly what let variant (а) of the bypass through last round. That
    rule doesn't distinguish "imported yaml to READ config" from "imported
    yaml to WRITE a wizard's answers back out"; ~10 files needed the
    latter (`project-intake-wizard.py`, `setup-blueprint.py`,
    `launch-plan.py`'s dry-run preview, etc.), so writing needs a home in
    this module too, same as reading does.
    """
    if yaml is None:  # pragma: no cover - same guard as the loaders above
        raise RuntimeError("PyYAML не установлен — dump_yaml недоступен")
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


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

