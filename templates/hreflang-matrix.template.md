---
project: {{project_name}}
created: {{YYYY-MM-DD}}
default_locale: en-US
locales: [en-US, en-GB, de-DE, ru-RU]
tags: [hreflang, i18n]
---

# Hreflang Matrix — {{project_name}}

> Source of truth для всех multi-region URL mappings.
> Используется генератором hreflang тегов в CMS / sitemap.

## Локали и их характеристики

| Locale | URL префикс | Region (GSC) | Engine приоритет | x-default |
|---|---|---|---|---|
| en-US | /en-us/ | United States | Google | ✅ |
| en-GB | /en-gb/ | United Kingdom | Google | |
| de-DE | /de/ | Germany | Google | |
| ru-RU | / (root) | Russia | Yandex > Google | |

## Mapping таблица (page concept × locale)

| Page concept | en-US | en-GB | de-DE | ru-RU |
|---|---|---|---|---|
| Homepage | /en-us/ | /en-gb/ | /de/ | / |
| About | /en-us/about/ | /en-gb/about/ | /de/uber-uns/ | /o-nas/ |
| Pricing | /en-us/pricing/ | /en-gb/pricing/ | /de/preise/ | /tseny/ |
| Mineral wool category | /en-us/minwool/ | /en-gb/minwool/ | /de/mineralwolle/ | /minvata/ |
| Article: How to choose | /en-us/blog/how-to-choose/ | /en-gb/blog/how-to-choose/ | /de/blog/wie-waehlen/ | /blog/kak-vybrat/ |
| ... | ... | ... | ... | ... |

## Pages без перевода (locale-specific)

Локальные страницы которые есть только в одном регионе.

### Only en-US
- /en-us/blog/us-specific-article/

### Only de-DE
- /de/impressum/ (legal требование Германии)
- /de/agb/

### Only ru-RU
- /o-dostavke/ (специфика РФ)
- /rasprodazha/

## Validation

```bash
# Проверка: hreflang в каждой странице ссылается на все альтернативы (включая self)
# (TODO: scripts/hreflang-validate.py — в roadmap)

# Ручная проверка одной страницы:
curl -s https://example.com/en-us/minwool/ | grep -A1 'hreflang'

# Должно показывать минимум 5 строк:
# hreflang="en-us" href=".../en-us/minwool/"
# hreflang="en-gb" href=".../en-gb/minwool/"
# hreflang="de-de" href=".../de/mineralwolle/"
# hreflang="ru-ru" href=".../minvata/"
# hreflang="x-default" href=".../en-us/minwool/"
```

## Hreflang errors checklist (Phase 9 monitoring)

- [ ] GSC → International Targeting: Errors count = 0
- [ ] Каждая страница имеет минимум N+1 hreflang тегов (N локалей + x-default)
- [ ] Все ссылки взаимны (return tags)
- [ ] Lang codes lowercase для language part (`en-us`, не `en-US` — это для display, в hreflang lowercase)
- [ ] x-default указывает на default locale URL
- [ ] No 404 on hreflang target URLs

## Изменения

| Дата | Что изменилось | Кто |
|---|---|---|
| {{YYYY-MM-DD}} | Initial matrix | {{owner}} |
