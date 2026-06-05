#!/usr/bin/env python3
"""Print the active token, budget, tool, and automation governance for a project.

The report is intentionally read-only and never prints secret values. Use it at
Phase 0 before expensive API calls, browser collection, publishing, or schedules.
"""

from __future__ import annotations

import argparse
import json
import os
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

PAID_OR_QUOTA_SOURCES = {
    "neuronwriter",
    "google_cloud_nlp",
    "keys_so",
    "keyso",
    "serpstat",
    "spyfu",
    "dataforseo",
    "google_ads",
    "yandex_direct",
    "microsoft_ads",
}


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


def rel_path(project_root: pathlib.Path, raw: str) -> pathlib.Path:
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def load_region_profile(profile_id: str) -> dict[str, Any]:
    path = pathlib.Path(__file__).resolve().parent.parent / "config" / "region-profiles" / f"{profile_id}.yaml"
    return load_yaml(path)


def load_env_names(project_root: pathlib.Path) -> set[str]:
    names = set(os.environ)
    env_file = project_root / ".env"
    if not env_file.exists():
        return names
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            names.add(key)
    return names


def source_enabled(source_cfg: Any) -> bool:
    return isinstance(source_cfg, dict) and bool(source_cfg.get("enabled"))


def active_source_set(cfg: dict[str, Any]) -> set[str]:
    sources = cfg.get("sources", {}) or {}
    active: set[str] = set()
    profile_id = cfg.get("region_profile")
    if profile_id:
        profile = load_region_profile(profile_id)
        active = (set(profile.get("sources_enable", [])) | set(profile.get("sources_proxy", []))) - set(profile.get("sources_disable", []))

    for name, source_cfg in sources.items():
        if isinstance(source_cfg, dict) and "enabled" in source_cfg:
            if source_cfg["enabled"]:
                active.add(name)
            else:
                active.discard(name)
            continue
        if isinstance(source_cfg, dict) and "enabled" not in source_cfg:
            for sub_name, sub_cfg in source_cfg.items():
                if source_enabled(sub_cfg):
                    active.add(f"{name}.{sub_name}")
    return active


def active_sources(cfg: dict[str, Any]) -> list[str]:
    return sorted(active_source_set(cfg))


def policy_file_status(cfg: dict[str, Any], project_root: pathlib.Path) -> list[dict[str, Any]]:
    defaults = {
        "neuronwriter_limits": "seo/neuronwriter-limits.yaml",
        "google_nlp_policy": "seo/entities/google-nlp-policy.yaml",
        "data_collection_map": "seo/seo-data-collection-map.md",
        "access_setup_runbook": "seo/access-setup-runbook.md",
        "ai_visibility_prompts": "seo/ai-visibility-prompts.csv",
        "tool_budget": "seo/tool-budget.yaml",
        "automation_policy": "seo/automation-policy.yaml",
        "usage_ledger": "seo/usage/usage-ledger.jsonl",
        "latest_usage_report": "seo/setup/latest-usage-ledger.md",
        "tool_stack_generated": "seo/tool-stack.generated.yaml",
        "tool_stack_report": "seo/setup/tool-stack-report.md",
        "latest_tool_stack": "seo/setup/latest-tool-stack.md",
        "growth_roadmap_generated": "seo/growth-roadmap.generated.yaml",
        "growth_roadmap_report": "seo/setup/growth-roadmap.md",
        "latest_growth_roadmap": "seo/setup/latest-growth-roadmap.md",
        "onboarding_generated": "seo/onboarding.generated.yaml",
        "onboarding_playbook": "seo/setup/onboarding-playbook.md",
        "onboarding_checklist": "seo/setup/onboarding-checklist.csv",
        "latest_onboarding_playbook": "seo/setup/latest-onboarding-playbook.md",
        "automation_recommendations": "seo/automations/automation-recommendations.md",
        "automation_policy_generated": "seo/automation-policy.generated.yaml",
        "setup_control_plane": "seo/setup/setup-control-plane.md",
        "latest_task_route": "seo/setup/latest-task-route.md",
        "project_intake": "seo/project-intake.yaml",
        "project_intake_report": "seo/project-intake-report.md",
        "project_profile": "seo/project-profile.generated.yaml",
    }
    configured = cfg.get("policy_files", {}) or {}
    rows = []
    for key, default in defaults.items():
        raw_path = configured.get(key, default) if isinstance(configured, dict) else default
        path = rel_path(project_root, raw_path)
        rows.append({"key": key, "path": raw_path, "exists": path.exists()})
    return rows


def paid_source_rows(cfg: dict[str, Any], env_names: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sources = cfg.get("sources", {}) or {}
    active = active_source_set(cfg)
    for name, source_cfg in sources.items():
        if name not in PAID_OR_QUOTA_SOURCES and not any(name.startswith(prefix) for prefix in PAID_OR_QUOTA_SOURCES):
            continue
        if not isinstance(source_cfg, dict):
            continue
        env_keys = sorted(
            value
            for key, value in source_cfg.items()
            if key.endswith("_env") and isinstance(value, str) and value
        )
        rows.append(
            {
                "source": name,
                "enabled": bool(source_cfg.get("enabled") or name in active),
                "env_present": [key for key in env_keys if key in env_names],
                "env_missing": [key for key in env_keys if key not in env_names],
            }
        )
    return rows


def build_report(cfg_path: pathlib.Path) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    env_names = load_env_names(project_root)
    governance = cfg.get("governance", {}) or {}
    token_policy = governance.get("token_policy", {}) if isinstance(governance.get("token_policy"), dict) else {}
    budget_policy = governance.get("budget_policy", {}) if isinstance(governance.get("budget_policy"), dict) else {}
    automation_policy = governance.get("automation_policy", {}) if isinstance(governance.get("automation_policy"), dict) else {}

    return {
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "locale": cfg.get("locale", {}),
        "engines": cfg.get("engines", []),
        "region_profile": cfg.get("region_profile"),
        "governance": {
            "profile": governance.get("profile", "not_configured"),
            "objective": governance.get("objective", "not_configured"),
            "token_policy": {
                "raw_data_in_context": token_policy.get("raw_data_in_context"),
                "progressive_disclosure": token_policy.get("progressive_disclosure"),
                "cache_first": token_policy.get("cache_first"),
                "max_context_input_tokens_per_phase": token_policy.get("max_context_input_tokens_per_phase"),
                "max_output_tokens_per_artifact": token_policy.get("max_output_tokens_per_artifact"),
                "browser_session_budget_minutes": token_policy.get("browser_session_budget_minutes"),
                "browser_pages_per_phase_cap": token_policy.get("browser_pages_per_phase_cap"),
            },
            "budget_policy": budget_policy,
            "automation_policy": {
                "default_mode": automation_policy.get("default_mode"),
                "create_schedules": automation_policy.get("create_schedules"),
                "approval_required": automation_policy.get("approval_required", []),
                "forbidden_without_explicit_policy": automation_policy.get("forbidden_without_explicit_policy", []),
            },
        },
        "policy_files": policy_file_status(cfg, project_root),
        "active_sources": active_sources(cfg),
        "paid_or_quota_sources": paid_source_rows(cfg, env_names),
    }


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    locale = report.get("locale", {})
    gov = report.get("governance", {})
    lines = [
        "# seo-cycle governance report",
        "",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Locale: {locale.get('language', '?')}-{locale.get('country', '?')} / {locale.get('region', '?')}",
        f"- Region profile: {report.get('region_profile')}",
        f"- Governance profile: {gov.get('profile')}",
        f"- Objective: {gov.get('objective')}",
        "",
        "## Token Policy",
    ]
    for key, value in gov.get("token_policy", {}).items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Budget Policy"])
    for key, value in gov.get("budget_policy", {}).items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Automation Policy"])
    automation = gov.get("automation_policy", {})
    lines.append(f"- default_mode: {automation.get('default_mode')}")
    lines.append(f"- create_schedules: {automation.get('create_schedules')}")
    if automation.get("approval_required"):
        lines.append(f"- approval_required: {', '.join(automation['approval_required'])}")
    if automation.get("forbidden_without_explicit_policy"):
        lines.append(f"- forbidden_without_explicit_policy: {', '.join(automation['forbidden_without_explicit_policy'])}")

    lines.extend(["", "## Policy Files", "| Key | Exists | Path |", "| --- | --- | --- |"])
    for row in report.get("policy_files", []):
        lines.append(f"| {row['key']} | {'yes' if row['exists'] else 'no'} | {row['path']} |")

    lines.extend(["", "## Active Sources"])
    active = report.get("active_sources", [])
    lines.append(", ".join(active) if active else "No active sources configured.")

    lines.extend(["", "## Paid Or Quota Sources", "| Source | Enabled | Env present | Env missing |", "| --- | --- | --- | --- |"])
    for row in report.get("paid_or_quota_sources", []):
        lines.append(
            f"| {row['source']} | {row['enabled']} | {', '.join(row['env_present']) or '-'} | {', '.join(row['env_missing']) or '-'} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
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

    report = build_report(cfg_path)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
