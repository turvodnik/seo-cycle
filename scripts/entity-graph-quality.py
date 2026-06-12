#!/usr/bin/env python3
"""Validate entity graph quality in page-outline-v2 JSON files."""

from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter
from typing import Any

from research_package_repair_core import (
    counter_dict,
    markdown_findings,
    normalize_key,
    print_report,
    relation_parts,
    resolve_package,
    write_json,
    write_text,
)


def outline_files(package: pathlib.Path) -> list[pathlib.Path]:
    outline_dir = package / "page-outlines-v2"
    if outline_dir.exists():
        return sorted(outline_dir.glob("*.json"))
    return sorted(package.glob("*outline*.json"))


def load_outline(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def known_nodes(outline: dict[str, Any]) -> set[str]:
    nodes = set()
    page = outline.get("page") or {}
    for field in ("primary_keyword", "title", "url", "intent", "page_type"):
        if page.get(field):
            nodes.add(normalize_key(page.get(field)))
    for entity in outline.get("entities") or []:
        if isinstance(entity, dict):
            nodes.add(normalize_key(entity.get("name")))
        else:
            nodes.add(normalize_key(entity))
    for section in outline.get("sections") or []:
        for entity in section.get("entities_to_cover") or []:
            nodes.add(normalize_key(entity))
    return {node for node in nodes if node}


def entity_weight_findings(path: pathlib.Path, outline: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for entity in outline.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        if entity.get("coverage_weight") is not None and not entity.get("weight_source"):
            findings.append(
                {
                    "id": "missing_weight_source",
                    "severity": "warning",
                    "location": str(path),
                    "message": f"Entity `{entity.get('name')}` has coverage_weight without weight_source.",
                }
            )
    return findings


def relation_findings(path: pathlib.Path, outline: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter[str], int, int]:
    findings: list[dict[str, Any]] = []
    nodes = known_nodes(outline)
    seen: Counter[tuple[str, str, str]] = Counter()
    relation_counts: Counter[str] = Counter()
    orphan_count = 0
    duplicate_count = 0
    for section in outline.get("sections") or []:
        for raw_relation in section.get("entity_connections") or []:
            parts = relation_parts(str(raw_relation))
            if not parts:
                continue
            subject, predicate, obj = parts
            triple = (normalize_key(subject), normalize_key(predicate), normalize_key(obj))
            seen[triple] += 1
            relation_counts[predicate] += 1
            if seen[triple] == 2:
                duplicate_count += 1
                findings.append(
                    {
                        "id": "duplicate_relation",
                        "severity": "warning",
                        "location": str(path),
                        "message": f"Duplicate relation `{subject} -> {predicate} -> {obj}`.",
                    }
                )
            for endpoint_label, endpoint in (("subject", subject), ("object", obj)):
                normalized = normalize_key(endpoint)
                if normalized and normalized not in nodes:
                    orphan_count += 1
                    findings.append(
                        {
                            "id": "orphan_relation_endpoint",
                            "severity": "error",
                            "location": str(path),
                            "message": f"Relation {endpoint_label} `{endpoint}` is not present in page entities/targets.",
                        }
                    )
    return findings, relation_counts, duplicate_count, orphan_count


def build_report(package: pathlib.Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    relation_counts: Counter[str] = Counter()
    duplicate_total = 0
    orphan_total = 0
    files = outline_files(package)
    for path in files:
        outline = load_outline(path)
        findings.extend(entity_weight_findings(path, outline))
        relation_items, counts, duplicates, orphans = relation_findings(path, outline)
        findings.extend(relation_items)
        relation_counts.update(counts)
        duplicate_total += duplicates
        orphan_total += orphans
    relation_coverage = {
        "relation_types": counter_dict(relation_counts),
        "duplicate_relations": duplicate_total,
        "orphan_endpoints": orphan_total,
    }
    return {
        "script": "entity-graph-quality",
        "summary": {
            "outline_files": len(files),
            "findings": len(findings),
            "duplicate_relations": duplicate_total,
            "orphan_endpoints": orphan_total,
        },
        "relation_coverage": relation_coverage,
        "outputs": {
            "json": "entity-graph-quality.json",
            "markdown": "entity-graph-quality.md",
        },
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [markdown_findings("Entity Graph Quality", report["summary"], report.get("findings")).rstrip(), "", "## Relation Coverage"]
    for relation, count in report["relation_coverage"]["relation_types"].items():
        lines.append(f"- `{relation}`: {count}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    write_json(package / "entity-graph-quality.json", report)
    write_text(package / "entity-graph-quality.md", render_markdown(report))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--write", action="store_true", help="Write graph quality reports")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    args = parser.parse_args()

    package = resolve_package(args.package)
    report = build_report(package)
    if args.write:
        write_outputs(package, report)
    print_report(report, args.format, render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
