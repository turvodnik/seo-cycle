#!/usr/bin/env python3
"""Report NotebookLM MCP/browser-export readiness for expert evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
from typing import Any

from seo_cycle_core.config import load_yaml, nested_get, policy_path, project_root_for
from seo_cycle_core.health import HealthSpec, run_health
from seo_cycle_core.providers import notebooklm_health


def output_paths(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    return {
        "markdown": policy_path(cfg, project_root, "notebooklm_health_report", "seo/setup/notebooklm-health.md"),
        "json": policy_path(cfg, project_root, "notebooklm_health_json", "seo/setup/notebooklm-health.json"),
        "latest_markdown": policy_path(cfg, project_root, "latest_notebooklm_health", "seo/setup/latest-notebooklm-health.md"),
        "latest_json": policy_path(cfg, project_root, "latest_notebooklm_health_json", "seo/setup/latest-notebooklm-health.json"),
    }


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    notebook_url = args.notebook_url or nested_get(cfg, "expert_sources.notebooklm_url")
    health = notebooklm_health(
        pathlib.Path(args.codex_config).expanduser(),
        tools_exposed=args.tools_exposed,
        notebook_url=notebook_url,
    )
    return {
        "provider": "notebooklm",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "status": health["status"],
        "health": health,
        "source_role": "curated expert evidence only",
        "not_ranking_signal": True,
        "fallback_order": ["mcp", "browser_export", "manual_export", "source_pack_ingestion"],
        "writes_to_site": False,
        "paths": {key: str(path.relative_to(project_root)) for key, path in output_paths(cfg, project_root).items()},
    }


def render_markdown(report: dict[str, Any]) -> str:
    health = report["health"]
    lines = [
        "# NotebookLM Provider Health",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- Configured: {health.get('configured')}",
        f"- Tools exposed: {health.get('tools_exposed')}",
        f"- Access mode: `{health.get('access_mode')}`",
        f"- Notebook URL: {health.get('notebook_url') or 'not configured'}",
        f"- Ranking signal: {health.get('ranking_signal')}",
        "",
        "## Disabled Tools",
    ]
    disabled = health.get("disabled_tools") or []
    lines.extend(f"- `{item}`" for item in disabled) if disabled else lines.append("No disabled tools detected in config.")
    lines.extend(
        [
            "",
            "## Use Policy",
            "- Use NotebookLM only as curated expert evidence with citations/source excerpts.",
            "- Do not use it for volume, KD, ranking signals, or automatic page publishing.",
            "- If MCP tools are not exposed, use browser/manual export and ingest a source pack.",
        ]
    )
    return "\n".join(lines) + "\n"


SPEC = HealthSpec(
    slug="notebooklm",
    style="policy",
    write_help="Write seo/setup/notebooklm-health.* artifacts.",
    build_report=build_report,
    render_markdown=render_markdown,
    output_paths=output_paths,
    extra_arguments=[
        {"flags": ("--codex-config",), "default": "~/.codex/config.toml",
         "help": "Codex TOML config to inspect for NotebookLM MCP."},
        {"flags": ("--tools-exposed",), "action": "store_true",
         "help": "Mark NotebookLM MCP tools as visible in the current session."},
        {"flags": ("--notebook-url",), "help": "NotebookLM SEO notebook URL."},
    ],
)

if __name__ == "__main__":
    raise SystemExit(run_health(SPEC))
