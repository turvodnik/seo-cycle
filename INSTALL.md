# seo-cycle: установка под новый проект

Универсальный SEO-цикл скилл адаптируется под конкретный проект через конфиг `seo-cycle.yaml`. Этот документ — пошаговая инструкция для первой настройки.

## TL;DR

```bash
# Вариант A — интерактивный wizard (рекомендуется)
cd <project-root>
bash ~/.claude/skills/seo-cycle/scripts/init-project.sh
# базовые вопросы + governance + image workflow → seo-cycle.yaml + .env.example + policy-файлы + валидация

# Вариант B — ручная установка
# 1. Скопируй шаблон конфига в корень проекта
cp ~/.claude/skills/seo-cycle/config/project.template.yaml \
   <project-root>/seo-cycle.yaml

# 2. Отредактируй под свой сайт (см. шаги ниже)
$EDITOR <project-root>/seo-cycle.yaml

# 3. Провалидируй
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py <project-root>/seo-cycle.yaml

# 4. Добавь API-ключи в .env по списку из валидатора
$EDITOR <project-root>/.env

# 5. Готово — спрашивай Claude/Codex:
# «давай запустим SEO-цикл для категории X»
```

`install-codex.sh` ставит ядро в `~/.claude/skills/seo-cycle`, создаёт симлинки `~/.codex/skills/seo-cycle` и `~/.codex/skills/codex-primary-runtime`, а `init-project.sh` создаёт проектный `AGENTS.md` если его ещё нет. Wizard также спрашивает governance profile, monthly paid API/LLM budget и automation mode, чтобы по умолчанию не тратить токены и деньги без approval.

**OAuth setup для GSC/GA4/PSI/Метрики/Яндекса** → см. `docs/oauth-setup.md`.

---

## Шаг 1. Скопировать шаблон конфига

```bash
cp ~/.claude/skills/seo-cycle/config/project.template.yaml \
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

`stop_words_extra` — твой проектный список запретов. Базовые стоп-слова уже в `~/.claude/skills/seo-cycle/templates/stop-words.md`.

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
    api_key_env: NEURON_API_KEY        # ключ в .env
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
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py <project-root>/seo-cycle.yaml
```

Что проверяет:
- Обязательные поля заполнены
- ISO-коды валидны (language, country)
- Для каждого `enabled: true` источника — есть ли необходимые env-vars в `.env`
- delegate-цели существуют (скиллы / агенты)
- Пути в `artifacts.*` существуют или создаются автоматом
- policy-файлы проекта для NeuronWriter, Google NLP, data collection/access и RF tracking guard
- governance sanity: raw data не грузится в контекст, cache-first включён, paid sources не активны при нулевом бюджете, schedules не создаются без automation policy

Выдаёт **чек-лист** что нужно подключить:
```
[ ] Установить агент yandex-seo-specialist (ставится из ~/.claude/agents/)
[ ] Добавить NEURON_API_KEY в .env
[ ] Установить codex CLI: brew install codex
[ ] Создать seo/entities/entities.yaml (или отключить entities-секцию)
```

---

## Шаг 4. Подключить API-ключи в .env

По чек-листу из валидатора. Типичные ключи:

```bash
# .env проекта (НЕ коммитить!)

# NeuronWriter
NEURON_API_KEY=your_key_here
NEURON_LIMITS_FILE=seo/neuronwriter-limits.yaml

# Google Cloud Natural Language (только после budget + local guards)
GOOGLE_NLP_ENABLED=0
GOOGLE_NLP_POLICY_FILE=seo/entities/google-nlp-policy.yaml

# AnswerThePublic
TOKEN_ANSWERTHEPUBLIC=atp_pk_live_...

# WordPress (если publishing.cms = wordpress)
WP_BASE_URL=https://example.com
WP_USER=admin
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx
WOO_REST_API_KEY=ck_...
WOO_REST_API_SECRET=cs_...

# DataForSEO (опционально)
DATAFORSEO_LOGIN=...
DATAFORSEO_PASSWORD=...
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
seo/project-intake.yaml
AGENTS.md -> ~/.claude/skills/seo-cycle/AGENTS.md
```

В этих файлах фиксируются подключённые аккаунты, пропущенные платные сервисы, лимиты NeuronWriter/Google NLP/Keys.so/Serpstat/LLM, policy по robots/Content-Signal, запрет зарубежных tracking tags/pixels для РФ-проектов без отдельного разрешения и правила автоматизаций.

Перед дорогим сбором или schedule запуском:

```bash
python3 ~/.claude/skills/seo-cycle/scripts/governance-report.py --format md
python3 ~/.claude/skills/seo-cycle/scripts/automation-plan.py --write --include-disabled
```

`automation-plan.py` создаёт `seo/automations/automation-plan.md`, `automation-plan.json`, `crontab.txt` и launchd plist-шаблоны. Реальный `--install-cron` заблокирован, пока одновременно не включены `governance.automation_policy.create_schedules: true`, `seo/automation-policy.yaml create_schedules: true` и env `SEO_CYCLE_ALLOW_SCHEDULE_INSTALL=1`.

---

## Шаг 6. (Опционально) Создать проектные суб-скиллы

Универсальный seo-cycle делегирует в субскиллы. По умолчанию использует общие из `~/.claude/agents/`, но для специфичных задач (custom CMS publishing, brand-specific entity map) лучше создать **проектные скиллы** в `<project>/.claude/skills/`.

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

> **Регион — одной строкой.** `region_profile: ru | eu | us | global` управляет тем, какие источники включены (Яндекс-стек для `ru`, западные SaaS для `eu`/`us`, и т.д.) и какие недоступны/нужен прокси. Профили: `config/region-profiles/`. `init-project.sh` выбирает профиль по стране автоматически. Развернуть в список активных: `python3 ~/.claude/skills/seo-cycle/scripts/resolve-sources.py`.

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
2. **Создай скрипт** в `<project>/seo/scripts/<source>.py` или `~/.claude/skills/seo-cycle/scripts/` (для PR upstream)
3. **Опиши в Phase 2 как использовать** в `<project>/CLAUDE.md`
4. (Опционально) **Создай PR в общий скилл** если решение полезно для других проектов

См. `docs/architecture.md` для деталей.

---

## Где что лежит после установки

```
<project-root>/
├── seo-cycle.yaml                       # КОНФИГ проекта
├── CLAUDE.md                            # правила проекта (опционально)
├── .env                                 # API ключи (gitignore!)
├── seo/
│   ├── cycles/<topic>-<quarter>/        # снапшоты циклов (создаётся скиллом)
│   ├── entities/entities.yaml           # реестр сущностей
│   └── research/
│       ├── perplexity/results/
│       ├── atp/results/
│       └── llm-cli/results/
├── blog/                                # черновики постов
└── categories/                          # черновики категорий

~/.claude/skills/seo-cycle/              # глобальный универсальный скилл
├── SKILL.md                             # этот скилл
├── AGENTS.md                            # Codex entrypoint, симлинк → SKILL.md
├── codex-primary-runtime/               # отдельный Codex-first entrypoint skill
├── INSTALL.md                           # этот файл
├── CHANGELOG.md                         # история версий
├── .env.example                         # шаблон ключей
├── config/
│   ├── project.template.yaml            # шаблон конфига проекта
│   ├── region-profiles/{ru,eu,us,global}.yaml   # пресеты источников по региону
│   ├── projects-registry.yaml           # реестр всех проектов (для monthly-runner --all)
│   └── triggers.yaml                    # правила Phase 10
├── prompts/                             # универсальные промпты
├── scripts/                             # переносимые скрипты (resolve-sources, db-sync,
│                                        #   notify, serpstat/spyfu-fetch, schema-org-build, ...)
├── templates/                           # шаблоны artifacts + project-policies
└── docs/                                # архитектура + adapt + migration
```

## Troubleshooting

**«Конфиг не найден»** — скилл искал в 4 локациях, всех нет. Проверь имя файла и место (см. начало этого документа).

**«Source X enabled but env-var Y not set»** — открой .env, добавь ключ; или временно отключи источник.

**«delegate.* refers to skill that doesn't exist»** — либо установи скилл (см. список агентов в `~/.claude/agents/`), либо удали поле из `delegate.*` — используется fallback.

**«NW evaluate fails»** — проверь project_id в конфиге; запусти `~/.claude/skills/seo-cycle/scripts/test-neuronwriter.py` для диагностики.

См. `docs/troubleshooting.md` для полного списка.

---

## Как поделиться скиллом

Скилл самодостаточен: вся логика — в `~/.claude/skills/seo-cycle/` (код, конфиг-шаблон, профили, промпты, доки). Проектные данные и ключи (`.env`, `seo-cycle.yaml`, контент) живут в репозитории проекта и НЕ входят в скилл.

**Что шарить:** весь каталог `~/.claude/skills/seo-cycle/` (без `__pycache__`). Секретов в нём нет — ключи только в `.env` проектов.

**Способы:**
1. **Git-репозиторий (рекомендуется).**
   ```bash
   cd ~/.claude/skills/seo-cycle
   git init && git add -A && git commit -m "seo-cycle skill"
   # запушить в GitHub. Получатель клонирует в ~/.claude/skills/seo-cycle/
   ```
2. **Архив.** `cd ~/.claude/skills && zip -r seo-cycle.zip seo-cycle -x '*__pycache__*'` → получатель распаковывает в `~/.claude/skills/`.
3. **Claude Code plugin.** Обернуть в плагин с `plugin.json` и раздать через marketplace/`/plugin install` (см. docs плагинов Claude Code).

**Получатель после установки:**
```bash
pip3 install pyyaml requests pillow beautifulsoup4 google-auth
cd <свой-проект>
~/.claude/skills/seo-cycle/scripts/init-project.sh   # wizard → seo-cycle.yaml
# заполнить .env своими ключами (см. .env.example)
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py
```
Дальше — в Claude Code или Codex: «запусти SEO-цикл для категории X».

**Проектные суб-скиллы** (`emwoody-*`) — это пример кастомизации под конкретный сайт; они НЕ шарятся как часть универсального скилла (содержат специфику проекта). Для нового проекта создаются свои тонкие wrapper-скиллы по образцу `emwoody-seo-cycle` (см. `docs/architecture.md`).
