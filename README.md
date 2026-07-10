# seo-cycle

**Версия 1.62.0** · универсальный SEO/контент-цикл-оркестратор для Codex CLI и Claude Code.

Полный цикл продвижения сайта — от стратегии и сбора семантики до публикации, fact-check, мониторинга и итераций — управляемый через декларативный конфиг `seo-cycle.yaml`. Адаптируется под любой проект: язык, регион, поисковики, тип сайта, CMS, набор источников.

---

## TL;DR

```bash
# Codex-first: запусти из корня нового проекта
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash

# Optional local AI toolchain for Codex/spec/research work:
bash ~/.codex/vendor/seo-cycle/scripts/install-ai-toolchain.sh --codex

# Optional NotebookLM bridge for a curated expert knowledge base:
bash ~/.codex/vendor/seo-cycle/scripts/install-ai-toolchain.sh --codex --notebooklm

# Claude Code variant:
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-claude.sh | bash

# Existing project: update shared core and refresh the local setup surface
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash -s -- --skip-init
python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-control-plane.py --write

# Knowledge Hub для проекта: wiki + Obsidian + Graphify/zvec distillates
bash ./.codex/skills/seo-cycle/scripts/knowledge/wiki-refresh-all.sh
bash ./.codex/skills/seo-cycle/scripts/knowledge/graphify-refresh.sh
```

Codex — canonical runtime. Project bootstrap теперь **local-entrypoint + shared-core**: общий код обновляется в `~/.codex/vendor/seo-cycle`, а в конкретном проекте создаются только локальные entrypoints `./.codex/skills/seo-cycle`, `./.agents/skills/seo-cycle`, `./.claude/skills/seo-cycle` как symlink на shared core. Если проект не bootstrap'или, seo-cycle skills в нём не появляются и не читаются. Legacy global skill links доступны только через явный `--global-skill`. Bootstrap запускает wizard, создаёт `seo-cycle.yaml`, `.env.example`, `.env`, `AGENTS.md`, policy-файлы, setup blueprint/matrix, upgrade assistant, access-key assistant, context pack, spend guard, onboarding, roadmap и automation recommendations. Секреты не заполняются автоматически.

WordPress/Novomira MCP тоже строго project-local и не создаётся bootstrap'ом по умолчанию. Включай его только в проектах, где он нужен: `python3 ./.codex/skills/seo-cycle/scripts/project-mcp-config.py --write` или `bootstrap-codex.sh --with-wordpress-mcp`. URL/user/password живут только в локальном `.env` или client-specific `.codex/config.toml` конкретного проекта.

WordPress-публикация и администрирование по умолчанию идут через обычный WordPress REST API + Application Password (`WP_BASE_URL`, `WP_USER`, `WP_APP_PASSWORD`): создание/обновление постов, страниц, товаров, мета, media и базовая работа с плагинами. Novomira MCP — не основной канал, а ручной project-local fallback для задач, где нужны его abilities, например Bricks-структуры или специальные plugin actions.

Ручная установка и Codex-режим (AGENTS.md, SEO_RUNTIME) — в [INSTALL.md](INSTALL.md) и [docs/codex-runtime.md](docs/codex-runtime.md).

Knowledge Hub — проектный слой памяти и preflight: [docs/knowledge-hub.md](docs/knowledge-hub.md). Он хранит правила проекта, inventory WordPress, статьи, категории, бренды, товары, решения, отчёты, compact context packs, Graphify-граф и SQLite/zvec-ready hybrid index. Core остаётся общим, а данные и overrides всегда project-local.

📖 **Полное руководство (RU + EN, подробно по каждому инструменту, фазе, команде, + инструкции для ИИ-автоустановки): [GUIDE.md](GUIDE.md)**

Подробная установка — [INSTALL.md](INSTALL.md). История изменений — [CHANGELOG.md](CHANGELOG.md).

---

## Почему так устроено (философия)

Принцип: **разделить «мозг» и «руки»**.

- **Мозг — LLM (Claude или Codex) в среде скилла.** Рассуждения: entity map по Шестакову, написание текстов, fact-check решения, stock-first логика, оценка качества. Это **нельзя** заменить no-code/workflow-движком — они не рассуждают.
- **Руки — Python/bash-скрипты.** Детерминированная работа: сбор данных по API, кэш, публикация, агрегация. Дёшево, версионируемо, тестируемо.
- **Конфиг — единая точка правды.** `seo-cycle.yaml` описывает проект; один и тот же код работает для РФ-строймага и англоязычного SaaS — разница только в конфиге.

Следствия, заложенные в дизайн:
- **Экономия токенов.** Сырьё research → на диск, в контекст LLM — только дистилляты (`*-merged-*.md`). Кэш с TTL не даёт повторно жечь дорогой сбор. Тяжёлая специфика — в `reference/`, грузится по необходимости (progressive disclosure).
- **Универсальность по регионам.** `region_profile` одной строкой переключает набор источников: РФ → Яндекс-стек + доступные из РФ инструменты; запад → Google + западные SaaS. Недоступные в регионе инструменты не запускаются.
- **Бережёт платные лимиты.** Клиенты API (Serpstat, SpyFu, XMLRiver) имеют guard'ы остатка кредитов/бюджета и кэш.

---

## Архитектура

```
┌─ LLM-ядро (Claude Skill tool / Codex) ── РАССУЖДЕНИЯ ─┐
│  entity map · написание · fact-check · QA · решения    │
└────────────────────────────────────────────────────────┘
        ↓ дёргает скрипты            ↓ пишет артефакты
┌─ Скрипты-руки (scripts/) ─────────────────────────────┐
│  resolve-sources · *-fetch (serpstat/spyfu/gsc/...)    │
│  *-suggest · llm-cli-collect · *-publish · db-sync      │
└────────────────────────────────────────────────────────┘
        ↓ единый слой данных          ↓ алерты
┌─ seo.db (SQLite) ──┐   ┌─ notify.py (Telegram) ────────┐
│ positions · usage   │   │ approval · ошибки · кредиты    │
│ queue · attribution │   └────────────────────────────────┘
└─────────────────────┘        ↓ визуализация
                          Obsidian-дашборд (авто из db-sync)
```

10 фаз: discovery → audit → keyword research (multi-source) → cluster+intent → Entity Map → content plan → writing → publishing → JSON-LD/schema → monitoring → iteration. Полное описание фаз — в [SKILL.md](SKILL.md).

### Единый CLI

`install-codex.sh` ставит symlink `~/.local/bin/seo-cycle` → `bin/seo-cycle`. Одна команда вместо десятков `python3 scripts/...`; все аргументы прозрачно пробрасываются в обёрнутый скрипт:

```bash
seo-cycle status                                # текущая стадия, blockers, следующие команды
seo-cycle pulse                                 # ежедневный срез: Вебмастер → снапшот → база → прогресс + алерты
seo-cycle doctor                                # сводный read-only health-check (config/journey/spend/ledger/providers)
seo-cycle loop research-package seo/research-package   # автоцикл качества: gate → repair → re-check (max 5 попыток)
seo-cycle gate draft <draft.md> --outline <outline.json> --write
seo-cycle approvals / approve <id> / reject <id>
seo-cycle run "написать статью про X"           # low-token маршрут задачи (task-router)
seo-cycle run monthly --dry-run                 # месячная автоматизация
seo-cycle --help                                # полный список команд
```

### Автоцикл качества (loop-runner)

`loop-runner.py` (или `seo-cycle loop`) повторяет «gate → repair → re-check» до прохождения, максимум N попыток (`governance.loop`, default 5). Самопроверки делятся на классы качество/достоверность (evidence findings — proof slots, SERP-валидация, E-E-A-T). Между попытками сравниваются fingerprints findings: два одинаковых подряд → ранняя эскалация (approval-тикет `loop_escalation` + Telegram) без сжигания лимита. Для LLM-шагов (переписать драфт, перегенерить outline) — протокол exit 3 с machine-readable инструкциями и `--resume` после исправления. Журнал попыток: `seo/loops/*.json|.md`, виден в `project-journey`.

---

## Возможности

| Область | Что есть |
|---|---|
| **Региональные профили** | `config/region-profiles/{ru,eu,us,global}.yaml` — пресет источников + флаги доступности. `resolve-sources.py` разворачивает в активный список. |
| **Источники семантики** | Яндекс (Wordstat/Suggest/SERP/Вебмастер/Кью/Карты/Товары), Google (GSC/Trends/Suggest/Merchant/Business Profile), Bing Webmaster/IndexNow/Bing Places, XMLRiver (Google/Yandex SERP blocks, Wordstat New, ads/shopping/maps/suggest/AI Overview guarded), Serpstat (вкл. РФ `g_ru`), SpyFu (US/UK/EU), NeuronWriter, WriterZen browser/export (Topic Discovery, Keyword Explorer, Keyword Planner, Domain Focus), LLM-CLI, AnswerThePublic, Perplexity. |
| **Guarded NLP/entity audit** | `google-nlp-audit.py` для Google Cloud Natural Language: entity salience, categories, syntax, moderation/sentiment только по policy, кэш 30 дней и unit caps. |
| **Token/budget governance** | `governance` в `seo-cycle.yaml` + `governance-report.py`: raw на диск, distillates в контекст, cache-first, лимиты платных API/LLM/браузера/автоматизаций. `token-waste-audit.py --write` проверяет, где raw/long reports могут зря сжигать контекст. |
| **Setup control plane** | `setup-control-plane.py --write` собирает intake/profile/sources/governance/validation/tool stack/spend guard/growth roadmap/onboarding/launch-plan/project-journey/setup-blueprint/upgrade assistant/access-key assistant/context-pack/token-waste/provider health/setup-gap-audit/automation/task route/usage ledger в `seo/setup/setup-control-plane.md/json` и next-action checklist. |
| **Context pack** | `context-pack.py --task "..." --write` создаёт первый короткий файл для Claude/Codex: read order, `context_manifest`, task route, caps, spend blockers, approval gates, do-not-load-raw и next commands в `seo/setup/context-pack.md/json`. |
| **Setup blueprint** | `setup-blueprint.py --write` создаёт компактную матрицу запуска проекта: страны, регионы, поисковики, тип бизнеса, local/ecommerce, marketing/ads/tracking policy, tools, budget/subscriptions, automations, guardrails и first-read файлы в `seo/setup/setup-blueprint.md/json` + `seo/setup/setup-matrix.csv`. |
| **Project upgrade assistant** | `project-upgrade-assistant.py --write` для существующих проектов: показывает новые функции текущей версии, missing policy keys/artifacts и yes/no/defer worksheet без автоперезаписи `seo-cycle.yaml`. После review запускай `project-upgrade-apply.py --write` для dry-run или `--apply --use-defaults`/reviewed answers для безопасного добавления missing `policy_files` с backup. |
| **Knowledge Hub** | `scripts/knowledge/wiki-refresh-all.sh` создаёт project-local wiki из WordPress inventory и локальных отчётов: правила, статьи, категории, бренды, товары, internal links, decisions, API catalog, review/comparison cluster candidates и latest context pack. `wiki-preflight.py` проверяет дубли/риски перед правкой, `content-taste-gate.py` ловит служебный SEO-язык и raw URLs, `graphify-refresh.sh` строит Graphify-граф через Antigravity/Gemini CLI/API или пишет degraded status, `zvec-hybrid-index.py` даёт SQLite FTS/zvec-ready hybrid search. |
| **Access-key assistant** | `access-key-assistant.py --write` строит project-specific список нужных Google/Yandex/Bing/NeuronWriter/WriterZen/AI ключей и browser/export setup: ссылки, env names, короткие шаги и CSV, но без secret values. |
| **Setup gap audit** | `setup-gap-audit.py --write` показывает readiness score и missing fields по рынку, бизнесу, local/ecommerce, инструментам, paid API/LLM budget, подпискам, spend guard и automations; дополнительно пишет заполняемый `seo/setup/setup-questionnaire.md/csv/json`. |
| **Setup answer plan** | `setup-answer-plan.py --write` читает заполненный `seo/setup/setup-questionnaire.csv` и пишет review-only план ручных правок `seo/setup/setup-answer-plan.md/json/csv`; секретоподобные ответы отклоняются и не сохраняются. |
| **Launch plan** | `launch-plan.py --write` создаёт первый экран проекта: market/business matrix, token/budget/subscription controls, tool packs, human-secret env names, approval gates, automations и execution order. |
| **Project journey** | `project-journey.py --write` показывает текущую стадию пути от старта до цели, чего не хватает для следующего шага, какие blockers есть сейчас, какую команду запускать и по каким exit criteria переходить дальше. После v3 briefs он отдельно блокирует writing/publishing на `content_draft_gate`, пока нет draft markdown и чистого `draft-quality-gate`. |
| **SEO/AEO/GEO vNext** | `expert-source-pack.py`, `ai-brand-audit.py`, `answer-units-audit.py`, `eeat-evidence-map.py`, `geo-kpi-model.py`, `log-bot-audit.py`, `ai-bot-access-check.py`, `technical-guardrails-audit.py`, `snippet-sitemap-audit.py`, `traffic-drop-diagnostics.py`, `cannibalization-audit.py`, `ru-commerce-readiness.py`, `offpage-risk-audit.py`, `conversion-sxo-audit.py` — report-only слой для AI Brand Audit, Answer Units, GEO KPI, логов, live AI bot access, technical guardrails, RU commerce, off-page, SXO и экспертных источников. |
| **Technical site tools** | `technical-site-audit.py`, `link-audit.py`, `redirect-map-audit.py`, `gsc-url-inspection.py`, `gsc-indexing-export-browser.py`, `gsc-indexing-queue.py`, `gsc-request-indexing-browser.py`, `gsc-indexing-recheck.py`, `indexnow-submit.py`, `yandex-recrawl-submit.py`, `bing-url-inspection.py`, `technical-mcp-health.py`, `lighthouse-audit.py`, `serpstat-audit.py`, `labrika-source-pack.py`, `labrika-health.py` — rollup, broken links/anchors, redirect maps, Google/Bing URL inspection, GSC Pages issue export capture, discovered/not-indexed priority queue, guarded browser UI request indexing helper, recheck after 3-7 days, IndexNow bulk submit for Bing/Yandex-compatible discovery, Yandex Webmaster recrawl queue submit/status, optional GSC/GA/Lighthouse MCP health, Lighthouse/CWV, guarded Serpstat Site Audit API и Labrika manual/export readiness. Live HTTP/API запускаются только явным `--live`/`--technical-check`; GSC UI отправка требует отдельный запуск `gsc-request-indexing-browser.py` и явный `--auto-click`; IndexNow/Yandex recrawl требуют env keys/tokens; Serpstat требует `SERPSTAT_API_KEY` и credit/budget approval. |
| **WordPress publishing/admin** | Primary channel is WordPress REST API with Application Password: posts, pages, products, media, meta and plugin REST endpoints. Novomira MCP is fallback/extension only when explicitly installed for a project. |
| **Project-local MCP** | Optional only: `project-mcp-config.py --write` creates `./.codex/config.toml` for WordPress/Novomira MCP in the current project. It is never installed globally and is not created by default bootstrap. |
| **Perplexity/NotebookLM/XMLRiver/WriterZen evidence** | `perplexity-health.py --write`, `notebooklm-health.py --write`, `xmlriver-health.py --write` и `writerzen-health.py --write` проверяют provider readiness без хранения паролей. `perplexity-collect.py`, `notebooklm-source-pack.py`, `xmlriver-source-pack.py`, `writerzen-browser-collect.py` и `writerzen-source-pack.py` пишут raw/cache на диск, bounded distillates с citations/vector records; WriterZen collector сам открывает browser profile, создаёт нужные отчёты, ловит downloads и импортирует их. Downstream prompts используют только distillates. |
| **Research package quality + repair + deep briefs** | `research-package-quality.py <package> --write` фейлит site-level research package при пустой SERP-валидации, URL/cluster drift, грязном GSC, дублях briefs, orphan URLs, entity-map drift, неагрегированном Google NLP, неиспользованных AI Overview/GEO signals и слабом E-E-A-T/evidence layer. `research-package-repair.py <package> --write` запускает repair layer: `semantic-core-clean.py`, `semantic-core-resync.py`, `entity-map-sync.py`, `google-nlp-aggregate.py`, `orphan-url-resolver.py`, `serp-validation-plan.py`, `spoke-opportunity-audit.py`, `entity-graph-quality.py`. Reviewed SERP exports возвращаются в архитектуру через guarded `serp-validation-import.py --input-json/--input-csv --write`. Если repair новее quality, `project-journey.py` блокирует следующий шаг до повторного quality rerun. После этого `page-outline-v3.py <package> --all-mvp --write` или `--priority P1 --write` создаёт copywriter-ready H2/H3 брифы, `copywriter-ready/<slug>.md` и `vector/page_outline_triplets.jsonl`; проверка: `page-outline-quality.py <package> --version v3 --write`. Затем черновик пишется в `<package>/drafts/*.md` из `copywriter-ready`, проверяется `draft-quality-gate.py <draft.md> --outline <page-outlines-v3/slug.json> --write`; NeuronWriter используется только после `usage-ledger.py check --service neuronwriter ... --fail-on-block` и как scoring/evaluate/import/plagiarism-gate слой, не как безусловный автописатель. WriterZen Plagiarism — только fallback/manual export, основной pre-publish gate — NeuronWriter quota/API. `page-outline-v2.py` остаётся legacy-compatible, `--archive-legacy-briefs` переносит дубли старых briefs только по явному флагу. |
| **Low-token task routing** | `task-router.py --task "..."` строит точный маршрут под задачу: фазы, источники, approval gates, blocked actions, automation и context caps; пишет `seo/setup/latest-task-route.md/json`. |
| **Usage/budget ledger** | `usage-ledger.py report/check/record` ведёт append-only расход токенов, USD, credits, units, requests, browser minutes, NeuronWriter content writer / AI credits / plagiarism checks; пишет `seo/usage/usage-ledger.jsonl` и `seo/setup/latest-usage-ledger.md/json`. |
| **Spend/subscription guard** | `spend-guard.py --write` показывает allowed/approval/blocked по каждому платному/API/LLM/subscription сервису, остатки лимитов и готовые `usage-ledger.py check` preflight-команды. |
| **Tool-stack recommender** | `tool-stack-recommender.py --write` выбирает инструменты под страну/движки/тип бизнеса/бюджет: бесплатные read-only включает, платные API/LLM/IndexNow/ads/tracking ставит за approval, RF foreign tracking отключает. |
| **Growth roadmap** | `growth-roadmap.py --write` превращает intake/tool-stack/budget/automation в top-N действий по технике, search evidence, ecommerce/local, entities/content, AI visibility, CRO/маркетингу и automations. |
| **Setup onboarding** | `setup-onboarding.py --write` создаёт подробный playbook нового проекта: owner каждого шага, human-secret env names, approval gates, команды и proof-артефакты. |
| **Detailed intake wizard** | `project-intake-wizard.py` точечно заполняет страны, регионы, поисковики, тип бизнеса, аудитории, local/merchant/ads/video/analytics, tools и governance. |
| **Detailed project profile** | `project-profile.py` читает `seo/project-intake.yaml` и генерирует overlay/report для стран, поисковиков, регионов, local/merchant/ads/video/analytics, marketing и source overrides. |
| **Automation recommender** | `automation-recommender.py --write` рекомендует tool-aware planned automations по intake/business/market/tool-stack/spend-guard: spend, indexability, search consoles, Bing, schema/CWV, content decay, AI visibility, ecommerce и local; `--apply` только после review. |
| **Safe automations** | `automation-plan.py` генерирует `seo/automations/automation-plan.md`, `crontab.txt`, launchd plist templates и safe read-only/dry-run команды для расширенной матрицы; реальный install заблокирован без двойного policy-разрешения. |
| **Project policies** | `seo/neuronwriter-limits.yaml`, `seo/entities/google-nlp-policy.yaml`, `seo/tool-budget.yaml`, `seo/tool-stack.generated.yaml`, `seo/setup/tool-stack-report.md`, `seo/growth-roadmap.generated.yaml`, `seo/setup/growth-roadmap.md`, `seo/onboarding.generated.yaml`, `seo/setup/onboarding-playbook.md`, `seo/setup/onboarding-checklist.csv`, `seo/setup-blueprint.generated.yaml`, `seo/setup/setup-blueprint.md`, `seo/setup/setup-matrix.csv`, `seo/setup/upgrade-assistant.md`, `seo/setup/upgrade-questionnaire.csv`, `seo/setup/project-upgrade-apply.md`, `seo/setup/project-upgrade-apply.csv`, `seo/setup/access-key-assistant.md`, `seo/setup/access-key-assistant.csv`, `seo/launch-plan.generated.yaml`, `seo/setup/launch-plan.md`, `seo/setup/project-journey.md`, `seo/setup/project-journey-checklist.csv`, `seo/research-package/research-package-quality.md`, `seo/research-package/research-package-action-plan.md`, `seo/research-package/research-package-repair.md`, `seo/research-package/semantic-core.cleaned.csv`, `seo/research-package/semantic-core.resynced.csv`, `seo/research-package/entity_coverage.jsonl`, `seo/research-package/serp-validation-plan.csv`, `seo/research-package/serp-validation-import.md`, `seo/research-package/serp-validation-import.json`, `seo/research-package/spoke-opportunities.csv`, `seo/research-package/page-outlines-v3/*.md/json`, `seo/research-package/copywriter-ready/*.md`, `seo/research-package/vector/page_outline_triplets.jsonl`, `seo/research-package/page-outline-quality.md`, `seo/research-package/page-outline-quality.json`, `seo/research-package/drafts/*.md`, `seo/research-package/drafts/*.draft-quality-gate.md/json`, `seo/setup/context-pack.md`, `seo/setup/token-waste-audit.md`, `seo/setup/perplexity-health.md`, `seo/setup/notebooklm-health.md`, `seo/setup/xmlriver-health.md`, `seo/setup/writerzen-health.md`, `seo/research/writerzen/imports/*`, `seo/research/raw/*`, `seo/research/distillates/*`, `seo/research/vector/source_pack.jsonl`, `seo/setup/setup-gap-audit.md`, `seo/setup/setup-questionnaire.md`, `seo/setup/setup-questionnaire.csv`, `seo/setup/setup-answer-plan.md`, `seo/setup/setup-answer-plan.csv`, `seo/setup/launch-checklist.csv`, `seo/vnext/*.md`, `seo/vnext/*.json`, `seo/technical/*.md`, `seo/technical/*.json`, `seo/spend-guard.generated.yaml`, `seo/setup/spend-guard.md`, `seo/setup/spend-checklist.csv`, `seo/automation-policy.yaml`, `seo/automation-policy.generated.yaml`, `seo/automations/automation-recommendations.md`, `seo/usage/usage-ledger.jsonl`, `seo/setup/latest-usage-ledger.md`, `seo/project-intake.yaml`, `seo/project-intake-report.md`, `seo/project-profile.generated.yaml`, `seo/setup/setup-control-plane.md`, `seo/setup/latest-task-route.md`, `seo/seo-data-collection-map.md`, `seo/access-setup-runbook.md`, `seo/ai-visibility-prompts.csv`. |
| **AI/dev support toolchain** | `install-ai-toolchain.sh --codex` installs Spec Kit, MarkItDown, Graphify and CodeGraph. `--notebooklm` adds a gated NotebookLM MCP bridge for curated expert knowledge bases. Use Spec Kit for large `seo-cycle` feature work, MarkItDown for trusted PDF/XLSX/DOCX/YouTube evidence ingestion, Graphify for mixed docs/code/research graphs, CodeGraph for local code-symbol MCP queries, and NotebookLM only after Google auth. |
| **E-E-A-T** | `schema-org-build.py` — канонический Organization/LocalBusiness узел из `business_profile`; `eeat-render.py` — trust-блок «Источники» из `fact_check_log`; `source-attribution.py` — какой источник даёт топ. |
| **Экономия** | `research-cache.py` (TTL), дистилляты в контекст, guard'ы кредитов Serpstat/SpyFu/XMLRiver. |
| **Слой данных** | `db-sync.py` → `seo.db` (SQLite) из всех CSV/JSON. Фундамент дашбордов. |
| **Уведомления** | `notify.py` — Telegram без n8n, graceful no-op без токена. |
| **Автоматизация** | `monthly-runner.sh` (cron, auto-detect по дате) + `approval-gate.py` + `keyword-queue.py`. `monthly-runner.sh all` — по всем проектам реестра. |
| **Масштаб** | `projects-registry.yaml` + `init-project.sh` — новый проект одной командой. |
| **Публикация** | CMS-aware (WordPress/Woo через REST в emwoody-примере). |

---

## Runtime: Claude и Codex (двойной режим)

Скилл рассчитан на **любой из двух «мозгов»** (`runtime: auto|claude|codex` / env `SEO_RUNTIME`):

- **Claude Code** — точка входа `SKILL.md`. Делегирование — subagents; изображения/браузер — через `codex exec`-обёртки и Claude in Chrome MCP.
- **Codex CLI** — точка входа `AGENTS.md` (симлинк на `SKILL.md`). **Гибрид:** наши скрипты для уникального (РФ-источники, Serpstat/SpyFu, кэш, публикация) + нативные Codex-skills для изображений (`seo-image-gen`/`image`/`sora`), браузера (`browser`/`playwright`) и делегирования (`dispatching-parallel-agents`). Без `codex exec` самовызовов.

Логика 10 фаз идентична; различается механика вызова инструментов. Маппинг и детали — [docs/codex-runtime.md](docs/codex-runtime.md). Один источник правды, без дублирования.

---

## Версионирование

[SemVer](https://semver.org): `MAJOR.MINOR.PATCH`. Текущая — в файле [VERSION](VERSION), история — в [CHANGELOG.md](CHANGELOG.md).

- **MAJOR** — несовместимые изменения схемы `seo-cycle.yaml` или структуры скилла.
- **MINOR** — новые источники/фазы/скрипты (обратная совместимость).
- **PATCH** — фиксы, доки.

Каждый релиз тегается в git (`v1.3.0`).

---

## Roadmap совершенствований

- **Этап 2 (агентство):** n8n self-hosted как слой триггеров/вебхуков/retry поверх скриптов; read-only дашборд (Metabase поверх `seo.db`).
- **Этап 3 (SaaS):** Next.js + multi-tenant + биллинг — только при подтверждённом спросе.
- **Источники:** Я.Маркет competitor-парсер; webhook-приём GSC/Вебмастер для near-real-time алертов.
- **E-E-A-T:** автоген `reviewedBy`/Person при появлении реальных авторов-экспертов.
- **Атрибуция:** автоотключение слабых источников в профиле по данным `source-attribution.py`.
- **Тесты:** smoke-тесты скриптов (pytest) для CI при шаринге.

(Полный архитектурный разбор «n8n vs Next.js vs CLI» — в истории проекта emwoody, план `immutable-leaping-stearns.md`.)

---

## Структура

```
seo-cycle/
├── SKILL.md            # точка входа Claude (frontmatter + 10 фаз)
├── AGENTS.md           # точка входа Codex (симлинк → SKILL.md)
├── codex-primary-runtime/ # отдельный Codex-first entrypoint skill
├── README.md           # этот файл
├── INSTALL.md          # установка под новый проект
├── CHANGELOG.md        # история версий
├── VERSION             # текущая версия (SemVer)
├── .env.example        # шаблон ключей
├── config/
│   ├── project.template.yaml
│   ├── region-profiles/{ru,eu,us,global}.yaml
│   ├── projects-registry.yaml
│   └── triggers.yaml
├── scripts/            # все переносимые скрипты
├── prompts/            # промпты (Perplexity и др.)
├── templates/          # шаблоны артефактов + project-policies
└── docs/               # architecture, adapt, codex-runtime, obsidian, ...
```

---

## Шаринг

Каталог самодостаточен, секретов нет (ключи — только в `.env` проектов). Git / zip / Claude-plugin — см. [INSTALL.md](INSTALL.md) → «Как поделиться скиллом».

Лицензия: личное использование (укажи свою при публикации).
