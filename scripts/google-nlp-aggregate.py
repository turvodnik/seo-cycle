#!/usr/bin/env python3
"""Aggregate raw Google NLP entities into canonical entity_coverage.jsonl."""

from __future__ import annotations

import argparse
import pathlib
from collections import Counter
from typing import Any

from research_package_repair_core import (
    counter_dict,
    load_architecture,
    markdown_findings,
    normalize_space,
    print_report,
    repeated_phrase_clean,
    resolve_package,
    to_float,
    write_jsonl,
)
from seo_cycle_core.reports import write_artifacts


def raw_entities(package: pathlib.Path, architecture: dict[str, Any]) -> list[dict[str, Any]]:
    sources = (((architecture.get("metadata") or {}).get("sources") or {}).get("google_nlp") or {})
    entities = sources.get("entities") or []
    if isinstance(entities, list):
        return [entity for entity in entities if isinstance(entity, dict)]
    return []


def aggregate_entities(entities: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    for entity in entities:
        original = normalize_space(entity.get("name"))
        canonical = repeated_phrase_clean(original)
        if not canonical:
            continue
        salience = to_float(entity.get("salience"))
        item = grouped.setdefault(
            canonical,
            {
                "entity": canonical,
                "mentions": 0,
                "salience_sum": 0.0,
                "salience_max": 0.0,
                "types": Counter(),
                "variants": Counter(),
            },
        )
        item["mentions"] += 1
        item["salience_sum"] += salience
        item["salience_max"] = max(item["salience_max"], salience)
        item["types"][normalize_space(entity.get("type") or "UNKNOWN")] += 1
        item["variants"][original] += 1
        if original.lower() != canonical:
            findings.append(
                {
                    "id": "google_nlp_entity_normalized",
                    "severity": "info",
                    "location": "semantic-architecture-final.json",
                    "message": f"Normalized `{original}` to `{canonical}`.",
                }
            )
    rows: list[dict[str, Any]] = []
    for item in grouped.values():
        mentions = max(1, int(item["mentions"]))
        rows.append(
            {
                "entity": item["entity"],
                "mentions": mentions,
                "salience_sum": round(float(item["salience_sum"]), 6),
                "salience_avg": round(float(item["salience_sum"]) / mentions, 6),
                "salience_max": round(float(item["salience_max"]), 6),
                "types": counter_dict(item["types"]),
                "variants": counter_dict(item["variants"]),
            }
        )
    rows.sort(key=lambda row: (-row["salience_sum"], row["entity"]))
    return rows, findings


def build_report(package: pathlib.Path) -> dict[str, Any]:
    architecture = load_architecture(package)
    entities = raw_entities(package, architecture)
    rows, findings = aggregate_entities(entities)
    return {
        "script": "google-nlp-aggregate",
        "summary": {
            "raw_entities": len(entities),
            "unique_entities": len(rows),
            "normalized_entities": len(findings),
        },
        "outputs": {
            "jsonl": "entity_coverage.jsonl",
            "json": "google-nlp-aggregate.json",
            "markdown": "google-nlp-aggregate.md",
        },
        "rows": rows,
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [markdown_findings("Google NLP Aggregate", report["summary"], report.get("findings")).rstrip(), "", "## Top Entities"]
    for row in report.get("rows", [])[:20]:
        lines.append(f"- `{row['entity']}`: mentions={row['mentions']}, salience_sum={row['salience_sum']}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    write_jsonl(package / "entity_coverage.jsonl", report["rows"])
    persist = {key: value for key, value in report.items() if key != "rows"}
    write_artifacts(
        text_files={package / "google-nlp-aggregate.md": render_markdown(report)},
        json_files={package / "google-nlp-aggregate.json": persist},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--write", action="store_true", help="Write entity_coverage.jsonl and reports")
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
