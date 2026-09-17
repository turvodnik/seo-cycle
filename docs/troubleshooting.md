# Troubleshooting — seo-cycle

Типичные ошибки и решения по фазам.

## Оператору: шесть частых ситуаций

Раздел для тех, кто гоняет `seo-cycle` руками каждый день — не для разработчика
инструмента. Инженерные разделы ниже (Observability hub, Phase 10 Triggers,
NeuronWriter, LLM CLI) — для отладки самого кода; эти шесть — для рутины.

### 1. `pulse` вернул пустой срез

Симптом: `seo-cycle pulse` отработал без ошибки, но в конце — предупреждение
`нет ни одного среза позиций — конвейер пуст` (`snapshot-freshness` в
`seo-cycle doctor` тоже говорит «нет снапшотов мониторинга»).

Причина: `pulse` собирает позиции только из двух источников — Я.Вебмастер и
Google Search Console (GSC) — и включает в запрос лишь то, для чего движок
включён в `seo-cycle.yaml` (`engines:`, пустой/отсутствующий список —
ограничения нет) И источник настроен: для Вебмастера — токен
(`YANDEX_WEBMASTER_OAUTH_TOKEN`/`YANDEX_OAUTH_TOKEN`), для GSC — ОБА срезу
`GOOGLE_APPLICATION_CREDENTIALS` И `GSC_SITE_URL` (одних credentials без
`GSC_SITE_URL` недостаточно). Если ни один источник не настроен, `pulse` сам
об этом печатает — не молчит: `fetch ✗ источник не настроен (auth login
yandex | google-sa + GSC_SITE_URL)`, плюс finding `fetch_not_configured`.

```bash
seo-cycle auth list                 # [env]/[project]/[global]/[—] по каждой переменной
grep -A3 '^engines:' seo-cycle.yaml # какие движки включены
seo-cycle pulse --skip-fetch        # проверить свежесть уже имеющихся данных без похода в сеть
```

Если токен есть, но движок выключен (или наоборот) — поправь `engines:` в
`seo-cycle.yaml` или добавь токен через `seo-cycle auth login <provider>`.

### 2. `doctor` показывает `agy: missing` — это красный статус?

Симптом: `seo-cycle doctor` в самом конце печатает `agy: missing — обязателен
для Phase 2 (Antigravity)` и кажется, что весь отчёт «красный».

Причина: строки `agy` и `perplexity-key` — справочные, не входят в проверки,
которые двигают итоговый exit-код. Exit-код 1 у `doctor` дают только строки
ВЫШЕ них со статусом `needs attention (rc=N)` или `MISSING` (config, journey,
spend-guard, usage-ledger, провайдеры, `snapshot-freshness: ПРОСРОЧЕН`) —
именно на них и нужно смотреть, если нужно понять, что чинить.

```bash
seo-cycle doctor          # найди строки needs attention / ПРОСРОЧЕН выше agy — чинить именно их
```

Если `agy` реально нужен для Phase 2 (Entity Map через Antigravity) —
поставь его отдельно; сам по себе он `doctor` не «красит».

### 3. `loop` эскалировал (exit 1) — что делать

Симптом: `seo-cycle loop <target> <path>` завершился с кодом 1 и сообщением
про `loop_escalation`.

Причина: лимит попыток `governance.loop.max_attempts` исчерпан, либо два
подряд прогона дали одинаковый набор findings (нет прогресса) — авто-ремонт
дальше буксует без вмешательства человека.

```bash
cat seo/loops/<loop-id>.md          # что именно не проходит и почему остановились
seo-cycle approvals                 # тикет loop_escalation ждёт решения
```

Дальше — правка руками (текста/outline/пакета) по замечаниям из
`seo/loops/<id>.md`, и только потом перезапуск с `--reset`:

```bash
seo-cycle loop <target> <path> --reset
```

Обходить `loop` прямыми вызовами `gate`/`repair` после эскалации нельзя —
эскалация существует именно для того, чтобы остановить зацикливание.

### 4. Проекта нет во вкладке `web`

Симптом: `seo-cycle web --open` открывает дашборд, но нужного проекта нет в
переключателе.

Причина: список проектов дашборд берёт из машинного реестра
`~/.seo-cycle/projects-registry.yaml` (`SEO_CYCLE_REGISTRY` переопределяет
путь) — в реестр проект попадает при `seo-cycle init` в его каталоге (шаг
дозаписи реестра — последний в скрипте, `scripts/init-project.sh`).
Проект, склонированный руками или скопированный с другой машины без
повторного `init`, в реестре не значится.

```bash
cat ~/.seo-cycle/projects-registry.yaml   # проект действительно отсутствует?
```

Самый дешёвый обходной путь — просто запусти `seo-cycle web --open` ИЗ
КАТАЛОГА этого проекта: дашборд всегда добавляет в переключатель текущий
каталог, если там есть `seo-cycle.yaml`, даже без реестра (`load_projects()`
в `webapp.py`). Реестр нужен только для проектов, к которым заходишь не из
их собственного каталога, и для портфельных команд (`pulse --global` и т.п.).

Если хочешь именно в реестре — и `seo-cycle.yaml` в проекте ещё нет, просто
`seo-cycle init` из его каталога: конфиг создастся и реестр допишется
автоматически, одним шагом.

Если `seo-cycle.yaml` уже есть (обычный случай для «второй машины») — **не
перезапускай `init` не глядя**: он спросит «Перезаписать?» и при `y`
сотрёт существующий конфиг с его правками. Безопаснее дописать запись в
реестр вручную, по образцу `config/projects-registry.example.yaml` (поля:
`name`, абсолютный `path` до каталога с `seo-cycle.yaml`, `region_profile`,
`cms`, `status`, `monthly_automation`). Если файла реестра ещё нет вообще —
СНАЧАЛА создай шапку из шаблона (без неё верхний уровень получится списком
вместо словаря, и `seo-cycle web` откажется стартовать с `SystemExit 2`
«верхний уровень конфига должен быть словарём»), ровно как это делает
`init-project.sh`:

```bash
# только если файла ещё нет (пропусти, если ~/.seo-cycle/projects-registry.yaml уже существует)
sed '/^projects:/q' config/projects-registry.example.yaml > ~/.seo-cycle/projects-registry.yaml

cat >> ~/.seo-cycle/projects-registry.yaml <<'EOF'
  - name: "<имя проекта>"
    path: "<абсолютный путь к проекту>"
    region_profile: ru
    cms: wordpress
    status: active
    monthly_automation: false
EOF
```

### 5. PDF отчёта не собирается — «Chrome не найден»

Симптом: `seo-cycle report --write --pdf` пишет markdown/HTML отчёт, но PDF
не появляется (или падает с ошибкой про headless Chrome).

Причина: `--pdf` печатает готовый HTML-отчёт в PDF через headless
Chrome/Chromium/Edge — это внешняя зависимость, а не часть Python-окружения.
md/html пишутся в любом случае (`--write` от них не зависит); если бинарник
браузера не найден, команда завершается НЕ с ошибкой, а с предупреждением в
stderr: `PDF skipped: no Chrome/Chromium/Edge binary found — set CHROME_BIN
env or open the .html and print to PDF manually`.

```bash
seo-cycle report --write --pdf 2>&1 | grep -i pdf   # покажет "PDF skipped: ..." если браузера нет
```

Дальше — либо поставить один из Chrome/Chromium/Edge и (если он не в
стандартном месте) указать `CHROME_BIN=<путь до бинарника>`, либо взять
готовый HTML-отчёт (`seo/reports/client-report-<период>.html`) и
напечатать его в PDF вручную из браузера («Печать → Сохранить как PDF»).

### 6. «Ключи есть, а срез всё равно старый» (`.env` против Keychain)

Симптом: `ai-secret run <scope> -- ...` подтверждает, что ключ провайдера
существует и валиден (в macOS Keychain, по глобальной политике секретов
§5 из `AGENTS.md`), но `pulse` не может забрать свежие данные, а
`seo-cycle auth list` печатает переменную с меткой `[—]`.

Канон один (T-108): значения ключей живут ТОЛЬКО в Keychain, `seo-cycle
auth login`/`auth set` пишут их туда через `ai-secret set` (скрытый ввод,
значение уходит по stdin — не в файл и не в аргументы). В `.env` — только
имена (`.env.example`); старые `.env`/`~/.seo-cycle/env.global` со
значениями инструмент по-прежнему ЧИТАЕТ (legacy, чтобы ничего не сломать
до переноса), но никогда в них не пишет.

Как ключ попадает в процесс: `seo-cycle` не читает Keychain напрямую — ему
нужна переменная окружения. Для команд семейства pulse (`pulse`,
`doctor`, `cohorts`) лончер `bin/seo-cycle` сам проверяет, есть ли ключи pulse
(`YANDEX_OAUTH_TOKEN`/`YANDEX_WEBMASTER_OAUTH_TOKEN`/`GOOGLE_APPLICATION_CREDENTIALS`)
в окружении, и если нет — перезапускает себя под `ai-secret run <scope>`
(scope = `project.brand_name_technical` из `seo-cycle.yaml`). Если ключи уже
экспортированы руками — не трогает их (`ai-secret run` кладёт Keychain
поверх окружения, поэтому проверка стоит ДО перезапуска). Команды с
ключами других провайдеров (`sync`, `ads`, `feed`, `notify`) лончер не
перезапускает — их ключи он не может оценить, не рискуя перекрыть
экспортированное значение; запускай их под `ai-secret run <scope> -- …`. Если `ai-secret` не найден или
scope не определён — печатает ОДНУ строку `⚠ seo-cycle pulse: …` в stderr и
идёт дальше: тихого прогона на старом срезе больше нет.

```bash
seo-cycle auth list                        # источник по каждой переменной: [keychain:<scope>] / [keychain:global] / [env] / [.env legacy] / [—]
seo-cycle pulse                            # сам перезапустится под ai-secret run <scope>
ai-secret run <scope> -- seo-cycle pulse   # ручной эквивалент (ключ приходит переменной процесса)
ai-secret import <scope> .env && rm .env   # разовый перенос legacy-значений в Keychain
```

Если `auth list` показывает `[—]`, а `ai-secret list <scope>` имя видит —
проверь, что scope совпадает: `project.brand_name_technical` в конфиге
должен быть тем же слагом, что и scope в Keychain (`--scope <slug>` у
`auth` переопределяет).

Известная граница: `pulse --all` по реестру проектов обходит несколько
scope, а один `ai-secret run <scope>` покрывает только один — для
портфельного прогона делай `ai-secret run <scope> -- seo-cycle pulse` на
каждый проект. Тот же I-061 (`_tools/SOLUTIONS.md`): для расписания
(launchd/cron) обёртка `ai-secret run <scope> -- <команда>` должна быть
зашита прямо в сам job (`ProgramArguments` плиста), а не запускаться руками
один раз — лончер под launchd тоже перезапустится сам, но только если
`ai-secret` стоит по каноническому пути `~/.local/bin/ai-secret` (PATH лончер
не смотрит; другой путь — только переменная `SEO_CYCLE_AI_SECRET`);
проверять поведением: `launchctl kickstart -k
<label>` → `LastExitStatus = 0` и свежий артефакт в логе, не фактом
загрузки плиста.

Не читай и не печатай значение секрета руками при диагностике — только
`ai-secret run` (§5).

## Конфиг и установка

### `seo-cycle.yaml не найден в <dir>`

Скилл искал в 4 локациях, нигде нет. Создай через wizard:
```bash
seo-cycle init
```
Или вручную скопируй template:
```bash
cp ./.codex/skills/seo-cycle/config/project.template.yaml seo-cycle.yaml
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
2. Условия слишком строгие — посмотри `./.codex/skills/seo-cycle/config/triggers.yaml` и подстрой пороги под свой проект
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
seo-cycle run script validate-entities seo/entities/entities.yaml
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

Скрипт `llm-cli-collect.sh` graceful: пропускает отсутствующую CLI, продолжает с одной (если хоть одна есть). Третий исход (T-069): без `--live` при живом вызове скрипт печатает план и выходит с кодом 3 — это не ошибка CLI, а отсутствие согласия на расход; код 1 с текстом «usage-ledger отказал» — потолок/битый журнал/нет `seo-cycle.yaml` в текущем каталоге. Тот же контракт (код 3 = нужно `--live`, код 1 = отказ леджера) у `img-generate.sh` (claude-режим), `nw-cli.sh new|plagiarism`, `writerzen-browser-collect.py` и `knowledge/graphify-refresh.sh`.

## Общие

### Скилл `seo-cycle` не подхватился после установки

Перезапусти Claude Code сессию — skills загружаются при старте.

### Permission denied при запуске скрипта

```bash
chmod +x ./.codex/skills/seo-cycle/scripts/<name>.{py,sh}
```

### `import: command not found` при запуске Python скрипта

Bash trying to execute Python file as shell. Используй явно:
```bash
python3 ./.codex/skills/seo-cycle/scripts/<name>.py
```
Или убедись что shebang `#!/usr/bin/env python3` есть в первой строке файла.
