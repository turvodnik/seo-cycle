#!/usr/bin/env python3
"""Capture a GSC Pages issue export through the browser and optionally build the indexing queue."""

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

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, rel_display, rel_path
from seo_cycle_core.technical_artifacts import write_technical_report


DEFAULT_PROFILE_DIR = pathlib.Path.home() / ".codex" / "browser-profiles" / "gsc"
DEFAULT_NODE_DEPS_DIR = pathlib.Path.home() / ".codex" / "vendor" / "seo-cycle-node"
DEFAULT_IMPORT_DIR = "seo/technical/gsc-indexing/imports"


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def ensure_browser_runtime(args: argparse.Namespace) -> dict[str, Any]:
    deps_dir = pathlib.Path(args.node_deps_dir).expanduser() if args.node_deps_dir else DEFAULT_NODE_DEPS_DIR
    package_path = deps_dir / "node_modules" / "playwright-core" / "package.json"
    if package_path.exists():
        return {"status": "ready", "node_modules": str(deps_dir / "node_modules"), "installed": False}
    if args.skip_install_browser_runtime:
        return {"status": "missing", "node_modules": str(deps_dir / "node_modules"), "installed": False}
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


def runner_command(args: argparse.Namespace, site_url: str, import_dir: pathlib.Path, result_file: pathlib.Path, profile_dir: pathlib.Path) -> list[str]:
    command = [
        "node",
        str(skill_root() / "scripts" / "gsc-indexing-export-runner.mjs"),
        "--site-url",
        site_url,
        "--profile-dir",
        str(profile_dir),
        "--import-dir",
        str(import_dir),
        "--result-file",
        str(result_file),
        "--browser-channel",
        args.browser_channel,
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--manual-fallback-seconds",
        str(args.manual_fallback_seconds),
    ]
    if args.issue_url:
        command.extend(["--issue-url", args.issue_url])
    if args.headless:
        command.append("--headless")
    if args.keep_open:
        command.append("--keep-open")
    return command


def build_queue(cfg_path: pathlib.Path, downloads: list[str], args: argparse.Namespace, project_root: pathlib.Path) -> dict[str, Any]:
    if not args.build_queue:
        return {"status": "skipped"}
    command = [
        sys.executable,
        str(skill_root() / "scripts" / "gsc-indexing-queue.py"),
        str(cfg_path),
        "--top",
        str(args.top),
        "--write",
        "--format",
        "json",
    ]
    for download in downloads:
        command.extend(["--gsc-discovered-file", download])
    for value in args.gsc_performance_file or []:
        command.extend(["--gsc-performance-file", value])
    for value in args.woocommerce_file or []:
        command.extend(["--woocommerce-file", value])
    for value in args.sitemap or []:
        command.extend(["--sitemap", value])
    for value in args.sitemap_file or []:
        command.extend(["--sitemap-file", value])
    if args.technical_check:
        command.append("--technical-check")
    proc = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False)
    try:
        report = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        report = {}
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "command": command,
        "exit_code": proc.returncode,
        "stderr": proc.stderr[-2000:],
        "report": report,
    }


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    domain = nested_get(cfg, "project.domain") or ""
    site_url = args.site_url or os.environ.get("GSC_SITE_URL") or (f"sc-domain:{domain}" if domain else "")
    import_dir = rel_path(project_root, args.import_dir or DEFAULT_IMPORT_DIR)
    profile_dir = pathlib.Path(args.profile_dir).expanduser() if args.profile_dir else DEFAULT_PROFILE_DIR
    browser: dict[str, Any] = {"status": "planned" if args.dry_run else "not_run", "downloads": []}
    runtime: dict[str, Any] = {}
    queue_result: dict[str, Any] = {"status": "skipped"}
    if not site_url:
        browser = {"status": "blocked", "error": "site_url_missing", "downloads": []}
    elif args.dry_run:
        browser["command_preview"] = runner_command(args, site_url, import_dir, pathlib.Path("<result.json>"), profile_dir)
    elif not shutil.which("node"):
        browser = {"status": "blocked", "error": "missing_node", "downloads": []}
    else:
        runtime = ensure_browser_runtime(args)
        if runtime.get("status") != "ready":
            browser = {"status": "blocked", "error": runtime.get("status"), "downloads": [], "runtime": runtime}
        else:
            import_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="gsc-indexing-export-") as tmp:
                result_file = pathlib.Path(tmp) / "result.json"
                command = runner_command(args, site_url, import_dir, result_file, profile_dir)
                env = os.environ.copy()
                env["GSC_PLAYWRIGHT_NODE_MODULES"] = str(runtime["node_modules"])
                proc = subprocess.run(command, cwd=project_root, text=True, capture_output=True, check=False, env=env)
                try:
                    browser = json.loads(result_file.read_text(encoding="utf-8")) if result_file.exists() else json.loads(proc.stdout or "{}")
                except json.JSONDecodeError:
                    browser = {}
                browser.setdefault("status", "failed" if proc.returncode else "finished")
                browser["exit_code"] = proc.returncode
                browser["stderr"] = proc.stderr[-3000:]
                browser["command"] = command
                queue_result = build_queue(cfg_path, [str(item) for item in browser.get("downloads", [])], args, project_root)
    status = "planned" if args.dry_run else "ready" if browser.get("status") == "downloaded" else "needs_input" if browser.get("status") == "no_download" else "blocked"
    summary = {
        "domain": domain,
        "mode": "gsc_indexing_export_browser",
        "site_url": site_url,
        "issue_url": args.issue_url or "",
        "import_dir": rel_display(project_root, import_dir),
        "downloads": len(browser.get("downloads") or []),
        "build_queue": bool(args.build_queue),
        "queue_status": queue_result.get("status"),
        "stores_password": False,
    }
    findings: list[dict[str, Any]] = []
    if browser.get("status") == "no_download":
        findings.append(
            {
                "id": "gsc_export_not_captured",
                "severity": "medium",
                "message": "No GSC export download was captured. Rerun with --manual-fallback-seconds 120 and click Export CSV manually in the opened browser.",
                "evidence": {"issue_url": args.issue_url or "pages_index"},
            }
        )
    distillate = {
        "summary": summary,
        "downloads": browser.get("downloads", []),
        "queue_report": (queue_result.get("report") or {}).get("paths", {}),
        "citations": ["https://support.google.com/webmasters/answer/9012289"],
    }
    return write_technical_report(
        project_root,
        slug="gsc-indexing-export",
        provider="google_search_console_ui",
        title="GSC Indexing Export Browser Capture",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload={"browser": browser, "queue": queue_result, "runtime": runtime},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-indexing-export-browser.py seo-cycle.yaml --manual-fallback-seconds 120 --build-queue --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-request-indexing-browser.py seo-cycle.yaml --queue-file seo/technical/gsc-indexing-request-queue.csv --max 10 --auto-click --write",
        ],
        notes=["Browser profile is outside the project. Passwords and cookies are not written to reports."],
        cache_parts={"slug": "gsc-indexing-export", "site_url": site_url, "downloads": browser.get("downloads", [])},
        extra_payload={"browser_status": browser.get("status"), "downloads": browser.get("downloads", []), "queue_result": queue_result},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--site-url", help="GSC property, e.g. sc-domain:example.com")
    parser.add_argument("--issue-url", help="Direct GSC Pages issue URL for Discovered - currently not indexed.")
    parser.add_argument("--import-dir", help=f"Download/import dir. Default: {DEFAULT_IMPORT_DIR}")
    parser.add_argument("--profile-dir", help=f"Persistent GSC browser profile. Default: {DEFAULT_PROFILE_DIR}")
    parser.add_argument("--browser-channel", default="chrome")
    parser.add_argument("--node-deps-dir", help=f"Shared Node dependency cache. Default: {DEFAULT_NODE_DEPS_DIR}")
    parser.add_argument("--skip-install-browser-runtime", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--manual-fallback-seconds", type=int, default=120)
    parser.add_argument("--build-queue", action="store_true")
    parser.add_argument("--gsc-performance-file", action="append")
    parser.add_argument("--woocommerce-file", action="append")
    parser.add_argument("--sitemap", action="append")
    parser.add_argument("--sitemap-file", action="append")
    parser.add_argument("--technical-check", action="store_true")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()
    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    report = build_report(cfg_path, args)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"GSC indexing export status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0 if report["status"] in {"planned", "ready", "needs_input"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
