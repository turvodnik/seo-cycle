#!/usr/bin/env python3
"""Pull published WordPress content into the local mirror and report site-side changes.

WordPress adapter over the shared mirror engine (seo_cycle_core/mirror.py):
read-only GET over /wp-json/wp/v2/posts|pages with pagination, normalized into
mirror records. See also tilda-content-pull.py and bitrix-content-pull.py.

Env: WP_BASE_URL (+ optional WP_USER/WP_APP_PASSWORD for non-public statuses).
Default is offline (--input-file <rest-export.json>); --live makes real GETs.
Output: seo/content-mirror/sync-report.md/json (+latest) with --write.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.mirror import apply_pull, html_to_text, make_record, render_sync_markdown, sync_output_paths
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("wp-content-pull")

CONTENT_TYPES = ("posts", "pages")
MAX_PAGES_DEFAULT = 10  # x100 items per type
FIELDS = "id,slug,link,status,modified,title,content"


def rest_fetch(base_url: str, content_type: str, max_pages: int) -> list[dict[str, Any]]:
    headers = {"User-Agent": "seo-cycle wp-content-pull", "Accept": "application/json"}
    user = os.environ.get("WP_USER", "")
    password = os.environ.get("WP_APP_PASSWORD", "")
    if user and password:
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    items: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        url = (f"{base_url.rstrip('/')}/wp-json/wp/v2/{content_type}"
               f"?per_page=100&page={page}&status=publish&_fields={FIELDS}")
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                batch = json.loads(resp.read().decode("utf-8"))
                total_pages = int(resp.headers.get("X-WP-TotalPages", "1") or "1")
        except urllib.error.HTTPError as exc:
            if exc.code == 400 and page > 1:  # past the last page
                break
            raise
        if not isinstance(batch, list) or not batch:
            break
        items.extend(batch)
        if page >= total_pages:
            break
    log.info("pulled %s %s", len(items), content_type)
    return items


def normalize_item(item: dict[str, Any], content_type: str) -> dict[str, Any] | None:
    slug = str(item.get("slug") or "").strip()
    if not slug:
        return None
    rendered = item.get("content", {})
    html = rendered.get("rendered") if isinstance(rendered, dict) else str(rendered or "")
    title = item.get("title", {})
    title_text = title.get("rendered") if isinstance(title, dict) else str(title or "")
    return make_record(
        content_type=content_type,
        item_id=item.get("id"),
        slug=slug,
        url=item.get("link"),
        status=item.get("status"),
        modified=item.get("modified"),
        title=html_to_text(title_text or ""),
        text=html_to_text(html or ""),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--types", default="posts,pages", help="Comma-separated WP REST types")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_DEFAULT, help="REST pages per type (x100 items)")
    parser.add_argument("--input-file", help="Saved WP REST export: JSON list of post objects")
    parser.add_argument("--live", action="store_true", help="Make real GETs to WP_BASE_URL")
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
    log = setup_logging("wp-content-pull", project_root, cfg)

    types = [item.strip() for item in args.types.split(",") if item.strip() in CONTENT_TYPES]
    records: list[dict[str, Any]] = []
    if args.input_file:
        raw = json.loads(pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else raw.get("items") or []
        type_map = {"post": "posts", "page": "pages"}
        for item in rows:
            content_type = type_map.get(str(item.get("type") or ""), str(item.get("type") or "posts"))
            record = normalize_item(item, content_type)
            if record:
                records.append(record)
    elif args.live:
        base_url = os.environ.get("WP_BASE_URL", "").strip() or str((cfg.get("project") or {}).get("url") or "").strip()
        if not base_url:
            print("ERROR: set WP_BASE_URL env (or project.url in seo-cycle.yaml)", file=sys.stderr)
            return 2
        try:
            for content_type in types:
                for item in rest_fetch(base_url, content_type, max(1, args.max_pages)):
                    record = normalize_item(item, content_type)
                    if record:
                        records.append(record)
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            print(f"ERROR: WP REST pull failed: {exc}", file=sys.stderr)
            return 1
    else:
        print("Provide --input-file <rest-export.json> or --live (read-only GET to the site).", file=sys.stderr)
        return 0

    report = apply_pull(project_root, records, source="wordpress", write=args.write)
    if args.write:
        write_report_bundle(sync_output_paths(project_root), render_sync_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_sync_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
