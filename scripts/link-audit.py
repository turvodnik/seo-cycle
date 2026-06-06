#!/usr/bin/env python3
"""Broken link and redirect audit using linkinator exports or explicit live runs."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import urllib.parse
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.technical_artifacts import write_technical_report


def load_json(path: str | None) -> dict[str, Any] | list[Any] | None:
    if not path:
        return None
    return json.loads(pathlib.Path(path).expanduser().read_text(encoding="utf-8"))


def link_like(value: dict[str, Any]) -> bool:
    return any(key in value for key in ("url", "href", "link", "status", "statusCode", "state"))


def collect_link_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            rows.extend(collect_link_rows(item))
        return rows
    if not isinstance(value, dict):
        return rows
    if link_like(value):
        rows.append(value)
    for key in ("links", "results", "checkedLinks", "data", "items"):
        if key in value:
            rows.extend(collect_link_rows(value[key]))
    return rows


def normalized_status(row: dict[str, Any]) -> int | None:
    for key in ("status", "statusCode", "code"):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def normalized_url(row: dict[str, Any]) -> str:
    return str(row.get("url") or row.get("href") or row.get("link") or "").strip()


def normalized_parent(row: dict[str, Any]) -> str:
    return str(row.get("parent") or row.get("parentUrl") or row.get("source") or row.get("referrer") or "").strip()


def is_broken(row: dict[str, Any], status: int | None) -> bool:
    state = str(row.get("state") or row.get("statusText") or "").lower()
    if "broken" in state or "error" in state:
        return True
    return status is None or status >= 400


def is_redirect(row: dict[str, Any], status: int | None) -> bool:
    state = str(row.get("state") or row.get("statusText") or "").lower()
    return bool(row.get("redirected")) or "redirect" in state or (status is not None and 300 <= status < 400)


def host(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower()


def run_linkinator(url: str, timeout: int, recurse: bool, extra_args: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    npx = shutil.which("npx")
    if not npx:
        return None, {"ok": False, "reason": "npx not found; install linkinator or pass --input-json"}
    command = [npx, "-y", "linkinator", url, "--format", "json", "--timeout", str(timeout), "--verbosity", "error"]
    if recurse:
        command.append("--recurse")
    command.extend(extra_args)
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    meta = {"ok": proc.returncode == 0, "returncode": proc.returncode, "command": command, "stderr": proc.stderr}
    try:
        return json.loads(proc.stdout or "{}"), meta
    except json.JSONDecodeError:
        meta["reason"] = "linkinator returned non-JSON output"
        meta["stdout_preview"] = (proc.stdout or "")[:1000]
        return None, meta


def summarize(rows: list[dict[str, Any]], target_url: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    target_host = host(target_url or "") if target_url else ""
    broken: list[dict[str, Any]] = []
    redirects: list[dict[str, Any]] = []
    insecure: list[dict[str, Any]] = []
    external_errors: list[dict[str, Any]] = []
    internal = 0
    external = 0
    for row in rows:
        url = normalized_url(row)
        status = normalized_status(row)
        if not url:
            continue
        current_host = host(url)
        internal_match = bool(target_host and current_host == target_host)
        internal += 1 if internal_match else 0
        external += 0 if internal_match else 1
        normalized = {"url": url, "status": status, "parent": normalized_parent(row)}
        if is_broken(row, status):
            broken.append(normalized)
            if not internal_match:
                external_errors.append(normalized)
        if is_redirect(row, status):
            redirects.append(normalized)
        if urllib.parse.urlparse(url).scheme == "http":
            insecure.append(normalized)

    summary = {
        "total_links": len(rows),
        "internal_links": internal,
        "external_links": external,
        "broken_links": len(broken),
        "redirect_links": len(redirects),
        "http_links": len(insecure),
        "mode": "linkinator",
    }
    findings: list[dict[str, Any]] = []
    if broken:
        findings.append(
            {
                "id": "broken_links_present",
                "severity": "high",
                "message": f"{len(broken)} broken links found. Fix internal 4xx/5xx first, then important external references.",
                "evidence": broken[:10],
            }
        )
    if redirects:
        findings.append(
            {
                "id": "redirect_links_present",
                "severity": "medium",
                "message": f"{len(redirects)} links resolve through redirects. Replace internal redirected links with final URLs.",
                "evidence": redirects[:10],
            }
        )
    if insecure:
        findings.append(
            {
                "id": "insecure_http_links_present",
                "severity": "medium",
                "message": f"{len(insecure)} HTTP links found. Prefer HTTPS for crawl quality and trust.",
                "evidence": insecure[:10],
            }
        )
    if external_errors:
        findings.append(
            {
                "id": "external_broken_links_present",
                "severity": "low",
                "message": f"{len(external_errors)} broken external links found. Replace or remove stale source references.",
                "evidence": external_errors[:10],
            }
        )
    return summary, findings


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    target_url = args.url or f"https://{nested_get(cfg, 'project.domain') or ''}/"
    raw_payload = load_json(args.input_json)
    run_meta: dict[str, Any] = {"live": False}
    if raw_payload is None and args.live:
        raw_payload, run_meta = run_linkinator(target_url, args.timeout, args.recurse, args.linkinator_arg or [])
        run_meta["live"] = True

    if raw_payload is None:
        summary = {"total_links": 0, "broken_links": 0, "redirect_links": 0, "http_links": 0, "mode": "needs_input"}
        findings = [
            {
                "id": "link_audit_input_required",
                "severity": "info",
                "message": "Provide --input-json from linkinator or rerun with --live --url to execute a public crawl.",
                "evidence": None,
            }
        ]
        status = "needs_input"
        raw_payload = {"status": status, "run_meta": run_meta}
    else:
        rows = collect_link_rows(raw_payload)
        summary, findings = summarize(rows, target_url)
        summary["target_url"] = target_url
        status = "ready"

    distillate = {
        "target_url": target_url,
        "summary": summary,
        "top_findings": findings[:10],
        "tool": "linkinator",
        "citations": ["https://github.com/JustinBeckwith/linkinator"],
    }
    return write_technical_report(
        project_root,
        slug="link-audit",
        provider="linkinator",
        title="Broken Link and Redirect Audit",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload={"payload": raw_payload, "run_meta": run_meta},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "npx -y linkinator https://example.com --recurse --format json > linkinator.json",
            "python3 ~/.codex/skills/seo-cycle/scripts/link-audit.py seo-cycle.yaml --input-json linkinator.json --write",
        ],
        cache_parts={"slug": "link-audit", "target_url": target_url, "payload": raw_payload},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--url", help="Target URL for live crawl or internal/external classification.")
    parser.add_argument("--input-json", help="JSON export from linkinator.")
    parser.add_argument("--live", action="store_true", help="Run linkinator via npx. Makes public HTTP requests.")
    parser.add_argument("--recurse", action="store_true", help="Pass --recurse to linkinator in live mode.")
    parser.add_argument("--timeout", type=int, default=15000)
    parser.add_argument("--linkinator-arg", action="append", default=[], help="Extra raw argument for linkinator live mode.")
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
        paths = report.get("paths", {})
        print(f"Link audit status: {report['status']}")
        print(f"Report: {paths.get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
