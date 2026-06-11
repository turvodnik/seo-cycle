#!/usr/bin/env python3
"""Safely apply reviewed seo-cycle upgrade policy paths.

This command is intentionally narrow: it only adds missing `policy_files`
entries from the current template to an existing project config. It never
stores secret values, enables paid tools, installs schedules, publishes
content, or changes business/project settings.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import shutil
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: PyYAML is required. Install with `pip3 install pyyaml`.", file=sys.stderr)
    sys.exit(2)

from seo_cycle_core.config import find_config, load_yaml, project_root_for, write_text


YES_ANSWERS = {"yes", "y", "true", "1", "да", "д", "yes_report_only", "yes_for_codex_projects"}
DEFER_ANSWERS = {"defer", "later", "skip_for_now", "not_now", "позже"}
NO_ANSWERS = {"no", "n", "false", "0", "нет", "н", "disabled"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def template_policy_files() -> dict[str, str]:
    template = load_yaml(skill_root() / "config" / "project.template.yaml")
    policy = template.get("policy_files", {}) if isinstance(template.get("policy_files"), dict) else {}
    return {str(key): str(value) for key, value in policy.items()}


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def questionnaire_path(project_root: pathlib.Path, raw: str | None) -> pathlib.Path:
    return pathlib.Path(raw).expanduser().resolve() if raw else project_root / "seo" / "setup" / "upgrade-questionnaire.csv"


def read_questionnaire(path: pathlib.Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def split_keys(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def normalized_decision(row: dict[str, str], *, use_defaults: bool) -> str:
    answer = str(row.get("answer") or "").strip().lower()
    if answer:
        return answer
    if use_defaults:
        return str(row.get("default_answer") or "").strip().lower()
    return ""


def plan_changes(
    cfg: dict[str, Any],
    template_policy: dict[str, str],
    rows: list[dict[str, str]],
    *,
    use_defaults: bool,
    all_missing_policy_defaults: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    planned: dict[str, dict[str, Any]] = {}
    skipped: list[dict[str, Any]] = []

    if all_missing_policy_defaults:
        for key, value in template_policy.items():
            if key not in policy_files:
                planned[key] = {"key": key, "path": value, "feature": "all_missing_policy_defaults", "decision": "yes"}

    for row in rows:
        decision = normalized_decision(row, use_defaults=use_defaults)
        feature = row.get("feature") or row.get("id") or "unknown"
        keys = split_keys(row.get("missing_policy_keys"))
        if not keys:
            continue
        if decision in NO_ANSWERS or decision in DEFER_ANSWERS or not decision:
            skipped.append({"feature": feature, "decision": decision or "blank", "missing_policy_keys": keys})
            continue
        if decision not in YES_ANSWERS:
            skipped.append({"feature": feature, "decision": decision, "missing_policy_keys": keys, "reason": "unsupported_answer"})
            continue
        for key in keys:
            if key in policy_files:
                skipped.append({"feature": feature, "decision": decision, "missing_policy_keys": [key], "reason": "already_configured"})
                continue
            if key not in template_policy:
                skipped.append({"feature": feature, "decision": decision, "missing_policy_keys": [key], "reason": "not_in_template"})
                continue
            planned[key] = {"key": key, "path": template_policy[key], "feature": feature, "decision": decision}

    return list(planned.values()), skipped


def apply_changes(cfg_path: pathlib.Path, cfg: dict[str, Any], planned: list[dict[str, Any]]) -> pathlib.Path | None:
    if not planned:
        return None
    backup = cfg_path.with_suffix(cfg_path.suffix + f".bak-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(cfg_path, backup)
    updated = dict(cfg)
    policy_files = dict(updated.get("policy_files", {}) if isinstance(updated.get("policy_files"), dict) else {})
    for row in planned:
        policy_files[row["key"]] = row["path"]
    updated["policy_files"] = policy_files
    cfg_path.write_text(dump_yaml(updated), encoding="utf-8")
    return backup


def build_report(
    cfg_path: pathlib.Path,
    *,
    answers: str | None = None,
    use_defaults: bool = False,
    all_missing_policy_defaults: bool = False,
    apply: bool = False,
) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    template_policy = template_policy_files()
    q_path = questionnaire_path(project_root, answers)
    rows = read_questionnaire(q_path)
    planned, skipped = plan_changes(
        cfg,
        template_policy,
        rows,
        use_defaults=use_defaults,
        all_missing_policy_defaults=all_missing_policy_defaults,
    )
    backup = apply_changes(cfg_path, cfg, planned) if apply else None
    return {
        "audit_id": "project_upgrade_apply",
        "generated": utc_now(),
        "mode": "apply" if apply else "dry_run",
        "config": str(cfg_path),
        "project_root": str(project_root),
        "questionnaire": str(q_path),
        "questionnaire_exists": q_path.exists(),
        "use_defaults": use_defaults,
        "all_missing_policy_defaults": all_missing_policy_defaults,
        "summary": {
            "planned_changes": len(planned),
            "applied_changes": len(planned) if apply else 0,
            "skipped_rows": len(skipped),
            "questionnaire_rows": len(rows),
        },
        "planned_policy_files": planned,
        "skipped": skipped,
        "backup": str(backup) if backup else None,
        "rules": [
            "Only missing policy_files entries are added.",
            "No secret values, env values, paid API actions, schedules, publishing, or index submissions are changed.",
            "A backup is created before applying changes.",
            "Run setup-control-plane.py --write after applying upgrades.",
        ],
        "next_actions": [
            "Review this dry run before applying, or inspect the backup after apply.",
            "Run project-upgrade-assistant.py --write to refresh the questionnaire if planned changes look stale.",
            "Run setup-control-plane.py --write after apply so generated artifacts and project journey are refreshed.",
        ],
        "paths": {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# seo-cycle project upgrade apply",
        "",
        f"- Generated: {report['generated']}",
        f"- Mode: `{report['mode']}`",
        f"- Config: `{report['config']}`",
        f"- Questionnaire: `{report['questionnaire']}`",
        f"- Questionnaire exists: `{report['questionnaire_exists']}`",
        f"- Planned changes: `{report['summary']['planned_changes']}`",
        f"- Applied changes: `{report['summary']['applied_changes']}`",
        f"- Backup: `{report.get('backup') or '-'}`",
        "",
        "## Planned Policy Files",
        "| Key | Path | Feature | Decision |",
        "| --- | --- | --- | --- |",
    ]
    if not report["planned_policy_files"]:
        lines.append("| - | - | - | - |")
    for row in report["planned_policy_files"]:
        lines.append(f"| `{row['key']}` | `{row['path']}` | `{row['feature']}` | `{row['decision']}` |")

    lines.extend(["", "## Skipped"])
    if not report["skipped"]:
        lines.append("- Nothing skipped.")
    for row in report["skipped"][:50]:
        lines.append(f"- `{row.get('feature')}` decision=`{row.get('decision')}` keys={', '.join(row.get('missing_policy_keys', []))} {row.get('reason', '')}")

    lines.extend(["", "## Rules"])
    lines.extend(f"- {rule}" for rule in report["rules"])
    lines.extend(["", "## Next Actions"])
    lines.extend(f"- {action}" for action in report["next_actions"])
    return "\n".join(lines) + "\n"


def planned_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["key", "path", "feature", "decision"])
    writer.writeheader()
    for row in report.get("planned_policy_files", []):
        writer.writerow(row)
    return buffer.getvalue()


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    setup_dir = project_root / "seo" / "setup"
    paths = {
        "markdown": setup_dir / "project-upgrade-apply.md",
        "json": setup_dir / "project-upgrade-apply.json",
        "csv": setup_dir / "project-upgrade-apply.csv",
        "latest_markdown": setup_dir / "latest-project-upgrade-apply.md",
        "latest_json": setup_dir / "latest-project-upgrade-apply.json",
    }
    report["paths"] = {key: str(path) for key, path in paths.items()}
    write_text(paths["markdown"], render_markdown(report))
    write_text(paths["json"], json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_text(paths["csv"], planned_csv(report))
    write_text(paths["latest_markdown"], render_markdown(report))
    write_text(paths["latest_json"], json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return paths["markdown"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely apply reviewed seo-cycle policy-file upgrades.")
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--answers", help="Path to upgrade-questionnaire.csv. Defaults to seo/setup/upgrade-questionnaire.csv.")
    parser.add_argument("--use-defaults", action="store_true", help="Treat blank answers as their default_answer values.")
    parser.add_argument("--all-missing-policy-defaults", action="store_true", help="Plan every missing template policy_files key, even without questionnaire rows.")
    parser.add_argument("--apply", action="store_true", help="Apply planned policy_files additions with a backup. Default is dry-run.")
    parser.add_argument("--write", action="store_true", help="Write seo/setup/project-upgrade-apply artifacts.")
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

    report = build_report(
        cfg_path,
        answers=args.answers,
        use_defaults=args.use_defaults,
        all_missing_policy_defaults=args.all_missing_policy_defaults,
        apply=args.apply,
    )
    if args.write:
        write_outputs(project_root_for(cfg_path), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
