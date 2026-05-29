# Migration Planner

Чеклист и workflow для миграции домена / CMS / структуры URL без потери SEO.

Активируется через `mode: migration` в `seo-cycle.yaml`. Расширяет Phase 0 (discovery) и Phase 1 (audit) специфическими шагами; Phase 9 включает 90-дневное окно повышенного мониторинга.

## Когда нужно

- Смена домена (`old.com` → `new.com`)
- Смена CMS (WordPress → Shopify, etc.)
- Реструктуризация URL (`/blog/article-name/` → `/articles/article-name/`)
- Объединение нескольких сайтов в один
- HTTPS миграция (если ещё не сделана)
- Изменение структуры категорий каталога

**НЕ нужно для:** косметических правок, переоформления страниц, обновления контента без изменения URL.

## Конфиг

```yaml
mode: migration

migration:
  enabled: true
  old_domain: "old-example.com"
  new_domain: "new-example.com"
  launch_date: "2026-08-01"
  redirects_file: "./redirects.csv"          # CSV: old_url,new_url,status_code
  monitoring_window_days: 90
```

## Pre-launch (T-30 → T-1)

### 1. Inventory — собрать ВСЕ старые URL

```bash
# Источники:
# - sitemap.xml старого сайта
# - GSC: Pages report → export all
# - Screaming Frog crawl (если есть)
# - Backlinks (ahrefs/semrush): получить все страницы с входящими ссылками
# - Server logs за 30 дней (топ-страницы по запросам ботов)

# Сохранить в:
echo "url,impressions_30d,clicks_30d,backlinks,priority" > inventory.csv
```

Минимум полей в inventory:
- URL (old)
- impressions/clicks за 30 дней (из GSC)
- кол-во входящих ссылок (из ahrefs/semrush)
- priority (высокий — если impressions > 100 ИЛИ backlinks > 0)

### 2. URL mapping — для каждой старой страницы новая

```csv
old_url,new_url,status_code,notes
https://old.com/blog/post-1/,https://new.com/articles/post-1/,301,article moved
https://old.com/products/sku-123/,https://new.com/p/sku-123/,301,
https://old.com/cat/old-category/,https://new.com/c/new-category/,301,category renamed
https://old.com/discontinued/,https://new.com/,410,gone (permanent)
```

Status codes:
- `301` — permanent redirect (большинство кейсов)
- `410` — Gone (page удалена навсегда, не редиректить на homepage)
- `404` — Not Found (только если случайно потеряна, не план)

**Запрет:** «301 всех на главную» — Google это видит как soft-404. Каждый редирект должен вести на **тематически релевантную** страницу.

### 3. Canonical strategy

Все новые страницы — с `<link rel="canonical" href="<full_url>">`. Если миграция включает мерж дубликатов:
- Выбрать canonical version (обычно — с большим числом backlinks или лучшим content score)
- Все дубликаты → canonical на выбранную + 301 redirect

### 4. Sitemap

Подготовить два sitemap:
- `sitemap.xml` — все НОВЫЕ URL
- `sitemap-old.xml` (опц.) — список старых URL для submit в GSC чтобы ускорить переобход редиректов

### 5. Robots.txt

- Старый домен: оставить `Sitemap: https://new.com/sitemap.xml` (показать Google куда переехал контент)
- Новый домен: стандартный robots.txt, не блокировать ничего критичного

### 6. Hreflang (если мультирегиональный)

Перепроверить хreflang теги — все альтернативные версии должны указывать на НОВЫЕ URL.

### 7. JS-rendering и assets

Если новый сайт SPA / SSG — убедиться:
- Robots могут рендерить контент (test через GSC URL Inspection live test)
- Static HTML генерируется (для SSR/SSG)
- Assets (images, CSS, JS) доступны с новых путей

### 8. Schema

Все JSON-LD на новых страницах:
- `url` — новый URL
- `sameAs` (для Organization) — внешние профили
- `BreadcrumbList` — обновлённые breadcrumb
- Прогон через `schema-validate.py`

## Launch day (T-0)

### 1. Включить редиректы

Server-level 301 (Apache .htaccess / Nginx config / CDN rules). НЕ JavaScript-редирект — Google не везде их учитывает корректно.

Файл `redirects.csv` импортируется в server config (формат зависит от CMS):

```nginx
# Nginx пример
location = /blog/post-1/ { return 301 https://new.com/articles/post-1/; }
location = /products/sku-123/ { return 301 https://new.com/p/sku-123/; }
```

### 2. Submit в GSC / Я.Вебмастер

- GSC: Settings → Change of address (для domain change)
- GSC: Sitemap submit для нового домена
- GSC: URL Inspection топ-10 страниц → Request indexing
- Я.Вебмастер: Настройки → Переезд сайта
- Я.Вебмастер: Sitemap submit + переобход топ-URL

### 3. Update внешних ссылок (по возможности)

Топ-10 источников backlinks с DR > 50 — outreach с просьбой обновить ссылки на новые URL. Не обязательно (301 работает), но улучшает immediate ranking signals.

### 4. Социальные профили

Все ссылки в bio Twitter/LinkedIn/Facebook/Instagram → новые URL.

## Post-launch monitoring (T+1 → T+90)

Включается автоматически если `monitoring.cadence` и `migration.monitoring_window_days` заданы. Phase 9 снимает снапшоты чаще (раз в 3-7 дней первый месяц).

### Чек-лист на каждом снапшоте

- [ ] **404 errors** в GSC: должны быть только намеренные (status_code=410)
- [ ] **Redirect chains** (cli: `curl -ILv <url>`): не более 1 hop, не должно быть 301→301→200
- [ ] **Impressions** на топ-старых URL: падают до 0 через 14-28 дней (после переобхода)
- [ ] **Impressions** на новых URL: растут, превышают старые к T+60
- [ ] **Positions**: временное падение на 10-20% в первые 2 недели — нормально. Если не восстановилось к T+45 — проблема
- [ ] **Crawl stats** в GSC: бот активно crawl-ит новые URL
- [ ] **Backlinks**: количество не должно резко упасть (проверяем через ahrefs/semrush еженедельно)
- [ ] **Branded queries**: должны вернуться к baseline к T+30

### Triggers (расширение `triggers.yaml` для migration mode)

```yaml
triggers:
  - id: migration_404_spike
    when: "page.status_code == 404 AND impressions > 10"
    scope: pages
    action: "Добавь редирект в redirects.csv для этого URL"
    priority: P0

  - id: migration_traffic_loss
    when: "delta_impr < -30 AND days_since_launch > 30"
    scope: queries
    action: "Падение >30% impressions через месяц после миграции — глубокий аудит"
    priority: P0
    delegate: technical_audit
```

## Rollback план (worst case)

Если через T+45 трафик не восстановился до 80% старого:

1. Проверь все 301 через `curl -I` — нет ли chains/loops
2. Сравни топ-10 запросов с прошлым годом — это сезонность или реально потеря?
3. Если потеря структурная — submit reconsideration request в GSC (если был manual action)
4. Крайний случай: откатиться на старый домен и переписать migration plan

## Lessons learned (заполняется по факту)

- ...

## Связанные файлы

- `redirects.csv` (проектный) — основная таблица редиректов
- `09-monitoring/` — снапшоты до и после launch (для сравнения)
- `triggers.yaml` (custom) — migration-specific правила
- `docs/oauth-setup.md` — для подключения GSC API во время мониторинга
