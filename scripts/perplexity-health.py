#!/usr/bin/env python3
"""Report Perplexity provider availability without storing credentials."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
from typing import Any

from seo_cycle_core.config import load_yaml, policy_path, project_root_for
from seo_cycle_core.health import HealthSpec, run_health
from seo_cycle_core.providers import perplexity_health


def output_paths(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    return {
        "markdown": policy_path(cfg, project_root, "perplexity_health_report", "seo/setup/perplexity-health.md"),
        "json": policy_path(cfg, project_root, "perplexity_health_json", "seo/setup/perplexity-health.json"),
        "latest_markdown": policy_path(cfg, project_root, "latest_perplexity_health", "seo/setup/latest-perplexity-health.md"),
        "latest_json": policy_path(cfg, project_root, "latest_perplexity_health_json", "seo/setup/latest-perplexity-health.json"),
    }


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    app_paths = [pathlib.Path(path).expanduser() for path in args.app_path] if args.app_path else None
    health = perplexity_health(app_paths=app_paths, browser_available=args.browser_available)
    provider_cfg = cfg.get("perplexity_provider", {}) if isinstance(cfg.get("perplexity_provider"), dict) else {}
    cache_policy = {
        "enabled": provider_cfg.get("cache_enabled", True),
        "key_parts": ["topic", "region", "prompt_version", "mode"],
        "raw_path": "seo/research/raw/perplexity/<cache_key>.json",
        "distillate_path": "seo/research/distillates/perplexity/<cache_key>.md",
        "downstream_context": "distillate_with_citations_only",
    }
    status = health["status"]
    if status != "available":
        status = "degraded_source"
    return {
        "provider": "perplexity",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "status": status,
        "health": health,
        "cache_policy": cache_policy,
        "writes_to_site": False,
        "stores_password": False,
        "api_default": "disabled",
        "fallback": "Codex/Antigravity/NotebookLM/manual browser export",
        "paths": {key: str(path.relative_to(project_root)) for key, path in output_paths(cfg, project_root).items()},
    }


def render_markdown(report: dict[str, Any]) -> str:
    health = report["health"]
    lines = [
        "# Perplexity Provider Health",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- Preferred mode: `{health.get('preferred_mode')}`",
        f"- App detected: {health.get('app_detected')}",
        f"- Browser session available: {health.get('browser_available')}",
        f"- API key present: {health.get('api_optional')}",
        f"- Stores password: {health.get('stores_password')}",
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
    return "\n".join(lines) + "\n"


SPEC = HealthSpec(
    slug="perplexity",
    style="policy",
    write_help="Write seo/setup/perplexity-health.* artifacts.",
    build_report=build_report,
    render_markdown=render_markdown,
    output_paths=output_paths,
    extra_arguments=[
        {"flags": ("--browser-available",), "action": "store_true",
         "help": "Mark an already logged-in browser/app session as usable."},
        {"flags": ("--app-path",), "action": "append", "default": [],
         "help": "Additional Perplexity.app path to test."},
    ],
)

if __name__ == "__main__":
    raise SystemExit(run_health(SPEC))
