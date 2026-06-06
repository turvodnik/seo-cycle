#!/usr/bin/env python3
"""Audit redirect maps for missing targets, chains, loops, and optional live status."""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.technical_artifacts import write_technical_report


SOURCE_KEYS = ("old_url", "source", "from", "from_url", "url")
TARGET_KEYS = ("new_url", "target", "to", "to_url", "destination")


def absolute_url(value: str, base_url: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if not base_url or "://" in value:
        return value
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", value.lstrip("/"))


def read_redirects(path: pathlib.Path, base_url: str | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        sample = handle.read(2048)
        handle.seek(0)
        dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        for row in reader:
            source = next((row.get(key, "") for key in SOURCE_KEYS if key in row), "")
            target = next((row.get(key, "") for key in TARGET_KEYS if key in row), "")
            rows.append({"source": absolute_url(source, base_url), "target": absolute_url(target, base_url)})
    return rows


def trace_chain(source: str, mapping: dict[str, str], max_depth: int = 20) -> dict[str, Any]:
    seen: list[str] = []
    current = source
    for _ in range(max_depth):
        target = mapping.get(current)
        if not target:
            return {"source": source, "chain": seen + [current], "loop": False, "terminal": current}
        seen.append(current)
        if target in seen:
            return {"source": source, "chain": seen + [target], "loop": True, "terminal": target}
        current = target
    return {"source": source, "chain": seen + [current], "loop": True, "terminal": current, "reason": "max_depth"}


def live_check(url: str, timeout: float) -> dict[str, Any]:
    if not url:
        return {"status_code": None, "error": "empty target"}
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "seo-cycle-redirect-audit/1.0"})
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
    try:
        with opener.open(request, timeout=timeout) as response:
            return {"status_code": int(response.status), "final_url": response.geturl(), "ok": True}
    except urllib.error.HTTPError as exc:
        return {"status_code": int(exc.code), "final_url": exc.geturl(), "ok": False, "error": str(exc)}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"status_code": None, "final_url": url, "ok": False, "error": str(exc)}


def analyze(rows: list[dict[str, str]], *, live: bool = False, timeout: float = 10) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    mapping = {row["source"]: row["target"] for row in rows if row.get("source")}
    missing_targets = [row for row in rows if not row.get("target")]
    self_redirects = [row for row in rows if row.get("source") and row.get("source") == row.get("target")]
    traces = [trace_chain(source, mapping) for source in mapping]
    loop_map: dict[tuple[str, ...], dict[str, Any]] = {}
    for trace in traces:
        if not trace.get("loop"):
            continue
        chain = trace.get("chain", [])
        signature = tuple(sorted(set(chain)))
        loop_map.setdefault(signature, trace)
    loops = list(loop_map.values())
    chains = [trace for trace in traces if len(trace.get("chain", [])) > 2 and not trace.get("loop")]
    live_results: list[dict[str, Any]] = []
    if live:
        for row in rows:
            live_results.append({"source": row.get("source"), "target": row.get("target"), "http": live_check(row.get("source", ""), timeout)})

    summary = {
        "rules": len(rows),
        "missing_targets": len(missing_targets),
        "self_redirects": len(self_redirects),
        "chains": len(chains),
        "loops": len(loops),
        "live_checked": bool(live),
        "mode": "redirect_map",
    }
    findings: list[dict[str, Any]] = []
    if loops:
        findings.append(
            {
                "id": "redirect_loops_present",
                "severity": "high",
                "message": f"{len(loops)} redirect loop(s) detected. Fix before launch/indexing.",
                "evidence": loops[:10],
            }
        )
    if chains:
        findings.append(
            {
                "id": "redirect_chains_present",
                "severity": "medium",
                "message": f"{len(chains)} redirect chain(s) detected. Map old URLs directly to final canonical URLs.",
                "evidence": chains[:10],
            }
        )
    if missing_targets:
        findings.append(
            {
                "id": "redirect_targets_missing",
                "severity": "high",
                "message": f"{len(missing_targets)} redirect rule(s) have empty targets.",
                "evidence": missing_targets[:10],
            }
        )
    if self_redirects:
        findings.append(
            {
                "id": "self_redirects_present",
                "severity": "medium",
                "message": f"{len(self_redirects)} self-redirect(s) found.",
                "evidence": self_redirects[:10],
            }
        )
    raw = {"rows": rows, "traces": traces, "live_results": live_results}
    return summary, findings, raw


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    load_yaml(cfg_path)
    if args.input:
        rows = read_redirects(pathlib.Path(args.input).expanduser(), args.base_url)
        summary, findings, raw = analyze(rows, live=args.live, timeout=args.timeout)
        status = "ready"
    else:
        rows = []
        summary = {"rules": 0, "missing_targets": 0, "chains": 0, "loops": 0, "mode": "needs_input"}
        findings = [
            {
                "id": "redirect_map_input_required",
                "severity": "info",
                "message": "Provide --input CSV with old_url/new_url or source/target columns.",
                "evidence": None,
            }
        ]
        raw = {"rows": rows}
        status = "needs_input"
    distillate = {
        "summary": summary,
        "top_findings": findings[:10],
        "source_columns": {"source": SOURCE_KEYS, "target": TARGET_KEYS},
        "citations": [],
    }
    return write_technical_report(
        project_root,
        slug="redirect-map-audit",
        provider="redirect-map",
        title="Redirect Map Audit",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload=raw,
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "python3 ~/.codex/skills/seo-cycle/scripts/redirect-map-audit.py seo-cycle.yaml --input redirects.csv --base-url https://example.com --write",
        ],
        cache_parts={"slug": "redirect-map-audit", "rows": rows, "base_url": args.base_url, "live": args.live},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--input", help="CSV with old_url/new_url, source/target, from/to columns.")
    parser.add_argument("--base-url", help="Base URL for relative redirect paths.")
    parser.add_argument("--live", action="store_true", help="Check source URLs over public HTTP.")
    parser.add_argument("--timeout", type=float, default=10)
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
        print(f"Redirect map audit status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
