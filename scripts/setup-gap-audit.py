#!/usr/bin/env python3
"""Audit detailed first-run setup completeness for one seo-cycle project.

This report answers: "what is still not configured enough to run high-quality,
low-token SEO/marketing work for this specific project?" It reads local config,
project intake, tool stack, spend guard, automations, launch plan, and context
pack. It also writes a fillable setup questionnaire with empty answer fields.
It never prints secret values.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.reports import write_artifacts

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. `pip3 install pyyaml`", file=sys.stderr)
    sys.exit(2)


CONFIG_SEARCH_PATHS = [
    "seo-cycle.yaml",
    ".seo-cycle.yaml",
    "seo/seo-cycle.yaml",
    ".claude/seo-cycle.yaml",
]


def find_config(start_dir: pathlib.Path) -> pathlib.Path | None:
    for rel in CONFIG_SEARCH_PATHS:
        path = start_dir / rel
        if path.exists():
            return path
    return None


def project_root_for(cfg_path: pathlib.Path) -> pathlib.Path:
    if cfg_path.name in (".seo-cycle.yaml", "seo-cycle.yaml"):
        return cfg_path.parent
    if "/seo/" in str(cfg_path) or "/.claude/" in str(cfg_path):
        return cfg_path.parent.parent
    return cfg_path.parent


def rel_path(project_root: pathlib.Path, raw: str | pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(raw).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def policy_path(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> pathlib.Path:
    policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files"), dict) else {}
    return rel_path(project_root, policy_files.get(key, default))


def load_policy_json(cfg: dict[str, Any], project_root: pathlib.Path, key: str, default: str) -> dict[str, Any]:
    path = policy_path(cfg, project_root, key, default)
    candidates = [path]
    if path.suffix == ".md":
        candidates.append(path.with_suffix(".json"))
    if path.name.startswith("latest-"):
        candidates.append(path.with_name(path.name.removeprefix("latest-")).with_suffix(".json"))
    for candidate in candidates:
        data = load_json(candidate)
        if data:
            return data
    return {}


def is_missing(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip() in {"", "not_configured", "__PROJECT_NAME__", "__DOMAIN__", "__DATE__"}
    return value in (None, [], {})


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1", "enabled", "да"}
    return bool(value)


def add_gap(gaps: list[dict[str, Any]], field: str, question: str, category: str, severity: str = "medium") -> None:
    gaps.append({"field": field, "category": category, "severity": severity, "question": question})


def status_for(required: list[str], missing: list[str]) -> str:
    if not required:
        return "not_applicable"
    if not missing:
        return "complete"
    if len(missing) == len(required):
        return "missing"
    return "needs_input"


def category(name: str, required: list[str], gaps: list[dict[str, Any]]) -> dict[str, Any]:
    missing = [gap["field"] for gap in gaps if gap["category"] == name]
    complete = max(0, len(required) - len(missing))
    return {
        "required_count": len(required),
        "missing_count": len(missing),
        "status": status_for(required, missing),
        "complete_ratio": round(complete / len(required), 3) if required else 1.0,
        "missing_fields": missing,
    }


def enabled_names(values: dict[str, Any]) -> list[str]:
    return sorted(str(key) for key, value in values.items() if boolish(value))


def tool_decisions(tool_stack: dict[str, Any], decision: str) -> list[str]:
    decisions = tool_stack.get("decisions", {}) if isinstance(tool_stack.get("decisions"), dict) else {}
    return sorted(
        str(tool_id)
        for tool_id, row in decisions.items()
        if isinstance(row, dict) and row.get("decision") == decision
    )


def spend_services(spend_guard: dict[str, Any], statuses: set[str]) -> list[str]:
    rows = []
    for row in spend_guard.get("service_guards", []):
        if isinstance(row, dict) and row.get("status") in statuses:
            rows.append(str(row.get("service")))
    return sorted(item for item in rows if item)


def gap_priority(severity: str) -> int:
    return {"high": 10, "medium": 30, "low": 60}.get(severity, 50)


def question_meta(field: str) -> dict[str, str]:
    if field.startswith("market.") or field.startswith("project."):
        return {
            "answer_format": "text_or_list",
            "target_file": "seo-cycle.yaml; seo/project-intake.yaml",
            "follow_up_command": "python3 ~/.codex/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write",
        }
    if field.startswith("business."):
        return {
            "answer_format": "text_or_list",
            "target_file": "seo/project-intake.yaml",
            "follow_up_command": "python3 ~/.codex/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write && python3 ~/.codex/skills/seo-cycle/scripts/project-profile.py --write",
        }
    if field.startswith("marketing."):
        return {
            "answer_format": "policy_choice",
            "target_file": "seo/project-intake.yaml; seo/seo-data-collection-map.md",
            "follow_up_command": "python3 ~/.codex/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write && python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write",
        }
    if field.startswith("local."):
        return {
            "answer_format": "urls_or_structured_nap",
            "target_file": "seo-cycle.yaml; seo/project-intake.yaml",
            "follow_up_command": "python3 ~/.codex/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write && python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write",
        }
    if field.startswith("ecommerce."):
        return {
            "answer_format": "policy_or_category_list",
            "target_file": "seo/project-intake.yaml; seo/access-setup-runbook.md",
            "follow_up_command": "python3 ~/.codex/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write && python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write",
        }
    if field.startswith("tools."):
        return {
            "answer_format": "review_decision",
            "target_file": "seo/tool-stack.generated.yaml; seo/setup/tool-stack-report.md",
            "follow_up_command": "python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write",
        }
    if field.startswith("budget."):
        return {
            "answer_format": "number_or_policy",
            "target_file": "seo-cycle.yaml; seo/tool-budget.yaml",
            "follow_up_command": "python3 ~/.codex/skills/seo-cycle/scripts/spend-guard.py --write && python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py report --write",
        }
    if field.startswith("automation."):
        return {
            "answer_format": "run_or_policy",
            "target_file": "seo/automation-policy.yaml; seo/automations/automation-recommendations.md",
            "follow_up_command": "python3 ~/.codex/skills/seo-cycle/scripts/automation-recommender.py --write && python3 ~/.codex/skills/seo-cycle/scripts/setup-control-plane.py --write",
        }
    return {
        "answer_format": "text",
        "target_file": "seo/project-intake.yaml",
        "follow_up_command": "python3 ~/.codex/skills/seo-cycle/scripts/setup-gap-audit.py --write",
    }


def questionnaire_rows(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gap in sorted(gaps, key=lambda row: (gap_priority(str(row.get("severity"))), str(row.get("category")), str(row.get("field")))):
        meta = question_meta(str(gap.get("field")))
        rows.append(
            {
                "priority": gap_priority(str(gap.get("severity"))),
                "field": str(gap.get("field")),
                "category": str(gap.get("category")),
                "severity": str(gap.get("severity")),
                "question": str(gap.get("question")),
                "answer_format": meta["answer_format"],
                "target_file": meta["target_file"],
                "follow_up_command": meta["follow_up_command"],
                "answer": "",
                "notes": "",
            }
        )
    return rows


def build_questionnaire(gaps: list[dict[str, Any]]) -> dict[str, Any]:
    rows = questionnaire_rows(gaps)
    return {
        "markdown": "seo/setup/setup-questionnaire.md",
        "csv": "seo/setup/setup-questionnaire.csv",
        "json": "seo/setup/setup-questionnaire.json",
        "latest_markdown": "seo/setup/latest-setup-questionnaire.md",
        "latest_json": "seo/setup/latest-setup-questionnaire.json",
        "rows": rows,
        "row_count": len(rows),
        "high_priority_count": sum(1 for row in rows if row["severity"] == "high"),
    }


def build_report(cfg_path: pathlib.Path) -> dict[str, Any]:
    project_root = project_root_for(cfg_path)
    cfg = load_yaml(cfg_path)
    intake = load_yaml(policy_path(cfg, project_root, "project_intake", "seo/project-intake.yaml"))
    tool_stack = load_policy_json(cfg, project_root, "tool_stack_report", "seo/setup/tool-stack-report.md")
    spend_guard = load_policy_json(cfg, project_root, "spend_guard_report", "seo/setup/spend-guard.md")
    automation = load_policy_json(cfg, project_root, "automation_recommendations", "seo/automations/automation-recommendations.md")
    launch_plan = load_policy_json(cfg, project_root, "launch_plan_report", "seo/setup/launch-plan.md")
    context_pack = load_policy_json(cfg, project_root, "context_pack_report", "seo/setup/context-pack.md")
    gaps: list[dict[str, Any]] = []

    project = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    business = intake.get("business", {}) if isinstance(intake.get("business"), dict) else {}
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    marketing = intake.get("marketing", {}) if isinstance(intake.get("marketing"), dict) else {}
    setup = intake.get("setup_decisions", {}) if isinstance(intake.get("setup_decisions"), dict) else {}
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    budget = governance.get("budget_policy", {}) if isinstance(governance.get("budget_policy"), dict) else {}
    token = governance.get("token_policy", {}) if isinstance(governance.get("token_policy"), dict) else {}
    subscriptions = governance.get("subscriptions", {}) if isinstance(governance.get("subscriptions"), dict) else {}

    market_required = [
        "project.name",
        "project.domain",
        "market.primary_country",
        "market.primary_region",
        "market.primary_city",
        "market.languages",
        "market.search_engines",
    ]
    if is_missing(project.get("name")):
        add_gap(gaps, "project.name", "Как называется проект/бренд для отчётов и текстов?", "market", "high")
    if is_missing(project.get("domain")):
        add_gap(gaps, "project.domain", "Какой основной домен проекта?", "market", "high")
    if is_missing(markets.get("primary_country")):
        add_gap(gaps, "market.primary_country", "Какая основная страна продвижения ISO-2?", "market", "high")
    if is_missing(markets.get("primary_region")):
        add_gap(gaps, "market.primary_region", "Какой основной регион/область продвижения?", "market", "medium")
    if is_missing(markets.get("primary_city")):
        add_gap(gaps, "market.primary_city", "Какой основной город или оставить 'не local'?", "market", "medium")
    if is_missing(markets.get("languages")):
        add_gap(gaps, "market.languages", "На каких языках публикуем и собираем семантику?", "market", "high")
    engines = enabled_names(markets.get("search_engines", {}) if isinstance(markets.get("search_engines"), dict) else {})
    if not engines:
        add_gap(gaps, "market.search_engines", "Какие поисковики целевые: Яндекс, Google, Bing?", "market", "high")

    business_required = [
        "business.project_type",
        "business.business_model",
        "business.sales_channels",
        "business.priority_products_or_services",
        "business.target_audiences",
        "business.conversion_goals",
    ]
    project_type = business.get("project_type") or cfg.get("project_type")
    if is_missing(project_type):
        add_gap(gaps, "business.project_type", "Какой тип проекта: ecommerce/blog/saas/local/corporate?", "business", "high")
    if is_missing(business.get("business_model")):
        add_gap(gaps, "business.business_model", "Какая бизнес-модель: retail, wholesale, leadgen, subscription?", "business", "medium")
    if is_missing(business.get("sales_channels")):
        add_gap(gaps, "business.sales_channels", "Где продаём: сайт, магазин, склад, маркетплейсы, дилеры?", "business", "medium")
    if is_missing(business.get("priority_products_or_services")):
        add_gap(gaps, "business.priority_products_or_services", "Какие товары/услуги приоритетны в первые 30-90 дней?", "business", "high")
    if is_missing(business.get("target_audiences")):
        add_gap(gaps, "business.target_audiences", "Кто целевые аудитории и сегменты?", "business", "high")
    if is_missing(business.get("conversion_goals")):
        add_gap(gaps, "business.conversion_goals", "Какие основные конверсии: заказ, звонок, лид, заявка, подписка?", "business", "high")

    marketing_required = ["marketing.organic_seo", "marketing.content_marketing", "marketing.paid_ads", "marketing.analytics_tags"]
    paid_ads = marketing.get("paid_ads", {}) if isinstance(marketing.get("paid_ads"), dict) else {}
    analytics = marketing.get("analytics_tags", {}) if isinstance(marketing.get("analytics_tags"), dict) else {}
    if not marketing.get("organic_seo"):
        add_gap(gaps, "marketing.organic_seo", "Нужна ли органика как канал или проект только paid/local?", "marketing", "medium")
    if not marketing.get("content_marketing"):
        add_gap(gaps, "marketing.content_marketing", "Нужен ли контент-маркетинг/статьи/FAQ?", "marketing", "medium")
    if not paid_ads:
        add_gap(gaps, "marketing.paid_ads", "Какая политика по Google Ads/Yandex Direct/Microsoft Ads?", "marketing", "medium")
    if not analytics:
        add_gap(gaps, "marketing.analytics_tags", "Какая политика по GA4/Clarity/Метрике и запретам tracking tags?", "marketing", "medium")

    local_required: list[str] = []
    local_platforms = enabled_names(markets.get("local_platforms", {}) if isinstance(markets.get("local_platforms"), dict) else {})
    business_profile = cfg.get("business_profile", {}) if isinstance(cfg.get("business_profile"), dict) else {}
    if project_type == "local_business" or marketing.get("local_seo"):
        local_required = ["local.platforms", "local.business_profile_urls", "local.nap", "local.competitors"]
        if not local_platforms:
            add_gap(gaps, "local.platforms", "Какие local-платформы вести: Google Business, Яндекс.Бизнес, Bing Places, 2ГИС?", "local", "high")
        urls = [business_profile.get("gbp_url"), business_profile.get("yandex_business_url"), business_profile.get("2gis_url")]
        if not any(not is_missing(url) for url in urls):
            add_gap(gaps, "local.business_profile_urls", "Дай URL карточек Google/Yandex/2GIS/Bing Places или отметь, что их нужно создать.", "local", "high")
        address = business_profile.get("address", {}) if isinstance(business_profile.get("address"), dict) else {}
        if is_missing(address.get("street")) or is_missing(address.get("locality")):
            add_gap(gaps, "local.nap", "Заполни NAP: адрес, телефон, город, часы работы.", "local", "high")
        if is_missing(business_profile.get("competitors")):
            add_gap(gaps, "local.competitors", "Укажи 3-5 локальных конкурентов/карточек для сравнения.", "local", "medium")

    ecommerce_required: list[str] = []
    if project_type == "ecommerce" or marketing.get("ecommerce_feeds"):
        ecommerce_required = ["ecommerce.feed_policy", "ecommerce.priority_products", "ecommerce.merchant_policy"]
        if not marketing.get("ecommerce_feeds"):
            add_gap(gaps, "ecommerce.feed_policy", "Нужны ли Google Merchant/Yandex Merchant/Woo feed diagnostics?", "ecommerce", "medium")
        if is_missing(business.get("priority_products_or_services")):
            add_gap(gaps, "ecommerce.priority_products", "Какие категории/товары дают выручку и требуют первичного SEO?", "ecommerce", "high")
        merchant_tools = {"google_merchant", "yandex_merchant"}
        active_merchants = merchant_tools & set(tool_decisions(tool_stack, "enabled") + tool_decisions(tool_stack, "report_only") + tool_decisions(tool_stack, "approval_required"))
        if not active_merchants:
            add_gap(gaps, "ecommerce.merchant_policy", "Нужны ли merchant/feed инструменты и какие кабинеты подключать?", "ecommerce", "medium")

    tool_required = ["tools.tool_stack", "tools.free_first", "tools.approval_required"]
    if not tool_stack.get("decisions"):
        add_gap(gaps, "tools.tool_stack", "Запусти tool-stack-recommender.py --write и проверь решения по инструментам.", "tools", "high")
    if not tool_decisions(tool_stack, "enabled") and not tool_decisions(tool_stack, "report_only"):
        add_gap(gaps, "tools.free_first", "Нет enabled/report-only инструментов. Уточни free-first стек.", "tools", "high")
    if not tool_decisions(tool_stack, "approval_required"):
        add_gap(gaps, "tools.approval_required", "Проверь, какие paid/API/LLM/ads инструменты должны быть approval-gated.", "tools", "low")

    budget_required = ["budget.token_policy", "budget.monthly_paid_api_usd_cap", "budget.subscriptions", "budget.spend_guard"]
    if token.get("raw_data_in_context") is True or token.get("cache_first") is False:
        add_gap(gaps, "budget.token_policy", "Верни cache-first/raw-on-disk политику или явно зафиксируй исключение.", "budget", "high")
    if float(budget.get("monthly_paid_api_usd_cap") or 0) <= 0 and tool_decisions(tool_stack, "approval_required"):
        add_gap(gaps, "budget.monthly_paid_api_usd_cap", "Укажи месячный paid API/LLM бюджет или оставь paid инструменты только approval-only.", "budget", "medium")
    if not subscriptions:
        add_gap(gaps, "budget.subscriptions", "Заполни подписки и остатки: NeuronWriter, Keys.so, Serpstat, SpyFu, DataForSEO, XMLRiver.", "budget", "medium")
    if not spend_guard.get("service_guards"):
        add_gap(gaps, "budget.spend_guard", "Запусти spend-guard.py --write перед платными/API/LLM действиями.", "budget", "high")

    automation_required = ["automation.recommendations", "automation.context_pack", "automation.launch_plan"]
    planned = (automation.get("policy_overlay") or {}).get("planned_automations", {}) if isinstance(automation.get("policy_overlay"), dict) else {}
    if not planned:
        add_gap(gaps, "automation.recommendations", "Запусти automation-recommender.py --write.", "automation", "medium")
    if not context_pack.get("read_order"):
        add_gap(gaps, "automation.context_pack", "Запусти context-pack.py --task \"...\" --write для текущей задачи.", "automation", "medium")
    if not launch_plan.get("execution_order"):
        add_gap(gaps, "automation.launch_plan", "Запусти launch-plan.py --write для первого экрана проекта.", "automation", "medium")

    categories = {
        "market": category("market", market_required, gaps),
        "business": category("business", business_required, gaps),
        "marketing": category("marketing", marketing_required, gaps),
        "local": category("local", local_required, gaps),
        "ecommerce": category("ecommerce", ecommerce_required, gaps),
        "tools": category("tools", tool_required, gaps),
        "budget": category("budget", budget_required, gaps),
        "automation": category("automation", automation_required, gaps),
    }
    total_required = sum(row["required_count"] for row in categories.values())
    total_missing = sum(row["missing_count"] for row in categories.values())
    score = round(100 * (total_required - total_missing) / total_required) if total_required else 100

    evidence = {
        "project_intake": "seo/project-intake.yaml",
        "tool_stack": "seo/setup/tool-stack-report.md",
        "spend_guard": "seo/setup/spend-guard.md",
        "automation.recommendations": "seo/automations/automation-recommendations.md",
        "launch_plan": "seo/setup/launch-plan.md",
        "context_pack": "seo/setup/context-pack.md",
    }
    missing_fields = [gap["field"] for gap in gaps]
    questionnaire = build_questionnaire(gaps)
    return {
        "version": 1,
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "project_root": str(project_root),
        "project": {
            "name": project.get("name"),
            "domain": project.get("domain"),
            "project_type": project_type,
        },
        "score": score,
        "summary": {
            "required": total_required,
            "missing": total_missing,
            "critical": sum(1 for gap in gaps if gap["severity"] == "high"),
        },
        "categories": categories,
        "missing_fields": missing_fields,
        "gaps": gaps,
        "recommended_questions": [gap["question"] for gap in gaps],
        "questionnaire": questionnaire,
        "signals": {
            "search_engines": engines,
            "local_platforms": local_platforms,
            "tool_enabled": tool_decisions(tool_stack, "enabled"),
            "tool_report_only": tool_decisions(tool_stack, "report_only"),
            "tool_approval_required": tool_decisions(tool_stack, "approval_required"),
            "spend_blocked_or_approval": spend_services(spend_guard, {"blocked", "approval_required"}),
        },
        "evidence": evidence,
        "read_first": [
            "seo/setup/context-pack.md",
            "seo/setup/launch-plan.md",
            "seo/project-intake.yaml",
            "seo/setup/tool-stack-report.md",
            "seo/setup/spend-guard.md",
            "seo/automations/automation-recommendations.md",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    lines = [
        "# seo-cycle setup gap audit",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name')} ({project.get('domain')})",
        f"- Project type: {project.get('project_type')}",
        f"- Score: {report.get('score')}/100",
        f"- Missing: {report.get('summary', {}).get('missing')} / {report.get('summary', {}).get('required')}",
        f"- Critical gaps: {report.get('summary', {}).get('critical')}",
        "",
        "## Categories",
        "| Category | Status | Missing | Required |",
        "| --- | --- | --- | --- |",
    ]
    for name, row in report.get("categories", {}).items():
        lines.append(f"| {name} | {row.get('status')} | {row.get('missing_count')} | {row.get('required_count')} |")

    lines.extend(["", "## Missing Fields"])
    if report.get("gaps"):
        for gap in report["gaps"]:
            lines.append(f"- `{gap['field']}` ({gap['severity']}): {gap['question']}")
    else:
        lines.append("- none")

    lines.extend(["", "## Setup Questionnaire"])
    questionnaire = report.get("questionnaire", {})
    lines.append(f"- Markdown: `{questionnaire.get('markdown')}`")
    lines.append(f"- CSV: `{questionnaire.get('csv')}`")
    lines.append(f"- Rows: {questionnaire.get('row_count', 0)}")

    lines.extend(["", "## Read First"])
    for path in report.get("read_first", []):
        lines.append(f"- `{path}`")

    lines.extend(["", "## Signals"])
    signals = report.get("signals", {})
    lines.append(f"- Search engines: {', '.join(signals.get('search_engines', [])) or '-'}")
    lines.append(f"- Local platforms: {', '.join(signals.get('local_platforms', [])) or '-'}")
    lines.append(f"- Approval tools: {', '.join(signals.get('tool_approval_required', [])) or '-'}")
    lines.append(f"- Spend blocked/approval: {', '.join(signals.get('spend_blocked_or_approval', [])) or '-'}")
    return "\n".join(lines) + "\n"


def render_questionnaire_markdown(report: dict[str, Any]) -> str:
    project = report.get("project", {})
    rows = report.get("questionnaire", {}).get("rows", [])
    lines = [
        "# seo-cycle setup questionnaire",
        "",
        f"- Generated: {report.get('generated')}",
        f"- Project: {project.get('name')} ({project.get('domain')})",
        "- Fill answers in this worksheet or directly in the target files. Do not paste API keys, OAuth tokens, passwords, service-account JSON, or private customer data here.",
        "- After answering a row, run its follow-up command and refresh `setup-gap-audit.py --write`.",
        "",
        "| Priority | Field | Severity | Question | Target file | Follow-up command |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if rows:
        for row in rows:
            lines.append(
                f"| {row['priority']} | `{row['field']}` | {row['severity']} | "
                f"{row['question']} | `{row['target_file']}` | `{row['follow_up_command']}` |"
            )
    else:
        lines.append("| - | - | - | No missing setup fields. | - | - |")
    return "\n".join(lines) + "\n"


def questionnaire_csv(report: dict[str, Any]) -> str:
    buffer = io.StringIO()
    fieldnames = [
        "priority",
        "field",
        "category",
        "severity",
        "question",
        "answer_format",
        "target_file",
        "follow_up_command",
        "answer",
        "notes",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in report.get("questionnaire", {}).get("rows", []):
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return buffer.getvalue()


def write_outputs(project_root: pathlib.Path, report: dict[str, Any]) -> pathlib.Path:
    out_dir = project_root / "seo" / "setup"
    md = render_markdown(report)
    questionnaire_md = render_questionnaire_markdown(report)
    questionnaire = report.get("questionnaire", {})
    write_artifacts(
        text_files={
            out_dir / "setup-gap-audit.md": md,
            out_dir / "latest-setup-gap-audit.md": md,
            out_dir / "setup-questionnaire.md": questionnaire_md,
            out_dir / "latest-setup-questionnaire.md": questionnaire_md,
            out_dir / "setup-questionnaire.csv": questionnaire_csv(report),
        },
        json_files={
            out_dir / "setup-gap-audit.json": report,
            out_dir / "latest-setup-gap-audit.json": report,
            out_dir / "setup-questionnaire.json": questionnaire,
            out_dir / "latest-setup-questionnaire.json": questionnaire,
        },
    )
    return out_dir / "setup-gap-audit.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--write", action="store_true", help="Write setup gap audit and setup questionnaire artifacts.")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    args = parser.parse_args()

    if args.config:
        cfg_path = pathlib.Path(args.config).expanduser().resolve()
    else:
        found = find_config(pathlib.Path.cwd())
        if not found:
            print(f"ERROR: seo-cycle.yaml не найден в {pathlib.Path.cwd()}", file=sys.stderr)
            return 2
        cfg_path = found.resolve()
    if not cfg_path.exists():
        print(f"ERROR: {cfg_path} не найден", file=sys.stderr)
        return 2

    project_root = project_root_for(cfg_path)
    report = build_report(cfg_path)
    if args.write:
        out = write_outputs(project_root, report)
        if args.format == "json":
            print(f"Wrote {out}", file=sys.stderr)
        else:
            print(f"Wrote {out}")
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif not args.write:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
