#!/usr/bin/env python3
"""Report Yandex Direct readiness without making API calls."""

from __future__ import annotations

import datetime as dt
from typing import Any

from seo_cycle_core.ads import ads_config, env_status, platform_health_status, primary_platform
from seo_cycle_core.health import HealthSpec, render_sections, run_health

PLATFORM = "yandex_direct"
OFFICIAL_DOCS = [
    "https://yandex.ru/dev/direct/doc/dg/concepts/about.html",
    "https://yandex.ru/dev/direct/doc/reports/reports.html",
    "https://yandex.ru/dev/direct/doc/dg/concepts/sandbox.html",
]


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
    ]
    lines.extend(render_sections([
        ("Capabilities", report["capabilities"]),
        ("Guardrails", report["guardrails"]),
        ("Official Docs", report["official_docs"]),
    ]))
    return "\n".join(lines) + "\n"


SPEC = HealthSpec(
    slug="yandex-direct",
    style="simple",
    description=__doc__,
    write_help="Write seo/setup/yandex-direct-health.* artifacts.",
    build_report=build_report,
    render_markdown=render_markdown,
)

if __name__ == "__main__":
    raise SystemExit(run_health(SPEC))
