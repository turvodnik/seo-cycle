#!/usr/bin/env bash
# bootstrap-claude.sh — one-command seo-cycle bootstrap for a Claude Code project.
#
# Run from a new project root:
#   curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-claude.sh | bash

set -euo pipefail

RAW_BASE="${SEO_CYCLE_RAW_BASE:-https://raw.githubusercontent.com/turvodnik/seo-cycle/main}"
CORE="${SEO_CYCLE_CORE:-$HOME/.codex/skills/seo-cycle}"
PROJECT_DIR="$PWD"
RUN_INIT=1
REGISTER=0
START_CLAUDE=0

usage() {
    cat <<'EOF'
seo-cycle Claude bootstrap

Usage:
  bootstrap-claude.sh [--project DIR] [--skip-init] [--register] [--start-claude]

Options:
  --project DIR     Project root to initialize. Default: current directory.
  --skip-init       Install/update global seo-cycle only; do not run project wizard.
  --register        Allow init-project.sh to add this project to the global registry.
  --start-claude    After setup, run a first Claude prompt if the `claude` CLI exists.
  -h, --help        Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --project)
            PROJECT_DIR="${2:?--project requires a directory}"
            shift 2
            ;;
        --skip-init)
            RUN_INIT=0
            shift
            ;;
        --register)
            REGISTER=1
            shift
            ;;
        --start-claude)
            START_CLAUDE=1
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

abs_path() {
    mkdir -p "$1"
    (cd "$1" && pwd)
}

ensure_env_file() {
    local project_dir="$1"
    if [ -f "$project_dir/.env.example" ] && [ ! -f "$project_dir/.env" ]; then
        cp "$project_dir/.env.example" "$project_dir/.env"
        echo "✓ .env создан из .env.example"
    fi
    if [ -f "$project_dir/.env" ] && ! grep -q '^SEO_RUNTIME=' "$project_dir/.env" 2>/dev/null; then
        printf '\n# seo-cycle runtime\nSEO_RUNTIME=claude\n' >> "$project_dir/.env"
        echo "✓ .env: SEO_RUNTIME=claude"
    fi
    if [ ! -f "$project_dir/.gitignore" ]; then
        printf ".env\n" > "$project_dir/.gitignore"
        echo "✓ .gitignore создан с .env"
    elif ! grep -qxF ".env" "$project_dir/.gitignore" 2>/dev/null; then
        printf "\n.env\n" >> "$project_dir/.gitignore"
        echo "✓ .gitignore: добавлен .env"
    fi
}

ensure_claude_entrypoint() {
    local project_dir="$1"
    if [ ! -e "$project_dir/CLAUDE.md" ]; then
        ln -s "$CORE/SKILL.md" "$project_dir/CLAUDE.md"
        echo "✓ CLAUDE.md → $CORE/SKILL.md"
    else
        echo "ℹ CLAUDE.md уже существует — не трогаю"
    fi
}

echo "════════════════════════════════════════════════"
echo "  seo-cycle Claude bootstrap"
echo "════════════════════════════════════════════════"

if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$RAW_BASE/install-codex.sh" | bash
elif [ -x "$CORE/install-codex.sh" ]; then
    bash "$CORE/install-codex.sh"
else
    echo "ERROR: curl is required to install seo-cycle" >&2
    exit 2
fi

PROJECT_DIR="$(abs_path "$PROJECT_DIR")"
echo ""
echo "✓ Ядро установлено в canonical Codex path: $CORE"
echo "  версия: $(cat "$CORE/VERSION" 2>/dev/null || echo '?')"
echo "▶ Project root: $PROJECT_DIR"

if [ "$RUN_INIT" = "1" ]; then
    cd "$PROJECT_DIR"
    export SEO_RUNTIME=claude
    if [ "$REGISTER" = "1" ]; then
        unset SEO_CYCLE_SKIP_REGISTRY
    else
        export SEO_CYCLE_SKIP_REGISTRY="${SEO_CYCLE_SKIP_REGISTRY:-1}"
    fi
    "$CORE/scripts/init-project.sh"
    ensure_claude_entrypoint "$PROJECT_DIR"
    ensure_env_file "$PROJECT_DIR"
fi

echo ""
echo "════════════════════════════════════════════════"
echo "  ✓ Claude bootstrap finished"
echo "════════════════════════════════════════════════"
echo "Core: $CORE"
echo "Project: $PROJECT_DIR"
echo ""
echo "Next Claude command:"
echo "  cd \"$PROJECT_DIR\""
echo "  export SEO_RUNTIME=claude"
echo "  claude \"Прочитай CLAUDE.md, seo-cycle.yaml и seo/setup/context-pack.md. Подготовь первый SEO-план проекта.\""

if [ "$START_CLAUDE" = "1" ]; then
    if command -v claude >/dev/null 2>&1; then
        cd "$PROJECT_DIR"
        export SEO_RUNTIME=claude
        claude "Прочитай CLAUDE.md, seo-cycle.yaml и seo/setup/context-pack.md. Подготовь первый SEO-план проекта."
    else
        echo "⚠ claude CLI не найден, автозапуск пропущен."
    fi
fi
