#!/usr/bin/env python3
"""Quarantined/invalid monitoring evidence must never re-enter seo.db."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import sqlite3
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("db_sync", ROOT / "scripts" / "db-sync.py")
db_sync = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(db_sync)


class DbSyncQuarantineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-db-quarantine-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def write_snapshot(self, relative: str, query: str, identity: dict | None = None) -> None:
        path = self.tmp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "snapshot_date": "2026-07-13",
            "engine": "yandex",
            "queries": [{"query": query, "position": 5, "clicks": 1, "impressions": 10}],
        }
        if identity is not None:
            payload["_identity"] = identity
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_path_components_quarantine_and_invalid_are_excluded(self) -> None:
        self.write_snapshot("seo/monitoring/webmaster-snapshot-2026-07-13.json", "gsse clean")
        self.write_snapshot("seo/monitoring/quarantine/yandex-snapshot-2026-07-12.json", "emwoody leaked")
        self.write_snapshot("seo/monitoring/archive/invalid/yandex-snapshot-2026-07-11.json", "invalid leaked")
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        inserted = db_sync.sync_positions(conn, self.tmp)
        queries = [row[0] for row in conn.execute("SELECT query FROM positions ORDER BY query")]

        self.assertEqual(inserted, 1)
        self.assertEqual(queries, ["gsse clean"])

    def test_foreign_snapshot_identity_is_excluded(self) -> None:
        (self.tmp / "seo-cycle.yaml").write_text(
            "project:\n  domain: gsse.ru\n",
            encoding="utf-8",
        )
        self.write_snapshot(
            "seo/monitoring/webmaster-snapshot-2026-07-13.json",
            "gsse clean",
            {"expected_domain": "gsse.ru", "selected_domain": "gsse.ru"},
        )
        self.write_snapshot(
            "seo/monitoring/webmaster-snapshot-2026-07-12.json",
            "emwoody leaked",
            {"expected_domain": "gsse.ru", "selected_domain": "emwoody.ru"},
        )
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)

        inserted = db_sync.sync_positions(conn, self.tmp)
        queries = [row[0] for row in conn.execute("SELECT query FROM positions ORDER BY query")]

        self.assertEqual(inserted, 1)
        self.assertEqual(queries, ["gsse clean"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
