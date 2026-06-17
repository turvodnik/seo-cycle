#!/usr/bin/env python3
"""Collect WriterZen reports through a persistent browser profile, then import exports."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, rel_path
from seo_cycle_core.reports import write_report_bundle


PROVIDER = "writerzen"
DEFAULT_REPORTS = ["topic_discovery", "keyword_explorer", "keyword_planner", "domain_focus"]
DEFAULT_IMPORT_DIR = "seo/research/writerzen/imports"
DEFAULT_PROFILE_DIR = pathlib.Path.home() / ".codex" / "browser-profiles" / "writerzen"
DEFAULT_NODE_DEPS_DIR = pathlib.Path.home() / ".codex" / "vendor" / "seo-cycle-node"
LOGIN_URL = "https://app.writerzen.net/"


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def setup_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    return {
        "markdown": project_root / "seo" / "setup" / "writerzen-browser-collect.md",
        "json": project_root / "seo" / "setup" / "writerzen-browser-collect.json",
        "latest_markdown": project_root / "seo" / "setup" / "latest-writerzen-browser-collect.md",
        "latest_json": project_root / "seo" / "setup" / "latest-writerzen-browser-collect.json",
    }


def parse_reports(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_REPORTS)
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or list(DEFAULT_REPORTS)


def run_command(command: list[str], cwd: pathlib.Path) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "command": command}


def build_plan(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    provider_cfg = cfg.get("writerzen_provider", {}) if isinstance(cfg.get("writerzen_provider"), dict) else {}
    topic = args.topic or nested_get(cfg, "project.name") or nested_get(cfg, "project.domain") or "writerzen"
    domain = args.domain or nested_get(cfg, "project.domain") or ""
    region = args.region or nested_get(cfg, "locale.country") or nested_get(cfg, "locale.region") or "global"
    import_dir = rel_path(project_root, args.import_dir or provider_cfg.get("import_dir") or DEFAULT_IMPORT_DIR)
    profile_dir = pathlib.Path(args.profile_dir).expanduser() if args.profile_dir else pathlib.Path(provider_cfg.get("browser_profile_dir") or DEFAULT_PROFILE_DIR).expanduser()
    reports = parse_reports(args.reports)
    return {
        "provider": PROVIDER,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "topic": str(topic),
        "domain": str(domain),
        "region": str(region),
        "reports": reports,
        "login_url": args.login_url or provider_cfg.get("login_url") or LOGIN_URL,
        "import_dir": str(import_dir),
        "profile_dir": str(profile_dir),
        "runner": str(skill_root() / "scripts" / "writerzen-browser-runner.mjs"),
        "source_pack_script": str(skill_root() / "scripts" / "writerzen-source-pack.py"),
        "node_deps_dir": str(pathlib.Path(args.node_deps_dir).expanduser() if args.node_deps_dir else DEFAULT_NODE_DEPS_DIR),
        "browser_channel": args.browser_channel,
        "headless": bool(args.headless),
        "manual_fallback_seconds": args.manual_fallback_seconds,
        "timeout_seconds": args.timeout_seconds,
        "login_timeout_seconds": args.login_timeout_seconds,
        "result_wait_seconds": args.result_wait_seconds,
        "create_missing": not args.skip_create_missing,
        "force_new_report": bool(args.force_new_report),
        "export_format": args.export_format,
        "stores_password": False,
        "writes_to_site": False,
        "paid_api_used": False,
        "mode": "browser_collect_then_import",
    }


def browser_command(plan: dict[str, Any], result_file: pathlib.Path, args: argparse.Namespace) -> list[str]:
    command = [
        "node",
        plan["runner"],
        "--topic",
        plan["topic"],
        "--domain",
        plan["domain"],
        "--login-url",
        plan["login_url"],
        "--profile-dir",
        plan["profile_dir"],
        "--import-dir",
        plan["import_dir"],
        "--result-file",
        str(result_file),
        "--browser-channel",
        plan["browser_channel"],
        "--timeout-seconds",
        str(plan["timeout_seconds"]),
        "--login-timeout-seconds",
        str(plan["login_timeout_seconds"]),
        "--result-wait-seconds",
        str(plan["result_wait_seconds"]),
        "--manual-fallback-seconds",
        str(plan["manual_fallback_seconds"]),
    ]
    if not plan["create_missing"]:
        command.append("--skip-create-missing")
    if plan["force_new_report"]:
        command.append("--force-new-report")
    for report in plan["reports"]:
        command.extend(["--report", report])
    if args.headless:
        command.append("--headless")
    if args.keep_open:
        command.append("--keep-open")
    return command


def ensure_browser_runtime(plan: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    deps_dir = pathlib.Path(plan["node_deps_dir"]).expanduser()
    package_path = deps_dir / "node_modules" / "playwright-core" / "package.json"
    if package_path.exists():
        return {"status": "ready", "node_modules": str(deps_dir / "node_modules"), "installed": False}
    if args.skip_install_browser_runtime:
        return {
            "status": "missing",
            "node_modules": str(deps_dir / "node_modules"),
            "installed": False,
            "error": "playwright-core is missing and --skip-install-browser-runtime was set.",
        }
    if not shutil.which("npm"):
        return {"status": "missing_npm", "node_modules": str(deps_dir / "node_modules"), "installed": False}
    deps_dir.mkdir(parents=True, exist_ok=True)
    command = ["npm", "install", "--prefix", str(deps_dir), "playwright-core@latest"]
    env = os.environ.copy()
    env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
    proc = subprocess.run(command, text=True, capture_output=True, check=False, env=env)
    return {
        "status": "ready" if proc.returncode == 0 and package_path.exists() else "install_failed",
        "node_modules": str(deps_dir / "node_modules"),
        "installed": proc.returncode == 0,
        "command": command,
        "exit_code": proc.returncode,
        "stderr": proc.stderr[-2000:],
    }


def import_downloads(cfg_path: pathlib.Path, plan: dict[str, Any], downloads: list[str], args: argparse.Namespace) -> dict[str, Any]:
    if args.no_import_after:
        return {"status": "skipped", "reason": "--no-import-after"}
    command = [
        sys.executable,
        plan["source_pack_script"],
        str(cfg_path),
        "--topic",
        plan["topic"],
        "--region",
        plan["region"],
        "--write",
        "--format",
        "json",
    ]
    for download in downloads:
        command.extend(["--export-file", download])
    if not downloads:
        command.extend(["--import-dir", plan["import_dir"]])
    result = run_command(command, pathlib.Path(plan["project_root"]))
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(result["stdout"] or "{}")
    except json.JSONDecodeError:
        parsed = {}
    return {
        "status": "ok" if result["exit_code"] == 0 else "failed",
        "command": result["command"],
        "exit_code": result["exit_code"],
        "stderr": result["stderr"][-2000:],
        "report": parsed,
    }


def render_markdown(report: dict[str, Any]) -> str:
    plan = report["plan"]
    browser = report.get("browser", {})
    importer = report.get("importer", {})
    lines = [
        "# WriterZen Browser Collect",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Status: `{report['status']}`",
        f"- Topic: {plan['topic']}",
        f"- Region: {plan['region']}",
        f"- Reports: {', '.join(plan['reports'])}",
        f"- Import dir: `{plan['import_dir']}`",
        f"- Browser profile: `{plan['profile_dir']}`",
        f"- Stores password: {plan['stores_password']}",
        "",
        "## Browser Result",
        f"- Status: `{browser.get('status', 'not_run')}`",
        f"- Downloads: {len(browser.get('downloads') or [])}",
    ]
    for item in browser.get("results") or []:
        lines.append(f"- {item.get('report')}: `{item.get('status')}` ({', '.join(item.get('actions') or [])})")
    lines.extend(["", "## Import Result", f"- Status: `{importer.get('status', 'not_run')}`"])
    if importer.get("report"):
        lines.append(f"- Source-pack status: `{importer['report'].get('status')}`")
        latest = (importer["report"].get("paths") or {}).get("latest_markdown")
        if latest:
            lines.append(f"- Latest distillate: `{latest}`")
    if report.get("next_actions"):
        lines.extend(["", "## Next Actions"])
        lines.extend(f"- {action}" for action in report["next_actions"])
    return "\n".join(lines) + "\n"


def write_report(project_root: pathlib.Path, report: dict[str, Any]) -> None:
    paths = setup_paths(project_root)
    markdown = render_markdown(report)
    write_report_bundle(paths, markdown, report, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--topic", help="Seed topic/query for WriterZen reports.")
    parser.add_argument("--domain", help="Domain seed for Domain Focus.")
    parser.add_argument("--region", help="Target region label.")
    parser.add_argument("--reports", help="Comma-separated reports: topic_discovery,keyword_explorer,keyword_planner,domain_focus.")
    parser.add_argument("--login-url", help="WriterZen login/app URL.")
    parser.add_argument("--profile-dir", help=f"Persistent browser profile outside the repo. Default: {DEFAULT_PROFILE_DIR}")
    parser.add_argument("--import-dir", help=f"Project import dir. Default: {DEFAULT_IMPORT_DIR}")
    parser.add_argument("--browser-channel", default="chrome", help="Playwright browser channel: chrome, msedge, chromium via auto/empty.")
    parser.add_argument("--node-deps-dir", help=f"Shared Node dependency cache. Default: {DEFAULT_NODE_DEPS_DIR}")
    parser.add_argument("--skip-install-browser-runtime", action="store_true", help="Do not auto-install playwright-core into the shared cache.")
    parser.add_argument("--headless", action="store_true", help="Run headless. Use headed for first login/2FA.")
    parser.add_argument("--keep-open", action="store_true", help="Leave browser open after collection.")
    parser.add_argument("--manual-fallback-seconds", type=int, default=0, help="If export button is not found, wait for a manual download for N seconds.")
    parser.add_argument("--skip-create-missing", action="store_true", help="Do not click New/Create if the report input is not visible.")
    parser.add_argument("--force-new-report", action="store_true", help="Start a fresh report instead of reusing an existing one when the UI offers that option.")
    parser.add_argument("--export-format", choices=("csv", "xlsx"), default="csv", help="Preferred export format when WriterZen opens an export menu.")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--login-timeout-seconds", type=int, default=600)
    parser.add_argument("--result-wait-seconds", type=int, default=15)
    parser.add_argument("--no-import-after", action="store_true", help="Collect downloads but do not run writerzen-source-pack.py.")
    parser.add_argument("--dry-run", action="store_true", help="Write/print the browser plan without opening WriterZen.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2

    plan = build_plan(cfg_path, args)
    project_root = pathlib.Path(plan["project_root"])
    pathlib.Path(plan["import_dir"]).mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "provider": PROVIDER,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "status": "planned" if args.dry_run else "started",
        "plan": plan,
        "browser": {},
        "importer": {},
        "next_actions": [],
    }

    if args.dry_run:
        report["browser_command"] = browser_command(plan, pathlib.Path("<result-file.json>"), args)
        report["next_actions"] = [
            "Run without --dry-run to open WriterZen in a persistent browser profile.",
            "For first run, keep headed mode and log in manually; the profile is outside the project repo.",
            "If WriterZen UI changes, rerun with --manual-fallback-seconds 120 and export manually while the script watches downloads.",
        ]
    else:
        if not shutil.which("node"):
            report["status"] = "blocked"
            report["browser"] = {"status": "missing_node"}
            report["next_actions"] = ["Install Node.js/npm so the WriterZen browser collector can run."]
        else:
            runtime = ensure_browser_runtime(plan, args)
            report["browser_runtime"] = runtime
            if runtime.get("status") != "ready":
                report["status"] = "blocked"
                report["browser"] = {"status": runtime.get("status"), "stderr": runtime.get("stderr", "")}
                if runtime.get("status") == "missing_npm":
                    report["next_actions"].append("Install npm or preinstall playwright-core into the shared cache.")
                elif runtime.get("status") == "missing":
                    report["next_actions"].append("Run without --skip-install-browser-runtime or install playwright-core manually in the shared cache.")
                else:
                    report["next_actions"].append("Browser runtime install failed; inspect seo/setup/writerzen-browser-collect.json stderr.")
                if args.write:
                    write_report(project_root, report)
                if args.format == "json":
                    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
                else:
                    print(render_markdown(report), end="")
                return 1
            with tempfile.TemporaryDirectory(prefix="writerzen-browser-") as tmp:
                result_file = pathlib.Path(tmp) / "writerzen-browser-result.json"
                command = browser_command(plan, result_file, args)
                env = os.environ.copy()
                env["WRITERZEN_EXPORT_FORMAT"] = str(plan.get("export_format") or "csv")
                env["WRITERZEN_PLAYWRIGHT_NODE_MODULES"] = str(runtime["node_modules"])
                proc = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False, env=env)
                browser_proc = {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "command": command}
                browser_payload: dict[str, Any] = {}
                if result_file.exists():
                    try:
                        browser_payload = json.loads(result_file.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        browser_payload = {}
                browser_payload.setdefault("status", "failed" if browser_proc["exit_code"] else "done")
                browser_payload["exit_code"] = browser_proc["exit_code"]
                browser_payload["stderr"] = browser_proc["stderr"][-3000:]
                report["browser"] = browser_payload
                downloads = [str(path) for path in browser_payload.get("downloads", [])]
                report["importer"] = import_downloads(cfg_path, plan, downloads, args)
                imported_status = (report["importer"].get("report") or {}).get("status")
                if browser_proc["exit_code"]:
                    report["status"] = "browser_failed"
                elif report["importer"].get("status") != "ok":
                    report["status"] = "import_failed"
                elif imported_status in {"ready", "cache_hit"}:
                    report["status"] = "ready"
                else:
                    report["status"] = "no_downloads"
                if report["status"] == "no_downloads" or browser_payload.get("status") in {"no_downloads", "download_not_captured"} or not downloads:
                    report["next_actions"].append("No WriterZen downloads were captured. Run again with --manual-fallback-seconds 120 or export CSV/XLSX manually into seo/research/writerzen/imports/.")
                if browser_proc["exit_code"] != 0:
                    report["next_actions"].append("If Playwright cannot launch Chrome, run with --browser-channel auto after installing Playwright browsers.")

    if args.write:
        write_report(project_root, report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0 if report["status"] in {"planned", "ready"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
