#!/usr/bin/env python3
"""Clean prompt/spam rows from semantic-core.csv and write repair artifacts."""

from __future__ import annotations

import argparse
import pathlib
import re
from typing import Any

from research_package_repair_core import (
    markdown_findings,
    normalize_key,
    normalize_space,
    print_report,
    read_csv,
    resolve_package,
    write_csv,
)
from seo_cycle_core.reports import write_artifacts


PROMPT_PATTERNS = [
    re.compile(r"\b(create|generate|draw|make|show)\b.*\b(image|graphic|portrait|side[- ]by[- ]side|comparison)", re.I),
    re.compile(r"\busing this (portrait|photo|image)\b", re.I),
    re.compile(r"\bprompt\b.*\b(ai|image|generator)\b", re.I),
]


def rejection_reasons(row: dict[str, str]) -> list[str]:
    keyword = normalize_space(row.get("keyword") or row.get("query"))
    reasons: list[str] = []
    if any(pattern.search(keyword) for pattern in PROMPT_PATTERNS):
        reasons.append("prompt_like_query")
    if len(keyword) > 160 and "," in keyword:
        reasons.append("oversized_comma_query")
    if row.get("_extra_fields"):
        reasons.append("malformed_csv_extra_fields")
    if not normalize_key(keyword):
        reasons.append("empty_keyword")
    return reasons


def clean_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, Any]]]:
    clean: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    findings: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        reasons = rejection_reasons(row)
        normalized = {key: normalize_space(value) for key, value in row.items() if key != "_extra_fields"}
        if reasons:
            rejected_row = dict(normalized)
            rejected_row["rejection_reasons"] = "|".join(reasons)
            rejected.append(rejected_row)
            findings.append(
                {
                    "id": "semantic_core_rejected_row",
                    "severity": "warning",
                    "location": f"semantic-core.csv:{index}",
                    "message": f"Rejected `{normalized.get('keyword', '')}`: {', '.join(reasons)}",
                }
            )
        else:
            clean.append(normalized)
    return clean, rejected, findings


def build_report(package: pathlib.Path) -> dict[str, Any]:
    source = package / "semantic-core.csv"
    rows = read_csv(source)
    clean, rejected, findings = clean_rows(rows)
    return {
        "script": "semantic-core-clean",
        "source": str(source),
        "summary": {
            "total_rows": len(rows),
            "clean_rows": len(clean),
            "rejected_rows": len(rejected),
        },
        "outputs": {
            "cleaned_csv": "semantic-core.cleaned.csv",
            "rejected_csv": "semantic-core.rejected.csv",
            "json": "semantic-core-clean.json",
            "markdown": "semantic-core-clean.md",
        },
        "clean_rows": clean,
        "rejected_rows": rejected,
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return markdown_findings("Semantic Core Clean", report["summary"], report.get("findings"))


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    clean_rows_data = report["clean_rows"]
    rejected_rows_data = report["rejected_rows"]
    if clean_rows_data:
        write_csv(package / "semantic-core.cleaned.csv", clean_rows_data)
    else:
        write_csv(package / "semantic-core.cleaned.csv", [], ["keyword"])
    write_csv(package / "semantic-core.rejected.csv", rejected_rows_data, None)
    persist = {key: value for key, value in report.items() if key not in {"clean_rows", "rejected_rows"}}
    write_artifacts(
        text_files={package / "semantic-core-clean.md": render_markdown(report)},
        json_files={package / "semantic-core-clean.json": persist},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--write", action="store_true", help="Write cleaned/rejected CSV and reports")
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
