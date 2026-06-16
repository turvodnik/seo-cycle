#!/usr/bin/env python3
"""Build a safe, curated corpus for Graphify.

Graphify is useful for relationship discovery, but the project root contains
raw exports, screenshots, caches, and local credentials. This script creates a
small source-of-truth corpus from wiki, distillates, vector JSONL, and v3 briefs.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from wiki_common import GRAPH_CORPUS_ROOT, ROOT, WIKI_ROOT, ensure_wiki_tree, utc_now, write_json


CORPUS_ROOT = GRAPH_CORPUS_ROOT
DEFAULT_MAX_BYTES = 450_000

SAFE_WIKI_DIRS = [
    "rules",
    "state",
    "articles",
    "categories",
    "brands",
    "reports",
    "frameworks",
    "api-catalog",
]

SAFE_SINGLE_FILES = [
    ROOT / "seo" / "research-package" / "semantic-core.csv",
    ROOT / "seo" / "research-package" / "content-plan.csv",
    ROOT / "seo" / "research-package" / "final-clusters.md",
    ROOT / "seo" / "research-package" / "semantic-architecture-final.json",
    ROOT / "seo" / "research-package" / "entity-map.md",
    ROOT / "seo" / "research-package" / "entity-map.yaml",
    ROOT / "seo" / "research-package" / "technical-spec.md",
    ROOT / "seo" / "research-package" / "research-package-quality.md",
    ROOT / "seo" / "research-package" / "page-outline-quality.md",
]

SAFE_GLOBS = [
    ROOT / "seo" / "research" / "vector",
    ROOT / "seo" / "research-package" / "vector",
    ROOT / "seo" / "research-package" / "page-outlines-v3",
    ROOT / "seo" / "research-package" / "copywriter-ready",
]

SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"ya29\.[0-9A-Za-z_\-]+"),
    re.compile(r"sk-[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[0-9A-Za-z_\-]{16,}"),
]


def should_copy(path: Path, max_bytes: int) -> tuple[bool, str]:
    if path.name.startswith("."):
        return False, "hidden"
    if path.suffix.lower() not in {".md", ".json", ".jsonl", ".csv", ".yaml", ".yml", ".txt"}:
        return False, "unsupported"
    if path.stat().st_size > max_bytes:
        return False, "too_large"
    text = path.read_text(encoding="utf-8", errors="ignore")
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        return False, "secret_like"
    return True, "ok"


def copy_file(source: Path, target: Path, max_bytes: int, copied: list[dict], skipped: list[dict]) -> None:
    allowed, reason = should_copy(source, max_bytes)
    record = {"source": str(source.relative_to(ROOT)), "target": str(target.relative_to(ROOT)), "bytes": source.stat().st_size}
    if not allowed:
        skipped.append({**record, "reason": reason})
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied.append(record)


def copy_tree(source_dir: Path, target_dir: Path, max_bytes: int, copied: list[dict], skipped: list[dict]) -> None:
    if not source_dir.exists():
        return
    for source in sorted(source_dir.rglob("*")):
        if not source.is_file():
            continue
        rel = source.relative_to(source_dir)
        copy_file(source, target_dir / rel, max_bytes, copied, skipped)


def write_readme(copied: list[dict], skipped: list[dict], max_bytes: int) -> None:
    lines = [
        "# Graphify Corpus",
        "",
        f"- Generated: `{utc_now()}`",
        f"- Copied files: `{len(copied)}`",
        f"- Skipped files: `{len(skipped)}`",
        f"- Max file size: `{max_bytes}` bytes",
        "",
        "This corpus is intentionally curated. It excludes `.env`, raw exports, caches, screenshots, and oversized files.",
        "",
        "## Source Layers",
        "- `wiki/`: project truth, rules, articles, categories, brands, reports.",
        "- `distillates/`: latest summaries from external tools.",
        "- `vectors/`: entities, relations, triplets, answer units, prompts.",
        "- `research-package/`: semantic architecture, briefs, v3 outlines.",
        "",
    ]
    if skipped:
        lines += ["## Skipped", ""]
        for item in skipped[:80]:
            lines.append(f"- `{item['source']}`: {item['reason']}")
    (CORPUS_ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()

    ensure_wiki_tree()
    copied: list[dict] = []
    skipped: list[dict] = []

    if args.write:
        if CORPUS_ROOT.exists():
            shutil.rmtree(CORPUS_ROOT)
        CORPUS_ROOT.mkdir(parents=True, exist_ok=True)

        for name in SAFE_WIKI_DIRS:
            copy_tree(WIKI_ROOT / name, CORPUS_ROOT / "wiki" / name, args.max_bytes, copied, skipped)

        for source in sorted((ROOT / "seo" / "research" / "distillates").glob("*/latest-summary.*")):
            provider = source.parent.name
            copy_file(source, CORPUS_ROOT / "distillates" / provider / source.name, args.max_bytes, copied, skipped)

        for source_dir in SAFE_GLOBS:
            copy_tree(source_dir, CORPUS_ROOT / "research-package" / source_dir.name, args.max_bytes, copied, skipped)

        for source in SAFE_SINGLE_FILES:
            if source.exists():
                copy_file(source, CORPUS_ROOT / "research-package" / source.name, args.max_bytes, copied, skipped)

        write_readme(copied, skipped, args.max_bytes)
        write_json(WIKI_ROOT / "graph" / "graphify-corpus-manifest.json", {
            "generated_at": utc_now(),
            "corpus_root": str(CORPUS_ROOT),
            "copied_count": len(copied),
            "skipped_count": len(skipped),
            "copied": copied,
            "skipped": skipped,
        })

    print(json.dumps({
        "status": "ok",
        "write": args.write,
        "corpus_root": str(CORPUS_ROOT),
        "copied": len(copied),
        "skipped": len(skipped),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
