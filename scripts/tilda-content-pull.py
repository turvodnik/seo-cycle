#!/usr/bin/env python3
"""Pull published Tilda pages into the local mirror and report site-side changes.

Tilda adapter over the shared mirror engine. --live uses the official Tilda
API (getpageslist + getpagefullexport, keys from tilda.cc → Settings → API):
env TILDA_PUBLIC_KEY, TILDA_SECRET_KEY, TILDA_PROJECT_ID. The API allows ~150
requests/hour — --max-pages caps the per-run export volume. Offline mode
ingests a saved export via --input-file (JSON list of {id, title, alias,
published, date, html}).

Output: seo/content-mirror/pages/<slug>.md + sync-report (shared contract with
wp-content-pull.py: new / changed-on-site / deleted / draft drift).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.mirror import apply_pull, html_to_text, make_record, render_sync_markdown, sync_output_paths
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("tilda-content-pull")

API_BASE = "https://api.tildacdn.info/v1"
MAX_PAGES_DEFAULT = 50
ENV_NAMES = ("TILDA_PUBLIC_KEY", "TILDA_SECRET_KEY", "TILDA_PROJECT_ID")


def api_get(method: str, params: dict[str, str]) -> Any:
    query = urllib.parse.urlencode({
        "publickey": os.environ["TILDA_PUBLIC_KEY"],
        "secretkey": os.environ["TILDA_SECRET_KEY"],
        **params,
    })
    req = urllib.request.Request(f"{API_BASE}/{method}/?{query}",
                                 headers={"User-Agent": "seo-cycle tilda-content-pull"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("status") != "FOUND":
        raise RuntimeError(f"Tilda API {method}: {data.get('message') or data.get('status')}")
    return data.get("result")


def live_fetch(max_pages: int) -> list[dict[str, Any]]:
    pages = api_get("getpageslist", {"projectid": os.environ["TILDA_PROJECT_ID"]}) or []
    published = [page for page in pages if str(page.get("published") or "") not in ("", "0")]
    items = []
    for page in published[:max_pages]:
        full = api_get("getpagefullexport", {"pageid": str(page.get("id"))}) or {}
        items.append({**page, "html": full.get("html", "")})
    log.info("pulled %s of %s published tilda pages", len(items), len(published))
    return items


def normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    alias = str(item.get("alias") or "").strip().strip("/")
    slug = alias or f"page{item.get('id')}"
    text = html_to_text(str(item.get("html") or item.get("descr") or ""))
    if not text and not item.get("title"):
        return None
    return make_record(
        content_type="pages",
        item_id=item.get("id"),
        slug=slug,
        url=f"https://{item.get('projectdomain') or ''}/{alias}" if item.get("projectdomain") else (alias or str(item.get("id"))),
        status="publish" if str(item.get("published") or "") not in ("", "0") else "draft",
        modified=item.get("date"),
        title=str(item.get("title") or slug),
        text=text,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_DEFAULT,
                        help="Full-export requests per run (Tilda API ~150 req/hour)")
    parser.add_argument("--input-file", help="Saved export: JSON list of Tilda page objects with html")
    parser.add_argument("--live", action="store_true", help="Call the Tilda API (requires TILDA_* env)")
    parser.add_argument("--write", action="store_true", help="Write mirror files, state, and sync report")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("tilda-content-pull", project_root, cfg)

    if args.input_file:
        raw = json.loads(pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("result") or raw.get("items") or []
    elif args.live:
        missing = [name for name in ENV_NAMES if not os.environ.get(name)]
        if missing:
            print(f"ERROR: missing env: {', '.join(missing)}", file=sys.stderr)
            return 2
        try:
            items = live_fetch(max(1, args.max_pages))
        except (RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"ERROR: Tilda API pull failed: {exc}", file=sys.stderr)
            return 1
    else:
        print("Provide --input-file <export.json> or --live (Tilda API, read-only).", file=sys.stderr)
        return 0

    records = [record for record in (normalize_item(item) for item in items) if record]
    report = apply_pull(project_root, records, source="tilda", write=args.write)
    if args.write:
        write_report_bundle(sync_output_paths(project_root), render_sync_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_sync_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
