#!/usr/bin/env python3
"""Browser-assisted Search Console indexing requester.

Google does not expose a general API to request indexing for ordinary pages.
This helper opens the URL Inspection UI with a persistent browser profile and
optionally clicks the visible "Request indexing" button for a small reviewed
queue. It never stores passwords or tokens.
"""

from __future__ import annotations

import argparse
import csv
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
DEFAULT_QUEUE = "seo/technical/gsc-indexing-request-queue.csv"


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def load_queue_file(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if isinstance(data.get("queue"), list):
                return [item for item in data["queue"] if isinstance(item, dict)]
            distillate = data.get("distillate")
            if isinstance(distillate, dict) and isinstance(distillate.get("queue"), list):
                return [item for item in distillate["queue"] if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def normalize_targets(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    allowed_priorities = {item.strip().upper() for item in args.priority.split(",") if item.strip()} if args.priority else set()
    for row in rows:
        url = str(row.get("url") or row.get("URL") or row.get("page") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        priority = str(row.get("priority") or row.get("Priority") or "").upper()
        if allowed_priorities and priority not in allowed_priorities:
            continue
        technical = row.get("technical") if isinstance(row.get("technical"), dict) else {}
        technical_status = str(row.get("technical_status") or technical.get("status") or "").lower()
        blockers = str(row.get("technical_blockers") or "")
        if args.require_technical_ok and technical_status not in {"indexable", "unchecked", ""}:
            continue
        if args.require_technical_ok and blockers:
            continue
        targets.append(
            {
                "url": url,
                "priority": priority or "P2",
                "priority_score": int(float(row.get("priority_score") or 0)),
                "page_type": row.get("page_type") or "",
            }
        )
    targets.extend({"url": url, "priority": "P0", "priority_score": 100, "page_type": "manual"} for url in args.url or [])
    targets.sort(key=lambda item: (-int(item.get("priority_score") or 0), item["url"]))
    return targets[: args.max]


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


def runner_command(args: argparse.Namespace, site_url: str, input_file: pathlib.Path, result_file: pathlib.Path, profile_dir: pathlib.Path) -> list[str]:
    command = [
        "node",
        str(skill_root() / "scripts" / "gsc-request-indexing-runner.mjs"),
        "--input-file",
        str(input_file),
        "--result-file",
        str(result_file),
        "--site-url",
        site_url,
        "--profile-dir",
        str(profile_dir),
        "--browser-channel",
        args.browser_channel,
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--live-test-wait-seconds",
        str(args.live_test_wait_seconds),
    ]
    if args.auto_click:
        command.append("--auto-click")
    if args.skip_live_test:
        command.append("--skip-live-test")
    if args.headless:
        command.append("--headless")
    if args.keep_open:
        command.append("--keep-open")
    return command


def summarize_results(browser: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in browser.get("results") or []:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    domain = nested_get(cfg, "project.domain") or ""
    site_url = args.site_url or os.environ.get("GSC_SITE_URL") or (f"sc-domain:{domain}" if domain else "")
    queue_path = rel_path(project_root, args.queue_file or DEFAULT_QUEUE)
    rows = load_queue_file(queue_path)
    targets = normalize_targets(rows, args)
    profile_dir = pathlib.Path(args.profile_dir).expanduser() if args.profile_dir else DEFAULT_PROFILE_DIR
    runtime: dict[str, Any] = {}
    browser: dict[str, Any] = {
        "status": "planned" if args.dry_run else "not_run",
        "results": [],
        "targets_total": len(targets),
        "auto_click": bool(args.auto_click),
    }
    if not site_url:
        browser = {"status": "blocked", "error": "site_url_missing", "results": [], "targets_total": len(targets)}
    elif args.dry_run:
        browser["command_preview"] = runner_command(args, site_url, pathlib.Path("<targets.json>"), pathlib.Path("<result.json>"), profile_dir)
    elif not targets:
        browser = {"status": "blocked", "error": "empty_queue", "results": [], "targets_total": 0}
    elif not shutil.which("node"):
        browser = {"status": "blocked", "error": "missing_node", "results": [], "targets_total": len(targets)}
    else:
        runtime = ensure_browser_runtime(args)
        if runtime.get("status") != "ready":
            browser = {"status": "blocked", "error": runtime.get("status"), "results": [], "targets_total": len(targets), "runtime": runtime}
        else:
            with tempfile.TemporaryDirectory(prefix="gsc-request-indexing-") as tmp:
                tmp_path = pathlib.Path(tmp)
                input_file = tmp_path / "targets.json"
                result_file = tmp_path / "result.json"
                input_file.write_text(json.dumps({"targets": targets}, ensure_ascii=False), encoding="utf-8")
                command = runner_command(args, site_url, input_file, result_file, profile_dir)
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
    counts = summarize_results(browser)
    status = "planned" if args.dry_run else "ready" if browser.get("status") in {"finished", "manual_action_required"} else "blocked"
    summary = {
        "domain": domain,
        "mode": "gsc_request_indexing_browser",
        "site_url": site_url,
        "queue_file": rel_display(project_root, queue_path),
        "targets": len(targets),
        "auto_click": bool(args.auto_click),
        "submitted_or_requested": counts.get("submitted_or_requested", 0),
        "manual_action_required": counts.get("manual_action_required", 0),
        "quota_hit": counts.get("quota_hit", 0),
        "request_button_not_found": counts.get("request_button_not_found", 0),
    }
    findings: list[dict[str, Any]] = []
    if not args.auto_click:
        findings.append(
            {
                "id": "gsc_manual_click_required",
                "severity": "info",
                "message": "Browser opened GSC URL Inspection targets but did not click Request indexing. Add --auto-click for guarded UI submission.",
                "evidence": {"targets": len(targets)},
            }
        )
    if counts.get("quota_hit"):
        findings.append(
            {
                "id": "gsc_request_indexing_quota_hit",
                "severity": "medium",
                "message": "Search Console appears to have hit a request indexing quota or retry limit.",
                "evidence": counts,
            }
        )
    distillate = {
        "summary": summary,
        "results": browser.get("results", [])[:50],
        "citations": [
            "https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl",
            "https://support.google.com/webmasters/answer/9012289",
        ],
    }
    return write_technical_report(
        project_root,
        slug="gsc-indexing-submit",
        provider="google_search_console_ui",
        title="GSC Request Indexing Browser Run",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload={"browser": browser, "runtime": runtime, "targets": targets},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-request-indexing-browser.py seo-cycle.yaml --queue-file seo/technical/gsc-indexing-request-queue.csv --max 10 --auto-click --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/gsc-indexing-recheck.py seo-cycle.yaml --submitted-log seo/technical/gsc-indexing-submit.json --gsc-discovered-file exports/discovered-after-7d.csv --write",
        ],
        notes=[
            "Uses a persistent browser profile; passwords and cookies are not written into the project.",
            "Keep queues small. Google says repeated recrawl requests do not make crawling faster.",
        ],
        cache_parts={"slug": "gsc-indexing-submit", "site_url": site_url, "targets": [item["url"] for item in targets], "counts": counts},
        paid_api_used=False,
        extra_payload={"browser_status": browser.get("status"), "result_counts": counts},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--queue-file", help=f"Queue CSV/JSON from gsc-indexing-queue.py. Default: {DEFAULT_QUEUE}")
    parser.add_argument("--url", action="append", help="Manual URL to submit; repeatable.")
    parser.add_argument("--site-url", help="GSC property, e.g. sc-domain:example.com or https://example.com/")
    parser.add_argument("--priority", default="P0,P1", help="Comma-separated priorities to submit.")
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--require-technical-ok", action="store_true", default=True)
    parser.add_argument("--auto-click", action="store_true", help="Click Request indexing when the GSC UI exposes the button.")
    parser.add_argument("--skip-live-test", action="store_true", help="Do not click Test live URL before request indexing fallback.")
    parser.add_argument("--profile-dir", help=f"Persistent GSC browser profile. Default: {DEFAULT_PROFILE_DIR}")
    parser.add_argument("--browser-channel", default="chrome")
    parser.add_argument("--node-deps-dir", help=f"Shared Node dependency cache. Default: {DEFAULT_NODE_DEPS_DIR}")
    parser.add_argument("--skip-install-browser-runtime", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--live-test-wait-seconds", type=int, default=90)
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
        print(f"GSC request indexing browser status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0 if report["status"] in {"planned", "ready"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
