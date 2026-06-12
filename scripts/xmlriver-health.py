#!/usr/bin/env python3
"""Report XMLRiver readiness without making paid API calls."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, policy_path, project_root_for
from seo_cycle_core.reports import write_report_bundle


ENV_NAMES = ["XMLRIVER_USER_ID", "XMLRIVER_API_KEY"]
PRICE_RUB_PER_1000 = {
    "basic": {"google": 25, "yandex": 25, "wordstat": 25, "yandex_search": 25},
    "pro": {"google": 20, "yandex": 20, "wordstat": 20, "yandex_search": 24},
    "mega": {"google": 15, "yandex": 15, "wordstat": 15, "yandex_search": 23},
    "giga": {"google": 12, "yandex": 12, "wordstat": 12, "yandex_search": 22},
}
CAPABILITIES = [
    "google_organic",
    "google_answer_block",
    "google_knowledge_graph",
    "google_related_questions",
    "google_related_searches",
    "google_ads",
    "google_product_shopping",
    "google_local_results",
    "google_news_video_discussions",
    "google_images_news_shopping_maps_suggest",
    "google_ai_overview",
    "yandex_organic",
    "yandex_searchsters",
    "yandex_ads",
    "yandex_carousel",
    "yandex_knowledge_graph",
    "yandex_commercial_offers",
    "yandex_news_related_searches",
    "yandex_shop_prices",
    "yandex_suggest",
    "yandex_ai_overview",
    "yandex_search_api",
    "wordstat_new",
]
OFFICIAL_DOCS = [
    "https://xmlriver.com/price.html",
    "https://xmlriver.com/api/api-connect/",
    "https://xmlriver.com/api/api-alt/",
    "https://xmlriver.com/apidoc/api-about/",
    "https://xmlriver.com/apiydoc/apiy-about/",
    "https://xmlriver.com/apiwordstatnew/apiwn-connect/",
]


def output_paths(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    return {
        "markdown": policy_path(cfg, project_root, "xmlriver_health_report", "seo/setup/xmlriver-health.md"),
        "json": policy_path(cfg, project_root, "xmlriver_health_json", "seo/setup/xmlriver-health.json"),
        "latest_markdown": policy_path(cfg, project_root, "latest_xmlriver_health", "seo/setup/latest-xmlriver-health.md"),
        "latest_json": policy_path(cfg, project_root, "latest_xmlriver_health_json", "seo/setup/latest-xmlriver-health.json"),
    }


def build_report(cfg_path: pathlib.Path) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    credentials_present = all(os.environ.get(name) for name in ENV_NAMES)
    return {
        "provider": "xmlriver",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": cfg.get("project", {}),
        "status": "available" if credentials_present else "needs_credentials",
        "env_names": ENV_NAMES,
        "credentials_present": credentials_present,
        "api_default": "disabled_until_live_allow_paid",
        "writes_to_site": False,
        "stores_password": False,
        "paid_api_used": False,
        "capabilities": CAPABILITIES,
        "price_reference": PRICE_RUB_PER_1000,
        "official_docs": OFFICIAL_DOCS,
        "comparison_notes": [
            "Prefer XMLRiver for cheap Yandex/Wordstat/Yandex-specific SERP block enrichment when volume/KD is not required.",
            "Keep Serpstat/DataForSEO for metrics or providers/features XMLRiver does not cover in the project policy.",
            "Do not compare paid providers from memory; refresh their price docs or local tool-budget before live runs.",
        ],
        "guardrails": [
            "No live HTTP/API call in health check.",
            "Use xmlriver-source-pack.py with --input-file by default.",
            "Use --live --allow-paid only after spend-guard and usage-ledger preflight.",
            "Keep raw XML/JSON in seo/research/raw/xmlriver and downstream context on distillates only.",
        ],
        "paths": {key: str(path.relative_to(project_root)) for key, path in output_paths(cfg, project_root).items()},
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# XMLRiver Provider Health",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- Credentials present: {report['credentials_present']}",
        f"- Env names: {', '.join(f'`{name}`' for name in report['env_names'])}",
        f"- API default: `{report['api_default']}`",
        f"- Stores password: {report['stores_password']}",
        "",
        "## Price Reference, RUB / 1000 Requests",
        "| Tariff | Google | Yandex | Wordstat | Yandex Search API |",
        "|---|---:|---:|---:|---:|",
    ]
    for tariff, row in report["price_reference"].items():
        lines.append(f"| {tariff} | {row['google']} | {row['yandex']} | {row['wordstat']} | {row['yandex_search']} |")
    lines.extend(["", "## Capabilities"])
    lines.extend(f"- {capability}" for capability in report["capabilities"])
    lines.extend(["", "## Guardrails"])
    lines.extend(f"- {guard}" for guard in report["guardrails"])
    lines.extend(["", "## Official Docs"])
    lines.extend(f"- {url}" for url in report["official_docs"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write seo/setup/xmlriver-health.* artifacts.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    report = build_report(cfg_path)
    if args.write:
        write_report_bundle(output_paths(cfg, project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
