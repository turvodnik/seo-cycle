"""T-090 (F-8): structural proof that no `scripts/*.py` file (other than
`seo_cycle_core/config.py` itself) can construct a PyYAML Loader.

Two independent layers are tested here:

1. A static AST sweep of every `scripts/**/*.py` file, looking for
   `import yaml` / `from yaml import ...` and any `yaml.<attr>` access that
   could reach a Loader (`safe_load`, `load`, `full_load`, `unsafe_load`,
   `SafeLoader`, `Loader`, `FullLoader`, `UnsafeLoader`, `BaseLoader`, and
   the C-accelerated variants). Only `seo_cycle_core/config.py` is allowed
   to touch any of these.

2. A grep-style sweep of every `scripts/*.sh` file for a heredoc python
   block that does `import yaml` directly (the `monthly-runner.sh` class of
   bypass a Python-only AST walk cannot see).

Both are proven to actually catch a NEW bypass, not just to "run and
report nothing" on the current tree: `test_bypass_is_actually_caught_ast`
and `..._runtime` write a temporary offending file, assert the checks
here (and the runtime guard in `seo_cycle_core/config.py`) both catch it,
then delete it.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "scripts"
ALLOWED_PY_FILES = {
    (SCRIPTS_DIR / "seo_cycle_core" / "config.py").resolve(),
}

YAML_LOADER_ATTRS = {
    "safe_load", "load", "full_load", "unsafe_load", "load_all",
    "safe_load_all", "full_load_all", "unsafe_load_all",
    "SafeLoader", "Loader", "FullLoader", "UnsafeLoader", "BaseLoader",
    "CSafeLoader", "CLoader", "CFullLoader", "CUnsafeLoader", "CBaseLoader",
}


def _iter_scripts() -> list[pathlib.Path]:
    return sorted(SCRIPTS_DIR.rglob("*.py"))


def _importlib_import_module_yaml_literal(node: ast.Call) -> str | None:
    """If `node` is a call that resolves to `importlib.import_module(...)`
    (as `importlib.import_module(...)` or, after `from importlib import
    import_module`, as bare `import_module(...)`) and at least one string-
    literal argument contains "yaml", return that literal. Else None.

    T-090 round 2 (🟡4): closes the `importlib.import_module("yaml")`
    variant of the bypass — a real gap the independent gate demonstrated
    (combined with disabling the runtime guard, it got past both layers).
    Only catches a LITERAL argument; a name built by string concatenation
    or built at runtime is a known, accepted residual gap (see this file's
    module docstring and config.py's own docstring).
    """
    func = node.func
    is_importlib_call = (
        (isinstance(func, ast.Attribute) and func.attr == "import_module"
         and isinstance(func.value, ast.Name) and func.value.id == "importlib")
        or (isinstance(func, ast.Name) and func.id == "import_module")
    )
    if not is_importlib_call:
        return None
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and "yaml" in arg.value:
            return arg.value
    for kw in node.keywords:
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str) and "yaml" in kw.value.value:
            return kw.value.value
    return None


def _is_guard_state_target(target: ast.expr) -> bool:
    """True if `target` is an assignment to the guard's internal flag —
    `config._guard_state[...] = ...`, `_guard_state[...] = ...`, or a bare
    rebind of the name `_guard_state`/the retired `_GUARD_ENABLED` — from
    OUTSIDE `seo_cycle_core/config.py` (T-090 round 2, 🟡4: the previous
    plain-bool `_GUARD_ENABLED` could be flipped off from any file with
    `config._GUARD_ENABLED = False`; the AST test never looked for that
    assignment at all)."""
    names = {"_guard_state", "_GUARD_ENABLED"}
    if isinstance(target, ast.Name):
        return target.id in names
    if isinstance(target, ast.Attribute):
        return target.attr in names
    if isinstance(target, ast.Subscript):
        return _is_guard_state_target(target.value)
    return False


def find_yaml_bypass_source(source: str, label: str = "<test-source>") -> list[str]:
    """Like `find_yaml_bypass()`, but for in-memory source text — used by
    tests that want to assert a violation is caught without writing a
    throwaway file into `scripts/`."""
    tree = ast.parse(source, filename=label)
    return _scan_tree(tree, label)


def find_yaml_bypass(path: pathlib.Path) -> list[str]:
    """Return a list of human-readable violations found in `path`, or []."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover
        return [f"{path}: could not parse for AST scan: {exc}"]
    return _scan_tree(tree, path)


def _scan_tree(tree: ast.AST, path) -> list[str]:
    violations: list[str] = []
    yaml_alias = None  # name bound to the `yaml` module, if imported that way

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "yaml" or alias.name.startswith("yaml."):
                    # T-090 round 2 (🟡4): ban the IMPORT itself, not just
                    # specific attribute access afterwards — the gate's
                    # variant (а) was a file that imports yaml and calls
                    # `yaml.safe_load` with no "loader attribute" anywhere
                    # near the import statement for the old check to catch
                    # differently; banning any `import yaml` outright
                    # closes that regardless of which attribute gets used.
                    violations.append(
                        f"{path}:{node.lineno}: `import {alias.name}` is not allowed "
                        f"outside seo_cycle_core/config.py — read YAML only via "
                        f"seo_cycle_core.config (load_config/load_yaml_any/parse_yaml_text)"
                    )
                    yaml_alias = alias.asname or alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module == "yaml" or (node.module or "").startswith("yaml."):
                violations.append(
                    f"{path}:{node.lineno}: `from {node.module} import ...` is not "
                    f"allowed outside seo_cycle_core/config.py"
                )
        elif isinstance(node, ast.Attribute):
            if (
                yaml_alias
                and isinstance(node.value, ast.Name)
                and node.value.id == yaml_alias
                and node.attr in YAML_LOADER_ATTRS
            ):
                violations.append(
                    f"{path}:{node.lineno}: `{yaml_alias}.{node.attr}` bypasses "
                    f"seo_cycle_core.config"
                )
        elif isinstance(node, ast.Call):
            literal = _importlib_import_module_yaml_literal(node)
            if literal is not None:
                violations.append(
                    f"{path}:{node.lineno}: `importlib.import_module({literal!r})` "
                    f"bypasses seo_cycle_core.config"
                )
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if target is not None and _is_guard_state_target(target):
                    violations.append(
                        f"{path}:{node.lineno}: assignment to the YAML-bypass "
                        f"guard's internal flag is not allowed outside "
                        f"seo_cycle_core/config.py or tests/ — use "
                        f"config._testing_disable_guard()/_testing_enable_guard() instead"
                    )
    return violations


class NoYamlBypassAstTest(unittest.TestCase):
    def test_only_config_py_touches_yaml_loaders(self) -> None:
        offenders: list[str] = []
        for path in _iter_scripts():
            if path.resolve() in ALLOWED_PY_FILES:
                continue
            offenders.extend(find_yaml_bypass(path))
        self.assertEqual(
            offenders, [],
            "Direct PyYAML Loader usage found outside seo_cycle_core/config.py "
            "(read YAML only via load_config/load_yaml_any/parse_yaml_text):\n"
            + "\n".join(offenders),
        )

    def test_no_shell_heredoc_imports_yaml_directly(self) -> None:
        offenders: list[str] = []
        for path in sorted(SCRIPTS_DIR.glob("*.sh")):
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped in ("import yaml",) or stripped.startswith("import yaml "):
                    # Allowed ONLY if this same heredoc also imports
                    # seo_cycle_core.config right around it (the T-090
                    # monthly-runner.sh boundary: bash cannot use the
                    # in-process guard, so it must route through the core
                    # loader explicitly instead of calling yaml directly).
                    window = "\n".join(text.splitlines()[max(0, i - 6):i + 6])
                    if "seo_cycle_core" not in window:
                        offenders.append(f"{path}:{i}: bare `import yaml` with no seo_cycle_core routing nearby")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_bypass_is_actually_caught_ast(self) -> None:
        """Prove the AST test isn't vacuously passing: plant a fresh bypass
        file, confirm find_yaml_bypass() flags it, then remove it."""
        temp = SCRIPTS_DIR / "zz-bypass-temp.py"
        temp.write_text(
            "import yaml\n"
            "cfg = yaml.safe_load(open('seo-cycle.yaml'))\n",
            encoding="utf-8",
        )
        try:
            violations = find_yaml_bypass(temp)
            self.assertTrue(violations, "AST scan failed to catch a planted yaml.safe_load bypass")
        finally:
            temp.unlink()

    def test_bypass_variant_a_bare_import_no_core_caught_by_ast(self) -> None:
        """Independent gate 2026-09-07, 🟡4, variant (а): a file that reads
        YAML without ever importing `seo_cycle_core` at all — the runtime
        guard is never installed in that process, so it genuinely can't
        catch this one (documented in config.py's own module docstring).
        The AST sweep is what closes this variant: it flags the bare
        `import yaml` on its own, independent of whether the file also
        touches a specific loader attribute or imports the core module."""
        violations = find_yaml_bypass_source(
            "import yaml, sys\n"
            "cfg = yaml.safe_load(open(sys.argv[1]))\n"
        )
        self.assertTrue(violations, "AST scan did not flag a bare `import yaml` with no core import")

    def test_bypass_variant_b_guard_disable_assignment_caught_by_ast(self) -> None:
        """Independent gate 2026-09-07, 🟡4, variant (б): the retired
        `config._GUARD_ENABLED = False` one-liner (and its replacement
        internal name, `_guard_state`) must be flagged if any
        `scripts/*.py` file other than config.py assigns to it."""
        violations = find_yaml_bypass_source(
            "from seo_cycle_core import config\n"
            "config._guard_state['enabled'] = False\n"
        )
        self.assertTrue(violations, "AST scan did not flag an external assignment to the guard's internal flag")

    def test_bypass_variant_c_importlib_literal_caught_by_ast(self) -> None:
        """Independent gate 2026-09-07, 🟡4, variant (в): guard disabled
        AND yaml imported via `importlib.import_module("yaml")` instead of
        a plain `import yaml` — the AST test must catch the importlib
        route too, not just the plain-import spelling."""
        violations = find_yaml_bypass_source(
            "import importlib\n"
            "y = importlib.import_module('yaml')\n"
            "y.safe_load('a: 1')\n"
        )
        self.assertTrue(violations, "AST scan did not flag importlib.import_module('yaml')")

    def test_bypass_is_actually_caught_at_runtime(self) -> None:
        """Same planted file, but prove the RUNTIME guard in
        seo_cycle_core/config.py also kills it when actually executed
        (not just flagged statically) — then remove it."""
        temp = SCRIPTS_DIR / "zz-bypass-temp.py"
        temp.write_text(
            "import sys, pathlib\n"
            "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))\n"
            "import seo_cycle_core.config  # noqa: F401 - installs the guard\n"
            "import yaml\n"
            "yaml.safe_load('a: 1')\n",
            encoding="utf-8",
        )
        try:
            proc = subprocess.run(
                [sys.executable, str(temp)],
                capture_output=True, text=True, timeout=30,
            )
        finally:
            temp.unlink()
        self.assertNotEqual(proc.returncode, 0, "planted bypass ran to completion instead of being rejected")
        self.assertIn("seo-cycle:", proc.stderr)
        self.assertIn("Loader", proc.stderr)


if __name__ == "__main__":
    unittest.main()
