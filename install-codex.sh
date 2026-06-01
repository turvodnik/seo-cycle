#!/usr/bin/env bash
# install-codex.sh — установка seo-cycle для Codex (и Claude Code) одной командой.
#
#   curl -sL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/install-codex.sh | bash
#
# Делает (идемпотентно): clone/обновление ядра seo-cycle + seo-keywords, ставит
# зависимости, создаёт симлинк для Codex (~/.codex/skills), чинит AGENTS.md.
# Проектную настройку (init-project + AGENTS.md + .env) показывает как след. шаги —
# она интерактивна и делается в каталоге конкретного проекта.

set -e

SKILLS_DIR="$HOME/.claude/skills"
CORE="$SKILLS_DIR/seo-cycle"
REPO="https://github.com/turvodnik/seo-cycle"
KW_REPO="https://github.com/turvodnik/seo-keywords"

echo "════════════════════════════════════════════════"
echo "  seo-cycle install (Codex + Claude)"
echo "════════════════════════════════════════════════"

# 1. Ядро
mkdir -p "$SKILLS_DIR"
if [ -d "$CORE/.git" ]; then
    echo "▶ обновляю seo-cycle (git pull)..."
    git -C "$CORE" pull --quiet --ff-only 2>/dev/null || echo "  (есть локальные изменения — pull пропущен)"
else
    echo "▶ клонирую seo-cycle..."
    git clone --quiet "$REPO" "$CORE"
fi

# 2. seo-keywords (опциональный фазовый скилл)
if [ ! -d "$SKILLS_DIR/seo-keywords/.git" ]; then
    git clone --quiet "$KW_REPO" "$SKILLS_DIR/seo-keywords" 2>/dev/null \
        && echo "▶ seo-keywords установлен" || echo "  (seo-keywords пропущен — необязателен)"
fi

# 3. Зависимости Python
echo "▶ проверяю зависимости (pyyaml, requests)..."
if ! python3 -c "import yaml, requests" 2>/dev/null; then
    pip3 install --quiet pyyaml requests 2>/dev/null \
        || pip install --quiet pyyaml requests 2>/dev/null \
        || echo "  ⚠ установи вручную: pip3 install pyyaml requests"
fi

# 4. Точка входа для Codex
mkdir -p "$HOME/.codex/skills"
ln -sf "$CORE" "$HOME/.codex/skills/seo-cycle"
echo "▶ Codex: ~/.codex/skills/seo-cycle → $CORE"

# 5. AGENTS.md симлинк (если git не восстановил)
if [ ! -e "$CORE/AGENTS.md" ]; then
    ( cd "$CORE" && ln -sf SKILL.md AGENTS.md )
    echo "▶ восстановлен симлинк AGENTS.md → SKILL.md"
fi

echo ""
echo "✓ Ядро установлено: $CORE"
echo "  версия: $(cat "$CORE/VERSION" 2>/dev/null || echo '?')"
echo ""
echo "── Дальше в КОРНЕ твоего проекта: ──"
echo "  cd /путь/к/проекту"
echo "  $CORE/scripts/init-project.sh          # wizard → seo-cycle.yaml (выберет region_profile)"
echo "  ln -sf $CORE/AGENTS.md ./AGENTS.md      # точка входа Codex"
echo "  cp $CORE/.env.example .env             # заполнить API-ключи"
echo "  export SEO_RUNTIME=codex"
echo "  codex exec -c model_reasoning_effort=\"xhigh\" -c web_search=\"live\" \\"
echo "      \"Прочитай AGENTS.md и seo-cycle.yaml. Запусти SEO-цикл для категории X.\""
echo ""
echo "  Документация: $CORE/GUIDE.md · Codex-режим: $CORE/docs/codex-runtime.md"
