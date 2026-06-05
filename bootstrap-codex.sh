#!/usr/bin/env bash
# bootstrap-codex.sh — one-command seo-cycle bootstrap for a Codex project.
#
# Run from a new project root:
#   curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash
#
# Or pass a project directory:
#   curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash -s -- --project /path/to/project

set -euo pipefail

RAW_BASE="${SEO_CYCLE_RAW_BASE:-https://raw.githubusercontent.com/turvodnik/seo-cycle/main}"
CORE="${SEO_CYCLE_CORE:-$HOME/.codex/skills/seo-cycle}"
PROJECT_DIR="$PWD"
RUN_INIT=1
REGISTER=0
START_CODEX=0

usage() {
    cat <<'EOF'
seo-cycle Codex bootstrap

Usage:
  bootstrap-codex.sh [--project DIR] [--skip-init] [--register] [--start-codex]

Options:
  --project DIR    Project root to initialize. Default: current directory.
  --skip-init      Install/update global seo-cycle only; do not run project wizard.
  --register       Allow init-project.sh to add this project to the global registry.
  --start-codex    After setup, run a first Codex prompt if the `codex` CLI exists.
  -h, --help       Show this help.
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
        --start-codex)
            START_CODEX=1
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
    if [ ! -f "$project_dir/.env.example" ] && [ -f "$CORE/.env.example" ]; then
        cp "$CORE/.env.example" "$project_dir/.env.example"
        echo "✓ .env.example создан из core template"
    fi
    if [ -f "$project_dir/.env.example" ] && [ ! -f "$project_dir/.env" ]; then
        cp "$project_dir/.env.example" "$project_dir/.env"
        echo "✓ .env создан из .env.example"
    fi
    if [ -f "$project_dir/.env" ] && ! grep -q '^SEO_RUNTIME=' "$project_dir/.env" 2>/dev/null; then
        printf '\n# seo-cycle runtime\nSEO_RUNTIME=codex\n' >> "$project_dir/.env"
        echo "✓ .env: SEO_RUNTIME=codex"
    fi
    if [ -f "$project_dir/.env" ] && ! grep -q '^SEO_SEARCH_RUNTIME=' "$project_dir/.env" 2>/dev/null; then
        printf 'SEO_SEARCH_RUNTIME=direct\n' >> "$project_dir/.env"
        echo "✓ .env: SEO_SEARCH_RUNTIME=direct"
    fi
    if [ ! -f "$project_dir/.gitignore" ]; then
        printf ".env\n" > "$project_dir/.gitignore"
        echo "✓ .gitignore создан с .env"
    elif ! grep -qxF ".env" "$project_dir/.gitignore" 2>/dev/null; then
        printf "\n.env\n" >> "$project_dir/.gitignore"
        echo "✓ .gitignore: добавлен .env"
    fi
}

find_project_config() {
    local project_dir="$1"
    local rel
    for rel in seo-cycle.yaml .seo-cycle.yaml seo/seo-cycle.yaml .claude/seo-cycle.yaml; do
        if [ -f "$project_dir/$rel" ]; then
            printf "%s\n" "$project_dir/$rel"
            return 0
        fi
    done
    return 1
}

ensure_codex_entrypoint() {
    local project_dir="$1"
    if [ ! -e "$project_dir/AGENTS.md" ]; then
        ln -s "$CORE/AGENTS.md" "$project_dir/AGENTS.md"
        echo "✓ AGENTS.md → $CORE/AGENTS.md"
    else
        echo "ℹ AGENTS.md уже существует — не трогаю"
    fi
}

run_existing_project_upgrade() {
    local project_dir="$1"
    local cfg_path="$2"
    echo "▶ existing seo-cycle project detected: $cfg_path"
    echo "▶ running upgrade/access/control-plane assistants instead of overwriting config..."
    python3 "$CORE/scripts/project-upgrade-assistant.py" "$cfg_path" --write \
        || echo "ℹ project-upgrade-assistant failed; run it manually after checking config"
    python3 "$CORE/scripts/access-key-assistant.py" "$cfg_path" --write \
        || echo "ℹ access-key-assistant failed; run it manually after checking tool stack"
    python3 "$CORE/scripts/setup-control-plane.py" "$cfg_path" --write --skip-intake \
        || echo "ℹ setup-control-plane reported validation/setup issues; open seo/setup/setup-control-plane.md"
}

echo "════════════════════════════════════════════════"
echo "  seo-cycle Codex bootstrap"
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
echo "▶ Project root: $PROJECT_DIR"

if [ "$RUN_INIT" = "1" ]; then
    cd "$PROJECT_DIR"
    export SEO_RUNTIME=codex
    export SEO_SEARCH_RUNTIME=direct
    if [ "$REGISTER" = "1" ]; then
        unset SEO_CYCLE_SKIP_REGISTRY
    else
        export SEO_CYCLE_SKIP_REGISTRY="${SEO_CYCLE_SKIP_REGISTRY:-1}"
    fi
    ensure_env_file "$PROJECT_DIR"
    ensure_codex_entrypoint "$PROJECT_DIR"
    cfg_path="$(find_project_config "$PROJECT_DIR" || true)"
    if [ -n "$cfg_path" ]; then
        run_existing_project_upgrade "$PROJECT_DIR" "$cfg_path"
    else
        "$CORE/scripts/init-project.sh"
        ensure_env_file "$PROJECT_DIR"
    fi
fi

echo ""
echo "════════════════════════════════════════════════"
echo "  ✓ Codex bootstrap finished"
echo "════════════════════════════════════════════════"
echo "Core: $CORE"
echo "Project: $PROJECT_DIR"
echo ""
echo "Next Codex command:"
echo "  cd \"$PROJECT_DIR\""
echo "  export SEO_RUNTIME=codex"
echo "  codex exec -c model_reasoning_effort=\"xhigh\" -c web_search=\"live\" \\"
echo "    \"Прочитай AGENTS.md, seo-cycle.yaml и seo/setup/context-pack.md. Подготовь первый SEO-план проекта.\""

if [ "$START_CODEX" = "1" ]; then
    if command -v codex >/dev/null 2>&1; then
        cd "$PROJECT_DIR"
        export SEO_RUNTIME=codex
        codex exec -c model_reasoning_effort="xhigh" -c web_search="live" \
            "Прочитай AGENTS.md, seo-cycle.yaml и seo/setup/context-pack.md. Подготовь первый SEO-план проекта."
    else
        echo "⚠ codex CLI не найден, автозапуск пропущен."
    fi
fi
