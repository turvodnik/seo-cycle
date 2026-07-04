#!/usr/bin/env python3
"""Audit SEO research packages before they become content/implementation briefs.

The audit is intentionally read-only unless --write is passed. It checks the
failure modes found when comparing site-level research packages with deep
single-page outlines: SERP validation gaps, URL drift after reclustering,
dirty GSC rows, duplicate/shallow briefs, orphan URLs, decorative NLP output,
entity map drift, and unused AI Overview/GEO signals.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import pathlib
import re
from collections import Counter
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from seo_cycle_core.config import nested_get, package_project_root, write_text
from research_package_repair_core import repeated_phrase_clean


REQUIRED_FILES = (
    "semantic-core.csv",
    "content-plan.csv",
    "final-clusters.md",
    "semantic-architecture-final.json",
    "entity-map.md",
    "entity-map.yaml",
)

SUSPICIOUS_QUERY_RE = re.compile(
    r"\b(create|generate|draw|make|prompt|midjourney|stable diffusion|"
    r"using this portrait|side[- ]by[- ]side|image generation|chatgpt)\b",
    re.IGNORECASE,
)

GEO_TERMS_RE = re.compile(r"(ai overview|geo|answer[- ]first|citability|answer unit|llms\.txt)", re.IGNORECASE)
EEAT_TERMS_RE = re.compile(
    r"(e-e-a-t|eeat|expert|author|reviewed|credential|source|citation|evidence|"
    r"schema|organization|person|privacy|trust|license|certificate)",
    re.IGNORECASE,
)

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}
SEVERITY_PENALTY = {"critical": 4, "high": 3, "medium": 2, "low": 1}

QUALITY_CRITERIA = (
    {"id": "structure_architecture", "label": "Structure and architecture"},
    {"id": "keyword_universe", "label": "Keyword universe and cleanliness"},
    {"id": "serp_intent_validation", "label": "SERP and intent validation"},
    {"id": "clustering_url_mapping", "label": "Cluster and URL mapping"},
    {"id": "entity_semantic_coverage", "label": "Entity and semantic coverage"},
    {"id": "content_brief_depth", "label": "Copywriter-ready brief depth"},
    {"id": "eeat_evidence", "label": "E-E-A-T and proof layer"},
    {"id": "geo_ai_citability", "label": "GEO/AEO/AI citability"},
    {"id": "technical_implementation", "label": "Technical implementation readiness"},
    {"id": "consistency_handoff", "label": "Internal consistency and handoff"},
)

FINDING_CRITERIA = {
    "missing_required_artifacts": ("structure_architecture", "technical_implementation", "consistency_handoff"),
    "required_research_source_missing": ("serp_intent_validation", "eeat_evidence", "geo_ai_citability", "consistency_handoff"),
    "serp_validation_incomplete": ("serp_intent_validation", "clustering_url_mapping"),
    "semantic_core_url_drift": ("clustering_url_mapping", "technical_implementation", "consistency_handoff"),
    "dirty_semantic_core_queries": ("keyword_universe", "consistency_handoff"),
    "duplicate_page_briefs": ("content_brief_depth", "consistency_handoff"),
    "orphan_internal_urls": ("structure_architecture", "technical_implementation", "consistency_handoff"),
    "entity_map_md_yaml_drift": ("entity_semantic_coverage", "consistency_handoff"),
    "google_nlp_not_aggregated": ("entity_semantic_coverage",),
    "ai_overview_signals_unused": ("geo_ai_citability", "content_brief_depth"),
    "page_briefs_too_shallow": ("content_brief_depth", "geo_ai_citability", "eeat_evidence"),
    "eeat_evidence_missing": ("eeat_evidence", "geo_ai_citability", "content_brief_depth"),
}

REMEDIATION_HINTS = {
    "missing_required_artifacts": {
        "mode": "source_refresh",
        "target_files": list(REQUIRED_FILES),
        "command": "Restore/regenerate the missing package artifacts, then rerun research-package-quality.py --write.",
        "definition_of_done": "Every required artifact exists and can be parsed before downstream briefs are generated.",
    },
    "required_research_source_missing": {
        "mode": "source_refresh",
        "target_files": ["seo/research/distillates/", "seo/research/llm-cli/results/"],
        "command": "Run the required source collectors, cache/distill the results, then rerun research-package-quality.py --write.",
        "definition_of_done": "Every project-required research source has a non-empty ready artifact before downstream writing starts.",
    },
    "serp_validation_incomplete": {
        "mode": "source_refresh",
        "target_files": ["serp-validation-plan.csv", "serp-validation-import.md", "semantic-architecture-final.json"],
        "command": "serp-validation-plan.py <package> --write; then serp-validation-import.py <package> --input-json <reviewed-serp-export.json> --write",
        "definition_of_done": "serp-validation-plan.csv lists every missing query/provider/region/device/page-type decision field; reviewed SERP export is imported and semantic-architecture-final.json contains non-empty validation.",
    },
    "semantic_core_url_drift": {
        "mode": "agent_fix",
        "target_files": ["semantic-core.resynced.csv", "semantic-architecture-final.json"],
        "command": "semantic-core-resync.py <package> --write",
        "definition_of_done": "semantic-core.resynced.csv maps old cluster IDs/URLs to final architecture IDs/URLs.",
    },
    "dirty_semantic_core_queries": {
        "mode": "agent_fix",
        "target_files": ["semantic-core.cleaned.csv", "semantic-core.rejected.csv"],
        "command": "semantic-core-clean.py <package> --write",
        "definition_of_done": "semantic-core.cleaned.csv contains search queries and semantic-core.rejected.csv explains removed prompt/spam rows.",
    },
    "duplicate_page_briefs": {
        "mode": "agent_fix",
        "target_files": ["page-briefs.md", "mvp-page-briefs.md"],
        "command": "Use page-outline-v2.py --all-mvp --write to create deeper MVP briefs; keep page-briefs as the backlog summary.",
        "definition_of_done": "MVP briefs differ from generic backlog briefs and contain section-level instructions.",
    },
    "orphan_internal_urls": {
        "mode": "manual_decision",
        "target_files": ["content-plan.orphan-backlog.csv", "content-plan.csv", "site-structure.md", "semantic-architecture-final.json"],
        "command": "orphan-url-resolver.py <package> --write",
        "definition_of_done": "content-plan.orphan-backlog.csv lists create/remove decisions for every referenced URL without a planned page.",
    },
    "entity_map_md_yaml_drift": {
        "mode": "agent_fix",
        "target_files": ["entity-map.md", "entity-map.yaml"],
        "command": "entity-map-sync.py <package> --write",
        "definition_of_done": "Markdown and YAML expose the same priority entities and attributes.",
    },
    "google_nlp_not_aggregated": {
        "mode": "agent_fix",
        "target_files": ["entity_coverage.jsonl", "semantic-architecture-final.json", "entity-map.yaml"],
        "command": "google-nlp-aggregate.py <package> --write",
        "definition_of_done": "entity_coverage.jsonl contains deduplicated entities with mentions, variants, salience sums/averages and type counts.",
    },
    "ai_overview_signals_unused": {
        "mode": "agent_fix",
        "target_files": ["page-briefs.md", "mvp-page-briefs.md"],
        "command": "Add answer-first blocks, proof blocks, and synthetic AI prompts for rows with AI Overview features.",
        "definition_of_done": "AI Overview signals are translated into GEO/AEO requirements in affected briefs.",
    },
    "page_briefs_too_shallow": {
        "mode": "agent_fix",
        "target_files": ["page-outlines-v2/"],
        "command": "Run page-outline-v2.py --all-mvp --write and review every generated outline before writing.",
        "definition_of_done": "Each MVP/P1 page has H2/H3 guidance, word counts, entities, visuals, proof, schema, and no-fabrication notes.",
    },
    "eeat_evidence_missing": {
        "mode": "manual_decision",
        "target_files": ["technical-spec.md", "page-briefs.md", "mvp-page-briefs.md", "entity-map.md"],
        "command": "Add an evidence map: authors, review policy, sources, schemas, trust assets, privacy/safety limits, and citation rules.",
        "definition_of_done": "Briefs define which claims need proof and where that proof must come from.",
    },
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_package(raw: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(raw).expanduser().resolve()
    if path.is_file():
        return path.parent
    return path


def read_csv(path: pathlib.Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_json_error": True}
    return data if isinstance(data, dict) else {"items": data}


def read_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists() or yaml is None:
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {"_yaml_error": True}
    return data if isinstance(data, dict) else {}


project_root_for_package = package_project_root


def normalize_required_sources(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        items = []
        for source_id, value in raw.items():
            if isinstance(value, dict):
                item = {"id": source_id, **value}
            else:
                item = {"id": source_id, "path": value}
            items.append(item)
        return items
    if isinstance(raw, list):
        items = []
        for value in raw:
            if isinstance(value, dict):
                items.append(value)
            else:
                items.append({"id": str(value)})
        return items
    return []


def source_status_value(data: dict[str, Any], field: str | None) -> Any:
    if not field:
        return None
    return nested_get(data, field, data.get(field))


def check_required_research_sources(project_root: pathlib.Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    required = normalize_required_sources(nested_get(cfg, "quality_gates.required_research_sources", []))
    for source in required:
        source_id = str(source.get("id") or "unnamed_source")
        min_bytes = int(source.get("min_bytes") or 100)
        mode = str(source.get("mode") or "all").lower()
        required_status = source.get("required_status")
        status_field = source.get("status_field")
        raw_paths: list[str] = []
        if source.get("path"):
            raw_paths.append(str(source["path"]))
        if isinstance(source.get("paths"), list):
            raw_paths.extend(str(path) for path in source["paths"])
        matched_paths: list[pathlib.Path] = []
        for raw_path in raw_paths:
            matched_paths.append((project_root / raw_path).resolve())
        if source.get("glob"):
            matched_paths.extend(sorted(project_root.glob(str(source["glob"]))))
        if not matched_paths:
            missing.append({"source": source_id, "reason": "no_paths_configured", "expected": source})
            continue

        checks = []
        for path in matched_paths:
            item: dict[str, Any] = {"path": str(path)}
            if not path.exists():
                item["ok"] = False
                item["reason"] = "missing"
            elif path.is_file() and path.stat().st_size < min_bytes:
                item["ok"] = False
                item["reason"] = "too_small"
                item["bytes"] = path.stat().st_size
            else:
                item["ok"] = True
                item["bytes"] = path.stat().st_size if path.is_file() else None
                if required_status and path.suffix.lower() == ".json":
                    value = source_status_value(read_json(path), str(status_field or "status"))
                    item["status"] = value
                    if value != required_status:
                        item["ok"] = False
                        item["reason"] = "status_mismatch"
                        item["required_status"] = required_status
            checks.append(item)

        ok_count = sum(1 for item in checks if item.get("ok"))
        source_ok = ok_count >= 1 if mode == "any" else ok_count == len(checks)
        if not source_ok:
            missing.append(
                {
                    "source": source_id,
                    "mode": mode,
                    "required_status": required_status,
                    "checks": checks[:20],
                }
            )
    return missing


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", "_", str(value or "").strip().lower(), flags=re.IGNORECASE).strip("_")


def compact_hash(path: pathlib.Path) -> str:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    compact = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def is_empty_serp(record: Any) -> bool:
    if not isinstance(record, dict):
        return True
    keys = ("features", "top_urls", "top_titles", "items", "organic_results")
    return all(not record.get(key) for key in keys)


def add_finding(findings: list[dict[str, Any]], *, finding_id: str, severity: str, title: str, evidence: Any, action: str) -> None:
    findings.append(
        {
            "id": finding_id,
            "severity": severity,
            "title": title,
            "evidence": evidence,
            "recommended_action": action,
        }
    )


def planned_urls(content_rows: list[dict[str, str]], clusters: list[dict[str, Any]]) -> set[str]:
    urls: set[str] = set()
    for row in content_rows:
        url = (row.get("url") or row.get("suggested_url") or "").strip()
        if url:
            urls.add(url)
    for cluster in clusters:
        url = (cluster.get("suggested_url") or cluster.get("url") or "").strip()
        if url:
            urls.add(url)
    return urls


def referenced_urls(clusters: list[dict[str, Any]], site_structure: str) -> set[str]:
    urls: set[str] = set()
    for cluster in clusters:
        links = cluster.get("internal_links") or []
        if isinstance(links, str):
            links = [part.strip() for part in links.split("|")]
        for link in links:
            if isinstance(link, str) and link.startswith("/"):
                urls.add(link.strip())
    for match in re.finditer(r"`(/[^`]+/)`|URL:\s*`?(/[^`\s]+/)", site_structure):
        urls.add(next(group for group in match.groups() if group))
    for match in re.finditer(r"(/(?:tools|hair-color|hairstyles|guides)/[a-z0-9\-/]+/)", site_structure):
        urls.add(match.group(1))
    return urls


def parse_md_entity_attributes(markdown: str) -> dict[str, set[str]]:
    entities: dict[str, set[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            current = norm(heading.group(1))
            entities.setdefault(current, set())
            continue
        if current and line.strip().lower().startswith("- attributes:"):
            raw = line.split(":", 1)[1]
            entities[current].update(norm(part) for part in raw.split(",") if norm(part))
    return entities


def yaml_entity_attributes(data: dict[str, Any]) -> dict[str, set[str]]:
    raw_entities = data.get("entities")
    if isinstance(raw_entities, dict):
        iterable = raw_entities.values()
    elif isinstance(raw_entities, list):
        iterable = raw_entities
    else:
        iterable = []
    result: dict[str, set[str]] = {}
    for item in iterable:
        if not isinstance(item, dict):
            continue
        name = norm(item.get("name") or item.get("id") or item.get("entity"))
        attrs = item.get("attributes") or []
        if isinstance(attrs, str):
            attrs = [part.strip() for part in attrs.split(",")]
        result[name] = {norm(attr) for attr in attrs if norm(attr)}
    return result


def scorecard_from_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scores = {criterion["id"]: 10 for criterion in QUALITY_CRITERIA}
    blocking: dict[str, list[str]] = {criterion["id"]: [] for criterion in QUALITY_CRITERIA}
    for finding in findings:
        penalty = SEVERITY_PENALTY.get(str(finding.get("severity")), 1)
        for criterion_id in FINDING_CRITERIA.get(str(finding.get("id")), ("consistency_handoff",)):
            scores[criterion_id] = max(0, scores[criterion_id] - penalty)
            blocking[criterion_id].append(str(finding.get("id")))
    result = []
    for criterion in QUALITY_CRITERIA:
        score = scores[criterion["id"]]
        result.append(
            {
                "id": criterion["id"],
                "label": criterion["label"],
                "score": score,
                "status": "excellent" if score == 10 else "needs_work" if score < 9 else "review",
                "blocking_findings": sorted(set(blocking[criterion["id"]])),
            }
        )
    return result


def remediation_plan_from_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = []
    for index, finding in enumerate(findings, start=1):
        hint = REMEDIATION_HINTS.get(str(finding.get("id")), {})
        severity = str(finding.get("severity", "medium"))
        priority_prefix = {"critical": "P0", "high": "P1", "medium": "P2", "low": "P3"}.get(severity, "P2")
        plan.append(
            {
                "step": index,
                "priority": f"{priority_prefix}-{index:02d}",
                "finding_id": finding.get("id"),
                "severity": severity,
                "title": finding.get("title"),
                "mode": hint.get("mode", "manual_review"),
                "target_files": hint.get("target_files", []),
                "command": hint.get("command", finding.get("recommended_action")),
                "definition_of_done": hint.get("definition_of_done", finding.get("recommended_action")),
            }
        )
    return plan


def launch_action_plan(report: dict[str, Any]) -> list[dict[str, Any]]:
    if not report["findings"]:
        source_lock_gate = report.get("source_lock_gate") if isinstance(report.get("source_lock_gate"), dict) else {}
        if source_lock_gate.get("status") == "required_before_final_draft":
            plan_path = source_lock_gate.get("plan") or "<package>/source-lock-plan.md"
            queue_path = source_lock_gate.get("queue") or "<package>/source-lock-queue.csv"
            return [
                {
                    "step": 1,
                    "priority": "P0-01",
                    "action": "Complete source-lock before final drafting.",
                    "command": f"Review {queue_path}; resolve claims using {plan_path}; rerun research-package-quality.py <package> --write",
                    "definition_of_done": "Every P0/P1 technical or numeric claim is verified, softened, or removed before draft-quality-gate/NeuronWriter/plagiarism checks.",
                },
                {
                    "step": 2,
                    "priority": "P0-02",
                    "action": "Refresh content/page production artifacts after source-lock decisions.",
                    "command": "page-outline-v3.py <package> --all-mvp --write && page-outline-quality.py <package> --version v3 --write",
                    "definition_of_done": "Every MVP page has a generated v3 outline, copywriter-ready brief, and passing v3 outline quality gate before drafting.",
                },
            ]
        return [
            {
                "step": 1,
                "priority": "P0-01",
                "action": "Proceed to content/page production.",
                "command": "page-outline-v3.py <package> --all-mvp --write && page-outline-quality.py <package> --version v3 --write",
                "definition_of_done": "Every MVP page has a generated v3 outline, copywriter-ready brief, and passing v3 outline quality gate before drafting.",
            }
        ]

    actions = [
        {
            "step": 1,
            "priority": "P0-01",
            "action": "Stop downstream writing/publishing for this package.",
            "command": "Do not publish or generate final content until all critical findings are resolved.",
            "definition_of_done": "Critical findings count is 0.",
        }
    ]
    repairable = {
        "serp_validation_incomplete",
        "semantic_core_url_drift",
        "dirty_semantic_core_queries",
        "orphan_internal_urls",
        "entity_map_md_yaml_drift",
        "google_nlp_not_aggregated",
    }
    if any(item.get("id") in repairable for item in report["findings"]):
        actions.append(
            {
                "step": len(actions) + 1,
                "priority": "P0-02",
                "action": "Run the research package repair layer.",
                "command": "research-package-repair.py <package> --write",
                "definition_of_done": "Repair report has 0 failed steps and generated cleaned/resynced/backlog/SERP/entity artifacts.",
            }
        )
    for item in report["remediation_plan"][:10]:
        actions.append(
            {
                "step": len(actions) + 1,
                "priority": item["priority"],
                "action": item["title"],
                "command": item["command"],
                "definition_of_done": item["definition_of_done"],
            }
        )
    actions.append(
        {
            "step": len(actions) + 1,
            "priority": "P0-final",
            "action": "Rerun quality gate and only proceed when the scorecard is clean.",
            "command": "research-package-quality.py <package> --write --format markdown",
            "definition_of_done": "Status is pass/warn by policy, no critical findings, and every scorecard criterion is 9+.",
        }
    )
    return actions


def audit_package(package_dir: pathlib.Path) -> dict[str, Any]:
    package_dir = resolve_package(package_dir)
    project_root = project_root_for_package(package_dir)
    project_cfg = read_yaml(project_root / "seo-cycle.yaml")
    architecture = read_json(package_dir / "semantic-architecture-final.json")
    semantic_rows, semantic_fields = read_csv(package_dir / "semantic-core.csv")
    content_rows, content_fields = read_csv(package_dir / "content-plan.csv")
    dataforseo_rows, dataforseo_fields = read_csv(package_dir / "dataforseo-keyword-expansion.csv")
    entity_yaml = read_yaml(package_dir / "entity-map.yaml")
    entity_md = (package_dir / "entity-map.md").read_text(encoding="utf-8") if (package_dir / "entity-map.md").exists() else ""
    site_structure = (package_dir / "site-structure.md").read_text(encoding="utf-8") if (package_dir / "site-structure.md").exists() else ""
    technical_spec = (package_dir / "technical-spec.md").read_text(encoding="utf-8") if (package_dir / "technical-spec.md").exists() else ""
    page_briefs = (package_dir / "page-briefs.md").read_text(encoding="utf-8") if (package_dir / "page-briefs.md").exists() else ""
    mvp_briefs = (package_dir / "mvp-page-briefs.md").read_text(encoding="utf-8") if (package_dir / "mvp-page-briefs.md").exists() else ""

    findings: list[dict[str, Any]] = []
    clusters = architecture.get("clusters") if isinstance(architecture.get("clusters"), list) else []

    missing = [name for name in REQUIRED_FILES if not (package_dir / name).exists()]
    if missing:
        add_finding(
            findings,
            finding_id="missing_required_artifacts",
            severity="critical",
            title="Research package is missing required artifacts.",
            evidence=missing,
            action="Regenerate or restore the missing CSV/JSON/MD/YAML files before handoff.",
        )

    missing_required_sources = check_required_research_sources(project_root, project_cfg)
    if missing_required_sources:
        add_finding(
            findings,
            finding_id="required_research_source_missing",
            severity="critical",
            title="Project-required research sources are missing or not ready.",
            evidence={"sources": missing_required_sources[:20]},
            action="Run the mandatory source collectors, write raw/distillate artifacts, and rerun the package gate before content drafting.",
        )

    serp = architecture.get("dataforseo_serp_validation") or {}
    expected_serp = []
    metadata = architecture.get("metadata") if isinstance(architecture.get("metadata"), dict) else {}
    sources = metadata.get("sources") if isinstance(metadata.get("sources"), dict) else {}
    expected_serp.extend(sources.get("dataforseo_serp_validation_keywords") or [])
    expected_serp.extend(cluster.get("primary_keyword") for cluster in clusters if cluster.get("mvp"))
    expected_serp = [str(item) for item in dict.fromkeys(item for item in expected_serp if item)]
    empty_serp = []
    if isinstance(serp, dict):
        for keyword in expected_serp:
            if keyword not in serp or is_empty_serp(serp.get(keyword)):
                empty_serp.append(keyword)
    elif expected_serp:
        empty_serp = expected_serp
    if empty_serp:
        add_finding(
            findings,
            finding_id="serp_validation_incomplete",
            severity="critical",
            title="SERP validation is empty for one or more checked/MVP keywords.",
            evidence={"empty_keywords": empty_serp[:20], "empty_count": len(empty_serp), "expected_count": len(expected_serp)},
            action="Fail the quality gate and rerun DataForSEO/SERP validation before choosing page type or MVP scope.",
        )

    cluster_url_by_id = {
        norm(cluster.get("id")): (cluster.get("suggested_url") or cluster.get("url") or "")
        for cluster in clusters
        if isinstance(cluster, dict)
    }
    url_mismatches = []
    for row in semantic_rows:
        cluster_id = norm(row.get("base_cluster") or row.get("cluster_id") or row.get("cluster") or row.get("source_cluster"))
        expected = cluster_url_by_id.get(cluster_id)
        actual = (row.get("suggested_url") or row.get("url") or "").strip()
        if expected and actual and expected != actual:
            url_mismatches.append({"keyword": row.get("keyword"), "cluster": cluster_id, "semantic_url": actual, "final_url": expected})
    if url_mismatches:
        add_finding(
            findings,
            finding_id="semantic_core_url_drift",
            severity="critical",
            title="Semantic core URLs drifted from final cluster URLs.",
            evidence={"mismatch_count": len(url_mismatches), "examples": url_mismatches[:10]},
            action="After reclustering, rewrite semantic-core.csv suggested_url and cluster IDs from the final architecture.",
        )

    dirty_keywords = []
    for idx, row in enumerate(semantic_rows, start=2):
        keyword = row.get("keyword") or ""
        if len(keyword) > 180 or SUSPICIOUS_QUERY_RE.search(keyword):
            dirty_keywords.append({"row": idx, "keyword_preview": keyword[:180]})
    if dirty_keywords:
        add_finding(
            findings,
            finding_id="dirty_semantic_core_queries",
            severity="high",
            title="Semantic core contains prompt/spam-like or malformed GSC queries.",
            evidence={"dirty_count": len(dirty_keywords), "examples": dirty_keywords[:10]},
            action="Run a cleaning step before clustering: remove prompt-like rows, normalize whitespace, and preserve CSV quoting.",
        )

    if (package_dir / "page-briefs.md").exists() and (package_dir / "mvp-page-briefs.md").exists():
        if compact_hash(package_dir / "page-briefs.md") == compact_hash(package_dir / "mvp-page-briefs.md"):
            add_finding(
                findings,
                finding_id="duplicate_page_briefs",
                severity="high",
                title="page-briefs.md and mvp-page-briefs.md are identical.",
                evidence={"files": ["page-briefs.md", "mvp-page-briefs.md"]},
                action="Either remove the duplicate or make MVP briefs deeper and page-specific while keeping page-briefs as the full backlog.",
            )

    planned = planned_urls(content_rows, clusters)
    referenced = referenced_urls(clusters, site_structure)
    orphan = sorted(url for url in referenced if url not in planned and not re.match(r"^/(tools|hair-color|hairstyles|guides)/$", url))
    if orphan:
        add_finding(
            findings,
            finding_id="orphan_internal_urls",
            severity="high",
            title="Internal links or site-structure URLs do not have planned pages/clusters.",
            evidence={"orphan_count": len(orphan), "examples": orphan[:20]},
            action="Add clusters/content-plan rows for referenced URLs or remove them from internal-link targets.",
        )

    yaml_attrs = yaml_entity_attributes(entity_yaml)
    md_attrs = parse_md_entity_attributes(entity_md)
    drift = []
    for entity_name, attrs in yaml_attrs.items():
        missing_attrs = sorted(attr for attr in attrs if attr and attr not in md_attrs.get(entity_name, set()))
        if missing_attrs:
            drift.append({"entity": entity_name, "missing_in_md": missing_attrs[:20]})
    if drift:
        add_finding(
            findings,
            finding_id="entity_map_md_yaml_drift",
            severity="medium",
            title="entity-map.md lost attributes that exist in entity-map.yaml.",
            evidence={"entity_count": len(drift), "examples": drift[:10]},
            action="Render entity-map.md from the structured YAML/JSON source instead of maintaining parallel manual versions.",
        )

    google_nlp = sources.get("google_nlp") if isinstance(sources, dict) else None
    if isinstance(google_nlp, dict):
        raw_entities = google_nlp.get("entities") or []
        names = [repeated_phrase_clean(str(item.get("name") or "")) for item in raw_entities if isinstance(item, dict) and norm(item.get("name"))]
        duplicates = {name: count for name, count in Counter(names).items() if count >= 3}
        if duplicates and not sources.get("google_nlp_aggregated"):
            add_finding(
                findings,
                finding_id="google_nlp_not_aggregated",
                severity="medium",
                title="Google NLP entities are present but not deduplicated or aggregated.",
                evidence={"duplicate_entities": dict(sorted(duplicates.items(), key=lambda item: item[1], reverse=True)[:10])},
                action="Aggregate by normalized entity name, sum/avg salience, remove malformed duplicates, then feed only the aggregate into entity-map decisions.",
            )

    has_ai_overview = any("ai_overview" in (row.get("dataforseo_serp_features") or row.get("serp_features") or "").lower() for row in semantic_rows + dataforseo_rows)
    geo_text = "\n".join([page_briefs, mvp_briefs, technical_spec, site_structure])
    if has_ai_overview and not GEO_TERMS_RE.search(geo_text):
        add_finding(
            findings,
            finding_id="ai_overview_signals_unused",
            severity="medium",
            title="AI Overview SERP features were collected but not translated into GEO/content requirements.",
            evidence={"ai_overview_rows_present": True},
            action="Add answer-first blocks, citation-ready Answer Units, source-backed proof, and AI prompt checks to affected page briefs.",
        )

    brief_text = "\n".join([page_briefs, mvp_briefs]).lower()
    if brief_text and not all(term in brief_text for term in ["word count", "entities", "copywriter"]):
        add_finding(
            findings,
            finding_id="page_briefs_too_shallow",
            severity="medium",
            title="Page briefs lack section-level writing guidance.",
            evidence={"missing_expected_markers": [term for term in ["word count", "entities", "copywriter"] if term not in brief_text]},
            action="Generate page-outline-v2 briefs with H2/H3 sections, word counts, entity coverage, visuals, copywriter notes, evidence requirements, and schema.",
        )

    evidence_text = "\n".join([page_briefs, mvp_briefs, technical_spec, entity_md]).lower()
    if evidence_text and not EEAT_TERMS_RE.search(evidence_text):
        add_finding(
            findings,
            finding_id="eeat_evidence_missing",
            severity="medium",
            title="Briefs do not define an E-E-A-T/evidence layer.",
            evidence={"checked_files": ["page-briefs.md", "mvp-page-briefs.md", "technical-spec.md", "entity-map.md"]},
            action="Add authors/review policy, source/citation rules, schema, trust assets, privacy/safety limits, and proof requirements.",
        )

    critical_count = sum(1 for item in findings if item["severity"] == "critical")
    high_count = sum(1 for item in findings if item["severity"] == "high")
    score = max(0, 100 - critical_count * 20 - high_count * 10 - sum(1 for item in findings if item["severity"] == "medium") * 5)
    status = "fail" if critical_count else "warn" if findings else "pass"
    findings.sort(key=lambda item: SEVERITY_ORDER.get(item["severity"], 0), reverse=True)
    scorecard = scorecard_from_findings(findings)
    remediation_plan = remediation_plan_from_findings(findings)

    report = {
        "audit_id": "research_package_quality",
        "title": "Research Package Quality Gate",
        "generated_at": utc_now(),
        "status": status,
        "score": score,
        "ten_point_score": round(sum(item["score"] for item in scorecard) / max(1, len(scorecard)), 1),
        "package_dir": str(package_dir),
        "counts": {
            "semantic_rows": len(semantic_rows),
            "content_plan_rows": len(content_rows),
            "dataforseo_rows": len(dataforseo_rows),
            "clusters": len(clusters),
            "planned_urls": len(planned),
            "findings": len(findings),
            "critical_findings": critical_count,
            "high_findings": high_count,
        },
        "inputs": {
            "required_files": {name: (package_dir / name).exists() for name in REQUIRED_FILES},
            "required_research_sources": normalize_required_sources(nested_get(project_cfg, "quality_gates.required_research_sources", [])),
            "semantic_core_fields": semantic_fields,
            "content_plan_fields": content_fields,
            "dataforseo_fields": dataforseo_fields,
        },
        "source_lock_gate": nested_get(architecture, "metadata.source_lock_gate", {}),
        "findings": findings,
        "scorecard": scorecard,
        "remediation_plan": remediation_plan,
        "actions": [item["recommended_action"] for item in findings[:8]],
        "paths": {},
    }
    report["launch_action_plan"] = launch_action_plan(report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Research Package Quality Gate",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- Score: `{report['score']}/100`",
        f"- 10-point score: `{report.get('ten_point_score')}/10`",
        f"- Package: `{report['package_dir']}`",
        "",
        "## Counts",
        "",
    ]
    for key, value in report["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## 10-Criteria Scorecard", ""])
    for item in report.get("scorecard", []):
        blockers = ", ".join(f"`{finding_id}`" for finding_id in item.get("blocking_findings", [])) or "none"
        lines.append(f"- `{item['score']}/10` {item['label']} ({item['status']}): {blockers}")

    lines.extend(["", "## Automatic Launch Action Plan", ""])
    for item in report.get("launch_action_plan", []):
        lines.extend(
            [
                f"### Step {item['step']}: {item['action']}",
                "",
                f"- Priority: `{item['priority']}`",
                f"- Command: {item['command']}",
                f"- Done: {item['definition_of_done']}",
                "",
            ]
        )

    lines.extend(["", "## Remediation Plan", ""])
    if not report.get("remediation_plan"):
        lines.append("No remediation required by the current gate.")
    for item in report.get("remediation_plan", []):
        target_files = ", ".join(f"`{path}`" for path in item.get("target_files", [])) or "manual review"
        lines.extend(
            [
                f"### {item['priority']} {item['title']}",
                "",
                f"- Finding: `{item['finding_id']}`",
                f"- Mode: `{item['mode']}`",
                f"- Target files: {target_files}",
                f"- Command: {item['command']}",
                f"- Done: {item['definition_of_done']}",
                "",
            ]
        )

    lines.extend(["", "## Findings", ""])
    if not report["findings"]:
        lines.append("No findings. Package passed the current quality gate.")
    for item in report["findings"]:
        lines.extend(
            [
                f"### [{item['severity'].upper()}] {item['title']}",
                "",
                f"- ID: `{item['id']}`",
                f"- Evidence: `{json.dumps(item['evidence'], ensure_ascii=False)[:1200]}`",
                f"- Action: {item['recommended_action']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Gate Policy",
            "",
            "- `critical` findings fail the package and block downstream page-type/content decisions.",
            "- `high` findings require cleanup before handoff to writers/developers.",
            "- `medium` findings can proceed only with a logged exception and next-step task.",
            "- The page-level fix for shallow briefs is `page-outline-v2.py`.",
            "",
        ]
    )
    return "\n".join(lines)


def render_action_plan(report: dict[str, Any]) -> str:
    lines = [
        "# Automatic SEO Launch Action Plan",
        "",
        f"- Status: `{report['status']}`",
        f"- Score: `{report['score']}/100`",
        f"- 10-point score: `{report.get('ten_point_score')}/10`",
        f"- Package: `{report['package_dir']}`",
        "",
    ]
    for item in report.get("launch_action_plan", []):
        lines.extend(
            [
                f"## Step {item['step']}: {item['action']}",
                "",
                f"- Priority: `{item['priority']}`",
                f"- Command: {item['command']}",
                f"- Done: {item['definition_of_done']}",
                "",
            ]
        )
    lines.extend(
        [
            "## 10/10 Rule",
            "",
            "- Do not publish from this package while critical findings exist.",
            "- Aim for every scorecard criterion at `10/10`; `9/10` is acceptable only with a logged exception.",
            "- Rerun this command after every remediation step.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(package_dir: pathlib.Path, report: dict[str, Any], output_dir: pathlib.Path | None = None) -> None:
    out = output_dir or package_dir
    paths = {
        "markdown": out / "research-package-quality.md",
        "json": out / "research-package-quality.json",
        "action_plan": out / "research-package-action-plan.md",
    }
    report["paths"] = {key: str(path) for key, path in paths.items()}
    write_text(paths["markdown"], render_markdown(report))
    write_text(paths["json"], json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_text(paths["action_plan"], render_action_plan(report))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit an SEO research package for handoff quality.")
    parser.add_argument("package", help="Research package directory, or a file inside it.")
    parser.add_argument("--write", action="store_true", help="Write research-package-quality.md/json.")
    parser.add_argument("--output-dir", help="Output directory for reports. Defaults to the package directory.")
    parser.add_argument("--format", choices=["json", "markdown", "plan"], default="json")
    args = parser.parse_args(argv)

    package_dir = resolve_package(args.package)
    report = audit_package(package_dir)
    if args.write:
        write_outputs(package_dir, report, pathlib.Path(args.output_dir).expanduser().resolve() if args.output_dir else None)

    if args.format == "markdown":
        print(render_markdown(report))
    elif args.format == "plan":
        print(render_action_plan(report))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
