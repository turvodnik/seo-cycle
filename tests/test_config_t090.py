"""T-090: tests for the new/changed pieces of seo_cycle_core.config —
`require_section` (F-7), `config_section`'s None-vs-absent distinction
(F-7), `load_yaml_any`/`parse_yaml_text` (F-8), and the runtime Loader
guard. Complements the existing T-067 coverage in
`test_config_robustness.py`, which already covers `load_yaml`/
`require_config`/`config_section`'s shape handling.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import shutil
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.config import (  # noqa: E402
    config_section,
    load_config,
    load_yaml,
    load_yaml_any,
    parse_yaml_text,
    require_section,
)


def tmp_dir() -> pathlib.Path:
    return pathlib.Path(tempfile.mkdtemp(prefix="t090-config-"))


class ConfigSectionNoneVsAbsentTest(unittest.TestCase):
    """F-7: `project: null` (key present, value None) must warn and be
    told apart from a key that's simply not there (silent default)."""

    def test_key_absent_is_silent(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            self.assertEqual(config_section({}, "project"), {})
        self.assertEqual(buf.getvalue(), "")

    def test_key_present_but_null_warns(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = config_section({"project": None}, "project")
        self.assertEqual(result, {})
        self.assertIn("WARNING", buf.getvalue())
        self.assertIn("project", buf.getvalue())
        self.assertIn("NoneType", buf.getvalue())

    def test_key_present_as_dict_no_warning(self) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = config_section({"project": {"name": "x"}}, "project")
        self.assertEqual(result, {"name": "x"})
        self.assertEqual(buf.getvalue(), "")


class RequireSectionTest(unittest.TestCase):
    """F-7: `require_section` — the strict "this command's whole output is
    meaningless without this section" gate, one level below `require_config`."""

    def test_null_section_exits_2(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            require_section({"project": None}, "project", "cfg.yaml")
        self.assertEqual(ctx.exception.code, 2)

    def test_absent_section_exits_2(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            require_section({}, "project", "cfg.yaml")
        self.assertEqual(ctx.exception.code, 2)

    def test_wrong_shape_section_exits_2(self) -> None:
        for bad in ("acme", ["a", "b"], 5):
            with self.assertRaises(SystemExit):
                require_section({"project": bad}, "project", "cfg.yaml")

    def test_empty_dict_section_exits_2(self) -> None:
        # An empty mapping is still "nothing to report" for a required
        # section (distinct from config_section's soft {} default).
        with self.assertRaises(SystemExit):
            require_section({"project": {}}, "project", "cfg.yaml")

    def test_valid_section_returns_it(self) -> None:
        cfg = {"project": {"name": "acme", "domain": "acme.ru"}}
        self.assertEqual(require_section(cfg, "project", "cfg.yaml"), cfg["project"])


class LoadYamlAnyTest(unittest.TestCase):
    """F-8: tolerant loader for non-project YAML (policy/entities/manifest/
    triggers) — same hard guarantees as load_config, no dict coercion."""

    def setUp(self):
        self.root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def test_missing_file_is_none(self) -> None:
        self.assertIsNone(load_yaml_any(self.root / "nope.yaml"))

    def test_list_top_level_survives_unforced(self) -> None:
        p = self.root / "triggers.yaml"
        p.write_text("- a\n- b\n", encoding="utf-8")
        self.assertEqual(load_yaml_any(p), ["a", "b"])

    def test_non_utf8_exits_2(self) -> None:
        p = self.root / "bad.yaml"
        p.write_bytes(b"\xff\xfe garbage")
        with self.assertRaises(SystemExit) as ctx:
            load_yaml_any(p)
        self.assertEqual(ctx.exception.code, 2)

    def test_broken_yaml_exits_2_with_coordinate(self) -> None:
        p = self.root / "broken.yaml"
        p.write_text("a: [unclosed\n", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), self.assertRaises(SystemExit) as ctx:
            load_yaml_any(p)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("строка", buf.getvalue())


class ParseYamlTextTest(unittest.TestCase):
    """F-8: in-memory YAML fragment parsing (eeat-render.py's frontmatter)."""

    def test_parses_dict(self) -> None:
        self.assertEqual(parse_yaml_text("a: 1\nb: 2\n"), {"a": 1, "b": 2})

    def test_broken_text_exits_2(self) -> None:
        with self.assertRaises(SystemExit):
            parse_yaml_text("a: [unclosed\n")


class LoadConfigVsLoadYamlSplitTest(unittest.TestCase):
    """T-090 round 2 (independent gate 2026-09-07, F-7b): `load_config`
    used to be a bare alias for `load_yaml` — an existing-but-empty file
    (0 bytes, comment-only, a bare `---\\nnull\\n` document, `{}`) parsed
    to `{}` exactly like a MISSING file for every caller, including the
    ~60 command entrypoints that only call `load_config`/local wrappers
    around it and never separately call `require_config`. This is the
    read-function-level fix: `load_config` now draws the "file exists but
    is semantically empty" line itself; `load_yaml` stays lenient for the
    legitimate optional/multi-project readers that still want it."""

    def setUp(self):
        self.root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def test_no_longer_the_same_object(self) -> None:
        self.assertIsNot(load_config, load_yaml)

    def test_missing_file_both_return_empty_dict(self) -> None:
        p = self.root / "nope.yaml"
        self.assertEqual(load_yaml(p), {})
        self.assertEqual(load_config(p), {})

    def test_empty_file_load_yaml_lenient_load_config_exits_2(self) -> None:
        p = self.root / "seo-cycle.yaml"
        p.write_text("", encoding="utf-8")
        self.assertEqual(load_yaml(p), {})
        with self.assertRaises(SystemExit) as ctx:
            load_config(p)
        self.assertEqual(ctx.exception.code, 2)

    def test_comment_only_file_load_config_exits_2(self) -> None:
        p = self.root / "seo-cycle.yaml"
        p.write_text("# just a comment\n# another one\n", encoding="utf-8")
        self.assertEqual(load_yaml(p), {})
        with self.assertRaises(SystemExit):
            load_config(p)

    def test_bare_null_document_load_config_exits_2(self) -> None:
        p = self.root / "seo-cycle.yaml"
        p.write_text("---\nnull\n", encoding="utf-8")
        self.assertEqual(load_yaml(p), {})
        with self.assertRaises(SystemExit):
            load_config(p)

    def test_empty_map_document_load_config_exits_2(self) -> None:
        # `{}` parses to an empty (falsy) dict, not `None` — same "nothing
        # to work with" case as the other three forms above.
        p = self.root / "seo-cycle.yaml"
        p.write_text("{}\n", encoding="utf-8")
        self.assertEqual(load_yaml(p), {})
        with self.assertRaises(SystemExit):
            load_config(p)

    def test_healthy_file_both_return_same_dict(self) -> None:
        p = self.root / "seo-cycle.yaml"
        p.write_text("project:\n  name: acme\n  domain: acme.ru\n", encoding="utf-8")
        expected = {"project": {"name": "acme", "domain": "acme.ru"}}
        self.assertEqual(load_yaml(p), expected)
        self.assertEqual(load_config(p), expected)

    def test_project_null_is_not_load_configs_problem(self) -> None:
        # `load_config` only closes the "file itself is empty" gap — a
        # non-empty file with a null SECTION (`project: null`) is a
        # different, per-section problem that `require_section` closes
        # (see RequireSectionTest above and the per-command integration
        # tests in test_t090_command_integration.py).
        p = self.root / "seo-cycle.yaml"
        p.write_text("project: null\n", encoding="utf-8")
        self.assertEqual(load_config(p), {"project": None})


class TestingGuardTogglesTest(unittest.TestCase):
    """T-090 round 2 (independent gate 2026-09-07, 🟡4): the old
    `config._GUARD_ENABLED = False` one-liner is gone — the only way to
    disable the runtime YAML-bypass guard is `_testing_disable_guard()`/
    `_testing_enable_guard()`, and even THOSE refuse to run unless the
    caller is a file under `tests/` (checked by walking the call stack,
    same technique the guard itself already used)."""

    def setUp(self) -> None:
        from seo_cycle_core import config as _config
        self._config = _config
        # Always leave the guard enabled for every other test in the
        # process, regardless of how this test ends. Wrapped in a lambda
        # DEFINED IN THIS FILE (not passed bare) so the stack-walk inside
        # `_testing_enable_guard()` sees a caller frame under tests/, not
        # unittest's own cleanup-runner frame.
        self.addCleanup(lambda: self._config._testing_enable_guard())

    def test_callable_from_this_test_file(self) -> None:
        # This call site IS under tests/ — must succeed silently.
        self._config._testing_disable_guard()
        self.assertFalse(self._config._guard_state["enabled"])
        self._config._testing_enable_guard()
        self.assertTrue(self._config._guard_state["enabled"])

    def test_rejected_from_a_non_tests_caller(self) -> None:
        # Simulate a `scripts/*.py` file calling the setter by invoking it
        # through a helper whose __code__.co_filename points outside
        # tests/ — reuses the exact stack-walk the real guard performs.
        fake_caller_path = str(SCRIPTS / "zz-not-a-test.py")
        src = (
            "def call_it(fn):\n"
            "    fn()\n"
        )
        namespace: dict = {}
        code = compile(src, fake_caller_path, "exec")
        exec(code, namespace)  # noqa: S102 - controlled, in-memory only
        with self.assertRaises(RuntimeError):
            namespace["call_it"](self._config._testing_disable_guard)
        # Guard must still be enabled — the rejected call must not have
        # had any side effect.
        self.assertTrue(self._config._guard_state["enabled"])


if __name__ == "__main__":
    unittest.main()
