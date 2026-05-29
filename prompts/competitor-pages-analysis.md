# Competitor Pages Analysis — промпт для Phase 1 / Phase 4

Глубокий анализ топ-10 SERP конкурентов по целевому запросу. Используется в:
- **Phase 1** — baseline competitor landscape
- **Phase 4** — Entity Map раздел 7 «Конкуренты»
- **Phase 10** — refresh: что новое появилось у конкурентов с прошлого снапшота

## Через что запускать

- **Perplexity Pro** (Pro Search) — лучший для SERP-анализа с источниками
- **Codex CLI** с web search — fallback
- **NeuronWriter competitors** (если есть NW project) — уже даёт топ-10 SERP с метриками

## Шаблон промпта (RU)

```
Я готовлю SEO-стратегию для страницы про '{{topic}}' на сайте {{domain}}.
Рынок: {{region}}, целевой поисковик: {{engine}} (Яндекс или Google).
Главный ключ: '{{main_keyword}}'.

Проанализируй ТОП-10 SERP по этому ключу и дай:

1. **Список ТОП-10 URL** с краткой характеристикой каждого:
   - URL
   - Тип страницы (категория / товар / статья / лендинг / агрегатор)
   - Тип сайта (производитель / интернет-магазин / медиа / справочник / каталог)
   - Бренд / автор
   - Approx age страницы (если можно определить по дате)

2. **Структура контента** топ-3 страниц:
   - H1 формулировка
   - H2-заголовки (полный список)
   - Word count (приблизительно)
   - Формат: текст / таблицы / списки / калькуляторы / видео / диаграммы
   - Наличие FAQ-блока

3. **Сущности и термины** которые есть у топ-3, но у нас нет:
   - Бренды/линейки которые они упоминают
   - Нормативы/ГОСТы которые они цитируют
   - Технические параметры с числами

4. **PAA / People Also Ask** блок Google (или «Также спрашивают» Яндекса) по запросу:
   - 10-15 вопросов с краткими ответами

5. **SERP features** для этого запроса:
   - Featured Snippet (есть? какой формат: список / таблица / абзац?)
   - Knowledge Panel / Колдунщик Яндекса
   - Image Pack
   - Video Pack
   - Local Pack (если локальный intent)
   - Related searches внизу страницы

6. **Gap analysis** — что есть у конкурентов и нет у нас:
   - Темы / разделы которые они покрывают
   - Уникальные углы / форматы
   - Интерактивные элементы (калькуляторы, конфигураторы)

7. **Weaknesses конкурентов** — что они делают плохо:
   - Слабые тексты (тонкий контент, нет источников, нет автора)
   - Отсутствие визуала
   - Старые даты публикации
   - Битые ссылки
   - Bad UX (popup-ы, paywalls)

8. **Рекомендации для нашей страницы** на основе анализа:
   - Какую структуру использовать
   - Какие сущности обязательно покрыть
   - Какие SERP features целить (Featured Snippet формат)
   - Минимальный word count
   - Уникальные углы которые сделают нас отличными

Источники — обязательно URL для каждого пункта. Без общих фраз — только конкретика
с цитатами из топа.
```

## Шаблон промпта (EN)

```
I'm preparing SEO strategy for '{{topic}}' page on {{domain}}.
Market: {{region}}, target engine: {{engine}}.
Main keyword: '{{main_keyword}}'.

Analyze TOP-10 SERP for this keyword and provide:

1. **TOP-10 URLs** with brief description each (URL, page type, site type, brand)
2. **Content structure** of top-3 (H1, H2 list, word count, format, FAQ?)
3. **Entities and terms** they have but we don't
4. **PAA block** questions (10-15 with brief answers)
5. **SERP features** (Featured Snippet format, Knowledge Panel, Image/Video Pack, Local Pack)
6. **Gap analysis** — what they cover, we don't
7. **Competitor weaknesses** — thin content, no sources, no author, bad UX
8. **Recommendations** for our page based on analysis

URLs for every point. No fluff — only specifics with citations from top.
```

## Плейсхолдеры

| Плейсхолдер | Источник |
|---|---|
| `{{topic}}` | задаётся при запуске |
| `{{domain}}` | `project.domain` |
| `{{region}}` | `locale.region` |
| `{{engine}}` | первый из `engines[]` |
| `{{main_keyword}}` | из кластера Phase 3 |

## Output workflow

1. Сохрани ответ в `seo/research/competitors/<keyword-slug>-<date>.md`
2. Выдели секции:
   - **Top-10 URLs** → в Entity Map раздел 7 (Конкуренты)
   - **Структура top-3** → используй как референс при написании Phase 6
   - **Gap analysis** → action items в content plan (Phase 5)
   - **Weaknesses** → возможности отстройки
   - **PAA вопросы** → FAQ-репитер целевой страницы

## Когда не нужно запускать

- Контент-план уже готов и работает > 6 месяцев
- Тема узкая и понятная — нет конкуренции в SERP
- Конкурент-анализ был сделан недавно (< 3 месяцев) — переиспользуй

## Cadence

- **На каждый новый кластер** — обязательно (Phase 4)
- **При просадке позиций** — refresh для топ-3 запросов
- **Раз в 6 месяцев** — для топовых страниц (Phase 10 monitoring)
