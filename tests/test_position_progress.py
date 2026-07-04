#!/usr/bin/env python3
"""Tests for position-progress.py (per-project deltas, movers, portfolio)."""

from __future__ import annotations

import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

CFG = "project:\n  name: progress-test\n  domain: example.ru\n"


def seed_project(root: pathlib.Path, *, snapshots: bool = True) -> None:
    (root / "seo-cycle.yaml").write_text(CFG, encoding="utf-8")
    db = root / "seo" / "seo.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE positions (snapshot_date TEXT, engine TEXT, query TEXT,
                    position REAL, clicks INTEGER, impressions INTEGER, url TEXT)""")
    if snapshots:
        rows = [
            # первый срез
            ("2026-06-01", "yandex", "купить вагонку", 12.0, 5, 400, "/vagonka/"),
            ("2026-06-01", "yandex", "вагонка штиль", 25.0, 1, 100, "/shtil/"),
            ("2026-06-01", "yandex", "вагонка цена", 8.0, 10, 300, "/price/"),
            # второй срез: рост, просадка, новый, потерянный
            ("2026-07-01", "yandex", "купить вагонку", 3.0, 40, 900, "/vagonka/"),   # improved 12→3
            ("2026-07-01", "yandex", "вагонка штиль", 31.0, 0, 80, "/shtil/"),        # declined 25→31
            ("2026-07-01", "yandex", "вагонка из кедра", 9.0, 6, 200, "/kedr/"),      # new
            # "вагонка цена" выпала → lost
        ]
        conn.executemany("INSERT INTO positions VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def seed_loop_journal(root: pathlib.Path) -> None:
    loops = root / "seo" / "loops"
    loops.mkdir(parents=True, exist_ok=True)
    state = {
        "loop_id": "draft--x-abc123",
        "target": "draft",
        "status": "passed",
        "attempts": [
            {"n": 1, "check": {"findings": [{"severity": "error", "id": "a"}, {"severity": "error", "id": "b"}]},
             "delta": {"resolved": [], "new": ["error:a", "error:b"], "unchanged": []}},
            {"n": 2, "check": {"findings": []},
             "delta": {"resolved": ["error:a", "error:b"], "new": [], "unchanged": []}},
        ],
    }
    (loops / "draft--x-abc123.json").write_text(json.dumps(state), encoding="utf-8")


def run_progress(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "position-progress.py"), *args],
        cwd=cwd, text=True, capture_output=True, check=False,
    )


class PositionProgressTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-progress-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        seed_project(self.tmp)
        seed_loop_journal(self.tmp)

    def test_deltas_movers_and_loops_digest(self) -> None:
        proc = run_progress(self.tmp, "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["latest"]["top3"], 1)
        self.assertEqual(report["latest"]["top10"], 2)
        self.assertEqual(report["delta_vs_previous"]["top10"], 1)   # июнь: только «цена» ≤10; июль: вагонка+кедр
        self.assertEqual(report["delta_vs_previous"]["clicks"], 46 - 16)
        movers = report["movers"]
        self.assertEqual(movers["improved"][0]["query"], "купить вагонку")
        self.assertEqual(movers["declined"][0]["query"], "вагонка штиль")
        self.assertEqual([row["query"] for row in movers["new"]], ["вагонка из кедра"])
        self.assertEqual([row["query"] for row in movers["lost"]], ["вагонка цена"])
        loops = report["loops"]
        self.assertEqual(loops["loops"], 1)
        self.assertEqual(loops["findings_resolved"], 2)
        self.assertEqual(loops["findings_open"], 0)

    def test_markdown_and_html_write(self) -> None:
        proc = run_progress(self.tmp, "--write", "--html")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Топ-10: 2", proc.stdout)
        self.assertIn("Циклы качества", proc.stdout)
        html_path = self.tmp / "seo" / "reports" / "position-progress.html"
        self.assertTrue(html_path.exists())
        body = html_path.read_text(encoding="utf-8")
        self.assertIn("bar-row", body)  # визуальные бары по срезам
        self.assertIn("Топ-10 по срезам", body)

    def test_no_snapshots_is_graceful(self) -> None:
        empty = pathlib.Path(tempfile.mkdtemp(prefix="seo-progress-empty-"))
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))
        seed_project(empty, snapshots=False)
        proc = run_progress(empty, "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "no_snapshots")

    def test_portfolio_global(self) -> None:
        second = pathlib.Path(tempfile.mkdtemp(prefix="seo-progress-p2-"))
        self.addCleanup(lambda: shutil.rmtree(second, ignore_errors=True))
        seed_project(second)
        registry = self.tmp / "registry.yaml"
        registry.write_text(
            "projects:\n"
            f"  - name: Первый\n    path: \"{self.tmp}\"\n    status: active\n"
            f"  - name: Второй\n    path: \"{second}\"\n    status: active\n",
            encoding="utf-8",
        )
        proc = run_progress(self.tmp, "--global", "--registry", str(registry), "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        portfolio = json.loads(proc.stdout)
        self.assertEqual(portfolio["totals"]["projects"], 2)
        self.assertEqual(portfolio["totals"]["top10"], 4)
        self.assertEqual(len(portfolio["projects"]), 2)
        markdown = run_progress(self.tmp, "--global", "--registry", str(registry)).stdout
        self.assertIn("Портфель", markdown)
        self.assertIn("Первый", markdown)


if __name__ == "__main__":
    unittest.main()
