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
#   ~/.claude/skills/seo-cycle/scripts/init-project.sh

set -e

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$SKILL_ROOT/config/project.template.yaml"
ENV_TEMPLATE="$SKILL_ROOT/.env.example"
POLICY_TEMPLATE_DIR="$SKILL_ROOT/templates/project-policies"
TARGET="seo-cycle.yaml"
TARGET_ENV=".env.example"

echo "════════════════════════════════════════════════════════════"
echo "  seo-cycle init wizard"
echo "════════════════════════════════════════════════════════════"
echo ""

# Проверка идемпотентности
if [ -f "$TARGET" ]; then
    echo "⚠  $TARGET уже существует."
    read -p "Перезаписать? [y/N]: " overwrite
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

read -p "1. Имя проекта (human-readable, например «Эмвуди»): " PROJECT_NAME
PROJECT_NAME="${PROJECT_NAME:-MyProject}"

read -p "2. Домен (без https://, например example.com): " DOMAIN
DOMAIN="${DOMAIN:-example.com}"

read -p "3. Brand name в user-facing текстах [$PROJECT_NAME]: " BRAND_UF
BRAND_UF="${BRAND_UF:-$PROJECT_NAME}"

read -p "4. Brand technical slug (для URL/кода, латиница) [$(echo "$DOMAIN" | cut -d. -f1)]: " BRAND_TECH
BRAND_TECH="${BRAND_TECH:-$(echo "$DOMAIN" | cut -d. -f1)}"

read -p "5. project_type [ecommerce/blog/saas/local_business/corporate/media/portfolio] (default: ecommerce): " PROJECT_TYPE
PROJECT_TYPE="${PROJECT_TYPE:-ecommerce}"

read -p "6. CMS [wordpress/shopify/webflow/nextjs/static/custom] (default: wordpress): " CMS
CMS="${CMS:-wordpress}"

read -p "7. Язык/Регион [ru-RU/en-US/en-GB/de-DE] (default: ru-RU): " LOCALE
LOCALE="${LOCALE:-ru-RU}"

echo ""
echo "Блок управления бюджетами и автоматизациями:"

read -p "8. Governance profile [lean_quality/balanced_growth/aggressive_growth/custom] (default: lean_quality): " GOVERNANCE_PROFILE
GOVERNANCE_PROFILE="${GOVERNANCE_PROFILE:-lean_quality}"

read -p "9. Monthly paid API budget USD (0 = без платных расходов, default: 0): " PAID_API_BUDGET
PAID_API_BUDGET="${PAID_API_BUDGET:-0}"

read -p "10. Monthly LLM/token budget USD (0 = без отдельного бюджета, default: 0): " LLM_BUDGET
LLM_BUDGET="${LLM_BUDGET:-0}"

read -p "11. Automation mode [disabled/report_only/approval_only/auto_with_caps] (default: approval_only): " AUTOMATION_MODE
AUTOMATION_MODE="${AUTOMATION_MODE:-approval_only}"

read -p "12. Создавать scheduled automations сейчас? [y/N]: " CREATE_SCHEDULES_ANSWER
case "$CREATE_SCHEDULES_ANSWER" in
    y|Y|yes|YES) CREATE_SCHEDULES=true ;;
    *) CREATE_SCHEDULES=false ;;
esac

echo ""
echo "Блок изображений для SEO-публикаций:"

read -p "13. Пропорция featured/hero изображений (default: 16:9): " IMAGE_FEATURED_RATIO
IMAGE_FEATURED_RATIO="${IMAGE_FEATURED_RATIO:-16:9}"

read -p "14. Пропорция inline изображений в статьях (default: 16:9): " IMAGE_INLINE_RATIO
IMAGE_INLINE_RATIO="${IMAGE_INLINE_RATIO:-16:9}"

read -p "15. Ширина WebP в px (default: 1200): " IMAGE_WIDTH
IMAGE_WIDTH="${IMAGE_WIDTH:-1200}"

read -p "16. WebP quality 1-100 (default: 86): " IMAGE_QUALITY
IMAGE_QUALITY="${IMAGE_QUALITY:-86}"

read -p "17. Источник фото [thematic_photos_first/product_photos_first/generate_if_missing/manual_only] (default: thematic_photos_first): " IMAGE_SOURCE_POLICY
IMAGE_SOURCE_POLICY="${IMAGE_SOURCE_POLICY:-thematic_photos_first}"

read -p "18. Визуальный стиль [clean_topical_photo/editorial_photo/product_context_photo] (default: clean_topical_photo): " IMAGE_VISUAL_STYLE
IMAGE_VISUAL_STYLE="${IMAGE_VISUAL_STYLE:-clean_topical_photo}"

read -p "19. Минимум inline-изображений на пост (default: 2): " IMAGE_INLINE_MIN
IMAGE_INLINE_MIN="${IMAGE_INLINE_MIN:-2}"

read -p "20. Caption под inline-картинками обязателен? [Y/n]: " IMAGE_CAPTIONS_ANSWER
case "$IMAGE_CAPTIONS_ANSWER" in
    n|N|no|NO) IMAGE_CAPTIONS_REQUIRED=false; IMAGE_CAPTION_MODE=none ;;
    *) IMAGE_CAPTIONS_REQUIRED=true; IMAGE_CAPTION_MODE=short_editorial ;;
esac

read -p "21. Разрешать видимый текст на изображениях? [y/N]: " IMAGE_TEXT_ANSWER
case "$IMAGE_TEXT_ANSWER" in
    y|Y|yes|YES) IMAGE_ALLOW_VISIBLE_TEXT=true ;;
    *) IMAGE_ALLOW_VISIBLE_TEXT=false ;;
esac

echo ""
echo "Детальный project intake:"
read -p "22. Запустить подробный wizard стран/движков/маркетинга/tools сейчас? [y/N]: " DETAILED_INTAKE_ANSWER
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
    read -p "23. Применить generated project profile к $TARGET сейчас? [y/N]: " APPLY_PROFILE_ANSWER
    case "$APPLY_PROFILE_ANSWER" in
        y|Y|yes|YES)
            python3 "$SKILL_ROOT/scripts/project-profile.py" "$TARGET" --apply \
                && echo "✓ project profile применён к $TARGET (backup создан рядом)"
            ;;
        *) echo "ℹ project profile не применён — после review запусти scripts/project-profile.py --apply" ;;
    esac
fi

python3 "$SKILL_ROOT/scripts/setup-control-plane.py" "$TARGET" --write --skip-intake >/dev/null 2>&1 \
    && echo "✓ setup control plane создан: setup/task-route/usage-ledger отчёты в seo/setup/" \
    || echo "ℹ setup control plane не создан — запусти scripts/setup-control-plane.py --write"

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
echo "  2. Заполни .env с API ключами (см. docs/oauth-setup.md в скилле)"
echo "  2b. Обнови policy-файлы в seo/ при подключении NeuronWriter, Google NLP, GSC/Яндекс/Бинг и автоматизаций"
echo "  3. Запусти валидатор:"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py"
echo "  4. Открой единый setup report:"
echo "     seo/setup/setup-control-plane.md"
echo "     # обновить: python3 ~/.claude/skills/seo-cycle/scripts/setup-control-plane.py --write"
echo "  5. При необходимости доуточни подробный intake:"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write"
echo "  6. Примени или обнови точечный project profile:"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/project-profile.py --write"
echo "     # после проверки: python3 ~/.claude/skills/seo-cycle/scripts/project-profile.py --apply"
echo "  7. Посмотри governance report:"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/governance-report.py --format md"
echo "  8. Перед конкретной задачей построй low-token task route:"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/task-router.py --task \"аудит индексации и robots\" --write"
echo "     # результат: seo/setup/latest-task-route.md"
echo "  9. Проверь/запиши расход токенов и платных инструментов:"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/usage-ledger.py report --write"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/usage-ledger.py check --service openai --category llm --usd 0.25 --fail-on-block"
echo "  10. Создай безопасный план автоматизаций:"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/automation-plan.py --write --include-disabled"
echo "  11. В Claude Code/Codex: «давай запустим SEO-цикл для категории X»"
echo ""

# Сразу прогоняем валидатор
read -p "Запустить validate-config.py сейчас? [Y/n]: " runval
case "$runval" in
    n|N|no|NO) echo "Пропущено." ;;
    *) echo ""; python3 "$SKILL_ROOT/scripts/validate-config.py" "$TARGET" || true ;;
esac
