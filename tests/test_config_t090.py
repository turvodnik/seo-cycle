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


class LoadConfigAliasTest(unittest.TestCase):
    def test_load_config_is_load_yaml(self) -> None:
        self.assertIs(load_config, load_yaml)


if __name__ == "__main__":
    unittest.main()
