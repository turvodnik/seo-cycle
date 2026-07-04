#!/usr/bin/env python3
"""Report the step-by-step path from project setup to SEO execution.

The journey is intentionally read-only by default. It inspects existing
project artifacts, identifies the current stage, and tells the agent exactly
what is missing before the next stage can start.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, policy_path, project_root_for, rel_display, rel_path, write_text
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.scorecard import load_latest as load_scorecards
from seo_cycle_core.scorecard import render_scorecards_markdown

log = setup_logging("project-journey")


from seo_cycle_core.journey import (  # noqa: E402
    artifact_exists,
    artifact_path,
    detect_research_package,
    json_summary,
    loop_evidence_line,
    loop_states,
    package_state,
    read_json,
    stage,
    unique_paths,
    utc_now,
)


def setup_stage(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    checks = [
        ("project_intake", "seo/project-intake.yaml"),
        ("setup_blueprint", "seo/setup/setup-blueprint.md"),
        ("setup_gap_audit_json", "seo/setup/setup-gap-audit.json"),
        ("setup_control_plane", "seo/setup/setup-control-plane.md"),
    ]
    evidence = []
    missing = []
    for key, default in checks:
        path, exists = artifact_exists(cfg, project_root, key, default)
        evidence.append(f"{path}: {'exists' if exists else 'missing'}")
        if not exists:
            missing.append(path)
    gap = json_summary(artifact_path(cfg, project_root, "setup_gap_audit_json", "seo/setup/setup-gap-audit.json"))
    missing_gaps = int(((gap.get("summary") or {}) if isinstance(gap.get("summary"), dict) else {}).get("missing") or 0)
    blockers = []
    if missing_gaps:
        blockers.append(f"{missing_gaps} setup questionnaire fields are still unanswered.")
    return stage(
        stage_id="setup_foundation",
        order=1,
        title="Setup foundation",
        objective="Project identity, market, governance, and setup questionnaire are known.",
        evidence=evidence,
        missing=missing,
        blockers=blockers,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/setup-control-plane.py --write",
            "Fill seo/setup/setup-questionnaire.csv, then run setup-answer-plan.py --write when gaps remain.",
        ],
        exit_criteria=[
            "seo/project-intake.yaml exists.",
            "seo/setup/setup-gap-audit.json has 0 missing required setup fields or a reviewed exception.",
            "seo/setup/setup-control-plane.md exists.",
        ],
    )


def governance_stage(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    checks = [
        ("tool_stack_report", "seo/setup/tool-stack-report.md"),
        ("access_key_assistant", "seo/setup/access-key-assistant.md"),
        ("spend_guard_report", "seo/setup/spend-guard.md"),
        ("launch_plan_report", "seo/setup/launch-plan.md"),
    ]
    evidence = []
    missing = []
    for key, default in checks:
        path, exists = artifact_exists(cfg, project_root, key, default)
        evidence.append(f"{path}: {'exists' if exists else 'missing'}")
        if not exists:
            missing.append(path)
    access = json_summary(artifact_path(cfg, project_root, "access_key_assistant_json", "seo/setup/access-key-assistant.json"))
    tasks = int(((access.get("summary") or {}) if isinstance(access.get("summary"), dict) else {}).get("tasks") or 0)
    approval = int(((access.get("summary") or {}) if isinstance(access.get("summary"), dict) else {}).get("approval_required") or 0)
    warnings = []
    if tasks:
        warnings.append(f"{tasks} access/key setup tasks are listed; {approval} require approval.")
    return stage(
        stage_id="access_budget_governance",
        order=2,
        title="Access, budget, and governance",
        objective="Needed tools are selected, secrets are listed by env name only, and spend gates are clear.",
        evidence=evidence,
        missing=missing,
        warnings=warnings,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/access-key-assistant.py --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/spend-guard.py --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/launch-plan.py --write",
        ],
        exit_criteria=[
            "Required provider env names are known and secrets are stored only in .env/provider consoles.",
            "Paid/API/LLM/ads gates are either approved or explicitly deferred.",
        ],
    )


def evidence_stage(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    checks = [
        ("expert_source_pack_report", "seo/vnext/expert-source-pack.md"),
        ("perplexity_health_report", "seo/setup/perplexity-health.md"),
        ("notebooklm_health_report", "seo/setup/notebooklm-health.md"),
    ]
    evidence = []
    missing = []
    for key, default in checks:
        path, exists = artifact_exists(cfg, project_root, key, default)
        evidence.append(f"{path}: {'exists' if exists else 'missing'}")
        if not exists:
            missing.append(path)
    xmlriver_path, xmlriver_exists = artifact_exists(cfg, project_root, "xmlriver_health_report", "seo/setup/xmlriver-health.md")
    evidence.append(f"{xmlriver_path}: {'exists' if xmlriver_exists else 'optional_missing'}")
    perplexity = json_summary(artifact_path(cfg, project_root, "perplexity_health_json", "seo/setup/perplexity-health.json"))
    notebook = json_summary(artifact_path(cfg, project_root, "notebooklm_health_json", "seo/setup/notebooklm-health.json"))
    xmlriver = json_summary(artifact_path(cfg, project_root, "xmlriver_health_json", "seo/setup/xmlriver-health.json"))
    warnings = []
    if perplexity.get("status") == "degraded_source":
        warnings.append("Perplexity is degraded; use Codex/Antigravity/NotebookLM fallback.")
    if notebook.get("status") in {"fallback_required", "unavailable"}:
        warnings.append("NotebookLM MCP is unavailable; use browser/manual export source-pack fallback.")
    if xmlriver.get("status") == "needs_credentials":
        warnings.append("XMLRiver live SERP/Wordstat enrichment needs XMLRIVER_USER_ID/XMLRIVER_API_KEY and paid API approval.")
    return stage(
        stage_id="expert_evidence_sources",
        order=3,
        title="Expert evidence sources",
        objective="Expert sources and AI research providers are available as cached distillates, not raw context dumps.",
        evidence=evidence,
        missing=missing,
        warnings=warnings,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/perplexity-health.py --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/notebooklm-health.py --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/xmlriver-health.py --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/expert-source-pack.py --write",
        ],
        exit_criteria=[
            "At least one expert/source-pack path is available or an explicit degraded fallback is logged.",
            "Raw transcripts and long exports stay on disk; only distillates enter prompt context.",
        ],
    )


def technical_stage(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    checks = [
        ("technical_site_audit_report", "seo/technical/technical-site-audit.md"),
        ("link_audit_report", "seo/technical/link-audit.md"),
        ("redirect_map_audit_report", "seo/technical/redirect-map-audit.md"),
    ]
    evidence = []
    missing = []
    for key, default in checks:
        path, exists = artifact_exists(cfg, project_root, key, default)
        evidence.append(f"{path}: {'exists' if exists else 'missing'}")
        if not exists:
            missing.append(path)
    return stage(
        stage_id="technical_baseline",
        order=4,
        title="Technical baseline",
        objective="Crawl, redirects, indexability, performance, and search-console inspections are known before content work.",
        evidence=evidence,
        missing=missing,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/link-audit.py --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/redirect-map-audit.py --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/technical-site-audit.py --write",
        ],
        exit_criteria=[
            "Broken links/redirects/indexability/CWV risks are logged or explicitly deferred.",
            "Technical blockers are separated from content recommendations.",
        ],
    )


def research_stage(project_root: pathlib.Path, package: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if not package["exists"]:
        missing.append("seo/research-package/semantic-architecture-final.json")
    missing.extend(f"{package.get('package_dir') or 'seo/research-package'}/{name}" for name in package.get("missing_required", []))
    evidence = [f"research package: {package.get('package_dir') or 'missing'}"]
    evidence.extend(f"{name}: {'exists' if exists else 'missing'}" for name, exists in package.get("required", {}).items())
    return stage(
        stage_id="research_architecture",
        order=5,
        title="Research architecture",
        objective="Macro plan exists: semantic core, clusters, URLs, page types, entities, and content plan.",
        evidence=evidence,
        missing=missing,
        commands=[
            "Create or import a research package under seo/research-package/.",
            "Use GSC/DataForSEO/SERP/entity sources to fill semantic-core.csv, content-plan.csv, and semantic-architecture-final.json.",
        ],
        exit_criteria=[
            "Research package required files exist.",
            "Architecture chooses page types from SERP evidence, not model preference.",
        ],
    )


def quality_stage(package: dict[str, Any]) -> dict[str, Any]:
    quality = package.get("quality", {})
    package_dir = package.get("package_dir") or "seo/research-package"
    missing = [] if package.get("quality_exists") else [f"{package_dir}/research-package-quality.json"]
    blockers = []
    warnings = []
    if package.get("quality_stale_after_repair"):
        blockers.append(
            "Rerun research-package-quality.py after research-package-repair: repair output is newer than quality output."
        )
    if quality.get("status") == "fail":
        critical = int(((quality.get("counts") or {}) if isinstance(quality.get("counts"), dict) else {}).get("critical_findings") or 0)
        high = int(((quality.get("counts") or {}) if isinstance(quality.get("counts"), dict) else {}).get("high_findings") or 0)
        warnings.append(f"Research package quality gate is fail: critical={critical}, high={high}; continue to repair layer.")
        for finding in quality.get("findings", [])[:5]:
            if isinstance(finding, dict):
                warnings.append(f"{finding.get('severity', 'finding')}: {finding.get('id')} — {finding.get('title')}")
    evidence = [
        f"{package_dir}/research-package-quality.json: {'exists' if package.get('quality_exists') else 'missing'}",
        f"{package_dir}/research-package-repair.json: {'exists' if package.get('repair_exists') else 'missing'}",
        f"quality status: {quality.get('status', 'not_run')}",
        f"10-point score: {quality.get('ten_point_score', 'n/a')}",
        f"quality stale after repair: {package.get('quality_stale_after_repair', False)}",
    ]
    loop_info = (package.get("loops") or {}).get("research-package")
    loop_line = loop_evidence_line(loop_info)
    if loop_line:
        evidence.append(loop_line)
    if loop_info and loop_info.get("status") == "escalated":
        blockers.append(
            f"Quality loop escalated after {loop_info.get('attempts_used')} attempts"
            f" (ticket {loop_info.get('escalation_ticket') or 'n/a'}) — review {loop_info.get('state_file')} before retrying."
        )
    return stage(
        stage_id="research_quality_gate",
        order=6,
        title="Research quality gate",
        objective="The macro package passes the comparison-audit failure checks before writing begins.",
        evidence=evidence,
        missing=missing,
        blockers=blockers,
        warnings=warnings,
        commands=[
            f"python3 ~/.codex/skills/seo-cycle/scripts/loop-runner.py research-package {package_dir}",
            f"python3 ~/.codex/skills/seo-cycle/scripts/research-package-quality.py {package_dir} --write --format plan",
        ],
        exit_criteria=[
            "No critical findings remain.",
            "research-package-quality.py has been rerun after any research-package-repair.py output.",
            "SERP validation, URL mapping, GSC cleanup, entity map, GEO signals, and E-E-A-T evidence are either clean or explicitly accepted.",
        ],
    )


REPAIR_COMMANDS = {
    "serp_validation_incomplete": "python3 ~/.codex/skills/seo-cycle/scripts/serp-validation-plan.py {package_dir} --write",
    "semantic_core_url_drift": "python3 ~/.codex/skills/seo-cycle/scripts/semantic-core-resync.py {package_dir} --write",
    "dirty_semantic_core_queries": "python3 ~/.codex/skills/seo-cycle/scripts/semantic-core-clean.py {package_dir} --write",
    "orphan_internal_urls": "python3 ~/.codex/skills/seo-cycle/scripts/orphan-url-resolver.py {package_dir} --write",
    "entity_map_md_yaml_drift": "python3 ~/.codex/skills/seo-cycle/scripts/entity-map-sync.py {package_dir} --write",
    "google_nlp_not_aggregated": "python3 ~/.codex/skills/seo-cycle/scripts/google-nlp-aggregate.py {package_dir} --write",
}


def repair_stage(package: dict[str, Any]) -> dict[str, Any]:
    package_dir = package.get("package_dir") or "seo/research-package"
    quality = package.get("quality", {})
    repair = package.get("repair", {})
    quality_failed = quality.get("status") == "fail"
    missing = []
    blockers = []
    commands = [
        f"python3 ~/.codex/skills/seo-cycle/scripts/loop-runner.py research-package {package_dir}",
        f"python3 ~/.codex/skills/seo-cycle/scripts/research-package-repair.py {package_dir} --write",
    ]
    if quality_failed and not package.get("repair_exists"):
        missing.append(f"{package_dir}/research-package-repair.json")
    if quality_failed:
        blockers.append("Research package repair is required before deep briefs.")
        for finding in quality.get("findings", [])[:8]:
            if isinstance(finding, dict):
                finding_id = str(finding.get("id") or "")
                blockers.append(f"{finding.get('severity', 'finding')}: {finding_id} — {finding.get('title')}")
                command = REPAIR_COMMANDS.get(finding_id)
                if command:
                    commands.append(command.format(package_dir=package_dir))
                if finding_id == "serp_validation_incomplete":
                    commands.append(
                        "python3 ~/.codex/skills/seo-cycle/scripts/serp-validation-import.py "
                        f"{package_dir} --input-json <reviewed-serp-export.json> --write"
                    )
        commands.append(f"python3 ~/.codex/skills/seo-cycle/scripts/research-package-quality.py {package_dir} --write --format plan")
    failed_steps = int(((repair.get("summary") or {}) if isinstance(repair.get("summary"), dict) else {}).get("failed_steps") or 0)
    if failed_steps:
        blockers.append(f"research-package-repair has {failed_steps} failed steps.")
    evidence = [
        f"{package_dir}/research-package-repair.json: {'exists' if package.get('repair_exists') else 'missing'}",
        f"quality status: {quality.get('status', 'not_run')}",
        f"repair failed steps: {failed_steps}",
    ]
    return stage(
        stage_id="research_package_repair",
        order=7,
        title="Research package repair",
        objective="Repair dirty semantic core, URL/cluster drift, entity/NLP drift, orphan URLs, missing SERP validation and phase-2 spoke opportunities before deep briefs.",
        evidence=evidence,
        missing=missing,
        blockers=blockers,
        commands=commands,
        exit_criteria=[
            "research-package-repair.json exists with 0 failed steps when the package previously failed quality.",
            "research-package-quality.py has been rerun after repair.",
            "No critical findings remain unless explicitly accepted in policy.",
        ],
    )


def brief_stage(package: dict[str, Any]) -> dict[str, Any]:
    package_dir = package.get("package_dir") or "seo/research-package"
    quality = package.get("quality", {})
    outline_quality = package.get("outline_quality", {})
    blockers = []
    warnings = []
    has_v3 = int(package.get("outline_v3_count") or 0) > 0
    if quality.get("status") == "fail":
        blockers.append("Deep briefs are blocked until research-package-quality has no critical findings.")
    if not has_v3 and outline_quality.get("status") == "fail":
        counts = outline_quality.get("counts") if isinstance(outline_quality.get("counts"), dict) else {}
        blockers.append(
            "Page outlines quality gate is fail: "
            f"critical={int(counts.get('critical_findings') or 0)}, high={int(counts.get('high_findings') or 0)}."
        )
        for finding in outline_quality.get("findings", [])[:5]:
            if isinstance(finding, dict):
                blockers.append(f"{finding.get('severity', 'finding')}: {finding.get('id')} — {finding.get('title')}")
    elif not has_v3 and outline_quality.get("status") == "warn":
        warnings.append("Page outlines have non-critical findings; review page-outline-quality action plan before writing.")
    missing = []
    if package.get("outline_count") and not has_v3 and not package.get("outline_quality_exists"):
        missing.append(f"{package_dir}/page-outline-quality.json")
    return stage(
        stage_id="deep_page_briefs",
        order=8,
        title="Deep page briefs",
        objective="Every MVP/P1 page has a validated section-level brief with word counts, entities, Answer Units, proof, schema, SEO meta, and no-fabrication guard.",
        evidence=[
            f"page-outlines-v2 json files: {package.get('outline_count', 0)}",
            f"page-outlines-v3 json files: {package.get('outline_v3_count', 0)}",
            f"{package_dir}/page-outline-quality.json: {'exists' if package.get('outline_quality_exists') else 'missing'}",
            f"outline quality status: {outline_quality.get('status', 'not_run')}",
            f"outline 10-point score: {outline_quality.get('ten_point_score', 'n/a')}",
        ],
        missing=missing,
        blockers=blockers,
        warnings=warnings,
        commands=[
            f"python3 ~/.codex/skills/seo-cycle/scripts/page-outline-v2.py {package_dir} --all-mvp --write",
            f"python3 ~/.codex/skills/seo-cycle/scripts/page-outline-v2.py {package_dir} --priority P1 --write",
            f"python3 ~/.codex/skills/seo-cycle/scripts/page-outline-quality.py {package_dir} --write --format markdown",
        ],
        exit_criteria=[
            "MVP/P1 pages have outline v2 files.",
            "page-outline-quality.json exists and has no critical findings.",
            "The generated brief preserves SERP-selected page type, SEO meta/schema/internal links, Answer Units, and forbids fabricated expertise.",
        ],
    )


def brief_stage_v3(package: dict[str, Any]) -> dict[str, Any]:
    package_dir = package.get("package_dir") or "seo/research-package"
    quality = package.get("quality", {})
    outline_quality = package.get("outline_quality", {})
    outline_version = outline_quality.get("outline_version")
    v3_count = int(package.get("outline_v3_count") or 0)
    copywriter_count = int(package.get("copywriter_ready_count") or 0)
    blockers = []
    warnings = []
    if quality.get("status") == "fail":
        blockers.append("Deep copywriter briefs v3 are blocked until research-package-quality has no critical findings.")
    if outline_quality.get("status") == "fail" and outline_version == "v3":
        counts = outline_quality.get("counts") if isinstance(outline_quality.get("counts"), dict) else {}
        blockers.append(
            "Page outline v3 quality gate is fail: "
            f"critical={int(counts.get('critical_findings') or 0)}, high={int(counts.get('high_findings') or 0)}."
        )
        for finding in outline_quality.get("findings", [])[:5]:
            if isinstance(finding, dict):
                blockers.append(f"{finding.get('severity', 'finding')}: {finding.get('id')} — {finding.get('title')}")
    elif outline_quality.get("status") == "warn" and outline_version == "v3":
        blockers.append("Page outline v3 has non-critical findings; improve or explicitly accept them before writing.")
    missing = []
    if not v3_count:
        missing.append(f"{package_dir}/page-outlines-v3/*.json")
    if v3_count and not copywriter_count:
        missing.append(f"{package_dir}/copywriter-ready/*.md")
    if v3_count and (not package.get("outline_quality_exists") or outline_version != "v3"):
        missing.append(f"{package_dir}/page-outline-quality.json")
    return stage(
        stage_id="deep_page_briefs_v3",
        order=9,
        title="Deep copywriter briefs v3",
        objective="Every MVP/P1 page has a copywriter-ready v3 brief with SERP-safe ordering, H2/H3 details, visuals, FAQ guidelines, triplets, and no-fabrication guard.",
        evidence=[
            f"page-outlines-v3 json files: {v3_count}",
            f"copywriter-ready markdown files: {copywriter_count}",
            f"{package_dir}/page-outline-quality.json: {'exists' if package.get('outline_quality_exists') else 'missing'}",
            f"outline quality version: {outline_version or 'not_run'}",
            f"outline quality status: {outline_quality.get('status', 'not_run')}",
            f"outline 10-point score: {outline_quality.get('ten_point_score', 'n/a')}",
        ],
        missing=missing,
        blockers=blockers,
        warnings=warnings,
        commands=[
            f"python3 ~/.codex/skills/seo-cycle/scripts/page-outline-v3.py {package_dir} --all-mvp --write",
            f"python3 ~/.codex/skills/seo-cycle/scripts/page-outline-v3.py {package_dir} --priority P1 --write",
            f"python3 ~/.codex/skills/seo-cycle/scripts/page-outline-quality.py {package_dir} --version v3 --write --format markdown",
        ],
        exit_criteria=[
            "MVP/P1 pages have page-outline-v3 JSON/Markdown files.",
            "copywriter-ready markdown exists for generated v3 pages.",
            "page-outline-quality.json has outline_version=v3 and status=pass.",
            "Tool/app pages preserve tool UX above supporting longform content.",
        ],
    )


def content_draft_stage(package: dict[str, Any]) -> dict[str, Any]:
    package_dir = package.get("package_dir") or "seo/research-package"
    outline_quality = package.get("outline_quality", {})
    outline_version = outline_quality.get("outline_version")
    outline_status = outline_quality.get("status", "not_run")
    v3_count = int(package.get("outline_v3_count") or 0)
    copywriter_count = int(package.get("copywriter_ready_count") or 0)
    draft_count = int(package.get("draft_count") or 0)
    draft_quality_count = int(package.get("draft_quality_count") or 0)
    draft_quality_errors = int(package.get("draft_quality_errors") or 0)
    draft_quality_warnings = int(package.get("draft_quality_warnings") or 0)
    blockers = []
    warnings = []
    missing = []

    if not v3_count:
        blockers.append("Content drafting is blocked until page-outline-v3 files exist.")
    if not copywriter_count:
        blockers.append("Content drafting is blocked until copywriter-ready markdown exists.")
    if outline_version != "v3" or outline_status != "pass":
        blockers.append(
            "Content drafting is blocked until page-outline-quality.json has outline_version=v3 and status=pass."
        )
    if not draft_count:
        missing.append(f"{package_dir}/drafts/*.md")
    else:
        missing.extend(package.get("draft_quality_missing", []))
    if draft_quality_errors:
        blockers.append(f"Draft quality gate has {draft_quality_errors} error/critical findings.")
        for finding in package.get("draft_quality_findings", [])[:8]:
            if isinstance(finding, dict) and finding.get("severity") in {"error", "critical"}:
                blockers.append(
                    f"{finding.get('severity')}: {finding.get('id')} — {finding.get('message')} ({finding.get('draft')})"
                )
    if draft_quality_warnings:
        warnings.append(f"Draft quality gate has {draft_quality_warnings} warning findings to review before publishing.")

    evidence = [
        f"page-outlines-v3 json files: {v3_count}",
        f"copywriter-ready markdown files: {copywriter_count}",
        f"outline quality version/status: {outline_version or 'not_run'}/{outline_status}",
        f"draft markdown files: {draft_count}",
        f"draft quality reports: {draft_quality_count}",
        f"draft quality errors: {draft_quality_errors}",
        f"draft quality warnings: {draft_quality_warnings}",
    ]
    draft_loop = (package.get("loops") or {}).get("draft")
    draft_loop_line = loop_evidence_line(draft_loop)
    if draft_loop_line:
        evidence.append(draft_loop_line)
    if draft_loop and draft_loop.get("status") == "escalated":
        blockers.append(
            f"Draft quality loop escalated after {draft_loop.get('attempts_used')} attempts"
            f" (ticket {draft_loop.get('escalation_ticket') or 'n/a'}) — review {draft_loop.get('state_file')}."
        )

    return stage(
        stage_id="content_draft_gate",
        order=10,
        title="Content draft and NeuronWriter gate",
        objective=(
            "Turn copywriter-ready v3 briefs into drafts, optionally use NeuronWriter within limits, "
            "then validate drafts before implementation or publishing."
        ),
        evidence=evidence,
        missing=missing,
        blockers=blockers,
        warnings=warnings,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py check --service neuronwriter --category paid_api --content-writer 1 --ai-credits 500 --fail-on-block",
            "python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py check --service neuronwriter --category paid_api --plagiarism-checks 1 --fail-on-block",
            f"Create or revise draft markdown under {package_dir}/drafts/ from {package_dir}/copywriter-ready/*.md, copywriting_playbook, writer_prompt_packet and source slots.",
            f"python3 ~/.codex/skills/seo-cycle/scripts/loop-runner.py draft {package_dir}/drafts/<slug>.md --outline {package_dir}/page-outlines-v3/<slug>.json",
            "bash ~/.codex/skills/seo-cycle/scripts/nw-cli.sh evaluate <query_id> <draft.html>",
            "bash ~/.codex/skills/seo-cycle/scripts/nw-cli.sh plagiarism <query_id> <draft.html>",
            "python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py record --service neuronwriter --category paid_api --plagiarism-checks 1 --task \"final plagiarism check\" --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/project-journey.py --write",
        ],
        exit_criteria=[
            "Draft markdown exists for the selected MVP/P1 page.",
            "draft-quality-gate JSON exists next to each draft.",
            "Draft quality gate has 0 error/critical findings.",
            "NeuronWriter usage is checked/recorded when it is used; if unavailable, fallback drafting/checking is explicitly logged.",
            "Final commercial/blog drafts pass the configured plagiarism check or carry an approved manual fallback note.",
            "The next project-journey run marks this stage done before implementation/publishing.",
        ],
    )


def implementation_stage(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    launch = json_summary(artifact_path(cfg, project_root, "latest_launch_plan", "seo/setup/latest-launch-plan.json"))
    gates = launch.get("approval_gates", []) if isinstance(launch.get("approval_gates"), list) else []
    warnings = [f"Approval gates still apply before publish/index/ads/tracking: {', '.join(gates)}"] if gates else []
    return stage(
        stage_id="implementation_review",
        order=11,
        title="Implementation and publication review",
        objective="Approved content/technical changes are implemented only after final review and project-specific gates.",
        evidence=[f"approval gates: {', '.join(gates) or 'none'}"],
        warnings=warnings,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/task-router.py --task \"implement approved SEO changes\" --write",
            "Run final Codex review before WordPress REST/API publishing or code changes.",
        ],
        exit_criteria=[
            "Only approved changes are applied.",
            "Publishing, index submission, tracking, ads, or paid API calls have explicit approval.",
        ],
    )


def monitoring_stage(cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    checks = [
        ("latest_usage_report", "seo/setup/latest-usage-ledger.md"),
        ("growth_roadmap_report", "seo/setup/growth-roadmap.md"),
        ("automation_recommendations", "seo/automations/automation-recommendations.md"),
    ]
    evidence = []
    missing = []
    for key, default in checks:
        path, exists = artifact_exists(cfg, project_root, key, default)
        evidence.append(f"{path}: {'exists' if exists else 'missing'}")
        if not exists:
            missing.append(path)
    return stage(
        stage_id="monitoring_iteration",
        order=12,
        title="Monitoring and iteration",
        objective="After launch, measurement, bot/index health, AI visibility, and refresh tasks feed the next cycle.",
        evidence=evidence,
        missing=missing,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py report --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/growth-roadmap.py --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/automation-recommender.py --write",
        ],
        exit_criteria=[
            "Monitoring sources and next refresh cadence are defined.",
            "Automation remains report-only unless policy allows schedules.",
        ],
    )


def assign_status(stages: list[dict[str, Any]]) -> None:
    first_open = None
    for item in stages:
        if item["missing_artifacts"] or item["blockers"]:
            first_open = item
            break
        item["status"] = "done"
    if first_open is None:
        return
    first_open["status"] = "blocked" if first_open["blockers"] else "current"
    for item in stages:
        if item["order"] > first_open["order"]:
            item["status"] = "pending"


def build_action_plan(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current = next((item for item in stages if item["status"] in {"current", "blocked"}), None)
    if current is None:
        return [
            {
                "step": 1,
                "priority": "P0-final",
                "stage": "monitoring_iteration",
                "action": "Project journey is complete for this cycle; start monitoring and next refresh.",
                "command": "python3 ~/.codex/skills/seo-cycle/scripts/growth-roadmap.py --write",
                "done": "Next cycle target is selected from monitored evidence.",
            }
        ]
    plan = [
        {
            "step": 1,
            "priority": "P0-current",
            "stage": current["id"],
            "action": f"Work only on current stage: {current['title']}.",
            "command": current["next_commands"][0] if current["next_commands"] else "Review current stage blockers.",
            "done": "; ".join(current["exit_criteria"]) or "Current stage has no missing artifacts or blockers.",
        }
    ]
    for idx, command in enumerate(current.get("next_commands", [])[1:4], start=2):
        plan.append(
            {
                "step": idx,
                "priority": f"P1-{idx:02d}",
                "stage": current["id"],
                "action": "Follow-up command for the same stage.",
                "command": command,
                "done": "Command output is reviewed and missing/blocking items are reduced.",
            }
        )
    plan.append(
        {
            "step": len(plan) + 1,
            "priority": "P0-verify",
            "stage": current["id"],
            "action": "Rerun project journey before moving forward.",
            "command": "python3 ~/.codex/skills/seo-cycle/scripts/project-journey.py --write",
            "done": "The current stage becomes done and the next stage is shown.",
        }
    )
    return plan


def build_report(cfg_path: pathlib.Path, *, goal: str, research_package: str | None = None) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    package = package_state(project_root, detect_research_package(project_root, research_package))
    stages = [
        setup_stage(cfg, project_root),
        governance_stage(cfg, project_root),
        evidence_stage(cfg, project_root),
        technical_stage(cfg, project_root),
        research_stage(project_root, package),
        quality_stage(package),
        repair_stage(package),
        brief_stage(package),
        brief_stage_v3(package),
        content_draft_stage(package),
        implementation_stage(cfg, project_root),
        monitoring_stage(cfg, project_root),
    ]
    assign_status(stages)
    current = next((item for item in stages if item["status"] in {"current", "blocked"}), None)
    done_count = sum(1 for item in stages if item["status"] == "done")
    status = "ready" if current is None else "blocked" if current["status"] == "blocked" else "needs_work"
    report = {
        "audit_id": "project_journey",
        "version": 2,
        "generated": utc_now(),
        "goal": goal,
        "status": status,
        "journey_score": round(done_count / len(stages) * 10, 1),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "research_package": package,
        "current_stage": current,
        "next_stage": next((item for item in stages if item["order"] == (current or {}).get("order", len(stages)) + 1), None)
        if current
        else None,
        "missing_for_next_step": (current or {}).get("missing_artifacts", []) + (current or {}).get("blockers", []),
        "stages": stages,
        "scorecards": load_scorecards(project_root),
        "action_plan": build_action_plan(stages),
        "rules": [
            "Do not skip a blocked/current stage just because a later artifact exists.",
            "Use distillates and generated reports as context; keep raw CSV/JSON/logs on disk.",
            "Publishing, indexing, tracking, ads, paid API, and schedules require explicit approval gates.",
            "Research package quality must pass before deep briefs can drive content production.",
            "Content drafting must use copywriter-ready v3 outputs and pass draft-quality-gate before implementation or publishing.",
            "NeuronWriter is optional and guarded: check usage limits before use, then record spend/credits after use.",
        ],
        "paths": {},
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    current = report.get("current_stage") or {}
    lines = [
        "# seo-cycle project journey",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Goal: {report.get('goal')}",
        f"- Status: `{report.get('status')}`",
        f"- Journey score: `{report.get('journey_score')}/10`",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Current stage: `{current.get('id', 'complete')}` {current.get('title', '')}",
        "",
        "## What Is Missing Now",
    ]
    missing = report.get("missing_for_next_step", [])
    if missing:
        lines.extend(f"- {item}" for item in missing)
    else:
        lines.append("- Nothing is blocking the next stage in this cycle.")
    lines.extend(["", "## Automatic Action Plan"])
    for item in report.get("action_plan", []):
        lines.extend(
            [
                f"### Step {item['step']}: {item['action']}",
                "",
                f"- Priority: `{item['priority']}`",
                f"- Stage: `{item['stage']}`",
                f"- Command: {item['command']}",
                f"- Done: {item['done']}",
                "",
            ]
        )
    lines.extend(["", "## Journey Stages", "| # | Stage | Status | Missing | Blockers | Next command |", "| --- | --- | --- | --- | --- | --- |"])
    for item in report.get("stages", []):
        missing_count = len(item.get("missing_artifacts", []))
        blocker_count = len(item.get("blockers", []))
        command = item.get("next_commands", [""])[0] if item.get("next_commands") else ""
        lines.append(f"| {item['order']} | {item['title']} | `{item['status']}` | {missing_count} | {blocker_count} | `{command}` |")
    lines.extend(["", "## Stage Details"])
    for item in report.get("stages", []):
        lines.extend([f"### {item['order']}. {item['title']}", "", f"- Status: `{item['status']}`", f"- Objective: {item['objective']}"])
        if item.get("evidence"):
            lines.append("- Evidence:")
            lines.extend(f"  - {value}" for value in item["evidence"])
        if item.get("missing_artifacts"):
            lines.append("- Missing:")
            lines.extend(f"  - {value}" for value in item["missing_artifacts"])
        if item.get("blockers"):
            lines.append("- Blockers:")
            lines.extend(f"  - {value}" for value in item["blockers"])
        if item.get("warnings"):
            lines.append("- Warnings:")
            lines.extend(f"  - {value}" for value in item["warnings"])
        if item.get("exit_criteria"):
            lines.append("- Exit criteria:")
            lines.extend(f"  - {value}" for value in item["exit_criteria"])
        lines.append("")
    lines.extend(["## Самооценки последних запусков", "", render_scorecards_markdown(report.get("scorecards", {}), limit=10)])
    lines.extend(["## Rules"])
    lines.extend(f"- {rule}" for rule in report.get("rules", []))
    return "\n".join(lines) + "\n"


def checklist_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    fields = ["order", "stage", "status", "missing_count", "blocker_count", "first_command", "exit_criteria"]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for item in report.get("stages", []):
        writer.writerow(
            {
                "order": item.get("order"),
                "stage": item.get("id"),
                "status": item.get("status"),
                "missing_count": len(item.get("missing_artifacts", [])),
                "blocker_count": len(item.get("blockers", [])),
                "first_command": (item.get("next_commands") or [""])[0],
                "exit_criteria": " | ".join(item.get("exit_criteria", [])),
            }
        )
    return buffer.getvalue()


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    setup_dir = project_root / "seo" / "setup"
    paths = {
        "markdown": setup_dir / "project-journey.md",
        "json": setup_dir / "project-journey.json",
        "checklist": setup_dir / "project-journey-checklist.csv",
        "latest_markdown": setup_dir / "latest-project-journey.md",
        "latest_json": setup_dir / "latest-project-journey.json",
    }
    report["paths"] = {key: str(path) for key, path in paths.items()}
    markdown = render_markdown(report)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    write_text(paths["markdown"], markdown)
    write_text(paths["json"], json_text)
    write_text(paths["checklist"], checklist_csv(report))
    write_text(paths["latest_markdown"], markdown)
    write_text(paths["latest_json"], json_text)
    return paths["markdown"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show the current seo-cycle stage and what is missing before the next step.")
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--goal", default="complete the next safe SEO cycle", help="Human-readable target goal for the journey.")
    parser.add_argument("--research-package", help="Optional research package directory or file.")
    parser.add_argument("--write", action="store_true", help="Write seo/setup/project-journey artifacts.")
    parser.add_argument("--fail-on-blocker", action="store_true", help="Exit 1 when the current journey stage is blocked.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args(argv)

    if args.config:
        cfg_path = pathlib.Path(args.config).expanduser().resolve()
    else:
        found = find_config(pathlib.Path.cwd())
        if not found:
            print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        cfg_path = found.resolve()
    if not cfg_path.exists():
        print(f"ERROR: {cfg_path} not found", file=sys.stderr)
        return 2

    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("project-journey", project_root, load_yaml(cfg_path))
    report = build_report(cfg_path, goal=args.goal, research_package=args.research_package)
    log.info("journey stage=%s status=%s", (report.get("current_stage") or {}).get("id"), report.get("status"))
    if args.write:
        write_outputs(project_root, report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 1 if args.fail_on_blocker and report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
