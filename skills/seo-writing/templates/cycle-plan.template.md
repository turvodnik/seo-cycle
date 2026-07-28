---
cycle: {{topic-YYYY-Qx}}
project: {{project_name}}
created: {{YYYY-MM-DD}}
status: drafting | active | completed
owner: {{name}}
bandwidth_per_week:
  hub_pages: 1
  spoke_articles: 3
  category_updates: 5
target_kpi:
  impressions_3m: +30%
  clicks_3m: +20%
  ranked_keywords_3m: +50
tags: [content-plan]
---

# Content Plan — {{topic}}

> Roadmap публикаций под кластер `{{topic}}` на квартал {{Qx YYYY}}.
> Источники: `03-clusters.md`, `04-entity-maps/`, `02-keywords.md`.

## TL;DR

- Главная цель квартала: {{например — закрыть кластер «минвата» от hub до 8 spokes}}
- Ключевые риски: {{например — сезонный пик август-октябрь, успеть до}}
- Депенденции: {{например — Phase 4 Entity Maps для 5 страниц должны быть готовы}}

## Воронка контента (TOFU/MOFU/BOFU)

| Уровень | Тип страницы | Цель | Кол-во | Примеры |
|---|---|---|---|---|
| TOFU | spoke-статьи (информационные) | Brand awareness | 8 | "что такое минвата", "как выбрать" |
| MOFU | сравнительные статьи + категории | Consideration | 3 | "минвата vs XPS", категория /mineralnaya-vata/ |
| BOFU | карточки товара + категории + транз. лендинги | Conversion | 5 | подкатегории под бренды, /shop/, /cutting/ |

## Roadmap (приоритизация по impact × effort)

| # | URL / тип | Главный ключ | Кластер | Intent | Когда | Зависимости | KPI 90d | Effort | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | /minvata/ (hub) | минеральная вата купить москва | hub | commercial | 2026-Wk22 | entity-map ready | top-10 в Я+G, 500 impr/mo | M | TODO |
| 2 | /blog/kak-vybrat-minvatu/ (spoke) | как выбрать минеральную вату | spoke | info | 2026-Wk23 | NW terms готовы | top-30 в Я, 300 impr/mo | S | TODO |
| 3 | /blog/minvata-vs-xps/ (spoke compare) | минвата или xps | compare | info | 2026-Wk24 | fact-check done | top-20 в Я+G, 200 impr/mo | M | TODO |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

### Легенда status
- `TODO` — в очереди
- `Drafting` — пишется черновик
- `QA` — прошёл stop-words/fact-check/NW evaluate
- `Published` — выложен
- `Monitoring` — собирается фактическая статистика

### Легенда effort
- `S` (small): < 4 часа
- `M` (medium): 4-12 часов
- `L` (large): 12+ часов (обычно hub-страницы и pillar-статьи)

## Распределение по неделям (cadence)

| Неделя | Hub | Spokes | Categories | Refresh | Notes |
|---|---|---|---|---|---|
| Wk22 | 1 | 0 | 0 | 0 | запуск hub |
| Wk23 | 0 | 2 | 1 | 0 | первые spokes |
| Wk24 | 0 | 2 | 1 | 1 | продолжение + refresh hub |
| ... | ... | ... | ... | ... | ... |

## Зависимости и блокеры

| ID | Зависимость | Готовность | Owner |
|---|---|---|---|
| D1 | Entity Map для /minvata/ | ✅ done | ... |
| D2 | NW query_ids для всех spoke-статей | ⏳ in progress | ... |
| D3 | Fact-check база по нормативам (СП 50.13330) | ⏳ done | ... |
| D4 | Stock-inventory актуализирован | ✅ | ... |

## Reuse существующего контента

Что переиспользуем (Phase 4 → Phase 5):
- Entity Map для hub можно частично использовать в FAQ spoke-статей
- Stock-inventory брендов → primary feature во всех текстах кластера
- Fact-check log → расшаривается между статьями одного кластера

## Refresh-кандидаты (старые страницы под обновление)

| URL | Last published | Last fact-check | Триггер refresh | Effort |
|---|---|---|---|---|
| /old-page/ | 2025-08-15 | > 6 месяцев | trigger fact_check_stale | S |

## Distribution (после публикации)

- ✅ Sitemap pinged GSC + Вебмастер
- ✅ IndexNow для Bing/Яндекс
- ⏳ Внутренняя перелинковка с related страниц (мин. 5 ссылок)
- ⏳ Соцсети / рассылка (если есть каналы)
- ⏳ Backlink-стратегия для hub-страниц (см. `delegate.link_building`)
