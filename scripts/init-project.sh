#!/bin/bash
# init-project.sh — интерактивный wizard для нового проекта seo-cycle.
#
# Задаёт базовые вопросы + блок image workflow → генерирует seo-cycle.yaml,
# .env.example, AGENTS.md и policy-шаблоны в текущей директории → запускает
# validate-config.py.
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
echo "Блок изображений для SEO-публикаций:"

read -p "8. Пропорция featured/hero изображений (default: 16:9): " IMAGE_FEATURED_RATIO
IMAGE_FEATURED_RATIO="${IMAGE_FEATURED_RATIO:-16:9}"

read -p "9. Пропорция inline изображений в статьях (default: 16:9): " IMAGE_INLINE_RATIO
IMAGE_INLINE_RATIO="${IMAGE_INLINE_RATIO:-16:9}"

read -p "10. Ширина WebP в px (default: 1200): " IMAGE_WIDTH
IMAGE_WIDTH="${IMAGE_WIDTH:-1200}"

read -p "11. WebP quality 1-100 (default: 86): " IMAGE_QUALITY
IMAGE_QUALITY="${IMAGE_QUALITY:-86}"

read -p "12. Источник фото [thematic_photos_first/product_photos_first/generate_if_missing/manual_only] (default: thematic_photos_first): " IMAGE_SOURCE_POLICY
IMAGE_SOURCE_POLICY="${IMAGE_SOURCE_POLICY:-thematic_photos_first}"

read -p "13. Визуальный стиль [clean_topical_photo/editorial_photo/product_context_photo] (default: clean_topical_photo): " IMAGE_VISUAL_STYLE
IMAGE_VISUAL_STYLE="${IMAGE_VISUAL_STYLE:-clean_topical_photo}"

read -p "14. Минимум inline-изображений на пост (default: 2): " IMAGE_INLINE_MIN
IMAGE_INLINE_MIN="${IMAGE_INLINE_MIN:-2}"

read -p "15. Caption под inline-картинками обязателен? [Y/n]: " IMAGE_CAPTIONS_ANSWER
case "$IMAGE_CAPTIONS_ANSWER" in
    n|N|no|NO) IMAGE_CAPTIONS_REQUIRED=false; IMAGE_CAPTION_MODE=none ;;
    *) IMAGE_CAPTIONS_REQUIRED=true; IMAGE_CAPTION_MODE=short_editorial ;;
esac

read -p "16. Разрешать видимый текст на изображениях? [y/N]: " IMAGE_TEXT_ANSWER
case "$IMAGE_TEXT_ANSWER" in
    y|Y|yes|YES) IMAGE_ALLOW_VISIBLE_TEXT=true ;;
    *) IMAGE_ALLOW_VISIBLE_TEXT=false ;;
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

# macOS / Linux compatible sed -i (GNU sed: -i; BSD sed: -i '')
if [ "$(uname)" = "Darwin" ]; then
    SED_I="sed -i ''"
else
    SED_I="sed -i"
fi

# Surgical замены — только в первой секции project: и locale:
$SED_I "s|name: \"Example Shop\"|name: \"$PROJECT_NAME\"|" "$TARGET"
$SED_I "s|domain: \"example.com\"|domain: \"$DOMAIN\"|" "$TARGET"
$SED_I "s|brand_name_user_facing: \"Example Shop\"|brand_name_user_facing: \"$BRAND_UF\"|" "$TARGET"
$SED_I "s|brand_name_technical: \"example\"|brand_name_technical: \"$BRAND_TECH\"|" "$TARGET"
$SED_I "s|^project_type: ecommerce|project_type: $PROJECT_TYPE|" "$TARGET"
$SED_I "s|^cms: wordpress|cms: $CMS|" "$TARGET"
$SED_I "s|  language: ru|  language: $LANG_CODE|" "$TARGET"
$SED_I "s|  country: RU|  country: $CTRY_CODE|" "$TARGET"
$SED_I "s|  region: \"Москва и Московская область\"|  region: \"$REGION_TEXT\"|" "$TARGET"
$SED_I "s|  city: \"Москва\"|  city: \"$CITY\"|" "$TARGET"
$SED_I "s|  locale_iso: ru-RU|  locale_iso: $LOCALE|" "$TARGET"
$SED_I "s|  yandex_region_code: 213|  yandex_region_code: $YANDEX_RC|" "$TARGET"
$SED_I "s|  google_gl: ru|  google_gl: $(echo $CTRY_CODE | tr A-Z a-z)|" "$TARGET"
$SED_I "s|  google_hl: ru|  google_hl: $LANG_CODE|" "$TARGET"
$SED_I "s|  timezone: \"Europe/Moscow\"|  timezone: \"$TZ\"|" "$TARGET"

# Image workflow defaults
$SED_I "s|  workflow: photo_first|  workflow: photo_first|" "$TARGET"
$SED_I "s|  source_policy: thematic_photos_first|  source_policy: $IMAGE_SOURCE_POLICY|" "$TARGET"
$SED_I "s|  visual_style: clean_topical_photo|  visual_style: $IMAGE_VISUAL_STYLE|" "$TARGET"
$SED_I "s|  allow_visible_text: false|  allow_visible_text: $IMAGE_ALLOW_VISIBLE_TEXT|" "$TARGET"
$SED_I "s|    width: 1200|    width: $IMAGE_WIDTH|" "$TARGET"
$SED_I "s|    quality: 86|    quality: $IMAGE_QUALITY|" "$TARGET"
$SED_I "s|    inline_required: true|    inline_required: $IMAGE_CAPTIONS_REQUIRED|" "$TARGET"
$SED_I "s|    mode: short_editorial|    mode: $IMAGE_CAPTION_MODE|" "$TARGET"
$SED_I "s|  inline_min_per_post: 2|  inline_min_per_post: $IMAGE_INLINE_MIN|" "$TARGET"
$SED_I "s|    featured: \"16:9\"|    featured: \"$IMAGE_FEATURED_RATIO\"|" "$TARGET"
$SED_I "s|    hero: \"16:9\"|    hero: \"$IMAGE_FEATURED_RATIO\"|" "$TARGET"
$SED_I "s|    article_inline: \"16:9\"|    article_inline: \"$IMAGE_INLINE_RATIO\"|" "$TARGET"

# Региональный профиль источников (управляет вкл/выкл Яндекс/Google/SaaS)
$SED_I "s|^region_profile: ru|region_profile: $REGION_PROFILE|" "$TARGET"
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
    $SED_I "s|__DATE__|$TODAY|g" "$dest"
    $SED_I "s|__PROJECT_NAME__|$PROJECT_NAME|g" "$dest"
    $SED_I "s|__DOMAIN__|$DOMAIN|g" "$dest"
    echo "✓ policy создан: $dest"
}

copy_policy_template "$POLICY_TEMPLATE_DIR/neuronwriter-limits.template.yaml" "seo/neuronwriter-limits.yaml"
copy_policy_template "$POLICY_TEMPLATE_DIR/google-nlp-policy.template.yaml" "seo/entities/google-nlp-policy.yaml"
copy_policy_template "$POLICY_TEMPLATE_DIR/seo-data-collection-map.template.md" "seo/seo-data-collection-map.md"
copy_policy_template "$POLICY_TEMPLATE_DIR/access-setup-runbook.template.md" "seo/access-setup-runbook.md"
copy_policy_template "$POLICY_TEMPLATE_DIR/ai-visibility-prompts.template.csv" "seo/ai-visibility-prompts.csv"

# Дозапись проекта в общий реестр (идемпотентно — по path)
REGISTRY="$SKILL_ROOT/config/projects-registry.yaml"
PROJECT_PATH="$(pwd)"
if [ -f "$REGISTRY" ]; then
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
echo "  2b. Обнови policy-файлы в seo/ при подключении NeuronWriter, Google NLP, GSC/Яндекс/Бинг"
echo "  3. Запусти валидатор:"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py"
echo "  4. В Claude Code/Codex: «давай запустим SEO-цикл для категории X»"
echo ""

# Сразу прогоняем валидатор
read -p "Запустить validate-config.py сейчас? [Y/n]: " runval
case "$runval" in
    n|N|no|NO) echo "Пропущено." ;;
    *) echo ""; python3 "$SKILL_ROOT/scripts/validate-config.py" "$TARGET" || true ;;
esac
