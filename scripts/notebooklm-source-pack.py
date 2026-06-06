#!/usr/bin/env python3
"""Ingest NotebookLM exports as curated expert evidence source packs."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.providers import notebooklm_health
from seo_cycle_core.source_artifacts import (
    compact_text,
    extract_urls,
    make_vector_record,
    read_cached_distillate,
    stable_cache_key,
    utc_now_iso,
    write_source_artifacts,
)


def read_optional_text(path: str | None) -> str | None:
    if not path:
        return None
    return pathlib.Path(path).expanduser().read_text(encoding="utf-8")


def heading_lines(text: str, limit: int = 20) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            headings.append(stripped.lstrip("#").strip())
        elif len(stripped) <= 120 and stripped.endswith(":"):
            headings.append(stripped.rstrip(":"))
        if len(headings) >= limit:
            break
    return headings


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    notebook_url = args.notebook_url or nested_get(cfg, "expert_sources.notebooklm_url") or "notebooklm"
    topic = args.topic or args.source_id or "expert-source-pack"
    region = args.region or nested_get(cfg, "locale.country") or "global"
    language = args.language or nested_get(cfg, "locale.language") or "ru"
    health = notebooklm_health(
        pathlib.Path(args.codex_config).expanduser(),
        tools_exposed=args.tools_exposed,
        notebook_url=notebook_url,
    )
    export_text = read_optional_text(args.export_file)
    if args.stdin_export:
        export_text = sys.stdin.read()

    cache_key = stable_cache_key(
        {
            "provider": "notebooklm",
            "topic": topic,
            "region": region,
            "language": language,
            "notebook_url": notebook_url,
            "source_id": args.source_id,
            "export_text": export_text or "",
        },
        label=topic,
    )
    cached = None if args.refresh else read_cached_distillate(project_root, "notebooklm", cache_key)
    if cached:
        return {
            "provider": "notebooklm",
            "status": "cache_hit",
            "generated_at": utc_now_iso(),
            "cache_key": cache_key,
            "topic": topic,
            "region": region,
            "language": language,
            "distillate": cached,
            "writes_to_site": False,
            "not_ranking_signal": True,
        }

    if export_text:
        status = "ready"
        summary = compact_text(export_text, max_chars=args.max_distillate_chars)
        citations = extract_urls(export_text)
        headings = heading_lines(export_text)
        raw_payload = {
            "provider": "notebooklm",
            "status": status,
            "collected_at": utc_now_iso(),
            "topic": topic,
            "region": region,
            "language": language,
            "source_id": args.source_id,
            "notebook_url": notebook_url,
            "access_mode": health["access_mode"],
            "export_text": export_text,
            "health": health,
        }
        distillate_payload = {
            "provider": "notebooklm",
            "status": status,
            "cache_key": cache_key,
            "topic": topic,
            "region": region,
            "language": language,
            "source_id": args.source_id,
            "notebook_url": notebook_url,
            "access_mode": health["access_mode"],
            "summary": summary,
            "headings": headings,
            "citations": citations,
            "source_role": "curated expert evidence with citations/source excerpts",
            "not_ranking_signal": True,
        }
    else:
        status = health["status"]
        summary = "NotebookLM export is not available. Use MCP if exposed, otherwise export/copy the source pack from the browser and rerun with --export-file or --stdin-export."
        citations = []
        raw_payload = {
            "provider": "notebooklm",
            "status": status,
            "created_at": utc_now_iso(),
            "topic": topic,
            "region": region,
            "language": language,
            "source_id": args.source_id,
            "notebook_url": notebook_url,
            "export_text": None,
            "health": health,
        }
        distillate_payload = {
            "provider": "notebooklm",
            "status": status,
            "cache_key": cache_key,
            "topic": topic,
            "region": region,
            "language": language,
            "source_id": args.source_id,
            "notebook_url": notebook_url,
            "access_mode": health["access_mode"],
            "summary": summary,
            "citations": citations,
            "source_role": "curated expert evidence with citations/source excerpts",
            "not_ranking_signal": True,
            "fallback": "browser_export/manual_export/source_pack_ingestion",
        }

    markdown = render_markdown(distillate_payload)
    vector_record = make_vector_record(
        provider="notebooklm",
        cache_key=cache_key,
        topic=topic,
        region=str(region),
        mode=str(distillate_payload.get("access_mode")),
        status=status,
        summary=summary[:1000],
        citations=citations,
        metadata={
            "language": language,
            "source_id": args.source_id,
            "notebook_url": notebook_url,
            "not_ranking_signal": True,
        },
    )
    paths: dict[str, str] = {}
    if args.write:
        paths = write_source_artifacts(
            project_root,
            "notebooklm",
            cache_key,
            raw_payload=raw_payload,
            distillate_markdown=markdown,
            distillate_payload=distillate_payload,
            vector_record=vector_record,
        )

    return {
        "provider": "notebooklm",
        "status": status,
        "generated_at": utc_now_iso(),
        "cache_key": cache_key,
        "topic": topic,
        "region": region,
        "language": language,
        "health": health,
        "distillate": distillate_payload,
        "paths": paths,
        "writes_to_site": False,
        "not_ranking_signal": True,
    }


def render_markdown(distillate: dict[str, Any]) -> str:
    lines = [
        "# NotebookLM Source Pack Distillate",
        "",
        f"- Topic: {distillate['topic']}",
        f"- Region: {distillate['region']}",
        f"- Language: {distillate['language']}",
        f"- Status: `{distillate['status']}`",
        f"- Access mode: `{distillate.get('access_mode')}`",
        f"- Notebook URL: {distillate.get('notebook_url')}",
        f"- Ranking signal: {not distillate.get('not_ranking_signal', True)}",
        f"- Cache key: `{distillate['cache_key']}`",
        "",
        "## Summary",
        distillate.get("summary") or "",
        "",
        "## Headings",
    ]
    headings = distillate.get("headings") or []
    lines.extend(f"- {item}" for item in headings) if headings else lines.append("- none")
    lines.append("")
    lines.append("## Citations")
    citations = distillate.get("citations") or []
    lines.extend(f"- {url}" for url in citations) if citations else lines.append("- none")
    lines.extend(["", "## Source Policy", distillate.get("source_role", "curated expert evidence only")])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--topic", help="Topic/source-pack label.")
    parser.add_argument("--region", help="Target country/region. Defaults to config locale.country.")
    parser.add_argument("--language", help="Target language. Defaults to config locale.language.")
    parser.add_argument("--source-id", help="Stable NotebookLM source identifier.")
    parser.add_argument("--notebook-url", help="NotebookLM notebook URL.")
    parser.add_argument("--codex-config", default="~/.codex/config.toml", help="Codex TOML config to inspect for NotebookLM MCP.")
    parser.add_argument("--tools-exposed", action="store_true", help="Mark NotebookLM MCP tools as visible in this session.")
    parser.add_argument("--export-file", help="NotebookLM export/notes/source-pack text file.")
    parser.add_argument("--stdin-export", action="store_true", help="Read NotebookLM export from stdin.")
    parser.add_argument("--max-distillate-chars", type=int, default=6000)
    parser.add_argument("--refresh", action="store_true", help="Ignore existing distillate cache.")
    parser.add_argument("--write", action="store_true", help="Write raw/distillate/vector artifacts.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.config:
        cfg_path = pathlib.Path(args.config).expanduser().resolve()
    else:
        found = find_config(pathlib.Path.cwd())
        if not found:
            print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        cfg_path = found.resolve()
    if not cfg_path.exists():
        print(f"ERROR: {cfg_path} not found", file=sys.stderr)
        return 2

    report = build_report(cfg_path, args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report["distillate"]), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
