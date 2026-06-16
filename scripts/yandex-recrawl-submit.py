#!/usr/bin/env python3
"""Guarded Yandex Webmaster recrawl queue submitter/status checker."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, rel_display, rel_path
from seo_cycle_core.technical_artifacts import write_technical_report


ENV_TOKEN = "YANDEX_OAUTH_TOKEN"
ENV_USER_ID = "YANDEX_USER_ID"
ENV_HOST_ID = "YANDEX_WEBMASTER_HOST_ID"
DEFAULT_API_BASE = "https://api.webmaster.yandex.net/v4"
DEFAULT_QUEUE = "seo/technical/gsc-indexing-request-queue.csv"


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


def load_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key in ("queue", "urls", "rows"):
                if isinstance(data.get(key), list):
                    return [item for item in data[key] if isinstance(item, dict)]
            distillate = data.get("distillate")
            if isinstance(distillate, dict) and isinstance(distillate.get("queue"), list):
                return [item for item in distillate["queue"] if isinstance(item, dict)]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [dict(row) for row in csv.DictReader(io.StringIO(text), dialect=dialect)]


def targets_from_queue(project_root: pathlib.Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(load_rows(rel_path(project_root, args.queue_file or DEFAULT_QUEUE)))
    rows.extend({"url": url, "priority": "P0", "priority_score": 100, "source": "manual"} for url in args.url or [])
    allowed = {item.strip().upper() for item in args.priority.split(",") if item.strip()} if args.priority else set()
    seen: set[str] = set()
    targets: list[dict[str, Any]] = []
    for row in rows:
        url = normalize_url(str(row.get("url") or row.get("URL") or row.get("page") or ""))
        if not url or url in seen:
            continue
        priority = str(row.get("priority") or "P2").upper()
        if allowed and priority not in allowed:
            continue
        seen.add(url)
        targets.append(
            {
                "url": url,
                "priority": priority,
                "priority_score": int(float(row.get("priority_score") or 0)),
                "page_type": row.get("page_type") or "",
            }
        )
    targets.sort(key=lambda item: (-int(item.get("priority_score") or 0), item["url"]))
    return targets[: args.max]


def api_url(api_base: str, user_id: str, host_id: str) -> str:
    return f"{api_base.rstrip('/')}/user/{urllib.parse.quote(str(user_id))}/hosts/{urllib.parse.quote(str(host_id), safe='')}/recrawl/queue"


def call_yandex(method: str, endpoint: str, token: str, payload: dict[str, Any] | None, timeout: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"OAuth {token}", "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(endpoint, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text) if text else {}
            except json.JSONDecodeError:
                parsed = {"body": text[:1000]}
            return {"status_code": response.status, "ok": 200 <= response.status < 300, "response": parsed}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = {"body": text[:1000]}
        return {"status_code": exc.code, "ok": False, "response": parsed}
    except Exception as exc:  # noqa: BLE001
        return {"status_code": None, "ok": False, "error": str(exc)[:500]}


def write_csv(project_root: pathlib.Path, slug: str, rows: list[dict[str, Any]], write: bool) -> dict[str, str]:
    paths = {
        "submit_csv": project_root / "seo" / "technical" / f"{slug}.csv",
        "latest_submit_csv": project_root / "seo" / "technical" / f"latest-{slug}.csv",
    }
    if write:
        header = ["url", "priority", "status", "status_code", "recrawl_status", "message"]
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=header)
                writer.writeheader()
                for row in rows:
                    writer.writerow({key: row.get(key, "") for key in header})
    return {key: rel_display(project_root, value) for key, value in paths.items()}


def distill_queue_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    node = payload.get("response") if isinstance(payload.get("response"), dict) else payload
    candidates = []
    for key in ("tasks", "recrawl_queue", "urls", "items"):
        if isinstance(node.get(key), list):
            candidates = node[key]
            break
    if not candidates and isinstance(node, list):
        candidates = node
    rows: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "url": item.get("url") or item.get("page_url") or item.get("pageUrl") or "",
                "recrawl_status": item.get("status") or item.get("recrawl_status") or item.get("state") or "",
                "status": "queue_status",
                "status_code": "",
                "message": item.get("status_text") or item.get("message") or "",
            }
        )
    return rows


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    domain = nested_get(cfg, "project.domain") or ""
    token = os.environ.get(args.token_env or ENV_TOKEN, "")
    user_id = args.user_id or os.environ.get(args.user_id_env or ENV_USER_ID, "")
    host_id = args.host_id or os.environ.get(args.host_id_env or ENV_HOST_ID, "")
    endpoint = api_url(args.api_base, user_id or "{user-id}", host_id or "{host-id}")
    targets = targets_from_queue(project_root, args)
    warnings: list[str] = []
    if args.mode == "submit" and not targets:
        warnings.append("No URLs selected from queue/manual input.")
    if args.live and not token:
        warnings.append(f"{args.token_env or ENV_TOKEN} is required for live Yandex Webmaster API calls.")
    if args.live and not user_id:
        warnings.append(f"{args.user_id_env or ENV_USER_ID} is required.")
    if args.live and not host_id:
        warnings.append(f"{args.host_id_env or ENV_HOST_ID} is required.")
    raw_results: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    if args.mode == "status":
        if args.live and not warnings:
            response = call_yandex("GET", endpoint, token, None, args.timeout)
            raw_results.append({"endpoint": endpoint, "method": "GET", "status_code": response.get("status_code"), "ok": response.get("ok"), "response": response.get("response") or response.get("error")})
            rows.extend(distill_queue_response(response))
        else:
            raw_results.append({"endpoint": endpoint, "method": "GET", "planned": True})
    else:
        for index, target in enumerate(targets, start=1):
            if args.live and not warnings:
                response = call_yandex("POST", endpoint, token, {"url": target["url"]}, args.timeout)
                status = "submitted" if response.get("ok") else "failed"
                raw_results.append(
                    {
                        "endpoint": endpoint,
                        "method": "POST",
                        "url": target["url"],
                        "status_code": response.get("status_code"),
                        "ok": response.get("ok"),
                        "response": response.get("response") or response.get("error"),
                    }
                )
            else:
                response = {"status_code": None, "ok": False}
                status = "planned"
                raw_results.append({"endpoint": endpoint, "method": "POST", "url": target["url"], "planned": True})
            rows.append(
                {
                    "url": target["url"],
                    "priority": target.get("priority", ""),
                    "status": status,
                    "status_code": response.get("status_code") or "",
                    "recrawl_status": "",
                    "message": "Yandex recrawl accepted" if response.get("ok") else "planned" if status == "planned" else "Yandex recrawl request failed",
                }
            )
            if args.live and args.sleep_seconds and index < len(targets):
                time.sleep(args.sleep_seconds)
    slug = "yandex-recrawl-status" if args.mode == "status" else "yandex-recrawl-submit"
    csv_paths = write_csv(project_root, slug, rows, args.write)
    submitted = len([row for row in rows if row.get("status") == "submitted"])
    failed = len([row for row in rows if row.get("status") == "failed"])
    status = "ready" if (submitted or args.mode == "status") and not failed else "attention_required" if failed else "guarded" if not args.live else "blocked"
    summary = {
        "domain": domain,
        "mode": f"yandex_recrawl_{args.mode}",
        "targets": len(targets),
        "submitted": submitted,
        "failed": failed,
        "queue_rows": len(rows) if args.mode == "status" else 0,
        "live_api_used": bool(args.live and not warnings),
        "token_present": bool(token),
        "user_id_present": bool(user_id),
        "host_id_present": bool(host_id),
    }
    findings: list[dict[str, Any]] = []
    if warnings:
        findings.append({"id": "yandex_recrawl_guard", "severity": "medium", "message": "Yandex recrawl live call is blocked or planned.", "evidence": warnings})
    if failed:
        findings.append({"id": "yandex_recrawl_failed", "severity": "high", "message": f"{failed} recrawl requests failed.", "evidence": raw_results[:10]})
    distillate = {
        "summary": summary,
        "rows": rows[:100],
        "citations": [
            "https://yandex.com/dev/webmaster/doc/dg/reference/host-recrawl-post.html",
            "https://yandex.com/dev/webmaster/doc/en/reference/host-recrawl-get",
        ],
    }
    return write_technical_report(
        project_root,
        slug=slug,
        provider="yandex_webmaster",
        title="Yandex Webmaster Recrawl" if args.mode == "submit" else "Yandex Webmaster Recrawl Queue Status",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload={"results": raw_results, "targets": targets, "token_present": bool(token), "user_id_present": bool(user_id), "host_id_present": bool(host_id)},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "YANDEX_OAUTH_TOKEN=*** YANDEX_USER_ID=123 YANDEX_WEBMASTER_HOST_ID=https:example.com:443 python3 ~/.codex/skills/seo-cycle/scripts/yandex-recrawl-submit.py seo-cycle.yaml --queue-file seo/technical/gsc-indexing-request-queue.csv --priority P0,P1 --max 20 --live --write",
            "python3 ~/.codex/skills/seo-cycle/scripts/yandex-recrawl-submit.py seo-cycle.yaml --mode status --live --write",
        ],
        notes=["Uses Yandex Webmaster API v4 recrawl queue. OAuth token is never written to reports."],
        cache_parts={"slug": slug, "mode": args.mode, "targets": [item["url"] for item in targets], "live": bool(args.live)},
        paid_api_used=False,
        extra_payload={**csv_paths, "rows": rows[:200], "warnings": warnings},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--mode", choices=("submit", "status"), default="submit")
    parser.add_argument("--queue-file", help=f"Queue CSV/JSON. Default: {DEFAULT_QUEUE}")
    parser.add_argument("--url", action="append", help="Manual URL. Repeatable.")
    parser.add_argument("--priority", default="P0,P1", help="Comma-separated priorities from queue.")
    parser.add_argument("--max", type=int, default=20)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--token-env", default=ENV_TOKEN)
    parser.add_argument("--user-id-env", default=ENV_USER_ID)
    parser.add_argument("--host-id-env", default=ENV_HOST_ID)
    parser.add_argument("--user-id")
    parser.add_argument("--host-id")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--live", action="store_true", help="Call Yandex Webmaster API.")
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
        print(f"Yandex recrawl status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0 if report["status"] in {"ready", "guarded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
