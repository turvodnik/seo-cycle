#!/usr/bin/env python3
"""Pull published WordPress content into a local mirror and report site-side changes.

Site → local half of two-way sync (publishing scripts are the local → site
half; the knowledge-hub `wp-blog-to-obsidian.py` serves the wiki instead).
Read-only for WordPress: GET /wp-json/wp/v2/posts|pages with pagination.

Each pull refreshes `seo/content-mirror/<type>/<slug>.md` (frontmatter: id,
url, status, modified, content hash + normalized text) and diffs against the
previous pull state: new / changed / deleted on the site. Posts whose slug
matches a local draft are checked for drift — a changed hash after the draft
was written means someone edited the page directly on the site.

Env: WP_BASE_URL (+ optional WP_USER/WP_APP_PASSWORD for non-public statuses).
Default is offline (--input-file <rest-export.json>); --live makes real GETs.
Output: seo/content-mirror/sync-report.md/json (+latest) with --write.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for, write_text
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("wp-content-pull")

CONTENT_TYPES = ("posts", "pages")
MAX_PAGES_DEFAULT = 10  # x100 items per type
FIELDS = "id,slug,link,status,modified,title,content"


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        if tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html or "")
    text = "".join(parser.parts)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def content_hash(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:16]


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
    text = html_to_text(html or "")
    return {
        "type": content_type,
        "id": item.get("id"),
        "slug": slug,
        "url": item.get("link"),
        "status": item.get("status"),
        "modified": item.get("modified"),
        "title": html_to_text(title_text or ""),
        "hash": content_hash(text),
        "words": len(text.split()),
        "text": text,
    }


def mirror_paths(project_root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    mirror = project_root / "seo" / "content-mirror"
    return mirror, mirror / "mirror-state.json"


def load_state(state_path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_mirror_file(mirror: pathlib.Path, record: dict[str, Any]) -> None:
    body = [
        "---",
        f"id: {record['id']}",
        f"type: {record['type']}",
        f"url: {record['url']}",
        f"status: {record['status']}",
        f"modified: {record['modified']}",
        f"content_hash: {record['hash']}",
        f"words: {record['words']}",
        "---",
        "",
        f"# {record['title']}",
        "",
        record["text"],
        "",
    ]
    write_text(mirror / record["type"] / f"{record['slug']}.md", "\n".join(body))


def local_draft_hashes(project_root: pathlib.Path) -> dict[str, dict[str, Any]]:
    """slug -> {hash, path, mtime} for local drafts (best-effort slug matching)."""
    drafts: dict[str, dict[str, Any]] = {}
    for pattern in ("seo/research-package/drafts/*.md", "seo/drafts/*.md", "06-drafts/*.md"):
        for path in sorted(project_root.glob(pattern)):
            if ".draft-quality-gate" in path.name:
                continue
            slug = path.stem.replace(".publish", "").replace(".wp-draft", "").replace(".public", "")
            try:
                text = html_to_text(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            drafts[slug] = {"hash": content_hash(text), "path": str(path.relative_to(project_root)),
                            "mtime": path.stat().st_mtime}
    return drafts


def build_report(records: list[dict[str, Any]], previous: dict[str, Any],
                 drafts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    current_keys = {f"{record['type']}/{record['slug']}": record for record in records}
    prev_items = previous.get("items", {}) if isinstance(previous.get("items"), dict) else {}

    new_items = sorted(key for key in current_keys if key not in prev_items)
    deleted = sorted(key for key in prev_items if key not in current_keys)
    changed = sorted(
        key for key, record in current_keys.items()
        if key in prev_items and prev_items[key].get("hash") != record["hash"]
    )

    drift = []
    for record in records:
        draft = drafts.get(record["slug"])
        if draft and draft["hash"] != record["hash"]:
            drift.append({"slug": record["slug"], "url": record["url"], "draft": draft["path"],
                          "note": "site content differs from the local draft"})

    return {
        "audit_id": "wp_content_sync",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "counts": {
            "mirrored": len(records),
            "new": len(new_items),
            "changed_on_site": len(changed),
            "deleted_on_site": len(deleted),
            "draft_drift": len(drift),
        },
        "new": new_items[:50],
        "changed_on_site": [
            {"key": key, "url": current_keys[key]["url"], "modified": current_keys[key]["modified"],
             "previous_hash": prev_items.get(key, {}).get("hash"), "hash": current_keys[key]["hash"]}
            for key in changed[:50]
        ],
        "deleted_on_site": deleted[:50],
        "draft_drift": drift[:50],
        "previous_pull": previous.get("generated_at"),
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "# WP Content Sync (site → local)",
        "",
        f"- Generated: {report['generated_at']} (previous pull: {report.get('previous_pull') or 'first pull'})",
        f"- Mirrored: {counts['mirrored']} · new: {counts['new']} · changed on site: {counts['changed_on_site']}"
        f" · deleted: {counts['deleted_on_site']} · draft drift: {counts['draft_drift']}",
    ]
    if report["changed_on_site"]:
        lines.extend(["", "## Changed on site since last pull", ""])
        for row in report["changed_on_site"][:15]:
            lines.append(f"- {row['url']} (modified {row['modified']})")
    if report["draft_drift"]:
        lines.extend(["", "## Draft drift (edited directly on the site?)", ""])
        for row in report["draft_drift"][:15]:
            lines.append(f"- `{row['slug']}` — {row['url']} vs {row['draft']}")
    if report["deleted_on_site"]:
        lines.extend(["", "## Deleted on site", ""])
        lines.extend(f"- {key}" for key in report["deleted_on_site"][:15])
    if report["new"]:
        lines.extend(["", "## New on site", ""])
        lines.extend(f"- {key}" for key in report["new"][:15])
    lines.extend(["", "Mirror: `seo/content-mirror/` (git-versioned text snapshots, indexed by RAG)."])
    return "\n".join(lines) + "\n"


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "content-mirror"
    return {
        "markdown": base / "sync-report.md",
        "json": base / "sync-report.json",
        "latest_markdown": base / "latest-sync-report.md",
        "latest_json": base / "latest-sync-report.json",
    }


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

    mirror, state_path = mirror_paths(project_root)
    previous = load_state(state_path)
    report = build_report(records, previous, local_draft_hashes(project_root))

    if args.write:
        for record in records:
            write_mirror_file(mirror, record)
        # prune mirror files for items deleted on the site
        for key in report["deleted_on_site"]:
            stale = mirror / f"{key}.md"
            if stale.exists():
                stale.unlink()
        state = {
            "generated_at": report["generated_at"],
            "items": {f"{r['type']}/{r['slug']}": {"id": r["id"], "hash": r["hash"], "modified": r["modified"]}
                      for r in records},
        }
        write_text(state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
