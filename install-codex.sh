#!/usr/bin/env bash
# install-codex.sh — legacy wrapper. The unified installer now lives in install.sh.
# Kept so documented curl URLs keep working:
#   curl -sL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/install-codex.sh | bash
set -euo pipefail
RAW_BASE="${SEO_CYCLE_RAW_BASE:-https://raw.githubusercontent.com/turvodnik/seo-cycle/main}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || echo "")"
if [ -n "$SELF_DIR" ] && [ -f "$SELF_DIR/install.sh" ]; then
    exec bash "$SELF_DIR/install.sh" "$@"
fi
curl -fsSL "$RAW_BASE/install.sh" | bash -s -- "$@"
