#!/usr/bin/env python3
"""Ingest a local SEO report into the project wiki report index."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from wiki_common import WIKI_ROOT, clean_text, ensure_wiki_tree, utc_now, write_json


def classify(path: Path, text: str) -> str:
    name = path.name.lower()
    blob = (name + "\n" + text[:4000]).lower()
    if "gsc" in blob or "search console" in blob:
        return "search-console"
    if "yandex" in blob or "яндекс" in blob:
        return "yandex"
    if "neuronwriter" in blob:
        return "neuronwriter"
    if "perplexity" in blob:
        return "perplexity"
    if "anchor" in blob or "link" in blob or "ссыл" in blob:
        return "links"
    if "category" in blob or "product_cat" in blob:
        return "category"
    if "quality" in blob:
        return "quality"
    return "general"


def summarize(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    clean = clean_text(raw)
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    urls = sorted(set(re.findall(r"https?://[^\s)\"']+", raw)))[:40]
    blockers = len(re.findall(r"\b(?:blocker|critical|ошибк|проблем|warning|warn)\b", raw, re.I))
    return {
        "source_path": str(path),
        "sha256_16": digest,
        "ingested_at": utc_now(),
        "kind": classify(path, raw),
        "chars": len(raw),
        "summary": clean[:1500],
        "urls": urls,
        "issue_signal_count": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--note", default="")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if not args.report.exists():
        raise SystemExit(f"Report not found: {args.report}")
    ensure_wiki_tree()
    item = summarize(args.report)
    item["note"] = args.note

    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", args.report.stem).strip("-")[:100] or "report"
    out_json = WIKI_ROOT / "reports" / f"{safe}.json"
    out_md = WIKI_ROOT / "reports" / f"{safe}.md"

    if args.write:
        write_json(out_json, item)
        out_md.write_text(
            f"""# {args.report.name}

- Ingested: `{item['ingested_at']}`
- Kind: `{item['kind']}`
- Source: `{item['source_path']}`
- Hash: `{item['sha256_16']}`
- Issue signal count: `{item['issue_signal_count']}`

## Summary
{item['summary']}

## URLs
{chr(10).join(f"- {url}" for url in item['urls']) or "- нет"}
""",
            encoding="utf-8",
        )
        print(json.dumps({"status": "ok", "json": str(out_json), "md": str(out_md)}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
