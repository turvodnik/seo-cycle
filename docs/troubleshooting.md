# Troubleshooting — seo-cycle

Типичные ошибки и решения по фазам.

## Конфиг и установка

### `seo-cycle.yaml не найден в <dir>`

Скилл искал в 4 локациях, нигде нет. Создай через wizard:
```bash
bash ~/.claude/skills/seo-cycle/scripts/init-project.sh
```
Или вручную скопируй template:
```bash
cp ~/.claude/skills/seo-cycle/config/project.template.yaml seo-cycle.yaml
```

### `validate-config.py показывает «delegate not found in ~/.claude/agents/ or ~/.claude/skills/»`

Не блокер — warning. Скилл/агент существует в plugin namespace (например `claude-seo:seo-google`) — валидатор не умеет проверять plugin skills через эвристику. Если плагин установлен через `/plugin install` — игнорируй.

### `PyYAML не установлен`

```bash
pip3 install pyyaml
```

## Observability hub (Phase 9)

### GSC: `403 PERMISSION_DENIED`

Service account email не добавлен в Search Console.

1. Открой Search Console → Settings → Users and permissions
2. Add user → email из `client_email` в твоём GOOGLE_APPLICATION_CREDENTIALS JSON
3. Permission: Full (или Restricted)

### GSC: `401 UNAUTHENTICATED`

`GOOGLE_APPLICATION_CREDENTIALS` указывает на несуществующий файл или ADC не настроен.

```bash
# Проверь:
ls -la "$GOOGLE_APPLICATION_CREDENTIALS"
cat "$GOOGLE_APPLICATION_CREDENTIALS" | python3 -m json.tool | head -5
# Если нет — установи через gcloud:
gcloud auth application-default login
```

### GSC: `400 Invalid argument: siteUrl`

Неправильный формат `GSC_SITE_URL`. Должно быть одно из:
- Domain property: `sc-domain:example.com` (без protocol, без слэша)
- URL prefix property: `https://example.com/` (со слэшем в конце)

### GA4: `403 PERMISSION_DENIED on properties/...`

Service account не добавлен в GA4 property:
- Admin → Property Access Management → Add users → email из service account JSON → role Viewer

### GA4: `Invalid Property ID`

`GA4_PROPERTY_ID` должен быть **числовым** ID (`123456789`), не Measurement ID (`G-XXXXXXXXXX`).

Найти: GA4 → Admin → Property Settings → Property ID.

### PSI: `429 Too Many Requests`

Без API key лимит ~25 req/день/IP. Решения:
1. Добавь `PSI_API_KEY` (см. `docs/oauth-setup.md` шаг 4) → лимит 25000/день
2. Уменьши batch размер (`--sleep 5` между URL)

### Яндекс.Метрика: `403 access_denied`

OAuth токен не имеет нужного scope. Пересоздай приложение в [oauth.yandex.ru](https://oauth.yandex.ru):
- ✅ Яндекс.Метрика: «Получение статистики, чтение параметров своих и доверенных счетчиков»

### Яндекс.Метрика: `401 invalid_token`

Токен истёк (~1 год жизни) или revoked. Получи новый через code flow:
```
https://oauth.yandex.ru/authorize?response_type=token&client_id=<твой_client_id>
```

### Яндекс.Вебмастер: `404 host not found`

`YANDEX_WEBMASTER_HOST_ID` неправильный формат. Должно быть: `https:example.com:443` (протокол, двоеточие, домен, двоеточие, порт).

Получить:
```bash
curl -H "Authorization: OAuth $YANDEX_OAUTH_TOKEN" \
  "https://api.webmaster.yandex.net/v4/user/$YANDEX_USER_ID/hosts/" | python3 -m json.tool
```

## Phase 10 — Triggers

### `triggers-eval.py: 0 правил сработало`

Возможные причины:
1. Snapshot пустой — проверь `snapshot.json` глазами (queries[]/pages[] не пустые?)
2. Условия слишком строгие — посмотри `~/.claude/skills/seo-cycle/config/triggers.yaml` и подстрой пороги под свой проект
3. Поля в snapshot не совпадают с условиями — DSL ожидает `position`, `impressions` и т.д.; убедись что snapshot-build нормализовал правильно

### `triggers-eval.py: ImportError yaml`

```bash
pip3 install pyyaml
```

## Phase 7 — Publishing

### WP REST: `401 incorrect_password`

`WP_APP_PASSWORD` — это **Application Password** (Users → Edit user → Application Passwords), не пароль от админки. Формат: `xxxx xxxx xxxx xxxx` (с пробелами).

### WP REST: `404 на /wp-json/wp/v2/<custom_post_type>`

CPT не зарегистрирован для REST API. В коде темы/плагина:
```php
register_post_type('blog', [
    'show_in_rest' => true,   // ← обязательно
    'rest_base' => 'blog',
]);
```

### SEOPress meta не сохраняется на term (категории/бренды)

Нужен PHP snippet который регистрирует SEOPress meta как `show_in_rest=true` для term. См. emwoody-проект: `seo/wp-snippets/seopress-term-meta-rest.php`.

## NeuronWriter

### `nw-cli get: timeout`

NW обрабатывает запрос дольше обычного. Запусти повторно — `get` polls 30 раз по 5 сек (≈2.5 мин). Если регулярно — open NW dashboard и проверь статус query вручную.

### `nw-cli evaluate: content_score слишком низкий (50-65)`

См. правило из emwoody pilot: NW требует **полный HTML** с `<title>` + `<meta description>`. Если шлёшь body-only — score падает на 15-20 пунктов.

Решение: оберни body в полный HTML или используй `wrap-html.py` (если есть в проектном скилле).

## Obsidian vault

### `obsidian-sync.py: 0 сущностей загружено`

`entities.yaml` имеет нестандартный формат или нет вообще. Проверь:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/validate-entities.py seo/entities/entities.yaml
```

### `obsidian-sync: -rebuild стирает корневой vault`

Safety check. Скрипт не удаляет директорию которая содержит `.obsidian/`. Для централизованного vault — используй `central_vault + project_subfolder` в конфиге; скрипт стирает только subfolder, не корень.

### Wiki-links не появляются в скопированных файлах

Проверь:
- `obsidian.generate_links: true` в seo-cycle.yaml
- Длина имени сущности > 3 символов (короткие пропускаются — много шума)
- Сущность есть в `entities.yaml` или `stock-inventory.yaml` (только зарегистрированные обрабатываются)

## LLM CLI

### `agy не установлен / codex не установлен`

```bash
# Antigravity (Google AI)
# Установка через antigravity.google.dev

# Codex (OpenAI)
# Установка через OpenAI CLI portal
```

Скрипт `llm-cli-collect.sh` graceful: пропускает отсутствующую CLI, продолжает с одной (если хоть одна есть).

## Общие

### Скилл `seo-cycle` не подхватился после установки

Перезапусти Claude Code сессию — skills загружаются при старте.

### Permission denied при запуске скрипта

```bash
chmod +x ~/.claude/skills/seo-cycle/scripts/<name>.{py,sh}
```

### `import: command not found` при запуске Python скрипта

Bash trying to execute Python file as shell. Используй явно:
```bash
python3 ~/.claude/skills/seo-cycle/scripts/<name>.py
```
Или убедись что shebang `#!/usr/bin/env python3` есть в первой строке файла.
