#!/usr/bin/env python3
"""Report WriterZen browser/export readiness without storing credentials."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, policy_path, project_root_for, rel_path
from seo_cycle_core.reports import write_report_bundle


PROVIDER = "writerzen"
CAPABILITIES = [
    "topic_discovery",
    "keyword_explorer",
    "keyword_planner",
    "keyword_clustering",
    "intent",
    "buying_journey",
    "serp_type",
    "brand_nonbrand",
    "allintitle",
    "kgr_golden_filter",
    "domain_focus",
    "plagiarism_export_fallback",
]
DEFAULT_IMPORT_DIR = "seo/research/writerzen/imports"
LOGIN_URL = "https://app.writerzen.net/"


def output_paths(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    return {
        "markdown": policy_path(cfg, project_root, "writerzen_health_report", "seo/setup/writerzen-health.md"),
        "json": policy_path(cfg, project_root, "writerzen_health_json", "seo/setup/writerzen-health.json"),
        "latest_markdown": policy_path(cfg, project_root, "latest_writerzen_health", "seo/setup/latest-writerzen-health.md"),
        "latest_json": policy_path(cfg, project_root, "latest_writerzen_health_json", "seo/setup/latest-writerzen-health.json"),
    }


def export_files(import_dir: pathlib.Path) -> list[pathlib.Path]:
    if not import_dir.exists():
        return []
    suffixes = {".csv", ".tsv", ".json", ".xlsx", ".md", ".txt"}
    return sorted(path for path in import_dir.iterdir() if path.is_file() and path.suffix.lower() in suffixes)


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    provider_cfg = cfg.get("writerzen_provider", {}) if isinstance(cfg.get("writerzen_provider"), dict) else {}
    configured_import_dir = provider_cfg.get("import_dir") or DEFAULT_IMPORT_DIR
    import_dir = rel_path(project_root, args.import_dir or configured_import_dir)
    exports = export_files(import_dir)
    browser_available = bool(args.browser_available)
    status = "available" if browser_available or exports else "browser_login_required"
    preferred_mode = "persistent_browser_export" if browser_available else "manual_browser_export"
    if exports and not browser_available:
        preferred_mode = "manual_export_ingestion"

    cache_policy = {
        "enabled": provider_cfg.get("cache_enabled", True),
        "key_parts": provider_cfg.get("cache_key_parts", ["topic", "region", "export_file", "mode", "export_hash"]),
        "raw_path": provider_cfg.get("raw_path", "seo/research/raw/writerzen/"),
        "distillate_path": provider_cfg.get("distillate_path", "seo/research/distillates/writerzen/"),
        "vector_path": provider_cfg.get("vector_path", "seo/research/vector/source_pack.jsonl"),
        "downstream_context": "distillate_only",
    }
    export_contract = {
        "import_dir": str(import_dir.relative_to(project_root)) if import_dir.is_relative_to(project_root) else str(import_dir),
        "supported_extensions": [".csv", ".tsv", ".json", ".xlsx", ".md", ".txt"],
        "recommended_exports": [
            "Topic Discovery CSV/XLSX",
            "Keyword Explorer CSV/XLSX",
            "Keyword Planner cluster CSV/XLSX",
            "Domain Focus competitor/export CSV/XLSX",
            "Plagiarism report only as fallback/manual evidence",
        ],
        "browser_collect_command": "python3 ./.codex/skills/seo-cycle/scripts/writerzen-browser-collect.py seo-cycle.yaml --topic \"<seed>\" --force-new-report --manual-fallback-seconds 120 --write",
        "ingest_command": "python3 ./.codex/skills/seo-cycle/scripts/writerzen-source-pack.py seo-cycle.yaml --export-file <writerzen-export.csv> --write",
    }
    return {
        "provider": PROVIDER,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "domain": nested_get(cfg, "project.domain"),
        "status": status,
        "preferred_mode": preferred_mode,
        "browser_session_available": browser_available,
        "import_dir_exists": import_dir.exists(),
        "export_files_detected": [path.name for path in exports],
        "capabilities": CAPABILITIES,
        "cache_policy": cache_policy,
        "export_contract": export_contract,
        "login_url": provider_cfg.get("login_url") or LOGIN_URL,
        "writes_to_site": False,
        "stores_password": False,
        "api_default": "no_public_api_browser_export",
        "paid_api_used": False,
        "fallback": "Use Google Suggest/Trends/GSC, XMLRiver, Serpstat, NeuronWriter and LLM multi-pass when WriterZen browser access is unavailable.",
        "paths": {key: str(path.relative_to(project_root)) for key, path in output_paths(cfg, project_root).items()},
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# WriterZen Provider Health",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- Preferred mode: `{report['preferred_mode']}`",
        f"- Browser session available: {report['browser_session_available']}",
        f"- Stores password: {report['stores_password']}",
        f"- API default: `{report['api_default']}`",
        f"- Login URL: {report['login_url']}",
        "",
        "## Capabilities",
    ]
    lines.extend(f"- {capability}" for capability in report["capabilities"])
    lines.extend(
        [
            "",
            "## Export Contract",
            f"- Import dir: `{report['export_contract']['import_dir']}`",
            f"- Supported extensions: {', '.join(report['export_contract']['supported_extensions'])}",
            f"- Browser collect command: `{report['export_contract']['browser_collect_command']}`",
            f"- Ingest command: `{report['export_contract']['ingest_command']}`",
            "",
            "## Detected Exports",
        ]
    )
    exports = report.get("export_files_detected") or []
    lines.extend(f"- {name}" for name in exports) if exports else lines.append("- none")
    lines.extend(
        [
            "",
            "## Cache Contract",
            f"- Key parts: {', '.join(report['cache_policy']['key_parts'])}",
            f"- Raw path: `{report['cache_policy']['raw_path']}`",
            f"- Distillate path: `{report['cache_policy']['distillate_path']}`",
            f"- Downstream context: `{report['cache_policy']['downstream_context']}`",
            "",
            "## Fallback",
            report["fallback"],
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--browser-available", action="store_true", help="Mark an already logged-in WriterZen browser/app session as usable.")
    parser.add_argument("--import-dir", help=f"Directory with WriterZen exports, default {DEFAULT_IMPORT_DIR}.")
    parser.add_argument("--write", action="store_true", help="Write seo/setup/writerzen-health.* artifacts.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    report = build_report(cfg_path, args)
    if args.write:
        write_report_bundle(output_paths(cfg, project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
