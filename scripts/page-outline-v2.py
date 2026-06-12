#!/usr/bin/env python3
"""Generate section-level SEO/AEO/GEO page outlines from a research package.

This bridges the gap between a site-level research package and a copywriter-
ready outline. It preserves the architecture/page type selected by SERP data
and adds section-level word counts, entities, visuals, copywriter notes,
Answer Units, evidence requirements, schema, and internal links.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import re
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from seo_cycle_core.config import write_text


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: Any, fallback: str = "page") -> str:
    slug = re.sub(r"[^a-z0-9а-яё]+", "-", str(value or "").strip().lower(), flags=re.IGNORECASE).strip("-")
    return slug[:96].strip("-") or fallback


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def read_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "_", str(value or "").strip().lower(), flags=re.IGNORECASE).strip("_")


def package_dir(raw: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(raw).expanduser().resolve()
    return path.parent if path.is_file() else path


def load_entities(raw: dict[str, Any]) -> list[dict[str, Any]]:
    entities = raw.get("entities")
    if isinstance(entities, dict):
        entities = list(entities.values())
    if not isinstance(entities, list):
        return []
    result = []
    for item in entities:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "id": item.get("id") or slugify(item.get("name")),
                "name": item.get("name") or item.get("entity") or item.get("id"),
                "priority": item.get("coverage_priority") or item.get("priority") or "P3",
                "target_clusters": item.get("target_clusters") or [],
                "related": item.get("related_entities") or item.get("related") or [],
                "attributes": item.get("attributes") or [],
            }
        )
    return result


def match_cluster(architecture: dict[str, Any], content_rows: list[dict[str, str]], selector: str | None) -> tuple[dict[str, Any], dict[str, str]]:
    clusters = architecture.get("clusters") if isinstance(architecture.get("clusters"), list) else []
    if not clusters:
        raise SystemExit("No clusters found in semantic-architecture-final.json")

    def cluster_matches(cluster: dict[str, Any]) -> bool:
        if not selector:
            return bool(cluster.get("mvp")) or cluster == clusters[0]
        candidates = [
            cluster.get("id"),
            cluster.get("name"),
            cluster.get("primary_keyword"),
            cluster.get("suggested_url"),
            cluster.get("url"),
        ]
        return normalize(selector) in {normalize(item) for item in candidates}

    cluster = next((item for item in clusters if isinstance(item, dict) and cluster_matches(item)), None)
    if cluster is None:
        raise SystemExit(f"No cluster/page matched selector: {selector}")
    url = cluster.get("suggested_url") or cluster.get("url") or ""
    primary = cluster.get("primary_keyword") or ""
    content = next(
        (
            row
            for row in content_rows
            if row.get("url") == url
            or normalize(row.get("source_cluster")) == normalize(cluster.get("id"))
            or normalize(row.get("primary_keyword")) == normalize(primary)
        ),
        {},
    )
    return cluster, content


def cluster_selector(cluster: dict[str, Any]) -> str:
    return str(
        cluster.get("suggested_url")
        or cluster.get("url")
        or cluster.get("id")
        or cluster.get("primary_keyword")
        or cluster.get("name")
        or ""
    )


def selected_cluster_selectors(
    architecture: dict[str, Any],
    *,
    selector: str | None = None,
    all_mvp: bool = False,
    priorities: list[str] | None = None,
) -> list[str | None]:
    clusters = architecture.get("clusters") if isinstance(architecture.get("clusters"), list) else []
    if not all_mvp and not priorities:
        return [selector]

    wanted_priorities = {normalize(item) for item in priorities or [] if item}
    selected: list[str] = []
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        is_mvp = str(cluster.get("mvp")).strip().lower() in {"true", "1", "yes"}
        priority = normalize(cluster.get("priority"))
        if all_mvp and is_mvp:
            selected.append(cluster_selector(cluster))
            continue
        if wanted_priorities and priority in wanted_priorities:
            selected.append(cluster_selector(cluster))
    return selected or [selector]


def select_entities(entities: list[dict[str, Any]], cluster_id: str, primary_keyword: str, limit: int = 8) -> list[dict[str, Any]]:
    scored = []
    keyword_norm = normalize(primary_keyword).replace("_", " ")
    for entity in entities:
        targets = {normalize(item) for item in entity.get("target_clusters", [])}
        name = str(entity.get("name") or "")
        score = 0
        if normalize(cluster_id) in targets:
            score += 5
        if name and name.lower() in keyword_norm:
            score += 3
        if entity.get("priority") == "P1":
            score += 2
        elif entity.get("priority") == "P2":
            score += 1
        if score:
            scored.append((score, entity))
    if not scored:
        scored = [(1, entity) for entity in entities[:limit]]
    return [entity for _, entity in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]


def split_keywords(cluster: dict[str, Any]) -> list[str]:
    keywords = [cluster.get("primary_keyword")]
    secondary = cluster.get("secondary_keywords") or []
    if isinstance(secondary, str):
        secondary = [part.strip() for part in secondary.split("|")]
    keywords.extend(secondary)
    return [str(item) for item in keywords if item]


def schema_for_page(page_type: str) -> list[str]:
    lower = page_type.lower()
    schema = ["BreadcrumbList", "FAQPage"]
    if "tool" in lower or "quiz" in lower or "detector" in lower:
        schema.insert(0, "WebApplication")
    elif "review" in lower or "comparison" in lower:
        schema.insert(0, "ItemList")
        schema.append("Review")
    else:
        schema.insert(0, "Article")
    return schema


def seo_meta_for_page(page: dict[str, Any], primary: str, page_type: str) -> dict[str, Any]:
    title = str(page.get("page_title") or page.get("name") or primary or "").strip()
    url = str(page.get("url") or page.get("suggested_url") or "").strip()
    title_tag = title if title else primary
    if primary and primary.lower() not in title_tag.lower():
        title_tag = f"{title_tag}: {primary}"
    page_type_label = "tool" if "tool" in page_type.lower() else "guide"
    meta_description = (
        f"Use this {page_type_label} to answer {primary} with SERP-matched structure, entity coverage, "
        "source-backed proof, FAQ, schema, and internal links."
    ).strip()
    return {
        "title_tag": title_tag[:62],
        "meta_description": meta_description[:155],
        "slug": url.rstrip("/").split("/")[-1] if url else slugify(primary),
        "canonical": url,
        "alt_text_guidance": "Alt text must describe the actual screenshot/table/result state and include the page task only when natural.",
        "source_note": "Generated from final research architecture; do not change page type without SERP re-validation.",
    }


def template_sections(page_type: str) -> list[dict[str, Any]]:
    lower = page_type.lower()
    if "tool" in lower:
        return [
            {"title": "Key Takeaways", "level": 2, "min": 45, "max": 80, "kind": "answer"},
            {"title": "What This Tool Does and Who It Helps", "level": 2, "min": 130, "max": 190, "kind": "definition"},
            {"title": "How to Use the Tool Step by Step", "level": 2, "min": 180, "max": 260, "kind": "howto"},
            {"title": "Accuracy, Privacy, and Real-World Limits", "level": 2, "min": 170, "max": 240, "kind": "trust"},
            {"title": "What to Do After You Get a Result", "level": 2, "min": 140, "max": 220, "kind": "conversion"},
            {"title": "Frequently Asked Questions", "level": 2, "min": 220, "max": 320, "kind": "faq"},
        ]
    if "quiz" in lower or "detector" in lower:
        return [
            {"title": "Key Takeaways", "level": 2, "min": 45, "max": 80, "kind": "answer"},
            {"title": "What the Quiz Detects", "level": 2, "min": 120, "max": 180, "kind": "definition"},
            {"title": "Inputs, Questions, and Scoring Logic", "level": 2, "min": 180, "max": 260, "kind": "howto"},
            {"title": "How to Interpret the Result", "level": 2, "min": 160, "max": 240, "kind": "answer"},
            {"title": "Limitations and When to Ask an Expert", "level": 2, "min": 120, "max": 180, "kind": "trust"},
            {"title": "Frequently Asked Questions", "level": 2, "min": 220, "max": 320, "kind": "faq"},
        ]
    if "hub" in lower or "gallery" in lower or "recommendation" in lower:
        return [
            {"title": "Key Takeaways", "level": 2, "min": 45, "max": 80, "kind": "answer"},
            {"title": "Recommendation Framework", "level": 2, "min": 160, "max": 240, "kind": "definition"},
            {"title": "Best Options by User Type", "level": 2, "min": 260, "max": 420, "kind": "list"},
            {"title": "Comparison Table and Visual Examples", "level": 2, "min": 180, "max": 280, "kind": "visual"},
            {"title": "Mistakes, Edge Cases, and Limitations", "level": 2, "min": 140, "max": 220, "kind": "trust"},
            {"title": "Frequently Asked Questions", "level": 2, "min": 220, "max": 320, "kind": "faq"},
        ]
    return [
        {"title": "Key Takeaways", "level": 2, "min": 45, "max": 80, "kind": "answer"},
        {"title": "Short Definition and Search Intent Answer", "level": 2, "min": 100, "max": 160, "kind": "definition"},
        {"title": "Decision Framework", "level": 2, "min": 220, "max": 340, "kind": "howto"},
        {"title": "Examples, Tables, and Practical Scenarios", "level": 2, "min": 240, "max": 380, "kind": "visual"},
        {"title": "Common Mistakes and Limits", "level": 2, "min": 140, "max": 220, "kind": "trust"},
        {"title": "Frequently Asked Questions", "level": 2, "min": 220, "max": 320, "kind": "faq"},
    ]


def section_visual(kind: str, page_type: str) -> str:
    if kind == "answer":
        return "Answer-first bullet block placed near the top."
    if kind == "howto":
        return "Numbered step-by-step UI/process block."
    if kind == "visual":
        return "Comparison table or gallery module with short captions."
    if kind == "conversion":
        return "CTA block linking to the next tool, guide, product, or consultation step."
    if "tool" in page_type.lower():
        return "Annotated tool UI screenshot with consent/privacy note."
    return "Simple diagram/table if it makes the decision easier."


def build_outline(package: pathlib.Path, selector: str | None, *, expert_author: bool = False) -> dict[str, Any]:
    architecture = read_json(package / "semantic-architecture-final.json")
    content_rows = read_csv(package / "content-plan.csv")
    entity_source = read_yaml(package / "entity-map.yaml") or architecture
    entities = load_entities(entity_source)
    cluster, content = match_cluster(architecture, content_rows, selector)

    page_type = content.get("page_type") or cluster.get("page_type") or "Guide"
    primary = content.get("primary_keyword") or cluster.get("primary_keyword") or ""
    cluster_id = cluster.get("id") or content.get("source_cluster") or slugify(primary)
    keywords = split_keywords(cluster)
    page_entities = select_entities(entities, str(cluster_id), primary)
    entity_names = [str(entity.get("name")) for entity in page_entities if entity.get("name")]
    internal_links = cluster.get("internal_links") or content.get("internal_links") or []
    if isinstance(internal_links, str):
        internal_links = [part.strip() for part in re.split(r"[|,]", internal_links) if part.strip()]

    sections = []
    for idx, template in enumerate(template_sections(page_type), start=1):
        section_keywords = [keywords[0]] + keywords[idx : idx + 3] if keywords else []
        section_entities = entity_names[:4] if template["kind"] in {"answer", "definition"} else entity_names[:6]
        no_fabrication = (
            "First-person expert claims are allowed only if the project has a real named expert/author."
            if expert_author
            else "Use neutral/third-person expert framing. Do not invent first-person client stories, testing claims, credentials, or quotes."
        )
        sections.append(
            {
                "order": idx,
                "level": template["level"],
                "title": template["title"],
                "word_count_min": template["min"],
                "word_count_max": template["max"],
                "entities_to_cover": section_entities,
                "keywords": section_keywords,
                "summary": f"Cover `{template['kind']}` intent for `{primary}` while preserving page type `{page_type}` selected by research/SERP context.",
                "visual_elements": section_visual(template["kind"], page_type),
                "copywriter_notes": [
                    no_fabrication,
                    "Lead with the user task and answer the intent before expanding into supporting explanation.",
                    "Use source-backed wording for facts, numbers, brand claims, technical limits, medical/safety/privacy claims, and product comparisons.",
                    "Keep sibling-cluster topics as internal links, not long detours that create cannibalization.",
                ],
                "answer_unit": {
                    "formula": "thesis -> context -> proof -> next step",
                    "required": template["kind"] in {"answer", "definition", "trust", "faq"},
                },
                "entity_connections": [
                    f"{section_entities[0]} -> supports_intent -> {primary}" if section_entities else f"{primary} -> maps_to -> {page_type}",
                    f"{primary} -> belongs_to_cluster -> {cluster_id}",
                ],
                "evidence_required": [
                    "SERP/page-type validation",
                    "Source URL or dataset row for factual claims",
                    "Expert/author proof if using first-person professional experience",
                ],
            }
        )

    total_min = sum(section["word_count_min"] for section in sections)
    total_max = sum(section["word_count_max"] for section in sections)
    schema = schema_for_page(page_type)
    seo_meta = seo_meta_for_page({**cluster, **content}, primary, page_type)
    return {
        "outline_id": "page_outline_v2",
        "generated_at": utc_now(),
        "package_dir": str(package),
        "page": {
            "title": content.get("page_title") or cluster.get("name") or primary,
            "url": content.get("url") or cluster.get("suggested_url") or cluster.get("url"),
            "cluster_id": cluster_id,
            "primary_keyword": primary,
            "secondary_keywords": keywords[1:],
            "intent": content.get("intent") or cluster.get("intent"),
            "funnel_stage": content.get("funnel_stage") or cluster.get("funnel_stage"),
            "page_type": page_type,
            "content_format": content.get("content_format") or cluster.get("content_format"),
            "priority": content.get("priority") or cluster.get("priority"),
            "mvp": str(content.get("mvp") or cluster.get("mvp")).lower() in {"true", "1", "yes"},
        },
        "computed_word_count": {"min": total_min, "max": total_max},
        "seo_meta": seo_meta,
        "entities": page_entities,
        "schema": schema,
        "internal_links": internal_links,
        "geo_requirements": [
            "Add a concise answer-first block near the top.",
            "Create FAQ answers in 40-60 words when applicable.",
            "Attach source-backed proof blocks to claims likely to be quoted by AI systems.",
            "Generate synthetic AI prompts for the cluster and test branded/non-branded answers.",
        ],
        "eeat_guard": {
            "expert_author_mode": "real_expert_allowed" if expert_author else "no_fabricated_first_person",
            "rule": "Do not fabricate professional experience, client anecdotes, tests, credentials, or quote-style statements.",
        },
        "sections": sections,
    }


def build_outlines(
    package: pathlib.Path,
    selector: str | None = None,
    *,
    all_mvp: bool = False,
    priorities: list[str] | None = None,
    expert_author: bool = False,
) -> list[dict[str, Any]]:
    architecture = read_json(package / "semantic-architecture-final.json")
    selectors = selected_cluster_selectors(architecture, selector=selector, all_mvp=all_mvp, priorities=priorities)
    seen: set[str] = set()
    outlines = []
    for item in selectors:
        key = normalize(item)
        if key in seen:
            continue
        seen.add(key)
        outlines.append(build_outline(package, item, expert_author=expert_author))
    return outlines


def render_markdown(outline: dict[str, Any]) -> str:
    page = outline["page"]
    lines = [
        f"# Page Outline v2: {page['title']}",
        "",
        f"- Generated: {outline['generated_at']}",
        f"- URL: `{page.get('url')}`",
        f"- Primary keyword: `{page.get('primary_keyword')}`",
        f"- Intent: `{page.get('intent')}`",
        f"- Page type: `{page.get('page_type')}`",
        f"- Computed word count: `{outline['computed_word_count']['min']}-{outline['computed_word_count']['max']}`",
        f"- E-E-A-T mode: `{outline['eeat_guard']['expert_author_mode']}`",
        "",
        "## SEO Meta",
        "",
        f"- Title tag: `{outline.get('seo_meta', {}).get('title_tag')}`",
        f"- Meta description: `{outline.get('seo_meta', {}).get('meta_description')}`",
        f"- Slug: `{outline.get('seo_meta', {}).get('slug')}`",
        f"- Canonical: `{outline.get('seo_meta', {}).get('canonical')}`",
        f"- Alt text guidance: {outline.get('seo_meta', {}).get('alt_text_guidance')}",
        "",
        "## Schema",
        "",
        ", ".join(f"`{item}`" for item in outline["schema"]),
        "",
        "## Internal Links",
        "",
    ]
    if outline["internal_links"]:
        lines.extend(f"- `{link}`" for link in outline["internal_links"])
    else:
        lines.append("- No internal links supplied by the research package.")
    lines.extend(["", "## GEO Requirements", ""])
    lines.extend(f"- {item}" for item in outline["geo_requirements"])
    lines.extend(["", "## Sections", ""])
    for section in outline["sections"]:
        hashes = "#" * section["level"]
        lines.extend(
            [
                f"{hashes} {section['title']}",
                "",
                f"- Word Count: `{section['word_count_min']}-{section['word_count_max']}`",
                f"- Entities: {', '.join(f'`{item}`' for item in section['entities_to_cover']) or 'none supplied'}",
                f"- Keywords: {', '.join(f'`{item}`' for item in section['keywords']) or 'none supplied'}",
                f"- Summary: {section['summary']}",
                f"- Visual Elements: {section['visual_elements']}",
                "- Copywriter Notes:",
            ]
        )
        lines.extend(f"  - {note}" for note in section["copywriter_notes"])
        lines.extend(
            [
                f"- Answer Unit: `{section['answer_unit']['formula']}`; required: `{section['answer_unit']['required']}`",
                "- Entity Connections:",
            ]
        )
        lines.extend(f"  - {connection}" for connection in section["entity_connections"])
        lines.extend(["- Evidence Required:"])
        lines.extend(f"  - {item}" for item in section["evidence_required"])
        lines.append("")
    return "\n".join(lines)


def render_batch_markdown(outlines: list[dict[str, Any]]) -> str:
    blocks = []
    for outline in outlines:
        blocks.append(render_markdown(outline))
    return "\n\n---\n\n".join(blocks)


def write_outline(package: pathlib.Path, outline: dict[str, Any], output_dir: pathlib.Path | None = None) -> dict[str, str]:
    out = output_dir or package / "page-outlines-v2"
    page = outline["page"]
    slug = slugify(page.get("url") or page.get("primary_keyword"))
    paths = {
        "markdown": out / f"{slug}.md",
        "json": out / f"{slug}.json",
    }
    write_text(paths["markdown"], render_markdown(outline))
    write_text(paths["json"], json.dumps(outline, ensure_ascii=False, indent=2) + "\n")
    return {key: str(path) for key, path in paths.items()}


def batch_payload(outlines: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "outline_id": "page_outline_v2_batch",
        "generated_at": utc_now(),
        "count": len(outlines),
        "outlines": outlines,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate section-level page outline v2 from an SEO research package.")
    parser.add_argument("package", help="Research package directory, or a file inside it.")
    parser.add_argument("--page", help="URL, cluster id, page title, or primary keyword to outline. Defaults to first MVP cluster.")
    parser.add_argument("--all-mvp", action="store_true", help="Generate outlines for every MVP cluster.")
    parser.add_argument("--priority", action="append", default=[], help="Generate outlines for clusters with this priority, e.g. P1. Can be repeated.")
    parser.add_argument("--expert-author", action="store_true", help="Allow first-person expert framing because a real expert author exists.")
    parser.add_argument("--write", action="store_true", help="Write markdown/json output.")
    parser.add_argument("--output-dir", help="Output directory. Defaults to <package>/page-outlines-v2.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args(argv)

    package = package_dir(args.package)
    batch_mode = bool(args.all_mvp or args.priority)
    outlines = build_outlines(
        package,
        args.page,
        all_mvp=args.all_mvp,
        priorities=args.priority,
        expert_author=args.expert_author,
    )
    if args.write:
        output_dir = pathlib.Path(args.output_dir).expanduser().resolve() if args.output_dir else None
        for outline in outlines:
            outline["paths"] = write_outline(package, outline, output_dir)
    payload: dict[str, Any] = batch_payload(outlines) if batch_mode else outlines[0]
    if args.format == "markdown":
        print(render_batch_markdown(outlines) if batch_mode else render_markdown(outlines[0]))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
