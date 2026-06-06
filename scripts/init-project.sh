#!/bin/bash
# init-project.sh — интерактивный wizard для нового проекта seo-cycle.
#
# Задаёт базовые вопросы + governance + image workflow → генерирует
# seo-cycle.yaml, .env.example, AGENTS.md и policy-шаблоны в текущей директории
# → запускает validate-config.py.
#
# Идемпотентный: если seo-cycle.yaml уже существует, спрашивает подтверждение
# перед перезаписью.
#
# Использование (из корня нового проекта):
#   ./.codex/skills/seo-cycle/scripts/init-project.sh

set -e

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$SKILL_ROOT/config/project.template.yaml"
ENV_TEMPLATE="$SKILL_ROOT/.env.example"
POLICY_TEMPLATE_DIR="$SKILL_ROOT/templates/project-policies"
TARGET="seo-cycle.yaml"
TARGET_ENV=".env.example"
NON_INTERACTIVE="${SEO_CYCLE_NON_INTERACTIVE:-0}"
USED_DEFAULT_STDIN_NOTICE=0

usage() {
    cat <<'EOF'
init-project.sh [--non-interactive]

Options:
  --non-interactive   Do not prompt; use safe defaults.
  -h, --help          Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --non-interactive|--defaults)
            NON_INTERACTIVE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

read_answer() {
    local __var="$1"
    local prompt="$2"
    local default_value="${3:-}"
    local answer=""

    if [ "$NON_INTERACTIVE" = "1" ]; then
        answer="$default_value"
    elif [ -r /dev/tty ] && { : </dev/tty; } 2>/dev/null; then
        IFS= read -r -p "$prompt" answer </dev/tty || answer=""
    else
        if [ "$USED_DEFAULT_STDIN_NOTICE" = "0" ]; then
            echo "ℹ интерактивный stdin недоступен — беру safe defaults"
            USED_DEFAULT_STDIN_NOTICE=1
        fi
        answer="$default_value"
    fi

    printf -v "$__var" '%s' "$answer"
}

echo "════════════════════════════════════════════════════════════"
echo "  seo-cycle init wizard"
echo "════════════════════════════════════════════════════════════"
echo ""

# Проверка идемпотентности
if [ -f "$TARGET" ]; then
    echo "⚠  $TARGET уже существует."
    read_answer overwrite "Перезаписать? [y/N]: " ""
    case "$overwrite" in
        y|Y|yes|YES) ;;
        *) echo "Отмена. Существующий конфиг не тронут."; exit 0 ;;
    esac
fi

if [ ! -f "$TEMPLATE" ]; then
    echo "ERROR: шаблон не найден: $TEMPLATE" >&2
    exit 2
fi

echo "Отвечай на базовые вопросы (Enter — взять default в скобках):"
echo ""

read_answer PROJECT_NAME "1. Имя проекта (human-readable, например «Эмвуди»): " ""
PROJECT_NAME="${PROJECT_NAME:-MyProject}"

read_answer DOMAIN "2. Домен (без https://, например example.com): " ""
DOMAIN="${DOMAIN:-example.com}"

read_answer BRAND_UF "3. Brand name в user-facing текстах [$PROJECT_NAME]: " ""
BRAND_UF="${BRAND_UF:-$PROJECT_NAME}"

read_answer BRAND_TECH "4. Brand technical slug (для URL/кода, латиница) [$(echo "$DOMAIN" | cut -d. -f1)]: " ""
BRAND_TECH="${BRAND_TECH:-$(echo "$DOMAIN" | cut -d. -f1)}"

read_answer PROJECT_TYPE "5. project_type [ecommerce/blog/saas/local_business/corporate/media/portfolio] (default: ecommerce): " ""
PROJECT_TYPE="${PROJECT_TYPE:-ecommerce}"

read_answer CMS "6. CMS [wordpress/shopify/webflow/nextjs/static/custom] (default: wordpress): " ""
CMS="${CMS:-wordpress}"

read_answer LOCALE "7. Язык/Регион [ru-RU/en-US/en-GB/de-DE] (default: ru-RU): " ""
LOCALE="${LOCALE:-ru-RU}"

echo ""
echo "Блок управления бюджетами и автоматизациями:"

read_answer GOVERNANCE_PROFILE "8. Governance profile [lean_quality/balanced_growth/aggressive_growth/custom] (default: lean_quality): " ""
GOVERNANCE_PROFILE="${GOVERNANCE_PROFILE:-lean_quality}"

read_answer PAID_API_BUDGET "9. Monthly paid API budget USD (0 = без платных расходов, default: 0): " ""
PAID_API_BUDGET="${PAID_API_BUDGET:-0}"

read_answer LLM_BUDGET "10. Monthly LLM/token budget USD (0 = без отдельного бюджета, default: 0): " ""
LLM_BUDGET="${LLM_BUDGET:-0}"

read_answer AUTOMATION_MODE "11. Automation mode [disabled/report_only/approval_only/auto_with_caps] (default: approval_only): " ""
AUTOMATION_MODE="${AUTOMATION_MODE:-approval_only}"

read_answer CREATE_SCHEDULES_ANSWER "12. Создавать scheduled automations сейчас? [y/N]: " ""
case "$CREATE_SCHEDULES_ANSWER" in
    y|Y|yes|YES) CREATE_SCHEDULES=true ;;
    *) CREATE_SCHEDULES=false ;;
esac

echo ""
echo "Блок изображений для SEO-публикаций:"

read_answer IMAGE_FEATURED_RATIO "13. Пропорция featured/hero изображений (default: 16:9): " ""
IMAGE_FEATURED_RATIO="${IMAGE_FEATURED_RATIO:-16:9}"

read_answer IMAGE_INLINE_RATIO "14. Пропорция inline изображений в статьях (default: 16:9): " ""
IMAGE_INLINE_RATIO="${IMAGE_INLINE_RATIO:-16:9}"

read_answer IMAGE_WIDTH "15. Ширина WebP в px (default: 1200): " ""
IMAGE_WIDTH="${IMAGE_WIDTH:-1200}"

read_answer IMAGE_QUALITY "16. WebP quality 1-100 (default: 86): " ""
IMAGE_QUALITY="${IMAGE_QUALITY:-86}"

read_answer IMAGE_SOURCE_POLICY "17. Источник фото [thematic_photos_first/product_photos_first/generate_if_missing/manual_only] (default: thematic_photos_first): " ""
IMAGE_SOURCE_POLICY="${IMAGE_SOURCE_POLICY:-thematic_photos_first}"

read_answer IMAGE_VISUAL_STYLE "18. Визуальный стиль [clean_topical_photo/editorial_photo/product_context_photo] (default: clean_topical_photo): " ""
IMAGE_VISUAL_STYLE="${IMAGE_VISUAL_STYLE:-clean_topical_photo}"

read_answer IMAGE_INLINE_MIN "19. Минимум inline-изображений на пост (default: 2): " ""
IMAGE_INLINE_MIN="${IMAGE_INLINE_MIN:-2}"

read_answer IMAGE_CAPTIONS_ANSWER "20. Caption под inline-картинками обязателен? [Y/n]: " ""
case "$IMAGE_CAPTIONS_ANSWER" in
    n|N|no|NO) IMAGE_CAPTIONS_REQUIRED=false; IMAGE_CAPTION_MODE=none ;;
    *) IMAGE_CAPTIONS_REQUIRED=true; IMAGE_CAPTION_MODE=short_editorial ;;
esac

read_answer IMAGE_TEXT_ANSWER "21. Разрешать видимый текст на изображениях? [y/N]: " ""
case "$IMAGE_TEXT_ANSWER" in
    y|Y|yes|YES) IMAGE_ALLOW_VISIBLE_TEXT=true ;;
    *) IMAGE_ALLOW_VISIBLE_TEXT=false ;;
esac

echo ""
echo "Детальный project intake:"
read_answer DETAILED_INTAKE_ANSWER "22. Запустить подробный wizard стран/движков/маркетинга/tools сейчас? [y/N]: " ""
case "$DETAILED_INTAKE_ANSWER" in
    y|Y|yes|YES) RUN_DETAILED_INTAKE=true ;;
    *) RUN_DETAILED_INTAKE=false ;;
esac

LANG_CODE="${LOCALE%-*}"   # ru
CTRY_CODE="${LOCALE#*-}"   # RU

# Маппинг страны → дефолтные значения yandex_region_code + region текст + профиль
case "$CTRY_CODE" in
    RU) YANDEX_RC=213; REGION_TEXT="Москва и Московская область"; CITY="Москва"; TZ="Europe/Moscow"; REGION_PROFILE=ru ;;
    US) YANDEX_RC=84;  REGION_TEXT="United States"; CITY="New York"; TZ="America/New_York"; REGION_PROFILE=us ;;
    GB) YANDEX_RC=102; REGION_TEXT="United Kingdom"; CITY="London"; TZ="Europe/London"; REGION_PROFILE=eu ;;
    DE) YANDEX_RC=96;  REGION_TEXT="Germany"; CITY="Berlin"; TZ="Europe/Berlin"; REGION_PROFILE=eu ;;
    *)  YANDEX_RC=225; REGION_TEXT="$CTRY_CODE"; CITY="?"; TZ="UTC"; REGION_PROFILE=global ;;
esac

echo ""
echo "Создаю $TARGET..."

# Копируем шаблон и подменяем ключевые поля через sed
cp "$TEMPLATE" "$TARGET"

# macOS / Linux compatible in-place sed. Keep this as a function;
# putting `sed -i ''` into a string variable creates backup files named *'' on macOS.
sed_in_place() {
    if [ "$(uname)" = "Darwin" ]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# Surgical замены — только в первой секции project: и locale:
sed_in_place "s|name: \"Example Shop\"|name: \"$PROJECT_NAME\"|" "$TARGET"
sed_in_place "s|domain: \"example.com\"|domain: \"$DOMAIN\"|" "$TARGET"
sed_in_place "s|brand_name_user_facing: \"Example Shop\"|brand_name_user_facing: \"$BRAND_UF\"|" "$TARGET"
sed_in_place "s|brand_name_technical: \"example\"|brand_name_technical: \"$BRAND_TECH\"|" "$TARGET"
sed_in_place "s|^project_type: ecommerce|project_type: $PROJECT_TYPE|" "$TARGET"
sed_in_place "s|^cms: wordpress|cms: $CMS|" "$TARGET"
sed_in_place "s|  language: ru|  language: $LANG_CODE|" "$TARGET"
sed_in_place "s|  country: RU|  country: $CTRY_CODE|" "$TARGET"
sed_in_place "s|  region: \"Москва и Московская область\"|  region: \"$REGION_TEXT\"|" "$TARGET"
sed_in_place "s|  city: \"Москва\"|  city: \"$CITY\"|" "$TARGET"
sed_in_place "s|  locale_iso: ru-RU|  locale_iso: $LOCALE|" "$TARGET"
sed_in_place "s|  yandex_region_code: 213|  yandex_region_code: $YANDEX_RC|" "$TARGET"
sed_in_place "s|  google_gl: ru|  google_gl: $(echo $CTRY_CODE | tr A-Z a-z)|" "$TARGET"
sed_in_place "s|  google_hl: ru|  google_hl: $LANG_CODE|" "$TARGET"
sed_in_place "s|  timezone: \"Europe/Moscow\"|  timezone: \"$TZ\"|" "$TARGET"

# Governance defaults
sed_in_place "s|  profile: lean_quality|  profile: $GOVERNANCE_PROFILE|" "$TARGET"
sed_in_place "s|    monthly_total_usd_cap: 0|    monthly_total_usd_cap: $PAID_API_BUDGET|" "$TARGET"
sed_in_place "s|    monthly_paid_api_usd_cap: 0|    monthly_paid_api_usd_cap: $PAID_API_BUDGET|" "$TARGET"
sed_in_place "s|    monthly_llm_usd_cap: 0|    monthly_llm_usd_cap: $LLM_BUDGET|" "$TARGET"
sed_in_place "s|    default_mode: approval_only|    default_mode: $AUTOMATION_MODE|" "$TARGET"
sed_in_place "s|    create_schedules: false|    create_schedules: $CREATE_SCHEDULES|" "$TARGET"

# Image workflow defaults
sed_in_place "s|  workflow: photo_first|  workflow: photo_first|" "$TARGET"
sed_in_place "s|  source_policy: thematic_photos_first|  source_policy: $IMAGE_SOURCE_POLICY|" "$TARGET"
sed_in_place "s|  visual_style: clean_topical_photo|  visual_style: $IMAGE_VISUAL_STYLE|" "$TARGET"
sed_in_place "s|  allow_visible_text: false|  allow_visible_text: $IMAGE_ALLOW_VISIBLE_TEXT|" "$TARGET"
sed_in_place "s|    width: 1200|    width: $IMAGE_WIDTH|" "$TARGET"
sed_in_place "s|    quality: 86|    quality: $IMAGE_QUALITY|" "$TARGET"
sed_in_place "s|    inline_required: true|    inline_required: $IMAGE_CAPTIONS_REQUIRED|" "$TARGET"
sed_in_place "s|    mode: short_editorial|    mode: $IMAGE_CAPTION_MODE|" "$TARGET"
sed_in_place "s|  inline_min_per_post: 2|  inline_min_per_post: $IMAGE_INLINE_MIN|" "$TARGET"
sed_in_place "s|    featured: \"16:9\"|    featured: \"$IMAGE_FEATURED_RATIO\"|" "$TARGET"
sed_in_place "s|    hero: \"16:9\"|    hero: \"$IMAGE_FEATURED_RATIO\"|" "$TARGET"
sed_in_place "s|    article_inline: \"16:9\"|    article_inline: \"$IMAGE_INLINE_RATIO\"|" "$TARGET"

# Региональный профиль источников (управляет вкл/выкл Яндекс/Google/SaaS)
sed_in_place "s|^region_profile: ru|region_profile: $REGION_PROFILE|" "$TARGET"
echo "ℹ region_profile: $REGION_PROFILE (для $CTRY_CODE) — источники развернутся через resolve-sources.py"

# Копируем .env.example если есть
if [ -f "$ENV_TEMPLATE" ] && [ ! -f "$TARGET_ENV" ]; then
    cp "$ENV_TEMPLATE" "$TARGET_ENV"
    echo "✓ $TARGET_ENV скопирован (заполни перед использованием API-источников)"
fi

# Codex entrypoint for project root (do not overwrite an existing AGENTS.md)
if [ ! -e "AGENTS.md" ]; then
    ln -sf "$SKILL_ROOT/AGENTS.md" "AGENTS.md"
    echo "✓ AGENTS.md → $SKILL_ROOT/AGENTS.md (точка входа Codex)"
else
    echo "ℹ AGENTS.md уже существует — не трогаю"
fi

# Project policy templates: safe defaults, no secrets
TODAY="$(date +%F)"
mkdir -p seo/entities
copy_policy_template() {
    local src="$1"
    local dest="$2"
    if [ ! -f "$src" ]; then
        return 0
    fi
    if [ -f "$dest" ]; then
        echo "ℹ $dest уже существует — не трогаю"
        return 0
    fi
    cp "$src" "$dest"
    sed_in_place "s|__DATE__|$TODAY|g" "$dest"
    sed_in_place "s|__PROJECT_NAME__|$PROJECT_NAME|g" "$dest"
    sed_in_place "s|__DOMAIN__|$DOMAIN|g" "$dest"
    echo "✓ policy создан: $dest"
}

copy_policy_template "$POLICY_TEMPLATE_DIR/neuronwriter-limits.template.yaml" "seo/neuronwriter-limits.yaml"
copy_policy_template "$POLICY_TEMPLATE_DIR/google-nlp-policy.template.yaml" "seo/entities/google-nlp-policy.yaml"
copy_policy_template "$POLICY_TEMPLATE_DIR/seo-data-collection-map.template.md" "seo/seo-data-collection-map.md"
copy_policy_template "$POLICY_TEMPLATE_DIR/access-setup-runbook.template.md" "seo/access-setup-runbook.md"
copy_policy_template "$POLICY_TEMPLATE_DIR/ai-visibility-prompts.template.csv" "seo/ai-visibility-prompts.csv"
copy_policy_template "$POLICY_TEMPLATE_DIR/tool-budget.template.yaml" "seo/tool-budget.yaml"
copy_policy_template "$POLICY_TEMPLATE_DIR/automation-policy.template.yaml" "seo/automation-policy.yaml"
copy_policy_template "$POLICY_TEMPLATE_DIR/project-intake.template.yaml" "seo/project-intake.yaml"

if [ -f "seo/tool-budget.yaml" ]; then
    sed_in_place "s|monthly_total_usd_cap: 0|monthly_total_usd_cap: $PAID_API_BUDGET|" "seo/tool-budget.yaml"
    sed_in_place "s|monthly_paid_api_usd_cap: 0|monthly_paid_api_usd_cap: $PAID_API_BUDGET|" "seo/tool-budget.yaml"
    sed_in_place "s|monthly_llm_usd_cap: 0|monthly_llm_usd_cap: $LLM_BUDGET|" "seo/tool-budget.yaml"
fi
if [ -f "seo/automation-policy.yaml" ]; then
    sed_in_place "s|default_mode: approval_only|default_mode: $AUTOMATION_MODE|" "seo/automation-policy.yaml"
    sed_in_place "s|create_schedules: false|create_schedules: $CREATE_SCHEDULES|" "seo/automation-policy.yaml"
fi
if [ -f "seo/project-intake.yaml" ]; then
    sed_in_place "s|default_governance_profile: lean_quality|default_governance_profile: $GOVERNANCE_PROFILE|" "seo/project-intake.yaml"
    sed_in_place "s|default_automation_mode: approval_only|default_automation_mode: $AUTOMATION_MODE|" "seo/project-intake.yaml"
fi

if [ -f "seo/project-intake.yaml" ]; then
    if [ "$RUN_DETAILED_INTAKE" = "true" ]; then
        python3 "$SKILL_ROOT/scripts/project-intake-wizard.py" "$TARGET" --interactive --write \
            && echo "✓ project intake заполнен: seo/project-intake.yaml + seo/project-intake-report.md"
    else
        python3 "$SKILL_ROOT/scripts/project-intake-wizard.py" "$TARGET" --defaults --write >/dev/null 2>&1 \
            && echo "✓ project intake уточнён из $TARGET: seo/project-intake.yaml + seo/project-intake-report.md" \
            || echo "ℹ project intake не уточнён — запусти scripts/project-intake-wizard.py --interactive --write"
    fi
    python3 "$SKILL_ROOT/scripts/project-profile.py" "$TARGET" --write >/dev/null 2>&1 \
        && echo "✓ project profile создан: seo/project-profile.generated.yaml + seo/project-profile-report.md" \
        || echo "ℹ project profile не создан — запусти scripts/project-profile.py после заполнения intake"
    read_answer APPLY_PROFILE_ANSWER "23. Применить generated project profile к $TARGET сейчас? [y/N]: " ""
    case "$APPLY_PROFILE_ANSWER" in
        y|Y|yes|YES)
            python3 "$SKILL_ROOT/scripts/project-profile.py" "$TARGET" --apply \
                && echo "✓ project profile применён к $TARGET (backup создан рядом)"
            ;;
        *) echo "ℹ project profile не применён — после review запусти scripts/project-profile.py --apply" ;;
    esac
fi

python3 "$SKILL_ROOT/scripts/setup-control-plane.py" "$TARGET" --write --skip-intake >/dev/null 2>&1 \
    && echo "✓ setup control plane создан: context-pack/setup-blueprint/setup-gap-audit/setup-questionnaire/setup-answer-plan path/launch-plan/spend-guard/setup/task-route/usage-ledger/tool-stack/growth-roadmap/onboarding + automation recommendations" \
    || echo "ℹ setup control plane не создан — запусти scripts/setup-control-plane.py --write"

python3 "$SKILL_ROOT/scripts/project-mcp-config.py" "$TARGET" --write >/dev/null 2>&1 \
    && echo "✓ project-local MCP config создан: .codex/config.toml (секреты читаются из .env)" \
    || echo "ℹ project-local MCP config не создан — запусти scripts/project-mcp-config.py --write"

# Дозапись проекта в общий реестр (идемпотентно — по path)
REGISTRY="$SKILL_ROOT/config/projects-registry.yaml"
PROJECT_PATH="$(pwd)"
if [ "${SEO_CYCLE_SKIP_REGISTRY:-0}" = "1" ]; then
    echo "ℹ Реестр проектов пропущен (SEO_CYCLE_SKIP_REGISTRY=1)"
elif [ -f "$REGISTRY" ]; then
    if grep -q "path: \"$PROJECT_PATH\"" "$REGISTRY" 2>/dev/null; then
        echo "ℹ Проект уже в реестре ($REGISTRY) — пропускаю"
    else
        cat >> "$REGISTRY" <<EOF
  - name: "$PROJECT_NAME"
    path: "$PROJECT_PATH"
    region_profile: $REGION_PROFILE
    cms: $CMS
    status: active
    monthly_automation: false
EOF
        echo "✓ Проект добавлен в реестр: $REGISTRY"
    fi
fi

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✓ Создан $TARGET"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Следующие шаги:"
echo "  1. Открой $TARGET и доуточни секции (sources, content_rules, publishing)"
echo "  2. Открой помощник обновления, если проект создавался старой версией:"
echo "     seo/setup/upgrade-assistant.md"
echo "     seo/setup/upgrade-questionnaire.csv"
echo "     # обновить: python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write"
echo "  3. Проверь, какие ключи/токены реально нужны этому проекту:"
echo "     seo/setup/access-key-assistant.md"
echo "     seo/setup/access-key-assistant.csv"
echo "     # обновить: python3 ./.codex/skills/seo-cycle/scripts/access-key-assistant.py --write"
echo "  4. Заполни .env только нужными API ключами (см. docs/oauth-setup.md в скилле)"
echo "     # Codex: SEO_RUNTIME=codex, SEO_SEARCH_RUNTIME=direct"
echo "     # Claude: SEO_RUNTIME=claude, SEO_SEARCH_RUNTIME=codex_external"
echo "     # WordPress MCP/Novomira: WP_API_URL, WP_API_USERNAME, WP_API_PASSWORD"
echo "  5. Проверь project-local MCP config для Codex:"
echo "     .codex/config.toml"
echo "     # обновить: python3 ./.codex/skills/seo-cycle/scripts/project-mcp-config.py --write"
echo "  6. Обнови policy-файлы в seo/ при подключении NeuronWriter, Google NLP, GSC/Яндекс/Бинг и автоматизаций"
echo "  7. Запусти валидатор:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/validate-config.py"
echo "  8. Открой короткий context pack — первый файл для Claude/Codex:"
echo "     seo/setup/context-pack.md"
echo "     # обновить под задачу: python3 ./.codex/skills/seo-cycle/scripts/context-pack.py --task \"аудит индексации и robots\" --write"
echo "  9. Открой setup blueprint — матрица стран/регионов/поисковиков/бизнеса/ads/tools/budget/automation:"
echo "     seo/setup/setup-blueprint.md"
echo "     seo/setup/setup-matrix.csv"
echo "     # обновить: python3 ./.codex/skills/seo-cycle/scripts/setup-blueprint.py --write"
echo "  10. Открой единый setup report:"
echo "     seo/setup/setup-control-plane.md"
echo "     # обновить: python3 ./.codex/skills/seo-cycle/scripts/setup-control-plane.py --write"
echo "  11. Открой вопросы по недонастроенным деталям проекта:"
echo "     seo/setup/setup-gap-audit.md"
echo "     seo/setup/setup-questionnaire.csv"
echo "     # обновить: python3 ./.codex/skills/seo-cycle/scripts/setup-gap-audit.py --write"
echo "     # после заполнения CSV: python3 ./.codex/skills/seo-cycle/scripts/setup-answer-plan.py --write"
echo "  12. Открой компактный launch contract:"
echo "     seo/setup/launch-plan.md"
echo "     # обновить: python3 ./.codex/skills/seo-cycle/scripts/launch-plan.py --write"
echo "  13. Открой spend/subscription guard:"
echo "     seo/setup/spend-guard.md"
echo "     # обновить: python3 ./.codex/skills/seo-cycle/scripts/spend-guard.py --write"
echo "  14. При необходимости доуточни подробный intake:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write"
echo "  15. Примени или обнови точечный project profile:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/project-profile.py --write"
echo "     # после проверки: python3 ./.codex/skills/seo-cycle/scripts/project-profile.py --apply"
echo "  16. Посмотри governance report:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/governance-report.py --format md"
echo "  17. Перед конкретной задачей построй low-token task route:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/task-router.py --task \"аудит индексации и robots\" --write"
echo "     # результат: seo/setup/latest-task-route.md"
echo "  18. Проверь/запиши расход токенов и платных инструментов:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/usage-ledger.py report --write"
echo "     python3 ./.codex/skills/seo-cycle/scripts/usage-ledger.py check --service openai --category llm --usd 0.25 --fail-on-block"
echo "  19. Сгенерируй и проверь рекомендации автоматизаций:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/automation-recommender.py --write"
echo "     # после review: python3 ./.codex/skills/seo-cycle/scripts/automation-recommender.py --apply"
echo "  20. Проверь рекомендуемый stack инструментов/доступов:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write"
echo "     # после review: python3 ./.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --apply"
echo "  21. Построй приоритетный growth roadmap:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/growth-roadmap.py --write"
echo "     # результат: seo/setup/growth-roadmap.md"
echo "  22. Собери подробный onboarding playbook:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/setup-onboarding.py --write"
echo "     # результат: seo/setup/onboarding-playbook.md + onboarding-checklist.csv"
echo "  23. Создай безопасный план автоматизаций:"
echo "     python3 ./.codex/skills/seo-cycle/scripts/automation-plan.py --write --include-disabled"
echo "  24. В Claude Code/Codex: «давай запустим SEO-цикл для категории X»"
echo ""

# Сразу прогоняем валидатор
read_answer runval "Запустить validate-config.py сейчас? [Y/n]: " ""
case "$runval" in
    n|N|no|NO) echo "Пропущено." ;;
    *) echo ""; python3 "$SKILL_ROOT/scripts/validate-config.py" "$TARGET" || true ;;
esac
