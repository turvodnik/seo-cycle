#!/usr/bin/env python3
"""Distill Google Lighthouse JSON into SEO/CWV technical artifacts."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, nested_get, project_root_for
from seo_cycle_core.technical_artifacts import write_technical_report


CORE_AUDITS = {
    "largest-contentful-paint": ("lcp_ms", 2500, "Largest Contentful Paint"),
    "cumulative-layout-shift": ("cls", 0.1, "Cumulative Layout Shift"),
    "total-blocking-time": ("tbt_ms", 200, "Total Blocking Time"),
    "speed-index": ("speed_index_ms", 3400, "Speed Index"),
}


def load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(pathlib.Path(path).expanduser().read_text(encoding="utf-8"))


def run_lighthouse(url: str, categories: str, device: str, extra_args: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    npx = shutil.which("npx")
    if not npx:
        return None, {"ok": False, "reason": "npx not found; pass --input-json or install Lighthouse"}
    form_factor = "mobile" if device == "mobile" else "desktop"
    command = [
        npx,
        "-y",
        "lighthouse",
        url,
        "--quiet",
        "--output=json",
        "--output-path=stdout",
        f"--only-categories={categories}",
        f"--form-factor={form_factor}",
        "--chrome-flags=--headless=new --no-sandbox",
    ]
    command.extend(extra_args)
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    meta = {"ok": proc.returncode == 0, "returncode": proc.returncode, "command": command, "stderr": proc.stderr}
    try:
        return json.loads(proc.stdout or "{}"), meta
    except json.JSONDecodeError:
        meta["reason"] = "lighthouse returned non-JSON output"
        meta["stdout_preview"] = (proc.stdout or "")[:1000]
        return None, meta


def score_value(payload: dict[str, Any], category: str) -> float | None:
    raw = ((payload.get("categories") or {}).get(category) or {}).get("score")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def audit_metric(payload: dict[str, Any], audit_id: str) -> dict[str, Any]:
    audit = (payload.get("audits") or {}).get(audit_id) or {}
    raw = audit.get("numericValue")
    try:
        numeric = float(raw)
    except (TypeError, ValueError):
        numeric = None
    return {
        "id": audit_id,
        "numeric_value": numeric,
        "display_value": audit.get("displayValue"),
        "score": audit.get("score"),
        "title": audit.get("title"),
    }


def distill(payload: dict[str, Any], url: str, device: str) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    scores = {
        "performance": score_value(payload, "performance"),
        "seo": score_value(payload, "seo"),
        "accessibility": score_value(payload, "accessibility"),
        "best_practices": score_value(payload, "best-practices"),
    }
    metrics = {}
    metric_rows = []
    for audit_id, (key, threshold, label) in CORE_AUDITS.items():
        row = audit_metric(payload, audit_id)
        metrics[key] = row.get("numeric_value")
        metric_rows.append({**row, "metric": key, "threshold": threshold, "label": label})

    opportunities = []
    for audit_id, audit in (payload.get("audits") or {}).items():
        if not isinstance(audit, dict):
            continue
        score = audit.get("score")
        if isinstance(score, (int, float)) and score < 0.5 and audit_id not in CORE_AUDITS:
            opportunities.append({"id": audit_id, "title": audit.get("title"), "score": score, "display_value": audit.get("displayValue")})

    summary = {
        "url": url or payload.get("finalUrl") or payload.get("requestedUrl"),
        "final_url": payload.get("finalUrl"),
        "device": device,
        "scores": scores,
        "metrics": metrics,
        "opportunities": len(opportunities),
        "mode": "lighthouse",
    }
    findings: list[dict[str, Any]] = []
    if scores["performance"] is not None and scores["performance"] < 0.7:
        findings.append(
            {
                "id": "lighthouse_performance_low",
                "severity": "high",
                "message": f"Lighthouse performance score is {scores['performance']:.2f}. Prioritize CWV and resource opportunities.",
                "evidence": scores,
            }
        )
    cwv_risks = [
        row
        for row in metric_rows
        if row.get("numeric_value") is not None and row.get("threshold") is not None and float(row["numeric_value"]) > float(row["threshold"])
    ]
    if cwv_risks:
        findings.append(
            {
                "id": "core_web_vitals_risk",
                "severity": "high",
                "message": "One or more Lighthouse lab metrics exceed recommended thresholds.",
                "evidence": cwv_risks,
            }
        )
    if scores["seo"] is not None and scores["seo"] < 0.9:
        findings.append(
            {
                "id": "lighthouse_seo_score_low",
                "severity": "medium",
                "message": f"Lighthouse SEO score is {scores['seo']:.2f}. Review crawlability, metadata, hreflang and structured data checks.",
                "evidence": scores["seo"],
            }
        )
    if opportunities:
        findings.append(
            {
                "id": "lighthouse_opportunities_present",
                "severity": "medium",
                "message": f"{len(opportunities)} Lighthouse opportunities with score below 0.5.",
                "evidence": opportunities[:12],
            }
        )
    distillate = {
        "summary": summary,
        "core_metrics": metric_rows,
        "top_opportunities": opportunities[:20],
        "citations": ["https://github.com/danielsogl/lighthouse-mcp-server"],
    }
    return summary, findings, distillate


def build_report(cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    url = args.url or f"https://{nested_get(cfg, 'project.domain') or ''}/"
    raw_payload = load_json(args.input_json)
    run_meta: dict[str, Any] = {"live": False}
    if raw_payload is None and args.live:
        raw_payload, run_meta = run_lighthouse(url, args.categories, args.device, args.lighthouse_arg or [])
        run_meta["live"] = True

    if raw_payload is None:
        summary = {"url": url, "device": args.device, "scores": {}, "mode": "needs_input"}
        findings = [
            {
                "id": "lighthouse_input_required",
                "severity": "info",
                "message": "Provide --input-json from Lighthouse or rerun with --live --url to execute a public Lighthouse audit.",
                "evidence": run_meta,
            }
        ]
        distillate = {"summary": summary, "top_findings": findings, "citations": ["https://github.com/danielsogl/lighthouse-mcp-server"]}
        status = "needs_input"
        raw_payload = {"status": status, "run_meta": run_meta}
    else:
        summary, findings, distillate = distill(raw_payload, url, args.device)
        status = "ready"
    return write_technical_report(
        project_root,
        slug="lighthouse-audit",
        provider="lighthouse",
        title="Lighthouse and Core Web Vitals Audit",
        status=status,
        summary=summary,
        findings=findings,
        raw_payload={"payload": raw_payload, "run_meta": run_meta},
        distillate_payload=distillate,
        write=args.write,
        commands=[
            "npx -y lighthouse https://example.com --quiet --output=json --output-path=lighthouse.json --only-categories=performance,accessibility,best-practices,seo",
            "python3 ~/.codex/skills/seo-cycle/scripts/lighthouse-audit.py seo-cycle.yaml --input-json lighthouse.json --write",
        ],
        notes=["Use Lighthouse MCP when configured; this CLI wrapper keeps the same data-contract for Codex projects."],
        cache_parts={"slug": "lighthouse-audit", "url": url, "device": args.device, "payload": raw_payload},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--url", help="Target URL.")
    parser.add_argument("--input-json", help="Lighthouse JSON report.")
    parser.add_argument("--live", action="store_true", help="Run Lighthouse via npx. Makes public HTTP requests.")
    parser.add_argument("--device", choices=("mobile", "desktop"), default="mobile")
    parser.add_argument("--categories", default="performance,accessibility,best-practices,seo")
    parser.add_argument("--lighthouse-arg", action="append", default=[], help="Extra raw argument for Lighthouse live mode.")
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
        print(f"Lighthouse audit status: {report['status']}")
        print(f"Report: {report.get('paths', {}).get('markdown', 'not written')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
