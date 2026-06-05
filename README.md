# seo-cycle

**Версия 1.27.0** · универсальный SEO/контент-цикл-оркестратор для Claude Code и Codex CLI.

Полный цикл продвижения сайта — от стратегии и сбора семантики до публикации, fact-check, мониторинга и итераций — управляемый через декларативный конфиг `seo-cycle.yaml`. Адаптируется под любой проект: язык, регион, поисковики, тип сайта, CMS, набор источников.

---

## TL;DR

```bash
# Установка одной командой (Codex + Claude): clone + deps + симлинки
curl -sL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/install-codex.sh | bash

# затем в корне своего проекта:
cd <свой-проект>
~/.claude/skills/seo-cycle/scripts/init-project.sh        # wizard → seo-cycle.yaml + policy templates
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py
python3 ~/.claude/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write
python3 ~/.claude/skills/seo-cycle/scripts/project-profile.py --write
python3 ~/.claude/skills/seo-cycle/scripts/setup-control-plane.py --write
python3 ~/.claude/skills/seo-cycle/scripts/task-router.py --task "аудит индексации и robots" --write
python3 ~/.claude/skills/seo-cycle/scripts/usage-ledger.py report --write
python3 ~/.claude/skills/seo-cycle/scripts/tool-stack-recommender.py --write
python3 ~/.claude/skills/seo-cycle/scripts/growth-roadmap.py --write
python3 ~/.claude/skills/seo-cycle/scripts/setup-onboarding.py --write
python3 ~/.claude/skills/seo-cycle/scripts/automation-recommender.py --write
python3 ~/.claude/skills/seo-cycle/scripts/governance-report.py --format md
python3 ~/.claude/skills/seo-cycle/scripts/automation-plan.py --write --include-disabled
# дальше в Claude Code / Codex: «запусти SEO-цикл для категории X»
```

Установщик создаёт каноническое ядро в `~/.claude/skills/seo-cycle`, симлинки `~/.codex/skills/seo-cycle` и `~/.codex/skills/codex-primary-runtime`, а проектный wizard создаёт `AGENTS.md` и безопасные policy-файлы для NeuronWriter, Google NLP, tracking/data access, robots/Content-Signal, token/budget governance и автоматизаций.

Ручная установка и Codex-режим (AGENTS.md, SEO_RUNTIME) — в [INSTALL.md](INSTALL.md) и [docs/codex-runtime.md](docs/codex-runtime.md).

📖 **Полное руководство (RU + EN, подробно по каждому инструменту, фазе, команде, + инструкции для ИИ-автоустановки): [GUIDE.md](GUIDE.md)**

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
| **Источники семантики** | Яндекс (Wordstat/Suggest/SERP/Вебмастер/Кью/Карты/Товары), Google (GSC/Trends/Suggest/Merchant/Business Profile), Bing Webmaster/IndexNow/Bing Places, Serpstat (вкл. РФ `g_ru`), SpyFu (US/UK/EU), NeuronWriter, LLM-CLI, AnswerThePublic, Perplexity. |
| **Guarded NLP/entity audit** | `google-nlp-audit.py` для Google Cloud Natural Language: entity salience, categories, syntax, moderation/sentiment только по policy, кэш 30 дней и unit caps. |
| **Token/budget governance** | `governance` в `seo-cycle.yaml` + `governance-report.py`: raw на диск, distillates в контекст, cache-first, лимиты платных API/LLM/браузера/автоматизаций. |
| **Setup control plane** | `setup-control-plane.py --write` собирает intake/profile/sources/governance/validation/tool stack/growth roadmap/onboarding/automation/task route/usage ledger в `seo/setup/setup-control-plane.md/json` и next-action checklist. |
| **Low-token task routing** | `task-router.py --task "..."` строит точный маршрут под задачу: фазы, источники, approval gates, blocked actions, automation и context caps; пишет `seo/setup/latest-task-route.md/json`. |
| **Usage/budget ledger** | `usage-ledger.py report/check/record` ведёт append-only расход токенов, USD, credits, units, requests, browser minutes; пишет `seo/usage/usage-ledger.jsonl` и `seo/setup/latest-usage-ledger.md/json`. |
| **Tool-stack recommender** | `tool-stack-recommender.py --write` выбирает инструменты под страну/движки/тип бизнеса/бюджет: бесплатные read-only включает, платные API/LLM/IndexNow/ads/tracking ставит за approval, RF foreign tracking отключает. |
| **Growth roadmap** | `growth-roadmap.py --write` превращает intake/tool-stack/budget/automation в top-N действий по технике, search evidence, ecommerce/local, entities/content, AI visibility, CRO/маркетингу и automations. |
| **Setup onboarding** | `setup-onboarding.py --write` создаёт подробный playbook нового проекта: owner каждого шага, human-secret env names, approval gates, команды и proof-артефакты. |
| **Detailed intake wizard** | `project-intake-wizard.py` точечно заполняет страны, регионы, поисковики, тип бизнеса, аудитории, local/merchant/ads/video/analytics, tools и governance. |
| **Detailed project profile** | `project-profile.py` читает `seo/project-intake.yaml` и генерирует overlay/report для стран, поисковиков, регионов, local/merchant/ads/video/analytics, marketing и source overrides. |
| **Automation recommender** | `automation-recommender.py --write` рекомендует planned automations по intake/business/market/tools/budget и создаёт `seo/automation-policy.generated.yaml`; `--apply` только после review. |
| **Safe automations** | `automation-plan.py` генерирует `seo/automations/automation-plan.md`, `crontab.txt`, launchd plist templates; реальный install заблокирован без двойного policy-разрешения. |
| **Project policies** | `seo/neuronwriter-limits.yaml`, `seo/entities/google-nlp-policy.yaml`, `seo/tool-budget.yaml`, `seo/tool-stack.generated.yaml`, `seo/setup/tool-stack-report.md`, `seo/growth-roadmap.generated.yaml`, `seo/setup/growth-roadmap.md`, `seo/onboarding.generated.yaml`, `seo/setup/onboarding-playbook.md`, `seo/setup/onboarding-checklist.csv`, `seo/automation-policy.yaml`, `seo/automation-policy.generated.yaml`, `seo/automations/automation-recommendations.md`, `seo/usage/usage-ledger.jsonl`, `seo/setup/latest-usage-ledger.md`, `seo/project-intake.yaml`, `seo/project-intake-report.md`, `seo/project-profile.generated.yaml`, `seo/setup/setup-control-plane.md`, `seo/setup/latest-task-route.md`, `seo/seo-data-collection-map.md`, `seo/access-setup-runbook.md`, `seo/ai-visibility-prompts.csv`. |
| **E-E-A-T** | `schema-org-build.py` — канонический Organization/LocalBusiness узел из `business_profile`; `eeat-render.py` — trust-блок «Источники» из `fact_check_log`; `source-attribution.py` — какой источник даёт топ. |
| **Экономия** | `research-cache.py` (TTL), дистилляты в контекст, guard'ы кредитов Serpstat/SpyFu. |
| **Слой данных** | `db-sync.py` → `seo.db` (SQLite) из всех CSV/JSON. Фундамент дашбордов. |
| **Уведомления** | `notify.py` — Telegram без n8n, graceful no-op без токена. |
| **Автоматизация** | `monthly-runner.sh` (cron, auto-detect по дате) + `approval-gate.py` + `keyword-queue.py`. `monthly-runner.sh all` — по всем проектам реестра. |
| **Масштаб** | `projects-registry.yaml` + `init-project.sh` — новый проект одной командой. |
| **Публикация** | CMS-aware (WordPress/Woo через REST в emwoody-примере). |

---

## Runtime: Claude и Codex (двойной режим)

Скилл рассчитан на **любой из двух «мозгов»** (`runtime: auto|claude|codex` / env `SEO_RUNTIME`):

- **Claude Code** — точка входа `SKILL.md`. Делегирование — subagents; изображения/браузер — через `codex exec`-обёртки и Claude in Chrome MCP.
- **Codex CLI** — точка входа `AGENTS.md` (симлинк на `SKILL.md`). **Гибрид:** наши скрипты для уникального (РФ-источники, Serpstat/SpyFu, кэш, публикация) + нативные Codex-skills для изображений (`seo-image-gen`/`image`/`sora`), браузера (`browser`/`playwright`) и делегирования (`dispatching-parallel-agents`). Без `codex exec` самовызовов.

Логика 10 фаз идентична; различается механика вызова инструментов. Маппинг и детали — [docs/codex-runtime.md](docs/codex-runtime.md). Один источник правды, без дублирования.

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
├── codex-primary-runtime/ # отдельный Codex-first entrypoint skill
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
├── templates/          # шаблоны артефактов + project-policies
└── docs/               # architecture, adapt, codex-runtime, obsidian, ...
```

---

## Шаринг

Каталог самодостаточен, секретов нет (ключи — только в `.env` проектов). Git / zip / Claude-plugin — см. [INSTALL.md](INSTALL.md) → «Как поделиться скиллом».

Лицензия: личное использование (укажи свою при публикации).
