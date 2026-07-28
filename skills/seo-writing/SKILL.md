---
name: seo-writing
description: Контент-план (hub-and-spoke, KPI-90d) и написание текстов под Entity Map (Phases 5–6): tone of voice, стоп-слова, AEO-абзац, stock-first, fact-check, изображения с alt/caption, NW evaluate, draft-quality-gate через loop. Используй когда просят «контент-план», «напиши статью по брифу» — отдельно или как стадию цикла.
---

# Content Plan + Writing — контент-план и тексты

Модуль seo-cycle v2 · **Фазы: 5–6** · запуск **отдельно** или **стадией конвейера**.

## Контракт модуля

- **Входы:** `04-entity-maps/*`, `page-outline-v3` брифы (`copywriter-ready/*.md`), RAG-контекст
- **Конвейер:** `_state.json` цикла (`scripts/cycle-state.py`) — предыдущая фаза `done`; **standalone:** state нет → `python3 scripts/cycle-state.py init --topic "<тема>"`, работай по этому файлу, state обнови на выходе.
- **Выходы:** `05-content-plan.md`; `06-drafts/*.publish.md` (+ `fact_check_log` frontmatter)
- **Gate:** `seo-cycle loop draft <draft.md> --outline <outline.json>` — exit 0; стоп-слова, fact-check, alt/caption — блокеры
- **Делегаты:** `delegate.content_strategy` (default `seo-content-strategist`), `delegate.content_writer` (default `seo-content-writer`)
- **Общие правила:** `../_shared/policy-intake.md` (политики/бюджеты проекта — прочитать до платных действий), `../_shared/scorecard.md` (самооценка после задачи), `../_shared/rag-usage.md` (переиспользуй накопленное).

---

## Phase 5 — Content Plan

**Цель:** roadmap публикаций с приоритетами.

**Делегировать:** `delegate.content_strategy` (по умолчанию `seo-content-strategist`).

**Структура плана:**
- Что: тип страницы (hub/spoke), URL, главный ключ
- Когда: дата, статус (TODO/Drafting/QA/Published)
- Зависимости: какие entity-maps готовы, какие источники собраны
- KPI: целевые impressions / clicks через 90 дней
- Bandwidth: блог N статей/неделю, категории M/месяц

**Выход:** `05-content-plan.md`.

---

## Phase 6 — Writing

**Цель:** написать тексты под Entity Map'ы.

**Делегировать:** `delegate.content_writer` (по умолчанию `seo-content-writer`).

**Перед написанием:** запроси накопленный контекст из локального RAG — `seo-cycle rag query "<primary keyword>" --top-k 5 --source-type source_pack --source-type distillate` (цитаты и факты из проверенных source packs; `--global` для пересечений с другими проектами). Брифы с подмешанными пассажами: `page-outline-v3.py --rag`.

**Универсальные правила (config-driven):**
- Tone of voice — из `tone.*` config
- Stop-words check — если `quality_gates.stop_words_check.enabled`
- AEO абзац в первые 400 символов — если `content_rules.aeo.enabled`
- Stock-first — если `content_rules.stock_first.enabled`
- Brand name discipline (user-facing vs technical) — `project.brand_name_*`
- Локальные сигналы ≥ `content_rules.local_signals.min_per_page`

**QA после написания (обязательная последовательность):**
1. **Stop-words check** (`scripts/check-stop-words.py`)
2. **Fact-check** — обязательно через Perplexity prompts (режим **Deep Research**) + Antigravity CLI cross-check для фактов, сущностей, интентов и спорных формулировок. Результаты записывай в `fact_check_log` frontmatter (claim/source/url/verdict/checked/tool). Если один из инструментов недоступен, не публикуй без записи blocker/exception в лог.
3. **Image visual + alt/caption check** — изображения создаются config-driven из `images.*`. Для фото-подготовки используй `scripts/wp-photo-image.py`: локальное фото/URL → crop по `images.aspect_ratios.*` → WebP по `images.output.*` → WordPress upload через SSH/WP-CLI при необходимости. Inline images должны быть чистыми тематическими фото/визуалами в `images.visual_style`. Не добавляй видимый текст на изображение, если `images.allow_visible_text=false` (SEO/AEO/GEO, схемы, подписи, описания товаров, дисклеймеры каталога) и не используй товарные карточки/коллажи как основной визуал, если пользователь явно не попросил. У каждого недекоративного изображения должен быть естественный `alt`; inline caption обязателен, если `images.captions.inline_required=true`: featured, inline, OG/schema, product/category visuals. Alt и caption описывают изображение и сущность, без переспама ключами и без служебных объяснений. Изображение без alt или inline image без обязательного caption = публикационный blocker.
4. **Stock-first проверка** (если ecommerce)
5. **NW evaluate** (если `sources.neuronwriter.enabled`) — target `quality_gates.neuronwriter_score.min_score`

**E-E-A-T trust-блок (если есть `fact_check_log`):** сгенерируй видимый блок «Источники» в конец статьи —
```bash
python3 ~/.codex/skills/seo-cycle/scripts/eeat-render.py 06-drafts/<name>.publish.md
```
Рендерятся только источники с verdict достоверно/частично; спорные — править формулировку в тексте, а не «подтверждать». Это прямой Trust-сигнал.

**После черновика:** валидация через автоцикл, не разовым гейтом: `seo-cycle loop draft <draft.md> --outline <page-outlines-v3/slug.json>` (exit 3 = переработай по instructions и `--resume`; лимит попыток не превышать).

Публикация только после прохождения всех гейтов.

**Выход:** `06-drafts/` — `*.publish.md`.
