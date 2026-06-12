#!/usr/bin/env python3
"""Render entity-map.md from entity-map.yaml and verify parity."""

from __future__ import annotations

import argparse
import pathlib
from typing import Any

from research_package_repair_core import (
    as_list,
    markdown_findings,
    normalize_space,
    print_report,
    resolve_package,
    write_json,
    write_text,
)

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def load_entity_map(path: pathlib.Path) -> dict[str, Any]:
    if yaml is None:
        raise SystemExit("ERROR: PyYAML is required for entity-map-sync.py")
    if not path.exists():
        return {"entities": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {"entities": []}


def entity_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    entities = data.get("entities") or []
    if isinstance(entities, dict):
        return [dict(value, id=key) if isinstance(value, dict) and "id" not in value else value for key, value in entities.items()]
    return [entity for entity in entities if isinstance(entity, dict)]


def render_entity(entity: dict[str, Any]) -> list[str]:
    name = normalize_space(entity.get("name") or entity.get("id") or "Unnamed entity")
    lines = [f"## {name}", ""]
    if entity.get("id"):
        lines.append(f"- ID: `{normalize_space(entity.get('id'))}`")
    if entity.get("coverage_priority"):
        lines.append(f"- Coverage priority: {normalize_space(entity.get('coverage_priority'))}")
    targets = as_list(entity.get("target_clusters"))
    if targets:
        lines.append(f"- Target clusters: {', '.join(f'`{target}`' for target in targets)}")
    related = as_list(entity.get("related_entities"))
    if related:
        lines.append(f"- Related entities: {', '.join(related)}")
    attributes = as_list(entity.get("attributes"))
    if attributes:
        lines.extend(["", "### Attributes"])
        for attribute in attributes:
            lines.append(f"- {attribute}")
    synonyms = as_list(entity.get("synonyms"))
    if synonyms:
        lines.extend(["", "### Synonyms"])
        for synonym in synonyms:
            lines.append(f"- {synonym}")
    lines.append("")
    return lines


def render_markdown_body(data: dict[str, Any]) -> str:
    lines = ["# Entity Map", ""]
    for entity in entity_rows(data):
        lines.extend(render_entity(entity))
    return "\n".join(lines).rstrip() + "\n"


def build_report(package: pathlib.Path) -> dict[str, Any]:
    path = package / "entity-map.yaml"
    data = load_entity_map(path)
    entities = entity_rows(data)
    findings = []
    existing = (package / "entity-map.md").read_text(encoding="utf-8") if (package / "entity-map.md").exists() else ""
    for entity in entities:
        for attribute in as_list(entity.get("attributes")):
            if existing and attribute not in existing:
                findings.append(
                    {
                        "id": "entity_map_md_missing_yaml_attribute",
                        "severity": "warning",
                        "location": "entity-map.md",
                        "message": f"`{attribute}` exists in YAML but is missing from Markdown.",
                    }
                )
    return {
        "script": "entity-map-sync",
        "summary": {
            "entities": len(entities),
            "missing_markdown_attributes": len(findings),
        },
        "outputs": {
            "markdown": "entity-map.md",
            "json": "entity-map-sync.json",
            "report": "entity-map-sync.md",
        },
        "rendered_markdown": render_markdown_body(data),
        "findings": findings,
    }


def render_report(report: dict[str, Any]) -> str:
    return markdown_findings("Entity Map Sync", report["summary"], report.get("findings"))


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    write_text(package / "entity-map.md", report["rendered_markdown"])
    persist = {key: value for key, value in report.items() if key != "rendered_markdown"}
    write_json(package / "entity-map-sync.json", persist)
    write_text(package / "entity-map-sync.md", render_report(report))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--write", action="store_true", help="Write canonical entity-map.md and reports")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    args = parser.parse_args()

    package = resolve_package(args.package)
    report = build_report(package)
    if args.write:
        write_outputs(package, report)
    print_report(report, args.format, render_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
