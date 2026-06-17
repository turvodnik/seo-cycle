# Архитектура skill `seo-cycle`

## Принципы

1. **Config-driven** — все решения зависят от `seo-cycle.yaml` проекта. Один кодовый базис для всех проектов.
2. **Source-flexible** — источники данных (Wordstat, GSC, NW, ATP, LLM CLI, Perplexity) включаются независимо. Скилл пропускает то, что не enabled.
3. **CMS-agnostic** — публикация делегируется проектным скиллам через `delegate.*`. Универсальный скилл сам не пишет в CMS — он оркестратор.
4. **LLM-агностичный** — каждый шаг с LLM можно выполнить через Claude (внутри сессии), либо через external CLI (Antigravity, Codex), либо через Perplexity Pro. Выбор по доступности и задаче.
5. **Идемпотентный** — повторный запуск той же фазы не ломает артефакты, а обновляет их с timestamp.
6. **Stage-gated** — новый v1.63 слой не заменяет старые команды, а оборачивает их в явный контракт `stage -> gate -> repair -> rerun -> next stage`.

## Поток управления

```
Пользователь
    ↓
Клод определяет: «нужен seo-cycle» (по триггерам из SKILL.md description)
    ↓
Phase 0 — найти seo-cycle.yaml → если нет, INSTALL wizard
                              → если есть, validate
    ↓
Phase 1 ← подключённые в config delegate.audit агенты
Phase 2 ← по списку sources.*.enabled (Wordstat → Suggest → ATP → LLM CLI → Perplexity → ...)
Phase 3 ← delegate.cluster_analysis
Phase 4 ← delegate.semantic_brief (использует ~/.codex/skills/seo-cycle/templates/entity-map.template.md как fallback)
Phase 5 ← delegate.content_strategy
Phase 6 ← delegate.content_writer + quality gates (stop-words, fact-check, NW)
Phase 7 ← delegate.publish_skills[<type>] (project-specific CMS handler)
Phase 8 ← delegate.schema_markup
Phase 9 ← delegate.google_data + delegate.yandex_specialist
Phase 10 ← сам скилл + проектные lessons learned
```

## v1.63 staged orchestrator

`scripts/seo-cycle-run.py` — пилотный Pifagor SEO skill wrapper. Он читает JSON/YAML stage contracts или строит короткий план из `--goal`, затем передаёт стадии в `scripts/seo_cycle_core/orchestrator.py`.

Минимальный контракт стадии:

```yaml
stages:
  - id: research_quality
    title: Research package quality
    required_inputs:
      - seo/research-package/semantic-architecture-final.json
    commands:
      - ["python3", "./.codex/skills/seo-cycle/scripts/research-package-quality.py", "seo/research-package", "--write"]
    outputs:
      - seo/research-package/research-package-quality.json
    gate: {}
    repair_commands:
      - ["python3", "./.codex/skills/seo-cycle/scripts/research-package-repair.py", "seo/research-package", "--write"]
    max_attempts: 5
    stop_conditions:
      - Reviewed SERP evidence is still missing.
    next_stage: deep_page_briefs
```

Поля контракта:

- `required_inputs` проверяются до запуска стадии; если их нет, стадия сразу `blocked`.
- `commands` выполняют основную работу стадии.
- `outputs` используются как output-gate, если `gate.command` не задан.
- `gate.command` решает, можно ли идти дальше; по умолчанию успешен только exit code `0`.
- `repair_commands` запускаются после проваленного gate.
- `max_attempts` — число repair-попыток, по умолчанию `5`.
- `approval_required` останавливает стадию до ручного `--approve`.
- `stop_conditions` попадают в blocker report, когда цикл исчерпан.

Артефакты:

- `seo/orchestrator/latest-run.md/json` — сводка всего запуска.
- `seo/orchestrator/<stage>-report.md/json` — полный stage report.
- `seo/orchestrator/<stage>-blocker.md/json` — отдельный blocker report, если gate не прошёл.

## Структура файлов скилла

```
~/.codex/skills/seo-cycle/
├── SKILL.md                          # entry-point, orchestrator instructions
├── INSTALL.md                        # setup wizard для нового проекта
├── CHANGELOG.md                      # история изменений
├── config/
│   └── project.template.yaml         # эталонный шаблон проектного конфига
├── prompts/                          # универсальные промпт-шаблоны
│   ├── fact-check.md
│   ├── entities-extract.md
│   ├── semantic-core-llm.md
│   ├── serp-news.md
│   └── (deep-research.md — для будущего)
├── scripts/                          # переносимые скрипты
│   ├── validate-config.py            # валидатор seo-cycle.yaml
│   ├── check-stop-words.py           # детектор стоп-слов (RU+EN+morphology)
│   ├── yandex-suggest.py             # Яндекс Suggest API
│   ├── google-suggest.py             # Google Suggest API
│   ├── atp-fetch.py                  # AnswerThePublic API клиент
│   ├── llm-cli-collect.sh            # параллельный Antigravity + Codex
│   └── llm-cli-merge.py              # дедуп результатов
├── templates/                        # шаблоны артефактов
│   ├── entity-map.template.md
│   ├── stop-words.md                 # документация правил
│   └── (cycle-plan.template.md — для будущего)
└── docs/
    ├── architecture.md               # этот файл
    ├── adapt.md                      # адаптация под проекты
    ├── migration.md                  # миграция с emwoody-seo-cycle
    └── troubleshooting.md            # FAQ
```

## Структура проекта (что появляется после установки)

```
<project>/
├── seo-cycle.yaml                    # КОНФИГ — единственный обязательный файл
├── .env                              # API ключи (gitignore!)
├── CLAUDE.md                         # правила проекта (опционально)
├── seo/
│   ├── cycles/                       # снапшоты циклов
│   │   └── <topic>-<YYYY-Qx>/
│   │       ├── 00-discovery.md
│   │       ├── 01-audit.md
│   │       ├── 02-keywords.md
│   │       ├── 03-clusters.md
│   │       ├── 04-entity-maps/
│   │       ├── 05-content-plan.md
│   │       ├── 06-drafts/
│   │       ├── 07-published.md
│   │       ├── 08-schema.md
│   │       ├── 09-monitoring/
│   │       └── 10-iterations.md
│   ├── entities/
│   │   └── entities.yaml             # реестр сущностей проекта
│   ├── research/
│   │   ├── perplexity/
│   │   │   ├── prompts/              # доп. промпты под нишу проекта
│   │   │   └── results/              # результаты прогонов
│   │   ├── atp/results/
│   │   └── llm-cli/results/
│   ├── prompts/                      # (опционально) override универсальных
│   └── publish-log.csv               # лог публикаций
├── blog/                             # черновики статей
├── categories/                       # черновики категорий
└── .claude/
    └── skills/                       # ПРОЕКТНЫЕ субскиллы
        ├── <project>-semantic-brief/
        └── <project>-publish-*/
```

## Делегирование (`delegate.*`)

Универсальный скилл делегирует специфичные задачи. В `seo-cycle.yaml`:

```yaml
delegate:
  semantic_brief: emwoody-semantic-brief          # проектный
  audit: seo-auditor                               # глобальный агент
  keyword_research: seo-keyword-researcher
  content_writer: seo-content-writer
  yandex_specialist: yandex-seo-specialist
  google_data: "claude-seo:seo-google"             # plugin skill
  schema_markup: "claude-seo:seo-schema"
```

Если делегат не указан — используется fallback из `~/.codex/skills/seo-cycle/templates/`:
- `templates/entity-map.template.md` — для Phase 4
- `templates/cycle-plan.template.md` — для Phase 5 (TBD)

## Точки расширения

| Расширение | Где |
|---|---|
| Новый источник данных | `sources.*` в конфиге + (опц.) скрипт в `scripts/` |
| Новый CMS | `publishing.publish_skills.*` + проектный publish-скилл |
| Новый язык стоп-слов | Добавить `XX_PATTERNS` в `check-stop-words.py` + PR |
| Новая ниша с особыми правилами | `content_rules.*` + проектные субскиллы для проверок |
| Новый LLM провайдер | Скрипт в `scripts/` по образцу `llm-cli-collect.sh` |
| Новый тип schema | `templates/schema-<type>.template.jsonld` + handler в Phase 8 |

## Версионирование

- **Major**: ломающие изменения в схеме `seo-cycle.yaml` (миграция конфигов)
- **Minor**: новые источники, новые delegate-цели, расширение фаз
- **Patch**: фиксы скриптов, доп. стоп-слова, доп. промпт-шаблоны

См. `CHANGELOG.md`.

## Безопасность

- Конфиг **не содержит секретов** — только имена env-vars (`api_key_env: NEURON_API_KEY`)
- `.env` проекта — обязательно в gitignore
- API ключи **не передаются** в LLM промпты — только используются для прямых API вызовов
- Browser MCP сессии — на стороне пользователя, скилл не видит cookies / paswords
