#!/usr/bin/env python3
"""Build Graphify graph using Antigravity/Gemini CLI OAuth as semantic overlay.

This avoids API keys. It calls the installed `agy` or `gemini` CLI in headless mode,
asks it for Graphify-compatible JSON per corpus chunk, validates/sanitizes the
result, merges it with deterministic wiki/vector extraction, then uses Graphify
to build `graph.json` and `GRAPH_REPORT.md`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.export import to_json
from graphify.report import generate

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from wiki_common import GRAPH_CORPUS_ROOT, GRAPH_ROOT, ROOT  # noqa: E402

CORPUS_ROOT = GRAPH_CORPUS_ROOT
OUT_ROOT = GRAPH_ROOT / "graphify-out"
CLI_DIR = GRAPH_ROOT / "antigravity-cli"
LOCAL_SCRIPT = Path(__file__).resolve().with_name("graphify-build-local-graph.py")
SUPPORTED_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".csv", ".yaml", ".yml"}


def load_local_builder():
    spec = importlib.util.spec_from_file_location("graphify_local_builder", LOCAL_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {LOCAL_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def slugify(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9а-яё/_-]+", "-", value, flags=re.I)
    return value.replace("/", "-").strip("-")[:140] or "unknown"


def corpus_files(max_files: int) -> list[Path]:
    files = [
        p for p in sorted(CORPUS_ROOT.rglob("*"))
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and p.stat().st_size <= 180_000
    ]
    priority = []
    rest = []
    for p in files:
        rel = str(p.relative_to(CORPUS_ROOT))
        if any(part in rel for part in ["wiki/rules/", "wiki/state/latest-summary", "wiki/articles/", "wiki/categories/", "wiki/brands/", "distillates/", "vector/"]):
            priority.append(p)
        else:
            rest.append(p)
    ordered = priority + rest
    return ordered[:max_files] if max_files > 0 else ordered


def chunk_files(files: list[Path], *, max_chars: int, per_file_chars: int) -> list[list[tuple[Path, str]]]:
    chunks: list[list[tuple[Path, str]]] = []
    current: list[tuple[Path, str]] = []
    current_chars = 0
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        text = text[:per_file_chars]
        cost = len(text)
        if current and current_chars + cost > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append((path, text))
        current_chars += cost
    if current:
        chunks.append(current)
    return chunks


def build_prompt(chunk: list[tuple[Path, str]], chunk_num: int, total: int) -> str:
    parts = [
        "Return ONLY valid JSON, no markdown, no comments.",
        "Build a Graphify extraction chunk for SEO knowledge graph.",
        "Schema:",
        '{"nodes":[{"id":"concept:slug","label":"Label","file_type":"concept|document","source_file":"relative/path"}],"edges":[{"source":"concept:a","target":"concept:b","relation":"related_to","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","source_file":"relative/path"}],"hyperedges":[],"input_tokens":0,"output_tokens":0}',
        "Rules:",
        "- Extract only important SEO/product/content concepts, pages, brands, categories, entities, intents, questions, and source-backed relationships.",
        "- Use stable lowercase ids with prefixes: concept:, topic:, page:, product:, brand:, category:, source:.",
        "- Do not include secrets, API keys, passwords, OAuth tokens, or credentials.",
        "- Do not invent facts. Use EXTRACTED for explicit relationships and INFERRED only when strongly supported.",
        "- Keep output compact: up to 80 nodes and 120 edges for this chunk.",
        f"Chunk {chunk_num}/{total}. Files:",
    ]
    for path, text in chunk:
        rel = str(path.relative_to(ROOT))
        parts.append(f"\n--- FILE: {rel} ---\n{text}\n--- END FILE ---")
    return "\n".join(parts)


def extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def cli_command(cli: str, prompt: str, timeout: int) -> list[str]:
    if cli == "agy":
        return ["agy", "--print", prompt, "--print-timeout", f"{timeout}s"]
    return ["gemini", "-p", prompt, "--output-format", "text", "--approval-mode", "plan"]


def call_llm_cli(cli: str, prompt: str, timeout: int) -> tuple[dict[str, Any] | None, str, str]:
    result = subprocess.run(
        cli_command(cli, prompt, timeout),
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout + 10,
    )
    raw = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
    return extract_json(result.stdout), raw, f"returncode={result.returncode}"


def sanitize_semantic(data: dict[str, Any], known_ids: set[str]) -> dict[str, list[dict]]:
    nodes: dict[str, dict] = {}
    for node in data.get("nodes", []):
        if not isinstance(node, dict):
            continue
        label = str(node.get("label") or node.get("id") or "").strip()
        if not label:
            continue
        node_id = str(node.get("id") or f"concept:{slugify(label)}")
        if ":" not in node_id:
            node_id = f"concept:{slugify(node_id)}"
        file_type = node.get("file_type") if node.get("file_type") in {"document", "concept", "code", "paper", "image", "rationale"} else "concept"
        nodes[node_id] = {
            "id": node_id[:180],
            "label": label[:240],
            "file_type": file_type,
            "source_file": str(node.get("source_file") or "gemini-cli"),
        }
    all_ids = set(nodes) | known_ids
    edges: list[dict] = []
    seen = set()
    for edge in data.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in all_ids or target not in all_ids or source == target:
            continue
        confidence = edge.get("confidence") if edge.get("confidence") in {"EXTRACTED", "INFERRED", "AMBIGUOUS"} else "INFERRED"
        relation = str(edge.get("relation") or "related_to")[:80]
        key = (source, target, relation)
        if key in seen:
            continue
        seen.add(key)
        edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "confidence": confidence,
            "source_file": str(edge.get("source_file") or "gemini-cli"),
        })
    return {"nodes": list(nodes.values()), "edges": edges}


def build_graph(extraction: dict, mode: str, chunks_ok: int, chunks_failed: int) -> dict:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / ".graphify_extract.json").write_text(json.dumps(extraction, ensure_ascii=False, indent=2), encoding="utf-8")
    G = build_from_json(extraction, directed=True, root=ROOT)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    labels = {cid: f"SEO Community {cid}" for cid in communities}
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    questions = suggest_questions(G, communities, labels)
    detection = {"total_files": 137, "total_words": 162697, "files": {}, "warning": ""}
    report = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        {"input": 0, "output": 0},
        str(CORPUS_ROOT),
        suggested_questions=questions,
    )
    (OUT_ROOT / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    to_json(G, communities, str(OUT_ROOT / "graph.json"), force=True)
    status = {
        "status": "ok",
        "mode": mode,
        "graph_root": str(OUT_ROOT),
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(communities),
        "chunks_ok": chunks_ok,
        "chunks_failed": chunks_failed,
        "llm_backend": "antigravity_cli_oauth",
    }
    (GRAPH_ROOT / "graphify-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=35, help="0 means all supported corpus files")
    parser.add_argument("--max-chars", type=int, default=28000)
    parser.add_argument("--per-file-chars", type=int, default=5000)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--cli", choices=["auto", "agy", "gemini"], default="auto")
    args = parser.parse_args()

    cli = args.cli
    if cli == "auto":
        cli = "agy" if shutil.which("agy") else "gemini" if shutil.which("gemini") else ""
    if not cli:
        raise SystemExit("Neither agy nor gemini CLI was found")

    local = load_local_builder()
    extraction = local.build_extraction()
    known_ids = {node["id"] for node in extraction.get("nodes", [])}

    files = corpus_files(args.max_files)
    chunks = chunk_files(files, max_chars=args.max_chars, per_file_chars=args.per_file_chars)
    CLI_DIR.mkdir(parents=True, exist_ok=True)

    semantic_nodes: dict[str, dict] = {}
    semantic_edges: list[dict] = []
    chunks_ok = 0
    chunks_failed = 0
    for index, chunk in enumerate(chunks, 1):
        prompt = build_prompt(chunk, index, len(chunks))
        data, raw, meta = call_llm_cli(cli, prompt, args.timeout)
        (CLI_DIR / f"chunk-{index:02d}.raw.txt").write_text(raw, encoding="utf-8")
        if data is None:
            chunks_failed += 1
            continue
        clean = sanitize_semantic(data, known_ids | set(semantic_nodes))
        (CLI_DIR / f"chunk-{index:02d}.json").write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        for node in clean["nodes"]:
            semantic_nodes[node["id"]] = node
        semantic_edges.extend(clean["edges"])
        known_ids |= set(semantic_nodes)
        chunks_ok += 1

    extraction["nodes"].extend(semantic_nodes.values())
    existing_edge_keys = {(e.get("source"), e.get("target"), e.get("relation")) for e in extraction.get("edges", [])}
    for edge in semantic_edges:
        key = (edge.get("source"), edge.get("target"), edge.get("relation"))
        if key not in existing_edge_keys:
            extraction["edges"].append(edge)
            existing_edge_keys.add(key)

    status = build_graph(extraction, f"{cli}_oauth_semantic_overlay", chunks_ok, chunks_failed)
    status["semantic_nodes"] = len(semantic_nodes)
    status["semantic_edges"] = len(semantic_edges)
    status["files_used"] = len(files)
    status["cli"] = cli
    (GRAPH_ROOT / "graphify-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if chunks_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
