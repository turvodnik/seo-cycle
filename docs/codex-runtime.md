# Codex как основной мозг seo-cycle

Скилл работает с двумя рантаймами. Логика 10 фаз — общая (в `SKILL.md`), различается **механика вызова инструментов**. Этот документ — про режим, когда оркестратор не Claude Code, а **Codex CLI**.

## Точка входа и детект режима

- Claude Code читает `SKILL.md` (распознаёт скилл по frontmatter).
- Codex читает `AGENTS.md` — **симлинк на `SKILL.md`** (тот же контент).
- Canonical checkout живёт в `~/.codex/skills/seo-cycle`. `~/.claude/skills/seo-cycle` и `~/.agents/skills/seo-cycle` — совместимые symlinks на Codex-ядро.

Codex-first установка нового проекта:

```bash
cd <project-root>
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash
```

Режим задаётся переменной **`SEO_RUNTIME`** = `claude | codex | auto` (default `auto`). При `auto` скрипты определяют Codex по env-признакам (`CODEX_SANDBOX`/`CODEX_THREAD_ID`/`CODEX_RUNNING`); иначе считают рантайм Claude. Принудительно: `export SEO_RUNTIME=codex`.

Запуск Codex-сессии из корня проекта:
```bash
ln -sf ~/.codex/skills/seo-cycle/AGENTS.md ./AGENTS.md   # один раз, чтобы Codex подхватил
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
- `seo/tool-budget.yaml`
- `seo/tool-stack.generated.yaml`
- `seo/setup/tool-stack-report.md`
- `seo/growth-roadmap.generated.yaml`
- `seo/setup/growth-roadmap.md`
- `seo/onboarding.generated.yaml`
- `seo/setup/onboarding-playbook.md`
- `seo/setup/onboarding-checklist.csv`
- `seo/setup-blueprint.generated.yaml`
- `seo/setup/setup-blueprint.md`
- `seo/setup/setup-matrix.csv`
- `seo/launch-plan.generated.yaml`
- `seo/setup/launch-plan.md`
- `seo/setup/launch-checklist.csv`
- `seo/setup/context-pack.md`
- `seo/setup/latest-context-pack.md`
- `seo/setup/setup-gap-audit.md`
- `seo/setup/latest-setup-gap-audit.md`
- `seo/setup/setup-questionnaire.md`
- `seo/setup/setup-questionnaire.csv`
- `seo/setup/setup-answer-plan.md`
- `seo/spend-guard.generated.yaml`
- `seo/setup/spend-guard.md`
- `seo/setup/spend-checklist.csv`
- `seo/automation-policy.yaml`
- `seo/setup/setup-control-plane.md`
- `seo/setup/latest-task-route.md`
- `seo/setup/latest-usage-ledger.md`
- `seo/usage/usage-ledger.jsonl`
- `seo/automations/automation-recommendations.md`
- `seo/automation-policy.generated.yaml`
- `seo/project-intake.yaml`
- `seo/project-intake-report.md`
- `seo/project-profile.generated.yaml`

Эти файлы задают локальный контракт по расходу NeuronWriter/Google NLP, tracking/tag policy, разрешённым источникам и подключённым аккаунтам. В Codex-режиме особенно важно:

- использовать NeuronWriter как primary SERP/NLP content editor только в пределах limits-файла;
- использовать Google Cloud Natural Language только как guarded technical entity audit с cache/unit caps;
- перед дорогим сбором, браузером, публикацией или schedule запускать `python3 ~/.codex/skills/seo-cycle/scripts/governance-report.py --format md`;
- перед началом большого цикла обновлять compact readiness, setup blueprint и gap audit: `python3 ~/.codex/skills/seo-cycle/scripts/setup-control-plane.py --write`;
- перед конкретной задачей строить bounded route: `python3 ~/.codex/skills/seo-cycle/scripts/task-router.py --task "<цель пользователя>" --write` и запускать только фазы/источники из `seo/setup/latest-task-route.md`;
- после route строить context pack: `python3 ~/.codex/skills/seo-cycle/scripts/context-pack.py --task "<цель пользователя>" --write` и читать `seo/setup/context-pack.md` первым; подробные отчёты открывать только по read order;
- перед расходом токенов/API/credits/ads строить spend guard `python3 ~/.codex/skills/seo-cycle/scripts/spend-guard.py --write`; если сервис не allowed, нужен approval/policy. Затем делать preflight `usage-ledger.py check --service <tool> ... --fail-on-block`, после расхода фиксировать `usage-ledger.py record --service <tool> ... --write`;
- перед подключением Google/Yandex/Bing/Microsoft/NLP/AI/merchant/local/ads/tracking инструментов строить stack: `python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write`; `--apply` только после review, без секретов;
- перед широким циклом строить top-N roadmap: `python3 ~/.codex/skills/seo-cycle/scripts/growth-roadmap.py --write` и начинать с `seo/setup/growth-roadmap.md`;
- перед первым запуском строить onboarding: `python3 ~/.codex/skills/seo-cycle/scripts/setup-onboarding.py --write`; human-secret значения вводятся только в `.env`/кабинетах;
- перед чтением подробных setup-отчётов строить context pack, setup blueprint, gap audit/questionnaire и launch contract: `context-pack.py --write`, `setup-blueprint.py --write`, `setup-gap-audit.py --write`, после заполнения questionnaire — `setup-answer-plan.py --write`, затем `launch-plan.py --write`; начинать с `seo/setup/context-pack.md`, потом `seo/setup/setup-blueprint.md`, потом `seo/setup/setup-questionnaire.csv` / `seo/setup/setup-gap-audit.md`, после заполнения CSV — `seo/setup/setup-answer-plan.md`, затем `seo/setup/launch-plan.md`;
- рекомендации schedule строить через `python3 ~/.codex/skills/seo-cycle/scripts/automation-recommender.py --write`; он использует tool-stack/spend-guard и покрывает spend, indexability, search consoles, Bing, schema/CWV, content decay, ecommerce/local и AI visibility; применять через `--apply` только после review, `--allow-schedules` только по явному разрешению;
- детальную настройку стран/поисковиков/регионов/ads/local/merchant/tools/governance делать через `python3 ~/.codex/skills/seo-cycle/scripts/project-intake-wizard.py --interactive --write` или `--defaults --write`;
- точечную настройку проекта делать через `python3 ~/.codex/skills/seo-cycle/scripts/project-profile.py --write`; `--apply` только после review generated overlay/report;
- schedule-артефакты создавать через `python3 ~/.codex/skills/seo-cycle/scripts/automation-plan.py --write --include-disabled`; expanded tasks должны оставаться report-only/dry-run/env-gated до approval, реальный cron install — только при двойном разрешении governance + `seo/automation-policy.yaml`;
- держать low-token режим: raw data на диск, в контекст только distillates/top-N, progressive disclosure вместо чтения всего репозитория;
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

`AGENTS.md → SKILL.md` создаётся один раз: `cd ~/.codex/skills/seo-cycle && ln -sf SKILL.md AGENTS.md`. Git хранит симлинк (mode 120000) — переживает `clone`. Проверка: `ls -l AGENTS.md`.
