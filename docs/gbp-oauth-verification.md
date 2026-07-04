# GBP OAuth verification: runbook для live-режима gbp-fetch

`gbp-fetch.py --live` требует OAuth-доступ к scope `business.manage`. Google
проверяет приложения с этим scope вручную — процесс проходит владелец
Google-аккаунта, автоматизировать его нельзя. Ниже — весь путь и что можно
сделать уже сегодня без verification.

## Что работает без verification (сегодня)

1. **Testing-режим OAuth-клиента.** До прохождения verification приложение в
   статусе «Testing» работает для до 100 явно добавленных test users. Для
   агентства этого обычно достаточно: добавьте свои менеджер-аккаунты GBP.
   Ограничение: refresh token в testing-режиме живёт 7 дней → раз в неделю
   перевыпускайте его через `gbp-oauth-helper.py` (одна минута).
2. **Браузерный workflow** (`prompts/local/google-maps.md` + Chrome MCP) и
   ручные выгрузки → `gbp-fetch.py --input-file` — без ключей вообще.

## Шаг 1. Google Cloud проект и OAuth-клиент

1. [console.cloud.google.com](https://console.cloud.google.com) → создать/выбрать проект.
2. APIs & Services → Library → включить:
   - **My Business Business Information API**
   - **My Business Account Management API**
   - (для отзывов) **Google My Business API** (v4, legacy)
3. APIs & Services → OAuth consent screen:
   - User type: **External**; заполнить название, support email, домен агентства.
   - Scopes: добавить `https://www.googleapis.com/auth/business.manage`.
   - Test users: добавить аккаунты, которыми управляете карточками.
4. Credentials → Create credentials → **OAuth client ID**:
   - Type: *Desktop app* (или *Web application* с redirect `http://localhost:8765`).
   - Скопируйте Client ID / Client Secret в `.env`:
     `GBP_OAUTH_CLIENT_ID=`, `GBP_OAUTH_CLIENT_SECRET=`.

## Шаг 2. Квота GBP API (отдельная заявка!)

По умолчанию квота **0 запросов** — её надо запросить независимо от OAuth:
[форма доступа к Business Profile APIs](https://developers.google.com/my-business/content/prereqs#request-access).
Указывайте реальный кейс агентства (read-only мониторинг отзывов и данных
локаций клиентов). Одобрение обычно 2–14 дней.

## Шаг 3. Refresh token (локально, одна команда)

```bash
set -a; . ./.env; set +a
python3 ~/.codex/skills/seo-cycle/scripts/gbp-oauth-helper.py            # локальный redirect
# или без локального сервера:
python3 ~/.codex/skills/seo-cycle/scripts/gbp-oauth-helper.py --print-url-only
```

Токен печатается один раз в stderr и никуда не сохраняется — внесите его в
`.env` как `GBP_OAUTH_REFRESH_TOKEN=`. Проверка:

```bash
python3 scripts/gbp-health.py            # status: available
python3 scripts/gbp-fetch.py --report locations --live --write
python3 scripts/gbp-fetch.py --report reviews --live --write
```

## Шаг 4. Verification (чтобы выйти из Testing)

APIs & Services → OAuth consent screen → **Publish app** → Google запросит:

- privacy policy на домене агентства (публичный URL);
- обоснование scope `business.manage` (текст: «агентство управляет карточками
  клиентов; приложение читает локации и отзывы для отчётности»);
- **видео-демонстрацию**: экран с consent screen → согласие → как приложение
  использует данные (покажите `gbp-fetch.py --report reviews --live` и отчёт);
- иногда — подтверждение владения доменом через Search Console.

Сроки: от нескольких дней до 4–6 недель. До одобрения продолжайте работать в
Testing-режиме (см. выше) — функционально это тот же live.

## Guardrails seo-cycle

- `gbp-fetch.py` — только чтение; ответы на отзывы и посты остаются за
  человеком (браузерный workflow с явным подтверждением).
- Секреты живут в `.env` проекта; helper ничего не пишет на диск.
- При недоступном API честный статус — `needs_oauth_verification`, и это
  не блокер цикла: offline-путь `--input-file` покрывает отчётность.
