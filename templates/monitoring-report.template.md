---
snapshot_date: {{YYYY-MM-DD}}
period_start: {{YYYY-MM-DD}}
period_end: {{YYYY-MM-DD}}
previous_snapshot: {{path/to/previous-snapshot.json | none}}
sources_collected: [gsc, ga4, metrika, webmaster, psi]
project: {{project_name}}
cycle: {{topic-quarter}}
tags: [monitoring, snapshot]
---

# Monitoring snapshot — {{snapshot_date}}

> Период: **{{period_start}} → {{period_end}}** ({{N}} дней)
> Источник истины: `09-monitoring/{{snapshot_date}}-snapshot.json`

## TL;DR (3-5 строк)

- Главное изменение в трафике / позициях / поведении (vs прошлый снапшот)
- Где появились возможности (новые impressions, поднявшиеся запросы)
- Где есть проблемы (упавшие позиции, плохой CWV, всплески bounce)
- Что делать в эту итерацию — ссылка на `10-iterations.md`

---

## 1. Google (GSC + GA4 + CrUX)

### 1.1. Топ-100 запросов (по impressions)

| # | Запрос | Impr | Clicks | CTR | Position | Δ impr | Δ pos | URL |
|---|---|---|---|---|---|---|---|---|
| 1 | ... | ... | ... | ... | ... | +/- | +/- | ... |

### 1.2. Топ-страниц (по clicks)

| # | URL | Impr | Clicks | CTR | Avg Position | Bounce | Avg Time |
|---|---|---|---|---|---|---|---|
| 1 | ... | ... | ... | ... | ... | ... | ... |

### 1.3. Core Web Vitals (CrUX/PSI)

| URL | LCP p75 | INP p75 | CLS p75 | Status |
|---|---|---|---|---|
| ... | ... | ... | ... | good/needs_improvement/poor |

---

## 2. Яндекс (Вебмастер + Метрика)

### 2.1. Топ-100 запросов (Вебмастер)

| # | Запрос | Показы | Клики | CTR | Позиция | Δ показы | Δ поз | URL |
|---|---|---|---|---|---|---|---|---|

### 2.2. Топ-страниц (Метрика)

| # | URL | Визиты | Отказы | Время | Глубина | Конверсии |
|---|---|---|---|---|---|---|

### 2.3. ИКС (если изменился)

- Текущий: {{N}}
- Прошлый снапшот: {{N}}
- Δ: {{+/-N}}

---

## 3. Поведение и конверсии (GA4 + Метрика)

| Метрика | Значение | Δ vs прошлый | Δ vs прошлый год |
|---|---|---|---|
| Сессии | ... | ... | ... |
| Bounce rate | ... | ... | ... |
| Avg engagement time | ... | ... | ... |
| Goal completions | ... | ... | ... |

---

## 4. Технические сигналы

| Сигнал | Источник | Статус |
|---|---|---|
| Sitemap submitted | GSC / Вебмастер | OK / Stale |
| Robots.txt errors | GSC | N |
| Indexed pages | GSC + Вебмастер | N google / M yandex |
| 404 / soft-404 | GSC | N |
| Crawl errors | GSC | N |
| Mobile usability | GSC | OK / Issues |

---

## 5. Дельты (vs прошлый снапшот)

### Растущие запросы (Δ impressions > +20%)

| Запрос | Δ impr | Текущая позиция | URL |
|---|---|---|---|

### Падающие запросы (Δ impressions < -20%)

| Запрос | Δ impr | Текущая позиция | URL | Причина (гипотеза) |
|---|---|---|---|---|

### Новые запросы (не было в прошлом снапшоте)

| Запрос | Impr | Position | URL |
|---|---|---|---|

### Сезонные сравнения (vs прошлый год, если данные есть)

- ...

---

## 6. Применённые триггеры Phase 10

См. `10-iterations.md` за {{snapshot_date}} — actionable список из `triggers-eval.py`.

Краткое резюме:
- P0: {{N}} срабатываний → {{N}} страниц к срочной правке
- P1: {{N}}
- P2: {{N}}

---

## Как сгенерирован этот отчёт

1. Собрано через делегаты: `claude-seo:seo-google` (GSC/GA4/CrUX) + `yandex-seo-specialist` (Вебмастер/Метрика)
2. Нормализовано в JSON через `scripts/snapshot-build.py --source <name>` → `09-monitoring/{{snapshot_date}}-snapshot.json`
3. Triggered правила через `scripts/triggers-eval.py snapshot.json triggers.yaml` → `10-iterations.md`
4. Этот markdown — человекочитаемая надстройка над snapshot.json
