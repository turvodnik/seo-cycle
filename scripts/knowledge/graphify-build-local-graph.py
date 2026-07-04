#!/usr/bin/env python3
"""Build a Graphify-compatible graph from local SEO wiki/vector data.

This is the no-API fallback. It does not perform LLM semantic extraction.
Instead it converts our source-of-truth artifacts into Graphify extraction JSON
and then uses Graphify's own builder, clustering, report, and graph.json export.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.export import to_json
from graphify.report import generate

from wiki_common import GRAPH_ROOT, ROOT, WIKI_ROOT, canonical_url

OUT_ROOT = GRAPH_ROOT / "graphify-out"
VECTOR_ROOT = ROOT / "seo" / "research" / "vector"
PACKAGE_VECTOR_ROOT = ROOT / "seo" / "research-package" / "vector"


def read_jsonl(path: Path) -> list[dict]:
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


def slugify(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9а-яё/_-]+", "-", value, flags=re.I)
    return value.replace("/", "-").strip("-")[:140] or "unknown"


class ExtractionBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.url_to_node: dict[str, str] = {}
        self.title_to_node: dict[str, str] = {}

    def add_node(self, node_id: str, label: str, *, file_type: str = "concept", source_file: str = "local-seo-graph", **attrs) -> str:
        node_id = node_id[:180]
        if node_id not in self.nodes:
            self.nodes[node_id] = {
                "id": node_id,
                "label": str(label or node_id),
                "file_type": file_type,
                "source_file": source_file,
                **{k: v for k, v in attrs.items() if v not in (None, "", [])},
            }
        return node_id

    def add_edge(self, source: str, target: str, relation: str, *, confidence: str = "EXTRACTED", source_file: str = "local-seo-graph", **attrs) -> None:
        if not source or not target or source == target:
            return
        self.edges.append({
            "source": source,
            "target": target,
            "relation": relation,
            "confidence": confidence,
            "source_file": source_file,
            **{k: v for k, v in attrs.items() if v not in (None, "", [])},
        })

    def add_page(self, row: dict, source_file: str) -> str:
        kind = row.get("type", "page")
        slug = row.get("slug") or slugify(row.get("url", ""))
        node_id = f"{kind}:{slugify(slug)}"
        url = canonical_url(row.get("url", ""))
        self.add_node(
            node_id,
            row.get("title") or slug,
            file_type="document",
            source_file=source_file,
            url=url,
            wp_id=row.get("wp_id"),
            page_type=kind,
            status=row.get("status"),
        )
        if url:
            self.url_to_node[url] = node_id
        title = str(row.get("title") or "").lower()
        if title:
            self.title_to_node[title] = node_id
        return node_id

    def node_for_url(self, url: str) -> str:
        url = canonical_url(url)
        if url in self.url_to_node:
            return self.url_to_node[url]
        node_id = f"url:{slugify(url)}"
        return self.add_node(node_id, url, file_type="concept", source_file="wiki/state/internal-links.jsonl", url=url)

    def node_for_concept(self, label: str, source_file: str = "seo/research/vector") -> str:
        return self.add_node(f"concept:{slugify(label)}", label, file_type="concept", source_file=source_file)


def build_extraction() -> dict:
    b = ExtractionBuilder()

    articles = read_jsonl(WIKI_ROOT / "state" / "articles.jsonl")
    categories = read_jsonl(WIKI_ROOT / "state" / "categories.jsonl")
    brands = read_jsonl(WIKI_ROOT / "state" / "brands.jsonl")
    products = read_jsonl(WIKI_ROOT / "state" / "products.jsonl")
    links = read_jsonl(WIKI_ROOT / "state" / "internal-links.jsonl")

    for source_file, rows in [
        ("wiki/state/articles.jsonl", articles),
        ("wiki/state/categories.jsonl", categories),
        ("wiki/state/brands.jsonl", brands),
        ("wiki/state/products.jsonl", products),
    ]:
        for row in rows:
            page_id = b.add_page(row, source_file)
            for heading in row.get("headings", [])[:30]:
                hnode = b.node_for_concept(str(heading.get("text", "")), source_file)
                b.add_edge(page_id, hnode, "has_heading", source_file=source_file)
            for category in row.get("categories", [])[:12]:
                cnode = b.node_for_concept(str(category), "wiki/state/products.jsonl")
                b.add_edge(page_id, cnode, "belongs_to_category", source_file="wiki/state/products.jsonl")
            for brand in row.get("brands", [])[:12]:
                bnode = b.node_for_concept(str(brand), "wiki/state/products.jsonl")
                b.add_edge(page_id, bnode, "has_brand", source_file="wiki/state/products.jsonl")

    for link in links:
        source_url = canonical_url(link.get("source_url", ""))
        source = b.url_to_node.get(source_url)
        target = b.node_for_url(link.get("target", ""))
        if source:
            b.add_edge(source, target, "links_to", source_file="wiki/state/internal-links.jsonl", anchor=link.get("anchor"))

    for row in read_jsonl(VECTOR_ROOT / "entities.jsonl"):
        entity = b.node_for_concept(row.get("name", ""), "seo/research/vector/entities.jsonl")
        for cluster in row.get("target_clusters", [])[:8]:
            cnode = b.node_for_concept(str(cluster), "seo/research/vector/entities.jsonl")
            b.add_edge(entity, cnode, "belongs_to_cluster", source_file="seo/research/vector/entities.jsonl")
        for related in row.get("related_entities", [])[:12]:
            rnode = b.node_for_concept(str(related), "seo/research/vector/entities.jsonl")
            b.add_edge(entity, rnode, "related_to", confidence="INFERRED", source_file="seo/research/vector/entities.jsonl")

    for path in [VECTOR_ROOT / "relations.jsonl", VECTOR_ROOT / "triplets.jsonl", PACKAGE_VECTOR_ROOT / "page_outline_triplets.jsonl"]:
        for row in read_jsonl(path):
            subject = b.node_for_concept(row.get("subject", ""), str(path.relative_to(ROOT)))
            obj_value = str(row.get("object", ""))
            obj = b.node_for_url(obj_value) if obj_value.startswith(("http://", "https://", "/")) else b.node_for_concept(obj_value, str(path.relative_to(ROOT)))
            predicate = str(row.get("predicate") or "related_to")
            b.add_edge(subject, obj, predicate, source_file=str(path.relative_to(ROOT)))
            cluster_value = row.get("cluster")
            if cluster_value:
                cnode = b.node_for_concept(str(cluster_value), str(path.relative_to(ROOT)))
                b.add_edge(subject, cnode, "belongs_to_cluster", source_file=str(path.relative_to(ROOT)))

    for row in read_jsonl(VECTOR_ROOT / "answer_units.jsonl"):
        prompt = b.node_for_concept(row.get("prompt", ""), "seo/research/vector/answer_units.jsonl")
        target = b.node_for_url(row.get("target_url", ""))
        cluster = b.node_for_concept(row.get("cluster", ""), "seo/research/vector/answer_units.jsonl")
        b.add_edge(prompt, target, "answers_for_page", source_file="seo/research/vector/answer_units.jsonl")
        b.add_edge(prompt, cluster, "belongs_to_cluster", source_file="seo/research/vector/answer_units.jsonl")

    for row in read_jsonl(VECTOR_ROOT / "sub_intents.jsonl"):
        keyword = b.node_for_concept(row.get("keyword", ""), "seo/research/vector/sub_intents.jsonl")
        cluster = b.node_for_concept(row.get("cluster", ""), "seo/research/vector/sub_intents.jsonl")
        intent = b.node_for_concept(row.get("intent_stage") or row.get("intent", ""), "seo/research/vector/sub_intents.jsonl")
        b.add_edge(keyword, cluster, "belongs_to_cluster", source_file="seo/research/vector/sub_intents.jsonl")
        b.add_edge(keyword, intent, "has_intent_stage", source_file="seo/research/vector/sub_intents.jsonl")

    for row in read_jsonl(VECTOR_ROOT / "synthetic_prompts.jsonl"):
        prompt = b.node_for_concept(row.get("prompt", ""), "seo/research/vector/synthetic_prompts.jsonl")
        target = b.node_for_url(row.get("target_url", ""))
        cluster = b.node_for_concept(row.get("cluster", ""), "seo/research/vector/synthetic_prompts.jsonl")
        b.add_edge(prompt, target, "tests_ai_visibility_for", source_file="seo/research/vector/synthetic_prompts.jsonl")
        b.add_edge(prompt, cluster, "belongs_to_cluster", source_file="seo/research/vector/synthetic_prompts.jsonl")

    # Deduplicate edges by source/target/relation/anchor.
    seen = set()
    deduped = []
    for edge in b.edges:
        key = (edge.get("source"), edge.get("target"), edge.get("relation"), edge.get("anchor", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)

    return {
        "nodes": list(b.nodes.values()),
        "edges": deduped,
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    extraction = build_extraction()
    extraction_path = OUT_ROOT / ".graphify_extract.json"
    extraction_path.write_text(json.dumps(extraction, ensure_ascii=False, indent=2), encoding="utf-8")

    G = build_from_json(extraction, directed=True, root=ROOT)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    labels = {cid: f"SEO Community {cid}" for cid in communities}
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    questions = suggest_questions(G, communities, labels)
    detection = {
        "total_files": 137,
        "total_words": 162697,
        "files": {},
        "warning": "",
    }
    report = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        {"input": 0, "output": 0},
        str(ROOT / "seo" / "knowledge" / "graph-corpus"),
        suggested_questions=questions,
    )
    (OUT_ROOT / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    to_json(G, communities, str(OUT_ROOT / "graph.json"), force=True)
    status = {
        "status": "ok",
        "mode": "local_wiki_vector_fallback",
        "graph_root": str(OUT_ROOT),
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(communities),
        "llm_backend": "none",
    }
    (GRAPH_ROOT / "graphify-status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
