#!/usr/bin/env python3
"""Generate deep copywriter-ready page outline v3 from a research package.

v3 keeps the evidence-backed v2 outline contract and adds the competitor-style
copywriter layer: tool-first ordering, section-level handoff fields, visual
inventory, copywriter-ready markdown, and reusable entity triplet records.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
from typing import Any

from seo_cycle_core.config import write_text


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent


def load_v2_module():
    spec = importlib.util.spec_from_file_location("page_outline_v2_base", SCRIPT_DIR / "page-outline-v2.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load page-outline-v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V2 = load_v2_module()


def is_tool_like(page_type: Any) -> bool:
    return str(page_type or "").strip().lower() in {"tool", "app", "tool/app", "quiz", "analyzer", "webapplication"}


def word_count_range(item: dict[str, Any]) -> dict[str, int]:
    return {"min": int(item.get("word_count_min") or 0), "max": int(item.get("word_count_max") or 0)}


def ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def section_source_slots(section: dict[str, Any]) -> list[dict[str, str]]:
    details = section.get("copywriting_details") if isinstance(section.get("copywriting_details"), dict) else {}
    slots = details.get("source_slots") if isinstance(details.get("source_slots"), list) else []
    if slots:
        return slots
    return [
        {"claim_type": "SERP intent", "proof": "Use SERP validation or page-type decision from the research package."},
        {"claim_type": "User-facing claim", "proof": "Use source URL, dataset row, screenshot, product docs, or named expert proof."},
    ]


def section_acceptance(section: dict[str, Any]) -> list[str]:
    details = section.get("copywriting_details") if isinstance(section.get("copywriting_details"), dict) else {}
    criteria = details.get("acceptance_criteria") if isinstance(details.get("acceptance_criteria"), list) else []
    if criteria:
        return criteria
    return [
        "Section answers the reader task before adding background.",
        "All factual claims have an attached source/proof slot.",
        "No sibling cluster is expanded beyond planned internal-link routing.",
    ]


def enhance_subsection(
    subsection: dict[str, Any],
    *,
    parent: dict[str, Any],
    index: int,
    page_type: str,
) -> dict[str, Any]:
    title = str(subsection.get("title") or f"Subsection {index}")
    source_slots = [
        {"claim_type": "Subsection proof", "proof": str(subsection.get("proof_needed") or "Use a source slot from the parent section.")},
        {"claim_type": "Entity coverage", "proof": "Tie the subsection back to its planned entities and keywords."},
    ]
    entities = ensure_list(subsection.get("entities_to_cover")) or ensure_list(parent.get("entities_to_cover"))
    keywords = ensure_list(subsection.get("keywords")) or ensure_list(parent.get("keywords"))
    return {
        **subsection,
        "word_count": word_count_range(subsection),
        "summary": subsection.get("writing_task") or f"Explain `{title}` in the context of a `{page_type}` page.",
        "visual_elements": subsection.get("visual_elements")
        or parent.get("visual_elements")
        or "Use a concise table, screenshot, checklist, or callout only if it clarifies the reader decision.",
        "copywriter_notes": subsection.get("copywriter_notes")
        or [
            "Write answer-first and stay inside the parent section scope.",
            "Use neutral expert phrasing unless real expert author mode is approved.",
        ],
        "entity_connections": subsection.get("entity_connections")
        or [
            f"{entities[0]} -> supports_subtopic -> {title}" if entities else f"{title} -> supports_page_type -> {page_type}",
        ],
        "answer_unit": subsection.get("answer_unit")
        or {"required": bool(subsection.get("answer_first")), "formula": "direct answer -> context -> proof -> next step"},
        "source_slots": subsection.get("source_slots") or source_slots,
        "acceptance_criteria": subsection.get("acceptance_criteria")
        or [
            "Contains a direct answer or concrete instruction.",
            "Uses planned entities and keywords naturally.",
            "Does not introduce unsupported first-person expertise.",
        ],
        "entities_to_cover": entities,
        "keywords": keywords,
    }


def enhance_section(section: dict[str, Any], *, index: int, page_type: str, tool_like: bool) -> dict[str, Any]:
    role = section.get("section_role")
    if tool_like and index == 0:
        role = "tool_ux_above_the_fold"
    elif index == 1:
        role = "short_aeo_guide"
    else:
        role = role or "supporting_longform"
    enhanced = {
        **section,
        "section_role": role,
        "word_count": word_count_range(section),
        "source_slots": section.get("source_slots") or section_source_slots(section),
        "acceptance_criteria": section.get("acceptance_criteria") or section_acceptance(section),
    }
    enhanced["h3_subsections"] = [
        enhance_subsection(item, parent=enhanced, index=sub_idx, page_type=page_type)
        for sub_idx, item in enumerate(ensure_list(section.get("h3_subsections")), start=1)
        if isinstance(item, dict)
    ]
    return enhanced


def visual_inventory(outline: dict[str, Any]) -> list[dict[str, str]]:
    page = outline.get("page", {})
    page_type = str(page.get("page_type") or "Guide")
    primary = str(page.get("primary_keyword") or page.get("title") or "page")
    visuals: list[dict[str, str]] = []
    if is_tool_like(page_type):
        visuals.extend(
            [
                {
                    "id": "tool-ui-preview",
                    "type": "screenshot annotation",
                    "placement": "above the fold tool area",
                    "purpose": "Show the user what the interactive tool or honest mock flow does before longform copy.",
                    "source_requirement": "Use implemented UI screenshot, wireframe, or clearly labeled mock preview.",
                    "alt_text_guidance": f"Describe the actual `{primary}` tool state and visible controls.",
                    "dedupe_key": V2.slugify(f"{primary}-tool-ui-preview"),
                },
                {
                    "id": "privacy-trust-note",
                    "type": "callout",
                    "placement": "near upload/preview controls",
                    "purpose": "Explain consent, image handling, account requirement, and mock/real processing limits.",
                    "source_requirement": "Use project privacy policy and implementation behavior; do not invent storage claims.",
                    "alt_text_guidance": "No image alt needed unless rendered as a graphic; keep visible text concise.",
                    "dedupe_key": V2.slugify(f"{primary}-privacy-trust-note"),
                },
            ]
        )
    for item in outline.get("visual_plan", []):
        if not isinstance(item, dict):
            continue
        visuals.append(
            {
                "id": str(item.get("id") or f"visual-{len(visuals) + 1}"),
                "type": str(item.get("type") or "callout"),
                "placement": str(item.get("placement") or "section body"),
                "purpose": str(item.get("label") or "Clarify the reader decision."),
                "source_requirement": str(item.get("source_requirement") or "Use verified source, screenshot, or project asset."),
                "alt_text_guidance": str(item.get("alt_text_guidance") or "Describe the actual visual content."),
                "dedupe_key": str(item.get("dedupe_key") or V2.slugify(f"{primary}-visual-{len(visuals) + 1}")),
            }
        )
    required_types = [
        ("comparison-table", "comparison table"),
        ("decision-checklist", "checklist"),
        ("framework-infographic", "infographic"),
        ("proof-callout", "callout"),
        ("before-after-block", "before/after block"),
        ("result-card", "quiz/result card"),
    ]
    existing_types = {item["type"] for item in visuals}
    for visual_id, visual_type in required_types:
        if len(visuals) >= 6 and visual_type in existing_types:
            continue
        if visual_type in existing_types and len(visuals) >= 6:
            continue
        visuals.append(
            {
                "id": visual_id,
                "type": visual_type,
                "placement": "most relevant section",
                "purpose": f"Give the copywriter a concrete `{visual_type}` option instead of generic image guidance.",
                "source_requirement": "Use project screenshots, verified examples, or explicit generated placeholder labels.",
                "alt_text_guidance": "Describe what the reader can inspect or decide from the visual.",
                "dedupe_key": V2.slugify(f"{primary}-{visual_id}"),
            }
        )
        existing_types.add(visual_type)
        if len(visuals) >= 8:
            break
    return visuals


def serp_safe_layout(page_type: str) -> dict[str, Any]:
    if is_tool_like(page_type):
        return {
            "mode": "tool_first",
            "order": ["tool_ux_above_the_fold", "short_aeo_guide", "supporting_longform"],
            "rule": "Interactive or honest mock tool UX must appear before longform SEO copy.",
        }
    return {
        "mode": "answer_first",
        "order": ["answer_first_summary", "evidence_backed_sections", "next_action"],
        "rule": "Answer the page intent before broad background or tangential sections.",
    }


def triplets_for_outline(outline: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = outline.get("page", {})
    for section in outline.get("sections", []):
        if not isinstance(section, dict):
            continue
        for raw in section.get("entity_connections", []):
            parts = [part.strip() for part in str(raw).split("->")]
            rows.append(
                {
                    "provider": "page_outline_v3",
                    "page_url": page.get("url"),
                    "page_primary_keyword": page.get("primary_keyword"),
                    "section": section.get("title"),
                    "raw": str(raw),
                    "subject": parts[0] if len(parts) >= 3 else "",
                    "predicate": parts[1] if len(parts) >= 3 else "",
                    "object": parts[2] if len(parts) >= 3 else "",
                }
            )
        for subsection in section.get("h3_subsections", []):
            if not isinstance(subsection, dict):
                continue
            for raw in subsection.get("entity_connections", []):
                parts = [part.strip() for part in str(raw).split("->")]
                rows.append(
                    {
                        "provider": "page_outline_v3",
                        "page_url": page.get("url"),
                        "page_primary_keyword": page.get("primary_keyword"),
                        "section": section.get("title"),
                        "subsection": subsection.get("title"),
                        "raw": str(raw),
                        "subject": parts[0] if len(parts) >= 3 else "",
                        "predicate": parts[1] if len(parts) >= 3 else "",
                        "object": parts[2] if len(parts) >= 3 else "",
                    }
                )
    return rows


def upgrade_outline(base: dict[str, Any], *, expert_author: bool = False) -> dict[str, Any]:
    page = base.get("page", {})
    page_type = str(page.get("page_type") or "Guide")
    tool_like = is_tool_like(page_type)
    sections = [
        enhance_section(section, index=idx, page_type=page_type, tool_like=tool_like)
        for idx, section in enumerate(base.get("sections", []))
        if isinstance(section, dict)
    ]
    outline = {
        **base,
        "outline_id": "page_outline_v3",
        "version": "v3",
        "serp_safe_layout": serp_safe_layout(page_type),
        "sections": sections,
        "visual_inventory": [],
        "copywriter_ready_contract": {
            "audience": "copywriter",
            "raw_files_required": False,
            "must_preserve": ["URL", "page_type", "primary_keyword", "SERP-safe layout", "E-E-A-T guard"],
        },
    }
    outline["visual_inventory"] = visual_inventory(outline)
    outline["entity_triplets"] = triplets_for_outline(outline)
    outline["eeat_guard"] = {
        **(outline.get("eeat_guard") if isinstance(outline.get("eeat_guard"), dict) else {}),
        "expert_author_mode": "real_expert_allowed" if expert_author else "no_fabricated_first_person",
        "v3_rule": "First-person professional voice requires real named author/expert evidence in the project.",
    }
    return outline


def source_lock_addendum(package: pathlib.Path, outline: dict[str, Any]) -> dict[str, Any] | None:
    architecture_path = package / "semantic-architecture-final.json"
    if not architecture_path.exists():
        return None
    try:
        architecture = json.loads(architecture_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    cluster_id = outline.get("page", {}).get("cluster_id")
    for cluster in architecture.get("clusters", []):
        if not isinstance(cluster, dict) or cluster.get("id") != cluster_id:
            continue
        source_lock = cluster.get("source_lock")
        if not isinstance(source_lock, dict):
            return None
        return {
            "status": source_lock.get("status", "unknown"),
            "report": source_lock.get("report"),
            "product_distillate": source_lock.get("product_distillate"),
            "allowed_technical_claims": ensure_list(source_lock.get("allowed_technical_claims")),
            "blocked_claims": ensure_list(source_lock.get("blocked_claims")),
            "draft_rule": (
                "Use only source-locked technical/product claims for this page. "
                "If the source-lock report conflicts with generic outline text, the source-lock report wins."
            ),
        }
    return None


def attach_source_lock(package: pathlib.Path, outline: dict[str, Any]) -> dict[str, Any]:
    addendum = source_lock_addendum(package, outline)
    if not addendum:
        return outline
    updated = {**outline, "source_lock_addendum": addendum}
    writer_handoff = dict(updated.get("writer_handoff") or {})
    must_do = list(writer_handoff.get("must_do") or [])
    source_lock_rule = "Apply the source-lock addendum before drafting numbers, product availability, brand claims, and technical recommendations."
    if source_lock_rule not in must_do:
        must_do.append(source_lock_rule)
    must_not = list(writer_handoff.get("must_not") or [])
    blocked_rule = "Do not use claims listed under source_lock_addendum.blocked_claims unless a newer approved source-lock report replaces them."
    if blocked_rule not in must_not:
        must_not.append(blocked_rule)
    fact_check_queue = list(writer_handoff.get("fact_check_queue") or [])
    report = addendum.get("report")
    if report and report not in fact_check_queue:
        fact_check_queue.insert(0, report)
    writer_handoff.update({"must_do": must_do, "must_not": must_not, "fact_check_queue": fact_check_queue})
    updated["writer_handoff"] = writer_handoff
    return updated


def build_outline(package: pathlib.Path, selector: str | None, *, expert_author: bool = False) -> dict[str, Any]:
    outline = upgrade_outline(V2.build_outline(package, selector, expert_author=expert_author), expert_author=expert_author)
    return attach_source_lock(package, outline)


def build_outlines(
    package: pathlib.Path,
    selector: str | None = None,
    *,
    all_mvp: bool = False,
    priorities: list[str] | None = None,
    expert_author: bool = False,
) -> list[dict[str, Any]]:
    bases = V2.build_outlines(package, selector, all_mvp=all_mvp, priorities=priorities, expert_author=expert_author)
    return [attach_source_lock(package, upgrade_outline(base, expert_author=expert_author)) for base in bases]


def render_markdown(outline: dict[str, Any]) -> str:
    base = V2.render_markdown(outline).replace("# Page Outline v2:", "# Page Outline v3:", 1)
    lines = [
        base,
        "",
        "## v3 SERP-Safe Layout",
        "",
        f"- Mode: `{outline['serp_safe_layout']['mode']}`",
        f"- Order: {', '.join(f'`{item}`' for item in outline['serp_safe_layout']['order'])}",
        f"- Rule: {outline['serp_safe_layout']['rule']}",
        "",
        "## v3 Visual Inventory",
        "",
    ]
    for visual in outline.get("visual_inventory", []):
        lines.append(
            f"- `{visual['id']}` ({visual['type']}): {visual['purpose']} "
            f"Placement: `{visual['placement']}`. Source: {visual['source_requirement']}"
        )
    addendum = outline.get("source_lock_addendum") if isinstance(outline.get("source_lock_addendum"), dict) else None
    if addendum:
        lines.extend(["", "## v3 Source-Lock Addendum", ""])
        lines.append(f"- Status: `{addendum.get('status')}`")
        if addendum.get("report"):
            lines.append(f"- Report: `{addendum.get('report')}`")
        if addendum.get("product_distillate"):
            lines.append(f"- Product distillate: `{addendum.get('product_distillate')}`")
        lines.extend(["", "### Allowed Technical/Product Claims"])
        lines.extend(f"- {item}" for item in addendum.get("allowed_technical_claims", []))
        lines.extend(["", "### Blocked Claims"])
        lines.extend(f"- {item}" for item in addendum.get("blocked_claims", []))
        lines.extend(["", f"Rule: {addendum.get('draft_rule')}"])
    return "\n".join(lines) + "\n"


def render_copywriter_ready(outline: dict[str, Any]) -> str:
    page = outline.get("page", {})
    lines = [
        f"# Copywriter Ready Brief: {page.get('title')}",
        "",
        f"- URL: `{page.get('url')}`",
        f"- Primary keyword: `{page.get('primary_keyword')}`",
        f"- Page type: `{page.get('page_type')}`",
        f"- Intent: `{page.get('intent')}`",
        f"- SERP-safe order: {', '.join(f'`{item}`' for item in outline.get('serp_safe_layout', {}).get('order', []))}",
        f"- E-E-A-T mode: `{outline.get('eeat_guard', {}).get('expert_author_mode')}`",
        "",
        "## Tone Rules",
        "",
    ]
    for item in outline.get("writer_handoff", {}).get("must_do", []):
        lines.append(f"- Do: {item}")
    for item in outline.get("writer_handoff", {}).get("must_not", []):
        lines.append(f"- Do not: {item}")
    lines.extend(["", "## H1/H2/H3 Outline", ""])
    lines.append(f"# {page.get('title')}")
    for section in outline.get("sections", []):
        lines.extend(
            [
                "",
                f"## {section.get('title')}",
                f"- Role: `{section.get('section_role')}`",
                f"- Word count: `{section.get('word_count', {}).get('min')}-{section.get('word_count', {}).get('max')}`",
                f"- Entities: {', '.join(f'`{item}`' for item in section.get('entities_to_cover', []))}",
                f"- Keywords: {', '.join(f'`{item}`' for item in section.get('keywords', []))}",
                f"- Summary: {section.get('summary')}",
                f"- Visual: {section.get('visual_elements')}",
                "- Copywriter notes:",
            ]
        )
        lines.extend(f"  - {note}" for note in section.get("copywriter_notes", []))
        lines.append("- Source slots:")
        for slot in section.get("source_slots", []):
            lines.append(f"  - {slot.get('claim_type')}: {slot.get('proof')}")
        lines.append("- Acceptance criteria:")
        lines.extend(f"  - {item}" for item in section.get("acceptance_criteria", []))
        for subsection in section.get("h3_subsections", []):
            lines.extend(
                [
                    "",
                    f"### {subsection.get('title')}",
                    f"- Word count: `{subsection.get('word_count', {}).get('min')}-{subsection.get('word_count', {}).get('max')}`",
                    f"- Summary: {subsection.get('summary')}",
                    f"- Entities: {', '.join(f'`{item}`' for item in subsection.get('entities_to_cover', []))}",
                    f"- Keywords: {', '.join(f'`{item}`' for item in subsection.get('keywords', []))}",
                    f"- Visual: {subsection.get('visual_elements')}",
                    f"- Answer unit: {subsection.get('answer_unit', {}).get('formula')}",
                ]
            )
    lines.extend(["", "## FAQ Answer Guidelines", ""])
    for item in outline.get("faq", []):
        lines.extend([f"### {item.get('question')}", item.get("answer_guidance", ""), ""])
    lines.extend(["## Visual/Table/Callout Inventory", ""])
    for visual in outline.get("visual_inventory", []):
        lines.append(f"- `{visual['type']}` in `{visual['placement']}`: {visual['purpose']}")
    lines.extend(["", "## Fact-Check Queue", ""])
    lines.extend(f"- {item}" for item in outline.get("writer_handoff", {}).get("fact_check_queue", []))
    addendum = outline.get("source_lock_addendum") if isinstance(outline.get("source_lock_addendum"), dict) else None
    if addendum:
        lines.extend(["", "## Source-Lock Addendum", ""])
        lines.append(f"- Status: `{addendum.get('status')}`")
        if addendum.get("report"):
            lines.append(f"- Report: `{addendum.get('report')}`")
        if addendum.get("product_distillate"):
            lines.append(f"- Product distillate: `{addendum.get('product_distillate')}`")
        lines.extend(["", "### Allowed Technical/Product Claims"])
        lines.extend(f"- {item}" for item in addendum.get("allowed_technical_claims", []))
        lines.extend(["", "### Blocked Claims"])
        lines.extend(f"- {item}" for item in addendum.get("blocked_claims", []))
        lines.extend(["", f"Rule: {addendum.get('draft_rule')}"])
    lines.extend(["", "## Banned Claims", ""])
    lines.extend(f"- {item}" for item in outline.get("writer_prompt_packet", {}).get("forbidden_actions", []))
    return "\n".join(lines) + "\n"


def write_triplets(package: pathlib.Path, outline: dict[str, Any]) -> str:
    path = package / "vector" / "page_outline_triplets.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    page_url = outline.get("page", {}).get("url")
    kept = []
    for line in existing:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if payload.get("provider") == "page_outline_v3" and payload.get("page_url") == page_url:
            continue
        kept.append(line)
    rows = kept + [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in outline.get("entity_triplets", [])]
    write_text(path, "\n".join(rows) + ("\n" if rows else ""))
    return str(path)


def write_outline(package: pathlib.Path, outline: dict[str, Any], output_dir: pathlib.Path | None = None) -> dict[str, str]:
    out = output_dir or package / "page-outlines-v3"
    copy_out = package / "copywriter-ready"
    page = outline["page"]
    slug = V2.slugify(page.get("url") or page.get("primary_keyword"))
    paths = {
        "markdown": out / f"{slug}.md",
        "json": out / f"{slug}.json",
        "copywriter_ready": copy_out / f"{slug}.md",
        "triplets_jsonl": pathlib.Path(write_triplets(package, outline)),
    }
    string_paths = {key: str(path) for key, path in paths.items()}
    outline_with_paths = {**outline, "paths": string_paths}
    write_text(paths["markdown"], render_markdown(outline_with_paths))
    write_text(paths["json"], json.dumps(outline_with_paths, ensure_ascii=False, indent=2) + "\n")
    write_text(paths["copywriter_ready"], render_copywriter_ready(outline_with_paths))
    return string_paths


def batch_payload(outlines: list[dict[str, Any]]) -> dict[str, Any]:
    return {"outline_id": "page_outline_v3_batch", "version": "v3", "generated_at": V2.utc_now(), "count": len(outlines), "outlines": outlines}


def attach_rag_passages(package: pathlib.Path, outlines: list[dict[str, Any]]) -> None:
    """Best-effort: enrich outlines with related passages from the local RAG index."""
    try:
        from seo_cycle_core.config import find_config, load_yaml, package_project_root
        from seo_cycle_core.rag import open_db, rag_db_path, search
    except ImportError:
        return
    project_root = package_project_root(package)
    cfg_path = find_config(project_root)
    cfg = load_yaml(cfg_path) if cfg_path else {}
    db_path = rag_db_path(project_root, cfg)
    if not db_path.exists():
        return
    conn = open_db(db_path)
    for outline in outlines:
        keyword = str((outline.get("page") or {}).get("primary_keyword") or "").strip()
        if not keyword:
            continue
        hits = search(conn, keyword, top_k=3, source_types=["source_pack", "distillate", "triplet"])
        outline["related_passages"] = [
            {"source_type": hit["source_type"], "path": hit["path"], "score": hit["score"],
             "text": hit["text"][:500], "meta": hit.get("meta", {})}
            for hit in hits
        ]
    conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deep copywriter-ready page outline v3 from an SEO research package.")
    parser.add_argument("package", help="Research package directory, or a file inside it.")
    parser.add_argument("--page", help="URL, cluster id, page title, or primary keyword to outline. Defaults to first MVP cluster.")
    parser.add_argument("--all-mvp", action="store_true", help="Generate outlines for every MVP cluster.")
    parser.add_argument("--priority", action="append", default=[], help="Generate outlines for clusters with this priority, e.g. P1. Can be repeated.")
    parser.add_argument("--expert-author", action="store_true", help="Allow first-person expert framing because a real expert author exists.")
    parser.add_argument("--write", action="store_true", help="Write markdown/json/copywriter-ready output.")
    parser.add_argument("--output-dir", help="Output directory. Defaults to <package>/page-outlines-v3.")
    parser.add_argument("--rag", action="store_true",
                        help="Attach top related passages from the local RAG index (no-op without seo/rag.db).")
    parser.add_argument("--format", choices=["json", "markdown", "copywriter"], default="json")
    args = parser.parse_args(argv)

    package = V2.package_dir(args.package)
    batch_mode = bool(args.all_mvp or args.priority)
    outlines = build_outlines(
        package,
        args.page,
        all_mvp=args.all_mvp,
        priorities=args.priority,
        expert_author=args.expert_author,
    )
    if args.rag:
        attach_rag_passages(package, outlines)
    if args.write:
        output_dir = pathlib.Path(args.output_dir).expanduser().resolve() if args.output_dir else None
        for outline in outlines:
            outline["paths"] = write_outline(package, outline, output_dir)
    payload: dict[str, Any] = batch_payload(outlines) if batch_mode else outlines[0]
    if args.format == "markdown":
        print("\n\n---\n\n".join(render_markdown(outline) for outline in outlines))
    elif args.format == "copywriter":
        print("\n\n---\n\n".join(render_copywriter_ready(outline) for outline in outlines))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
