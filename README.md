# seo-cycle

**Версия 1.3.0** · универсальный SEO/контент-цикл-оркестратор для Claude Code и Codex CLI.

Полный цикл продвижения сайта — от стратегии и сбора семантики до публикации, fact-check, мониторинга и итераций — управляемый через декларативный конфиг `seo-cycle.yaml`. Адаптируется под любой проект: язык, регион, поисковики, тип сайта, CMS, набор источников.

---

## TL;DR

```bash
pip3 install pyyaml requests
cd <свой-проект>
~/.claude/skills/seo-cycle/scripts/init-project.sh        # wizard → seo-cycle.yaml
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py
# дальше в Claude Code / Codex: «запусти SEO-цикл для категории X»
```

Подробная установка — [INSTALL.md](INSTALL.md). История изменений — [CHANGELOG.md](CHANGELOG.md).

---

## Почему так устроено (философия)

Принцип: **разделить «мозг» и «руки»**.

- **Мозг — LLM (Claude или Codex) в среде скилла.** Рассуждения: entity map по Шестакову, написание текстов, fact-check решения, stock-first логика, оценка качества. Это **нельзя** заменить no-code/workflow-движком — они не рассуждают.
- **Руки — Python/bash-скрипты.** Детерминированная работа: сбор данных по API, кэш, публикация, агрегация. Дёшево, версионируемо, тестируемо.
- **Конфиг — единая точка правды.** `seo-cycle.yaml` описывает проект; один и тот же код работает для РФ-строймага и англоязычного SaaS — разница только в конфиге.

Следствия, заложенные в дизайн:
- **Экономия токенов.** Сырьё research → на диск, в контекст LLM — только дистилляты (`*-merged-*.md`). Кэш с TTL не даёт повторно жечь дорогой сбор. Тяжёлая специфика — в `reference/`, грузится по необходимости (progressive disclosure).
- **Универсальность по регионам.** `region_profile` одной строкой переключает набор источников: РФ → Яндекс-стек + доступные из РФ инструменты; запад → Google + западные SaaS. Недоступные в регионе инструменты не запускаются.
- **Бережёт платные лимиты.** Клиенты API (Serpstat, SpyFu) имеют guard'ы остатка кредитов/бюджета и кэш.

---

## Архитектура

```
┌─ LLM-ядро (Claude Skill tool / Codex) ── РАССУЖДЕНИЯ ─┐
│  entity map · написание · fact-check · QA · решения    │
└────────────────────────────────────────────────────────┘
        ↓ дёргает скрипты            ↓ пишет артефакты
┌─ Скрипты-руки (scripts/) ─────────────────────────────┐
│  resolve-sources · *-fetch (serpstat/spyfu/gsc/...)    │
│  *-suggest · llm-cli-collect · *-publish · db-sync      │
└────────────────────────────────────────────────────────┘
        ↓ единый слой данных          ↓ алерты
┌─ seo.db (SQLite) ──┐   ┌─ notify.py (Telegram) ────────┐
│ positions · usage   │   │ approval · ошибки · кредиты    │
│ queue · attribution │   └────────────────────────────────┘
└─────────────────────┘        ↓ визуализация
                          Obsidian-дашборд (авто из db-sync)
```

10 фаз: discovery → audit → keyword research (multi-source) → cluster+intent → Entity Map → content plan → writing → publishing → JSON-LD/schema → monitoring → iteration. Полное описание фаз — в [SKILL.md](SKILL.md).

---

## Возможности

| Область | Что есть |
|---|---|
| **Региональные профили** | `config/region-profiles/{ru,eu,us,global}.yaml` — пресет источников + флаги доступности. `resolve-sources.py` разворачивает в активный список. |
| **Источники семантики** | Яндекс (Wordstat/Suggest/SERP/Вебмастер/Кью/Карты), Google (GSC/Trends/Suggest), Serpstat (вкл. РФ `g_ru`), SpyFu (US/UK/EU), NeuronWriter, LLM-CLI (Antigravity+Codex, deep-режим), AnswerThePublic, Perplexity (Deep Research). |
| **E-E-A-T** | `schema-org-build.py` — канонический Organization/LocalBusiness узел из `business_profile`; `eeat-render.py` — trust-блок «Источники» из `fact_check_log`; `source-attribution.py` — какой источник даёт топ. |
| **Экономия** | `research-cache.py` (TTL), дистилляты в контекст, guard'ы кредитов Serpstat/SpyFu. |
| **Слой данных** | `db-sync.py` → `seo.db` (SQLite) из всех CSV/JSON. Фундамент дашбордов. |
| **Уведомления** | `notify.py` — Telegram без n8n, graceful no-op без токена. |
| **Автоматизация** | `monthly-runner.sh` (cron, auto-detect по дате) + `approval-gate.py` + `keyword-queue.py`. `monthly-runner.sh all` — по всем проектам реестра. |
| **Масштаб** | `projects-registry.yaml` + `init-project.sh` — новый проект одной командой. |
| **Публикация** | CMS-aware (WordPress/Woo через REST в emwoody-примере). |

---

## Runtime: Claude и Codex (двойной режим)

Скилл рассчитан на **любой из двух «мозгов»**:

- **Claude Code** — точка входа `SKILL.md` (Skill tool распознаёт по frontmatter). Делегирование — через subagents.
- **Codex CLI** — точка входа `AGENTS.md` (симлинк на `SKILL.md` — один и тот же контент). Отличия запуска (codex exec, делегирование, headless) — в [docs/codex-runtime.md](docs/codex-runtime.md).

Логика фаз идентична; различается только механика вызова инструментов. Один источник правды, без дублирования.

---

## Версионирование

[SemVer](https://semver.org): `MAJOR.MINOR.PATCH`. Текущая — в файле [VERSION](VERSION), история — в [CHANGELOG.md](CHANGELOG.md).

- **MAJOR** — несовместимые изменения схемы `seo-cycle.yaml` или структуры скилла.
- **MINOR** — новые источники/фазы/скрипты (обратная совместимость).
- **PATCH** — фиксы, доки.

Каждый релиз тегается в git (`v1.3.0`).

---

## Roadmap совершенствований

- **Этап 2 (агентство):** n8n self-hosted как слой триггеров/вебхуков/retry поверх скриптов; read-only дашборд (Metabase поверх `seo.db`).
- **Этап 3 (SaaS):** Next.js + multi-tenant + биллинг — только при подтверждённом спросе.
- **Источники:** Я.Маркет competitor-парсер; webhook-приём GSC/Вебмастер для near-real-time алертов.
- **E-E-A-T:** автоген `reviewedBy`/Person при появлении реальных авторов-экспертов.
- **Атрибуция:** автоотключение слабых источников в профиле по данным `source-attribution.py`.
- **Тесты:** smoke-тесты скриптов (pytest) для CI при шаринге.

(Полный архитектурный разбор «n8n vs Next.js vs CLI» — в истории проекта emwoody, план `immutable-leaping-stearns.md`.)

---

## Структура

```
seo-cycle/
├── SKILL.md            # точка входа Claude (frontmatter + 10 фаз)
├── AGENTS.md           # точка входа Codex (симлинк → SKILL.md)
├── README.md           # этот файл
├── INSTALL.md          # установка под новый проект
├── CHANGELOG.md        # история версий
├── VERSION             # текущая версия (SemVer)
├── .env.example        # шаблон ключей
├── config/
│   ├── project.template.yaml
│   ├── region-profiles/{ru,eu,us,global}.yaml
│   ├── projects-registry.yaml
│   └── triggers.yaml
├── scripts/            # все переносимые скрипты
├── prompts/            # промпты (Perplexity и др.)
├── templates/          # шаблоны артефактов
└── docs/               # architecture, adapt, codex-runtime, obsidian, ...
```

---

## Шаринг

Каталог самодостаточен, секретов нет (ключи — только в `.env` проектов). Git / zip / Claude-plugin — см. [INSTALL.md](INSTALL.md) → «Как поделиться скиллом».

Лицензия: личное использование (укажи свою при публикации).
