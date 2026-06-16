#!/usr/bin/env python3
"""Guarded IndexNow bulk URL submitter for Bing/Yandex-compatible discovery.

Live submission is explicit (`--live`). API keys are read from environment
variables and never written to reports.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for, rel_display, rel_path
from seo_cycle_core.technical_artifacts import write_technical_report


ENV_KEY = "INDEXNOW_KEY"
ENV_KEY_LOCATION = "INDEXNOW_KEY_LOCATION"
DEFAULT_ENDPOINT = "https://api.indexnow.org/indexnow"
DEFAULT_QUEUE = "seo/technical/gsc-indexing-request-queue.csv"


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""))


def host_from_url(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower()


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


def urls_from_queue(project_root: pathlib.Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    queue_path = rel_path(project_root, args.queue_file or DEFAULT_QUEUE)
    rows.extend(load_rows(queue_path))
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


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def planned_payload(host: str, urls: list[str], key_location: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "host": host,
        "key": "***",
        "urlList": urls,
    }
    if key_location:
        payload["keyLocation"] = key_location
    return payload


def live_payload(host: str, urls: list[str], key: str, key_location: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"host": host, "key": key, "urlList": urls}
    if key_location:
        payload["keyLocation"] = key_location
    return payload


def post_indexnow(endpoint: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"}, method="POST")
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
        return {"status_code": exc.code, "ok": False, "response": {"body": text[:1000]}}
    except Exception as exc:  # noqa: BLE001 - report external request failures
        return {"status_code": None, "ok": False, "error": str(exc)[:500]}


def write_submission_csv(project_root: pathlib.Path, rows: list[dict[str, Any]], write: bool) -> dict[str, str]:
    paths = {
        "submit_csv": project_root / "seo" / "technical" / "indexnow-submit-log.csv",
        "latest_submit_csv": project_root / "seo" / "technical" / "latest-indexnow-submit-log.csv",
    }
    if write:
        header = ["url", "priority", "endpoint", "status", "status_code", "message"]
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=header)
                writer.writeheader()
                for row in rows:
                    writer.writerow({key: row.get(key, "") for key in header})
    return {key: rel_display(project_root, value) for key, value in paths.items()}


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    domain = nested_get(cfg, "project.domain") or ""
    targets = urls_from_queue(project_root, args)
    urls = [item["url"] for item in targets]
    hosts = sorted({host_from_url(url) for url in urls if host_from_url(url)})
    host = args.host or (hosts[0] if len(hosts) == 1 else domain)
    key = os.environ.get(args.key_env or ENV_KEY, "")
    key_location = args.key_location or os.environ.get(args.key_location_env or ENV_KEY_LOCATION, "")
    endpoints = args.endpoint or [DEFAULT_ENDPOINT]
    warnings: list[str] = []
    if not urls:
        warnings.append("No URLs selected from queue/manual input.")
    if len(hosts) > 1 and not args.host:
        warnings.append("Selected URLs contain multiple hosts; pass --host and submit per host.")
    if args.live and not key:
        warnings.append(f"{args.key_env or ENV_KEY} is required for live IndexNow submission.")
    batches = chunked(urls, max(1, min(args.batch_size, 10000)))
    results: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    for endpoint in endpoints:
        for batch_index, batch in enumerate(batches, start=1):
            if args.live and key and not warnings:
                response = post_indexnow(endpoint, live_payload(host, batch, key, key_location), args.timeout)
                batch_status = "submitted" if response.get("ok") else "failed"
            else:
                response = {"status_code": None, "ok": False, "planned_request": planned_payload(host, batch, key_location)}
                batch_status = "planned"
            raw_results.append(
                {
                    "endpoint": endpoint,
                    "batch": batch_index,
                    "url_count": len(batch),
                    "status": batch_status,
                    "status_code": response.get("status_code"),
                    "response": response.get("response") or response.get("error") or response.get("planned_request"),
                }
            )
            for url in batch:
                source = next((item for item in targets if item["url"] == url), {})
                results.append(
                    {
                        "url": url,
                        "priority": source.get("priority", ""),
                        "endpoint": endpoint,
                        "status": batch_status,
                        "status_code": response.get("status_code") or "",
                        "message": "IndexNow accepted" if response.get("ok") else "planned" if batch_status == "planned" else "IndexNow request failed",
                    }
                )
    csv_paths = write_submission_csv(project_root, results, args.write)
    submitted = len([row for row in results if row["status"] == "submitted"])
    failed = len([row for row in results if row["status"] == "failed"])
    status = "ready" if submitted and not failed else "attention_required" if failed else "guarded" if not args.live else "blocked"
    summary = {
        "domain": domain,
        "mode": "indexnow_submit",
        "host": host,
        "targets": len(urls),
        "endpoints": len(endpoints),
        "batches": len(batches) * len(endpoints),
        "submitted": submitted,
        "failed": failed,
        "live_api_used": bool(args.live and key and not warnings),
        "key_present": bool(key),
        "key_location_present": bool(key_location),
    }
    findings: list[dict[str, Any]] = []
    if warnings:
        findings.append({"id": "indexnow_submit_guard", "severity": "medium", "message": "IndexNow live submission is blocked or planned.", "evidence": warnings})
    if failed:
        findings.append({"id": "indexnow_submit_failed", "severity": "high", "message": f"{failed} URL endpoint submissions failed.", "evidence": raw_results[:10]})
    distillate = {
        "summary": summary,
        "results": results[:100],
        "raw_results": raw_results[:20],
        "citations": [
            "https://www.indexnow.org/documentation",
            "https://www.bing.com/indexnow/getstarted",
        ],
    }
    return write_technical_report(
        project_root,
        slug="indexnow-submit",
        provider="indexnow",
        title="IndexNow URL Submission",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload={"results": raw_results, "targets": targets, "key_present": bool(key), "key_location": key_location},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "INDEXNOW_KEY=*** INDEXNOW_KEY_LOCATION=https://example.com/key.txt python3 ~/.codex/skills/seo-cycle/scripts/indexnow-submit.py seo-cycle.yaml --queue-file seo/technical/gsc-indexing-request-queue.csv --priority P0,P1 --max 100 --live --write",
        ],
        notes=["IndexNow can submit up to 10,000 URLs per POST. HTTP 200 only means the URLs were received, not indexed."],
        cache_parts={"slug": "indexnow-submit", "host": host, "urls": urls, "endpoints": endpoints, "live": bool(args.live)},
        paid_api_used=False,
        extra_payload={**csv_paths, "results": results[:200], "warnings": warnings},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--queue-file", help=f"Queue CSV/JSON. Default: {DEFAULT_QUEUE}")
    parser.add_argument("--url", action="append", help="Manual URL. Repeatable.")
    parser.add_argument("--priority", default="P0,P1", help="Comma-separated priorities from queue.")
    parser.add_argument("--max", type=int, default=100)
    parser.add_argument("--host", help="IndexNow host. Required when queue contains multiple hosts.")
    parser.add_argument("--endpoint", action="append", help=f"IndexNow endpoint. Default: {DEFAULT_ENDPOINT}")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--key-env", default=ENV_KEY)
    parser.add_argument("--key-location-env", default=ENV_KEY_LOCATION)
    parser.add_argument("--key-location", help="Public URL of the hosted IndexNow key file.")
    parser.add_argument("--live", action="store_true", help="Submit URLs to IndexNow. Requires INDEXNOW_KEY.")
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
        print(f"IndexNow submit status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0 if report["status"] in {"ready", "guarded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
