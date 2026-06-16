#!/usr/bin/env python3
"""Build/search a local hybrid knowledge index.

The project plan is Wiki -> Graphify -> zvec. This pilot keeps the interface
stable today even when the `zvec` Python package is not installed: it writes a
plain JSONL corpus and a SQLite FTS index. When zvec is available, the status
records that it can be promoted to a native zvec collection without changing
the upstream wiki workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from wiki_common import HYBRID_INDEX_ROOT, ROOT, WIKI_ROOT, clean_text, ensure_wiki_tree, utc_now, write_json, write_jsonl


INDEX_ROOT = HYBRID_INDEX_ROOT
INDEX_JSONL = INDEX_ROOT / "index.jsonl"
INDEX_DB = INDEX_ROOT / "hybrid.sqlite"
VECTOR_FILES = [
    ROOT / "seo" / "research" / "vector" / "entities.jsonl",
    ROOT / "seo" / "research" / "vector" / "relations.jsonl",
    ROOT / "seo" / "research" / "vector" / "triplets.jsonl",
    ROOT / "seo" / "research" / "vector" / "answer_units.jsonl",
    ROOT / "seo" / "research" / "vector" / "synthetic_prompts.jsonl",
    ROOT / "seo" / "research-package" / "vector" / "page_outline_triplets.jsonl",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def doc_id(kind: str, value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_-]+", "-", value).strip("-").lower()[:120] or "untitled"
    return f"{kind}:{value}"


def wiki_state_docs() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for name, kind in [
        ("articles.jsonl", "article"),
        ("categories.jsonl", "category"),
        ("brands.jsonl", "brand"),
        ("products.jsonl", "product"),
    ]:
        path = WIKI_ROOT / "state" / name
        for row in read_jsonl(path):
            title = row.get("title") or row.get("slug") or row.get("sku") or ""
            text = " ".join(
                clean_text(row.get(key, ""))
                for key in ["title", "slug", "url", "h1", "sku", "status", "categories", "brands"]
            )
            docs.append(
                {
                    "id": doc_id(kind, str(row.get("slug") or title)),
                    "kind": kind,
                    "title": title,
                    "url": row.get("url", ""),
                    "source_path": str(path.relative_to(ROOT)),
                    "text": text,
                    "metadata": row,
                }
            )
    return docs


def vector_docs() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for path in VECTOR_FILES:
        for idx, row in enumerate(read_jsonl(path), 1):
            title = row.get("name") or row.get("subject") or row.get("prompt") or row.get("cluster") or f"record-{idx}"
            text = clean_text(json.dumps(row, ensure_ascii=False))
            docs.append(
                {
                    "id": doc_id("vector", f"{path.stem}-{idx}-{title}"),
                    "kind": "vector",
                    "title": str(title),
                    "url": row.get("target_url") or row.get("url") or "",
                    "source_path": str(path.relative_to(ROOT)),
                    "text": text,
                    "metadata": row,
                }
            )
    return docs


def markdown_docs() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for folder, kind in [(WIKI_ROOT / "frameworks", "framework"), (WIKI_ROOT / "rules", "rule"), (WIKI_ROOT / "reports", "report")]:
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.md")):
            text = clean_text(path.read_text(encoding="utf-8", errors="ignore"))
            first = next((line.strip("# ") for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.startswith("#")), path.stem)
            docs.append(
                {
                    "id": doc_id(kind, path.stem),
                    "kind": kind,
                    "title": first,
                    "url": "",
                    "source_path": str(path.relative_to(ROOT)),
                    "text": text,
                    "metadata": {},
                }
            )
    return docs


def collect_docs() -> list[dict[str, Any]]:
    seen: set[str] = set()
    docs: list[dict[str, Any]] = []
    for item in wiki_state_docs() + vector_docs() + markdown_docs():
        if item["id"] in seen or not item["text"].strip():
            continue
        seen.add(item["id"])
        docs.append(item)
    return docs


def build_sqlite(docs: list[dict[str, Any]]) -> bool:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    if INDEX_DB.exists():
        INDEX_DB.unlink()
    con = sqlite3.connect(INDEX_DB)
    try:
        con.execute("CREATE TABLE docs(id TEXT PRIMARY KEY, kind TEXT, title TEXT, url TEXT, source_path TEXT, text TEXT, metadata TEXT)")
        try:
            con.execute("CREATE VIRTUAL TABLE docs_fts USING fts5(id UNINDEXED, title, text, kind UNINDEXED, source_path UNINDEXED)")
            has_fts = True
        except sqlite3.OperationalError:
            has_fts = False
        for doc in docs:
            con.execute(
                "INSERT INTO docs VALUES(?,?,?,?,?,?,?)",
                (doc["id"], doc["kind"], doc["title"], doc["url"], doc["source_path"], doc["text"], json.dumps(doc["metadata"], ensure_ascii=False)),
            )
            if has_fts:
                con.execute("INSERT INTO docs_fts VALUES(?,?,?,?,?)", (doc["id"], doc["title"], doc["text"], doc["kind"], doc["source_path"]))
        con.commit()
        return has_fts
    finally:
        con.close()


def zvec_available() -> bool:
    try:
        import zvec  # noqa: F401
        return True
    except Exception:
        return False


def build(write: bool) -> dict[str, Any]:
    ensure_wiki_tree()
    docs = collect_docs()
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    has_fts = build_sqlite(docs)
    if write:
        write_jsonl(INDEX_JSONL, docs)
    status = {
        "status": "ok",
        "generated_at": utc_now(),
        "docs": len(docs),
        "sqlite_fts": has_fts,
        "zvec_available": zvec_available(),
        "index_jsonl": str(INDEX_JSONL),
        "sqlite": str(INDEX_DB),
        "policy": "Search aid only; facts must still come from wiki source records and source packs.",
    }
    if write:
        write_json(INDEX_ROOT / "zvec-status.json", status)
    return status


def normalize_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9]{2,}", query)
    return " OR ".join(tokens) or query


def search(query: str, limit: int) -> dict[str, Any]:
    if not INDEX_DB.exists():
        build(write=True)
    con = sqlite3.connect(INDEX_DB)
    con.row_factory = sqlite3.Row
    try:
        try:
            rows = con.execute(
                """
                SELECT d.id, d.kind, d.title, d.url, d.source_path,
                       snippet(docs_fts, 2, '[', ']', ' … ', 12) AS snippet,
                       bm25(docs_fts) AS score
                FROM docs_fts
                JOIN docs d ON d.id = docs_fts.id
                WHERE docs_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (normalize_query(query), limit),
            ).fetchall()
        except sqlite3.OperationalError:
            like = f"%{query}%"
            rows = con.execute(
                "SELECT id, kind, title, url, source_path, substr(text, 1, 260) AS snippet, 0 AS score FROM docs WHERE text LIKE ? LIMIT ?",
                (like, limit),
            ).fetchall()
        return {
            "query": query,
            "results": [dict(row) for row in rows],
            "generated_at": utc_now(),
        }
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if args.build or not args.query:
        result = build(write=True if args.write or args.build else False)
    else:
        result = search(args.query, args.limit)
        if args.write:
            safe = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_-]+", "-", args.query).strip("-").lower()[:80] or "query"
            write_json(INDEX_ROOT / f"search-{safe}.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
