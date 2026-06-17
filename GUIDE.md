<!--
  GUIDE.md — полное руководство по skill `seo-cycle`.
  СНАЧАЛА РУССКАЯ ВЕРСИЯ, НИЖЕ — ПОЛНЫЙ АНГЛИЙСКИЙ ПЕРЕВОД (раздел "English").
  ПРАВИЛО: при ЛЮБОМ изменении кода/конфига/возможностей — обновляй этот файл
  (обе языковые версии) и CHANGELOG.md в том же коммите.
-->

# seo-cycle — полное руководство 🇷🇺

> Универсальный SEO/контент-цикл-оркестратор для **Claude Code** и **Codex CLI**.
> Один фреймворк ведёт сайт от стратегии и сбора семантики до публикации,
> fact-check, мониторинга и итераций. Адаптируется под любой проект через
> декларативный конфиг `seo-cycle.yaml`.

Содержание: [Что это](#что-это) · [Преимущества](#преимущества) · [Установка](#установка) · [Для ИИ](#установка-ии) · [Архитектура](#архитектура) · [Рантаймы](#рантаймы) · [Политики проекта](#политики-проекта) · [Инструменты](#инструменты) · [10 фаз](#фазы) · [Агенты](#агенты) · [Команды](#команды) · [Сценарии](#сценарии) · [Обновление доков](#обновление-доков)

---

## <a id="что-это"></a>1. Что это

`seo-cycle` — это **скилл** (набор инструкций + скриптов), который превращает LLM-ассистента (Claude или Codex) в полноценного SEO-специалиста для конкретного сайта. Он:

- собирает семантику из 10+ источников (Яндекс, Google, XMLRiver, Serpstat, SpyFu, NeuronWriter, WriterZen browser/export, LLM-CLI, AnswerThePublic, Perplexity);
- всегда использует Antigravity CLI и Perplexity Deep Research для сбора семантики, сущностей и фактчекинга перед публикацией, если инструменты доступны;
- строит карту сущностей (методика Шестакова), кластеры, контент-план;
- пишет тексты с учётом tone of voice, stock-first, локальных сигналов;
- проверяет факты (fact-check) и формирует E-E-A-T-сигналы;
- публикует в CMS (WordPress/WooCommerce);
- мониторит позиции и выдаёт приоритизированные доработки;
- работает по расписанию (cron) с человеческими approval-точками.

**Принцип:** «мозг» (рассуждения) — у LLM, «руки» (детерминированные операции) — у скриптов, «правда о проекте» — в одном конфиге.

---

## <a id="преимущества"></a>2. Преимущества

| Преимущество | Как достигается |
|---|---|
| **Универсальность** | Один код для РФ/ЕС/США/глобал — отличия в `region_profile` (1 строка). |
| **Экономия токенов** | Сырьё research → на диск; в контекст LLM — только дистилляты. Кэш с TTL не даёт жечь повторный сбор. |
| **Работает в РФ** | Региональный профиль `ru`: Яндекс-стек + Serpstat (`g_ru`) + доступные из РФ Google-инструменты; недоступное (Ahrefs/SEMrush) не запускается. |
| **Бережёт платные лимиты** | Клиенты Serpstat/SpyFu/XMLRiver имеют guard'ы остатка кредитов/бюджета и кэш. |
| **Двойной рантайм** | Работает и под Claude Code, и под Codex CLI (гибрид: наши скрипты + нативные skills). |
| **E-E-A-T из коробки** | Канонический Organization/LocalBusiness-узел, trust-блок источников, атрибуция источник→топ. |
| **Масштаб на N проектов** | Реестр проектов + `init-project.sh` + `monthly-runner.sh all`. |
| **Контроль токенов и бюджета** | `governance` + `tool-budget.yaml` + `governance-report.py`: cache-first, raw на диск, distillates в контекст, approval gates. |
| **Маршрут под задачу** | `task-router.py --task "..."`: выбирает только нужные фазы/источники, показывает approval gates, blocked actions, automation и context caps. |
| **Фактический расход** | `usage-ledger.py report/check/record`: append-only учёт токенов, USD, requests, credits, units, browser minutes и подписок. |
| **Spend guard** | `spend-guard.py --write`: allowed/approval/blocked по paid/API/LLM/subscription сервисам, остатки лимитов, reserves и preflight-команды. |
| **Стек инструментов под проект** | `tool-stack-recommender.py --write`: Google/Yandex/Bing/Microsoft/NLP/AI/merchant/local/ads/tracking решения по стране, бизнесу, бюджету и RF policy. |
| **Growth roadmap** | `growth-roadmap.py --write`: top-N roadmap по технике, search evidence, ecommerce/local, entities/content, AI visibility, CRO/маркетингу и automation gates. |
| **Onboarding playbook** | `setup-onboarding.py --write`: подробный first-run checklist с owner, human-secret env names, approval gates, командами и proof-файлами. |
| **Setup blueprint** | `setup-blueprint.py --write`: компактная матрица стран, регионов, поисковиков, типа бизнеса, marketing/ads/tracking policy, tools, budgets, subscriptions, automations и guardrails. |
| **Upgrade/access assistants** | `project-upgrade-assistant.py --write` и `access-key-assistant.py --write`: review-only обновление старых проектов и project-specific список нужных ключей/токенов без secret values. |
| **Safe upgrade apply** | `project-upgrade-apply.py --write`: dry-run/apply reviewed missing `policy_files` для старых проектов с backup, без секретов и без включения платных/опасных действий. |
| **Launch plan** | `launch-plan.py --write`: первый экран проекта с market/business matrix, token/budget/subscription controls, tool packs, env names, approval gates и execution order. |
| **Project journey** | `project-journey.py --write`: текущая стадия пути от старта до цели, missing artifacts/blockers, next command и exit criteria для перехода дальше. |
| **Context pack** | `context-pack.py --task "..." --write`: первый короткий файл для Claude/Codex с `context_manifest`, read order, task route, caps, spend blockers, approval gates и do-not-load-raw. |
| **Token/provider evidence** | `token-waste-audit.py`, `perplexity-health.py`, `notebooklm-health.py`, `xmlriver-health.py`, `writerzen-health.py`, `perplexity-collect.py`, `notebooklm-source-pack.py`, `xmlriver-source-pack.py`, `writerzen-browser-collect.py`, `writerzen-source-pack.py`: проверка raw/large артефактов, provider health и запись raw/distillate/vector source packs без хранения паролей. WriterZen browser collector сам создаёт отчёты, ловит downloads и импортирует их в distillates. |
| **Автоматизации под проект** | `automation-recommender.py --write`: рекомендует tool-aware planned automations по типу бизнеса, рынку, tool-stack/spend-guard, indexability, search consoles, Bing, schema/CWV, content decay, ecommerce/local и AI visibility. |
| **Прозрачность** | Все артефакты — файлы в репозитории проекта; единая SQLite-БД; Obsidian-дашборд. |

---

## <a id="установка"></a>3. Установка (для человека)

```bash
# Codex-first: одна команда из корня СВОЕГО проекта
cd /path/to/your-project
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash

# Claude Code variant:
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-claude.sh | bash

# Bootstrap сам ставит ядро, зависимости, symlinks, запускает wizard,
# создаёт seo-cycle.yaml, .env.example, .env, AGENTS.md/CLAUDE.md и setup reports.

# Существующий проект: обновить shared core и пересобрать локальную setup-поверхность
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash -s -- --skip-init
python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-control-plane.py --write
```

Shared core: `~/.codex/vendor/seo-cycle`. Project-local entrypoints are created only by bootstrap: `./.codex/skills/seo-cycle`, `./.agents/skills/seo-cycle`, `./.claude/skills/seo-cycle` symlink to that shared core. Projects that were not bootstrapped do not load seo-cycle.

**Что выдаёт `validate-config.py`:** список активных источников (с учётом `region_profile`), список недостающих env-переменных, предупреждения о несуществующих делегатах/путях/policy-файлах/governance, итог ✓/ошибки.

Перед дорогим сбором, браузерной сессией, публикацией или schedule:
```bash
python3 ./.codex/skills/seo-cycle/scripts/task-router.py --task "собрать семантику по теме X" --write
python3 ./.codex/skills/seo-cycle/scripts/context-pack.py --task "собрать семантику по теме X" --write
python3 ./.codex/skills/seo-cycle/scripts/usage-ledger.py check --service openai --category llm --usd 0.25 --fail-on-block
python3 ./.codex/skills/seo-cycle/scripts/spend-guard.py --write
python3 ./.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write
python3 ./.codex/skills/seo-cycle/scripts/growth-roadmap.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-onboarding.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-blueprint.py --write
python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write
python3 ./.codex/skills/seo-cycle/scripts/access-key-assistant.py --write
python3 ./.codex/skills/seo-cycle/scripts/launch-plan.py --write
python3 ./.codex/skills/seo-cycle/scripts/automation-recommender.py --write
python3 ./.codex/skills/seo-cycle/scripts/governance-report.py --format md
```

---

## <a id="установка-ии"></a>4. Установка для ИИ-агента (самостоятельная)

> Этот раздел — машинно-исполнимый сценарий. ИИ-агент (Claude/Codex/любой) может выполнить его сам, по шагам, без участия человека (кроме ввода секретных ключей).

```bash
# Codex-first bootstrap: ставит ядро, зависимости, symlinks и запускает wizard.
cd <project-root>
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash

# Claude Code variant:
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-claude.sh | bash

# После bootstrap человек заполняет только секреты в .env.
```

**Правила для ИИ-агента (самопроверка перед работой):**
1. Прочитай `SKILL.md` (или `AGENTS.md` для Codex) — это логика 10 фаз.
2. Прочитай `seo-cycle.yaml` проекта — это правила/источники/локаль.
3. Прочитай `CLAUDE.md` проекта (если есть) — проектные правила (tone, stock-first, fact-check).
4. Запусти `resolve-sources.py` — узнай, какие источники активны.
5. Никогда не тяни в контекст сырьё research — только `*-merged-*.md` и `02-keywords.md`.
6. В Codex-режиме не вызывай `codex exec` сам в себе — используй нативные skills (см. `docs/codex-runtime.md`).

---

## <a id="архитектура"></a>5. Архитектура

```
┌─ LLM-ядро (Claude Skill tool / Codex) ── РАССУЖДЕНИЯ ─┐
│  entity map · написание · fact-check · QA · решения    │  ← не переносится в скрипты
└────────────────────────────────────────────────────────┘
        ↓ вызывает                      ↓ пишет артефакты
┌─ Скрипты-руки (scripts/) ─────────────────────────────┐
│  сбор · кэш · публикация · агрегация · уведомления      │
└────────────────────────────────────────────────────────┘
        ↓ единый слой данных            ↓ алерты
┌─ seo.db (SQLite) ──┐   ┌─ notify.py (Telegram) ────────┐
└─────────────────────┘   └────────────────────────────────┘
        ↓ визуализация
   Obsidian-дашборд (авто из db-sync)
```

- **Конфиг — единый источник правды.** `seo-cycle.yaml`: locale, `region_profile`, `runtime`, источники, `business_profile`, tone, publishing, delegate-мапа.
- **Региональный профиль** (`config/region-profiles/{ru,eu,us,global}.yaml`) переключает набор источников одной строкой.

---

## <a id="рантаймы"></a>6. Рантаймы: Claude и Codex

Режим задаётся `runtime: auto|claude|codex` в конфиге или `SEO_RUNTIME` в env.

| | Claude Code | Codex CLI |
|---|---|---|
| Точка входа | `SKILL.md` | `AGENTS.md` (симлинк → `SKILL.md`) |
| Изображения | `codex exec` обёртка | нативный `seo-image-gen`/`image`/`sora` |
| Браузер (Perplexity/Wordstat/Вебмастер) | Claude in Chrome MCP | `browser`/`playwright`/`screenshot` |
| Делегирование | subagents (`Agent`) | `dispatching-parallel-agents` |
| Наши скрипты | через bash | через bash (одинаково) |

Запуск под Codex:
```bash
cd <проект>
export SEO_RUNTIME=codex
codex exec -c model_reasoning_effort="xhigh" -c web_search="live" \
  "Прочитай AGENTS.md и seo-cycle.yaml. Запусти Phase 2 для кластера X."
```
Полный маппинг — [docs/codex-runtime.md](docs/codex-runtime.md).

---

## <a id="модульность"></a>6b. Модульная архитектура (фазовые скиллы + state)

`seo-cycle` — **диспетчер**. Фазы постепенно выносятся в самостоятельные **фазовые скиллы** (каждый — папка `SKILL.md` + README, можно дёргать независимо, шарить и продавать отдельно). Координация — через единый файл состояния `seo/cycles/<тема>/_state.json` (контракт `cycle-state.py`). Это «цепочка передачи»: фазовый скилл читает state → делает своё → обновляет state → разблокирует следующую фазу.

**Вынесено (пилот):** `seo-keywords` (Phase 2-3). **Статус: дробление заморожено** (решение 2026-05-30) — монолитный `seo-cycle` основной; остальные фазы не выносим без явной потребности (продажа модулей / команда / переиспользование / параллелизм).

**v1.63 Pifagor orchestrator pilot:** старые команды остаются рабочими, но новый тонкий слой `seo-cycle-run.py` умеет читать контракт стадии и выполнять цикл `stage -> gate -> repair -> rerun -> next stage`. Это не автономное переписывание проекта, а контрольный каркас: каждая стадия явно объявляет входы, команды, ожидаемые outputs, gate-команду или output-gate, repair-команды, `max_attempts` (по умолчанию 5), approval flag, stop conditions и `next_stage`. Отчёты пишутся в `seo/orchestrator/`; если gate не проходит после лимита, появляется blocker report.

```bash
python3 ./.codex/skills/seo-cycle/scripts/cycle-state.py init --topic "минвата"
python3 ./.codex/skills/seo-cycle/scripts/cycle-state.py next      # разблокированные фазы
# → вызвать соответствующий фазовый скилл (seo-keywords и т.д.)
python3 ./.codex/skills/seo-cycle/scripts/cycle-state.py gate keywords
python3 ./.codex/skills/seo-cycle/scripts/cycle-state.py show      # прогресс

# Новый v1.63 pilot без отдельного stage-файла:
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --goal "собрать research package" --write
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --stage-template setup-readiness --goal "first SEO setup" --write
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --stage-template research-package --package seo/research-package --write
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --stage-template copywriting --draft seo/research-package/drafts/sample.md --write
python3 ./.codex/skills/seo-cycle/scripts/stage-template-export.py --write

# Контрактный запуск из JSON/YAML:
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --stage-file seo/stages/research-package.yaml --write
```

Преимущества дробления: переиспользование (фаза вне цикла), ясность/контроль (видно прогресс и gate'ы), параллельность (независимые фазы разом), продажа (модуль = отдельный продукт). «Улучшение» — на данных (`source-attribution.py` + `triggers-eval.py`), без авто-переписывания кода.

---

## <a id="политики-проекта"></a>6c. Локальные политики проекта

Перед запуском фаз, API-запросов, расходом кредитов или изменением tracking/indexing поведения прочитай project-local policy файлы, если они есть:

- `seo/neuronwriter-limits.yaml` — тариф NeuronWriter, остатки, резерв, reset, разрешённый расход автоматизации.
- `seo/neuronwriter.md` — workflow NeuronWriter, project ID, helper-команды и scoring policy.
- `seo/entities/google-nlp-policy.yaml` — Google Cloud Natural Language: budget alert, cache TTL, per-run limits, unit caps, language restrictions.
- `seo/seo-data-collection-map.md` — разрешённые источники данных, AI visibility checks, ecommerce/product sources, tracking/tag policy.
- `seo/access-setup-runbook.md` — подключённые аккаунты, пропущенные платные сервисы, API notes, операционные ограничения.
- `seo/ai-visibility-prompts.csv` — стартовая очередь AI visibility запросов и evidence-полей для Google AI/Bing Copilot/Perplexity/OpenAI/Claude/Gemini/DeepSeek.
- `seo/tool-budget.yaml` — token/API/LLM/subscription caps, cache policy, stop conditions.
- `seo/tool-stack.generated.yaml` и `seo/setup/tool-stack-report.md` — выбранный/рекомендованный набор инструментов с решениями enabled/report-only/approval-required/disabled/not-applicable.
- `seo/growth-roadmap.generated.yaml` и `seo/setup/growth-roadmap.md` — top-N приоритетов по technical/search evidence/ecommerce/local/content/entities/AI visibility/CRO/automation.
- `seo/onboarding.generated.yaml`, `seo/setup/onboarding-playbook.md` и `seo/setup/onboarding-checklist.csv` — first-run checklist с владельцами шагов, human-secret env names, approval gates, командами и proof-файлами.
- `seo/setup-blueprint.generated.yaml`, `seo/setup/setup-blueprint.md` и `seo/setup/setup-matrix.csv` — low-token setup matrix по странам, регионам, поисковикам, типу бизнеса, marketing/ads/tracking policy, tools, budget/subscriptions, automations, guardrails и first-read файлам.
- `seo/setup/upgrade-assistant.md` и `seo/setup/upgrade-questionnaire.csv` — review-only worksheet для включения новых возможностей в существующих проектах.
- `seo/setup/project-upgrade-apply.md`, `seo/setup/project-upgrade-apply.json` и `seo/setup/project-upgrade-apply.csv` — safe updater для старых проектов: dry-run/apply reviewed missing `policy_files` keys с backup; применяет только с `--apply`.
- `seo/setup/access-key-assistant.md` и `seo/setup/access-key-assistant.csv` — список нужных ключей/токенов под конкретный проект: env names, ссылки и шаги без secret values.
- `seo/launch-plan.generated.yaml`, `seo/setup/launch-plan.md` и `seo/setup/launch-checklist.csv` — first-screen launch contract по market/business/tools/token/budget/subscriptions/approval/execution order.
- `seo/setup/project-journey.md`, `seo/setup/project-journey.json` и `seo/setup/project-journey-checklist.csv` — автоматический путь проекта: текущая стадия, missing artifacts, blockers, next command, exit criteria и action plan.
- `seo/orchestrator/latest-run.md/json`, `seo/orchestrator/*-report.md/json`, `seo/orchestrator/*-blocker.md/json` — v1.63 staged orchestrator: что запускалось, сколько gate/repair попыток было, какие outputs не найдены, какие stop conditions требуют ручного решения.
- `seo/research-package/research-package-quality.md`, `seo/research-package/research-package-quality.json` и `seo/research-package/research-package-action-plan.md` — quality gate и пошаговый action plan для site-level research package перед repair/writing.
- `seo/research-package/research-package-repair.md/json`, `seo/research-package/semantic-core.cleaned.csv`, `seo/research-package/semantic-core.rejected.csv`, `seo/research-package/semantic-core.resynced.csv`, `seo/research-package/entity_coverage.jsonl`, `seo/research-package/content-plan.orphan-backlog.csv`, `seo/research-package/serp-validation-plan.csv`, `seo/research-package/serp-validation-import.md/json`, `seo/research-package/spoke-opportunities.csv`, `seo/research-package/entity-graph-quality.md/json` — repair layer для findings сравнительного отчёта: очистка ядра, ресинхрон URL/cluster IDs, sync entity map, агрегация Google NLP, orphan backlog, план SERP-проверки, guarded импорт reviewed SERP export, phase-2 spokes и качество entity graph.
- `seo/research-package/page-outline-quality.md`, `seo/research-package/page-outline-quality.json` и latest copies — quality gate для MVP/P1 page briefs перед writing/design/schema/publishing.
- `<draft>.draft-quality-gate.md/json` — gate для готового markdown-черновика против `page-outline-v2`: missing H2/H3, unsafe first-person expertise, missing internal links, missing proof/source slots и FAQ mismatch.
- `seo/setup/context-pack.md` и `seo/setup/latest-context-pack.md` — first-read context pack под текущую задачу: `context_manifest`, read order, task route, caps, spend blockers, approval gates, do-not-load-raw и next commands.
- `seo/setup/token-waste-audit.md`, `seo/setup/perplexity-health.md`, `seo/setup/notebooklm-health.md`, `seo/setup/xmlriver-health.md`, `seo/setup/writerzen-health.md` — low-token/provider readiness: raw/large artifact findings, Perplexity persistent app/browser/API optional mode, NotebookLM MCP/export fallback, XMLRiver readiness/prices/capabilities, WriterZen browser/export readiness.
- `seo/research/raw/*`, `seo/research/distillates/*`, `seo/research/vector/source_pack.jsonl` — source evidence contract для Perplexity/NotebookLM/XMLRiver: raw хранится на диске, downstream context получает только distillates/latest-summary + citations.
- `seo/setup/setup-gap-audit.md`, `seo/setup/setup-questionnaire.md` и `seo/setup/setup-questionnaire.csv` — readiness score, missing fields и заполняемый worksheet по рынку, бизнесу, local/ecommerce, инструментам, budget/subscriptions, spend guard и automations.
- `seo/setup/setup-answer-plan.md` и `seo/setup/setup-answer-plan.csv` — review-only план ручных правок из заполненного `setup-questionnaire.csv`; secret-like ответы отклоняются и не сохраняются.
- `seo/automation-policy.yaml` — scheduled automations, approval gates, forbidden actions.
- `seo/automation-policy.generated.yaml` — generated overlay with recommended automations, tools, and approval gates; apply only after review.
- `seo/automations/automation-recommendations.md` — human-readable automation recommendations by project type/market/tools/spend guard.
- `seo/usage/usage-ledger.jsonl` — append-only журнал фактического расхода токенов, USD, credits, units, requests и browser minutes.
- `seo/setup/latest-usage-ledger.md` — текущий месячный usage report и cap/approval/block status.
- `seo/spend-guard.generated.yaml`, `seo/setup/spend-guard.md` и `seo/setup/spend-checklist.csv` — spend/subscription guard: allowed/approval/blocked, остатки лимитов, preflight-команды.
- `seo/setup/setup-control-plane.md` — compact readiness report: intake/profile/sources/governance/validation/tool stack/spend guard/growth roadmap/onboarding/launch-plan/project-journey/setup-blueprint/upgrade/access-key/context-pack/token-waste/provider-health/setup-gap-audit/automation + next actions.
- `seo/setup/latest-task-route.md` — low-token route for the latest task: phases, sources, approval gates, blocked actions, automation and context caps.
- `seo/project-intake.yaml` — детальная карта стран, регионов, поисковиков, рекламы, local/merchant/video/analytics decisions.
- `seo/project-intake-report.md` — человекочитаемый отчёт по intake для review перед profile/apply.

Правила:

- NeuronWriter — primary SERP/NLP редактор контента для briefs, terms, entities, questions, competitor scores, финального scoring и plagiarism-gate, если есть `NEURON_API_KEY`, helper и limits-файл.
- WriterZen — browser/export source без публичного API: использовать уже залогиненный браузер для Topic Discovery, Keyword Explorer, Keyword Planner и Domain Focus, экспортировать CSV/XLSX в `seo/research/writerzen/imports/`, затем запускать `writerzen-source-pack.py --write`; downstream берёт только distillates/vector records.
- Plagiarism Checker по умолчанию учитывать через NeuronWriter quota в `usage-ledger.py`: `check --service neuronwriter --category paid_api --plagiarism-checks 1 --fail-on-block` перед финальной проверкой и `record` после неё. Запуск проверки — через NeuronWriter Editor menu после `import-content`, потому что публичная API-документация описывает `import-content`/`evaluate-content`, но не отдельный plagiarism endpoint. WriterZen Plagiarism использовать только как manual fallback/export, не как основной gate.
- Google Cloud Natural Language — guarded technical entity audit: entities, salience, syntax/category, mismatch `title/H1/schema/text`. Это не ranking submission и не прямой ranking signal.
- Whole-site NeuronWriter/Google NLP jobs запрещены без одобренной очереди URL/keywords и достаточного остатка в policy.
- Перед дорогим сбором или автоматизацией запускай `governance-report.py`; если бюджет/approval не позволяют, делай только report-only/cached/read-only шаг.
- Перед конкретной задачей запускай `task-router.py --task "..." --write` и следуй `seo/setup/latest-task-route.md`, чтобы не запускать лишние фазы/источники.
- После task-router запускай `context-pack.py --task "..." --write` и открывай `seo/setup/context-pack.md` первым; подробные отчёты открывай только если они указаны в read order.
- После first-run или изменения policy запускай `setup-gap-audit.py --write` и закрывай missing fields через `seo/setup/setup-questionnaire.csv` / `seo/setup/setup-gap-audit.md` до широких циклов, платных API/LLM, массового local/ecommerce или automations. После заполнения CSV запускай `setup-answer-plan.py --write` и применяй только review-safe значения вручную.
- Перед фактическим расходом запускай `usage-ledger.py check ... --fail-on-block`; после расхода фиксируй `usage-ledger.py record ... --write`.
- Перед paid/API/LLM/subscription расходом запускай `spend-guard.py --write`; если сервис не allowed или status approval/blocked, остановись до approval/policy.
- Перед подключением новых Google/Yandex/Bing/Microsoft/NLP/AI/merchant/local/ads/tracking инструментов запускай `tool-stack-recommender.py --write`; `--apply` только после review.
- Перед широким циклом или маркетинг-задачей запускай `growth-roadmap.py --write` и начинай с `seo/setup/growth-roadmap.md`.
- Перед first-run открывай `setup-onboarding.py --write` / `seo/setup/onboarding-playbook.md`; secret values не записывай в playbook.
- Перед чтением подробных setup-отчётов открывай `context-pack.py --write` / `seo/setup/context-pack.md`, затем `project-journey.py --write` / `seo/setup/project-journey.md`, затем `setup-blueprint.py --write` / `seo/setup/setup-blueprint.md`, затем `project-upgrade-assistant.py --write` / `seo/setup/upgrade-questionnaire.csv`, затем `access-key-assistant.py --write` / `seo/setup/access-key-assistant.md`, затем `setup-gap-audit.py --write` / `seo/setup/setup-questionnaire.csv` и `seo/setup/setup-gap-audit.md`, после заполнения CSV — `setup-answer-plan.py --write` / `seo/setup/setup-answer-plan.md`, затем `launch-plan.py --write` / `seo/setup/launch-plan.md`; это low-token вход, пошаговый journey, проектная матрица, review-only upgrade, список нужных ключей, заполняемый worksheet, review-only план ручных правок и первый экран проекта.
- Перед `automation-plan.py` запускай `automation-recommender.py --write`; `--apply` только после review generated policy, `--allow-schedules` только при явном разрешении. Расширенные задачи должны оставаться report-only/dry-run или env-gated до approval.
- Low-token режим обязателен: raw CSV/JSON/HTML на диск, в контекст только distillates/top-N; не читай весь репозиторий или сырьё без необходимости. После широкого сбора запускай `token-waste-audit.py --write`.
- Perplexity используй через persistent app/browser session, если доступна; API optional/paid и выключен по умолчанию. NotebookLM используй как curated expert evidence только с citations/source excerpts, не как volume/KD/ranking signal. XMLRiver используй как approval-gated paid SERP/Wordstat enrichment: сначала `--input-file`, live только `--live --allow-paid` после spend guard.
- Для writing-фазы после research package запускай `research-package-quality.py --write`, затем `research-package-repair.py --write` или точечные repair scripts из action plan, при внешней SERP-проверке — `serp-validation-import.py --input-json/--input-csv --write`, затем повторный `research-package-quality.py --write`, затем `page-outline-v3.py --all-mvp --write` или `--priority P1 --write`, затем `page-outline-quality.py --version v3 --write`. Если repair/import свежее quality, `project-journey.py` блокирует writing до rerun quality. Для черновика читай `copywriter-ready/*.md`, `copywriting_playbook`, `writer_prompt_packet` и `metrics_rollup`, пиши draft в `<package>/drafts/*.md`, после черновика запускай `draft-quality-gate.py <draft.md> --outline <page-outlines-v3/slug.json> --write`; `project-journey.py` не пустит к implementation/publishing, пока `content_draft_gate` не пройден. NeuronWriter запускай только после `usage-ledger.py check --service neuronwriter --category paid_api --content-writer 1 --ai-credits 500 --fail-on-block`; он служит для SERP/NLP/scoring/evaluate/import, а не как обязательный автописатель. Raw research не загружай, пока gate не просит конкретный источник.
- Robots/Content-Signal: `search=yes, ai-input=yes, ai-train=no` допустимо как запрет обучения моделей. Публичный `robots.txt` должен быть чистым `text/plain`, без PHP warnings/HTML и editor/preview мусора.
- Для РФ-проектов не ставь зарубежные analytics/tracking tags или pixels без явного разрешения policy. GSC, Bing Webmaster, PageSpeed/CrUX, sitemap/robots checks и off-site API audits допустимы без установки кода аналитики.
- Никогда не выводи API keys, OAuth tokens, service-account JSON или значения `.env`; только имена переменных и пути.

### 6.1 Optional AI/dev support toolchain

Для развития самого `seo-cycle`, больших изменений, evidence ingestion и графовой навигации используй локальный support-набор:

```bash
bash ./.codex/skills/seo-cycle/scripts/install-ai-toolchain.sh --codex
bash ./.codex/skills/seo-cycle/scripts/install-ai-toolchain.sh --codex --notebooklm
bash ./.codex/skills/seo-cycle/scripts/install-ai-toolchain.sh --check
```

| Инструмент | Когда использовать | Правило безопасности |
|---|---|---|
| GitHub Spec Kit (`specify`) | Большие изменения в `seo-cycle`: constitution → spec → plan → tasks → implementation | Не заменяет SEO-фазы и не нужен для мелких правок |
| Microsoft MarkItDown (`markitdown`) | PDF/XLSX/DOCX/PPTX/HTML/YouTube → Markdown для evidence/fact-check/entity extraction | Только trusted local files или явно разрешённые URL |
| Graphify (`graphify`) | Mixed graph по коду, docs, markdown, research artifacts и media | Держать `graphify-out/` локальным кэшем, не коммитить без причины |
| CodeGraph (`codegraph`) | Local code-symbol graph + Codex MCP, когда нужно быстро понять код без массового чтения файлов | `.codegraph/` локальный индекс, не коммитить |
| NotebookLM MCP (`notebooklm`) | Доступ к curated expert knowledge base пользователя: видео/статьи/notes про SEO/AEO/GEO | Только после Google `setup_auth`; использовать ответы с citations/source excerpts как expert synthesis, не как прямой факт без проверки |

CloakBrowser/CloakMCP и другие stealth/anti-bot инструменты не входят в стандартный набор. Для SEO-сбора соблюдай robots, rate limits, project policy и source terms.

---

## <a id="инструменты"></a>7. Инструменты (что делает · команда · результат)

> В установленном проекте скрипты доступны через `./.codex/skills/seo-cycle/scripts/`. Общий обновляемый core лежит в `~/.codex/vendor/seo-cycle`. Запуск: `python3 <script>.py` или `bash <script>.sh`. Core-скрипты поддерживают системный Python 3.9+; UTC timestamps пишутся через совместимый timezone-aware helper.

### 7.0 Локальный AI/dev support-набор
| Инструмент | Что делает | Команда | Результат |
|---|---|---|---|
| `install-ai-toolchain.sh` | Ставит Spec Kit, MarkItDown, Graphify, CodeGraph и Codex-интеграции Graphify/CodeGraph | `bash install-ai-toolchain.sh --codex` / `--check` | Локальные CLI, Graphify skill, CodeGraph MCP config |
| `specify` | Spec-driven workflow для крупных изменений в `seo-cycle` | `specify init <project> --integration codex` | `.specify/`, Codex skills/commands для spec/plan/tasks |
| `markitdown` | Конвертация trusted документов в Markdown для evidence layer | `markitdown source.pdf -o evidence.md` | Markdown-дистиллят для fact-check/entity extraction |
| `graphify` | Граф знаний по code/docs/research/media | `graphify update . --no-cluster` / `$graphify` | `graphify-out/graph.json`, graph reports/query |
| `codegraph` | Локальный code-symbol graph + MCP для Codex | `codegraph init .` / `codegraph status .` | `.codegraph/` SQLite index, MCP `codegraph` |
| `notebooklm` | MCP-доступ к NotebookLM notebooks | `bash install-ai-toolchain.sh --codex --notebooklm` | Codex MCP config; дальше `setup_auth`, `add_notebook`, `ask_question` |

### 7.1 Управление источниками и конфигом
| Скрипт | Что делает | Команда | Результат |
|---|---|---|---|
| `validate-config.py` | Проверяет `seo-cycle.yaml`, env, делегатов, policy-файлы и governance | `python3 validate-config.py` | Список активных источников, недостающие ключи/policy, ✓/ошибки |
| `resolve-sources.py` | Разворачивает `region_profile` + override в список активных источников | `python3 resolve-sources.py` | Активные/пропущенные источники с причиной + `seo/cycles/<date>/active-sources.json` |
| `setup-control-plane.py` | Единый low-token setup/readiness отчёт по intake/profile/sources/governance/validation/tool stack/spend guard/growth roadmap/onboarding/launch-plan/project-journey/setup-blueprint/upgrade/access-key/context-pack/token-waste/provider-health/setup-gap-audit/automation/task route/usage ledger | `python3 setup-control-plane.py --write` | `seo/setup/setup-control-plane.md/json`, latest validation/governance/sources/tool stack/spend/growth roadmap/onboarding/launch-plan/project-journey/setup-blueprint/upgrade/access-key/context-pack/token-waste/provider-health/setup-gap-audit/task route/usage |
| `project-journey.py` | Показывает текущий этап пути от старта до цели, что не хватает для следующего шага, blockers, next command и exit criteria | `python3 project-journey.py --write` / `--goal "собрать и опубликовать кластер"` | `seo/setup/project-journey.md/json`, `project-journey-checklist.csv`, latest copies |
| `seo-cycle-run.py` | v1.63 staged orchestrator: запускает контрактные стадии с gate, repair, rerun, blocker reports и latest run summary | `python3 seo-cycle-run.py --goal "собрать research package" --write` / `--stage-template research-package --package seo/research-package --write` / `--stage-template copywriting --draft <draft.md> --write` / `--stage-file stages.yaml --write` | `seo/orchestrator/latest-run.md/json`, `<stage>-report.md/json`, `<stage>-blocker.md/json` |
| `task-router.py` | Строит low-token маршрут под конкретную SEO/маркетинг-задачу | `python3 task-router.py --task "аудит индексации" --write` | `seo/setup/latest-task-route.md/json` + archived route |
| `context-pack.py` | Строит первый короткий task-scoped handoff для Claude/Codex с `context_manifest` | `python3 context-pack.py --task "аудит индексации" --write` | `seo/setup/context-pack.md/json`, `seo/setup/latest-context-pack.md/json` |
| `knowledge/wiki-refresh-all.sh` | Обновляет project-local Knowledge Hub: WordPress inventory, правила, статьи, категории, бренды, товары, internal links, API catalog, review-cluster plan, latest wiki context pack и hybrid index | `bash ./.codex/skills/seo-cycle/scripts/knowledge/wiki-refresh-all.sh` | `seo/knowledge/wiki/**`, `seo/knowledge/zvec/zvec-status.json`, `seo/knowledge/wiki/context/latest-context-pack.md` |
| `knowledge/wiki-preflight.py` | Проверяет страницу/черновик перед правкой: дубли slug/intent, правила проекта, служебные слова, raw URLs, связанные статьи/категории/товары | `python3 ./.codex/skills/seo-cycle/scripts/knowledge/wiki-preflight.py --url "<url>" --draft draft.md --write` | `seo/knowledge/wiki/preflight/wiki-preflight.md/json` + history JSON |
| `knowledge/content-taste-gate.py` | Проверяет публичный текст на человеческий стиль: без "интент", "SEO-текст", raw URL, служебных примечаний, claims про наличие и неподтверждённых сравнений | `python3 ./.codex/skills/seo-cycle/scripts/knowledge/content-taste-gate.py draft.md --write` | `seo/knowledge/wiki/reports/content-taste-gate.md/json` |
| `knowledge/graphify-refresh.sh` | Собирает curated corpus и строит Graphify-граф через Antigravity/Gemini CLI/API; если Graphify не установлен, пишет degraded status без падения upgrade | `bash ./.codex/skills/seo-cycle/scripts/knowledge/graphify-refresh.sh` | `seo/knowledge/graph/graphify-status.json`, optional `graphify-out/graph.json`, `GRAPH_REPORT.md`, `GRAPH_TREE.html` |
| `knowledge/zvec-hybrid-index.py` | Строит SQLite FTS/zvec-ready hybrid index по wiki и vector records для поиска похожих интентов, ссылок, товаров и сущностей | `python3 ./.codex/skills/seo-cycle/scripts/knowledge/zvec-hybrid-index.py --build --write` / `--query "Изоспан"` | `seo/knowledge/zvec/index.jsonl`, `hybrid.sqlite`, `zvec-status.json` |
| `token-waste-audit.py` | Находит raw/large artifacts и oversized distillates, которые зря тратят context | `python3 token-waste-audit.py --write` | `seo/setup/token-waste-audit.md/json`, latest copies |
| `perplexity-health.py` | Проверяет Perplexity persistent app/browser/API optional режим без хранения паролей | `python3 perplexity-health.py --write` | `seo/setup/perplexity-health.md/json`, latest copies |
| `notebooklm-health.py` | Проверяет NotebookLM MCP/tools и fallback browser/manual export | `python3 notebooklm-health.py --write` | `seo/setup/notebooklm-health.md/json`, latest copies |
| `xmlriver-health.py` | Проверяет XMLRiver readiness, env names, цены и capabilities без live paid API | `python3 xmlriver-health.py --write` | `seo/setup/xmlriver-health.md/json`, latest copies |
| `writerzen-health.py` | Проверяет WriterZen browser/export readiness без хранения паролей | `python3 writerzen-health.py --browser-available --write` | `seo/setup/writerzen-health.md/json`, latest copies |
| `writerzen-browser-collect.py` | Открывает WriterZen в persistent browser profile, создаёт нужные отчёты, скачивает CSV/XLSX в `seo/research/writerzen/imports/` и запускает importer одной командой | `python3 writerzen-browser-collect.py --topic "Плита ОСП" --force-new-report --manual-fallback-seconds 120 --write` | `seo/setup/writerzen-browser-collect.md/json` + WriterZen raw/distillate/vector |
| `perplexity-collect.py` | Кэширует Perplexity export/raw response, пишет bounded distillate с citations и vector record; API paid disabled by default | `python3 perplexity-collect.py --topic "Плита ОСП" --raw-file response.md --write` | `seo/research/raw/perplexity/*.json`, `seo/research/distillates/perplexity/*.md/json`, `seo/research/vector/source_pack.jsonl` |
| `notebooklm-source-pack.py` | Ингестит NotebookLM MCP/browser/manual export как curated expert evidence, не как ranking signal | `python3 notebooklm-source-pack.py --topic "SEO" --export-file notebook.md --write` | `seo/research/raw/notebooklm/*.json`, `seo/research/distillates/notebooklm/*.md/json`, `seo/research/vector/source_pack.jsonl` |
| `xmlriver-source-pack.py` | Guarded XMLRiver adapter: Google/Yandex SERP XML, Wordstat New JSON, ads/shopping/maps/suggest/AI Overview request plans; live только `--live --allow-paid` | `python3 xmlriver-source-pack.py --query "Плита ОСП" --engine yandex --input-file serp.xml --write` | `seo/research/raw/xmlriver/*.json`, `seo/research/distillates/xmlriver/*.md/json`, `seo/research/vector/source_pack.jsonl` |
| `writerzen-source-pack.py` | Ингестит WriterZen browser exports: Topic Discovery, Keyword Explorer, Keyword Planner, Domain Focus; нормализует volume/KD/CPC/intent/Buying Journey/SERP Type/Allintitle/KGR | `python3 writerzen-source-pack.py --topic "Плита ОСП" --export-file writerzen.csv --write` | `seo/research/raw/writerzen/*.json`, `seo/research/distillates/writerzen/*.md/json`, `seo/research/vector/source_pack.jsonl` |
| `research-package-quality.py` | Quality gate для site-level research package: SERP validation gaps, URL/cluster drift, GSC мусор, duplicate briefs, orphan URLs, entity drift, raw Google NLP, unused AI Overview/GEO signals, E-E-A-T/evidence gaps; даёт 10-критериальный scorecard и автоматический план действий | `python3 research-package-quality.py ./research-package --write`; короткий запуск: `--format plan` | `research-package-quality.md/json`, `research-package-action-plan.md`; exit 1 при critical findings |
| `research-package-repair.py` | Единый wrapper repair layer: запускает cleanup/resync/entity/NLP/orphan/SERP/spoke/entity-graph шаги и пишет общий статус | `python3 research-package-repair.py ./research-package --write` | `research-package-repair.md/json` + repair artifacts |
| `semantic-core-clean.py` / `semantic-core-resync.py` | Repair ядра: убирает prompt/spam-like GSC строки в rejected CSV и пересинхронизирует `semantic-core` с финальными cluster IDs/URLs после рекластеризации | `python3 semantic-core-clean.py ./research-package --write`; затем `python3 semantic-core-resync.py ./research-package --write` | `semantic-core.cleaned.csv`, `semantic-core.rejected.csv`, `semantic-core.resynced.csv`, отчёты `.md/.json` |
| `entity-map-sync.py` / `google-nlp-aggregate.py` | Repair сущностей: рендерит `entity-map.md` из YAML без потерь, дедуплицирует Google NLP entities, агрегирует mentions/salience/types и пишет компактный coverage layer | `python3 entity-map-sync.py ./research-package --write`; `python3 google-nlp-aggregate.py ./research-package --write` | `entity-map.md`, `entity_coverage.jsonl`, отчёты `.md/.json` |
| `orphan-url-resolver.py` / `serp-validation-plan.py` / `serp-validation-import.py` / `spoke-opportunity-audit.py` | Repair архитектуры: закрывает orphan internal URLs backlog-строками, планирует недостающие SERP проверки, импортирует reviewed DataForSEO/Serpstat/manual SERP export обратно в `semantic-architecture-final.json` и выносит GSC long-tail в phase-2 spokes | `python3 orphan-url-resolver.py ./research-package --write`; `python3 serp-validation-plan.py ./research-package --write`; `python3 serp-validation-import.py ./research-package --input-json serp-export.json --write`; `python3 spoke-opportunity-audit.py ./research-package --write` | `content-plan.orphan-backlog.csv`, `serp-validation-plan.csv`, `serp-validation-import.md/json`, `spoke-opportunities.csv`, отчёты `.md/.json` |
| `page-outline-v3.py` | Генерирует copywriter-ready H2/H3 briefs из research package: tool-first ordering для tool/app/quiz, `copywriter-ready/*.md`, section/H3 word counts, `metrics_rollup`, intro/conclusion, SEO meta, Key Takeaways, FAQ answer guidelines, visual inventory, writer handoff, `copywriting_playbook`, `writer_prompt_packet`, source slots, acceptance criteria, entity triplets, schema, internal links, synthetic prompts, E-E-A-T guard | `python3 page-outline-v3.py ./research-package --all-mvp --write`; одиночно: `--page "/tools/virtual-hair-color-try-on/"`; expert mode: `--expert-author` | `page-outlines-v3/<page>.md/json`, `copywriter-ready/<page>.md`, `vector/page_outline_triplets.jsonl` |
| `page-outline-v2.py` | Legacy-compatible H2/H3 page briefs; оставлен для старых проектов и архивирования дублей | `python3 page-outline-v2.py ./research-package --all-mvp --write`; архив дублей: `--archive-legacy-briefs` | `page-outlines-v2/<page>.md/json`; optional `archive/legacy-briefs/` |
| `page-outline-quality.py` | Quality gate для page briefs: word-count drift, H3/H2 mismatch, SERP/page-type lock, intro/conclusion, SEO meta, Key Takeaways, FAQ, handoff, copywriting playbook, writer prompt packet, revision checklist, fact-check queue, schema, internal links, Answer Units, source slots, acceptance criteria, entity orphans, bridges, visuals, trust limits, synthetic prompts, fabricated first-person expertise, v3 tool-first ordering, v3 visual inventory and triplet export | `python3 page-outline-quality.py ./research-package --version v3 --write`; коротко: `--format markdown` | `page-outline-quality.md/json`, `latest-page-outline-quality.md/json`; exit 1 при critical findings |
| `entity-graph-quality.py` / `draft-quality-gate.py` | Quality gates после repair/briefing: ловят дубли/сироты триплетов, entity weights без source, а в черновике — missing H2/H3, обязательные ссылки, source/proof slots и unsafe first-person expertise | `python3 entity-graph-quality.py ./research-package --write`; `python3 draft-quality-gate.py draft.md --outline page-outlines-v3/page.json --write` | `entity-graph-quality.md/json`, `<draft>.draft-quality-gate.md/json` |
| `technical-site-audit.py` | Собирает latest technical distillates в единый low-token rollup без live-запусков | `python3 technical-site-audit.py --write` | `seo/technical/technical-site-audit.md/json`, latest copies |
| `link-audit.py` | Дистиллирует `linkinator` JSON или явный live crawl: broken links, redirects, HTTP links | `python3 link-audit.py --input-json linkinator.json --url https://example.com/ --write` | `seo/technical/link-audit.md/json`, raw/distillate/vector source records |
| `redirect-map-audit.py` | Проверяет CSV redirect map на chains, loops, self-redirects, missing targets и optional live status | `python3 redirect-map-audit.py --input redirects.csv --base-url https://example.com --write` | `seo/technical/redirect-map-audit.md/json`, raw/distillate/vector source records |
| `lighthouse-audit.py` | Дистиллирует Lighthouse JSON или явный live run: performance, SEO, accessibility, CWV, opportunities | `python3 lighthouse-audit.py --input-json lighthouse.json --url https://example.com/ --write` | `seo/technical/lighthouse-audit.md/json`, raw/distillate/vector source records |
| `gsc-url-inspection.py` | Guarded Google URL Inspection adapter: input JSON или read-only live OAuth token | `python3 gsc-url-inspection.py --input-json gsc-url-inspection.json --url https://example.com/ --site-url sc-domain:example.com --write` | `seo/technical/gsc-url-inspection.md/json`, raw/distillate/vector source records |
| `gsc-indexing-export-browser.py` | Открывает GSC Pages/issue URL, ловит export download и может сразу собрать indexing queue | `python3 gsc-indexing-export-browser.py --issue-url "<GSC issue URL>" --manual-fallback-seconds 120 --build-queue --write` | `seo/technical/gsc-indexing-export.md/json`, `seo/technical/gsc-indexing/imports/*` |
| `gsc-indexing-queue.py` | Делает top-10/top-20 очередь из GSC “Обнаружена, не проиндексирована” + sitemap + WooCommerce + GSC impressions; фильтрует мусор и technical blockers | `python3 gsc-indexing-queue.py --gsc-discovered-file exports/discovered.csv --gsc-performance-file exports/gsc-performance.json --woocommerce-file exports/woo.csv --technical-check --top 20 --write` | `seo/technical/gsc-indexing-queue.md/json`, `seo/technical/gsc-indexing-request-queue.csv` |
| `gsc-request-indexing-browser.py` | Открывает GSC URL Inspection через persistent browser profile и по явному `--auto-click` нажимает Request indexing для P0/P1 | `python3 gsc-request-indexing-browser.py --queue-file seo/technical/gsc-indexing-request-queue.csv --max 10 --auto-click --write` | `seo/technical/gsc-indexing-submit.md/json` |
| `gsc-indexing-recheck.py` | Через 3-7 дней сверяет отправленные URL со свежим GSC export/search data | `python3 gsc-indexing-recheck.py --submitted-log seo/technical/gsc-indexing-submit.json --gsc-discovered-file exports/discovered-after-7d.csv --write` | `seo/technical/gsc-indexing-recheck.md/json` |
| `indexnow-submit.py` | Массово уведомляет IndexNow/Bing/Yandex-compatible endpoints по P0/P1 queue; live только с `INDEXNOW_KEY` | `INDEXNOW_KEY=*** INDEXNOW_KEY_LOCATION=https://example.com/key.txt python3 indexnow-submit.py --queue-file seo/technical/gsc-indexing-request-queue.csv --priority P0,P1 --max 100 --live --write` | `seo/technical/indexnow-submit.md/json`, `seo/technical/indexnow-submit-log.csv` |
| `yandex-recrawl-submit.py` | Отправляет P0/P1 URL в Яндекс.Вебмастер `/recrawl/queue` и проверяет очередь переобхода | `YANDEX_OAUTH_TOKEN=*** python3 yandex-recrawl-submit.py --queue-file seo/technical/gsc-indexing-request-queue.csv --priority P0,P1 --max 20 --live --write` / `--mode status --live` | `seo/technical/yandex-recrawl-submit.md/json`, `seo/technical/yandex-recrawl-status.md/json` |
| `bing-url-inspection.py` | Guarded Bing Webmaster `GetUrlInfo`: input JSON или read-only live API key | `python3 bing-url-inspection.py --input-json bing-url-info.json --url https://example.com/ --site-url https://example.com/ --write` | `seo/technical/bing-url-inspection.md/json`, raw/distillate/vector source records |
| `technical-mcp-health.py` | Проверяет optional MCP readiness для mcp-gsc, Google Analytics MCP и Lighthouse MCP без установки и без секретов | `python3 technical-mcp-health.py --write` | `seo/technical/technical-mcp-health.md/json`, latest copies |
| `project-mcp-config.py` | Опционально создаёт project-local `.codex/config.toml` для WordPress/Novomira MCP; используй только когда REST API недостаточно или нужны Novomira abilities | `python3 project-mcp-config.py --write` | `.codex/config.toml`, `.env.example` hints; не трогает чужие MCP-блоки вне managed markers |
| `serpstat-audit.py` | Guarded Serpstat API adapter: projects/create/start/settings/issue reports/export/basic-info/categories/scan-urls; live только с `SERPSTAT_API_KEY` | `python3 serpstat-audit.py --action basic-info --report-id 123 --write` / `--live` | `seo/technical/serpstat-audit.md/json`, raw/distillate/vector source records |
| `labrika-source-pack.py` | Ингестит Labrika manual/browser export как third-party technical evidence, пока public API не подтверждён | `python3 labrika-source-pack.py --export-file labrika.md --write` | `seo/technical/labrika-source-pack.md/json`, `seo/research/raw/labrika/*`, vector records |
| `labrika-health.py` | Фиксирует Labrika API readiness, support questions и manual/export fallback | `python3 labrika-health.py --write` | `seo/technical/labrika-health.md/json`, latest copies |
| `setup-blueprint.py` | Строит компактную per-project матрицу настройки: страны, регионы, поисковики, бизнес, marketing/ads/tracking, tools, budget, subscriptions, automations, guardrails | `python3 setup-blueprint.py --write` | `seo/setup-blueprint.generated.yaml`, `seo/setup/setup-blueprint.md/json`, `seo/setup/setup-matrix.csv`, latest copies |
| `project-upgrade-assistant.py` | Проверяет существующий проект против текущего template/control-plane surface и строит review-only yes/no/defer worksheet | `python3 project-upgrade-assistant.py --write` | `seo/setup/upgrade-assistant.md/json`, `seo/setup/upgrade-questionnaire.csv`, latest copies |
| `project-upgrade-apply.py` | Безопасно применяет reviewed missing `policy_files` keys из upgrade questionnaire с backup; default dry-run, без секретов/платных действий/публикации | `python3 project-upgrade-apply.py --write` / `--apply --write` / `--use-defaults` | `seo/setup/project-upgrade-apply.md/json/csv`, backup `seo-cycle.yaml.bak-*` при apply |
| `access-key-assistant.py` | Строит список нужных ключей/токенов по tool-stack и `.env`: env names, provider links, короткие шаги, без secret values | `python3 access-key-assistant.py --write` | `seo/setup/access-key-assistant.md/json/csv`, latest copies |
| `setup-gap-audit.py` | Проверяет детальную готовность проекта и создаёт заполняемый worksheet владельца по бизнесу, local/ecommerce, tools, budget/subscriptions и automations | `python3 setup-gap-audit.py --write` | `seo/setup/setup-gap-audit.md/json`, `seo/setup/setup-questionnaire.md/csv/json`, latest copies |
| `setup-answer-plan.py` | Читает заполненный setup questionnaire и строит review-only план ручных правок без сохранения secret-like ответов | `python3 setup-answer-plan.py --write` | `seo/setup/setup-answer-plan.md/json/csv`, latest copies |
| `usage-ledger.py` | Ведёт фактический расход токенов, USD, credits, units, requests, browser minutes и проверяет caps | `python3 usage-ledger.py report --write` / `check --service openai --usd 0.25 --fail-on-block` / `record --service openai --usd 0.25` | `seo/usage/usage-ledger.jsonl`, `seo/setup/latest-usage-ledger.md/json` |
| `spend-guard.py` | Показывает allowed/approval/blocked по paid/API/LLM/subscription сервисам, остатки лимитов и preflight-команды | `python3 spend-guard.py --write` | `seo/spend-guard.generated.yaml`, `seo/setup/spend-guard.md/json`, `seo/setup/spend-checklist.csv` |
| `tool-stack-recommender.py` | Рекомендует стек инструментов по country/search engines/business/local/ecommerce/budget/tracking policy | `python3 tool-stack-recommender.py --write` / `--apply` | `seo/tool-stack.generated.yaml`, `seo/setup/tool-stack-report.md/json`, optional backup+safe source flags |
| `growth-roadmap.py` | Строит top-N roadmap по technical/search evidence/ecommerce/local/content/entities/AI visibility/CRO/automation | `python3 growth-roadmap.py --write` / `--max-actions 8` | `seo/growth-roadmap.generated.yaml`, `seo/setup/growth-roadmap.md/json` |
| `setup-onboarding.py` | Строит подробный first-run checklist с owner, env names, approval gates, командами и proofs | `python3 setup-onboarding.py --write` / `--max-steps 24` | `seo/onboarding.generated.yaml`, `seo/setup/onboarding-playbook.md/json`, `seo/setup/onboarding-checklist.csv` |
| `launch-plan.py` | Строит первый low-token экран проекта с market/business/tools/token/budget/subscriptions/env/approval/execution contract | `python3 launch-plan.py --write` / `--max-execution-steps 12` | `seo/launch-plan.generated.yaml`, `seo/setup/launch-plan.md/json`, `seo/setup/launch-checklist.csv` |
| `automation-recommender.py` | Рекомендует tool-aware planned automations по intake/business/market/tool-stack/spend-guard/policy | `python3 automation-recommender.py --write` / `--apply` | `seo/automations/automation-recommendations.md/json`, `seo/automation-policy.generated.yaml`, optional backup+policy update |
| `project-intake-wizard.py` | Подробно заполняет `seo/project-intake.yaml` под конкретный проект | `python3 project-intake-wizard.py --interactive --write` / `--defaults --write` | `seo/project-intake.yaml`, `seo/project-intake-report.md` |
| `project-profile.py` | Строит точечный профиль проекта из `seo/project-intake.yaml` | `python3 project-profile.py --write` / `--apply` | `seo/project-profile.generated.yaml`, report, опц. backup+обновление `seo-cycle.yaml` |
| `governance-report.py` | Показывает token/budget/tool/automation policy без секретов | `python3 governance-report.py --format md` | Markdown/JSON отчёт для Phase 0 и approval gates |
| `automation-plan.py` | Генерирует безопасный schedule plan, cron, launchd templates и safe команды для spend/index/search/schema/CWV/content/local/ecommerce задач | `python3 automation-plan.py --write --include-disabled` | `seo/automations/automation-plan.md`, `crontab.txt`, plist-шаблоны; install blocked без policy |
| `init-project.sh` | Мастер нового проекта | `bash init-project.sh` | `seo-cycle.yaml`, `.env.example`, policy-файлы, запись в реестр |
| `cycle-state.py` | Контракт состояния цикла (handoff между фазовыми скиллами) | `python3 cycle-state.py init --topic "X"` / `next` / `set <фаза> --status done --gate-passed` / `show` | `_state.json` с DAG фаз; «цепочка передачи» |

### 7.2 Сбор семантики
| Скрипт | Что делает | Команда | Результат |
|---|---|---|---|
| `yandex-suggest.py` | Long-tail из Яндекс.Suggest (бесплатно) | `python3 yandex-suggest.py "<seed>" --region 213 --depth 2` | CSV подсказок |
| `google-suggest.py` | Long-tail из Google Suggest | `python3 google-suggest.py "<seed>" --region RU` | список ключей |
| `google-trends.py` | Сезонность/тренды | `python3 google-trends.py "<тема>" --region RU` | markdown с трендом |
| `serpstat-fetch.py` | Volume/KD/CPC + конкуренты (вкл. РФ `g_ru`) | `python3 serpstat-fetch.py keywords-info "<ключ>" --se g_ru` | md-таблица; кэш; guard кредитов (`stats` — остаток) |
| `keyso-fetch.py` | **Keys.so — Яндекс/РФ**: Wordstat-частоты, видимость, конкуренты, потерянные ключи | `python3 keyso-fetch.py competitors <домен>` / `keyword-info "<ключ>"` / `lost <домен>` | md-таблица; **кэш 60д** + usage-трекер (`_usage.json`); лимит 10/10сек |
| `competitor-discovery.py` | Поиск **максимально похожих конкурентов** через топ выдачи по коммерч. ключам (Keys.so) | `python3 competitor-discovery.py "ключ1" "ключ2" --exclude-giants` | ранжированный список конкурентов + флаг гигантов |
| `keyso-save.py` | Сохранить группу доменов (конкуренты) **в кабинет Keys.so** (write-API `/report/group`) | `python3 keyso-save.py group-report --from-config` | rid отчёта в Keys.so |
| `keyso-clustering-export.py` | Подготовить файл ключей для clustering Keys.so (загрузка — браузером, см. `prompts/keyso-clustering-upload.md`) | `python3 keyso-clustering-export.py --from-keyso-cache <домен> --out keys.txt` | .txt по ключу на строку |
| `spyfu-fetch.py` | Competitor/PPC US/UK/EU (не РФ) | `python3 spyfu-fetch.py domain-stats <domain> --cc US` | md-таблица; usage-трекер $-бюджета |
| `atp-fetch.py` | Шаблоны вопросов AnswerThePublic (en/us) | `python3 atp-fetch.py "<en keyword>"` | md с questions/prepositions/comparisons |
| `nw-cli.sh` | NeuronWriter: SERP terms/entities/score | `bash nw-cli.sh get <query_id>` | terms, entities, competitors, target score |
| `llm-cli-collect.sh` | Параллельный сбор Antigravity + Codex (RUNTIME-aware, deep-режим); Antigravity обязателен для семантики/интентов/сущностей | `bash llm-cli-collect.sh "<тема>"` | 2 файла сырья + подсказка merge |
| `llm-cli-merge.py` | Слияние+дедуп результатов LLM-CLI | `python3 llm-cli-merge.py a.md b.md -o merged.md` | `*-merged-*.md` (дистиллят) |
| `research-cache.py` | TTL-кэш дорогого сбора | `python3 research-cache.py check --dir ... --slug ... --source ... --ttl 14` | путь к свежему кэшу (HIT) или код 1 (MISS) |
| `google-nlp-audit.py` | Guarded Google Cloud NLP entity/category/syntax audit с кэшем и unit caps | `python3 google-nlp-audit.py --project-root . --url https://example.com/ --dry-run` | JSON plan/cache/API results; без публикации и без обхода лимитов |

Обязательное правило: для полного цикла семантика и Entity Map не считаются завершенными без Antigravity CLI и Perplexity Deep Research. Raw-ответы сохраняются на диск; в рабочий контекст подтягивается только merge/distilled artifact. Если Perplexity или Antigravity недоступны, это фиксируется как blocker/exception в артефакте.

### 7.3 Данные мониторинга (Google/Яндекс)
| Скрипт | Что делает | Команда |
|---|---|---|
| `gsc-fetch.py` | Google Search Console queries | `python3 gsc-fetch.py --site <url> --days 90` |
| `ga4-fetch.py` | Google Analytics 4 трафик/поведение | `python3 ga4-fetch.py ...` |
| `psi-fetch.py` | PageSpeed Insights / CrUX (Core Web Vitals) | `python3 psi-fetch.py <url>` |
| `webmaster-fetch.py` | Яндекс.Вебмастер запросы | `python3 webmaster-fetch.py ...` |
| `metrika-fetch.py` | Яндекс.Метрика | `python3 metrika-fetch.py ...` |
| `snapshot-build.py` | Сводит источники в единый snapshot | `python3 snapshot-build.py ...` → `*-snapshot.json` |
| `lost-keywords.py` | Потерянные/просевшие ключи между двумя снапшотами | `python3 lost-keywords.py --old O.json --new N.json` |
| `competitor-benchmark.py` | Медианный бенчмарк по конкурентам (где мы ниже) | `python3 competitor-benchmark.py bench.csv --md` |

### 7.4 Контент, E-E-A-T, качество
| Скрипт | Что делает | Команда | Результат |
|---|---|---|---|
| `check-stop-words.py` | Ловит запрещённые слова/латиницу бренда | `python3 check-stop-words.py <file>` | список нарушений |
| `schema-org-build.py` | Канонический Organization/LocalBusiness JSON-LD из `business_profile` | `python3 schema-org-build.py inject schema/*.json` | @id-узел + author/publisher как @id |
| `eeat-render.py` | Trust-блок «Источники» из `fact_check_log` | `python3 eeat-render.py <publish.md>` | HTML-блок источников |
| `schema-validate.py` | Валидация JSON-LD | `python3 schema-validate.py <file>` | ошибки/предупреждения |
| `source-attribution.py` | Какой источник дал ключи в топ | `python3 source-attribution.py --csv ... --snapshot ...` | таблица отдачи + рекомендации отключить слабые |
| `ice-score.py` | ICE-приоритизация находок (конкурентный анализ/аудит) | `python3 ice-score.py findings.csv --md` | список по ICE (Impact×Confidence×Ease) с зонами 🔥/✅/⏳ |
| `roi-calc.py` | Воронка и ROI/CAC/ДРР по каналам — «конечный результат» в деньгах | `python3 roi-calc.py funnel.csv --margin 0.3` | таблица каналов + вердикт «что окупается / нужна ли реклама» |
| `programmatic-template-gen.py` | Программатик-страницы (город×категория) | `python3 programmatic-template-gen.py ...` | шаблоны страниц |
| `validate-entities.py` | Проверка реестра сущностей | `python3 validate-entities.py` | кросс-ссылки/ошибки |

### 7.5 Публикация (CMS)
| Скрипт | Что делает |
|---|---|
| `img-generate.sh` | Генерация изображения (RUNTIME-aware: codex exec / нативный image-skill) |
| `wp-photo-image.py` | Детерминированное фото: локальный файл/URL → crop по `images.aspect_ratios.*` → WebP → WordPress upload через SSH/WP-CLI → alt/caption/featured |
| (в проекте) `wp-*-publish.py` | Публикация постов/категорий/страниц |

Image gate: настройки берутся из `images.*` в `seo-cycle.yaml`: `workflow`, `source_policy`, `visual_style`, `aspect_ratios`, `output`, `captions`, `alt`, `lazy_loading`, `upload`. Для photo-first workflow используй `wp-photo-image.py`, а не ручную нарезку. Inline images должны быть чистыми тематическими фото/визуалами в стиле проекта. Не добавляй видимый текст на изображение (SEO/AEO/GEO, схемы, подписи, описания товаров, дисклеймеры каталога), если `images.allow_visible_text=false`, и не делай товарные карточки/коллажи основным визуалом без явного запроса. У каждого недекоративного изображения должен быть `alt` до публикации: featured, inline, OG/schema, product/category visuals. Inline image также должен иметь короткий редакционный caption, если `images.captions.inline_required=true`. Alt и caption описывают видимый объект и сущность страницы естественно, без набивки ключами и без служебных объяснений. После публикации проверь публичный HTML и браузерный screenshot: `<img>` без `alt`, inline image без обязательного caption, запрещённый текст на/под изображением или lazy-load плейсхолдер вместо first-screen фото = blocker/exception в логе. Если оптимизатор подменяет первое/above-the-fold inline image на плейсхолдер, исключи только это критичное изображение из lazy-load (`skip-lazy`/`data-no-lazy` или CMS-аналог) и перепроверь. Остальные inline images ниже первого экрана оставляй lazy-loaded.

### 7.6 Данные, автоматизация, уведомления
| Скрипт | Что делает | Команда | Результат |
|---|---|---|---|
| `db-sync.py` | CSV/JSON → единая `seo.db` + Obsidian-дашборд | `python3 db-sync.py` | таблицы positions/queue/usage/attribution + `_Dashboards/SEO-Automation.md` |
| `notify.py` | Telegram-алерты (graceful no-op без токена) | `python3 notify.py "текст" --level alert` / `--test` | сообщение в Telegram |
| `monthly-runner.sh` | Авто-детект операции по дате; `all` — по реестру | `bash monthly-runner.sh status` / `all` | запуск нужной системы + approval-тикеты |
| `approval-gate.py` | Файловые approval-тикеты (+ notify) | `python3 approval-gate.py create --type custom --title "..."` | тикет в `pending-approvals.md` |
| `keyword-queue.py` | FIFO-очередь ключей | `python3 keyword-queue.py status` | состояние очереди |
| `triggers-eval.py` | Правила Phase 10 (просадки, striking distance) | `python3 triggers-eval.py snapshot.json triggers.yaml` | приоритизированный action-list |
| `deindex-detect.py` | Деиндексация (sitemap vs GSC) | `python3 deindex-detect.py ...` | список выпавших URL |
| `obsidian-sync.py` | Зеркалирование артефактов в Obsidian | `python3 obsidian-sync.py` | заметки в vault |
| `monthly-dashboard.py` | Markdown-дашборд статуса | `python3 monthly-dashboard.py` | отчёт |

### 7.7 Локальное SEO (карты: Google + Яндекс/2ГИС)
Тактики локального доминирования — парно для обеих карт-экосистем (для РФ приоритет Яндекс.Карты + 2ГИС). Промпты: `prompts/local/google-maps.md` + `prompts/local/yandex-maps.md` (категории/рубрики, скорость отзывов, календарь постов, визуальное доминирование, локальная видимость). Источник бизнеса/конкурентов — `business_profile` (`gbp_url`, `yandex_business_url`, `2gis_url`, `competitors[]`). Выполняются через браузер (Chrome MCP / browser-skill).

| Скрипт | Что делает | Команда | Результат |
|---|---|---|---|
| `review-velocity.py` | План догона лидера по отзывам (Google/Яндекс/2ГИС) | `python3 review-velocity.py --my-total N --leader-total M --leader-30d X --my-target-30d Y` | сколько отзывов/мес нужно + срок догона |

Уже покрыто другими инструментами: keyword gap → `serpstat-fetch competitors`/SpyFu; позиции 11-20 → `triggers-eval` (striking_distance); бэклинки → `seo-backlinks`/`seo-ahrefs`; общий GBP/NAP → плагин `seo-maps`/`seo-local`.

### 7.8 Маркетинговые мостики (marketing-skills + РФ-адаптация)
Плагин `marketing-skills` (CRO, платный трафик, удержание, монетизация) дополняет seo-cycle. Включается секцией `marketing` в конфиге. Карта «фаза → скилл» и **РФ-замены каналов** (Яндекс.Директ вместо Google Ads, VK/Telegram вместо Meta, Метрика, 2ГИС/Яндекс.Бизнес, ЮKassa) — в `docs/marketing-bridges.md`. Связка: seo-cycle (органика) → `page-cro`/`form-cro` (конверсия) → `referral-program`/`email-sequence` (удержание). SEO-скиллы плагина НЕ дублируем — ведём через seo-cycle.

### 7.9 Маркетинг-слой (стратегия → результат)
Верхний слой над органикой — стратегия и измерение результата в деньгах:
- `prompts/marketing-strategy.md` — цели → **нужна ли реклама** (на цифрах через `roi-calc.py`) → медиаплан/бюджет → KPI.
- `roi-calc.py` — воронка трафик→лиды→заказы→выручка, ROI/CAC/ДРР по каналам, вердикт окупаемости.
- `prompts/distribution-channels.md` — каналы РФ (email/Telegram/видео) + **товарные фиды/маркетплейсы** (Яндекс.Маркет, Озон, Google Merchant).
- `prompts/orm.md` — мониторинг отзывов + алерт на негатив (`notify.py`).
- `prompts/marketing-calendar.md` — единый календарь SEO+соцсети+email+реклама+акции.

Внешнее (подключается отдельно, не код скилла): цели/конверсии в Яндекс.Метрике, коллтрекинг, CRM, кабинеты маркетплейсов, РФ ESP — без них «конечный результат» не измерить.

---

## <a id="фазы"></a>8. 10 фаз — что происходит по шагам

| Фаза | Что делает | Вход → Выход |
|---|---|---|
| **0 Discovery** | Цель, scope, регион, бюджет | вопросы → `00-discovery.md` |
| **1 Audit** | Тех/контент-аудит, гэпы | сайт → `01-audit.md` |
| **2 Keyword research** | Сбор из активных источников (`resolve-sources` → Wordstat/Serpstat/suggest/LLM-CLI/...), кэш, лог источников | тема → `02-keywords.md` (+ raw на диске) |
| **3 Cluster + Intent** | Группировка в кластеры, hub-and-spoke | ключи → `03-clusters.md` |
| **4 Entity Map** | Карта сущностей (Шестаков), 17 разделов, Antigravity+Perplexity evidence, fact_check_log, experience-маркеры | кластер → `04-entity-maps/*.md` |
| **5 Content plan** | Roadmap, приоритеты, перелинковка, сезонность | карты → `05-content-plan.md` |
| **6 Writing** | Текст + tone + AEO + stock-first; QA: стоп-слова → Perplexity+Antigravity fact-check → NW≥65; E-E-A-T trust-блок | бриф → `06-drafts/*.publish.md` |
| **7 Publishing** | Текст + изображения в CMS; для WordPress основной канал REST API + Application Password, MCP опционален, SSH/WP-CLI fallback; alt обязателен для всех недекоративных изображений | draft → опубликовано + `07-published.md` |
| **8 Schema** | JSON-LD + канонический org-узел (`schema-org-build inject`) | страница → `08-schema.md` |
| **9 Monitoring** | Снапшоты GSC/Вебмастер/Метрика | период → `09-monitoring/*-snapshot.json` |
| **10 Iteration** | `triggers-eval` + `source-attribution` → доработки | снапшот → `10-iterations.md` |

Артефакты каждого запуска — в `seo/cycles/<тема>-<квартал>/`.

---

## <a id="агенты"></a>9. Агенты и делегаты — кого как вызывать

В Claude Code логика делегируется субагентам (поле `delegate.*` в конфиге). Для seo-cycle ставь нужные агенты локально в проекте (`.claude/agents/` или `.agents/`), чтобы они не появлялись в проектах без установки:

| Агент | Для чего | Когда |
|---|---|---|
| `seo-orchestrator` | Координатор комплексной задачи | «запусти полный цикл», многошаговое |
| `seo-auditor` | Тех/контент-аудит | Phase 1 |
| `seo-keyword-researcher` | Сбор/кластеризация семантики | Phase 2-3 |
| `seo-content-strategist` | Контент-план, KPI | Phase 5 |
| `seo-content-writer` | Написание текстов | Phase 6 |
| `yandex-seo-specialist` | Яндекс-экосистема (Wordstat/Вебмастер/Бизнес) | Phase 2, 9 (РФ) |
| `seo-linkbuilder` | Линкбилдинг | по запросу |
| `seo-monthly-orchestrator` + System-агенты (`-weekly-publisher`, `-monthly-auditor`, `-refresh-rescuer`, `-keyword-queue-manager`, `-approval-gate`) | Месячная автоматизация (Step 10) | по расписанию |

Вызов в Claude Code: через Skill tool (`/seo-cycle` или триггер-фраза) либо Agent tool. В Codex: нативное делегирование (`dispatching-parallel-agents`) — см. `docs/codex-runtime.md`.

Плагины (опционально): `claude-seo:seo-*` (seo-google, seo-dataforseo, seo-schema, seo-cluster, seo-technical).

---

## <a id="команды"></a>10. Команды-шпаргалка

```bash
# Настройка
bash init-project.sh                              # новый проект
python3 validate-config.py                        # проверить конфиг
python3 resolve-sources.py                        # активные источники

# Сбор
python3 serpstat-fetch.py stats                   # остаток кредитов Serpstat
python3 serpstat-fetch.py keywords-info "X" --se g_ru
python3 spyfu-fetch.py usage                      # расход $ SpyFu
bash llm-cli-collect.sh "тема"                    # сбор Antigravity+Codex
python3 yandex-suggest.py "X" --region 213 --depth 2
python3 link-audit.py --input-json linkinator.json --url https://example.com/ --write
python3 redirect-map-audit.py --input redirects.csv --base-url https://example.com --write
python3 gsc-url-inspection.py --input-json gsc-url-inspection.json --url https://example.com/ --site-url sc-domain:example.com --write
python3 bing-url-inspection.py --input-json bing-url-info.json --url https://example.com/ --site-url https://example.com/ --write
python3 technical-mcp-health.py --write
python3 lighthouse-audit.py --input-json lighthouse.json --url https://example.com/ --write
python3 serpstat-audit.py --action basic-info --report-id 123456 --write
python3 labrika-source-pack.py --export-file labrika.md --write
python3 labrika-health.py --write
python3 technical-site-audit.py --write

# E-E-A-T / качество
python3 check-stop-words.py draft.md
python3 schema-org-build.py inject schema/*.json
python3 eeat-render.py draft.publish.md

# Данные / автоматизация
python3 db-sync.py                                # обновить seo.db + дашборд
python3 notify.py --test                          # проверить Telegram
bash monthly-runner.sh status                     # статус автоматизации
bash monthly-runner.sh all                        # по всем проектам реестра
python3 source-attribution.py --csv seo/source-attribution.csv --snapshot <snap>.json
```

---

## <a id="сценарии"></a>11. Типовые сценарии

- **Продвинуть категорию с нуля:** «запусти SEO-цикл для категории "минеральная вата"» → фазы 0→8.
- **Расширить блог под кластер:** «расширь блог под кластер "пароизоляция"» → фазы 2→7.
- **Разбор просадки:** «проанализируй позиции и предложи доработки» → фазы 9→10.
- **Анализ западного конкурента:** `spyfu-fetch.py domain-stats competitor.com --cc US`.
- **Месячная автоматизация:** cron → `monthly-runner.sh` → approval-тикеты → Telegram.

---

## <a id="обновление-доков"></a>12. Обновление документации (обязательное правило)

> **При ЛЮБОМ изменении** кода, конфига, набора инструментов, источников или возможностей — в **том же коммите**:
> 1. Обновить этот `GUIDE.md` (обе версии — RU и EN).
> 2. Добавить запись в `CHANGELOG.md`.
> 3. Поднять `VERSION` по SemVer.
> 4. Если добавлен скрипт/источник/команда — описать его в разделах [Инструменты](#инструменты) и [Команды](#команды).
> 5. Если изменилась установка/запуск — обновить [Установка](#установка) и [Для ИИ](#установка-ии).

Версионирование: SemVer (MAJOR — несовместимые изменения схемы конфига; MINOR — новые источники/скрипты; PATCH — фиксы/доки). Каждый релиз — git-тег `vX.Y.Z`.

---
---

# seo-cycle — Full Guide 🇬🇧

> Universal SEO/content-cycle orchestrator for **Claude Code** and **Codex CLI**.
> One framework drives a site from strategy and keyword research to publishing,
> fact-check, monitoring and iteration. Adapts to any project via the declarative
> `seo-cycle.yaml` config.

Contents: [What it is](#en-what) · [Benefits](#en-benefits) · [Install](#en-install) · [For AI](#en-ai) · [Architecture](#en-arch) · [Runtimes](#en-runtimes) · [Project policies](#en-project-policies) · [Tools](#en-tools) · [10 phases](#en-phases) · [Agents](#en-agents) · [Commands](#en-commands) · [Scenarios](#en-scenarios) · [Updating docs](#en-docs)

---

## <a id="en-what"></a>1. What it is

`seo-cycle` is a **skill** (instructions + scripts) that turns an LLM assistant
(Claude or Codex) into a full SEO specialist for a specific site. It:

- collects keywords from 10+ sources (Yandex, Google, XMLRiver, Serpstat, SpyFu, NeuronWriter, WriterZen browser/export, LLM-CLI, AnswerThePublic, Perplexity);
- always uses Antigravity CLI and Perplexity Deep Research for semantic collection, entity validation, and fact-checking before publication when the tools are available;
- builds an entity map (Shestakov method), clusters, content plan;
- writes copy honoring tone of voice, stock-first, local signals;
- fact-checks and builds E-E-A-T signals;
- publishes to a CMS (WordPress/WooCommerce);
- monitors rankings and produces prioritized fixes;
- runs on schedule (cron) with human approval gates.

**Principle:** the "brain" (reasoning) is the LLM, the "hands" (deterministic ops)
are scripts, the "project truth" lives in one config.

---

## <a id="en-benefits"></a>2. Benefits

| Benefit | How |
|---|---|
| **Universal** | One codebase for RU/EU/US/global — differences in `region_profile` (1 line). |
| **Token-efficient** | Raw research → disk; only distilled summaries enter LLM context. TTL cache prevents re-collection. |
| **Works in Russia** | `ru` profile: Yandex stack + Serpstat (`g_ru`) + RU-available Google tools; blocked tools (Ahrefs/SEMrush) are skipped. |
| **Protects paid limits** | Serpstat/SpyFu/XMLRiver clients have credit/budget guards and caching. |
| **Dual runtime** | Runs under both Claude Code and Codex CLI (hybrid: our scripts + native skills). |
| **E-E-A-T built-in** | Canonical Organization/LocalBusiness node, source trust-block, source→top attribution. |
| **Scales to N projects** | Project registry + `init-project.sh` + `monthly-runner.sh all`. |
| **Token and budget control** | `governance` + `tool-budget.yaml` + `governance-report.py`: cache-first, raw to disk, distillates in context, approval gates. |
| **Task-level routing** | `task-router.py --task "..."` selects only the needed phases/sources and reports approval gates, blocked actions, automation, and context caps. |
| **Actual usage ledger** | `usage-ledger.py report/check/record`: append-only tracking for tokens, USD, requests, credits, units, browser minutes, and subscriptions. |
| **Spend guard** | `spend-guard.py --write`: allowed/approval/blocked status for paid/API/LLM/subscription services, remaining limits, reserves, and preflight commands. |
| **Per-project tool stack** | `tool-stack-recommender.py --write` decides Google/Yandex/Bing/Microsoft/NLP/AI/merchant/local/ads/tracking tools by country, business type, budget, and RF policy. |
| **Growth roadmap** | `growth-roadmap.py --write` builds a top-N roadmap across technical, search evidence, ecommerce/local, entities/content, AI visibility, CRO/marketing, and automation gates. |
| **Onboarding playbook** | `setup-onboarding.py --write` creates a detailed first-run checklist with owners, human-secret env names, approval gates, commands, and proof artifacts. |
| **Setup blueprint** | `setup-blueprint.py --write` creates a compact matrix for countries, regions, search engines, business type, marketing/ads/tracking policy, tools, budgets, subscriptions, automations, and guardrails. |
| **Upgrade/access assistants** | `project-upgrade-assistant.py --write` and `access-key-assistant.py --write` provide review-only upgrades for old projects plus project-specific key/token steps without secret values. |
| **Safe upgrade apply** | `project-upgrade-apply.py --write` dry-runs/applies reviewed missing `policy_files` for old projects with a backup, without secrets or paid/dangerous actions. |
| **Launch plan** | `launch-plan.py --write` creates the first project screen with market/business matrix, token/budget/subscription controls, tool packs, env names, approval gates, and execution order. |
| **Project journey** | `project-journey.py --write` shows the current stage from setup to goal, missing artifacts/blockers, next command, and exit criteria for moving forward. |
| **Context pack** | `context-pack.py --task "..." --write` creates the first short Claude/Codex handoff with `context_manifest`, read order, task route, caps, spend blockers, approval gates, and do-not-load-raw. |
| **Token/provider evidence** | `token-waste-audit.py`, `perplexity-health.py`, `notebooklm-health.py`, `xmlriver-health.py`, `writerzen-health.py`, `perplexity-collect.py`, `notebooklm-source-pack.py`, `xmlriver-source-pack.py`, `writerzen-browser-collect.py`, `writerzen-source-pack.py`: raw/large artifact checks, provider health, and raw/distillate/vector source packs without password storage. WriterZen browser collector creates reports, captures downloads and imports them into distillates. |
| **Per-project automations** | `automation-recommender.py --write` recommends tool-aware planned automations by business type, market, tool stack/spend guard, indexability, search consoles, Bing, schema/CWV, content decay, ecommerce/local, and AI visibility. |
| **Transparent** | All artifacts are files in the project repo; single SQLite DB; Obsidian dashboard. |

---

## <a id="en-install"></a>3. Install (for humans)

```bash
# Codex-first: one command from YOUR project root
cd /path/to/your-project
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash

# Claude Code variant:
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-claude.sh | bash

# Bootstrap installs core, dependencies, symlinks, runs the wizard,
# and creates seo-cycle.yaml, .env.example, .env, AGENTS.md/CLAUDE.md, and setup reports.

# Existing project: update shared core and refresh local setup surface
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash -s -- --skip-init
python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-control-plane.py --write
```

Shared core: `~/.codex/vendor/seo-cycle`. Project-local entrypoints are created only by bootstrap: `./.codex/skills/seo-cycle`, `./.agents/skills/seo-cycle`, `./.claude/skills/seo-cycle` symlink to that shared core. Projects that were not bootstrapped do not load seo-cycle.

---

## <a id="en-ai"></a>4. Install for an AI agent (self-service)

> Machine-executable script. An AI agent (Claude/Codex/any) can run it itself,
> step by step, without a human (except entering secret keys).

```bash
# Codex-first bootstrap: installs core, dependencies, symlinks, and runs the wizard.
cd <project-root>
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash

# Claude Code variant:
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-claude.sh | bash

# After bootstrap, the human only fills secrets in .env.
```

**Rules for the AI agent (self-check before working):**
1. Read `SKILL.md` (or `AGENTS.md` for Codex) — the 10-phase logic.
2. Read the project `seo-cycle.yaml` — rules/sources/locale.
3. Read the project `CLAUDE.md` (if present) — project rules (tone, stock-first, fact-check).
4. Run `resolve-sources.py` — learn which sources are active.
5. Never pull raw research into context — only `*-merged-*.md` and `02-keywords.md`.
6. In Codex mode, do not call `codex exec` inside itself — use native skills (see `docs/codex-runtime.md`).

---

## <a id="en-arch"></a>5. Architecture

```
┌─ LLM brain (Claude Skill tool / Codex) ── REASONING ──┐
│  entity map · writing · fact-check · QA · decisions     │  ← not portable to scripts
└────────────────────────────────────────────────────────┘
        ↓ invokes                       ↓ writes artifacts
┌─ Scripts = hands (scripts/) ──────────────────────────┐
│  collection · cache · publishing · aggregation · alerts │
└────────────────────────────────────────────────────────┘
        ↓ single data layer             ↓ alerts
┌─ seo.db (SQLite) ──┐   ┌─ notify.py (Telegram) ────────┐
└─────────────────────┘   └────────────────────────────────┘
        ↓ visualization
   Obsidian dashboard (auto from db-sync)
```

- **Config = single source of truth.** `seo-cycle.yaml`: locale, `region_profile`, `runtime`, sources, `business_profile`, tone, publishing, delegate map.
- **Region profile** (`config/region-profiles/{ru,eu,us,global}.yaml`) switches the source set with one line.

---

## <a id="en-runtimes"></a>6. Runtimes: Claude and Codex

Mode is set by `runtime: auto|claude|codex` in config or `SEO_RUNTIME` env.

| | Claude Code | Codex CLI |
|---|---|---|
| Entry point | `SKILL.md` | `AGENTS.md` (symlink → `SKILL.md`) |
| Images | `codex exec` wrapper | native `seo-image-gen`/`image`/`sora` |
| Browser (Perplexity/Wordstat/Webmaster) | Claude in Chrome MCP | `browser`/`playwright`/`screenshot` |
| Delegation | subagents (`Agent`) | `dispatching-parallel-agents` |
| Our scripts | via bash | via bash (identical) |

Run under Codex:
```bash
cd <project>
export SEO_RUNTIME=codex
codex exec -c model_reasoning_effort="xhigh" -c web_search="live" \
  "Read AGENTS.md and seo-cycle.yaml. Run Phase 2 for cluster X."
```
Full mapping — [docs/codex-runtime.md](docs/codex-runtime.md).

---

## <a id="en-modularity"></a>6b. Modular architecture (phase skills + state)

`seo-cycle` is a **dispatcher**. Phases are gradually extracted into standalone **phase skills** (each a `SKILL.md` + README folder — invokable independently, shareable, sellable separately). Coordination is via a single state file `seo/cycles/<topic>/_state.json` (the `cycle-state.py` contract). This is the "handoff chain": a phase skill reads state → does its job → updates state → unblocks the next phase.

**Extracted (pilot):** `seo-keywords` (Phase 2-3). **Status: splitting is frozen** (decision 2026-05-30) — the monolithic `seo-cycle` is primary; remaining phases are not extracted without a clear need (selling modules / a team / reuse / parallelism).

**v1.63 Pifagor orchestrator pilot:** old commands remain callable, while the new thin `seo-cycle-run.py` layer reads a stage contract and executes `stage -> gate -> repair -> rerun -> next stage`. It is not a self-rewriting automation layer; it is a control shell. Each stage declares inputs, commands, expected outputs, a command gate or output gate, repair commands, `max_attempts` (default 5), approval flag, stop conditions, and `next_stage`. Reports are written under `seo/orchestrator/`; if the gate still fails after the limit, the run writes a blocker report.

```bash
python3 ./.codex/skills/seo-cycle/scripts/cycle-state.py init --topic "mineral wool"
python3 ./.codex/skills/seo-cycle/scripts/cycle-state.py next      # unblocked phases
# → invoke the matching phase skill (seo-keywords, etc.)
python3 ./.codex/skills/seo-cycle/scripts/cycle-state.py gate keywords
python3 ./.codex/skills/seo-cycle/scripts/cycle-state.py show      # progress

# New v1.63 pilot without a separate stage file:
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --goal "build research package" --write
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --stage-template research-package --package seo/research-package --write
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --stage-template copywriting --draft seo/research-package/drafts/sample.md --write

# Contract run from JSON/YAML:
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py --stage-file seo/stages/research-package.yaml --write
```

Benefits of splitting: reuse (phase outside the cycle), clarity/control (visible progress and gates), parallelism (independent phases at once), sale (a module is a separate product). "Improvement" is data-driven (`source-attribution.py` + `triggers-eval.py`), no code self-rewriting.

---

## <a id="en-project-policies"></a>6c. Project-local policies

Before starting phases, making API calls, spending credits, or changing tracking/indexing behavior, read project-local policy files when present:

- `seo/neuronwriter-limits.yaml` — NeuronWriter plan, remaining quota, reserve, reset time, allowed automation spend.
- `seo/neuronwriter.md` — NeuronWriter workflow, project ID, helper commands, and scoring policy.
- `seo/entities/google-nlp-policy.yaml` — Google Cloud Natural Language budget alert, cache TTL, per-run limits, unit caps, and language restrictions.
- `seo/seo-data-collection-map.md` — approved data sources, AI visibility checks, ecommerce/product sources, tracking/tag policy.
- `seo/access-setup-runbook.md` — connected accounts, skipped paid services, API notes, operational constraints.
- `seo/ai-visibility-prompts.csv` — starter AI visibility query queue and evidence fields for Google AI/Bing Copilot/Perplexity/OpenAI/Claude/Gemini/DeepSeek.
- `seo/tool-budget.yaml` — token/API/LLM/subscription caps, cache policy, stop conditions.
- `seo/tool-stack.generated.yaml` and `seo/setup/tool-stack-report.md` — generated tool decisions: enabled/report-only/approval-required/disabled/not-applicable.
- `seo/growth-roadmap.generated.yaml` and `seo/setup/growth-roadmap.md` — top-N priorities across technical/search evidence/ecommerce/local/content/entities/AI visibility/CRO/automation.
- `seo/onboarding.generated.yaml`, `seo/setup/onboarding-playbook.md`, and `seo/setup/onboarding-checklist.csv` — first-run checklist with owners, human-secret env names, approval gates, commands, and proof files.
- `seo/setup-blueprint.generated.yaml`, `seo/setup/setup-blueprint.md`, and `seo/setup/setup-matrix.csv` — low-token setup matrix for countries, regions, search engines, business type, marketing/ads/tracking policy, tools, budget/subscriptions, automations, guardrails, and first-read files.
- `seo/setup/upgrade-assistant.md` and `seo/setup/upgrade-questionnaire.csv` — review-only worksheet for enabling new functionality in existing projects.
- `seo/setup/project-upgrade-apply.md`, `seo/setup/project-upgrade-apply.json`, and `seo/setup/project-upgrade-apply.csv` — safe updater for old projects: dry-run/apply reviewed missing `policy_files` keys with a backup; applies only with `--apply`.
- `seo/setup/access-key-assistant.md` and `seo/setup/access-key-assistant.csv` — project-specific key/token checklist with env names, links, and steps, without secret values.
- `seo/launch-plan.generated.yaml`, `seo/setup/launch-plan.md`, and `seo/setup/launch-checklist.csv` — first-screen launch contract for market/business/tools/token/budget/subscriptions/approval/execution order.
- `seo/setup/project-journey.md`, `seo/setup/project-journey.json`, and `seo/setup/project-journey-checklist.csv` — automatic project journey: current stage, missing artifacts, blockers, next command, exit criteria, and action plan.
- `seo/orchestrator/latest-run.md/json`, `seo/orchestrator/*-report.md/json`, `seo/orchestrator/*-blocker.md/json` — v1.63 staged orchestrator artifacts: what ran, how many gate/repair attempts happened, which outputs are missing, and which stop conditions need a human decision.
- `seo/research-package/research-package-quality.md`, `seo/research-package/research-package-quality.json`, and `seo/research-package/research-package-action-plan.md` — quality gate and step-by-step action plan for a site-level research package before repair/writing.
- `seo/research-package/research-package-repair.md/json`, `seo/research-package/semantic-core.cleaned.csv`, `seo/research-package/semantic-core.rejected.csv`, `seo/research-package/semantic-core.resynced.csv`, `seo/research-package/entity_coverage.jsonl`, `seo/research-package/content-plan.orphan-backlog.csv`, `seo/research-package/serp-validation-plan.csv`, `seo/research-package/serp-validation-import.md/json`, `seo/research-package/spoke-opportunities.csv`, `seo/research-package/entity-graph-quality.md/json` — repair layer for comparison-report findings: semantic-core cleanup, URL/cluster ID resync, entity-map sync, Google NLP aggregation, orphan backlog, missing SERP validation plan, guarded reviewed SERP export import, phase-2 spokes, and entity graph quality.
- `seo/research-package/page-outline-quality.md`, `seo/research-package/page-outline-quality.json`, and latest copies — quality gate for MVP/P1 page briefs before writing/design/schema/publishing.
- `<draft>.draft-quality-gate.md/json` — gate for a Markdown draft against `page-outline-v2`: missing H2/H3, unsafe first-person expertise, missing internal links, missing proof/source slots, and FAQ mismatch.
- `seo/setup/context-pack.md` and `seo/setup/latest-context-pack.md` — first-read context pack for the current task: `context_manifest`, read order, task route, caps, spend blockers, approval gates, do-not-load-raw, and next commands.
- `seo/setup/token-waste-audit.md`, `seo/setup/perplexity-health.md`, `seo/setup/notebooklm-health.md`, `seo/setup/xmlriver-health.md`, `seo/setup/writerzen-health.md` — low-token/provider readiness: raw/large artifact findings, Perplexity persistent app/browser/API optional mode, NotebookLM MCP/export fallback, XMLRiver readiness/prices/capabilities, WriterZen browser/export readiness.
- `seo/research/raw/*`, `seo/research/distillates/*`, `seo/research/vector/source_pack.jsonl` — source evidence contract for Perplexity/NotebookLM/XMLRiver: raw stays on disk; downstream context gets only distillates/latest-summary + citations.
- `seo/setup/setup-gap-audit.md`, `seo/setup/setup-questionnaire.md`, and `seo/setup/setup-questionnaire.csv` — readiness score, missing fields, and a fillable worksheet for market, business, local/ecommerce, tools, budget/subscriptions, spend guard, and automations.
- `seo/setup/setup-answer-plan.md` and `seo/setup/setup-answer-plan.csv` — review-only manual change plan from filled `setup-questionnaire.csv`; secret-like answers are rejected and not stored.
- `seo/automation-policy.yaml` — scheduled automations, approval gates, forbidden actions.
- `seo/automation-policy.generated.yaml` — generated overlay with recommended automations, tools, and approval gates; apply only after review.
- `seo/automations/automation-recommendations.md` — human-readable automation recommendations by project type/market/tools/spend guard.
- `seo/usage/usage-ledger.jsonl` — append-only actual usage ledger for tokens, USD, credits, units, requests, and browser minutes.
- `seo/setup/latest-usage-ledger.md` — current monthly usage report plus cap/approval/block status.
- `seo/spend-guard.generated.yaml`, `seo/setup/spend-guard.md`, and `seo/setup/spend-checklist.csv` — spend/subscription guard with allowed/approval/blocked status, remaining limits, and preflight commands.
- `seo/setup/setup-control-plane.md` — compact readiness report: intake/profile/sources/governance/validation/tool stack/spend guard/growth roadmap/onboarding/launch-plan/project-journey/setup-blueprint/upgrade/access-key/context-pack/token-waste/provider-health/setup-gap-audit/automation + next actions.
- `seo/setup/latest-task-route.md` — low-token route for the latest task: phases, sources, approval gates, blocked actions, automation, and context caps.
- `seo/project-intake.yaml` — detailed map of countries, regions, search engines, ads, local/merchant/video/analytics decisions.
- `seo/project-intake-report.md` — human-readable intake report for review before profile/apply.

Rules:

- NeuronWriter is the primary SERP/NLP content editor for briefs, terms, entities, questions, competitor scores, final scoring, and the plagiarism gate when `NEURON_API_KEY`, the helper, and a limits file are present.
- WriterZen is a browser/export source without a public API in this workflow: use an already logged-in browser for Topic Discovery, Keyword Explorer, Keyword Planner and Domain Focus, export CSV/XLSX into `seo/research/writerzen/imports/`, then run `writerzen-source-pack.py --write`; downstream prompts use only distillates/vector records.
- Track Plagiarism Checker through NeuronWriter quota in `usage-ledger.py` by default: run `check --service neuronwriter --category paid_api --plagiarism-checks 1 --fail-on-block` before the final check and `record` after it. Run the check from the NeuronWriter Editor menu after `import-content`, because the public API documentation describes `import-content`/`evaluate-content` but not a separate plagiarism endpoint. Use WriterZen Plagiarism only as a manual fallback/export, not as the primary gate.
- Google Cloud Natural Language is a guarded technical entity audit layer for entities, salience, syntax/category, and `title/H1/schema/text` mismatches. It is not a ranking submission mechanism or direct ranking signal.
- Whole-site NeuronWriter/Google NLP jobs are forbidden without an approved URL/keyword queue and enough remaining policy budget.
- Run `governance-report.py` before expensive collection or automation; if budget/approval does not allow it, do only report-only/cached/read-only steps.
- Before each concrete task, run `task-router.py --task "..." --write` and follow `seo/setup/latest-task-route.md` so unnecessary phases/sources are skipped.
- After task-router, run `context-pack.py --task "..." --write` and open `seo/setup/context-pack.md` first; open detailed reports only when they appear in the read order.
- After first run or policy changes, run `setup-gap-audit.py --write` and close missing fields through `seo/setup/setup-questionnaire.csv` / `seo/setup/setup-gap-audit.md` before broad cycles, paid API/LLM use, bulk local/ecommerce work, or automations. After filling the CSV, run `setup-answer-plan.py --write` and apply only reviewed safe values manually.
- Before actual spend, run `usage-ledger.py check ... --fail-on-block`; after spend, record it with `usage-ledger.py record ... --write`.
- Before paid/API/LLM/subscription spend, run `spend-guard.py --write`; if the service is not allowed or has approval/blocked status, stop until approval/policy changes.
- Before connecting new Google/Yandex/Bing/Microsoft/NLP/AI/merchant/local/ads/tracking tools, run `tool-stack-recommender.py --write`; use `--apply` only after review.
- Before broad cycles or marketing tasks, run `growth-roadmap.py --write` and start from `seo/setup/growth-roadmap.md`.
- Before first run, use `setup-onboarding.py --write` / `seo/setup/onboarding-playbook.md`; never store secret values in the playbook.
- Before reading detailed setup reports, run `context-pack.py --write` / open `seo/setup/context-pack.md`, then `project-journey.py --write` / open `seo/setup/project-journey.md`, then `setup-blueprint.py --write` / open `seo/setup/setup-blueprint.md`, then `project-upgrade-assistant.py --write` / open `seo/setup/upgrade-questionnaire.csv`, then `access-key-assistant.py --write` / open `seo/setup/access-key-assistant.md`, then `setup-gap-audit.py --write` / open `seo/setup/setup-questionnaire.csv` and `seo/setup/setup-gap-audit.md`, after filling the CSV run `setup-answer-plan.py --write` / open `seo/setup/setup-answer-plan.md`, then `launch-plan.py --write` / open `seo/setup/launch-plan.md`; these are the low-token entry point, step-by-step journey, project setup matrix, review-only upgrade, key/token checklist, fillable worksheet, review-only manual change plan, and first project screen.
- Before `automation-plan.py`, run `automation-recommender.py --write`; use `--apply` only after review and `--allow-schedules` only with explicit permission. Expanded tasks must stay report-only/dry-run or env-gated until approval.
- Low-token mode is mandatory: raw CSV/JSON/HTML to disk, only distillates/top-N in context; do not read the whole repository or raw source files without need. After broad collection, run `token-waste-audit.py --write`.
- Use Perplexity through a persistent app/browser session when available; API is optional/paid and disabled by default. Use NotebookLM only as curated expert evidence with citations/source excerpts, not as volume/KD/ranking signal. Use XMLRiver as approval-gated paid SERP/Wordstat enrichment: prefer `--input-file`, live only with `--live --allow-paid` after spend guard.
- For the writing phase after a research package, run `research-package-quality.py --write`, then `research-package-repair.py --write` or the targeted repair scripts from the action plan, import externally reviewed SERP evidence with `serp-validation-import.py --input-json/--input-csv --write` when applicable, rerun `research-package-quality.py --write`, then `page-outline-v3.py --all-mvp --write` or `--priority P1 --write`, then `page-outline-quality.py --version v3 --write`. If repair/import is newer than quality, `project-journey.py` blocks writing until quality is rerun. Draft from `copywriter-ready/*.md`, `copywriting_playbook`, `writer_prompt_packet`, and `metrics_rollup` into `<package>/drafts/*.md`, then run `draft-quality-gate.py <draft.md> --outline <page-outlines-v3/slug.json> --write`; `project-journey.py` blocks implementation/publishing until `content_draft_gate` passes. Run NeuronWriter only after `usage-ledger.py check --service neuronwriter --category paid_api --content-writer 1 --ai-credits 500 --fail-on-block`; it is a guarded SERP/NLP/scoring/evaluate/import layer, not a mandatory auto-writer. Do not load raw research unless the gate requests a specific source.
- Robots/Content-Signal: `search=yes, ai-input=yes, ai-train=no` is acceptable as a model-training opt-out. Public `robots.txt` must be clean `text/plain`, with no PHP warnings/HTML or editor/preview noise.
- For Russian/RF projects, do not add foreign analytics/tracking tags or pixels without explicit policy approval. GSC, Bing Webmaster, PageSpeed/CrUX, sitemap/robots checks, and off-site API audits are acceptable because they do not install analytics code.
- Never print API keys, OAuth tokens, service-account JSON, or `.env` values; use variable names and paths only.

### 6.1 Optional AI/dev support toolchain

For `seo-cycle` development, larger changes, evidence ingestion, and graph-based navigation, use the local support toolchain:

```bash
bash ./.codex/skills/seo-cycle/scripts/install-ai-toolchain.sh --codex
bash ./.codex/skills/seo-cycle/scripts/install-ai-toolchain.sh --codex --notebooklm
bash ./.codex/skills/seo-cycle/scripts/install-ai-toolchain.sh --check
```

| Tool | When to use | Safety rule |
|---|---|---|
| GitHub Spec Kit (`specify`) | Large `seo-cycle` changes: constitution → spec → plan → tasks → implementation | Does not replace SEO phases and is not needed for small edits |
| Microsoft MarkItDown (`markitdown`) | PDF/XLSX/DOCX/PPTX/HTML/YouTube → Markdown for evidence/fact-check/entity extraction | Trusted local files or explicitly approved URLs only |
| Graphify (`graphify`) | Mixed graph across code, docs, markdown, research artifacts, and media | Keep `graphify-out/` as a local cache unless there is a clear reason to commit it |
| CodeGraph (`codegraph`) | Local code-symbol graph + Codex MCP for understanding code without broad file reads | `.codegraph/` is a local index and must not be committed |
| NotebookLM MCP (`notebooklm`) | Access to the user's curated expert knowledge base: videos/articles/notes about SEO/AEO/GEO | Only after Google `setup_auth`; use answers with citations/source excerpts as expert synthesis, not as unchecked facts |

CloakBrowser/CloakMCP and other stealth/anti-bot tools are not part of the standard set. For SEO collection, follow robots, rate limits, project policy, and source terms.

---

## <a id="en-tools"></a>7. Tools (what · command · output)

> In an installed project, scripts are available through `./.codex/skills/seo-cycle/scripts/`. The shared updatable core lives in `~/.codex/vendor/seo-cycle`. Run via `python3 <script>.py` or `bash <script>.sh`. Core scripts support system Python 3.9+; UTC timestamps use a compatible timezone-aware helper.

### 7.0 Local AI/dev support toolchain
| Tool | What | Command | Output |
|---|---|---|---|
| `install-ai-toolchain.sh` | Installs Spec Kit, MarkItDown, Graphify, CodeGraph, and Codex integrations for Graphify/CodeGraph | `bash install-ai-toolchain.sh --codex` / `--check` | Local CLIs, Graphify skill, CodeGraph MCP config |
| `specify` | Spec-driven workflow for large `seo-cycle` changes | `specify init <project> --integration codex` | `.specify/`, Codex skills/commands for spec/plan/tasks |
| `markitdown` | Converts trusted documents to Markdown for the evidence layer | `markitdown source.pdf -o evidence.md` | Markdown distillate for fact-check/entity extraction |
| `graphify` | Knowledge graph across code/docs/research/media | `graphify update . --no-cluster` / `$graphify` | `graphify-out/graph.json`, graph reports/query |
| `codegraph` | Local code-symbol graph + MCP for Codex | `codegraph init .` / `codegraph status .` | `.codegraph/` SQLite index, MCP `codegraph` |
| `notebooklm` | MCP access to NotebookLM notebooks | `bash install-ai-toolchain.sh --codex --notebooklm` | Codex MCP config; then `setup_auth`, `add_notebook`, `ask_question` |

### 7.1 Source & config management
| Script | What | Command | Output |
|---|---|---|---|
| `validate-config.py` | Validates config, env, delegates, policy files, governance | `python3 validate-config.py` | Active sources, missing keys/policies, ✓/errors |
| `resolve-sources.py` | Expands `region_profile` + overrides into active sources | `python3 resolve-sources.py` | Active/skipped sources with reason + `active-sources.json` |
| `setup-control-plane.py` | Single low-token setup/readiness report for intake/profile/sources/governance/validation/tool stack/spend guard/growth roadmap/onboarding/launch-plan/project-journey/setup-blueprint/upgrade/access-key/context-pack/token-waste/provider-health/setup-gap-audit/automation/task route/usage ledger | `python3 setup-control-plane.py --write` | `seo/setup/setup-control-plane.md/json`, latest validation/governance/sources/tool stack/spend/growth roadmap/onboarding/launch-plan/project-journey/setup-blueprint/upgrade/access-key/context-pack/token-waste/provider-health/setup-gap-audit/task route/usage |
| `project-journey.py` | Shows the current stage from setup to goal, what is missing for the next step, blockers, next command, and exit criteria | `python3 project-journey.py --write` / `--goal "publish approved cluster"` | `seo/setup/project-journey.md/json`, `project-journey-checklist.csv`, latest copies |
| `seo-cycle-run.py` | v1.63 staged orchestrator: runs contract stages with gate, repair, rerun, blocker reports, and latest run summary | `python3 seo-cycle-run.py --goal "build research package" --write` / `--stage-template setup-readiness --goal "first SEO setup" --write` / `--stage-template research-package --package seo/research-package --write` / `--stage-template copywriting --draft <draft.md> --write` / `--stage-file stages.yaml --write` | `seo/orchestrator/latest-run.md/json`, `<stage>-report.md/json`, `<stage>-blocker.md/json` |
| `stage-template-export.py` | Writes editable project-local stage contract templates without secrets or overwriting manual edits | `python3 stage-template-export.py --write` | `seo/stages/setup-readiness.yaml`, `seo/stages/research-package.yaml`, `seo/stages/copywriting-draft.yaml`, `stage-template-export.md/json` |
| `task-router.py` | Builds a low-token route for one SEO/marketing task | `python3 task-router.py --task "indexation audit" --write` | `seo/setup/latest-task-route.md/json` + archived route |
| `context-pack.py` | Builds the first short task-scoped handoff for Claude/Codex with `context_manifest` | `python3 context-pack.py --task "indexation audit" --write` | `seo/setup/context-pack.md/json`, `seo/setup/latest-context-pack.md/json` |
| `token-waste-audit.py` | Finds raw/large artifacts and oversized distillates that waste context | `python3 token-waste-audit.py --write` | `seo/setup/token-waste-audit.md/json`, latest copies |
| `perplexity-health.py` | Checks Perplexity persistent app/browser/API optional mode without password storage | `python3 perplexity-health.py --write` | `seo/setup/perplexity-health.md/json`, latest copies |
| `notebooklm-health.py` | Checks NotebookLM MCP/tools and browser/manual export fallback | `python3 notebooklm-health.py --write` | `seo/setup/notebooklm-health.md/json`, latest copies |
| `xmlriver-health.py` | Checks XMLRiver readiness, env names, prices and capabilities without live paid API | `python3 xmlriver-health.py --write` | `seo/setup/xmlriver-health.md/json`, latest copies |
| `writerzen-health.py` | Checks WriterZen browser/export readiness without password storage | `python3 writerzen-health.py --browser-available --write` | `seo/setup/writerzen-health.md/json`, latest copies |
| `writerzen-browser-collect.py` | Opens WriterZen in a persistent browser profile, creates the required reports, downloads CSV/XLSX into `seo/research/writerzen/imports/`, then runs the importer in one command | `python3 writerzen-browser-collect.py --topic "OSB board" --force-new-report --manual-fallback-seconds 120 --write` | `seo/setup/writerzen-browser-collect.md/json` + WriterZen raw/distillate/vector |
| `perplexity-collect.py` | Caches Perplexity export/raw response, writes bounded distillate with citations and a vector record; paid API disabled by default | `python3 perplexity-collect.py --topic "OSB board" --raw-file response.md --write` | `seo/research/raw/perplexity/*.json`, `seo/research/distillates/perplexity/*.md/json`, `seo/research/vector/source_pack.jsonl` |
| `notebooklm-source-pack.py` | Ingests NotebookLM MCP/browser/manual export as curated expert evidence, not as a ranking signal | `python3 notebooklm-source-pack.py --topic "SEO" --export-file notebook.md --write` | `seo/research/raw/notebooklm/*.json`, `seo/research/distillates/notebooklm/*.md/json`, `seo/research/vector/source_pack.jsonl` |
| `xmlriver-source-pack.py` | Guarded XMLRiver adapter: Google/Yandex SERP XML, Wordstat New JSON, ads/shopping/maps/suggest/AI Overview request plans; live only with `--live --allow-paid` | `python3 xmlriver-source-pack.py --query "OSB board" --engine google --input-file serp.xml --write` | `seo/research/raw/xmlriver/*.json`, `seo/research/distillates/xmlriver/*.md/json`, `seo/research/vector/source_pack.jsonl` |
| `writerzen-source-pack.py` | Ingests WriterZen browser exports: Topic Discovery, Keyword Explorer, Keyword Planner, Domain Focus; normalizes volume/KD/CPC/intent/Buying Journey/SERP Type/Allintitle/KGR | `python3 writerzen-source-pack.py --topic "OSB board" --export-file writerzen.csv --write` | `seo/research/raw/writerzen/*.json`, `seo/research/distillates/writerzen/*.md/json`, `seo/research/vector/source_pack.jsonl` |
| `research-package-quality.py` | Quality gate for a site-level research package: SERP validation gaps, URL/cluster drift, dirty GSC rows, duplicate briefs, orphan URLs, entity drift, raw Google NLP, unused AI Overview/GEO signals, E-E-A-T/evidence gaps; returns a 10-criterion scorecard and automatic action plan | `python3 research-package-quality.py ./research-package --write`; short launch mode: `--format plan` | `research-package-quality.md/json`, `research-package-action-plan.md`; exits 1 on critical findings |
| `research-package-repair.py` | One-command repair wrapper: runs cleanup/resync/entity/NLP/orphan/SERP/spoke/entity-graph steps and writes aggregate status | `python3 research-package-repair.py ./research-package --write` | `research-package-repair.md/json` + repair artifacts |
| `semantic-core-clean.py` / `semantic-core-resync.py` | Core repair: moves prompt/spam-like GSC rows into rejected CSV and resyncs `semantic-core` with final cluster IDs/URLs after reclustering | `python3 semantic-core-clean.py ./research-package --write`; then `python3 semantic-core-resync.py ./research-package --write` | `semantic-core.cleaned.csv`, `semantic-core.rejected.csv`, `semantic-core.resynced.csv`, `.md/.json` reports |
| `entity-map-sync.py` / `google-nlp-aggregate.py` | Entity repair: renders `entity-map.md` from YAML without dropped attributes, deduplicates Google NLP entities, aggregates mentions/salience/types, and writes a compact coverage layer | `python3 entity-map-sync.py ./research-package --write`; `python3 google-nlp-aggregate.py ./research-package --write` | `entity-map.md`, `entity_coverage.jsonl`, `.md/.json` reports |
| `orphan-url-resolver.py` / `serp-validation-plan.py` / `serp-validation-import.py` / `spoke-opportunity-audit.py` | Architecture repair: turns orphan internal URLs into backlog rows, plans missing SERP checks, imports reviewed DataForSEO/Serpstat/manual SERP exports back into `semantic-architecture-final.json`, and promotes measured GSC long-tail into phase-2 spokes | `python3 orphan-url-resolver.py ./research-package --write`; `python3 serp-validation-plan.py ./research-package --write`; `python3 serp-validation-import.py ./research-package --input-json serp-export.json --write`; `python3 spoke-opportunity-audit.py ./research-package --write` | `content-plan.orphan-backlog.csv`, `serp-validation-plan.csv`, `serp-validation-import.md/json`, `spoke-opportunities.csv`, `.md/.json` reports |
| `page-outline-v3.py` | Generates copywriter-ready H2/H3 briefs from a research package: tool-first ordering for tool/app/quiz pages, `copywriter-ready/*.md`, section/H3 word counts, `metrics_rollup`, intro/conclusion, SEO meta, Key Takeaways, FAQ answer guidelines, visual inventory, writer handoff, `copywriting_playbook`, `writer_prompt_packet`, source slots, acceptance criteria, entity triplets, schema, internal links, synthetic prompts, E-E-A-T guard | `python3 page-outline-v3.py ./research-package --all-mvp --write`; single page: `--page "/tools/virtual-hair-color-try-on/"`; expert mode: `--expert-author` | `page-outlines-v3/<page>.md/json`, `copywriter-ready/<page>.md`, `vector/page_outline_triplets.jsonl` |
| `page-outline-v2.py` | Legacy-compatible H2/H3 page briefs; retained for old projects and duplicate legacy archiving | `python3 page-outline-v2.py ./research-package --all-mvp --write`; duplicate legacy archive: `--archive-legacy-briefs` | `page-outlines-v2/<page>.md/json`; optional `archive/legacy-briefs/` |
| `page-outline-quality.py` | Quality gate for page briefs: word-count drift, H3/H2 mismatch, SERP/page-type lock, intro/conclusion, SEO meta, Key Takeaways, FAQ, handoff, copywriting playbook, writer prompt packet, revision checklist, fact-check queue, schema, internal links, Answer Units, source slots, acceptance criteria, entity orphans, bridges, visuals, trust limits, synthetic prompts, fabricated first-person expertise, v3 tool-first ordering, v3 visual inventory and triplet export | `python3 page-outline-quality.py ./research-package --version v3 --write`; short mode: `--format markdown` | `page-outline-quality.md/json`, `latest-page-outline-quality.md/json`; exits 1 on critical findings |
| `entity-graph-quality.py` / `draft-quality-gate.py` | Quality gates after repair/briefing: catch duplicate/orphan triplets, entity weights without sources, and in drafts missing H2/H3, required links, source/proof slots, and unsafe first-person expertise | `python3 entity-graph-quality.py ./research-package --write`; `python3 draft-quality-gate.py draft.md --outline page-outlines-v3/page.json --write` | `entity-graph-quality.md/json`, `<draft>.draft-quality-gate.md/json` |
| `technical-site-audit.py` | Aggregates latest technical distillates into one low-token rollup without live runs | `python3 technical-site-audit.py --write` | `seo/technical/technical-site-audit.md/json`, latest copies |
| `link-audit.py` | Distills `linkinator` JSON or explicit live crawl: broken links, redirects, HTTP links | `python3 link-audit.py --input-json linkinator.json --url https://example.com/ --write` | `seo/technical/link-audit.md/json`, raw/distillate/vector source records |
| `redirect-map-audit.py` | Audits CSV redirect maps for chains, loops, self-redirects, missing targets, and optional live status | `python3 redirect-map-audit.py --input redirects.csv --base-url https://example.com --write` | `seo/technical/redirect-map-audit.md/json`, raw/distillate/vector source records |
| `lighthouse-audit.py` | Distills Lighthouse JSON or explicit live run: performance, SEO, accessibility, CWV, opportunities | `python3 lighthouse-audit.py --input-json lighthouse.json --url https://example.com/ --write` | `seo/technical/lighthouse-audit.md/json`, raw/distillate/vector source records |
| `gsc-url-inspection.py` | Guarded Google URL Inspection adapter: input JSON or read-only live OAuth token | `python3 gsc-url-inspection.py --input-json gsc-url-inspection.json --url https://example.com/ --site-url sc-domain:example.com --write` | `seo/technical/gsc-url-inspection.md/json`, raw/distillate/vector source records |
| `gsc-indexing-export-browser.py` | Opens GSC Pages/issue URL, captures export download and can immediately build the indexing queue | `python3 gsc-indexing-export-browser.py --issue-url "<GSC issue URL>" --manual-fallback-seconds 120 --build-queue --write` | `seo/technical/gsc-indexing-export.md/json`, `seo/technical/gsc-indexing/imports/*` |
| `gsc-indexing-queue.py` | Builds a top-10/top-20 queue from GSC discovered/not-indexed export + sitemap + WooCommerce + GSC impressions; filters junk and technical blockers | `python3 gsc-indexing-queue.py --gsc-discovered-file exports/discovered.csv --gsc-performance-file exports/gsc-performance.json --woocommerce-file exports/woo.csv --technical-check --top 20 --write` | `seo/technical/gsc-indexing-queue.md/json`, `seo/technical/gsc-indexing-request-queue.csv` |
| `gsc-request-indexing-browser.py` | Opens GSC URL Inspection through a persistent browser profile and clicks Request indexing only with explicit `--auto-click` | `python3 gsc-request-indexing-browser.py --queue-file seo/technical/gsc-indexing-request-queue.csv --max 10 --auto-click --write` | `seo/technical/gsc-indexing-submit.md/json` |
| `gsc-indexing-recheck.py` | Rechecks submitted URLs after 3-7 days from fresh GSC exports/search data | `python3 gsc-indexing-recheck.py --submitted-log seo/technical/gsc-indexing-submit.json --gsc-discovered-file exports/discovered-after-7d.csv --write` | `seo/technical/gsc-indexing-recheck.md/json` |
| `indexnow-submit.py` | Bulk notifies IndexNow/Bing/Yandex-compatible endpoints from the P0/P1 queue; live only with `INDEXNOW_KEY` | `INDEXNOW_KEY=*** INDEXNOW_KEY_LOCATION=https://example.com/key.txt python3 indexnow-submit.py --queue-file seo/technical/gsc-indexing-request-queue.csv --priority P0,P1 --max 100 --live --write` | `seo/technical/indexnow-submit.md/json`, `seo/technical/indexnow-submit-log.csv` |
| `yandex-recrawl-submit.py` | Sends P0/P1 URLs to Yandex Webmaster `/recrawl/queue` and checks recrawl queue status | `YANDEX_OAUTH_TOKEN=*** python3 yandex-recrawl-submit.py --queue-file seo/technical/gsc-indexing-request-queue.csv --priority P0,P1 --max 20 --live --write` / `--mode status --live` | `seo/technical/yandex-recrawl-submit.md/json`, `seo/technical/yandex-recrawl-status.md/json` |
| `bing-url-inspection.py` | Guarded Bing Webmaster `GetUrlInfo`: input JSON or read-only live API key | `python3 bing-url-inspection.py --input-json bing-url-info.json --url https://example.com/ --site-url https://example.com/ --write` | `seo/technical/bing-url-inspection.md/json`, raw/distillate/vector source records |
| `technical-mcp-health.py` | Checks optional MCP readiness for mcp-gsc, Google Analytics MCP, and Lighthouse MCP without installing servers or reading secrets | `python3 technical-mcp-health.py --write` | `seo/technical/technical-mcp-health.md/json`, latest copies |
| `serpstat-audit.py` | Guarded Serpstat API adapter: projects/create/start/settings/issue reports/export/basic-info/categories/scan-urls; live only with `SERPSTAT_API_KEY` | `python3 serpstat-audit.py --action basic-info --report-id 123 --write` / `--live` | `seo/technical/serpstat-audit.md/json`, raw/distillate/vector source records |
| `labrika-source-pack.py` | Ingests Labrika manual/browser export as third-party technical evidence until public API is confirmed | `python3 labrika-source-pack.py --export-file labrika.md --write` | `seo/technical/labrika-source-pack.md/json`, `seo/research/raw/labrika/*`, vector records |
| `labrika-health.py` | Records Labrika API readiness, support questions, and manual/export fallback | `python3 labrika-health.py --write` | `seo/technical/labrika-health.md/json`, latest copies |
| `setup-blueprint.py` | Builds a compact per-project setup matrix for countries, regions, engines, business, marketing/ads/tracking, tools, budget, subscriptions, automations, and guardrails | `python3 setup-blueprint.py --write` | `seo/setup-blueprint.generated.yaml`, `seo/setup/setup-blueprint.md/json`, `seo/setup/setup-matrix.csv`, latest copies |
| `project-upgrade-assistant.py` | Checks an existing project against the current template/control-plane surface and writes a review-only yes/no/defer worksheet | `python3 project-upgrade-assistant.py --write` | `seo/setup/upgrade-assistant.md/json`, `seo/setup/upgrade-questionnaire.csv`, latest copies |
| `project-upgrade-apply.py` | Safely applies reviewed missing `policy_files` keys from the upgrade questionnaire with a backup; default dry-run, no secrets/paid actions/publishing | `python3 project-upgrade-apply.py --write` / `--apply --write` / `--use-defaults` | `seo/setup/project-upgrade-apply.md/json/csv`, backup `seo-cycle.yaml.bak-*` on apply |
| `access-key-assistant.py` | Builds needed key/token steps from tool-stack and `.env`: env names, provider links, short steps, no secret values | `python3 access-key-assistant.py --write` | `seo/setup/access-key-assistant.md/json/csv`, latest copies |
| `setup-gap-audit.py` | Checks detailed project readiness and creates a fillable owner worksheet for business, local/ecommerce, tools, budget/subscriptions, and automations | `python3 setup-gap-audit.py --write` | `seo/setup/setup-gap-audit.md/json`, `seo/setup/setup-questionnaire.md/csv/json`, latest copies |
| `setup-answer-plan.py` | Reads the filled setup questionnaire and builds a review-only manual change plan without storing secret-like answers | `python3 setup-answer-plan.py --write` | `seo/setup/setup-answer-plan.md/json/csv`, latest copies |
| `usage-ledger.py` | Tracks actual tokens, USD, credits, units, requests, browser minutes and checks caps | `python3 usage-ledger.py report --write` / `check --service openai --usd 0.25 --fail-on-block` / `record --service openai --usd 0.25` | `seo/usage/usage-ledger.jsonl`, `seo/setup/latest-usage-ledger.md/json` |
| `spend-guard.py` | Shows allowed/approval/blocked status for paid/API/LLM/subscription services, remaining limits, and preflight commands | `python3 spend-guard.py --write` | `seo/spend-guard.generated.yaml`, `seo/setup/spend-guard.md/json`, `seo/setup/spend-checklist.csv` |
| `tool-stack-recommender.py` | Recommends the tool stack from country/search engines/business/local/ecommerce/budget/tracking policy | `python3 tool-stack-recommender.py --write` / `--apply` | `seo/tool-stack.generated.yaml`, `seo/setup/tool-stack-report.md/json`, optional backup+safe source flags |
| `growth-roadmap.py` | Builds a top-N roadmap across technical/search evidence/ecommerce/local/content/entities/AI visibility/CRO/automation | `python3 growth-roadmap.py --write` / `--max-actions 8` | `seo/growth-roadmap.generated.yaml`, `seo/setup/growth-roadmap.md/json` |
| `setup-onboarding.py` | Builds the detailed first-run checklist with owners, env names, approval gates, commands, and proofs | `python3 setup-onboarding.py --write` / `--max-steps 24` | `seo/onboarding.generated.yaml`, `seo/setup/onboarding-playbook.md/json`, `seo/setup/onboarding-checklist.csv` |
| `launch-plan.py` | Builds the first low-token project screen with market/business/tools/token/budget/subscriptions/env/approval/execution contract | `python3 launch-plan.py --write` / `--max-execution-steps 12` | `seo/launch-plan.generated.yaml`, `seo/setup/launch-plan.md/json`, `seo/setup/launch-checklist.csv` |
| `automation-recommender.py` | Recommends tool-aware planned automations from intake/business/market/tool-stack/spend-guard/policy | `python3 automation-recommender.py --write` / `--apply` | `seo/automations/automation-recommendations.md/json`, `seo/automation-policy.generated.yaml`, optional backup+policy update |
| `project-intake-wizard.py` | Fills `seo/project-intake.yaml` for a concrete project | `python3 project-intake-wizard.py --interactive --write` / `--defaults --write` | `seo/project-intake.yaml`, `seo/project-intake-report.md` |
| `project-profile.py` | Builds per-project profile from `seo/project-intake.yaml` | `python3 project-profile.py --write` / `--apply` | `seo/project-profile.generated.yaml`, report, optional backup+`seo-cycle.yaml` update |
| `governance-report.py` | Shows token/budget/tool/automation policy without secrets | `python3 governance-report.py --format md` | Markdown/JSON report for Phase 0 and approval gates |
| `automation-plan.py` | Generates safe schedule plan, cron, launchd templates, and safe commands for spend/index/search/schema/CWV/content/local/ecommerce tasks | `python3 automation-plan.py --write --include-disabled` | `seo/automations/automation-plan.md`, `crontab.txt`, plist templates; install blocked without policy |
| `init-project.sh` | New-project wizard | `bash init-project.sh` | `seo-cycle.yaml`, `.env.example`, policy files, registry entry |
| `cycle-state.py` | Cycle state contract (handoff between phase skills) | `python3 cycle-state.py init --topic "X"` / `next` / `set <phase> --status done --gate-passed` / `show` | `_state.json` with phase DAG; the "handoff chain" |

### 7.2 Keyword research
| Script | What | Command | Output |
|---|---|---|---|
| `yandex-suggest.py` | Long-tail from Yandex Suggest (free) | `python3 yandex-suggest.py "<seed>" --region 213 --depth 2` | CSV of suggestions |
| `google-suggest.py` | Long-tail from Google Suggest | `python3 google-suggest.py "<seed>" --region RU` | keyword list |
| `google-trends.py` | Seasonality/trends | `python3 google-trends.py "<topic>" --region RU` | markdown trend |
| `serpstat-fetch.py` | Volume/KD/CPC + competitors (incl. RU `g_ru`) | `python3 serpstat-fetch.py keywords-info "<kw>" --se g_ru` | md table; cache; credit guard (`stats`) |
| `keyso-fetch.py` | **Keys.so — Yandex/RU**: Wordstat volumes, visibility, competitors, lost keywords | `python3 keyso-fetch.py competitors <domain>` / `keyword-info "<kw>"` / `lost <domain>` | md table; **60d cache** + usage tracker (`_usage.json`); 10/10s limit |
| `competitor-discovery.py` | Find **closest competitors** via SERP top of commercial keywords (Keys.so) | `python3 competitor-discovery.py "kw1" "kw2" --exclude-giants` | ranked competitor list + giants flag |
| `keyso-save.py` | Save a domain group (competitors) **into the Keys.so account** (write-API `/report/group`) | `python3 keyso-save.py group-report --from-config` | report rid in Keys.so |
| `keyso-clustering-export.py` | Prepare keyword file for Keys.so clustering (upload via browser, see `prompts/keyso-clustering-upload.md`) | `python3 keyso-clustering-export.py --from-keyso-cache <domain> --out keys.txt` | .txt one keyword per line |
| `spyfu-fetch.py` | Competitor/PPC US/UK/EU (not RU) | `python3 spyfu-fetch.py domain-stats <domain> --cc US` | md table; $-budget tracker |
| `atp-fetch.py` | AnswerThePublic question templates (en/us) | `python3 atp-fetch.py "<en keyword>"` | md questions/prepositions/comparisons |
| `nw-cli.sh` | NeuronWriter: SERP terms/entities/score | `bash nw-cli.sh get <query_id>` | terms, entities, competitors, target score |
| `llm-cli-collect.sh` | Parallel Antigravity + Codex (RUNTIME-aware, deep mode); Antigravity is mandatory for semantics/intents/entities | `bash llm-cli-collect.sh "<topic>"` | 2 raw files + merge hint |
| `llm-cli-merge.py` | Merge+dedup LLM-CLI results | `python3 llm-cli-merge.py a.md b.md -o merged.md` | `*-merged-*.md` (distilled) |
| `research-cache.py` | TTL cache for expensive collection | `python3 research-cache.py check --dir ... --slug ... --source ... --ttl 14` | path to fresh cache (HIT) or exit 1 (MISS) |
| `google-nlp-audit.py` | Guarded Google Cloud NLP entity/category/syntax audit with cache and unit caps | `python3 google-nlp-audit.py --project-root . --url https://example.com/ --dry-run` | JSON plan/cache/API results; no publishing and no guard bypass |

Mandatory rule: a full cycle's semantic collection and Entity Map are not complete without Antigravity CLI and Perplexity Deep Research. Raw outputs are saved to disk; only the merged/distilled artifact is pulled into context. If Perplexity or Antigravity is unavailable, record a blocker/exception in the artifact.

### 7.3 Monitoring data (Google/Yandex)
| Script | What | Command |
|---|---|---|
| `gsc-fetch.py` | Google Search Console queries | `python3 gsc-fetch.py --site <url> --days 90` |
| `ga4-fetch.py` | Google Analytics 4 traffic/behavior | `python3 ga4-fetch.py ...` |
| `psi-fetch.py` | PageSpeed Insights / CrUX (Core Web Vitals) | `python3 psi-fetch.py <url>` |
| `webmaster-fetch.py` | Yandex.Webmaster queries | `python3 webmaster-fetch.py ...` |
| `metrika-fetch.py` | Yandex.Metrika | `python3 metrika-fetch.py ...` |
| `snapshot-build.py` | Merges sources into one snapshot | `python3 snapshot-build.py ...` → `*-snapshot.json` |
| `lost-keywords.py` | Lost/dropped keywords between two snapshots | `python3 lost-keywords.py --old O.json --new N.json` |
| `competitor-benchmark.py` | Median benchmark vs competitors (where you're below) | `python3 competitor-benchmark.py bench.csv --md` |

### 7.4 Content, E-E-A-T, quality
| Script | What | Command | Output |
|---|---|---|---|
| `check-stop-words.py` | Catches banned words / brand transliteration | `python3 check-stop-words.py <file>` | violations list |
| `schema-org-build.py` | Canonical Organization/LocalBusiness JSON-LD from `business_profile` | `python3 schema-org-build.py inject schema/*.json` | @id node + author/publisher as @id |
| `eeat-render.py` | "Sources" trust-block from `fact_check_log` | `python3 eeat-render.py <publish.md>` | HTML sources block |
| `schema-validate.py` | JSON-LD validation | `python3 schema-validate.py <file>` | errors/warnings |
| `source-attribution.py` | Which source produced top-ranking keywords | `python3 source-attribution.py --csv ... --snapshot ...` | yield table + disable-weak recommendations |
| `ice-score.py` | ICE prioritization of findings (competitor analysis/audit) | `python3 ice-score.py findings.csv --md` | list by ICE (Impact×Confidence×Ease) with zones 🔥/✅/⏳ |
| `roi-calc.py` | Funnel & ROI/CAC/DRR per channel — the bottom-line result in money | `python3 roi-calc.py funnel.csv --margin 0.3` | per-channel table + verdict "what pays off / is ads needed" |
| `programmatic-template-gen.py` | Programmatic pages (city×category) | `python3 programmatic-template-gen.py ...` | page templates |
| `validate-entities.py` | Entity registry check | `python3 validate-entities.py` | cross-links/errors |

### 7.5 Publishing (CMS)
| Script | What |
|---|---|
| `img-generate.sh` | Image generation (RUNTIME-aware: codex exec / native image-skill) |
| `wp-photo-image.py` | Deterministic photo pipeline: local file/URL → crop by `images.aspect_ratios.*` → WebP → WordPress upload through SSH/WP-CLI → alt/caption/featured |
| (project) `wp-*-publish.py` | Publish posts/categories/pages |

Image gate: settings come from `images.*` in `seo-cycle.yaml`: `workflow`, `source_policy`, `visual_style`, `aspect_ratios`, `output`, `captions`, `alt`, `lazy_loading`, `upload`. For photo-first workflow, use `wp-photo-image.py` instead of manual cropping. Inline images should be clean topical photos/visuals that match the project's style. Do not add visible text to the image (SEO/AEO/GEO, process diagrams, labels, product descriptions, catalog disclaimers) when `images.allow_visible_text=false`, and do not make product-card collages the main visual unless explicitly requested. Every non-decorative image must have `alt` before publication: featured, inline, OG/schema, product/category visuals. Inline images must also have a short editorial caption when `images.captions.inline_required=true`. Alt text and captions should describe the visible object and page entity naturally, without keyword stuffing or process/meta explanations. After publication, verify public HTML and a browser screenshot: `<img>` without `alt`, an inline image without required caption, forbidden visible text on/under an image, or a lazy-load placeholder instead of the first-screen photo is a blocker/exception in the log. If an optimizer rewrites the first/above-the-fold inline image to a placeholder, exclude only that critical image from lazy-load (`skip-lazy`/`data-no-lazy` or CMS equivalent) and re-check. Keep lower inline images lazy-loaded.

### 7.6 Data, automation, alerts
| Script | What | Command | Output |
|---|---|---|---|
| `db-sync.py` | CSV/JSON → single `seo.db` + Obsidian dashboard | `python3 db-sync.py` | positions/queue/usage/attribution tables + dashboard md |
| `notify.py` | Telegram alerts (graceful no-op without token) | `python3 notify.py "text" --level alert` / `--test` | Telegram message |
| `monthly-runner.sh` | Auto-detect op by date; `all` — across registry | `bash monthly-runner.sh status` / `all` | runs the right system + approval tickets |
| `approval-gate.py` | File-based approval tickets (+ notify) | `python3 approval-gate.py create --type custom --title "..."` | ticket in `pending-approvals.md` |
| `keyword-queue.py` | FIFO keyword queue | `python3 keyword-queue.py status` | queue state |
| `triggers-eval.py` | Phase 10 rules (drops, striking distance) | `python3 triggers-eval.py snapshot.json triggers.yaml` | prioritized action list |
| `deindex-detect.py` | Deindexation (sitemap vs GSC) | `python3 deindex-detect.py ...` | dropped URLs |
| `obsidian-sync.py` | Mirror artifacts to Obsidian | `python3 obsidian-sync.py` | vault notes |
| `monthly-dashboard.py` | Markdown status dashboard | `python3 monthly-dashboard.py` | report |

### 7.7 Local SEO (maps: Google + Yandex/2GIS)
Local-dominance tactics — paired for both map ecosystems (in Russia, Yandex.Maps + 2GIS take priority). Prompts: `prompts/local/google-maps.md` + `prompts/local/yandex-maps.md` (categories/rubrics, review velocity, posts calendar, visual dominance, local visibility). Business/competitor source — `business_profile` (`gbp_url`, `yandex_business_url`, `2gis_url`, `competitors[]`). Run via browser (Chrome MCP / browser-skill).

| Script | What | Command | Output |
|---|---|---|---|
| `review-velocity.py` | Catch-up plan vs leader by reviews (Google/Yandex/2GIS) | `python3 review-velocity.py --my-total N --leader-total M --leader-30d X --my-target-30d Y` | reviews/month needed + catch-up time |

Already covered elsewhere: keyword gap → `serpstat-fetch competitors`/SpyFu; positions 11-20 → `triggers-eval` (striking_distance); backlinks → `seo-backlinks`/`seo-ahrefs`; general GBP/NAP → `seo-maps`/`seo-local` plugins.

### 7.8 Marketing bridges (marketing-skills + RU adaptation)
The `marketing-skills` plugin (CRO, paid traffic, retention, monetization) complements seo-cycle. Enabled via the `marketing` config section. The "phase → skill" map and **RU channel swaps** (Yandex.Direct instead of Google Ads, VK/Telegram instead of Meta, Yandex.Metrika, 2GIS/Yandex.Business, YooKassa) live in `docs/marketing-bridges.md`. Chain: seo-cycle (organic) → `page-cro`/`form-cro` (conversion) → `referral-program`/`email-sequence` (retention). Don't duplicate the plugin's SEO skills — run SEO through seo-cycle.

### 7.9 Marketing layer (strategy → result)
Top layer above organic — strategy and measuring the result in money:
- `prompts/marketing-strategy.md` — goals → **is paid advertising needed** (on numbers via `roi-calc.py`) → media plan/budget → KPIs.
- `roi-calc.py` — funnel traffic→leads→orders→revenue, ROI/CAC/DRR per channel, payback verdict.
- `prompts/distribution-channels.md` — RU channels (email/Telegram/video) + **product feeds/marketplaces** (Yandex.Market, Ozon, Google Merchant).
- `prompts/orm.md` — review monitoring + negative-review alert (`notify.py`).
- `prompts/marketing-calendar.md` — unified calendar SEO+social+email+ads+promos.

External (connected separately, not skill code): goals/conversions in Yandex.Metrika, call tracking, CRM, marketplace dashboards, RU ESP — without them the bottom-line result can't be measured.

---

## <a id="en-phases"></a>8. The 10 phases — step by step

| Phase | What | In → Out |
|---|---|---|
| **0 Discovery** | Goal, scope, region, budget | questions → `00-discovery.md` |
| **1 Audit** | Tech/content audit, gaps | site → `01-audit.md` |
| **2 Keyword research** | Collect from active sources (`resolve-sources` → Wordstat/Serpstat/suggest/LLM-CLI/...), cache, source log | topic → `02-keywords.md` (+ raw on disk) |
| **3 Cluster + Intent** | Group into clusters, hub-and-spoke | keywords → `03-clusters.md` |
| **4 Entity Map** | Entity map (Shestakov), 17 sections, Antigravity+Perplexity evidence, fact_check_log, experience markers | cluster → `04-entity-maps/*.md` |
| **5 Content plan** | Roadmap, priorities, internal links, seasonality | maps → `05-content-plan.md` |
| **6 Writing** | Copy + tone + AEO + stock-first; QA: stop-words → Perplexity+Antigravity fact-check → NW≥65; E-E-A-T trust-block | brief → `06-drafts/*.publish.md` |
| **7 Publishing** | Text + images to CMS; for WordPress, primary channel is REST API + Application Password, MCP is optional, SSH/WP-CLI is fallback; alt is required for every non-decorative image | draft → published + `07-published.md` |
| **8 Schema** | JSON-LD + canonical org node (`schema-org-build inject`) | page → `08-schema.md` |
| **9 Monitoring** | GSC/Webmaster/Metrika snapshots | period → `09-monitoring/*-snapshot.json` |
| **10 Iteration** | `triggers-eval` + `source-attribution` → fixes | snapshot → `10-iterations.md` |

Each run's artifacts go to `seo/cycles/<topic>-<quarter>/`.

---

## <a id="en-agents"></a>9. Agents & delegates — who to call

In Claude Code, work is delegated to subagents (`delegate.*` in config). For seo-cycle, install required agents locally in the project (`.claude/agents/` or `.agents/`) so they do not appear in projects without bootstrap:

| Agent | For | When |
|---|---|---|
| `seo-orchestrator` | Coordinator of complex tasks | "run full cycle", multi-step |
| `seo-auditor` | Tech/content audit | Phase 1 |
| `seo-keyword-researcher` | Collect/cluster keywords | Phase 2-3 |
| `seo-content-strategist` | Content plan, KPIs | Phase 5 |
| `seo-content-writer` | Writing | Phase 6 |
| `yandex-seo-specialist` | Yandex ecosystem | Phase 2, 9 (RU) |
| `seo-linkbuilder` | Link building | on demand |
| `seo-monthly-orchestrator` + system agents | Monthly automation (Step 10) | scheduled |

Invoke in Claude Code via Skill tool (trigger phrase) or Agent tool. In Codex: native delegation (`dispatching-parallel-agents`) — see `docs/codex-runtime.md`.

Optional plugins: `claude-seo:seo-*` (seo-google, seo-dataforseo, seo-schema, seo-cluster, seo-technical).

---

## <a id="en-commands"></a>10. Command cheat-sheet

```bash
# Setup
bash init-project.sh
python3 validate-config.py
python3 resolve-sources.py

# Collection
python3 serpstat-fetch.py stats
python3 serpstat-fetch.py keywords-info "X" --se g_ru
python3 spyfu-fetch.py usage
bash llm-cli-collect.sh "topic"
python3 yandex-suggest.py "X" --region 213 --depth 2
python3 link-audit.py --input-json linkinator.json --url https://example.com/ --write
python3 redirect-map-audit.py --input redirects.csv --base-url https://example.com --write
python3 gsc-url-inspection.py --input-json gsc-url-inspection.json --url https://example.com/ --site-url sc-domain:example.com --write
python3 bing-url-inspection.py --input-json bing-url-info.json --url https://example.com/ --site-url https://example.com/ --write
python3 technical-mcp-health.py --write
python3 lighthouse-audit.py --input-json lighthouse.json --url https://example.com/ --write
python3 serpstat-audit.py --action basic-info --report-id 123456 --write
python3 labrika-source-pack.py --export-file labrika.md --write
python3 labrika-health.py --write
python3 technical-site-audit.py --write

# E-E-A-T / quality
python3 check-stop-words.py draft.md
python3 schema-org-build.py inject schema/*.json
python3 eeat-render.py draft.publish.md

# Data / automation
python3 db-sync.py
python3 notify.py --test
bash monthly-runner.sh status
bash monthly-runner.sh all
python3 source-attribution.py --csv seo/source-attribution.csv --snapshot <snap>.json
```

---

## <a id="en-scenarios"></a>11. Common scenarios

- **Promote a category from scratch:** "run the SEO cycle for category X" → phases 0→8.
- **Expand blog for a cluster:** "expand the blog for cluster Y" → phases 2→7.
- **Investigate a ranking drop:** "analyze positions and suggest fixes" → phases 9→10.
- **Analyze a Western competitor:** `spyfu-fetch.py domain-stats competitor.com --cc US`.
- **Monthly automation:** cron → `monthly-runner.sh` → approval tickets → Telegram.

---

## <a id="en-docs"></a>12. Updating documentation (mandatory rule)

> **On ANY change** to code, config, tools, sources or capabilities — in the **same commit**:
> 1. Update this `GUIDE.md` (both RU and EN).
> 2. Add a `CHANGELOG.md` entry.
> 3. Bump `VERSION` per SemVer.
> 4. If a script/source/command was added — document it in [Tools](#en-tools) and [Commands](#en-commands).
> 5. If install/run changed — update [Install](#en-install) and [For AI](#en-ai).

Versioning: SemVer (MAJOR — incompatible config-schema changes; MINOR — new sources/scripts; PATCH — fixes/docs). Each release is a git tag `vX.Y.Z`.
