#!/usr/bin/env python3
"""Review-only upgrade assistant for existing seo-cycle projects.

When a project already has seo-cycle.yaml, the bootstrap should not overwrite
it. This script compares the project against the current template/control-plane
surface and writes a questionnaire for newly available features.
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

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. `pip3 install pyyaml`", file=sys.stderr)
    sys.exit(2)


CONFIG_SEARCH_PATHS = [
    "seo-cycle.yaml",
    ".seo-cycle.yaml",
    "seo/seo-cycle.yaml",
    ".claude/seo-cycle.yaml",
]

FEATURES: list[dict[str, Any]] = [
    {
        "id": "codex_first_runtime",
        "title": "Codex-first runtime and search routing",
        "policy_keys": [],
        "artifacts": ["AGENTS.md"],
        "question": "Use Codex as the primary runtime and set Claude search collection to Codex external mode?",
        "default_answer": "yes_for_codex_projects",
        "command": "curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash",
        "notes": "Codex runs search/browser/native skills directly. Claude projects should use SEO_SEARCH_RUNTIME=codex_external for separate Codex search collection.",
    },
    {
        "id": "setup_blueprint",
        "title": "Setup blueprint matrix",
        "policy_keys": ["setup_blueprint_generated", "setup_blueprint", "setup_blueprint_json", "setup_matrix_csv", "latest_setup_blueprint"],
        "artifacts": ["seo/setup/setup-blueprint.md", "seo/setup/setup-matrix.csv"],
        "question": "Generate the low-token country/engine/business/tools/budget/automation matrix?",
        "default_answer": "yes",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/setup-blueprint.py --write",
        "notes": "Useful for every upgraded project; secret-free.",
    },
    {
        "id": "setup_gap_questionnaire",
        "title": "Setup gap audit and questionnaire",
        "policy_keys": ["setup_gap_audit_report", "setup_questionnaire", "setup_questionnaire_csv", "setup_answer_plan"],
        "artifacts": ["seo/setup/setup-gap-audit.md", "seo/setup/setup-questionnaire.csv", "seo/setup/setup-answer-plan.md"],
        "question": "Create/update the missing-fields questionnaire and review-only answer plan?",
        "default_answer": "yes",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/setup-gap-audit.py --write",
        "notes": "Fill CSV with non-secret answers, then run setup-answer-plan.py --write.",
    },
    {
        "id": "safe_upgrade_apply",
        "title": "Safe upgrade apply helper",
        "policy_keys": [
            "project_upgrade_apply_report",
            "project_upgrade_apply_json",
            "project_upgrade_apply_csv",
            "latest_project_upgrade_apply",
            "latest_project_upgrade_apply_json",
        ],
        "artifacts": ["seo/setup/project-upgrade-apply.md"],
        "question": "Enable the safe updater that applies reviewed missing policy_files keys with a backup?",
        "default_answer": "yes",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/project-upgrade-apply.py --write",
        "notes": "Dry-run by default. Use --apply only after reviewing upgrade-questionnaire.csv; it only adds missing policy_files keys and never changes secrets, paid tools, schedules, publishing, or indexing.",
    },
    {
        "id": "project_journey",
        "title": "Project journey gate",
        "policy_keys": [
            "project_journey_report",
            "project_journey_json",
            "project_journey_checklist",
            "latest_project_journey",
            "latest_project_journey_json",
        ],
        "artifacts": ["seo/setup/project-journey.md", "seo/setup/project-journey-checklist.csv"],
        "question": "Enable the automatic step-by-step project journey that shows the current stage, missing inputs, blockers, next command, and exit criteria?",
        "default_answer": "yes",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/project-journey.py --write",
        "notes": "Read-only by default. It prevents skipping from setup/research into writing/publishing when quality gates or approvals are missing.",
    },
    {
        "id": "page_outline_quality_gate",
        "title": "Page outline quality gate",
        "policy_keys": [
            "page_outline_quality_report",
            "page_outline_quality_json",
            "latest_page_outline_quality",
            "latest_page_outline_quality_json",
        ],
        "artifacts": ["seo/research-package/page-outline-quality.md"],
        "question": "Enable the automatic page-outline quality gate before writing or publishing MVP/P1 pages?",
        "default_answer": "yes",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/page-outline-quality.py seo/research-package --write --format markdown",
        "notes": "Checks page briefs for word-count drift, missing SERP/page-type lock, SEO meta, schema, internal links, Answer Units, evidence, entity orphans, visuals, and fabricated first-person expertise.",
    },
    {
        "id": "research_package_repair_layer",
        "title": "Research package repair layer",
        "policy_keys": [
            "research_package_quality_report",
            "research_package_quality_json",
            "research_package_action_plan",
            "semantic_core_cleaned",
            "semantic_core_rejected",
            "semantic_core_resynced",
            "google_nlp_entity_coverage",
            "orphan_url_backlog",
            "serp_validation_plan",
            "serp_validation_import_report",
            "serp_validation_import_json",
            "spoke_opportunities",
            "research_package_repair_report",
            "research_package_repair_json",
            "entity_graph_quality_report",
            "entity_graph_quality_json",
        ],
        "artifacts": [
            "seo/research-package/research-package-action-plan.md",
            "seo/research-package/serp-validation-plan.csv",
            "seo/research-package/serp-validation-import.md",
        ],
        "question": "Enable the repair layer for dirty semantic cores, URL/cluster drift, entity-map drift, Google NLP aggregation, orphan URLs, missing SERP validations and phase-2 spokes?",
        "default_answer": "yes",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/research-package-quality.py seo/research-package --write --format plan",
        "notes": "Run the specific repair scripts from the action plan. Use serp-validation-import.py only with reviewed JSON/CSV exports; the layer writes reviewable artifacts and does not publish or call paid APIs.",
    },
    {
        "id": "access_key_assistant",
        "title": "Access key/token assistant",
        "policy_keys": ["access_key_assistant", "access_key_assistant_json", "access_key_assistant_csv"],
        "artifacts": ["seo/setup/access-key-assistant.md", "seo/setup/access-key-assistant.csv"],
        "question": "Generate project-specific links and short instructions for only the needed keys/tokens?",
        "default_answer": "yes",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/access-key-assistant.py --write",
        "notes": "Skips providers that are not applicable or blocked; never stores secret values.",
    },
    {
        "id": "spend_usage_guard",
        "title": "Spend guard and usage ledger",
        "policy_keys": ["tool_budget", "spend_guard_report", "spend_checklist", "usage_ledger", "latest_usage_report"],
        "artifacts": ["seo/setup/spend-guard.md", "seo/setup/latest-usage-ledger.md"],
        "question": "Enable budget/subscription/token guardrails for this project?",
        "default_answer": "yes",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/spend-guard.py --write && python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py report --write",
        "notes": "Required before paid API, LLM, browser, subscription, or ads work.",
    },
    {
        "id": "tool_stack_growth_onboarding",
        "title": "Tool stack, growth roadmap, onboarding",
        "policy_keys": ["tool_stack_report", "growth_roadmap_report", "onboarding_playbook", "onboarding_checklist"],
        "artifacts": ["seo/setup/tool-stack-report.md", "seo/setup/growth-roadmap.md", "seo/setup/onboarding-playbook.md"],
        "question": "Refresh project-specific tools, roadmap, and onboarding playbook?",
        "default_answer": "yes",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write && python3 ~/.codex/skills/seo-cycle/scripts/growth-roadmap.py --write && python3 ~/.codex/skills/seo-cycle/scripts/setup-onboarding.py --write",
        "notes": "Keeps free/read-only tools first and gates paid/tracking/ads.",
    },
    {
        "id": "token_efficiency_provider_health",
        "title": "Token efficiency and provider health",
        "policy_keys": [
            "token_waste_audit_report",
            "token_waste_audit_json",
            "perplexity_health_report",
            "perplexity_health_json",
            "notebooklm_health_report",
            "notebooklm_health_json",
        ],
        "artifacts": [
            "seo/setup/token-waste-audit.md",
            "seo/setup/perplexity-health.md",
            "seo/setup/notebooklm-health.md",
        ],
        "question": "Enable token waste audit plus Perplexity/NotebookLM health reports for low-token evidence workflows?",
        "default_answer": "yes_report_only",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/token-waste-audit.py --write && python3 ~/.codex/skills/seo-cycle/scripts/perplexity-health.py --write && python3 ~/.codex/skills/seo-cycle/scripts/notebooklm-health.py --write",
        "notes": "Report-only. Perplexity uses persistent browser/app when available, no password storage; NotebookLM falls back to browser/manual source-pack export if MCP tools are unavailable.",
    },
    {
        "id": "automation_governance",
        "title": "Automation recommendations and safe schedule plan",
        "policy_keys": ["automation_policy", "automation_recommendations", "automation_policy_generated", "automation_plan"],
        "artifacts": ["seo/automations/automation-recommendations.md", "seo/automations/automation-plan.md"],
        "question": "Create report-only automation recommendations for this project?",
        "default_answer": "yes_report_only",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/automation-recommender.py --write && python3 ~/.codex/skills/seo-cycle/scripts/automation-plan.py --write --include-disabled",
        "notes": "Real cron/schedules remain disabled unless policy and explicit approval allow them.",
    },
    {
        "id": "seo_aeo_geo_vnext",
        "title": "SEO/AEO/GEO vNext report layer",
        "policy_keys": [
            "ai_brand_audit_report",
            "answer_units_audit_report",
            "eeat_evidence_map_report",
            "geo_kpi_model_report",
            "log_bot_audit_report",
            "ai_bot_access_check_report",
            "ai_bot_access_check_json",
            "technical_guardrails_audit_report",
            "snippet_sitemap_audit_report",
            "traffic_drop_diagnostics_report",
            "cannibalization_audit_report",
            "ru_commerce_readiness_report",
            "offpage_risk_audit_report",
            "conversion_sxo_audit_report",
            "expert_source_pack_report",
        ],
        "artifacts": ["seo/vnext/ai-brand-audit.md", "seo/vnext/expert-source-pack.md", "seo/vnext/technical-guardrails-audit.md"],
        "question": "Enable report-only SEO/AEO/GEO vNext audits: AI Brand, Answer Units, E-E-A-T, GEO KPI, logs, live AI bot access, technical, local/RU commerce, off-page, SXO, and expert sources?",
        "default_answer": "yes_report_only",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/expert-source-pack.py --write && python3 ~/.codex/skills/seo-cycle/scripts/ai-brand-audit.py --write && python3 ~/.codex/skills/seo-cycle/scripts/technical-guardrails-audit.py --write",
        "notes": "Additive and safe by default: no publishing, paid APIs, index submission, tracking tags, or ads. Live AI bot access check is explicit/manual because it sends public HTTP requests.",
    },
    {
        "id": "technical_site_tools",
        "title": "Technical site tools: rollup, links, redirects, URL inspection, Lighthouse, Serpstat, Labrika",
        "policy_keys": [
            "technical_site_audit_report",
            "technical_site_audit_json",
            "link_audit_report",
            "link_audit_json",
            "redirect_map_audit_report",
            "redirect_map_audit_json",
            "lighthouse_audit_report",
            "lighthouse_audit_json",
            "gsc_url_inspection_report",
            "gsc_url_inspection_json",
            "bing_url_inspection_report",
            "bing_url_inspection_json",
            "serpstat_audit_report",
            "serpstat_audit_json",
            "labrika_source_pack_report",
            "labrika_source_pack_json",
            "labrika_health_report",
            "labrika_health_json",
            "technical_mcp_health_report",
            "technical_mcp_health_json",
        ],
        "artifacts": [
            "seo/technical/technical-site-audit.md",
            "seo/technical/link-audit.md",
            "seo/technical/redirect-map-audit.md",
            "seo/technical/lighthouse-audit.md",
            "seo/technical/gsc-url-inspection.md",
            "seo/technical/bing-url-inspection.md",
            "seo/technical/serpstat-audit.md",
            "seo/technical/labrika-source-pack.md",
            "seo/technical/labrika-health.md",
            "seo/technical/technical-mcp-health.md",
        ],
        "question": "Enable technical-site report pack for rollup, broken links, redirect maps, GSC/Bing URL inspection, optional MCP health, Lighthouse/CWV, guarded Serpstat Site Audit, and Labrika export/health?",
        "default_answer": "yes_report_only",
        "command": "python3 ~/.codex/skills/seo-cycle/scripts/link-audit.py --write && python3 ~/.codex/skills/seo-cycle/scripts/redirect-map-audit.py --write && python3 ~/.codex/skills/seo-cycle/scripts/lighthouse-audit.py --write && python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py --write && python3 ~/.codex/skills/seo-cycle/scripts/bing-url-inspection.py --write && python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py --write && python3 ~/.codex/skills/seo-cycle/scripts/labrika-source-pack.py --write && python3 ~/.codex/skills/seo-cycle/scripts/labrika-health.py --write && python3 ~/.codex/skills/seo-cycle/scripts/technical-mcp-health.py --write && python3 ~/.codex/skills/seo-cycle/scripts/technical-site-audit.py --write",
        "notes": "Report-only by default. Live HTTP/API calls require --live; GSC/Bing are read-only with env tokens; Serpstat requires SERPSTAT_API_KEY and credit/budget approval. Labrika stays manual/export until a public API is confirmed.",
    },
]


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def find_config(start_dir: pathlib.Path) -> pathlib.Path | None:
    for rel in CONFIG_SEARCH_PATHS:
        path = start_dir / rel
        if path.exists():
            return path
    return None


def project_root_for(cfg_path: pathlib.Path) -> pathlib.Path:
    if cfg_path.name in (".seo-cycle.yaml", "seo-cycle.yaml"):
        return cfg_path.parent
    if "/seo/" in str(cfg_path) or "/.claude/" in str(cfg_path):
        return cfg_path.parent.parent
    return cfg_path.parent


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def rel_path(project_root: pathlib.Path, raw: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(str(raw)).expanduser()
    return path if path.is_absolute() else project_root / path


def current_version() -> str:
    version_file = skill_root() / "VERSION"
    return version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unknown"


def template_policy_files() -> dict[str, str]:
    template = load_yaml(skill_root() / "config" / "project.template.yaml")
    return template.get("policy_files", {}) if isinstance(template.get("policy_files"), dict) else {}


def existing_policy_files(cfg: dict[str, Any]) -> dict[str, str]:
    return cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}


def feature_status(feature: dict[str, Any], cfg: dict[str, Any], project_root: pathlib.Path, template_policy: dict[str, str]) -> dict[str, Any]:
    policy_files = existing_policy_files(cfg)
    missing_policy_keys = [key for key in feature.get("policy_keys", []) if key not in policy_files and key in template_policy]
    missing_artifacts = [path for path in feature.get("artifacts", []) if not rel_path(project_root, path).exists()]
    configured = not missing_policy_keys and not missing_artifacts
    status = "configured" if configured else "review_needed"
    return {
        "id": feature["id"],
        "title": feature["title"],
        "status": status,
        "missing_policy_keys": missing_policy_keys,
        "missing_artifacts": missing_artifacts,
        "question": feature["question"],
        "default_answer": feature["default_answer"],
        "answer": "",
        "command": feature["command"],
        "notes": feature["notes"],
    }


def build_report(cfg_path: pathlib.Path) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    template_policy = template_policy_files()
    rows = [feature_status(feature, cfg, project_root, template_policy) for feature in FEATURES]
    missing_policy_defaults = {
        key: value
        for key, value in template_policy.items()
        if key not in existing_policy_files(cfg)
    }
    review_rows = [row for row in rows if row["status"] != "configured"]
    runtime = cfg.get("runtime", "auto")
    report = {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "core_version": current_version(),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "runtime": runtime,
        "summary": {
            "features": len(rows),
            "review_needed": len(review_rows),
            "missing_policy_defaults": len(missing_policy_defaults),
        },
        "features": rows,
        "missing_policy_defaults": missing_policy_defaults,
        "rules": [
            "This report is review-only and never edits seo-cycle.yaml automatically.",
            "Fill upgrade-questionnaire.csv with yes/no/defer and apply safe changes manually or through the listed commands.",
            "Do not paste secrets into the questionnaire; use access-key-assistant.md and .env for secret setup.",
        ],
        "next_actions": [
            "Open seo/setup/upgrade-questionnaire.csv and answer only needed features.",
            "Run access-key-assistant.py --write for provider-specific key/token steps.",
            "Run setup-control-plane.py --write after applying reviewed upgrade choices.",
        ],
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    lines = [
        "# seo-cycle project upgrade assistant",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Core version: {report.get('core_version')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Runtime: {report.get('runtime')}",
        f"- Review-needed features: {report.get('summary', {}).get('review_needed')}",
        "",
        "## Feature Review",
        "| Feature | Status | Default | Question | Command |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report.get("features", []):
        lines.append(
            f"| `{row['id']}` | `{row['status']}` | `{row['default_answer']}` | {row['question']} | `{row['command']}` |"
        )
        if row.get("missing_policy_keys"):
            lines.append(f"| | | | Missing policy keys: {', '.join(row['missing_policy_keys'])} | |")
        if row.get("missing_artifacts"):
            lines.append(f"| | | | Missing artifacts: {', '.join(row['missing_artifacts'])} | |")
    lines.extend(["", "## Missing Policy Defaults"])
    for key, path in report.get("missing_policy_defaults", {}).items():
        lines.append(f"- `{key}`: `{path}`")
    lines.extend(["", "## Rules"])
    for rule in report.get("rules", []):
        lines.append(f"- {rule}")
    lines.extend(["", "## Next Actions"])
    for action in report.get("next_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def questionnaire_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    fields = ["feature", "status", "default_answer", "answer", "question", "missing_policy_keys", "missing_artifacts", "command", "notes"]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in report.get("features", []):
        writer.writerow(
            {
                "feature": row.get("id", ""),
                "status": row.get("status", ""),
                "default_answer": row.get("default_answer", ""),
                "answer": row.get("answer", ""),
                "question": row.get("question", ""),
                "missing_policy_keys": ", ".join(row.get("missing_policy_keys", [])),
                "missing_artifacts": ", ".join(row.get("missing_artifacts", [])),
                "command": row.get("command", ""),
                "notes": row.get("notes", ""),
            }
        )
    return buffer.getvalue()


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    setup_dir = project_root / "seo" / "setup"
    markdown = render_markdown(report)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    write_text(setup_dir / "upgrade-assistant.md", markdown)
    write_text(setup_dir / "upgrade-assistant.json", json_text)
    write_text(setup_dir / "upgrade-questionnaire.csv", questionnaire_csv(report))
    write_text(setup_dir / "latest-upgrade-assistant.md", markdown)
    write_text(setup_dir / "latest-upgrade-assistant.json", json_text)
    return setup_dir / "upgrade-assistant.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write upgrade assistant artifacts under seo/setup.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.config:
        cfg_path = pathlib.Path(args.config).expanduser().resolve()
    else:
        found = find_config(pathlib.Path.cwd())
        if not found:
            print(f"ERROR: seo-cycle.yaml не найден в {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        cfg_path = found.resolve()
    if not cfg_path.exists():
        print(f"ERROR: {cfg_path} не найден", file=sys.stderr)
        return 2

    project_root = project_root_for(cfg_path)
    report = build_report(cfg_path)
    if args.write:
        write_outputs(project_root, report)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
