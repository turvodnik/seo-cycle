# Automated Monthly Workflow (Step 10)

4-system автоматизация: ежемесячный SEO-цикл с минимальным человеческим вмешательством (~2-3 часа в месяц).

## Концепция

Заменяет работу команды из 4 человек:
- Content Strategist ($3-5k/mo) — System 1 (Keyword Research)
- Content Writer ($2-4k/mo) — System 2 (Weekly Publisher)
- Technical SEO ($2-3k/mo) — System 3 (Monthly Auditor)
- Content Editor ($1.5-3k/mo) — System 4 (Refresh + Rescue)

**Total команды:** $8.5-15k/mo → **Total системы:** <$50/mo (API + tools).

## Расписание

```
Week 1:  Mon 9am  — Pub #1 (System 2)
Week 2:  Mon 9am  — Pub #2
         Wed 2pm  — Site Audit (System 3) + fixes
Week 3:  Mon 9am  — Pub #3
         Wed 2pm  — Refresh Recommendation (System 4)
Week 4:  Mon 9am  — Pub #4
         Fri 4pm  — Keyword Replenish (System 1) if queue low
         Fri 5pm  — Deindex Check (System 4 — Full Step 10)
```

## Активация

В `seo-cycle.yaml`:

```yaml
mode: automated_monthly

monthly_automation:
  enabled: true
  schedule:
    timezone: "Europe/Moscow"
    content_writer: "0 9 * * 1"        # Mon 9am
    # ... (см. project.template.yaml секция 21)
  keyword_queue:
    file: "./seo/keyword-queue.csv"
    min_queue_depth: 4
  approval_gates:
    keyword_research: required
    content_pre_publish: required
    audit_fixes: required
    refresh_recommendation: required
    deindex_rewrite: required
```

## Setup

### 1. Создать keyword queue

```bash
cp ~/.codex/skills/seo-cycle/templates/keyword-queue.template.csv \
   seo/keyword-queue.csv
# Заполни 4-8 ключей под свою нишу + approve через keyword-queue.py
```

Или запусти `seo-keyword-queue-manager` для генерации:
> «Запусти keyword research для кластера X»

### 2. Подключить расписание

#### Вариант A — системный cron (рекомендуется)

```bash
# Открой crontab
crontab -e

# Добавь (пути замени на свои)
PROJECT=/Users/turvodnik/AI/emwoody
0 9 * * 1   cd $PROJECT && bash ~/.codex/skills/seo-cycle/scripts/monthly-runner.sh content >> $PROJECT/seo/cron.log 2>&1
0 14 * * 3  cd $PROJECT && bash ~/.codex/skills/seo-cycle/scripts/monthly-runner.sh >> $PROJECT/seo/cron.log 2>&1
0 16 * * 5  cd $PROJECT && bash ~/.codex/skills/seo-cycle/scripts/monthly-runner.sh >> $PROJECT/seo/cron.log 2>&1
```

`monthly-runner.sh` без аргумента auto-detect какая операция нужна по дню недели + неделе месяца.

#### Вариант B — Claude Code schedule skill

Если используешь Claude Code:
```
/schedule create "0 9 * * 1" "запусти seo-weekly-publisher для следующего keyword из очереди emwoody"
```

#### Вариант C — Codex CLI schedule

Если на Codex CLI — аналогично через свой schedule mechanism.

### 3. Включить approval gates

Уже включено по умолчанию (`approval_gates.*: required`). После каждого scheduled запуска проверяй:

```bash
python3 ~/.codex/skills/seo-cycle/scripts/approval-gate.py list --status pending
```

Или просто открой `seo/pending-approvals.md` в Obsidian.

## Workflow по неделям

### Week 1 — Monday morning

**Cron триггер:** `0 9 * * 1` → `monthly-runner.sh` → auto-detect `content`

1. `monthly-runner.sh content` → проверяет queue
2. Если есть approved keyword — делегирует в `seo-weekly-publisher`
3. Publisher:
   - Pop keyword → Entity Map → Write → QA (stop-words/fact-check/NW)
   - Создаёт approval ticket `content_publish`
   - **STOP** — ждёт человека
4. Notification (опц.) → email с ticket ID

**Ты:**
1. Открой `seo/pending-approvals.md` (~2 min)
2. Прочитай draft: `head -100 blog/<slug>.publish.md`
3. Approve: `approval-gate.py approve <ticket_id>`
4. Publisher продолжает: publish через `emwoody-publish-*` → mark in queue

### Week 2 — Mon + Wed

**Mon 9am:** то же что Week 1 — Post #2.

**Wed 2pm cron:** `monthly-runner.sh` auto-detects week 2 + Wed → `audit`
1. Делегирует в `seo-monthly-auditor`
2. Auditor: параллельный audit (seo-auditor + claude-seo:seo-technical)
3. Фильтр только P0+P1 → отчёт в `seo/cycles/audit-YYYY-MM/01-audit.md`
4. Approval ticket `audit_fixes`
5. **STOP**

**Ты:**
1. Review (~30 min): `cat seo/cycles/audit-YYYY-MM/01-audit.md`
2. Approve / reject с reasoning
3. Если approve — auditor применяет safe auto-fixes, для остального — список инструкций для devops

### Week 3 — Mon + Wed

**Mon 9am:** Post #3.

**Wed 2pm:** `refresh` → `seo-refresh-rescuer`
1. Триггеры по последнему snapshot
2. Score + rank страниц
3. Refresh plan в `seo/cycles/refresh-YYYY-MM/refresh-plan.md`
4. Approval ticket `refresh_plan`

**Ты:** (~10 min) review план + approve

После approve — refresh-rescuer запускает Phase 6 для каждой страницы из плана.

### Week 4 — Mon + Fri

**Mon 9am:** Post #4.

**Fri 4pm:** `keyword_and_deindex` (две операции подряд)

**Часть A — Keyword replenish:**
- Если queue depth < min (default 4) — делегирует в `seo-keyword-queue-manager`
- Phase 2 multi-source research (Wordstat + Suggest + GSC + LLM CLI + ATP)
- Approval ticket `keyword_research` (~5 min review)
- После approve — добавляет в queue (всего ~10-15 новых)

**Часть B — Deindex check (Full Step 10):**
- В MVP — placeholder, пользователь запускает руками если нужно
- В Full — sitemap vs GSC diff → потерянные → approval → rewrite

**Ты:** (~5-10 min) approve keyword research, опц. запустить deindex.

## Personal time math

| Activity | Frequency | Time per | Monthly total |
|---|---|---|---|
| Approve keyword research | 1×/mo (Week 4) | 5 min | 5 min |
| Approve each post | 4×/mo (Mondays) | 2 min | 8 min |
| Site audit review + fixes | 1×/mo (Week 2) | 30 min | 30 min |
| Refresh plan review | 1×/mo (Week 3) | 10 min | 10 min |
| Deindex (if Full Step 10) | <1×/mo | 5 min | 5 min |
| Misc (monitor health, ad-hoc) | weekly | 5 min | 20 min |
| **Total** | | | **~1.5-2 часа в месяц** |

## Cross-platform — Claude Code + Codex CLI

Все компоненты универсальны:

| Слой | Реализация |
|---|---|
| **Subagents** | YAML frontmatter + markdown body — Anthropic Agent Skills spec. Работает в Claude Code (auto-discovery из `~/.claude/agents/`) и Codex CLI (нужна копия в `skills/seo-cycle/agents/` per Codex convention) |
| **Scripts** | Pure Python 3 / bash, без Claude-specific API. Работает везде |
| **Storage** | CSV (keyword queue), markdown (approvals), JSON (snapshots) — все human-readable, переносимые |
| **Schedule** | Системный cron (универсально), Claude Code schedule skill, или Codex schedule |

Для миграции на Codex:
```bash
# Скопировать agents в Codex convention path (если он другой)
mkdir -p ~/.codex/agents  # или skill-local, зависит от Codex
cp ~/.claude/agents/seo-{monthly-orchestrator,keyword-queue-manager,weekly-publisher,monthly-auditor,refresh-rescuer,approval-gate}.md ~/.codex/agents/

# Scripts уже работают
```

## Approval gates — деталями

### Когда **нельзя** пропускать approval

- Любая публикация на сайт (`content_publish`, `refresh_plan` per page)
- Server-level fixes (htaccess, nginx — даже не пытайся auto-apply)
- Mass operations (>5 страниц одновременно)
- Изменение CMS settings (роли, sharing, theme)

### Когда **можно** пропустить (с риском)

- Sitemap regeneration (если включил `approval_gates.audit_fixes: optional`)
- Robots.txt minor changes
- Schema markup для новых страниц (auto-generation из template)

В MVP по умолчанию ВСЁ требует approval. Со временем можно ослабить для проверенных операций (auto_approve_threshold).

## Failure modes & recovery

### Queue пустая в Monday 9am
- `monthly-runner.sh content` → exit 1 с сообщением
- Cron job logs ошибку
- Ничего страшного — следующий понедельник попробует снова
- **Действие:** вызови `seo-keyword-queue-manager` руками

### Pending approval не resolved >7 дней
- Operation не продолжается
- `seo-weekly-publisher` не создаст новый ticket по той же теме
- **Действие:** approve, reject или cancel (через `approval-gate.py reject ... --reason "obsolete"`)

### QA gate fails (stop-words / fact-check / NW low)
- Publisher останавливается, не создаёт content_publish ticket
- Сообщает в логи что не прошло
- **Действие:** прочитай лог, попроси `seo-content-writer` переписать с конкретной проблемой

### Snapshot устарел >30 дней
- `seo-refresh-rescuer` отказывается работать (нужен свежий контекст)
- **Действие:** запусти Phase 9 (через `claude-seo:seo-google` + `yandex-seo-specialist`) → новый snapshot

## Известные ограничения MVP

- **Deindex detection** — только placeholder. Full Step 10 добавит `scripts/deindex-detect.py`
- **Monthly dashboard** — не реализован. Сейчас статус через `monthly-runner.sh status`
- **Auto-notification** (email на P0 audit) — не реализовано
- **Schedule из конфига** не парсится автоматически monthly-runner'ом — расписание захардкожено как defaults (можно override через cron явно)

Roadmap → Full Step 10:
- `scripts/deindex-detect.py` + `prompts/page-rewrite-rescue.md`
- `scripts/monthly-dashboard.py` — генерация status doc
- Schedule parser из yaml в monthly-runner.sh

## Связанные файлы

- Скрипты: `keyword-queue.py`, `approval-gate.py`, `monthly-runner.sh`
- Subagents: `seo-monthly-orchestrator`, `seo-keyword-queue-manager`, `seo-weekly-publisher`, `seo-monthly-auditor`, `seo-refresh-rescuer`, `seo-approval-gate`
- Config: `seo-cycle.yaml` секция `monthly_automation`
- Templates: `keyword-queue.template.csv`
- Triggers: `config/triggers.yaml`
