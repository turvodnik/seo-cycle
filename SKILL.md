---
name: seo-cycle
description: Универсальный SEO/контент-цикл — тонкий оркестратор модульных фазовых скиллов (v2). От стратегии и сбора семантики до публикации, fact-check, мониторинга и итераций. Используй когда пользователь просит «запусти SEO-цикл», «полная SEO-стратегия с нуля», «продвинь раздел X», «семантическое ядро + контент-план + публикация», «мониторинг и обновления», «универсальный SEO под мой проект». Отдельные задачи (аудит, семантика, Entity Map, тексты, публикация, мониторинг, итерации) — это самостоятельные модули в `skills/*`, запускаются и поодиночке, и конвейером через единый `_state.json`. Адаптация под проект — `seo-cycle.yaml` (язык, регион, поисковики, тип проекта, CMS, источники, tone). При первом запуске без конфига — install wizard. НЕ для одношаговых микрозадач, у которых есть точечный скрипт/скилл.
---

# Универсальный SEO-цикл (`seo-cycle`) — оркестратор v2

Скилл-оркестратор полного SEO-цикла для **любого проекта**. Все решения config-driven: один и тот же фреймворк работает для интернет-магазина в РФ, англоязычного блога, локального бизнеса или SaaS — отличия задаются в `seo-cycle.yaml` проекта.

> **Документация.** Полное руководство (RU + EN) — `GUIDE.md`; установка — `INSTALL.md`; архитектура — `docs/architecture.md`. **Правило: при ЛЮБОМ изменении кода/конфига/возможностей обнови `GUIDE.md`, `CHANGELOG.md` в том же коммите + подними `VERSION` по SemVer.**

> **Рантайм (Claude / Codex / Gemini).** Этот файл — точка входа Claude Code; `AGENTS.md` (симлинк сюда) — точка входа Codex. Режим: `runtime:` в конфиге или env `SEO_RUNTIME=claude|codex|auto`. Логика фаз одинакова; маппинг инструментов в codex-режиме — `docs/codex-runtime.md`.

> **Экономия контекста — правило №1.** Не загружай этот репозиторий целиком. Точка входа под задачу: `seo-cycle status` → `seo/setup/context-pack.md` → нужный модуль `skills/<имя>/SKILL.md`. Общие правила подгружай по требованию из `skills/_shared/*`.

## Модульная архитектура v2

`seo-cycle` — **диспетчер**. Каждая фаза — самостоятельный модуль в `skills/`, запускается **отдельно** (по своему триггеру) или **конвейером** через единый файл состояния `seo/cycles/<тема>/_state.json` (контракт `scripts/cycle-state.py`): модуль читает state на входе, делает своё, обновляет state на выходе, разблокируя следующую фазу.

| Фаза | Модуль | Что делает | Выход |
|---|---|---|---|
| 0 | *(оркестратор, ниже)* | Discovery & Project Setup | `00-discovery.md` |
| 1 | `skills/seo-audit` | аудит сайта, локальные карты, конкуренты+ICE | `01-audit.md` |
| 2–3 | `skills/seo-keywords` | семантика из активных источников + кластеры (внешний репозиторий seo-keywords) | `02-keywords.md`, `03-clusters.md` |
| 4 | `skills/seo-entity-map` | Entity Map по Шестакову, evidence через Antigravity/Perplexity | `04-entity-maps/*` |
| 5–6 | `skills/seo-writing` | контент-план + тексты, fact-check, стоп-слова, draft-gate | `05-content-plan.md`, `06-drafts/*` |
| 7–8 | `skills/seo-publishing` | CMS-aware публикация + JSON-LD/Organization | `07-published.md`, `08-schema.md` |
| 9 | `skills/seo-monitoring` | pulse-снапшоты GSC/Вебмастер/Метрика/PSI | `09-monitoring/*-snapshot.json` |
| 10 | `skills/seo-iteration` | triggers-eval, source attribution, KPI-контракт | `10-iterations.md` |

Реестр модулей — `skills/manifest.yaml` (валидируется `scripts/skill-manifest-validate.py`). Общие фрагменты — `skills/_shared/`: `policy-intake.md` (политики/бюджеты проекта — читать до платных действий), `scorecard.md` (обязательная самооценка), `rag-usage.md`, `toolchain.md`, `setup-commands.md`, `customization.md`, `sources-of-truth.md`, `lessons-learned.md`.

Как диспетчер ведёт цикл:
```bash
python3 scripts/cycle-state.py init --topic "<тема>"   # создать цикл + _state.json
python3 scripts/cycle-state.py next                      # какие фазы разблокированы
# → открыть skills/<модуль>/SKILL.md соответствующей фазы и работать по нему
python3 scripts/cycle-state.py gate <phase>              # проверить quality-gate
python3 scripts/cycle-state.py show                      # прогресс цикла
```
Перед передачей фазы дальше диспетчер проверяет **quality-gate**. Независимые фазы (где `depends_on` уже `done`) можно запускать параллельно. Управление «улучшением» — на данных: `source-attribution.py` + `triggers-eval.py`, **без** авто-переписывания кода.

**Канон контент-конвейера.** Для контента канонический путь — research-package цепочка с жёсткими гейтами: `research-package-quality` → `page-outline-v3` → `page-outline-quality` → draft → `draft-quality-gate` (всё через `seo-cycle loop`). Каталоги `seo/cycles/<тема>/00–10` — рамка оркестрации и место артефактов фаз; они не подменяют research-package гейты, а ссылаются на них.

## Единый CLI (`seo-cycle`)

`install.sh` ставит symlink `~/.local/bin/seo-cycle` → `bin/seo-cycle`. Это тонкий диспетчер над скриптами (полный passthrough аргументов, exit-коды и stdout-контракты не меняются). Предпочитай его прямым `python3 scripts/...`-вызовам в инструкциях пользователю:

```bash
seo-cycle status                 # дашборд: стадия, возраст снапшота, P0, approvals, next command
seo-cycle doctor                 # первый шаг диагностики: config/journey/spend/ledger/provider health
seo-cycle loop <target> <path>   # автоцикл качества (см. секцию ниже)
seo-cycle resume <target> <path> # продолжить прерванный loop (= loop ... --resume)
seo-cycle gate research-package|outline|draft [...]
seo-cycle repair <package> --write
seo-cycle triggers <snapshot>    # Phase 10: action list по правилам
seo-cycle snapshot [...]         # сборка снапшота мониторинга
seo-cycle cannibalization --write | lost-keywords [...] | ice [...] | attribution [...]
seo-cycle approvals | approve <id> | reject <id>
seo-cycle ads health|fetch|analytics|draft|apply [...]
seo-cycle rag index --write | rag query "<вопрос>" [--global]
seo-cycle run "<задача>"         # task-router; run monthly [...]; run script <name> [...]
```

## Автоцикл качества (loop-runner)

**Вместо ручной пары «gate → repair → gate» всегда используй `seo-cycle loop`** (`scripts/loop-runner.py`). Он сам гоняет проверку и ремонт до прохождения, максимум `governance.loop.max_attempts` попыток (default 5; per-target: research_package 5, page_outline 3, draft 3), ведёт журнал `seo/loops/<loop-id>.json/.md` (виден в project-journey) и делит findings на классы качество/достоверность.

```bash
seo-cycle loop research-package seo/research-package        # machine repair внутри
seo-cycle loop draft <draft.md> --outline <outline.json>    # LLM-protocol
seo-cycle loop page-outline <package>                        # LLM-protocol
# опционально: --phase keywords --cycle-dir <dir> → при успехе cycle-state set --gate-passed
```

Протокол для модели (exit-коды):
- **0 passed** — цель прошла gate; двигайся дальше по journey.
- **3 awaiting_llm** — stdout содержит JSON `{"action_required": "llm_repair", findings, instructions}`. Выполни instructions (перепиши драфт / перегенерируй outline, устрани каждый finding), затем запусти команду с `--resume`. НЕ превышай лимит попыток и не обходи loop прямыми вызовами gate.
- **1 escalated** — лимит исчерпан или нет прогресса (два одинаковых fingerprint подряд). Создан approval-тикет `loop_escalation` + Telegram alert. Остановись, покажи пользователю `seo/loops/<id>.md` и жди решения человека; продолжение — только `--reset` после его правок.
- **2 config error** — почини вызов/конфиг.

Самопроверки: класс `evidence` (eeat_evidence_missing, serp_validation_incomplete, missing_proof_slot, unsafe_first_person_expertise, …) — это честность/достоверность: такие findings нельзя «дожимать» переформулировкой, только реальными источниками и фактами.

**Самооценка обязательна** после каждой содержательной задачи — правила и команды: `skills/_shared/scorecard.md`.

## Платная реклама (полуавтомат, approval-only)

Слой выключен по умолчанию (`ads.enabled: false`). Порядок: `ads health` → `ads fetch` (read-only; default кэш/`--input-file`, live только с `--live` после `seo-cycle spend` и ledger-preflight) → `ads analytics` (SEO+PPC кросс-правила: органика в топ-3 ↔ ставки, конверсионные search terms вне ядра, CPA/ROAS, wasted spend → минус-слова) → `ads draft --create-ticket` (черновики кампаний из семантического ядра, бюджеты = 0 by design) → human approve → `ads apply --ticket <id> --live --allow-write` (только Директ в v1, sandbox-first, кап операций).

Для `region_profile: ru` Google Ads в статусе `region_limited` — **это норма, не ошибка**: primary канал Директ, а Google-драфты экспортируются в Google Ads Editor CSV.

**Локальный RAG** — перед написанием и ресёрчем переиспользуй накопленное: `skills/_shared/rag-usage.md`.

## Когда запускать

Триггеры:
- «запусти полный SEO-цикл / SEO-стратегию для X»
- «продвинь раздел / категорию / тему Y с нуля»
- «семантическое ядро + контент-план + публикация»
- «расширь блог под кластер»
- «мониторинг и план итераций»
- «универсальный SEO под мой проект»
- «настрой seo-cycle для нового проекта»

## Когда НЕ запускать (весь цикл)

- Одиночная фаза — открой её модуль напрямую: аудит → `skills/seo-audit`, семантика → `skills/seo-keywords`, Entity Map → `skills/seo-entity-map`, тексты → `skills/seo-writing`, публикация → `skills/seo-publishing`, позиции → `skills/seo-monitoring`, «что улучшать» → `skills/seo-iteration`.
- Точечные микрозадачи — сразу скрипт/агент: проверка стоп-слов → `scripts/check-stop-words.py`; аудит агентом → `seo-auditor`; проектные publish-скиллы — по registry проекта.
- Если пользователь даёт готовый Entity Map / контент-бриф — заходи сразу на нужную фазу конвейера.

---

## Phase 0 — Discovery & Project Setup (фаза оркестратора)

**Цель:** загрузить конфиг проекта или запустить install wizard, зафиксировать цель и маршрут цикла.

**Шаги:**
1. Найти `seo-cycle.yaml` (поиск: `./seo-cycle.yaml` → `./.seo-cycle.yaml` → `./seo/seo-cycle.yaml` → `./.claude/seo-cycle.yaml`).
2. Если **не найден** — запусти project attach/wizard: `bash <core>/install.sh --project "$(pwd)"` (или `bash <core>/scripts/init-project.sh` при уже подключённом проекте). Wizard создаёт `seo-cycle.yaml`, `.env.example` (только имена ключей — значения в Keychain через `ai-secret`), политики и весь набор `seo/setup/*` артефактов.
3. Если **найден** — провалидировать: `python3 scripts/validate-config.py <path>`.
4. Прочитать `context_files` из конфига (обычно `AGENTS.md`, brand guidelines) и `skills/_shared/policy-intake.md` — локальный контракт проекта (политики, бюджеты, gates).
5. Определить **режим цикла** (`mode` в конфиге, default `standard`): `standard` — все 10 фаз; `migration` — миграция домена/CMS (`docs/migration-planner.md`); `programmatic` — массовая генерация (Phase 4P, `skills/seo-entity-map/templates/programmatic-page.template.md`).
6. Уточнить у пользователя цель цикла (1-3 вопроса): что продвигаем; разовая кампания или регулярный цикл; глубина (семантика / до publish / до monitoring).
7. Зафиксировать low-token маршрут и context pack — читать их первыми:
```bash
python3 scripts/task-router.py --task "<цель пользователя>" --write
python3 scripts/context-pack.py --task "<цель пользователя>" --write
```
Запускай только фазы/источники из маршрута, соблюдая approval gates и context caps.
8. Preflight расхода до платных действий и запись после (`usage-ledger.py check ... --fail-on-block` / `record`) — команды и полный setup/audit набор Phase 0: `skills/_shared/setup-commands.md` (загружай по требованию, не целиком в контекст).
9. **Маркетинг-стратегия** (если `marketing.enabled` и цель шире SEO): оценить, нужна ли платная реклама или хватит органики+локалки — `prompts/marketing-strategy.md` + `scripts/roi-calc.py`. Каналы дистрибуции — `prompts/distribution-channels.md`; единый план — `prompts/marketing-calendar.md`.

**Выход:** `<cycles_root>/<topic>/00-discovery.md` с зафиксированными целями и snapshot config (+ `marketing-strategy.md` при маркетинг-цели). Дальше — по таблице модулей и `cycle-state next`.

---

## Установка и обновление

Полная инструкция — `INSTALL.md`. Кратко: хранилище + версии + attach одной командой `install.sh` (проекты пинуются на версии, обновление — `--pin`/`--upgrade-all`).

### Auth-профили: глобально или per-project

Два уровня хранения ключей (приоритет: process env > Keychain scope проекта > global scope); значения живут в macOS Keychain (`ai-secret`), legacy-цепочка `.env`/`~/.seo-cycle/env.global` поддерживается для совместимости:

```bash
seo-cycle auth list                        # кто настроен и откуда
seo-cycle auth login yandex --global       # общий токен агентства (Метрика/Вебмастер)
seo-cycle auth login gbp                   # OAuth-flow GBP для ЭТОГО проекта
seo-cycle auth login wordpress             # клиентские креды сайта — всегда per-project
```

Секреты не печатаются и не логируются.

### Визуальный дашборд агентства

`seo-cycle web --open` (или двойной клик по «SEO Cycle» на рабочем столе) — локальный веб-интерфейс: портфель по всем проектам, карточка проекта (journey, позиции с дельтами, самооценки), approvals с кнопками одобрить/отклонить, панель безопасных команд (только read-only/локальные отчёты — платное и публикация остаются за CLI+approvals), отчёты клиенту, статус доступов. Токен-защита на localhost; для внешнего `--host` обязателен пароль (`SEO_CYCLE_DASHBOARD_PASSWORD` или `--ask-password`).

## Кастомизация, источники истины, lessons learned

- Адаптация под нишу/проект — `skills/_shared/customization.md` (+ `docs/adapt.md`).
- Универсальные источники истины проекта — `skills/_shared/sources-of-truth.md`.
- Накопленные уроки — `skills/_shared/lessons-learned.md` (пополняется).

## Версионирование

См. `CHANGELOG.md` рядом с этим файлом. v2.0.0: модульные skills/, единый install.sh с версионированным хранилищем; совместимость — старые пути `prompts/*` и `templates/*` работают через симлинк-шимы (удаление в v3).
