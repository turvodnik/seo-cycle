#!/usr/bin/env python3
"""Audit public SEO copy for human-quality and project-rule issues.

This is the content counterpart to the publish/preflight layer. It is
deliberately opinionated: public text should sound like a specialist/editor,
not like a technical SEO brief.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from wiki_common import CONFIG, WIKI_ROOT, clean_text, ensure_wiki_tree, utc_now, write_json


project_cfg = CONFIG.get("project", {}) if isinstance(CONFIG.get("project"), dict) else {}
TECHNICAL_BRAND = str(project_cfg.get("brand_name_technical") or "").strip()
PUBLIC_BRAND = str(project_cfg.get("brand_name_user_facing") or project_cfg.get("name") or "").strip()


BLOCKERS = {
    "service_terms": re.compile(r"\b(?:интент|семантик\w*|сущност\w*|SEO[-\s]?текст|source-lock|research package)\b", re.I),
    "visible_raw_url": re.compile(r"(?<!\]\()https?://[^\s)]+", re.I),
    "stock_claim": re.compile(r"\b(?:в наличии|есть в наличии|остатк\w+|цены актуальн\w+|актуальн\w+ выгрузк\w+)\b", re.I),
    "service_note": re.compile(r"(?:материал подготовлен|перед покупкой проверяйте|на дату выгрузки|на момент выгрузки)", re.I),
}

if TECHNICAL_BRAND and PUBLIC_BRAND and TECHNICAL_BRAND.lower() != PUBLIC_BRAND.lower():
    BLOCKERS["technical_brand_in_public_copy"] = re.compile(rf"\b{re.escape(TECHNICAL_BRAND)}\b", re.I)

WARNINGS = {
    "weak_heading_characteristics": re.compile(r"какие\s+характеристики\s+смотреть", re.I),
    "weak_heading_sections": re.compile(r"какие\s+разделы\s+открыть", re.I),
    "seo_process_phrase": re.compile(r"\b(?:под\s+эти\s+запросы|для\s+охвата\s+запросов|мы\s+не\s+пишем)\b", re.I),
    "visible_slug_like_text": re.compile(r"\b[a-z0-9]+(?:-[a-z0-9]+){2,}\b", re.I),
    "generic_cta": re.compile(r"(?:откройте\s+карточк\w+|сравните\s+назначение|свяжитесь\s+с\s+нами\s+для\s+подбора)", re.I),
    "unsupported_superlative": re.compile(r"\b(?:лучше\s+всех|самый\s+лучший|без\s+аналогов|гарантированно\s+лучше)\b", re.I),
}

POSITIVE_SIGNALS = {
    "practical_application": re.compile(r"\b(?:для\s+пола|для\s+кровли|для\s+стен|для\s+швов|для\s+перегородок|для\s+фундамента|для\s+цоколя)\b", re.I),
    "selection_logic": re.compile(r"\b(?:выбирают|подходит|уместен|важно|зависит|сравнивать|проверяют)\b", re.I),
    "evidence_terms": re.compile(r"\b(?:ГОСТ|класс|плотность|толщина|формат|производитель|инструкция|основание|узел)\b", re.I),
    "limitations": re.compile(r"\b(?:не\s+подходит|нельзя|ограничение|проверить|совместимость|условия\s+применения)\b", re.I),
}


def strip_frontmatter(text: str) -> str:
    if text.startswith("---\n") and "\n---\n" in text:
        return text.split("\n---\n", 1)[1]
    return text


def public_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = strip_frontmatter(text)
    for marker in ["\n## JSON-LD", "\n## Внутренние ссылки", "\n## Чек-лист", "\n## Альты"]:
        index = text.find(marker)
        if index > 0:
            text = text[:index]
            break
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"href=[\"'][^\"']+[\"']", "", text, flags=re.I)
    return clean_text(text)


def snippet(text: str, match: re.Match[str]) -> str:
    return " ".join(text[max(0, match.start() - 90): min(len(text), match.end() + 90)].split())


def audit_file(path: Path) -> dict[str, Any]:
    text = public_text(path)
    issues: list[dict[str, Any]] = []
    for code, pattern in BLOCKERS.items():
        for match in pattern.finditer(text):
            issues.append({"severity": "blocker", "code": code, "snippet": snippet(text, match)})
            break
    for code, pattern in WARNINGS.items():
        for match in pattern.finditer(text):
            value = match.group(0).lower()
            if code == "visible_slug_like_text" and value in {"meta-title", "meta-description"}:
                continue
            issues.append({"severity": "warning", "code": code, "snippet": snippet(text, match)})
            break

    positive = {code: bool(pattern.search(text)) for code, pattern in POSITIVE_SIGNALS.items()}
    score = 100
    score -= 30 * sum(1 for issue in issues if issue["severity"] == "blocker")
    score -= 8 * sum(1 for issue in issues if issue["severity"] == "warning")
    score += 4 * sum(1 for ok in positive.values() if ok)
    score = max(0, min(100, score))
    blockers = [issue for issue in issues if issue["severity"] == "blocker"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    return {
        "file": str(path),
        "chars": len(text),
        "score": score,
        "positive_signals": positive,
        "issues": issues,
        "blockers": len(blockers),
        "warnings": len(warnings),
        "decision": "blocked" if blockers else "pass_with_warnings" if warnings else "pass",
    }


def candidate_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(p for p in sorted(path.rglob("*")) if p.suffix.lower() in {".md", ".html", ".txt"})
        elif path.exists():
            files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    ensure_wiki_tree()
    reports = [audit_file(path.resolve()) for path in candidate_files(args.paths)]
    blockers = sum(item["blockers"] for item in reports)
    warnings = sum(item["warnings"] for item in reports)
    payload = {
        "generated_at": utc_now(),
        "files": len(reports),
        "blockers": blockers,
        "warnings": warnings,
        "decision": "blocked" if blockers else "pass_with_warnings" if warnings else "pass",
        "reports": reports,
    }

    if args.write:
        out = WIKI_ROOT / "reports" / "content-taste-gate.json"
        write_json(out, payload)
        md_lines = [
            "# Content Taste Gate",
            "",
            f"- Generated: `{payload['generated_at']}`",
            f"- Files: `{payload['files']}`",
            f"- Decision: `{payload['decision']}`",
            f"- Blockers: `{blockers}`",
            f"- Warnings: `{warnings}`",
            "",
        ]
        for item in reports:
            md_lines.append(f"## {Path(item['file']).name}")
            md_lines.append(f"- Score: `{item['score']}`")
            md_lines.append(f"- Decision: `{item['decision']}`")
            for issue in item["issues"][:8]:
                md_lines.append(f"- {issue['severity']} `{issue['code']}`: {issue['snippet']}")
            md_lines.append("")
        (WIKI_ROOT / "reports" / "content-taste-gate.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
