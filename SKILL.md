---
name: seo-cycle
description: Универсальный SEO/контент-цикл оркестратор для любого проекта — от стратегии и сбора семантики до публикации, fact-check, мониторинга и итераций. Используй когда пользователь просит «запусти SEO-цикл», «полная SEO-стратегия с нуля», «продвинь раздел X», «семантическое ядро + контент-план + публикация», «расширь блог под кластер», «мониторинг и обновления», «универсальный SEO под мой проект». Адаптируется под конкретный сайт через `seo-cycle.yaml` (язык, регион, поисковики, тип проекта, CMS, источники данных, tone of voice). Поддерживает 10 фаз: discovery → audit → multi-source keyword research (Яндекс Wordstat/Suggest/SERP/Я.Вебмастер + Google GSC/Trends/Suggest + NeuronWriter + LLM CLI Antigravity/Codex + AnswerThePublic + Perplexity Pro) → cluster + intent → Entity Map (методика Шестакова) → content plan → writing → publishing (CMS-aware) → JSON-LD schema → monitoring → iteration. Все шаги config-driven: пропускает источники/фазы, которых нет в проекте. При первом запуске без `seo-cycle.yaml` — запускает install wizard. НЕ для одношаговых задач — для них вызывай конкретный субскилл/агент напрямую.
---

# Универсальный SEO-цикл (`seo-cycle`)

Скилл-оркестратор полного SEO-цикла для **любого проекта**. Все решения config-driven: один и тот же фреймворк работает для интернет-магазина в РФ, англоязычного блога, локального бизнеса в Германии или SaaS-стартапа в США — отличия задаются в `seo-cycle.yaml` проекта.

> **Документация.** Полное руководство (RU + EN, все инструменты/фазы/команды + AI-автоустановка) — `GUIDE.md`. **Правило: при ЛЮБОМ изменении кода/конфига/возможностей обнови `GUIDE.md` (обе версии) и `CHANGELOG.md` в том же коммите + подними `VERSION` по SemVer.**

> **Рантайм (Claude / Codex).** Этот файл — точка входа Claude Code. Если основной мозг — **Codex CLI**, точка входа `AGENTS.md` (симлинк сюда). Режим: `runtime:` в конфиге или env `SEO_RUNTIME=claude|codex|auto`. Логика фаз одинакова; в codex-режиме генерация изображений, браузер (Perplexity/Wordstat/Вебмастер) и делегирование идут через **нативные Codex-skills**, а не `codex exec`-обёртки/Claude-in-Chrome/subagents. Гибрид и маппинг инструментов — в **`docs/codex-runtime.md`** (читай при работе в Codex).

## Project Policy Intake (локальные правила проекта)

Перед выбором фаз, запуском API, расходом кредитов или изменением индексации/аналитики проверь, есть ли в активном проекте локальные SEO-policy файлы:

- `seo/neuronwriter-limits.yaml` — тариф NeuronWriter, остатки, резерв, reset, разрешённый расход автоматизации.
- `seo/neuronwriter.md` — workflow NeuronWriter, project ID, helper-команды, target score.
- `seo/entities/google-nlp-policy.yaml` — статус Google Cloud Natural Language, budget alert, cache TTL, лимиты на запуск, unit caps по функциям, языковые ограничения.
- `seo/seo-data-collection-map.md` — разрешённые источники данных, AI visibility checks, ecommerce/product sources, политика tracking/tag.
- `seo/access-setup-runbook.md` — подключённые аккаунты, пропущенные платные сервисы, API notes, операционные ограничения.
- `seo/ai-visibility-prompts.csv` — стартовая очередь AI visibility запросов и evidence-полей для Google AI/Bing Copilot/Perplexity/OpenAI/Claude/Gemini/DeepSeek.
- `seo/tool-budget.yaml` — лимиты токенов, paid API, LLM, подписок, кэша и stop-условия по источникам.
- `seo/tool-stack.generated.yaml` и `seo/setup/tool-stack-report.md` — рекомендуемый стек Google/Yandex/Bing/Microsoft/NLP/AI/merchant/local/ads/tracking под страну, бизнес, бюджет и policy; создаётся `scripts/tool-stack-recommender.py --write`.
- `seo/growth-roadmap.generated.yaml` и `seo/setup/growth-roadmap.md` — top-N приоритетов по technical/search evidence/ecommerce/local/content/entities/AI visibility/CRO/automation; создаётся `scripts/growth-roadmap.py --write`.
- `seo/automation-policy.yaml` — какие scheduled automations разрешены, какие требуют approval, какие запрещены без явной policy.
- `seo/automation-policy.generated.yaml` и `seo/automations/automation-recommendations.md` — рекомендованный набор автоматизаций по intake/business/market/tools/budget; применять через `scripts/automation-recommender.py --apply`.
- `seo/usage/usage-ledger.jsonl` — append-only журнал фактического расхода токенов/USD/API/credits/units/requests/browser minutes; создаётся `scripts/usage-ledger.py report --write`.
- `seo/setup/latest-usage-ledger.md` — текущий месячный отчёт по usage ledger, остаткам и approval/block status.
- `seo/project-intake.yaml` — детальная карта проекта: страны, регионы, поисковики, local/merchant/ads/video/analytics decisions.
- `seo/project-intake-report.md` — человекочитаемый отчёт по intake; создаётся `scripts/project-intake-wizard.py`.
- `seo/project-profile.generated.yaml` и `seo/project-profile-report.md` — сгенерированный overlay/отчёт по intake; применять к `seo-cycle.yaml` только через явный `scripts/project-profile.py --apply`.
- `seo/setup/setup-control-plane.md` — компактная readiness-сводка intake/profile/sources/governance/validation/tool-stack/growth-roadmap/automation; создаётся `scripts/setup-control-plane.py --write`.
- `seo/setup/latest-task-route.md` — low-token маршрут под последнюю конкретную задачу: фазы, источники, approval gates, blocked actions, automation и context caps; создаётся `scripts/task-router.py --task "..." --write`.

Если файлы есть, они являются локальным контрактом проекта:

- NeuronWriter — основной SERP/NLP редактор для content briefs, terms, entities, questions, competitor scores и финального content scoring, если есть `NEURON_API_KEY`, `seo/scripts/nw.sh` и limits-файл.
- Google Cloud Natural Language — только guarded technical entity audit: entity extraction, salience, syntax/category checks, title/H1/schema/text mismatch. Не описывай его как ranking submission или прямой ranking signal.
- Не запускай whole-site NeuronWriter или Google NLP без конкретной одобренной очереди URL/keywords и достаточного остатка в policy.
- Перед дорогими или широкими задачами запускай `scripts/governance-report.py --format md`: он показывает active sources, budget caps, token policy, missing policy files и approval gates.
- Для первого запуска или handoff используй `scripts/setup-control-plane.py --write`: он собирает low-token readiness report и next actions без вывода секретов.
- Перед конкретной задачей запускай `scripts/task-router.py --task "<что делаем>" --write` и следуй `seo/setup/latest-task-route.md`; не поднимай полный цикл/сырьё в контекст, если route ограничивает фазы и источники.
- Перед расходом токенов/paid API/credits/ads запускай `scripts/usage-ledger.py check --service <tool> ... --fail-on-block`; после расхода фиксируй `scripts/usage-ledger.py record --service <tool> ...`. Без ledger-записи нельзя считать лимиты управляемыми.
- Перед подключением новых API/кабинетов/тегов/ads или переносом проекта в новый регион запускай `scripts/tool-stack-recommender.py --write`: он разделяет бесплатные read-only источники, approval-only paid/quota/LLM/index-submission и forbidden/disabled tracking для РФ. `--apply` только после review, без секретов.
- Перед широким циклом или маркетинг-задачей запускай `scripts/growth-roadmap.py --write` и начинай с `seo/setup/growth-roadmap.md`: он ограничивает работу top-N действиями и привязывает технику, контент, local/ecommerce, AI visibility, CRO и автоматизации к approval gates.
- Перед созданием schedule-артефактов запускай `scripts/automation-recommender.py --write`: он предлагает безопасные planned automations; `--apply` только после review generated policy. Не включай `create_schedules` без явного `--allow-schedules`.
- Для запланированных автоматизаций используй `scripts/automation-plan.py`: сначала `--write --include-disabled`, затем ручной review `seo/automations/*`; `--install-cron` только если governance и automation-policy разрешают schedules.
- Для детальной настройки нового проекта используй `scripts/project-intake-wizard.py --interactive --write`; для автозаполнения из `seo-cycle.yaml` — `--defaults --write`.
- Для точечной настройки нового проекта используй `scripts/project-profile.py --write`: он выводит recommended engines/sources/marketing/governance по `seo/project-intake.yaml`; `--apply` делает backup и обновляет `seo-cycle.yaml`.
- Оптимизация токенов обязательна: сырьё сохраняй на диск, в контекст загружай только distillates/top-N; не читай raw CSV/JSON целиком, если `governance.token_policy.raw_data_in_context=false`.
- Robots/Content-Signal — отдельная техническая политика: `search=yes, ai-input=yes, ai-train=no` означает "можно показывать в поиске и AI-ответах, нельзя использовать для обучения". Если SEO plugin ломает `robots.txt` PHP warning'ом, сначала отключи/почини источник генерации, затем проверь чистый публичный `robots.txt`.
- Для РФ/российских проектов не добавляй зарубежные analytics/tracking tags или pixels без явного разрешения в policy. GSC, Bing Webmaster, PageSpeed/CrUX, sitemap/robots checks и off-site API audits допустимы, потому что не требуют установки аналитического кода на сайт.
- Никогда не выводи API keys, OAuth tokens, service-account JSON или значения `.env`; используй только имена переменных и пути к файлам.

## Модульная архитектура (фазовые скиллы + state)

`seo-cycle` — **диспетчер**. Фазы постепенно выносятся в самостоятельные шарибельные фазовые скиллы, координируемые через единый файл состояния `seo/cycles/<тема>/_state.json` (контракт `scripts/cycle-state.py`). Это «цепочка передачи»: каждый фазовый скилл читает state на входе, делает своё, обновляет state на выходе, разблокируя следующую фазу.

Вынесено (пилот): **`seo-keywords`** — Phase 2-3 (сбор семантики + кластеризация), самостоятельный скилл.

> **Статус: дробление заморожено на пилоте (решение 2026-05-30).** Монолитный `seo-cycle` со всеми 10 фазами — **основной и полностью рабочий**. Остальные фазы (`seo-entity-map`, `seo-writing`, `seo-publishing`, `seo-monitoring`) **НЕ выносить** без явной потребности (продажа модулей / команда / переиспользование вне цикла / параллелизм). Для не-вынесенных фаз действуй по их описанию ниже в этом файле — это норма, а не временное состояние.

Как диспетчер ведёт цикл:
```bash
python3 scripts/cycle-state.py init --topic "<тема>"   # создать цикл + _state.json
python3 scripts/cycle-state.py next                      # какие фазы разблокированы
# → вызвать соответствующий фазовый скилл (напр. seo-keywords)
python3 scripts/cycle-state.py gate <phase>              # проверить quality-gate
python3 scripts/cycle-state.py show                      # прогресс цикла
```
Перед передачей фазы дальше диспетчер проверяет **quality-gate** (артефакт готов/непуст + фаза-специфичные проверки). Независимые фазы (где `depends_on` уже `done`) можно запускать параллельно. Управление «улучшением» — на данных: `source-attribution.py` + `triggers-eval.py`, **без** авто-переписывания кода.

Для фаз, ещё не вынесенных в отдельные скиллы, действуй по их описанию ниже в этом файле.

## Когда запускать

Триггеры:
- «запусти полный SEO-цикл / SEO-стратегию для X»
- «продвинь раздел / категорию / тему Y с нуля»
- «семантическое ядро + контент-план + публикация»
- «расширь блог под кластер»
- «мониторинг и план итераций»
- «универсальный SEO под мой проект»
- «настрой seo-cycle для нового проекта»

## Когда НЕ запускать

- Одношаговые задачи — напрямую к скиллам:
  - Только Entity Map → `emwoody-semantic-brief` (или универсальный fallback)
  - Только публикация одного готового материала → `emwoody-publish-*` или CMS-специфичный скилл
  - Только аудит → агент `seo-auditor`
  - Только проверка стоп-слов → `scripts/check-stop-words.py`
- Если пользователь даёт уже готовый Entity Map / contentbrief — переходи сразу на нужную фазу.

---

## Архитектура

```
Phase 0  Discovery & Project Setup    (читает seo-cycle.yaml; install wizard если конфига нет)
Phase 1  Site Audit                   (config-driven — какие тулы, какой CMS)
Phase 2  Keyword Research             (multi-source: только enabled-источники из config)
Phase 3  Cluster + Intent Mapping
Phase 4  Entity Map (Шестаков)        (универсальный шаблон, адаптирован под industry)
Phase 5  Content Plan                 (hub-and-spoke, учёт project_type)
Phase 6  Writing                      (tone of voice, stop-words, stock-first, fact-check)
Phase 7  Publishing                   (CMS-aware: WordPress / Shopify / static / ...)
Phase 8  JSON-LD & Schema             (тип схемы по project_type)
Phase 9  Monitoring                   (GSC + Я.Вебмастер + Метрика + GA — по enabled-источникам)
Phase 10 Iteration                    (cycle continues)
```

Каждый запуск создаёт каталог `<cycles_root>/<topic>-<YYYY-Qx>/` с артефактами по фазам.

---

## Phase 0 — Discovery & Project Setup

**Цель:** загрузить конфиг проекта или запустить install wizard.

**Шаги:**
1. Найти `seo-cycle.yaml` в проекте (поиск: `./seo-cycle.yaml` → `./.seo-cycle.yaml` → `./seo/seo-cycle.yaml` → `./.claude/seo-cycle.yaml`).
2. Если **не найден** — запусти `bash ~/.claude/skills/seo-cycle/scripts/init-project.sh` (интерактивный wizard: базовые поля + governance + image workflow + optional detailed intake → готовый yaml + .env.example). Wizard обязан записать `images.*`: featured/inline ratios, WebP width/quality, source_policy, visual_style, captions/alt policy, lazy-loading policy и upload env для `wp-photo-image.py`, а также создать `seo/project-intake.yaml`, `seo/project-intake-report.md`, `seo/setup/setup-control-plane.md`, `seo/setup/latest-task-route.md`, `seo/setup/latest-usage-ledger.md`, `seo/tool-stack.generated.yaml`, `seo/setup/tool-stack-report.md`, `seo/growth-roadmap.generated.yaml`, `seo/setup/growth-roadmap.md` и `seo/automations/automation-recommendations.md`.
3. Если **найден** — провалидировать: `python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py <path>`.
4. Прочитать `context_files` из конфига (обычно `CLAUDE.md`, brand guidelines).
5. Определить **режим цикла** (`mode` в конфиге, default `standard`):
   - `standard` — обычный цикл по всем 10 фазам
   - `migration` — миграция домена/CMS (см. `docs/migration-planner.md`, расширяет Phase 0/1)
   - `programmatic` — массовая генерация страниц по шаблону (Phase 4 заменяется на Phase 4P, см. `templates/programmatic-page.template.md`)
6. Уточнить у пользователя цель текущего цикла (1-3 вопроса):
   - Что продвигаем: категорию / кластер блога / тему / весь сайт?
   - Сроки: разовая кампания или регулярный цикл?
   - Глубина: только семантика, до publish, или до monitoring?
7. Зафиксировать low-token маршрут текущей задачи:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/task-router.py --task "<цель пользователя>" --write
```
Затем читать `seo/setup/latest-task-route.md` и запускать только фазы/источники из маршрута, соблюдая approval gates и context caps.
8. Перед фактическим расходом сделать preflight и после запуска записать расход:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/usage-ledger.py check --service openai --category llm --usd 0.25 --input-tokens 5000 --output-tokens 1000 --fail-on-block
python3 ~/.claude/skills/seo-cycle/scripts/usage-ledger.py record --service openai --category llm --usd 0.25 --input-tokens 5000 --output-tokens 1000 --task "<цель пользователя>" --write
```
9. Сгенерировать и проверить рекомендации автоматизаций:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/tool-stack-recommender.py --write
# после review: python3 ~/.claude/skills/seo-cycle/scripts/tool-stack-recommender.py --apply
python3 ~/.claude/skills/seo-cycle/scripts/growth-roadmap.py --write
python3 ~/.claude/skills/seo-cycle/scripts/automation-recommender.py --write
# после review: python3 ~/.claude/skills/seo-cycle/scripts/automation-recommender.py --apply
```

**Маркетинг-стратегия (если `marketing.enabled` и цель шире SEO):** оценить, нужна ли платная реклама или хватит органики+локалки — `prompts/marketing-strategy.md` + `scripts/roi-calc.py` (воронка/ROI/ДРР по каналам). Реклама — только при дефиците объёма с ROI>0. Каналы дистрибуции и маркетплейсы — `prompts/distribution-channels.md`. Единый план — `prompts/marketing-calendar.md`.

**Выход:** `<cycles_root>/<topic>/00-discovery.md` с зафиксированными целями и snapshot config (+ `marketing-strategy.md` при маркетинг-цели).

---

## Phase 1 — Site Audit

**Цель:** понять текущее состояние сайта по выбранным поисковикам.

**Делегировать:** `delegate.audit` из config (по умолчанию `seo-auditor` агент).

Доп. техн. аудит (если включено): `delegate.technical_audit` (`claude-seo:seo-technical`).

**Что проверять (универсально):**
- Индексация (XML sitemap, robots.txt, canonical)
- Чистота `robots.txt`: без PHP warnings/HTML, без случайных Bricks preview/editor URLs, без плагиновых Content-Signal строк, противоречащих policy
- Шаблонные следы (демо-контент, пустые `href="#"`, lorem ipsum)
- Служебные страницы в индексе (cart, checkout, my-account для ecommerce)
- Скорость / Core Web Vitals
- Существующий контент: какие страницы есть, какие пустые
- Schema markup: что уже стоит

**Project-type-specific:**
- `ecommerce` → проверка карточек товара, категорий, фильтров
- `blog` → структура архивов, тегов, авторов
- `local_business` → LocalBusiness schema, NAP-консистентность
- `saas` → лендинги фич, документация, /pricing

**Локальный аудит (если есть `business_profile.gbp_url`/`yandex_business_url` или офлайн-точка):**
Сравнить с топ-3 конкурентами (`business_profile.competitors`) на **обеих** картах по чек-листу — это быстрые победы локального SEO:
- **Категории/рубрики** — что есть у конкурентов, но не у нас (Google Categories + рубрики Яндекс.Бизнес/2ГИС).
- **Отзывы** — число, оценка, скорость (план догона: `scripts/review-velocity.py`).
- **Публикации** — частота постов конкурентов (GBP Posts + Яндекс.Бизнес Новости).
- **Фото** — количество/типы/качество.
Тактики и промпты — `prompts/local/` (`google-maps.md` + `yandex-maps.md`), оба рантайма через браузер. Для РФ приоритет Яндекс.Карты + 2ГИС.

**Конкурентный анализ + ICE:** свести данные конкурентов (Serpstat/SpyFu/Keys.so/local/GSC) в приоритизированный список быстрых побед — метод `prompts/competitor-analysis.md` (7 шагов) + `scripts/ice-score.py` (Impact×Confidence×Ease). Топ quick-wins → в roadmap (Phase 3/5) и `keyword-queue`.

**Выход:** `01-audit.md` (+ `local/` подкаталог при локальном аудите, `competitor-analysis.md` при конкурентном) со списком проблем по приоритетам (P0/P1/P2 или ICE).

---

## Phase 2 — Keyword Research (Multi-source, config-driven)

**Цель:** собрать полное семантическое ядро под тему **из всех активных источников региона**.

**Шаг 0 — развернуть источники региона (обязательно, один раз):**
```bash
python3 ~/.claude/skills/seo-cycle/scripts/resolve-sources.py
```
Скрипт читает `region_profile` из конфига (`ru`/`eu`/`us`/`global`), мёрджит с локальными `sources.*` override и печатает финальный список активных источников + пропущенных с причиной (напр. «ahrefs недоступно в регионе», «dataforseo через прокси»). Артефакт: `seo/cycles/<date>/active-sources.json`. **Запускай только источники из этого списка** — это и экономит токены, и не даёт дёрнуть инструмент, недоступный в регионе. Если в конфиге нет `region_profile` (legacy) — скрипт отдаёт `sources.*.enabled` как есть.

**Экономия токенов (обязательные правила Phase 2):**
- **Кэш:** дорогой сбор (Wordstat/NW/LLM-CLI/suggest/ATP) не перезапускай, если свежий результат (< `research_cache_ttl_days`, дефолт 14) уже лежит в `seo/research/.../results/`. `llm-cli-collect.sh` проверяет это автоматически через `research-cache.py`.
- **Сырьё — на диск, дистиллят — в контекст.** В свой контекст подтягивай **только** сведённый `*-merged-*.md` (и итоговый `02-keywords.md`), а НЕ исходные `*-antigravity-*.md` / `*-codex-*.md` / сырые CSV. Скрипты сами пишут сырьё на диск и возвращают сжатый top-N.
- **Antigravity + Perplexity обязательны для семантики и сущностей.** При сборе ядра и Entity Map всегда используй Antigravity CLI (`agy`) и Perplexity Pro/Deep Research как отдельные источники идей, интентов, вопросов, сущностей и проверяемых фактов. Если источник недоступен технически, запиши это в артефакт как blocker/exception; не выдавай сбор за полный.

### Универсальные источники

#### Group A — Search engines (Яндекс)
*(Только если `yandex` в `engines`)*

| Источник | Тип | Когда |
|---|---|---|
| Wordstat (core) | агент | Всегда — `delegate.yandex_specialist` |
| Wordstat правая колонка + сезонность | browser_mcp | Для сезонных тем |
| Yandex Suggest | script | Long-tail без частот, `scripts/yandex-suggest.py` |
| Yandex SERP blocks | browser_mcp | Related, PAA, Колдунщик |
| Я.Вебмастер «История запросов» | browser_mcp | Реальные данные по сайту (после верификации) |
| Yandex.Картинки suggest | browser_mcp | Image-SEO |
| Я.Бизнес/Карты «запросы для перехода» | dashboard | Локальный бизнес |
| Яндекс.Кью | browser_mcp | PAA-аналог для info-тем |

#### Group B — Search engines (Google)
*(Только если `google` в `engines`)*

| Источник | Тип | Когда |
|---|---|---|
| Google Search Console | API | После 30 дней с публикации |
| Google Trends | script | Сезонность |
| Google Suggest | script | Long-tail |
| DataForSEO | paid API | Опционально |
| **Serpstat** | API | Volume/KD/CPC + конкуренты. **Работает с РФ/СНГ** (`g_ru`) — замена Ahrefs/SEMrush там, где они заблокированы. `scripts/serpstat-fetch.py` |
| **SpyFu** | API | Competitor/PPC/SEO домен-аналитика. **Только US/UK/EU — НЕ РФ.** Профили us/eu/global. `scripts/spyfu-fetch.py` |

> **Serpstat — беречь кредиты** (план Appsumo: 1000/мес, 1 req/sec): точечно — KD/volume по главным ключам кластера (`keywords-info`) и competitor gap по hub-категориям (`competitors`, `domain-keywords`). Массовый long-tail — через Wordstat/suggest/LLM-CLI, не через Serpstat. Скрипт сам проверяет остаток (getStats, бесплатно) и кэширует на 30 дней. `stats` — посмотреть остаток в любой момент.

> **SpyFu — беречь бюджет** (Pro: $40 кредита/мес, pay-as-you-go по строкам): дешёвые эндпоинты `domain-stats` (latest, 1 строка) и competitors ($0.20–0.50 CPM); дорогие top-pages ($5 CPM) — избегать. Локальный usage-трекер блокирует при достижении `--budget`. `usage` — сколько потрачено за месяц. Применять для анализа западных конкурентов; для РФ-проектов бесполезен (RU не покрывается).

#### Group C — SERP analysis
| Источник | Тип | Когда |
|---|---|---|
| NeuronWriter | API | SERP terms (если `sources.neuronwriter.enabled`) |

#### Group D — LLM CLI (универсально)
| Источник | Тип | Когда |
|---|---|---|
| **Antigravity** (`agy`) | CLI | Обязательно для семантики, интентов, сущностей и альтернативных формулировок |
| **Codex** (`codex exec`) | CLI | С URL для fact-check, web search |
| **Параллельный запуск + merge** | script | `scripts/llm-cli-collect.sh "<тема>"` |

#### Group E — Public APIs
| Источник | Тип | Когда |
|---|---|---|
| AnswerThePublic | API | Универсальные шаблоны вопросов (для не-RU рынков работает напрямую; для RU — переводим en/us шаблоны) |
| Perplexity Pro | browser_mcp | Обязательно для сущностей с источниками, Deep Research и фактчекинга |

### Сведение в единое ядро

После сбора — слить в `02-keywords.md`:

```markdown
| Ключ | Wordstat | GSC impressions | NW priority | Intent | Cluster | Source |
|---|---|---|---|---|---|---|
| ... |
```

**Делегировать:** `delegate.keyword_research` (по умолчанию `seo-keyword-researcher`).

**Веди лог источников:** добавляй ключи в `seo/source-attribution.csv` (`keyword,source,date_added,cluster,target_url`) с пометкой источника. Через 30-60 дней это даст замер эффективности источников в Phase 10 (`source-attribution.py`) — какие источники реально приносят топ, а какие отключить ради экономии.

**Выход:** `02-keywords.md` + raw-экспорты в подкаталогах `02a-...` / `02b-...`.

---

## Phase 3 — Cluster + Intent Mapping

**Цель:** сгруппировать ключи в кластеры под отдельные страницы.

**Делегировать:** `delegate.cluster_analysis` (по умолчанию `claude-seo:seo-cluster`) + `delegate.keyword_research`.

**Intent типы (универсально):**
- Commercial — «купить X», «X цена», «X сравнить»
- Informational — «как», «что такое», «почему»
- Navigational — «бренд X», «адрес склада»
- Transactional — «доставка X», «заказать X»

**Hub-and-spoke:**
- **Hub** — главная страница темы (для ecommerce: категория; для blog: pillar-статья; для SaaS: фич-лендинг)
- **Spokes** — info-страницы под long-tail (статьи блога, FAQ-страницы)

**Выход:** `03-clusters.md` — таблица: cluster / intent / тип страницы / целевой URL.

---

## Phase 4 — Entity Map (методика Шестакова)

**Цель:** для каждой страницы из кластера — Entity Map (entities → relations → intents → structure → keys).

**Делегировать:** `delegate.semantic_brief` (`emwoody-semantic-brief` если есть, иначе универсальный шаблон `templates/entity-map.template.md`).

**Обязательные evidence-источники:** перед фиксацией Entity Map сверяй сущности, интенты, PAA/FAQ и спорные утверждения через Antigravity CLI и Perplexity Deep Research. Сохраняй raw-ответы на диск, а в Entity Map добавляй только дистиллированные сущности с указанием источника. Без этой сверки карта не проходит quality-gate, кроме явно залогированного технического исключения.

**Универсальная структура (17 разделов):**
1. Центральная сущность (AEO-цитата 2-3 предложения)
2. Атрибуты (таблица)
3. Связанные сущности (15-20)
4. Тройки отношений (≥12)
5. Явные интенты
6. Скрытые интенты (≥5 страхов/сомнений)
7. PAA вопросы (≥15)
8. Конкуренты (топ-10 SERP)
9. Граф сущностей (визуализация)
10. SERP-фичи (Featured Snippet, Колдунщик, AEO)
11. Структура страницы
12. FAQ (явные + скрытые)
13. Внутренние ссылки
14. Meta-теги (title/description)
15. JSON-LD plan
16. Чек-лист готовности
17. NW evaluate plan

**Frontmatter обязательно (extends по проектам):**
```yaml
target_url:
created:
status: pilot | active | archived
neuronwriter_query_id:
stock_skus: []                  # для ecommerce
fact_check_log: []              # если content_rules.fact_check.enabled
last_fact_check:
```

**Выход:** `04-entity-maps/<slug>.entity-map.md` для каждой страницы.

---

## Phase 5 — Content Plan

**Цель:** roadmap публикаций с приоритетами.

**Делегировать:** `delegate.content_strategy` (по умолчанию `seo-content-strategist`).

**Структура плана:**
- Что: тип страницы (hub/spoke), URL, главный ключ
- Когда: дата, статус (TODO/Drafting/QA/Published)
- Зависимости: какие entity-maps готовы, какие источники собраны
- KPI: целевые impressions / clicks через 90 дней
- Bandwidth: блог N статей/неделю, категории M/месяц

**Выход:** `05-content-plan.md`.

---

## Phase 6 — Writing

**Цель:** написать тексты под Entity Map'ы.

**Делегировать:** `delegate.content_writer` (по умолчанию `seo-content-writer`).

**Универсальные правила (config-driven):**
- Tone of voice — из `tone.*` config
- Stop-words check — если `quality_gates.stop_words_check.enabled`
- AEO абзац в первые 400 символов — если `content_rules.aeo.enabled`
- Stock-first — если `content_rules.stock_first.enabled`
- Brand name discipline (user-facing vs technical) — `project.brand_name_*`
- Локальные сигналы ≥ `content_rules.local_signals.min_per_page`

**QA после написания (обязательная последовательность):**
1. **Stop-words check** (`scripts/check-stop-words.py`)
2. **Fact-check** — обязательно через Perplexity prompts (режим **Deep Research**) + Antigravity CLI cross-check для фактов, сущностей, интентов и спорных формулировок. Результаты записывай в `fact_check_log` frontmatter (claim/source/url/verdict/checked/tool). Если один из инструментов недоступен, не публикуй без записи blocker/exception в лог.
3. **Image visual + alt/caption check** — изображения создаются config-driven из `images.*`. Для фото-подготовки используй `scripts/wp-photo-image.py`: локальное фото/URL → crop по `images.aspect_ratios.*` → WebP по `images.output.*` → WordPress upload через SSH/WP-CLI при необходимости. Inline images должны быть чистыми тематическими фото/визуалами в `images.visual_style`. Не добавляй видимый текст на изображение, если `images.allow_visible_text=false` (SEO/AEO/GEO, схемы, подписи, описания товаров, дисклеймеры каталога) и не используй товарные карточки/коллажи как основной визуал, если пользователь явно не попросил. У каждого недекоративного изображения должен быть естественный `alt`; inline caption обязателен, если `images.captions.inline_required=true`: featured, inline, OG/schema, product/category visuals. Alt и caption описывают изображение и сущность, без переспама ключами и без служебных объяснений. Изображение без alt или inline image без обязательного caption = публикационный blocker.
4. **Stock-first проверка** (если ecommerce)
5. **NW evaluate** (если `sources.neuronwriter.enabled`) — target `quality_gates.neuronwriter_score.min_score`

**E-E-A-T trust-блок (если есть `fact_check_log`):** сгенерируй видимый блок «Источники» в конец статьи —
```bash
python3 ~/.claude/skills/seo-cycle/scripts/eeat-render.py 06-drafts/<name>.publish.md
```
Рендерятся только источники с verdict достоверно/частично; спорные — править формулировку в тексте, а не «подтверждать». Это прямой Trust-сигнал.

Публикация только после прохождения всех гейтов.

**Выход:** `06-drafts/` — `*.publish.md`.

---

## Phase 7 — Publishing (CMS-aware)

**Цель:** залить контент на сайт.

Делегирование зависит от `publishing.cms` и `publishing.publish_skills`:

| CMS | Скилл / подход |
|---|---|
| WordPress | REST API + Application Password как основной независимый канал; MCP/`emwoody-publish-*` как удобный интерфейс; SSH/WP-CLI fallback для backup/cache/meta/server repairs |
| Shopify | (TBD — Liquid + Storefront API) |
| Webflow | (TBD — CMS Collections API) |
| Next.js/static | git commit в content/ + redeploy |
| custom | по обстоятельствам |

**Универсальный шаги:**
1. Парсинг `publish.md`
2. Backup текущих значений
3. POST в CMS endpoint
4. Featured image / OG картинка (если `images.generator != none` или `images.workflow=photo_first`) через `scripts/wp-photo-image.py`/CMS media workflow + обязательный alt; inline images по `images.inline_min_per_post` и `images.aspect_ratios.article_inline` + обязательный короткий caption, если включён в `images.captions`
5. Schema/meta через SEO plugin endpoint
6. Verify через GET + браузер: публичный HTML не должен содержать недекоративные `<img>` без `alt`, inline images без caption и запрещённые тексты на/под изображениями. Если кеш/оптимизатор/lazy-load подменяет first-screen/above-the-fold inline image на плейсхолдер в браузере, исключи только это критичное inline image из lazy-load (`skip-lazy`/`data-no-lazy` или CMS-аналог) и перепроверь screenshot. Остальные inline images ниже первого экрана оставляй lazy-loaded.
7. Лог в `artifacts.publish_log`

**WordPress channel policy:** не завязывай публикацию только на MCP-сервер. Если `publishing.cms=wordpress`, держи REST API publisher через Application Password как основной повторяемый путь; MCP используй когда он доступен в клиенте; SSH/WP-CLI оставляй для восстановления, purge cache, backup, незарегистрированных REST meta и серверных исправлений.

**Маркетинговый мостик (если `marketing.enabled`):** после публикации — поднять конверсию страницы через плагин `marketing-skills` (`page-cro` / `form-cro` / `popup-cro`). Каналы привлечения/удержания (`paid-ads`, `social-content`, `email-sequence`, `referral-program`) — **с РФ-адаптацией** (Яндекс.Директ / VK / Telegram / Метрика / 2ГИС вместо западных). Карта мостиков и замен каналов — `docs/marketing-bridges.md`.

**Выход:** `07-published.md` — URL + дата каждой публикации.

---

## Phase 8 — JSON-LD & Schema

**Цель:** структурированные данные под выбранные типы страниц.

**Делегировать:** `delegate.schema_markup` (по умолчанию `claude-seo:seo-schema`).

**Типы по `project_type`:**
- `ecommerce`: Product, Offer, AggregateRating (только реальные!), BreadcrumbList
- `local_business`: LocalBusiness + Service + AggregateRating
- `blog`: Article, FAQPage, HowTo, BreadcrumbList
- `saas`: SoftwareApplication, Product, Organization
- Везде: WebSite, Organization, FAQPage (где есть FAQ)

**E-E-A-T: канонический узел организации (обязательно).** Не оставляй `author`/`publisher` голым `{"@type":"Organization","name":...}`. Собери единый узел из `business_profile` и ссылайся на него через `@id`:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/schema-org-build.py build              # посмотреть узел
python3 ~/.claude/skills/seo-cycle/scripts/schema-org-build.py inject schema/*.json  # вставить + переписать author/publisher на @id
```
Узел несёт trust-сигналы (address, telephone, openingHours, areaServed, knowsAbout, sameAs) — это то, что связывает контент с реальным бизнесом и усиливает Authoritativeness/Trust. Инжект идемпотентен. Требует секцию `business_profile` в конфиге.

**Запрет:** фейковые рейтинги и отзывы. Если нет реальных — не делай AggregateRating. `same_as` — только подтверждённые профили.

**Выход:** `08-schema.md`.

---

## Phase 9 — Monitoring

**Цель:** регулярные снапшоты позиций / трафика / поведения.

**Делегировать:**
- `delegate.google_data` (`claude-seo:seo-google`) — GSC + GA4 + CrUX (если включено)
- `delegate.yandex_specialist` — Я.Вебмастер + Метрика (если включено)

**Cadence:** 2-недельные снапшоты в `09-monitoring/YYYY-MM-DD-snapshot.json` + markdown-надстройка `*.md` по `templates/monitoring-report.template.md`.

**Локальный мониторинг (если локальный бизнес):** раз в месяц снимать прогресс vs конкуренты на обеих картах — скорость отзывов (`review-velocity.py`), новые категории/рубрики, частота постов, прирост фото. Промпты — `prompts/local/`. Отставание → задача в Phase 10.

**Потерянные ключи:** сравнить текущий снапшот с прошлым — `scripts/lost-keywords.py --old <prev> --new <cur>` (выпавшие/просевшие ключи → refresh + перелинковка).

**AI-visibility (GEO):** свод присутствия в Яндекс Нейро / Google AI Overviews / ChatGPT / Perplexity — промпт `prompts/ai-visibility.md` (+ плагины `seo-geo`/`seo-seranking`).

**Медианный бенчмарк по конкурентам:** `scripts/competitor-benchmark.py` — где мы ниже медианы топ-N (ключи/бэклинки/отзывы/посты/фото) → приоритеты в roadmap (ICE).

**Реклама + соцсети:** разведка платной выдачи и соцактивности конкурентов + генерация объявлений/постов (Директ/VK/TG/Дзен) — промпт `prompts/ad-and-social.md`.

**Pipeline (observability hub):**

```
delegate(claude-seo:seo-google) → GSC/GA4 JSON ┐
delegate(yandex-seo-specialist) → Webmaster/   ├→ snapshot-build.py --source X
  Metrika данные                               │   (нормализация в единую schema)
psi-fetch.py URL → PSI JSON                    ┘                  ↓
                                                    09-monitoring/YYYY-MM-DD-snapshot.json
```

**Единая schema `snapshot.json`:** см. `scripts/snapshot-build.py --help`. Поля: `queries[]`, `pages[]`, `cwv{}`, `behavior{}`, `sources[]`. Скрипт умеет мердж нескольких источников в один snapshot через `--merge`.

**Что собирать:**
- Топ-100 запросов: impressions, clicks, CTR, position, дельты
- Топ-страниц: то же + behavior (bounce, time, conversions)
- CWV per URL (PSI) с статусом good/needs_improvement/poor
- Изменения vs прошлый снапшот
- Сезонные сравнения (если есть данные за прошлый период)

**Выход:** `09-monitoring/YYYY-MM-DD-snapshot.json` + `*.md` отчёт по шаблону.

---

## Phase 10 — Iteration (actionable feedback engine)

**Цель:** действовать по данным через декларативные правила.

### Pipeline

```
09-monitoring/YYYY-MM-DD-snapshot.json ┐
config/triggers.yaml                   ├→ triggers-eval.py → 10-iterations.md
(+ опц. project-override triggers)     ┘    (markdown action list по P0/P1/P2
                                             с конкретными URL и запросами)
```

### Команда

```bash
python3 ~/.claude/skills/seo-cycle/scripts/triggers-eval.py \
    09-monitoring/YYYY-MM-DD-snapshot.json \
    ~/.claude/skills/seo-cycle/config/triggers.yaml \
    --output 10-iterations.md \
    --project-yaml ./seo-cycle.yaml   # для project-override правил
```

### Правила в `config/triggers.yaml`

Декларативные `when → action → priority → delegate`. Текущий набор покрывает:

- **Запросы:** low_ctr_in_top_positions, striking_distance, position_drop, high_impressions_no_clicks, new_emerging_query
- **Страницы:** high_bounce_low_engagement, low_engagement_time, high_traffic_no_conversions, orphan_page_low_clicks
- **CWV:** cwv_poor, cwv_needs_improvement, lcp_critical
- **Поведение:** bounce_spike_site_wide
- **Контент-гигиена:** fact_check_stale, page_unchanged_long
- **Бэклинки:** lost_top_backlink, gained_top_backlink

Расширить можно копированием правил в `<project>/seo-triggers.yaml` и указанием `monitoring.triggers_file` в проектном `seo-cycle.yaml`.

### Source attribution (обратная связь по источникам семантики)

Замыкает петлю «откуда брали ключи → что сработало». Раз в квартал (когда накопились данные ≥30-60 дней) сопоставь лог источников со snapshot:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/source-attribution.py \
    --csv seo/source-attribution.csv \
    --snapshot 09-monitoring/<date>-snapshot.json
```
Скрипт покажет, какие источники дают ключи в топ-10, а какие — пустую породу, и пометит кандидатов на снижение приоритета/отключение. Малоэффективный источник → убери из `region_profile` override или `sources_disable`. **Это прямая экономия токенов/времени на следующих циклах.**

> Предусловие: в Phase 2 веди `seo/source-attribution.csv` — помечай, из какого источника пришёл каждый ключ (`keyword,source,date_added,cluster,target_url`).

**Выход:** `10-iterations.md` — приоритизированный action list со ссылками на конкретные URL/запросы + рекомендуемыми делегатами для каждого пункта.

---

## Установка под новый проект

Полная инструкция в `INSTALL.md` рядом с этим файлом. Кратко:

1. Скопировать `~/.claude/skills/seo-cycle/config/project.template.yaml` в корень проекта как `seo-cycle.yaml`.
2. Заполнить под свой сайт (язык, регион, поисковики, CMS, источники).
3. Запустить валидатор: `python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py`.
4. Подключить API-ключи в `.env` проекта по списку, который выдаст валидатор.
5. (Опционально) Создать проектные скиллы для специфичных задач (custom publishing, brand-specific entity map) и прописать в `delegate.*`.
6. Запустить: «давай запустим SEO-цикл для категории X».

## Кастомизация под нишу

Адаптация под конкретный проект через:

- **`seo-cycle.yaml`** — основной механизм (язык, поисковики, project_type, источники, tone, content_rules)
- **`content_rules.fact_check`** — отключи для не-технических ниш
- **`content_rules.stock_first`** — только для ecommerce с инвентарём
- **`content_rules.local_signals`** — отключи для глобального B2B SaaS
- **`tone.stop_words_extra`** — добавляй свои запреты
- **Custom prompts** — клонируй `~/.claude/skills/seo-cycle/prompts/*` в `<project>/seo/prompts/` и переопредели
- **Custom delegate** — создавай проектные субскиллы и прописывай в `delegate.*`

См. `docs/adapt.md` для подробной инструкции по адаптации.

## Источники истины (универсальные)

1. `seo-cycle.yaml` — конфиг проекта
2. `<project>/CLAUDE.md` — правила проекта (если есть)
3. `<project>/seo/entities/entities.yaml` — реестр сущностей проекта
4. `~/.claude/skills/seo-cycle/prompts/` — универсальные промпт-шаблоны
5. `<artifacts.research_root>` — результаты исследований (ATP, Perplexity, LLM CLI)

## Lessons learned (пополняется)

- *Заполняется по ходу реальных запусков на разных проектах.*
- Первый запуск на новом проекте — пройти Phase 0 (wizard) и Phase 1 (audit) полностью, прежде чем приступать к контенту.
- Не включай все источники сразу. Включай постепенно — после подключения каждого API/доступа.
- LLM CLI (Antigravity + Codex) **не заменяют** Wordstat/GSC — они дополняют их идеями и URL-ями для fact-check.

## Версионирование

См. `CHANGELOG.md` рядом с этим файлом.
