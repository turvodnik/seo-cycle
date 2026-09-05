#!/usr/bin/env python3
"""Report Google Ads readiness without making API calls.

For `region_profile: ru` projects a missing Google Ads setup is reported as
`region_limited` — an expected state, not an error: Yandex Direct is the
primary paid channel and Google Ads campaign drafts can still be exported as
Google Ads Editor CSV.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from seo_cycle_core.ads import ads_config, env_status, platform_health_status, primary_platform, region_limited
from seo_cycle_core.health import HealthSpec, render_sections, run_health

PLATFORM = "google_ads"
OFFICIAL_DOCS = [
    "https://developers.google.com/google-ads/api/docs/start",
    "https://developers.google.com/google-ads/api/docs/rest/overview",
    "https://developers.google.com/google-ads/api/docs/best-practices/quotas",
]


def build_report(cfg: dict[str, Any]) -> dict[str, Any]:
    ads = ads_config(cfg)
    env = env_status(PLATFORM)
    limited = region_limited(cfg, PLATFORM)
    return {
        "provider": PLATFORM,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "status": platform_health_status(cfg, PLATFORM),
        "region_limited": limited,
        "region_note": (
            "Google Ads is restricted for RF projects; this status is expected, not an error. "
            "Primary paid channel is yandex_direct; drafts export to Google Ads Editor CSV."
        ) if limited else "",
        "ads_enabled": bool(ads.get("enabled")),
        "platform_enabled": bool(ads.get(PLATFORM, {}).get("enabled")),
        "apply_enabled": bool(ads.get(PLATFORM, {}).get("apply_enabled")),
        "primary_platform": primary_platform(cfg),
        "env_names": env["required"],
        "optional_env_names": env["optional"],
        "missing_env": env["missing"],
        "credentials_present": env["present"],
        "api_default": "read_only_gaql_behind_live_flag",
        "writes_to_platform": "disabled by default (ads.google_ads.apply_enabled: false); CSV export instead",
        "stores_password": False,
        "capabilities": [
            "campaigns/ad groups/keywords/search terms/metrics via REST GAQL search",
            "recommendations API (read-only)",
            "OAuth refresh-token flow via urllib (no SDK dependency)",
            "draft campaigns as JSON + Google Ads Editor CSV export",
        ],
        "guardrails": [
            "No live HTTP/API call in health check.",
            "google-ads-fetch.py defaults to cache/--input-file; --live requires usage-ledger preflight.",
            "API writes stay disabled unless ads.google_ads.apply_enabled is set after review.",
            "region_profile: ru → region_limited is the expected status.",
        ],
        "official_docs": OFFICIAL_DOCS,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Google Ads Provider Health",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
    ]
    if report["region_note"]:
        lines.append(f"- Note: {report['region_note']}")
    lines.extend(
        [
            f"- Ads layer enabled: {report['ads_enabled']} · platform enabled: {report['platform_enabled']}"
            f" · apply enabled: {report['apply_enabled']}",
            f"- Primary platform: `{report['primary_platform']}`",
            f"- Env names: {', '.join(f'`{name}`' for name in report['env_names'])}"
            + (f" (missing: {', '.join(report['missing_env'])})" if report["missing_env"] else ""),
            f"- API default: `{report['api_default']}`",
        ]
    )
    lines.extend(render_sections([
        ("Capabilities", report["capabilities"]),
        ("Guardrails", report["guardrails"]),
        ("Official Docs", report["official_docs"]),
    ]))
    return "\n".join(lines) + "\n"


SPEC = HealthSpec(
    slug="google-ads",
    style="simple",
    description=__doc__,
    write_help="Write seo/setup/google-ads-health.* artifacts.",
    build_report=build_report,
    render_markdown=render_markdown,
)

if __name__ == "__main__":
    raise SystemExit(run_health(SPEC))
