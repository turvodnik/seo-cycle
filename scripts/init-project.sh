#!/bin/bash
# init-project.sh — интерактивный wizard для нового проекта seo-cycle.
#
# Задаёт 7 базовых вопросов → генерирует seo-cycle.yaml и .env.example
# в текущей директории → запускает validate-config.py.
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

echo "Отвечай на 7 вопросов (Enter — взять default в скобках):"
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

# Региональный профиль источников (управляет вкл/выкл Яндекс/Google/SaaS)
$SED_I "s|^region_profile: ru|region_profile: $REGION_PROFILE|" "$TARGET"
echo "ℹ region_profile: $REGION_PROFILE (для $CTRY_CODE) — источники развернутся через resolve-sources.py"

# Копируем .env.example если есть
if [ -f "$ENV_TEMPLATE" ] && [ ! -f "$TARGET_ENV" ]; then
    cp "$ENV_TEMPLATE" "$TARGET_ENV"
    echo "✓ $TARGET_ENV скопирован (заполни перед использованием API-источников)"
fi

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
echo "  3. Запусти валидатор:"
echo "     python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py"
echo "  4. В Claude Code: «давай запустим SEO-цикл для категории X»"
echo ""

# Сразу прогоняем валидатор
read -p "Запустить validate-config.py сейчас? [Y/n]: " runval
case "$runval" in
    n|N|no|NO) echo "Пропущено." ;;
    *) echo ""; python3 "$SKILL_ROOT/scripts/validate-config.py" "$TARGET" || true ;;
esac
