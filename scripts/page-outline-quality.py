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

from seo_cycle_core.config import write_text


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

FINDING_CRITERIA = {
    "no_outline_json": ("handoff_machine_readability",),
    "unstructured_html_outline": ("handoff_machine_readability", "technical_seo_wrap"),
    "missing_required_fields": ("handoff_machine_readability", "copywriter_actionability"),
    "word_count_mismatch": ("word_count_integrity", "copywriter_actionability"),
    "missing_page_context": ("serp_intent_lock", "copywriter_actionability"),
    "missing_seo_meta": ("technical_seo_wrap",),
    "missing_schema": ("technical_seo_wrap",),
    "missing_internal_links": ("internal_links_cannibalization",),
    "missing_answer_units": ("geo_answer_units", "copywriter_actionability"),
    "missing_evidence_requirements": ("eeat_no_fabrication", "copywriter_actionability"),
    "unsafe_first_person_expertise": ("eeat_no_fabrication",),
    "orphan_entities": ("entity_coverage",),
    "missing_entity_connections": ("entity_coverage", "handoff_machine_readability"),
    "missing_visual_guidance": ("visual_ux_guidance",),
    "missing_geo_requirements": ("geo_answer_units",),
}

REMEDIATION = {
    "no_outline_json": "Generate outlines with page-outline-v2.py --all-mvp --write or pass a JSON outline file.",
    "unstructured_html_outline": "Regenerate as page-outline-v2 JSON/Markdown; avoid HTML-only briefs that cannot be validated.",
    "missing_required_fields": "Regenerate the outline from the research package so page, sections, schema and guards are present.",
    "word_count_mismatch": "Recompute outline computed_word_count from the section min/max totals.",
    "missing_page_context": "Carry page_type, intent, primary_keyword and URL from final research architecture into the outline.",
    "missing_seo_meta": "Add title tag, meta description, slug/canonical and alt text guidance.",
    "missing_schema": "Add schema recommendations such as WebApplication/Article, FAQPage and BreadcrumbList.",
    "missing_internal_links": "Add internal links from final cluster architecture; do not invent unrelated detours.",
    "missing_answer_units": "Add required Answer Units to answer/definition/trust/FAQ sections.",
    "missing_evidence_requirements": "Add source/proof requirements per section, especially for numbers, claims and expert statements.",
    "unsafe_first_person_expertise": "Remove first-person expert anecdotes or switch to real_expert_allowed only with named proof.",
    "orphan_entities": "Either assign each page entity to sections/connections or remove it from the page entity set.",
    "missing_entity_connections": "Add section-level entity triplets/relations tied to the primary intent.",
    "missing_visual_guidance": "Add concrete visual/table/screenshot guidance per section.",
    "missing_geo_requirements": "Add answer-first, FAQ, proof block and synthetic AI prompt requirements.",
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
    if data.get("outline_id") == "page_outline_v2":
        return [data]
    return []


def discover_outline_files(raw: str | pathlib.Path) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    path = pathlib.Path(raw).expanduser().resolve()
    if path.is_file():
        if path.suffix.lower() == ".json":
            return [path], []
        return [], [path]
    candidates = []
    md_candidates = []
    if (path / "page-outlines-v2").exists():
        candidates.extend(sorted((path / "page-outlines-v2").glob("*.json")))
        md_candidates.extend(sorted((path / "page-outlines-v2").glob("*.md")))
    candidates.extend(sorted(path.glob("*.json")))
    md_candidates.extend(sorted(path.glob("*.md")))
    return list(dict.fromkeys(candidates)), list(dict.fromkeys(md_candidates))


def text_blob(outline: dict[str, Any]) -> str:
    chunks = [json.dumps(outline.get("page", {}), ensure_ascii=False)]
    for section in outline.get("sections", []):
        if isinstance(section, dict):
            chunks.append(json.dumps(section, ensure_ascii=False))
    return "\n".join(chunks)


def validate_outline(outline: dict[str, Any], fallback: str) -> list[dict[str, Any]]:
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
    if sections_without_visuals:
        add_finding(
            findings,
            finding_id="missing_visual_guidance",
            severity="medium",
            title="Some sections lack visual/table/screenshot guidance.",
            outline=title,
            evidence={"sections": sections_without_visuals[:10]},
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
    return findings


def scorecard(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scores = {criterion["id"]: 10 for criterion in QUALITY_CRITERIA}
    blockers: dict[str, list[str]] = {criterion["id"]: [] for criterion in QUALITY_CRITERIA}
    for finding in findings:
        penalty = SEVERITY_PENALTY.get(str(finding.get("severity")), 1)
        for criterion_id in FINDING_CRITERIA.get(str(finding.get("id")), ("handoff_machine_readability",)):
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
        for criterion in QUALITY_CRITERIA
    ]


def audit(raw: str | pathlib.Path) -> dict[str, Any]:
    json_files, md_files = discover_outline_files(raw)
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
            findings.extend(validate_outline(outline, str(path)))
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
    cards = scorecard(findings)
    status = "fail" if critical else "warn" if findings else "pass"
    return {
        "audit_id": "page_outline_quality",
        "title": "Page Outline Quality Gate",
        "generated_at": utc_now(),
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
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    write_text(paths["markdown"], markdown)
    write_text(paths["json"], json_text)
    write_text(paths["latest_markdown"], markdown)
    write_text(paths["latest_json"], json_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit page-outline-v2 JSON/Markdown quality before writing or publishing.")
    parser.add_argument("input", help="A page-outline-v2 JSON file, batch JSON, page-outlines-v2 directory, or research package directory.")
    parser.add_argument("--write", action="store_true", help="Write page-outline-quality.md/json next to the input or under --output-dir.")
    parser.add_argument("--output-dir", help="Optional output directory.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args(argv)

    input_path = pathlib.Path(args.input).expanduser().resolve()
    report = audit(input_path)
    if args.write:
        write_outputs(input_path, report, pathlib.Path(args.output_dir).expanduser().resolve() if args.output_dir else None)
    if args.format == "markdown":
        print(render_markdown(report), end="")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
