#!/usr/bin/env bash
# bootstrap-codex.sh — legacy wrapper over install.sh (Codex-flavoured defaults).
#   curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash
set -euo pipefail

RAW_BASE="${SEO_CYCLE_RAW_BASE:-https://raw.githubusercontent.com/turvodnik/seo-cycle/main}"
PROJECT_DIR="$PWD"
ARGS=(--runtime codex)
START_CODEX=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --project) PROJECT_DIR="${2:?--project requires a directory}"; shift 2 ;;
        --skip-init) ARGS+=(--skip-init); shift ;;
        --register) ARGS+=(--register); shift ;;
        --start-codex) START_CODEX=1; shift ;;
        --local) shift ;;  # default in install.sh
        --vendor-local) ARGS+=(--vendor-local); shift ;;
        --global|--global-skill) ARGS+=(--global-skill); shift ;;
        --with-wordpress-mcp) ARGS+=(--with-wordpress-mcp); shift ;;
        -h|--help)
            echo "bootstrap-codex.sh [--project DIR] [--skip-init] [--register] [--start-codex]"
            echo "                   [--vendor-local] [--global-skill] [--with-wordpress-mcp]"
            echo "Legacy wrapper: см. install.sh --help"
            exit 0 ;;
        *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
    esac
done

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || echo "")"
if [ -n "$SELF_DIR" ] && [ -f "$SELF_DIR/install.sh" ]; then
    bash "$SELF_DIR/install.sh" --project "$PROJECT_DIR" "${ARGS[@]}"
else
    curl -fsSL "$RAW_BASE/install.sh" | bash -s -- --project "$PROJECT_DIR" "${ARGS[@]}"
fi

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
