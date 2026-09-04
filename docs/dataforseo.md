# DataForSEO в seo-cycle: MCP и API

DataForSEO — платный поставщик SEO-данных (SERP Google/Bing, частотность Google Ads,
собственная база Labs, бэклинки, технический разбор страниц). Работает по всему миру,
**кроме РФ и Белоруссии** — DataForSEO исключила обе локации из всех API и баз с марта
2022 (санкции, приостановка Google Ads/Bing Ads и Yandex SERP API в этих странах;
источник: [dataforseo.com/update/russia-and-belarus-api-locations](https://dataforseo.com/update/russia-and-belarus-api-locations)).
Для РФ/СНГ — Keys.so (Яндекс) и Serpstat (`g_ru`); DataForSEO закрывает остальной мир,
где у них только ограниченный набор.

## Два пути к одним и тем же данным

| | MCP-сервер `dataforseo` | `scripts/dataforseo-fetch.py` |
|---|---|---|
| Кому | агенту в диалоге (Claude Code, Codex, Gemini) | конвейерам, cron, батчам |
| Как вызывается | агент сам выбирает инструмент | обычная команда в терминале |
| Плюс | разведка «на лету», не надо помнить эндпоинты | детерминизм, кэш, учёт трат, никакого контекста |
| Минус | ~44 схемы инструментов в контексте сессии | нужно знать, какая подкоманда нужна |

Правило по умолчанию: **разведка — MCP, повторяемая работа — скрипт.**

## Ключ

Один ключ на оба пути: `base64("login:password")` из кабинета DataForSEO.
Значение живёт в macOS Keychain (scope `global`, имя `DATAFORSEO_API_KEY_BASE64`),
исходник — Bitwarden `ai/global/seo-tools`. В `.env` проектов значение не кладём.

```bash
ai-secret run global -- python3 scripts/dataforseo-fetch.py balance
```

MCP-сервер запускается обёрткой `~/.local/bin/dataforseo-mcp`: она сама
достаёт ключ из Keychain, поэтому в `.mcp.json` проекта и в конфигах агентов секретов нет.

## Верификация аккаунта — обязательна

Пока аккаунт не верифицирован в `app.dataforseo.com`, **все методы данных отвечают
HTTP 403 / `40104`** («Please verify your account»), а бесплатный `appendix/user_data`
работает. Это упирается в аккаунт, а не в настройки: и MCP, и скрипт получат одну ошибку.

## Деньги

Тариф — pay-as-you-go: тратится баланс счёта, подписки нет. Скрипт считает реальную
стоимость из поля `cost` каждого ответа и складывает её в `seo/research/dataforseo/_usage.json`
(сброс помесячно, запись атомарная и под файловой блокировкой — параллельные запуски не
теряют чужой расход). Стоп срабатывает по минимуму из `--budget` (по умолчанию 5 USD) и
`governance.subscriptions.dataforseo.monthly_usd_cap` проекта, если конфиг найден; `--force` снимает
стоп осознанно. Битый или нечитаемый `_usage.json` — это отказ с подсказкой, а не «потрачено
0»: молчаливый пропуск платного вызова недопустим. Кэш на 30 дней означает: повторный запрос
той же выборки не стоит ничего (ответы с ошибкой задачи в кэш не попадают — переспросятся).

## Подкоманды

```bash
balance                      # остаток и лимиты (бесплатно)
serp        "ключ"           # органическая выдача Google
volume      "к1" "к2" ...    # частотность/CPC/конкуренция Google Ads
ideas       "ключ"           # идеи ключей (Labs)
related     "ключ"           # связанные ключи (Labs)
ranked      example.com      # ключи, по которым ранжируется домен
competitors example.com      # домены-конкуренты по органике
backlinks   example.com      # сводка ссылочного профиля
onpage      https://…/page   # мгновенный технический разбор страницы
```

Общие опции работают с обеих сторон подкоманды: `--location` (код локации Google Ads,
2840 = США, 2203 = Чехия — полный список см. в справке DataForSEO по локациям; РФ и
Белоруссия недоступны, см. выше), `--language` (`ru`, `cs`, `en`), `--limit`, `--depth`,
`--md`, `--ttl`, `--budget`, `--force`, `--out`.

## Включение в проекте

1. В `<проект>/seo-cycle.yaml`: `engines.dataforseo.enabled: true` и
   `governance.subscriptions.dataforseo.monthly_usd_cap` под ваш аппетит.
2. MCP-сервер уже прописан в `.mcp.json` проекта (Claude Code) и
   `.gemini/settings.json` (Gemini CLI); у Codex сервер глобальный.
3. Первый запуск Claude Code в проекте попросит подтвердить MCP-сервер — это разовое действие.
