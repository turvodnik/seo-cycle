#!/usr/bin/env python3
"""Ingest Labrika technical audit exports as a source pack.

Labrika is useful for technical SEO reports, but this adapter intentionally
does not claim public API automation unless an export/API endpoint is provided.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.source_artifacts import (
    compact_text,
    extract_urls,
    make_vector_record,
    stable_cache_key,
    utc_now_iso,
    write_source_artifacts,
)
from seo_cycle_core.technical_artifacts import technical_paths, rel_paths
from seo_cycle_core.config import write_text


def read_text(path: str | None) -> str | None:
    if not path:
        return None
    return pathlib.Path(path).expanduser().read_text(encoding="utf-8")


def headings(text: str) -> list[str]:
    rows: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            rows.append(stripped.lstrip("#").strip())
        elif len(rows) < 8 and stripped.endswith(":") and len(stripped) < 90:
            rows.append(stripped[:-1].strip())
        if len(rows) >= 12:
            break
    return rows


def risk_terms(text: str) -> list[str]:
    lowered = text.lower()
    terms = []
    catalog = {
        "broken_links": ["broken link", "бит", "404", "not found"],
        "duplicate_titles": ["duplicate title", "дубли", "duplicate titles"],
        "redirect_chains": ["redirect chain", "цепоч", "301", "302"],
        "meta_descriptions": ["description", "meta description", "дескрип"],
        "performance": ["core web vitals", "lcp", "cls", "speed", "скорост"],
        "indexability": ["noindex", "robots", "canonical", "индекс"],
    }
    for key, patterns in catalog.items():
        if any(pattern in lowered for pattern in patterns):
            terms.append(key)
    return terms


def render_markdown(distillate: dict[str, Any]) -> str:
    lines = [
        "# Labrika Technical Source Pack",
        "",
        f"- Domain: {distillate['domain']}",
        f"- Status: `{distillate['status']}`",
        f"- Source type: `{distillate['source_type']}`",
        f"- Cache key: `{distillate['cache_key']}`",
        "",
        "## Summary",
        distillate.get("summary") or "",
        "",
        "## Detected Risk Terms",
    ]
    terms = distillate.get("risk_terms") or []
    lines.extend(f"- {term}" for term in terms) if terms else lines.append("- none")
    lines.extend(["", "## Citations"])
    citations = distillate.get("citations") or []
    lines.extend(f"- {url}" for url in citations) if citations else lines.append("- none")
    if distillate.get("fallback"):
        lines.extend(["", "## Fallback", distillate["fallback"]])
    lines.extend(["", "## Source Policy", distillate.get("source_policy", "Use distillate only downstream.")])
    return "\n".join(lines) + "\n"


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    domain = args.domain or nested_get(cfg, "project.domain") or ""
    raw_text = read_text(args.export_file)
    source_type = "manual_export" if raw_text else "unavailable"
    cache_key = stable_cache_key(
        {"provider": "labrika", "domain": domain, "source_type": source_type, "export": raw_text or ""},
        label=domain or "labrika",
    )

    if raw_text:
        status = "ready"
        summary = compact_text(raw_text, max_chars=args.max_distillate_chars)
        citations = extract_urls(raw_text)
        raw_payload = {
            "provider": "labrika",
            "status": status,
            "domain": domain,
            "source_type": source_type,
            "collected_at": utc_now_iso(),
            "export_text": raw_text,
        }
        distillate = {
            "provider": "labrika",
            "status": status,
            "cache_key": cache_key,
            "domain": domain,
            "source_type": source_type,
            "summary": summary,
            "headings": headings(raw_text),
            "risk_terms": risk_terms(raw_text),
            "citations": citations,
            "source_policy": "Labrika export is third-party technical evidence; keep raw export out of LLM context.",
        }
    else:
        status = "fallback_required"
        summary = "No Labrika export supplied. Use browser/manual export from Labrika and rerun with --export-file."
        raw_payload = {
            "provider": "labrika",
            "status": status,
            "domain": domain,
            "source_type": source_type,
            "created_at": utc_now_iso(),
            "export_text": None,
        }
        distillate = {
            "provider": "labrika",
            "status": status,
            "cache_key": cache_key,
            "domain": domain,
            "source_type": source_type,
            "summary": summary,
            "headings": [],
            "risk_terms": [],
            "citations": ["https://labrika.com/seo-auditor"],
            "fallback": "Public Labrika API documentation was not found. Treat Labrika as manual/browser export source until support provides API/export details.",
            "source_policy": "No live Labrika API call was made.",
        }

    markdown = render_markdown(distillate)
    paths: dict[str, str] = {}
    if args.write:
        paths = write_source_artifacts(
            project_root,
            "labrika",
            cache_key,
            raw_payload=raw_payload,
            distillate_markdown=markdown,
            distillate_payload=distillate,
            vector_record=make_vector_record(
                provider="labrika",
                cache_key=cache_key,
                topic=domain,
                region=str(nested_get(cfg, "locale.country") or ""),
                mode=source_type,
                status=status,
                summary=summary[:1000],
                citations=distillate.get("citations") or [],
                metadata={"not_api_automated": True, "risk_terms": distillate.get("risk_terms") or []},
            ),
        )
        tech = technical_paths(project_root, "labrika-source-pack")
        write_text(tech["markdown"], markdown)
        write_text(tech["json"], json.dumps(distillate, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        write_text(tech["latest_markdown"], markdown)
        write_text(tech["latest_json"], json.dumps(distillate, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    return {
        "audit_id": "labrika-source-pack",
        "provider": "labrika",
        "status": status,
        "source_type": source_type,
        "generated_at": utc_now_iso(),
        "domain": domain,
        "summary": {"domain": domain, "source_type": source_type, "risk_terms": len(distillate.get("risk_terms") or [])},
        "distillate": distillate,
        "paths": paths,
        "technical_paths": rel_paths(project_root, technical_paths(project_root, "labrika-source-pack")),
        "writes_to_site": False,
        "paid_api_used": False,
        "api_status": "manual_export_until_public_api_is_confirmed",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--domain", help="Domain represented by this Labrika export.")
    parser.add_argument("--export-file", help="Labrika report export in markdown/text/html-converted-to-text.")
    parser.add_argument("--max-distillate-chars", type=int, default=6000)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()
    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    report = build_report(cfg_path, args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Labrika source pack status: {report['status']}")
        print(f"Latest: {report.get('paths', {}).get('latest_markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
