---
name: seo-publishing
description: CMS-aware публикация (WordPress REST + App Password как основной канал; Tilda/static/custom) и JSON-LD schema по типу проекта с каноническим узлом Organization (Phases 7–8). Используй когда просят «опубликуй материал», «проставь schema/микроразметку» — отдельно или как стадию цикла.
---

# Publishing + Schema — публикация и JSON-LD

Модуль seo-cycle v2 · **Фазы: 7–8** · запуск **отдельно** или **стадией конвейера**.

## Контракт модуля

- **Входы:** `06-drafts/*.publish.md`, `publishing.*` из конфига, `business_profile`
- **Конвейер:** `_state.json` цикла (`scripts/cycle-state.py`) — предыдущая фаза `done`; **standalone:** state нет → `seo-cycle cycle init --topic "<тема>"`, работай по этому файлу, state обнови на выходе.
- **Выходы:** `07-published.md` (URL+дата), `08-schema.md`, лог в `artifacts.publish_log`
- **Gate:** verify GET+браузер после публикации; img без alt / inline без caption = блокер; фейковый AggregateRating запрещён
- **Делегаты:** `publishing.publish_skills` (проектные), `delegate.schema_markup` (default `claude-seo:seo-schema`)
- **Общие правила:** `../_shared/policy-intake.md` (политики/бюджеты проекта — прочитать до платных действий), `../_shared/scorecard.md` (самооценка после задачи), `../_shared/rag-usage.md` (переиспользуй накопленное).

---

## Phase 7 — Publishing (CMS-aware)

**Цель:** залить контент на сайт.

Делегирование зависит от `publishing.cms` и `publishing.publish_skills`:

| CMS | Скилл / подход |
|---|---|
| WordPress | REST API + Application Password как основной независимый канал; project-specific publish skills могут оборачивать REST; Novomira/WordPress MCP только если явно подключён для специальных abilities; SSH/WP-CLI fallback для backup/cache/meta/server repairs |
| Shopify | (TBD — Liquid + Storefront API) |
| Webflow | (TBD — CMS Collections API) |
| Next.js/static | git commit в content/ + redeploy |
| custom | по обстоятельствам |

**Универсальный шаги:**
1. Парсинг `publish.md`
2. Backup текущих значений
3. POST в CMS endpoint
4. Featured image / OG картинка (если `images.generator != none` или `images.workflow=photo_first`) через `scripts/wp-photo-image.py`/CMS media workflow + обязательный alt; inline images по `images.inline_min_per_post` и `images.aspect_ratios.article_inline` + обязательный короткий caption, если включён в `images.captions`
5. Schema/meta через SEO plugin endpoint
6. Verify через GET + браузер: публичный HTML не должен содержать недекоративные `<img>` без `alt`, inline images без caption и запрещённые тексты на/под изображениями. Если кеш/оптимизатор/lazy-load подменяет first-screen/above-the-fold inline image на плейсхолдер в браузере, исключи только это критичное inline image из lazy-load (`skip-lazy`/`data-no-lazy` или CMS-аналог) и перепроверь screenshot. Остальные inline images ниже первого экрана оставляй lazy-loaded.
7. Лог в `artifacts.publish_log`

**WordPress channel policy:** не завязывай публикацию только на MCP-сервер. Если `publishing.cms=wordpress`, REST API через Application Password — основной повторяемый путь для постов, страниц, товаров, media, meta и plugin REST endpoints. Novomira/WordPress MCP не включай автоматически; используй только как project-local fallback/extension, когда REST API недостаточно или нужны специальные abilities (например Bricks-структуры). SSH/WP-CLI оставляй для восстановления, purge cache, backup, незарегистрированных REST meta и серверных исправлений.

**Маркетинговый мостик (если `marketing.enabled`):** после публикации — поднять конверсию страницы через плагин `marketing-skills` (`page-cro` / `form-cro` / `popup-cro`). Каналы привлечения/удержания (`paid-ads`, `social-content`, `email-sequence`, `referral-program`) — **с РФ-адаптацией** (Яндекс.Директ / VK / Telegram / Метрика / 2ГИС вместо западных). Карта мостиков и замен каналов — `docs/marketing-bridges.md`.

**Выход:** `07-published.md` — URL + дата каждой публикации.

---

## Phase 8 — JSON-LD & Schema

**Цель:** структурированные данные под выбранные типы страниц.

**Делегировать:** `delegate.schema_markup` (по умолчанию `claude-seo:seo-schema`).

**Типы по `project_type`:**
- `ecommerce`: Product, Offer, AggregateRating (только реальные!), BreadcrumbList
- `local_business`: LocalBusiness + Service + AggregateRating
- `blog`: Article, FAQPage, HowTo, BreadcrumbList
- `saas`: SoftwareApplication, Product, Organization
- Везде: WebSite, Organization, FAQPage (где есть FAQ)

**E-E-A-T: канонический узел организации (обязательно).** Не оставляй `author`/`publisher` голым `{"@type":"Organization","name":...}`. Собери единый узел из `business_profile` и ссылайся на него через `@id`:
```bash
seo-cycle run script schema-org-build build              # посмотреть узел
seo-cycle run script schema-org-build inject schema/*.json  # вставить + переписать author/publisher на @id
```
Узел несёт trust-сигналы (address, telephone, openingHours, areaServed, knowsAbout, sameAs) — это то, что связывает контент с реальным бизнесом и усиливает Authoritativeness/Trust. Инжект идемпотентен. Требует секцию `business_profile` в конфиге.

**Запрет:** фейковые рейтинги и отзывы. Если нет реальных — не делай AggregateRating. `same_as` — только подтверждённые профили.

**Выход:** `08-schema.md`.
