#!/usr/bin/env python3
"""Tests for the unified seo-cycle CLI dispatcher."""

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
LAUNCHER = ROOT / "bin" / "seo-cycle"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_cli import ADS_FETCH, ADS_HEALTH, ADS_SCRIPTS, COMMANDS, DOCTOR_STEPS, GATE_SCRIPTS  # noqa: E402


class CliTableTest(unittest.TestCase):
    def test_every_mapping_points_to_an_existing_script(self) -> None:
        for name, spec in COMMANDS.items():
            self.assertTrue((SCRIPTS / spec["script"]).exists(), f"{name} -> {spec['script']} missing")
        for name, script in GATE_SCRIPTS.items():
            self.assertTrue((SCRIPTS / script).exists(), f"gate {name} -> {script} missing")
        for label, script, _ in DOCTOR_STEPS:
            self.assertTrue((SCRIPTS / script).exists(), f"doctor {label} -> {script} missing")
        for name, script in ADS_SCRIPTS.items():
            if script:
                self.assertTrue((SCRIPTS / script).exists(), f"ads {name} -> {script} missing")
        for name, script in ADS_FETCH.items():
            self.assertTrue((SCRIPTS / script).exists(), f"ads fetch {name} -> {script} missing")
        for script in ADS_HEALTH:
            self.assertTrue((SCRIPTS / script).exists(), f"ads health {script} missing")

    def test_launcher_exists_and_is_executable(self) -> None:
        self.assertTrue(LAUNCHER.exists())
        self.assertTrue(LAUNCHER.stat().st_mode & 0o111, "bin/seo-cycle must be executable")


class CliDispatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cli-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def run_cli(self, *args: str, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(LAUNCHER), *args],
            cwd=cwd or self.tmp,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_help_lists_all_commands(self) -> None:
        proc = self.run_cli("--help")
        self.assertEqual(proc.returncode, 0)
        for name in [*COMMANDS, "gate", "run", "doctor", "version"]:
            self.assertIn(name, proc.stdout)

    def test_version_matches_version_file(self) -> None:
        proc = self.run_cli("version")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), (ROOT / "VERSION").read_text(encoding="utf-8").strip())

    def test_unknown_command_fails_clearly(self) -> None:
        proc = self.run_cli("frobnicate")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown command", proc.stderr)

    def test_gate_draft_is_equivalent_to_direct_script(self) -> None:
        outline = self.tmp / "outline.json"
        outline.write_text(json.dumps({"sections": [], "internal_links": [], "faq": []}), encoding="utf-8")
        draft = self.tmp / "draft.md"
        draft.write_text("# Пост\n\nТекст. Source: https://example.com\n", encoding="utf-8")
        via_cli = self.run_cli("gate", "draft", str(draft), "--outline", str(outline), "--format", "json")
        direct = subprocess.run(
            [sys.executable, str(SCRIPTS / "draft-quality-gate.py"), str(draft), "--outline", str(outline), "--format", "json"],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(via_cli.returncode, direct.returncode)
        self.assertEqual(json.loads(via_cli.stdout)["findings"], json.loads(direct.stdout)["findings"])

    def test_doctor_survives_empty_project_without_traceback(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: cli-doctor\n", encoding="utf-8")
        proc = self.run_cli("doctor")
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("seo-cycle doctor", proc.stdout)
        self.assertIn("config:", proc.stdout)

    def test_project_flag_switches_cwd(self) -> None:
        other = self.tmp / "proj"
        other.mkdir()
        (other / "seo-cycle.yaml").write_text("project:\n  name: other\n", encoding="utf-8")
        proc = self.run_cli("--project", str(other), "validate", cwd=self.tmp)
        self.assertNotIn("Traceback", proc.stderr)

    def _write_snapshot(self, age_days: int) -> None:
        import os
        import time
        snap = self.tmp / "seo" / "monitoring" / "webmaster-snapshot-2026-01-01.json"
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text("{}", encoding="utf-8")
        stamp = time.time() - age_days * 86400
        os.utime(snap, (stamp, stamp))

    def test_doctor_prints_numeric_threshold_and_agy_line(self) -> None:
        # T-052 (C7): --help promised "fails on stale snapshots" but never named
        # the threshold, and doctor never mentioned whether `agy` (Antigravity,
        # mandatory for Phase 2) was even installed.
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: cli-doctor\n", encoding="utf-8")
        self._write_snapshot(age_days=1)
        proc = self.run_cli("doctor")
        # config-шаг требует governance-секцию, которой в минимальной фикстуре
        # нет — это уже существующее (не T-052) поведение validate-config.py,
        # поэтому здесь мы не утверждаем итоговый rc, только конкретные строки.
        self.assertIn("порог 7", proc.stdout, proc.stdout + proc.stderr)
        self.assertIn("agy:", proc.stdout)
        self.assertIn("perplexity-key:", proc.stdout)

    def test_doctor_honors_configured_snapshot_max_age(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  name: cli-doctor\nmonitoring:\n  snapshot_max_age_days: 2\n", encoding="utf-8")
        self._write_snapshot(age_days=5)
        proc = self.run_cli("doctor")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("ПРОСРОЧЕН", proc.stdout)
        self.assertIn("порог 2", proc.stdout)

    def test_status_without_config_errors_before_header(self) -> None:
        # T-052: раньше status печатал шапку («снапшот: нет», «triggers не
        # строился») ДО того, как обнаруживал отсутствие конфига — читалось
        # как реальное состояние проекта, а не как «проекта тут вообще нет».
        proc = self.run_cli("status")
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("seo-cycle status", proc.stdout)
        self.assertNotIn("снапшот", proc.stdout)
        self.assertIn("ERROR: seo-cycle.yaml not found", proc.stderr)


if __name__ == "__main__":
    unittest.main()
