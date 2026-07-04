#!/usr/bin/env python3
"""Pull 1C-Bitrix site content into the local mirror and report site-side changes.

Bitrix CMS ships no public content REST out of the box, so this adapter is
honest about the two working paths:
  1. --input-file — a JSON export of infoblock elements (typical developer
     export or «Экспорт в JSON» module output): list of objects with
     ID/CODE/NAME/DETAIL_TEXT/DETAIL_PAGE_URL/TIMESTAMP_X (case-insensitive).
  2. --live + env BITRIX_EXPORT_URL — a GET to a JSON feed endpoint that the
     site developer exposes (recommended: a simple /api/content.json built on
     CIBlockElement::GetList). Optional BITRIX_EXPORT_TOKEN is sent as a
     Bearer header.

Output: shared sync-report contract (new / changed-on-site / deleted / draft
drift) + mirror files under seo/content-mirror/.
"""

from __future__ import annotations

import argparse
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

log = setup_logging("bitrix-content-pull")


def field(item: dict[str, Any], *names: str) -> Any:
    lower = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    code = str(field(item, "CODE", "slug") or "").strip()
    item_id = field(item, "ID", "id")
    slug = code or (f"element-{item_id}" if item_id is not None else "")
    if not slug:
        return None
    text = html_to_text(str(field(item, "DETAIL_TEXT", "PREVIEW_TEXT", "text", "content") or ""))
    title = str(field(item, "NAME", "title") or slug)
    return make_record(
        content_type=str(field(item, "IBLOCK_CODE", "type") or "elements"),
        item_id=item_id,
        slug=slug,
        url=field(item, "DETAIL_PAGE_URL", "url", "link"),
        status="publish" if str(field(item, "ACTIVE", "status") or "Y").upper() in ("Y", "PUBLISH", "1", "TRUE") else "inactive",
        modified=field(item, "TIMESTAMP_X", "modified", "DATE_MODIFY"),
        title=title,
        text=text,
    )


def live_fetch(url: str) -> list[dict[str, Any]]:
    headers = {"User-Agent": "seo-cycle bitrix-content-pull", "Accept": "application/json"}
    token = os.environ.get("BITRIX_EXPORT_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, list):
        return data
    for key in ("items", "elements", "result", "data"):
        if isinstance(data.get(key), list):
            return data[key]
    raise RuntimeError("feed did not return a JSON list (or items/elements/result/data key)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--input-file", help="JSON export of infoblock elements")
    parser.add_argument("--live", action="store_true", help="GET the BITRIX_EXPORT_URL JSON feed")
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
    log = setup_logging("bitrix-content-pull", project_root, cfg)

    if args.input_file:
        raw = json.loads(pathlib.Path(args.input_file).expanduser().read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("items") or raw.get("elements") or []
    elif args.live:
        url = os.environ.get("BITRIX_EXPORT_URL", "").strip()
        if not url:
            print("ERROR: set BITRIX_EXPORT_URL env (a JSON feed endpoint on the site)", file=sys.stderr)
            return 2
        try:
            items = live_fetch(url)
        except (RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"ERROR: Bitrix feed pull failed: {exc}", file=sys.stderr)
            return 1
    else:
        print("Provide --input-file <elements.json> or --live with BITRIX_EXPORT_URL.", file=sys.stderr)
        return 0

    records = [record for record in (normalize_item(item) for item in items) if record]
    report = apply_pull(project_root, records, source="bitrix", write=args.write)
    if args.write:
        write_report_bundle(sync_output_paths(project_root), render_sync_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_sync_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
