---
name: seo-audit
description: Аудит сайта в рамках seo-cycle (Phase 1): индексация, robots, CWV, schema, шаблонные следы, локальный аудит карт (Google/Яндекс/2ГИС), конкурентный анализ + ICE. Используй когда просят «сделай SEO-аудит сайта», «проверь индексацию/робots/скорость», «сравни с конкурентами на картах» — отдельно или как стадию полного цикла seo-cycle.
---

# Site Audit — аудит сайта

Модуль seo-cycle v2 · **Фазы: 1** · запуск **отдельно** или **стадией конвейера**.

## Контракт модуля

- **Входы:** `seo-cycle.yaml`; доступы по `seo/setup/access-key-assistant.md`
- **Конвейер:** `_state.json` цикла (`scripts/cycle-state.py`) — предыдущая фаза `done`; **standalone:** state нет → `seo-cycle cycle init --topic "<тема>"`, работай по этому файлу, state обнови на выходе.
- **Выходы:** `<cycles_root>/<topic>/01-audit.md` (+ `local/`, `competitor-analysis.md`)
- **Gate:** `seo-cycle cycle gate audit` — артефакт готов и непуст
- **Делегаты:** `delegate.audit` (default `seo-auditor`), `delegate.technical_audit`
- **Общие правила:** `../_shared/policy-intake.md` (политики/бюджеты проекта — прочитать до платных действий), `../_shared/scorecard.md` (самооценка после задачи), `../_shared/rag-usage.md` (переиспользуй накопленное).

---

## Phase 1 — Site Audit

**Цель:** понять текущее состояние сайта по выбранным поисковикам.

**Делегировать:** `delegate.audit` из config (по умолчанию `seo-auditor` агент).

Доп. техн. аудит (если включено): `delegate.technical_audit` (`claude-seo:seo-technical`).

**Что проверять (универсально):**
- Индексация (XML sitemap, robots.txt, canonical)
- Чистота `robots.txt`: без PHP warnings/HTML, без случайных Bricks preview/editor URLs, без плагиновых Content-Signal строк, противоречащих policy
- Шаблонные следы (демо-контент, пустые `href="#"`, lorem ipsum)
- Служебные страницы в индексе (cart, checkout, my-account для ecommerce)
- Скорость / Core Web Vitals
- Существующий контент: какие страницы есть, какие пустые
- Schema markup: что уже стоит

**Project-type-specific:**
- `ecommerce` → проверка карточек товара, категорий, фильтров
- `blog` → структура архивов, тегов, авторов
- `local_business` → LocalBusiness schema, NAP-консистентность
- `saas` → лендинги фич, документация, /pricing

**Локальный аудит (если есть `business_profile.gbp_url`/`yandex_business_url` или офлайн-точка):**
Сравнить с топ-3 конкурентами (`business_profile.competitors`) на **обеих** картах по чек-листу — это быстрые победы локального SEO:
- **Категории/рубрики** — что есть у конкурентов, но не у нас (Google Categories + рубрики Яндекс.Бизнес/2ГИС).
- **Отзывы** — число, оценка, скорость (план догона: `scripts/review-velocity.py`).
- **Публикации** — частота постов конкурентов (GBP Posts + Яндекс.Бизнес Новости).
- **Фото** — количество/типы/качество.
Тактики и промпты — `prompts/local/` (`google-maps.md` + `yandex-maps.md`), оба рантайма через браузер. Для РФ приоритет Яндекс.Карты + 2ГИС.

**Конкурентный анализ + ICE:** свести данные конкурентов (Serpstat/SpyFu/Keys.so/local/GSC) в приоритизированный список быстрых побед — метод `prompts/competitor-analysis.md` (7 шагов) + `scripts/ice-score.py` (Impact×Confidence×Ease). Топ quick-wins → в roadmap (Phase 3/5) и `keyword-queue`.

**Выход:** `01-audit.md` (+ `local/` подкаталог при локальном аудите, `competitor-analysis.md` при конкурентном) со списком проблем по приоритетам (P0/P1/P2 или ICE).

---
