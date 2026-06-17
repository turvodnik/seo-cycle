#!/usr/bin/env python3
"""Create or refine seo/project-intake.yaml for a concrete project.

The intake file is the human/project contract for countries, regions, search
engines, business type, marketing channels, local/merchant/ads decisions,
tracking policy, guarded tools, and governance defaults.

Use `--defaults --write` after init-project.sh for non-interactive setup.
Use `--interactive --write` when the user wants a detailed project wizard.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
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

FREE_FIRST_TOOLS = [
    "robots_sitemap",
    "search_console",
    "yandex_webmaster",
    "bing_webmaster",
    "pagespeed_crux",
    "suggest_sources",
    "schema_crawl",
]

PAID_OR_QUOTA_TOOLS = [
    "neuronwriter",
    "google_cloud_nlp",
    "keys_so",
    "serpstat",
    "spyfu",
    "dataforseo",
]

AI_VISIBILITY_TOOLS = [
    "google_ai_overview",
    "bing_copilot",
    "perplexity",
    "openai_chatgpt",
    "claude",
    "gemini",
    "deepseek",
]

PROJECT_TYPES = [
    "ecommerce",
    "blog",
    "saas",
    "local_business",
    "corporate",
    "media",
    "portfolio",
]

GOVERNANCE_PROFILES = [
    "lean_quality",
    "balanced_growth",
    "aggressive_growth",
    "custom",
]

AUTOMATION_MODES = [
    "disabled",
    "report_only",
    "approval_only",
    "auto_with_caps",
]

PAID_POLICIES = [
    "disabled",
    "approval_only",
    "enabled",
    "skipped_if_billing_required",
]

TRACKING_POLICIES = [
    "disabled",
    "project_policy_required",
    "approval_required_for_rf",
    "allowed",
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


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def yes_no(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"y", "yes", "true", "1", "да", "д"}
    return bool(value)


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def current_project_name(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    project = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    return str(project.get("name") or intake.get("project") or "not_configured")


def current_domain(cfg: dict[str, Any], intake: dict[str, Any]) -> str:
    project = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    return str(project.get("domain") or intake.get("domain") or "not_configured")


def engine_defaults(country: str, cfg: dict[str, Any]) -> dict[str, bool]:
    country = country.upper()
    if country == "RU":
        return {"yandex": True, "google": True, "bing": False}
    if country in {"US", "GB", "CA", "AU"}:
        return {"yandex": False, "google": True, "bing": True}
    if country in {"DE", "FR", "ES", "IT", "NL", "PL", "PT", "SE", "FI", "NO", "DK"}:
        return {"yandex": False, "google": True, "bing": True}

    configured = {
        str(engine.get("name")): True
        for engine in cfg.get("engines", [])
        if isinstance(engine, dict) and engine.get("name")
    }
    return {
        "yandex": bool(configured.get("yandex")),
        "google": bool(configured.get("google", True)),
        "bing": bool(configured.get("bing", True)),
    }


def default_intake(cfg: dict[str, Any], intake: dict[str, Any]) -> dict[str, Any]:
    locale = cfg.get("locale", {}) if isinstance(cfg.get("locale"), dict) else {}
    governance = cfg.get("governance", {}) if isinstance(cfg.get("governance"), dict) else {}
    automation = governance.get("automation_policy", {}) if isinstance(governance.get("automation_policy"), dict) else {}
    project_type = cfg.get("project_type") or "ecommerce"
    country = str(locale.get("country") or "RU").upper()
    language = str(locale.get("language") or "ru")
    is_rf = country == "RU"
    is_local = project_type == "local_business"
    is_ecommerce = project_type == "ecommerce"

    return {
        "version": 1,
        "updated": dt.date.today().isoformat(),
        "project": current_project_name(cfg, intake),
        "domain": current_domain(cfg, intake),
        "business": {
            "project_type": project_type,
            "business_model": cfg.get("business_model", []),
            "sales_channels": cfg.get("sales_channels", []),
            "priority_products_or_services": [],
            "target_audiences": cfg.get("target_audiences", []),
            "conversion_goals": ["lead", "order"] if is_ecommerce else ["lead"],
            "forbidden_claims_or_topics": [],
        },
        "markets": {
            "primary_country": country,
            "primary_region": locale.get("region") or "not_configured",
            "primary_city": locale.get("city") or "not_configured",
            "languages": [language],
            "search_engines": engine_defaults(country, cfg),
            "local_platforms": {
                "yandex_business": is_rf and is_local,
                "google_business_profile": is_local,
                "bing_places": is_local and country != "RU",
                "two_gis": is_rf and is_local,
            },
        },
        "marketing": {
            "organic_seo": True,
            "content_marketing": True,
            "local_seo": is_local,
            "ecommerce_feeds": is_ecommerce,
            "email_or_messenger": False,
            "video_youtube": False,
            "paid_ads": {
                "google_ads": "approval_only",
                "yandex_direct": "approval_only" if is_rf else "disabled",
                "microsoft_ads": "skipped_if_billing_required",
            },
            "analytics_tags": {
                "google_analytics": "approval_required_for_rf" if is_rf else "project_policy_required",
                "microsoft_clarity": "approval_required_for_rf" if is_rf else "project_policy_required",
                "yandex_metrika": "project_policy_required" if is_rf else "disabled",
            },
        },
        "tools": {
            "free_first": FREE_FIRST_TOOLS,
            "paid_or_quota_guarded": PAID_OR_QUOTA_TOOLS,
            "ai_visibility": AI_VISIBILITY_TOOLS,
        },
        "setup_decisions": {
            "default_governance_profile": governance.get("profile", "lean_quality"),
            "default_automation_mode": automation.get("default_mode", "approval_only"),
            "allow_paid_spend_without_explicit_approval": False,
            "allow_foreign_tracking_tags_for_rf_project": False,
            "require_cache_for_expensive_sources": True,
            "require_distillate_before_llm_synthesis": True,
        },
    }


def is_empty_or_placeholder(value: Any) -> bool:
    if isinstance(value, str) and value.startswith("__") and value.endswith("__"):
        return True
    return value in (None, "", [], {}) or value == "not_configured"


def deep_fill(existing: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    for key, default_value in defaults.items():
        current = result.get(key)
        if isinstance(default_value, dict):
            result[key] = deep_fill(current if isinstance(current, dict) else {}, default_value)
            continue
        if is_empty_or_placeholder(current):
            result[key] = copy.deepcopy(default_value)
    return result


def apply_defaults(existing: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    result = deep_fill(existing, defaults)

    # Fresh templates contain RU-biased engine defaults. Recompute for the
    # configured country so non-RU projects do not accidentally keep Yandex first.
    markets = result.setdefault("markets", {})
    country = str(markets.get("primary_country") or defaults["markets"]["primary_country"]).upper()
    engines = markets.get("search_engines", {})
    if engines in ({}, {"yandex": True, "google": True, "bing": False}):
        markets["search_engines"] = copy.deepcopy(defaults["markets"]["search_engines"])

    local_platforms = markets.get("local_platforms", {})
    if local_platforms in ({}, {"yandex_business": False, "google_business_profile": False, "bing_places": False, "two_gis": False}):
        markets["local_platforms"] = copy.deepcopy(defaults["markets"]["local_platforms"])

    marketing = result.setdefault("marketing", {})
    project_type = result.get("business", {}).get("project_type")
    if project_type == "ecommerce":
        marketing["ecommerce_feeds"] = True
    if project_type == "local_business":
        marketing["local_seo"] = True

    if country != "RU":
        analytics = marketing.setdefault("analytics_tags", {})
        if analytics.get("google_analytics") == "approval_required_for_rf":
            analytics["google_analytics"] = "project_policy_required"
        if analytics.get("microsoft_clarity") == "approval_required_for_rf":
            analytics["microsoft_clarity"] = "project_policy_required"
        if analytics.get("yandex_metrika") == "project_policy_required":
            analytics["yandex_metrika"] = "disabled"

    result["updated"] = dt.date.today().isoformat()
    return result


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    return raw if raw else str(default or "")


def ask_list(prompt: str, default: list[str]) -> list[str]:
    raw = ask(prompt, ", ".join(default))
    return string_list(raw)


def ask_bool(prompt: str, default: bool) -> bool:
    raw = ask(prompt, "Y" if default else "n").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes", "true", "1", "да", "д"}


def ask_choice(prompt: str, choices: list[str], default: str) -> str:
    choice_text = "/".join(choices)
    while True:
        value = ask(f"{prompt} ({choice_text})", default)
        if value in choices:
            return value
        print(f"  Допустимо: {choice_text}")


def ask_engines(current: dict[str, bool]) -> dict[str, bool]:
    enabled = [name for name, is_enabled in current.items() if is_enabled]
    selected = set(ask_list("Поисковики через запятую", enabled))
    return {name: name in selected for name in ("yandex", "google", "bing")}


def interactive_refine(intake: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(intake)
    business = result.setdefault("business", {})
    markets = result.setdefault("markets", {})
    marketing = result.setdefault("marketing", {})
    tools = result.setdefault("tools", {})
    setup = result.setdefault("setup_decisions", {})

    print("\nДетальный intake wizard. Enter оставляет значение по умолчанию.")
    print("Секреты, токены и пароли здесь не вводятся.\n")

    business["project_type"] = ask_choice("Тип проекта", PROJECT_TYPES, business.get("project_type", "ecommerce"))
    business["business_model"] = ask_list("Business model tags", string_list(business.get("business_model")))
    business["sales_channels"] = ask_list("Sales channels", string_list(business.get("sales_channels")))
    business["priority_products_or_services"] = ask_list(
        "Приоритетные товары/услуги", string_list(business.get("priority_products_or_services"))
    )
    business["target_audiences"] = ask_list("Целевые аудитории", string_list(business.get("target_audiences")))
    business["conversion_goals"] = ask_list("Conversion goals", string_list(business.get("conversion_goals")))
    business["forbidden_claims_or_topics"] = ask_list(
        "Запрещённые обещания/темы", string_list(business.get("forbidden_claims_or_topics"))
    )

    markets["primary_country"] = ask("Основная страна ISO-2", markets.get("primary_country", "RU")).upper()
    markets["primary_region"] = ask("Основной регион", markets.get("primary_region", "not_configured"))
    markets["primary_city"] = ask("Основной город", markets.get("primary_city", "not_configured"))
    markets["languages"] = ask_list("Языки контента ISO-639-1", string_list(markets.get("languages")))
    markets["search_engines"] = ask_engines(markets.get("search_engines", {}))

    local = markets.setdefault("local_platforms", {})
    local["yandex_business"] = ask_bool("Нужен Яндекс.Бизнес/Карты", yes_no(local.get("yandex_business")))
    local["google_business_profile"] = ask_bool("Нужен Google Business Profile", yes_no(local.get("google_business_profile")))
    local["bing_places"] = ask_bool("Нужен Bing Places", yes_no(local.get("bing_places")))
    local["two_gis"] = ask_bool("Нужен 2ГИС", yes_no(local.get("two_gis")))

    marketing["organic_seo"] = ask_bool("Organic SEO включать", yes_no(marketing.get("organic_seo", True)))
    marketing["content_marketing"] = ask_bool("Content marketing включать", yes_no(marketing.get("content_marketing", True)))
    marketing["local_seo"] = ask_bool("Local SEO включать", yes_no(marketing.get("local_seo")))
    marketing["ecommerce_feeds"] = ask_bool("Merchant/product feeds включать", yes_no(marketing.get("ecommerce_feeds")))
    marketing["email_or_messenger"] = ask_bool("Email/мессенджер как канал", yes_no(marketing.get("email_or_messenger")))
    marketing["video_youtube"] = ask_bool("YouTube/video SEO включать", yes_no(marketing.get("video_youtube")))

    paid_ads = marketing.setdefault("paid_ads", {})
    for name in ("google_ads", "yandex_direct", "microsoft_ads"):
        paid_ads[name] = ask_choice(f"Policy для {name}", PAID_POLICIES, paid_ads.get(name, "approval_only"))

    tracking = marketing.setdefault("analytics_tags", {})
    for name in ("google_analytics", "microsoft_clarity", "yandex_metrika"):
        tracking[name] = ask_choice(f"Tracking policy для {name}", TRACKING_POLICIES, tracking.get(name, "project_policy_required"))

    tools["free_first"] = ask_list("Free-first tools", string_list(tools.get("free_first")) or FREE_FIRST_TOOLS)
    tools["paid_or_quota_guarded"] = ask_list(
        "Paid/quota tools под guard", string_list(tools.get("paid_or_quota_guarded")) or PAID_OR_QUOTA_TOOLS
    )
    tools["ai_visibility"] = ask_list("AI visibility platforms", string_list(tools.get("ai_visibility")) or AI_VISIBILITY_TOOLS)

    setup["default_governance_profile"] = ask_choice(
        "Governance profile", GOVERNANCE_PROFILES, setup.get("default_governance_profile", "lean_quality")
    )
    setup["default_automation_mode"] = ask_choice(
        "Automation mode", AUTOMATION_MODES, setup.get("default_automation_mode", "approval_only")
    )
    setup["allow_paid_spend_without_explicit_approval"] = ask_bool(
        "Разрешить платные расходы без отдельного approval", yes_no(setup.get("allow_paid_spend_without_explicit_approval"))
    )
    setup["allow_foreign_tracking_tags_for_rf_project"] = ask_bool(
        "Для РФ разрешить зарубежные tracking tags без отдельного approval",
        yes_no(setup.get("allow_foreign_tracking_tags_for_rf_project")),
    )
    setup["require_cache_for_expensive_sources"] = ask_bool(
        "Требовать cache-first для дорогих источников", yes_no(setup.get("require_cache_for_expensive_sources", True))
    )
    setup["require_distillate_before_llm_synthesis"] = ask_bool(
        "Требовать distillate перед LLM synthesis",
        yes_no(setup.get("require_distillate_before_llm_synthesis", True)),
    )

    result["updated"] = dt.date.today().isoformat()
    return result


def render_report(intake_path: pathlib.Path, intake: dict[str, Any]) -> str:
    business = intake.get("business", {})
    markets = intake.get("markets", {})
    marketing = intake.get("marketing", {})
    setup = intake.get("setup_decisions", {})
    enabled_engines = [
        name for name, enabled in (markets.get("search_engines", {}) or {}).items() if enabled
    ]
    local_platforms = [
        name for name, enabled in (markets.get("local_platforms", {}) or {}).items() if enabled
    ]
    lines = [
        "# seo-cycle project intake report",
        "",
        f"- Intake: {intake_path}",
        f"- Project: {intake.get('project')} ({intake.get('domain')})",
        f"- Type: {business.get('project_type')}",
        f"- Country/region/city: {markets.get('primary_country')} / {markets.get('primary_region')} / {markets.get('primary_city')}",
        f"- Languages: {', '.join(markets.get('languages', [])) or 'not_configured'}",
        f"- Search engines: {', '.join(enabled_engines) or 'none'}",
        f"- Local platforms: {', '.join(local_platforms) or 'none'}",
        f"- Marketing: organic={marketing.get('organic_seo')}, content={marketing.get('content_marketing')}, local={marketing.get('local_seo')}, ecommerce_feeds={marketing.get('ecommerce_feeds')}, video={marketing.get('video_youtube')}",
        f"- Governance: {setup.get('default_governance_profile')} / automation={setup.get('default_automation_mode')}",
        f"- Cache-first: {setup.get('require_cache_for_expensive_sources')}",
        f"- Distillate before synthesis: {setup.get('require_distillate_before_llm_synthesis')}",
        "",
        "## Next Steps",
        "1. Review `seo/project-intake.yaml`.",
        "2. Run `project-profile.py --write` to generate profile overlay/report.",
        "3. Run `project-profile.py --apply` only after reviewing generated files.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(project_root: pathlib.Path, intake_path: pathlib.Path, intake: dict[str, Any], report: str) -> None:
    write_artifacts(
        text_files={
            intake_path: dump_yaml(intake),
            project_root / "seo" / "project-intake-report.md": report,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--intake", default="seo/project-intake.yaml", help="Path to project-intake.yaml")
    parser.add_argument("--defaults", action="store_true", help="Fill missing/template intake values from seo-cycle.yaml.")
    parser.add_argument("--interactive", action="store_true", help="Ask detailed questions and write selected answers.")
    parser.add_argument("--write", action="store_true", help="Write intake/report files.")
    parser.add_argument("--format", choices=("md", "json", "yaml"), default="md")
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
    cfg = load_yaml(cfg_path)
    intake_path = rel_path(project_root, args.intake)
    intake = load_yaml(intake_path)
    defaults = default_intake(cfg, intake)
    next_intake = apply_defaults(intake, defaults)

    if args.interactive:
        next_intake = interactive_refine(next_intake)
    elif not args.defaults and sys.stdin.isatty():
        print("INFO: интерактивный режим не запрошен. Использую --defaults. Для опроса запусти --interactive --write.", file=sys.stderr)

    report = render_report(intake_path, next_intake)
    if args.write:
        write_outputs(project_root, intake_path, next_intake, report)

    if args.format == "json":
        print(json.dumps(next_intake, ensure_ascii=False, indent=2))
    elif args.format == "yaml":
        print(dump_yaml(next_intake), end="")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
