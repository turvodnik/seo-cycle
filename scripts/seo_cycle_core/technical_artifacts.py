"""Technical SEO report helpers.

These helpers keep live/tool raw payloads on disk and expose bounded
distillates for downstream prompts. Scripts remain report-only by default.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from .config import rel_display, write_text
from .source_artifacts import make_vector_record, stable_cache_key, utc_now_iso, write_source_artifacts


def technical_paths(project_root: pathlib.Path, slug: str) -> dict[str, pathlib.Path]:
    base = project_root / "seo" / "technical"
    return {
        "markdown": base / f"{slug}.md",
        "json": base / f"{slug}.json",
        "latest_markdown": base / f"latest-{slug}.md",
        "latest_json": base / f"latest-{slug}.json",
    }


def rel_paths(project_root: pathlib.Path, paths: dict[str, pathlib.Path]) -> dict[str, str]:
    return {key: rel_display(project_root, value) for key, value in paths.items()}


def absolute_paths(paths: dict[str, pathlib.Path]) -> dict[str, str]:
    return {key: str(value) for key, value in paths.items()}


def severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for finding in findings:
        severity = str(finding.get("severity") or "info").lower()
        counts[severity if severity in counts else "info"] += 1
    return counts


def status_from_findings(findings: list[dict[str, Any]], *, ready: bool = True) -> str:
    if not ready:
        return "needs_input"
    counts = severity_counts(findings)
    if counts["critical"] or counts["high"]:
        return "attention_required"
    return "ready"


def render_markdown(
    *,
    title: str,
    status: str,
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    source_policy: str,
    commands: list[str] | None = None,
    notes: list[str] | None = None,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Status: `{status}`",
        f"- Generated: {utc_now_iso()}",
        "",
        "## Summary",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Findings"])
    if findings:
        for item in findings:
            lines.append(
                f"- [{str(item.get('severity', 'info')).upper()}] `{item.get('id', 'finding')}` — {item.get('message', '')}"
            )
            evidence = item.get("evidence")
            if evidence not in (None, "", [], {}):
                lines.append(f"  Evidence: `{evidence}`")
    else:
        lines.append("- none")
    if commands:
        lines.extend(["", "## Next Commands"])
        lines.extend(f"- `{command}`" for command in commands)
    if notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in notes)
    lines.extend(["", "## Source Policy", source_policy])
    return "\n".join(lines) + "\n"


def write_technical_report(
    project_root: pathlib.Path,
    *,
    slug: str,
    provider: str,
    title: str,
    status: str,
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    raw_payload: dict[str, Any],
    distillate_payload: dict[str, Any],
    write: bool,
    commands: list[str] | None = None,
    notes: list[str] | None = None,
    cache_parts: dict[str, Any] | None = None,
    paid_api_used: bool = False,
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report_paths = technical_paths(project_root, slug)
    source_policy = "Keep raw tool/API data on disk; use this distillate and top-N findings in LLM context."
    markdown = render_markdown(
        title=title,
        status=status,
        summary=summary,
        findings=findings,
        source_policy=source_policy,
        commands=commands,
        notes=notes,
    )
    payload = {
        "audit_id": slug,
        "provider": provider,
        "status": status,
        "generated_at": utc_now_iso(),
        "summary": summary,
        "severity_counts": severity_counts(findings),
        "findings": findings,
        "distillate": distillate_payload,
        "writes_to_site": False,
        "paid_api_used": paid_api_used,
        "paths": rel_paths(project_root, report_paths),
    }
    if extra_payload:
        payload.update(extra_payload)
    cache_key = stable_cache_key(cache_parts or {"provider": provider, "slug": slug, "summary": summary}, label=slug)
    source_paths: dict[str, str] = {}
    if write:
        write_text(report_paths["markdown"], markdown)
        write_text(report_paths["json"], json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        write_text(report_paths["latest_markdown"], markdown)
        write_text(report_paths["latest_json"], json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        source_paths = write_source_artifacts(
            project_root,
            provider,
            cache_key,
            raw_payload=raw_payload,
            distillate_markdown=markdown,
            distillate_payload=distillate_payload,
            vector_record=make_vector_record(
                provider=provider,
                cache_key=cache_key,
                topic=slug,
                region=str(summary.get("region") or ""),
                mode=str(summary.get("mode") or "technical_audit"),
                status=status,
                summary=json.dumps(summary, ensure_ascii=False, sort_keys=True)[:1000],
                citations=distillate_payload.get("citations", []) if isinstance(distillate_payload.get("citations"), list) else [],
                metadata={"audit_id": slug, "severity_counts": severity_counts(findings)},
            ),
        )
    payload["source_paths"] = source_paths
    payload["paths"] = rel_paths(project_root, report_paths)
    return payload
