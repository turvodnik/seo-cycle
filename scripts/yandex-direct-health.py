#!/usr/bin/env python3
"""Report Yandex Direct readiness without making API calls."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.ads import ads_config, env_status, platform_health_status, primary_platform
from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.reports import write_report_bundle

PLATFORM = "yandex_direct"
OFFICIAL_DOCS = [
    "https://yandex.ru/dev/direct/doc/dg/concepts/about.html",
    "https://yandex.ru/dev/direct/doc/reports/reports.html",
    "https://yandex.ru/dev/direct/doc/dg/concepts/sandbox.html",
]


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "setup"
    return {
        "markdown": base / "yandex-direct-health.md",
        "json": base / "yandex-direct-health.json",
        "latest_markdown": base / "latest-yandex-direct-health.md",
        "latest_json": base / "latest-yandex-direct-health.json",
    }


def build_report(cfg: dict[str, Any]) -> dict[str, Any]:
    ads = ads_config(cfg)
    env = env_status(PLATFORM)
    return {
        "provider": PLATFORM,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "status": platform_health_status(cfg, PLATFORM),
        "ads_enabled": bool(ads.get("enabled")),
        "platform_enabled": bool(ads.get(PLATFORM, {}).get("enabled")),
        "primary_platform": primary_platform(cfg),
        "sandbox": bool(ads.get(PLATFORM, {}).get("sandbox")),
        "env_names": env["required"],
        "optional_env_names": env["optional"],
        "missing_env": env["missing"],
        "credentials_present": env["present"],
        "api_default": "read_only_fetch_behind_live_flag",
        "writes_to_platform": "only via ads-apply.py with approved ticket + --live --allow-write",
        "stores_password": False,
        "capabilities": [
            "campaigns/adgroups/keywords via Direct API v5 (JSON)",
            "performance stats and search queries via Reports API (TSV, offline mode)",
            "sandbox host support for safe apply rehearsal",
            "draft campaigns from the semantic core via ads-draft-builder.py",
        ],
        "guardrails": [
            "No live HTTP/API call in health check.",
            "yandex-direct-fetch.py defaults to cache/--input-file; --live requires usage-ledger preflight.",
            "ads-apply.py requires an approved ads ticket, --live --allow-write, and per-run change caps.",
            "Budgets are frozen unless ads.apply.max_daily_budget > 0.",
        ],
        "official_docs": OFFICIAL_DOCS,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Yandex Direct Provider Health",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- Ads layer enabled: {report['ads_enabled']} · platform enabled: {report['platform_enabled']}",
        f"- Primary platform: `{report['primary_platform']}`",
        f"- Sandbox: {report['sandbox']}",
        f"- Env names: {', '.join(f'`{name}`' for name in report['env_names'])}"
        + (f" (missing: {', '.join(report['missing_env'])})" if report["missing_env"] else ""),
        f"- API default: `{report['api_default']}`",
        "",
        "## Capabilities",
    ]
    lines.extend(f"- {item}" for item in report["capabilities"])
    lines.extend(["", "## Guardrails"])
    lines.extend(f"- {item}" for item in report["guardrails"])
    lines.extend(["", "## Official Docs"])
    lines.extend(f"- {url}" for url in report["official_docs"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write seo/setup/yandex-direct-health.* artifacts.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    report = build_report(cfg)
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
