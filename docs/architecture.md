# Архитектура `seo-cycle` (v2)

Обновлено: 2026-07-29 (v2.0.0 — модульные фазовые скиллы, версионированное хранилище).

## Принципы

1. **Config-driven** — все решения зависят от `seo-cycle.yaml` проекта. Один кодовый базис для всех проектов.
2. **Source-flexible** — источники данных (Wordstat, GSC, NW, ATP, LLM CLI, Perplexity, XMLRiver, Serpstat, SpyFu) включаются независимо; скилл пропускает то, что не enabled/не доступно в регионе (`resolve-sources.py`).
3. **CMS-agnostic** — публикация делегируется проектным скиллам через `delegate.*` / `publishing.publish_skills`.
4. **LLM-агностичный** — каждый LLM-шаг выполняется через Claude, Codex CLI, Antigravity CLI или Perplexity — по доступности.
5. **Идемпотентный** — повторный запуск фазы обновляет артефакты, а не ломает их.
6. **Модульный (v2)** — фазы 1–10 разнесены по самостоятельным скиллам `skills/*`; корневой `SKILL.md` — тонкий оркестратор (Phase 0 + диспетчеризация). Каждый модуль запускается отдельно или стадией конвейера через `_state.json`.
7. **Контекст-экономный** — агент грузит только оркестратор + модуль текущей фазы + нужные `_shared`-фрагменты; сырьё живёт на диске, в контекст идут дистилляты.
8. **Секреты — в Keychain** — значения ключей живут в macOS Keychain (`ai-secret`), конфиги и `.env.example` содержат только имена.

## Поток управления

```
Пользователь
    ↓
триггер полного цикла → корневой SKILL.md (оркестратор)
триггер одной фазы    → skills/<модуль>/SKILL.md напрямую
    ↓
Phase 0 (оркестратор) — конфиг/wizard, цель, task-router, context-pack
    ↓  cycle-state init/next
Phase 1   skills/seo-audit       ← delegate.audit (+technical_audit)
Phase 2–3 skills/seo-keywords    ← delegate.keyword_research + cluster_analysis (внешний репозиторий seo-keywords)
Phase 4   skills/seo-entity-map  ← delegate.semantic_brief (fallback: его же templates/entity-map.template.md)
Phase 5–6 skills/seo-writing     ← delegate.content_strategy + content_writer + gates (stop-words, fact-check, NW, draft-gate)
Phase 7–8 skills/seo-publishing  ← publishing.publish_skills + delegate.schema_markup
Phase 9   skills/seo-monitoring  ← delegate.google_data + yandex_specialist (pulse, snapshot-build, db-sync)
Phase 10  skills/seo-iteration   ← triggers-eval + source-attribution + kpi/forecast
    ↺ (gate каждой фазы: cycle-state gate <phase>; контент — через loop-runner)
```

Три сервисных машины поверх фаз:
- **loop-runner** (`scripts/loop-runner.py`) — автоцикл gate → repair → re-gate (exit 3 = LLM-ремонт, exit 1 = эскалация в approvals);
- **governance/spend** (`usage-ledger.py`, `spend-guard.py`, `approvals.py`) — preflight и учёт платного;
- **data pipeline** (`pulse` → `*-fetch.py` → `snapshot-build.py` → `db-sync.py` → `position-progress.py` → `triggers-eval.py`).

## Структура репозитория (v2)

```
seo-cycle/
├── SKILL.md                     # ТОНКИЙ ОРКЕСТРАТОР: Phase 0, диспетчеризация, CLI, loop, ads
├── AGENTS.md → SKILL.md         # entry-point Codex
├── skills/
│   ├── manifest.yaml            # реестр модулей (валидируется skill-manifest-validate.py)
│   ├── _shared/                 # общие фрагменты: policy-intake, scorecard, rag-usage,
│   │                            #   toolchain, setup-commands, customization, sources-of-truth, lessons
│   ├── seo-audit/               # Phase 1   (SKILL.md + prompts/: competitor-analysis, local/)
│   ├── seo-keywords/            # Phases 2–3 (контракт; реализация — внешний репозиторий seo-keywords)
│   ├── seo-entity-map/          # Phase 4   (templates/: entity-map, programmatic-page)
│   ├── seo-writing/             # Phases 5–6 (prompts/fact-check; templates/: cycle-plan, stop-words, stock-inventory)
│   ├── seo-publishing/          # Phases 7–8 (templates/hreflang-matrix)
│   ├── seo-monitoring/          # Phase 9   (prompts/: ai-visibility, ad-and-social, serp-news; templates/monitoring-report)
│   └── seo-iteration/           # Phase 10  (prompts/page-rewrite-rescue)
├── prompts/, templates/         # v1-пути: реальные файлы оркестратора (marketing-*) + СИМЛИНК-ШИМЫ
│                                #   на переехавшие в skills/* файлы (совместимость, удаление в v3)
├── scripts/                     # общий движок: ~180 CLI-скриптов + пакет seo_cycle_core/
├── bin/seo-cycle                # единый CLI (scripts/seo_cycle_cli.py)
├── config/                      # project.template.yaml, triggers.yaml, region-profiles/,
│                                #   projects-registry.example.yaml (реальный projects-registry.yaml — локальный, .gitignore)
├── tests/                       # unittest-набор (обязателен зелёным до push)
├── install.sh                   # ЕДИНЫЙ установщик: хранилище + версии + attach/detach/upgrade
├── install-codex.sh, bootstrap-*.sh   # legacy-обёртки над install.sh (стабильные curl-URL)
└── docs/                        # этот файл, adapt.md, migration.md, codex-runtime.md, knowledge-hub.md, ...
```

## Дистрибуция (v2): хранилище + версии + attach

```
~/.codex/vendor/seo-cycle                    # единственный клон (fetch обновлений)
~/.codex/vendor/versions/seo-cycle/vX.Y.Z    # read-only git worktree на каждый релиз-тег
~/.codex/vendor/attached-projects.yaml       # machine-local реестр подключённых проектов

<project>/.agents/external/seo-cycle → ~/.codex/vendor/versions/seo-cycle/vX.Y.Z
<project>/.claude/skills/seo-cycle   → ../../.agents/external/seo-cycle
<project>/.codex/skills/seo-cycle    → ../../.agents/external/seo-cycle
<project>/.agents/external-skills.lock.yaml  # пин версии + commit
```

Проект без attach не содержит ни одного файла seo-cycle и не получает его в контекст агентов. Разные проекты — разные версии; `install.sh --upgrade-all` переводит все подключённые проекты на новый тег, откат — переключение пина.

## Структура проекта (после attach)

```
<project>/
├── seo-cycle.yaml               # КОНФИГ — единственный обязательный файл
├── .env.example                 # только ИМЕНА ключей (значения — в Keychain через ai-secret)
├── AGENTS.md                    # канонические правила проекта (CLAUDE.md и GEMINI.md — симлинки)
├── seo/
│   ├── cycles/<topic>-<YYYY-Qx>/       # артефакты фаз 00–10 + _state.json
│   ├── research/<source>/results/      # сырьё источников (gitignore)
│   ├── research/distillates/           # дистилляты для контекста
│   ├── research-package/               # канонический контент-конвейер с гейтами
│   ├── reports/                        # отчёты для человека
│   ├── knowledge/                      # вики (источник истины), corpus, rag.db
│   ├── monitoring/, strategy/, setup/, loops/, ads/, logs/
│   └── project-rules.md                # проектные override'ы
├── workspace/{runs,results,history}    # малое рабочее (в git)
├── workspace/{artifacts,cache,tmp}     # регенерируемое (gitignore)
└── .agents/ .claude/ .codex/           # канонический слой + генерируемые поверхности
```

## Делегирование (`delegate.*`)

```yaml
delegate:
  semantic_brief: <project>-semantic-brief         # проектный
  audit: seo-auditor                               # глобальный агент
  keyword_research: seo-keyword-researcher
  content_strategy: seo-content-strategist
  content_writer: seo-content-writer
  yandex_specialist: yandex-seo-specialist
  google_data: "claude-seo:seo-google"             # plugin skill
  schema_markup: "claude-seo:seo-schema"
```

Если делегат не указан — fallback-шаблоны модуля: `skills/seo-entity-map/templates/entity-map.template.md` (Phase 4), `skills/seo-writing/templates/cycle-plan.template.md` (Phase 5). Старые пути `templates/*.template.md` продолжают работать через шимы.

## Точки расширения

| Расширение | Где |
|---|---|
| Новый источник данных | `sources.*` в конфиге + (опц.) скрипт в `scripts/` |
| Новый CMS | `publishing.publish_skills.*` + проектный publish-скилл |
| Новая фаза/модуль | каталог в `skills/` + запись в `skills/manifest.yaml` (валидатор следит за покрытием фаз) |
| Новый язык стоп-слов | `XX_PATTERNS` в `check-stop-words.py` |
| Новая ниша | `content_rules.*` + проектные субскиллы |
| Новый триггер Phase 10 | `config/triggers.yaml` или `<project>/seo-triggers.yaml` (merge по `id`) |
| Новый тип schema | шаблон + handler в `skills/seo-publishing` |

## Версионирование

- **Major**: ломающие изменения схемы `seo-cycle.yaml` ИЛИ контракта раскладки репозитория (v2.0.0 — модульные skills/, перенос prompts/templates под шимы).
- **Minor**: новые источники, delegate-цели, модульные возможности.
- **Patch**: фиксы скриптов, стоп-слова, промпты.

См. `CHANGELOG.md`. Совместимость: v1-пути `prompts/*`, `templates/*` — симлинк-шимы до v3.

## Безопасность

- Конфиг **не содержит секретов** — только имена env-vars (`api_key_env: NEURON_API_KEY`).
- Значения ключей — в macOS Keychain (`ai-secret set/run`); `.env` с значениями в проекте — нарушение политики (legacy переносится `ai-secret import`).
- API-ключи **не передаются** в LLM-промпты — только в env дочерних процессов прямых API-вызовов.
- Browser MCP сессии — на стороне пользователя; скилл не видит cookies/пароли.
- Секрет-скан обязателен перед коммитом проекта (`scripts/secret-scan.py` из состава attach или проектный).
