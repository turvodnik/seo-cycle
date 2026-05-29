# Changelog — seo-cycle

## [1.5.0] — 2026-05-29

### Полная двуязычная документация + AI-автоустановка

- **`GUIDE.md`** — подробное руководство **RU (сверху) + EN (полный перевод ниже)**: что это, преимущества, установка для человека и **для ИИ-агента (самостоятельный машинный сценарий)**, архитектура, оба рантайма, **все ~36 инструментов** (что делает / команда / какой результат), 10 фаз по шагам, агенты/делегаты, команды-шпаргалка, типовые сценарии.
- **Правило обновления документации** закреплено в `GUIDE.md`, `SKILL.md` и памяти: при любом изменении — обновить GUIDE (обе версии) + CHANGELOG + VERSION в том же коммите.
- README: ссылка на GUIDE как главную документацию.

## [1.4.0] — 2026-05-29

### Codex как основной мозг (гибридный двойной рантайм)

Полная адаптация под сценарий, когда оркестратор — Codex CLI, а не Claude. Принцип гибрида: наши скрипты для уникального (РФ-источники, Serpstat/SpyFu, кэш, guard'ы, публикация); нативные Codex-skills для изображений/браузера/делегирования; **без `codex exec` самовызовов**.

- **RUNTIME-режим:** `runtime: auto|claude|codex` в конфиге + env `SEO_RUNTIME`. Авто-детект Codex по env-признакам.
- **`llm-cli-collect.sh`** — RUNTIME-aware: в codex-режиме запускает только `agy`, печатает промпт для нативного сбора Codex (web_search), без вложенного `codex exec`.
- **`img-generate.sh`** — перенесён в скилл, RUNTIME-aware: claude → `codex exec` обёртка; codex → вывод `CODEX_NATIVE_IMAGE` для нативного `seo-image-gen`/`image`/`sora`. emwoody-версия стала тонким враппером.
- **`docs/codex-runtime.md`** — полный маппинг Claude↔Codex (изображения, браузер, делегирование, сбор, фазы) + детект режима.
- Заполнен `~/.codex/skills/codex-primary-runtime/SKILL.md` — точка входа для Codex-сессии.
- `runtime` добавлен в `project.template.yaml`; секция RUNTIME в `SKILL.md`.

## [1.3.0] — 2026-05-29

### Слой данных + уведомления (Этап 1 автоматизации — без n8n/Next.js)

После разбора «n8n vs Next.js vs CLI»: вместо тяжёлой инфры — тонкий слой к существующему ядру.
- **`scripts/db-sync.py`** — собирает CSV/JSON-артефакты (keyword-queue, source-attribution, publish-log, monitoring snapshots, api usage) в единую `seo/seo.db` (SQLite). Фундамент под дашборды (Obsidian/Metabase/Next.js) и алерты. Устойчив к отсутствию файлов, идемпотентен.
- **`scripts/notify.py`** — Telegram-уведомления одним скриптом (без n8n). Graceful no-op без токена (pipeline не ломается). `--test`, уровни info/warn/alert.
- Интеграция: `approval-gate.py` шлёт алерт при создании тикета; `monthly-runner.sh all` — при сбое проекта.
- Секции `data_store` + `notifications` в `project.template.yaml`, `.env.example` (TELEGRAM_*). `seo/seo.db` в .gitignore.

### SpyFu (новый источник Phase 2 — competitor/PPC для US/UK/EU)

- **`scripts/spyfu-fetch.py`** — клиент SpyFu API (Basic auth из `API_SpyFu_ID:API_SpyFu_secret_key`). Подкоманды: `usage`, `domain-stats` (latest/all), `raw`. ⚠ Покрывает только западные рынки (countryCode US/GB/DE/...), **RU отвергается** — поэтому в профилях us/eu/global, в ru → `sources_disable` с причиной.
- Защита $-бюджета (Pro $40/мес, pay-as-you-go): локальный usage-трекер с месячным сбросом + CPM-таблица по эндпоинтам, блок при достижении `--budget`. Кэш 30 дней, дистиллят → stdout.
- Добавлен в `region-profiles` (us/eu/global), `project.template.yaml`, `.env.example`, Phase 2 SKILL.

### Serpstat (новый источник Phase 2 — volume/KD/конкуренты для РФ/СНГ)

- **`scripts/serpstat-fetch.py`** — клиент Serpstat API v4 (JSON-RPC). Подкоманды: `stats` (бесплатно), `keywords-info`, `related`, `suggestions`, `domain-keywords`, `competitors`. Работает с `g_ru` — закрывает дыру Ahrefs/SEMrush в РФ.
- Защита кредитов (план Appsumo 1000/мес, 1 req/sec): pre-flight через getStats + `--min-credits` guard, `--size` лимит строк, кэш на диск (`--ttl 30`), rate-limit 1.1с/запрос. Сырьё → диск, дистиллят (md-таблица) → stdout.
- Добавлен в `region-profiles` (ru/eu/us/global), `project.template.yaml`, `.env.example` (`SERPSTAT_API_KEY`), Phase 2 SKILL.

### Региональные профили источников (универсальность по странам)

- **`config/region-profiles/{ru,eu,us,global}.yaml`** — пресет источников на регион. Проект задаёт одной строкой `region_profile: ru`. ru = Яндекс-приоритет + Google-инструменты доступные из РФ, Ahrefs/SEMrush выключены, DataForSEO через прокси. eu/us = Google-моно + полный западный SaaS, Яндекс off, ATP без перевода.
- **`scripts/resolve-sources.py`** — разворачивает профиль + локальные override → список активных/пропущенных источников с причиной + `seo/cycles/<date>/active-sources.json`. Legacy-режим для конфигов без `region_profile`.
- `validate-config.py` научен резолвить активность источников через профиль.

### Экономия токенов

- **`scripts/research-cache.py`** — TTL-кэш (`research_cache_ttl_days`, дефолт 14): дорогой сбор не перезапускается, если свежий результат на диске. Подключён в `llm-cli-collect.sh`.
- LLM-CLI **deep-режим**: Codex `model_reasoning_effort=xhigh` + `web_search=live` явно; Antigravity + Perplexity — через deep-преамбулы промптов.
- Правило в SKILL: «сырьё на диск, в контекст — только `*-merged-*.md` / дистилляты».

### E-E-A-T

- **`scripts/schema-org-build.py`** — канонический Organization/LocalBusiness узел из `business_profile` конфига (@id, trust-сигналы: address/telephone/openingHours/areaServed/knowsAbout/sameAs); `inject` переписывает author/publisher всех Article/Product на @id-референс (идемпотентно).
- **`scripts/eeat-render.py`** — из `fact_check_log` frontmatter рендерит видимый trust-блок «Источники» (только verdict достоверно/частично).
- **`scripts/source-attribution.py`** — замыкает петлю: какой источник семантики дал ключи в топ (джойн `source-attribution.csv` × snapshot) → рекомендации, какие источники отключить.
- `business_profile` + `region_profile` + `research_cache_ttl_days` добавлены в `project.template.yaml`.

### Масштабирование на N проектов

- **`config/projects-registry.yaml`** — реестр всех проектов (path/region_profile/cms/status/monthly_automation).
- `init-project.sh` — выбирает `region_profile` по стране и дозаписывает проект в реестр.
- `monthly-runner.sh all [subcmd]` — итерация по активным проектам реестра.

## [1.2.0] — 2026-05-28

### Step 10 — Monthly Automation (MVP + Full)

**4-system automated monthly workflow** заменяющий команду из 4 SEO-специалистов:
- System 1 — Keyword Research (replenish queue)
- System 2 — Weekly Publisher (Mon 9am, 4 posts/mo)
- System 3 — Monthly Site Audit (Week 2)
- System 4 — Refresh + Deindex Rescue (Week 3-4)

**Новые скрипты (5):**
- `scripts/keyword-queue.py` — FIFO очередь ключей (add/pop/approve/publish/status)
- `scripts/approval-gate.py` — file-based approval tickets (5 типов)
- `scripts/monthly-runner.sh` — auto-detect day/week → запуск операции; парсит расписание из yaml
- `scripts/deindex-detect.py` — sitemap vs GSC diff + HTTP classification (deindex/4xx/5xx/noindex/redirect)
- `scripts/monthly-dashboard.py` — auto-generated status dashboard в markdown

**Новые subagents (6 экспертов в `~/.claude/agents/`):**
- `seo-monthly-orchestrator` — top-level координатор расписания и approval gates
- `seo-keyword-queue-manager` — System 1 expert (replenish + Phase 2 research)
- `seo-weekly-publisher` — System 2 expert (pop → entity-map → write → QA → approval → publish)
- `seo-monthly-auditor` — System 3 expert (P0+P1 filter, approval перед фиксами)
- `seo-refresh-rescuer` — System 4 expert (refresh + полный deindex workflow)
- `seo-approval-gate` — helper для всех 5 approval точек

Все subagents в стандарте Anthropic Agent Skills (YAML frontmatter + markdown) — **работают в Claude Code и Codex CLI без модификаций**.

**Новые templates (1):**
- `templates/keyword-queue.template.csv` — стартовый шаблон очереди

**Новые prompts (1):**
- `prompts/page-rewrite-rescue.md` — diagnose + rewrite plan для деиндексированных страниц

**Новая документация (1):**
- `docs/automated-monthly.md` — полный workflow doc (setup cron, approval flow, troubleshooting, cross-platform notes для Codex)

**Обновления existing:**
- `config/project.template.yaml` — секция 21 `monthly_automation` (cron schedule, queue file, approval gates, refresh triggers, deindex)
- `scripts/monthly-runner.sh` — schedule parser из yaml (опц. override defaults)
- `agents/seo-refresh-rescuer.md` — полная реализация DEINDEX RESCUE workflow (вместо placeholder из MVP)

**Регрессия:**
- ✅ emwoody pilot активирован: `monthly_automation.enabled: true`, 5 approved keywords в очереди (minvata×2, shumoizolyacziya, plitochnyy-kley, xps)
- ✅ Все 26 скриптов имеют `--help`
- ✅ End-to-end: deindex-detect на dummy data → diff корректен (2 lost из 5 sitemap)
- ✅ Dashboard для emwoody генерится: TL;DR + queue + approvals + snapshot status

**Personal time (target ~2-3h/month):**
- Approve keyword research: 5 min × 1/mo
- Approve каждый пост: 2 min × 4/mo = 8 min
- Audit review + fixes: 30 min × 1/mo
- Refresh plan review: 10 min × 1/mo
- Deindex rewrite approve: 5 min × variable
- **Total: ~1.5-2 часа в месяц**

**Заменяет:**
- Content Strategist ($3-5k/mo)
- Content Writer ($2-4k/mo)
- Technical SEO ($2-3k/mo)
- Content Editor ($1.5-3k/mo)
- **Total команды: $8.5-15k/mo → Total системы: <$50/mo**

### Roadmap → v1.3

- [ ] `scripts/notification.py` — email на P0 audit findings (опц.)
- [ ] Schedule parser в monthly-runner.sh — полный (сейчас MVP: content + audit)
- [ ] WooCommerce auto-sync для stock-inventory.yaml
- [ ] Shopify / Webflow publish handlers (универсальные)
- [ ] Готовые Schema.org JSON-LD скелеты по project_type
- [ ] DataForSEO fallback для Wordstat
- [ ] Stop-words для DE/TR/PL/EN-более-расширенный

## [1.1.0] — 2026-05-27

### Production-ready upgrade: observability hub + actionable feedback engine

**Архитектурное:**

- Phase 9 переработана как **master observability hub** с единой schema snapshot.json
- Phase 10 = **actionable feedback engine** на декларативных правилах (`config/triggers.yaml`)
- Введён `mode: standard | migration | programmatic` для разных типов циклов
- Новые опц. секции конфига (back-compat): `monitoring`, `eeat`, `migration`, `backlinks`

**Новые скрипты (P0/P1/P2 = 12 шт):**

- `google-trends.py` — pytrends wrapper для сезонности
- `init-project.sh` — интерактивный wizard (7 вопросов → готовый yaml)
- `snapshot-build.py` — нормализатор аналитики в единую schema (5 источников: gsc/ga4/metrika/webmaster/psi)
- `triggers-eval.py` — оценщик правил Phase 10 → markdown action list
- `nw-cli.sh` — universal NeuronWriter wrapper
- `validate-entities.py` — universal entity registry checker
- `psi-fetch.py` — PageSpeed Insights API client (free, без OAuth)
- `gsc-fetch.py` — Search Console API client (service account)
- `ga4-fetch.py` — GA4 Data API client
- `metrika-fetch.py` — Я.Метрика API client (OAuth)
- `webmaster-fetch.py` — Я.Вебмастер API client (OAuth)
- `programmatic-template-gen.py` — data-driven генератор страниц
- `schema-validate.py` — JSON-LD валидатор

**Новые шаблоны:**

- `templates/monitoring-report.template.md` — snapshot отчёт
- `templates/cycle-plan.template.md` — content plan
- `templates/programmatic-page.template.md` — для PSEO
- `templates/hreflang-matrix.template.md` — мультирегион
- `templates/stock-inventory.template.yaml` — перенесён из scripts/, расширен примерами WooCommerce/Shopify

**Новый config:**

- `config/triggers.yaml` — 18 декларативных правил Phase 10

**Новая документация (9 docs):**

- `docs/oauth-setup.md` — единый OAuth setup (GCP + Яндекс), таблица всех env vars
- `docs/troubleshooting.md` — FAQ по типичным ошибкам
- `docs/migration-planner.md` — domain/CMS миграция
- `docs/eeat-audit.md` — E-E-A-T cross-cutting checklist
- `docs/backlink-research.md` — backlink workflow
- `docs/sxo-quality-gates.md` — SXO quality gates
- `docs/international-seo.md` — hreflang strategy
- `docs/image-seo.md` — image SEO checklist
- `docs/video-seo.md` — video SEO + VideoObject schema
- `docs/versioning-migration.md` — upgrade guide для v1.0 → v1.1

**Новые промпты:**

- `prompts/competitor-pages-analysis.md` — глубокий SERP-анализ топ-10

**Новые конфиг-файлы:**

- `.env.example` — шаблон env vars

**Обновления existing:**

- `SKILL.md` — Phase 0 (mode), Phase 9 (snapshot pipeline + единая schema), Phase 10 (triggers engine + декларативные правила)
- `INSTALL.md` — TL;DR Вариант A: интерактивный wizard
- `config/project.template.yaml` — schema v1.1, новые секции 17-20
- `scripts/validate-config.py` — поддержка v1.1 расширений + OAuth env vars check

**Регрессия:**

- ✅ Existing `emwoody/seo-cycle.yaml` валидируется без новых ошибок
- ✅ End-to-end pipeline: API → snapshot → triggers → markdown action list
- ✅ Все 7 P0 + 5 P1 fetcher скриптов имеют `--help`
- ✅ programmatic-template-gen + schema-validate тестируется на dummy данных

### Известные ограничения

- AnswerThePublic не поддерживает регион Россия — используем en/us для шаблонов с переводом
- LLM CLI (Antigravity / Codex) могут давать разный результат, нужен merge через `llm-cli-merge.py`
- Perplexity требует ручной установки Claude for Chrome extension — autosetup невозможен
- ATP может создать все провайдеры даже когда указан один — кредитный овершут возможен

### Roadmap → v1.2

- [ ] `scripts/stock-sync-woo.py` — авто-синк stock-inventory.yaml из WooCommerce
- [ ] `scripts/stock-sync-shopify.py` — то же для Shopify
- [ ] `scripts/backlinks-normalize.py` — нормализация backlinks export в snapshot
- [ ] `scripts/hreflang-validate.py` — валидация hreflang кросс-ссылок
- [ ] Shopify / Webflow publish handlers (универсальные)
- [ ] Schema.org templates по project_type (готовые JSON-LD скелеты)
- [ ] DataForSEO интеграция как fallback для Wordstat
- [ ] Поддержка немецкого / турецкого / польского tone of voice в `check-stop-words.py`

## [1.0.0] — 2026-05-26

### Initial release — универсальный SEO-цикл скилл

[см. предыдущую версию CHANGELOG ниже]

**Что внутри:**

- `SKILL.md` — оркестратор 10 фаз
- `INSTALL.md` — wizard для нового проекта
- `config/project.template.yaml` — полная схема конфига
- 4 универсальных промпта, 2 шаблона, 4 doc
- 7 переносимых скриптов (validate-config, check-stop-words, yandex/google suggest, atp-fetch, llm-cli×2, obsidian-sync)
- 16 sources в config (Yandex 8, Google 5, NW 1, LLM CLI 1, ATP 1)
- 12 делегатов через `~/.claude/agents/` и `claude-seo:*` plugin skills
- Obsidian-интеграция (через obsidian-native-mcp + obsidian-sync.py)
- 5 kepano-skills установлены параллельно
