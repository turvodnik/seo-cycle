#!/usr/bin/env python3
"""Report Google Merchant Center readiness without making API calls.

For `region_profile: ru` a missing Merchant setup is `region_limited` — Google
Shopping is suspended for RF stores, the expected product-feed channel is
Yandex (see yml-feed-audit.py for the local YML validator).
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

from seo_cycle_core.health import HealthSpec, render_sections, run_health

ENV_NAMES = ["GOOGLE_MERCHANT_ACCOUNT_ID", "GOOGLE_APPLICATION_CREDENTIALS"]
OFFICIAL_DOCS = [
    "https://developers.google.com/shopping-content/guides/quickstart",
    "https://support.google.com/merchants/answer/6363310",
]


def build_report(cfg: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in ENV_NAMES if not os.environ.get(name)]
    region_ru = str(cfg.get("region_profile") or "").lower() == "ru"
    if not missing:
        status = "available"
    elif region_ru:
        status = "region_limited"
    else:
        status = "needs_credentials"
    return {
        "provider": "google_merchant",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "status": status,
        "region_note": (
            "Google Shopping is suspended for RF stores; region_limited is expected. "
            "Use yml-feed-audit.py for the Yandex product feed instead."
        ) if region_ru and missing else "",
        "env_names": ENV_NAMES,
        "missing_env": missing,
        "credentials_present": not missing,
        "api_default": "read_only_statuses_behind_live_flag",
        "writes_to_platform": False,
        "stores_password": False,
        "capabilities": [
            "account-level issues via Content API accountstatuses",
            "product disapprovals with reasons via productstatuses",
            "offline mode: ingest a saved statuses export via --input-file",
        ],
        "guardrails": [
            "No live HTTP/API call in health check.",
            "merchant-fetch.py defaults to --input-file/cache; --live is read-only statuses.",
            "Feed writes/uploads are out of scope: fix the source feed, not the API.",
        ],
        "official_docs": OFFICIAL_DOCS,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Google Merchant Provider Health",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
    ]
    if report["region_note"]:
        lines.append(f"- Note: {report['region_note']}")
    lines.extend(
        [
            f"- Env names: {', '.join(f'`{name}`' for name in report['env_names'])}"
            + (f" (missing: {', '.join(report['missing_env'])})" if report["missing_env"] else ""),
        ]
    )
    lines.extend(render_sections([
        ("Capabilities", report["capabilities"]),
        ("Guardrails", report["guardrails"]),
        ("Official Docs", report["official_docs"]),
    ]))
    return "\n".join(lines) + "\n"


SPEC = HealthSpec(
    slug="merchant",
    style="simple",
    description=__doc__,
    write_help="Write seo/setup/merchant-health.* artifacts.",
    build_report=build_report,
    render_markdown=render_markdown,
)

if __name__ == "__main__":
    raise SystemExit(run_health(SPEC))
