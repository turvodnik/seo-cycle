#!/usr/bin/env python3
"""Wiki preflight before publishing or editing project content."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from wiki_common import CONFIG, WIKI_ROOT, canonical_url, clean_text, ensure_wiki_tree, read_json, utc_now, write_json


project_cfg = CONFIG.get("project", {}) if isinstance(CONFIG.get("project"), dict) else {}
TECHNICAL_BRAND = str(project_cfg.get("brand_name_technical") or "").strip()
PUBLIC_BRAND = str(project_cfg.get("brand_name_user_facing") or project_cfg.get("name") or "").strip()

BAD_PUBLIC_PATTERNS = {
    "service_seo_terms": re.compile(r"\b(?:интент|семантик|сущност|SEO-текст|source-lock)\b", re.I),
    "visible_slug_path": re.compile(r"\b[a-z0-9][a-z0-9_-]{2,}/[a-z0-9][a-z0-9_-]{2,}\b", re.I),
    "stock_sensitive": re.compile(r"\b(?:наличи[ея]|остатк[аиов]|актуальн\w*\s+выгрузк\w*)\b", re.I),
    "service_note": re.compile(r"(?:Материал\s+подготовлен|на\s+дату\s+выгрузки|перед\s+покупкой\s+проверяйте)", re.I),
}

if TECHNICAL_BRAND and PUBLIC_BRAND and TECHNICAL_BRAND.lower() != PUBLIC_BRAND.lower():
    BAD_PUBLIC_PATTERNS["technical_brand_in_public_copy"] = re.compile(rf"\b{re.escape(TECHNICAL_BRAND)}\b", re.I)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def text_blob(row: dict) -> str:
    return " ".join(
        clean_text(row.get(key, ""))
        for key in ("title", "slug", "url", "status", "h1")
    )


def find_target(url: str, slug: str) -> tuple[dict | None, list[dict]]:
    articles = read_jsonl(WIKI_ROOT / "state" / "articles.jsonl")
    categories = read_jsonl(WIKI_ROOT / "state" / "categories.jsonl")
    brands = read_jsonl(WIKI_ROOT / "state" / "brands.jsonl")
    all_rows = articles + categories + brands
    normalized = canonical_url(url) if url else ""
    target = None
    if normalized:
        target = next((row for row in all_rows if canonical_url(row.get("url", "")) == normalized), None)
    if not target and slug:
        target = next((row for row in all_rows if row.get("slug") == slug), None)

    target_slug = slug or (target or {}).get("slug", "")
    duplicates = []
    if target_slug:
        base_slug = re.sub(r"-\d+$", "", target_slug)
        duplicates = [
            row
            for row in all_rows
            if row.get("slug") != target_slug and re.sub(r"-\d+$", "", str(row.get("slug", ""))) == base_slug
        ]
    return target, duplicates


def related_rows(query: str, target: dict | None) -> list[dict]:
    query_tokens = {token.lower() for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", query or "")}
    if target:
        query_tokens.update(token.lower() for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", text_blob(target)))
    rows = []
    for path in [
        WIKI_ROOT / "state" / "articles.jsonl",
        WIKI_ROOT / "state" / "categories.jsonl",
        WIKI_ROOT / "state" / "brands.jsonl",
        WIKI_ROOT / "state" / "products.jsonl",
    ]:
        for row in read_jsonl(path):
            row_tokens = {token.lower() for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]{3,}", text_blob(row))}
            score = len(query_tokens & row_tokens)
            if score:
                rows.append({"score": score, "type": row.get("type"), "slug": row.get("slug"), "title": row.get("title"), "url": row.get("url")})
    return sorted(rows, key=lambda item: (-item["score"], item.get("type") or "", item.get("slug") or ""))[:20]


def scan_draft(path: Path | None) -> list[dict]:
    if not path or not path.exists():
        return []
    text = public_draft_text(path.read_text(encoding="utf-8", errors="ignore"))
    issues = []
    for label, pattern in BAD_PUBLIC_PATTERNS.items():
        for match in pattern.finditer(text):
            start = max(0, match.start() - 80)
            end = min(len(text), match.end() + 80)
            issues.append({"severity": "blocker", "pattern": label, "snippet": " ".join(text[start:end].split())})
            break
    return issues


def public_draft_text(text: str) -> str:
    """Return the visible/public portion of a draft, not frontmatter or link targets."""
    match = re.match(r"^---\n.*?\n---\n(.*)$", text, flags=re.S)
    if match:
        text = match.group(1)
    for marker in ["\n## JSON-LD", "\n## Внутренние ссылки", "\n## Чек-лист", "\n## Альты"]:
        index = text.find(marker)
        if index > 0:
            text = text[:index]
            break
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r'href=["\'][^"\']+["\']', "", text, flags=re.I)
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="")
    parser.add_argument("--slug", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    ensure_wiki_tree()
    manifest = read_json(WIKI_ROOT / "project-manifest.json", {})
    target, duplicates = find_target(args.url, args.slug)
    draft_issues = scan_draft(args.draft)
    related = related_rows(args.query or args.slug or args.url, target)

    blockers = []
    warnings = []
    if not manifest:
        blockers.append("wiki manifest missing; run wiki-export-project-state.py first")
    if duplicates:
        warnings.append("possible duplicate slug/intent: " + ", ".join(row.get("slug", "") for row in duplicates[:8]))
    if draft_issues:
        blockers.extend(f"draft issue: {issue['pattern']}" for issue in draft_issues)

    result = {
        "generated_at": utc_now(),
        "target": target,
        "duplicates": duplicates,
        "related": related,
        "draft_issues": draft_issues,
        "blockers": blockers,
        "warnings": warnings,
        "decision": "blocked" if blockers else "pass_with_warnings" if warnings else "pass",
        "required_next_step": "fix blockers before publish/update" if blockers else "safe to continue with explicit task scope",
    }

    if args.write:
        out = WIKI_ROOT / "preflight" / f"preflight-{args.slug or slug_from_url(args.url) or 'query'}-{utc_now().replace(':', '').replace('+', 'Z')}.json"
        write_json(out, result)
        latest_json = WIKI_ROOT / "preflight" / "wiki-preflight.json"
        latest_md = WIKI_ROOT / "preflight" / "wiki-preflight.md"
        write_json(latest_json, {**result, "history_report": str(out)})
        lines = [
            "# Wiki Preflight",
            "",
            f"- Generated: `{result['generated_at']}`",
            f"- Decision: `{result['decision']}`",
            f"- Blockers: `{len(blockers)}`",
            f"- Warnings: `{len(warnings)}`",
            f"- History report: `{out}`",
            "",
        ]
        if blockers:
            lines.append("## Blockers")
            lines.extend(f"- {item}" for item in blockers)
            lines.append("")
        if warnings:
            lines.append("## Warnings")
            lines.extend(f"- {item}" for item in warnings)
            lines.append("")
        if related:
            lines.append("## Related Records")
            for item in related[:12]:
                lines.append(f"- {item.get('type') or 'record'} | {item.get('title') or item.get('slug')} | {item.get('url')}")
            lines.append("")
        latest_md.write_text("\n".join(lines), encoding="utf-8")
        print(json.dumps({"status": result["decision"], "report": str(out), "latest": str(latest_json), "blockers": len(blockers), "warnings": len(warnings)}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if blockers else 0


def slug_from_url(url: str) -> str:
    if not url:
        return ""
    return Path(urlparse(url).path.rstrip("/")).name


if __name__ == "__main__":
    raise SystemExit(main())
