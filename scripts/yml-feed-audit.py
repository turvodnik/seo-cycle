#!/usr/bin/env python3
"""Validate a YML product feed (Yandex Market Language) for Яндекс.Товары/Маркет.

Fully local (stdlib xml.etree): checks the <shop> header, category tree, and
every <offer> for required fields (name/model, url, price, currencyId,
categoryId, picture), duplicate offer ids, prices <= 0, unknown categoryId
references, missing availability, oversized names, and http:// (non-TLS) URLs.

Input: --file <feed.xml> (default seo/feeds/yandex.yml if present) or
--url https://site/feed.yml with --live (plain GET, no auth).
Output: seo/merchant/yml-feed-audit.md/json (+latest) with --write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("yml-feed-audit")

REQUIRED_OFFER_FIELDS = ("url", "price", "currencyId", "categoryId")
NAME_MAX = 256


def offer_name(offer: ET.Element) -> str:
    for tag in ("name", "model"):
        node = offer.find(tag)
        if node is not None and (node.text or "").strip():
            return node.text.strip()
    return ""


def build_report(xml_text: str, source: str) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    def add(finding_id: str, severity: str, title: str, evidence: Any = None) -> None:
        findings.append({"id": finding_id, "severity": severity, "title": title,
                         "evidence": evidence if evidence is not None else []})

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        return {
            "audit_id": "yml_feed_audit",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "source": source,
            "status": "fail",
            "counts": {"offers": 0, "categories": 0, "findings": 1},
            "findings": [{"id": "xml_parse_error", "severity": "critical",
                          "title": f"Feed is not valid XML: {exc}", "evidence": []}],
        }

    shop = root.find("shop")
    if shop is None:
        add("missing_shop", "critical", "No <shop> element — not a YML feed")
        categories, offers = [], []
    else:
        for tag in ("name", "company", "url"):
            node = shop.find(tag)
            if node is None or not (node.text or "").strip():
                add("missing_shop_field", "medium", f"<shop> is missing <{tag}>")
        categories = shop.findall("categories/category")
        offers = shop.findall("offers/offer")

    category_ids = {cat.get("id") for cat in categories if cat.get("id")}
    orphan_parents = [cat.get("id") for cat in categories
                      if cat.get("parentId") and cat.get("parentId") not in category_ids]
    if orphan_parents:
        add("category_orphan_parent", "medium",
            f"{len(orphan_parents)} category(ies) reference a missing parentId", orphan_parents[:10])

    if not offers:
        add("no_offers", "critical", "Feed contains zero <offer> elements")

    id_counts = Counter(offer.get("id") or "" for offer in offers)
    duplicates = [offer_id for offer_id, count in id_counts.items() if offer_id and count > 1]
    if duplicates:
        add("duplicate_offer_ids", "critical", f"{len(duplicates)} duplicate offer id(s)", duplicates[:10])
    if id_counts.get(""):
        add("offers_without_id", "critical", f"{id_counts['']} offer(s) have no id attribute")

    missing_by_field: Counter = Counter()
    bad_price = []
    unknown_category = []
    no_picture = []
    no_availability = []
    long_names = []
    insecure_urls = []
    unnamed = []
    for offer in offers:
        offer_id = offer.get("id") or "?"
        if not offer_name(offer):
            unnamed.append(offer_id)
        for field in REQUIRED_OFFER_FIELDS:
            node = offer.find(field)
            if node is None or not (node.text or "").strip():
                missing_by_field[field] += 1
                continue
            if field == "price":
                try:
                    if float(node.text.strip().replace(",", ".")) <= 0:
                        bad_price.append(offer_id)
                except ValueError:
                    bad_price.append(offer_id)
            if field == "categoryId" and category_ids and node.text.strip() not in category_ids:
                unknown_category.append(offer_id)
            if field == "url" and node.text.strip().startswith("http://"):
                insecure_urls.append(offer_id)
        if offer.find("picture") is None or not ((offer.find("picture").text or "").strip() if offer.find("picture") is not None else ""):
            no_picture.append(offer_id)
        if offer.get("available") is None and offer.find("available") is None:
            no_availability.append(offer_id)
        name = offer_name(offer)
        if len(name) > NAME_MAX:
            long_names.append(offer_id)

    for field, count in missing_by_field.items():
        add(f"missing_{field}", "critical" if field in ("url", "price", "currencyId") else "high",
            f"{count} offer(s) are missing <{field}>")
    if unnamed:
        add("missing_name", "critical", f"{len(unnamed)} offer(s) have no <name>/<model>", unnamed[:10])
    if bad_price:
        add("non_positive_price", "critical", f"{len(bad_price)} offer(s) have price <= 0 or unparsable", bad_price[:10])
    if unknown_category:
        add("unknown_category_id", "high",
            f"{len(unknown_category)} offer(s) reference a categoryId missing from <categories>", unknown_category[:10])
    if no_picture:
        add("missing_picture", "high", f"{len(no_picture)} offer(s) have no <picture>", no_picture[:10])
    if no_availability:
        add("missing_availability", "medium",
            f"{len(no_availability)} offer(s) have no available attribute/element", no_availability[:10])
    if long_names:
        add("name_too_long", "low", f"{len(long_names)} offer name(s) exceed {NAME_MAX} chars", long_names[:10])
    if insecure_urls:
        add("insecure_offer_urls", "medium", f"{len(insecure_urls)} offer URL(s) use http:// instead of https://",
            insecure_urls[:10])

    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    findings.sort(key=lambda item: severity_rank.get(item["severity"], 0), reverse=True)
    status = "fail" if any(f["severity"] == "critical" for f in findings) else "warn" if findings else "pass"
    return {
        "audit_id": "yml_feed_audit",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "status": status,
        "counts": {"offers": len(offers), "categories": len(categories), "findings": len(findings)},
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# YML Feed Audit (Яндекс.Товары/Маркет)",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Source: `{report['source']}`",
        f"- Status: `{report['status']}`",
        f"- Offers: {report['counts']['offers']} · categories: {report['counts']['categories']}"
        f" · findings: {report['counts']['findings']}",
        "",
        "## Findings",
        "",
    ]
    if not report["findings"]:
        lines.append("Feed passes all local checks.")
    for finding in report["findings"]:
        lines.append(f"- **{finding['severity']}** `{finding['id']}`: {finding['title']}")
        if finding["evidence"]:
            lines.append(f"  - examples: {', '.join(str(x) for x in finding['evidence'][:10])}")
    return "\n".join(lines) + "\n"


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "merchant"
    return {
        "markdown": base / "yml-feed-audit.md",
        "json": base / "yml-feed-audit.json",
        "latest_markdown": base / "latest-yml-feed-audit.md",
        "latest_json": base / "latest-yml-feed-audit.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--file", help="Local YML feed file")
    parser.add_argument("--url", help="Feed URL (requires --live)")
    parser.add_argument("--live", action="store_true", help="Allow the HTTP GET for --url")
    parser.add_argument("--write", action="store_true", help="Write seo/merchant/yml-feed-audit.* artifacts")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("yml-feed-audit", project_root, cfg)

    if args.url:
        if not args.live:
            print("--url requires --live (explicit consent for the HTTP GET).", file=sys.stderr)
            return 2
        req = urllib.request.Request(args.url, headers={"User-Agent": "seo-cycle yml-feed-audit"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
        except OSError as exc:
            print(f"ERROR: cannot download feed: {exc}", file=sys.stderr)
            return 1
        source = args.url
    else:
        feed_path = pathlib.Path(args.file).expanduser() if args.file else project_root / "seo" / "feeds" / "yandex.yml"
        if not feed_path.exists():
            print(f"Feed not found: {feed_path}. Pass --file <feed.xml> or --url <...> --live.", file=sys.stderr)
            return 0
        xml_text = feed_path.read_text(encoding="utf-8", errors="replace")
        source = str(feed_path)

    report = build_report(xml_text, source)
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
