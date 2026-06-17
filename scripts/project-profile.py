#!/usr/bin/env python3
"""Build and optionally apply a project-specific seo-cycle profile.

Reads `seo/project-intake.yaml` and current `seo-cycle.yaml`, then creates a
small overlay/report that answers: which countries, engines, regions, business
type, marketing channels, ads, local/merchant tools, and paid/quota tools should
be active for this project.

Default mode is non-destructive: write `seo/project-profile.generated.yaml` and
`seo/project-profile-report.md`. Use `--apply` to update `seo-cycle.yaml`; a
timestamped backup is created first.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import pathlib
import sys
from typing import Any

from seo_cycle_core.config import find_config, load_yaml, project_root_for, rel_path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML не установлен. `pip3 install pyyaml`", file=sys.stderr)
    sys.exit(2)


COUNTRY_TO_PROFILE = {
    "RU": "ru",
    "US": "us",
    "GB": "eu",
    "DE": "eu",
    "FR": "eu",
    "ES": "eu",
    "IT": "eu",
    "NL": "eu",
    "PL": "eu",
    "PT": "eu",
    "SE": "eu",
    "FI": "eu",
    "NO": "eu",
    "DK": "eu",
}

ENGINE_DEFAULTS = {
    "yandex": [
        "yandex_wordstat",
        "yandex_wordstat_deep",
        "yandex_suggest",
        "yandex_serp_blocks",
        "yandex_images_suggest",
        "yandex_q",
    ],
    "google": [
        "google_search_console",
        "google_trends",
        "google_suggest",
    ],
    "bing": [
        "bing_webmaster",
        "indexnow",
    ],
}


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "yes", "y", "1", "enabled"}
    return bool(value)


def country_from_intake(intake: dict[str, Any], cfg: dict[str, Any]) -> str:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    country = markets.get("primary_country")
    if not country or country == "not_configured":
        country = (cfg.get("locale", {}) or {}).get("country")
    return str(country or "RU").upper()


def region_profile_for(country: str) -> str:
    return COUNTRY_TO_PROFILE.get(country.upper(), "global")


def configured_project_type(business: dict[str, Any], cfg: dict[str, Any]) -> str | None:
    project_type = business.get("project_type")
    if project_type and project_type != "not_configured":
        return str(project_type)
    return cfg.get("project_type")


def engines_from_intake(intake: dict[str, Any], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    configured = markets.get("search_engines", {}) if isinstance(markets.get("search_engines"), dict) else {}
    if not configured:
        return cfg.get("engines", [])
    priorities = {"yandex": 1, "google": 2, "bing": 3, "baidu": 4}
    engines = [
        {"name": name, "priority": priorities.get(name, 10)}
        for name, enabled in configured.items()
        if boolish(enabled)
    ]
    return sorted(engines, key=lambda item: item["priority"])


def set_source(sources: dict[str, Any], name: str, enabled: bool) -> None:
    current = sources.get(name)
    if isinstance(current, dict):
        current["enabled"] = enabled
    else:
        sources[name] = {"enabled": enabled}


def source_overrides(intake: dict[str, Any], cfg: dict[str, Any]) -> dict[str, bool]:
    engines = {engine["name"] for engine in engines_from_intake(intake, cfg)}
    business = intake.get("business", {}) if isinstance(intake.get("business"), dict) else {}
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    marketing = intake.get("marketing", {}) if isinstance(intake.get("marketing"), dict) else {}
    local_platforms = markets.get("local_platforms", {}) if isinstance(markets.get("local_platforms"), dict) else {}
    project_type = configured_project_type(business, cfg)
    local_seo = boolish(marketing.get("local_seo")) or project_type == "local_business"
    ecommerce_feeds = boolish(marketing.get("ecommerce_feeds")) or project_type == "ecommerce"

    overrides: dict[str, bool] = {}
    for engine, names in ENGINE_DEFAULTS.items():
        for name in names:
            overrides[name] = engine in engines

    overrides["yandex_business_maps"] = "yandex" in engines and local_seo and boolish(local_platforms.get("yandex_business", True))
    overrides["google_business_profile"] = "google" in engines and local_seo and boolish(local_platforms.get("google_business_profile", True))
    overrides["bing_places"] = "bing" in engines and local_seo and boolish(local_platforms.get("bing_places", True))
    overrides["yandex_merchant"] = "yandex" in engines and ecommerce_feeds
    overrides["google_merchant"] = "google" in engines and ecommerce_feeds

    paid_ads = marketing.get("paid_ads", {}) if isinstance(marketing.get("paid_ads"), dict) else {}
    # Ads are represented as policy decisions, not enabled spend, unless explicitly "enabled".
    overrides["google_ads"] = paid_ads.get("google_ads") == "enabled"
    overrides["yandex_direct"] = paid_ads.get("yandex_direct") == "enabled"
    overrides["microsoft_ads"] = paid_ads.get("microsoft_ads") == "enabled"

    tools = intake.get("tools", {}) if isinstance(intake.get("tools"), dict) else {}
    guarded = set(tools.get("paid_or_quota_guarded", []) or [])
    for raw_name in ("neuronwriter", "google_cloud_nlp", "keyso", "keys_so", "serpstat", "spyfu", "dataforseo"):
        if raw_name in guarded:
            source_name = "keyso" if raw_name == "keys_so" else raw_name
            overrides.setdefault(source_name, False)

    return overrides


def recommended_profile(cfg: dict[str, Any], intake: dict[str, Any]) -> dict[str, Any]:
    business = intake.get("business", {}) if isinstance(intake.get("business"), dict) else {}
    markets = intake.get("markets", {}) if isinstance(intake.get("markets"), dict) else {}
    marketing = intake.get("marketing", {}) if isinstance(intake.get("marketing"), dict) else {}
    setup = intake.get("setup_decisions", {}) if isinstance(intake.get("setup_decisions"), dict) else {}
    country = country_from_intake(intake, cfg)
    engines = engines_from_intake(intake, cfg)
    source_map = source_overrides(intake, cfg)
    project_type = configured_project_type(business, cfg)
    effective_local_seo = boolish(marketing.get("local_seo", False)) or project_type == "local_business"
    effective_ecommerce_feeds = boolish(marketing.get("ecommerce_feeds", False)) or project_type == "ecommerce"
    primary_region = markets.get("primary_region")
    primary_city = markets.get("primary_city")
    languages = markets.get("languages") or ([markets.get("language")] if markets.get("language") else [])
    if not languages and (cfg.get("locale", {}) or {}).get("language"):
        languages = [(cfg.get("locale", {}) or {}).get("language")]

    return {
        "region_profile": region_profile_for(country),
        "locale": {
            "country": country,
            "region": primary_region if primary_region and primary_region != "not_configured" else (cfg.get("locale", {}) or {}).get("region"),
            "city": primary_city if primary_city and primary_city != "not_configured" else (cfg.get("locale", {}) or {}).get("city"),
            "languages": [item for item in languages if item],
        },
        "engines": engines,
        "project_type": project_type,
        "business_model": business.get("business_model") or cfg.get("business_model", []),
        "sales_channels": business.get("sales_channels") or cfg.get("sales_channels", []),
        "target_audiences": business.get("target_audiences") or cfg.get("target_audiences", []),
        "sources": source_map,
        "marketing": {
            "enabled": any(boolish(marketing.get(key)) for key in ("organic_seo", "content_marketing", "local_seo", "ecommerce_feeds", "email_or_messenger", "video_youtube")),
            "rf_adaptation": country == "RU",
            "organic_seo": boolish(marketing.get("organic_seo", True)),
            "content_marketing": boolish(marketing.get("content_marketing", True)),
            "local_seo": effective_local_seo,
            "ecommerce_feeds": effective_ecommerce_feeds,
            "video_youtube": boolish(marketing.get("video_youtube", False)),
            "paid_ads": marketing.get("paid_ads", {}),
            "analytics_tags": marketing.get("analytics_tags", {}),
        },
        "governance": {
            "profile": setup.get("default_governance_profile", (cfg.get("governance", {}) or {}).get("profile", "lean_quality")),
            "automation_mode": setup.get("default_automation_mode", ((cfg.get("governance", {}) or {}).get("automation_policy", {}) or {}).get("default_mode", "approval_only")),
            "allow_paid_spend_without_explicit_approval": boolish(setup.get("allow_paid_spend_without_explicit_approval", False)),
            "allow_foreign_tracking_tags_for_rf_project": boolish(setup.get("allow_foreign_tracking_tags_for_rf_project", False)),
            "require_cache_for_expensive_sources": boolish(setup.get("require_cache_for_expensive_sources", True)),
            "require_distillate_before_llm_synthesis": boolish(setup.get("require_distillate_before_llm_synthesis", True)),
        },
    }


def apply_profile(cfg: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    next_cfg = copy.deepcopy(cfg)
    next_cfg["region_profile"] = profile["region_profile"]
    if profile.get("engines"):
        next_cfg["engines"] = profile["engines"]
    next_cfg["project_type"] = profile.get("project_type") or next_cfg.get("project_type")
    for key in ("business_model", "sales_channels", "target_audiences"):
        if profile.get(key):
            next_cfg[key] = profile[key]

    locale = next_cfg.setdefault("locale", {})
    for key in ("country", "region", "city"):
        if profile.get("locale", {}).get(key):
            locale[key] = profile["locale"][key]

    sources = next_cfg.setdefault("sources", {})
    for name, enabled in profile.get("sources", {}).items():
        set_source(sources, name, enabled)

    marketing = next_cfg.setdefault("marketing", {})
    marketing["enabled"] = profile["marketing"]["enabled"]
    marketing["rf_adaptation"] = profile["marketing"]["rf_adaptation"]
    marketing["project_profile"] = {
        "organic_seo": profile["marketing"]["organic_seo"],
        "content_marketing": profile["marketing"]["content_marketing"],
        "local_seo": profile["marketing"]["local_seo"],
        "ecommerce_feeds": profile["marketing"]["ecommerce_feeds"],
        "video_youtube": profile["marketing"]["video_youtube"],
        "paid_ads": profile["marketing"]["paid_ads"],
        "analytics_tags": profile["marketing"]["analytics_tags"],
    }

    governance = next_cfg.setdefault("governance", {})
    governance["profile"] = profile["governance"]["profile"]
    automation = governance.setdefault("automation_policy", {})
    automation["default_mode"] = profile["governance"]["automation_mode"]
    token_policy = governance.setdefault("token_policy", {})
    token_policy["cache_first"] = profile["governance"]["require_cache_for_expensive_sources"]
    token_policy["require_distillate_before_synthesis"] = profile["governance"]["require_distillate_before_llm_synthesis"]
    budget = governance.setdefault("budget_policy", {})
    budget["paid_tools_default"] = "enabled_with_caps" if profile["governance"]["allow_paid_spend_without_explicit_approval"] else "approval_only"
    return next_cfg


def render_report(cfg: dict[str, Any], intake: dict[str, Any], profile: dict[str, Any]) -> str:
    project = cfg.get("project", {}) if isinstance(cfg.get("project"), dict) else {}
    enabled_sources = sorted(name for name, enabled in profile["sources"].items() if enabled)
    disabled_sources = sorted(name for name, enabled in profile["sources"].items() if not enabled)
    lines = [
        "# seo-cycle project profile report",
        "",
        f"- Project: {project.get('name', intake.get('project', '?'))} ({project.get('domain', intake.get('domain', '?'))})",
        f"- Region profile: {profile['region_profile']}",
        f"- Project type: {profile.get('project_type')}",
        f"- Engines: {', '.join(engine['name'] for engine in profile.get('engines', [])) or 'none'}",
        f"- Governance: {profile['governance']['profile']} / automation={profile['governance']['automation_mode']}",
        "",
        "## Enabled Source Overrides",
        ", ".join(enabled_sources) if enabled_sources else "No explicit source enables.",
        "",
        "## Disabled / Approval-Only Source Overrides",
        ", ".join(disabled_sources) if disabled_sources else "No explicit source disables.",
        "",
        "## Marketing Decisions",
    ]
    for key, value in profile["marketing"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Token And Budget Impact",
            f"- cache_first: {profile['governance']['require_cache_for_expensive_sources']}",
            f"- require_distillate_before_synthesis: {profile['governance']['require_distillate_before_llm_synthesis']}",
            f"- paid spend without explicit approval: {profile['governance']['allow_paid_spend_without_explicit_approval']}",
            f"- foreign tracking tags for RF project: {profile['governance']['allow_foreign_tracking_tags_for_rf_project']}",
            "",
            "## Next Steps",
            "1. Review `seo/project-profile.generated.yaml`.",
            "2. If it is correct, run `project-profile.py --apply` to update `seo-cycle.yaml` with a timestamped backup.",
            "3. Run `validate-config.py`, `governance-report.py`, and `automation-plan.py --write --include-disabled`.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_artifacts(project_root: pathlib.Path, profile: dict[str, Any], report: str) -> None:
    seo_dir = project_root / "seo"
    seo_dir.mkdir(parents=True, exist_ok=True)
    (seo_dir / "project-profile.generated.yaml").write_text(dump_yaml(profile), encoding="utf-8")
    (seo_dir / "project-profile-report.md").write_text(report, encoding="utf-8")


def write_applied_config(cfg_path: pathlib.Path, cfg: dict[str, Any]) -> pathlib.Path:
    backup = cfg_path.with_suffix(cfg_path.suffix + f".bak-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}")
    backup.write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    cfg_path.write_text(dump_yaml(cfg), encoding="utf-8")
    return backup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", nargs="?", help="Path to seo-cycle.yaml")
    parser.add_argument("--intake", default="seo/project-intake.yaml", help="Path to project-intake.yaml")
    parser.add_argument("--write", action="store_true", help="Write generated overlay/report artifacts.")
    parser.add_argument("--apply", action="store_true", help="Apply recommendations to seo-cycle.yaml with backup.")
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
    if not intake:
        print(f"ERROR: project intake не найден или пуст: {intake_path}", file=sys.stderr)
        return 2

    profile = recommended_profile(cfg, intake)
    report = render_report(cfg, intake, profile)
    if args.write or args.apply:
        write_artifacts(project_root, profile, report)
    if args.apply:
        backup = write_applied_config(cfg_path, apply_profile(cfg, profile))
        print(f"Applied profile to {cfg_path}; backup: {backup}")
        return 0

    if args.format == "json":
        print(json.dumps(profile, ensure_ascii=False, indent=2))
    elif args.format == "yaml":
        print(dump_yaml(profile), end="")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
