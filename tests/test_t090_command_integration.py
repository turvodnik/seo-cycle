"""T-090 round 2 (independent gate 2026-09-07, 🔴3): integration coverage
for the config-reading migration itself.

The gate's mutation test showed the previous test suite (861 tests) never
actually ran a migrated COMMAND end to end against a bad config — it only
tested `require_section`/`load_yaml_any` as pure functions in isolation.
Mutating `require_section(cfg, "project", args.config)` back to
`(cfg.get("project") or {})` in `monthly-dashboard.py`/`db-sync.py`
reproduced the original F-7 bug (`rc=0`, a green "✓ ..." report) and the
full suite stayed green.

These tests close that gap: each one launches a REAL `scripts/*.py` file
as a subprocess (not an import — a subprocess is the only way to prove
the command's own `main()` wiring, not just a helper function, refuses)
against a `project: null` (and/or empty) `seo-cycle.yaml`, and asserts
`returncode == 2`. Revert any of the `require_section`/`load_config`
call sites this test covers back to the old `cfg.get(...)` idiom, and the
matching test here goes red.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"


def run_script(name: str, cwd: pathlib.Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{name}.py"), *extra_args],
        cwd=cwd, capture_output=True, text=True, timeout=30,
    )


class _TempProjectMixin:
    def make_project(self, config_text: str | None) -> pathlib.Path:
        d = pathlib.Path(tempfile.mkdtemp(prefix="t090-integ-"))
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        cfg = d / "seo-cycle.yaml"
        if config_text is not None:
            cfg.write_text(config_text, encoding="utf-8")
        return d


class RequireSectionProjectNullIntegrationTest(_TempProjectMixin, unittest.TestCase):
    """Every command here has a `require_section(cfg, "project", ...)` (or
    equivalent) call site on its main-config read path. `project: null` is
    the exact gate reproduction input (§ "Кросс-голосование", 🔴2) — a
    present-but-null section that a bare `cfg.get("project", {})` lets
    through as `None`, and that this test proves is refused with rc=2 by
    running the actual command, not a helper function."""

    PROJECT_NULL = "project: null\n"

    def assert_refuses(self, name: str, *extra_args: str) -> None:
        proj = self.make_project(self.PROJECT_NULL)
        proc = run_script(name, proj, *extra_args)
        self.assertEqual(
            proc.returncode, 2,
            f"{name}.py on `project: null` should exit 2, got {proc.returncode}\n"
            f"stdout: {proc.stdout[:500]}\nstderr: {proc.stderr[:500]}",
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stdout + proc.stderr)

    # T-090 round 1 fixes (already covered by the gate's own mutation, kept
    # here so a future revert of either is caught the same way).
    def test_monthly_dashboard(self) -> None:
        self.assert_refuses("monthly-dashboard")

    def test_db_sync(self) -> None:
        # db-sync's `require_section(cfg, "project", ...)` call site only
        # runs on the Obsidian-dashboard code path (`dashboard_path(cfg)`
        # returning non-None) — the gate's own mutation target
        # (report §"3. Мутация", `db-sync.py:363`). A `project: null`
        # config with Obsidian dashboards off never reaches that line at
        # all, so this test enables it explicitly to actually exercise it,
        # not just get an unrelated argparse rc=2.
        proj = self.make_project(
            "project: null\n"
            "obsidian:\n"
            "  enabled: true\n"
            "  dashboards: true\n"
            "  central_vault: ./vault\n"
        )
        proc = run_script("db-sync", proj)
        self.assertEqual(
            proc.returncode, 2,
            f"db-sync.py on `project: null` (Obsidian dashboards on) should exit 2, "
            f"got {proc.returncode}\nstdout: {proc.stdout[:500]}\nstderr: {proc.stderr[:500]}",
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stdout + proc.stderr)

    # T-090 round 2 fixes: the crash-to-F-7b class the gate's 🔴1/🔴2 named.
    def test_governance_report(self) -> None:
        self.assert_refuses("governance-report")

    def test_growth_roadmap(self) -> None:
        self.assert_refuses("growth-roadmap")

    def test_automation_plan(self) -> None:
        self.assert_refuses("automation-plan")

    def test_launch_plan(self) -> None:
        self.assert_refuses("launch-plan")

    def test_task_router(self) -> None:
        self.assert_refuses("task-router", "--task", "next")

    def test_tool_stack_recommender(self) -> None:
        self.assert_refuses("tool-stack-recommender")

    def test_access_key_assistant(self) -> None:
        self.assert_refuses("access-key-assistant")

    def test_project_upgrade_assistant(self) -> None:
        self.assert_refuses("project-upgrade-assistant")

    def test_setup_answer_plan(self) -> None:
        self.assert_refuses("setup-answer-plan")

    def test_setup_blueprint(self) -> None:
        self.assert_refuses("setup-blueprint")

    def test_setup_control_plane(self) -> None:
        self.assert_refuses("setup-control-plane")


class LoadConfigEmptyFileIntegrationTest(_TempProjectMixin, unittest.TestCase):
    """The read-function-level fix (🔴1): a `seo-cycle.yaml` that EXISTS
    but is empty/comment-only/bare-null must make every command whose main
    config read is `load_config` (directly, or via a per-file `load_yaml`
    wrapper that calls it) refuse with rc=2 — not print a report that
    looks like a healthy run. These are the gate's own "group A" repro
    commands (report §"1. F-7b не закрыт")."""

    def assert_refuses_on(self, name: str, content: str, *extra_args: str) -> None:
        proj = self.make_project(content)
        proc = run_script(name, proj, *extra_args)
        self.assertEqual(
            proc.returncode, 2,
            f"{name}.py on {content!r} config should exit 2, got {proc.returncode}\n"
            f"stdout: {proc.stdout[:500]}\nstderr: {proc.stderr[:500]}",
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stdout + proc.stderr)

    def test_automation_plan_empty_file(self) -> None:
        self.assert_refuses_on("automation-plan", "")

    def test_governance_report_comment_only(self) -> None:
        self.assert_refuses_on("governance-report", "# nothing here\n")

    def test_growth_roadmap_bare_null(self) -> None:
        self.assert_refuses_on("growth-roadmap", "---\nnull\n")

    def test_automation_recommender_empty_file(self) -> None:
        self.assert_refuses_on("automation-recommender", "")

    def test_task_router_empty_file(self) -> None:
        self.assert_refuses_on("task-router", "", "--task", "next")

    def test_tool_stack_recommender_empty_file(self) -> None:
        self.assert_refuses_on("tool-stack-recommender", "")

    def test_launch_plan_empty_file(self) -> None:
        self.assert_refuses_on("launch-plan", "")

    def test_token_waste_audit_empty_file(self) -> None:
        self.assert_refuses_on("token-waste-audit", "")

    def test_no_report_files_created_on_empty_config(self) -> None:
        """The gate's other explicit complaint: on an empty config,
        commands must not create output files that look like a successful
        run (`obsidian-vault/`, `seo/cycles/.../active-sources.json`,
        etc.). automation-plan's --write path is one concrete repro."""
        proj = self.make_project("")
        run_script("automation-plan", proj, "--write")
        # Nothing besides the (empty) config file itself should exist.
        created = sorted(p.relative_to(proj).as_posix() for p in proj.rglob("*") if p.is_file())
        self.assertEqual(created, ["seo-cycle.yaml"], f"unexpected files created on empty config: {created}")


class ObsidianSyncProjectShapeIntegrationTest(_TempProjectMixin, unittest.TestCase):
    """obsidian-sync.py's f-string project-name interpolation crashed on
    both `project: null` (AttributeError on None) and `project: "acme"`
    (AttributeError on str) before this round — a real, reproduced
    traceback the gate found, not a theoretical one."""

    def test_project_null_no_traceback(self) -> None:
        proj = self.make_project("project: null\n")
        proc = run_script("obsidian-sync", proj)
        self.assertNotIn("Traceback (most recent call last)", proc.stdout + proc.stderr)

    def test_project_as_string_no_traceback(self) -> None:
        proj = self.make_project('project: "acme"\n')
        proc = run_script("obsidian-sync", proj)
        self.assertNotIn("Traceback (most recent call last)", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
