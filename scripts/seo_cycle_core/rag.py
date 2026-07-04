"""Local RAG layer: SQLite FTS5 (BM25) by default, optional embedding rerank.

Zero external dependencies: the index lives in `seo/rag.db` (config
`data_store.rag_path`), full-text search uses the FTS5 module bundled with
Python's sqlite3, and Russian works via the unicode61 tokenizer. When
`EMBEDDING_API_URL/KEY/MODEL` point to an OpenAI-compatible `/embeddings`
endpoint, chunks are additionally embedded (BLOB via struct, no numpy) and
queries run hybrid: FTS5 prefilter → cosine rerank in pure Python.

Cross-project mode: the same schema in `~/.seo-cycle/rag/global.db`, one
`project` value per registry entry.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import sqlite3
import struct
import urllib.request
from typing import Any, Iterator

from .config import nested_get

DEFAULT_CHUNK_CHARS = 1200
DEFAULT_CHUNK_OVERLAP = 150
DEFAULT_SOURCES = ("source_pack", "triplet", "distillate", "draft", "mirror")
FTS_PREFILTER = 200
GLOBAL_DB = pathlib.Path.home() / ".seo-cycle" / "rag" / "global.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    project TEXT NOT NULL,
    source_type TEXT NOT NULL,
    path TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    mtime REAL,
    content_hash TEXT,
    embedding BLOB,
    embedding_model TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS chunks_key ON chunks(project, path, chunk_index);
CREATE TABLE IF NOT EXISTS files (
    project TEXT NOT NULL,
    path TEXT NOT NULL,
    mtime REAL,
    content_hash TEXT,
    chunk_count INTEGER,
    PRIMARY KEY (project, path)
);
"""


def rag_db_path(project_root: pathlib.Path, cfg: dict[str, Any]) -> pathlib.Path:
    rel = nested_get(cfg, "data_store.rag_path", "seo/rag.db") or "seo/rag.db"
    path = pathlib.Path(rel).expanduser()
    return path if path.is_absolute() else project_root / path


class RagConnection(sqlite3.Connection):
    """sqlite3.Connection subclass so we can carry the fts5_enabled flag (3.14-safe)."""

    fts5_enabled = False


def open_db(path: pathlib.Path | str) -> RagConnection:
    if str(path) != ":memory:":
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), factory=RagConnection)
    conn.executescript(SCHEMA)
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
            "text, content='chunks', content_rowid='id', "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        conn.fts5_enabled = True
    except sqlite3.OperationalError:
        conn.fts5_enabled = False
    return conn


def chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_CHARS,
               overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            newline = text.rfind("\n", start + max_chars // 2, end)
            space = text.rfind(" ", start + max_chars // 2, end)
            cut = newline if newline > 0 else space
            if cut > start:
                end = cut
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def content_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def read_jsonl(path: pathlib.Path) -> Iterator[dict[str, Any]]:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row
    except OSError:
        return


def source_pack_chunks(path: pathlib.Path) -> list[tuple[str, dict[str, Any]]]:
    chunks = []
    for row in read_jsonl(path):
        summary = str(row.get("summary") or "").strip()
        if not summary:
            continue
        topic = str(row.get("topic") or "")
        text = f"{topic}: {summary}" if topic else summary
        chunks.append((text, {"provider": row.get("provider"), "topic": topic,
                              "citations": row.get("citations") or []}))
    return chunks


def triplet_chunks(path: pathlib.Path) -> list[tuple[str, dict[str, Any]]]:
    chunks = []
    for row in read_jsonl(path):
        raw = str(row.get("raw") or "").strip()
        if not raw:
            continue
        parts = [raw]
        if row.get("section"):
            parts.append(f"Раздел: {row['section']}")
        if row.get("page_primary_keyword"):
            parts.append(f"Страница: {row['page_primary_keyword']}")
        chunks.append((". ".join(parts), {"page_url": row.get("page_url"),
                                          "provider": row.get("provider")}))
    return chunks


def iter_project_documents(project_root: pathlib.Path, cfg: dict[str, Any]
                           ) -> Iterator[tuple[str, pathlib.Path, list[tuple[str, dict[str, Any]]]]]:
    """Yield (source_type, absolute_path, [(chunk_text, meta), ...]) per document."""
    sources = nested_get(cfg, "rag.sources", list(DEFAULT_SOURCES)) or list(DEFAULT_SOURCES)
    max_chars = int(nested_get(cfg, "rag.chunk_chars", DEFAULT_CHUNK_CHARS) or DEFAULT_CHUNK_CHARS)
    overlap = int(nested_get(cfg, "rag.chunk_overlap", DEFAULT_CHUNK_OVERLAP) or DEFAULT_CHUNK_OVERLAP)

    def md_chunks(path: pathlib.Path) -> list[tuple[str, dict[str, Any]]]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return []
        return [(chunk, {}) for chunk in chunk_text(text, max_chars, overlap)]

    if "source_pack" in sources:
        for path in sorted(project_root.glob("seo/research/vector/*.jsonl")):
            yield "source_pack", path, source_pack_chunks(path)
    if "triplet" in sources:
        for path in sorted(project_root.glob("seo/**/vector/page_outline_triplets.jsonl")):
            yield "triplet", path, triplet_chunks(path)
    if "distillate" in sources:
        for path in sorted(project_root.glob("seo/research/distillates/**/*.md")):
            yield "distillate", path, md_chunks(path)
    if "draft" in sources:
        seen: set[pathlib.Path] = set()
        for pattern in ("seo/research-package/drafts/*.md", "seo/research-package/copywriter-ready/*.md",
                        "seo/drafts/*.md", "06-drafts/*.md"):
            for path in sorted(project_root.glob(pattern)):
                if ".draft-quality-gate" in path.name or path in seen:
                    continue
                seen.add(path)
                yield "draft", path, md_chunks(path)
    if "mirror" in sources:
        for path in sorted(project_root.glob("seo/content-mirror/*/*.md")):
            yield "mirror", path, md_chunks(path)


def embedding_env() -> dict[str, str] | None:
    url = os.environ.get("EMBEDDING_API_URL", "").strip()
    model = os.environ.get("EMBEDDING_MODEL", "").strip()
    if not url or not model:
        return None
    return {"url": url.rstrip("/"), "model": model, "key": os.environ.get("EMBEDDING_API_KEY", "")}


def embed_texts(texts: list[str]) -> list[bytes] | None:
    """Call an OpenAI-compatible /embeddings endpoint; None when not configured."""
    env = embedding_env()
    if not env or not texts:
        return None
    endpoint = env["url"] if env["url"].endswith("/embeddings") else env["url"] + "/embeddings"
    headers = {"Content-Type": "application/json"}
    if env["key"]:
        headers["Authorization"] = f"Bearer {env['key']}"
    req = urllib.request.Request(endpoint, headers=headers,
                                 data=json.dumps({"model": env["model"], "input": texts}).encode("utf-8"))
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    vectors = [item.get("embedding") or [] for item in payload.get("data") or []]
    if len(vectors) != len(texts):
        return None
    return [struct.pack(f"<{len(vector)}f", *vector) for vector in vectors]


def unpack_vector(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))


def cosine(a: bytes, b: bytes) -> float:
    va, vb = unpack_vector(a), unpack_vector(b)
    if len(va) != len(vb) or not va:
        return 0.0
    dot = sum(x * y for x, y in zip(va, vb, strict=True))
    norm = math.sqrt(sum(x * x for x in va)) * math.sqrt(sum(y * y for y in vb))
    return dot / norm if norm else 0.0


def index_project(conn: sqlite3.Connection, project_root: pathlib.Path, cfg: dict[str, Any],
                  project: str, *, embed: str = "auto", dry_run: bool = False,
                  embed_fn=embed_texts) -> dict[str, Any]:
    """Incrementally index one project; returns per-source stats."""
    stats: dict[str, Any] = {"indexed_files": 0, "skipped_files": 0, "removed_files": 0,
                             "chunks": 0, "embedded_chunks": 0, "by_source": {}}
    want_embeddings = embed == "required" or (embed == "auto" and embedding_env() is not None)
    seen_paths: set[str] = set()
    for source_type, path, chunks in iter_project_documents(project_root, cfg):
        rel = str(path.relative_to(project_root)) if path.is_relative_to(project_root) else str(path)
        seen_paths.add(rel)
        text_blob = "\n".join(chunk for chunk, _ in chunks)
        digest = content_hash(text_blob)
        mtime = path.stat().st_mtime if path.exists() else 0.0
        row = conn.execute("SELECT content_hash FROM files WHERE project=? AND path=?",
                           (project, rel)).fetchone()
        if row and row[0] == digest:
            stats["skipped_files"] += 1
            continue
        stats["indexed_files"] += 1
        stats["by_source"][source_type] = stats["by_source"].get(source_type, 0) + 1
        if dry_run:
            stats["chunks"] += len(chunks)
            continue
        delete_document(conn, project, rel)
        embeddings: list[bytes] | None = None
        if want_embeddings and chunks:
            embeddings = embed_fn([chunk for chunk, _ in chunks])
            if embeddings is None and embed == "required":
                raise RuntimeError("embedding mode `required`, but EMBEDDING_API_* env is not configured")
        model = os.environ.get("EMBEDDING_MODEL", "") if embeddings else ""
        for index, (chunk, meta) in enumerate(chunks):
            blob = embeddings[index] if embeddings else None
            cursor = conn.execute(
                "INSERT INTO chunks(project, source_type, path, chunk_index, text, meta, mtime,"
                " content_hash, embedding, embedding_model) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (project, source_type, rel, index, chunk, json.dumps(meta, ensure_ascii=False),
                 mtime, digest, blob, model),
            )
            if getattr(conn, "fts5_enabled", False):
                conn.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                             (cursor.lastrowid, chunk))
            stats["chunks"] += 1
            if blob:
                stats["embedded_chunks"] += 1
        conn.execute("INSERT OR REPLACE INTO files(project, path, mtime, content_hash, chunk_count)"
                     " VALUES (?,?,?,?,?)", (project, rel, mtime, digest, len(chunks)))
    if not dry_run:
        stale = [row[0] for row in conn.execute("SELECT path FROM files WHERE project=?", (project,))
                 if row[0] not in seen_paths]
        for rel in stale:
            delete_document(conn, project, rel)
            conn.execute("DELETE FROM files WHERE project=? AND path=?", (project, rel))
            stats["removed_files"] += 1
        conn.commit()
    return stats


def delete_document(conn: sqlite3.Connection, project: str, rel: str) -> None:
    ids = [row[0] for row in conn.execute("SELECT id FROM chunks WHERE project=? AND path=?",
                                          (project, rel))]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    if getattr(conn, "fts5_enabled", False):
        conn.execute(f"DELETE FROM chunks_fts WHERE rowid IN ({placeholders})", ids)
    conn.execute(f"DELETE FROM chunks WHERE id IN ({placeholders})", ids)


def fts_query(query: str) -> str:
    """Turn free text into an OR-of-terms FTS5 query, quoting each token."""
    terms = [term.strip('"«».,!?:;()[]') for term in query.split()]
    terms = [term for term in terms if term]
    return " OR ".join(f'"{term}"' for term in terms) or '""'


def search(conn: sqlite3.Connection, query: str, *, top_k: int = 8,
           source_types: list[str] | None = None, project: str | None = None,
           mode: str = "auto") -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if source_types:
        filters.append(f"c.source_type IN ({','.join('?' for _ in source_types)})")
        params.extend(source_types)
    if project:
        filters.append("c.project = ?")
        params.append(project)
    where_extra = (" AND " + " AND ".join(filters)) if filters else ""

    if getattr(conn, "fts5_enabled", False):
        rows = conn.execute(
            f"SELECT c.id, c.project, c.source_type, c.path, c.text, c.meta, c.embedding,"
            f" bm25(chunks_fts) AS rank FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid"
            f" WHERE chunks_fts MATCH ?{where_extra} ORDER BY rank LIMIT ?",
            [fts_query(query), *params, FTS_PREFILTER],
        ).fetchall()
    else:  # degraded LIKE fallback (no FTS5 in this Python build)
        like = f"%{query.split()[0] if query.split() else query}%"
        rows = conn.execute(
            f"SELECT c.id, c.project, c.source_type, c.path, c.text, c.meta, c.embedding, 0"
            f" FROM chunks c WHERE c.text LIKE ?{where_extra} LIMIT ?",
            [like, *params, FTS_PREFILTER],
        ).fetchall()

    results = [
        {"id": row[0], "project": row[1], "source_type": row[2], "path": row[3],
         "text": row[4], "meta": json.loads(row[5] or "{}"), "_embedding": row[6],
         "score": round(-float(row[7]), 4)}
        for row in rows
    ]

    use_embeddings = mode in ("auto", "hybrid") and embedding_env() is not None
    if use_embeddings and any(item["_embedding"] for item in results):
        query_vectors = embed_texts([query])
        if query_vectors:
            for item in results:
                item["score"] = round(cosine(query_vectors[0], item["_embedding"]), 4) if item["_embedding"] else -1.0
            results.sort(key=lambda item: item["score"], reverse=True)
    for item in results:
        item.pop("_embedding", None)
    return results[:top_k]


def index_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    totals = conn.execute(
        "SELECT COUNT(*), COUNT(embedding), COUNT(DISTINCT project) FROM chunks"
    ).fetchone()
    by_source = dict(conn.execute("SELECT source_type, COUNT(*) FROM chunks GROUP BY source_type"))
    return {"chunks": totals[0], "embedded": totals[1], "projects": totals[2], "by_source": by_source}
