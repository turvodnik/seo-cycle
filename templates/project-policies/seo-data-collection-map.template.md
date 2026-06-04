# SEO / AI Data Collection Map

Дата: __DATE__

Проект: __PROJECT_NAME__ (`__DOMAIN__`)

Секреты и токены не хранить в этом файле.

## Search Indexing

| Источник | Что собирать | Как использовать |
| --- | --- | --- |
| Google Search Console | Индексация, исключения, запросы, страницы, CTR, позиции, sitemap, Core Web Vitals | Решать, какие страницы отправлять в индекс, какие закрывать, где менять title/description и контент |
| Яндекс.Вебмастер | Индекс, исключенные страницы, обход, ошибки robots/sitemap | Приоритизировать Яндекс: товары, категории, дубли, noindex, ошибки обхода |
| Bing Webmaster Tools | Индексация Bing, URL Inspection, ключевые слова, backlinks, crawl errors, sitemap | Закрыть Bing/Copilot и собирать бесплатные backlink/keyword-сигналы |
| IndexNow | Быстрая отправка измененных URL | Пушить новые/измененные товары, категории и важные статьи после публикации |

## Robots / AI Content Signals

| Правило | Default | Комментарий |
| --- | --- | --- |
| `Content-Signal: search` | `yes` | Разрешить использование контента для поиска |
| `Content-Signal: ai-input` | `yes` | Разрешить использование в AI-ответах/вводе |
| `Content-Signal: ai-train` | `no` | Не разрешать обучение моделей на контенте |
| Editor/preview URLs | block/noindex | Bricks preview, editor, cart/account/checkout/search/feed закрывать по типу URL |

`robots.txt` должен отдаваться чистым `text/plain`: без PHP warnings, `<br>`, HTML и дублей, которые ломают парсинг Google/Yandex/Bing.

## Merchant / Local / Ads Accounts

| Источник | Что собирать | Как использовать |
| --- | --- | --- |
| Google Merchant Center | Фиды, ошибки товаров, availability, GTIN/brand, price mismatch | Исправлять товарные данные; не запускать платные кампании без отдельного разрешения |
| Яндекс Товары / Merchant | Фиды, ошибки товаров, категории, доставка, цены | Для РФ e-commerce приоритетно чинить карточки и фид |
| Google Business Profile / Maps | NAP, категории, отзывы, локальные запросы | Локальное SEO без установки кода на сайт |
| Яндекс Бизнес / Карты | NAP, рубрики, отзывы, фото, локальная видимость | Основной local SEO слой для РФ |
| Bing Places | NAP, категории, фото, отзывы, локальная карточка | Для Bing/Copilot local signals; обычно через кабинет, API ограничен |
| Google Ads / Яндекс Директ / Microsoft Ads | Search terms, конверсии, объявления, минус-слова | Использовать как источник семантики и доказательств; платные кампании не включать без approval и бюджета |
| YouTube / Видео | Поисковые подсказки, канальные данные, видео-страницы, описания | Контентные идеи и entity evidence; публикация только по отдельному approval |

## Content And Entity Tools

| Источник | Что собирать | Как использовать |
| --- | --- | --- |
| NeuronWriter | SERP/NLP terms, entities, questions, competitor content score, content briefs | Основной редактор для подготовки и усиления текстов; лимиты в `seo/neuronwriter-limits.yaml` |
| Google Cloud Natural Language | Entities, salience, syntax, categories | Технический entity audit с кэшем/лимитами; не считать прямым ranking signal |
| Knowledge Graph / schema crawl | Organization/Product/LocalBusiness entities | Проверять, совпадают ли schema, H1/title и видимый текст |
| Gemini / OpenAI / Claude / Perplexity / DeepSeek | Ответы AI-поиска, цитаты, competitors cited, missing entity coverage | Собирать только evidence: запрос, регион, дата, ответ, цитируемые URL, next action |

## Behavior And Quality

Для российских проектов не ставим зарубежные аналитические теги/пиксели на сайт без отдельного разрешения владельца. Google Search Console, Bing Webmaster, PageSpeed/CrUX и API-аудиты без счетчика допустимы, потому что не требуют установки кода аналитики на сайт.

| Источник | Что собирать | Как использовать |
| --- | --- | --- |
| PageSpeed / CrUX / Lighthouse | LCP, INP, CLS, мобильная скорость, ресурсы | Исправлять техническое качество, влияющее на SEO и конверсию |
| Яндекс.Метрика | Визиты, цели, Вебвизор, карты кликов/скролла | Для РФ-проектов основной поведенческий источник, если установлен законно |
| GA4 / Clarity | Органический трафик, события, session replay | Для РФ-проектов не ставить тег без отдельного разрешения |

## AI Search Visibility

Минимальный формат записи:

```csv
date,platform,query,region,answer_present,domain_cited,cited_url,cited_competitors,next_action
```

Хранить доказательства: скриншот, текст ответа, список цитируемых URL, дату, регион и язык. Не считать ручной ответ AI источником факта без внешней проверки.
