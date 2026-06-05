#!/usr/bin/env bash
# install-codex.sh — установка seo-cycle для Codex-first runtime одной командой.
#
#   curl -sL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/install-codex.sh | bash
#
# Делает (идемпотентно): clone/обновление ядра seo-cycle + seo-keywords в
# canonical Codex skills dir, ставит зависимости, создаёт совместимые симлинки
# для Claude Code и ~/.agents/skills, чинит AGENTS.md.
# Проектную настройку (init-project + AGENTS.md + .env) показывает как след. шаги —
# она интерактивна и делается в каталоге конкретного проекта.

set -euo pipefail

CODEX_SKILLS_DIR="$HOME/.codex/skills"
AGENTS_SKILLS_DIR="$HOME/.agents/skills"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CORE="$CODEX_SKILLS_DIR/seo-cycle"
KW_CORE="$CODEX_SKILLS_DIR/seo-keywords"
REPO="https://github.com/turvodnik/seo-cycle"
KW_REPO="https://github.com/turvodnik/seo-keywords"

echo "════════════════════════════════════════════════"
echo "  seo-cycle install (Codex-first)"
echo "════════════════════════════════════════════════"

# 1. Ядро
mkdir -p "$CODEX_SKILLS_DIR" "$AGENTS_SKILLS_DIR" "$CLAUDE_SKILLS_DIR"
if [ -L "$CORE" ]; then
    old_target="$(readlink "$CORE")"
    rm "$CORE"
    echo "▶ заменяю старый Codex symlink на canonical git checkout ($old_target сохранён отдельно)"
fi
if [ -d "$CORE/.git" ]; then
    echo "▶ обновляю seo-cycle (git pull)..."
    git -C "$CORE" pull --quiet --ff-only 2>/dev/null || echo "  (есть локальные изменения — pull пропущен)"
else
    if [ -e "$CORE" ]; then
        backup="${CORE}.backup.$(date +%Y%m%d-%H%M%S)"
        mv "$CORE" "$backup"
        echo "  (backup: $backup)"
    fi
    echo "▶ клонирую seo-cycle..."
    git clone --quiet "$REPO" "$CORE"
fi

# 2. seo-keywords (опциональный фазовый скилл)
if [ -L "$KW_CORE" ]; then
    rm "$KW_CORE"
fi
if [ ! -d "$KW_CORE/.git" ]; then
    if [ -e "$KW_CORE" ]; then
        backup="${KW_CORE}.backup.$(date +%Y%m%d-%H%M%S)"
        mv "$KW_CORE" "$backup"
        echo "  (backup: $backup)"
    fi
    git clone --quiet "$KW_REPO" "$KW_CORE" 2>/dev/null \
        && echo "▶ seo-keywords установлен" || echo "  (seo-keywords пропущен — необязателен)"
else
    git -C "$KW_CORE" pull --quiet --ff-only 2>/dev/null || true
fi

# 3. Зависимости Python
echo "▶ проверяю зависимости (pyyaml, requests, pillow, beautifulsoup4, google-auth)..."
if ! python3 -c "import yaml, requests, PIL, bs4; import google.auth, google.oauth2.service_account" 2>/dev/null; then
    pip3 install --quiet pyyaml requests pillow beautifulsoup4 google-auth 2>/dev/null \
        || pip install --quiet pyyaml requests pillow beautifulsoup4 google-auth 2>/dev/null \
        || echo "  ⚠ установи вручную: pip3 install pyyaml requests pillow beautifulsoup4 google-auth"
fi

replace_with_symlink() {
    local target="$1"
    local link="$2"
    if [ "$target" = "$link" ]; then
        return 0
    fi
    if [ -L "$link" ]; then
        rm "$link"
    elif [ -e "$link" ]; then
        local backup="${link}.backup.$(date +%Y%m%d-%H%M%S)"
        mv "$link" "$backup"
        echo "  (backup: $backup)"
    fi
    ln -s "$target" "$link"
}

# 4. Точки входа: Codex canonical + Claude/agents symlinks
echo "▶ Codex canonical: $CORE"

replace_with_symlink "$CORE" "$AGENTS_SKILLS_DIR/seo-cycle"
echo "▶ Agents: ~/.agents/skills/seo-cycle → $CORE"

replace_with_symlink "$CORE" "$CLAUDE_SKILLS_DIR/seo-cycle"
echo "▶ Claude: ~/.claude/skills/seo-cycle → $CORE"

if [ -d "$KW_CORE" ]; then
    replace_with_symlink "$KW_CORE" "$AGENTS_SKILLS_DIR/seo-keywords"
    replace_with_symlink "$KW_CORE" "$CLAUDE_SKILLS_DIR/seo-keywords"
    echo "▶ seo-keywords canonical: $KW_CORE"
fi

# 5. Codex-first entrypoint skill
if [ -d "$CORE/codex-primary-runtime" ]; then
    replace_with_symlink "$CORE/codex-primary-runtime" "$CODEX_SKILLS_DIR/codex-primary-runtime"
    replace_with_symlink "$CORE/codex-primary-runtime" "$AGENTS_SKILLS_DIR/codex-primary-runtime"
    replace_with_symlink "$CORE/codex-primary-runtime" "$CLAUDE_SKILLS_DIR/codex-primary-runtime"
    echo "▶ codex-primary-runtime → $CORE/codex-primary-runtime"
fi

# 6. AGENTS.md симлинк (если git не восстановил)
if [ ! -e "$CORE/AGENTS.md" ]; then
    ( cd "$CORE" && ln -sf SKILL.md AGENTS.md )
    echo "▶ восстановлен симлинк AGENTS.md → SKILL.md"
fi

echo ""
echo "✓ Ядро установлено в canonical Codex path: $CORE"
echo "  версия: $(cat "$CORE/VERSION" 2>/dev/null || echo '?')"
echo ""
echo "── Дальше в КОРНЕ твоего проекта: ──"
echo "  cd /путь/к/проекту"
echo "  curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash"
echo "  # или вручную: $CORE/scripts/init-project.sh"
echo "  # wizard создаст AGENTS.md → $CORE/AGENTS.md, если AGENTS.md ещё нет"
echo "  cp .env.example .env                   # если bootstrap не сделал это сам"
echo "  export SEO_RUNTIME=codex"
echo "  codex exec -c model_reasoning_effort=\"xhigh\" -c web_search=\"live\" \\"
echo "      \"Прочитай AGENTS.md и seo-cycle.yaml. Запусти SEO-цикл для категории X.\""
echo ""
echo "  Документация: $CORE/GUIDE.md · Codex-режим: $CORE/docs/codex-runtime.md"
