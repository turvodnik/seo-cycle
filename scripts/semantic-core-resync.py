#!/usr/bin/env python3
"""Resync semantic-core rows with final cluster IDs and URLs."""

from __future__ import annotations

import argparse
import pathlib
from typing import Any

from research_package_repair_core import (
    cluster_lookup,
    load_architecture,
    markdown_findings,
    normalize_key,
    normalize_url,
    preferred_semantic_core,
    print_report,
    read_csv,
    resolve_package,
    write_csv,
)
from seo_cycle_core.reports import write_artifacts


CLUSTER_FIELDS = ("base_cluster", "cluster_id", "source_cluster")
URL_FIELDS = ("suggested_url", "url", "target_url")


def match_cluster(row: dict[str, str], lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    candidates = []
    for field in (*CLUSTER_FIELDS, *URL_FIELDS, "keyword", "query", "primary_keyword"):
        value = row.get(field)
        if value:
            candidates.extend([normalize_key(value), normalize_url(value)])
    for key in candidates:
        if key and key in lookup:
            return lookup[key]
    return None


def resync_rows(rows: list[dict[str, str]], lookup: dict[str, dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    output: list[dict[str, str]] = []
    findings: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        updated = dict(row)
        cluster = match_cluster(row, lookup)
        changed_fields: list[str] = []
        if cluster:
            cluster_id = str(cluster.get("id") or "")
            url = normalize_url(cluster.get("suggested_url") or cluster.get("url"))
            for field in CLUSTER_FIELDS:
                if field in updated and cluster_id and updated.get(field) != cluster_id:
                    updated[field] = cluster_id
                    changed_fields.append(field)
            for field in URL_FIELDS:
                if field in updated and url and normalize_url(updated.get(field)) != url:
                    updated[field] = url
                    changed_fields.append(field)
        if changed_fields:
            findings.append(
                {
                    "id": "semantic_core_row_resynced",
                    "severity": "info",
                    "location": f"semantic-core.csv:{index}",
                    "message": f"Updated {', '.join(sorted(set(changed_fields)))} for `{row.get('keyword', '')}`",
                }
            )
        output.append(updated)
    return output, findings


def build_report(package: pathlib.Path) -> dict[str, Any]:
    architecture = load_architecture(package)
    lookup = cluster_lookup(architecture)
    source = preferred_semantic_core(package)
    rows = read_csv(source)
    output_rows, findings = resync_rows(rows, lookup)
    return {
        "script": "semantic-core-resync",
        "source": str(source),
        "summary": {
            "total_rows": len(rows),
            "changed_rows": len(findings),
            "cluster_aliases": len(lookup),
        },
        "outputs": {
            "resynced_csv": "semantic-core.resynced.csv",
            "json": "semantic-core-resync.json",
            "markdown": "semantic-core-resync.md",
        },
        "rows": output_rows,
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return markdown_findings("Semantic Core Resync", report["summary"], report.get("findings"))


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    rows = report["rows"]
    write_csv(package / "semantic-core.resynced.csv", rows)
    persist = {key: value for key, value in report.items() if key != "rows"}
    write_artifacts(
        text_files={package / "semantic-core-resync.md": render_markdown(report)},
        json_files={package / "semantic-core-resync.json": persist},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--write", action="store_true", help="Write resynced CSV and reports")
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
