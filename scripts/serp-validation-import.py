#!/usr/bin/env python3
"""Import reviewed SERP validation exports into semantic architecture.

This is intentionally guarded: the script does not call live APIs. It accepts
manual/DataForSEO/Serpstat exports that were already reviewed and writes them
back into semantic-architecture-final.json only with --write.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

from research_package_repair_core import (
    as_list,
    architecture_path,
    load_architecture,
    markdown_findings,
    normalize_space,
    print_report,
    read_csv,
    resolve_package,
    write_json,
)
from seo_cycle_core.reports import write_artifacts


def list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [normalize_space(item) for item in value if normalize_space(item)]
    text = normalize_space(value)
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [normalize_space(item) for item in parsed if normalize_space(item)]
    return as_list(text)


def load_json_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("items", "rows", "results", "data"):
        rows = data.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return [data]


def load_input_rows(input_json: str | None, input_csv: str | None) -> tuple[pathlib.Path | None, list[dict[str, Any]]]:
    if input_json:
        path = pathlib.Path(input_json).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"ERROR: input JSON not found: {path}")
        return path, load_json_rows(path)
    if input_csv:
        path = pathlib.Path(input_csv).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"ERROR: input CSV not found: {path}")
        return path, read_csv(path)
    return None, []


def first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and normalize_space(row.get(key)):
            return row.get(key)
    return ""


def normalized_record(
    row: dict[str, Any],
    *,
    source_file: pathlib.Path | None,
    provider_default: str,
    country_default: str,
    language_default: str,
    device_default: str,
    imported_at: str,
) -> dict[str, Any] | None:
    keyword = normalize_space(first_value(row, "keyword", "query", "search_query", "phrase"))
    if not keyword:
        return None
    record = {
        "provider": normalize_space(first_value(row, "provider", "source")) or provider_default,
        "country": normalize_space(first_value(row, "country", "location_code", "location")) or country_default,
        "language": normalize_space(first_value(row, "language", "language_code", "lang")) or language_default,
        "device": normalize_space(first_value(row, "device")) or device_default,
        "features": list_value(first_value(row, "features", "serp_features", "dataforseo_serp_features")),
        "top_urls": list_value(first_value(row, "top_urls", "urls", "organic_urls", "serp_urls")),
        "top_titles": list_value(first_value(row, "top_titles", "titles", "organic_titles", "serp_titles")),
        "dominant_page_type": normalize_space(first_value(row, "dominant_page_type", "page_type", "serp_page_type")),
        "notes": normalize_space(first_value(row, "notes", "note", "comment")),
        "imported_at": imported_at,
    }
    if source_file:
        record["source_file"] = str(source_file)
    return {"keyword": keyword, "record": record}


def validation_is_empty(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return True
    for field in ("features", "top_urls", "top_titles", "items", "results"):
        field_value = value.get(field)
        if isinstance(field_value, list) and field_value:
            return False
    return not any(normalize_space(value.get(field)) for field in ("dominant_page_type", "notes"))


def utc_now() -> str:
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_report(
    package: pathlib.Path,
    *,
    input_json: str | None,
    input_csv: str | None,
    provider: str,
    country: str,
    language: str,
    device: str,
    write: bool,
    force: bool,
) -> dict[str, Any]:
    source_file, rows = load_input_rows(input_json, input_csv)
    architecture = load_architecture(package)
    imported_at = utc_now()
    validation = architecture.setdefault("dataforseo_serp_validation", {})
    if not isinstance(validation, dict):
        validation = {}
        architecture["dataforseo_serp_validation"] = validation

    imported: list[dict[str, Any]] = []
    skipped_existing: list[str] = []
    skipped_missing_keyword = 0
    for row in rows:
        normalized = normalized_record(
            row,
            source_file=source_file,
            provider_default=provider,
            country_default=country,
            language_default=language,
            device_default=device,
            imported_at=imported_at,
        )
        if normalized is None:
            skipped_missing_keyword += 1
            continue
        keyword = normalized["keyword"]
        existing = validation.get(keyword)
        if existing is not None and not force and not validation_is_empty(existing):
            skipped_existing.append(keyword)
            continue
        validation[keyword] = normalized["record"]
        imported.append({"keyword": keyword, **normalized["record"]})

    metadata = architecture.setdefault("metadata", {})
    if isinstance(metadata, dict):
        sources = metadata.setdefault("sources", {})
        if isinstance(sources, dict):
            sources["serp_validation_import"] = {
                "last_imported_at": imported_at,
                "source_file": str(source_file) if source_file else "",
                "imported_queries": len(imported),
                "skipped_existing": len(skipped_existing),
                "force": force,
            }

    findings = []
    if not source_file:
        findings.append(
            {
                "id": "serp_validation_import_missing_source",
                "severity": "warning",
                "location": str(package),
                "message": "No --input-json or --input-csv was supplied; live API imports are intentionally disabled.",
            }
        )
    if skipped_existing:
        findings.append(
            {
                "id": "serp_validation_existing_skipped",
                "severity": "info",
                "location": ", ".join(skipped_existing[:8]),
                "message": "Existing non-empty SERP validation was preserved. Use --force only after review.",
            }
        )

    report = {
        "script": "serp-validation-import",
        "package": str(package),
        "source_file": str(source_file) if source_file else "",
        "summary": {
            "input_rows": len(rows),
            "imported_queries": len(imported),
            "skipped_existing": len(skipped_existing),
            "skipped_missing_keyword": skipped_missing_keyword,
            "write": write,
            "force": force,
        },
        "imported": imported,
        "skipped_existing": skipped_existing,
        "findings": findings,
        "outputs": {
            "architecture": "semantic-architecture-final.json",
            "json": "serp-validation-import.json",
            "markdown": "serp-validation-import.md",
        },
    }
    if write:
        write_json(architecture_path(package), architecture)
        write_outputs(package, report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SERP Validation Import",
        "",
        f"- Package: `{report['package']}`",
        f"- Source file: `{report.get('source_file') or 'none'}`",
        f"- Input rows: `{report['summary']['input_rows']}`",
        f"- Imported queries: `{report['summary']['imported_queries']}`",
        f"- Skipped existing: `{report['summary']['skipped_existing']}`",
        f"- Skipped missing keyword: `{report['summary']['skipped_missing_keyword']}`",
        f"- Write mode: `{report['summary']['write']}`",
        f"- Force overwrite: `{report['summary']['force']}`",
        "",
    ]
    if report.get("imported"):
        lines.extend(["## Imported Queries", ""])
        for item in report["imported"]:
            lines.append(f"- `{item.get('keyword')}`: {item.get('provider')} / {item.get('dominant_page_type') or 'page type not supplied'}")
        lines.append("")
    findings_md = markdown_findings("SERP Validation Import Findings", {}, report.get("findings"))
    if report.get("findings"):
        lines.extend(findings_md.splitlines())
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(package: pathlib.Path, report: dict[str, Any]) -> None:
    write_artifacts(
        text_files={package / "serp-validation-import.md": render_markdown(report)},
        json_files={package / "serp-validation-import.json": report},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Research package directory")
    parser.add_argument("--input-json", help="Reviewed JSON export from DataForSEO, Serpstat, or manual SERP review")
    parser.add_argument("--input-csv", help="Reviewed CSV export from DataForSEO, Serpstat, or manual SERP review")
    parser.add_argument("--provider", default="manual")
    parser.add_argument("--country", default="US")
    parser.add_argument("--language", default="en")
    parser.add_argument("--device", default="desktop")
    parser.add_argument("--force", action="store_true", help="Overwrite non-empty existing validation after manual review")
    parser.add_argument("--write", action="store_true", help="Write semantic-architecture-final.json and import reports")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    args = parser.parse_args()

    package = resolve_package(args.package)
    report = build_report(
        package,
        input_json=args.input_json,
        input_csv=args.input_csv,
        provider=args.provider,
        country=args.country,
        language=args.language,
        device=args.device,
        write=args.write,
        force=args.force,
    )
    print_report(report, args.format, render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
