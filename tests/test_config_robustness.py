#!/usr/bin/env python3
"""T-067: closes the "конфиг читается без проверки формы" class (F-26,
F-35, F-36, F-37 — QA report 2026-09-06, seo-cycle v2.1.0).

Three sub-classes, one test group each:

- F-35 — `load_yaml()` let a malformed YAML file (tab indent, unclosed
  bracket, non-UTF8 bytes) or a well-formed-but-wrong-shape top level
  (a string/list/number instead of a mapping) reach the caller as a raw
  traceback, or as something that crashes on the NEXT `.get()` call.
- F-26/F-36 — a config *section* (`project`, `locale`, `sources`, ...)
  used as a dict without checking it actually is one; a human writing
  `project: "имя"` instead of a nested block got `AttributeError: 'str'
  object has no attribute 'get'` two calls later, anywhere from
  `seo-cycle status` to the validator itself.
- F-37 — commands whose whole output is derived from the project config
  treated "config not found" as "config is `{}`" and printed a green
  "✓ ..." / exit 0 over a directory that isn't a seo-cycle project at all.

Each test drives the REAL function/CLI, not a re-implementation of the
fix, and each targets one broken site so a regression at exactly that
site fails exactly that test (mutation table in the T-067 packet
«Результат», not reproduced here — this file is what the table's "тест"
column points at).
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LAUNCHER = ROOT / "bin" / "seo-cycle"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.config import config_section, load_yaml, require_config  # noqa: E402


def tmp_dir() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp(prefix="seo-config-robustness-"))


def run_cli(args: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LAUNCHER), *args],
        cwd=cwd,
        env={**__import__("os").environ, "SEO_CYCLE_LAUNCHER_REEXEC": "1"},
        text=True,
        capture_output=True,
        check=False,
    )


class LoadYamlFormTest(unittest.TestCase):
    """`seo_cycle_core.config.load_yaml` — F-35."""

    def setUp(self) -> None:
        self.root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def test_missing_file_returns_empty_dict_unchanged(self) -> None:
        # Behavior-preservation control: this is the ONE case that must
        # NOT start exiting — many callers legitimately run with no
        # config yet (setup wizards).
        self.assertEqual(load_yaml(self.root / "does-not-exist.yaml"), {})

    def test_well_formed_config_round_trips_unchanged(self) -> None:
        cfg_path = self.root / "seo-cycle.yaml"
        cfg_path.write_text("project:\n  name: acme\n  domain: acme.example\n", encoding="utf-8")
        self.assertEqual(load_yaml(cfg_path), {"project": {"name": "acme", "domain": "acme.example"}})

    def test_tab_indent_exits_2_with_coordinates_no_traceback(self) -> None:
        cfg_path = self.root / "seo-cycle.yaml"
        cfg_path.write_bytes(b"project:\n\tname: x\n")
        with self.assertRaises(SystemExit) as ctx:
            load_yaml(cfg_path)
        self.assertEqual(ctx.exception.code, 2)

    def test_tab_indent_message_names_file_and_line(self) -> None:
        cfg_path = self.root / "seo-cycle.yaml"
        cfg_path.write_bytes(b"project:\n\tname: x\n")
        proc = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); "
             f"from seo_cycle_core.config import load_yaml; import pathlib; "
             f"load_yaml(pathlib.Path({str(cfg_path)!r}))"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn(str(cfg_path), proc.stderr)
        self.assertIn("строка 2", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_project_as_scalar_string_exits_2_not_silently_accepted(self) -> None:
        cfg_path = self.root / "seo-cycle.yaml"
        cfg_path.write_text("just a string\n", encoding="utf-8")
        with self.assertRaises(SystemExit) as ctx:
            load_yaml(cfg_path)
        self.assertEqual(ctx.exception.code, 2)

    def test_top_level_list_exits_2(self) -> None:
        cfg_path = self.root / "seo-cycle.yaml"
        cfg_path.write_text("- 1\n- 2\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            load_yaml(cfg_path)

    def test_empty_file_returns_empty_dict(self) -> None:
        cfg_path = self.root / "seo-cycle.yaml"
        cfg_path.write_text("", encoding="utf-8")
        self.assertEqual(load_yaml(cfg_path), {})


class ConfigSectionTest(unittest.TestCase):
    """`seo_cycle_core.config.config_section` — F-26/F-36 helper itself."""

    def test_dict_section_passes_through(self) -> None:
        cfg = {"project": {"name": "acme"}}
        self.assertEqual(config_section(cfg, "project"), {"name": "acme"})

    def test_string_section_becomes_empty_dict_not_attributeerror(self) -> None:
        cfg = {"project": "acme"}
        section = config_section(cfg, "project")
        self.assertEqual(section, {})
        section.get("name")  # would raise AttributeError pre-fix if this were the raw string

    def test_list_section_becomes_empty_dict(self) -> None:
        self.assertEqual(config_section({"engines": [1, 2]}, "engines"), {})

    def test_missing_key_becomes_empty_dict(self) -> None:
        self.assertEqual(config_section({}, "project"), {})


class RequireConfigTest(unittest.TestCase):
    """`seo_cycle_core.config.require_config` — F-37 helper itself."""

    def test_none_path_exits_2(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            require_config(None)
        self.assertEqual(ctx.exception.code, 2)

    def test_real_path_loads_normally(self) -> None:
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg_path = root / "seo-cycle.yaml"
        cfg_path.write_text("project:\n  name: acme\n", encoding="utf-8")
        self.assertEqual(require_config(cfg_path), {"project": {"name": "acme"}})


class CliSectionAccessTest(unittest.TestCase):
    """End-to-end: the exact F-26 repro from the QA report, plus F-36's
    validator sibling — both against the real launcher, not a unit stub."""

    def setUp(self) -> None:
        self.root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        (self.root / "seo-cycle.yaml").write_text(
            'project: plain\ndomain: plain.example\nmarkets:\n  - code: ru\n    locale: ru-RU\n',
            encoding="utf-8",
        )

    def test_status_on_project_as_string_does_not_crash(self) -> None:
        proc = run_cli(["status"], cwd=self.root)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        self.assertNotIn("AttributeError", proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)

    def test_validate_on_project_as_string_reports_error_not_traceback(self) -> None:
        proc = run_cli(["validate"], cwd=self.root)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        self.assertNotIn("AttributeError", proc.stdout + proc.stderr)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("project must be a mapping", proc.stdout + proc.stderr)


class CliMissingConfigTest(unittest.TestCase):
    """F-37: no config anywhere in the project — the command must refuse,
    not report a green success over nothing."""

    def setUp(self) -> None:
        self.root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def test_dashboard_refuses_without_config(self) -> None:
        proc = run_cli(["dashboard"], cwd=self.root)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("✓", proc.stdout + proc.stderr)
        self.assertFalse((self.root / "seo" / "monthly-dashboard.md").exists())

    def test_db_refuses_without_config(self) -> None:
        proc = run_cli(["db"], cwd=self.root)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("✓", proc.stdout + proc.stderr)
        self.assertFalse((self.root / "seo" / "seo.db").exists())

    def test_status_already_refused_without_config_unchanged(self) -> None:
        # Regression control for a command that was already honest
        # (T-052) — T-067 must not have disturbed it.
        proc = run_cli(["status"], cwd=self.root)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
