#!/usr/bin/env python3
"""Build a compact context pack from the project SEO wiki."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from wiki_common import PROJECT_SLUG, WIKI_ROOT, clean_text, ensure_wiki_tree, read_json, utc_now, write_json


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_row(row: dict, tokens: set[str]) -> int:
    text = " ".join(str(row.get(key, "")) for key in ("title", "slug", "url", "h1", "sku"))
    row_tokens = {token.lower() for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", text)}
    return len(tokens & row_tokens)


def top_rows(path: Path, tokens: set[str], limit: int) -> list[dict]:
    rows = read_jsonl(path)
    scored = [(score_row(row, tokens), row) for row in rows]
    scored = [(score, row) for score, row in scored if score > 0]
    return [row for score, row in sorted(scored, key=lambda item: -item[0])[:limit]]


def render_rows(title: str, rows: list[dict]) -> list[str]:
    lines = [f"## {title}"]
    if not rows:
        return lines + ["- нет релевантных записей", ""]
    for row in rows:
        parts = [str(row.get("title") or row.get("slug") or row.get("sku") or "без названия")]
        if row.get("url"):
            parts.append(str(row["url"]))
        if row.get("status"):
            parts.append(f"status={row['status']}")
        if row.get("faq_count") is not None:
            parts.append(f"FAQ={row.get('faq_count')}")
        lines.append("- " + " | ".join(parts))
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--max-rows", type=int, default=12)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    ensure_wiki_tree()
    tokens = {token.lower() for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", args.topic)}
    manifest = read_json(WIKI_ROOT / "project-manifest.json", {})

    articles = top_rows(WIKI_ROOT / "state" / "articles.jsonl", tokens, args.max_rows)
    categories = top_rows(WIKI_ROOT / "state" / "categories.jsonl", tokens, args.max_rows)
    brands = top_rows(WIKI_ROOT / "state" / "brands.jsonl", tokens, args.max_rows)
    products = top_rows(WIKI_ROOT / "state" / "products.jsonl", tokens, args.max_rows)
    api = top_rows(WIKI_ROOT / "api-catalog" / "api-candidates.jsonl", tokens, args.max_rows)

    rules = []
    for path in [WIKI_ROOT / "rules" / "project-rules.md", WIKI_ROOT / "rules" / "content-taste.md", WIKI_ROOT / "rules" / "lean-engineering.md"]:
        if path.exists():
            rules.append(path.read_text(encoding="utf-8"))

    lines = [
        "# Wiki Context Pack",
        "",
        f"- Generated: `{utc_now()}`",
        f"- Topic: `{args.topic}`",
        f"- Project: `{manifest.get('project', PROJECT_SLUG)}`",
        "",
        "## Read Order",
        "1. Project rules",
        "2. Related articles/categories/brands/products",
        "3. Latest reports only if evidence is missing",
        "4. Raw exports only when explicitly needed",
        "",
        "## Project Rules Summary",
        clean_text('\\n'.join(rules))[:4000] or "rules missing",
        "",
    ]
    lines += render_rows("Related Articles", articles)
    lines += render_rows("Related Categories", categories)
    lines += render_rows("Related Brands", brands)
    lines += render_rows("Related Products", products)
    lines += render_rows("Related API Candidates", api)
    lines += [
        "## Blocked Raw Context",
        "- `seo/research/raw/**` не читать без необходимости.",
        "- `seo/cache/**` не читать целиком.",
        "- `.env` не читать в контекст и не копировать в отчёты.",
        "",
    ]

    output = "\n".join(lines)
    if args.write:
        safe_topic = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_-]+", "-", args.topic).strip("-").lower()[:80] or "topic"
        out = WIKI_ROOT / "context" / f"context-pack-{safe_topic}.md"
        latest = WIKI_ROOT / "context" / "latest-context-pack.md"
        latest_json = WIKI_ROOT / "context" / "latest-context-pack.json"
        out.write_text(output, encoding="utf-8")
        latest.write_text(output, encoding="utf-8")
        payload = {
            "status": "ok",
            "path": str(out),
            "latest": str(latest),
            "chars": len(output),
            "topic": args.topic,
            "generated_at": utc_now(),
        }
        write_json(latest_json, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
