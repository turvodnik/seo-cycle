# Универсальный промпт: семантическое ядро через LLM CLI

Phase 2 — расширение long-tail и сущностей через Antigravity / Codex / Perplexity. Этот шаблон уже встроен в `scripts/llm-cli-collect.sh`, но если запускаешь вручную / в другом инструменте — используй здесь.

## Шаблон (RU)

```
Собери семантическое ядро на {{language}} для темы '{{topic}}'.
Рынок: {{region}}.
Сегмент: {{segment}}.
Контекст бизнеса: {{business_context}}.

Дай:

1. **30 long-tail запросов**, разделённых на:
   - **Информационные** (15): «как», «какой», «что лучше», «сравнение», «расчёт»
   - **Коммерческие** (15): «купить», «цена», «доставка», «опт»
   - С привязкой к конкретным локациям где уместно ({{cities}}).

2. **15 связанных сущностей** с короткими (1-2 предложения) определениями:
   - **Бренды-производители** с конкретными линейками
   - **Нормативы** ({{normative_docs}}) — точные номера документов
   - **Альтернативные материалы/решения** — что используют в той же нише
   - Если есть live web search — обязательно URL-ы к нормативам и брендам.

3. **Классификация интента**: помечай каждый long-tail маркером [И] (info) или [К] (commercial).

4. **Конкретность важнее объёма**.

Формат: чистый markdown, два списка под заголовками '## Long-Tail запросы'
и '## Связанные сущности'.
```

## Шаблон (EN — для не-RU проектов)

```
Build a semantic keyword core in {{language}} for the topic '{{topic}}'.
Market: {{region}}.
Segment: {{segment}}.
Business context: {{business_context}}.

Provide:

1. **30 long-tail queries**, split into:
   - **Informational** (15): 'how', 'what is', 'which is better', 'comparison'
   - **Commercial** (15): 'buy', 'price', 'delivery', 'wholesale'
   - With local references where relevant ({{cities}}).

2. **15 related entities** with 1-2 sentence definitions:
   - **Brands** with specific product lines
   - **Standards / norms** ({{normative_docs}}) — exact document numbers
   - **Alternative materials / solutions**
   - If live web search available — include URLs for standards and brands.

3. **Intent classification**: mark each with [I] / [C].

4. **Specificity over volume**.

Format: clean markdown with '## Long-Tail Queries' and '## Related Entities'.
```

## Плейсхолдеры

| Плейсхолдер | Источник |
|---|---|
| `{{language}}` | `locale.language` |
| `{{topic}}` | задаётся при запуске |
| `{{region}}` | `locale.region` |
| `{{segment}}` | пользовательский ввод (B2C / B2B / both / consumer / enterprise) |
| `{{business_context}}` | `industry.primary_categories` |
| `{{cities}}` | по проекту — города из `locale.region` |
| `{{normative_docs}}` | по нише (см. fact-check.md) |

## Workflow с двумя CLI параллельно

Используй `scripts/llm-cli-collect.sh "<тема>"` — он:
1. Подставляет плейсхолдеры (читает из `seo-cycle.yaml` если есть)
2. Запускает agy + codex параллельно
3. Сохраняет результаты в `<research_root>/llm-cli/results/`
4. Печатает команду для merge

Затем `scripts/llm-cli-merge.py` дедуплицирует и помечает источники.
