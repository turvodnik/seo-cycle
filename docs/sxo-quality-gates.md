# SXO Quality Gates

**Search Experience Optimization** — расширение `quality_gates` поверх стандартных stop-words / fact-check / NW score. SXO смотрит как контент **воспринимается пользователем** после клика из SERP.

Сигналы для Google и Яндекса с 2023-2024: dwell time, pogo-sticking back to SERP, scroll depth, intent satisfaction.

## Активация

```yaml
quality_gates:
  sxo:
    enabled: true
    cwv_thresholds:
      lcp_ms: 2500
      inp_ms: 200
      cls: 0.1
    readability:
      min_paragraph_count: 8
      max_paragraph_words: 80           # длинные параграфы убивают читаемость
      max_sentence_words: 25
    structure:
      require_toc_if_words_gt: 1500
      min_h2_per_1000_words: 2
      require_intro_under_words: 100
    interactive:
      require_faq: true                  # FAQ-блок обязателен
      require_jump_links: true           # для длинных статей
    mobile:
      no_horizontal_scroll: true
      tap_targets_min_size_px: 44
```

## Чеклист SXO для каждой страницы

### 1. Above-the-fold (первые 600px на mobile)

- [ ] H1 виден без скролла
- [ ] Lead-абзац (TL;DR / прямой ответ на запрос) — 2-3 предложения в первые 400 символов (AEO правило)
- [ ] Главный CTA — visible
- [ ] Hero-image не блокирует контент
- [ ] **Нет** auto-play видео / popup-ов / sticky banners сразу

### 2. Структура для скимминга

Большинство пользователей **скимят**, не читают. Контент должен «читаться по заголовкам».

- [ ] **H2 каждые 200-400 слов**
- [ ] **Bullet lists** где можно (вместо абзацев перечислений)
- [ ] **Таблицы** для сравнений / параметров
- [ ] **Bold ключевые фразы** (не злоупотреблять — 3-5 на 1000 слов)
- [ ] **Jump links / TOC** в начале для статей > 1500 слов
- [ ] **Промежуточные TL;DR** ("в этом разделе:") для длинных секций

### 3. Параграфы и предложения

- [ ] Параграф **3-5 предложений максимум**
- [ ] Предложения **до 25 слов** (большинство — до 15)
- [ ] Без passive voice где можно
- [ ] Активный голос, конкретные глаголы

### 4. Визуал и формат

- [ ] **Custom фото** (не stock) — повышает trust
- [ ] **Schema / diagrams** для технических концептов
- [ ] **Скриншоты с подписями** там где описывается процесс
- [ ] **Видео** (опц.) — embed YouTube/Vimeo, не auto-play
- [ ] **Image alt** — все картинки, описательные

### 5. Интерактивность

- [ ] **FAQ-блок** (FAQPage schema) — закрывает PAA сигналы
- [ ] **Калькуляторы / форма ввода** для расчётных тем (теплопотери, КПД, цены)
- [ ] **Comparison table** для сравнительных
- [ ] **Internal links** на related — 5-10 за статью
- [ ] **External links** на источники — 2-3 (для trust)

### 6. CTA и conversion

- [ ] **Главный CTA** — выделенный, виден at-least дважды (header + footer статьи)
- [ ] **Вторичный CTA** — soft, в середине статьи (newsletter / lead magnet)
- [ ] **Контактные данные** — телефон/email в шапке/футере
- [ ] **Доверие-блок** перед CTA (отзывы, цифры, гарантии)

### 7. Core Web Vitals (CWV thresholds)

| Метрика | Good | Needs Improvement | Poor |
|---|---|---|---|
| LCP | < 2.5s | 2.5-4s | > 4s |
| INP | < 200ms | 200-500ms | > 500ms |
| CLS | < 0.1 | 0.1-0.25 | > 0.25 |

Получаются через `psi-fetch.py` → `snapshot-build.py --source psi`. Triggers Phase 10:

```yaml
- id: cwv_blocks_publish
  when: "cwv.status == 'poor'"
  scope: cwv
  action: "Блокировать публикацию пока CWV не подтянется в зелёную зону"
  priority: P0
```

### 8. Mobile-first

- [ ] **Tap targets** не меньше 44×44px
- [ ] **Font ≥ 16px** body
- [ ] **Нет horizontal scroll** (test через DevTools mobile emulation)
- [ ] **Меню accessible** без сложных gestures
- [ ] **Sticky elements** не заслоняют контент на mobile

### 9. Pogo-sticking prevention

Pogo-sticking = пользователь возвращается на SERP в первые 30 секунд. Сигнал Google «не то».

- [ ] **Title/meta description** соответствуют контенту (no clickbait)
- [ ] **Intent match** — если запрос «купить» → коммерческий контент в первом экране, если «как сделать» → инструкция
- [ ] **Прямой ответ** в первых 100 словах
- [ ] **No paywalls** до ответа на основной запрос
- [ ] **No popups** в первые 5 секунд

## Phase 6 (writing QA) — порядок применения

```bash
# Стандартный QA + SXO gates:
1. python3 ~/.claude/skills/seo-cycle/scripts/check-stop-words.py draft.md   # tone of voice
2. # Fact-check через Perplexity (правило #11)
3. # Stock-first check (правило #10)
4. # Прогон через NW evaluate (target >= 65)
5. # SXO checklist (этот документ) — проходить руками или через subagent
```

### Subagent для SXO review

Можно делегировать в `claude-seo:seo-sxo` (если плагин установлен) — он смотрит готовый HTML и даёт report.

## Phase 10 — SXO-specific triggers

```yaml
- id: long_content_no_toc
  when: "page.word_count > 1500 AND page.has_toc == false"
  scope: pages
  action: "Добавить Table of Contents с jump links — критично для длинного контента"
  priority: P1
  delegate: content_writer

- id: paragraph_walls
  when: "page.avg_paragraph_words > 80"
  scope: pages
  action: "Стены текста — разбить на короткие абзацы, добавить bullets"
  priority: P1

- id: missing_faq_yet_paa_high
  when: "page.has_faq_schema == false AND page.paa_appearances > 3"
  scope: pages
  action: "Google показывает PAA по этой теме — добавь FAQ-блок с этими вопросами"
  priority: P0
  delegate: content_writer
```

## Anti-patterns

| Anti-pattern | Решение |
|---|---|
| 3000 слов сплошным текстом | Разбить на H2 каждые 200-400 слов + bullets |
| Auto-play видео в hero | Убрать или сделать opt-in (click to play) |
| Newsletter popup через 5 сек | Отложить до 30+ сек или exit intent |
| «Скачайте PDF чтобы прочитать» | Контент должен быть на странице |
| Sticky header на 30% высоты экрана | Уменьшить или убрать на mobile |
| 10-step «next page» pagination | Бесконечный scroll или single page |
| Image-as-text вместо HTML | Текст HTML, image — иллюстрация |

## Метрики мониторинга SXO

Из GA4 / Я.Метрика → `snapshot-build.py --source ga4/metrika`:

- **Bounce rate** (норма зависит от типа: info-страницы 50-70%, transactional 30-50%)
- **Avg engagement time** > 60 сек для info, > 120 сек для long-form
- **Scroll depth** (>50%) — для статей
- **Click-through to other pages** — health internal linking
- **Conversion rate** (для коммерческих)

## Связанные файлы

- `templates/entity-map.template.md` — секция 11 «Структура страницы» (от сущностей)
- `templates/monitoring-report.template.md` — секция «Behavior»
- `config/triggers.yaml` — SXO triggers
- `scripts/psi-fetch.py` — для CWV метрик
