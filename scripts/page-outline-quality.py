#!/usr/bin/env python3
"""Quality gate for section-level SEO/AEO/GEO page outlines.

This catches the page-brief failure modes from the comparison audit: word-count
math drift, page-type/SERP context loss, fabricated first-person expertise,
missing SEO meta/schema/internal links, weak Answer Units/GEO, orphan entities,
and shallow copywriter handoff.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
from typing import Any

from seo_cycle_core.reports import write_report_bundle


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
SEVERITY_PENALTY = {"critical": 4, "high": 3, "medium": 2, "low": 1}
FIRST_PERSON_RISK_RE = re.compile(
    r"\b(in my years|my clients|my client|i recommend|i use|i have seen|"
    r"from what i've observed|testing dozens|working with .* clients)\b",
    re.IGNORECASE,
)

QUALITY_CRITERIA = (
    {"id": "word_count_integrity", "label": "Word-count integrity"},
    {"id": "serp_intent_lock", "label": "SERP/page-type and intent lock"},
    {"id": "entity_coverage", "label": "Entity coverage and graph usefulness"},
    {"id": "copywriter_actionability", "label": "Copywriter actionability"},
    {"id": "eeat_no_fabrication", "label": "E-E-A-T no-fabrication safety"},
    {"id": "geo_answer_units", "label": "GEO/AEO Answer Units"},
    {"id": "technical_seo_wrap", "label": "Technical SEO wrapper"},
    {"id": "internal_links_cannibalization", "label": "Internal links and cannibalization guard"},
    {"id": "visual_ux_guidance", "label": "Visual/UX guidance"},
    {"id": "handoff_machine_readability", "label": "Machine-readable handoff"},
)

V3_QUALITY_CRITERIA = QUALITY_CRITERIA + (
    {"id": "serp_safe_ux", "label": "SERP-safe UX and page ordering"},
    {"id": "entity_triplet_export", "label": "Entity/triplet export readiness"},
)

FINDING_CRITERIA = {
    "no_outline_json": ("handoff_machine_readability",),
    "unstructured_html_outline": ("handoff_machine_readability", "technical_seo_wrap"),
    "missing_required_fields": ("handoff_machine_readability", "copywriter_actionability"),
    "word_count_mismatch": ("word_count_integrity", "copywriter_actionability"),
    "missing_page_context": ("serp_intent_lock", "copywriter_actionability"),
    "missing_intro_conclusion": ("copywriter_actionability", "handoff_machine_readability"),
    "missing_seo_meta": ("technical_seo_wrap",),
    "missing_schema": ("technical_seo_wrap",),
    "missing_internal_links": ("internal_links_cannibalization",),
    "missing_answer_units": ("geo_answer_units", "copywriter_actionability"),
    "missing_key_takeaways": ("geo_answer_units", "copywriter_actionability"),
    "missing_faq_assets": ("geo_answer_units", "technical_seo_wrap"),
    "missing_evidence_requirements": ("eeat_no_fabrication", "copywriter_actionability"),
    "unsafe_first_person_expertise": ("eeat_no_fabrication",),
    "orphan_entities": ("entity_coverage",),
    "missing_entity_connections": ("entity_coverage", "handoff_machine_readability"),
    "missing_section_bridges": ("copywriter_actionability", "handoff_machine_readability"),
    "missing_visual_guidance": ("visual_ux_guidance",),
    "weak_visual_plan": ("visual_ux_guidance", "handoff_machine_readability"),
    "missing_geo_requirements": ("geo_answer_units",),
    "missing_writer_handoff": ("copywriter_actionability", "handoff_machine_readability"),
    "missing_copywriting_playbook": ("copywriter_actionability", "handoff_machine_readability"),
    "missing_revision_checklist": ("copywriter_actionability", "handoff_machine_readability"),
    "missing_writer_prompt_packet": ("copywriter_actionability", "handoff_machine_readability"),
    "missing_h3_subsections": ("copywriter_actionability", "handoff_machine_readability"),
    "subsection_word_count_mismatch": ("word_count_integrity", "copywriter_actionability"),
    "weak_copywriting_details": ("copywriter_actionability",),
    "missing_source_slots": ("eeat_no_fabrication", "copywriter_actionability"),
    "missing_acceptance_criteria": ("copywriter_actionability", "handoff_machine_readability"),
    "missing_fact_check_queue": ("eeat_no_fabrication", "copywriter_actionability"),
    "missing_trust_limitations": ("eeat_no_fabrication", "geo_answer_units"),
    "missing_synthetic_prompts": ("geo_answer_units", "handoff_machine_readability"),
    "tool_first_order_violation": ("serp_safe_ux", "copywriter_actionability"),
    "weak_visual_inventory": ("visual_ux_guidance", "handoff_machine_readability"),
    "missing_copywriter_ready_contract": ("copywriter_actionability", "handoff_machine_readability"),
    "missing_triplet_export": ("entity_triplet_export", "entity_coverage"),
    "missing_section_v3_fields": ("copywriter_actionability", "handoff_machine_readability"),
}

REMEDIATION = {
    "no_outline_json": "Generate outlines with page-outline-v2.py --all-mvp --write or pass a JSON outline file.",
    "unstructured_html_outline": "Regenerate as page-outline-v2 JSON/Markdown; avoid HTML-only briefs that cannot be validated.",
    "missing_required_fields": "Regenerate the outline from the research package so page, sections, schema and guards are present.",
    "word_count_mismatch": "Recompute outline computed_word_count from the section min/max totals.",
    "missing_page_context": "Carry page_type, intent, primary_keyword and URL from final research architecture into the outline.",
    "missing_intro_conclusion": "Add intro_brief and conclusion_brief with word counts, promise/recap, CTA and constraints.",
    "missing_seo_meta": "Add title tag, meta description, slug/canonical and alt text guidance.",
    "missing_schema": "Add schema recommendations such as WebApplication/Article, FAQPage and BreadcrumbList.",
    "missing_internal_links": "Add internal links from final cluster architecture; do not invent unrelated detours.",
    "missing_answer_units": "Add required Answer Units to answer/definition/trust/FAQ sections.",
    "missing_key_takeaways": "Add answer-first key takeaways immediately below the page summary/H1 handoff.",
    "missing_faq_assets": "Add FAQ answer units with concise answer guidance and FAQPage schema readiness.",
    "missing_evidence_requirements": "Add source/proof requirements per section, especially for numbers, claims and expert statements.",
    "unsafe_first_person_expertise": "Remove first-person expert anecdotes or switch to real_expert_allowed only with named proof.",
    "orphan_entities": "Either assign each page entity to sections/connections or remove it from the page entity set.",
    "missing_entity_connections": "Add section-level entity triplets/relations tied to the primary intent.",
    "missing_section_bridges": "Add bridge instructions so sections connect into one funnel instead of isolated blocks.",
    "missing_visual_guidance": "Add concrete visual/table/screenshot guidance per section.",
    "weak_visual_plan": "Add a numbered visual plan with placement, dedupe keys, alt guidance and source requirements.",
    "missing_geo_requirements": "Add answer-first, FAQ, proof block and synthetic AI prompt requirements.",
    "missing_writer_handoff": "Add writer_handoff with reader task, voice, must-do, must-not and safe memorable lines.",
    "missing_copywriting_playbook": "Add a copywriting_playbook with reader state, tone contract, angle stack, draft sequence and revision checklist.",
    "missing_revision_checklist": "Add a concrete revision_checklist before the draft moves to design/schema/publishing.",
    "missing_writer_prompt_packet": "Add a writer_prompt_packet with input/output contracts, forbidden actions and acceptance gate for low-token drafting.",
    "missing_fact_check_queue": "Add a fact_check_queue for SERP, claims, expert proof, schema and technical/privacy checks.",
    "missing_trust_limitations": "Add trust_limitations covering page-type, evidence, technical/privacy and decision limits.",
    "missing_synthetic_prompts": "Add synthetic AI prompts for non-branded, page-type, comparison and trust checks.",
    "missing_h3_subsections": "Add H3 subsection plans under each H2 with writing task, entities, keywords, proof and answer-first flag.",
    "subsection_word_count_mismatch": "Make H3 subsection word counts add up exactly to their parent section word count.",
    "weak_copywriting_details": "Add section copywriting details: reader question, opening angle, do-write, do-not-write, safe phrases and CTA.",
    "missing_source_slots": "Add source_slots that map claim types to required proof.",
    "missing_acceptance_criteria": "Add concrete acceptance criteria for each section before handoff.",
    "tool_first_order_violation": "Regenerate with page-outline-v3.py so tool/app pages start with tool_ux_above_the_fold before longform copy.",
    "weak_visual_inventory": "Add v3 visual_inventory items with type, placement, purpose, source_requirement, alt guidance and dedupe key.",
    "missing_copywriter_ready_contract": "Regenerate with page-outline-v3.py --write so copywriter-ready output can be produced.",
    "missing_triplet_export": "Add v3 entity_triplets and write vector/page_outline_triplets.jsonl during outline generation.",
    "missing_section_v3_fields": "Regenerate v3 outlines so each section and H3 has word_count, source_slots, acceptance criteria and answer units.",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "_", str(value or "").strip().lower(), flags=re.IGNORECASE).strip("_")


def read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def add_finding(
    findings: list[dict[str, Any]],
    *,
    finding_id: str,
    severity: str,
    title: str,
    outline: str,
    evidence: Any,
) -> None:
    findings.append(
        {
            "id": finding_id,
            "severity": severity,
            "title": title,
            "outline": outline,
            "evidence": evidence,
            "recommended_action": REMEDIATION.get(finding_id, "Review and regenerate the page outline."),
        }
    )


def outline_title(outline: dict[str, Any], fallback: str) -> str:
    page = outline.get("page") if isinstance(outline.get("page"), dict) else {}
    return str(page.get("url") or page.get("title") or page.get("primary_keyword") or fallback)


def outlines_from_json(data: dict[str, Any]) -> list[dict[str, Any]]:
    if data.get("outline_id") == "page_outline_v2_batch" and isinstance(data.get("outlines"), list):
        return [item for item in data["outlines"] if isinstance(item, dict)]
    if data.get("outline_id") == "page_outline_v3_batch" and isinstance(data.get("outlines"), list):
        return [item for item in data["outlines"] if isinstance(item, dict)]
    if data.get("outline_id") == "page_outline_v2":
        return [data]
    if data.get("outline_id") == "page_outline_v3":
        return [data]
    return []


def discover_outline_files(raw: str | pathlib.Path, version: str = "auto") -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    path = pathlib.Path(raw).expanduser().resolve()
    if path.is_file():
        if path.suffix.lower() == ".json":
            return [path], []
        return [], [path]
    candidates = []
    md_candidates = []
    if version in {"auto", "v2"} and (path / "page-outlines-v2").exists():
        candidates.extend(sorted((path / "page-outlines-v2").glob("*.json")))
        md_candidates.extend(sorted((path / "page-outlines-v2").glob("*.md")))
    if version in {"auto", "v3"} and (path / "page-outlines-v3").exists():
        candidates.extend(sorted((path / "page-outlines-v3").glob("*.json")))
        md_candidates.extend(sorted((path / "page-outlines-v3").glob("*.md")))
    candidates.extend(sorted(path.glob("*.json")))
    md_candidates.extend(sorted(path.glob("*.md")))
    return list(dict.fromkeys(candidates)), list(dict.fromkeys(md_candidates))


def text_blob(outline: dict[str, Any]) -> str:
    chunks = [
        json.dumps(outline.get("page", {}), ensure_ascii=False),
        json.dumps(outline.get("writer_handoff", {}), ensure_ascii=False),
        json.dumps(outline.get("copywriting_playbook", {}), ensure_ascii=False),
        json.dumps(outline.get("writer_prompt_packet", {}), ensure_ascii=False),
        json.dumps(outline.get("key_takeaways", []), ensure_ascii=False),
        json.dumps(outline.get("faq", []), ensure_ascii=False),
    ]
    for section in outline.get("sections", []):
        if isinstance(section, dict):
            chunks.append(json.dumps(section, ensure_ascii=False))
    return "\n".join(chunks)


def validate_outline(outline: dict[str, Any], fallback: str, version: str = "auto") -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    title = outline_title(outline, fallback)
    page = outline.get("page") if isinstance(outline.get("page"), dict) else {}
    sections = outline.get("sections") if isinstance(outline.get("sections"), list) else []

    if not page or not sections:
        add_finding(
            findings,
            finding_id="missing_required_fields",
            severity="critical",
            title="Outline is missing page metadata or sections.",
            outline=title,
            evidence={"has_page": bool(page), "sections": len(sections)},
        )
        return findings

    computed = outline.get("computed_word_count") if isinstance(outline.get("computed_word_count"), dict) else {}
    section_min = sum(int(section.get("word_count_min") or 0) for section in sections if isinstance(section, dict))
    section_max = sum(int(section.get("word_count_max") or 0) for section in sections if isinstance(section, dict))
    if computed.get("min") != section_min or computed.get("max") != section_max:
        add_finding(
            findings,
            finding_id="word_count_mismatch",
            severity="high",
            title="Computed word count does not equal the sum of section word counts.",
            outline=title,
            evidence={"computed": computed, "section_sum": {"min": section_min, "max": section_max}},
        )

    missing_context = [key for key in ("url", "primary_keyword", "intent", "page_type") if not page.get(key)]
    if missing_context:
        add_finding(
            findings,
            finding_id="missing_page_context",
            severity="high",
            title="Outline lost required page context from the research architecture.",
            outline=title,
            evidence={"missing": missing_context},
        )

    intro = outline.get("intro_brief") if isinstance(outline.get("intro_brief"), dict) else {}
    conclusion = outline.get("conclusion_brief") if isinstance(outline.get("conclusion_brief"), dict) else {}
    missing_intro_conclusion = []
    if not intro.get("word_count_min") or not intro.get("word_count_max") or not intro.get("hook_strategy") or not intro.get("promise"):
        missing_intro_conclusion.append("intro_brief")
    if not conclusion.get("word_count_min") or not conclusion.get("word_count_max") or not conclusion.get("recap_strategy") or not conclusion.get("cta"):
        missing_intro_conclusion.append("conclusion_brief")
    if missing_intro_conclusion:
        add_finding(
            findings,
            finding_id="missing_intro_conclusion",
            severity="high",
            title="Outline lacks copy-ready intro or conclusion briefs.",
            outline=title,
            evidence={"missing": missing_intro_conclusion},
        )

    seo_meta = outline.get("seo_meta") if isinstance(outline.get("seo_meta"), dict) else {}
    missing_meta = [key for key in ("title_tag", "meta_description", "slug", "canonical", "alt_text_guidance") if not seo_meta.get(key)]
    if missing_meta:
        add_finding(
            findings,
            finding_id="missing_seo_meta",
            severity="high",
            title="Outline is missing SEO meta/canonical/alt guidance.",
            outline=title,
            evidence={"missing": missing_meta},
        )

    if not outline.get("schema"):
        add_finding(
            findings,
            finding_id="missing_schema",
            severity="high",
            title="Outline does not include schema recommendations.",
            outline=title,
            evidence={"schema": outline.get("schema")},
        )

    if not outline.get("internal_links"):
        add_finding(
            findings,
            finding_id="missing_internal_links",
            severity="medium",
            title="Outline has no internal links from the architecture.",
            outline=title,
            evidence={"internal_links": outline.get("internal_links")},
        )

    required_answer_units = [
        section.get("title")
        for section in sections
        if isinstance(section, dict) and (section.get("answer_unit") or {}).get("required") and not (section.get("answer_unit") or {}).get("formula")
    ]
    has_required_answer_unit = any(
        (section.get("answer_unit") or {}).get("required")
        for section in sections
        if isinstance(section, dict)
    )
    if required_answer_units or not has_required_answer_unit:
        add_finding(
            findings,
            finding_id="missing_answer_units",
            severity="high",
            title="Outline is missing required Answer Unit coverage.",
            outline=title,
            evidence={
                "sections_missing_formula": required_answer_units,
                "has_required_answer_unit": has_required_answer_unit,
            },
        )

    key_takeaways = outline.get("key_takeaways") if isinstance(outline.get("key_takeaways"), list) else []
    if len(key_takeaways) < 4 or any(not isinstance(item, dict) or not item.get("statement") for item in key_takeaways):
        add_finding(
            findings,
            finding_id="missing_key_takeaways",
            severity="high",
            title="Outline lacks answer-first key takeaways.",
            outline=title,
            evidence={"key_takeaways": len(key_takeaways)},
        )

    faq = outline.get("faq") if isinstance(outline.get("faq"), list) else []
    if len(faq) < 3 or any(not isinstance(item, dict) or not item.get("question") or not item.get("answer_guidance") for item in faq):
        add_finding(
            findings,
            finding_id="missing_faq_assets",
            severity="medium",
            title="Outline lacks FAQ answer-unit assets.",
            outline=title,
            evidence={"faq": len(faq)},
        )

    writer_handoff = outline.get("writer_handoff") if isinstance(outline.get("writer_handoff"), dict) else {}
    missing_handoff = [
        key
        for key in ("reader_task", "voice", "must_do", "must_not", "memorable_lines")
        if not writer_handoff.get(key)
    ]
    if missing_handoff:
        add_finding(
            findings,
            finding_id="missing_writer_handoff",
            severity="high",
            title="Outline lacks a copywriter-ready handoff contract.",
            outline=title,
            evidence={"missing": missing_handoff},
        )

    playbook = outline.get("copywriting_playbook") if isinstance(outline.get("copywriting_playbook"), dict) else {}
    tone_contract = playbook.get("tone_contract") if isinstance(playbook.get("tone_contract"), dict) else {}
    target_reader_state = playbook.get("target_reader_state") if isinstance(playbook.get("target_reader_state"), dict) else {}
    missing_playbook = [
        key
        for key in ("page_job", "angle_stack", "draft_sequence", "revision_checklist")
        if not playbook.get(key)
    ]
    if not target_reader_state.get("before") or not target_reader_state.get("after"):
        missing_playbook.append("target_reader_state")
    if not tone_contract.get("voice") or not tone_contract.get("rhythm") or not tone_contract.get("banned_patterns"):
        missing_playbook.append("tone_contract")
    if missing_playbook:
        add_finding(
            findings,
            finding_id="missing_copywriting_playbook",
            severity="high",
            title="Outline lacks a complete copywriting playbook.",
            outline=title,
            evidence={"missing": sorted(set(missing_playbook))},
        )
    revision_checklist = playbook.get("revision_checklist") if isinstance(playbook.get("revision_checklist"), list) else []
    if len(revision_checklist) < 6:
        add_finding(
            findings,
            finding_id="missing_revision_checklist",
            severity="medium",
            title="Outline lacks a useful final revision checklist for drafting.",
            outline=title,
            evidence={"revision_checklist": len(revision_checklist)},
        )

    prompt_packet = outline.get("writer_prompt_packet") if isinstance(outline.get("writer_prompt_packet"), dict) else {}
    missing_prompt = [
        key
        for key in ("role", "input_contract", "output_contract", "forbidden_actions", "acceptance_gate", "starter_prompt")
        if not prompt_packet.get(key)
    ]
    if missing_prompt:
        add_finding(
            findings,
            finding_id="missing_writer_prompt_packet",
            severity="medium",
            title="Outline lacks a low-token writer prompt packet.",
            outline=title,
            evidence={"missing": missing_prompt},
        )

    fact_check_queue = writer_handoff.get("fact_check_queue") if isinstance(writer_handoff.get("fact_check_queue"), list) else []
    if len(fact_check_queue) < 3:
        add_finding(
            findings,
            finding_id="missing_fact_check_queue",
            severity="medium",
            title="Outline lacks a useful fact-check queue.",
            outline=title,
            evidence={"fact_check_queue": len(fact_check_queue)},
        )

    sections_without_evidence = [
        section.get("title")
        for section in sections
        if isinstance(section, dict) and not section.get("evidence_required")
    ]
    if sections_without_evidence:
        add_finding(
            findings,
            finding_id="missing_evidence_requirements",
            severity="medium",
            title="Some sections do not require proof/source evidence.",
            outline=title,
            evidence={"sections": sections_without_evidence[:10]},
        )

    guard = outline.get("eeat_guard") if isinstance(outline.get("eeat_guard"), dict) else {}
    if not guard:
        add_finding(
            findings,
            finding_id="unsafe_first_person_expertise",
            severity="critical",
            title="Outline has no E-E-A-T no-fabrication guard.",
            outline=title,
            evidence={"eeat_guard": None},
        )
    elif guard.get("expert_author_mode") != "real_expert_allowed" and FIRST_PERSON_RISK_RE.search(text_blob(outline)):
        add_finding(
            findings,
            finding_id="unsafe_first_person_expertise",
            severity="critical",
            title="Outline asks for first-person expertise without real expert mode.",
            outline=title,
            evidence={"expert_author_mode": guard.get("expert_author_mode")},
        )

    entity_names = {norm(entity.get("name")) for entity in outline.get("entities", []) if isinstance(entity, dict) and entity.get("name")}
    covered_entities = set()
    sections_without_connections = []
    sections_without_visuals = []
    sections_without_bridges = []
    sections_without_h3 = []
    subsection_mismatches = []
    weak_copywriting = []
    missing_source_slots = []
    missing_acceptance = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        covered_entities.update(norm(entity) for entity in section.get("entities_to_cover", []) if norm(entity))
        connections = section.get("entity_connections") or []
        if not connections:
            sections_without_connections.append(section.get("title"))
        for connection in connections:
            for entity_name in entity_names:
                if entity_name and entity_name.replace("_", " ") in str(connection).lower():
                    covered_entities.add(entity_name)
        if not str(section.get("visual_elements") or "").strip():
            sections_without_visuals.append(section.get("title"))
        bridge = section.get("bridge") if isinstance(section.get("bridge"), dict) else {}
        if not bridge.get("from_previous") or not bridge.get("to_next"):
            sections_without_bridges.append(section.get("title"))
        h3_subsections = section.get("h3_subsections") if isinstance(section.get("h3_subsections"), list) else []
        if len(h3_subsections) < 2:
            sections_without_h3.append(section.get("title"))
        else:
            h3_min = sum(int(item.get("word_count_min") or 0) for item in h3_subsections if isinstance(item, dict))
            h3_max = sum(int(item.get("word_count_max") or 0) for item in h3_subsections if isinstance(item, dict))
            if h3_min != int(section.get("word_count_min") or 0) or h3_max != int(section.get("word_count_max") or 0):
                subsection_mismatches.append(
                    {
                        "section": section.get("title"),
                        "section_range": [section.get("word_count_min"), section.get("word_count_max")],
                        "h3_sum": [h3_min, h3_max],
                    }
                )
        details = section.get("copywriting_details") if isinstance(section.get("copywriting_details"), dict) else {}
        missing_detail_keys = [
            key
            for key in ("reader_question", "opening_angle", "do_write", "do_not_write", "safe_phrases", "cta")
            if not details.get(key)
        ]
        if missing_detail_keys:
            weak_copywriting.append({"section": section.get("title"), "missing": missing_detail_keys})
        source_slots = details.get("source_slots") if isinstance(details.get("source_slots"), list) else []
        if len(source_slots) < 2 or any(not isinstance(item, dict) or not item.get("claim_type") or not item.get("proof") for item in source_slots):
            missing_source_slots.append(section.get("title"))
        acceptance = details.get("acceptance_criteria") if isinstance(details.get("acceptance_criteria"), list) else []
        if len(acceptance) < 3:
            missing_acceptance.append(section.get("title"))

    orphan = sorted(entity for entity in entity_names if entity and entity not in covered_entities)
    if orphan:
        add_finding(
            findings,
            finding_id="orphan_entities",
            severity="medium",
            title="Page-level entities are not assigned to sections or connections.",
            outline=title,
            evidence={"entities": orphan[:20]},
        )
    if sections_without_connections:
        add_finding(
            findings,
            finding_id="missing_entity_connections",
            severity="medium",
            title="Some sections lack entity connections/triplets.",
            outline=title,
            evidence={"sections": sections_without_connections[:10]},
        )
    if sections_without_bridges:
        add_finding(
            findings,
            finding_id="missing_section_bridges",
            severity="medium",
            title="Some sections lack bridge instructions.",
            outline=title,
            evidence={"sections": sections_without_bridges[:10]},
        )
    if sections_without_h3:
        add_finding(
            findings,
            finding_id="missing_h3_subsections",
            severity="high",
            title="Some sections lack copywriter-ready H3 subsection plans.",
            outline=title,
            evidence={"sections": sections_without_h3[:10]},
        )
    if subsection_mismatches:
        add_finding(
            findings,
            finding_id="subsection_word_count_mismatch",
            severity="high",
            title="H3 subsection word counts do not add up to their parent H2 section.",
            outline=title,
            evidence={"mismatches": subsection_mismatches[:10]},
        )
    if weak_copywriting:
        add_finding(
            findings,
            finding_id="weak_copywriting_details",
            severity="high",
            title="Some sections lack concrete copywriting instructions.",
            outline=title,
            evidence={"sections": weak_copywriting[:10]},
        )
    if missing_source_slots:
        add_finding(
            findings,
            finding_id="missing_source_slots",
            severity="medium",
            title="Some sections lack source slots for claim proof.",
            outline=title,
            evidence={"sections": missing_source_slots[:10]},
        )
    if missing_acceptance:
        add_finding(
            findings,
            finding_id="missing_acceptance_criteria",
            severity="medium",
            title="Some sections lack acceptance criteria for copy review.",
            outline=title,
            evidence={"sections": missing_acceptance[:10]},
        )
    if sections_without_visuals:
        add_finding(
            findings,
            finding_id="missing_visual_guidance",
            severity="medium",
            title="Some sections lack visual/table/screenshot guidance.",
            outline=title,
            evidence={"sections": sections_without_visuals[:10]},
        )

    visual_plan = outline.get("visual_plan") if isinstance(outline.get("visual_plan"), list) else []
    weak_visuals = [
        item
        for item in visual_plan
        if not isinstance(item, dict)
        or not item.get("id")
        or not item.get("placement")
        or not item.get("dedupe_key")
        or not item.get("alt_text_guidance")
    ]
    if len(visual_plan) < 2 or weak_visuals:
        add_finding(
            findings,
            finding_id="weak_visual_plan",
            severity="medium",
            title="Outline lacks a numbered, deduped visual plan.",
            outline=title,
            evidence={"visuals": len(visual_plan), "weak_visuals": len(weak_visuals)},
        )

    if not outline.get("geo_requirements"):
        add_finding(
            findings,
            finding_id="missing_geo_requirements",
            severity="medium",
            title="Outline has no GEO/AEO requirements.",
            outline=title,
            evidence={"geo_requirements": outline.get("geo_requirements")},
        )
    trust_limitations = outline.get("trust_limitations") if isinstance(outline.get("trust_limitations"), list) else []
    if len(trust_limitations) < 3:
        add_finding(
            findings,
            finding_id="missing_trust_limitations",
            severity="medium",
            title="Outline lacks explicit trust and limitations guidance.",
            outline=title,
            evidence={"trust_limitations": len(trust_limitations)},
        )
    synthetic_prompts = outline.get("synthetic_prompts") if isinstance(outline.get("synthetic_prompts"), list) else []
    if len(synthetic_prompts) < 3:
        add_finding(
            findings,
            finding_id="missing_synthetic_prompts",
            severity="medium",
            title="Outline lacks synthetic AI visibility prompts.",
            outline=title,
            evidence={"synthetic_prompts": len(synthetic_prompts)},
        )
    outline_version = "v3" if outline.get("outline_id") == "page_outline_v3" or outline.get("version") == "v3" else "v2"
    if version == "v3" or outline_version == "v3":
        findings.extend(validate_v3_outline(outline, title))
    return findings


def validate_v3_outline(outline: dict[str, Any], title: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    page = outline.get("page") if isinstance(outline.get("page"), dict) else {}
    page_type = str(page.get("page_type") or "").strip().lower()
    sections = outline.get("sections") if isinstance(outline.get("sections"), list) else []
    order = ((outline.get("serp_safe_layout") or {}) if isinstance(outline.get("serp_safe_layout"), dict) else {}).get("order")
    tool_like = page_type in {"tool", "app", "tool/app", "quiz", "analyzer", "webapplication"}
    first_role = (sections[0].get("section_role") if sections and isinstance(sections[0], dict) else None)
    if tool_like and (not isinstance(order, list) or not order or order[0] != "tool_ux_above_the_fold" or first_role != "tool_ux_above_the_fold"):
        add_finding(
            findings,
            finding_id="tool_first_order_violation",
            severity="critical",
            title="Tool/app page does not put tool UX above longform copy.",
            outline=title,
            evidence={"page_type": page_type, "order": order, "first_section_role": first_role},
        )
    visual_inventory = outline.get("visual_inventory") if isinstance(outline.get("visual_inventory"), list) else []
    weak_visuals = [
        item
        for item in visual_inventory
        if not isinstance(item, dict)
        or not item.get("type")
        or not item.get("placement")
        or not item.get("purpose")
        or not item.get("source_requirement")
        or not item.get("alt_text_guidance")
        or not item.get("dedupe_key")
    ]
    if len(visual_inventory) < 6 or weak_visuals:
        add_finding(
            findings,
            finding_id="weak_visual_inventory",
            severity="high",
            title="v3 outline lacks a concrete visual/table/callout inventory.",
            outline=title,
            evidence={"visual_inventory": len(visual_inventory), "weak_visuals": len(weak_visuals)},
        )
    if not outline.get("copywriter_ready_contract"):
        add_finding(
            findings,
            finding_id="missing_copywriter_ready_contract",
            severity="high",
            title="v3 outline lacks the copywriter-ready handoff contract.",
            outline=title,
            evidence={"copywriter_ready_contract": None},
        )
    if not outline.get("entity_triplets"):
        add_finding(
            findings,
            finding_id="missing_triplet_export",
            severity="high",
            title="v3 outline lacks reusable entity triplet records.",
            outline=title,
            evidence={"entity_triplets": len(outline.get("entity_triplets") or [])},
        )
    required = (
        "word_count",
        "entities_to_cover",
        "keywords",
        "summary",
        "visual_elements",
        "copywriter_notes",
        "entity_connections",
        "answer_unit",
        "source_slots",
        "acceptance_criteria",
    )
    missing = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_missing = [key for key in required if not section.get(key)]
        if section_missing:
            missing.append({"section": section.get("title"), "missing": section_missing})
        for subsection in section.get("h3_subsections") or []:
            if isinstance(subsection, dict):
                sub_missing = [key for key in required if not subsection.get(key)]
                if sub_missing:
                    missing.append({"section": section.get("title"), "subsection": subsection.get("title"), "missing": sub_missing})
    if missing:
        add_finding(
            findings,
            finding_id="missing_section_v3_fields",
            severity="high",
            title="v3 sections or H3 subsections are missing copywriter-ready fields.",
            outline=title,
            evidence={"missing": missing[:10]},
        )
    return findings


def scorecard(findings: list[dict[str, Any]], version: str = "auto") -> list[dict[str, Any]]:
    criteria = V3_QUALITY_CRITERIA if version == "v3" else QUALITY_CRITERIA
    scores = {criterion["id"]: 10 for criterion in criteria}
    blockers: dict[str, list[str]] = {criterion["id"]: [] for criterion in criteria}
    for finding in findings:
        penalty = SEVERITY_PENALTY.get(str(finding.get("severity")), 1)
        for criterion_id in FINDING_CRITERIA.get(str(finding.get("id")), ("handoff_machine_readability",)):
            if criterion_id not in scores:
                continue
            scores[criterion_id] = max(0, scores[criterion_id] - penalty)
            blockers[criterion_id].append(str(finding.get("id")))
    return [
        {
            "id": criterion["id"],
            "label": criterion["label"],
            "score": scores[criterion["id"]],
            "status": "excellent" if scores[criterion["id"]] == 10 else "needs_work" if scores[criterion["id"]] < 9 else "review",
            "blocking_findings": sorted(set(blockers[criterion["id"]])),
        }
        for criterion in criteria
    ]


def audit(raw: str | pathlib.Path, version: str = "auto") -> dict[str, Any]:
    json_files, md_files = discover_outline_files(raw, version=version)
    findings: list[dict[str, Any]] = []
    outlines: list[dict[str, Any]] = []
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        if "<div" in text.lower() or "<h2" in text.lower() or "<h3" in text.lower():
            add_finding(
                findings,
                finding_id="unstructured_html_outline",
                severity="high",
                title="Markdown outline contains HTML structure that is hard to validate.",
                outline=str(md_file),
                evidence={"file": str(md_file)},
            )
    for path in json_files:
        data = read_json(path)
        for outline in outlines_from_json(data):
            outlines.append(outline)
            findings.extend(validate_outline(outline, str(path), version=version))
    if not outlines:
        add_finding(
            findings,
            finding_id="no_outline_json",
            severity="critical",
            title="No page-outline-v2 JSON outlines found.",
            outline=str(raw),
            evidence={"json_files": [str(path) for path in json_files[:10]]},
        )
    findings.sort(key=lambda item: SEVERITY_ORDER.get(item["severity"], 0), reverse=True)
    critical = sum(1 for item in findings if item["severity"] == "critical")
    high = sum(1 for item in findings if item["severity"] == "high")
    medium = sum(1 for item in findings if item["severity"] == "medium")
    score = max(0, 100 - critical * 20 - high * 10 - medium * 5)
    resolved_version = version
    if resolved_version == "auto":
        resolved_version = "v3" if any(outline.get("outline_id") == "page_outline_v3" or outline.get("version") == "v3" for outline in outlines) else "v2"
    cards = scorecard(findings, version=resolved_version)
    status = "fail" if critical else "warn" if findings else "pass"
    return {
        "audit_id": "page_outline_quality",
        "title": "Page Outline Quality Gate",
        "generated_at": utc_now(),
        "outline_version": resolved_version,
        "status": status,
        "score": score,
        "ten_point_score": round(sum(item["score"] for item in cards) / max(1, len(cards)), 1),
        "input": str(pathlib.Path(raw).expanduser()),
        "counts": {
            "json_files": len(json_files),
            "markdown_files": len(md_files),
            "outlines": len(outlines),
            "findings": len(findings),
            "critical_findings": critical,
            "high_findings": high,
            "medium_findings": medium,
        },
        "scorecard": cards,
        "findings": findings,
        "action_plan": [
            {
                "step": idx,
                "priority": {"critical": "P0", "high": "P1", "medium": "P2", "low": "P3"}.get(item["severity"], "P2"),
                "finding_id": item["id"],
                "outline": item["outline"],
                "command": item["recommended_action"],
                "done": "Rerun page-outline-quality.py and clear this finding.",
            }
            for idx, item in enumerate(findings[:12], start=1)
        ],
        "paths": {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Page Outline Quality Gate",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- Score: `{report['score']}/100`",
        f"- 10-point score: `{report['ten_point_score']}/10`",
        f"- Input: `{report['input']}`",
        "",
        "## Counts",
    ]
    lines.extend(f"- {key}: {value}" for key, value in report["counts"].items())
    lines.extend(["", "## 10-Criteria Scorecard"])
    for item in report["scorecard"]:
        blockers = ", ".join(f"`{finding}`" for finding in item["blocking_findings"]) or "none"
        lines.append(f"- `{item['score']}/10` {item['label']} ({item['status']}): {blockers}")
    lines.extend(["", "## Action Plan"])
    if not report["action_plan"]:
        lines.append("- No action required.")
    for item in report["action_plan"]:
        lines.extend(
            [
                f"### Step {item['step']}: `{item['finding_id']}`",
                "",
                f"- Priority: `{item['priority']}`",
                f"- Outline: `{item['outline']}`",
                f"- Command: {item['command']}",
                f"- Done: {item['done']}",
                "",
            ]
        )
    lines.extend(["", "## Findings"])
    if not report["findings"]:
        lines.append("No findings. Page outlines passed the current quality gate.")
    for item in report["findings"]:
        lines.extend(
            [
                f"### [{item['severity'].upper()}] {item['title']}",
                "",
                f"- ID: `{item['id']}`",
                f"- Outline: `{item['outline']}`",
                f"- Evidence: `{json.dumps(item['evidence'], ensure_ascii=False)[:1200]}`",
                f"- Action: {item['recommended_action']}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def write_outputs(input_path: pathlib.Path, report: dict[str, Any], output_dir: pathlib.Path | None = None) -> None:
    base = input_path if input_path.is_dir() else input_path.parent
    out = output_dir or base
    paths = {
        "markdown": out / "page-outline-quality.md",
        "json": out / "page-outline-quality.json",
        "latest_markdown": out / "latest-page-outline-quality.md",
        "latest_json": out / "latest-page-outline-quality.json",
    }
    report["paths"] = {key: str(path) for key, path in paths.items()}
    markdown = render_markdown(report)
    write_report_bundle(paths, markdown, report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit page-outline JSON/Markdown quality before writing or publishing.")
    parser.add_argument("input", help="A page-outline JSON file, batch JSON, page-outlines-v2/v3 directory, or research package directory.")
    parser.add_argument("--version", choices=["auto", "v2", "v3"], default="auto", help="Outline version to discover and validate.")
    parser.add_argument("--write", action="store_true", help="Write page-outline-quality.md/json next to the input or under --output-dir.")
    parser.add_argument("--output-dir", help="Optional output directory.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args(argv)

    input_path = pathlib.Path(args.input).expanduser().resolve()
    report = audit(input_path, version=args.version)
    if args.write:
        write_outputs(input_path, report, pathlib.Path(args.output_dir).expanduser().resolve() if args.output_dir else None)
    if args.format == "markdown":
        print(render_markdown(report), end="")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
