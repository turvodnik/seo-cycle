---
name: seo-keywords
description: Сбор семантического ядра из всех активных источников региона и кластеризация с intent-типизацией (Phases 2–3). Используй когда просят «собери семантику», «семантическое ядро для X», «кластеризуй запросы» — отдельно или как стадию цикла. Вынесен в самостоятельный репозиторий seo-keywords; этот модуль — канонический контракт фаз.
---

# Keyword Research + Clustering — семантика и кластеры

Модуль seo-cycle v2 · **Фазы: 2–3** · запуск **отдельно** или **стадией конвейера**.

## Контракт модуля

- **Входы:** `seo-cycle.yaml` (`region_profile`, `sources.*`); `resolve-sources.py` — обязательный шаг 0
- **Конвейер:** `_state.json` цикла (`scripts/cycle-state.py`) — предыдущая фаза `done`; **standalone:** state нет → `python3 scripts/cycle-state.py init --topic "<тема>"`, работай по этому файлу, state обнови на выходе.
- **Выходы:** `02-keywords.md`, `03-clusters.md`, `seo/source-attribution.csv`, raw в `02a-*/02b-*`
- **Gate:** `python3 scripts/cycle-state.py gate keywords` / `gate clusters`
- **Делегаты:** `delegate.keyword_research` (default `seo-keyword-researcher`), `delegate.cluster_analysis`
- **Общие правила:** `../_shared/policy-intake.md` (политики/бюджеты проекта — прочитать до платных действий), `../_shared/scorecard.md` (самооценка после задачи), `../_shared/rag-usage.md` (переиспользуй накопленное).

---

> **Внешний скилл.** Полная реализация фаз 2–3 вынесена в репозиторий `seo-keywords` (устанавливается вместе с seo-cycle, поверхность `.claude|.codex/skills/seo-keywords`). Если внешний скилл подключён — работай по нему; текст ниже остаётся каноническим контрактом входов/выходов и правил экономии.
## Phase 2 — Keyword Research (Multi-source, config-driven)

**Цель:** собрать полное семантическое ядро под тему **из всех активных источников региона**.

**Шаг 0 — развернуть источники региона (обязательно, один раз):**
```bash
python3 ~/.codex/skills/seo-cycle/scripts/resolve-sources.py
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
| XMLRiver Yandex SERP/Wordstat | paid API | Только approval-gated enrichment: SERP blocks, колдунщики, коммерческие предложения, цены, подсказки, AI Overview; `scripts/xmlriver-source-pack.py` |
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
| XMLRiver Google SERP blocks | paid API | Approval-gated enrichment: organic, PAA/related, KG, ads, shopping, local/maps, news/video/discussions, AI Overview; `scripts/xmlriver-source-pack.py` |
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
| XMLRiver | paid API | Дешёвый SERP/Wordstat source pack; сначала экспорт/кэш, live только после approval |

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
