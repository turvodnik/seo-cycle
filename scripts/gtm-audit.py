#!/usr/bin/env python3
"""Audit a Google Tag Manager container: tag/trigger/variable map + hygiene findings.

Primary mode is offline: feed it a standard GTM container export
(Admin → Export Container → JSON) via --input-file — no API access needed.
Optional --live mode reads the default workspace through the GTM API v2
(service account via GOOGLE_APPLICATION_CREDENTIALS, scope tagmanager.readonly,
env GTM_ACCOUNT_ID + GTM_CONTAINER_ID).

Findings (report-only, nothing is changed in the container):
  paused tags, tags without firing triggers, duplicate tags (same type + key
  params), orphan triggers/variables, missing consent settings, duplicate
  GA4/Metrika base tags.

Output: seo/tracking/gtm-audit.md/json (+latest) with --write.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from collections import Counter
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for
from seo_cycle_core.logging_setup import setup_logging
from seo_cycle_core.reports import write_report_bundle

log = setup_logging("gtm-audit")

GTM_SCOPE = "https://www.googleapis.com/auth/tagmanager.readonly"
API_BASE = "https://tagmanager.googleapis.com/tagmanager/v2"

ANALYTICS_TAG_TYPES = {"gaawc": "GA4 config", "gaawe": "GA4 event", "ua": "Universal Analytics",
                       "cvt_metrika": "Yandex Metrika (custom)", "html": "Custom HTML"}


def load_container_export(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("containerVersion") if isinstance(data, dict) else None
    if not isinstance(version, dict):
        raise ValueError("not a GTM container export: missing containerVersion")
    return version


def live_fetch() -> dict[str, Any]:
    try:
        from google.auth import default as adc_default
        from google.auth.transport.requests import Request as AuthRequest
        from google.oauth2 import service_account
    except ImportError:
        raise RuntimeError("google-auth is required for --live: pip3 install google-auth")
    account_id = os.environ.get("GTM_ACCOUNT_ID", "")
    container_id = os.environ.get("GTM_CONTAINER_ID", "")
    if not account_id or not container_id:
        raise RuntimeError("set GTM_ACCOUNT_ID and GTM_CONTAINER_ID env")
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and pathlib.Path(creds_path).expanduser().exists():
        creds = service_account.Credentials.from_service_account_file(creds_path, scopes=[GTM_SCOPE])
    else:
        creds, _ = adc_default(scopes=[GTM_SCOPE])
    creds.refresh(AuthRequest())

    def get(url: str) -> dict[str, Any]:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {creds.token}"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    parent = f"{API_BASE}/accounts/{account_id}/containers/{container_id}"
    workspaces = get(f"{parent}/workspaces").get("workspace") or []
    if not workspaces:
        raise RuntimeError("no workspaces visible for this container")
    ws_path = workspaces[0]["path"]
    return {
        "container": get(parent),
        "tag": get(f"{API_BASE}/{ws_path}/tags").get("tag") or [],
        "trigger": get(f"{API_BASE}/{ws_path}/triggers").get("trigger") or [],
        "variable": get(f"{API_BASE}/{ws_path}/variables").get("variable") or [],
    }


def tag_key(tag: dict[str, Any]) -> str:
    params = {p.get("key"): p.get("value") for p in tag.get("parameter") or [] if isinstance(p, dict)}
    ident = params.get("measurementIdOverride") or params.get("tagId") or params.get("trackingId") \
        or params.get("html", "")[:120] or params.get("measurementId", "")
    return f"{tag.get('type')}::{ident}"


def referenced_variables(blob: Any, found: set[str]) -> None:
    if isinstance(blob, dict):
        for value in blob.values():
            referenced_variables(value, found)
    elif isinstance(blob, list):
        for item in blob:
            referenced_variables(item, found)
    elif isinstance(blob, str):
        start = 0
        while True:
            open_idx = blob.find("{{", start)
            if open_idx < 0:
                break
            close_idx = blob.find("}}", open_idx)
            if close_idx < 0:
                break
            found.add(blob[open_idx + 2:close_idx].strip())
            start = close_idx + 2


def build_report(version: dict[str, Any]) -> dict[str, Any]:
    tags = [t for t in version.get("tag") or [] if isinstance(t, dict)]
    triggers = [t for t in version.get("trigger") or [] if isinstance(t, dict)]
    variables = [v for v in version.get("variable") or [] if isinstance(v, dict)]
    container = version.get("container") or {}

    findings: list[dict[str, Any]] = []

    def add(finding_id: str, severity: str, title: str, evidence: Any) -> None:
        findings.append({"id": finding_id, "severity": severity, "title": title, "evidence": evidence})

    paused = [t.get("name") for t in tags if t.get("paused")]
    if paused:
        add("paused_tags", "medium", f"{len(paused)} paused tag(s) left in the container", paused[:10])

    no_trigger = [t.get("name") for t in tags if not t.get("firingTriggerId") and not t.get("paused")]
    if no_trigger:
        add("tags_without_triggers", "high", f"{len(no_trigger)} active tag(s) have no firing trigger", no_trigger[:10])

    key_counts = Counter(tag_key(t) for t in tags if not t.get("paused"))
    duplicates = {key: count for key, count in key_counts.items() if count > 1 and "::" in key and key.split("::", 1)[1]}
    if duplicates:
        add("duplicate_tags", "high",
            "Duplicate tags with the same type and target id (double counting risk)",
            [{"key": key, "count": count} for key, count in sorted(duplicates.items())[:10]])

    used_trigger_ids: set[str] = set()
    for tag in tags:
        used_trigger_ids.update(str(x) for x in tag.get("firingTriggerId") or [])
        used_trigger_ids.update(str(x) for x in tag.get("blockingTriggerId") or [])
    orphan_triggers = [t.get("name") for t in triggers if str(t.get("triggerId")) not in used_trigger_ids]
    if orphan_triggers:
        add("orphan_triggers", "low", f"{len(orphan_triggers)} trigger(s) not referenced by any tag", orphan_triggers[:10])

    referenced: set[str] = set()
    referenced_variables({"tags": tags, "triggers": triggers, "variables": variables}, referenced)
    orphan_vars = [v.get("name") for v in variables if v.get("name") not in referenced]
    if orphan_vars:
        add("orphan_variables", "low", f"{len(orphan_vars)} user variable(s) never referenced", orphan_vars[:10])

    consent_aware = [t.get("name") for t in tags if t.get("consentSettings")]
    if tags and not consent_aware:
        add("no_consent_settings", "medium",
            "No tag declares consentSettings (Consent Mode not configured)", [])

    analytics_pairs = Counter(t.get("type") for t in tags if t.get("type") in {"gaawc", "ua"} and not t.get("paused"))
    if analytics_pairs.get("gaawc", 0) > 1:
        add("multiple_ga4_config_tags", "high",
            f"{analytics_pairs['gaawc']} GA4 configuration tags fire in one container", [])

    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    findings.sort(key=lambda item: severity_rank.get(item["severity"], 0), reverse=True)
    status = "fail" if any(f["severity"] == "critical" for f in findings) else "warn" if findings else "pass"

    return {
        "audit_id": "gtm_audit",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "container": {
            "name": container.get("name"),
            "public_id": container.get("publicId"),
            "usage_context": container.get("usageContext"),
        },
        "counts": {
            "tags": len(tags),
            "active_tags": sum(1 for t in tags if not t.get("paused")),
            "triggers": len(triggers),
            "variables": len(variables),
            "findings": len(findings),
        },
        "tag_map": [
            {
                "name": t.get("name"),
                "type": t.get("type"),
                "type_label": ANALYTICS_TAG_TYPES.get(str(t.get("type")), t.get("type")),
                "paused": bool(t.get("paused")),
                "firing_triggers": [str(x) for x in t.get("firingTriggerId") or []],
            }
            for t in tags
        ],
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# GTM Container Audit",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Container: {report['container'].get('name')} (`{report['container'].get('public_id')}`)",
        f"- Status: `{report['status']}`",
        f"- Tags: {report['counts']['tags']} (active {report['counts']['active_tags']})"
        f" · triggers: {report['counts']['triggers']} · variables: {report['counts']['variables']}",
        "",
        "## Findings",
        "",
    ]
    if not report["findings"]:
        lines.append("No hygiene issues detected.")
    for finding in report["findings"]:
        lines.append(f"- **{finding['severity']}** `{finding['id']}`: {finding['title']}")
        if finding["evidence"]:
            lines.append(f"  - {json.dumps(finding['evidence'], ensure_ascii=False)[:300]}")
    lines.extend(["", "## Tag map", "", "| Tag | Type | Paused | Firing triggers |", "|---|---|---|---|"])
    for tag in report["tag_map"][:40]:
        lines.append(f"| {tag['name']} | {tag['type_label']} | {tag['paused']} | {', '.join(tag['firing_triggers']) or '—'} |")
    return "\n".join(lines) + "\n"


def output_paths(project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "tracking"
    return {
        "markdown": base / "gtm-audit.md",
        "json": base / "gtm-audit.json",
        "latest_markdown": base / "latest-gtm-audit.md",
        "latest_json": base / "latest-gtm-audit.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--input-file", help="GTM container export JSON (Admin → Export Container)")
    parser.add_argument("--live", action="store_true", help="Read the default workspace via GTM API v2 (read-only)")
    parser.add_argument("--write", action="store_true", help="Write seo/tracking/gtm-audit.* artifacts")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    cfg_path = pathlib.Path(args.config).expanduser().resolve() if args.config else find_config(pathlib.Path.cwd())
    if not cfg_path or not cfg_path.exists():
        print(f"ERROR: seo-cycle.yaml not found in {pathlib.Path.cwd()}", file=sys.stderr)
        return 2
    cfg = load_yaml(cfg_path)
    project_root = project_root_for(cfg_path)
    global log
    log = setup_logging("gtm-audit", project_root, cfg)

    if args.input_file:
        try:
            version = load_container_export(pathlib.Path(args.input_file).expanduser())
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read container export: {exc}", file=sys.stderr)
            return 2
    elif args.live:
        try:
            version = live_fetch()
        except (RuntimeError, urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"ERROR: GTM API read failed: {exc}", file=sys.stderr)
            return 1
    else:
        print(
            "Provide --input-file <container-export.json> (GTM UI → Admin → Export Container) "
            "or --live with GTM_ACCOUNT_ID/GTM_CONTAINER_ID + GOOGLE_APPLICATION_CREDENTIALS.",
            file=sys.stderr,
        )
        return 0

    report = build_report(version)
    if args.write:
        write_report_bundle(output_paths(project_root), render_markdown(report), report)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
