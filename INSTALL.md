# seo-cycle: установка

Универсальный SEO-цикл адаптируется под конкретный проект через конфиг `seo-cycle.yaml`. Этот документ — установка и первая настройка.

## TL;DR — единый установщик `install.sh`

```bash
# 0. Хранилище (один раз на машину): клон + версии-worktree + CLI `seo-cycle`
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/install.sh | bash

# 1. Подключить проект (attach): канонический слой .agents/, поверхности
#    .claude/.codex, AGENTS.md (+ симлинки CLAUDE.md/GEMINI.md), wizard конфига
cd <project-root>
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/install.sh | bash -s -- --project "$(pwd)"

# Обновления и версии
~/.codex/vendor/seo-cycle/install.sh --update                          # fetch новых тегов в хранилище
~/.codex/vendor/seo-cycle/install.sh --project <dir> --pin vX.Y.Z --sync   # перевести проект на версию
~/.codex/vendor/seo-cycle/install.sh --upgrade-all                     # перевести все подключённые проекты
~/.codex/vendor/seo-cycle/install.sh --project <dir> --detach          # отключить проект (файлы проекта не трогаются)
```

**Модель дистрибуции.** Код скачивается один раз в хранилище `~/.codex/vendor/seo-cycle`; каждый релиз-тег доступен как read-only снапшот `~/.codex/vendor/versions/seo-cycle/vX.Y.Z` (git worktree — общие объекты, места почти не занимает). Проект видит seo-cycle только после явного `--project` attach: симлинк `.agents/external/seo-cycle → <версия>` плюс поверхности `.claude/skills/` и `.codex/skills/`. Пин версии фиксируется в `.agents/external-skills.lock.yaml`; разные проекты спокойно живут на разных версиях, обновление одного не трогает другие. Проекты без attach не получают ни одного файла и ни строчки контекста агентов.

**Мульти-агентная конвенция.** Attach создаёт канонический `AGENTS.md` проекта (реальный файл) и симлинки `CLAUDE.md → AGENTS.md`, `GEMINI.md → AGENTS.md` — Codex, Claude Code и Gemini/Antigravity читают один и тот же источник. Существующие файлы не перезаписываются.

**Секреты.** Значения API-ключей живут в macOS Keychain (инструмент `ai-secret`), а не в `.env`. `.env.example` в проекте — только список имён. Скрипты получают ключи через `ai-secret run <scope> -- <команда>`; legacy `.env` переносится разово командой `ai-secret import <scope> .env`.

Legacy-обёртки (URL стабильны, внутри вызывают `install.sh`): `bootstrap-codex.sh`, `bootstrap-claude.sh`, `install-codex.sh`.

```bash
# Опционально: локальный AI/dev toolchain для Codex/spec/research задач
bash ~/.codex/vendor/seo-cycle/scripts/install-ai-toolchain.sh --codex

# Опционально: NotebookLM MCP для curated expert knowledge base
bash ~/.codex/vendor/seo-cycle/scripts/install-ai-toolchain.sh --codex --notebooklm

# Ручной путь без wizard: скопируй шаблон конфига и провалидируй
cp ~/.codex/vendor/seo-cycle/config/project.template.yaml <project-root>/seo-cycle.yaml
$EDITOR <project-root>/seo-cycle.yaml
python3 ~/.codex/vendor/seo-cycle/scripts/validate-config.py <project-root>/seo-cycle.yaml

# 4. Сгенерируй безопасный стек инструментов
python3 ~/.codex/vendor/seo-cycle/scripts/tool-stack-recommender.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/growth-roadmap.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/setup-onboarding.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/setup-blueprint.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/project-upgrade-assistant.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/access-key-assistant.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/setup-gap-audit.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/setup-answer-plan.py <project-root>/seo-cycle.yaml --write  # после заполнения setup-questionnaire.csv
python3 ~/.codex/vendor/seo-cycle/scripts/launch-plan.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/spend-guard.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/expert-source-pack.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/ai-brand-audit.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/answer-units-audit.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/technical-guardrails-audit.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/link-audit.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/redirect-map-audit.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/lighthouse-audit.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/serpstat-audit.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/labrika-source-pack.py <project-root>/seo-cycle.yaml --write
python3 ~/.codex/vendor/seo-cycle/scripts/ai-bot-access-check.py <project-root>/seo-cycle.yaml --url https://example.com/ --write

# 5. Добавь API-ключи в Keychain только по списку из access-key assistant
#    (значения вводятся скрытым вводом; .env с значениями не создаётся)
ai-secret set <project-scope> <ИМЯ_КЛЮЧА>

# 6. Готово — спрашивай Claude/Codex:
# «давай запустим SEO-цикл для категории X»

# 7. Project Knowledge Hub: wiki + context pack + Graphify/zvec status
cd <project-root>
bash ./.codex/skills/seo-cycle/scripts/knowledge/wiki-refresh-all.sh
bash ./.codex/skills/seo-cycle/scripts/knowledge/graphify-refresh.sh
```

### Единая команда `seo-cycle`

`install-codex.sh` создаёт symlink `~/.local/bin/seo-cycle` (если `~/.local/bin` не в PATH — установщик подскажет export-строку, ничего в shell rc не меняется молча). Дальше из корня любого проекта:

```bash
seo-cycle status          # текущая стадия, blockers, следующие команды (project-journey)
seo-cycle doctor          # сводный read-only health: config, journey, spend, ledger, provider health
seo-cycle loop research-package seo/research-package   # автоцикл gate → repair → re-check
seo-cycle approvals       # pending approval-тикеты; approve/reject <id>
seo-cycle run "задача"    # low-token маршрут через task-router
seo-cycle --help          # полный список команд
```

Каждая подкоманда — тонкая обёртка над соответствующим скриптом: все флаги (`--write`, `--live`, `--format` и т.д.) пробрасываются как есть, exit-коды и stdout-контракты не меняются.

`install.sh --project` ставит seo-cycle как **версионированное хранилище + project-local attach**: общий код в `~/.codex/vendor/`, в проекте — симлинк `.agents/external/seo-cycle` на конкретную версию и поверхности `./.codex/skills/seo-cycle`, `./.claude/skills/seo-cycle`. Если проект не подключали, seo-cycle в нём не появляется и не читается. Полный vendor clone в проект доступен через `--vendor-local`; legacy global skill exposure только через `--global-skill`. Attach создаёт `AGENTS.md` (+ симлинки `CLAUDE.md`/`GEMINI.md`), `.env.example` (только имена ключей — значения в Keychain через `ai-secret`), дефолтный `.gitignore` и запускает `init-project.sh`. WordPress/Novomira MCP не создаётся автоматически; включай его только флагом `--with-wordpress-mcp` или явной командой. Wizard спрашивает governance profile, monthly paid API/LLM budget и automation mode, чтобы по умолчанию не тратить токены и деньги без approval.

WordPress/Novomira MCP не надо добавлять в глобальный `~/.codex/config.toml` и не надо включать во всех проектах. Для проекта, где он нужен, запускай:

```bash
cd <project-root>
python3 ./.codex/skills/seo-cycle/scripts/project-mcp-config.py --write
```

Это создаст/обновит только managed-блок в `./.codex/config.toml`. Реальные значения живут в macOS Keychain (scope проекта) и попадают только в env дочернего процесса:

```bash
ai-secret set <project> WP_API_URL        # человек вводит значения скрытым вводом
ai-secret set <project> WP_API_USERNAME
ai-secret set <project> WP_API_PASSWORD
```

Так MCP появляется только в текущем проекте, а URL/логин/ключ не перезаписывают другие сайты.

Основной канал для WordPress остаётся REST API + Application Password — ключи `WP_BASE_URL`, `WP_USER`, `WP_APP_PASSWORD` в том же Keychain-scope; скрипты публикации запускаются как `ai-secret run <project> -- python3 …`.

Через него делаем стандартные операции: создавать/обновлять посты, страницы, товары, media, meta и использовать REST endpoints плагинов. Novomira MCP подключается только точечно, когда REST API недостаточно или нужны специальные abilities.

`scripts/install-ai-toolchain.sh --codex` ставит только безопасный локальный support-набор: GitHub Spec Kit CLI, Microsoft MarkItDown, Graphify и CodeGraph + Codex-интеграции Graphify/CodeGraph. Он не ставит stealth/anti-bot браузеры, платные API, memory-сервисы и не пишет секреты. Проверка: `bash ./.codex/skills/seo-cycle/scripts/install-ai-toolchain.sh --check` из установленного проекта или `bash ~/.codex/vendor/seo-cycle/scripts/install-ai-toolchain.sh --check` для shared core.

`--notebooklm` — отдельный явный флаг для подключения NotebookLM MCP как gated bridge к curated expert knowledge base. Он добавляет MCP-сервер в `~/.codex/config.toml`, но не получает доступ к notebook без первичного Google login через `setup_auth`. По умолчанию включён `standard` profile и отключены destructive/write/audio tools.

После wizard сначала открой `seo/setup/context-pack.md`: это самый короткий task-scoped вход для Claude/Codex, теперь с `context_manifest` и явным запретом raw-артефактов в контексте. Затем открой `seo/setup/token-waste-audit.md`, `seo/setup/perplexity-health.md`, `seo/setup/notebooklm-health.md`, `seo/setup/xmlriver-health.md` и `seo/setup/writerzen-health.md`: они показывают, где нужно заменить raw на distillate, доступен ли Perplexity persistent app/browser/API fallback, в каком режиме работает NotebookLM MCP/export, готов ли XMLRiver для guarded SERP/Wordstat enrichment и готов ли WriterZen browser/export workflow. Для evidence-сбора используй `perplexity-collect.py --topic "<тема>" --write`, `notebooklm-source-pack.py --topic "<тема>" --export-file <export.md> --write`, `xmlriver-source-pack.py --query "<запрос>" --engine yandex --input-file serp.xml --write` и `writerzen-browser-collect.py --topic "<тема>" --force-new-report --manual-fallback-seconds 120 --write`: raw уходит в `seo/research/raw/`, bounded summaries — в `seo/research/distillates/`, связи — в `seo/research/vector/source_pack.jsonl`. XMLRiver live запускается только `--live --allow-paid` после spend guard; WriterZen collector работает через persistent browser profile, сам создаёт отчёты, скачивает CSV/XLSX и импортирует их, без хранения пароля. Затем открой `seo/setup/setup-blueprint.md`: там компактная матрица стран/регионов/поисковиков/типа бизнеса/marketing/ads/tools/budget/automations и first-read файлы. Для существующих проектов открой `seo/setup/upgrade-assistant.md` и `seo/setup/upgrade-questionnaire.csv`: там yes/no/defer вопросы по новым функциям без автоперезаписи `seo-cycle.yaml`. Затем открой `seo/setup/access-key-assistant.md`: там только нужные этому проекту ключи/токены, ссылки и env names, без secret values. Затем открой `seo/setup/setup-questionnaire.csv` или `seo/setup/setup-gap-audit.md`: там readiness score и вопросы по незаполненным бизнес/рынок/local/ecommerce/budget/tool деталям, без хранения секретов. После заполнения CSV запусти `setup-answer-plan.py --write` и открой `seo/setup/setup-answer-plan.md`: это review-only план ручных правок, без автоприменения и без сохранения secret-like ответов. Если нужно больше контекста, открой `seo/setup/launch-plan.md`: компактный первый экран проекта с market/business matrix, token/budget/subscription controls, tool packs, env names, approval gates, automations и execution order.
После setup/control-plane запусти Knowledge Hub: `bash ./.codex/skills/seo-cycle/scripts/knowledge/wiki-refresh-all.sh`. Он создаёт `seo/knowledge/wiki/` как источник правды по проекту: правила, статьи, категории, бренды, товары, internal links, API catalog, review/comparison candidates и `latest-context-pack.md`. Затем `bash ./.codex/skills/seo-cycle/scripts/knowledge/graphify-refresh.sh` построит Graphify-граф через Antigravity/Gemini CLI/API или безопасно запишет degraded status, если Graphify ещё не установлен. Перед правкой страницы используй `wiki-preflight.py`; перед публикацией публичного текста — `content-taste-gate.py`. Подробно: `docs/knowledge-hub.md`.
Затем открой `seo/setup/tool-stack-report.md`: там видно, какие Google/Yandex/Bing/Microsoft/NLP/AI/merchant/local/ads/tracking инструменты можно использовать сразу, какие требуют approval, а какие отключены из-за региона, бюджета или RF tracking policy.
Перед платными/API/LLM/subscription действиями открой `seo/setup/spend-guard.md`: там allowed/approval/blocked по сервисам, остатки лимитов и точные `usage-ledger.py check` preflight-команды.
Затем открой `seo/setup/growth-roadmap.md`: там top-N приоритетов по техническому SEO, search evidence, ecommerce/local, контенту/сущностям, AI visibility, CRO/маркетингу и automations.
Для расширенного SEO/AEO/GEO слоя открой `seo/vnext/expert-source-pack.md`, `seo/vnext/ai-brand-audit.md`, `seo/vnext/answer-units-audit.md` и `seo/vnext/technical-guardrails-audit.md`. Остальные vNext отчёты запускай точечно: `eeat-evidence-map.py`, `geo-kpi-model.py`, `log-bot-audit.py`, `ai-bot-access-check.py`, `snippet-sitemap-audit.py`, `traffic-drop-diagnostics.py`, `cannibalization-audit.py`, `ru-commerce-readiness.py`, `offpage-risk-audit.py`, `conversion-sxo-audit.py`. Для инструментальной технички используй `seo/technical/*.md`: `technical-site-audit.py` (rollup), `link-audit.py` (`linkinator` JSON/live, включая anchors), `redirect-map-audit.py` (CSV redirect map), `gsc-url-inspection.py` (Google URL Inspection export/live read-only), `bing-url-inspection.py` (Bing GetUrlInfo export/live read-only), `technical-mcp-health.py` (optional GSC/GA/Lighthouse MCP readiness), `lighthouse-audit.py` (Lighthouse JSON/live), `serpstat-audit.py` (guarded API), `labrika-source-pack.py` и `labrika-health.py` (manual/export/readiness). Все они report-only и не меняют сайт; `ai-bot-access-check.py`, `link-audit.py --live`, `lighthouse-audit.py --live`, GSC/Bing/Serpstat `--live` делают live HTTP/API-запросы и поэтому запускаются явно. Serpstat live требует `SERPSTAT_API_KEY` и approval на кредиты.
Подробный файл первого запуска — `seo/setup/onboarding-playbook.md`: там разделены шаги агента, human-secret ввод, review и approval.

**OAuth setup для GSC/GA4/PSI/Метрики/Яндекса** → см. `docs/oauth-setup.md`.

---

## Шаг 1. Скопировать шаблон конфига

```bash
cp ./.codex/skills/seo-cycle/config/project.template.yaml \
   <project-root>/seo-cycle.yaml
```

Допустимые имена и места:
- `<project-root>/seo-cycle.yaml` ← **рекомендованное**
- `<project-root>/.seo-cycle.yaml`
- `<project-root>/seo/seo-cycle.yaml`
- `<project-root>/.claude/seo-cycle.yaml`

Скилл ищет в этом порядке.

---

## Шаг 2. Заполнить конфиг

Открой `seo-cycle.yaml` и пройдись по секциям. Минимально нужно заполнить identity, locale, engines, governance, project type, business profile и sources:

### Секция 1 — Identity
```yaml
project:
  name: "Имя проекта в свободной форме"
  domain: "example.com"                # без https://
  brand_name_user_facing: "Бренд"      # как пишем в user-facing текстах
  brand_name_technical: "brand"        # для URL/slug — латиница
  description: "1-3 предложения: ниша, аудитория, что продаём"
```

**Важно для кириллических проектов:** если бренд пишется кириллицей в текстах (как «Эмвуди»), указывай оба варианта — скилл будет автоматом следить, чтобы в user-facing контенте использовался `brand_name_user_facing`, а в URL/коде — `brand_name_technical`.

### Секция 2 — Locale
```yaml
locale:
  language: ru                          # ISO 639-1
  country: RU                           # ISO 3166-1 alpha-2
  region: "Москва и МО"                 # человеческое название
  yandex_region_code: 213               # 213=Москва, 1=МО, 225=Россия
  google_gl: ru
  google_hl: ru
  timezone: "Europe/Moscow"
```

**Подсказки:**
- Глобальный проект без региональной привязки → `region: "Global"`, `yandex_region_code: 225` (или удалить весь блок Яндекса).
- Только западный рынок → удали `yandex_*` поля, оставь только Google.
- Локальный бизнес → укажи конкретный город, используется для LocalBusiness schema и локальных сигналов.

### Секция 3 — Search engines
```yaml
engines:
  - name: yandex
    priority: 1
  - name: google
    priority: 2
```

Удали то, что не нужно. Скилл пропустит фазы для удалённых движков.

### Секция 3b — Governance
```yaml
governance:
  profile: lean_quality
  token_policy:
    raw_data_in_context: false
    cache_first: true
  budget_policy:
    monthly_paid_api_usd_cap: 0
    monthly_llm_usd_cap: 0
    paid_tools_default: approval_only
  automation_policy:
    default_mode: approval_only
    create_schedules: false
```

Для новых проектов оставляй `lean_quality` и нулевой бюджет, пока не подключены реальные лимиты. Платные API, публикация, index submission, массовый браузерный сбор и schedule-автоматизации должны идти через approval gates.

### Секция 4 — Project type
```yaml
project_type: ecommerce       # ecommerce | blog | saas | local_business | corporate | media | portfolio
cms: wordpress                # wordpress | shopify | webflow | nextjs | static | custom
```

Используется в Phase 1 (что аудитим) и Phase 8 (типы schema). Если CMS уникальная — ставь `custom` и описывай в `publishing.publish_skills` свой подход.

### Секция 5 — Industry & niche
```yaml
industry:
  name: "Building Materials"
  tags: [construction, b2c, b2b]
  primary_categories: ["...", "..."]
  homepage_h1: "..."          # утверждённый H1, если есть
```

Используется как контекст для LLM-промптов и валидации релевантности контента.

### Секция 6 — Tone of voice
```yaml
tone:
  formal_level: 2             # 1-5
  avoid_epithets: true
  stop_words_extra:
    - "уникальный"
    - "лучший"
  description: "Деловой, без воды, факты."
```

`stop_words_extra` — твой проектный список запретов. Базовые стоп-слова уже в `./.codex/skills/seo-cycle/templates/stop-words.md` после bootstrap.

### Секция 7 — Data sources
**Главный шаг настройки.** Идём по списку источников и решаем, что **сейчас** доступно. Что недоступно — `enabled: false`, потом включим.

Минимум для старта (бесплатно, без API):
```yaml
sources:
  yandex_wordstat:
    enabled: true             # делегируется в yandex-seo-specialist агент
  yandex_suggest:
    enabled: true             # script — бесплатно, без API
  google_suggest:
    enabled: true             # script — бесплатно
  llm_cli:
    antigravity:
      enabled: true           # если установлен `agy`
    codex:
      enabled: true           # если установлен `codex`
```

Платные/API источники включай по мере подключения:
```yaml
  neuronwriter:
    enabled: true
    api_key_env: NEURON_API_KEY        # имя env-переменной (значение — в Keychain через ai-secret)
    project_id: "<твой ID из NW>"

  answerthepublic:
    enabled: true
    api_key_env: TOKEN_ANSWERTHEPUBLIC
```

Browser-MCP источники (требуют установленного Claude for Chrome) включай когда настроишь:
```yaml
  yandex_wordstat_deep:
    enabled: true
  yandex_serp_blocks:
    enabled: true
  perplexity:
    enabled: true
    setup_doc: "./seo/research/perplexity/SETUP.md"
```

---

## Шаг 3. Провалидировать конфиг

```bash
python3 ./.codex/skills/seo-cycle/scripts/validate-config.py <project-root>/seo-cycle.yaml
```

Что проверяет:
- Обязательные поля заполнены
- ISO-коды валидны (language, country)
- Для каждого `enabled: true` источника — есть ли необходимые env-vars в `.env`
- delegate-цели существуют (скиллы / агенты)
- Пути в `artifacts.*` существуют или создаются автоматом
- policy-файлы проекта для NeuronWriter, Google NLP, data collection/access и RF tracking guard
- governance sanity: raw data не грузится в контекст, cache-first включён, paid sources не активны при нулевом бюджете, schedules не создаются без automation policy
- tool-stack артефакты для выбора бесплатных, paid/quota, AI, merchant/local, ads и tracking инструментов под регион/бизнес/бюджет
- spend-guard артефакты для контроля подписок, paid API, LLM, ads, остатков лимитов и preflight-команд
- growth-roadmap артефакты для приоритизации действий перед широким циклом
- onboarding playbook с владельцами шагов, env names, approval gates, командами и proof-файлами
- setup-blueprint и setup-matrix с точечной матрицей стран, регионов, поисковиков, бизнеса, marketing/ads/tracking policy, инструментов, budget/subscriptions, automations и guardrails
- upgrade-assistant и upgrade-questionnaire для review-only включения новых функций в существующих проектах
- access-key-assistant для project-specific списка нужных ключей/токенов без secret values
- context-pack handoff с read order, task route, caps, spend blockers, approval gates и do-not-load-raw
- setup-gap-audit, setup-questionnaire и setup-answer-plan с readiness score, missing fields, target files, follow-up commands, вопросами по деталям проекта и review-only планом ручного внесения заполненных ответов
- launch-plan contract с market/business matrix, token/budget/subscription controls, tool packs, env names, approval gates и execution order

Выдаёт **чек-лист** что нужно подключить:
```
[ ] Установить агент yandex-seo-specialist в project-local `.claude/agents/` или `.agents/`
[ ] Добавить NEURON_API_KEY в .env
[ ] Установить codex CLI: brew install codex
[ ] Создать seo/entities/entities.yaml (или отключить entities-секцию)
```

---

## Шаг 4. Подключить API-ключи через Keychain (`ai-secret`)

**`.env` с реальными значениями запрещён политикой (§5 глобальных правил).** Значения ключей живут в macOS Keychain, доступ к ним — только через инструмент `ai-secret`; `.env.example` в проекте — каталог ИМЁН без значений (см. `docs/oauth-setup.md` — как получить каждый ключ).

По чек-листу из валидатора зарегистрируй нужные проекту ключи в Keychain (человек вводит значение скрытым вводом, агент значений не видит):

```bash
# scope — слаг проекта (например emwoody) или global
ai-secret set <project-scope> NEURON_API_KEY
ai-secret set <project-scope> TOKEN_ANSWERTHEPUBLIC
ai-secret set <project-scope> WP_BASE_URL
ai-secret set <project-scope> WP_USER
ai-secret set <project-scope> WP_APP_PASSWORD
ai-secret set <project-scope> WOO_REST_API_KEY
ai-secret set <project-scope> WOO_REST_API_SECRET
ai-secret set <project-scope> DATAFORSEO_LOGIN
ai-secret set <project-scope> DATAFORSEO_PASSWORD
# полный список имён — .env.example проекта
```

Не заполняющиеся ключи (опции, которые не используешь) просто не регистрируй — валидатор считает отсутствующий необязательный ключ нормой.

Скрипты и агент получают значения только в окружении дочернего процесса, не читая их сами:

```bash
ai-secret run <project-scope> -- seo-cycle <команда>
```

Если в проекте уже есть legacy `.env` со значениями — перенеси разово и удали файл:

```bash
ai-secret import <project-scope> .env
rm .env
```

---

## Шаг 5. Создать стартовую структуру каталогов

Скилл создаст автоматически при первом запуске, но можно подготовить заранее:

```bash
cd <project-root>
mkdir -p seo/{cycles,entities,research/{perplexity/{prompts,results},atp/results,llm-cli/{prompts,results}}}
mkdir -p blog categories pages-service

# Опционально — реестр сущностей
touch seo/entities/entities.yaml
```

Wizard также создаёт безопасные шаблоны:

```
seo/neuronwriter-limits.yaml
seo/entities/google-nlp-policy.yaml
seo/seo-data-collection-map.md
seo/access-setup-runbook.md
seo/ai-visibility-prompts.csv
seo/tool-budget.yaml
seo/automation-policy.yaml
seo/automation-policy.generated.yaml
seo/automations/automation-recommendations.md
seo/setup-blueprint.generated.yaml
seo/setup/setup-blueprint.md
seo/setup/setup-matrix.csv
seo/setup/upgrade-assistant.md
seo/setup/upgrade-questionnaire.csv
seo/setup/access-key-assistant.md
seo/setup/access-key-assistant.csv
seo/setup/context-pack.md
seo/setup/setup-gap-audit.md
seo/setup/setup-questionnaire.csv
seo/usage/usage-ledger.jsonl
seo/setup/latest-usage-ledger.md
seo/project-intake.yaml
.codex/skills/seo-cycle -> ~/.codex/vendor/seo-cycle
.agents/skills/seo-cycle -> .codex/skills/seo-cycle
.claude/skills/seo-cycle -> .codex/skills/seo-cycle
.codex/config.toml        # project-local MCP wrapper (известное исключение: этот
                           # конкретный интеграционный путь пока читает секреты из
                           # .env при MCP-старте, а не через ai-secret — легаси
                           # project-mcp-config.py, чинится отдельно, не Шагом 4)
AGENTS.md                 # project-local wrapper, if project did not have one
```

В этих файлах фиксируются подключённые аккаунты, пропущенные платные сервисы, лимиты NeuronWriter/Google NLP/Keys.so/Serpstat/LLM, policy по robots/Content-Signal, запрет зарубежных tracking tags/pixels для РФ-проектов без отдельного разрешения и правила автоматизаций. После заполнения `seo/setup/setup-questionnaire.csv` отдельная команда `setup-answer-plan.py --write` создаёт `seo/setup/setup-answer-plan.md/json/csv`.

Перед дорогим сбором или schedule запуском:

```bash
python3 ./.codex/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write
python3 ./.codex/skills/seo-cycle/scripts/setup-control-plane.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-blueprint.py --write
python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write
python3 ./.codex/skills/seo-cycle/scripts/access-key-assistant.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-gap-audit.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-answer-plan.py --write  # после заполнения setup-questionnaire.csv
python3 ./.codex/skills/seo-cycle/scripts/launch-plan.py --write
python3 ./.codex/skills/seo-cycle/scripts/spend-guard.py --write
python3 ./.codex/skills/seo-cycle/scripts/task-router.py --task "аудит индексации и robots" --write
python3 ./.codex/skills/seo-cycle/scripts/context-pack.py --task "аудит индексации и robots" --write
python3 ./.codex/skills/seo-cycle/scripts/usage-ledger.py report --write
python3 ./.codex/skills/seo-cycle/scripts/automation-recommender.py --write
python3 ./.codex/skills/seo-cycle/scripts/governance-report.py --format md
python3 ./.codex/skills/seo-cycle/scripts/project-profile.py --write
python3 ./.codex/skills/seo-cycle/scripts/automation-plan.py --write --include-disabled
```

`setup-control-plane.py` — единый post-init отчёт: refresh intake/profile, resolve sources, governance, validate-config, automation plan, spend guard, launch plan, setup blueprint, upgrade assistant, access-key assistant, context pack, token-waste audit, Perplexity/NotebookLM/XMLRiver health, setup gap audit/questionnaire, answer-plan path readiness и стартовый task route; пишет `seo/setup/setup-control-plane.md`, `setup-control-plane.json`, `setup-blueprint.md/json`, `setup-matrix.csv`, `upgrade-assistant.md/json`, `upgrade-questionnaire.csv`, `access-key-assistant.md/json/csv`, `context-pack.md/json`, `token-waste-audit.md/json`, `perplexity-health.md/json`, `notebooklm-health.md/json`, `xmlriver-health.md/json`, `setup-gap-audit.md/json`, `setup-questionnaire.md/csv/json`, `spend-guard.md/json`, `launch-plan.md/json`, `latest-validation.txt`, `latest-governance.json`, `latest-sources.json`, `latest-task-route.md/json`. `--apply-profile` остаётся отдельным явным действием.

`context-pack.py` — самый короткий task-scoped handoff для Claude/Codex. Пишет `seo/setup/context-pack.md/json` и `seo/setup/latest-context-pack.md/json`: что читать первым, `context_manifest`, какие raw-артефакты не грузить, какие approval gates/spend blockers действуют, какие команды запускать дальше.

`token-waste-audit.py` — read-only аудит лишнего контекста. Пишет `seo/setup/token-waste-audit.md/json` и latest copies: raw artifacts, oversized distillates и large context candidates. Исправление — делать distillates/latest-summary, а не читать raw в модель.

`perplexity-health.py`, `notebooklm-health.py` и `xmlriver-health.py` — read-only provider health. Perplexity проверяет persistent app/browser/API optional режимы без хранения паролей; NotebookLM проверяет MCP config/tools и fallback browser/manual export; XMLRiver показывает env names, цены и capabilities без live paid API. Эти отчёты нужны перед evidence work, где downstream prompts должны использовать только cached distillates + citations.

`perplexity-collect.py`, `notebooklm-source-pack.py` и `xmlriver-source-pack.py` — безопасные source evidence collectors. Первый принимает Perplexity export/raw response через `--raw-file` или `--stdin-raw` и пишет prompt packet/degraded status, если ответа ещё нет; второй принимает NotebookLM export через `--export-file` или `--stdin-export`; XMLRiver принимает SERP XML/Wordstat JSON через `--input-file` либо пишет guarded request plan. Все пишут `seo/research/raw/<provider>/`, `seo/research/distillates/<provider>/latest-summary.md/json` и `seo/research/vector/source_pack.jsonl`; live paid API и публикация на сайт не включаются по умолчанию.

`setup-blueprint.py` — компактная project setup matrix. Пишет `seo/setup-blueprint.generated.yaml`, `seo/setup/setup-blueprint.md/json`, latest copies и `seo/setup/setup-matrix.csv`: страны, регионы, поисковики, тип бизнеса, local/ecommerce, marketing/ads/tracking policy, tools, budget/subscriptions, automations, guardrails и first-read файлы. Секреты не хранит и конфиг не меняет.

`project-upgrade-assistant.py` — review-only помощник для существующих проектов. Сравнивает проект с текущим template/control-plane surface, пишет `seo/setup/upgrade-assistant.md/json`, latest copies и `seo/setup/upgrade-questionnaire.csv` с yes/no/defer вопросами. `seo-cycle.yaml` не меняет.

`access-key-assistant.py` — project-specific помощник по ключам/токенам. Читает tool-stack decision report, пишет `seo/setup/access-key-assistant.md/json/csv` только с нужными провайдерами, env names, ссылками и шагами. Secret values не печатает и не сохраняет; известное исключение — сгенерированные шаги-подсказки этого конкретного помощника пока советуют «скопировать в `.env`» вместо `ai-secret set` (легаси текст самого скрипта, чинится отдельно, не Шагом 4).

`setup-gap-audit.py` — детальный first-run readiness audit. Пишет `seo/setup/setup-gap-audit.md/json`, `seo/setup/setup-questionnaire.md/csv/json` и latest copies: score, missing fields, owner questions, target files, follow-up commands и project-type-aware проверки local/ecommerce/budget/tools без вывода секретов.

`setup-answer-plan.py` — безопасный разбор заполненного `seo/setup/setup-questionnaire.csv`. Пишет `seo/setup/setup-answer-plan.md/json/csv` и latest copies: target files, target paths, parsed proposed values и follow-up commands. Режим только `manual_review`; конфиги не меняет, secret-like ответы отклоняет и не сохраняет.

`task-router.py` — low-token роутер перед каждой конкретной задачей. Пример: `python3 ./.codex/skills/seo-cycle/scripts/task-router.py --task "собрать семантику по минеральной вате" --write`. Он классифицирует задачу, выбирает фазы/источники, показывает approval gates, blocked actions, рекомендуемую automation и context caps, чтобы не поднимать весь проект и сырые данные в контекст.

`usage-ledger.py` — единый учёт фактического расхода. `report --write` создаёт `seo/usage/usage-ledger.jsonl` и `seo/setup/latest-usage-ledger.md/json`; `check --service <tool> --usd ... --fail-on-block` проверяет лимиты перед запуском; `record --service <tool> ...` добавляет append-only событие после расхода. Ledger также импортирует старые `_usage.json` от Keys.so/SpyFu и usage Google NLP.

`automation-recommender.py` — подбирает tool-aware planned automations под тип проекта, рынок, поисковики, tool-stack/spend-guard, indexability, search consoles, Bing, schema/CWV, content decay, local/ecommerce/AI visibility и текущую policy. Пишет `seo/automations/automation-recommendations.md/json` и `seo/automation-policy.generated.yaml` с `tools`/`approval_gates`. `--apply` обновляет `seo/automation-policy.yaml` с backup; `create_schedules: true` ставится только с явным `--allow-schedules`.

`project-intake-wizard.py` создаёт/уточняет `seo/project-intake.yaml` + `seo/project-intake-report.md`: тип проекта, бизнес-модель, каналы продаж, страны/регионы/языки, поисковики, local platforms, merchant feeds, ads policy, analytics tracking policy, guarded tools, AI visibility platforms и governance defaults. После `init-project.sh` можно запускать `--interactive --write`; для автоматического заполнения из `seo-cycle.yaml` используется `--defaults --write`.

`project-profile.py` читает `seo/project-intake.yaml` и создаёт `seo/project-profile.generated.yaml` + `seo/project-profile-report.md`: какие страны/регионы/поисковики/источники/маркетинг/local/merchant/ads/video/analytics применять. `--apply` обновляет `seo-cycle.yaml` только явно и создаёт backup.

`automation-plan.py` создаёт `seo/automations/automation-plan.md`, `automation-plan.json`, `crontab.txt` и launchd plist-шаблоны. Для expanded matrix он генерирует safe report-only/dry-run/env-gated команды: spend guard refresh, read-only GSC/Yandex fetch при наличии env, Bing governance check, schema/CWV candidate checks и content refresh dry-run. Реальный `--install-cron` заблокирован, пока одновременно не включены `governance.automation_policy.create_schedules: true`, `seo/automation-policy.yaml create_schedules: true` и env `SEO_CYCLE_ALLOW_SCHEDULE_INSTALL=1`.

---

## Шаг 6. (Опционально) Создать проектные суб-скиллы

Универсальный seo-cycle делегирует в субскиллы. По умолчанию bootstrap создаёт project-local skill surface в `<project>/.codex/skills/`, `<project>/.agents/skills/`, `<project>/.claude/skills/`. Для специфичных задач (custom CMS publishing, brand-specific entity map) лучше создать **проектные скиллы** рядом, например `<project>/.claude/skills/`.

Пример (emwoody): `<project>/.claude/skills/emwoody-semantic-brief/`, `<project>/.claude/skills/emwoody-publish-taxonomy/`.

В конфиге пропишешь:
```yaml
delegate:
  semantic_brief: emwoody-semantic-brief
  category: emwoody-publish-taxonomy
```

---

## Шаг 7. Готово — запускаем цикл

В любой Claude Code или Codex сессии в этом проекте:

```
давай запустим SEO-цикл для категории «минеральная вата»
```

Скилл:
1. Найдёт `seo-cycle.yaml`
2. Валидирует
3. Спросит несколько уточняющих вопросов (Phase 0)
4. Пройдёт все enabled фазы для этого кластера
5. Сохранит артефакты в `<artifacts.cycles_root>/<topic>-<quarter>/`

---

## Адаптация под разные типы проектов

> **Регион — одной строкой.** `region_profile: ru | eu | us | global` управляет тем, какие источники включены (Яндекс-стек для `ru`, западные SaaS для `eu`/`us`, и т.д.) и какие недоступны/нужен прокси. Профили: `config/region-profiles/`. `init-project.sh` выбирает профиль по стране автоматически. Развернуть в список активных: `python3 ./.codex/skills/seo-cycle/scripts/resolve-sources.py`.

### A. Глобальный SaaS (английский, без региональной привязки)
```yaml
region_profile: us            # Яндекс off, западные SaaS on — автоматически
locale:
  language: en
  country: US
  region: "Global"
  google_gl: us
  google_hl: en
engines:
  - name: google
    priority: 1
project_type: saas
cms: webflow                  # или nextjs
content_rules:
  stock_first:
    enabled: false             # не релевантно
  local_signals:
    min_per_page: 0            # не нужны
```

### B. Локальный бизнес одного города в РФ (стоматология, автосервис)
```yaml
locale:
  language: ru
  yandex_region_code: 213
project_type: local_business
sources:
  yandex_business_maps:
    enabled: true             # критично
  yandex_q:
    enabled: true
content_rules:
  local_signals:
    min_per_page: 5
    examples: ["Москва", "район Хамовники", "м. Парк культуры"]
```

### C. Англоязычный блог (нет CMS, статика на Hugo/Astro)
```yaml
locale:
  language: en
  country: GB
project_type: blog
cms: static
publishing:
  enabled: false              # или укажи свою git-based pipeline
sources:
  answerthepublic:
    enabled: true             # тут region en/gb работает!
    default_region: gb
content_rules:
  stock_first:
    enabled: false
```

### D. E-commerce с акцентом на Я.Маркет (РФ)
Доп. источники в Phase 2:
```yaml
# Я.Маркет в твоём конфиге будет в custom-разделе sources:
sources:
  yandex_market_competitors:
    enabled: true
    method: manual            # пока скрипт не написан, делаем вручную
```

---

## Что делать когда нужно расширить скилл

Если в твоей нише нужны источники, которых нет в шаблоне:

1. **Добавь в свой `seo-cycle.yaml`** в `sources` под новым ключом
2. **Создай скрипт** в `<project>/seo/scripts/<source>.py` или в shared core `~/.codex/vendor/seo-cycle/scripts/` только если это upstream-изменение для всех проектов.
3. **Опиши в Phase 2 как использовать** в `<project>/CLAUDE.md`
4. (Опционально) **Создай PR в общий скилл** если решение полезно для других проектов

См. `docs/architecture.md` для деталей.

---

## Где что лежит после установки

```
<project-root>/
├── seo-cycle.yaml                       # КОНФИГ проекта
├── CLAUDE.md                            # правила проекта (опционально)
├── .env.example                         # только имена ключей (значения — в Keychain через ai-secret)
├── seo/
│   ├── cycles/<topic>-<quarter>/        # снапшоты циклов (создаётся скиллом)
│   ├── entities/entities.yaml           # реестр сущностей
│   └── research/
│       ├── perplexity/results/
│       ├── atp/results/
│       └── llm-cli/results/
├── blog/                                # черновики постов
└── categories/                          # черновики категорий

~/.codex/vendor/seo-cycle/              # shared updatable core, not auto-loaded as a global skill
├── SKILL.md                             # этот скилл
├── AGENTS.md                            # Codex entrypoint, симлинк → SKILL.md
├── codex-primary-runtime/               # отдельный Codex-first entrypoint skill
├── INSTALL.md                           # этот файл
├── CHANGELOG.md                         # история версий
├── .env.example                         # шаблон ключей
├── config/
│   ├── project.template.yaml            # шаблон конфига проекта
│   ├── region-profiles/{ru,eu,us,global}.yaml   # пресеты источников по региону
│   ├── projects-registry.example.yaml   # шаблон реестра; реальный projects-registry.yaml — локальный,
│   │                                    #   в .gitignore, создаётся init-project.sh (для monthly-runner --all)
│   └── triggers.yaml                    # правила Phase 10
├── prompts/                             # универсальные промпты
├── scripts/                             # переносимые скрипты (resolve-sources, db-sync,
│                                        #   notify, serpstat/spyfu-fetch, schema-org-build, ...)
├── templates/                           # шаблоны artifacts + project-policies
└── docs/                                # архитектура + adapt + migration
```

## Troubleshooting

**Обновляешь уже существующий clone/vendor-store, где реестр проектов
(config/projects-registry.yaml, машинно-локальный файл — не часть репозитория, в
`.gitignore` начиная с T-061) раньше отслеживался git'ом (версия до T-061)?** Начиная с этой версии файл убран из
трекинга (личные пути/домены не должны попадать в тег — T-061), а `git checkout`/
`git pull` на коммит ≥ этой версии удалит его из рабочего дерева, если он не изменён
локально (обычный переход tracked → untracked в git). Порядок безопасного апгрейда:
1. `cp config/projects-registry.yaml ~/.seo-cycle/projects-registry.yaml` (резервная копия
   вне git-дерева — если у тебя ещё не настроен `~/.seo-cycle/`, `mkdir -p ~/.seo-cycle`
   сначала).
2. Выполни апгрейд (`git pull` / `install.sh --update` / `--upgrade-all`) как обычно.
3. `cp ~/.seo-cycle/projects-registry.yaml config/projects-registry.yaml` — восстановить
   реальный реестр (файл теперь в `.gitignore`, коммитить его не нужно и не даст смысла).
Если реестра раньше не было или он не менялся руками — `init-project.sh` создаст пустой
из `config/projects-registry.example.yaml` при следующем подключении проекта сам, ничего
делать не нужно.

**«Конфиг не найден»** — скилл искал в 4 локациях, всех нет. Проверь имя файла и место (см. начало этого документа).

**«Source X enabled but env-var Y not set»** — зарегистрируй ключ через `ai-secret set <project-scope> <ИМЯ>` (см. Шаг 4); или временно отключи источник.

**«delegate.* refers to skill that doesn't exist»** — либо установи нужный project-local skill/agent в `.agents/skills/` или `.claude/skills/`, либо удали поле из `delegate.*` — используется fallback.

**«NW evaluate fails»** — проверь project_id в конфиге; запусти `ai-secret run <project-scope> -- ./.codex/skills/seo-cycle/scripts/nw-cli.sh projects` для диагностики (список проектов подтверждает, что ключ и доступ рабочие).

См. `docs/troubleshooting.md` для полного списка.

---

## Как поделиться скиллом

Скилл самодостаточен: вся общая логика — в `~/.codex/vendor/seo-cycle/` (код, конфиг-шаблон, профили, промпты, доки). В проекте лежат только локальные entrypoints/symlinks, конфиг, правила и `.env.example` (`seo-cycle.yaml`, `seo/project-rules.md`, контент) — значения ключей в проекте не хранятся, они в Keychain через `ai-secret`.

**Что шарить:** GitHub repo `turvodnik/seo-cycle`. Секретов в нём нет — значения ключей живут в Keychain каждой машины, в проектах — только имена (`.env.example`).

**Способы:**
1. **Git-репозиторий (рекомендуется).**
   ```bash
   cd ~/.codex/vendor/seo-cycle
   git init && git add -A && git commit -m "seo-cycle skill"
   # запушить в GitHub. Получатель ставит shared core через install-codex.sh.
   ```
2. **Одна команда установки.** `curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/install-codex.sh | bash` обновляет shared core. `bootstrap-codex.sh` потом создаёт project-local symlinks в нужном проекте.
3. **Claude Code plugin.** Обернуть в плагин с `plugin.json` и раздать через marketplace/`/plugin install` (см. docs плагинов Claude Code).

**Получатель после установки:**
```bash
pip3 install pyyaml requests pillow beautifulsoup4 google-auth
cd <свой-проект>
./.codex/skills/seo-cycle/scripts/init-project.sh   # wizard → seo-cycle.yaml
# зарегистрировать ключи в Keychain по .env.example (см. Шаг 4)
ai-secret set <project-scope> <ИМЯ_КЛЮЧА>
python3 ./.codex/skills/seo-cycle/scripts/validate-config.py
```
Дальше — в Claude Code или Codex: «запусти SEO-цикл для категории X».

**Проектные суб-скиллы** (`emwoody-*`) — это пример кастомизации под конкретный сайт; они НЕ шарятся как часть универсального скилла (содержат специфику проекта). Для нового проекта создаются свои тонкие wrapper-скиллы по образцу `emwoody-seo-cycle` (см. `docs/architecture.md`).
