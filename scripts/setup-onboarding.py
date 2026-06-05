#!/usr/bin/env python3
"""Create a detailed first-run onboarding playbook for one seo-cycle project.

This script stitches together existing generated artifacts into an executable
setup checklist. It separates agent work, human-secret input, review, and
approval gates; it never stores or prints secret values.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import subprocess
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

DEFAULT_MAX_STEPS = 32


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


def rel_path(project_root: pathlib.Path, raw: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get(key, default))


def load_policy_json(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> dict[str, Any]:
    path = policy_path(cfg, project_root, key, default)
    candidates = [path]
    if path.suffix == ".md":
        candidates.append(path.with_suffix(".json"))
    for candidate in candidates:
        report = load_json(candidate)
        if report:
            return report
    return {}


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "enabled", "да", "д"}
    return bool(value)


def run_json_script(script: str, cfg_path: pathlib.Path, project_root: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(skill_root() / "scripts" / script), str(cfg_path), "--format", "json"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def load_tool_stack(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    report = load_policy_json(cfg, project_root, "tool_stack_report", "seo/setup/tool-stack-report.json")
    return report or run_json_script("tool-stack-recommender.py", cfg_path, project_root)


def load_growth_roadmap(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    report = load_policy_json(cfg, project_root, "growth_roadmap_report", "seo/setup/growth-roadmap.json")
    return report or run_json_script("growth-roadmap.py", cfg_path, project_root)


def load_automation(cfg_path: pathlib.Path, cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, Any]:
    report = load_policy_json(cfg, project_root, "automation_recommendations", "seo/automations/automation-recommendations.json")
    return report or run_json_script("automation-recommender.py", cfg_path, project_root)


def country(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    locale = cfg.get("locale", {}) if isinstance(cfg.get("locale"), dict) else {}
    return str(markets.get("primary_country") or locale.get("country") or "").upper()


def project_type(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    business = intake.get("business", {}) if isinstance(intake.get("business"), dict) else {}
    return str(business.get("project_type") or cfg.get("project_type") or "")


def business_flags(cfg: dict[str, Any], intake: dict[str, Any]) -> dict[str, bool]:
    pt = project_type(cfg, intake)
    marketing = intake.get("marketing", {}) if isinstance(intake.get("marketing"), dict) else {}
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    local_platforms = markets.get("local_platforms", {}) if isinstance(markets.get("local_platforms"), dict) else {}
    business_profile = cfg.get("business_profile", {}) if isinstance(cfg.get("business_profile"), dict) else {}
    has_address = isinstance(business_profile.get("address"), dict) and any(business_profile.get("address", {}).values())
    return {
        "ecommerce": pt == "ecommerce" or boolish(marketing.get("ecommerce_feeds")),
        "local": pt == "local_business" or boolish(marketing.get("local_seo")) or any(boolish(v) for v in local_platforms.values()) or has_address,
        "organic": boolish(marketing.get("organic_seo", True)),
        "content": boolish(marketing.get("content_marketing", True)),
    }


def decisions(tool_stack: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return tool_stack.get("decisions", {}) if isinstance(tool_stack.get("decisions"), dict) else {}


def decision_enabled(decisions_by_tool: dict[str, dict[str, Any]], tool_id: str) -> bool:
    row = decisions_by_tool.get(tool_id, {})
    return row.get("decision") in {"enabled", "report_only", "approval_required"}


def secret_env_names(decisions_by_tool: dict[str, dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for row in decisions_by_tool.values():
        if not isinstance(row, dict):
            continue
        if row.get("decision") not in {"enabled", "report_only", "approval_required"}:
            continue
        for name in row.get("env", []):
            if isinstance(name, str) and name and "=" not in name:
                names.add(name)
    return sorted(names)


def approval_gates_from(decisions_by_tool: dict[str, dict[str, Any]], growth_roadmap: dict[str, Any]) -> list[str]:
    gates: set[str] = set()
    for row in decisions_by_tool.values():
        if isinstance(row, dict):
            gates.update(str(gate) for gate in row.get("approval_gates", []) if gate)
    gates.update(str(gate) for gate in growth_roadmap.get("approval_gates", []) if gate)
    return sorted(gates)


def step(
    step_id: str,
    phase: str,
    owner: str,
    title: str,
    details: str,
    commands: list[str] | None = None,
    proofs: list[str] | None = None,
    gates: list[str] | None = None,
    env_names: list[str] | None = None,
    priority: int = 50,
) -> dict[str, Any]:
    return {
        "id": step_id,
        "phase": phase,
        "owner": owner,
        "priority": priority,
        "title": title,
        "details": details,
        "commands": commands or [],
        "proofs": proofs or [],
        "approval_gates": gates or [],
        "env_names": env_names or [],
    }


def build_steps(
    cfg_path: pathlib.Path,
    cfg: dict[str, Any],
    intake: dict[str, Any],
    tool_stack: dict[str, Any],
    growth_roadmap: dict[str, Any],
    automation: dict[str, Any],
) -> list[dict[str, Any]]:
    cty = country(cfg, intake)
    flags = business_flags(cfg, intake)
    by_tool = decisions(tool_stack)
    env_names = secret_env_names(by_tool)
    gates = approval_gates_from(by_tool, growth_roadmap)
    steps: list[dict[str, Any]] = [
        step(
            "confirm_project_identity",
            "identity",
            "review",
            "Confirm project identity, country, language, CMS, business type, and goals",
            "Review `seo-cycle.yaml` and `seo/project-intake.yaml`; correct country, search engines, city/region, project type, CMS, business model, sales channels, audiences, and conversion goals before connecting tools.",
            proofs=["seo-cycle.yaml", "project_intake"],
            priority=10,
        ),
        step(
            "generate_project_profile",
            "identity",
            "agent",
            "Generate project profile overlay",
            "Create a project-specific overlay from intake. Apply it only after review because it updates `seo-cycle.yaml`.",
            commands=[
                f"python3 {skill_root()}/scripts/project-profile.py {cfg_path} --write",
                f"python3 {skill_root()}/scripts/project-profile.py {cfg_path} --apply",
            ],
            proofs=["project_profile", "project_profile_report"],
            gates=["config_change_review"],
            priority=20,
        ),
        step(
            "create_policy_files",
            "policies",
            "agent",
            "Create and review local policy files",
            "Ensure budget, data collection, access, AI visibility, NeuronWriter, Google NLP, and automation policy files exist before tool execution.",
            commands=[f"python3 {skill_root()}/scripts/validate-config.py {cfg_path}"],
            proofs=[
                "tool_budget",
                "data_collection_map",
                "access_setup_runbook",
                "ai_visibility_prompts",
                "neuronwriter_limits",
                "google_nlp_policy",
                "automation_policy",
            ],
            priority=30,
        ),
        step(
            "add_secret_env_names",
            "access",
            "human_secret",
            "Add required API/OAuth/service-account values to `.env` or provider consoles",
            "Only the human should paste secrets. Store values in `.env` or provider consoles; the playbook records names only.",
            proofs=[".env names only", "access_setup_runbook"],
            env_names=env_names,
            priority=40,
        ),
    ]

    if decision_enabled(by_tool, "google_search_console"):
        steps.append(
            step(
                "connect_google_search_console",
                "access",
                "human_secret",
                "Connect Google Search Console read-only data",
                "Add the service account/user in Search Console for the property. This does not install analytics code on the site.",
                proofs=["GOOGLE_APPLICATION_CREDENTIALS", "GSC_SITE_URL", "search_console_access"],
                env_names=[name for name in ("GOOGLE_APPLICATION_CREDENTIALS", "GSC_SITE_URL") if name in env_names],
                priority=45,
            )
        )

    if decision_enabled(by_tool, "yandex_webmaster"):
        steps.append(
            step(
                "connect_yandex_webmaster",
                "access",
                "human_secret",
                "Connect Yandex Webmaster read-only data",
                "Create or reuse Yandex OAuth credentials and add site host IDs. Keep tokens out of docs.",
                proofs=["YANDEX_OAUTH_TOKEN", "YANDEX_USER_ID", "YANDEX_WEBMASTER_HOST_ID"],
                env_names=[name for name in ("YANDEX_OAUTH_TOKEN", "YANDEX_USER_ID", "YANDEX_WEBMASTER_HOST_ID") if name in env_names],
                priority=46,
            )
        )

    if decision_enabled(by_tool, "bing_webmaster"):
        steps.append(
            step(
                "connect_bing_webmaster",
                "access",
                "human_secret",
                "Connect Bing Webmaster Tools",
                "Add the site in Bing Webmaster and create an API key/site URL env pair for read-only index, crawl, keyword, and backlink evidence.",
                proofs=["BING_WEBMASTER_API_KEY", "BING_SITE_URL"],
                env_names=[name for name in ("BING_WEBMASTER_API_KEY", "BING_SITE_URL") if name in env_names],
                priority=47,
            )
        )

    if flags["local"]:
        local_envs = [name for name in ("GOOGLE_BUSINESS_ACCOUNT_ID", "GOOGLE_BUSINESS_LOCATION_ID") if name in env_names]
        steps.append(
            step(
                "connect_local_profiles",
                "local",
                "review",
                "Connect and document local profiles",
                "Review Google Business Profile, Bing Places, Yandex Business/Maps, and 2GIS applicability from `tool-stack-report.md`; add NAP/profile URLs and competitors in `business_profile`.",
                proofs=["business_profile", "tool_stack_report", "growth_roadmap_report"],
                env_names=local_envs,
                priority=55,
            )
        )

    if flags["ecommerce"]:
        steps.append(
            step(
                "connect_merchant_feeds",
                "ecommerce",
                "review",
                "Connect merchant/feed quality sources",
                "Review Google Merchant/Yandex Merchant/WooCommerce feed applicability. Keep ads separate from feed diagnostics.",
                proofs=["tool_stack_report", "growth_roadmap_report", "merchant_feed_access"],
                env_names=[name for name in env_names if "MERCHANT" in name or "WOO_" in name],
                priority=56,
            )
        )

    if cty == "RU":
        steps.append(
            step(
                "rf_tracking_policy_review",
                "policy",
                "approval",
                "Review RF tracking policy before any foreign analytics tag",
                "For RF projects, keep GA4, Clarity, pixels, and other foreign tracking disabled unless a written project policy explicitly allows them.",
                proofs=["data_collection_map", "tool_stack_report"],
                gates=["tracking_tag_install"],
                priority=35,
            )
        )

    if decision_enabled(by_tool, "google_cloud_nlp"):
        steps.append(
            step(
                "google_cloud_nlp_budget_guard",
                "budget",
                "approval",
                "Approve Google Cloud NLP budget and cache guard",
                "Use Google NLP only for priority URL entity audits with cache and unit caps. Confirm Cloud budget alert and local policy before any run.",
                commands=[f"python3 {skill_root()}/scripts/usage-ledger.py check {cfg_path} --service google_cloud_nlp --category paid_api --usd 1 --fail-on-block"],
                proofs=["google_nlp_policy", "latest_usage_report"],
                gates=["paid_api_run"],
                env_names=[name for name in ("GOOGLE_APPLICATION_CREDENTIALS",) if name in env_names],
                priority=60,
            )
        )

    if decision_enabled(by_tool, "neuronwriter"):
        steps.append(
            step(
                "neuronwriter_limits_guard",
                "budget",
                "approval",
                "Record NeuronWriter plan and remaining limits",
                "Use NeuronWriter for priority pages only; no whole-catalog runs without approved queue and remaining content writer/AI credits.",
                proofs=["neuronwriter_limits", "latest_usage_report"],
                gates=["paid_api_run"],
                env_names=[name for name in ("NEURON_API_KEY",) if name in env_names],
                priority=61,
            )
        )

    steps.extend(
        [
            step(
                "run_tool_stack_recommender",
                "tools",
                "agent",
                "Generate tool-stack report",
                "Refresh decisions for enabled/report-only/approval-required/disabled/not-applicable tools.",
                commands=[f"python3 {skill_root()}/scripts/tool-stack-recommender.py {cfg_path} --write"],
                proofs=["tool_stack_generated", "tool_stack_report"],
                priority=70,
            ),
            step(
                "run_spend_guard",
                "budget",
                "agent",
                "Generate spend/subscription guard",
                "Create a compact spend guard before paid/API/LLM/subscription work; use its preflight commands before each run.",
                commands=[f"python3 {skill_root()}/scripts/spend-guard.py {cfg_path} --write"],
                proofs=["spend_guard_report", "latest_spend_guard", "spend_checklist"],
                priority=72,
            ),
            step(
                "run_growth_roadmap",
                "roadmap",
                "agent",
                "Generate growth roadmap",
                "Create top-N action priorities across technical, search evidence, ecommerce/local, content/entities, AI visibility, CRO/marketing, and automations.",
                commands=[f"python3 {skill_root()}/scripts/growth-roadmap.py {cfg_path} --write"],
                proofs=["growth_roadmap_generated", "growth_roadmap_report"],
                priority=75,
            ),
            step(
                "run_automation_recommender",
                "automation",
                "agent",
                "Generate automation recommendations",
                "Recommend report-only/approval-gated recurring checks. Do not install schedules yet.",
                commands=[f"python3 {skill_root()}/scripts/automation-recommender.py {cfg_path} --write"],
                proofs=["automation_recommendations", "automation_policy_generated"],
                gates=["schedule_install"],
                priority=80,
            ),
            step(
                "run_setup_control_plane",
                "verification",
                "agent",
                "Run full setup control plane",
                "Refresh readiness, validation, sources, setup blueprint, task route, context pack, setup gap audit/questionnaire, answer-plan path, usage ledger, tool stack, growth roadmap, and automation recommendations.",
                commands=[f"python3 {skill_root()}/scripts/setup-control-plane.py {cfg_path} --write --task \"first SEO setup\""],
                proofs=["setup_control_plane", "setup_blueprint", "setup_matrix_csv", "context_pack_report", "setup_gap_audit_report", "setup_questionnaire", "setup_answer_plan", "latest_task_route", "latest_usage_report", "tool_stack_report", "growth_roadmap_report"],
                priority=90,
            ),
            step(
                "validate_before_first_cycle",
                "verification",
                "agent",
                "Validate config before first SEO cycle",
                "Run validator and resolve all blocking errors; checklist items become onboarding tasks, not ignored warnings.",
                commands=[f"python3 {skill_root()}/scripts/validate-config.py {cfg_path}"],
                proofs=["latest_validation"],
                priority=95,
            ),
            step(
                "route_first_roadmap_action",
                "execution",
                "agent",
                "Route the first roadmap action before execution",
                "Pick the top approved roadmap action and generate a bounded task route plus context pack before loading data or using tools.",
                commands=[
                    f"python3 {skill_root()}/scripts/task-router.py {cfg_path} --task \"<top growth-roadmap action>\" --write",
                    f"python3 {skill_root()}/scripts/context-pack.py {cfg_path} --task \"<top growth-roadmap action>\" --write",
                ],
                proofs=["latest_task_route", "context_pack_report", "growth_roadmap_report"],
                priority=100,
            ),
        ]
    )

    if automation.get("policy_overlay", {}).get("planned_automations"):
        steps.append(
            step(
                "review_schedule_install_policy",
                "automation",
                "approval",
                "Review schedule install policy",
                "Keep schedules uninstalled until governance, automation policy, and explicit env gate allow it.",
                commands=[f"python3 {skill_root()}/scripts/automation-plan.py {cfg_path} --write --include-disabled"],
                proofs=["automation_plan", "automation_policy"],
                gates=["schedule_install"],
                priority=85,
            )
        )

    if gates:
        steps.append(
            step(
                "approval_gate_register",
                "approval",
                "approval",
                "Create approval register for gated actions",
                "Review each gate before paid API, LLM spend, index submission, ads, tracking tags, publishing, or schedules.",
                proofs=["growth_roadmap_report", "tool_stack_report", "latest_usage_report"],
                gates=gates,
                priority=65,
            )
        )

    return sorted(steps, key=lambda row: (row["priority"], row["id"]))


def limit_steps(steps: list[dict[str, Any]], max_steps: int) -> list[dict[str, Any]]:
    return steps[:max_steps]


def phase_summary(steps: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in steps:
        summary[row["phase"]] = summary.get(row["phase"], 0) + 1
    return dict(sorted(summary.items()))


def owner_summary(steps: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in steps:
        summary[row["owner"]] = summary.get(row["owner"], 0) + 1
    return dict(sorted(summary.items()))


def build_report(cfg_path: pathlib.Path, max_steps: int = DEFAULT_MAX_STEPS) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    intake = load_yaml(policy_path(cfg, project_root, "project_intake", "seo/project-intake.yaml"))
    tool_stack = load_tool_stack(cfg_path, cfg, project_root)
    growth_roadmap = load_growth_roadmap(cfg_path, cfg, project_root)
    automation = load_automation(cfg_path, cfg, project_root)
    all_steps = build_steps(cfg_path, cfg, intake, tool_stack, growth_roadmap, automation)
    steps = limit_steps(all_steps, max_steps)
    env_names = sorted({name for row in steps for name in row.get("env_names", []) if name and "=" not in name})
    gates = sorted({gate for row in steps for gate in row.get("approval_gates", []) if gate})
    return {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "market": {
            "country": country(cfg, intake),
            "region_profile": cfg.get("region_profile"),
        },
        "business": {
            "project_type": project_type(cfg, intake),
            **business_flags(cfg, intake),
        },
        "limits": {
            "max_steps": max_steps,
            "emitted_steps": len(steps),
            "available_steps": len(all_steps),
        },
        "phase_summary": phase_summary(steps),
        "owner_summary": owner_summary(steps),
        "secret_env_names": env_names,
        "approval_gates": gates,
        "steps": steps,
        "next_actions": [
            "Human fills secret values only in `.env` or provider consoles; this playbook keeps names only.",
            "Run `setup-control-plane.py --write` after secret/policy changes.",
            "Start execution from `growth-roadmap.md` and route the chosen action with `task-router.py`.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    market = report.get("market", {})
    business = report.get("business", {})
    lines = [
        "# seo-cycle onboarding playbook",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Country/profile: {market.get('country')} / {market.get('region_profile')}",
        f"- Project type: {business.get('project_type')}",
        f"- Steps: {report.get('limits', {}).get('emitted_steps')} of {report.get('limits', {}).get('available_steps')}",
        "",
        "## Owner Summary",
    ]
    for owner, count in report.get("owner_summary", {}).items():
        lines.append(f"- {owner}: {count}")
    lines.extend(["", "## Secret Env Names"])
    for name in report.get("secret_env_names", []):
        lines.append(f"- `{name}`")
    lines.extend(
        [
            "",
            "## Checklist",
            "| Priority | Phase | Owner | Step | Gates | Proofs |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.get("steps", []):
        lines.append(
            f"| {row['priority']} | {row['phase']} | {row['owner']} | {row['id']} | "
            f"{', '.join(row.get('approval_gates', [])) or '-'} | {', '.join(row.get('proofs', [])) or '-'} |"
        )
    lines.extend(["", "## Commands"])
    for row in report.get("steps", []):
        if not row.get("commands"):
            continue
        lines.append(f"### {row['id']}")
        for command in row["commands"]:
            lines.append(f"- `{command}`")
    lines.extend(["", "## Next Actions"])
    for item in report.get("next_actions", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Rules",
            "- Do not write secret values into this file, git, prompts, chat, or reports.",
            "- Approval gates are blockers until the human explicitly approves the action and budget.",
            "- Proofs name the artifact or env-name that demonstrates a step was handled; they are not secret values.",
        ]
    )
    return "\n".join(lines) + "\n"


def checklist_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=["priority", "phase", "owner", "id", "title", "approval_gates", "env_names", "proofs", "commands"],
    )
    writer.writeheader()
    for row in report.get("steps", []):
        writer.writerow(
            {
                "priority": row.get("priority"),
                "phase": row.get("phase"),
                "owner": row.get("owner"),
                "id": row.get("id"),
                "title": row.get("title"),
                "approval_gates": ";".join(row.get("approval_gates", [])),
                "env_names": ";".join(row.get("env_names", [])),
                "proofs": ";".join(row.get("proofs", [])),
                "commands": " && ".join(row.get("commands", [])),
            }
        )
    return buffer.getvalue()


def generated_yaml(report: dict[str, Any]) -> str:
    payload = {
        "version": report["version"],
        "generated": report["generated"],
        "project": report.get("project", {}),
        "market": report.get("market", {}),
        "business": report.get("business", {}),
        "limits": report.get("limits", {}),
        "phase_summary": report.get("phase_summary", {}),
        "owner_summary": report.get("owner_summary", {}),
        "secret_env_names": report.get("secret_env_names", []),
        "approval_gates": report.get("approval_gates", []),
        "steps": report.get("steps", []),
    }
    return dump_yaml(payload)


def write_reports(project_root: pathlib.Path, report: dict[str, Any]) -> None:
    markdown = render_markdown(report)
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    write_text(project_root / "seo" / "onboarding.generated.yaml", generated_yaml(report))
    write_text(project_root / "seo" / "setup" / "onboarding-playbook.md", markdown)
    write_text(project_root / "seo" / "setup" / "onboarding-playbook.json", json_text)
    write_text(project_root / "seo" / "setup" / "latest-onboarding-playbook.md", markdown)
    write_text(project_root / "seo" / "setup" / "latest-onboarding-playbook.json", json_text)
    write_text(project_root / "seo" / "setup" / "onboarding-checklist.csv", checklist_csv(report))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write onboarding playbook artifacts under seo/setup.")
    parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS, help="Maximum onboarding steps to emit.")
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
    report = build_report(cfg_path, max_steps=max(1, args.max_steps))
    if args.write:
        write_reports(project_root, report)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
