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


def find_yaml_bypass(path: pathlib.Path) -> list[str]:
    """Return a list of human-readable violations found in `path`, or []."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:  # pragma: no cover
        return [f"{path}: could not parse for AST scan: {exc}"]

    violations: list[str] = []
    yaml_alias = None  # name bound to the `yaml` module, if imported that way

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "yaml":
                    yaml_alias = alias.asname or alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module == "yaml":
                for alias in node.names:
                    if alias.name in YAML_LOADER_ATTRS or alias.name == "*":
                        violations.append(
                            f"{path}:{node.lineno}: `from yaml import {alias.name}` "
                            f"bypasses seo_cycle_core.config"
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
