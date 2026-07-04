#!/usr/bin/env python3
"""Tests for v1.85 delivery/analytics: notify --file, cohorts, overlap, citations, schedule."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_tool(cwd: pathlib.Path, name: str, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("TELEGRAM")}
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args],
                          cwd=cwd, env=env, text=True, capture_output=True, check=False)


class NotifyFileTest(unittest.TestCase):
    def test_file_flag_noop_without_token(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-notify-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        report = tmp / "r.md"
        report.write_text("# x\n", encoding="utf-8")
        proc = run_tool(tmp, "notify.py", "отчёт", "--file", str(report))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("telegram не настроен", proc.stdout)
        self.assertIn("r.md", proc.stdout)


class MetrikaCohortsTest(unittest.TestCase):
    def test_cohorts_from_tsv(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-cohorts-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text("project:\n  name: c\n", encoding="utf-8")
        tsv = tmp / "visits.tsv"
        rows = [
            "ym:s:clientID\tym:s:date\tym:s:goalsID\tym:s:lastTrafficSource",
            "c1\t2026-06-01\t[]\torganic",       # когорта 2026-06-01 (пн)
            "c1\t2026-06-10\t[123]\torganic",    # вернулся + конверсия
            "c2\t2026-06-03\t[]\tdirect",        # та же когорта, 1 визит
            "c3\t2026-06-09\t[55]\torganic",     # когорта 2026-06-08
        ]
        tsv.write_text("\n".join(rows) + "\n", encoding="utf-8")
        proc = run_tool(tmp, "metrika-cohorts.py", "--input-file", str(tsv), "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["unique_clients"], 3)
        first = report["cohorts"][0]
        self.assertEqual(first["cohort_week"], "2026-06-01")
        self.assertEqual(first["clients"], 2)
        self.assertEqual(first["returned_share"], 0.5)   # вернулся только c1
        self.assertEqual(first["converted_share"], 0.5)
        second = report["cohorts"][1]
        self.assertEqual(second["cohort_week"], "2026-06-08")
        self.assertEqual(second["converted_share"], 1.0)


class PortfolioOverlapTest(unittest.TestCase):
    def seed(self, root: pathlib.Path, url: str) -> None:
        (root / "seo-cycle.yaml").write_text("project:\n  name: p\n", encoding="utf-8")
        db = root / "seo" / "seo.db"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE positions (snapshot_date TEXT, engine TEXT, query TEXT,
                        position REAL, clicks INTEGER, impressions INTEGER, url TEXT)""")
        conn.execute("INSERT INTO positions VALUES ('2026-07-01','yandex','общий запрос',?,5,100,?)",
                     (3.0 if "one" in url else 12.0, url))
        conn.execute("INSERT INTO positions VALUES ('2026-07-01','yandex','уникальный '||?,7.0,1,10,?)",
                     (url, url))
        conn.commit()
        conn.close()

    def test_cross_project_overlap_detected(self) -> None:
        one = pathlib.Path(tempfile.mkdtemp(prefix="seo-ovl-one-"))
        two = pathlib.Path(tempfile.mkdtemp(prefix="seo-ovl-two-"))
        for root, url in ((one, "/one/"), (two, "/two/")):
            self.addCleanup(lambda r=root: shutil.rmtree(r, ignore_errors=True))
            self.seed(root, url)
        registry = one / "registry.yaml"
        registry.write_text(
            f"projects:\n  - name: Один\n    path: \"{one}\"\n  - name: Два\n    path: \"{two}\"\n",
            encoding="utf-8")
        proc = run_tool(one, "position-progress.py", "--global", "--registry", str(registry),
                        "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        portfolio = json.loads(proc.stdout)
        overlaps = portfolio["cross_project_overlap"]
        self.assertEqual(len(overlaps), 1)
        self.assertEqual(overlaps[0]["query"], "общий запрос")
        self.assertEqual(overlaps[0]["projects"][0]["project"], "Один")  # лучшая позиция первой
        markdown = run_tool(one, "position-progress.py", "--global", "--registry", str(registry)).stdout
        self.assertIn("Пересечения проектов", markdown)


class GeoCitationLogTest(unittest.TestCase):
    def test_record_and_trend(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-geocit-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text("project:\n  name: g\n", encoding="utf-8")
        run_tool(tmp, "geo-citation-log.py", "--record", "--engine", "perplexity",
                 "--query", "лучшая вагонка", "--cited")
        run_tool(tmp, "geo-citation-log.py", "--record", "--engine", "perplexity",
                 "--query", "вагонка обзор", "--not-cited")
        proc = run_tool(tmp, "geo-citation-log.py", "--format", "json")
        report = json.loads(proc.stdout)
        self.assertEqual(report["observations"], 2)
        month = report["months"][0]["engines"]["perplexity"]
        self.assertEqual(month["checks"], 2)
        self.assertEqual(month["share"], 0.5)

    def test_import_audit_shapes(self) -> None:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-geocit2-"))
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "seo-cycle.yaml").write_text("project:\n  name: g\n", encoding="utf-8")
        audit = tmp / "audit.json"
        audit.write_text(json.dumps({"results": [
            {"query": "q1", "engine": "chatgpt", "brand_mentioned": True},
            {"query": "q2", "platform": "ai_overview", "cited": False},
        ]}), encoding="utf-8")
        proc = run_tool(tmp, "geo-citation-log.py", "--import-audit", str(audit), "--format", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["observations"], 2)


class ScheduleInstallerTest(unittest.TestCase):
    def test_linux_mode_prints_crontab(self) -> None:
        proc = subprocess.run(
            ["bash", "-c", f"uname() {{ echo Linux; }}; export -f uname; "
             f"bash '{SCRIPTS}/install-schedule.sh' --project /tmp/x --with-monthly"],
            text=True, capture_output=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("crontab", proc.stdout)
        self.assertIn("progress --global", proc.stdout)
        self.assertIn("run monthly", proc.stdout)


if __name__ == "__main__":
    unittest.main()
