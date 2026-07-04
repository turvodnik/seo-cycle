#!/usr/bin/env python3
"""Build paid-campaign drafts from the semantic core (never applies anything).

Reads `semantic-architecture-final.json` (clusters, priorities, URLs) plus the
semantic core CSV and produces a reviewable draft: one campaign per priority
tier, one ad group per cluster, keywords from the cluster's core rows, negative
seeds from the rejected core, and ad text placeholders from cluster names.

Outputs (with --write):
  seo/ads/drafts/<date>-<platform>-draft.json   — machine-readable draft
  seo/ads/drafts/<date>-<platform>-draft.md     — human preview
  seo/ads/drafts/<date>-google-ads-editor.csv   — Google Ads Editor import (google_ads)

--create-ticket registers an `ads_campaign_draft` approval ticket; ads-apply.py
refuses to touch any platform without that ticket approved.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import Any

from seo_cycle_core.ads import primary_platform
from seo_cycle_core.config import find_config, load_yaml, package_project_root, write_text
from seo_cycle_core.logging_setup import setup_logging

log = setup_logging("ads-draft-builder")

MAX_KEYWORDS_PER_GROUP = 20


def scripts_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent


def load_architecture(package: pathlib.Path) -> dict[str, Any]:
    path = package / "semantic-architecture-final.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run the research package first")
    return json.loads(path.read_text(encoding="utf-8"))


def load_core_rows(package: pathlib.Path) -> list[dict[str, str]]:
    for name in ("semantic-core.cleaned.csv", "semantic-core.csv"):
        path = package / name
        if path.exists():
            with path.open(encoding="utf-8", newline="") as handle:
                return list(csv.DictReader(handle))
    return []


def load_negative_seeds(package: pathlib.Path) -> list[str]:
    path = package / "semantic-core.rejected.csv"
    if not path.exists():
        return []
    seeds = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            keyword = (row.get("keyword") or row.get("query") or "").strip()
            if keyword and len(keyword.split()) <= 4:
                seeds.append(keyword)
    return seeds[:50]


def cluster_keywords(rows: list[dict[str, str]], cluster_id: str) -> list[dict[str, Any]]:
    matched = [row for row in rows if (row.get("cluster_id") or row.get("base_cluster")) == cluster_id]

    def volume(row: dict[str, str]) -> float:
        for field in ("frequency", "volume", "impressions"):
            try:
                return float(row.get(field) or 0)
            except ValueError:
                continue
        return 0.0

    matched.sort(key=volume, reverse=True)
    return [
        {"text": row.get("keyword") or row.get("query"), "match_type": "phrase", "bid": None}
        for row in matched[:MAX_KEYWORDS_PER_GROUP]
        if (row.get("keyword") or row.get("query"))
    ]


def build_draft(package: pathlib.Path, cfg: dict[str, Any], platform: str,
                site_url: str) -> dict[str, Any]:
    architecture = load_architecture(package)
    rows = load_core_rows(package)
    negatives = load_negative_seeds(package)
    clusters = [item for item in architecture.get("clusters") or [] if isinstance(item, dict)]

    campaigns: dict[str, dict[str, Any]] = {}
    for cluster in clusters:
        if not cluster.get("mvp") and str(cluster.get("priority") or "") not in {"P0", "P1"}:
            continue
        priority = str(cluster.get("priority") or ("P1" if cluster.get("mvp") else "P2"))
        campaign = campaigns.setdefault(
            priority,
            {
                "name": f"seo-cycle {priority} search",
                "platform": platform,
                "channel": "search",
                "budget_daily": 0,
                "negatives": negatives,
                "ad_groups": [],
            },
        )
        keywords = cluster_keywords(rows, str(cluster.get("id") or ""))
        if not keywords:
            keywords = [{"text": cluster.get("primary_keyword"), "match_type": "phrase", "bid": None}]
        final_url = site_url.rstrip("/") + str(cluster.get("suggested_url") or "/")
        campaign["ad_groups"].append(
            {
                "name": str(cluster.get("name") or cluster.get("id")),
                "cluster_id": cluster.get("id"),
                "final_url": final_url,
                "keywords": [kw for kw in keywords if kw.get("text")],
                "ads": [
                    {
                        "headlines": [str(cluster.get("name") or "")[:30],
                                      str(cluster.get("primary_keyword") or "")[:30],
                                      "Официальный сайт"[:30]],
                        "descriptions": [
                            f"{cluster.get('name')}: подробный разбор, цены и наличие."[:90],
                            "Доставка, гарантия, консультация специалиста."[:90],
                        ],
                        "final_url": final_url,
                    }
                ],
            }
        )

    draft = {
        "draft_id": f"{platform}-{dt.date.today().isoformat()}",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "platform": platform,
        "status": "draft",
        "applies_nothing": True,
        "budget_note": "budget_daily is 0 by design: a human sets budgets during review",
        "campaigns": sorted(campaigns.values(), key=lambda item: item["name"]),
    }
    draft["summary"] = {
        "campaigns": len(draft["campaigns"]),
        "ad_groups": sum(len(campaign["ad_groups"]) for campaign in draft["campaigns"]),
        "keywords": sum(
            len(group["keywords"]) for campaign in draft["campaigns"] for group in campaign["ad_groups"]
        ),
        "negatives": len(negatives),
    }
    return draft


def render_markdown(draft: dict[str, Any]) -> str:
    lines = [
        f"# Ads Draft — {draft['platform']}",
        "",
        f"- Draft: `{draft['draft_id']}` · generated: {draft['generated_at']}",
        f"- Campaigns: {draft['summary']['campaigns']} · ad groups: {draft['summary']['ad_groups']}"
        f" · keywords: {draft['summary']['keywords']} · negatives: {draft['summary']['negatives']}",
        f"- {draft['budget_note']}",
        "",
    ]
    for campaign in draft["campaigns"]:
        lines.extend([f"## {campaign['name']}", ""])
        for group in campaign["ad_groups"]:
            keywords = ", ".join(f"`{kw['text']}`" for kw in group["keywords"][:8])
            lines.append(f"- **{group['name']}** → {group['final_url']}")
            lines.append(f"  - keywords ({len(group['keywords'])}): {keywords}")
        lines.append("")
    lines.append("Apply only via: `ads-apply.py --draft <this.json> --ticket <approved-id> --live --allow-write`")
    return "\n".join(lines) + "\n"


def write_editor_csv(path: pathlib.Path, draft: dict[str, Any]) -> None:
    """Google Ads Editor import: campaign/ad group/keyword rows."""
    lines = ["Campaign,Ad Group,Keyword,Criterion Type,Final URL"]
    for campaign in draft["campaigns"]:
        for group in campaign["ad_groups"]:
            for keyword in group["keywords"]:
                text = str(keyword.get("text") or "").replace(",", " ")
                lines.append(
                    f"{campaign['name']},{group['name']},{text},Phrase,{group['final_url']}"
                )
    write_text(path, "\n".join(lines) + "\n")


def create_ticket(project_root: pathlib.Path, draft_path: pathlib.Path, draft: dict[str, Any]) -> str | None:
    proc = subprocess.run(
        [
            sys.executable,
            str(scripts_dir() / "approval-gate.py"),
            "create",
            "--type",
            "ads_campaign_draft",
            "--title",
            f"{draft['platform']} draft: {draft['summary']['campaigns']} campaigns,"
            f" {draft['summary']['keywords']} keywords",
            "--file",
            str(draft_path),
            "--context",
            "Review budgets, keywords, and ad copy; apply via ads-apply.py after approval.",
        ],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    ticket = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else None
    return ticket if proc.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", nargs="?", default="seo/research-package", help="Research package directory")
    parser.add_argument("--platform", choices=("auto", "yandex_direct", "google_ads"), default="auto")
    parser.add_argument("--write", action="store_true", help="Write draft artifacts under seo/ads/drafts/")
    parser.add_argument("--create-ticket", action="store_true", help="Register an ads_campaign_draft approval ticket")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    package = pathlib.Path(args.package).expanduser().resolve()
    if not package.is_dir():
        print(f"ERROR: package {package} not found", file=sys.stderr)
        return 2
    project_root = package_project_root(package)
    cfg_path = find_config(project_root)
    cfg = load_yaml(cfg_path) if cfg_path else {}
    global log
    log = setup_logging("ads-draft-builder", project_root, cfg)

    platform = args.platform if args.platform != "auto" else primary_platform(cfg)
    site_url = str((cfg.get("project") or {}).get("url") or "").strip()
    try:
        draft = build_draft(package, cfg, platform, site_url)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    drafts_dir = project_root / "seo" / "ads" / "drafts"
    draft_path = drafts_dir / f"{dt.date.today().isoformat()}-{platform.replace('_', '-')}-draft.json"
    if args.write:
        write_text(draft_path, json.dumps(draft, ensure_ascii=False, indent=2) + "\n")
        write_text(draft_path.with_suffix(".md"), render_markdown(draft))
        if platform == "google_ads":
            write_editor_csv(drafts_dir / f"{dt.date.today().isoformat()}-google-ads-editor.csv", draft)
        log.info("draft written: %s", draft_path)
    if args.create_ticket:
        if not args.write:
            print("ERROR: --create-ticket requires --write (the ticket links the draft file)", file=sys.stderr)
            return 2
        ticket = create_ticket(project_root, draft_path, draft)
        if ticket:
            draft["ticket_id"] = ticket
            write_text(draft_path, json.dumps(draft, ensure_ascii=False, indent=2) + "\n")
            print(f"ticket: {ticket}", file=sys.stderr)
    if args.format == "json":
        print(json.dumps(draft, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(draft), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
