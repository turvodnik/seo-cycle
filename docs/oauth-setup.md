# OAuth Setup — подключение аналитики

Разовая настройка API-доступа к Google Search Console, Google Analytics 4, PageSpeed Insights и Яндекс.Метрика/Вебмастер для observability hub (Phase 9).

После настройки скрипты `gsc-fetch.py`, `ga4-fetch.py`, `psi-fetch.py`, `metrika-fetch.py`, `webmaster-fetch.py` будут вызывать API напрямую и выдавать JSON для `snapshot-build.py`.

## TL;DR — что надо

1. **GCP project** + service account JSON ключ → `GOOGLE_APPLICATION_CREDENTIALS`
2. **Search Console**: добавить service account email как пользователя сайта
3. **GA4**: добавить service account email как Viewer на property
4. **Яндекс OAuth токен** → `YANDEX_OAUTH_TOKEN`
5. **PSI** — без авторизации работает, опц. API key для повышенного rate limit
6. Скопировать `.env.example` → `.env`, заполнить, добавить в `.gitignore`

## 1. Google Cloud Platform setup (одноразово)

### 1.1. Создать project

1. Открой [console.cloud.google.com](https://console.cloud.google.com/)
2. Top bar → «Select project» → New project
3. Имя: `seo-cycle-<имя-проекта>` (например `seo-cycle-emwoody`)
4. Жми Create

### 1.2. Включить нужные API

В созданном project: `APIs & Services` → `Library` → найти и Enable:

- **Search Console API** (`searchconsole.googleapis.com`)
- **Google Analytics Data API** (`analyticsdata.googleapis.com`)
- **PageSpeed Insights API** (`pagespeedonline.googleapis.com`)
- (опц.) **Indexing API** — для пуша новых URL в индекс

### 1.3. Создать service account

`IAM & Admin` → `Service Accounts` → `Create service account`

- Name: `seo-cycle-fetcher`
- Permission: пропустить (доступ выдаём в самих сервисах)
- Done

В созданном service account: `Keys` → `Add key` → `Create new key` → **JSON** → скачать.

Файл `<project-id>-<hash>.json` положить в безопасное место, например:
```bash
mkdir -p ~/.config/seo-cycle
mv ~/Downloads/seo-cycle-fetcher-*.json ~/.config/seo-cycle/google-credentials.json
chmod 600 ~/.config/seo-cycle/google-credentials.json
```

### 1.4. Добавить в .env

```bash
GOOGLE_APPLICATION_CREDENTIALS=/Users/<you>/.config/seo-cycle/google-credentials.json
```

### 1.5. Запомнить email service account

Откройте JSON и найдите поле `"client_email"`. Запомните его — будем добавлять в GSC и GA4.

## 2. Search Console (GSC) доступ

1. Открыть [search.google.com/search-console](https://search.google.com/search-console)
2. Выбрать сайт → `Settings` → `Users and permissions` → `Add user`
3. Email: тот самый `client_email` из service account JSON
4. Permission: **Full** (можно Restricted, но Full проще)
5. В `.env`:
   ```bash
   GSC_SITE_URL=sc-domain:example.com
   # либо для URL prefix property:
   GSC_SITE_URL=https://example.com/
   ```

Проверка:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/gsc-fetch.py --days 7 --row-limit 10 | head
```

## 3. Google Analytics 4 (GA4) доступ

1. Открыть [analytics.google.com](https://analytics.google.com)
2. Admin → `Property settings` → `Property Access Management` → `+` → Add users
3. Email: `client_email` из service account
4. Roles: **Viewer**
5. Запомнить **Property ID** (Admin → Property Settings, числовой ID типа `123456789`)
6. В `.env`:
   ```bash
   GA4_PROPERTY_ID=123456789
   ```

Проверка:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/ga4-fetch.py --days 7 --limit 10 | head
```

## 4. PageSpeed Insights

PSI работает **без авторизации**, но с лимитом ~25 запросов/день/IP.

Опционально, для production:

1. В том же GCP project: `APIs & Services` → `Credentials` → `Create credentials` → `API key`
2. Ограничить ключ: API restrictions → PageSpeed Insights API
3. В `.env`:
   ```bash
   PSI_API_KEY=AIza...your_key_here
   ```

Проверка:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/psi-fetch.py https://example.com --strategy mobile
```

## 5. Яндекс OAuth (для Метрики и Вебмастера)

### 5.1. Создать приложение

1. [oauth.yandex.ru](https://oauth.yandex.ru/) → `Зарегистрировать новое приложение`
2. Платформы: `Веб-сервисы`
3. Redirect URI: `https://oauth.yandex.ru/verification_code` (для manual flow)
4. **Доступы:**
   - Яндекс.Метрика: `Получение статистики, чтение параметров своих и доверенных счетчиков`
   - Яндекс.Вебмастер: `Получение результатов индексирования сайта`
5. Сохранить

### 5.2. Получить OAuth токен (manual code flow)

В браузере открыть:
```
https://oauth.yandex.ru/authorize?response_type=token&client_id=<твой_client_id>
```

После авторизации получите URL вида:
```
https://oauth.yandex.ru/verification_code#access_token=y0_AgAA...&token_type=bearer&expires_in=...
```

Скопируйте `access_token`.

### 5.3. Получить counter ID и user_id

```bash
export TOKEN=y0_AgAA...your_token

# Метрика — список счётчиков
curl -s -H "Authorization: OAuth $TOKEN" \
  "https://api-metrika.yandex.net/management/v1/counters" | python3 -m json.tool | head -30

# Вебмастер — user_id
curl -s -H "Authorization: OAuth $TOKEN" \
  "https://api.webmaster.yandex.net/v4/user/" | python3 -m json.tool

# Вебмастер — список hosts (нужен user_id из шага выше)
curl -s -H "Authorization: OAuth $TOKEN" \
  "https://api.webmaster.yandex.net/v4/user/<USER_ID>/hosts/" | python3 -m json.tool
```

### 5.4. В .env

```bash
YANDEX_OAUTH_TOKEN=y0_AgAA...
YANDEX_METRIKA_COUNTER_ID=12345678
YANDEX_USER_ID=87654321
YANDEX_WEBMASTER_HOST_ID=https:example.com:443
```

Проверка:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/metrika-fetch.py --days 7 --limit 5
python3 ~/.claude/skills/seo-cycle/scripts/webmaster-fetch.py --days 7 --limit 10
```

## 6. Полная таблица env vars

| Переменная | Источник | Тип | Обязательность |
|---|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | путь к service account JSON | path | для GSC/GA4 |
| `GSC_SITE_URL` | `sc-domain:example.com` или URL | string | для GSC |
| `GA4_PROPERTY_ID` | Property ID (числовой) | string | для GA4 |
| `PSI_API_KEY` | PageSpeed API key | string | опц. (без — rate limit 25/день) |
| `YANDEX_OAUTH_TOKEN` | OAuth токен Яндекса | string | для Метрики + Вебмастера |
| `YANDEX_METRIKA_COUNTER_ID` | Counter ID Метрики | string | для Метрики |
| `YANDEX_USER_ID` | Yandex user ID | string | для Вебмастера |
| `YANDEX_WEBMASTER_HOST_ID` | `https:example.com:443` | string | для Вебмастера |
| `NEURON_API_KEY` | NeuronWriter | string | для NW evaluate/import |
| `TOKEN_ANSWERTHEPUBLIC` | ATP | string | опц. (только en/us) |
| `WP_BASE_URL`, `WP_USER`, `WP_APP_PASSWORD` | WordPress REST | string | для WP publishing |
| `WOO_REST_API_KEY`, `WOO_REST_API_SECRET` | WooCommerce REST | string | для WooCommerce |
| `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` | DataForSEO | string | опц. (платная подписка) |

## 7. Безопасность

- **`.env` в `.gitignore`** — никогда не коммить
- Service account JSON — `chmod 600`, не публиковать
- Yandex OAuth токен живёт ~1 год; обновлять по мере истечения
- В CI/CD — использовать secret manager (GitHub Secrets, GCP Secret Manager)
- Rate limits: GSC ~1200 запросов/мин, GA4 ~120 req/min/property, PSI без ключа — 25/день

## 8. Troubleshooting

См. `docs/troubleshooting.md` для типичных ошибок (`403 PERMISSION_DENIED`, `401 Unauthorized`, expired tokens).
