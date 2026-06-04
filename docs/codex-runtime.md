# Codex как основной мозг seo-cycle

Скилл работает с двумя рантаймами. Логика 10 фаз — общая (в `SKILL.md`), различается **механика вызова инструментов**. Этот документ — про режим, когда оркестратор не Claude Code, а **Codex CLI**.

## Точка входа и детект режима

- Claude Code читает `SKILL.md` (распознаёт скилл по frontmatter).
- Codex читает `AGENTS.md` — **симлинк на `SKILL.md`** (тот же контент).

Режим задаётся переменной **`SEO_RUNTIME`** = `claude | codex | auto` (default `auto`). При `auto` скрипты определяют Codex по env-признакам (`CODEX_SANDBOX`/`CODEX_THREAD_ID`/`CODEX_RUNNING`); иначе считают рантайм Claude. Принудительно: `export SEO_RUNTIME=codex`.

Запуск Codex-сессии из корня проекта:
```bash
ln -sf ~/.claude/skills/seo-cycle/AGENTS.md ./AGENTS.md   # один раз, чтобы Codex подхватил
export SEO_RUNTIME=codex
codex exec -c model_reasoning_effort="xhigh" -c web_search="live" \
  "Прочитай AGENTS.md и seo-cycle.yaml. Запусти SEO-цикл Phase 2 для кластера 'минеральная вата'."
```

## Project policy intake в Codex

Перед запуском фаз Codex должен прочитать не только `seo-cycle.yaml`, но и локальные policy-файлы проекта, если они есть:

- `seo/neuronwriter-limits.yaml`
- `seo/neuronwriter.md`
- `seo/entities/google-nlp-policy.yaml`
- `seo/seo-data-collection-map.md`
- `seo/access-setup-runbook.md`
- `seo/ai-visibility-prompts.csv`

Эти файлы задают локальный контракт по расходу NeuronWriter/Google NLP, tracking/tag policy, разрешённым источникам и подключённым аккаунтам. В Codex-режиме особенно важно:

- использовать NeuronWriter как primary SERP/NLP content editor только в пределах limits-файла;
- использовать Google Cloud Natural Language только как guarded technical entity audit с cache/unit caps;
- проверять robots/Content-Signal policy: `search=yes, ai-input=yes, ai-train=no` допустимо как запрет обучения, но публичный `robots.txt` не должен содержать PHP warnings/HTML или editor preview мусор;
- не ставить зарубежные tracking tags/pixels на РФ-проекты без явного разрешения policy;
- не печатать секреты из `.env`, OAuth, API keys или service-account JSON.

## Гибрид: что наше, что нативное Codex

Принцип: **наши скрипты — для уникального** (РФ-источники, кэш, guard'ы кредитов, региональные профили, публикация); **нативные Codex-skills — для того, что в Claude-режиме шло через `codex exec`-обёртки, Claude in Chrome MCP и Claude subagents**. Никаких `codex exec` самовызовов изнутри Codex-сессии.

| Возможность | Claude-режим | Codex-режим (нативно) | Наш скрипт (оба режима) |
|---|---|---|---|
| РФ-семантика | наши скрипты | наши скрипты | `serpstat-fetch.py`, `yandex-suggest.py`, делегат yandex |
| Доп. сбор LLM | `agy` + `codex exec` | **только `agy`** (Codex собирает сам web_search, потом merge) | `llm-cli-collect.sh` (RUNTIME-aware) + `llm-cli-merge.py` |
| Генерация изображений | `img-generate.sh` → `codex exec` | **`seo-image-gen` / `image` / `sora`** (вывод `CODEX_NATIVE_IMAGE`) | `img-generate.sh` (RUNTIME-aware); `img-optimize.sh`, `wp-image-upload.py` — общие |
| Браузер (Perplexity Deep Research, Wordstat deep, Я.Вебмастер, SERP-блоки) | Claude in Chrome MCP | **`browser@openai-bundled` / `playwright` / `screenshot`** | — |
| Делегирование субзадач | Claude subagents (`Agent`) | **`dispatching-parallel-agents` / `subagent-driven-development`** | — |
| Google-данные (GSC/GA4/CrUX) | `claude-seo:seo-google` или наши fetch | наши `gsc-fetch.py`/`ga4-fetch.py` или нативный `seo-google` | `*-fetch.py` — общие |
| NeuronWriter | `nw.sh` | `nw.sh` | ✅ |
| Serpstat / SpyFu | наши клиенты с guard'ами | наши клиенты с guard'ами | `serpstat-fetch.py`, `spyfu-fetch.py` |
| Публикация WP/Woo | `wp-*-publish.py` | `wp-*-publish.py` | ✅ |
| Данные / алерты / очередь / approval | наши скрипты | наши скрипты | `db-sync.py`, `notify.py`, `keyword-queue.py`, `approval-gate.py` |
| Расписание/оркестрация | cron + `monthly-runner.sh` | cron + `monthly-runner.sh` | ✅ |

**Главное:** все `scripts/*.py` и большинство `*.sh` рантайм-агностичны (чистый Python/bash) — работают одинаково. RUNTIME-aware только те, что оборачивали Codex: `llm-cli-collect.sh`, `img-generate.sh`.

## Фазы в Codex-режиме (отличия от Claude)

- **Phase 2 (сбор):** РФ-источники + Serpstat/SpyFu/suggest — наши скрипты. `llm-cli-collect.sh` в codex-режиме запускает только `agy`; вторую половину Codex собирает нативно (web_search) по напечатанному промпту и сам сливает через `llm-cli-merge.py`. Браузерные источники (Wordstat deep, Я.Вебмастер) — через codex `browser`/`playwright`.
- **Phase 6 (writing) fact-check:** вместо Perplexity-через-Claude-in-Chrome — codex `browser` skill + `web_search`. Результат так же пишется в `fact_check_log`.
- **Phase 7 (изображения):** `img-generate.sh` отдаёт `CODEX_NATIVE_IMAGE` — Codex генерит своим image-skill и сохраняет в `save_to`; дальше общие `img-optimize.sh` + `wp-image-upload.py`.
- **Делегирование (любая фаза):** вместо Claude subagents — `dispatching-parallel-agents` / последовательные шаги Codex.
- **Phase 9-10 (мониторинг/итерация):** наши `*-fetch.py` + `triggers-eval.py` + `source-attribution.py` — без изменений.

## Codex reasoning + web search

Включать явно при сборе/fact-check: `-c model_reasoning_effort="xhigh" -c web_search="live"` (уже зашито в `llm-cli-collect.sh` для claude-режима; в codex-режиме Codex применяет нативно).

## Поддержание симлинка

`AGENTS.md → SKILL.md` создаётся один раз: `cd ~/.claude/skills/seo-cycle && ln -sf SKILL.md AGENTS.md`. Git хранит симлинк (mode 120000) — переживает `clone`. Проверка: `ls -l AGENTS.md`.
