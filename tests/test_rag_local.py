#!/usr/bin/env python3
"""Tests for the local RAG layer (seo_cycle_core/rag.py + rag-index.py + rag-query.py)."""

from __future__ import annotations

import json
import pathlib
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from seo_cycle_core.rag import (  # noqa: E402
    chunk_text,
    cosine,
    index_project,
    index_stats,
    open_db,
    search,
)

FTS5_AVAILABLE = True
try:
    _conn = sqlite3.connect(":memory:")
    _conn.execute("CREATE VIRTUAL TABLE _t USING fts5(text)")
    _conn.close()
except sqlite3.OperationalError:  # pragma: no cover
    FTS5_AVAILABLE = False

CFG: dict = {"rag": {"chunk_chars": 300, "chunk_overlap": 50}}


def pack_vector(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


class ChunkingTest(unittest.TestCase):
    def test_short_text_is_single_chunk(self) -> None:
        self.assertEqual(chunk_text("короткий текст"), ["короткий текст"])

    def test_long_text_splits_with_overlap(self) -> None:
        text = "\n".join(f"строка номер {index} про монтаж вагонки" for index in range(60))
        chunks = chunk_text(text, max_chars=300, overlap=50)
        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(len(chunk) <= 300 for chunk in chunks))

    def test_cosine(self) -> None:
        a = pack_vector([1.0, 0.0])
        b = pack_vector([0.0, 1.0])
        self.assertAlmostEqual(cosine(a, a), 1.0, places=5)
        self.assertAlmostEqual(cosine(a, b), 0.0, places=5)


@unittest.skipUnless(FTS5_AVAILABLE, "sqlite3 built without FTS5")
class RagIndexSearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-rag-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.seed_project(self.tmp)
        self.db = open_db(self.tmp / "seo" / "rag.db")
        self.addCleanup(self.db.close)

    def seed_project(self, root: pathlib.Path) -> None:
        vector = root / "seo" / "research" / "vector"
        vector.mkdir(parents=True)
        (vector / "source_pack.jsonl").write_text(
            json.dumps({"record_type": "source_pack", "provider": "perplexity",
                        "topic": "вагонка из кедра",
                        "summary": "Кедровая вагонка устойчива к влаге и подходит для бани.",
                        "citations": ["https://example.com/kedr"]}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        distillates = root / "seo" / "research" / "distillates"
        distillates.mkdir(parents=True)
        (distillates / "montazh.md").write_text(
            "# Монтаж\n\nКляймеры — скрытый крепёж для вагонки; шаг обрешётки 50 см.",
            encoding="utf-8",
        )
        drafts = root / "seo" / "research-package" / "drafts"
        drafts.mkdir(parents=True)
        (drafts / "vagonka.md").write_text("# Вагонка\n\nЧерновик про сорта вагонки: экстра, А, B.",
                                           encoding="utf-8")
        (drafts / "vagonka.draft-quality-gate.md").write_text("gate", encoding="utf-8")
        triplets = root / "seo" / "research-package" / "vector"
        triplets.mkdir(parents=True)
        (triplets / "page_outline_triplets.jsonl").write_text(
            json.dumps({"provider": "page_outline_v3", "page_url": "/catalog/vagonka/",
                        "page_primary_keyword": "купить вагонку", "section": "Крепёж",
                        "raw": "вагонка -> крепится -> кляймерами",
                        "subject": "вагонка", "predicate": "крепится", "object": "кляймерами"},
                       ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def test_index_and_bm25_search_russian(self) -> None:
        stats = index_project(self.db, self.tmp, CFG, "test-project")
        self.assertEqual(stats["indexed_files"], 4)
        self.assertGreaterEqual(stats["chunks"], 4)
        self.assertEqual(stats["embedded_chunks"], 0)

        hits = search(self.db, "кляймеры крепёж", top_k=5)
        self.assertTrue(hits)
        self.assertIn(hits[0]["source_type"], {"distillate", "triplet"})
        self.assertIn("кляймер", hits[0]["text"].lower())

    def test_quality_gate_reports_are_not_indexed(self) -> None:
        index_project(self.db, self.tmp, CFG, "test-project")
        paths = [row[0] for row in self.db.execute("SELECT DISTINCT path FROM chunks")]
        self.assertFalse(any("draft-quality-gate" in path for path in paths))

    def test_source_type_and_project_filters(self) -> None:
        index_project(self.db, self.tmp, CFG, "test-project")
        hits = search(self.db, "вагонка", top_k=10, source_types=["draft"])
        self.assertTrue(hits)
        self.assertTrue(all(hit["source_type"] == "draft" for hit in hits))
        self.assertFalse(search(self.db, "вагонка", top_k=10, project="another-project"))

    def test_incremental_reindex_touches_only_changed_files(self) -> None:
        first = index_project(self.db, self.tmp, CFG, "test-project")
        self.assertEqual(first["indexed_files"], 4)
        second = index_project(self.db, self.tmp, CFG, "test-project")
        self.assertEqual(second["indexed_files"], 0)
        self.assertEqual(second["skipped_files"], 4)
        draft = self.tmp / "seo" / "research-package" / "drafts" / "vagonka.md"
        draft.write_text("# Вагонка\n\nОбновлённый черновик про липу и осину.", encoding="utf-8")
        third = index_project(self.db, self.tmp, CFG, "test-project")
        self.assertEqual(third["indexed_files"], 1)
        hits = search(self.db, "осину", top_k=3)
        self.assertTrue(hits and hits[0]["source_type"] == "draft")

    def test_deleted_files_are_purged(self) -> None:
        index_project(self.db, self.tmp, CFG, "test-project")
        (self.tmp / "seo" / "research-package" / "drafts" / "vagonka.md").unlink()
        stats = index_project(self.db, self.tmp, CFG, "test-project")
        self.assertEqual(stats["removed_files"], 1)
        self.assertFalse(search(self.db, "сорта", top_k=3, source_types=["draft"]))

    def test_injected_embeddings_enable_rerank_storage(self) -> None:
        def fake_embed(texts: list[str]) -> list[bytes]:
            return [pack_vector([float(len(text) % 7), 1.0, 0.5]) for text in texts]

        stats = index_project(self.db, self.tmp, CFG, "test-project", embed="required",
                              embed_fn=fake_embed)
        self.assertEqual(stats["embedded_chunks"], stats["chunks"])
        self.assertEqual(index_stats(self.db)["embedded"], stats["chunks"])

    def test_global_mode_multiple_projects_in_one_db(self) -> None:
        other = pathlib.Path(tempfile.mkdtemp(prefix="seo-rag-other-"))
        self.addCleanup(lambda: shutil.rmtree(other, ignore_errors=True))
        self.seed_project(other)
        index_project(self.db, self.tmp, CFG, "project-a")
        index_project(self.db, other, CFG, "project-b")
        stats = index_stats(self.db)
        self.assertEqual(stats["projects"], 2)
        hits = search(self.db, "кляймеры", top_k=10, project="project-b")
        self.assertTrue(all(hit["project"] == "project-b" for hit in hits))


@unittest.skipUnless(FTS5_AVAILABLE, "sqlite3 built without FTS5")
class RagCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="seo-rag-cli-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        (self.tmp / "seo-cycle.yaml").write_text("project:\n  name: rag-cli\n", encoding="utf-8")
        vector = self.tmp / "seo" / "research" / "vector"
        vector.mkdir(parents=True)
        (vector / "source_pack.jsonl").write_text(
            json.dumps({"topic": "вагонка", "summary": "Вагонка из кедра для бани.",
                        "provider": "perplexity"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def run_script(self, script: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=self.tmp,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_dry_run_then_write_then_query(self) -> None:
        dry = self.run_script("rag-index.py", "--format", "json")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertEqual(json.loads(dry.stdout)["mode"], "dry_run")
        self.assertFalse((self.tmp / "seo" / "rag.db").exists())

        write = self.run_script("rag-index.py", "--write", "--format", "json")
        self.assertEqual(write.returncode, 0, write.stderr)
        report = json.loads(write.stdout)
        self.assertGreaterEqual(report["stats"]["chunks"], 1)
        self.assertTrue((self.tmp / "seo" / "rag.db").exists())
        self.assertTrue((self.tmp / "seo" / "rag" / "rag-index.md").exists())

        query = self.run_script("rag-query.py", "вагонка кедр", "--format", "json")
        self.assertEqual(query.returncode, 0, query.stderr)
        hits = json.loads(query.stdout)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["source_type"], "source_pack")

    def test_query_without_index_is_graceful(self) -> None:
        proc = self.run_script("rag-query.py", "вагонка")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("rag-index", proc.stderr)


if __name__ == "__main__":
    unittest.main()
