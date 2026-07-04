#!/usr/bin/env python3
"""Cross-channel SEO+PPC analytics from cached ads exports (no network).

Inputs: seo/ads/raw/<platform>/*-latest.json (yandex-direct-fetch / google-ads-fetch),
`positions` from seo.db (db-sync.py), and the research-package semantic core.

Rules:
  1. organic_overlap   — query ranks in organic top-N AND has active paid clicks
                         → recommend lowering the bid / pausing the keyword.
  2. keyword_candidates— converting paid search terms missing from the semantic
                         core → candidates CSV (plan only, never auto-appended).
  3. campaign_economics— CPA / cost / conversions per campaign.
  4. wasted_spend      — search terms with cost above the threshold and zero
                         conversions → negative-keyword candidates CSV.

Outputs: seo/ads/ads-analytics.md/json (+latest), seo/ads/keyword-candidates.csv,
seo/ads/negative-candidates.csv (with --write).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import sqlite3
import sys
from typing import Any

from seo_cycle_core.ads import ads_config, load_latest_raw
from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("ads-analytics")


def norm_query(text: Any) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def load_organic_top(project_root: pathlib.Path, cfg: dict[str, Any], threshold: float) -> dict[str, float]:
    db_rel = nested_get(cfg, "data_store.path", "seo/seo.db") or "seo/seo.db"
    db_path = project_root / db_rel
    if not db_path.exists():
        return {}
    top: dict[str, float] = {}
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT query, MIN(position) FROM positions WHERE position > 0 GROUP BY query"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return {}
    for query, position in rows:
        if position is not None and float(position) <= threshold:
            top[norm_query(query)] = float(position)
    return top


def load_semantic_core_keywords(project_root: pathlib.Path) -> set[str]:
    keywords: set[str] = set()
    for candidate in (
        project_root / "seo" / "research-package" / "semantic-core.cleaned.csv",
        project_root / "seo" / "research-package" / "semantic-core.csv",
    ):
        if not candidate.exists():
            continue
        with candidate.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                keyword = norm_query(row.get("keyword") or row.get("query"))
                if keyword:
                    keywords.add(keyword)
        break
    return keywords


def direct_search_terms(project_root: pathlib.Path) -> list[dict[str, Any]]:
    payload = load_latest_raw(project_root, "yandex_direct", "search_queries") or {}
    rows = []
    for row in payload.get("rows") or []:
        rows.append(
            {
                "platform": "yandex_direct",
                "query": row.get("Query", ""),
                "campaign_id": row.get("CampaignId", ""),
                "clicks": float(row.get("Clicks") or 0),
                "cost": float(row.get("Cost") or 0),
                "conversions": float(row.get("Conversions") or 0),
            }
        )
    return rows


def google_search_terms(project_root: pathlib.Path) -> list[dict[str, Any]]:
    payload = load_latest_raw(project_root, "google_ads", "search_terms") or {}
    rows = []
    for row in payload.get("results") or []:
        rows.append(
            {
                "platform": "google_ads",
                "query": nested_get(row, "searchTermView.searchTerm", ""),
                "campaign_id": nested_get(row, "campaign.id", ""),
                "clicks": float(nested_get(row, "metrics.clicks", 0) or 0),
                "cost": float(nested_get(row, "metrics.costMicros", 0) or 0) / 1_000_000,
                "conversions": float(nested_get(row, "metrics.conversions", 0) or 0),
            }
        )
    return rows


def campaign_stats(project_root: pathlib.Path) -> list[dict[str, Any]]:
    campaigns: dict[tuple[str, str], dict[str, Any]] = {}
    direct = load_latest_raw(project_root, "yandex_direct", "stats") or {}
    for row in direct.get("rows") or []:
        key = ("yandex_direct", str(row.get("CampaignId") or ""))
        agg = campaigns.setdefault(key, {"platform": key[0], "campaign_id": key[1],
                                         "name": row.get("CampaignName", ""), "clicks": 0.0,
                                         "cost": 0.0, "conversions": 0.0})
        agg["clicks"] += float(row.get("Clicks") or 0)
        agg["cost"] += float(row.get("Cost") or 0)
        agg["conversions"] += float(row.get("Conversions") or 0)
    google = load_latest_raw(project_root, "google_ads", "stats") or {}
    for row in google.get("results") or []:
        key = ("google_ads", str(nested_get(row, "campaign.id", "") or ""))
        agg = campaigns.setdefault(key, {"platform": key[0], "campaign_id": key[1],
                                         "name": nested_get(row, "campaign.name", ""), "clicks": 0.0,
                                         "cost": 0.0, "conversions": 0.0})
        agg["clicks"] += float(nested_get(row, "metrics.clicks", 0) or 0)
        agg["cost"] += float(nested_get(row, "metrics.costMicros", 0) or 0) / 1_000_000
        agg["conversions"] += float(nested_get(row, "metrics.conversions", 0) or 0)
    result = []
    for agg in campaigns.values():
        agg["cpa"] = round(agg["cost"] / agg["conversions"], 2) if agg["conversions"] else None
        agg["cost"] = round(agg["cost"], 2)
        result.append(agg)
    return sorted(result, key=lambda item: item["cost"], reverse=True)


def build_report(project_root: pathlib.Path, cfg: dict[str, Any]) -> dict[str, Any]:
    ads = ads_config(cfg)
    threshold = float(nested_get(ads, "analytics.top_position_threshold", 3) or 3)
    wasted_min = float(nested_get(ads, "analytics.wasted_spend_min_cost", 300) or 300)
    organic_top = load_organic_top(project_root, cfg, threshold)
    core = load_semantic_core_keywords(project_root)
    terms = direct_search_terms(project_root) + google_search_terms(project_root)

    organic_overlap = []
    keyword_candidates = []
    wasted = []
    for term in terms:
        query = norm_query(term["query"])
        if not query:
            continue
        if query in organic_top and term["clicks"] > 0:
            organic_overlap.append({**term, "organic_position": organic_top[query],
                                    "action": "lower bid or pause; organic already ranks top"})
        if term["conversions"] > 0 and core and query not in core:
            keyword_candidates.append({**term, "action": "add to semantic core / content plan"})
        if term["cost"] >= wasted_min and term["conversions"] == 0:
            wasted.append({**term, "action": "add as negative keyword"})

    campaigns = campaign_stats(project_root)
    return {
        "audit_id": "ads_analytics",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "organic_top_queries": len(organic_top),
            "semantic_core_keywords": len(core),
            "search_terms": len(terms),
            "top_position_threshold": threshold,
            "wasted_spend_min_cost": wasted_min,
        },
        "organic_overlap": sorted(organic_overlap, key=lambda item: item["cost"], reverse=True)[:100],
        "keyword_candidates": sorted(keyword_candidates, key=lambda item: item["conversions"], reverse=True)[:200],
        "wasted_spend": sorted(wasted, key=lambda item: item["cost"], reverse=True)[:200],
        "campaigns": campaigns,
        "summary": {
            "organic_overlap": len(organic_overlap),
            "keyword_candidates": len(keyword_candidates),
            "wasted_spend": len(wasted),
            "campaigns": len(campaigns),
            "total_cost": round(sum(item["cost"] for item in campaigns), 2),
            "total_conversions": round(sum(item["conversions"] for item in campaigns), 1),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Ads Analytics (SEO + PPC)",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Campaign cost (window): {summary['total_cost']} · conversions: {summary['total_conversions']}",
        f"- Organic-overlap keywords: {summary['organic_overlap']}"
        f" · core candidates: {summary['keyword_candidates']}"
        f" · wasted-spend terms: {summary['wasted_spend']}",
        "",
        "## Campaign economics",
        "",
        "| Platform | Campaign | Cost | Clicks | Conv. | CPA |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["campaigns"][:20]:
        lines.append(
            f"| {row['platform']} | {row['name'] or row['campaign_id']} | {row['cost']}"
            f" | {int(row['clicks'])} | {row['conversions']} | {row['cpa'] if row['cpa'] is not None else '—'} |"
        )
    for section, title in (("organic_overlap", "Organic top + active bid → lower/pause"),
                           ("keyword_candidates", "Converting paid terms missing from the core"),
                           ("wasted_spend", "Wasted spend → negative candidates")):
        lines.extend(["", f"## {title}", ""])
        rows = report[section]
        if not rows:
            lines.append("_none_")
            continue
        for row in rows[:15]:
            extra = f", organic pos {row['organic_position']}" if section == "organic_overlap" else ""
            lines.append(
                f"- `{row['query']}` ({row['platform']}, cost {round(row['cost'], 2)},"
                f" conv {row['conversions']}{extra}) — {row['action']}"
            )
    lines.extend(["", "CSV plans: `seo/ads/keyword-candidates.csv`, `seo/ads/negative-candidates.csv`."])
    return "\n".join(lines) + "\n"


def write_candidate_csv(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    fields = ["query", "platform", "campaign_id", "clicks", "cost", "conversions", "action"]
    buffer = [",".join(fields)]
    for row in rows:
        buffer.append(",".join(str(row.get(field, "")).replace(",", " ") for field in fields))
    write_text(path, "\n".join(buffer) + "\n")


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "ads"
    return {
        "markdown": base / "ads-analytics.md",
        "json": base / "ads-analytics.json",
        "latest_markdown": base / "latest-ads-analytics.md",
        "latest_json": base / "latest-ads-analytics.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write report + candidate CSV plans")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("ads-analytics", project_root, cfg)

    report = build_report(project_root, cfg)
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
        base = project_root / "seo" / "ads"
        write_candidate_csv(base / "keyword-candidates.csv", report["keyword_candidates"])
        write_candidate_csv(base / "negative-candidates.csv", report["wasted_spend"])
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
