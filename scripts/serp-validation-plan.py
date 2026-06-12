#!/usr/bin/env python3
"""Plan missing SERP validations for MVP/priority keywords."""

from __future__ import annotations

import argparse
import pathlib
from typing import Any

from research_package_repair_core import (
    as_list,
    clusters_from_architecture,
    load_architecture,
    markdown_findings,
    normalize_key,
    normalize_url,
    print_report,
    resolve_package,
    write_csv,
    write_json,
    write_text,
)


def expected_keywords(architecture: dict[str, Any]) -> list[str]:
    sources = ((architecture.get("metadata") or {}).get("sources") or {})
    keywords = as_list(sources.get("dataforseo_serp_validation_keywords"))
    for cluster in clusters_from_architecture(architecture):
        if cluster.get("primary_keyword") and (cluster.get("mvp") is True or str(cluster.get("priority", "")).upper() == "P1"):
            keywords.append(str(cluster.get("primary_keyword")))
    seen = set()
    ordered = []
    for keyword in keywords:
        key = normalize_key(keyword)
        if key and key not in seen:
            ordered.append(keyword)
            seen.add(key)
    return ordered


def validation_is_empty(validation: Any) -> bool:
    if not isinstance(validation, dict):
        return True
    for field in ("features", "top_urls", "top_titles", "items", "results"):
        value = validation.get(field)
        if isinstance(value, list) and value:
            return False
    return True


def cluster_by_keyword(architecture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping = {}
    for cluster in clusters_from_architecture(architecture):
        primary = normalize_key(cluster.get("primary_keyword"))
        if primary:
            mapping[primary] = cluster
    return mapping


def build_report(package: pathlib.Path, provider: str, country: str, language: str, device: str) -> dict[str, Any]:
    architecture = load_architecture(package)
    validation = architecture.get("dataforseo_serp_validation") or {}
    clusters = cluster_by_keyword(architecture)
    rows = []
    for keyword in expected_keywords(architecture):
        existing = validation.get(keyword) or validation.get(normalize_key(keyword))
        if not validation_is_empty(existing):
            continue
        cluster = clusters.get(normalize_key(keyword), {})
        rows.append(
            {
                "keyword": keyword,
                "provider": provider,
                "country": country,
                "language": language,
                "device": device,
                "current_page_type": cluster.get("page_type", ""),
                "expected_url": normalize_url(cluster.get("suggested_url") or cluster.get("url")),
                "page_type_decision_fields": "top_urls|top_titles|serp_features|dominant_page_type|notes",
                "reason": "missing_or_empty_serp_validation",
            }
        )
    findings = [
        {
            "id": "missing_serp_validation",
            "severity": "error",
            "location": row["keyword"],
            "message": "SERP validation is missing/empty; page-type decision must be rechecked.",
        }
        for row in rows
    ]
    return {
        "script": "serp-validation-plan",
        "summary": {
            "expected_queries": len(expected_keywords(architecture)),
            "planned_queries": len(rows),
        },
        "outputs": {
            "plan_csv": "serp-validation-plan.csv",
            "json": "serp-validation-plan.json",
            "markdown": "serp-validation-plan.md",
        },
        "rows": rows,
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return markdown_findings("SERP Validation Plan", report["summary"], report.get("findings"))


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    write_csv(package / "serp-validation-plan.csv", report["rows"])
    persist = {key: value for key, value in report.items() if key != "rows"}
    write_json(package / "serp-validation-plan.json", persist)
    write_text(package / "serp-validation-plan.md", render_markdown(report))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--write", action="store_true", help="Write SERP validation plan and reports")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    parser.add_argument("--provider", default="dataforseo")
    parser.add_argument("--country", default="US")
    parser.add_argument("--language", default="en")
    parser.add_argument("--device", default="desktop")
    args = parser.parse_args()

    package = resolve_package(args.package)
    report = build_report(package, args.provider, args.country, args.language, args.device)
    if args.write:
        write_outputs(package, report)
    print_report(report, args.format, render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
