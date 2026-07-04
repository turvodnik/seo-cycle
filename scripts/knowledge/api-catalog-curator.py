#!/usr/bin/env python3
"""Create a curated SEO/marketing API catalog for the project wiki.

The API-mega-list repository is useful as a discovery catalog, not as a direct
integration list. This script creates a scored, project-safe shortlist.
"""

from __future__ import annotations

import argparse
import json

from wiki_common import WIKI_ROOT, ensure_wiki_tree, utc_now, write_json, write_jsonl


SEED_CANDIDATES = [
    {
        "name": "XMLRiver",
        "category": "serp",
        "use_cases": ["Google/Yandex SERP", "Wordstat", "commercial snippets", "AI overview signals"],
        "region_fit": "RU+global",
        "cost_model": "paid-low-cost",
        "default": "enabled_with_budget",
        "why": "Дешёвый слой SERP/Wordstat/колдунщиков для Яндекса и Google, полезен для семантики и проверки выдачи.",
    },
    {
        "name": "Google Search Console API",
        "category": "owned-search",
        "use_cases": ["queries", "pages", "index status", "performance"],
        "region_fit": "global",
        "cost_model": "free",
        "default": "enabled",
        "why": "Главный факт-источник по Google: клики, показы, позиции, URL Inspection.",
    },
    {
        "name": "Yandex Webmaster API",
        "category": "owned-search",
        "use_cases": ["indexing", "recrawl", "diagnostics", "links"],
        "region_fit": "RU",
        "cost_model": "free",
        "default": "enabled",
        "why": "Главный факт-источник по Яндексу и переобходу.",
    },
    {
        "name": "Bing Webmaster / IndexNow",
        "category": "owned-search",
        "use_cases": ["indexing", "IndexNow", "Bing/Copilot visibility"],
        "region_fit": "global",
        "cost_model": "free",
        "default": "enabled",
        "why": "Полезен для Bing/Copilot и автоматической отправки URL через IndexNow.",
    },
    {
        "name": "NeuronWriter",
        "category": "content-optimization",
        "use_cases": ["SERP terms", "content score", "plagiarism checks", "content editor"],
        "region_fit": "global",
        "cost_model": "subscription-owned",
        "default": "enabled_with_limits",
        "why": "Уже куплен; использовать лимиты для scoring и plagiarism перед публикацией.",
    },
    {
        "name": "Keyso",
        "category": "keyword-competitor",
        "use_cases": ["RU keywords", "competitors", "lost queries", "visibility"],
        "region_fit": "RU",
        "cost_model": "subscription-owned",
        "default": "enabled_with_limits",
        "why": "Полезен для Яндекс/Google RU семантики и конкурентного анализа.",
    },
    {
        "name": "Serpstat",
        "category": "keyword-technical",
        "use_cases": ["keyword metrics", "site audit", "competitors", "rank tracking"],
        "region_fit": "global+RU",
        "cost_model": "subscription/credits",
        "default": "guarded",
        "why": "Использовать для technical audit и метрик, но с квотами.",
    },
    {
        "name": "WriterZen",
        "category": "keyword-planning",
        "use_cases": ["topic discovery", "keyword explorer", "keyword planner", "clusters"],
        "region_fit": "Google/global",
        "cost_model": "subscription-owned-browser",
        "default": "browser_export",
        "why": "API нет; использовать браузерные экспорты и импорт в research package.",
    },
    {
        "name": "Perplexity",
        "category": "source-backed-research",
        "use_cases": ["source-backed research", "question mining", "self-audit"],
        "region_fit": "global",
        "cost_model": "subscription-owned",
        "default": "enabled_with_cache",
        "why": "Запускать как обязательный evidence-источник с кэшем.",
    },
    {
        "name": "Google Cloud Natural Language",
        "category": "entity-nlp",
        "use_cases": ["entities", "content classification", "syntax", "moderation"],
        "region_fit": "global",
        "cost_model": "paid-guarded-budget",
        "default": "guarded",
        "why": "Использовать ограниченно для entity audit с кэшем и бюджетом.",
    },
    {
        "name": "Lighthouse",
        "category": "technical-quality",
        "use_cases": ["performance", "SEO", "accessibility", "best practices"],
        "region_fit": "global",
        "cost_model": "free-local",
        "default": "enabled",
        "why": "Бесплатный технический слой для сайта и шаблонов.",
    },
    {
        "name": "Linkinator",
        "category": "link-quality",
        "use_cases": ["broken links", "redirects", "anchors"],
        "region_fit": "global",
        "cost_model": "free-local",
        "default": "enabled",
        "why": "Проверять 404, редиректы и качество внутренних ссылок.",
    },
]


def score(candidate: dict) -> int:
    value = 0
    if candidate["cost_model"] in {"free", "free-local", "subscription-owned", "subscription-owned-browser"}:
        value += 3
    if "RU" in candidate["region_fit"]:
        value += 2
    if candidate["default"] in {"enabled", "enabled_with_limits", "enabled_with_cache", "enabled_with_budget"}:
        value += 2
    if candidate["category"] in {"owned-search", "serp", "keyword-competitor", "content-optimization"}:
        value += 2
    if candidate["default"] == "guarded":
        value -= 1
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    ensure_wiki_tree()
    rows = [{**item, "score": score(item), "reviewed_at": utc_now()} for item in SEED_CANDIDATES]
    rows = sorted(rows, key=lambda item: (-item["score"], item["name"]))
    payload = {
        "generated_at": utc_now(),
        "source_catalogs": [
            "https://github.com/cporter202/API-mega-list",
            "project-owned subscriptions and integrations",
        ],
        "policy": "API candidates are discovery records only. No integration is enabled without explicit keys, quota policy, ToS review, and project fit.",
        "candidates": rows,
    }

    if args.write:
        write_json(WIKI_ROOT / "api-catalog" / "api-catalog.json", payload)
        write_jsonl(WIKI_ROOT / "api-catalog" / "api-candidates.jsonl", rows)
        lines = [
            "# API Catalog",
            "",
            f"- Generated: `{payload['generated_at']}`",
            "- Source: API-mega-list + project-owned tools",
            "",
            "| API | Category | Score | Default | Cost | Use |",
            "|---|---|---:|---|---|---|",
        ]
        for item in rows:
            lines.append(
                f"| {item['name']} | {item['category']} | {item['score']} | {item['default']} | {item['cost_model']} | {', '.join(item['use_cases'][:3])} |"
            )
        (WIKI_ROOT / "api-catalog" / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps({"status": "ok", "candidates": len(rows), "path": str(WIKI_ROOT / "api-catalog")}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
