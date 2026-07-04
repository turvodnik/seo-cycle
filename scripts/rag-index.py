#!/usr/bin/env python3
"""Index project research artifacts into the local RAG store (seo/rag.db).

Sources (config `rag.sources`): source_pack JSONL, page-outline entity
triplets, research distillates, drafts/copywriter-ready markdown. Indexing is
incremental (content hash per file); deleted files are purged. Without --write
it is a dry-run report of what would be indexed.

Embeddings are optional: with EMBEDDING_API_URL/KEY/MODEL set (OpenAI-compatible
/embeddings), chunks are embedded for hybrid search; otherwise the index is
BM25-only and fully offline. Live embedding calls run a usage-ledger preflight.

--global mode walks config/projects-registry.yaml (active projects) and builds
the cross-project index in ~/.seo-cycle/rag/global.db.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.ads import ledger_preflight, ledger_record  # generic ledger helpers
from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, skill_root
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.rag import GLOBAL_DB, embedding_env, index_project, index_stats, open_db, rag_db_path
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("rag-index")


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "rag"
    return {
        "markdown": base / "rag-index.md",
        "json": base / "rag-index.json",
        "latest_markdown": base / "latest-rag-index.md",
        "latest_json": base / "latest-rag-index.json",
    }


def registry_projects() -> list[dict[str, Any]]:
    registry = load_yaml(skill_root(__file__) / "config" / "projects-registry.yaml")
    rows = registry.get("projects") if isinstance(registry, dict) else None
    projects = []
    for row in rows or []:
        if isinstance(row, dict) and row.get("path") and str(row.get("status", "active")) == "active":
            projects.append({"name": str(row.get("name") or pathlib.Path(row["path"]).name),
                             "path": pathlib.Path(str(row["path"])).expanduser()})
    return projects


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# RAG Index",
        "",
        f"- Generated: {report['generated_at']}",
        f"- DB: `{report['db']}`",
        f"- Mode: {report['mode']} · embeddings: {report['embeddings']}",
        f"- Totals: {report['stats']['chunks']} chunks"
        f" ({report['stats']['embedded']} embedded) across {report['stats']['projects']} project(s)",
        "",
        "## Per-run",
        "",
    ]
    for name, stats in report["runs"].items():
        lines.append(
            f"- **{name}**: indexed {stats['indexed_files']}, skipped {stats['skipped_files']},"
            f" removed {stats['removed_files']}, chunks {stats['chunks']}"
            f" (embedded {stats['embedded_chunks']}) · by source: {json.dumps(stats['by_source'], ensure_ascii=False)}"
        )
    lines.extend(["", "Query: `seo-cycle rag query \"<вопрос>\" --top-k 8`"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Actually index (default: dry-run report)")
    parser.add_argument("--rebuild", action="store_true", help="Drop and re-create the index first")
    parser.add_argument("--embed", choices=("auto", "off", "required"), default=None,
                        help="Embedding mode (default: rag.embedding.mode or auto)")
    parser.add_argument("--global", dest="global_mode", action="store_true",
                        help="Index all active registry projects into ~/.seo-cycle/rag/global.db")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.global_mode:
        projects = registry_projects()
        if not projects:
            print("ERROR: no active projects in config/projects-registry.yaml", file=sys.stderr)
            return 2
        db_path = GLOBAL_DB
        report_root = None
    else:
        cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
        if not cfg_path or not cfg_path.exists():
            print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        cfg = load_yaml(cfg_path)
        report_root = project_root_for(cfg_path)
        global log
        log = setup_logging("rag-index", report_root, cfg)
        projects = [{"name": str((cfg.get("project") or {}).get("name") or report_root.name),
                     "path": report_root, "cfg": cfg}]
        db_path = rag_db_path(report_root, cfg)

    if args.rebuild and args.write and db_path.exists():
        db_path.unlink()

    embed_mode = args.embed
    # dry-run must not create the DB file on disk
    conn = open_db(db_path if args.write or db_path.exists() else ":memory:")
    runs: dict[str, Any] = {}
    for entry in projects:
        cfg = entry.get("cfg")
        if cfg is None:
            entry_cfg_path = find_config(entry["path"])
            cfg = load_yaml(entry_cfg_path) if entry_cfg_path else {}
        mode = embed_mode or str(nested_get(cfg, "rag.embedding.mode", "auto") or "auto")
        if mode != "off" and embedding_env() is not None and args.write:
            ok, message = ledger_preflight(entry["path"], "embedding_api", category="llm")
            if not ok:
                print(f"ERROR: usage-ledger preflight blocked embeddings: {message}", file=sys.stderr)
                return 2
        try:
            stats = index_project(conn, entry["path"], cfg, entry["name"],
                                  embed=mode, dry_run=not args.write)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if args.write and stats["embedded_chunks"]:
            ledger_record(entry["path"], "embedding_api", requests=1, category="llm",
                          note=f"rag-index embedded {stats['embedded_chunks']} chunks")
        runs[entry["name"]] = stats
        log.info("rag index %s: %s", entry["name"], stats)

    report = {
        "audit_id": "rag_index",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "db": str(db_path),
        "mode": "write" if args.write else "dry_run",
        "embeddings": "configured" if embedding_env() else "off (BM25 only)",
        "fts5": bool(getattr(conn, "fts5_enabled", False)),
        "runs": runs,
        "stats": index_stats(conn),
    }
    conn.close()
    if args.write and report_root is not None:
        write_report_bundle(output_paths(report_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
