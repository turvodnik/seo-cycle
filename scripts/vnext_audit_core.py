#!/usr/bin/env python3
"""Shared report engine for SEO/AEO/GEO vNext audit generators.

The vNext layer is intentionally report-only. It creates project-local
diagnostics, checklists, and JSONL data-contract stubs, but it never publishes,
submits URLs, installs tracking tags, or calls paid APIs.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any

from seo_cycle_core.config import boolish, find_config, load_yaml, nested_get, policy_path, project_root_for, rel_path, write_text


SOURCES = [
    {"label": "SEO AGENTS", "url": "https://seo-agents.io/", "topic": "seo_agents_process"},
    {"label": "SEO AGENTS demo", "url": "https://seo-agents.io/demo/index.html", "topic": "seo_agents_process"},
    {
        "label": "Google AI features and your website",
        "url": "https://developers.google.com/search/docs/appearance/ai-features",
        "topic": "google_ai_search",
    },
    {
        "label": "Google AI search success tips",
        "url": "https://developers.google.com/search/blog/2025/05/succeeding-in-ai-search",
        "topic": "google_ai_search",
    },
    {
        "label": "Topvisor GEO source readiness",
        "url": "https://journal.topvisor.com/ru/seo-kitchen/become-a-source-for-ai-answers/",
        "topic": "geo",
    },
    {
        "label": "Yandex Commerce Protocol",
        "url": "https://pr-cy.ru/news/p/10699-yandex-commerce-protocol",
        "topic": "ru_commerce",
    },
    {"label": "Kokoc robots.txt", "url": "https://kokoc.com/blog/robots-txt/", "topic": "technical"},
    {
        "label": "Kokoc robots.txt errors",
        "url": "https://kokoc.com/blog/oshibki-v-fajle-robots-txt/",
        "topic": "technical",
    },
    {
        "label": "Yandex Webmaster Links",
        "url": "https://webmaster.yandex.ru/blog/perezapuskaem-razdel-ssylki-v-yandeks-vebmastere",
        "topic": "links",
    },
    {
        "label": "NotebookLM SEO knowledge base",
        "url": "https://notebooklm.google.com/notebook/8ad724f9-72ab-43be-8fcd-77239f0cc2e4",
        "topic": "expert_sources",
    },
]


AUDIT_SPECS: dict[str, dict[str, Any]] = {
    "ai_brand_audit": {
        "slug": "ai-brand-audit",
        "title": "AI Brand Audit",
        "config_key": "ai_brand_audit",
        "summary": "Pre-intake prompt pack for what AI systems already say about the brand, competitors, prices, reviews, and weaknesses.",
        "records": ["ai_visibility_checks.jsonl", "source_pack.jsonl"],
        "required": ["project.brand_name_user_facing", "project.domain", "industry.primary_categories"],
        "actions": [
            "Run branded and non-branded prompts in ChatGPT, Perplexity, Yandex Neuro, and Google AI surfaces.",
            "Record mention rate, competitor mentions, wrong claims, negative review themes, and price/product misunderstandings.",
            "Repeat monthly before content refreshes; keep prompts and responses in evidence records, not in page copy directly.",
        ],
        "prompts": [
            "Кто является лидером в нише {industry} в регионе {region}?",
            "Какие недостатки у бренда {brand} по сравнению с конкурентами?",
            "Где купить {priority_category} с доставкой в {region} и почему выбрать {brand}?",
        ],
    },
    "answer_units": {
        "slug": "answer-units-audit",
        "title": "Answer Units Audit",
        "config_key": "answer_units",
        "summary": "Citation-ready paragraph checklist using thesis, context, proof, and conclusion.",
        "records": ["answer_units.jsonl", "synthetic_prompts.jsonl", "entity_coverage.jsonl"],
        "required": ["industry.primary_categories", "tone.description"],
        "actions": [
            "For each cluster, create answer paragraphs that make sense without surrounding article context.",
            "Attach one sub-intent, one entity set, one proof/evidence item, and one synthetic AI prompt to every answer unit.",
            "Keep FAQ and Answer Units separate: FAQ answers close questions; Answer Units are reusable citation paragraphs.",
        ],
    },
    "eeat_evidence": {
        "slug": "eeat-evidence-map",
        "title": "E-E-A-T Evidence Map",
        "config_key": "eeat_evidence",
        "summary": "Evidence inventory for people, organization, products, certifications, reviews, cases, and sameAs signals.",
        "records": ["eeat_evidence.jsonl", "source_pack.jsonl"],
        "required": ["business_profile.legal_name", "business_profile.url", "business_profile.same_as"],
        "actions": [
            "Map authors, experts, certificates, licenses, reviews, cases, photos, and official documents to page surfaces.",
            "Validate Organization, Person, Product, and LocalBusiness schema against visible page content.",
            "Flag claims without proof before publishing or refreshing important pages.",
        ],
    },
    "geo_kpi": {
        "slug": "geo-kpi-model",
        "title": "GEO KPI Model",
        "config_key": "geo_kpi",
        "summary": "Measurement model for AI mention rate, citation share, answer accuracy, source diversity, and conversion quality.",
        "records": ["ai_visibility_checks.jsonl", "synthetic_prompts.jsonl", "traffic_diagnostics.jsonl"],
        "required": ["project.domain", "engines", "governance.budget_policy.monthly_llm_usd_cap"],
        "actions": [
            "Measure branded and non-branded prompt visibility separately.",
            "Track answer accuracy and cited source diversity, not only clicks.",
            "Use Search Console traffic as the base; AI surfaces are separate evidence checks until APIs expose stable reporting.",
        ],
    },
    "server_logs": {
        "slug": "log-bot-audit",
        "title": "Server Log / AI Bot Audit",
        "config_key": "server_logs",
        "summary": "Manual access-log upload audit for search bots, AI bots, crawl waste, 404/5xx, parameters, and faceted pages.",
        "records": ["traffic_diagnostics.jsonl", "ai_visibility_checks.jsonl"],
        "required": ["server_logs.ingestion_mode"],
        "actions": [
            "Upload sanitized access logs manually; do not require SSH/SFTP in the default workflow.",
            "Review Googlebot, YandexBot, Bingbot, GPTBot, ClaudeBot, PerplexityBot, Applebot, and generic crawlers.",
            "Use GoAccess summaries when available; keep raw logs on disk and only load aggregates into context.",
        ],
    },
    "technical_guardrails": {
        "slug": "technical-guardrails-audit",
        "title": "Technical SEO Guardrails",
        "config_key": "technical_guardrails",
        "summary": "Robots, indexability, canonical, redirects, AJAX/JS SEO, and structured-data visibility checks.",
        "records": ["traffic_diagnostics.jsonl", "source_pack.jsonl"],
        "required": ["policy_files.data_collection_map"],
        "actions": [
            "Validate robots.txt groups, sitemap links, unsupported noindex directives, CSS/JS blocking, and preview controls.",
            "Check that important content is available in text/rendered DOM, not only hidden AJAX responses.",
            "Use noindex/nosnippet/max-snippet controls for previews; do not rely on robots.txt to remove indexed URLs.",
        ],
    },
    "snippet_sitemap": {
        "slug": "snippet-sitemap-audit",
        "title": "Snippet and Sitemap Audit",
        "config_key": "snippet_sitemap",
        "summary": "XML/HTML sitemap, title/description/snippet, canonical, schema, and orphan-page review.",
        "records": ["traffic_diagnostics.jsonl", "entity_coverage.jsonl"],
        "required": ["project.domain"],
        "actions": [
            "Compare XML sitemap, HTML sitemap, canonical URLs, and known important pages.",
            "Review title links, meta descriptions, snippet controls, and schema-visible text consistency.",
            "Find orphan and low-value URLs before submitting missing important pages for indexing.",
        ],
    },
    "traffic_drop": {
        "slug": "traffic-drop-diagnostics",
        "title": "Traffic Drop Diagnostics",
        "config_key": "traffic_diagnostics",
        "summary": "Traffic-loss playbook for indexation, robots, sitemap, canonical, demand shifts, competitors, updates, and snippets.",
        "records": ["traffic_diagnostics.jsonl"],
        "required": ["engines"],
        "actions": [
            "Separate demand decline, ranking loss, indexing loss, technical breakage, and snippet/CTR loss.",
            "Compare by page type, query group, device, region, and search engine before proposing content rewrites.",
            "When access is missing, fall back to public crawl, SERP checks, robots/sitemap/schema, and server logs if provided.",
        ],
    },
    "cannibalization": {
        "slug": "cannibalization-audit",
        "title": "Query Cannibalization Audit",
        "config_key": "cannibalization",
        "summary": "Find URL conflicts where multiple pages compete for one intent or AI answer surface.",
        "records": ["traffic_diagnostics.jsonl", "sub_intents.jsonl"],
        "required": ["project.domain"],
        "actions": [
            "Group URLs by normalized query, entity, sub-intent, and page target.",
            "Decide whether to merge, canonicalize, noindex, strengthen internal links, or split intent surfaces.",
            "Prioritize conflicts with commercial/GEO value or declining CTR/rank.",
        ],
    },
    "ru_commerce": {
        "slug": "ru-commerce-readiness",
        "title": "RU Commerce / Yandex Readiness",
        "config_key": "ru_commerce",
        "summary": "Yandex Commerce Protocol, Yandex Tag Manager policy, product feeds, schema, snippets, and Alice readiness.",
        "records": ["commercial_factors.jsonl", "local_seo_signals.jsonl"],
        "required": ["project_type", "locale.country", "sources.yandex_merchant"],
        "actions": [
            "For ecommerce projects, review Yandex Merchant/feed errors before YCP/Alice workflows.",
            "Use Yandex Tag Manager as the preferred tag layer for RF projects when foreign analytics counters are forbidden.",
            "Keep paid ads and checkout integrations approval-gated; do not enable billing-dependent services by default.",
        ],
    },
    "offpage_risk": {
        "slug": "offpage-risk-audit",
        "title": "Off-page / Links Risk Audit",
        "config_key": "offpage_risk",
        "summary": "Donor/acceptor, anchor placement, Yandex Webmaster Links, content islands, and high-risk PBN/drop-domain review.",
        "records": ["source_pack.jsonl", "eeat_evidence.jsonl"],
        "required": ["sources.yandex_webmaster_history", "project.domain"],
        "actions": [
            "Use Yandex Webmaster Links and backlink tools for evidence before link recommendations.",
            "Separate safe content islands and outreach from PBN/drop-domain tactics.",
            "Mark PBN and drop-domain findings as high-risk competitor intelligence, not default recommendations.",
        ],
    },
    "conversion_sxo": {
        "slug": "conversion-sxo-audit",
        "title": "Traffic / SXO / Conversion Audit",
        "config_key": "conversion_sxo",
        "summary": "Bounce-rate, CR, pricing UX, lead blocks, FAQ, snippets, trust blocks, and commercial factor readiness.",
        "records": ["commercial_factors.jsonl", "traffic_diagnostics.jsonl"],
        "required": ["sales_channels", "target_audiences"],
        "actions": [
            "Audit conversion paths and commercial blocks before scaling informational traffic.",
            "Review price presentation, delivery, guarantees, stock, comparison blocks, forms, and phone/checkout friction.",
            "Treat AI Overview/AI Mode clicks as potentially higher quality; measure leads and orders, not only sessions.",
        ],
    },
    "expert_sources": {
        "slug": "expert-source-pack",
        "title": "Expert Source Pack",
        "config_key": "expert_sources",
        "summary": "Curated source queue for NotebookLM, articles, videos, transcripts, citations, and implementation gaps.",
        "records": ["source_pack.jsonl", "eeat_evidence.jsonl"],
        "required": ["expert_sources.notebooklm_url"],
        "actions": [
            "Treat NotebookLM as curated expert evidence, not volume/KD data.",
            "Extract source notes, gap matrix, claim/evidence rows, and implementation recommendations.",
            "Keep full transcripts out of normal context; store distillates, citations, and source excerpts.",
        ],
    },
}


BOT_PATTERNS = {
    "googlebot": re.compile(r"Googlebot", re.I),
    "yandexbot": re.compile(r"YandexBot|YandexMobileBot", re.I),
    "bingbot": re.compile(r"bingbot", re.I),
    "gptbot": re.compile(r"GPTBot|ChatGPT-User|OpenAI", re.I),
    "claudebot": re.compile(r"ClaudeBot|Claude-User", re.I),
    "perplexitybot": re.compile(r"PerplexityBot", re.I),
    "applebot": re.compile(r"Applebot", re.I),
}


def missing(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip() in {"", "not_configured", "__PROJECT_NAME__", "__DOMAIN__", "__DATE__"}
    return value in (None, [], {})


def output_paths(spec: dict[str, Any], cfg: dict[str, Any], project_root: pathlib.Path) -> dict[str, pathlib.Path]:
    slug = str(spec["slug"])
    policy_base = slug.replace("-", "_")
    md = policy_path(cfg, project_root, f"{policy_base}_report", f"seo/vnext/{slug}.md")
    js = policy_path(cfg, project_root, f"{policy_base}_json", f"seo/vnext/{slug}.json")
    latest_md = policy_path(cfg, project_root, f"latest_{policy_base}", f"seo/vnext/latest-{slug}.md")
    latest_json = policy_path(cfg, project_root, f"latest_{policy_base}_json", f"seo/vnext/latest-{slug}.json")
    return {"markdown": md, "json": js, "latest_markdown": latest_md, "latest_json": latest_json}


def project_summary(cfg: dict[str, Any]) -> dict[str, Any]:
    project = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    locale = cfg.get("locale", {}) if isinstance(cfg.get("locale"), dict) else {}
    industry = cfg.get("industry", {}) if isinstance(cfg.get("industry"), dict) else {}
    return {
        "name": project.get("name"),
        "domain": project.get("domain"),
        "brand": project.get("brand_name_user_facing") or project.get("name"),
        "project_type": cfg.get("project_type"),
        "cms": cfg.get("cms"),
        "country": locale.get("country"),
        "region": locale.get("region"),
        "city": locale.get("city"),
        "language": locale.get("language"),
        "industry": industry.get("name"),
        "primary_categories": industry.get("primary_categories", []),
    }


def config_status(cfg: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    block = cfg.get(spec["config_key"], {})
    if not isinstance(block, dict):
        block = {}
    return {
        "enabled": boolish(block.get("enabled"), True),
        "mode": str(block.get("mode") or block.get("default_mode") or "report_only"),
        "paid_api_required": boolish(block.get("paid_api_required"), False),
        "writes_to_site": boolish(block.get("writes_to_site"), False),
        "cache_enabled": boolish(block.get("cache_enabled"), True),
    }


def required_findings(cfg: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for field in spec.get("required", []):
        value = nested_get(cfg, field)
        if missing(value):
            findings.append(
                {
                    "id": f"missing_{field.replace('.', '_')}",
                    "severity": "medium",
                    "status": "needs_input",
                    "message": f"Заполнить `{field}` для более точного отчета.",
                    "field": field,
                }
            )
    return findings


def parse_access_log(path: pathlib.Path) -> dict[str, Any]:
    counters: dict[str, collections.Counter[str]] = {
        "bots": collections.Counter(),
        "statuses": collections.Counter(),
        "methods": collections.Counter(),
    }
    faceted = 0
    total = 0
    sample_errors: list[str] = []
    status_re = re.compile(r'"\S+\s+([^"]+)\s+HTTP/[^"]+"\s+(\d{3})')
    method_re = re.compile(r'"([A-Z]+)\s+')
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        total += 1
        for bot, pattern in BOT_PATTERNS.items():
            if pattern.search(line):
                counters["bots"][bot] += 1
        if method_match := method_re.search(line):
            counters["methods"][method_match.group(1)] += 1
        if status_match := status_re.search(line):
            url, status = status_match.groups()
            counters["statuses"][status] += 1
            if "?" in url or any(marker in url for marker in ("filter", "add-to-cart", "utm_", "orderby")):
                faceted += 1
            if status.startswith(("4", "5")) and len(sample_errors) < 8:
                sample_errors.append(f"{status} {url}")
    ai_bot_requests = sum(counters["bots"][bot] for bot in ("gptbot", "claudebot", "perplexitybot", "applebot"))
    return {
        "total_lines": total,
        "bot_requests": dict(counters["bots"]),
        "status_counts": dict(counters["statuses"]),
        "method_counts": dict(counters["methods"]),
        "faceted_or_parameter_requests": faceted,
        "ai_bot_requests": ai_bot_requests,
        "sample_errors": sample_errors,
    }


def parse_robots(path: pathlib.Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    groups = 0
    sitemaps = []
    issues = []
    current_has_agent = False
    for idx, raw in enumerate(lines, 1):
        stripped = raw.strip()
        low = stripped.lower()
        if not stripped or stripped.startswith("#"):
            continue
        if low.startswith("user-agent:"):
            if not current_has_agent:
                groups += 1
            current_has_agent = True
        elif low.startswith("sitemap:"):
            sitemaps.append(stripped.split(":", 1)[1].strip())
        elif low.startswith("noindex"):
            issues.append({"line": idx, "issue": "robots_noindex_unsupported", "message": "Use meta robots/X-Robots-Tag noindex, not robots.txt noindex."})
        elif low.startswith(("allow:", "disallow:", "crawl-delay:")):
            continue
        elif ":" in stripped:
            issues.append({"line": idx, "issue": "unknown_directive", "message": stripped.split(":", 1)[0]})
    if not sitemaps:
        issues.append({"line": None, "issue": "missing_sitemap", "message": "Add Sitemap directive when possible."})
    return {"groups": groups, "sitemaps": sitemaps, "issues": issues, "line_count": len(lines)}


def parse_cannibalization_csv(path: pathlib.Path) -> dict[str, Any]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    by_query: dict[str, set[str]] = collections.defaultdict(set)
    for row in rows:
        query = (row.get("query") or row.get("keyword") or "").strip().lower()
        url = (row.get("url") or row.get("page") or "").strip()
        if query and url:
            by_query[query].add(url)
    conflicts = [
        {"query": query, "url_count": len(urls), "urls": sorted(urls)}
        for query, urls in by_query.items()
        if len(urls) > 1
    ]
    conflicts.sort(key=lambda row: (-row["url_count"], row["query"]))
    return {"row_count": len(rows), "conflict_count": len(conflicts), "conflicts": conflicts[:25]}


def parse_traffic_csv(path: pathlib.Path) -> dict[str, Any]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    drops = []
    for row in rows:
        before = row.get("clicks_before") or row.get("sessions_before") or row.get("before")
        after = row.get("clicks_after") or row.get("sessions_after") or row.get("after")
        try:
            before_num = float(before) if before not in (None, "") else None
            after_num = float(after) if after not in (None, "") else None
        except ValueError:
            continue
        if before_num is not None and after_num is not None and after_num < before_num:
            loss = before_num - after_num
            drops.append({"url": row.get("url") or row.get("page") or "", "query": row.get("query") or "", "loss": loss})
    drops.sort(key=lambda row: row["loss"], reverse=True)
    return {"row_count": len(rows), "drop_count": len(drops), "top_drops": drops[:25]}


def specialized_evidence(audit_id: str, args: argparse.Namespace) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    if audit_id == "server_logs" and args.log:
        evidence["log_summary"] = parse_access_log(pathlib.Path(args.log))
    if audit_id == "technical_guardrails" and args.robots:
        evidence["robots_summary"] = parse_robots(pathlib.Path(args.robots))
    if audit_id == "cannibalization" and args.input:
        evidence["cannibalization_summary"] = parse_cannibalization_csv(pathlib.Path(args.input))
    if audit_id == "traffic_drop" and args.input:
        evidence["traffic_summary"] = parse_traffic_csv(pathlib.Path(args.input))
    return evidence


def extra_findings(audit_id: str, evidence: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if robots := evidence.get("robots_summary"):
        for issue in robots.get("issues", []):
            findings.append(
                {
                    "id": issue["issue"],
                    "severity": "high" if issue["issue"] == "robots_noindex_unsupported" else "medium",
                    "status": "issue",
                    "message": issue["message"],
                    "line": issue.get("line"),
                }
            )
    if logs := evidence.get("log_summary"):
        if logs.get("ai_bot_requests", 0) == 0:
            findings.append(
                {
                    "id": "no_ai_bot_requests_seen",
                    "severity": "low",
                    "status": "observe",
                    "message": "AI bot requests were not seen in the provided log sample.",
                }
            )
        if logs.get("sample_errors"):
            findings.append(
                {
                    "id": "bot_or_crawl_errors_present",
                    "severity": "high",
                    "status": "issue",
                    "message": "4xx/5xx examples exist in the log sample.",
                    "examples": logs["sample_errors"],
                }
            )
    if cannibal := evidence.get("cannibalization_summary"):
        if cannibal.get("conflict_count", 0) > 0:
            findings.append(
                {
                    "id": "query_url_conflicts_present",
                    "severity": "high",
                    "status": "issue",
                    "message": f"{cannibal['conflict_count']} query groups have multiple URLs.",
                }
            )
    if traffic := evidence.get("traffic_summary"):
        if traffic.get("drop_count", 0) > 0:
            findings.append(
                {
                    "id": "traffic_drops_present",
                    "severity": "high",
                    "status": "issue",
                    "message": f"{traffic['drop_count']} rows show decline in the supplied traffic file.",
                }
            )
    return findings


def build_report(audit_id: str, cfg_path: pathlib.Path, args: argparse.Namespace) -> dict[str, Any]:
    spec = AUDIT_SPECS[audit_id]
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    paths = output_paths(spec, cfg, project_root)
    cfg_status = config_status(cfg, spec)
    evidence = specialized_evidence(audit_id, args)
    findings = required_findings(cfg, spec) + extra_findings(audit_id, evidence)
    blockers = [
        "writes_to_site must stay false" if cfg_status["writes_to_site"] else "",
        "paid_api_required should be false for default runs" if cfg_status["paid_api_required"] else "",
    ]
    blockers = [item for item in blockers if item]
    if blockers:
        findings.append({"id": "unsafe_config", "severity": "critical", "status": "blocked", "message": "; ".join(blockers)})

    score = max(0, 100 - sum({"critical": 40, "high": 25, "medium": 12, "low": 5}.get(str(f.get("severity")), 8) for f in findings))
    project = project_summary(cfg)
    record_dir = "seo/research/vnext/vector"
    report = {
        "audit_id": audit_id,
        "slug": spec["slug"],
        "title": spec["title"],
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "project": project,
        "config": cfg_status,
        "score": score,
        "status": "blocked" if any(f.get("severity") == "critical" for f in findings) else ("needs_input" if findings else "ready"),
        "summary": spec["summary"],
        "findings": findings,
        "actions": spec.get("actions", []),
        "prompts": [prompt.format(brand=project.get("brand") or "brand", industry=project.get("industry") or "industry", region=project.get("region") or "region", priority_category=(project.get("primary_categories") or ["category"])[0]) for prompt in spec.get("prompts", [])],
        "output_records": [f"{record_dir}/{name}" for name in spec.get("records", [])],
        "source_policy": {
            "raw_data_in_context": False,
            "paid_api_default": "disabled",
            "publish_default": "disabled",
            "cache_first": cfg_status["cache_enabled"],
        },
        "sources": SOURCES,
        "evidence": evidence,
        "paths": {key: str(path.relative_to(project_root)) for key, path in paths.items()},
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['title']}",
        "",
        f"- Audit ID: `{report['audit_id']}`",
        f"- Generated: {report['generated_at']}",
        f"- Project: {report['project'].get('name')} ({report['project'].get('domain')})",
        f"- Status: `{report['status']}`",
        f"- Score: {report['score']}/100",
        f"- Mode: `{report['config']['mode']}`",
        "",
        "## Summary",
        "",
        report["summary"],
        "",
        "## Guardrails",
        "",
        "- Report-only by default; no publishing, index submission, tag installation, paid API calls, or ads.",
        f"- Paid API required: `{str(report['config']['paid_api_required']).lower()}`",
        f"- Writes to site: `{str(report['config']['writes_to_site']).lower()}`",
        "- Raw transcripts/logs should stay on disk; use distillates and JSONL evidence records in context.",
        "",
        "## Findings",
        "",
    ]
    if report["findings"]:
        for finding in report["findings"]:
            lines.append(f"- `{finding['severity']}` `{finding['id']}`: {finding['message']}")
    else:
        lines.append("- No blocking findings in configured inputs.")
    lines.extend(["", "## Actions", ""])
    for action in report["actions"]:
        lines.append(f"- {action}")
    if report.get("prompts"):
        lines.extend(["", "## Synthetic Prompts", ""])
        for prompt in report["prompts"]:
            lines.append(f"- {prompt}")
    lines.extend(["", "## Output Records", ""])
    for record in report["output_records"]:
        lines.append(f"- `{record}`")
    if report.get("evidence"):
        lines.extend(["", "## Parsed Evidence", "", "```json", json.dumps(report["evidence"], ensure_ascii=False, indent=2), "```"])
    lines.extend(["", "## Sources", ""])
    for source in report["sources"]:
        lines.append(f"- [{source['label']}]({source['url']})")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], cfg_path: pathlib.Path) -> None:
    project_root = project_root_for(cfg_path)
    paths = {key: rel_path(project_root, path) for key, path in report["paths"].items()}
    md = render_markdown(report)
    js = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    write_text(paths["markdown"], md)
    write_text(paths["json"], js)
    write_text(paths["latest_markdown"], md)
    write_text(paths["latest_json"], js)


def parse_args(audit_id: str, argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=AUDIT_SPECS[audit_id]["summary"])
    parser.add_argument("config", nargs="?", type=pathlib.Path, help="Path to seo-cycle.yaml. If omitted, search cwd.")
    parser.add_argument("--write", action="store_true", help="Write markdown/json reports into the project seo/vnext directory.")
    parser.add_argument("--format", choices=["json", "md"], default="md")
    parser.add_argument("--input", type=pathlib.Path, help="Optional CSV input for traffic/cannibalization audits.")
    parser.add_argument("--log", type=pathlib.Path, help="Optional sanitized access log for log-bot-audit.")
    parser.add_argument("--robots", type=pathlib.Path, help="Optional robots.txt file for technical-guardrails-audit.")
    return parser.parse_args(argv)


def main(audit_id: str, argv: list[str] | None = None) -> int:
    if audit_id not in AUDIT_SPECS:
        print(f"ERROR: unknown audit id: {audit_id}", file=sys.stderr)
        return 2
    args = parse_args(audit_id, argv)
    cfg_path = args.config or find_config(pathlib.Path.cwd())
    if not cfg_path:
        print("ERROR: seo-cycle.yaml not found", file=sys.stderr)
        return 2
    cfg_path = cfg_path.resolve()
    report = build_report(audit_id, cfg_path, args)
    if args.write:
        write_report(report, cfg_path)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0
