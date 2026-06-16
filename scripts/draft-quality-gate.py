#!/usr/bin/env python3
"""Validate a copy draft against a page-outline v2/v3 brief."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any

from research_package_repair_core import (
    markdown_findings,
    normalize_space,
    normalize_url,
    print_report,
    write_json,
    write_text,
)


FIRST_PERSON_EXPERTISE = re.compile(
    r"\b(in my years|my clients|from what i['’]?ve observed|i have seen|working with clients)\b",
    re.I,
)


def load_outline(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))


def heading_set(text: str, level: int | None = None) -> set[str]:
    headings = set()
    for match in re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, flags=re.M):
        if level is not None and len(match.group(1)) != level:
            continue
        headings.add(normalize_space(match.group(2)).lower())
    return headings


def markdown_link_targets(text: str) -> set[str]:
    targets = set()
    for match in re.findall(r"\]\(([^)]+)\)", text):
        targets.add(normalize_url(match))
    for match in re.findall(r"(?<![A-Za-z0-9])/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", text):
        targets.add(normalize_url(match.strip("`),.;")))
    return {target for target in targets if target}


def has_proof_slot(text: str) -> bool:
    lower = text.lower()
    if any(marker in lower for marker in ("source:", "proof:", "evidence:", "[source", "citation:")):
        return True
    return bool(re.search(r"https?://", text))


def expected_h2(outline: dict[str, Any]) -> list[str]:
    return [normalize_space(section.get("title")) for section in outline.get("sections") or [] if section.get("level") == 2 and section.get("title")]


def expected_h3(outline: dict[str, Any]) -> list[str]:
    headings = []
    for section in outline.get("sections") or []:
        for child in section.get("h3_subsections") or []:
            if isinstance(child, dict) and child.get("title"):
                headings.append(normalize_space(child.get("title")))
            elif isinstance(child, str):
                headings.append(normalize_space(child))
    return headings


def is_public_handoff_draft(draft_path: pathlib.Path) -> bool:
    name = draft_path.name.lower()
    return ".public." in name or ".wp-draft." in name or name.endswith(".public.md") or name.endswith(".wp-draft.md")


def build_report(draft_path: pathlib.Path, outline_path: pathlib.Path) -> dict[str, Any]:
    draft_path = draft_path.expanduser().resolve()
    outline_path = outline_path.expanduser().resolve()
    text = draft_path.read_text(encoding="utf-8")
    outline = load_outline(outline_path)
    public_handoff = is_public_handoff_draft(draft_path)
    h2 = heading_set(text, 2)
    h3 = heading_set(text, 3)
    links = markdown_link_targets(text)
    findings: list[dict[str, Any]] = []

    for title in expected_h2(outline):
        if title.lower() not in h2:
            if public_handoff:
                continue
            findings.append(
                {
                    "id": "missing_h2_heading",
                    "severity": "error",
                    "location": str(draft_path),
                    "message": f"Draft is missing H2 `{title}` from outline.",
                }
            )
    for title in expected_h3(outline):
        if title.lower() not in h3:
            if public_handoff:
                continue
            findings.append(
                {
                    "id": "missing_h3_heading",
                    "severity": "warning",
                    "location": str(draft_path),
                    "message": f"Draft is missing H3 `{title}` from outline.",
                }
            )
    if FIRST_PERSON_EXPERTISE.search(text):
        findings.append(
            {
                "id": "unsafe_first_person_expertise",
                "severity": "error",
                "location": str(draft_path),
                "message": "Draft uses first-person expert/client claims; require real author evidence or rewrite in neutral voice.",
            }
        )
    for url in outline.get("internal_links") or []:
        normalized = normalize_url(url)
        if normalized and normalized not in links:
            findings.append(
                {
                    "id": "missing_internal_link",
                    "severity": "warning",
                    "location": normalized,
                    "message": "Required internal link from outline is missing in draft.",
                }
            )
    if not has_proof_slot(text):
        findings.append(
            {
                "id": "missing_proof_slot",
                "severity": "warning",
                "location": str(draft_path),
                "message": "Draft has no source/proof/citation marker; add evidence for claims and numbers.",
            }
        )
    faq_questions = [normalize_space(item.get("question")) for item in outline.get("faq") or [] if isinstance(item, dict)]
    for question in faq_questions:
        if question and question.lower() not in text.lower():
            if public_handoff and "## faq" in text.lower():
                continue
            findings.append(
                {
                    "id": "missing_faq_question",
                    "severity": "warning",
                    "location": str(draft_path),
                    "message": f"FAQ question `{question}` is in outline but missing in draft.",
                }
            )
    if public_handoff:
        findings.append(
            {
                "id": "public_localized_heading_check",
                "severity": "info",
                "location": str(draft_path),
                "message": "Public/WP draft uses localized reader-facing headings; exact internal outline H2/H3/FAQ placeholder matching was skipped.",
            }
        )

    return {
        "script": "draft-quality-gate",
        "summary": {
            "findings": len(findings),
            "expected_h2": len(expected_h2(outline)),
            "expected_h3": len(expected_h3(outline)),
            "required_internal_links": len(outline.get("internal_links") or []),
            "public_handoff": public_handoff,
        },
        "outputs": {
            "json": str(draft_path.with_suffix(".draft-quality-gate.json")),
            "markdown": str(draft_path.with_suffix(".draft-quality-gate.md")),
        },
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return markdown_findings("Draft Quality Gate", report["summary"], report.get("findings"))


def write_outputs(draft_path: pathlib.Path, report: dict[str, Any]) -> None:
    draft_path = draft_path.expanduser().resolve()
    write_json(draft_path.with_suffix(".draft-quality-gate.json"), report)
    write_text(draft_path.with_suffix(".draft-quality-gate.md"), render_markdown(report))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", help="Draft markdown file")
    parser.add_argument("--outline", required=True, help="page-outline-v2 JSON file")
    parser.add_argument("--write", action="store_true", help="Write draft quality reports next to the draft")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    args = parser.parse_args()

    report = build_report(pathlib.Path(args.draft), pathlib.Path(args.outline))
    if args.write:
        write_outputs(pathlib.Path(args.draft), report)
    print_report(report, args.format, render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
