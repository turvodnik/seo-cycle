# SEO Access Setup Runbook

Дата: __DATE__

Проект: __PROJECT_NAME__ (`__DOMAIN__`)

Секреты и токены не хранить в этом файле. Хранить их только в `.env`, системном keychain или password manager.

## Connected Accounts

| Сервис | Статус | Доступ | Заметки |
| --- | --- | --- | --- |
| Google Search Console | not_configured | service account/OAuth | Без установки тега аналитики |
| Yandex Webmaster | not_configured | OAuth | Для РФ-проектов приоритетный источник индексации |
| Bing Webmaster | not_configured | API key/OAuth | Полезно для Bing/Copilot |
| IndexNow | not_configured | key file/API key | Быстрая отправка изменённых URL |
| Google Merchant Center | not_configured | user/service account where supported | Только фиды/качество данных без платных кампаний |
| Yandex Merchant / Товары | not_configured | OAuth/cabinet | Фиды, ошибки товаров, категории |
| Google Ads | skipped_until_approved | manager/user OAuth | Не включать платные кампании без approval и бюджета |
| Яндекс Директ | skipped_until_approved | OAuth | Использовать семантику/отчёты, не запускать расходы без approval |
| Microsoft Ads | skipped_until_approved | OAuth | Пропускать, если требуется биллинг |
| Google Business Profile / Maps | not_configured | OAuth | Local SEO без analytics tag |
| Яндекс Бизнес / Карты | not_configured | OAuth/cabinet | Local SEO для РФ |
| Bing Places | not_configured | cabinet | Можно вести как агентство; API обычно только trusted partners |
| YouTube Data API | not_configured | OAuth/API key | Анализ видео и публикация только по approval |
| NeuronWriter | not_configured | API key | Лимиты фиксировать в `seo/neuronwriter-limits.yaml` |
| Google Cloud Natural Language | disabled | service account | Включать только после billing budget + local guard |
| Gemini API | optional | API key/service account | Только если нужен AI/NLP слой; расходы контролировать лимитами |
| OpenAI / Claude / Perplexity / DeepSeek | optional | API/browser/account | AI visibility evidence, entity prompts, fact-check support; не источник истины без проверки |

## Tracking Policy

- Для РФ-проектов не добавлять зарубежные analytics/tracking tags или pixels без явного разрешения владельца.
- Search Console, Bing Webmaster, PageSpeed/CrUX, sitemap/robots checks и off-site API audits допустимы без установки кода аналитики.
- Любой publish/change требует отдельного approval, если проект так настроен.

## Google Cloud Natural Language

- Использовать только для priority entity audit.
- Budget alert не является hard cap.
- Локальный hard guard и cache обязательны.
- Политика: `seo/entities/google-nlp-policy.yaml`.
- Стартовый guard: budget alert $5/month, cache 30 дней, только важные URL, RU sentiment/entity sentiment выключены.

## NeuronWriter

- Использовать как primary SERP/NLP content editor.
- Не запускать массовые `new-query` без очереди URL/keywords и проверки остатка.
- Политика лимитов: `seo/neuronwriter-limits.yaml`.

## AI Search Evidence

- Для каждого запроса хранить: platform, query, region, language, answer text, cited URLs, screenshot/source file, date.
- Проверять Google/Bing/Yandex/Perplexity/OpenAI/Claude/Gemini/DeepSeek только как visibility research.
- Ничего не "передавать в AI для ранжирования": используем schema, robots, sitemap, IndexNow, качество контента и публичные сущности.
