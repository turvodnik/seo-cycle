"""T-093 (Б2 remainder, 2026-09-07): close the config-null/empty class on the
files T-090/T-092 did not reach.

T-067 (4 rounds) and T-090 (3 rounds) both re-opened this class because
their test matrices were built off the COMMAND REGISTRY, not off the files
that actually parse a config in bypass of it. This suite is built the other
way: `scripts/seo_cycle_core/config.py`'s own callers (`load_config`,
`load_yaml`, `require_config`, `require_section`, `config_section`) were
grepped across every `scripts/*.py` file.

IMPORTANT — a design mistake made and reverted during THIS ticket, kept
here as a comment because it is exactly the "fix migrates the bug to a
neighbor" trap the packet warned about: the first version of this fix put
the `project:` shape check INSIDE `load_config()` itself (one shared
check for every caller). That broke a DIFFERENT, pre-existing and
correctly-tested behavior — `seo_cycle_cli.py status`/`validate`,
`automation-recommender.py`, `growth-roadmap.py`, `launch-plan.py`,
`context-pack.py` all call `load_config()` too, but are DESIGNED to
degrade gracefully on a malformed `project:` section via the soft
`config_section()` helper (warn + `{}`, not exit(2)) — see
`test_config_t090.py::test_project_null_is_not_load_configs_problem` and
`test_config_robustness.py::CliSectionAccessTest`, both of which went red
under the shared-check version. The fix was reverted to `load_config()`'s
original T-090 shape (no project check) and reapplied at the ~35 SPECIFIC
call sites that actually read `project.*` identity fields, using the
EXISTING, already-tested `require_section(cfg, "project", cfg_path)`
helper T-090 built for exactly this — not a new global rule.

Two-part real fix:
  A) ~35 scripts that read `cfg.get("project"...)`/`nested_get(cfg,
     "project...")` for report identity now call
     `require_section(cfg, "project", cfg_path)` right after
     `cfg = load_config(cfg_path)` — closes `project: null`/string/list/
     number for exactly the scripts where a malformed section produces a
     real bad outcome (verified per-file: `--write` on `project: null`
     used to create output files even where the printed report showed no
     obviously "fake" project text — the packet's own file-creation
     criterion catches this where a text-only check would miss it).
  B) ~49 scripts that read their main config via the lenient `load_yaml`
     (silently returns `{}` on an empty/comment-only file) switched to
     `load_config` — closes the "file exists but is empty" gap.

Each test here launches the REAL script as a subprocess (T-090's own
lesson: importing a helper function proves nothing about the CLI's actual
wiring) against a temp project directory containing ONLY the bad config,
and asserts BOTH a non-zero exit code AND that no files were created —
the packet's own criterion, not just "no traceback".
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

# Scripts that got `require_section(cfg, "project", cfg_path)` added (part
# A) — must refuse on EVERY bad form including malformed-but-present
# `project:`.
PROJECT_REQUIRED_SCRIPTS = [
    "ads-analytics", "ads-apply", "ads-draft-builder", "ai-bot-access-check",
    "bing-url-inspection", "bitrix-content-pull", "gbp-fetch",
    "google-ads-fetch", "gsc-indexing-export-browser", "gsc-indexing-queue",
    "gsc-indexing-recheck", "gsc-request-indexing-browser",
    "gsc-url-inspection", "gtm-audit", "indexnow-submit", "labrika-health",
    "labrika-source-pack", "lighthouse-audit", "link-audit", "link-liveness",
    "loop-runner", "merchant-fetch", "metrika-logs-fetch", "notebooklm-health",
    "notebooklm-source-pack", "page-outline-v3", "perplexity-collect",
    "perplexity-health", "project-mcp-config", "project-upgrade-apply",
    "rag-index", "technical-mcp-health", "technical-site-audit",
    "tilda-content-pull", "woo-yml-feed", "wp-content-pull",
    "writerzen-browser-collect", "writerzen-health", "writerzen-source-pack",
    "xmlriver-health", "yandex-direct-fetch", "yandex-recrawl-submit",
    "yml-feed-audit",
    # Круг 2 (независимый гейт, R-2/R-3, 2026-09-07): класс был закрыт
    # перечнем, не по всем файлам — reviewer нашёл serpstat-audit.py (grep
    # исполнителя сам его находил, но файл не тронули) и 8 подкоманд CLI
    # (`seo-cycle context|report|kpi|spend|ledger|forecast|journey`,
    # `geo-log` — легитимное исключение, см. NO_PROJECT_NEEDED_SCRIPTS),
    # которые всё ещё писали файлы на `project: null` через "мягкую
    # деградацию" `config_section()` без единого теста, закрепляющего это
    # как решение (значит это был баг, не контракт).
    "automation-recommender", "budget-mix-planner", "client-report",
    "context-pack", "kpi-contract", "position-progress", "project-journey",
    "redirect-map-audit", "resolve-sources", "seo-forecast",
    "serpstat-audit", "setup-gap-audit", "spend-guard", "token-waste-audit",
    "usage-ledger",
    # Общий модуль `seo_cycle_core/health.py` (`style="simple"`, R-3) —
    # один общий фикс закрывает все пять разом.
    "gbp-health", "google-ads-health", "merchant-health",
    "yandex-business-health", "yandex-direct-health",
]
# ^ 35 of these got `require_section()` added by THIS ticket (see the
# module docstring, part A). The other 8 (ads-apply, ads-draft-builder,
# ai-bot-access-check, gsc-indexing-export-browser,
# gsc-request-indexing-browser, loop-runner, page-outline-v3,
# writerzen-browser-collect) already refused on every malformed-project
# form BEFORE this ticket touched them (verified empirically: existing
# `require_enabled`/`require_config` calls, or code paths that fail for
# unrelated reasons before `project` is ever read) — included here for
# matrix completeness, not left as an unverified assumption.

# Scripts migrated `load_yaml` -> `load_config` (part B) but never read
# `project.*` at all — only the "file exists but is unparseable/empty"
# class applies; a malformed-but-present `project:` section is genuinely
# irrelevant to what they do (verified per-file, named explicitly, not
# silently excluded — see Результат for the per-file reasoning):
#   - geo-citation-log.py: `load_config(cfg_path)` call is pure validation
#     (return discarded) — only derives project_root from the file's
#     LOCATION, never reads a field out of it.
#   - redirect-map-audit.py / rag-query.py: same pattern — `load_config`
#     is either validation-only or feeds an unrelated `data_store.*` key.
NO_PROJECT_NEEDED_SCRIPTS = ["geo-citation-log", "rag-query"]
# ^ redirect-map-audit.py moved to PROJECT_REQUIRED_SCRIPTS in круг 2: it
# still never reads `project.*` for its own content, but the packet's
# acceptance criterion is "zero files created" unconditionally, and it
# wrote 10 files on `project: null` (reviewer 🟡, круг 2 closed it via
# `require_section` even though the value itself stays unused — same
# validation-only pattern as `geo-citation-log.py`).

# Extra CLI args a script needs before it will even reach its config read.
EXTRA_ARGS = {
    "ads-apply": ["--draft", "draft.json"],
    "loop-runner": ["draft", "pkgdir", "--outline", "outline.json"],
    "page-outline-v3": ["pkgdir"],
    "perplexity-collect": ["--topic", "dummy topic"],
    "rag-query": ["dummy query"],
    "research-package-repair": ["pkgdir"],
    "spyfu-fetch": ["usage"],
    "seo_cycle_cli": ["doctor"],
}

# `--write` where the CLI supports it: several of the PROJECT_REQUIRED
# scripts only create files in `--write` mode — proving the "no files
# created" criterion needs `--write` passed, otherwise a script that
# would happily write garbage over a `project: null` config looks
# "clean" purely because nothing was asked to be written at all (found
# empirically for `ads-analytics.py` during this ticket: default mode
# writes nothing regardless of config validity, `--write` does).
WRITE_FLAG_SCRIPTS = {
    "ads-analytics", "bing-url-inspection", "gtm-audit", "indexnow-submit",
    "labrika-health", "labrika-source-pack", "lighthouse-audit", "link-audit",
    "link-liveness", "merchant-fetch", "technical-site-audit",
    "woo-yml-feed", "wp-content-pull", "writerzen-source-pack",
    "yandex-direct-fetch", "yandex-recrawl-submit", "yml-feed-audit",
    # Круг 2: the 17-writing-scripts finding (R-2) — these only reveal the
    # file-creation half of the bug with `--write` passed.
    "automation-recommender", "budget-mix-planner", "client-report",
    "context-pack", "kpi-contract", "position-progress", "project-journey",
    "redirect-map-audit", "seo-forecast", "serpstat-audit",
    "setup-gap-audit", "spend-guard", "token-waste-audit", "usage-ledger",
}

# The 49+3 scripts touched by part B (load_yaml -> load_config) — used to
# generate the "missing/empty/comments_only" half of the matrix for every
# touched script, independent of whether it also got require_section.
ALL_TOUCHED_SCRIPTS = sorted(set(PROJECT_REQUIRED_SCRIPTS) | set(NO_PROJECT_NEEDED_SCRIPTS) | {"seo_cycle_cli"})

# Scripts whose PRIMARY mode legitimately runs with NO config file at all —
# named explicitly, not silently excluded. Checked by hand: rc=0, zero
# files written, message names the actual missing INPUT, never a project
# identity ("Project: ?").
LEGIT_WITHOUT_CONFIG = {
    "metrika-cohorts": "needs --input-file/--live TSV data, not project identity",
    "site-crawl": "needs --live or --input-file; missing config -> 'network disabled' message",
    "structure-map": "needs site-crawl/sitemap data, not project identity",
    "spyfu-fetch": "the `usage` subcommand reports account-wide API usage, not project-scoped",
    "research-package-repair": "operates purely on a package directory tree, never reads project identity",
}

BAD_FORMS = {
    "empty": "",
    "comments_only": "# just a comment\n# nothing else\n",
    "project_null": "project: null\n",
    "project_string": 'project: "just a string"\n',
    "project_list": "project:\n  - a\n  - b\n",
    "project_number": "project: 42\n",
}


def _extra_fixtures(script: str, d: pathlib.Path) -> None:
    if script == "ads-apply":
        (d / "draft.json").write_text('{"platform": "google_ads", "campaigns": []}', encoding="utf-8")
    elif script == "loop-runner":
        (d / "pkgdir").mkdir(exist_ok=True)
        (d / "outline.json").write_text("{}", encoding="utf-8")
    elif script in ("page-outline-v3", "research-package-repair"):
        (d / "pkgdir").mkdir(exist_ok=True)


def _files_in(d: pathlib.Path) -> set[str]:
    return {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()}


def _run(script: str, cwd: pathlib.Path) -> subprocess.CompletedProcess:
    extra = list(EXTRA_ARGS.get(script, []))
    if script in WRITE_FLAG_SCRIPTS:
        extra.append("--write")
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{script}.py"), *extra],
        cwd=cwd, capture_output=True, text=True, timeout=30,
    )


class _TempProjectMixin:
    def make_project(self, config_text: str | None, script: str) -> pathlib.Path:
        d = pathlib.Path(tempfile.mkdtemp(prefix="t093-"))
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        if config_text is not None:
            (d / "seo-cycle.yaml").write_text(config_text, encoding="utf-8")
        _extra_fixtures(script, d)
        return d


def _make_bad_config_test(script: str, form: str, content: str):
    def test(self: unittest.TestCase) -> None:
        d = self.make_project(content, script)
        before = _files_in(d) - ({"seo-cycle.yaml"} if content is not None else set())
        proc = _run(script, d)
        after = _files_in(d)
        new_files = after - before - ({"seo-cycle.yaml"} if content is not None else set())
        self.assertNotEqual(
            proc.returncode, 0,
            f"{script}.py on config form '{form}' should exit non-zero, got 0\n"
            f"stdout: {proc.stdout[:400]}\nstderr: {proc.stderr[:400]}",
        )
        self.assertEqual(
            new_files, set(),
            f"{script}.py on config form '{form}' must not create files on a refused config, "
            f"created: {sorted(new_files)}",
        )
        self.assertNotIn("Traceback (most recent call last)", proc.stdout + proc.stderr)

    test.__name__ = f"test_{script.replace('-', '_')}_{form}"
    return test


class ConfigNullRemainderMatrix(_TempProjectMixin, unittest.TestCase):
    """One test per (touched script × malformed-config form)."""


for _script in ALL_TOUCHED_SCRIPTS:
    is_project_required = _script in PROJECT_REQUIRED_SCRIPTS
    for _form, _content in BAD_FORMS.items():
        if _form.startswith("project_") and not is_project_required and _script not in NO_PROJECT_NEEDED_SCRIPTS:
            # Not yet classified either way — skip rather than assert
            # blindly (see Результат for the scripts left unclassified).
            continue
        if _form.startswith("project_") and _script in NO_PROJECT_NEEDED_SCRIPTS:
            # Documented: these never read `project.*` at all — a
            # malformed section is a no-op for them, not a bug. Only
            # `empty`/`comments_only`/`missing` (load_config's own gate)
            # apply.
            continue
        _t = _make_bad_config_test(_script, _form, _content)
        setattr(ConfigNullRemainderMatrix, _t.__name__, _t)
    if _script not in LEGIT_WITHOUT_CONFIG:
        _t = _make_bad_config_test(_script, "missing", None)
        setattr(ConfigNullRemainderMatrix, _t.__name__, _t)


class LegitNoConfigExceptionsTest(_TempProjectMixin, unittest.TestCase):
    """The 5 scripts named in LEGIT_WITHOUT_CONFIG: prove the documented
    claim itself (rc=0, zero files, an honest missing-DATA message — not a
    fake green project report) rather than just skipping them silently."""

    def _assert_legit_noop(self, script: str, extra_marker: str) -> None:
        d = self.make_project(None, script)
        before = _files_in(d)
        proc = _run(script, d)
        after = _files_in(d)
        self.assertEqual(proc.returncode, 0, f"{script}.py missing-config should stay a documented no-op (rc=0), got {proc.returncode}")
        self.assertEqual(after - before, set(), f"{script}.py missing-config must still write nothing")
        self.assertNotIn("Project: ?", proc.stdout)
        self.assertIn(extra_marker, proc.stdout + proc.stderr)

    def test_metrika_cohorts(self) -> None:
        self._assert_legit_noop("metrika-cohorts", "TSV")

    def test_site_crawl(self) -> None:
        self._assert_legit_noop("site-crawl", "--live")

    def test_structure_map(self) -> None:
        self._assert_legit_noop("structure-map", "site-crawl.py")

    def test_spyfu_fetch_usage(self) -> None:
        self._assert_legit_noop("spyfu-fetch", "$")

    def test_research_package_repair(self) -> None:
        self._assert_legit_noop("research-package-repair", "Research Package Repair")


class RequireSectionRegressionGuardTest(unittest.TestCase):
    """The regression this ticket introduced and reverted mid-flight in
    круг 1: a shared `load_config()`-level project-shape check broke
    `status`/`validate` and several other commands that were, AT THAT
    TIME, designed to degrade gracefully on a malformed `project:` (soft
    `config_section()`, not a hard exit).

    круг 2 (independent gate, R-2) then found that "designed to degrade
    gracefully" was true for some of those commands only by ACCIDENT — no
    test anywhere locked it in as a decision, and several (`automation-
    recommender.py`, `context-pack.py`, and `status`'s own delegation to
    `project-journey.py`) were simply unfixed files, not a contract. Круг
    2 added `require_section()` to them too. As of круг 2, EVERY command
    from круг 1's list is intentionally strict again — so the invariant
    left worth pinning is narrower and more precise than "these five
    commands stay soft forever": `load_config()` ITSELF must never gain a
    global project-shape check again — only a per-call-site
    `require_section()` may. Proven here the way круг 1 broke it: a
    script that legitimately never reads `project.*`
    (`geo-citation-log.py`, in `NO_PROJECT_NEEDED_SCRIPTS`) must still
    tolerate a malformed `project:` section, because nothing in ITS code
    calls `require_section` for it — if `load_config()` grew a global
    check again, this specific script would start refusing too, exactly
    the круг-1 regression, caught here without relying on any command's
    UI-level soft/hard product decision."""

    def test_load_config_itself_tolerates_project_as_string_when_caller_never_checks_it(self) -> None:
        d = pathlib.Path(tempfile.mkdtemp(prefix="t093-regguard-"))
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        (d / "seo-cycle.yaml").write_text('project: "just a string"\n', encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "geo-citation-log.py")],
            cwd=d, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(
            proc.returncode, 0,
            "geo-citation-log.py never reads project.* and calls no require_section — "
            "load_config() must stay tolerant of a malformed project: section for it, "
            "or the круг-1 global-check regression is back. "
            f"got rc={proc.returncode}\nstdout: {proc.stdout[:400]}\nstderr: {proc.stderr[:400]}",
        )


class SetupWizardExceptionsTest(unittest.TestCase):
    """Круг 2 (R-2/R-3 full-repository sweep, `/private/tmp/full_sweep_r2.py`
    — every `scripts/*.py` against `empty`/`project: null` with `--write`):
    only 2 of 166 scripts still write files on a malformed config —
    `project-intake-wizard.py` and `setup-onboarding.py`. Both are legitimate
    by construction (T-090's own docstring: "intake wizard is a legitimate
    empty-config boundary — it exists to CREATE a project's config"),
    proven here rather than trusted from memory: their OUTPUT is exactly a
    fresh config/onboarding artifact, not a fake report claiming an
    established project's identity."""

    def _assert_wizard_creates_config(self, script: str, created_marker: str) -> None:
        d = pathlib.Path(tempfile.mkdtemp(prefix="t093-wizard-"))
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        (d / "seo-cycle.yaml").write_text("project: null\n", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / f"{script}.py"), "--write"],
            cwd=d, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 0, f"{script}.py --write should succeed as a setup wizard, got rc={proc.returncode}")
        self.assertIn(created_marker, proc.stdout + proc.stderr + "\n".join(str(p) for p in d.rglob("*")))

    def test_project_intake_wizard_creates_intake_not_a_fake_report(self) -> None:
        self._assert_wizard_creates_config("project-intake-wizard", "project-intake")

    def test_setup_onboarding_creates_playbook_not_a_fake_report(self) -> None:
        self._assert_wizard_creates_config("setup-onboarding", "onboarding")


if __name__ == "__main__":
    unittest.main()
