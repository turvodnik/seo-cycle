# Image SEO Strategy

Cross-cutting checklist для всех изображений: каталог, статьи, OG, иконки. Применяется в Phase 6 (writing) и Phase 7 (publishing).

## Что важно

Image SEO даёт:
1. **Image search traffic** (Google Images, Я.Картинки) — отдельный канал
2. **Page CWV** (LCP часто = hero image)
3. **AI visibility** — Bing/Google AI Overviews используют image alt
4. **Accessibility** (a11y) — alt для screen readers
5. **Social preview** (OG image) — CTR из соцсетей

## Naming convention

```
✗ ПЛОХО: IMG_1234.jpg, screen.png, photo.webp
✓ ХОРОШО: minvata-knauf-akustik-100mm-moskva.webp
```

Шаблон:
```
{category-slug}-{brand-slug}-{key-spec}-{location}.{ext}
```

Примеры:
- `epoksidnaya-zatirka-litokol-starlike-1kg-vanna.webp`
- `osp-3-15mm-kronospan-pol-stroitelnyy.webp`
- `mineralnaya-vata-tehnonikol-rokleyt-100mm-fasad.webp`

**Запреты:**
- Пробелы в именах файлов (используй `-`)
- Кириллица (escape будет уродливый)
- CamelCase (везде lowercase)
- Маркетинговые эпитеты («luchshiy», «premium»)

## Alt-text стандарт

| Контекст | Шаблон | Пример |
|---|---|---|
| Hero/cover | `{H1 page} — {brand if relevant}` | «Минеральная вата Knauf Akustik для звукоизоляции — Эмвуди» |
| Inline / иллюстрация процесса | Описание действия | «Монтаж минваты между стойками каркаса с шагом 600мм» |
| Product card thumbnail | `{product name} {key spec}` | «Knauf Akustik 100мм 1200×600мм» |
| Иконка категории | `{категория}` (короткое) | «Шумоизоляция» |
| Comparison diagram | Описание сравнения | «Сравнение слоёв пирога стены: с пароизоляцией и без» |
| Decoration / pattern | `alt=""` (пустое, аriahidden) | n/a |
| OG image | `{Page title} — {brand}` | «Как выбрать минеральную вату — гайд Эмвуди» |

**Запреты:**
- `alt="image"`, `alt="photo"`, `alt="picture"`
- alt = filename
- alt-spam: «купить минвату Москва дёшево цена доставка»
- Дублирование текста рядом с картинкой в alt

## Размеры и форматы

| Тип | Размер (px) | Формат | Max KB |
|---|---|---|---|
| Hero image (top of post) | 1200 × 675 | WebP | 100 |
| Inline article image | 800 × 533 | WebP | 60 |
| Product card | 600 × 600 | WebP | 50 |
| Category icon | 300 × 300 | WebP/SVG | 20 (WebP) / 5 (SVG) |
| Open Graph (social preview) | 1200 × 630 | WebP/JPG | 100 |
| Favicon | 32 × 32 | ICO/PNG | 5 |
| Logo | vector | SVG | 10 |

**Pipeline в seo-cycle:** существующий `seo/scripts/publish/img-generate.sh` + `img-optimize.sh` (если эти проектные скрипты есть — emwoody-стиль). Универсального генератора пока нет (на roadmap).

## CWV impact (LCP)

Hero image = первый paint в большинстве layouts. Оптимизация:

- [ ] **WebP** или AVIF (на 30-50% меньше JPEG)
- [ ] **Adaptive sizes** через `srcset`:
  ```html
  <img src="hero-800.webp" srcset="hero-400.webp 400w, hero-800.webp 800w, hero-1200.webp 1200w" sizes="(max-width:768px) 100vw, 1200px" alt="..." />
  ```
- [ ] **`width` + `height` атрибуты** обязательно (CLS prevention)
- [ ] **`loading="eager"`** для above-fold, **`loading="lazy"`** для below-fold
- [ ] **`fetchpriority="high"`** для hero
- [ ] **`<link rel="preload" as="image" href="hero.webp" fetchpriority="high">`** в `<head>`
- [ ] **CDN** для image delivery (Cloudflare Images, Bunny CDN, ImageKit)
- [ ] **No layout shift** — placeholder с правильным aspect ratio

## Structured data для изображений

```json
{
  "@context": "https://schema.org",
  "@type": "ImageObject",
  "contentUrl": "https://example.com/img/minvata-knauf.webp",
  "license": "https://example.com/license",
  "acquireLicensePage": "https://example.com/license-info",
  "creator": {"@type": "Organization", "name": "Эмвуди"},
  "creditText": "Эмвуди (emwoody.ru)",
  "copyrightNotice": "© Эмвуди 2026"
}
```

Особенно важно для:
- Product images → `Product.image`
- Article hero → `Article.image` (для News/Top Stories carousel)
- Recipe / HowTo step images

## Image sitemap (опц.)

Для больших каталогов (>1000 images) — отдельный sitemap:

```xml
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
  <url>
    <loc>https://example.com/minvata/</loc>
    <image:image>
      <image:loc>https://example.com/img/minvata-knauf.webp</image:loc>
      <image:title>Минеральная вата Knauf Akustik</image:title>
      <image:caption>Минвата для звукоизоляции 100мм</image:caption>
    </image:image>
  </url>
</urlset>
```

Submit отдельно в GSC.

## IndexNow для image discovery

Для Bing/Yandex — push новых картинок:
```bash
curl "https://api.indexnow.org/indexnow?url=https://example.com/img/new-image.webp&key=YOUR_KEY"
```

## Я.Картинки специфика

- **Файлы должны быть accessible** через прямой URL (не за auth)
- **Alt + title** атрибуты используются для ранжирования сильнее чем у Google
- **Окружающий текст** влияет на релевантность
- **Дубликаты detected** — не публикуй одну и ту же картинку на 100 страницах
- **Visual similarity** — Яндекс активно использует визуальные эмбеддинги, оригинальный визуал ранжируется выше

## AI image generation

Для seo-cycle проектов используется генерация (например emwoody — Codex CLI):

- [ ] **Brand palette consistency** (см. `images.brand_palette` в конфиге)
- [ ] **Aspect ratio** соответствует target (4:3 / 1:1 / 16:9 / 1.91:1)
- [ ] **Style guide** — фотореализм vs иллюстрация (одно на проект)
- [ ] **Не использовать stock-фото** — узнаваемо, снижает trust
- [ ] **Real photos** для product cards (если возможно)

## Phase 9 — мониторинг

Из GSC «Performance → Search type → Image»:
- Impressions / clicks из image search
- Top images по traffic

Из Я.Вебмастер → «Поисковые запросы» → фильтр по типу «Картинки».

## Anti-patterns

| Anti-pattern | Решение |
|---|---|
| 5MB PNG как hero | WebP < 100KB |
| `alt="image.jpg"` или нет alt | Описательный alt по шаблону выше |
| Одна картинка на 50 разных страницах | Уникальный визуал на каждую |
| Hero image без preload | `<link rel="preload">` + `fetchpriority="high"` |
| Stock-фото с улыбающейся командой | Реальные фото или skip |
| Огромные dimensions масштабированы CSS | Resize до actual displayed size |

## Связанные файлы

- `seo-cycle.yaml` секция `images` — palette, aspect ratios, output format
- Phase 8 schema — ImageObject в JSON-LD
- `docs/oauth-setup.md` — для IndexNow API key
