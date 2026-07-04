#!/usr/bin/env bash
# install-codex.sh — update shared seo-cycle vendor core.
#
#   curl -sL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/install-codex.sh | bash
#
# Default behavior:
# - installs/updates shared code in ~/.codex/vendor/seo-cycle
# - installs/updates optional shared seo-keywords in ~/.codex/vendor/seo-keywords
# - does NOT expose seo-cycle as a global skill
#
# Project bootstrap creates local skill entrypoints only inside projects where
# seo-cycle is installed. This keeps unrelated projects from loading seo-cycle.

set -euo pipefail

SHARED_DIR="${SEO_CYCLE_SHARED_DIR:-$HOME/.codex/vendor}"
CORE="${SEO_CYCLE_CORE:-$SHARED_DIR/seo-cycle}"
KW_CORE="${SEO_KEYWORDS_CORE:-$SHARED_DIR/seo-keywords}"
REPO="${SEO_CYCLE_REPO:-https://github.com/turvodnik/seo-cycle}"
KW_REPO="${SEO_KEYWORDS_REPO:-https://github.com/turvodnik/seo-keywords}"
LEGACY_GLOBAL_SKILL=0
MIGRATE_OLD_GLOBAL=1

usage() {
    cat <<'EOF'
seo-cycle shared installer

Usage:
  install-codex.sh [--global-skill] [--no-migrate-old-global]

Options:
  --global-skill           Legacy mode: also link seo-cycle into global skill roots.
                           This makes it visible in every project, so avoid it by default.
  --no-migrate-old-global  Do not move old ~/.codex/skills/seo-cycle checkout to vendor.
  -h, --help               Show help.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --global-skill)
            LEGACY_GLOBAL_SKILL=1
            shift
            ;;
        --no-migrate-old-global)
            MIGRATE_OLD_GLOBAL=0
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

echo "════════════════════════════════════════════════"
echo "  seo-cycle shared install (Codex-first)"
echo "════════════════════════════════════════════════"

install_or_update_repo() {
    local repo="$1"
    local dest="$2"
    local label="$3"
    mkdir -p "$(dirname "$dest")"
    if [ -L "$dest" ]; then
        rm "$dest"
    fi
    if [ -d "$dest/.git" ]; then
        echo "▶ обновляю $label..."
        git -C "$dest" pull --quiet --ff-only 2>/dev/null || echo "  (есть локальные изменения — pull пропущен)"
    else
        if [ -e "$dest" ]; then
            local backup="${dest}.backup.$(date +%Y%m%d-%H%M%S)"
            mv "$dest" "$backup"
            echo "  (backup: $backup)"
        fi
        echo "▶ клонирую $label..."
        git clone --quiet "$repo" "$dest"
    fi
}

install_or_update_optional_repo() {
    local repo="$1"
    local dest="$2"
    local label="$3"
    mkdir -p "$(dirname "$dest")"
    if [ -L "$dest" ]; then
        rm "$dest"
    fi
    if [ -d "$dest/.git" ]; then
        git -C "$dest" pull --quiet --ff-only 2>/dev/null || true
    elif git clone --quiet "$repo" "$dest" 2>/dev/null; then
        echo "▶ $label установлен"
    else
        echo "  ($label пропущен — необязателен)"
    fi
}

replace_with_symlink() {
    local target="$1"
    local link="$2"
    mkdir -p "$(dirname "$link")"
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

migrate_old_global_checkout() {
    local old="$HOME/.codex/skills/seo-cycle"
    local old_kw="$HOME/.codex/skills/seo-keywords"
    if [ "$MIGRATE_OLD_GLOBAL" != "1" ]; then
        return 0
    fi
    mkdir -p "$SHARED_DIR"
    if [ "$old" != "$CORE" ] && [ -d "$old/.git" ] && [ ! -e "$CORE" ]; then
        echo "▶ переношу старый global skill checkout в shared vendor..."
        mv "$old" "$CORE"
    elif [ "$old" != "$CORE" ] && [ -L "$old" ] && [ "$(readlink "$old")" = "$CORE" ] && [ "$LEGACY_GLOBAL_SKILL" != "1" ]; then
        rm "$old"
    fi
    if [ "$old_kw" != "$KW_CORE" ] && [ -d "$old_kw/.git" ] && [ ! -e "$KW_CORE" ]; then
        echo "▶ переношу старый seo-keywords checkout в shared vendor..."
        mv "$old_kw" "$KW_CORE"
    elif [ "$old_kw" != "$KW_CORE" ] && [ -L "$old_kw" ] && [ "$(readlink "$old_kw")" = "$KW_CORE" ] && [ "$LEGACY_GLOBAL_SKILL" != "1" ]; then
        rm "$old_kw"
    fi
}

remove_global_skill_link() {
    local link="$1"
    if [ -L "$link" ]; then
        rm "$link"
    fi
}

cleanup_legacy_global_links() {
    if [ "$LEGACY_GLOBAL_SKILL" = "1" ]; then
        return 0
    fi
    remove_global_skill_link "$HOME/.codex/skills/seo-cycle"
    remove_global_skill_link "$HOME/.agents/skills/seo-cycle"
    remove_global_skill_link "$HOME/.claude/skills/seo-cycle"
    remove_global_skill_link "$HOME/.codex/skills/seo-keywords"
    remove_global_skill_link "$HOME/.agents/skills/seo-keywords"
    remove_global_skill_link "$HOME/.claude/skills/seo-keywords"
    remove_global_skill_link "$HOME/.codex/skills/codex-primary-runtime"
    remove_global_skill_link "$HOME/.agents/skills/codex-primary-runtime"
    remove_global_skill_link "$HOME/.claude/skills/codex-primary-runtime"
}

migrate_old_global_checkout

install_or_update_repo "$REPO" "$CORE" "seo-cycle shared vendor core"
install_or_update_optional_repo "$KW_REPO" "$KW_CORE" "seo-keywords shared vendor"

echo "▶ проверяю зависимости (pyyaml, requests, pillow, beautifulsoup4, google-auth)..."
if ! python3 -c "import yaml, requests, PIL, bs4; import google.auth, google.oauth2.service_account" 2>/dev/null; then
    pip3 install --quiet pyyaml requests pillow beautifulsoup4 google-auth 2>/dev/null \
        || pip install --quiet pyyaml requests pillow beautifulsoup4 google-auth 2>/dev/null \
        || echo "  ⚠ установи вручную: pip3 install pyyaml requests pillow beautifulsoup4 google-auth"
fi

if [ ! -e "$CORE/AGENTS.md" ]; then
    ( cd "$CORE" && ln -sf SKILL.md AGENTS.md )
    echo "▶ восстановлен симлинк AGENTS.md → SKILL.md"
fi

cleanup_legacy_global_links

# Unified CLI: expose `seo-cycle` in ~/.local/bin (no shell rc edits).
if [ -f "$CORE/bin/seo-cycle" ]; then
    mkdir -p "$HOME/.local/bin"
    chmod +x "$CORE/bin/seo-cycle" 2>/dev/null || true
    ln -sf "$CORE/bin/seo-cycle" "$HOME/.local/bin/seo-cycle"
    echo "✓ CLI: ~/.local/bin/seo-cycle → $CORE/bin/seo-cycle"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) echo "  ⚠ ~/.local/bin не в PATH. Добавь в свой shell rc: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac
fi

if [ "$LEGACY_GLOBAL_SKILL" = "1" ]; then
    replace_with_symlink "$CORE" "$HOME/.codex/skills/seo-cycle"
    replace_with_symlink "$CORE" "$HOME/.agents/skills/seo-cycle"
    replace_with_symlink "$CORE" "$HOME/.claude/skills/seo-cycle"
    if [ -d "$KW_CORE" ]; then
        replace_with_symlink "$KW_CORE" "$HOME/.codex/skills/seo-keywords"
        replace_with_symlink "$KW_CORE" "$HOME/.agents/skills/seo-keywords"
        replace_with_symlink "$KW_CORE" "$HOME/.claude/skills/seo-keywords"
    fi
    if [ -d "$CORE/codex-primary-runtime" ]; then
        replace_with_symlink "$CORE/codex-primary-runtime" "$HOME/.codex/skills/codex-primary-runtime"
        replace_with_symlink "$CORE/codex-primary-runtime" "$HOME/.agents/skills/codex-primary-runtime"
        replace_with_symlink "$CORE/codex-primary-runtime" "$HOME/.claude/skills/codex-primary-runtime"
    fi
    echo "⚠ legacy global skill links enabled: seo-cycle is visible in every project"
fi

echo ""
echo "✓ Shared seo-cycle core: $CORE"
echo "  version: $(cat "$CORE/VERSION" 2>/dev/null || echo '?')"
echo ""
echo "Project install:"
echo "  cd /path/to/project"
echo "  curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash"
echo ""
echo "Project-local files after bootstrap:"
echo "  .codex/skills/seo-cycle -> $CORE"
echo "  .agents/skills/seo-cycle -> .codex/skills/seo-cycle"
echo "  .claude/skills/seo-cycle -> .codex/skills/seo-cycle"
echo "  .codex/config.toml      # project MCP wrapper"
echo "  .env                    # project secrets"
echo "  seo/project-rules.md    # project-only overrides"
