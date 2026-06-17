#!/usr/bin/env python3
"""Build a safe manual apply plan from setup-questionnaire answers.

The script reads `seo/setup/setup-questionnaire.csv`, keeps only filled,
non-secret answers, and writes a reviewable plan. It never edits project config
or stores rejected secret-like values.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import re
import sys
from typing import Any

from seo_cycle_core.reports import write_artifacts

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

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"ya29\."),
    re.compile(r"xox[baprs]-"),
    re.compile(r"(^|[^A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----"),
    re.compile(r"(api[_-]?key|client_secret|secret|refresh_token|access_token|password)\s*[:=]", re.IGNORECASE),
    re.compile(r'"private_key"\s*:', re.IGNORECASE),
]


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


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get(key, default))


def has_secret_like_value(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_PATTERNS)


def split_list(value: str) -> list[str]:
    normalized = value.replace("\n", ";").replace("|", ";")
    if ";" in normalized:
        parts = normalized.split(";")
    elif "," in normalized:
        parts = normalized.split(",")
    else:
        parts = [normalized]
    return [part.strip() for part in parts if part.strip()]


def parse_number(value: str) -> int | float | str:
    stripped = value.strip().replace(",", ".")
    try:
        number = float(stripped)
    except ValueError:
        return value.strip()
    return int(number) if number.is_integer() else number


def parse_answer(value: str, answer_format: str) -> Any:
    stripped = value.strip()
    if answer_format == "number_or_policy":
        return parse_number(stripped)
    if answer_format in {"text_or_list", "policy_or_category_list", "urls_or_structured_nap"}:
        parts = split_list(stripped)
        return parts if len(parts) > 1 else (parts[0] if parts else "")
    return stripped


def target_path_for(field: str) -> str:
    mapping = {
        "budget.monthly_paid_api_usd_cap": "governance.budget_policy.monthly_paid_api_usd_cap",
        "budget.subscriptions": "governance.subscriptions",
        "budget.token_policy": "governance.token_policy",
        "budget.spend_guard": "seo/setup/spend-guard.md",
        "local.business_profile_urls": "business_profile.gbp_url / business_profile.yandex_business_url / business_profile.2gis_url",
        "local.nap": "business_profile.address / business_profile.telephone / business_profile.opening_hours",
        "local.competitors": "business_profile.competitors",
        "ecommerce.feed_policy": "marketing.ecommerce_feeds / seo/access-setup-runbook.md",
        "ecommerce.priority_products": "business.priority_products_or_services",
        "ecommerce.merchant_policy": "seo/access-setup-runbook.md",
        "tools.tool_stack": "seo/tool-stack.generated.yaml",
        "tools.free_first": "seo/tool-stack.generated.yaml",
        "tools.approval_required": "seo/tool-stack.generated.yaml",
        "automation.recommendations": "seo/automations/automation-recommendations.md",
        "automation.context_pack": "seo/setup/context-pack.md",
        "automation.launch_plan": "seo/setup/launch-plan.md",
    }
    if field in mapping:
        return mapping[field]
    return field


def value_summary(value: Any) -> str:
    if isinstance(value, list):
        text = "; ".join(str(item) for item in value)
    else:
        text = str(value)
    return text if len(text) <= 160 else text[:157] + "..."


def read_questionnaire(path: pathlib.Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_report(cfg_path: pathlib.Path, questionnaire_path: pathlib.Path | None = None) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    questionnaire = questionnaire_path or policy_path(cfg, project_root, "setup_questionnaire_csv", "seo/setup/setup-questionnaire.csv")
    rows = read_questionnaire(questionnaire)
    changes: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    empty_count = 0

    for row in rows:
        field = str(row.get("field") or "").strip()
        answer = str(row.get("answer") or "").strip()
        if not field:
            continue
        if not answer:
            empty_count += 1
            continue
        if has_secret_like_value(answer):
            rejected.append({"field": field, "reason": "secret_like_answer"})
            continue
        answer_format = str(row.get("answer_format") or "text")
        proposed = parse_answer(answer, answer_format)
        changes.append(
            {
                "field": field,
                "category": str(row.get("category") or ""),
                "severity": str(row.get("severity") or ""),
                "target_file": str(row.get("target_file") or ""),
                "target_path": target_path_for(field),
                "answer_format": answer_format,
                "proposed_value": proposed,
                "answer_summary": value_summary(proposed),
                "follow_up_command": str(row.get("follow_up_command") or "python3 ~/.codex/skills/seo-cycle/scripts/setup-gap-audit.py --write"),
                "apply_mode": "manual_review",
            }
        )

    follow_up_commands = sorted({row["follow_up_command"] for row in changes if row.get("follow_up_command")})
    target_files = sorted({part.strip() for row in changes for part in row.get("target_file", "").split(";") if part.strip()})
    return {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": cfg.get("project", {}),
        "questionnaire_csv": str(questionnaire),
        "row_count": len(rows),
        "accepted_count": len(changes),
        "rejected_count": len(rejected),
        "empty_count": empty_count,
        "answered_fields": [row["field"] for row in changes],
        "target_files": target_files,
        "follow_up_commands": follow_up_commands,
        "changes": changes,
        "rejected": rejected,
        "outputs": {
            "markdown": "seo/setup/setup-answer-plan.md",
            "json": "seo/setup/setup-answer-plan.json",
            "csv": "seo/setup/setup-answer-plan.csv",
            "latest_markdown": "seo/setup/latest-setup-answer-plan.md",
            "latest_json": "seo/setup/latest-setup-answer-plan.json",
        },
        "next_actions": [
            "Review `seo/setup/setup-answer-plan.md`; apply safe values manually to target files.",
            "Do not paste secrets into questionnaire or answer-plan artifacts; keep secrets in `.env` or provider consoles.",
            "Run the listed follow-up commands, then refresh `setup-gap-audit.py --write`.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    lines = [
        "# seo-cycle setup answer plan",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Accepted answers: {report.get('accepted_count')}",
        f"- Rejected answers: {report.get('rejected_count')}",
        f"- Empty rows: {report.get('empty_count')}",
        "",
        "## Changes",
        "| Field | Target file | Target path | Proposed value | Follow-up command |",
        "| --- | --- | --- | --- | --- |",
    ]
    if report.get("changes"):
        for row in report["changes"]:
            lines.append(
                f"| `{row['field']}` | `{row['target_file']}` | `{row['target_path']}` | "
                f"{row['answer_summary']} | `{row['follow_up_command']}` |"
            )
    else:
        lines.append("| - | - | - | No accepted answers. | - |")

    lines.extend(["", "## Rejected"])
    if report.get("rejected"):
        for row in report["rejected"]:
            lines.append(f"- `{row['field']}`: {row['reason']}")
    else:
        lines.append("- none")

    lines.extend(["", "## Next Actions"])
    for item in report.get("next_actions", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def plan_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    fieldnames = ["field", "target_file", "target_path", "answer_summary", "follow_up_command", "apply_mode"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in report.get("changes", []):
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return buffer.getvalue()


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    out_dir = project_root / "seo" / "setup"
    markdown = render_markdown(report)
    write_artifacts(
        text_files={
            out_dir / "setup-answer-plan.md": markdown,
            out_dir / "latest-setup-answer-plan.md": markdown,
            out_dir / "setup-answer-plan.csv": plan_csv(report),
        },
        json_files={
            out_dir / "setup-answer-plan.json": report,
            out_dir / "latest-setup-answer-plan.json": report,
        },
    )
    return out_dir / "setup-answer-plan.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--questionnaire", help="Path to setup-questionnaire.csv")
    parser.add_argument("--write", action="store_true", help="Write seo/setup/setup-answer-plan.md/json/csv.")
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

    questionnaire = pathlib.Path(args.questionnaire).expanduser().resolve() if args.questionnaire else None
    project_root = project_root_for(cfg_path)
    report = build_report(cfg_path, questionnaire)
    if args.write:
        out = write_outputs(project_root, report)
        if args.format == "json":
            print(f"Wrote {out}", file=sys.stderr)
        else:
            print(f"Wrote {out}")
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not args.write:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
