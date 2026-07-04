#!/usr/bin/env bash
# Put a double-click launcher for seo-cycle on the Desktop (macOS).
#
# Creates:
#   ~/Desktop/SEO Cycle.app      — AppleScript applet: opens Terminal → seo-cycle menu
#   ~/Desktop/SEO Cycle.command  — plain fallback (works even if osacompile is unavailable)
#
# The menu lets a non-terminal user pick a project from config/projects-registry.yaml
# and run journey / progress / dashboard / approvals / doctor without typing commands.
#
# Usage: bash scripts/install-desktop-app.sh [--desktop-dir <dir>]

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$ROOT/bin/seo-cycle"
DESKTOP="${HOME}/Desktop"

if [[ "${1:-}" == "--desktop-dir" && -n "${2:-}" ]]; then
  DESKTOP="$2"
fi

if [[ ! -x "$LAUNCHER" ]]; then
  echo "ERROR: $LAUNCHER не найден или не исполняемый" >&2
  exit 2
fi
mkdir -p "$DESKTOP"

# --- 1. .command fallback (двойной клик открывает Terminal) -------------------
CMD_FILE="$DESKTOP/SEO Cycle.command"
cat > "$CMD_FILE" <<EOF
#!/usr/bin/env bash
exec "$LAUNCHER" menu
EOF
chmod +x "$CMD_FILE"
echo "✓ $CMD_FILE"

# --- 2. Полноценный .app через osacompile (только macOS) ----------------------
if command -v osacompile >/dev/null 2>&1; then
  APP="$DESKTOP/SEO Cycle.app"
  rm -rf "$APP"
  osacompile -o "$APP" <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "exec '$LAUNCHER' menu"
end tell
APPLESCRIPT
  echo "✓ $APP"
  echo "  Иконку можно заменить: Get Info на .app → перетащить свою картинку на значок."
else
  echo "osacompile не найден (не macOS?) — остаётся .command файл." >&2
fi

echo
echo "Готово: двойной клик по «SEO Cycle» на рабочем столе открывает меню"
echo "(выбор проекта из реестра → journey / прогресс позиций / дашборд / approvals / doctor)."
