# Page Rewrite Rescue — для деиндексированных страниц

Используется в Step 10 Full deindex rescue workflow. После того как
`deindex-detect.py` нашёл «потерянные» страницы — этот промпт помогает
diagnostose причину и предложить план переписывания.

## Через что запускать

- **Perplexity Pro** — лучший вариант (есть search context для аналогичных кейсов)
- **Codex CLI** с web search — для look up best practices
- **Antigravity / Claude** — для прямого анализа контента

## Когда применять

- URL classified как `deindex` в deindex-detect output
- Страница возвращает 200, нет noindex, но Google её исключил
- **НЕ** применять для `http_4xx`, `http_5xx`, `noindex` — это другие проблемы (см. deindex-detect classification)

## Шаблон промпта

```
Я анализирую деиндексированную страницу — Google исключил её из выдачи
несмотря на то что она возвращает 200 OK и не имеет noindex.

**URL:** {{url}}
**Тематика сайта:** {{niche}}, {{region}}
**Текущее состояние:**
- Статус: 200 OK, индексируется robots, в sitemap
- Impressions за 90 дней: {{impressions_90d}} (если данные есть)
- Last published/updated: {{last_updated}}
- Word count: {{word_count}}
- Backlinks: {{backlinks_count}} (если данные есть)

**Контент страницы (фрагмент):**
```html
{{first_2000_chars_of_content}}
```

Помоги:

1. **Диагноз — почему Google мог исключить.** Оцени каждую гипотезу
   вероятностью (0-100%):
   - **Thin content** — мало уникальной информации
   - **Duplicate content** — дубликат другой страницы (на этом сайте или внешней)
   - **Low quality / AI-generated detected** — генерический текст, нет E-E-A-T
   - **Crawl budget** — Google не приоритизирует переобход (большой сайт, низкие сигналы)
   - **Soft 404 / тонкая страница без ценности** — Google расценил как пустую
   - **Cannibalization** — конкурирует с другой страницей того же сайта
   - **Old content** — устаревшая, не обновлялась годами
   - **Technical** — slow load, JS-rendering issues, mobile UX
   - **Other** — ...

2. **Самая вероятная причина** (1 шт) — с обоснованием 2-3 предложения.

3. **План переписывания (rewrite plan):**
   - **Сохранить:** что в текущей версии работает (URL, основной keyword, какие-то источники)
   - **Удалить:** что точно убрать (общие фразы, повторы, низкокачественные секции)
   - **Добавить:** новые секции, данные, источники, визуал
   - **Изменить структуру:** новый H1, новые H2, новый порядок
   - **Минимальный word count target:** {{target_word_count}}

4. **Уникальные сигналы качества** которые усилят E-E-A-T:
   - Конкретные данные/числа (с источниками)
   - First-hand experience (если применимо)
   - Уникальный визуал (диаграммы, фото)
   - Экспертные цитаты
   - Свежая дата (publication / last reviewed)

5. **Post-publish checklist** для re-indexing:
   - [ ] Внутренние ссылки на эту страницу с авторитетных страниц сайта
   - [ ] Request Indexing через GSC URL Inspection
   - [ ] IndexNow ping для Bing/Яндекса
   - [ ] Social signal (если есть аудитория)
   - [ ] Schema.org обновлён (lastReviewed дата)
   - [ ] Monitor через 14-28 дней — индексировалась ли

6. **Альтернатива переписыванию:**
   - Если страница безнадёжно низкого качества — **301 на лучшую** существующую (consolidation)
   - Если ниша больше не актуальна — **410 Gone** (явный сигнал Google)
   - НЕ оставляй "as is" — это будет повторно деиндексировано

**Формат ответа:** markdown, разделы 1-6 явно.
**Тон:** инженерный, конкретный, без воды.
```

## Плейсхолдеры

| Плейсхолдер | Источник |
|---|---|
| `{{url}}` | из deindex-detect output |
| `{{niche}}` | `industry.name` в seo-cycle.yaml |
| `{{region}}` | `locale.region` |
| `{{impressions_90d}}` | из snapshot.json по URL |
| `{{last_updated}}` | из frontmatter publish.md или CMS |
| `{{word_count}}` | подсчитать по контенту |
| `{{backlinks_count}}` | если есть backlinks data |
| `{{first_2000_chars_of_content}}` | curl + извлечение body |
| `{{target_word_count}}` | из NeuronWriter или industry benchmark |

## Output workflow

Сохрани ответ в `seo/research/deindex/<url-slug>-<date>.md`:

```markdown
---
url: <url>
diagnosed_date: YYYY-MM-DD
diagnosis_via: perplexity | codex | claude
primary_cause: <causality>
confidence: <0-100>%
rewrite_plan_status: pending_approval | approved | in_progress | published
---

# Diagnosis: <url>

[содержимое ответа LLM с 6 разделами]
```

Далее workflow в `seo-refresh-rescuer`:

1. Approval gate `deindex_rewrite` с этим diagnosis
2. После approve — делегировать в `seo-content-writer` с конкретным rewrite plan (из раздела 3)
3. Прогон QA gates (как обычно)
4. Publish обновлённой версии
5. Post-publish checklist (раздел 5) — выполнить руками или через GSC API

## Anti-patterns

- ❌ Переписывать без diagnosis — может оказаться что причина в дубликате или crawl budget, а не в контенте
- ❌ Косметический edit (поменять title, добавить параграф) — недостаточно для уже исключённого
- ❌ Слепо запросить Indexing — если причина в quality, переиндексация не поможет
- ❌ Молча оставить «as is» если нет ресурсов на rewrite — лучше 301 или 410

## Стратегия в долгосрочной перспективе

Если на сайте регулярно деиндексируются страницы (>5 в квартал) — это signal что:
- Content production process генерирует низкокачественный контент → пересмотреть `quality_gates`, NW target, E-E-A-T правила
- Cannibalization — нужна consolidation strategy
- Crawl budget issues — оптимизировать sitemap (только важные URL), убрать тонкие страницы

Это не индивидуальные fixes, а системные. Должно попадать в Phase 1 audit findings.

## Связанные файлы

- `scripts/deindex-detect.py` — обнаружение
- `seo-refresh-rescuer` agent — workflow обработки
- `seo-content-writer` agent — исполнитель rewrite
- `scripts/approval-gate.py` — approval ticket
- `docs/eeat-audit.md` — для усиления качества при rewrite
