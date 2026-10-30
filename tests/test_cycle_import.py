#!/usr/bin/env python3
"""Tests for `cycle-state.py import` / `seo-cycle cycle import` (T-057).

Old projects (a project without a cycles directory) keep phase artifacts as flat files in `seo/`
(`02-keywords.md`, `03-clusters.md`, `keywords/`, `entities/`, ...) and have
no `seo/cycles/<topic>/_state.json`, so `cycle gate` never ran for them.
`import` builds that state from what is on disk: found phases become `done`
with `gate_passed: false` (gates are never confirmed retroactively).

Commands run as subprocesses with cwd = project root, like the real CLI.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT = SCRIPTS / "cycle-state.py"
CLI = SCRIPTS / "seo_cycle_cli.py"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core import journey  # noqa: E402


def write(path: pathlib.Path, text: str = "content\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CycleImportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cycle-import-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo").mkdir()

    def run_cs(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )

    def legacy_layout(self) -> None:
        """Flat legacy layout of a project without a cycles directory (only the mapped parts)."""
        seo = self.tmp / "seo"
        write(seo / "02-keywords.md", "# keywords\n")
        write(seo / "03-clusters.md", "# clusters\n")
        write(seo / "keywords" / "parent" / "a.json", "{}\n")
        write(seo / "entities" / "entities.yaml", "a: 1\n")
        write(seo / "content-drafts" / "page.md", "draft\n")
        write(seo / "monitoring" / "webmaster-snapshot-2026-07-04.json", "{}\n")
        write(seo / "setup" / "context-pack.md", "# context\n")
        write(seo / "technical" / "technical-site-audit.md", "# audit\n")
        # Not a phase artifact: must not change anything.
        write(seo / "research-package" / "x.md", "noise\n")

    def state_path(self, topic: str = "legacy-main") -> pathlib.Path:
        return self.tmp / "seo" / "cycles" / topic / "_state.json"

    def load_state(self, topic: str = "legacy-main") -> dict:
        return json.loads(self.state_path(topic).read_text(encoding="utf-8"))

    # -- flat legacy layout ------------------------------------------------

    def test_flat_legacy_layout_builds_state(self) -> None:
        self.legacy_layout()
        proc = self.run_cs("import", "legacy-main", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = self.load_state()
        ph = state["phases"]
        self.assertEqual(state["topic"], "legacy-main")
        self.assertEqual(state["cycle_dir"], "seo/cycles/legacy-main")
        expected = {
            "discovery": "seo/setup/context-pack.md",
            "audit": "seo/technical/technical-site-audit.md",
            "keywords": "seo/02-keywords.md",
            "clusters": "seo/03-clusters.md",
            "entity_map": "seo/entities",
            "writing": "seo/content-drafts",
            "monitoring": "seo/monitoring",
        }
        # writing / monitoring: files found, but content_plan / publishing are
        # not in the legacy layout -> blocked, not done (T-057 gate 💭2).
        waiting = {"writing", "monitoring"}
        for phase, output in expected.items():
            self.assertEqual(ph[phase]["status"], "blocked" if phase in waiting else "done", phase)
            self.assertEqual(ph[phase]["output"], output, phase)
            self.assertIs(ph[phase]["gate_passed"], False, phase)
            self.assertTrue((self.tmp / output).exists(), output)
        self.assertEqual(ph["keywords"]["imported_from"], ["seo/02-keywords.md", "seo/keywords"])
        # Phases the old layout does not know stay unconfirmed, blocked by deps.
        for phase in ("content_plan", "publishing", "schema", "iteration"):
            self.assertEqual(ph[phase]["status"], "blocked", phase)
            self.assertNotIn("imported_from", ph[phase])
        # Never a retroactive gate.
        self.assertFalse(any(p["gate_passed"] for p in ph.values()))
        # Same phase set and deps as `init`, so every reader of _state.json works.
        init = self.run_cs("init", "--topic", "x", "--dir", "ref")
        self.assertEqual(init.returncode, 0, init.stderr)
        ref = json.loads((self.tmp / "ref" / "_state.json").read_text(encoding="utf-8"))["phases"]
        self.assertEqual(list(ph), list(ref))
        for name in ref:
            self.assertEqual(ph[name]["depends_on"], ref[name]["depends_on"], name)

    def test_empty_artifact_does_not_count(self) -> None:
        write(self.tmp / "seo" / "02-keywords.md", "")
        (self.tmp / "seo" / "entities").mkdir()
        proc = self.run_cs("import", "t", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ph = self.load_state("t")["phases"]
        self.assertNotEqual(ph["keywords"]["status"], "done")
        self.assertNotEqual(ph["entity_map"]["status"], "done")

    def test_placeholder_files_do_not_count(self) -> None:
        """QA 3.0.1 Y4: `.gitkeep`, `.DS_Store`, an empty subdirectory and a
        whitespace-only file are not artifacts — neither for import nor for gate."""
        seo = self.tmp / "seo"
        write(seo / "keywords" / ".gitkeep", "")
        write(seo / "entities" / ".DS_Store", "Bud1")
        (seo / "content-drafts" / "empty-subdir").mkdir(parents=True)
        write(seo / "02-keywords.md", "\n  \n")
        proc = self.run_cs("import", "junk", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ph = self.load_state("junk")["phases"]
        for phase in ("keywords", "entity_map", "writing"):
            self.assertNotEqual(ph[phase]["status"], "done", phase)
            self.assertNotIn("imported_from", ph[phase], phase)
        # The gate uses the same rule: a placeholder-only cycle dir does not pass.
        self.assertEqual(self.run_cs("init", "--topic", "c", "--dir", "seo/cycles/c").returncode, 0)
        write(seo / "cycles" / "c" / "06-drafts" / ".DS_Store", "Bud1")
        (seo / "cycles" / "c" / "06-drafts" / "sub").mkdir()
        write(seo / "cycles" / "c" / "02-keywords.md", "\n")
        for phase in ("writing", "keywords"):
            gate = self.run_cs("gate", phase, "--dir", "seo/cycles/c")
            self.assertEqual(gate.returncode, 1, gate.stdout)
        # A real file deep inside counts.
        write(seo / "cycles" / "c" / "06-drafts" / "sub" / "page.md", "draft\n")
        self.assertEqual(self.run_cs("gate", "writing", "--dir", "seo/cycles/c").returncode, 0)

    def test_import_does_not_mark_done_after_a_missing_predecessor(self) -> None:
        """T-057 gate 💭2: a phase found on disk whose predecessor was not
        found stays blocked (files recorded in `imported_from`), so its gate
        cannot close a journey stage out of DAG order."""
        self.legacy_layout()
        proc = self.run_cs("import", "legacy-main", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ph = self.load_state()["phases"]
        for phase in ("writing", "monitoring"):  # content_plan / publishing are not in the legacy layout
            self.assertEqual(ph[phase]["status"], "blocked", phase)
            self.assertTrue(ph[phase]["imported_from"], phase)
        self.assertRegex(proc.stdout, r"writing\s+blocked\s+seo/content-drafts")
        show = self.run_cs("show", "--dir", "seo/cycles/legacy-main")
        self.assertIn("ждут предыдущих фаз: writing, monitoring", show.stdout)
        gate = self.run_cs("gate", "writing", "--dir", "seo/cycles/legacy-main")
        self.assertEqual(gate.returncode, 0, gate.stdout)
        self.assertEqual(self.load_state()["phases"]["writing"]["status"], "blocked")
        self.assertFalse(journey.read_cycle_phases({}, self.tmp)["writing"]["closed"])

    # -- refusal on existing state -------------------------------------------

    def test_existing_state_is_refused(self) -> None:
        self.legacy_layout()
        first = self.run_cs("import", "legacy-main", "--write")
        self.assertEqual(first.returncode, 0, first.stderr)
        before = self.state_path().read_bytes()
        again = self.run_cs("import", "legacy-main", "--write")
        self.assertEqual(again.returncode, 1)
        self.assertIn("уже существует", again.stderr)
        self.assertIn("seo-cycle cycle show --dir seo/cycles/legacy-main", again.stderr)
        self.assertEqual(self.state_path().read_bytes(), before, "state must not be overwritten")
        # dry-run on an existing state warns but never writes
        dry = self.run_cs("import", "legacy-main")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("--write откажет", dry.stdout)
        self.assertEqual(self.state_path().read_bytes(), before)

    def test_foreign_state_from_init_is_refused(self) -> None:
        init = self.run_cs("init", "--topic", "x", "--dir", "seo/cycles/legacy-main")
        self.assertEqual(init.returncode, 0, init.stderr)
        before = self.state_path().read_bytes()
        proc = self.run_cs("import", "legacy-main", "--write")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.state_path().read_bytes(), before)

    # -- empty project ----------------------------------------------------------

    def test_empty_project_has_no_done_phases(self) -> None:
        proc = self.run_cs("import", "empty", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ph = self.load_state("empty")["phases"]
        self.assertFalse(any(p["status"] == "done" for p in ph.values()))
        self.assertEqual(ph["discovery"]["status"], "pending")
        self.assertTrue(all(p["status"] == "blocked" for n, p in ph.items() if n != "discovery"))
        self.assertIn("Найдено фаз: 0 из 11", proc.stdout)

    # -- dry-run ------------------------------------------------------------------

    def test_dry_run_is_default_and_idempotent(self) -> None:
        self.legacy_layout()
        runs = [self.run_cs("import", "legacy-main"), self.run_cs("import", "legacy-main", "--dry-run")]
        for proc in runs:
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("dry-run, ничего не записано", proc.stdout)
            self.assertRegex(proc.stdout, r"keywords\s+done\s+seo/02-keywords\.md \(\+ seo/keywords\)")
            self.assertRegex(proc.stdout, r"clusters\s+done\s+seo/03-clusters\.md")
            self.assertRegex(proc.stdout, r"content_plan\s+blocked\s+— не найдено")
        self.assertEqual(runs[0].stdout, runs[1].stdout)
        self.assertFalse((self.tmp / "seo" / "cycles").exists(), "dry-run must not create anything")

    def test_dry_run_and_write_are_exclusive(self) -> None:
        proc = self.run_cs("import", "t", "--dry-run", "--write")
        self.assertEqual(proc.returncode, 2)
        self.assertFalse((self.tmp / "seo" / "cycles").exists())

    # -- show / gate after import ------------------------------------------------

    def test_show_explains_unconfirmed_gates(self) -> None:
        self.legacy_layout()
        self.assertEqual(self.run_cs("import", "legacy-main", "--write").returncode, 0)
        show = self.run_cs("show", "--dir", "seo/cycles/legacy-main")
        self.assertEqual(show.returncode, 0, show.stderr)
        self.assertRegex(show.stdout, r"keywords\s+done \[импорт, gate_passed: false — ворота не проходились\]")
        self.assertIn("ворота не проходились: discovery, audit, keywords, clusters", show.stdout)
        self.assertNotIn("[gate✓]", show.stdout)

    def test_gate_checks_imported_project_relative_output(self) -> None:
        self.legacy_layout()
        self.assertEqual(self.run_cs("import", "legacy-main", "--write").returncode, 0)
        gate = self.run_cs("gate", "keywords", "--dir", "seo/cycles/legacy-main")
        self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
        self.assertIn("✓ PASS: gate keywords (output: seo/02-keywords.md)", gate.stdout)
        ph = self.load_state()["phases"]
        self.assertIs(ph["keywords"]["gate_passed"], True)
        self.assertIs(ph["clusters"]["gate_passed"], False, "gate confirms one phase, not all")
        show = self.run_cs("show", "--dir", "seo/cycles/legacy-main")
        self.assertRegex(show.stdout, r"keywords\s+done \[gate✓\]")
        self.assertRegex(show.stdout, r"clusters\s+done \[импорт, gate_passed: false")
        # Artifact gone -> the gate fails honestly instead of passing.
        (self.tmp / "seo" / "03-clusters.md").unlink()
        fail = self.run_cs("gate", "clusters", "--dir", "seo/cycles/legacy-main")
        self.assertEqual(fail.returncode, 1)
        self.assertIn("✗ FAIL: gate clusters", fail.stdout)

    def test_gate_still_prefers_output_inside_cycle_dir(self) -> None:
        cdir = self.tmp / "seo" / "cycles" / "c"
        self.assertEqual(self.run_cs("init", "--topic", "c", "--dir", "seo/cycles/c").returncode, 0)
        write(cdir / "02-keywords.md", "kw\n")
        gate = self.run_cs("gate", "keywords", "--dir", "seo/cycles/c")
        self.assertEqual(gate.returncode, 0, gate.stdout)
        self.assertIn("output: seo/cycles/c/02-keywords.md", gate.stdout)

    def test_gate_ignores_stray_root_file_for_init_cycle(self) -> None:
        """QA 3.0.1 R1: a same-named file in the project root must not pass the
        gate of a cycle created by `init` (3.0.0 behaviour: FAIL)."""
        write(self.tmp / "02-keywords.md", "# stray\n")
        write(self.tmp / "10-iterations.md", "# stray triggers output\n")
        self.assertEqual(self.run_cs("init", "--topic", "fresh", "--dir", "seo/cycles/fresh").returncode, 0)
        for phase in ("keywords", "iteration"):
            gate = self.run_cs("gate", phase, "--dir", "seo/cycles/fresh")
            self.assertEqual(gate.returncode, 1, gate.stdout + gate.stderr)
            self.assertIn(f"✗ FAIL: gate {phase}", gate.stdout)
        ph = json.loads((self.tmp / "seo" / "cycles" / "fresh" / "_state.json").read_text(encoding="utf-8"))["phases"]
        self.assertIs(ph["keywords"]["gate_passed"], False)

    def test_cyrillic_topics_get_readable_distinct_dirs(self) -> None:
        """QA 3.0.1 Y7: Cyrillic topics are transliterated, different topics
        never share a directory, `--dir` to a missing cycle is one line rc 2."""
        write(self.tmp / "seo" / "02-keywords.md", "kw\n")
        proc = self.run_cs("import", "минеральная вата", "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.tmp / "seo" / "cycles" / "mineralnaya-vata" / "_state.json").exists(), proc.stdout)
        for a, b in (("вата 2026", "утеплитель 2026"), ("минеральная вата-import", "утеплитель-import")):
            self.assertEqual(self.run_cs("import", a, "--write").returncode, 0)
            second = self.run_cs("import", b, "--write")
            self.assertEqual(second.returncode, 0, f"{a!r} and {b!r} collided: {second.stderr}")
        again = self.run_cs("import", "минеральная вата", "--write")
        self.assertEqual(again.returncode, 1)
        self.assertIn("seo-cycle cycle import 'минеральная вата-import' --write", again.stderr)
        self.assertIn("seo/cycles/mineralnaya-vata-import", again.stderr)
        show = self.run_cs("show", "--dir", "seo/cycles/минеральная вата")
        self.assertEqual(show.returncode, 2, show.stdout + show.stderr)
        self.assertNotIn("Traceback", show.stderr)
        self.assertEqual(len(show.stderr.strip().splitlines()), 1, show.stderr)

    # -- custom map / --from ------------------------------------------------------

    def test_custom_map_and_from(self) -> None:
        write(self.tmp / "legacy" / "plan.md", "plan\n")
        write(self.tmp / "legacy" / "02-keywords.md", "kw\n")
        mp = self.tmp / "map.json"
        mp.write_text(json.dumps({"content_plan": "plan.md"}), encoding="utf-8")
        proc = self.run_cs("import", "t", "--from", "legacy", "--map", str(mp), "--write")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ph = self.load_state("t")["phases"]
        self.assertEqual(ph["content_plan"]["output"], "legacy/plan.md")
        self.assertEqual(ph["keywords"]["output"], "legacy/02-keywords.md", "default map still applies")

    def test_bad_map_is_a_usage_error(self) -> None:
        mp = self.tmp / "map.json"
        mp.write_text(json.dumps({"nope": "x.md"}), encoding="utf-8")
        proc = self.run_cs("import", "t", "--map", str(mp), "--write")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("неизвестная фаза 'nope'", proc.stderr)
        mp.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.run_cs("import", "t", "--map", str(mp)).returncode, 2)
        self.assertFalse((self.tmp / "seo" / "cycles").exists())

    def test_missing_from_dir_is_a_usage_error(self) -> None:
        proc = self.run_cs("import", "t", "--from", "absent", "--write")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("не найден", proc.stderr)

    # -- consumers ------------------------------------------------------------------

    def test_unified_cli_routes_cycle_import(self) -> None:
        self.legacy_layout()
        proc = subprocess.run(
            [sys.executable, str(CLI), "--project", str(self.tmp), "cycle", "import", "legacy-main", "--write"],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.state_path().exists())

    def test_custom_cycles_root_is_one_model_with_status(self) -> None:
        """QA 3.0.1 Y2: `artifacts.cycles_root` is honoured by cycle-state too,
        so gates passed with documented commands count in `status`."""
        template = (ROOT / "config" / "project.template.yaml").read_text(encoding="utf-8")
        self.assertIn('cycles_root: "./seo/cycles"', template)
        (self.tmp / "seo-cycle.yaml").write_text(
            template.replace('cycles_root: "./seo/cycles"', 'cycles_root: "./custom/cycles"'), encoding="utf-8")
        self.legacy_layout()

        def cli(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, str(CLI), "--project", str(self.tmp), *args],
                                  cwd=ROOT, text=True, capture_output=True, check=False)

        self.assertEqual(cli("cycle", "import", "main", "--write").returncode, 0)
        self.assertTrue((self.tmp / "custom" / "cycles" / "main" / "_state.json").exists())
        self.assertFalse((self.tmp / "seo" / "cycles").exists())
        for phase in ("discovery", "audit"):
            gate = cli("cycle", "gate", phase)  # no --dir: the newest cycle under cycles_root
            self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
        status = cli("status")
        self.assertIn("Сделано: 2 из 12", status.stdout + status.stderr)
        init = cli("cycle", "init", "--topic", "fresh")
        self.assertIn("custom/cycles/fresh-", init.stdout)

    def test_symlinked_cycles_root_stays_project_relative(self) -> None:
        """QA2 3.0.1 #1: `seo/cycles` (or the whole `seo/`) as a symlink to a
        folder outside the project (an Obsidian vault) must not put an
        absolute path into `_state.json`; after moving the project the gate
        still passes."""
        template = (ROOT / "config" / "project.template.yaml").read_text(encoding="utf-8")
        for linked in ("seo/cycles", "seo"):
            with self.subTest(linked=linked):
                base = pathlib.Path(tempfile.mkdtemp(prefix="cycle-sym-"))
                self.addCleanup(lambda b=base: shutil.rmtree(b, ignore_errors=True))
                proj, vault = base / "p", base / "vault"
                vault.mkdir()
                (proj / "seo").mkdir(parents=True) if linked == "seo/cycles" else proj.mkdir()
                (proj / linked).symlink_to(vault, target_is_directory=True)
                (proj / "seo-cycle.yaml").write_text(template, encoding="utf-8")

                def cs(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
                    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                                          text=True, capture_output=True, check=False)

                init = cs(proj, "init", "--topic", "topic")
                self.assertEqual(init.returncode, 0, init.stderr)
                cdir = next((proj / "seo" / "cycles").glob("topic-*"))
                rel = f"seo/cycles/{cdir.name}"
                state = json.loads((cdir / "_state.json").read_text(encoding="utf-8"))
                self.assertEqual(state["cycle_dir"], rel)
                (cdir / "00-discovery.md").write_text("# discovery\n", encoding="utf-8")
                self.assertEqual(cs(proj, "set", "discovery", "--status", "done", "--dir", rel).returncode, 0)
                self.assertEqual(cs(proj, "gate", "discovery", "--dir", rel).returncode, 0)
                moved = base / "p-moved"
                proj.rename(moved)
                gate = cs(moved, "gate", "discovery", "--dir", rel)
                self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)

    def test_absolute_cycles_root_through_a_symlink_stays_project_relative(self) -> None:
        """QA3 3.0.1 #2: an absolute `artifacts.cycles_root` that points inside
        the project through a symlinked path (`~/ai` -> `~/Проекты ai`, macOS
        `/tmp` -> `/private/tmp`) must still be stored project-relative — with
        `seo/cycles` a plain folder and with `seo/cycles` itself a symlink to a
        vault outside the project (the QA2 #1 case must keep working too)."""
        template = (ROOT / "config" / "project.template.yaml").read_text(encoding="utf-8")
        self.assertIn('cycles_root: "./seo/cycles"', template)
        for cycles_kind in ("dir", "symlink"):
            with self.subTest(cycles=cycles_kind):
                base = pathlib.Path(tempfile.mkdtemp(prefix="cycle-abs-"))
                self.addCleanup(lambda b=base: shutil.rmtree(b, ignore_errors=True))
                (base / "alias").symlink_to(base, target_is_directory=True)
                proj = base / "p"
                (proj / "seo").mkdir(parents=True)
                if cycles_kind == "symlink":
                    (base / "vault").mkdir()
                    (proj / "seo" / "cycles").symlink_to(base / "vault", target_is_directory=True)

                def configure(project: pathlib.Path, base: pathlib.Path = base) -> None:
                    root = base / "alias" / project.name / "seo" / "cycles"
                    (project / "seo-cycle.yaml").write_text(
                        template.replace('cycles_root: "./seo/cycles"', f'cycles_root: "{root}"'),
                        encoding="utf-8")

                def cs(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
                    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                                          text=True, capture_output=True, check=False)

                configure(proj)
                init = cs(proj, "init", "--topic", "topic")
                self.assertEqual(init.returncode, 0, init.stderr)
                cdir = next((proj / "seo" / "cycles").glob("topic-*"))
                rel = f"seo/cycles/{cdir.name}"
                state = json.loads((cdir / "_state.json").read_text(encoding="utf-8"))
                self.assertEqual(state["cycle_dir"], rel)
                (cdir / "00-discovery.md").write_text("# discovery\n", encoding="utf-8")
                self.assertEqual(cs(proj, "set", "discovery", "--status", "done", "--dir", rel).returncode, 0)
                self.assertEqual(cs(proj, "gate", "discovery", "--dir", rel).returncode, 0)
                moved = base / "p-moved"
                proj.rename(moved)
                configure(moved)
                gate = cs(moved, "gate", "discovery", "--dir", rel)
                self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)

    def test_printed_commands_run_as_printed(self) -> None:
        """QA2 3.0.1 #6: the dry-run «Записать:» hint and the «Подтвердить
        фазу» hint are shell-quoted, so a two-word topic runs as printed."""
        import shlex

        self.legacy_layout()
        dry = self.run_cs("import", "минеральная вата")
        line = next(ln for ln in dry.stdout.splitlines() if "Записать:" in ln)
        argv = shlex.split(line.split("Записать:", 1)[1])
        self.assertEqual(argv[:3], ["seo-cycle", "cycle", "import"])
        wrote = self.run_cs(*argv[2:])
        self.assertEqual(wrote.returncode, 0, wrote.stderr)
        self.assertTrue((self.tmp / "seo" / "cycles" / "mineralnaya-vata" / "_state.json").exists())
        # «Подтвердить фазу» with a --dir that contains a space.
        spaced = self.run_cs("import", "x", "--dir", "seo/cycles/with space", "--write")
        self.assertEqual(spaced.returncode, 0, spaced.stderr)
        hint = next(ln for ln in spaced.stdout.splitlines() if "Подтвердить фазу:" in ln)
        argv = shlex.split(hint.split("Подтвердить фазу:", 1)[1].replace("<фаза>", "discovery"))
        self.assertEqual(argv[-2:], ["--dir", "seo/cycles/with space"])
        # The dry-run hint keeps the non-default --dir, so it writes where it showed.
        dry_dir = self.run_cs("import", "y z", "--dir", "seo/cycles/other place")
        line = next(ln for ln in dry_dir.stdout.splitlines() if "Записать:" in ln)
        argv = shlex.split(line.split("Записать:", 1)[1])
        self.assertEqual(self.run_cs(*argv[2:]).returncode, 0)
        self.assertTrue((self.tmp / "seo" / "cycles" / "other place" / "_state.json").exists())

    def test_broken_config_falls_back_silently(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text("a: [\n", encoding="utf-8")
        proc = self.run_cs("init", "--topic", "x")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertIn("seo/cycles/x-", proc.stdout)

    def test_journey_does_not_count_imported_phases(self) -> None:
        """T-184: `done` without `gate_passed` never closes a journey stage."""
        self.legacy_layout()
        self.assertEqual(self.run_cs("import", "legacy-main", "--write").returncode, 0)
        phases = journey.read_cycle_phases({}, self.tmp)
        self.assertIn("keywords", phases)
        self.assertFalse(any(info["closed"] for info in phases.values()))
        self.assertEqual(journey.stage_closed_by_cycle("research_architecture", phases), [])
        gate = self.run_cs("gate", "keywords", "--dir", "seo/cycles/legacy-main")
        self.assertEqual(gate.returncode, 0)
        self.assertTrue(journey.read_cycle_phases({}, self.tmp)["keywords"]["closed"])


if __name__ == "__main__":
    unittest.main()
