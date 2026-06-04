#!/usr/bin/env python3
"""Generate safe seo-cycle automation plans, cron lines, and launchd plists.

Default behavior is read-only: print a plan. Use `--write` to create files under
`seo/automations/`. This script does not install crontabs or launchd jobs unless
all local policy gates allow schedules and `--install-cron` is explicitly passed.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

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

RUNNER_COMMANDS = {
    "content_writer": "content",
    "audit": "audit",
    "refresh": "refresh",
    "keyword_replenish": "keyword",
    "deindex_check": "deindex",
}

DEFAULT_AUTOMATION_CRON = {
    "usage_budget_watch": "0 7 * * 1",
    "weekly_read_only_health": "0 8 * * 1",
    "monthly_keyword_refresh": "0 10 1 * *",
    "monthly_ai_visibility": "0 11 2 * *",
    "ecommerce_feed_quality": "0 8 * * 2",
    "local_seo_reputation": "0 8 * * 4",
}


@dataclass(frozen=True)
class Task:
    task_id: str
    cron: str
    command: str
    mode: str
    source: str
    enabled: bool


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


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def shell_quote(value: pathlib.Path | str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def automation_policy_path(cfg: dict[str, Any], project_root: pathlib.Path) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get("automation_policy", "seo/automation-policy.yaml"))


def governance_allows_schedules(cfg: dict[str, Any], policy: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    gov_automation = governance.get("automation_policy", {}) if isinstance(governance.get("automation_policy"), dict) else {}
    if gov_automation.get("create_schedules") is not True:
        reasons.append("governance.automation_policy.create_schedules is not true")
    if policy.get("create_schedules") is not True:
        reasons.append("seo/automation-policy.yaml create_schedules is not true")
    mode = policy.get("default_mode") or gov_automation.get("default_mode")
    if mode not in ("report_only", "approval_only", "auto_with_caps"):
        reasons.append(f"automation mode {mode!r} does not allow schedules")
    return not reasons, reasons


def command_for_policy_task(project_root: pathlib.Path, task_id: str, mode: str) -> str:
    root = skill_root()
    if task_id == "usage_budget_watch":
        return (
            f"cd {shell_quote(project_root)} && "
            f"python3 {shell_quote(root / 'scripts/usage-ledger.py')} report --write && "
            f"python3 {shell_quote(root / 'scripts/governance-report.py')} --format md > seo/automations/latest-governance.md"
        )
    if task_id == "weekly_read_only_health":
        return (
            f"cd {shell_quote(project_root)} && "
            f"python3 {shell_quote(root / 'scripts/validate-config.py')} >/tmp/seo-cycle-validate.log && "
            f"python3 {shell_quote(root / 'scripts/governance-report.py')} --format md > seo/automations/latest-governance.md && "
            f"bash {shell_quote(root / 'scripts/monthly-runner.sh')} status --dry-run"
        )
    if task_id == "monthly_ai_visibility":
        return f"cd {shell_quote(project_root)} && python3 {shell_quote(root / 'scripts/governance-report.py')} --format md > seo/automations/latest-ai-visibility-governance.md"
    if task_id == "monthly_keyword_refresh":
        dry = " --dry-run" if mode != "auto_with_caps" else ""
        return f"cd {shell_quote(project_root)} && bash {shell_quote(root / 'scripts/monthly-runner.sh')} keyword{dry}"
    if task_id == "ecommerce_feed_quality":
        return f"cd {shell_quote(project_root)} && bash {shell_quote(root / 'scripts/monthly-runner.sh')} status --dry-run"
    if task_id == "local_seo_reputation":
        return f"cd {shell_quote(project_root)} && bash {shell_quote(root / 'scripts/monthly-runner.sh')} status --dry-run"
    return f"cd {shell_quote(project_root)} && bash {shell_quote(root / 'scripts/monthly-runner.sh')} status --dry-run"


def build_tasks(cfg: dict[str, Any], policy: dict[str, Any], project_root: pathlib.Path, include_disabled: bool) -> list[Task]:
    root = skill_root()
    tasks: list[Task] = []
    monthly = cfg.get("monthly_automation", {}) if isinstance(cfg.get("monthly_automation"), dict) else {}
    schedule = monthly.get("schedule", {}) if isinstance(monthly.get("schedule"), dict) else {}
    monthly_enabled = bool(monthly.get("enabled"))

    for key, runner_cmd in RUNNER_COMMANDS.items():
        cron = schedule.get(key)
        if not cron:
            continue
        enabled = monthly_enabled
        if enabled or include_disabled:
            tasks.append(
                Task(
                    task_id=f"monthly_{key}",
                    cron=cron,
                    command=f"cd {shell_quote(project_root)} && bash {shell_quote(root / 'scripts/monthly-runner.sh')} {runner_cmd}",
                    mode="approval_only",
                    source="monthly_automation.schedule",
                    enabled=enabled,
                )
            )

    planned = policy.get("planned_automations", {}) if isinstance(policy.get("planned_automations"), dict) else {}
    for task_id, task_cfg in planned.items():
        if not isinstance(task_cfg, dict):
            continue
        enabled = bool(task_cfg.get("enabled"))
        if not enabled and not include_disabled:
            continue
        mode = task_cfg.get("mode", policy.get("default_mode", "approval_only"))
        cron = task_cfg.get("cron") or DEFAULT_AUTOMATION_CRON.get(task_id, "0 9 * * 1")
        tasks.append(
            Task(
                task_id=task_id,
                cron=cron,
                command=command_for_policy_task(project_root, task_id, mode),
                mode=mode,
                source="automation-policy.yaml",
                enabled=enabled,
            )
        )
    return tasks


def cron_lines(tasks: list[Task], include_disabled: bool) -> list[str]:
    lines = [
        "# seo-cycle generated crontab",
        "# Review before installing. Disabled tasks are commented out.",
    ]
    for task in tasks:
        prefix = "" if task.enabled else "# "
        if task.enabled or include_disabled:
            lines.append(f"{prefix}{task.cron} {task.command} # seo-cycle:{task.task_id} mode={task.mode}")
    return lines


def launchd_interval_from_cron(cron: str) -> dict[str, int] | None:
    parts = cron.split()
    if len(parts) != 5:
        return None
    minute, hour, _dom, _mon, weekday = parts
    if not minute.isdigit() or not hour.isdigit():
        return None
    interval = {"Minute": int(minute), "Hour": int(hour)}
    if weekday.isdigit():
        # launchd: 0 and 7 are Sunday; cron in this project uses 1=Monday.
        interval["Weekday"] = int(weekday)
    return interval


def launchd_plist(task: Task, project_root: pathlib.Path) -> str:
    label = f"com.seocycle.{project_root.name}.{task.task_id}".replace("_", "-").replace(" ", "-")
    interval = launchd_interval_from_cron(task.cron)
    interval_xml = ""
    if interval:
        items = "\n".join(f"    <key>{escape(key)}</key><integer>{value}</integer>" for key, value in interval.items())
        interval_xml = f"<key>StartCalendarInterval</key>\n  <dict>\n{items}\n  </dict>"
    else:
        interval_xml = "<key>Disabled</key><true/>"
    log_dir = project_root / "seo" / "automations" / "logs"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{escape(label)}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>{escape(task.command)}</string>
  </array>
  <key>WorkingDirectory</key><string>{escape(str(project_root))}</string>
  {interval_xml}
  <key>StandardOutPath</key><string>{escape(str(log_dir / f"{task.task_id}.out.log"))}</string>
  <key>StandardErrorPath</key><string>{escape(str(log_dir / f"{task.task_id}.err.log"))}</string>
</dict>
</plist>
"""


def render_markdown(cfg: dict[str, Any], policy: dict[str, Any], project_root: pathlib.Path, tasks: list[Task], allowed: bool, reasons: list[str]) -> str:
    project = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    lines = [
        "# seo-cycle automation plan",
        "",
        f"- Project: {project.get('name', '?')} ({project.get('domain', '?')})",
        f"- Project root: {project_root}",
        f"- Policy mode: {policy.get('default_mode', 'not_configured')}",
        f"- Schedule install allowed: {'yes' if allowed else 'no'}",
    ]
    if reasons:
        lines.append(f"- Blockers: {', '.join(reasons)}")
    lines.extend(["", "## Tasks", "| Task | Enabled | Cron | Mode | Source |", "| --- | --- | --- | --- | --- |"])
    for task in tasks:
        lines.append(f"| {task.task_id} | {task.enabled} | `{task.cron}` | {task.mode} | {task.source} |")
    lines.extend(["", "## Install Guard", ""])
    lines.append("This file is generated. Do not install schedules unless governance and automation-policy both allow it.")
    lines.append("Use `--write` to create files, and `--install-cron` only after reviewing `seo/automations/crontab.txt`.")
    return "\n".join(lines) + "\n"


def write_outputs(project_root: pathlib.Path, cfg: dict[str, Any], policy: dict[str, Any], tasks: list[Task], allowed: bool, reasons: list[str]) -> pathlib.Path:
    out_dir = project_root / "seo" / "automations"
    launchd_dir = out_dir / "launchd"
    logs_dir = out_dir / "logs"
    launchd_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "automation-plan.md").write_text(render_markdown(cfg, policy, project_root, tasks, allowed, reasons), encoding="utf-8")
    (out_dir / "crontab.txt").write_text("\n".join(cron_lines(tasks, include_disabled=True)) + "\n", encoding="utf-8")
    payload = {
        "project_root": str(project_root),
        "schedule_install_allowed": allowed,
        "blockers": reasons,
        "tasks": [task.__dict__ for task in tasks],
    }
    (out_dir / "automation-plan.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for task in tasks:
        if task.enabled:
            (launchd_dir / f"{task.task_id}.plist").write_text(launchd_plist(task, project_root), encoding="utf-8")
    return out_dir


def install_cron(project_root: pathlib.Path, tasks: list[Task], allowed: bool, reasons: list[str]) -> None:
    if not allowed:
        raise RuntimeError("Schedule install blocked: " + "; ".join(reasons))
    if os.environ.get("SEO_CYCLE_ALLOW_SCHEDULE_INSTALL") != "1":
        raise RuntimeError("Set SEO_CYCLE_ALLOW_SCHEDULE_INSTALL=1 to install crontab")
    active_lines = [line for line in cron_lines(tasks, include_disabled=False) if line and not line.startswith("#")]
    existing = subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False)
    old = existing.stdout if existing.returncode == 0 else ""
    filtered = "\n".join(line for line in old.splitlines() if "seo-cycle:" not in line)
    new_cron = (filtered + "\n" if filtered.strip() else "") + "\n".join(active_lines) + "\n"
    subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--write", action="store_true", help="Write files under seo/automations/")
    parser.add_argument("--include-disabled", action="store_true", help="Include disabled tasks in generated outputs.")
    parser.add_argument("--install-cron", action="store_true", help="Install active tasks into user crontab when all guards allow it.")
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

    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    policy_path = automation_policy_path(cfg, project_root)
    policy = load_yaml(policy_path)
    allowed, reasons = governance_allows_schedules(cfg, policy)
    tasks = build_tasks(cfg, policy, project_root, include_disabled=args.include_disabled)

    if args.write:
        out_dir = write_outputs(project_root, cfg, policy, tasks, allowed, reasons)
        print(f"Wrote {out_dir}")
    elif args.format == "json":
        print(json.dumps({"tasks": [task.__dict__ for task in tasks], "allowed": allowed, "blockers": reasons}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(cfg, policy, project_root, tasks, allowed, reasons), end="")

    if args.install_cron:
        try:
            install_cron(project_root, tasks, allowed, reasons)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print("Installed seo-cycle crontab entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
