#!/usr/bin/env bash
# monthly-runner.sh — главный entry point для Step 10 automation.
#
# Запускается через cron / Claude Code schedule / Codex schedule / вручную.
# Сам определяет какая операция нужна по дню недели + неделе месяца + статусу
# очереди. Создаёт approval tickets вместо непосредственных действий —
# реальное выполнение делегируется субагентам.
#
# Команды:
#   monthly-runner.sh                    # auto-detect по дате
#   monthly-runner.sh content            # System 2: weekly publisher
#   monthly-runner.sh audit              # System 3: site audit
#   monthly-runner.sh refresh            # System 4: refresh recommendation
#   monthly-runner.sh keyword            # System 1: replenish queue
#   monthly-runner.sh deindex            # System 4: deindex check
#   monthly-runner.sh status             # текущий статус (queue + pending approvals)
#   monthly-runner.sh dry-run [cmd]      # показать что будет сделано, без действий
#
# Опции:
#   --week N           Override week-of-month (1-4)
#   --force            Игнорировать "wrong day" check
#   --dry-run          Не вызывать subagent, только напечатать что будет
#
# Расписание по умолчанию (см. ниже SCHEDULE_*) — настраивается в seo-cycle.yaml
# секция monthly_automation.schedule.

set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_ROOT="$(pwd)"

# Расписание (cron-style). Defaults — переопределяются из seo-cycle.yaml
# секция monthly_automation.schedule (если файл доступен и python3+yaml).
SCHEDULE_CONTENT_DOW=1          # Monday
SCHEDULE_CONTENT_HOUR=9
SCHEDULE_AUDIT_WEEK=2           # Week 2 of month
SCHEDULE_AUDIT_DOW=3            # Wednesday
SCHEDULE_REFRESH_WEEK=3
SCHEDULE_REFRESH_DOW=3
SCHEDULE_KEYWORD_WEEK=4
SCHEDULE_KEYWORD_DOW=5          # Friday
SCHEDULE_DEINDEX_WEEK=4
SCHEDULE_DEINDEX_DOW=5

# Парс seo-cycle.yaml если доступен (используем python3 для надёжности)
CONFIG_FILE=""
for candidate in "seo-cycle.yaml" ".seo-cycle.yaml" "seo/seo-cycle.yaml" ".claude/seo-cycle.yaml"; do
    if [[ -f "$candidate" ]]; then
        CONFIG_FILE="$candidate"
        break
    fi
done

if [[ -n "$CONFIG_FILE" ]]; then
    # Извлекаем cron expressions из monthly_automation.schedule и парсим
    # cron "M H DOM MON DOW" → DOW = последнее поле
    parse_cron_dow() {
        local cron_expr="$1"
        local dow=$(echo "$cron_expr" | awk '{print $5}')
        # "1" остаётся "1", "*" → дефолт
        if [[ "$dow" =~ ^[0-9]+$ ]]; then
            echo "$dow"
        fi
    }
    if command -v python3 >/dev/null 2>&1; then
        SCHED_CONTENT=$(python3 -c "
import sys
try:
    import yaml
    cfg = yaml.safe_load(open('$CONFIG_FILE')) or {}
    sched = cfg.get('monthly_automation', {}).get('schedule', {}) or {}
    print(sched.get('content_writer', ''))
except Exception:
    pass
" 2>/dev/null || echo "")
        if [[ -n "$SCHED_CONTENT" ]]; then
            dow=$(parse_cron_dow "$SCHED_CONTENT")
            [[ -n "$dow" ]] && SCHEDULE_CONTENT_DOW=$dow
        fi
        SCHED_AUDIT=$(python3 -c "
import sys
try:
    import yaml
    cfg = yaml.safe_load(open('$CONFIG_FILE')) or {}
    sched = cfg.get('monthly_automation', {}).get('schedule', {}) or {}
    print(sched.get('audit', ''))
except Exception:
    pass
" 2>/dev/null || echo "")
        if [[ -n "$SCHED_AUDIT" ]]; then
            dow=$(parse_cron_dow "$SCHED_AUDIT")
            [[ -n "$dow" ]] && SCHEDULE_AUDIT_DOW=$dow
        fi
        # Аналогично можно парсить остальные. Для MVP — content + audit достаточно.
    fi
fi

# Auto-detect неделя месяца (1-4) и день недели (1=Mon..7=Sun)
TODAY=$(date +%Y-%m-%d)
DAY_OF_MONTH=$(date +%-d)
DAY_OF_WEEK=$(date +%u)
WEEK_OF_MONTH=$(( (DAY_OF_MONTH - 1) / 7 + 1 ))

# Парс CLI
CMD=""
DRY_RUN=0
FORCE=0
WEEK_OVERRIDE=""
ALL_MODE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)   DRY_RUN=1; shift ;;
        --force)     FORCE=1; shift ;;
        --week)      WEEK_OVERRIDE="$2"; shift 2 ;;
        all)         ALL_MODE=1; shift ;;
        -h|--help)
            sed -n '1,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//' | head -30
            exit 0
            ;;
        *)           CMD="$1"; shift ;;
    esac
done

# Режим all: итерация по реестру проектов (status=active, monthly_automation=true).
# Команда после all (если есть) прокидывается каждому проекту: `all content`,
# `all audit` и т.д. Без неё — auto-detect по дате в каждом проекте.
if [[ $ALL_MODE -eq 1 ]]; then
    REGISTRY="$SKILL_ROOT/config/projects-registry.yaml"
    [[ -f "$REGISTRY" ]] || { echo "Реестр не найден: $REGISTRY" >&2; exit 2; }
    FLAGS=""
    [[ $DRY_RUN -eq 1 ]] && FLAGS="$FLAGS --dry-run"
    [[ $FORCE -eq 1 ]] && FLAGS="$FLAGS --force"
    [[ -n "$WEEK_OVERRIDE" ]] && FLAGS="$FLAGS --week $WEEK_OVERRIDE"
    PROJECTS=$(python3 -c "
import yaml
d = yaml.safe_load(open('$REGISTRY')) or {}
for p in d.get('projects', []):
    if p.get('status') == 'active' and p.get('monthly_automation'):
        print(p['path'])
")
    if [[ -z "$PROJECTS" ]]; then
        echo "В реестре нет активных проектов с monthly_automation: true"
        exit 0
    fi
    RC=0
    while IFS= read -r proj; do
        [[ -z "$proj" ]] && continue
        echo "════════════════════════════════════════════════════════════"
        echo "  Проект: $proj  (cmd: ${CMD:-auto})"
        echo "════════════════════════════════════════════════════════════"
        if [[ -d "$proj" ]]; then
            if ! ( cd "$proj" && bash "$SKILL_ROOT/scripts/monthly-runner.sh" $CMD $FLAGS ); then
                RC=$?
                python3 "$SKILL_ROOT/scripts/notify.py" \
                    "Сбой monthly-runner в проекте $proj (cmd: ${CMD:-auto})" \
                    --title "SEO automation: ошибка" --level alert 2>/dev/null || true
            fi
        else
            echo "  ⚠ путь не найден, пропуск" >&2
        fi
    done <<< "$PROJECTS"
    exit $RC
fi

[[ -n "$WEEK_OVERRIDE" ]] && WEEK_OF_MONTH=$WEEK_OVERRIDE

# Helper: запуск с dry-run wrapper
run() {
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "  [DRY-RUN] $*"
    else
        eval "$@"
    fi
}

# Helper: вывод текущего контекста
print_context() {
    echo "═══════════════════════════════════════════════"
    echo "  monthly-runner.sh"
    echo "═══════════════════════════════════════════════"
    echo "  Today:        $TODAY"
    echo "  Day of week:  $DAY_OF_WEEK (1=Mon, 7=Sun)"
    echo "  Week of month: $WEEK_OF_MONTH"
    echo "  Project:      $PROJECT_ROOT"
    echo "  Dry-run:      $([[ $DRY_RUN -eq 1 ]] && echo YES || echo no)"
    echo ""
}


# ────────────────────── Auto-detect ─────────────────────────────────────

auto_detect() {
    # Mon — content
    if [[ $DAY_OF_WEEK -eq $SCHEDULE_CONTENT_DOW ]]; then
        echo "content"
        return
    fi
    # Week 2 Wed — audit
    if [[ $WEEK_OF_MONTH -eq $SCHEDULE_AUDIT_WEEK && $DAY_OF_WEEK -eq $SCHEDULE_AUDIT_DOW ]]; then
        echo "audit"
        return
    fi
    # Week 3 Wed — refresh
    if [[ $WEEK_OF_MONTH -eq $SCHEDULE_REFRESH_WEEK && $DAY_OF_WEEK -eq $SCHEDULE_REFRESH_DOW ]]; then
        echo "refresh"
        return
    fi
    # Week 4 Fri — keyword + deindex
    if [[ $WEEK_OF_MONTH -eq $SCHEDULE_KEYWORD_WEEK && $DAY_OF_WEEK -eq $SCHEDULE_KEYWORD_DOW ]]; then
        echo "keyword_and_deindex"
        return
    fi
    echo "none"
}


# ────────────────────── Команды ──────────────────────────────────────────

cmd_content() {
    print_context
    echo "🟢 System 2: Weekly Publisher"
    echo ""
    # Pop next approved keyword
    local queue_depth
    queue_depth=$(python3 "$SKILL_ROOT/scripts/keyword-queue.py" depth 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('approved',0))" 2>/dev/null || echo 0)
    echo "  Approved keywords in queue: $queue_depth"
    if [[ $queue_depth -lt 1 ]]; then
        echo "  ⚠ Нет approved ключей. Запусти keyword research или approve pending."
        echo "  Команда: python3 $SKILL_ROOT/scripts/keyword-queue.py list --status pending"
        return 1
    fi
    echo ""
    echo "  Workflow:"
    echo "    1. keyword-queue.py pop → получить next keyword"
    echo "    2. Делегировать в субагента seo-weekly-publisher"
    echo "    3. Субагент: Entity Map → write → QA → approval gate → publish"
    echo ""
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "  [DRY-RUN] Next в очереди:"
        python3 "$SKILL_ROOT/scripts/keyword-queue.py" pop --peek 2>/dev/null | head -20
        return 0
    fi
    echo "  → Передаю управление субагенту seo-weekly-publisher."
    echo "    (В Claude Code: используй Skill tool с агентом)"
    echo "    Команда для запуска руками:"
    echo "    python3 $SKILL_ROOT/scripts/keyword-queue.py pop"
}

cmd_audit() {
    print_context
    if [[ $WEEK_OF_MONTH -ne $SCHEDULE_AUDIT_WEEK && $FORCE -ne 1 ]]; then
        echo "⚠ Сегодня неделя $WEEK_OF_MONTH, audit запланирован на неделю $SCHEDULE_AUDIT_WEEK."
        echo "  Используй --force чтобы запустить вне расписания."
        return 1
    fi
    echo "🔧 System 3: Monthly Site Audit"
    echo ""
    echo "  Workflow:"
    echo "    1. Делегировать в субагента seo-monthly-auditor"
    echo "    2. Агент: вызывает seo-auditor + claude-seo:seo-technical"
    echo "    3. Filter only critical issues"
    echo "    4. Approval gate перед применением фиксов"
    echo ""
    echo "  → Используй Skill tool: спроси Claude «запусти аудит через seo-monthly-auditor»"
}

cmd_refresh() {
    print_context
    if [[ $WEEK_OF_MONTH -ne $SCHEDULE_REFRESH_WEEK && $FORCE -ne 1 ]]; then
        echo "⚠ Сегодня неделя $WEEK_OF_MONTH, refresh запланирован на неделю $SCHEDULE_REFRESH_WEEK."
        echo "  --force чтобы запустить вне расписания."
        return 1
    fi
    echo "♻️  System 4: Refresh Recommendation"
    echo ""
    echo "  Требует snapshot в 09-monitoring/*.json"
    echo "  Workflow:"
    echo "    1. Делегировать в субагента seo-refresh-rescuer"
    echo "    2. Агент: triggers-eval по правилам fact_check_stale / page_unchanged_long / position_drop"
    echo "    3. Сгенерировать ranked list страниц для refresh"
    echo "    4. Approval gate"
    echo ""
    echo "  → Используй Skill tool: «запусти refresh recommendation»"
}

cmd_keyword() {
    print_context
    echo "🔑 System 1: Keyword Queue Replenish"
    echo ""
    local depth
    depth=$(python3 "$SKILL_ROOT/scripts/keyword-queue.py" depth 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('approved',0)+d.get('pending',0))" 2>/dev/null || echo 0)
    echo "  Текущая глубина (pending+approved): $depth"
    if [[ $depth -ge 4 ]]; then
        echo "  ✓ Очередь достаточно глубокая (>=4). Replenish не требуется."
        if [[ $FORCE -ne 1 ]]; then
            return 0
        fi
        echo "  --force: запускаю всё равно"
    fi
    echo ""
    echo "  Workflow:"
    echo "    1. Делегировать в субагента seo-keyword-queue-manager"
    echo "    2. Агент: Phase 2 (Wordstat + GSC + NW + LLM CLI + ATP) на стратегические темы"
    echo "    3. Approval gate: одобрение списка (5 min)"
    echo "    4. Approved keywords → keyword-queue.py add ..."
    echo ""
    echo "  → Используй Skill tool: «запусти keyword research для кластера X»"
}

cmd_deindex() {
    print_context
    echo "🚨 System 4: Deindexation Check"
    echo ""
    echo "  Требует:"
    echo "    - sitemap.xml (проектный)"
    echo "    - GSC доступ (gsc-fetch.py или delegate claude-seo:seo-google)"
    echo ""
    echo "  Workflow (MVP placeholder):"
    echo "    1. Сравнить sitemap URLs vs GSC indexed pages"
    echo "    2. Identify lost (был indexed, теперь нет)"
    echo "    3. Approval gate: подтвердить список для rescue"
    echo "    4. Rescue: переписать страницу + Request Indexing в GSC"
    echo ""
    echo "  (Full implementation в Step 10 Full — пока placeholder.)"
}

cmd_status() {
    print_context
    echo "📊 Status overview"
    echo ""
    echo "── Keyword queue ──"
    python3 "$SKILL_ROOT/scripts/keyword-queue.py" status 2>/dev/null || echo "  (queue file не найден)"
    echo ""
    echo "── Pending approvals ──"
    python3 "$SKILL_ROOT/scripts/approval-gate.py" list --status pending 2>/dev/null || echo "  (нет pending)"
    echo ""
    echo "── Last monitoring snapshot ──"
    local latest_snap
    latest_snap=$(ls -t 09-monitoring/*-snapshot.json 2>/dev/null | head -1 || echo "")
    if [[ -n "$latest_snap" ]]; then
        echo "  $latest_snap"
        python3 -c "import json,sys; d=json.load(open('$latest_snap')); print(f'  queries: {len(d.get(\"queries\",[]))}, pages: {len(d.get(\"pages\",[]))}, sources: {[s.get(\"source\") for s in d.get(\"sources\",[])]}')" 2>/dev/null
    else
        echo "  (snapshot не найден — запусти Phase 9)"
    fi
}


# ────────────────────── Main ─────────────────────────────────────────────

# Auto-detect если cmd не задан
if [[ -z "$CMD" ]]; then
    DETECTED=$(auto_detect)
    if [[ "$DETECTED" == "none" ]]; then
        print_context
        echo "ℹ Сегодня нет запланированных операций."
        echo "  Команды:"
        echo "    monthly-runner.sh status        # текущий статус"
        echo "    monthly-runner.sh content       # запустить вручную"
        echo "    monthly-runner.sh audit"
        echo "    monthly-runner.sh refresh"
        echo "    monthly-runner.sh keyword"
        echo "    monthly-runner.sh deindex"
        exit 0
    fi
    CMD="$DETECTED"
    echo "ℹ Auto-detected: $CMD"
    echo ""
fi

case "$CMD" in
    content)             cmd_content ;;
    audit)               cmd_audit ;;
    refresh)             cmd_refresh ;;
    keyword)             cmd_keyword ;;
    deindex)             cmd_deindex ;;
    keyword_and_deindex) cmd_keyword; echo ""; cmd_deindex ;;
    status)              cmd_status ;;
    dry-run)             DRY_RUN=1; CMD="${1:-status}"; eval "cmd_$CMD" ;;
    *)
        echo "Unknown command: $CMD" >&2
        echo "Use --help для списка." >&2
        exit 1
        ;;
esac
