#!/usr/bin/env bash
# Schedule the recurring seo-cycle jobs so прогресс copится без ноутбука в руках.
#
# macOS: пишет launchd-плисты в ~/Library/LaunchAgents и загружает их.
# Linux: печатает готовый crontab-блок (crontab -e и вставить).
#
# Jobs (все read-only/локальные, платное остаётся за approvals):
#   daily    seo-cycle pulse   (свежий срез Вебмастера → snapshot → db → progress + алерты)
#   weekly   seo-cycle progress --global --write --html          (портфель)
#   monthly  seo-cycle run monthly                               (только с --with-monthly)
#
# Usage:
#   bash scripts/install-schedule.sh --project /path/to/project [--with-monthly]
#   bash scripts/install-schedule.sh --uninstall

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$ROOT/bin/seo-cycle"
AGENTS_DIR="$HOME/Library/LaunchAgents"
PREFIX="com.seo-cycle"
PROJECT=""
WITH_MONTHLY=0
UNINSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2;;
    --with-monthly) WITH_MONTHLY=1; shift;;
    --uninstall) UNINSTALL=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

if [[ "$(uname)" != "Darwin" ]]; then
  PROJECT="${PROJECT:-/path/to/project}"
  echo "# Linux: добавьте в crontab -e:"
  echo "10 6 * * *  '$LAUNCHER' pulse --global"
  echo "30 6 * * 1  '$LAUNCHER' progress --global --write --html"
  [[ $WITH_MONTHLY -eq 1 ]] && echo "0 7 1 * *   cd '$PROJECT' && '$LAUNCHER' run monthly"
  exit 0
fi

if [[ $UNINSTALL -eq 1 ]]; then
  for plist in "$AGENTS_DIR"/$PREFIX.*.plist; do
    [[ -e "$plist" ]] || continue
    launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist"
    echo "✗ removed $(basename "$plist")"
  done
  exit 0
fi

if [[ -z "$PROJECT" || ! -f "$PROJECT/seo-cycle.yaml" ]]; then
  echo "ERROR: --project /path/to/project (с seo-cycle.yaml) обязателен" >&2
  exit 2
fi
mkdir -p "$AGENTS_DIR"

xml_escape() { # & < > обязаны быть сущностями внутри <string> (launchd прощает, plutil/PlistBuddy — нет)
  local s="$1"
  s="${s//&/&amp;}"; s="${s//</&lt;}"; s="${s//>/&gt;}"
  printf '%s' "$s"
}

write_plist() { # name interval-xml program-args
  local name="$1" schedule="$2" args
  args="$(xml_escape "$3")"
  local plist="$AGENTS_DIR/$PREFIX.$name.plist"
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$PREFIX.$name</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>-lc</string>
    <string>$args</string>
  </array>
  $schedule
  <key>StandardOutPath</key><string>/tmp/$PREFIX.$name.log</string>
  <key>StandardErrorPath</key><string>/tmp/$PREFIX.$name.log</string>
</dict></plist>
PLIST
  launchctl unload "$plist" 2>/dev/null || true
  launchctl load "$plist"
  echo "✓ $PREFIX.$name (лог: /tmp/$PREFIX.$name.log)"
}

DAILY="<key>StartCalendarInterval</key><dict><key>Hour</key><integer>6</integer><key>Minute</key><integer>10</integer></dict>"
WEEKLY="<key>StartCalendarInterval</key><dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>30</integer></dict>"
MONTHLY="<key>StartCalendarInterval</key><dict><key>Day</key><integer>1</integer><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>"

# pulse --global идёт по реестру (все active-проекты); cd — только запасной контекст
write_plist "daily-progress" "$DAILY" "cd '$PROJECT' && '$LAUNCHER' pulse --global"
write_plist "weekly-portfolio" "$WEEKLY" "'$LAUNCHER' progress --global --write --html"
if [[ $WITH_MONTHLY -eq 1 ]]; then
  write_plist "monthly-runner" "$MONTHLY" "cd '$PROJECT' && '$LAUNCHER' run monthly"
fi

echo
echo "Готово. Проверка: launchctl list | grep $PREFIX · Снятие: bash scripts/install-schedule.sh --uninstall"
echo "⚠ Если Obsidian-дашборд лежит в OneDrive/iCloud: launchd не имеет прав на"
echo "  ~/Library/CloudStorage — дайте /bin/bash Full Disk Access (System Settings →"
echo "  Privacy & Security → Full Disk Access), иначе db-sync будет пропускать дашборд."
