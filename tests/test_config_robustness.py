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

    def test_non_utf8_exits_2_not_silently_mangled(self) -> None:
        # T-067 round 3 (second independent gate, §5 — the blocker): an
        # earlier version used `errors="replace"`, which turned a cp1251
        # config (not exotic for Russian text) into mojibake that "parsed"
        # instead of failing — 25 of 42 commands went from an honest crash
        # (F-35) to a silent "✓ ..." over corrupted data (F-37). The
        # original QA report named `UnicodeDecodeError` explicitly among
        # the F-35 inputs this ticket exists to close.
        cfg_path = self.root / "seo-cycle.yaml"
        cfg_path.write_bytes("project:\n  name: тест\n".encode("cp1251"))
        with self.assertRaises(SystemExit) as ctx:
            load_yaml(cfg_path)
        self.assertEqual(ctx.exception.code, 2)

    def test_non_utf8_message_names_file_no_traceback(self) -> None:
        cfg_path = self.root / "seo-cycle.yaml"
        cfg_path.write_bytes("project:\n  name: тест\n".encode("cp1251"))
        proc = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); "
             f"from seo_cycle_core.config import load_yaml; import pathlib; "
             f"load_yaml(pathlib.Path({str(cfg_path)!r}))"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn(str(cfg_path), proc.stderr)
        self.assertIn("UTF-8", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


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

    def test_empty_file_exits_2_not_treated_as_valid(self) -> None:
        # T-067 round 3 (second gate, §6): `require_config` checked only
        # "does the file exist", so an existing-but-empty file (or a
        # comment-only file, or a bare `null` document) passed through as
        # a "valid" config and produced the same green "✓ ..." over
        # nothing this function exists to stop.
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        cfg_path = root / "seo-cycle.yaml"
        cfg_path.write_text("", encoding="utf-8")
        with self.assertRaises(SystemExit) as ctx:
            require_config(cfg_path)
        self.assertEqual(ctx.exception.code, 2)


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

    def test_status_on_project_as_string_warns_instead_of_silently_swallowing(self) -> None:
        # Review round 2: a bare `assertEqual(rc, 0)` here would fossilize
        # "silently degrade to `?`" as the accepted behavior. The command may
        # still complete (its output doesn't otherwise depend on `project`
        # being well-formed) but it must NOT do so silently — `config_section`
        # is required to name the offending key in stderr.
        proc = run_cli(["status"], cwd=self.root)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        self.assertNotIn("AttributeError", proc.stdout + proc.stderr)
        self.assertEqual(proc.returncode, 0)
        # T-067 round 3 (second gate, §7): a bare `assertIn("str", stderr)`
        # is too loose — "str" is a substring of plenty of unrelated
        # messages. Assert the exact warning prefix `config_section` prints.
        self.assertIn("WARNING: конфиг: раздел 'project' задан как str", proc.stderr)

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

    def test_dashboard_refuses_on_cp1251_config(self) -> None:
        # T-067 round 3 (second gate, §5 — the blocker itself, exact
        # reproduction): a config saved by an editor in cp1251 instead of
        # UTF-8 (not exotic for Russian text) used to make `dashboard`
        # print a green "✓ Dashboard → ..." and exit 0 over mangled
        # data — a verbatim repro of the ticket's own F-37, on the branch
        # that closes F-37.
        (self.root / "seo-cycle.yaml").write_bytes("project:\n  name: тест\n".encode("cp1251"))
        proc = run_cli(["dashboard"], cwd=self.root)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("✓", proc.stdout + proc.stderr)
        self.assertFalse((self.root / "seo" / "monthly-dashboard.md").exists())

    def test_empty_config_file_refuses_like_missing(self) -> None:
        (self.root / "seo-cycle.yaml").write_text("", encoding="utf-8")
        proc = run_cli(["dashboard"], cwd=self.root)
        self.assertNotEqual(proc.returncode, 0)
        self.assertNotIn("✓", proc.stdout + proc.stderr)
        self.assertFalse((self.root / "seo" / "monthly-dashboard.md").exists())


class MatrixSiteTest(unittest.TestCase):
    """T-067 review round 2 — an independent gate built a "раздел × форма ×
    команда" matrix over `config/project.template.yaml` and found 12 more
    crash sites this ticket's first pass had missed by narrowing its own
    search to files that import `seo_cycle_core.config` — `validate-config.py`
    alone accounted for 8 of the 12 (`sources`, `publishing`, `content_rules`,
    `artifacts`, `monitoring`, `eeat`, `backlinks`, plus a `TypeError` on
    `engines`). One test per site, each mutating exactly the section the
    review named and running exactly the command that crashed on it."""

    TEMPLATE = ROOT / "config" / "project.template.yaml"

    def healthy_cfg(self) -> dict:
        import yaml
        return yaml.safe_load(self.TEMPLATE.read_text(encoding="utf-8"))

    def project_with(self, **overrides) -> pathlib.Path:
        import yaml
        cfg = self.healthy_cfg()
        cfg.update(overrides)
        root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        (root / "seo-cycle.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        return root

    def assert_no_traceback(self, args: list[str], root: pathlib.Path) -> subprocess.CompletedProcess:
        proc = run_cli(args, cwd=root)
        out = proc.stdout + proc.stderr
        self.assertNotIn("Traceback", out, msg=f"{args} on {root}: {out[-800:]}")
        return proc

    def test_validate_survives_sources_as_scalar(self) -> None:
        self.assert_no_traceback(["validate"], self.project_with(sources="mutant"))

    def test_validate_survives_publishing_as_scalar(self) -> None:
        self.assert_no_traceback(["validate"], self.project_with(publishing=[1, 2]))

    def test_validate_survives_content_rules_as_scalar(self) -> None:
        self.assert_no_traceback(["validate"], self.project_with(content_rules=7))

    def test_validate_survives_artifacts_as_scalar(self) -> None:
        self.assert_no_traceback(["validate"], self.project_with(artifacts="mutant"))

    def test_validate_survives_monitoring_as_scalar(self) -> None:
        self.assert_no_traceback(["validate"], self.project_with(monitoring=[1, 2]))

    def test_validate_survives_eeat_as_scalar(self) -> None:
        self.assert_no_traceback(["validate"], self.project_with(eeat=7))

    def test_validate_survives_backlinks_as_scalar(self) -> None:
        self.assert_no_traceback(["validate"], self.project_with(backlinks="mutant"))

    def test_validate_survives_engines_as_int(self) -> None:
        # `engine_names()` did `for item in raw` after `raw = cfg.get("engines")
        # or []` — an int is truthy and not iterable: TypeError, not
        # AttributeError, at `seo_cycle_core/engines.py:17`.
        self.assert_no_traceback(["validate"], self.project_with(engines=7))

    def test_spend_survives_project_as_scalar(self) -> None:
        self.assert_no_traceback(["spend"], self.project_with(project="mutant"))

    def test_ledger_report_survives_project_as_scalar(self) -> None:
        self.assert_no_traceback(["ledger", "report"], self.project_with(project=[1, 2]))

    def test_db_survives_data_store_as_scalar(self) -> None:
        self.assert_no_traceback(["db"], self.project_with(data_store="mutant"))

    def test_db_survives_obsidian_as_scalar(self) -> None:
        self.assert_no_traceback(["db"], self.project_with(obsidian=7))


class EmptyConfigWritesNothingTest(unittest.TestCase):
    """T-067 round 4 (third gate): `require_config()` was wired into only
    2 of the (now known) 12 report-writing entrypoints — `context` and
    `pulse` each still gave rc=0 and wrote files over an existing-but-empty
    config, the exact class this whole sub-fix exists to close. One test
    per newly-wired command, driving the real CLI with a genuinely empty
    `seo-cycle.yaml` — not a re-check of `require_config()` itself (that's
    `RequireConfigTest`), but proof each call site actually reaches it."""

    def setUp(self) -> None:
        self.root = tmp_dir()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        (self.root / "seo-cycle.yaml").write_text("", encoding="utf-8")

    def _assert_refuses(self, args: list[str], report_glob: str) -> None:
        proc = run_cli(args, cwd=self.root)
        self.assertNotEqual(proc.returncode, 0, msg=f"{args}: {proc.stdout + proc.stderr}")
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        self.assertFalse(list(self.root.glob(report_glob)), msg=f"{args} wrote a report over an empty config")

    def test_context_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["context", "--write"], "seo/setup/context-pack*")

    def test_pulse_refuses_on_empty_config(self) -> None:
        # `pulse` writes scorecards and a position-progress report as part
        # of its pipeline, not under a `*pulse*`-named path — check the
        # files it ACTUALLY produces (verified by removing the fix: rc
        # becomes 1, not 0, but the files still get written — a naive
        # `rc != 0` check alone would have missed that).
        proc = run_cli(["pulse"], cwd=self.root)
        self.assertNotEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stdout + proc.stderr)
        self.assertFalse(list(self.root.glob("seo/reports/position-progress*")))
        self.assertFalse(list(self.root.glob("seo/scorecards/*")))

    def test_spend_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["spend", "--write"], "seo/setup/*spend*")

    def test_journey_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["journey", "--write"], "seo/setup/*journey*")

    def test_ledger_report_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["ledger", "report", "--write"], "seo/setup/*ledger*")

    def test_client_report_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["report", "--write"], "seo/reports/*")

    def test_kpi_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["kpi", "--write"], "seo/strategy/kpi*")

    def test_budget_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["budget", "--write"], "seo/strategy/budget*")

    def test_forecast_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["forecast", "--write"], "seo/strategy/*forecast*")

    def test_progress_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["progress", "--write"], "seo/reports/position-progress*")

    def test_cannibalization_refuses_on_empty_config(self) -> None:
        self._assert_refuses(["cannibalization", "--write"], "seo/vnext/*")


if __name__ == "__main__":
    unittest.main()
