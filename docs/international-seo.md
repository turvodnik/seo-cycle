# International SEO

Стратегия для мульти-региональных и мульти-языковых проектов. Активируется когда в `engines[]` или подпроектах несколько локалей.

## Архитектура: 3 варианта

| Подход | Pros | Cons | Когда |
|---|---|---|---|
| **ccTLD** (`example.de`, `example.ru`) | Сильный геосигнал, доверие локальных пользователей | Дорого, отдельная авторитетность, raw start | Крупный международный бизнес |
| **Subdomain** (`de.example.com`, `ru.example.com`) | Гибкость, отдельные настройки | Слабее ccTLD, доверие частично с домена | Среднее |
| **Subdirectory** (`example.com/de/`, `example.com/ru/`) | Сохраняет всю авторитетность домена, проще админить | Слабее геосигнал, сложнее multi-region targeting | Большинство SaaS / медиа |

**Рекомендация для seo-cycle проектов:**
- Один регион (РФ) → root domain без префикса
- Несколько регионов, ограниченный бюджет → subdirectory
- Несколько регионов, большой бизнес → ccTLD per страна

## Конфиг для мульти-региона

Один `seo-cycle.yaml` в корне проекта **+** отдельные конфиги в подпапках:

```
project/
├── seo-cycle.yaml              # дефолт (или main region)
├── ru/
│   └── seo-cycle.yaml          # РФ — Яндекс приоритет
├── en-us/
│   └── seo-cycle.yaml          # США — Google only
└── de/
    └── seo-cycle.yaml          # Германия — Google + локальные источники
```

Скилл подхватывает свой конфиг при запуске из подпапки.

## Hreflang strategy

Все мульти-региональные/мульти-языковые страницы должны иметь `<link rel="alternate" hreflang="...">` теги, указывающие на все альтернативные версии **включая саму себя** (self-reference).

### Матрица lang × region

См. `templates/hreflang-matrix.template.md` — шаблон таблицы для документирования всех версий.

Пример:

| Page concept | EN-US | EN-GB | DE-DE | RU-RU |
|---|---|---|---|---|
| /minwool/ | /en-us/minwool/ | /en-gb/minwool/ | /de/mineralwolle/ | /minvata/ |
| /about/ | /en-us/about/ | /en-gb/about/ | /de/uber-uns/ | /o-nas/ |

### Hreflang в HTML head

```html
<!-- На каждой странице /en-us/minwool/: -->
<link rel="alternate" hreflang="en-us" href="https://example.com/en-us/minwool/" />
<link rel="alternate" hreflang="en-gb" href="https://example.com/en-gb/minwool/" />
<link rel="alternate" hreflang="de-de" href="https://example.com/de/mineralwolle/" />
<link rel="alternate" hreflang="ru-ru" href="https://example.com/minvata/" />
<link rel="alternate" hreflang="x-default" href="https://example.com/en-us/minwool/" />
```

### x-default

Обязательный fallback для пользователей не из перечисленных locale. Обычно — английская US или главная (homepage).

### Hreflang в XML sitemap (альтернатива)

Для крупных сайтов вместо тегов в HTML — в sitemap:

```xml
<url>
  <loc>https://example.com/en-us/minwool/</loc>
  <xhtml:link rel="alternate" hreflang="en-us" href="https://example.com/en-us/minwool/"/>
  <xhtml:link rel="alternate" hreflang="de-de" href="https://example.com/de/mineralwolle/"/>
  <xhtml:link rel="alternate" hreflang="x-default" href="https://example.com/en-us/minwool/"/>
</url>
```

## Geo-targeting

- **GSC**: International Targeting → Country (только для subdirectory/subdomain, не для ccTLD)
- **Я.Вебмастер**: Региональность → выбрать регион (для подразделов)
- **Schema.org Organization**: `address.addressCountry` + `areaServed`

## Content localization (не translation!)

| Уровень | Что значит | Когда |
|---|---|---|
| **Translation** | Дословный перевод | Никогда не достаточно для SEO |
| **Localization** | Адаптация: единицы (км vs miles), валюты, дат форматы, культурные референсы | Стандарт |
| **Trans-creation** | Новый контент с теми же целями но локальный воркфлоу | Premium / brand-критичный |

Для seo-cycle — минимум **localization**:
- Цены в локальной валюте
- Единицы измерения (метры/футы, кг/lbs)
- Локальные нормативы (ГОСТ vs ASTM vs DIN vs ISO)
- Локальные бренды и примеры
- Phone format, address format
- Локальная лексика (UK vs US English, Hochdeutsch vs Schweiz, etc)

## Конкретные настройки по странам

### RU / RU-CIS
- Engines: yandex (priority 1), google (priority 2)
- Я.Вебмастер обязателен
- Locale ru-RU
- Нормативы: ГОСТ, СП, СНиП, СанПиН
- ATP не поддерживает регион — используй en/us шаблоны + перевод

### EN-US / EN-GB
- Google only
- Нормативы: ASTM (US), BSI (UK), FDA (US)
- ATP работает напрямую
- Distance: miles + km (тех. тематика)

### DE-DE / DE-AT / DE-CH
- Google + (Bing 5-10% доли)
- Нормативы: DIN, EN, ISO
- TÜV сертификации = trust signal
- Strict legal: Impressum обязателен по закону

### FR / ES / IT
- Google dominantes
- Локальные нормативы (NF, UNE, UNI)
- Локальные комплаенс-требования (CNIL France, etc)

## Hreflang errors monitor

Phase 9 / GSC показывает hreflang errors. Топ-3 проблемы:
1. **Missing return tags** — A ссылается на B через hreflang, B не ссылается на A
2. **Wrong language code** — `en` вместо `en-us` или `de-DE` (case matters)
3. **Self-referential broken** — страница не указывает на саму себя

## Anti-patterns

| Anti-pattern | Решение |
|---|---|
| Auto-redirect по IP геолокации | НЕТ — Google боты не туда попадают; используй language switcher + hreflang |
| Translate всех страниц одинаково | Только то, что reasonably рейтится в локали |
| Одинаковые meta_title для всех языков | Локализуй включая ключи |
| Hreflang только в HTML на маленькой части страниц | Полное покрытие через sitemap |

## Файлы

- `templates/hreflang-matrix.template.md` — матрица версий
- `seo-cycle.yaml` в каждой подпапке для свойственных настроек
- Phase 1 audit включает проверку hreflang errors из GSC
