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

- собирает семантику из 10+ источников (Яндекс, Google, Serpstat, SpyFu, NeuronWriter, LLM-CLI, AnswerThePublic, Perplexity);
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
| **Бережёт платные лимиты** | Клиенты Serpstat/SpyFu имеют guard'ы остатка кредитов и кэш. |
| **Двойной рантайм** | Работает и под Claude Code, и под Codex CLI (гибрид: наши скрипты + нативные skills). |
| **E-E-A-T из коробки** | Канонический Organization/LocalBusiness-узел, trust-блок источников, атрибуция источник→топ. |
| **Масштаб на N проектов** | Реестр проектов + `init-project.sh` + `monthly-runner.sh all`. |
| **Контроль токенов и бюджета** | `governance` + `tool-budget.yaml` + `governance-report.py`: cache-first, raw на диск, distillates в контекст, approval gates. |
| **Прозрачность** | Все артефакты — файлы в репозитории проекта; единая SQLite-БД; Obsidian-дашборд. |

---

## <a id="установка"></a>3. Установка (для человека)

```bash
# 1. Поставить сам скилл (один раз на машину)
git clone https://github.com/turvodnik/seo-cycle ~/.claude/skills/seo-cycle

# 2. Зависимости Python
pip3 install pyyaml requests pillow beautifulsoup4 google-auth

# 3. В корне СВОЕГО проекта — мастер настройки
cd /path/to/your-project
~/.claude/skills/seo-cycle/scripts/init-project.sh
#   → базовые вопросы + governance + image workflow →
#   → создаёт seo-cycle.yaml, .env.example, AGENTS.md и policy-файлы
#   → регистрирует проект в реестре

# 4. Заполнить ключи (только те источники, что используешь)
cp ~/.claude/skills/seo-cycle/.env.example .env
#   отредактировать .env (NEURON_API_KEY, SERPSTAT_API_KEY, WP_* и т.д.)

# 5. Проверить конфиг
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py
#   → печатает активные источники, чего не хватает в .env, предупреждения

# 6. Готово. В Claude Code / Codex: «запусти SEO-цикл для категории X»
```

**Что выдаёт `validate-config.py`:** список активных источников (с учётом `region_profile`), список недостающих env-переменных, предупреждения о несуществующих делегатах/путях/policy-файлах/governance, итог ✓/ошибки.

Перед дорогим сбором, браузерной сессией, публикацией или schedule:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/governance-report.py --format md
```

---

## <a id="установка-ии"></a>4. Установка для ИИ-агента (самостоятельная)

> Этот раздел — машинно-исполнимый сценарий. ИИ-агент (Claude/Codex/любой) может выполнить его сам, по шагам, без участия человека (кроме ввода секретных ключей).

```bash
# Шаг 1. Установить скилл
test -d ~/.claude/skills/seo-cycle || \
  git clone https://github.com/turvodnik/seo-cycle ~/.claude/skills/seo-cycle

# Шаг 2. Зависимости
python3 -c "import yaml, requests, PIL, bs4; import google.auth" 2>/dev/null || \
  pip3 install pyyaml requests pillow beautifulsoup4 google-auth

# Шаг 3. Создать конфиг проекта (неинтерактивно — через шаблон)
cd <project-root>
test -f seo-cycle.yaml || cp ~/.claude/skills/seo-cycle/config/project.template.yaml seo-cycle.yaml
#   затем отредактировать поля: project.name/domain, locale, region_profile,
#   project_type, cms, business_profile и images.*. Для РФ: region_profile: ru.

# Альтернатива: интерактивный wizard сразу спросит базовые поля + image workflow
# (governance profile, paid API/LLM budget, automation mode,
# featured/inline ratios, WebP width/quality, source policy, captions, lazy policy)
# и создаст AGENTS.md + policy-шаблоны для NeuronWriter/Google NLP/data access/budgets/automations.
~/.claude/skills/seo-cycle/scripts/init-project.sh

# Шаг 4. Создать .env (попросить у человека только значения ключей)
test -f .env || cp ~/.claude/skills/seo-cycle/.env.example .env

# Шаг 5. Валидация
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py
python3 ~/.claude/skills/seo-cycle/scripts/resolve-sources.py   # активные источники

# Шаг 6. Выбрать рантайм
#   Claude Code: читать ~/.claude/skills/seo-cycle/SKILL.md
#   Codex CLI:   export SEO_RUNTIME=codex; читать AGENTS.md + docs/codex-runtime.md
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
ln -sf ~/.claude/skills/seo-cycle/AGENTS.md ./AGENTS.md
export SEO_RUNTIME=codex
codex exec -c model_reasoning_effort="xhigh" -c web_search="live" \
  "Прочитай AGENTS.md и seo-cycle.yaml. Запусти Phase 2 для кластера X."
```
Полный маппинг — [docs/codex-runtime.md](docs/codex-runtime.md).

---

## <a id="модульность"></a>6b. Модульная архитектура (фазовые скиллы + state)

`seo-cycle` — **диспетчер**. Фазы постепенно выносятся в самостоятельные **фазовые скиллы** (каждый — папка `SKILL.md` + README, можно дёргать независимо, шарить и продавать отдельно). Координация — через единый файл состояния `seo/cycles/<тема>/_state.json` (контракт `cycle-state.py`). Это «цепочка передачи»: фазовый скилл читает state → делает своё → обновляет state → разблокирует следующую фазу.

**Вынесено (пилот):** `seo-keywords` (Phase 2-3). **Статус: дробление заморожено** (решение 2026-05-30) — монолитный `seo-cycle` основной; остальные фазы не выносим без явной потребности (продажа модулей / команда / переиспользование / параллелизм).

```bash
python3 ~/.claude/skills/seo-cycle/scripts/cycle-state.py init --topic "минвата"
python3 ~/.claude/skills/seo-cycle/scripts/cycle-state.py next      # разблокированные фазы
# → вызвать соответствующий фазовый скилл (seo-keywords и т.д.)
python3 ~/.claude/skills/seo-cycle/scripts/cycle-state.py gate keywords
python3 ~/.claude/skills/seo-cycle/scripts/cycle-state.py show      # прогресс
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
- `seo/automation-policy.yaml` — scheduled automations, approval gates, forbidden actions.
- `seo/project-intake.yaml` — детальная карта стран, регионов, поисковиков, рекламы, local/merchant/video/analytics decisions.

Правила:

- NeuronWriter — primary SERP/NLP редактор контента для briefs, terms, entities, questions, competitor scores и финального scoring, если есть `NEURON_API_KEY`, helper и limits-файл.
- Google Cloud Natural Language — guarded technical entity audit: entities, salience, syntax/category, mismatch `title/H1/schema/text`. Это не ranking submission и не прямой ranking signal.
- Whole-site NeuronWriter/Google NLP jobs запрещены без одобренной очереди URL/keywords и достаточного остатка в policy.
- Перед дорогим сбором или автоматизацией запускай `governance-report.py`; если бюджет/approval не позволяют, делай только report-only/cached/read-only шаг.
- Low-token режим обязателен: raw CSV/JSON/HTML на диск, в контекст только distillates/top-N; не читай весь репозиторий или сырьё без необходимости.
- Robots/Content-Signal: `search=yes, ai-input=yes, ai-train=no` допустимо как запрет обучения моделей. Публичный `robots.txt` должен быть чистым `text/plain`, без PHP warnings/HTML и editor/preview мусора.
- Для РФ-проектов не ставь зарубежные analytics/tracking tags или pixels без явного разрешения policy. GSC, Bing Webmaster, PageSpeed/CrUX, sitemap/robots checks и off-site API audits допустимы без установки кода аналитики.
- Никогда не выводи API keys, OAuth tokens, service-account JSON или значения `.env`; только имена переменных и пути.

---

## <a id="инструменты"></a>7. Инструменты (что делает · команда · результат)

> Все скрипты лежат в `~/.claude/skills/seo-cycle/scripts/`. Запуск: `python3 <script>.py` или `bash <script>.sh`.

### 7.1 Управление источниками и конфигом
| Скрипт | Что делает | Команда | Результат |
|---|---|---|---|
| `validate-config.py` | Проверяет `seo-cycle.yaml`, env, делегатов, policy-файлы и governance | `python3 validate-config.py` | Список активных источников, недостающие ключи/policy, ✓/ошибки |
| `resolve-sources.py` | Разворачивает `region_profile` + override в список активных источников | `python3 resolve-sources.py` | Активные/пропущенные источники с причиной + `seo/cycles/<date>/active-sources.json` |
| `governance-report.py` | Показывает token/budget/tool/automation policy без секретов | `python3 governance-report.py --format md` | Markdown/JSON отчёт для Phase 0 и approval gates |
| `automation-plan.py` | Генерирует безопасный schedule plan, cron и launchd templates | `python3 automation-plan.py --write --include-disabled` | `seo/automations/automation-plan.md`, `crontab.txt`, plist-шаблоны; install blocked без policy |
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

В Claude Code логика делегируется субагентам (поле `delegate.*` в конфиге). Универсальные агенты в `~/.claude/agents/`:

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

- collects keywords from 10+ sources (Yandex, Google, Serpstat, SpyFu, NeuronWriter, LLM-CLI, AnswerThePublic, Perplexity);
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
| **Protects paid limits** | Serpstat/SpyFu clients have credit/budget guards and caching. |
| **Dual runtime** | Runs under both Claude Code and Codex CLI (hybrid: our scripts + native skills). |
| **E-E-A-T built-in** | Canonical Organization/LocalBusiness node, source trust-block, source→top attribution. |
| **Scales to N projects** | Project registry + `init-project.sh` + `monthly-runner.sh all`. |
| **Token and budget control** | `governance` + `tool-budget.yaml` + `governance-report.py`: cache-first, raw to disk, distillates in context, approval gates. |
| **Transparent** | All artifacts are files in the project repo; single SQLite DB; Obsidian dashboard. |

---

## <a id="en-install"></a>3. Install (for humans)

```bash
# 1. Install the skill itself (once per machine)
git clone https://github.com/turvodnik/seo-cycle ~/.claude/skills/seo-cycle

# 2. Python deps
pip3 install pyyaml requests pillow beautifulsoup4 google-auth

# 3. In YOUR project root — setup wizard
cd /path/to/your-project
~/.claude/skills/seo-cycle/scripts/init-project.sh
#   → base questions + governance + image workflow → seo-cycle.yaml + .env.example + AGENTS.md + policy files
#   → registers the project

# 4. Fill keys (only sources you use)
cp ~/.claude/skills/seo-cycle/.env.example .env
#   edit .env (NEURON_API_KEY, SERPSTAT_API_KEY, WP_*, etc.)

# 5. Validate
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py

# 6. Done. In Claude Code / Codex: "run the SEO cycle for category X"
```

---

## <a id="en-ai"></a>4. Install for an AI agent (self-service)

> Machine-executable script. An AI agent (Claude/Codex/any) can run it itself,
> step by step, without a human (except entering secret keys).

```bash
# Step 1. Install skill
test -d ~/.claude/skills/seo-cycle || \
  git clone https://github.com/turvodnik/seo-cycle ~/.claude/skills/seo-cycle

# Step 2. Deps
python3 -c "import yaml, requests, PIL, bs4; import google.auth" 2>/dev/null || \
  pip3 install pyyaml requests pillow beautifulsoup4 google-auth

# Step 3. Project config (non-interactive — via template)
cd <project-root>
test -f seo-cycle.yaml || cp ~/.claude/skills/seo-cycle/config/project.template.yaml seo-cycle.yaml
#   then edit: project.name/domain, locale, region_profile, project_type, cms, business_profile, images.*.
#   For Russia: region_profile: ru.

# Alternative: the interactive wizard asks for base fields + image workflow
# (governance profile, paid API/LLM budget, automation mode,
# featured/inline ratios, WebP width/quality, source policy, captions, lazy policy)
# and creates AGENTS.md + policy templates for NeuronWriter/Google NLP/data access/budgets/automations.
~/.claude/skills/seo-cycle/scripts/init-project.sh

# Step 4. .env (ask the human only for key values)
test -f .env || cp ~/.claude/skills/seo-cycle/.env.example .env

# Step 5. Validate
python3 ~/.claude/skills/seo-cycle/scripts/validate-config.py
python3 ~/.claude/skills/seo-cycle/scripts/resolve-sources.py

# Step 6. Choose runtime
#   Claude Code: read ~/.claude/skills/seo-cycle/SKILL.md
#   Codex CLI:   export SEO_RUNTIME=codex; read AGENTS.md + docs/codex-runtime.md
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
ln -sf ~/.claude/skills/seo-cycle/AGENTS.md ./AGENTS.md
export SEO_RUNTIME=codex
codex exec -c model_reasoning_effort="xhigh" -c web_search="live" \
  "Read AGENTS.md and seo-cycle.yaml. Run Phase 2 for cluster X."
```
Full mapping — [docs/codex-runtime.md](docs/codex-runtime.md).

---

## <a id="en-modularity"></a>6b. Modular architecture (phase skills + state)

`seo-cycle` is a **dispatcher**. Phases are gradually extracted into standalone **phase skills** (each a `SKILL.md` + README folder — invokable independently, shareable, sellable separately). Coordination is via a single state file `seo/cycles/<topic>/_state.json` (the `cycle-state.py` contract). This is the "handoff chain": a phase skill reads state → does its job → updates state → unblocks the next phase.

**Extracted (pilot):** `seo-keywords` (Phase 2-3). **Status: splitting is frozen** (decision 2026-05-30) — the monolithic `seo-cycle` is primary; remaining phases are not extracted without a clear need (selling modules / a team / reuse / parallelism).

```bash
python3 ~/.claude/skills/seo-cycle/scripts/cycle-state.py init --topic "mineral wool"
python3 ~/.claude/skills/seo-cycle/scripts/cycle-state.py next      # unblocked phases
# → invoke the matching phase skill (seo-keywords, etc.)
python3 ~/.claude/skills/seo-cycle/scripts/cycle-state.py gate keywords
python3 ~/.claude/skills/seo-cycle/scripts/cycle-state.py show      # progress
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
- `seo/automation-policy.yaml` — scheduled automations, approval gates, forbidden actions.
- `seo/project-intake.yaml` — detailed map of countries, regions, search engines, ads, local/merchant/video/analytics decisions.

Rules:

- NeuronWriter is the primary SERP/NLP content editor for briefs, terms, entities, questions, competitor scores, and final scoring when `NEURON_API_KEY`, the helper, and a limits file are present.
- Google Cloud Natural Language is a guarded technical entity audit layer for entities, salience, syntax/category, and `title/H1/schema/text` mismatches. It is not a ranking submission mechanism or direct ranking signal.
- Whole-site NeuronWriter/Google NLP jobs are forbidden without an approved URL/keyword queue and enough remaining policy budget.
- Run `governance-report.py` before expensive collection or automation; if budget/approval does not allow it, do only report-only/cached/read-only steps.
- Low-token mode is mandatory: raw CSV/JSON/HTML to disk, only distillates/top-N in context; do not read the whole repository or raw source files without need.
- Robots/Content-Signal: `search=yes, ai-input=yes, ai-train=no` is acceptable as a model-training opt-out. Public `robots.txt` must be clean `text/plain`, with no PHP warnings/HTML or editor/preview noise.
- For Russian/RF projects, do not add foreign analytics/tracking tags or pixels without explicit policy approval. GSC, Bing Webmaster, PageSpeed/CrUX, sitemap/robots checks, and off-site API audits are acceptable because they do not install analytics code.
- Never print API keys, OAuth tokens, service-account JSON, or `.env` values; use variable names and paths only.

---

## <a id="en-tools"></a>7. Tools (what · command · output)

> All scripts live in `~/.claude/skills/seo-cycle/scripts/`. Run via `python3 <script>.py` or `bash <script>.sh`.

### 7.1 Source & config management
| Script | What | Command | Output |
|---|---|---|---|
| `validate-config.py` | Validates config, env, delegates, policy files, governance | `python3 validate-config.py` | Active sources, missing keys/policies, ✓/errors |
| `resolve-sources.py` | Expands `region_profile` + overrides into active sources | `python3 resolve-sources.py` | Active/skipped sources with reason + `active-sources.json` |
| `governance-report.py` | Shows token/budget/tool/automation policy without secrets | `python3 governance-report.py --format md` | Markdown/JSON report for Phase 0 and approval gates |
| `automation-plan.py` | Generates safe schedule plan, cron, and launchd templates | `python3 automation-plan.py --write --include-disabled` | `seo/automations/automation-plan.md`, `crontab.txt`, plist templates; install blocked without policy |
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

In Claude Code, work is delegated to subagents (`delegate.*` in config). Universal agents in `~/.claude/agents/`:

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
