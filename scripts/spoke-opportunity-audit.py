#!/usr/bin/env python3
"""Find phase-2 spoke page opportunities from semantic-core metrics."""

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
    slugify,
    to_bool,
    to_float,
    write_csv,
    write_json,
    write_text,
)


def match_cluster(row: dict[str, str], lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for field in ("base_cluster", "cluster_id", "source_cluster", "suggested_url", "url"):
        value = row.get(field)
        for key in (normalize_key(value), normalize_url(value)):
            if key and key in lookup:
                return lookup[key]
    return None


def parent_base(url: str) -> str:
    normalized = normalize_url(url)
    parts = [part for part in normalized.strip("/").split("/") if part]
    if not parts:
        return "/"
    return f"/{parts[0]}/"


def suggested_spoke_url(cluster: dict[str, Any], keyword: str) -> str:
    base = parent_base(str(cluster.get("suggested_url") or cluster.get("url") or "/"))
    return f"{base}{slugify(keyword)}/"


def is_spoke_candidate(row: dict[str, str], cluster: dict[str, Any] | None, min_impressions: float, max_position: float) -> bool:
    keyword = row.get("keyword") or row.get("query") or ""
    if len(normalize_key(keyword).split()) < 3:
        return False
    if cluster and normalize_key(keyword) == normalize_key(cluster.get("primary_keyword")):
        return False
    impressions = to_float(row.get("impressions") or row.get("search_volume"))
    position = to_float(row.get("position") or row.get("avg_position"), default=999.0)
    if impressions < min_impressions or position > max_position:
        return False
    if cluster and not to_bool(cluster.get("mvp")):
        return True
    features = normalize_key(row.get("dataforseo_serp_features") or row.get("serp_features"))
    return "ai overview" in features


def build_report(package: pathlib.Path, min_impressions: float, max_position: float) -> dict[str, Any]:
    architecture = load_architecture(package)
    lookup = cluster_lookup(architecture)
    source = preferred_semantic_core(package)
    rows = read_csv(source)
    opportunities = []
    for row in rows:
        cluster = match_cluster(row, lookup)
        if not is_spoke_candidate(row, cluster, min_impressions, max_position):
            continue
        keyword = row.get("keyword") or row.get("query") or ""
        opportunities.append(
            {
                "phase": "phase_2",
                "keyword": keyword,
                "source_cluster": cluster.get("id", "") if cluster else row.get("base_cluster", ""),
                "parent_url": normalize_url(cluster.get("suggested_url") if cluster else row.get("suggested_url")),
                "suggested_url": suggested_spoke_url(cluster or {}, keyword),
                "impressions": row.get("impressions", ""),
                "clicks": row.get("clicks", ""),
                "position": row.get("position", ""),
                "reason": "long_tail_has_measured_demand",
            }
        )
    findings = [
        {
            "id": "phase_2_spoke_opportunity",
            "severity": "info",
            "location": row["keyword"],
            "message": f"Create spoke page `{row['suggested_url']}` under `{row['parent_url']}`.",
        }
        for row in opportunities
    ]
    return {
        "script": "spoke-opportunity-audit",
        "summary": {
            "source_rows": len(rows),
            "opportunities": len(opportunities),
            "min_impressions": min_impressions,
            "max_position": max_position,
        },
        "outputs": {
            "csv": "spoke-opportunities.csv",
            "json": "spoke-opportunity-audit.json",
            "markdown": "spoke-opportunity-audit.md",
        },
        "rows": opportunities,
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return markdown_findings("Spoke Opportunity Audit", report["summary"], report.get("findings"))


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    write_csv(package / "spoke-opportunities.csv", report["rows"])
    persist = {key: value for key, value in report.items() if key != "rows"}
    write_json(package / "spoke-opportunity-audit.json", persist)
    write_text(package / "spoke-opportunity-audit.md", render_markdown(report))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--write", action="store_true", help="Write spoke opportunity CSV and reports")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    parser.add_argument("--min-impressions", type=float, default=50.0)
    parser.add_argument("--max-position", type=float, default=20.0)
    args = parser.parse_args()

    package = resolve_package(args.package)
    report = build_report(package, args.min_impressions, args.max_position)
    if args.write:
        write_outputs(package, report)
    print_report(report, args.format, render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
