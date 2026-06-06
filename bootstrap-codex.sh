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
PROJECT_DIR="$PWD"
RUN_INIT=1
REGISTER=0
START_CODEX=0
INSTALL_SCOPE="${SEO_CYCLE_INSTALL_SCOPE:-local}"
WITH_WORDPRESS_MCP="${SEO_CYCLE_WITH_WORDPRESS_MCP:-0}"
REPO="${SEO_CYCLE_REPO:-https://github.com/turvodnik/seo-cycle}"
KW_REPO="${SEO_KEYWORDS_REPO:-https://github.com/turvodnik/seo-keywords}"
SHARED_DIR="${SEO_CYCLE_SHARED_DIR:-$HOME/.codex/vendor}"
CORE="${SEO_CYCLE_CORE:-$SHARED_DIR/seo-cycle}"
KW_CORE=""

usage() {
    cat <<'EOF'
seo-cycle Codex bootstrap

Usage:
  bootstrap-codex.sh [--project DIR] [--skip-init] [--register] [--start-codex]

Options:
  --project DIR    Project root to initialize. Default: current directory.
  --skip-init      Install/update shared core and project-local links only; do not run project wizard.
  --register       Allow init-project.sh to add this project to the global registry.
  --start-codex    After setup, run a first Codex prompt if the `codex` CLI exists.
  --local          Use shared vendor core + project-local skills/config (default).
  --vendor-local   Clone full seo-cycle core into PROJECT/.codex/skills.
  --global-skill   Legacy: also expose seo-cycle in global ~/.codex/skills.
  --with-wordpress-mcp
                  Also create project-local WordPress/Novomira MCP config.
                  Default is off; run only in projects that need it.
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
        --local)
            INSTALL_SCOPE=local
            shift
            ;;
        --vendor-local)
            INSTALL_SCOPE=vendor-local
            shift
            ;;
        --global|--global-skill)
            INSTALL_SCOPE=global-skill
            shift
            ;;
        --with-wordpress-mcp)
            WITH_WORDPRESS_MCP=1
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

ensure_python_deps() {
    echo "▶ проверяю зависимости (pyyaml, requests, pillow, beautifulsoup4, google-auth)..."
    if ! python3 -c "import yaml, requests, PIL, bs4; import google.auth, google.oauth2.service_account" 2>/dev/null; then
        pip3 install --quiet pyyaml requests pillow beautifulsoup4 google-auth 2>/dev/null \
            || pip install --quiet pyyaml requests pillow beautifulsoup4 google-auth 2>/dev/null \
            || echo "  ⚠ установи вручную: pip3 install pyyaml requests pillow beautifulsoup4 google-auth"
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
    if [ -d "$dest/.git" ]; then
        git -C "$dest" pull --quiet --ff-only 2>/dev/null || true
    elif git clone --quiet "$repo" "$dest" 2>/dev/null; then
        echo "▶ $label установлен"
    else
        echo "  ($label пропущен — необязателен)"
    fi
}

install_shared_core() {
    if [ -z "$CORE" ]; then
        CORE="$SHARED_DIR/seo-cycle"
    fi
    KW_CORE="$SHARED_DIR/seo-keywords"
    install_or_update_repo "$REPO" "$CORE" "seo-cycle shared vendor core"
    install_or_update_optional_repo "$KW_REPO" "$KW_CORE" "seo-keywords shared vendor"
    ensure_python_deps
}

install_legacy_global_skill_links() {
    mkdir -p "$HOME/.codex/skills" "$HOME/.agents/skills" "$HOME/.claude/skills"
    replace_with_symlink "$CORE" "$HOME/.codex/skills/seo-cycle"
    replace_with_symlink "$CORE" "$HOME/.agents/skills/seo-cycle"
    replace_with_symlink "$CORE" "$HOME/.claude/skills/seo-cycle"
    if [ -n "$KW_CORE" ] && [ -d "$KW_CORE" ]; then
        replace_with_symlink "$KW_CORE" "$HOME/.codex/skills/seo-keywords"
        replace_with_symlink "$KW_CORE" "$HOME/.agents/skills/seo-keywords"
        replace_with_symlink "$KW_CORE" "$HOME/.claude/skills/seo-keywords"
    fi
    if [ -d "$CORE/codex-primary-runtime" ]; then
        replace_with_symlink "$CORE/codex-primary-runtime" "$HOME/.codex/skills/codex-primary-runtime"
        replace_with_symlink "$CORE/codex-primary-runtime" "$HOME/.agents/skills/codex-primary-runtime"
        replace_with_symlink "$CORE/codex-primary-runtime" "$HOME/.claude/skills/codex-primary-runtime"
    fi
    echo "⚠ legacy global skill links enabled; seo-cycle will be visible in every project"
}

install_vendor_core() {
    local project_dir="$1"
    CORE="$project_dir/.codex/skills/seo-cycle"
    KW_CORE="$project_dir/.codex/skills/seo-keywords"
    install_or_update_repo "$REPO" "$CORE" "seo-cycle в project-local .codex/skills"
    install_or_update_optional_repo "$KW_REPO" "$KW_CORE" "seo-keywords project-local"
    ensure_python_deps
}

ensure_project_skill_links() {
    local project_dir="$1"
    mkdir -p "$project_dir/.codex/skills" "$project_dir/.agents/skills" "$project_dir/.claude/skills"
    if [ "$CORE" != "$project_dir/.codex/skills/seo-cycle" ]; then
        replace_with_symlink "$CORE" "$project_dir/.codex/skills/seo-cycle"
    fi
    if [ -n "$KW_CORE" ] && [ -d "$KW_CORE" ] && [ "$KW_CORE" != "$project_dir/.codex/skills/seo-keywords" ]; then
        replace_with_symlink "$KW_CORE" "$project_dir/.codex/skills/seo-keywords"
    fi
    replace_with_symlink "$project_dir/.codex/skills/seo-cycle" "$project_dir/.agents/skills/seo-cycle"
    replace_with_symlink "$project_dir/.codex/skills/seo-cycle" "$project_dir/.claude/skills/seo-cycle"
    if [ -d "$KW_CORE" ] || [ -d "$project_dir/.codex/skills/seo-keywords" ]; then
        replace_with_symlink "$project_dir/.codex/skills/seo-keywords" "$project_dir/.agents/skills/seo-keywords"
        replace_with_symlink "$project_dir/.codex/skills/seo-keywords" "$project_dir/.claude/skills/seo-keywords"
    fi
    if [ -d "$CORE/codex-primary-runtime" ]; then
        replace_with_symlink "$CORE/codex-primary-runtime" "$project_dir/.codex/skills/codex-primary-runtime"
        replace_with_symlink "$project_dir/.codex/skills/codex-primary-runtime" "$project_dir/.agents/skills/codex-primary-runtime"
        replace_with_symlink "$project_dir/.codex/skills/codex-primary-runtime" "$project_dir/.claude/skills/codex-primary-runtime"
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
        cat > "$project_dir/AGENTS.md" <<'EOF'
# Project Agent Instructions

This project uses seo-cycle through the project-local Codex surface:
`./.codex/skills/seo-cycle`.

Read order for SEO/AEO/GEO work:
1. `./.codex/skills/seo-cycle/AGENTS.md` — shared workflow contract.
2. `./seo-cycle.yaml` — project config.
3. `./seo/project-rules.md` — project-specific overrides.
4. `./seo/setup/context-pack.md` — task-scoped low-token context when present.

Do not edit the shared seo-cycle skill to handle one project's exception.
Put project-specific rules, exclusions, approvals and notes in
`seo/project-rules.md`, `seo-cycle.yaml`, or the relevant `seo/*.yaml` policy.
EOF
        echo "✓ AGENTS.md создан как project-local wrapper"
    else
        echo "ℹ AGENTS.md уже существует — не трогаю"
    fi
}

ensure_project_overlay() {
    local project_dir="$1"
    mkdir -p "$project_dir/seo" "$project_dir/.codex"
    if [ ! -f "$project_dir/seo/project-rules.md" ]; then
        cat > "$project_dir/seo/project-rules.md" <<'EOF'
# Project-Specific SEO Rules

Use this file for rules that apply only to this project.

Examples:
- hosting/CDN constraints;
- regional legal or analytics restrictions;
- CMS/plugin quirks;
- publishing approvals;
- URLs, templates or bot policies that differ from the shared seo-cycle defaults.

Do not change the shared seo-cycle skill for one project's exception.
EOF
        echo "✓ seo/project-rules.md создан"
    fi
    if [ ! -f "$project_dir/.codex/PROJECT.md" ]; then
        cat > "$project_dir/.codex/PROJECT.md" <<'EOF'
# Project-Local Codex Overlay

Shared code is reached through `./.codex/skills/seo-cycle` (usually a symlink to
the shared vendor core). Project secrets and MCP endpoints live in `.env` and
`.codex/config.toml`.

Keep project-specific behavior in `seo/project-rules.md` or `seo-cycle.yaml`.
EOF
        echo "✓ .codex/PROJECT.md создан"
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
    if [ "$WITH_WORDPRESS_MCP" = "1" ]; then
        python3 "$CORE/scripts/project-mcp-config.py" "$cfg_path" --write \
            || echo "ℹ project-mcp-config failed; run it manually after checking .env"
    fi
}

echo "════════════════════════════════════════════════"
echo "  seo-cycle Codex bootstrap"
echo "════════════════════════════════════════════════"

PROJECT_DIR="$(abs_path "$PROJECT_DIR")"
echo ""
echo "▶ Project root: $PROJECT_DIR"
echo "▶ Install scope: $INSTALL_SCOPE"

if [ "$INSTALL_SCOPE" = "vendor-local" ]; then
    install_vendor_core "$PROJECT_DIR"
else
    install_shared_core
    if [ "$INSTALL_SCOPE" = "global-skill" ]; then
        install_legacy_global_skill_links
    fi
fi
ensure_project_skill_links "$PROJECT_DIR"
ensure_project_overlay "$PROJECT_DIR"

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
    ensure_project_skill_links "$PROJECT_DIR"
    ensure_project_overlay "$PROJECT_DIR"
    ensure_codex_entrypoint "$PROJECT_DIR"
    cfg_path="$(find_project_config "$PROJECT_DIR" || true)"
    if [ -n "$cfg_path" ]; then
        run_existing_project_upgrade "$PROJECT_DIR" "$cfg_path"
    else
        if [ "$WITH_WORDPRESS_MCP" = "1" ]; then
            SEO_CYCLE_WITH_WORDPRESS_MCP=1 "$CORE/scripts/init-project.sh"
        else
            "$CORE/scripts/init-project.sh"
        fi
        ensure_env_file "$PROJECT_DIR"
        ensure_project_skill_links "$PROJECT_DIR"
        ensure_project_overlay "$PROJECT_DIR"
    fi
fi

echo ""
echo "════════════════════════════════════════════════"
echo "  ✓ Codex bootstrap finished"
echo "════════════════════════════════════════════════"
echo "Core: $CORE"
echo "Project: $PROJECT_DIR"
echo "WordPress/Novomira MCP: optional; run project-mcp-config.py or bootstrap with --with-wordpress-mcp only where needed."
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
