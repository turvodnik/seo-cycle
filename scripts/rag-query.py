#!/usr/bin/env python3
"""Query the local RAG store (project seo/rag.db or the global cross-project index).

Examples:
  python3 scripts/rag-query.py "чем крепить вагонку" --top-k 5
  python3 scripts/rag-query.py "монтаж" --source-type draft --source-type distillate
  python3 scripts/rag-query.py "вагонка кедр" --global --project emwoody --format json

BM25 (FTS5) by default; with EMBEDDING_API_* env set the query runs hybrid
(FTS5 prefilter → cosine rerank). Empty index exits 0 with a hint.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.rag import GLOBAL_DB, open_db, rag_db_path, search

SOURCE_TYPES = ("source_pack", "triplet", "distillate", "draft", "mirror")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", help="Free-text question / keyword")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--source-type", action="append", choices=SOURCE_TYPES,
                        help="Repeatable source-type filter")
    parser.add_argument("--project", help="Filter by project name (useful with --global)")
    parser.add_argument("--global", dest="global_mode", action="store_true",
                        help="Query the cross-project index (~/.seo-cycle/rag/global.db)")
    parser.add_argument("--mode", choices=("auto", "bm25", "hybrid"), default="auto")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.global_mode:
        db_path = GLOBAL_DB
    else:
        cfg_path = find_config(pathlib.Path.cwd())
        if not cfg_path:
            print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        db_path = rag_db_path(project_root_for(cfg_path), load_yaml(cfg_path))

    if not db_path.exists():
        print(f"RAG index not found at {db_path} — run `seo-cycle run script rag-index --write` first.",
              file=sys.stderr)
        return 0

    conn = open_db(db_path)
    mode = "bm25" if args.mode == "bm25" else args.mode
    results = search(conn, args.query, top_k=args.top_k, source_types=args.source_type,
                     project=args.project, mode=mode)
    conn.close()

    if not results:
        print("No matches. Try broader terms or reindex with `rag-index.py --write`.", file=sys.stderr)
        return 0
    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    lines = [f"# RAG: {args.query}", ""]
    for index, item in enumerate(results, 1):
        snippet = " ".join(item["text"].split())
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        meta = item.get("meta") or {}
        cite = f" · {meta.get('page_url')}" if meta.get("page_url") else ""
        citations = meta.get("citations") or []
        cite += f" · sources: {', '.join(citations[:2])}" if citations else ""
        lines.append(f"{index}. **[{item['source_type']}]** {item['project']}:{item['path']}"
                     f" (score {item['score']}){cite}")
        lines.append(f"   > {snippet}")
        lines.append("")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
