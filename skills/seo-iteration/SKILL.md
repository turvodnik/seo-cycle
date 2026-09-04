---
name: seo-iteration
description: Итерации по данным (Phase 10): triggers-eval по декларативным правилам (push_to_top3, low CTR, каннибализация, decay), source attribution, KPI-контракт план-vs-факт. Используй когда просят «что улучшать по данным», «разбери снапшот», «почему просели» — отдельно или как стадию цикла.
---

# Iteration — actionable feedback engine

Модуль seo-cycle v2 · **Фазы: 10** · запуск **отдельно** или **стадией конвейера**.

## Контракт модуля

- **Входы:** свежий `09-monitoring/*-snapshot.json`, `config/triggers.yaml` (+ `<project>/seo-triggers.yaml` override)
- **Конвейер:** `_state.json` цикла (`scripts/cycle-state.py`) — предыдущая фаза `done`; **standalone:** state нет → `seo-cycle cycle init --topic "<тема>"`, работай по этому файлу, state обнови на выходе.
- **Выходы:** `10-iterations.md` — приоритизированный action list (P0/P1/P2, URL/запросы, делегаты)
- **Gate:** список отсортирован по потенциалу и дедуплицирован; KPI-статус посчитан при заполненной секции `kpi`
- **Делегаты:** по правилам триггеров: `content_strategist` / `content_writer` / `seo-auditor` и др.
- **Общие правила:** `../_shared/policy-intake.md` (политики/бюджеты проекта — прочитать до платных действий), `../_shared/scorecard.md` (самооценка после задачи), `../_shared/rag-usage.md` (переиспользуй накопленное).

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
seo-cycle triggers \
    09-monitoring/YYYY-MM-DD-snapshot.json \
    ./.codex/skills/seo-cycle/config/triggers.yaml \
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
seo-cycle attribution \
    --csv seo/source-attribution.csv \
    --snapshot 09-monitoring/<date>-snapshot.json
```
Скрипт покажет, какие источники дают ключи в топ-10, а какие — пустую породу, и пометит кандидатов на снижение приоритета/отключение. Малоэффективный источник → убери из `region_profile` override или `sources_disable`. **Это прямая экономия токенов/времени на следующих циклах.**

> Предусловие: в Phase 2 веди `seo/source-attribution.csv` — помечай, из какого источника пришёл каждый ключ (`keyword,source,date_added,cluster,target_url`).

**Выход:** `10-iterations.md` — приоритизированный action list со ссылками на конкретные URL/запросы + рекомендуемыми делегатами для каждого пункта.

**KPI-контракт («гарантированный результат»):** если в конфиге заполнена секция `kpi` — раз в месяц сверяй план с фактом и держи стратегию на цифрах:

```bash
seo-cycle forecast --write     # сценарии current/top10/top3, upside по кластерам, рампа
seo-cycle kpi --write --escalate   # план vs факт: on_track/at_risk/off_track; off_track → тикет + alert
seo-cycle sync --live --write  # зеркало сайта: что изменилось на сайте, drift против драфтов
```

Corrective actions при отставании берутся из forecast (кластеры с максимальным upside) + стандартные рычаги (quality loop, refresh, lost-keywords, ads analytics). Все допущения модели перечислены в отчёте `seo/strategy/seo-forecast.md` — это простая CTR-модель, не обещание.
