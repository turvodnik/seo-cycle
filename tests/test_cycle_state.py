#!/usr/bin/env python3
"""Tests for scripts/cycle-state.py (T-102).

Orchestration of the SEO cycle DAG (init/set/gate/next/show) had zero test
coverage before this ticket. The gate criterion itself (file/dir non-empty)
is intentionally NOT changed here — that is a separate L-spec item; this
file only pins down current behavior so a future change is visible as a
diff, not a silent regression.

All commands run as a subprocess (not imported), same as the real CLI.
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


class CycleStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cycle-state-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def run_cs(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
        )

    def init_cycle(self, cycle_dir: str = "cycle") -> pathlib.Path:
        proc = self.run_cs("init", "--topic", "минеральная вата", "--dir", cycle_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return self.tmp / cycle_dir

    # -- init -------------------------------------------------------------

    def test_init_creates_state_json_with_all_phases(self) -> None:
        cdir = self.init_cycle()
        state_path = cdir / "_state.json"
        self.assertTrue(state_path.exists())
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["topic"], "минеральная вата")
        expected_phases = {
            "discovery", "audit", "keywords", "clusters", "entity_map",
            "content_plan", "writing", "publishing", "schema", "monitoring", "iteration",
        }
        self.assertEqual(set(state["phases"]), expected_phases)
        # discovery has no deps -> pending; everything else blocked initially.
        self.assertEqual(state["phases"]["discovery"]["status"], "pending")
        self.assertEqual(state["phases"]["audit"]["status"], "blocked")

    def test_init_on_existing_dir_recreates_state(self) -> None:
        # Documents current behavior: a second init on the same --dir does
        # not refuse and overwrites _state.json (no merge, no error).
        cdir = self.init_cycle()
        state_path = cdir / "_state.json"
        # Mutate state, then re-init on the same dir.
        set_proc = self.run_cs("set", "keywords", "--status", "done", "--dir", str(cdir))
        self.assertEqual(set_proc.returncode, 0, set_proc.stderr)
        mutated = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(mutated["phases"]["keywords"]["status"], "done", "set must actually apply before re-init")

        proc = self.run_cs("init", "--topic", "минеральная вата", "--dir", str(cdir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        # Fresh state -> earlier mutation is gone (overwritten, not merged).
        self.assertEqual(state["phases"]["keywords"]["status"], "blocked")

    # -- set ----------------------------------------------------------------

    def test_set_changes_status_and_output(self) -> None:
        cdir = self.init_cycle()
        proc = self.run_cs("set", "discovery", "--status", "done", "--output", "00-discovery.md",
                            "--gate-passed", "--dir", str(cdir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        state = json.loads((cdir / "_state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["phases"]["discovery"]["status"], "done")
        self.assertEqual(state["phases"]["discovery"]["output"], "00-discovery.md")
        self.assertTrue(state["phases"]["discovery"]["gate_passed"])
        # audit depends only on discovery(done+gate) -> unblocked to pending.
        self.assertEqual(state["phases"]["audit"]["status"], "pending")

    def test_set_unknown_phase_fails_clearly(self) -> None:
        cdir = self.init_cycle()
        proc = self.run_cs("set", "not_a_phase", "--status", "done", "--dir", str(cdir))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("неизвестная фаза", proc.stderr)

    # -- gate -----------------------------------------------------------------

    def test_gate_on_missing_output_fails(self) -> None:
        cdir = self.init_cycle()
        self.run_cs("set", "discovery", "--output", "00-discovery.md", "--dir", str(cdir))
        # Output file does not exist yet.
        proc = self.run_cs("gate", "discovery", "--dir", str(cdir))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL", proc.stdout)
        state = json.loads((cdir / "_state.json").read_text(encoding="utf-8"))
        self.assertFalse(state["phases"]["discovery"]["gate_passed"])

    def test_gate_on_zero_byte_output_fails(self) -> None:
        # "Пустой выход" per the ticket: an existing but empty (0-byte) file
        # must fail the gate too, not just a missing one.
        cdir = self.init_cycle()
        self.run_cs("set", "discovery", "--output", "00-discovery.md", "--dir", str(cdir))
        (cdir / "00-discovery.md").write_text("", encoding="utf-8")
        proc = self.run_cs("gate", "discovery", "--dir", str(cdir))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL", proc.stdout)
        state = json.loads((cdir / "_state.json").read_text(encoding="utf-8"))
        self.assertFalse(state["phases"]["discovery"]["gate_passed"])

    def test_gate_on_empty_directory_output_fails(self) -> None:
        cdir = self.init_cycle()
        self.run_cs("set", "writing", "--output", "06-drafts/", "--dir", str(cdir))
        (cdir / "06-drafts").mkdir()
        proc = self.run_cs("gate", "writing", "--dir", str(cdir))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL", proc.stdout)

    def test_gate_on_nonempty_file_passes_and_records_gate_passed(self) -> None:
        cdir = self.init_cycle()
        self.run_cs("set", "discovery", "--output", "00-discovery.md", "--dir", str(cdir))
        (cdir / "00-discovery.md").write_text("# Discovery\n\nSome content.\n", encoding="utf-8")
        proc = self.run_cs("gate", "discovery", "--dir", str(cdir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PASS", proc.stdout)
        state = json.loads((cdir / "_state.json").read_text(encoding="utf-8"))
        self.assertTrue(state["phases"]["discovery"]["gate_passed"])

    def test_gate_unknown_phase_fails_clearly(self) -> None:
        cdir = self.init_cycle()
        proc = self.run_cs("gate", "not_a_phase", "--dir", str(cdir))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("неизвестная фаза", proc.stderr)

    # -- next -----------------------------------------------------------------

    def test_next_respects_depends_on(self) -> None:
        cdir = self.init_cycle()
        proc = self.run_cs("next", "--dir", str(cdir), "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        ready = json.loads(proc.stdout)
        self.assertEqual(ready, ["discovery"])

        self.run_cs("set", "discovery", "--output", "00-discovery.md", "--dir", str(cdir))
        (cdir / "00-discovery.md").write_text("content", encoding="utf-8")
        self.run_cs("set", "discovery", "--status", "done", "--dir", str(cdir))
        self.run_cs("gate", "discovery", "--dir", str(cdir))

        proc = self.run_cs("next", "--dir", str(cdir), "--json")
        ready = json.loads(proc.stdout)
        self.assertEqual(ready, ["audit"])

    # -- show -----------------------------------------------------------------

    def test_show_runs_and_lists_topic_and_ready(self) -> None:
        cdir = self.init_cycle()
        proc = self.run_cs("show", "--dir", str(cdir))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("минеральная вата", proc.stdout)
        self.assertIn("discovery", proc.stdout)
        self.assertIn("READY", proc.stdout)


if __name__ == "__main__":
    unittest.main()
