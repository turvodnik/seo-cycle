#!/usr/bin/env python3
"""Fetch Google Business Profile locations and reviews (read-only, guarded).

Works today without OAuth verification via --input-file (a saved API export or
a browser-collected JSON); --live needs approved GBP OAuth credentials
(GBP_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN + GOOGLE_BUSINESS_ACCOUNT_ID, and
GOOGLE_BUSINESS_LOCATION_ID for reviews).

Reports: locations | reviews. Summary: locations with categories/phones,
review count, rating distribution, unanswered share, freshest/oldest review.
Output: seo/local/gbp-summary.md/json (+latest); raw to seo/local/raw/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("gbp-fetch")

TOKEN_URL = "https://oauth2.googleapis.com/token"
INFO_BASE = "https://mybusinessbusinessinformation.googleapis.com/v1"
REVIEWS_BASE = "https://mybusiness.googleapis.com/v4"
REPORTS = ("locations", "reviews")
STAR_VALUES = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def oauth_token() -> str:
    body = urllib.parse.urlencode(
        {
            "client_id": os.environ["GBP_OAUTH_CLIENT_ID"],
            "client_secret": os.environ["GBP_OAUTH_CLIENT_SECRET"],
            "refresh_token": os.environ["GBP_OAUTH_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def get_json(url: str, token: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def live_fetch(report: str) -> dict[str, Any]:
    missing = [name for name in ("GBP_OAUTH_CLIENT_ID", "GBP_OAUTH_CLIENT_SECRET",
                                 "GBP_OAUTH_REFRESH_TOKEN", "GOOGLE_BUSINESS_ACCOUNT_ID")
               if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"missing env: {', '.join(missing)}")
    token = oauth_token()
    account = os.environ["GOOGLE_BUSINESS_ACCOUNT_ID"]
    if report == "locations":
        url = (f"{INFO_BASE}/accounts/{account}/locations"
               "?readMask=name,title,phoneNumbers,categories,storefrontAddress,websiteUri&pageSize=100")
        return {"locations": get_json(url, token).get("locations") or []}
    location = os.environ.get("GOOGLE_BUSINESS_LOCATION_ID", "")
    if not location:
        raise RuntimeError("set GOOGLE_BUSINESS_LOCATION_ID for reviews")
    reviews: list[dict[str, Any]] = []
    page_token = ""
    for _ in range(10):
        url = f"{REVIEWS_BASE}/accounts/{account}/locations/{location}/reviews?pageSize=50"
        if page_token:
            url += f"&pageToken={page_token}"
        data = get_json(url, token)
        reviews.extend(data.get("reviews") or [])
        page_token = data.get("nextPageToken") or ""
        if not page_token:
            break
    return {"reviews": reviews}


def summarize_locations(payload: dict[str, Any]) -> dict[str, Any]:
    locations = payload.get("locations") or []
    rows = []
    for location in locations:
        categories = location.get("categories") or {}
        primary = (categories.get("primaryCategory") or {}).get("displayName") if isinstance(categories, dict) else ""
        rows.append(
            {
                "title": location.get("title"),
                "primary_category": primary,
                "phone": (location.get("phoneNumbers") or {}).get("primaryPhone"),
                "website": location.get("websiteUri"),
                "locality": ((location.get("storefrontAddress") or {}).get("locality")),
            }
        )
    return {"count": len(locations), "locations": rows[:30],
            "missing_website": sum(1 for row in rows if not row["website"]),
            "missing_phone": sum(1 for row in rows if not row["phone"])}


def summarize_reviews(payload: dict[str, Any]) -> dict[str, Any]:
    reviews = payload.get("reviews") or []
    ratings = Counter()
    unanswered = 0
    dates = []
    for review in reviews:
        star = STAR_VALUES.get(str(review.get("starRating")), 0)
        if star:
            ratings[star] += 1
        if not review.get("reviewReply"):
            unanswered += 1
        if review.get("createTime"):
            dates.append(str(review["createTime"])[:10])
    total_stars = sum(star * count for star, count in ratings.items())
    rated = sum(ratings.values())
    return {
        "count": len(reviews),
        "average_rating": round(total_stars / rated, 2) if rated else None,
        "rating_distribution": {str(star): ratings.get(star, 0) for star in range(5, 0, -1)},
        "unanswered": unanswered,
        "unanswered_share": round(unanswered / len(reviews), 2) if reviews else 0,
        "newest": max(dates) if dates else None,
        "oldest": min(dates) if dates else None,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Google Business Profile Summary", "", f"- Generated: {summary['generated_at']}"]
    locations = summary["reports"].get("locations")
    if locations:
        lines.append(f"- Locations: {locations['count']} (no website: {locations['missing_website']},"
                     f" no phone: {locations['missing_phone']})")
        for row in locations["locations"][:10]:
            lines.append(f"  - {row['title']} — {row['primary_category'] or '—'}"
                         f" · {row['locality'] or ''} · {row['phone'] or 'no phone'}")
    reviews = summary["reports"].get("reviews")
    if reviews:
        lines.extend(
            [
                f"- Reviews: {reviews['count']} · avg {reviews['average_rating']}"
                f" · unanswered {reviews['unanswered']} ({int(reviews['unanswered_share'] * 100)}%)",
                f"- Freshest: {reviews['newest']} · oldest: {reviews['oldest']}",
                f"- Distribution 5→1: "
                + " / ".join(f"{star}:{count}" for star, count in reviews["rating_distribution"].items()),
            ]
        )
        if reviews["unanswered"]:
            lines.append("- Action: ответьте на отзывы без реакции — прямой local-trust сигнал.")
    if not summary["reports"]:
        lines.append("- No data: run with --input-file <export.json> or --live.")
    return "\n".join(lines) + "\n"


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "local"
    return {
        "markdown": base / "gbp-summary.md",
        "json": base / "gbp-summary.json",
        "latest_markdown": base / "latest-gbp-summary.md",
        "latest_json": base / "latest-gbp-summary.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--report", choices=REPORTS, default="reviews")
    parser.add_argument("--input-file", help="Saved API/browser export (JSON)")
    parser.add_argument("--live", action="store_true", help="Call GBP APIs (requires verified OAuth env)")
    parser.add_argument("--write", action="store_true", help="Write seo/local artifacts")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("gbp-fetch", project_root, cfg)

    if args.input_file:
        payload = json.loads(pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8"))
        if isinstance(payload, list):
            payload = {"reviews": payload} if args.report == "reviews" else {"locations": payload}
    elif args.live:
        try:
            payload = live_fetch(args.report)
        except (RuntimeError, urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
            print(f"ERROR: GBP API read failed: {exc}. Without verified OAuth use the browser workflow "
                  "and --input-file.", file=sys.stderr)
            return 1
    else:
        print("Provide --input-file <export.json> (browser/manual export) or --live (verified OAuth).",
              file=sys.stderr)
        return 0

    if args.write:
        raw = project_root / "seo" / "local" / "raw" / f"gbp-{args.report}-latest.json"
        write_text(raw, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    summary = {
        "audit_id": "gbp_summary",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "reports": {args.report: summarize_locations(payload) if args.report == "locations"
                    else summarize_reviews(payload)},
    }
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(summary), summary)
    if args.format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
