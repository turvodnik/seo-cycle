---
name: seo-cycle
description: Универсальный SEO/контент-цикл оркестратор для любого проекта — от стратегии и сбора семантики до публикации, fact-check, мониторинга и итераций. Используй когда пользователь просит «запусти SEO-цикл», «полная SEO-стратегия с нуля», «продвинь раздел X», «семантическое ядро + контент-план + публикация», «расширь блог под кластер», «мониторинг и обновления», «универсальный SEO под мой проект». Адаптируется под конкретный сайт через `seo-cycle.yaml` (язык, регион, поисковики, тип проекта, CMS, источники данных, tone of voice). Поддерживает 10 фаз: discovery → audit → multi-source keyword research (Яндекс Wordstat/Suggest/SERP/Я.Вебмастер + Google GSC/Trends/Suggest + NeuronWriter + LLM CLI Antigravity/Codex + AnswerThePublic + Perplexity Pro) → cluster + intent → Entity Map (методика Шестакова) → content plan → writing → publishing (CMS-aware) → JSON-LD schema → monitoring → iteration. Все шаги config-driven: пропускает источники/фазы, которых нет в проекте. При первом запуске без `seo-cycle.yaml` — запускает install wizard. НЕ для одношаговых задач — для них вызывай конкретный субскилл/агент напрямую.
---

# Универсальный SEO-цикл (`seo-cycle`)

Скилл-оркестратор полного SEO-цикла для **любого проекта**. Все решения config-driven: один и тот же фреймворк работает для интернет-магазина в РФ, англоязычного блога, локального бизнеса в Германии или SaaS-стартапа в США — отличия задаются в `seo-cycle.yaml` проекта.

> **Документация.** Полное руководство (RU + EN, все инструменты/фазы/команды + AI-автоустановка) — `GUIDE.md`. **Правило: при ЛЮБОМ изменении кода/конфига/возможностей обнови `GUIDE.md` (обе версии) и `CHANGELOG.md` в том же коммите + подними `VERSION` по SemVer.**

> **Рантайм (Claude / Codex).** Этот файл — точка входа Claude Code. Если основной мозг — **Codex CLI**, точка входа `AGENTS.md` (симлинк сюда). Режим: `runtime:` в конфиге или env `SEO_RUNTIME=claude|codex|auto`. Логика фаз одинакова; в codex-режиме генерация изображений, браузер (Perplexity/Wordstat/Вебмастер) и делегирование идут через **нативные Codex-skills**, а не `codex exec`-обёртки/Claude-in-Chrome/subagents. Гибрид и маппинг инструментов — в **`docs/codex-runtime.md`** (читай при работе в Codex).

## Project Policy Intake (локальные правила проекта)

Перед выбором фаз, запуском API, расходом кредитов или изменением индексации/аналитики проверь, есть ли в активном проекте локальные SEO-policy файлы:

- `seo/neuronwriter-limits.yaml` — тариф NeuronWriter, остатки, резерв, reset, разрешённый расход автоматизации.
- `seo/neuronwriter.md` — workflow NeuronWriter, project ID, helper-команды, target score.
- `seo/entities/google-nlp-policy.yaml` — статус Google Cloud Natural Language, budget alert, cache TTL, лимиты на запуск, unit caps по функциям, языковые ограничения.
- `seo/seo-data-collection-map.md` — разрешённые источники данных, AI visibility checks, ecommerce/product sources, политика tracking/tag.
- `seo/access-setup-runbook.md` — подключённые аккаунты, пропущенные платные сервисы, API notes, операционные ограничения.
- `seo/ai-visibility-prompts.csv` — стартовая очередь AI visibility запросов и evidence-полей для Google AI/Bing Copilot/Perplexity/OpenAI/Claude/Gemini/DeepSeek.
- `seo/tool-budget.yaml` — лимиты токенов, paid API, LLM, подписок, кэша и stop-условия по источникам.
- `seo/tool-stack.generated.yaml` и `seo/setup/tool-stack-report.md` — рекомендуемый стек Google/Yandex/Bing/Microsoft/NLP/AI/merchant/local/ads/tracking под страну, бизнес, бюджет и policy; создаётся `scripts/tool-stack-recommender.py --write`.
- `seo/growth-roadmap.generated.yaml` и `seo/setup/growth-roadmap.md` — top-N приоритетов по technical/search evidence/ecommerce/local/content/entities/AI visibility/CRO/automation; создаётся `scripts/growth-roadmap.py --write`.
- `seo/onboarding.generated.yaml`, `seo/setup/onboarding-playbook.md` и `seo/setup/onboarding-checklist.csv` — подробный first-run setup playbook с владельцами шагов, human-secret env names, approval gates, командами и proof-артефактами; создаётся `scripts/setup-onboarding.py --write`.
- `seo/setup-blueprint.generated.yaml`, `seo/setup/setup-blueprint.md` и `seo/setup/setup-matrix.csv` — компактная матрица запуска проекта: страны, регионы, поисковики, тип бизнеса, marketing/ads/tracking policy, tools, budget/subscriptions, automations, guardrails и first-read файлы; создаётся `scripts/setup-blueprint.py --write`.
- `seo/setup/upgrade-assistant.md` и `seo/setup/upgrade-questionnaire.csv` — review-only помощник для существующих проектов: показывает новые возможности текущей версии, missing policy keys/artifacts и yes/no/defer вопросы; создаётся `scripts/project-upgrade-assistant.py --write`.
- `seo/setup/project-upgrade-apply.md`, `seo/setup/project-upgrade-apply.json` и `seo/setup/project-upgrade-apply.csv` — safe updater для старых проектов: dry-run/apply reviewed missing `policy_files` keys с backup; создаётся `scripts/project-upgrade-apply.py --write`, применяет только с `--apply`.
- `seo/setup/access-key-assistant.md` и `seo/setup/access-key-assistant.csv` — project-specific помощник по ключам/токенам: показывает только нужные провайдеры, ссылки, env names и короткие шаги без secret values; создаётся `scripts/access-key-assistant.py --write`.
- `seo/launch-plan.generated.yaml`, `seo/setup/launch-plan.md` и `seo/setup/launch-checklist.csv` — компактный first-screen launch contract: страна/движки/регион, тип бизнеса, token/budget/subscription controls, tool packs, human-secret env names, approval gates, automations и execution order; создаётся `scripts/launch-plan.py --write`.
- `seo/setup/project-journey.md`, `seo/setup/project-journey.json` и `seo/setup/project-journey-checklist.csv` — автоматический путь от старта до цели: текущая стадия, missing artifacts, blockers, next command, exit criteria и action plan; после v3 briefs отдельно блокирует `content_draft_gate`, пока нет draft markdown и чистого `draft-quality-gate`; создаётся `scripts/project-journey.py --write`.
- `seo/setup/context-pack.md` и `seo/setup/latest-context-pack.md` — первый короткий файл для Claude/Codex под текущую задачу: read order, `context_manifest`, task route, caps, spend blockers, approval gates, do-not-load-raw и next commands; создаётся `scripts/context-pack.py --task "..." --write`.
- `seo/setup/token-waste-audit.md` — проверка raw/large artifacts, oversized distillates и accidental context waste; создаётся `scripts/token-waste-audit.py --write`.
- `seo/setup/perplexity-health.md` и `seo/setup/notebooklm-health.md` — provider health для Perplexity persistent browser/app/API fallback и NotebookLM MCP/export fallback; создаются `scripts/perplexity-health.py --write` и `scripts/notebooklm-health.py --write`, пароли/секреты не хранят.
- `seo/research/raw/*`, `seo/research/distillates/*`, `seo/research/vector/source_pack.jsonl` — единый raw/distillate/vector contract для evidence; Perplexity собирается через `scripts/perplexity-collect.py`, NotebookLM exports — через `scripts/notebooklm-source-pack.py`.
- `seo/research-package/research-package-quality.md/json` или `<package>/research-package-quality.md/json` — quality gate для site-level research package: пустой SERP validation, URL/cluster drift, грязные GSC-запросы, дубли briefs, orphan URLs, entity-map drift, неагрегированный Google NLP, неиспользованные AI Overview/GEO signals и слабый E-E-A-T/evidence layer; создаётся `scripts/research-package-quality.py <package> --write`.
- `seo/research-package/research-package-action-plan.md` или `<package>/research-package-action-plan.md` — автоматический пошаговый план действий при запуске/аудите: priority, command, target files, definition of done; создаётся тем же `scripts/research-package-quality.py <package> --write`, короткий вывод: `--format plan`.
- `<package>/research-package-repair.md/json`, `<package>/semantic-core.cleaned.csv`, `<package>/semantic-core.rejected.csv`, `<package>/semantic-core.resynced.csv`, `<package>/entity_coverage.jsonl`, `<package>/content-plan.orphan-backlog.csv`, `<package>/serp-validation-plan.csv`, `<package>/serp-validation-import.md/json`, `<package>/spoke-opportunities.csv`, `<package>/entity-graph-quality.md/json` — repair layer для findings research package gate: очистка ядра, ресинхрон URL/cluster IDs, синхронизация entity map, агрегация Google NLP, orphan backlog, план SERP-проверки, guarded импорт reviewed DataForSEO/Serpstat/manual SERP export обратно в архитектуру, phase-2 spokes и качество entity graph; единый запуск `research-package-repair.py`, точечный fallback: `semantic-core-clean.py`, `semantic-core-resync.py`, `entity-map-sync.py`, `google-nlp-aggregate.py`, `orphan-url-resolver.py`, `serp-validation-plan.py`, `serp-validation-import.py --input-json/--input-csv`, `spoke-opportunity-audit.py`, `entity-graph-quality.py`.
- `seo/research-package/page-outlines-v3/*.md/json`, `seo/research-package/copywriter-ready/*.md` и `seo/research-package/vector/page_outline_triplets.jsonl` — основной deep copywriter handoff: H2/H3 briefs уровня конкурента поверх evidence architecture, tool-first ordering для tool/app/quiz страниц, computed word count, H3 allocation, `metrics_rollup`, intro/conclusion, SEO meta, Key Takeaways, FAQ answer guidelines, visual inventory, section bridges, writer handoff, `copywriting_playbook`, `writer_prompt_packet`, copywriting details, source slots, acceptance criteria, entities, keywords, visuals, copywriter notes, Answer Units, evidence required, entity triplets, schema, internal links, synthetic prompts и E-E-A-T no-fabrication guard; создаётся `scripts/page-outline-v3.py <package> --page "<url|cluster|keyword>" --write`, массово: `--all-mvp --write` или `--priority P1 --write`.
- `seo/research-package/page-outlines-v2/*.md/json` или `<package>/page-outlines-v2/*.md/json` — legacy-compatible глубокие page briefs; `--archive-legacy-briefs` переносит дубли старых briefs только по явному флагу.
- `seo/research-package/page-outline-quality.md/json` или `<package>/page-outline-quality.md/json` — quality gate для page briefs: word-count drift, H3/H2 word-count mismatch, SERP/page-type lock, intro/conclusion, SEO meta, Key Takeaways, FAQ, writer handoff, copywriting playbook, writer prompt packet, revision checklist, fact-check queue, schema, internal links, Answer Units, source slots, acceptance criteria, evidence, entity orphans, section bridges, visuals, trust limits, synthetic prompts, no-fabricated-expertise, v3 tool-first ordering, v3 visual inventory и v3 triplet export; создаётся `scripts/page-outline-quality.py <package> --version v3 --write`.
- `<package>/drafts/*.md` и `<draft>.draft-quality-gate.md/json` — writing gate после `copywriter-ready`: markdown-черновик проверяется против `page-outline-v3` на missing H2/H3, unsafe first-person expertise, missing internal links, missing proof/source slots и FAQ mismatch; создаётся `scripts/draft-quality-gate.py <draft.md> --outline <outline.json> --write`.
- `seo/setup/setup-gap-audit.md`, `seo/setup/setup-questionnaire.md` и `seo/setup/setup-questionnaire.csv` — readiness score, missing fields и заполняемый worksheet по рынку, бизнесу, local/ecommerce, инструментам, budget/subscriptions, spend guard и automations; создаётся `scripts/setup-gap-audit.py --write`.
- `seo/setup/setup-answer-plan.md` и `seo/setup/setup-answer-plan.csv` — review-only план ручных правок из заполненного `setup-questionnaire.csv`; создаётся `scripts/setup-answer-plan.py --write`, отклоняет secret-like ответы и не меняет конфиги автоматически.
- `seo/vnext/*.md` и `seo/vnext/*.json` — report-only SEO/AEO/GEO vNext слой: AI Brand Audit, Answer Units, E-E-A-T evidence, GEO KPI, logs/AI bots, technical guardrails, snippets/sitemap, traffic drops, cannibalization, RU commerce/YCP, off-page risk, conversion/SXO и expert source pack; создаётся соответствующими `scripts/*-audit.py` / `scripts/*-model.py` / `scripts/*-readiness.py`.
- `seo/technical/*.md` и `seo/technical/*.json` — инструментальный technical-site слой: `technical-site-audit.py` (rollup), `link-audit.py` (linkinator JSON/live, включая anchors), `redirect-map-audit.py` (CSV redirect map), `gsc-url-inspection.py` (Google URL Inspection export/live read-only), `bing-url-inspection.py` (Bing GetUrlInfo export/live read-only), `technical-mcp-health.py` (optional GSC/GA/Lighthouse MCP readiness), `lighthouse-audit.py` (Lighthouse JSON/live), `serpstat-audit.py` (guarded Serpstat API), `labrika-source-pack.py` и `labrika-health.py` (manual/export/readiness). Live HTTP/API только явным флагом, Serpstat требует `SERPSTAT_API_KEY` и approval на credits.
- `seo/automation-policy.yaml` — какие scheduled automations разрешены, какие требуют approval, какие запрещены без явной policy.
- `seo/automation-policy.generated.yaml` и `seo/automations/automation-recommendations.md` — tool-aware набор автоматизаций по intake/business/market/tool-stack/spend-guard: spend, indexability, search consoles, Bing, schema/CWV, content decay, AI visibility, ecommerce и local; применять через `scripts/automation-recommender.py --apply`.
- `seo/usage/usage-ledger.jsonl` — append-only журнал фактического расхода токенов/USD/API/credits/units/requests/browser minutes; создаётся `scripts/usage-ledger.py report --write`.
- `seo/setup/latest-usage-ledger.md` — текущий месячный отчёт по usage ledger, остаткам и approval/block status.
- `seo/spend-guard.generated.yaml`, `seo/setup/spend-guard.md` и `seo/setup/spend-checklist.csv` — spend/subscription control plane: allowed/approval/blocked по сервисам, остатки лимитов, approval gates, env names и preflight-команды; создаётся `scripts/spend-guard.py --write`.
- `seo/project-intake.yaml` — детальная карта проекта: страны, регионы, поисковики, local/merchant/ads/video/analytics decisions.
- `seo/project-intake-report.md` — человекочитаемый отчёт по intake; создаётся `scripts/project-intake-wizard.py`.
- `seo/project-profile.generated.yaml` и `seo/project-profile-report.md` — сгенерированный overlay/отчёт по intake; применять к `seo-cycle.yaml` только через явный `scripts/project-profile.py --apply`.
- `seo/setup/setup-control-plane.md` — компактная readiness-сводка intake/profile/sources/governance/validation/tool-stack/spend-guard/growth-roadmap/onboarding/setup-blueprint/upgrade/access-key/launch-plan/context-pack/token-waste/provider-health/setup-gap-audit/automation; создаётся `scripts/setup-control-plane.py --write`.
- `seo/setup/latest-task-route.md` — low-token маршрут под последнюю конкретную задачу: фазы, источники, approval gates, blocked actions, automation и context caps; создаётся `scripts/task-router.py --task "..." --write`.

Если файлы есть, они являются локальным контрактом проекта:

- NeuronWriter — основной SERP/NLP редактор для content briefs, terms, entities, questions, competitor scores и финального content scoring, если есть `NEURON_API_KEY`, `seo/scripts/nw.sh` и limits-файл.
- Google Cloud Natural Language — только guarded technical entity audit: entity extraction, salience, syntax/category checks, title/H1/schema/text mismatch. Не описывай его как ranking submission или прямой ranking signal.
- Не запускай whole-site NeuronWriter или Google NLP без конкретной одобренной очереди URL/keywords и достаточного остатка в policy.
- Перед дорогими или широкими задачами запускай `scripts/governance-report.py --format md`: он показывает active sources, budget caps, token policy, missing policy files и approval gates.
- Для первого запуска или handoff используй `scripts/setup-control-plane.py --write`: он собирает low-token readiness report, setup blueprint, upgrade assistant, access-key assistant, project journey, context pack, token-waste audit, Perplexity/NotebookLM/XMLRiver health, setup gap audit и next actions без вывода секретов.
- Для старого проекта сначала запускай `scripts/project-upgrade-assistant.py --write`, затем `scripts/project-upgrade-apply.py --write` для dry-run. Применяй `scripts/project-upgrade-apply.py --apply --write` только после review `upgrade-questionnaire.csv`; он добавляет только missing `policy_files` keys, делает backup и не трогает секреты/платные инструменты/публикацию.
- После setup-control-plane открывай `seo/setup/project-journey.md`: он показывает текущую стадию, чего не хватает для следующего шага, blockers, next command и exit criteria. Не перескакивай на writing/publishing/paid/API/indexing, если journey показывает `current` или `blocked` на более ранней стадии.
- Перед конкретной задачей запускай `scripts/task-router.py --task "<что делаем>" --write` и следуй `seo/setup/latest-task-route.md`; не поднимай полный цикл/сырьё в контекст, если route ограничивает фазы и источники.
- После task-router запускай `scripts/context-pack.py --task "<что делаем>" --write` и открывай `seo/setup/context-pack.md` первым. Переходи к launch/tool-stack/spend/growth reports только если context pack указывает, что они нужны.
- После first-run или изменения policy запускай `scripts/setup-gap-audit.py --write` и закрывай missing fields через `seo/setup/setup-questionnaire.csv` / `seo/setup/setup-gap-audit.md` до широких циклов, платных API/LLM, массового local/ecommerce или automations. После заполнения CSV запускай `scripts/setup-answer-plan.py --write` и применяй только review-safe значения вручную.
- Перед расходом токенов/paid API/credits/ads запускай `scripts/usage-ledger.py check --service <tool> ... --fail-on-block`; после расхода фиксируй `scripts/usage-ledger.py record --service <tool> ...`. Без ledger-записи нельзя считать лимиты управляемыми.
- Перед расходом подписок/paid API/LLM/ads открывай `seo/setup/spend-guard.md`: если сервис `allowed_now=false` или `status=approval_required/blocked`, не запускай его без изменения policy/approval. Используй точную preflight-команду из spend guard.
- Перед Perplexity/NotebookLM/XMLRiver evidence work запускай `scripts/perplexity-health.py --write`, `scripts/notebooklm-health.py --write` и `scripts/xmlriver-health.py --write`. Perplexity использует persistent browser/app сессию, если она доступна, API остаётся optional/paid и disabled by default; NotebookLM — curated expert evidence only, не volume/KD/ranking signal; XMLRiver — approval-gated SERP/Wordstat enrichment. Сбор делай через `scripts/perplexity-collect.py --topic "<тема>" --write`, `scripts/notebooklm-source-pack.py --topic "<тема>" --export-file <file> --write` и `scripts/xmlriver-source-pack.py --query "<запрос>" --engine yandex --input-file <serp.xml> --write`: raw ответы и transcripts сохраняются в `seo/research/raw/`, downstream prompts получают только `seo/research/distillates/*/latest-summary.md` + citations, vector-связи пишутся в `seo/research/vector/source_pack.jsonl`.
- После сборки site-level research package запускай `scripts/research-package-quality.py <package> --write` до передачи в контент/дизайн/разработку. Critical findings (`serp_validation_incomplete`, `semantic_core_url_drift`, missing artifacts) блокируют выбор page type и downstream briefs; high findings (`dirty_semantic_core_queries`, `duplicate_page_briefs`, `orphan_internal_urls`) требуют очистки до handoff.
- При старте работы открывай/выводи `research-package-action-plan.md` или `scripts/research-package-quality.py <package> --format plan`: это обязательный пошаговый план действий, а не справочный отчёт.
- Если package quality или внешний аудит нашли repair findings, сначала запускай единый repair layer: `scripts/research-package-repair.py <package> --write`. Если нужен точечный режим, бери конкретные команды из `research-package-action-plan.md`: `semantic-core-clean.py`, `semantic-core-resync.py`, `entity-map-sync.py`, `google-nlp-aggregate.py`, `orphan-url-resolver.py`, `serp-validation-plan.py`, `spoke-opportunity-audit.py`, `entity-graph-quality.py`. Если SERP проверили во внешнем инструменте, импортируй только reviewed export: `scripts/serp-validation-import.py <package> --input-json serp-export.json --write` или `--input-csv serp-export.csv --write`; live API здесь не вызывается, non-empty validation не перезаписывается без `--force`. После любого repair/import повторяй quality gate до генерации новых page briefs; `project-journey.py` блокирует путь, если `research-package-repair.json` свежее `research-package-quality.json`.
- Для MVP/P1 страниц после прохождения research-package gate запускай `scripts/page-outline-v3.py <package> --all-mvp --write` или `--priority P1 --write`. Это обязательный мост между макро-пакетом (semantic core, clusters, site architecture) и writing phase: не писать/публиковать страницу только по скелетному `mvp-page-briefs.md`. В `copywriter-ready/*.md` и `metrics_rollup` копирайтер получает структуру, volume/clicks/impressions/priority/top supporting keywords, FAQ guidelines, visual inventory и source slots без чтения CSV; `page-outline-v2.py` используй только для legacy.
- Сразу после `page-outline-v3.py` запускай `scripts/page-outline-quality.py <package> --version v3 --write --format markdown` и следуй его action plan. Writing/design/schema/publishing blocked, пока `page-outline-quality.json` отсутствует, не `outline_version=v3`, или status не `pass`; `project-journey.py --write` тоже покажет этот стопор как текущий шаг `deep_page_briefs_v3`.
- Для черновика используй `copywriter-ready/*.md`, `copywriting_playbook` и `writer_prompt_packet` из `page-outline-v3` как основной low-token handoff: они задают reader state, tone contract, angle stack, draft sequence, forbidden actions и acceptance gate. Пиши черновик в `<package>/drafts/<slug>.md`; после черновика запускай `draft-quality-gate.py <draft.md> --outline <page-outlines-v3/slug.json> --write`; raw research, CSV и full SERP загружай только если source slot или fact-check queue просит конкретный источник. `project-journey.py` не пускает к implementation/publishing, пока `content_draft_gate` не видит draft markdown и 0 error/critical findings.
- NeuronWriter после v3 — не безусловный автописатель. Он используется как guarded SERP/NLP/scoring/evaluate/import слой: перед запуском делай `usage-ledger.py check --service neuronwriter --category paid_api --content-writer 1 --ai-credits 500 --fail-on-block`, затем при необходимости `nw-cli.sh new/get/evaluate/import`, после расхода фиксируй `usage-ledger.py record`. Если NeuronWriter недоступен или не одобрен, draft можно делать из `copywriter-ready` через Codex/копирайтера, но draft-quality-gate остаётся обязательным.
- Перед подключением новых API/кабинетов/тегов/ads или переносом проекта в новый регион запускай `scripts/tool-stack-recommender.py --write`: он разделяет бесплатные read-only источники, approval-only paid/quota/LLM/index-submission и forbidden/disabled tracking для РФ. `--apply` только после review, без секретов.
- Перед широким циклом или маркетинг-задачей запускай `scripts/growth-roadmap.py --write` и начинай с `seo/setup/growth-roadmap.md`: он ограничивает работу top-N действиями и привязывает технику, контент, local/ecommerce, AI visibility, CRO и автоматизации к approval gates.
- Перед первым запуском проекта открывай `seo/setup/onboarding-playbook.md`: он отделяет действия агента от human-secret ввода и approval steps. Секреты храни только в `.env`/кабинетах, не в playbook.
- Перед чтением подробных setup-отчётов открывай `seo/setup/context-pack.md`, затем `seo/setup/project-journey.md`, затем `seo/setup/setup-blueprint.md`, `seo/setup/upgrade-questionnaire.csv` и `seo/setup/access-key-assistant.md`, затем `seo/setup/setup-questionnaire.csv` / `seo/setup/setup-gap-audit.md`, после заполнения CSV — `seo/setup/setup-answer-plan.md`, затем `seo/setup/launch-plan.md`: context pack ограничивает текущую задачу, project journey показывает текущую стадию и next command, blueprint показывает точечную матрицу проекта, upgrade assistant показывает новые функции для старых проектов, access-key assistant показывает только нужные ключи, questionnaire показывает что заполнить, answer plan показывает куда вручную внести review-safe ответы, launch-plan даёт первый экран проекта. Загружай `tool-stack`, `growth-roadmap`, `onboarding` и policy-файлы только если context pack/journey/blueprint/launch-plan указывают на нужный блок.
- Для SEO/AEO/GEO vNext запускай report-only команды: `expert-source-pack.py --write`, `ai-brand-audit.py --write`, `answer-units-audit.py --write`, `eeat-evidence-map.py --write`, `geo-kpi-model.py --write`, `technical-guardrails-audit.py --write`, `snippet-sitemap-audit.py --write`, `traffic-drop-diagnostics.py --write`, `cannibalization-audit.py --write`, `log-bot-audit.py --write`, `ai-bot-access-check.py --url https://example.com/ --write`, `ru-commerce-readiness.py --write`, `offpage-risk-audit.py --write`, `conversion-sxo-audit.py --write`. Для инструментальной технички запускай `link-audit.py --input-json linkinator.json --write`, `redirect-map-audit.py --input redirects.csv --write`, `gsc-url-inspection.py --input-json gsc-url-inspection.json --write`, `bing-url-inspection.py --input-json bing-url-info.json --write`, `lighthouse-audit.py --input-json lighthouse.json --write`, `serpstat-audit.py --write` или `--live` только после credit approval, `labrika-source-pack.py --export-file labrika.md --write`, `labrika-health.py --write`, затем `technical-site-audit.py --write`. Сырые transcript/log/CSV/JSON держи на диске; в контекст бери markdown/json distillate. Live AI bot/link/Lighthouse/GSC/Bing checks запускай явно, потому что они делают публичные HTTP/API-запросы.
- Перед созданием schedule-артефактов запускай `scripts/automation-recommender.py --write`: он предлагает безопасные planned automations на базе tool-stack/spend-guard; `--apply` только после review generated policy. Не включай `create_schedules` без явного `--allow-schedules`.
- Для запланированных автоматизаций используй `scripts/automation-plan.py`: сначала `--write --include-disabled`, затем ручной review `seo/automations/*`; новые задачи должны оставаться report-only/dry-run или env-gated до явного approval; `--install-cron` только если governance и automation-policy разрешают schedules.
- Для детальной настройки нового проекта используй `scripts/project-intake-wizard.py --interactive --write`; для автозаполнения из `seo-cycle.yaml` — `--defaults --write`.
- Для точечной настройки нового проекта используй `scripts/project-profile.py --write`: он выводит recommended engines/sources/marketing/governance по `seo/project-intake.yaml`; `--apply` делает backup и обновляет `seo-cycle.yaml`.
- Оптимизация токенов обязательна: сырьё сохраняй на диск, в контекст загружай только distillates/top-N; не читай raw CSV/JSON целиком, если `governance.token_policy.raw_data_in_context=false`.
- Для контроля расхода контекста запускай `scripts/token-waste-audit.py --write` после широкого сбора или перед handoff: findings по raw/large artifacts закрывай через distillates/latest-summary, а не чтением raw в модель.
- XMLRiver — optional paid SERP/Wordstat enrichment provider для Google/Yandex blocks, Wordstat New, ads/shopping/maps/suggest/AI Overview. По умолчанию используй `xmlriver-source-pack.py --input-file`; live только `--live --allow-paid` после `spend-guard.py` и `usage-ledger.py check`. Ключи только в `.env`: `XMLRIVER_USER_ID`, `XMLRIVER_API_KEY`; отчёты показывают только env names.
- Robots/Content-Signal — отдельная техническая политика: `search=yes, ai-input=yes, ai-train=no` означает "можно показывать в поиске и AI-ответах, нельзя использовать для обучения". Если SEO plugin ломает `robots.txt` PHP warning'ом, сначала отключи/почини источник генерации, затем проверь чистый публичный `robots.txt`.
- Для РФ/российских проектов не добавляй зарубежные analytics/tracking tags или pixels без явного разрешения в policy. GSC, Bing Webmaster, PageSpeed/CrUX, sitemap/robots checks и off-site API audits допустимы, потому что не требуют установки аналитического кода на сайт.
- Никогда не выводи API keys, OAuth tokens, service-account JSON или значения `.env`; используй только имена переменных и пути к файлам.

## Optional AI/dev support toolchain

Если задача касается развития самого `seo-cycle`, больших рефакторингов, evidence ingestion или построения графов знаний, можно использовать локальный support-набор:

```bash
bash ~/.codex/skills/seo-cycle/scripts/install-ai-toolchain.sh --codex
```

Назначение:

- GitHub Spec Kit (`specify`) — только для крупных изменений в коде/архитектуре: constitution/spec/plan/tasks/implementation. Не использовать как замену SEO-фазам.
- Microsoft MarkItDown (`markitdown`) — trusted local ingestion: PDF/XLSX/DOCX/PPTX/HTML/YouTube в Markdown перед fact-check/evidence extraction. Не передавать ему непроверенные пользовательские URL без явного разрешения.
- Graphify (`graphify`) — mixed graph по коду, docs, markdown, research artifacts и media; полезен для cross-project knowledge graph и связи docs/code/research.
- CodeGraph (`codegraph`) — local code-symbol graph и Codex MCP для навигации по коду без массового чтения файлов.
- NotebookLM MCP (`notebooklm`) — gated bridge к curated expert knowledge base пользователя. Подключать только через `install-ai-toolchain.sh --codex --notebooklm`, после Google `setup_auth`, и использовать ответы только с citations/source excerpts. Не считать NotebookLM прямым ranking signal; это synthesis из загруженных пользователем источников.

Не ставить по умолчанию и не использовать без отдельного решения: CloakBrowser/CloakMCP и другие stealth/anti-bot инструменты; paid APIs; memory-сервисы, которые уводят данные во внешний сервис. Для SEO-сбора соблюдай robots, rate limits, project policy и source terms.

## Модульная архитектура (фазовые скиллы + state)

`seo-cycle` — **диспетчер**. Фазы постепенно выносятся в самостоятельные шарибельные фазовые скиллы, координируемые через единый файл состояния `seo/cycles/<тема>/_state.json` (контракт `scripts/cycle-state.py`). Это «цепочка передачи»: каждый фазовый скилл читает state на входе, делает своё, обновляет state на выходе, разблокируя следующую фазу.

Вынесено (пилот): **`seo-keywords`** — Phase 2-3 (сбор семантики + кластеризация), самостоятельный скилл.

> **Статус: дробление заморожено на пилоте (решение 2026-05-30).** Монолитный `seo-cycle` со всеми 10 фазами — **основной и полностью рабочий**. Остальные фазы (`seo-entity-map`, `seo-writing`, `seo-publishing`, `seo-monitoring`) **НЕ выносить** без явной потребности (продажа модулей / команда / переиспользование вне цикла / параллелизм). Для не-вынесенных фаз действуй по их описанию ниже в этом файле — это норма, а не временное состояние.

Как диспетчер ведёт цикл:
```bash
python3 scripts/cycle-state.py init --topic "<тема>"   # создать цикл + _state.json
python3 scripts/cycle-state.py next                      # какие фазы разблокированы
# → вызвать соответствующий фазовый скилл (напр. seo-keywords)
python3 scripts/cycle-state.py gate <phase>              # проверить quality-gate
python3 scripts/cycle-state.py show                      # прогресс цикла
```
Перед передачей фазы дальше диспетчер проверяет **quality-gate** (артефакт готов/непуст + фаза-специфичные проверки). Независимые фазы (где `depends_on` уже `done`) можно запускать параллельно. Управление «улучшением» — на данных: `source-attribution.py` + `triggers-eval.py`, **без** авто-переписывания кода.

Для фаз, ещё не вынесенных в отдельные скиллы, действуй по их описанию ниже в этом файле.

## Единый CLI (`seo-cycle`)

`install-codex.sh` ставит symlink `~/.local/bin/seo-cycle` → `bin/seo-cycle`. Это тонкий диспетчер над скриптами (полный passthrough аргументов, exit-коды и stdout-контракты не меняются). Предпочитай его прямым `python3 scripts/...`-вызовам в инструкциях пользователю:

```bash
seo-cycle status                 # = project-journey: стадия, blockers, следующие команды
seo-cycle doctor                 # первый шаг диагностики: config/journey/spend/ledger/provider health
seo-cycle loop <target> <path>   # автоцикл качества (см. секцию ниже)
seo-cycle gate research-package|outline|draft [...]
seo-cycle repair <package> --write
seo-cycle approvals | approve <id> | reject <id>
seo-cycle ads health|fetch|analytics|draft|apply [...]
seo-cycle rag index --write | rag query "<вопрос>" [--global]
seo-cycle run "<задача>"         # task-router; run monthly [...]; run script <name> [...]
```

## Автоцикл качества (loop-runner)

**Вместо ручной пары «gate → repair → gate» всегда используй `seo-cycle loop`** (`scripts/loop-runner.py`). Он сам гоняет проверку и ремонт до прохождения, максимум `governance.loop.max_attempts` попыток (default 5; per-target: research_package 5, page_outline 3, draft 3), ведёт журнал `seo/loops/<loop-id>.json/.md` (виден в project-journey) и делит findings на классы качество/достоверность.

```bash
seo-cycle loop research-package seo/research-package        # machine repair внутри
seo-cycle loop draft <draft.md> --outline <outline.json>    # LLM-protocol
seo-cycle loop page-outline <package>                        # LLM-protocol
# опционально: --phase keywords --cycle-dir <dir> → при успехе cycle-state set --gate-passed
```

Протокол для модели (exit-коды):
- **0 passed** — цель прошла gate; двигайся дальше по journey.
- **3 awaiting_llm** — stdout содержит JSON `{"action_required": "llm_repair", findings, instructions}`. Выполни instructions (перепиши драфт / перегенерируй outline, устрани каждый finding), затем запусти команду с `--resume`. НЕ превышай лимит попыток и не обходи loop прямыми вызовами gate.
- **1 escalated** — лимит исчерпан или нет прогресса (два одинаковых fingerprint подряд). Создан approval-тикет `loop_escalation` + Telegram alert. Остановись, покажи пользователю `seo/loops/<id>.md` и жди решения человека; продолжение — только `--reset` после его правок.
- **2 config error** — почини вызов/конфиг.

Самопроверки: класс `evidence` (eeat_evidence_missing, serp_validation_incomplete, missing_proof_slot, unsafe_first_person_expertise, …) — это честность/достоверность: такие findings нельзя «дожимать» переформулировкой, только реальными источниками и фактами.

## Самооценка результатов (scorecard, обязательна)

**После каждой содержательной задачи ставь честную оценку 0–10 в двух местах: в ответе пользователю и в scorecard проекта.** Loop-runner делает это сам (passed/escalated); всё остальное — руками:

```bash
seo-cycle score record --tool <task-name> --score 8.5 \
  --done "что сделано" --done "ещё пункт" \
  --missing "чего не хватает" [--status done|partial|failed]
seo-cycle score show               # таблица последних оценок (видна и в journey)
seo-cycle score record --tool gate --findings-json <report.json>  # авто-оценка из findings
```

Правила честной оценки: 10 = сделано полностью и проверено; каждая нерешённая критика −3, ошибка −2, warning −0.75 (та же формула, что в `score_from_findings`). Не завышай: «частично» = `--status partial` со списком `--missing`. В чате всегда дублируй кратко: «Оценка: 8.5/10 — сделано X, Y; не хватает Z».

## Платная реклама (полуавтомат, approval-only)

Слой выключен по умолчанию (`ads.enabled: false`). Порядок: `ads health` → `ads fetch` (read-only; default кэш/`--input-file`, live только с `--live` после `seo-cycle spend` и ledger-preflight) → `ads analytics` (SEO+PPC кросс-правила: органика в топ-3 ↔ ставки, конверсионные search terms вне ядра, CPA/ROAS, wasted spend → минус-слова) → `ads draft --create-ticket` (черновики кампаний из семантического ядра, бюджеты = 0 by design) → human approve → `ads apply --ticket <id> --live --allow-write` (только Директ в v1, sandbox-first, кап операций).

Для `region_profile: ru` Google Ads в статусе `region_limited` — **это норма, не ошибка**: primary канал Директ, а Google-драфты экспортируются в Google Ads Editor CSV.

## Локальный RAG (перед написанием и ресёрчем)

`seo/rag.db` (FTS5/BM25, русский из коробки, embeddings опциональны через env `EMBEDDING_API_*`). Индексирует source packs, entity triplets, дистилляты и драфты. Перед Phase 4/6 запроси контекст:

```bash
seo-cycle rag query "<primary keyword>" --top-k 5 --source-type source_pack --source-type distillate
seo-cycle rag query "<сущность>" --global          # пересечения с другими проектами агентства
python3 scripts/page-outline-v3.py <pkg> --all-mvp --rag --write   # брифы с related_passages
```

Индекс обновляй `seo-cycle rag index --write` после новых distillates/drafts (инкрементально, дёшево). Кросс-проектный: `rag index --global` по projects-registry.

## Когда запускать

Триггеры:
- «запусти полный SEO-цикл / SEO-стратегию для X»
- «продвинь раздел / категорию / тему Y с нуля»
- «семантическое ядро + контент-план + публикация»
- «расширь блог под кластер»
- «мониторинг и план итераций»
- «универсальный SEO под мой проект»
- «настрой seo-cycle для нового проекта»

## Когда НЕ запускать

- Одношаговые задачи — напрямую к скиллам:
  - Только Entity Map → `emwoody-semantic-brief` (или универсальный fallback)
  - Только публикация одного готового материала → `emwoody-publish-*` или CMS-специфичный скилл
  - Только аудит → агент `seo-auditor`
  - Только проверка стоп-слов → `scripts/check-stop-words.py`
- Если пользователь даёт уже готовый Entity Map / contentbrief — переходи сразу на нужную фазу.

---

## Архитектура

```
Phase 0  Discovery & Project Setup    (читает seo-cycle.yaml; install wizard если конфига нет)
Phase 1  Site Audit                   (config-driven — какие тулы, какой CMS)
Phase 2  Keyword Research             (multi-source: только enabled-источники из config)
Phase 3  Cluster + Intent Mapping
Phase 4  Entity Map (Шестаков)        (универсальный шаблон, адаптирован под industry)
Phase 5  Content Plan                 (hub-and-spoke, учёт project_type)
Phase 6  Writing                      (tone of voice, stop-words, stock-first, fact-check)
Phase 7  Publishing                   (CMS-aware: WordPress / Shopify / static / ...)
Phase 8  JSON-LD & Schema             (тип схемы по project_type)
Phase 9  Monitoring                   (GSC + Я.Вебмастер + Метрика + GA — по enabled-источникам)
Phase 10 Iteration                    (cycle continues)
```

Каждый запуск создаёт каталог `<cycles_root>/<topic>-<YYYY-Qx>/` с артефактами по фазам.

---

## Phase 0 — Discovery & Project Setup

**Цель:** загрузить конфиг проекта или запустить install wizard.

**Шаги:**
1. Найти `seo-cycle.yaml` в проекте (поиск: `./seo-cycle.yaml` → `./.seo-cycle.yaml` → `./seo/seo-cycle.yaml` → `./.claude/seo-cycle.yaml`).
2. Если **не найден** — запусти `bash ~/.codex/skills/seo-cycle/scripts/init-project.sh` (интерактивный wizard: базовые поля + governance + image workflow + optional detailed intake → готовый yaml + .env.example). Wizard обязан записать `images.*`: featured/inline ratios, WebP width/quality, source_policy, visual_style, captions/alt policy, lazy-loading policy и upload env для `wp-photo-image.py`, а также создать `seo/project-intake.yaml`, `seo/project-intake-report.md`, `seo/setup/setup-control-plane.md`, `seo/setup/project-journey.md`, `seo/setup/project-journey-checklist.csv`, `seo/setup/context-pack.md`, `seo/setup/token-waste-audit.md`, `seo/setup/perplexity-health.md`, `seo/setup/notebooklm-health.md`, `seo/setup/xmlriver-health.md`, `seo/setup/setup-blueprint.md`, `seo/setup/setup-matrix.csv`, `seo/setup/upgrade-assistant.md`, `seo/setup/upgrade-questionnaire.csv`, `seo/setup/access-key-assistant.md`, `seo/setup/access-key-assistant.csv`, `seo/setup/setup-gap-audit.md`, `seo/setup/setup-questionnaire.csv`, `seo/setup/launch-plan.md`, `seo/setup/launch-checklist.csv`, `seo/setup/spend-guard.md`, `seo/setup/spend-checklist.csv`, `seo/setup/latest-task-route.md`, `seo/setup/latest-usage-ledger.md`, `seo/tool-stack.generated.yaml`, `seo/setup/tool-stack-report.md`, `seo/growth-roadmap.generated.yaml`, `seo/setup/growth-roadmap.md`, `seo/setup/onboarding-playbook.md`, `seo/setup/onboarding-checklist.csv`, `seo/vnext/*.md/json`, `seo/technical/*.md/json` и `seo/automations/automation-recommendations.md`. После заполнения `setup-questionnaire.csv` запусти `scripts/setup-answer-plan.py --write`.
3. Если **найден** — провалидировать: `python3 ~/.codex/skills/seo-cycle/scripts/validate-config.py <path>`.
4. Прочитать `context_files` из конфига (обычно `CLAUDE.md`, brand guidelines).
5. Определить **режим цикла** (`mode` в конфиге, default `standard`):
   - `standard` — обычный цикл по всем 10 фазам
   - `migration` — миграция домена/CMS (см. `docs/migration-planner.md`, расширяет Phase 0/1)
   - `programmatic` — массовая генерация страниц по шаблону (Phase 4 заменяется на Phase 4P, см. `templates/programmatic-page.template.md`)
6. Уточнить у пользователя цель текущего цикла (1-3 вопроса):
   - Что продвигаем: категорию / кластер блога / тему / весь сайт?
   - Сроки: разовая кампания или регулярный цикл?
   - Глубина: только семантика, до publish, или до monitoring?
7. Зафиксировать low-token маршрут текущей задачи:
```bash
python3 ~/.codex/skills/seo-cycle/scripts/task-router.py --task "<цель пользователя>" --write
```
Затем собрать context pack и читать его первым:
```bash
python3 ~/.codex/skills/seo-cycle/scripts/context-pack.py --task "<цель пользователя>" --write
```
Открывай `seo/setup/context-pack.md`, затем при необходимости `seo/setup/latest-task-route.md`; запускай только фазы/источники из маршрута, соблюдая approval gates и context caps.
8. Перед фактическим расходом сделать preflight и после запуска записать расход:
```bash
python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py check --service openai --category llm --usd 0.25 --input-tokens 5000 --output-tokens 1000 --fail-on-block
python3 ~/.codex/skills/seo-cycle/scripts/usage-ledger.py record --service openai --category llm --usd 0.25 --input-tokens 5000 --output-tokens 1000 --task "<цель пользователя>" --write
```
9. Сгенерировать и проверить рекомендации автоматизаций:
```bash
python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --write
# после review: python3 ~/.codex/skills/seo-cycle/scripts/tool-stack-recommender.py --apply
python3 ~/.codex/skills/seo-cycle/scripts/growth-roadmap.py --write
python3 ~/.codex/skills/seo-cycle/scripts/setup-onboarding.py --write
python3 ~/.codex/skills/seo-cycle/scripts/setup-blueprint.py --write
python3 ~/.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write
python3 ~/.codex/skills/seo-cycle/scripts/access-key-assistant.py --write
python3 ~/.codex/skills/seo-cycle/scripts/setup-gap-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/setup-answer-plan.py --write  # после заполнения setup-questionnaire.csv
python3 ~/.codex/skills/seo-cycle/scripts/launch-plan.py --write
python3 ~/.codex/skills/seo-cycle/scripts/spend-guard.py --write
python3 ~/.codex/skills/seo-cycle/scripts/token-waste-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/perplexity-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/notebooklm-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/xmlriver-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/perplexity-collect.py --topic "<тема>" --write
python3 ~/.codex/skills/seo-cycle/scripts/notebooklm-source-pack.py --topic "<тема>" --export-file <export.md> --write
python3 ~/.codex/skills/seo-cycle/scripts/expert-source-pack.py --write
python3 ~/.codex/skills/seo-cycle/scripts/ai-brand-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/answer-units-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/technical-guardrails-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/link-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/redirect-map-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py --write
python3 ~/.codex/skills/seo-cycle/scripts/bing-url-inspection.py --write
python3 ~/.codex/skills/seo-cycle/scripts/lighthouse-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/technical-mcp-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/labrika-source-pack.py --write
python3 ~/.codex/skills/seo-cycle/scripts/labrika-health.py --write
python3 ~/.codex/skills/seo-cycle/scripts/technical-site-audit.py --write
python3 ~/.codex/skills/seo-cycle/scripts/automation-recommender.py --write
# после review: python3 ~/.codex/skills/seo-cycle/scripts/automation-recommender.py --apply
```

**Маркетинг-стратегия (если `marketing.enabled` и цель шире SEO):** оценить, нужна ли платная реклама или хватит органики+локалки — `prompts/marketing-strategy.md` + `scripts/roi-calc.py` (воронка/ROI/ДРР по каналам). Реклама — только при дефиците объёма с ROI>0. Каналы дистрибуции и маркетплейсы — `prompts/distribution-channels.md`. Единый план — `prompts/marketing-calendar.md`.

**Выход:** `<cycles_root>/<topic>/00-discovery.md` с зафиксированными целями и snapshot config (+ `marketing-strategy.md` при маркетинг-цели).

---

## Phase 1 — Site Audit

**Цель:** понять текущее состояние сайта по выбранным поисковикам.

**Делегировать:** `delegate.audit` из config (по умолчанию `seo-auditor` агент).

Доп. техн. аудит (если включено): `delegate.technical_audit` (`claude-seo:seo-technical`).

**Что проверять (универсально):**
- Индексация (XML sitemap, robots.txt, canonical)
- Чистота `robots.txt`: без PHP warnings/HTML, без случайных Bricks preview/editor URLs, без плагиновых Content-Signal строк, противоречащих policy
- Шаблонные следы (демо-контент, пустые `href="#"`, lorem ipsum)
- Служебные страницы в индексе (cart, checkout, my-account для ecommerce)
- Скорость / Core Web Vitals
- Существующий контент: какие страницы есть, какие пустые
- Schema markup: что уже стоит

**Project-type-specific:**
- `ecommerce` → проверка карточек товара, категорий, фильтров
- `blog` → структура архивов, тегов, авторов
- `local_business` → LocalBusiness schema, NAP-консистентность
- `saas` → лендинги фич, документация, /pricing

**Локальный аудит (если есть `business_profile.gbp_url`/`yandex_business_url` или офлайн-точка):**
Сравнить с топ-3 конкурентами (`business_profile.competitors`) на **обеих** картах по чек-листу — это быстрые победы локального SEO:
- **Категории/рубрики** — что есть у конкурентов, но не у нас (Google Categories + рубрики Яндекс.Бизнес/2ГИС).
- **Отзывы** — число, оценка, скорость (план догона: `scripts/review-velocity.py`).
- **Публикации** — частота постов конкурентов (GBP Posts + Яндекс.Бизнес Новости).
- **Фото** — количество/типы/качество.
Тактики и промпты — `prompts/local/` (`google-maps.md` + `yandex-maps.md`), оба рантайма через браузер. Для РФ приоритет Яндекс.Карты + 2ГИС.

**Конкурентный анализ + ICE:** свести данные конкурентов (Serpstat/SpyFu/Keys.so/local/GSC) в приоритизированный список быстрых побед — метод `prompts/competitor-analysis.md` (7 шагов) + `scripts/ice-score.py` (Impact×Confidence×Ease). Топ quick-wins → в roadmap (Phase 3/5) и `keyword-queue`.

**Выход:** `01-audit.md` (+ `local/` подкаталог при локальном аудите, `competitor-analysis.md` при конкурентном) со списком проблем по приоритетам (P0/P1/P2 или ICE).

---

## Phase 2 — Keyword Research (Multi-source, config-driven)

**Цель:** собрать полное семантическое ядро под тему **из всех активных источников региона**.

**Шаг 0 — развернуть источники региона (обязательно, один раз):**
```bash
python3 ~/.codex/skills/seo-cycle/scripts/resolve-sources.py
```
Скрипт читает `region_profile` из конфига (`ru`/`eu`/`us`/`global`), мёрджит с локальными `sources.*` override и печатает финальный список активных источников + пропущенных с причиной (напр. «ahrefs недоступно в регионе», «dataforseo через прокси»). Артефакт: `seo/cycles/<date>/active-sources.json`. **Запускай только источники из этого списка** — это и экономит токены, и не даёт дёрнуть инструмент, недоступный в регионе. Если в конфиге нет `region_profile` (legacy) — скрипт отдаёт `sources.*.enabled` как есть.

**Экономия токенов (обязательные правила Phase 2):**
- **Кэш:** дорогой сбор (Wordstat/NW/LLM-CLI/suggest/ATP) не перезапускай, если свежий результат (< `research_cache_ttl_days`, дефолт 14) уже лежит в `seo/research/.../results/`. `llm-cli-collect.sh` проверяет это автоматически через `research-cache.py`.
- **Сырьё — на диск, дистиллят — в контекст.** В свой контекст подтягивай **только** сведённый `*-merged-*.md` (и итоговый `02-keywords.md`), а НЕ исходные `*-antigravity-*.md` / `*-codex-*.md` / сырые CSV. Скрипты сами пишут сырьё на диск и возвращают сжатый top-N.
- **Antigravity + Perplexity обязательны для семантики и сущностей.** При сборе ядра и Entity Map всегда используй Antigravity CLI (`agy`) и Perplexity Pro/Deep Research как отдельные источники идей, интентов, вопросов, сущностей и проверяемых фактов. Если источник недоступен технически, запиши это в артефакт как blocker/exception; не выдавай сбор за полный.

### Универсальные источники

#### Group A — Search engines (Яндекс)
*(Только если `yandex` в `engines`)*

| Источник | Тип | Когда |
|---|---|---|
| Wordstat (core) | агент | Всегда — `delegate.yandex_specialist` |
| Wordstat правая колонка + сезонность | browser_mcp | Для сезонных тем |
| Yandex Suggest | script | Long-tail без частот, `scripts/yandex-suggest.py` |
| XMLRiver Yandex SERP/Wordstat | paid API | Только approval-gated enrichment: SERP blocks, колдунщики, коммерческие предложения, цены, подсказки, AI Overview; `scripts/xmlriver-source-pack.py` |
| Yandex SERP blocks | browser_mcp | Related, PAA, Колдунщик |
| Я.Вебмастер «История запросов» | browser_mcp | Реальные данные по сайту (после верификации) |
| Yandex.Картинки suggest | browser_mcp | Image-SEO |
| Я.Бизнес/Карты «запросы для перехода» | dashboard | Локальный бизнес |
| Яндекс.Кью | browser_mcp | PAA-аналог для info-тем |

#### Group B — Search engines (Google)
*(Только если `google` в `engines`)*

| Источник | Тип | Когда |
|---|---|---|
| Google Search Console | API | После 30 дней с публикации |
| Google Trends | script | Сезонность |
| Google Suggest | script | Long-tail |
| XMLRiver Google SERP blocks | paid API | Approval-gated enrichment: organic, PAA/related, KG, ads, shopping, local/maps, news/video/discussions, AI Overview; `scripts/xmlriver-source-pack.py` |
| DataForSEO | paid API | Опционально |
| **Serpstat** | API | Volume/KD/CPC + конкуренты. **Работает с РФ/СНГ** (`g_ru`) — замена Ahrefs/SEMrush там, где они заблокированы. `scripts/serpstat-fetch.py` |
| **SpyFu** | API | Competitor/PPC/SEO домен-аналитика. **Только US/UK/EU — НЕ РФ.** Профили us/eu/global. `scripts/spyfu-fetch.py` |

> **Serpstat — беречь кредиты** (план Appsumo: 1000/мес, 1 req/sec): точечно — KD/volume по главным ключам кластера (`keywords-info`) и competitor gap по hub-категориям (`competitors`, `domain-keywords`). Массовый long-tail — через Wordstat/suggest/LLM-CLI, не через Serpstat. Скрипт сам проверяет остаток (getStats, бесплатно) и кэширует на 30 дней. `stats` — посмотреть остаток в любой момент.

> **SpyFu — беречь бюджет** (Pro: $40 кредита/мес, pay-as-you-go по строкам): дешёвые эндпоинты `domain-stats` (latest, 1 строка) и competitors ($0.20–0.50 CPM); дорогие top-pages ($5 CPM) — избегать. Локальный usage-трекер блокирует при достижении `--budget`. `usage` — сколько потрачено за месяц. Применять для анализа западных конкурентов; для РФ-проектов бесполезен (RU не покрывается).

#### Group C — SERP analysis
| Источник | Тип | Когда |
|---|---|---|
| NeuronWriter | API | SERP terms (если `sources.neuronwriter.enabled`) |

#### Group D — LLM CLI (универсально)
| Источник | Тип | Когда |
|---|---|---|
| **Antigravity** (`agy`) | CLI | Обязательно для семантики, интентов, сущностей и альтернативных формулировок |
| **Codex** (`codex exec`) | CLI | С URL для fact-check, web search |
| **Параллельный запуск + merge** | script | `scripts/llm-cli-collect.sh "<тема>"` |

#### Group E — Public APIs
| Источник | Тип | Когда |
|---|---|---|
| AnswerThePublic | API | Универсальные шаблоны вопросов (для не-RU рынков работает напрямую; для RU — переводим en/us шаблоны) |
| Perplexity Pro | browser_mcp | Обязательно для сущностей с источниками, Deep Research и фактчекинга |
| XMLRiver | paid API | Дешёвый SERP/Wordstat source pack; сначала экспорт/кэш, live только после approval |

### Сведение в единое ядро

После сбора — слить в `02-keywords.md`:

```markdown
| Ключ | Wordstat | GSC impressions | NW priority | Intent | Cluster | Source |
|---|---|---|---|---|---|---|
| ... |
```

**Делегировать:** `delegate.keyword_research` (по умолчанию `seo-keyword-researcher`).

**Веди лог источников:** добавляй ключи в `seo/source-attribution.csv` (`keyword,source,date_added,cluster,target_url`) с пометкой источника. Через 30-60 дней это даст замер эффективности источников в Phase 10 (`source-attribution.py`) — какие источники реально приносят топ, а какие отключить ради экономии.

**Выход:** `02-keywords.md` + raw-экспорты в подкаталогах `02a-...` / `02b-...`.

---

## Phase 3 — Cluster + Intent Mapping

**Цель:** сгруппировать ключи в кластеры под отдельные страницы.

**Делегировать:** `delegate.cluster_analysis` (по умолчанию `claude-seo:seo-cluster`) + `delegate.keyword_research`.

**Intent типы (универсально):**
- Commercial — «купить X», «X цена», «X сравнить»
- Informational — «как», «что такое», «почему»
- Navigational — «бренд X», «адрес склада»
- Transactional — «доставка X», «заказать X»

**Hub-and-spoke:**
- **Hub** — главная страница темы (для ecommerce: категория; для blog: pillar-статья; для SaaS: фич-лендинг)
- **Spokes** — info-страницы под long-tail (статьи блога, FAQ-страницы)

**Выход:** `03-clusters.md` — таблица: cluster / intent / тип страницы / целевой URL.

---

## Phase 4 — Entity Map (методика Шестакова)

**Цель:** для каждой страницы из кластера — Entity Map (entities → relations → intents → structure → keys).

**Делегировать:** `delegate.semantic_brief` (`emwoody-semantic-brief` если есть, иначе универсальный шаблон `templates/entity-map.template.md`).

**Обязательные evidence-источники:** перед фиксацией Entity Map сверяй сущности, интенты, PAA/FAQ и спорные утверждения через Antigravity CLI и Perplexity Deep Research. Сохраняй raw-ответы на диск, а в Entity Map добавляй только дистиллированные сущности с указанием источника. Без этой сверки карта не проходит quality-gate, кроме явно залогированного технического исключения.

**Сначала переиспользуй накопленное:** `seo-cycle rag query "<сущность>" --source-type triplet --source-type source_pack` — уже проверенные триплеты и цитаты этого проекта (с `--global` — соседних проектов агентства) дешевле нового ресёрча.

**Универсальная структура (17 разделов):**
1. Центральная сущность (AEO-цитата 2-3 предложения)
2. Атрибуты (таблица)
3. Связанные сущности (15-20)
4. Тройки отношений (≥12)
5. Явные интенты
6. Скрытые интенты (≥5 страхов/сомнений)
7. PAA вопросы (≥15)
8. Конкуренты (топ-10 SERP)
9. Граф сущностей (визуализация)
10. SERP-фичи (Featured Snippet, Колдунщик, AEO)
11. Структура страницы
12. FAQ (явные + скрытые)
13. Внутренние ссылки
14. Meta-теги (title/description)
15. JSON-LD plan
16. Чек-лист готовности
17. NW evaluate plan

**Frontmatter обязательно (extends по проектам):**
```yaml
target_url:
created:
status: pilot | active | archived
neuronwriter_query_id:
stock_skus: []                  # для ecommerce
fact_check_log: []              # если content_rules.fact_check.enabled
last_fact_check:
```

**Выход:** `04-entity-maps/<slug>.entity-map.md` для каждой страницы.

---

## Phase 5 — Content Plan

**Цель:** roadmap публикаций с приоритетами.

**Делегировать:** `delegate.content_strategy` (по умолчанию `seo-content-strategist`).

**Структура плана:**
- Что: тип страницы (hub/spoke), URL, главный ключ
- Когда: дата, статус (TODO/Drafting/QA/Published)
- Зависимости: какие entity-maps готовы, какие источники собраны
- KPI: целевые impressions / clicks через 90 дней
- Bandwidth: блог N статей/неделю, категории M/месяц

**Выход:** `05-content-plan.md`.

---

## Phase 6 — Writing

**Цель:** написать тексты под Entity Map'ы.

**Делегировать:** `delegate.content_writer` (по умолчанию `seo-content-writer`).

**Перед написанием:** запроси накопленный контекст из локального RAG — `seo-cycle rag query "<primary keyword>" --top-k 5 --source-type source_pack --source-type distillate` (цитаты и факты из проверенных source packs; `--global` для пересечений с другими проектами). Брифы с подмешанными пассажами: `page-outline-v3.py --rag`.

**Универсальные правила (config-driven):**
- Tone of voice — из `tone.*` config
- Stop-words check — если `quality_gates.stop_words_check.enabled`
- AEO абзац в первые 400 символов — если `content_rules.aeo.enabled`
- Stock-first — если `content_rules.stock_first.enabled`
- Brand name discipline (user-facing vs technical) — `project.brand_name_*`
- Локальные сигналы ≥ `content_rules.local_signals.min_per_page`

**QA после написания (обязательная последовательность):**
1. **Stop-words check** (`scripts/check-stop-words.py`)
2. **Fact-check** — обязательно через Perplexity prompts (режим **Deep Research**) + Antigravity CLI cross-check для фактов, сущностей, интентов и спорных формулировок. Результаты записывай в `fact_check_log` frontmatter (claim/source/url/verdict/checked/tool). Если один из инструментов недоступен, не публикуй без записи blocker/exception в лог.
3. **Image visual + alt/caption check** — изображения создаются config-driven из `images.*`. Для фото-подготовки используй `scripts/wp-photo-image.py`: локальное фото/URL → crop по `images.aspect_ratios.*` → WebP по `images.output.*` → WordPress upload через SSH/WP-CLI при необходимости. Inline images должны быть чистыми тематическими фото/визуалами в `images.visual_style`. Не добавляй видимый текст на изображение, если `images.allow_visible_text=false` (SEO/AEO/GEO, схемы, подписи, описания товаров, дисклеймеры каталога) и не используй товарные карточки/коллажи как основной визуал, если пользователь явно не попросил. У каждого недекоративного изображения должен быть естественный `alt`; inline caption обязателен, если `images.captions.inline_required=true`: featured, inline, OG/schema, product/category visuals. Alt и caption описывают изображение и сущность, без переспама ключами и без служебных объяснений. Изображение без alt или inline image без обязательного caption = публикационный blocker.
4. **Stock-first проверка** (если ecommerce)
5. **NW evaluate** (если `sources.neuronwriter.enabled`) — target `quality_gates.neuronwriter_score.min_score`

**E-E-A-T trust-блок (если есть `fact_check_log`):** сгенерируй видимый блок «Источники» в конец статьи —
```bash
python3 ~/.codex/skills/seo-cycle/scripts/eeat-render.py 06-drafts/<name>.publish.md
```
Рендерятся только источники с verdict достоверно/частично; спорные — править формулировку в тексте, а не «подтверждать». Это прямой Trust-сигнал.

**После черновика:** валидация через автоцикл, не разовым гейтом: `seo-cycle loop draft <draft.md> --outline <page-outlines-v3/slug.json>` (exit 3 = переработай по instructions и `--resume`; лимит попыток не превышать).

Публикация только после прохождения всех гейтов.

**Выход:** `06-drafts/` — `*.publish.md`.

---

## Phase 7 — Publishing (CMS-aware)

**Цель:** залить контент на сайт.

Делегирование зависит от `publishing.cms` и `publishing.publish_skills`:

| CMS | Скилл / подход |
|---|---|
| WordPress | REST API + Application Password как основной независимый канал; project-specific publish skills могут оборачивать REST; Novomira/WordPress MCP только если явно подключён для специальных abilities; SSH/WP-CLI fallback для backup/cache/meta/server repairs |
| Shopify | (TBD — Liquid + Storefront API) |
| Webflow | (TBD — CMS Collections API) |
| Next.js/static | git commit в content/ + redeploy |
| custom | по обстоятельствам |

**Универсальный шаги:**
1. Парсинг `publish.md`
2. Backup текущих значений
3. POST в CMS endpoint
4. Featured image / OG картинка (если `images.generator != none` или `images.workflow=photo_first`) через `scripts/wp-photo-image.py`/CMS media workflow + обязательный alt; inline images по `images.inline_min_per_post` и `images.aspect_ratios.article_inline` + обязательный короткий caption, если включён в `images.captions`
5. Schema/meta через SEO plugin endpoint
6. Verify через GET + браузер: публичный HTML не должен содержать недекоративные `<img>` без `alt`, inline images без caption и запрещённые тексты на/под изображениями. Если кеш/оптимизатор/lazy-load подменяет first-screen/above-the-fold inline image на плейсхолдер в браузере, исключи только это критичное inline image из lazy-load (`skip-lazy`/`data-no-lazy` или CMS-аналог) и перепроверь screenshot. Остальные inline images ниже первого экрана оставляй lazy-loaded.
7. Лог в `artifacts.publish_log`

**WordPress channel policy:** не завязывай публикацию только на MCP-сервер. Если `publishing.cms=wordpress`, REST API через Application Password — основной повторяемый путь для постов, страниц, товаров, media, meta и plugin REST endpoints. Novomira/WordPress MCP не включай автоматически; используй только как project-local fallback/extension, когда REST API недостаточно или нужны специальные abilities (например Bricks-структуры). SSH/WP-CLI оставляй для восстановления, purge cache, backup, незарегистрированных REST meta и серверных исправлений.

**Маркетинговый мостик (если `marketing.enabled`):** после публикации — поднять конверсию страницы через плагин `marketing-skills` (`page-cro` / `form-cro` / `popup-cro`). Каналы привлечения/удержания (`paid-ads`, `social-content`, `email-sequence`, `referral-program`) — **с РФ-адаптацией** (Яндекс.Директ / VK / Telegram / Метрика / 2ГИС вместо западных). Карта мостиков и замен каналов — `docs/marketing-bridges.md`.

**Выход:** `07-published.md` — URL + дата каждой публикации.

---

## Phase 8 — JSON-LD & Schema

**Цель:** структурированные данные под выбранные типы страниц.

**Делегировать:** `delegate.schema_markup` (по умолчанию `claude-seo:seo-schema`).

**Типы по `project_type`:**
- `ecommerce`: Product, Offer, AggregateRating (только реальные!), BreadcrumbList
- `local_business`: LocalBusiness + Service + AggregateRating
- `blog`: Article, FAQPage, HowTo, BreadcrumbList
- `saas`: SoftwareApplication, Product, Organization
- Везде: WebSite, Organization, FAQPage (где есть FAQ)

**E-E-A-T: канонический узел организации (обязательно).** Не оставляй `author`/`publisher` голым `{"@type":"Organization","name":...}`. Собери единый узел из `business_profile` и ссылайся на него через `@id`:
```bash
python3 ~/.codex/skills/seo-cycle/scripts/schema-org-build.py build              # посмотреть узел
python3 ~/.codex/skills/seo-cycle/scripts/schema-org-build.py inject schema/*.json  # вставить + переписать author/publisher на @id
```
Узел несёт trust-сигналы (address, telephone, openingHours, areaServed, knowsAbout, sameAs) — это то, что связывает контент с реальным бизнесом и усиливает Authoritativeness/Trust. Инжект идемпотентен. Требует секцию `business_profile` в конфиге.

**Запрет:** фейковые рейтинги и отзывы. Если нет реальных — не делай AggregateRating. `same_as` — только подтверждённые профили.

**Выход:** `08-schema.md`.

---

## Phase 9 — Monitoring

**Цель:** регулярные снапшоты позиций / трафика / поведения.

**Делегировать:**
- `delegate.google_data` (`claude-seo:seo-google`) — GSC + GA4 + CrUX (если включено)
- `delegate.yandex_specialist` — Я.Вебмастер + Метрика (если включено)

**Cadence:** 2-недельные снапшоты в `09-monitoring/YYYY-MM-DD-snapshot.json` + markdown-надстройка `*.md` по `templates/monitoring-report.template.md`.

**Локальный мониторинг (если локальный бизнес):** раз в месяц снимать прогресс vs конкуренты на обеих картах — скорость отзывов (`review-velocity.py`), новые категории/рубрики, частота постов, прирост фото. Промпты — `prompts/local/`. Отставание → задача в Phase 10.

**Потерянные ключи:** сравнить текущий снапшот с прошлым — `scripts/lost-keywords.py --old <prev> --new <cur>` (выпавшие/просевшие ключи → refresh + перелинковка).

**AI-visibility (GEO):** свод присутствия в Яндекс Нейро / Google AI Overviews / ChatGPT / Perplexity — промпт `prompts/ai-visibility.md` (+ плагины `seo-geo`/`seo-seranking`).

**Медианный бенчмарк по конкурентам:** `scripts/competitor-benchmark.py` — где мы ниже медианы топ-N (ключи/бэклинки/отзывы/посты/фото) → приоритеты в roadmap (ICE).

**Реклама + соцсети:** разведка платной выдачи и соцактивности конкурентов + генерация объявлений/постов (Директ/VK/TG/Дзен) — промпт `prompts/ad-and-social.md`.

**Pipeline (observability hub):**

```
delegate(claude-seo:seo-google) → GSC/GA4 JSON ┐
delegate(yandex-seo-specialist) → Webmaster/   ├→ snapshot-build.py --source X
  Metrika данные                               │   (нормализация в единую schema)
psi-fetch.py URL → PSI JSON                    ┘                  ↓
                                                    09-monitoring/YYYY-MM-DD-snapshot.json
```

**Единая schema `snapshot.json`:** см. `scripts/snapshot-build.py --help`. Поля: `queries[]`, `pages[]`, `cwv{}`, `behavior{}`, `sources[]`. Скрипт умеет мердж нескольких источников в один snapshot через `--merge`.

**Что собирать:**
- Топ-100 запросов: impressions, clicks, CTR, position, дельты
- Топ-страниц: то же + behavior (bounce, time, conversions)
- CWV per URL (PSI) с статусом good/needs_improvement/poor
- Изменения vs прошлый снапшот
- Сезонные сравнения (если есть данные за прошлый период)

**Выход:** `09-monitoring/YYYY-MM-DD-snapshot.json` + `*.md` отчёт по шаблону.

---

## Phase 10 — Iteration (actionable feedback engine)

**Цель:** действовать по данным через декларативные правила.

### Pipeline

```
09-monitoring/YYYY-MM-DD-snapshot.json ┐
config/triggers.yaml                   ├→ triggers-eval.py → 10-iterations.md
(+ опц. project-override triggers)     ┘    (markdown action list по P0/P1/P2
                                             с конкретными URL и запросами)
```

### Команда

```bash
python3 ~/.codex/skills/seo-cycle/scripts/triggers-eval.py \
    09-monitoring/YYYY-MM-DD-snapshot.json \
    ~/.codex/skills/seo-cycle/config/triggers.yaml \
    --output 10-iterations.md \
    --project-yaml ./seo-cycle.yaml   # для project-override правил
```

### Правила в `config/triggers.yaml`

Декларативные `when → action → priority → delegate`. Текущий набор покрывает:

- **Запросы:** low_ctr_in_top_positions, striking_distance, position_drop, high_impressions_no_clicks, new_emerging_query
- **Страницы:** high_bounce_low_engagement, low_engagement_time, high_traffic_no_conversions, orphan_page_low_clicks
- **CWV:** cwv_poor, cwv_needs_improvement, lcp_critical
- **Поведение:** bounce_spike_site_wide
- **Контент-гигиена:** fact_check_stale, page_unchanged_long
- **Бэклинки:** lost_top_backlink, gained_top_backlink

Расширить можно копированием правил в `<project>/seo-triggers.yaml` и указанием `monitoring.triggers_file` в проектном `seo-cycle.yaml`.

### Source attribution (обратная связь по источникам семантики)

Замыкает петлю «откуда брали ключи → что сработало». Раз в квартал (когда накопились данные ≥30-60 дней) сопоставь лог источников со snapshot:
```bash
python3 ~/.codex/skills/seo-cycle/scripts/source-attribution.py \
    --csv seo/source-attribution.csv \
    --snapshot 09-monitoring/<date>-snapshot.json
```
Скрипт покажет, какие источники дают ключи в топ-10, а какие — пустую породу, и пометит кандидатов на снижение приоритета/отключение. Малоэффективный источник → убери из `region_profile` override или `sources_disable`. **Это прямая экономия токенов/времени на следующих циклах.**

> Предусловие: в Phase 2 веди `seo/source-attribution.csv` — помечай, из какого источника пришёл каждый ключ (`keyword,source,date_added,cluster,target_url`).

**Выход:** `10-iterations.md` — приоритизированный action list со ссылками на конкретные URL/запросы + рекомендуемыми делегатами для каждого пункта.

**KPI-контракт («гарантированный результат»):** если в конфиге заполнена секция `kpi` — раз в месяц сверяй план с фактом и держи стратегию на цифрах:

```bash
seo-cycle forecast --write     # сценарии current/top10/top3, upside по кластерам, рампа
seo-cycle kpi --write --escalate   # план vs факт: on_track/at_risk/off_track; off_track → тикет + alert
seo-cycle sync --live --write  # зеркало сайта: что изменилось на сайте, drift против драфтов
```

Corrective actions при отставании берутся из forecast (кластеры с максимальным upside) + стандартные рычаги (quality loop, refresh, lost-keywords, ads analytics). Все допущения модели перечислены в отчёте `seo/strategy/seo-forecast.md` — это простая CTR-модель, не обещание.

---

## Установка под новый проект

Полная инструкция в `INSTALL.md` рядом с этим файлом. Кратко:

1. Скопировать `~/.codex/skills/seo-cycle/config/project.template.yaml` в корень проекта как `seo-cycle.yaml`.
2. Заполнить под свой сайт (язык, регион, поисковики, CMS, источники).
3. Запустить валидатор: `python3 ~/.codex/skills/seo-cycle/scripts/validate-config.py`.
4. Подключить API-ключи в `.env` проекта по списку, который выдаст валидатор.
5. (Опционально) Создать проектные скиллы для специфичных задач (custom publishing, brand-specific entity map) и прописать в `delegate.*`.
6. Запустить: «давай запустим SEO-цикл для категории X».

### Auth-профили: глобально или per-project

Два уровня хранения ключей (приоритет: process env > `.env` проекта > `~/.seo-cycle/env.global`); `seo-cycle` сам подмешивает цепочку в каждый запуск. Логин один раз глобально работает во всех проектах, а клиентские аккаунты конкретного проекта кладутся в его `.env` и перекрывают глобальные:

```bash
seo-cycle auth list                        # кто настроен и откуда (process/project/global)
seo-cycle auth login yandex --global       # общий токен агентства (Метрика/Вебмастер)
seo-cycle auth login gbp                   # OAuth-flow GBP для ЭТОГО проекта (браузер → refresh token в .env)
seo-cycle auth login wordpress             # клиентские креды сайта — всегда per-project
seo-cycle auth set PERPLEXITY_API_KEY --global
```

Секреты не печатаются и не логируются; файлы пишутся с правами 0600.

## Кастомизация под нишу

Адаптация под конкретный проект через:

- **`seo-cycle.yaml`** — основной механизм (язык, поисковики, project_type, источники, tone, content_rules)
- **`content_rules.fact_check`** — отключи для не-технических ниш
- **`content_rules.stock_first`** — только для ecommerce с инвентарём
- **`content_rules.local_signals`** — отключи для глобального B2B SaaS
- **`tone.stop_words_extra`** — добавляй свои запреты
- **Custom prompts** — клонируй `~/.codex/skills/seo-cycle/prompts/*` в `<project>/seo/prompts/` и переопредели
- **Custom delegate** — создавай проектные субскиллы и прописывай в `delegate.*`

См. `docs/adapt.md` для подробной инструкции по адаптации.

## Источники истины (универсальные)

1. `seo-cycle.yaml` — конфиг проекта
2. `<project>/CLAUDE.md` — правила проекта (если есть)
3. `<project>/seo/entities/entities.yaml` — реестр сущностей проекта
4. `~/.codex/skills/seo-cycle/prompts/` — универсальные промпт-шаблоны
5. `<artifacts.research_root>` — результаты исследований (ATP, Perplexity, LLM CLI)
6. `seo/loops/` — журналы автоциклов качества (attempts, delta, эскалации)
7. `seo/ads/` — raw exports, аналитика и драфты платной рекламы
8. `seo/rag.db` — локальный RAG-индекс (`rag-query.py`); глобальный — `~/.seo-cycle/rag/global.db`
9. `seo/logs/` — файловые логи скриптов (`seo-cycle-YYYY-MM-DD.log`)
10. `seo/content-mirror/` — зеркало опубликованного контента сайта + `sync-report` (что изменилось на сайте)
11. `seo/strategy/` — forecast и KPI-контракт (план vs факт, corrective actions)

## Lessons learned (пополняется)

- *Заполняется по ходу реальных запусков на разных проектах.*
- Первый запуск на новом проекте — пройти Phase 0 (wizard) и Phase 1 (audit) полностью, прежде чем приступать к контенту.
- Не включай все источники сразу. Включай постепенно — после подключения каждого API/доступа.
- LLM CLI (Antigravity + Codex) **не заменяют** Wordstat/GSC — они дополняют их идеями и URL-ями для fact-check.

## Версионирование

См. `CHANGELOG.md` рядом с этим файлом.
