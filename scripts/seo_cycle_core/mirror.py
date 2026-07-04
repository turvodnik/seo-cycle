"""Shared site→local content-mirror engine used by the CMS pull adapters.

Adapters (wp-content-pull, tilda-content-pull, bitrix-content-pull) normalize
platform items into records `{type, id, slug, url, status, modified, title,
hash, words, text}`; this module owns the mirror files under
`seo/content-mirror/<type>/<slug>.md`, the pull state, the change diff
(new / changed-on-site / deleted-on-site), and draft-drift detection.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
from html.parser import HTMLParser
from typing import Any

from .config import write_text


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


def make_record(*, content_type: str, item_id: Any, slug: str, url: Any, status: Any,
                modified: Any, title: str, text: str) -> dict[str, Any]:
    return {
        "type": content_type,
        "id": item_id,
        "slug": slug,
        "url": url,
        "status": status,
        "modified": modified,
        "title": title,
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


def build_sync_report(records: list[dict[str, Any]], previous: dict[str, Any],
                      drafts: dict[str, dict[str, Any]], *, source: str) -> dict[str, Any]:
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
        "audit_id": "content_sync",
        "source": source,
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


def render_sync_markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        f"# Content Sync (site → local, {report.get('source', 'cms')})",
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


def apply_pull(project_root: pathlib.Path, records: list[dict[str, Any]], *, source: str,
               write: bool) -> dict[str, Any]:
    """Diff against the previous pull; with write=True refresh mirror files + state."""
    mirror, state_path = mirror_paths(project_root)
    previous = load_state(state_path)
    report = build_sync_report(records, previous, local_draft_hashes(project_root), source=source)
    if write:
        for record in records:
            write_mirror_file(mirror, record)
        for key in report["deleted_on_site"]:
            stale = mirror / f"{key}.md"
            if stale.exists():
                stale.unlink()
        state = {
            "generated_at": report["generated_at"],
            "source": source,
            "items": {f"{r['type']}/{r['slug']}": {"id": r["id"], "hash": r["hash"], "modified": r["modified"]}
                      for r in records},
        }
        write_text(state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return report


def sync_output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "content-mirror"
    return {
        "markdown": base / "sync-report.md",
        "json": base / "sync-report.json",
        "latest_markdown": base / "latest-sync-report.md",
        "latest_json": base / "latest-sync-report.json",
    }
