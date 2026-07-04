#!/usr/bin/env python3
"""Report Google Business Profile API readiness without making API calls.

GBP API access is gated by Google's OAuth verification for the
business.manage scope — a real approval process, not just keys. Until it is
granted the honest status is `needs_oauth_verification`, and the working path
stays the browser workflow (prompts/local/google-maps.md via Chrome MCP) plus
manual exports ingested by `gbp-fetch.py --input-file`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.reports import write_report_bundle

OAUTH_ENV = ["GBP_OAUTH_CLIENT_ID", "GBP_OAUTH_CLIENT_SECRET", "GBP_OAUTH_REFRESH_TOKEN"]
ID_ENV = ["GOOGLE_BUSINESS_ACCOUNT_ID", "GOOGLE_BUSINESS_LOCATION_ID"]
OFFICIAL_DOCS = [
    "https://developers.google.com/my-business/content/prereqs",
    "https://developers.google.com/my-business/content/review-data",
    "https://support.google.com/business/answer/7107242",
]


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "setup"
    return {
        "markdown": base / "gbp-health.md",
        "json": base / "gbp-health.json",
        "latest_markdown": base / "latest-gbp-health.md",
        "latest_json": base / "latest-gbp-health.json",
    }


def build_report(cfg: dict[str, Any]) -> dict[str, Any]:
    oauth_missing = [name for name in OAUTH_ENV if not os.environ.get(name)]
    id_missing = [name for name in ID_ENV if not os.environ.get(name)]
    if not oauth_missing and not id_missing:
        status = "available"
    elif oauth_missing:
        status = "needs_oauth_verification"
    else:
        status = "needs_credentials"
    gbp_url = str(((cfg.get("business_profile") or {}) if isinstance(cfg.get("business_profile"), dict) else {}).get("gbp_url") or "")
    return {
        "provider": "google_business_profile",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "status": status,
        "gbp_url": gbp_url,
        "oauth_env": OAUTH_ENV,
        "id_env": ID_ENV,
        "missing_env": oauth_missing + id_missing,
        "credentials_present": not (oauth_missing or id_missing),
        "api_default": "read_only_fetch_behind_live_flag",
        "writes_to_platform": False,
        "stores_password": False,
        "verification_note": (
            "GBP API requires Google OAuth verification for the business.manage scope. "
            "Until approved, use the browser workflow (prompts/local/google-maps.md) and manual "
            "exports via gbp-fetch.py --input-file — this is the expected state, not an error."
        ),
        "capabilities": [
            "locations list (name, address, phone, categories) via Business Information API",
            "reviews with ratings/replies via My Business v4 reviews endpoint",
            "offline ingestion of saved exports (--input-file) — works today without OAuth verification",
        ],
        "guardrails": [
            "No live HTTP/API call in health check.",
            "gbp-fetch.py is read-only; posting/replies stay manual or browser-driven with human review.",
            "For RF local presence, Yandex Business is the primary channel (see yandex-business-health.py).",
        ],
        "official_docs": OFFICIAL_DOCS,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Google Business Profile Health",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- GBP URL: {report['gbp_url'] or 'not set in business_profile.gbp_url'}",
        f"- OAuth env: {', '.join(f'`{name}`' for name in report['oauth_env'])}",
        f"- ID env: {', '.join(f'`{name}`' for name in report['id_env'])}"
        + (f" (missing: {', '.join(report['missing_env'])})" if report["missing_env"] else ""),
        f"- Note: {report['verification_note']}",
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
    parser.add_argument("--write", action="store_true", help="Write seo/setup/gbp-health.* artifacts.")
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
