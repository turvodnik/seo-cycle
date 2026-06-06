#!/usr/bin/env python3
"""
validate-config.py — валидатор seo-cycle.yaml.

Проверяет:
- Обязательные поля заполнены
- ISO-коды валидны (language, country)
- Для каждого `enabled: true` источника — есть ли необходимые env-vars в .env проекта
- delegate-цели существуют (предупреждение если нет)
- Пути в artifacts.* — существуют или создаются автоматом

Выдаёт:
- ✓ если всё ок
- список предупреждений (warnings) — не блокеры
- список ошибок (errors) — блокеры
- чек-лист «что подключить»

Использование:
    python3 ~/.codex/skills/seo-cycle/scripts/validate-config.py [path-to-config]

Если путь не указан — ищет в 4 стандартных локациях.
"""

from __future__ import annotations
import argparse, os, pathlib, sys

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
        p = start_dir / rel
        if p.exists():
            return p
    return None


def load_env(project_root: pathlib.Path) -> dict[str, str]:
    env = dict(os.environ)
    envf = project_root / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


# Простейшие справочники для валидации
ISO_LANGUAGES = {"ru","en","de","fr","es","pt","it","tr","ar","zh","ja","ko","uk","pl","nl","sv","fi","no","da","cs"}
ISO_COUNTRIES = {"RU","US","GB","DE","FR","ES","PT","IT","TR","UA","PL","NL","SE","FI","NO","DK","CZ","JP","KR","CN","IN","BR","AU","CA"}


def check_required(cfg: dict, errors: list, warnings: list):
    for key in ("project", "locale", "engines", "project_type"):
        if key not in cfg:
            errors.append(f"Missing required top-level key: {key}")
    if "project" in cfg:
        for k in ("name", "domain"):
            if not cfg["project"].get(k):
                errors.append(f"project.{k} is required")
    if "locale" in cfg:
        lang = cfg["locale"].get("language")
        cty = cfg["locale"].get("country")
        if lang and lang not in ISO_LANGUAGES:
            warnings.append(f"locale.language={lang!r} — не в стандартном списке ISO 639-1 (возможно опечатка)")
        if cty and cty not in ISO_COUNTRIES:
            warnings.append(f"locale.country={cty!r} — не в стандартном списке ISO 3166-1 (возможно опечатка)")
    if "engines" in cfg and not isinstance(cfg["engines"], list):
        errors.append("engines must be a list of {name, priority}")


def load_region_profile(profile_id: str) -> dict | None:
    prof_path = (pathlib.Path(__file__).resolve().parent.parent
                 / "config" / "region-profiles" / f"{profile_id}.yaml")
    if not prof_path.exists():
        return None
    with prof_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def check_sources(cfg: dict, env: dict, checklist: list, warnings: list):
    sources = cfg.get("sources", {})
    if not sources:
        warnings.append("Секция sources пуста — Phase 2 не сможет собрать данные")
        return

    profile_id = cfg.get("region_profile")

    # === Профиль-режим: активность источника берётся из region-profile ===
    if profile_id:
        profile = load_region_profile(profile_id)
        if profile is None:
            warnings.append(f"region_profile={profile_id!r} — файл профиля не найден в config/region-profiles/")
            return
        active = (set(profile.get("sources_enable", [])) | set(profile.get("sources_proxy", []))) - set(profile.get("sources_disable", []))
        # Локальные override: enabled:false убирает, enabled:true добавляет
        for name, scfg in sources.items():
            if isinstance(scfg, dict) and "enabled" in scfg:
                if scfg["enabled"]:
                    active.add(name)
                else:
                    active.discard(name)
        if not active:
            warnings.append(f"Профиль {profile_id} + override не дали ни одного активного источника")
        for name in sorted(active):
            merged = sources.get(name, {}) if isinstance(sources.get(name), dict) else {}
            check_one_source(name, merged, env, checklist, warnings)
        return

    # === Legacy-режим: активность по локальному enabled ===
    enabled_count = 0
    for src_name, src_cfg in sources.items():
        if not isinstance(src_cfg, dict):
            continue

        # Вложенные источники (llm_cli.antigravity, llm_cli.codex)
        if "enabled" not in src_cfg:
            for sub_name, sub_cfg in src_cfg.items():
                if isinstance(sub_cfg, dict) and sub_cfg.get("enabled"):
                    enabled_count += 1
                    check_one_source(f"{src_name}.{sub_name}", sub_cfg, env, checklist, warnings)
            continue

        if src_cfg.get("enabled"):
            enabled_count += 1
            check_one_source(src_name, src_cfg, env, checklist, warnings)

    if enabled_count == 0:
        warnings.append("Ни один источник в sources не enabled — Phase 2 будет пустой")


def check_one_source(name: str, cfg: dict, env: dict, checklist: list, warnings: list):
    # API key check
    api_env = cfg.get("api_key_env")
    if api_env and not env.get(api_env):
        checklist.append(f"Добавить в .env: {api_env}= (для источника {name})")

    for cfg_key, env_name in cfg.items():
        if cfg_key == "api_key_env":
            continue
        if cfg_key.endswith("_env") and isinstance(env_name, str) and env_name and not env.get(env_name):
            checklist.append(f"Добавить в .env: {env_name}= (для источника {name}.{cfg_key})")

    # Script existence check
    for key in ("script", "helper_script", "generator_script", "optimize_script"):
        path = cfg.get(key)
        if path:
            expanded = pathlib.Path(os.path.expanduser(path))
            if not expanded.exists():
                warnings.append(f"{name}.{key} → {path} не существует (либо создай, либо отключи источник)")

    # CLI existence check
    cmd = cfg.get("cmd")
    if cmd:
        from shutil import which
        if not which(cmd):
            checklist.append(f"Установить CLI `{cmd}` (для источника {name})")

    # delegate_to skill/agent check (warning only)
    delegate = cfg.get("delegate_to")
    if delegate:
        # Простая эвристика: ищем в ~/.claude/agents/ и ~/.claude/skills/
        home = pathlib.Path.home() / ".claude"
        possible = [
            home / "agents" / f"{delegate}.md",
            home / "skills" / delegate / "SKILL.md",
            home / "plugins" / delegate.split(":")[0] / "skills" / delegate.split(":")[-1] / "SKILL.md" if ":" in delegate else None,
        ]
        if not any(p and p.exists() for p in possible):
            warnings.append(f"{name}.delegate_to={delegate} — не найден в ~/.claude/agents/ или ~/.claude/skills/")


def check_publishing(cfg: dict, env: dict, checklist: list, warnings: list):
    pub = cfg.get("publishing", {})
    if not pub.get("enabled"):
        return
    env_vars = pub.get("env_vars", {})
    for label, env_name in env_vars.items():
        if env_name and not env.get(env_name):
            checklist.append(f"Добавить в .env: {env_name}= (publishing.{label})")


def check_images(cfg: dict, env: dict, project_root: pathlib.Path, checklist: list, warnings: list):
    images = cfg.get("images", {})
    if not isinstance(images, dict) or not images:
        return

    for key in ("tool_script", "generator_script", "optimize_script"):
        path = images.get(key)
        if not path:
            continue
        if key == "generator_script" and images.get("generator") in ("manual", "none"):
            continue
        expanded = pathlib.Path(os.path.expanduser(path))
        if not expanded.is_absolute():
            expanded = project_root / expanded
        if not expanded.exists():
            warnings.append(f"images.{key} → {path} не существует (создай скрипт или поправь путь)")

    ratios = images.get("aspect_ratios", {})
    if isinstance(ratios, dict):
        for key in ("featured", "article_inline"):
            if key not in ratios:
                warnings.append(f"images.aspect_ratios.{key} не задан — wp-photo-image будет использовать fallback")

    upload = images.get("upload", {})
    cms = (cfg.get("publishing", {}) or {}).get("cms") or cfg.get("cms")
    if isinstance(upload, dict) and upload.get("method") == "ssh_wp_cli" and cms == "wordpress":
        remote_root_env = upload.get("remote_root_env", "WP_REMOTE_ROOT")
        env_file = upload.get("env_file", ".env")
        if not env.get(remote_root_env):
            checklist.append(f"Добавить в {env_file}: {remote_root_env}=<remote WordPress root> (images.upload.remote_root_env)")
        for env_name in ("SSH_HOST", "SSH_USER"):
            if not env.get(env_name):
                checklist.append(f"Добавить в {env_file}: {env_name}= (для scripts/wp-photo-image.py upload)")


def rel_project_path(project_root: pathlib.Path, raw_path: str) -> pathlib.Path:
    path = pathlib.Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    return path


def numeric_value(value, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def check_project_policies(cfg: dict, env: dict, project_root: pathlib.Path, checklist: list, warnings: list):
    defaults = {
        "neuronwriter_limits": "seo/neuronwriter-limits.yaml",
        "google_nlp_policy": "seo/entities/google-nlp-policy.yaml",
        "data_collection_map": "seo/seo-data-collection-map.md",
        "access_setup_runbook": "seo/access-setup-runbook.md",
        "ai_visibility_prompts": "seo/ai-visibility-prompts.csv",
        "tool_budget": "seo/tool-budget.yaml",
        "automation_policy": "seo/automation-policy.yaml",
        "usage_ledger": "seo/usage/usage-ledger.jsonl",
        "latest_usage_report": "seo/setup/latest-usage-ledger.md",
        "spend_guard_generated": "seo/spend-guard.generated.yaml",
        "spend_guard_report": "seo/setup/spend-guard.md",
        "spend_checklist": "seo/setup/spend-checklist.csv",
        "latest_spend_guard": "seo/setup/latest-spend-guard.md",
        "tool_stack_generated": "seo/tool-stack.generated.yaml",
        "tool_stack_report": "seo/setup/tool-stack-report.md",
        "latest_tool_stack": "seo/setup/latest-tool-stack.md",
        "growth_roadmap_generated": "seo/growth-roadmap.generated.yaml",
        "growth_roadmap_report": "seo/setup/growth-roadmap.md",
        "latest_growth_roadmap": "seo/setup/latest-growth-roadmap.md",
        "onboarding_generated": "seo/onboarding.generated.yaml",
        "onboarding_playbook": "seo/setup/onboarding-playbook.md",
        "onboarding_checklist": "seo/setup/onboarding-checklist.csv",
        "latest_onboarding_playbook": "seo/setup/latest-onboarding-playbook.md",
        "setup_blueprint_generated": "seo/setup-blueprint.generated.yaml",
        "setup_blueprint": "seo/setup/setup-blueprint.md",
        "setup_blueprint_json": "seo/setup/setup-blueprint.json",
        "setup_matrix_csv": "seo/setup/setup-matrix.csv",
        "latest_setup_blueprint": "seo/setup/latest-setup-blueprint.md",
        "upgrade_assistant": "seo/setup/upgrade-assistant.md",
        "upgrade_assistant_json": "seo/setup/upgrade-assistant.json",
        "upgrade_questionnaire_csv": "seo/setup/upgrade-questionnaire.csv",
        "latest_upgrade_assistant": "seo/setup/latest-upgrade-assistant.md",
        "access_key_assistant": "seo/setup/access-key-assistant.md",
        "access_key_assistant_json": "seo/setup/access-key-assistant.json",
        "access_key_assistant_csv": "seo/setup/access-key-assistant.csv",
        "latest_access_key_assistant": "seo/setup/latest-access-key-assistant.md",
        "launch_plan_generated": "seo/launch-plan.generated.yaml",
        "launch_plan_report": "seo/setup/launch-plan.md",
        "launch_checklist": "seo/setup/launch-checklist.csv",
        "latest_launch_plan": "seo/setup/latest-launch-plan.md",
        "context_pack_report": "seo/setup/context-pack.md",
        "context_pack_json": "seo/setup/context-pack.json",
        "latest_context_pack": "seo/setup/latest-context-pack.md",
        "setup_gap_audit_report": "seo/setup/setup-gap-audit.md",
        "setup_gap_audit_json": "seo/setup/setup-gap-audit.json",
        "latest_setup_gap_audit": "seo/setup/latest-setup-gap-audit.md",
        "setup_questionnaire": "seo/setup/setup-questionnaire.md",
        "setup_questionnaire_csv": "seo/setup/setup-questionnaire.csv",
        "latest_setup_questionnaire": "seo/setup/latest-setup-questionnaire.md",
        "setup_answer_plan": "seo/setup/setup-answer-plan.md",
        "setup_answer_plan_json": "seo/setup/setup-answer-plan.json",
        "latest_setup_answer_plan": "seo/setup/latest-setup-answer-plan.md",
        "automation_recommendations": "seo/automations/automation-recommendations.md",
        "automation_policy_generated": "seo/automation-policy.generated.yaml",
        "setup_control_plane": "seo/setup/setup-control-plane.md",
        "latest_task_route": "seo/setup/latest-task-route.md",
        "project_intake": "seo/project-intake.yaml",
        "project_intake_report": "seo/project-intake-report.md",
        "project_profile": "seo/project-profile.generated.yaml",
        "ai_brand_audit_report": "seo/vnext/ai-brand-audit.md",
        "ai_brand_audit_json": "seo/vnext/ai-brand-audit.json",
        "latest_ai_brand_audit": "seo/vnext/latest-ai-brand-audit.md",
        "latest_ai_brand_audit_json": "seo/vnext/latest-ai-brand-audit.json",
        "answer_units_audit_report": "seo/vnext/answer-units-audit.md",
        "answer_units_audit_json": "seo/vnext/answer-units-audit.json",
        "latest_answer_units_audit": "seo/vnext/latest-answer-units-audit.md",
        "latest_answer_units_audit_json": "seo/vnext/latest-answer-units-audit.json",
        "eeat_evidence_map_report": "seo/vnext/eeat-evidence-map.md",
        "eeat_evidence_map_json": "seo/vnext/eeat-evidence-map.json",
        "latest_eeat_evidence_map": "seo/vnext/latest-eeat-evidence-map.md",
        "latest_eeat_evidence_map_json": "seo/vnext/latest-eeat-evidence-map.json",
        "geo_kpi_model_report": "seo/vnext/geo-kpi-model.md",
        "geo_kpi_model_json": "seo/vnext/geo-kpi-model.json",
        "latest_geo_kpi_model": "seo/vnext/latest-geo-kpi-model.md",
        "latest_geo_kpi_model_json": "seo/vnext/latest-geo-kpi-model.json",
        "log_bot_audit_report": "seo/vnext/log-bot-audit.md",
        "log_bot_audit_json": "seo/vnext/log-bot-audit.json",
        "latest_log_bot_audit": "seo/vnext/latest-log-bot-audit.md",
        "latest_log_bot_audit_json": "seo/vnext/latest-log-bot-audit.json",
        "ai_bot_access_check_report": "seo/vnext/ai-bot-access-check.md",
        "ai_bot_access_check_json": "seo/vnext/ai-bot-access-check.json",
        "latest_ai_bot_access_check": "seo/vnext/latest-ai-bot-access-check.md",
        "latest_ai_bot_access_check_json": "seo/vnext/latest-ai-bot-access-check.json",
        "technical_guardrails_audit_report": "seo/vnext/technical-guardrails-audit.md",
        "technical_guardrails_audit_json": "seo/vnext/technical-guardrails-audit.json",
        "latest_technical_guardrails_audit": "seo/vnext/latest-technical-guardrails-audit.md",
        "latest_technical_guardrails_audit_json": "seo/vnext/latest-technical-guardrails-audit.json",
        "snippet_sitemap_audit_report": "seo/vnext/snippet-sitemap-audit.md",
        "snippet_sitemap_audit_json": "seo/vnext/snippet-sitemap-audit.json",
        "latest_snippet_sitemap_audit": "seo/vnext/latest-snippet-sitemap-audit.md",
        "latest_snippet_sitemap_audit_json": "seo/vnext/latest-snippet-sitemap-audit.json",
        "traffic_drop_diagnostics_report": "seo/vnext/traffic-drop-diagnostics.md",
        "traffic_drop_diagnostics_json": "seo/vnext/traffic-drop-diagnostics.json",
        "latest_traffic_drop_diagnostics": "seo/vnext/latest-traffic-drop-diagnostics.md",
        "latest_traffic_drop_diagnostics_json": "seo/vnext/latest-traffic-drop-diagnostics.json",
        "cannibalization_audit_report": "seo/vnext/cannibalization-audit.md",
        "cannibalization_audit_json": "seo/vnext/cannibalization-audit.json",
        "latest_cannibalization_audit": "seo/vnext/latest-cannibalization-audit.md",
        "latest_cannibalization_audit_json": "seo/vnext/latest-cannibalization-audit.json",
        "ru_commerce_readiness_report": "seo/vnext/ru-commerce-readiness.md",
        "ru_commerce_readiness_json": "seo/vnext/ru-commerce-readiness.json",
        "latest_ru_commerce_readiness": "seo/vnext/latest-ru-commerce-readiness.md",
        "latest_ru_commerce_readiness_json": "seo/vnext/latest-ru-commerce-readiness.json",
        "offpage_risk_audit_report": "seo/vnext/offpage-risk-audit.md",
        "offpage_risk_audit_json": "seo/vnext/offpage-risk-audit.json",
        "latest_offpage_risk_audit": "seo/vnext/latest-offpage-risk-audit.md",
        "latest_offpage_risk_audit_json": "seo/vnext/latest-offpage-risk-audit.json",
        "conversion_sxo_audit_report": "seo/vnext/conversion-sxo-audit.md",
        "conversion_sxo_audit_json": "seo/vnext/conversion-sxo-audit.json",
        "latest_conversion_sxo_audit": "seo/vnext/latest-conversion-sxo-audit.md",
        "latest_conversion_sxo_audit_json": "seo/vnext/latest-conversion-sxo-audit.json",
        "expert_source_pack_report": "seo/vnext/expert-source-pack.md",
        "expert_source_pack_json": "seo/vnext/expert-source-pack.json",
        "latest_expert_source_pack": "seo/vnext/latest-expert-source-pack.md",
        "latest_expert_source_pack_json": "seo/vnext/latest-expert-source-pack.json",
    }
    configured = cfg.get("policy_files", {}) or {}
    if not isinstance(configured, dict):
        warnings.append("policy_files должен быть словарём путей")
        configured = {}

    policy_paths = {key: configured.get(key, default) for key, default in defaults.items()}
    for key, raw_path in policy_paths.items():
        path = rel_project_path(project_root, raw_path)
        if not path.exists():
            checklist.append(f"Создать policy-файл: {raw_path} ({key})")

    neuron = cfg.get("sources", {}).get("neuronwriter", {}) if isinstance(cfg.get("sources", {}), dict) else {}
    if (neuron.get("enabled") or env.get("NEURON_API_KEY")) and not rel_project_path(project_root, policy_paths["neuronwriter_limits"]).exists():
        warnings.append("NeuronWriter включён/настроен, но нет seo/neuronwriter-limits.yaml — нельзя безопасно тратить лимиты")

    google_nlp = cfg.get("sources", {}).get("google_cloud_nlp", {}) if isinstance(cfg.get("sources", {}), dict) else {}
    nlp_enabled = google_nlp.get("enabled") or env.get("GOOGLE_NLP_ENABLED") == "1"
    if nlp_enabled:
        if not rel_project_path(project_root, policy_paths["google_nlp_policy"]).exists():
            warnings.append("Google Cloud NLP включён, но нет seo/entities/google-nlp-policy.yaml")
        if env.get("GOOGLE_NLP_BILLING_APPROVED") == "1":
            budget_status = env.get("GOOGLE_NLP_BUDGET_STATUS", "")
            if not budget_status or budget_status.startswith("disabled"):
                checklist.append("Обновить GOOGLE_NLP_BUDGET_STATUS после создания Cloud budget alert")
        if env.get("GOOGLE_NLP_CACHE_DIR") and not env.get("GOOGLE_NLP_CACHE_DAYS"):
            checklist.append("Добавить GOOGLE_NLP_CACHE_DAYS=30 для кэширования Google NLP")

    country = (cfg.get("locale", {}) or {}).get("country")
    if country == "RU" and not rel_project_path(project_root, policy_paths["data_collection_map"]).exists():
        warnings.append("RU-проект без seo/seo-data-collection-map.md — зафиксируй tracking policy перед аналитикой")


def check_governance(cfg: dict, project_root: pathlib.Path, checklist: list, warnings: list):
    gov = cfg.get("governance", {})
    if not isinstance(gov, dict) or not gov:
        checklist.append("Добавить governance: token_policy, budget_policy, automation_policy")
        return

    token_policy = gov.get("token_policy", {}) if isinstance(gov.get("token_policy"), dict) else {}
    if token_policy.get("raw_data_in_context") is True:
        warnings.append("governance.token_policy.raw_data_in_context=true — это резко увеличит расход токенов")
    if token_policy.get("progressive_disclosure") is False:
        warnings.append("governance.token_policy.progressive_disclosure=false — скилл будет читать лишний контекст")
    if token_policy.get("cache_first") is False:
        warnings.append("governance.token_policy.cache_first=false — дорогие источники могут запускаться повторно")
    if numeric_value(token_policy.get("max_context_input_tokens_per_phase")) > 90000:
        warnings.append("max_context_input_tokens_per_phase > 90000 — проверь, действительно ли нужен такой большой контекст")

    budget_policy = gov.get("budget_policy", {}) if isinstance(gov.get("budget_policy"), dict) else {}
    paid_api_cap = numeric_value(budget_policy.get("monthly_paid_api_usd_cap"))
    paid_default = budget_policy.get("paid_tools_default", "approval_only")
    sources = cfg.get("sources", {}) if isinstance(cfg.get("sources", {}), dict) else {}
    paid_source_names = {
        "neuronwriter",
        "google_cloud_nlp",
        "keyso",
        "keys_so",
        "serpstat",
        "spyfu",
        "dataforseo",
    }
    active_by_profile: set[str] = set()
    profile_id = cfg.get("region_profile")
    if profile_id:
        profile = load_region_profile(profile_id) or {}
        active_by_profile = (set(profile.get("sources_enable", [])) | set(profile.get("sources_proxy", []))) - set(profile.get("sources_disable", []))
        for name, src in sources.items():
            if isinstance(src, dict) and "enabled" in src:
                if src["enabled"]:
                    active_by_profile.add(name)
                else:
                    active_by_profile.discard(name)
    active_paid = [
        name
        for name, src in sources.items()
        if name in paid_source_names and isinstance(src, dict) and (src.get("enabled") or name in active_by_profile)
    ]
    if active_paid and paid_api_cap <= 0 and paid_default != "enabled_with_caps":
        checklist.append(f"Утвердить budget_policy.monthly_paid_api_usd_cap для активных paid/quota sources: {', '.join(active_paid)}")
    if budget_policy.get("ads_spend_enabled") and numeric_value(budget_policy.get("monthly_total_usd_cap")) <= 0:
        warnings.append("ads_spend_enabled=true, но monthly_total_usd_cap=0")

    automation = gov.get("automation_policy", {}) if isinstance(gov.get("automation_policy"), dict) else {}
    valid_modes = {"disabled", "report_only", "approval_only", "auto_with_caps"}
    mode = automation.get("default_mode")
    if mode and mode not in valid_modes:
        warnings.append(f"governance.automation_policy.default_mode={mode!r} — ожидалось {sorted(valid_modes)}")
    if automation.get("create_schedules"):
        policy_files = cfg.get("policy_files", {}) if isinstance(cfg.get("policy_files", {}), dict) else {}
        automation_policy = policy_files.get("automation_policy", "seo/automation-policy.yaml")
        if not rel_project_path(project_root, automation_policy).exists():
            checklist.append("Создать seo/automation-policy.yaml перед созданием scheduled automations")
        planner = automation.get("planner_script") or (cfg.get("monthly_automation", {}) or {}).get("planner_script")
        if planner and not pathlib.Path(os.path.expanduser(planner)).exists():
            warnings.append(f"automation planner_script не найден: {planner}")
        checklist.append("Сгенерировать и проверить schedule artifacts: python3 ~/.codex/skills/seo-cycle/scripts/automation-plan.py --write --include-disabled")


def check_content_rules(cfg: dict, warnings: list):
    rules = cfg.get("content_rules", {})
    if rules.get("stock_first", {}).get("enabled") and cfg.get("project_type") not in ("ecommerce", "local_business"):
        warnings.append(f"content_rules.stock_first.enabled=true, но project_type={cfg.get('project_type')!r} — обычно stock-first нужен только для ecommerce")
    if rules.get("fact_check", {}).get("enabled"):
        results_dir = rules["fact_check"].get("results_dir")
        if results_dir:
            p = pathlib.Path(results_dir)
            if not p.exists():
                warnings.append(f"content_rules.fact_check.results_dir={results_dir} не существует — будет создан автоматом при первом fact-check")


def check_artifacts(cfg: dict, project_root: pathlib.Path, warnings: list):
    arts = cfg.get("artifacts", {})
    for key, path in arts.items():
        if path:
            p = pathlib.Path(path)
            if not p.is_absolute():
                p = project_root / p
            if not p.exists():
                warnings.append(f"artifacts.{key}={path} не существует — будет создан автоматом")


def check_observability_env(cfg: dict, env: dict, checklist: list, warnings: list):
    """Проверка env vars для observability hub (Phase 9 fetchers)."""
    sources = cfg.get("sources", {}) or {}
    mon = cfg.get("monitoring", {}) or {}

    # GSC (через делегат `claude-seo:seo-google`, но если хочется напрямую — gsc-fetch.py)
    gsc = sources.get("google_search_console", {})
    if gsc.get("enabled"):
        if not env.get("GOOGLE_APPLICATION_CREDENTIALS"):
            checklist.append("Опц. в .env: GOOGLE_APPLICATION_CREDENTIALS=<path> (для gsc-fetch.py / ga4-fetch.py прямого вызова)")
        if not env.get("GSC_SITE_URL"):
            checklist.append("Опц. в .env: GSC_SITE_URL=sc-domain:example.com (для gsc-fetch.py)")

    # GA4
    if mon.get("google_analytics_4", {}).get("enabled") or sources.get("google_analytics_4", {}).get("enabled"):
        if not env.get("GA4_PROPERTY_ID"):
            checklist.append("Опц. в .env: GA4_PROPERTY_ID=<numeric_id> (для ga4-fetch.py)")

    # PSI
    psi = mon.get("pagespeed_insights", {})
    if psi.get("enabled"):
        # API key опционален — без него работает с rate limit
        pass

    # Яндекс (если yandex в engines)
    yandex_engines = any(e.get("name") == "yandex" for e in cfg.get("engines", []))
    if yandex_engines:
        for src_name in ("yandex_metrika", "yandex_webmaster_history"):
            s = sources.get(src_name, {})
            if s.get("enabled"):
                if not env.get("YANDEX_OAUTH_TOKEN"):
                    checklist.append(f"Опц. в .env: YANDEX_OAUTH_TOKEN=<oauth_token> (для {src_name})")
                    break
        if sources.get("yandex_metrika", {}).get("enabled") and not env.get("YANDEX_METRIKA_COUNTER_ID"):
            checklist.append("Опц. в .env: YANDEX_METRIKA_COUNTER_ID=<id> (для metrika-fetch.py)")
        if sources.get("yandex_webmaster_history", {}).get("enabled"):
            if not env.get("YANDEX_USER_ID"):
                checklist.append("Опц. в .env: YANDEX_USER_ID=<id> (для webmaster-fetch.py)")
            if not env.get("YANDEX_WEBMASTER_HOST_ID"):
                checklist.append("Опц. в .env: YANDEX_WEBMASTER_HOST_ID=https:example.com:443 (для webmaster-fetch.py)")


def check_v11_extensions(cfg: dict, env: dict, checklist: list, warnings: list):
    """Опц. проверки для секций schema v1.1: mode, monitoring, eeat, migration, backlinks."""
    mode = cfg.get("mode", "standard")
    if mode not in ("standard", "migration", "programmatic"):
        warnings.append(f"mode={mode!r} — неизвестное значение (ожидаем standard|migration|programmatic)")

    if mode == "migration":
        mig = cfg.get("migration", {})
        if not mig.get("enabled"):
            warnings.append("mode=migration, но migration.enabled=false — включи блок migration")
        for f in ("old_domain", "new_domain", "redirects_file"):
            if not mig.get(f):
                warnings.append(f"migration.{f} не заполнено — обязательно для mode=migration")

    mon = cfg.get("monitoring", {})
    if mon.get("pagespeed_insights", {}).get("enabled"):
        api_env = mon["pagespeed_insights"].get("api_key_env")
        if api_env and not env.get(api_env):
            checklist.append(f"Опц. в .env: {api_env}= (для PSI без ключа — rate limit ~25 req/day)")

    eeat = cfg.get("eeat", {})
    if eeat.get("enabled") and cfg.get("project_type") not in ("blog", "media", "ecommerce", "saas"):
        warnings.append(f"eeat.enabled=true для project_type={cfg.get('project_type')!r} — обычно EEAT критичнее для blog/media/ecommerce")

    bl = cfg.get("backlinks", {})
    if bl.get("enabled") and bl.get("source") == "manual" and not pathlib.Path(bl.get("file","")).exists():
        warnings.append(f"backlinks.enabled=true с source=manual, но файл {bl.get('file')} не существует")


def check_vnext_guardrails(cfg: dict, checklist: list, warnings: list):
    """Report-only safety checks for SEO/AEO/GEO vNext modules."""
    modules = [
        "ai_brand_audit",
        "answer_units",
        "server_logs",
        "eeat_evidence",
        "geo_kpi",
        "technical_guardrails",
        "snippet_sitemap",
        "traffic_diagnostics",
        "cannibalization",
        "local_seo",
        "ru_commerce",
        "offpage_risk",
        "conversion_sxo",
        "expert_sources",
    ]
    vnext = cfg.get("vnext", {}) if isinstance(cfg.get("vnext"), dict) else {}
    if vnext and vnext.get("raw_data_in_context") is True:
        warnings.append("vnext.raw_data_in_context=true — full transcripts/logs should stay on disk; use distillates/JSONL.")
    if vnext and vnext.get("paid_api_default") not in (None, "disabled", "approval_only"):
        warnings.append("vnext.paid_api_default should be disabled or approval_only.")
    for module in modules:
        block = cfg.get(module, {}) if isinstance(cfg.get(module), dict) else {}
        if not block:
            continue
        if block.get("writes_to_site"):
            warnings.append(f"{module}.writes_to_site=true — vNext modules must stay report-only by default.")
        if block.get("paid_api_required") and (cfg.get("governance", {}).get("budget_policy", {}).get("monthly_paid_api_usd_cap", 0) in (0, "0", None)):
            checklist.append(f"Утвердить paid API budget/approval перед запуском {module}.paid_api_required=true")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config", nargs="?", help="Путь к seo-cycle.yaml (по умолчанию — поиск в текущей директории)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.config:
        cfg_path = pathlib.Path(args.config).resolve()
        if not cfg_path.exists():
            print(f"ERROR: {cfg_path} не найден", file=sys.stderr)
            sys.exit(2)
    else:
        cfg_path = find_config(pathlib.Path.cwd())
        if not cfg_path:
            print(f"ERROR: seo-cycle.yaml не найден в {pathlib.Path.cwd()}", file=sys.stderr)
            print(f"  Ожидаемые имена/места:", file=sys.stderr)
            for p in CONFIG_SEARCH_PATHS:
                print(f"    {p}", file=sys.stderr)
            print(f"\n  Скопируй шаблон:", file=sys.stderr)
            print(f"    cp ~/.codex/skills/seo-cycle/config/project.template.yaml seo-cycle.yaml", file=sys.stderr)
            sys.exit(2)

    project_root = cfg_path.parent
    if cfg_path.name in (".seo-cycle.yaml", "seo-cycle.yaml"):
        project_root = cfg_path.parent
    elif "/seo/" in str(cfg_path) or "/.claude/" in str(cfg_path):
        project_root = cfg_path.parent.parent

    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: не могу распарсить YAML: {e}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(cfg, dict):
        print(f"ERROR: конфиг не является словарём", file=sys.stderr)
        sys.exit(2)

    env = load_env(project_root)

    errors: list[str] = []
    warnings: list[str] = []
    checklist: list[str] = []

    check_required(cfg, errors, warnings)
    check_sources(cfg, env, checklist, warnings)
    check_publishing(cfg, env, checklist, warnings)
    check_images(cfg, env, project_root, checklist, warnings)
    check_project_policies(cfg, env, project_root, checklist, warnings)
    check_governance(cfg, project_root, checklist, warnings)
    check_content_rules(cfg, warnings)
    check_artifacts(cfg, project_root, warnings)
    check_v11_extensions(cfg, env, checklist, warnings)
    check_vnext_guardrails(cfg, checklist, warnings)
    check_observability_env(cfg, env, checklist, warnings)

    print(f"== seo-cycle config validation ==")
    print(f"  Config: {cfg_path}")
    print(f"  Project root: {project_root}")
    print(f"  Project: {cfg.get('project',{}).get('name','?')} ({cfg.get('project',{}).get('domain','?')})")
    print(f"  Locale: {cfg.get('locale',{}).get('language','?')}-{cfg.get('locale',{}).get('country','?')} / {cfg.get('locale',{}).get('region','?')}")
    print(f"  Type: {cfg.get('project_type','?')} on {cfg.get('cms','?')}")
    print(f"  Engines: {', '.join(e.get('name','?') for e in cfg.get('engines', []))}")
    print()

    if errors:
        print(f"❌ ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        print()
    if warnings:
        print(f"⚠  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
        print()
    if checklist:
        print(f"📋 ЧЕК-ЛИСТ что подключить ({len(checklist)}):")
        for c in checklist:
            print(f"  [ ] {c}")
        print()

    if not errors and not warnings and not checklist:
        print("✓ Конфиг полностью валиден, все источники готовы к запуску.")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
