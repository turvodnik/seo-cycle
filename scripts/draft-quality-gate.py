#!/usr/bin/env python3
"""Validate a copy draft against a page-outline v2/v3 brief and the project rules.

Structure checks (always): H2/H3 from the outline, required internal links,
FAQ questions, a proof/citation marker, fabricated first-person expertise
(EN + RU), a broken frontmatter.

Project rules (3.1.0, only when `seo-cycle.yaml` is found and the rule is
enabled there): stop-words (`quality_gates.stop_words_check`), the
fact-check log (`quality_gates.fact_check_log_present`), image alt and inline
captions (`images.alt`, `images.captions`, `images.inline_min_per_post`),
word count (`quality_gates.word_count_min`), internal links and local signals
(`content_rules.*`). The config is looked up from the draft's directory
upwards (`--config` overrides); without a config the gate behaves as before.

Exit code follows the same pass/warn/fail scale as page-outline-quality.py
and research-package-quality.py: 0 when there are no findings or only
warnings (status "pass"/"warn"), 1 when at least one error-severity finding
is present (status "fail"), 2 on a call/config error. The JSON report always
carries the full "status" and "findings" list regardless of exit code.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any

from research_package_repair_core import (
    markdown_findings,
    normalize_space,
    normalize_url,
    print_report,
)
from seo_cycle_core import brand_voice
from seo_cycle_core.config import find_project_config, load_yaml, project_root_for
from seo_cycle_core.draft_checks import run_config_checks
from seo_cycle_core.frontmatter import split_frontmatter
from seo_cycle_core.page_types import normalize_page_type


FIRST_PERSON_EXPERTISE = re.compile(
    r"\b(in my years|my clients|from what i['’]?ve observed|i have seen|working with clients)\b"
    # 3.1.0: the Russian forms of the same fabricated-expertise claims. The
    # gate only knew English, so a Russian draft with «по моему опыту» passed
    # the E-E-A-T guard. Plain brand voice («мы доставляем») is not matched.
    r"|(?<!\w)(по моему опыту|из моего опыта|за годы (?:моей )?работы я|за \d+ лет работы я"
    r"|мои клиенты|моих клиентов|моим клиентам|в нашей практике|из нашей практики"
    r"|мы (?:протестировали|проверили|испытали) (?:на (?:объекте|объектах|себе|своих объектах)))(?!\w)",
    re.I,
)


class OutlineShapeError(ValueError):
    """Outline is valid JSON but not the object shape the gate reads (QA 3.0.1 Y3)."""


class CallError(Exception):
    """Call/config error with a ready one-line message (exit 2)."""


def _check_outline_shape(outline: Any) -> None:
    if not isinstance(outline, dict):
        raise OutlineShapeError(f"нужен JSON-объект, получено {type(outline).__name__}")
    sections = outline.get("sections")
    if sections is not None:
        if not isinstance(sections, list) or not all(isinstance(item, dict) for item in sections):
            raise OutlineShapeError("`sections` должен быть списком объектов")
        for item in sections:
            subs = item.get("h3_subsections")
            if subs is not None and not isinstance(subs, list):
                raise OutlineShapeError("`h3_subsections` должен быть списком")
    for key in ("internal_links", "faq"):
        value = outline.get(key)
        if value is not None and not isinstance(value, list):
            raise OutlineShapeError(f"`{key}` должен быть списком")


def load_outline(path: pathlib.Path) -> dict[str, Any]:
    outline = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    _check_outline_shape(outline)
    try:
        # JSON accepts a lone surrogate (`"\\ud800"`); such text cannot be
        # written or printed as UTF-8 — the gate used to crash after
        # truncating its report (QA3 3.0.1 #1).
        json.dumps(outline, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise OutlineShapeError("строка с непарным суррогатом (\\ud800–\\udfff) — не UTF-8") from exc
    return outline


def heading_set(text: str, level: int | None = None) -> set[str]:
    headings = set()
    for match in re.finditer(r"^(#{1,6})\s+(.+?)\s*$", text, flags=re.M):
        if level is not None and len(match.group(1)) != level:
            continue
        headings.add(normalize_space(match.group(2)).lower())
    return headings


def markdown_link_targets(text: str) -> set[str]:
    targets = set()
    for match in re.findall(r"\]\(([^)]+)\)", text):
        targets.add(normalize_url(match))
    for match in re.findall(r"(?<![A-Za-z0-9])/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", text):
        targets.add(normalize_url(match.strip("`),.;")))
    return {target for target in targets if target}


def has_proof_slot(text: str) -> bool:
    lower = text.lower()
    if any(marker in lower for marker in ("source:", "proof:", "evidence:", "[source", "citation:")):
        return True
    return bool(re.search(r"https?://", text))


def expected_h2(outline: dict[str, Any]) -> list[str]:
    return [normalize_space(section.get("title")) for section in outline.get("sections") or [] if section.get("level") == 2 and section.get("title")]


def expected_h3(outline: dict[str, Any]) -> list[str]:
    headings = []
    for section in outline.get("sections") or []:
        for child in section.get("h3_subsections") or []:
            if isinstance(child, dict) and child.get("title"):
                headings.append(normalize_space(child.get("title")))
            elif isinstance(child, str):
                headings.append(normalize_space(child))
    return headings


def is_public_handoff_draft(draft_path: pathlib.Path) -> bool:
    name = draft_path.name.lower()
    return ".public." in name or ".wp-draft." in name or name.endswith(".public.md") or name.endswith(".wp-draft.md")


def _read_input(path: pathlib.Path, label: str, reader: Any) -> Any:
    """Read one input and turn every call error into a CallError that names
    THIS file (QA 3.0.1 Y3: an undecodable outline used to be reported as the
    draft)."""
    try:
        return reader(path)
    except FileNotFoundError as exc:
        raise CallError(f"файл не найден: {exc.filename or path}") from exc
    except json.JSONDecodeError as exc:
        raise CallError(f"outline не разобран: {path}: {exc.msg}") from exc
    except OutlineShapeError as exc:
        raise CallError(f"outline не той формы: {path}: {exc}") from exc
    except (IsADirectoryError, PermissionError, UnicodeDecodeError, OSError) as exc:
        raise CallError(f"файл не прочитан ({label}): {path}: {exc}") from exc


def resolve_config(draft_path: pathlib.Path, explicit: pathlib.Path | None) -> tuple[pathlib.Path | None, dict[str, Any]]:
    """The project config for this draft: `--config`, else the nearest one up the tree.

    `load_yaml` prints one `ERROR:` line and exits 2 on a broken file — the
    same rc-2 contract as the gate's other call errors. An empty file means
    "no rules", like no config at all.
    """
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.exists():
            raise CallError(f"конфиг не найден: {path}")
        return path, load_yaml(path)
    path = find_project_config(draft_path.parent)
    if path is None:
        return None, {}
    return path, load_yaml(path)


def raw_page_type(outline: dict[str, Any], frontmatter: dict[str, Any]) -> Any:
    page = outline.get("page") if isinstance(outline.get("page"), dict) else {}
    return frontmatter.get("page_type") or page.get("page_type")


def page_type_of(outline: dict[str, Any], frontmatter: dict[str, Any]) -> str:
    return normalize_page_type(raw_page_type(outline, frontmatter))


def real_expert_in_brief(outline: dict[str, Any]) -> bool:
    guard = outline.get("eeat_guard") if isinstance(outline.get("eeat_guard"), dict) else {}
    return guard.get("expert_author_mode") == "real_expert_allowed"


def build_report(
    draft_path: pathlib.Path,
    outline_path: pathlib.Path,
    config_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    draft_path = draft_path.expanduser().resolve()
    outline_path = outline_path.expanduser().resolve()
    text = _read_input(draft_path, "черновик", lambda p: p.read_text(encoding="utf-8"))
    outline = _read_input(outline_path, "outline", load_outline)
    cfg_path, cfg = resolve_config(draft_path, config_path)
    front = split_frontmatter(text)
    page_type = page_type_of(outline, front.data)
    public_handoff = is_public_handoff_draft(draft_path)
    h2 = heading_set(text, 2)
    h3 = heading_set(text, 3)
    links = markdown_link_targets(text)
    findings: list[dict[str, Any]] = []

    for title in expected_h2(outline):
        if title.lower() not in h2:
            if public_handoff:
                continue
            findings.append(
                {
                    "id": "missing_h2_heading",
                    "severity": "error",
                    "location": str(draft_path),
                    "message": f"Draft is missing H2 `{title}` from outline.",
                }
            )
    for title in expected_h3(outline):
        if title.lower() not in h3:
            if public_handoff:
                continue
            findings.append(
                {
                    "id": "missing_h3_heading",
                    "severity": "warning",
                    "location": str(draft_path),
                    "message": f"Draft is missing H3 `{title}` from outline.",
                }
            )
    if FIRST_PERSON_EXPERTISE.search(text):
        if real_expert_in_brief(outline):
            # 3.1.0: the brief was generated with a real, proven author
            # (`--expert-author`, or a profile author with proof_url and
            # first_person_allowed) — first person is the approved voice.
            findings.append(
                {
                    "id": "unsafe_first_person_expertise",
                    "severity": "info",
                    "location": str(draft_path),
                    "message": "First-person expertise is allowed: the brief names a real expert author (eeat_guard.expert_author_mode).",
                }
            )
        else:
            findings.append(
                {
                    "id": "unsafe_first_person_expertise",
                    "severity": "error",
                    "location": str(draft_path),
                    "message": "Draft uses first-person expert/client claims; require real author evidence or rewrite in neutral voice.",
                }
            )
    for url in outline.get("internal_links") or []:
        normalized = normalize_url(url)
        if normalized and normalized not in links:
            findings.append(
                {
                    "id": "missing_internal_link",
                    "severity": "warning",
                    "location": normalized,
                    "message": "Required internal link from outline is missing in draft.",
                }
            )
    if not has_proof_slot(text):
        findings.append(
            {
                "id": "missing_proof_slot",
                "severity": "warning",
                "location": str(draft_path),
                "message": "Draft has no source/proof/citation marker; add evidence for claims and numbers.",
            }
        )
    faq_questions = [normalize_space(item.get("question")) for item in outline.get("faq") or [] if isinstance(item, dict)]
    for question in faq_questions:
        if question and question.lower() not in text.lower():
            if public_handoff and "## faq" in text.lower():
                continue
            findings.append(
                {
                    "id": "missing_faq_question",
                    "severity": "warning",
                    "location": str(draft_path),
                    "message": f"FAQ question `{question}` is in outline but missing in draft.",
                }
            )
    if front.error:
        findings.append(
            {
                "id": "frontmatter_invalid",
                "severity": "error",
                "location": str(draft_path),
                "message": f"Frontmatter не разобран ({front.error}): почини YAML — без него не читаются fact_check_log и метаданные.",
            }
        )
    checks_run: list[str] = []
    skipped: list[dict[str, str]] = []
    voice_profile: str | None = None
    if cfg:
        result = run_config_checks(text, front, cfg, page_type, str(draft_path))
        findings.extend(result.findings)
        checks_run, skipped = result.checks_run, result.skipped
        assert cfg_path is not None
        project_root = project_root_for(cfg_path)
        # strict: a broken profile file exits 2 with one ERROR line (load_yaml)
        profile, _error = brand_voice.load_profile(cfg, project_root, strict=True)
        if profile is not None:
            problems = brand_voice.validate_profile(profile)
            if problems:
                raise CallError(f"профиль голоса с ошибками ({len(problems)}): {problems[0]} — seo-cycle voice validate")
            findings.extend(
                brand_voice.check_draft(
                    text, profile, page_type=raw_page_type(outline, front.data) or page_type,
                    frontmatter=front.data, cfg=cfg, location=str(draft_path), already_checked=set(checks_run),
                )
            )
            checks_run.append("brand_voice")
            voice_profile = brand_voice.display_path(project_root, brand_voice.profile_path(cfg, project_root))
    else:
        skipped.append({"check": "project_rules", "reason": "seo-cycle.yaml не найден или пуст — проверяется только структура"})
    if public_handoff:
        findings.append(
            {
                "id": "public_localized_heading_check",
                "severity": "info",
                "location": str(draft_path),
                "message": "Public/WP draft uses localized reader-facing headings; exact internal outline H2/H3/FAQ placeholder matching was skipped.",
            }
        )

    has_error = any(finding.get("severity") == "error" for finding in findings)
    status = "fail" if has_error else "warn" if findings else "pass"

    return {
        "script": "draft-quality-gate",
        "status": status,
        "summary": {
            "findings": len(findings),
            "expected_h2": len(expected_h2(outline)),
            "expected_h3": len(expected_h3(outline)),
            "required_internal_links": len(outline.get("internal_links") or []),
            "public_handoff": public_handoff,
            "page_type": page_type,
            "config": str(cfg_path) if cfg_path and cfg else None,
            "checks_run": checks_run,
            "skipped_checks": skipped,
            "brand_voice_profile": voice_profile,
        },
        "outputs": {
            "json": str(draft_path.with_suffix(".draft-quality-gate.json")),
            "markdown": str(draft_path.with_suffix(".draft-quality-gate.md")),
        },
        "findings": findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return markdown_findings("Draft Quality Gate", report["summary"], report.get("findings"))


def write_outputs(draft_path: pathlib.Path, report: dict[str, Any]) -> None:
    draft_path = draft_path.expanduser().resolve()
    # Encode both reports before opening either file: an encoding error must
    # not leave a truncated 0-byte report behind (QA3 3.0.1 #1).
    json_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    md_bytes = render_markdown(report).encode("utf-8")
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.with_suffix(".draft-quality-gate.json").write_bytes(json_bytes)
    draft_path.with_suffix(".draft-quality-gate.md").write_bytes(md_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", help="Draft markdown file")
    parser.add_argument("--outline", required=True, help="page-outline-v2 JSON file")
    parser.add_argument("--config", help="seo-cycle.yaml with the project rules (default: nearest one up from the draft)")
    parser.add_argument("--write", action="store_true", help="Write draft quality reports next to the draft")
    parser.add_argument("--format", choices=("json", "md"), default="md")
    args = parser.parse_args()

    # Call/config errors (missing file, unparsable outline) are exit 2 with one
    # line — not a traceback; 1 stays reserved for "gate failed" (T-182 F12).
    try:
        report = build_report(
            pathlib.Path(args.draft),
            pathlib.Path(args.outline),
            pathlib.Path(args.config) if args.config else None,
        )
    except CallError as exc:
        print(str(exc).replace("\n", " "), file=sys.stderr)
        return 2
    if args.write:
        # An unwritable report is a call error too: rc 1 here would let a
        # caller fall back to the stale report on disk (QA 3.0.1 R2, path 2).
        try:
            write_outputs(pathlib.Path(args.draft), report)
        except (OSError, UnicodeError) as exc:
            print(f"отчёт не записан: {getattr(exc, 'filename', None) or args.draft}: "
                  f"{getattr(exc, 'strerror', None) or exc}", file=sys.stderr)
            return 2
    print_report(report, args.format, render_markdown(report))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
