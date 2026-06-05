# OAuth Setup — подключение аналитики и webmaster/API источников

Разовая настройка API-доступа к Google Search Console, PageSpeed Insights, Яндекс.Вебмастер/Метрика, Bing Webmaster/IndexNow и optional Google/Yandex/Microsoft сервисам для observability hub (Phase 9).

После настройки скрипты `gsc-fetch.py`, `ga4-fetch.py`, `psi-fetch.py`, `metrika-fetch.py`, `webmaster-fetch.py` будут вызывать API напрямую и выдавать JSON для `snapshot-build.py`.

Для РФ-проектов не ставь зарубежные analytics/tracking tags или pixels без явного разрешения в `seo/seo-data-collection-map.md`. GSC, Bing Webmaster, PageSpeed/CrUX, sitemap/robots checks, Google NLP audit и кабинеты без кода на сайте допустимы как off-site/read-only источники.

## TL;DR — что надо

1. **GCP project** + service account JSON ключ → `GOOGLE_APPLICATION_CREDENTIALS`
2. **Search Console**: добавить service account email как пользователя сайта
3. **GA4**: добавлять только если проект разрешает счетчик/аналитику; для РФ по умолчанию не ставим новый tag
4. **Яндекс OAuth токен** → `YANDEX_OAUTH_TOKEN`
5. **PSI** — без авторизации работает, опц. API key для повышенного rate limit
6. **Bing Webmaster API key** и **IndexNow key** — без установки analytics tag
7. Запустить `access-key-assistant.py --write`, чтобы увидеть только нужные этому проекту ключи
8. Скопировать `.env.example` → `.env`, заполнить, добавить в `.gitignore`

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
python3 ~/.codex/skills/seo-cycle/scripts/gsc-fetch.py --days 7 --row-limit 10 | head
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
python3 ~/.codex/skills/seo-cycle/scripts/ga4-fetch.py --days 7 --limit 10 | head
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
python3 ~/.codex/skills/seo-cycle/scripts/psi-fetch.py https://example.com --strategy mobile
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
python3 ~/.codex/skills/seo-cycle/scripts/metrika-fetch.py --days 7 --limit 5
python3 ~/.codex/skills/seo-cycle/scripts/webmaster-fetch.py --days 7 --limit 10
```

## 6. Google Cloud Natural Language

Используй только как guarded entity audit: сущности, salience, категории, syntax и moderation/sentiment только в рамках `seo/entities/google-nlp-policy.yaml`. Это не "передача сущностей в Google для ранжирования".

1. В GCP включить **Cloud Natural Language API** (`language.googleapis.com`).
2. Подключить billing и создать budget alert, обычно `$5/month`.
3. Включить локальные guards:
   ```bash
   GOOGLE_NLP_ENABLED=1
   GOOGLE_NLP_BILLING_APPROVED=1
   GOOGLE_NLP_CLOUD_BUDGET_USD=5
   GOOGLE_NLP_CACHE_DAYS=30
   GOOGLE_NLP_POLICY_FILE=seo/entities/google-nlp-policy.yaml
   ```
4. Запускать только важные URL и кэшировать результаты:
   ```bash
   python3 ~/.codex/skills/seo-cycle/scripts/google-nlp-audit.py --help
   ```

## 7. Google Merchant, Business Profile и YouTube

Эти сервисы подключаются только когда нужны проекту и не требуют установки аналитического кода:

- **Google Merchant Center**: добавить service account/user туда, где API поддержан аккаунтом; в `.env` указать `GOOGLE_MERCHANT_ACCOUNT_ID`.
- **Google Business Profile / Maps**: OAuth/user access; в `.env` указать `GOOGLE_BUSINESS_ACCOUNT_ID` и `GOOGLE_BUSINESS_LOCATION_ID`.
- **YouTube Data API**: включить в GCP, OAuth нужен для публикации/управления; API key обычно достаточно только для публичного чтения. В `.env`: `YOUTUBE_CHANNEL_ID`.

Платные кампании Google Ads не запускать без `governance.budget_policy.ads_spend_enabled=true`, бюджета и отдельного approval.

## 8. Bing / Microsoft

### 8.1. Bing Webmaster

1. Открыть [bing.com/webmasters](https://www.bing.com/webmasters/).
2. Добавить сайт или импортировать из GSC.
3. Получить API key в настройках Bing Webmaster.
4. В `.env`:
   ```bash
   BING_WEBMASTER_API_KEY=...
   BING_SITE_URL=https://example.com/
   ```

### 8.2. IndexNow

1. Сгенерировать ключ.
2. Разместить файл `<key>.txt` в корне сайта или через CMS/plugin.
3. В `.env`:
   ```bash
   INDEXNOW_KEY=...
   INDEXNOW_KEY_LOCATION=https://example.com/<indexnow-key>.txt
   ```

### 8.3. Bing Places и Microsoft Ads

- **Bing Places** обычно ведётся через кабинет; публичный API ограничен trusted partner program. Для агентства можно вести клиентские карточки в агентском кабинете, если регион/сервис принимает бизнес.
- **Microsoft Ads** пропускать, если требуется биллинг. Включать только для чтения/настройки после approval.

## 9. Яндекс дополнительные сервисы

В одном Яндекс OAuth приложении добавляй только нужные доступы:

- Яндекс.Вебмастер: индексация, диагностика, поисковые запросы.
- Яндекс.Метрика: только если проект разрешает счетчик/аналитику и счетчик уже легален для сайта.
- Яндекс.Товары / Merchant: фиды, ошибки товаров, категории; `.env`: `YANDEX_MERCHANT_BUSINESS_ID`.
- Яндекс.Директ: семантика/отчеты/настройки без расходов; `.env`: `YANDEX_DIRECT_CLIENT_LOGIN`.

Яндекс Алису пока не подключаем: для SEO нет прямого API, который "передаёт сайт в ранжирование Алисы". Возвращаемся к ней только если появится конкретный сценарий навыка/каталога/контента.

## 10. Полная таблица env vars

| Переменная | Источник | Тип | Обязательность |
|---|---|---|---|
| `SEO_RUNTIME` | runtime routing | enum | `codex`, `claude` или `auto` |
| `SEO_SEARCH_RUNTIME` | search/browser routing | enum | `direct`, `codex_external` или `auto` |
| `GOOGLE_APPLICATION_CREDENTIALS` | путь к service account JSON | path | для GSC/GA4 |
| `GSC_SITE_URL` | `sc-domain:example.com` или URL | string | для GSC |
| `GA4_PROPERTY_ID` | Property ID (числовой) | string | для GA4, если разрешено policy |
| `PSI_API_KEY` | PageSpeed API key | string | опц. (без — rate limit 25/день) |
| `GOOGLE_MERCHANT_ACCOUNT_ID` | Merchant account ID | string | опц. |
| `GOOGLE_BUSINESS_ACCOUNT_ID` | GBP account ID | string | опц. |
| `GOOGLE_BUSINESS_LOCATION_ID` | GBP location ID | string | опц. |
| `YOUTUBE_CHANNEL_ID` | YouTube channel ID | string | опц. |
| `GOOGLE_NLP_*` | NLP local guards/cache/budget | string | опц., billing-gated |
| `YANDEX_OAUTH_TOKEN` | OAuth токен Яндекса | string | для Метрики + Вебмастера |
| `YANDEX_METRIKA_COUNTER_ID` | Counter ID Метрики | string | для Метрики |
| `YANDEX_USER_ID` | Yandex user ID | string | для Вебмастера |
| `YANDEX_WEBMASTER_HOST_ID` | `https:example.com:443` | string | для Вебмастера |
| `YANDEX_MERCHANT_BUSINESS_ID` | ID бизнеса Яндекс.Товаров/Маркет | string | опц. |
| `YANDEX_DIRECT_CLIENT_LOGIN` | логин клиента Директа | string | опц., без расходов без approval |
| `BING_WEBMASTER_API_KEY` | Bing Webmaster API key | string | опц. |
| `BING_SITE_URL` | verified Bing site URL | string | опц. |
| `INDEXNOW_KEY` | IndexNow key | string | опц. |
| `INDEXNOW_KEY_LOCATION` | URL key-файла | string | опц. |
| `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` | Microsoft OAuth app | string | опц., если нужен Graph/Ads OAuth |
| `NEURON_API_KEY` | NeuronWriter | string | для NW evaluate/import |
| `NEURON_PROJECT_ID` | NeuronWriter project | string | опц., для ручной привязки проекта |
| `NEURON_LIMITS_FILE` | NeuronWriter лимиты | path | опц., default `seo/neuronwriter-limits.yaml` |
| `KEYSO_API_TOKEN` | Keys.so | string | опц., RU/Yandex keyword evidence |
| `SERPSTAT_API_KEY` | Serpstat | string | опц., quota-based keyword/competitor evidence |
| `TOKEN_ANSWERTHEPUBLIC` | ATP | string | опц. (только en/us) |
| `GEMINI_API_KEY` | Gemini API | string | опц., AI comparison layer |
| `DEEPSEEK_API_KEY` | DeepSeek API | string | опц., AI comparison layer |
| `WP_BASE_URL`, `WP_USER`, `WP_APP_PASSWORD` | WordPress REST | string | для WP publishing |
| `WOO_REST_API_KEY`, `WOO_REST_API_SECRET` | WooCommerce REST | string | для WooCommerce |
| `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` | DataForSEO | string | опц. (платная подписка) |

## 11. Paid/subscription tools

Эти сервисы подключай только если tool-stack ставит их в `enabled`/`report_only`/`approval_required`, а `spend-guard.py --write` не блокирует расход.

- **NeuronWriter**: открой account/API settings, скопируй API key только в `.env` как `NEURON_API_KEY`. Project ID и лимиты фиксируй в `seo/neuronwriter-limits.yaml`, не в отчётах.
- **Keys.so**: токен только в `.env` как `KEYSO_API_TOKEN`; до первого запуска задай request caps/reserve в `seo/tool-budget.yaml`.
- **Serpstat**: API key только в `.env` как `SERPSTAT_API_KEY`; перед запуском проверь credits через spend guard/usage ledger.
- **AnswerThePublic**: `TOKEN_ANSWERTHEPUBLIC` только если вопросная семантика действительно нужна и регион/язык поддерживается.
- **DataForSEO/SpyFu**: подключать отдельно по policy; без бюджета и approval не запускать.

## 12. AI API keys

AI API keys нужны только для сравнительных AI visibility/entity/content checks. Они не передают сайт напрямую в ранжирование.

- **Gemini**: создай key в [AI Studio](https://aistudio.google.com/app/apikey), по возможности ограничь ключ, сохрани только `GEMINI_API_KEY` в `.env`.
- **DeepSeek**: создай key в [DeepSeek Platform](https://platform.deepseek.com/api_keys), сохрани только `DEEPSEEK_API_KEY` в `.env`.
- **OpenAI/Claude/Perplexity**: подключай только если проектная policy разрешает LLM spend; ключи вводятся в `.env` или системный secret manager, не в setup reports.

Перед любым AI API запуском:
```bash
python3 ~/.codex/skills/seo-cycle/scripts/spend-guard.py --write
python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py check --service gemini --category llm --usd 0.25 --fail-on-block
```

## 13. Безопасность

- **`.env` в `.gitignore`** — никогда не коммить
- Service account JSON — `chmod 600`, не публиковать
- Yandex OAuth токен живёт ~1 год; обновлять по мере истечения
- В CI/CD — использовать secret manager (GitHub Secrets, GCP Secret Manager)
- Rate limits: GSC ~1200 запросов/мин, GA4 ~120 req/min/property, PSI без ключа — 25/день

## 14. Troubleshooting

См. `docs/troubleshooting.md` для типичных ошибок (`403 PERMISSION_DENIED`, `401 Unauthorized`, expired tokens).
