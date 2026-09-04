---
name: seo-entity-map
description: Entity Map по методике Шестакова (Phase 4): сущности, тройки отношений, скрытые интенты, PAA, SERP-фичи, структура страницы, 17 разделов + evidence через Antigravity/Perplexity. Используй когда просят «сделай Entity Map / семантический бриф страницы» — отдельно или как стадию цикла. Для programmatic-режима — Phase 4P по `templates/programmatic-page.template.md`.
---

# Entity Map (методика Шестакова)

Модуль seo-cycle v2 · **Фазы: 4** · запуск **отдельно** или **стадией конвейера**.

## Контракт модуля

- **Входы:** `03-clusters.md` (кластер → страницы); RAG-подсказки (`_shared/rag-usage.md`)
- **Конвейер:** `_state.json` цикла (`scripts/cycle-state.py`) — предыдущая фаза `done`; **standalone:** state нет → `seo-cycle cycle init --topic "<тема>"`, работай по этому файлу, state обнови на выходе.
- **Выходы:** `04-entity-maps/<slug>.entity-map.md` на каждую страницу
- **Gate:** evidence cross-check (Antigravity + Perplexity) обязателен; `scripts/entity-graph-quality.py <package> --write`
- **Делегаты:** `delegate.semantic_brief` (проектный скилл, иначе `templates/entity-map.template.md`)
- **Общие правила:** `../_shared/policy-intake.md` (политики/бюджеты проекта — прочитать до платных действий), `../_shared/scorecard.md` (самооценка после задачи), `../_shared/rag-usage.md` (переиспользуй накопленное).

---

## Phase 4 — Entity Map (методика Шестакова)

**Цель:** для каждой страницы из кластера — Entity Map (entities → relations → intents → structure → keys).

**Делегировать:** `delegate.semantic_brief` (`emwoody-semantic-brief` если есть, иначе универсальный шаблон `templates/entity-map.template.md`).

**Обязательные evidence-источники:** перед фиксацией Entity Map сверяй сущности, интенты, PAA/FAQ и спорные утверждения через Antigravity CLI и Perplexity Deep Research. Сохраняй raw-ответы на диск, а в Entity Map добавляй только дистиллированные сущности с указанием источника. Без этой сверки карта не проходит quality-gate, кроме явно залогированного технического исключения.

**Сначала переиспользуй накопленное:** `seo-cycle rag query "<сущность>" --source-type triplet --source-type source_pack` — уже проверенные триплеты и цитаты этого проекта (с `--global` — соседних проектов агентства) дешевле нового ресёрча.

**Универсальная структура (17 разделов):**
1. Центральная сущность (AEO-цитата 2-3 предложения)
2. Атрибуты (таблица)
3. Связанные сущности (15-20)
4. Тройки отношений (≥12)
5. Явные интенты
6. Скрытые интенты (≥5 страхов/сомнений)
7. PAA вопросы (≥15)
8. Конкуренты (топ-10 SERP)
9. Граф сущностей (визуализация)
10. SERP-фичи (Featured Snippet, Колдунщик, AEO)
11. Структура страницы
12. FAQ (явные + скрытые)
13. Внутренние ссылки
14. Meta-теги (title/description)
15. JSON-LD plan
16. Чек-лист готовности
17. NW evaluate plan

**Frontmatter обязательно (extends по проектам):**
```yaml
target_url:
created:
status: pilot | active | archived
neuronwriter_query_id:
stock_skus: []                  # для ecommerce
fact_check_log: []              # если content_rules.fact_check.enabled
last_fact_check:
```

**Выход:** `04-entity-maps/<slug>.entity-map.md` для каждой страницы.
