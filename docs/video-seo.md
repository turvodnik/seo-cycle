# Video SEO Strategy

Базовый checklist для видео-контента (если он есть у проекта). Минимальное покрытие — embed + schema + transcripts.

## Когда нужно

- **Обязательно**: каналы с собственным видео (tutorials, обзоры, демо)
- **Очень полезно**: e-commerce с product video, как-сделать статьи
- **Полезно**: B2B SaaS (демо фич), курсы, медиа
- **Skip**: чисто текстовые блоги / каталоги без видео-контента

## VideoObject schema (обязательно)

Если на странице есть `<video>` или embed (YouTube, Vimeo):

```json
{
  "@context": "https://schema.org",
  "@type": "VideoObject",
  "name": "Как выбрать минеральную вату",
  "description": "Детальный гайд по выбору минваты для каркасного дома: толщина, плотность, бренды.",
  "thumbnailUrl": [
    "https://example.com/video-thumb-16x9.jpg",
    "https://example.com/video-thumb-4x3.jpg",
    "https://example.com/video-thumb-1x1.jpg"
  ],
  "uploadDate": "2026-05-20T10:00:00+03:00",
  "duration": "PT8M30S",
  "contentUrl": "https://example.com/videos/how-to-choose-minwool.mp4",
  "embedUrl": "https://www.youtube.com/embed/VIDEO_ID",
  "publisher": {
    "@type": "Organization",
    "name": "Эмвуди",
    "logo": {"@type": "ImageObject", "url": "https://example.com/logo.png"}
  },
  "interactionStatistic": {
    "@type": "InteractionCounter",
    "interactionType": {"@type": "WatchAction"},
    "userInteractionCount": 1500
  }
}
```

**Обязательные поля:** `name`, `description`, `thumbnailUrl`, `uploadDate`.
**Рекомендуемые:** `duration` (ISO 8601 — `PT8M30S`), `contentUrl` ИЛИ `embedUrl`.

Несколько thumbnails (16:9, 4:3, 1:1) — для разных ratio в Image Pack.

Прогон через `schema-validate.py` — проверяет VideoObject обязательные поля.

## Transcripts (текстовая версия)

**Критично для SEO + accessibility:**
- Поисковик не индексирует аудио — только текст рядом с видео
- Транскрипт даёт seo «ключи» из live speech
- Соответствие WCAG (a11y)

Варианты:
1. **Inline на странице** (рекомендуется) — секция `## Транскрипт` после `<video>`
2. **Сворачиваемый блок** (`<details>` или JS accordion) — занимает меньше места
3. **Отдельная страница** `/video-name/transcript/` (хуже — fragmented authority)

Дополнительно: **YouTube auto-captions** + manual review (исправь auto-CC ошибки).

## Chapters / Timestamps

Структурированные временные метки помогают YouTube ранжированию + Google video результатам с timestamps:

```
00:00 Введение
00:45 Что такое минвата
02:10 Виды и плотности
04:30 Толщина для каркасного дома
06:50 Бренды на рынке РФ
08:15 Где купить и сколько стоит
```

Добавь в **description** видео на YouTube — Google автоматом подхватит как chapters.

Также в JSON-LD:
```json
"hasPart": [
  {"@type": "Clip", "name": "Что такое минвата", "startOffset": 45, "endOffset": 130, "url": "https://...?t=45"},
  {"@type": "Clip", "name": "Виды и плотности", "startOffset": 130, "endOffset": 270, "url": "https://...?t=130"}
]
```

## Thumbnails — кастомные обязательны

- YouTube auto-thumbnail = random frame, обычно blurry/bad
- Кастомный thumbnail повышает CTR на 30-50%
- Размеры: 1280×720 (16:9), PNG/JPG, < 2MB
- Включить: title overlay, контрастные цвета, человека/предмет (face attention)

## Hosting decision

| Хост | Pros | Cons |
|---|---|---|
| **YouTube** | Free, огромная аудитория, search dominance | Уход трафика, ads, ограниченный control |
| **Vimeo** | No ads, professional, custom player | Платный, меньше SEO |
| **Self-hosted (CDN)** | Полный control, нет ads, нет уходящего трафика | Bandwidth costs, сложнее CDN setup, нет встроенной SEO |
| **Wistia** | Marketing-focused, аналитика | Дорого |

**Рекомендация для SEO:**
- Primary: **YouTube** (для discovery + рекомендаций)
- Embed на свой сайт с `VideoObject` schema (получаешь оба бенефита)
- Если контент уникальный и важный — дублировать на self-hosted с canonical

## CWV для видео

- **Lazy-load videos** ниже fold: `loading="lazy"` (для `<iframe>` YouTube)
- **Facade pattern** для YouTube — показывать static thumbnail + click → загрузка iframe (экономит ~500KB загрузки)
- **No autoplay** (плохо для UX + блокируется браузерами)
- **Captions/subtitles** — для silent autoplay (если уж нужно)

## Video sitemap (для крупных проектов)

```xml
<url>
  <loc>https://example.com/blog/how-to-choose-minwool/</loc>
  <video:video>
    <video:thumbnail_loc>https://example.com/thumb.jpg</video:thumbnail_loc>
    <video:title>Как выбрать минеральную вату</video:title>
    <video:description>...</video:description>
    <video:content_loc>https://example.com/video.mp4</video:content_loc>
    <video:duration>510</video:duration>
    <video:publication_date>2026-05-20T10:00:00+03:00</video:publication_date>
  </video:video>
</url>
```

Submit в GSC отдельно.

## Я.Видео + Rutube + VK Видео

Для русскоязычной аудитории дублируй важное видео:
- **Я.Видео** — для появления в Я.Видео и Я.Картинках
- **Rutube** — российская аудитория
- **VK Видео** — социальный traffic

На своей странице — основной embed YouTube, дополнительно `sameAs` в schema:
```json
"sameAs": [
  "https://youtube.com/watch?v=...",
  "https://rutube.ru/video/...",
  "https://vk.com/video..."
]
```

## Anti-patterns

| Anti-pattern | Решение |
|---|---|
| Embed без VideoObject schema | Обязательно schema |
| Нет transcript | Inline transcript ниже видео |
| Auto-play sound on | Никогда (UX + adblock) |
| Random YouTube thumbnail | Custom thumbnail с контрастным title |
| Видео без chapters в длинных формах (>5 мин) | Chapters в description |
| Видео = единственный способ потребить информацию | Дублировать ключевые моменты в тексте |

## Phase 9 — мониторинг

- **GSC → Search type → Video**: impressions / clicks
- **YouTube Analytics**: source = External (сколько идёт с твоего сайта)
- **GA4**: события `video_start`, `video_progress`, `video_complete`

## Связанные файлы

- `scripts/schema-validate.py` — валидация VideoObject
- `docs/image-seo.md` — для thumbnails оптимизации
- `templates/entity-map.template.md` — секция 14 schema может включать VideoObject
