#!/usr/bin/env python3
"""Find internal-link orphan URLs and create a backlog repair CSV."""

from __future__ import annotations

import argparse
import pathlib
from typing import Any

from research_package_repair_core import (
    as_list,
    clusters_from_architecture,
    extract_urls,
    load_architecture,
    markdown_findings,
    normalize_url,
    print_report,
    read_csv,
    resolve_package,
    slugify,
    write_csv,
)
from seo_cycle_core.reports import write_artifacts


def known_urls(package: pathlib.Path, architecture: dict[str, Any]) -> set[str]:
    urls = set()
    for cluster in clusters_from_architecture(architecture):
        for field in ("suggested_url", "url"):
            url = normalize_url(cluster.get(field))
            if url:
                urls.add(url)
    for row in read_csv(package / "content-plan.csv"):
        for field in ("url", "suggested_url", "target_url"):
            url = normalize_url(row.get(field))
            if url:
                urls.add(url)
    return urls


def referenced_urls(package: pathlib.Path, architecture: dict[str, Any]) -> set[str]:
    urls = set()
    for cluster in clusters_from_architecture(architecture):
        for url in as_list(cluster.get("internal_links")):
            normalized = normalize_url(url)
            if normalized:
                urls.add(normalized)
    for row in read_csv(package / "content-plan.csv"):
        for url in as_list(row.get("internal_links")):
            normalized = normalize_url(url)
            if normalized:
                urls.add(normalized)
    for name in ("site-structure.md", "README.md", "final-clusters.md"):
        path = package / name
        if path.exists():
            urls.update(extract_urls(path.read_text(encoding="utf-8")))
    return urls


def title_from_url(url: str) -> str:
    slug = url.strip("/").split("/")[-1]
    return slug.replace("-", " ").title()


def backlog_rows(orphans: list[str]) -> list[dict[str, str]]:
    rows = []
    for url in orphans:
        title = title_from_url(url)
        rows.append(
            {
                "priority": "P3",
                "mvp": "False",
                "url": url,
                "page_title": title,
                "primary_keyword": title.lower(),
                "page_type": "Guide" if url.startswith("/guides/") else "Landing",
                "source_cluster": slugify(title),
                "status": "backlog_from_orphan_url",
                "action": "create_backlog_row" if url.startswith(("/guides/", "/hair-color/", "/hairstyles/")) else "remove_or_replace_link",
            }
        )
    return rows


def build_report(package: pathlib.Path) -> dict[str, Any]:
    architecture = load_architecture(package)
    known = known_urls(package, architecture)
    referenced = referenced_urls(package, architecture)
    orphans = sorted(url for url in referenced if url and url not in known)
    rows = backlog_rows(orphans)
    findings = [
        {
            "id": "orphan_internal_url",
            "severity": "warning",
            "location": url,
            "message": "Internal link target is referenced but has no cluster/content-plan row.",
        }
        for url in orphans
    ]
    return {
        "script": "orphan-url-resolver",
        "summary": {
            "known_urls": len(known),
            "referenced_urls": len(referenced),
            "orphan_urls": len(orphans),
        },
        "outputs": {
            "backlog_csv": "content-plan.orphan-backlog.csv",
            "json": "orphan-url-resolver.json",
            "markdown": "orphan-url-resolver.md",
        },
        "backlog_rows": rows,
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return markdown_findings("Orphan URL Resolver", report["summary"], report.get("findings"))


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    write_csv(package / "content-plan.orphan-backlog.csv", report["backlog_rows"])
    persist = {key: value for key, value in report.items() if key != "backlog_rows"}
    write_artifacts(
        text_files={package / "orphan-url-resolver.md": render_markdown(report)},
        json_files={package / "orphan-url-resolver.json": persist},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--write", action="store_true", help="Write orphan backlog CSV and reports")
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
