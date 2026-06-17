# Changelog — seo-cycle

## [Unreleased]

## [1.63.0] — 2026-06-17

### Staged orchestrator pilot

- Added `scripts/seo-cycle-run.py`, a thin CLI for declarative stage contracts with `stage -> gate -> repair -> rerun -> next stage` control.
- Added `scripts/seo_cycle_core/{stages,gates,repair,orchestrator}.py` as a small core layer for immutable stage contracts, command/output gates, bounded repair loops, blocker reports and latest run summaries.
- Added shared `seo_cycle_core.reports` and `seo_cycle_core.subprocesses` helpers for artifact writes, path stringification, command-step capture and JSON parsing; migrated `task-router.py`, `project-journey.py` and `setup-control-plane.py` onto that shared layer.
- Stage contracts default to five repair attempts and write `seo/orchestrator/<stage>-report.md/json`; exhausted gates write `seo/orchestrator/<stage>-blocker.md/json` with stop conditions and missing artifacts.
- Added a built-in `--goal` pilot route that runs `task-router.py`, then `project-journey.py`, and refreshes `setup-control-plane.py` once when the journey gate is still blocked.
- Added regression coverage for contract defaults, repair/rerun behavior, blocker reports and CLI execution.
- Added `docs/orchestrator.md` and `docs/refactor-v1.63-plan.md` to document the Pifagor SEO skill direction and the safe refactor path.

## [1.62.0] — 2026-06-16

### Project Knowledge Hub

- Added project-local `scripts/knowledge/` workflow: wiki export, report ingestion, compact context packs, preflight checks, content taste gate, decision log, review/comparison cluster planning, API catalog curation, Graphify corpus/graph refresh, and zvec-ready hybrid search.
- Added `knowledge_*` policy paths to `config/project.template.yaml` and setup artifact status, so new projects receive the wiki/Graphify/zvec surface by default and old projects can add missing keys through the upgrade assistant.
- Added `knowledge_hub` to `project-upgrade-assistant.py` as a report-only migration feature. It never stores secrets, publishes content, submits indexing, schedules automations, or calls paid APIs.
- `wiki-refresh-all.sh` now uses generic report candidates and optional `SEO_CYCLE_WIKI_INGEST_REPORTS`, not project-specific dated paths.
- `graphify-refresh.sh` now respects project policy paths, tries Antigravity/Gemini CLI/API backends, and degrades safely when Graphify is not installed.
- `review-cluster-plan.py` now generates default review/comparison candidates from real inventory; project-specific construction or niche comparison seeds live in `seo/knowledge/review-cluster-seeds.json`.
- Added `docs/knowledge-hub.md` with installation, old-project update, preflight, taste gate, Graphify/zvec, override, and quality-control workflow.

### GSC indexing queue and browser workflow

- Added `gsc-indexing-queue.py`: builds a P0/P1 request-indexing queue from Google Search Console discovered/not-indexed exports, sitemap URLs, WooCommerce product/category exports and Search Analytics page metrics.
- Added `gsc-indexing-export-browser.py` plus `gsc-indexing-export-runner.mjs` to capture GSC Pages issue exports through a persistent browser profile and optionally pass the downloaded file straight into the queue builder.
- The queue filters editor/API/cart/checkout/feed/preview/search junk URLs, optionally runs a live HTTP/canonical/noindex technical gate, writes `seo/technical/gsc-indexing-request-queue.csv`, and records a bounded technical report.
- Added `gsc-request-indexing-browser.py` plus `gsc-request-indexing-runner.mjs` for guarded Search Console URL Inspection UI submission through a persistent browser profile. It stores no passwords; actual button clicking requires explicit `--auto-click`.
- Added `gsc-indexing-recheck.py` to re-evaluate submitted URLs after 3-7 days against fresh GSC issue exports, indexed-page exports and/or Search Analytics data.
- Added `indexnow-submit.py` for guarded bulk IndexNow/Bing-compatible URL notifications from the same P0/P1 queue.
- Added `yandex-recrawl-submit.py` for guarded Yandex Webmaster API v4 `/recrawl/queue` submit and queue-status checks from the same P0/P1 queue.
- Wired the new reports into project templates, validation, setup artifact status, technical rollup and docs.

### WriterZen browser automation

- Added `writerzen-health.py` for browser/export readiness without API keys or password storage.
- Added `writerzen-browser-collect.py` and `writerzen-browser-runner.mjs`: the collector uses a persistent browser profile outside project repos, creates WriterZen reports for Topic Discovery / Keyword Explorer / Keyword Planner / Domain Focus, captures CSV/XLSX downloads into `seo/research/writerzen/imports/`, and runs `writerzen-source-pack.py` in the same command.
- Added `writerzen-source-pack.py` to normalize WriterZen browser exports into raw/distillate/vector artifacts with volume/KD/CPC/intent/Buying Journey/SERP Type/Allintitle/KGR fields and cache hits.
- Wired WriterZen into region profiles, project template, setup control plane, tool-stack recommender, access-key assistant, docs and `seo-keywords` as a subscription/browser source.

### NeuronWriter plagiarism gate

- Added `plagiarism_checks` to `usage-ledger.py` so NeuronWriter plagiarism checks can be preflighted and recorded separately from content writer analyses and AI credits.
- `usage-ledger.py` now imports current NeuronWriter used/limit values from `seo/neuronwriter-limits.yaml`, including `content_writer`, `ai_credits`, and `plagiarism_checks`.
- Added guarded `nw-cli.sh plagiarism <query_id> [draft.html]` support with optional `NW_PLAGIARISM_PATH` for account-specific endpoint paths; there is no default undocumented endpoint, so the standard workflow remains `import-content` followed by the NeuronWriter Editor menu plagiarism check.
- Updated project templates and docs so NeuronWriter is the primary plagiarism gate; WriterZen plagiarism is fallback/manual export only.

## [1.59.0] — 2026-06-12

### Orchestrated writing gate

- Added a dedicated `content_draft_gate` stage to `scripts/project-journey.py` between v3 copywriter briefs and implementation/publishing. The journey now blocks until drafts exist and `draft-quality-gate` has no error/critical findings.
- `project-journey.py` now detects `copywriter-ready/*.md`, draft markdown under `<package>/drafts/`, `<package>/06-drafts/`, `seo/drafts/`, or `06-drafts/`, and sibling `<draft>.draft-quality-gate.json` reports.
- The v3 stage now requires actual `copywriter-ready` markdown and treats non-passing v3 outline quality as a blocker before writing.
- The automatic action plan now includes guarded NeuronWriter usage preflight, draft creation from `copywriter-ready`, draft quality validation, optional NeuronWriter evaluation, and a journey rerun before implementation.

## [1.58.0] — 2026-06-12

### Deep Copywriter Brief v3

- Added `scripts/page-outline-v3.py`, a copywriter-ready layer on top of the existing evidence-backed v2 outline. It writes `page-outlines-v3/<slug>.md/json`, `copywriter-ready/<slug>.md`, and `vector/page_outline_triplets.jsonl`.
- v3 enforces SERP-safe page ordering: tool/app/quiz pages start with `tool_ux_above_the_fold`, followed by a short AEO guide and supporting longform below the tool.
- Added section and H3-level copywriter fields: word counts, entities, keywords, summaries, visuals, copywriter notes, entity connections, Answer Units, source slots, and acceptance criteria.
- Extended `page-outline-quality.py` with `--version v3`, v3 discovery, v3-only findings, and extra scorecard criteria for SERP-safe UX and entity/triplet export readiness.
- Updated `project-journey.py` so the modern path routes through `deep_page_briefs_v3` before implementation while preserving v2 compatibility for older packages.

## [1.57.0] — 2026-06-12

### XMLRiver guarded provider

- Added `scripts/xmlriver-source-pack.py` as a guarded XMLRiver adapter for Google/Yandex SERP XML, Yandex Search, and Wordstat New JSON. It ingests exported XML/JSON by default, writes raw/distillate/vector source-pack artifacts, parses organic results, SERP features and Wordstat query groups, and only performs live HTTP with explicit `--live --allow-paid`.
- Added `scripts/xmlriver-health.py` for report-only readiness: env names, secret-free credential status, official price reference, capabilities, and guardrails. `setup-control-plane.py` now runs it with the other provider health checks.
- Wired XMLRiver into `tool-stack-recommender.py`, `access-key-assistant.py`, spend guard via generated tool-stack decisions, project templates, upgrade assistant and docs. It is approval-gated as paid API by default and never prints `XMLRIVER_API_KEY`.
- Added regression coverage for XMLRiver source-pack ingestion, secret-free guarded request plans, provider health, tool-stack recommendations and access-key assistant tasks.

## [1.56.0] — 2026-06-12

### Research package import and outline upgrades

- Added guarded `scripts/serp-validation-import.py` for reviewed DataForSEO/Serpstat/manual SERP exports. It writes validated SERP evidence back into `semantic-architecture-final.json` only from explicit JSON/CSV input, preserves non-empty validation unless `--force` is used, and writes `serp-validation-import.md/json`.
- Added a freshness gate to `project-journey.py`: if `research-package-repair.json` is newer than `research-package-quality.json`, the journey blocks at `research_quality_gate` until quality is rerun.
- Extended `page-outline-v2.py` with `metrics_rollup` per page: matched semantic-core rows, volume, clicks, impressions, priority score and top supporting keywords for copywriters without opening raw CSV.
- Added explicit `page-outline-v2.py --archive-legacy-briefs`, which archives duplicate `page-briefs.md` / `mvp-page-briefs.md` into `archive/legacy-briefs/` only after a successful `--write`.
- Updated project templates, setup/control-plane, upgrade assistant and docs for the v1.56 research-package flow.

## [1.55.0] — 2026-06-12

### Repair orchestration

- Added `scripts/research-package-repair.py`, a one-command repair wrapper that runs semantic-core cleanup/resync, entity-map sync, Google NLP aggregation, orphan URL backlog, SERP validation plan, phase-2 spoke audit and entity graph quality, then writes `research-package-repair.md/json`.
- Updated `research-package-quality.py` remediation and launch action plans to point to exact repair commands instead of generic manual instructions, including the new wrapper.
- Added `research_package_repair` to `project-journey.py` so failed package quality now routes users through a concrete repair stage before deep page briefs.
- Updated Codex runtime and research-package docs to use the full flow: quality gate -> repair layer -> quality rerun -> page-outline v2 -> page-outline quality -> draft quality gate.
- Added regression coverage for repair wrapper execution, exact remediation commands and journey repair routing.

## [1.54.0] — 2026-06-12

### Research package repair layer

- Added repair-layer CLI scripts for the exact comparison-report gaps: `semantic-core-clean.py`, `semantic-core-resync.py`, `entity-map-sync.py`, `google-nlp-aggregate.py`, `orphan-url-resolver.py`, `serp-validation-plan.py`, and `spoke-opportunity-audit.py`.
- Added quality gates for downstream work: `entity-graph-quality.py` validates relation duplicates/orphans and entity weight provenance; `draft-quality-gate.py` checks drafts against page outlines for missing H2/H3, required links, source/proof slots and unsafe first-person expertise.
- Added shared `research_package_repair_core.py` helpers so repair scripts use one CSV/JSON/URL/entity normalization layer and produce stable JSON/Markdown/CSV/JSONL artifacts.
- Added regression coverage for the full repair flow using the comparison-report fixture: dirty GSC cleanup, URL/cluster resync, entity-map parity, Google NLP aggregation, orphan URL backlog, SERP validation planning, phase-2 spokes, entity graph findings and draft gate findings.
- Updated README/GUIDE/SKILL/runbook so the package flow is now: quality gate -> repair layer -> page-outline v2 -> page-outline quality -> draft quality gate.

## [1.53.0] — 2026-06-12

### Draft-ready copywriting handoff

- Extended `page-outline-v2.py` with `copywriting_playbook`: page job, before/after reader state, tone contract, angle stack, draft sequence, banned patterns and a final revision checklist.
- Added `writer_prompt_packet` for low-token drafting handoff: role, input/output contracts, forbidden actions, acceptance gate and starter prompt for the next AI/copywriter step.
- Extended `page-outline-quality.py` so weak outlines now fail when they lack a copywriting playbook, revision checklist or writer prompt packet.
- Updated docs for users and AI agents with the latest package -> outline -> quality -> writing flow and old-project update commands.

## [1.52.0] — 2026-06-12

### Copywriter-grade brief depth

- Extended `page-outline-v2.py` with copywriting-specific brief assets that were still stronger in the comparison outline: `intro_brief`, `conclusion_brief`, H3 subsection plans under every H2, section reader questions, opening angles, do-write/do-not-write rules, safe phrases, source slots, CTA guidance and acceptance criteria.
- Added deterministic H3 word-count allocation: subsection min/max totals must add up exactly to the parent H2, avoiding the competitor outline's word-count arithmetic drift.
- Extended `page-outline-quality.py` with stricter copywriting checks for missing intro/conclusion, missing H3 plans, H3/H2 word-count mismatch, weak copywriting details, missing source slots and missing acceptance criteria.
- Verified generated page outlines still pass the stricter gate at `10.0/10` on the real hair-stylist research package.

## [1.51.0] — 2026-06-12

### Competitor-grade page brief assets

- Extended `page-outline-v2.py` with the useful micro-brief advantages from the competitor outline while keeping seo-cycle's data-backed architecture: answer-first key takeaways, FAQ answer units, numbered visual plan with dedupe keys, section bridges, writer handoff, safe memorable lines, trust/limitations guidance, synthetic AI prompts, and entity weights with an explicit source basis.
- Kept the E-E-A-T guard strict: first-person expertise remains blocked unless `--expert-author` is explicitly used, and generated FAQ/handoff text avoids first-person phrasing that could look like fabricated experience.
- Extended `page-outline-quality.py` so the new assets are enforced by the quality gate: missing takeaways, FAQ, handoff, fact-check queue, visual plan, section bridges, trust limits, or synthetic prompts now produce actionable findings.
- Updated regression coverage so generated outlines must pass the stricter quality gate, while shallow/unsafe outlines fail on the new criteria.

## [1.50.0] — 2026-06-12

### Page outline quality gate

- Added `scripts/page-outline-quality.py`, a 10-criterion page brief validator that catches the comparison-audit failure modes: word-count drift, missing SERP/page-type lock, shallow copywriter handoff, missing SEO meta/schema/internal links, weak Answer Units/GEO, orphan entities, missing visuals, and fabricated first-person expertise.
- Extended `page-outline-v2.py` with SEO meta output: title tag, meta description, slug, canonical and alt-text guidance, so generated briefs are ready for technical SEO review before writing.
- Wired page-outline quality into `project-journey.py`: after MVP/P1 outline generation the automatic journey now requires `page-outline-quality.json`, reports blockers, and shows the exact next command before implementation can start.
- Added page-outline quality policy paths to the project template, setup-control-plane visibility, and project-upgrade assistant so existing projects can adopt the gate through the safe upgrade flow.
- Updated docs and regression tests for generated-outline pass, unsafe-outline failure, and journey blocking before implementation.

## [1.49.0] — 2026-06-12

### Safe old-project upgrades

- Added `scripts/project-upgrade-apply.py`, a safe dry-run/apply helper for old projects. It reads `seo/setup/upgrade-questionnaire.csv`, adds reviewed missing `policy_files` keys from the current template, creates a backup before apply, and never changes secrets, paid tools, schedules, publishing, indexing, or business settings.
- Added project-upgrade-apply policy paths to the project template and setup-control-plane artifact visibility.
- Added project-upgrade-apply to `project-upgrade-assistant.py` so old projects can discover the safer upgrade path.
- Added regression coverage proving dry-run does not edit configs and apply restores reviewed policy keys with a backup.

## [1.48.0] — 2026-06-12

### Project journey gate

- Added `scripts/project-journey.py`, a read-only step-by-step journey gate from setup to monitoring: it reports the current stage, missing artifacts, blockers, next command, exit criteria and a bounded action plan.
- Wired project journey artifacts into `config/project.template.yaml`, `setup-control-plane.py`, and `project-upgrade-assistant.py` so existing projects see the new journey as an upgradeable surface.
- The journey explicitly blocks deep briefs when the research package quality gate fails and prevents agents from skipping setup/research/evidence stages just because later files exist.
- Added regression tests for new-project guidance and failed research-package quality gating.

## [1.47.0] — 2026-06-12

### Research package quality and deep page briefs

- Added `scripts/research-package-quality.py`, a quality gate for site-level SEO research packages that catches the comparison-audit failure modes: empty SERP validation for MVP/checked keywords, semantic-core URL/cluster drift after reclustering, dirty prompt-like GSC rows, duplicate page briefs, orphan internal URLs, entity-map markdown/YAML drift, raw Google NLP duplication and unused AI Overview/GEO signals.
- Added a 10-criterion scorecard, `research-package-action-plan.md`, and `--format plan` so every package run produces a clear automatic next-step checklist with priority, target files, command and definition of done.
- Added an explicit E-E-A-T/evidence gap check for packages that do not define proof, sources, schema/trust signals or no-fabrication rules.
- Added `scripts/page-outline-v2.py` to turn a validated research package into section-level H2/H3 page briefs with computed word-count totals, entities, keywords, visual elements, copywriter notes, Answer Units, evidence requirements, schema, internal links, GEO requirements and a no-fabricated-E-E-A-T guard by default.
- Added batch outline modes: `page-outline-v2.py <package> --all-mvp --write` and `--priority P1 --write`.
- Added `docs/research-package-quality.md` runbook for the package → quality gate → deep page outline pipeline.
- Updated SKILL, README and GUIDE so research packages must pass quality gate before handoff, and MVP/P1 pages should receive a `page-outline-v2` brief before writing/publishing.
- Added regression tests covering the third-party audit findings and the deep outline contract.

## [1.46.1] — 2026-06-06

### Optional WordPress MCP

- Changed Codex bootstrap/init behavior so WordPress/Novomira MCP is not created automatically, even project-locally.
- Added explicit `bootstrap-codex.sh --with-wordpress-mcp` for projects that need WordPress/Novomira MCP.
- Kept `project-mcp-config.py --write` as the manual project-local setup command; global MCP config remains untouched.
- Documented WordPress REST API + Application Password as the primary publishing/admin channel; Novomira MCP is a manual fallback/extension for special abilities.

## [1.46.0] — 2026-06-06

### Project-local Codex and WordPress MCP

- Changed `install-codex.sh` / `bootstrap-codex.sh` to be local-entrypoint by default: shared code updates in `~/.codex/vendor/seo-cycle`, while installed projects get local `./.codex/skills`, `./.agents/skills` and `./.claude/skills` symlinks. Uninstalled projects no longer load/read seo-cycle. Legacy global exposure is available only with explicit `--global-skill`.
- Added `scripts/project-mcp-config.py` to generate a project-local `.codex/config.toml` for WordPress/Novomira MCP without writing secrets. The MCP wrapper reads `WP_API_URL`, `WP_API_USERNAME`, and `WP_API_PASSWORD` from that project's `.env`.
- Wired project-local MCP generation into `init-project.sh` and existing-project bootstrap upgrades.
- Added `.env.example`, README, INSTALL and GUIDE documentation for project-local WordPress MCP.
- Added regression tests that verify MCP config generation preserves existing local config, avoids secret values and skips non-WordPress projects.

## [1.45.1] — 2026-06-06

### Technical run reliability

- Fixed `ai-bot-access-check.py` so crawler checks treat closed HTTP connections as `unreachable` findings instead of crashing.
- Fixed `technical-site-audit.py` so the rollup includes technical vNext reports from `seo/vnext/` such as AI bot access, guardrails and snippet/sitemap audits.
- Added regression tests for closed crawler connections and vNext report aggregation.

## [1.45.0] — 2026-06-06

### Technical SEO Evidence Layer

- Added `scripts/technical-site-audit.py` to aggregate latest technical distillates into one bounded rollup without triggering live crawls/API calls.
- Added guarded `scripts/gsc-url-inspection.py` for Google URL Inspection JSON/live read-only checks with `GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`.
- Added guarded `scripts/bing-url-inspection.py` for Bing Webmaster `GetUrlInfo` JSON/live read-only checks with `BING_WEBMASTER_API_KEY`.
- Added `scripts/labrika-health.py` to record Labrika API readiness, support questions and manual/export fallback.
- Added `scripts/technical-mcp-health.py` to check optional mcp-gsc, Google Analytics MCP and Lighthouse MCP readiness without installing servers or reading secrets.
- Extended `scripts/link-audit.py` with a separate `broken_anchors` summary and finding.
- Extended `scripts/serpstat-audit.py` with settings, list/poll, issue report, error/sub-element, history and export planned/live actions while keeping Serpstat credit/API use gated.
- Wired new technical reports into project template policy files, validation defaults, setup control plane, task routing, upgrade assistant, access-key assistant and docs.
- Added regression tests for GSC/Bing guarded/input adapters, Labrika health, Serpstat extended actions and technical rollup.

## [1.44.1] — 2026-06-06

### Compatibility

- Fixed source artifact timestamps on clean macOS/system Python 3.9 installs by replacing `datetime.UTC` with `datetime.timezone.utc`.
- Added a regression test for the UTC timestamp helper used by technical/source collectors.

## [1.44.0] — 2026-06-06

### Technical site tools

- Added `scripts/link-audit.py` for `linkinator` JSON/live broken-link, redirect, HTTP-link and external-link distillates under `seo/technical/` plus raw/distillate/vector source artifacts.
- Added `scripts/redirect-map-audit.py` for CSV redirect-map checks: chains, loops, self-redirects, missing targets and optional live URL status.
- Added `scripts/lighthouse-audit.py` for Lighthouse JSON/live Core Web Vitals, performance, SEO, accessibility and opportunity distillates.
- Added `scripts/serpstat-audit.py` as a guarded Serpstat Site Audit adapter for projects/create/start/basic-info/categories/scan-urls; live calls require `--live` plus `SERPSTAT_API_KEY` and credit/budget approval.
- Added `scripts/labrika-source-pack.py` for Labrika manual/browser export ingestion until public API automation is confirmed.
- Wired technical reports into project templates, validation defaults, task routing, setup control plane, upgrade assistant, README, INSTALL, GUIDE and vNext docs.
- Added regression tests for link, redirect, Lighthouse, Serpstat guarded/input, and Labrika export collectors.

## [1.43.0] — 2026-06-06

### Source artifacts and provider collectors

- Added `scripts/seo_cycle_core/source_artifacts.py` for stable raw/distillate/latest/vector source records under `seo/research/raw`, `seo/research/distillates`, and `seo/research/vector/source_pack.jsonl`.
- Added `scripts/perplexity-collect.py` to cache Perplexity raw exports, emit bounded distillates with citations, reuse cache hits, and write degraded/manual prompt packets without paid API calls by default.
- Added `scripts/notebooklm-source-pack.py` to ingest NotebookLM MCP/browser/manual exports as curated expert evidence source packs; NotebookLM remains non-ranking-signal evidence only.
- Refactored `task-router.py` and `context-pack.py` onto shared `seo_cycle_core` config/path/subprocess helpers without changing public CLI outputs.
- Added regression tests for provider collectors and source artifact contracts.

## [1.42.2] — 2026-06-06

### Bootstrap reliability

- Silenced false `/dev/tty: Device not configured` warnings in headless one-command smoke runs by probing `/dev/tty` before prompting.

## [1.42.1] — 2026-06-06

### Bootstrap reliability

- Fixed one-command `curl ... bootstrap-codex.sh | bash` setup so `init-project.sh` reads from `/dev/tty` when available and otherwise uses safe defaults instead of consuming the remaining bootstrap script as wizard answers.
- Added `init-project.sh --non-interactive` / `--defaults` for clean smoke tests and CI-like setup runs.
- Added a regression test proving piped stdin cannot pollute generated `seo-cycle.yaml` values.

## [1.42.0] — 2026-06-06

### Core quality and token efficiency

- Added `scripts/seo_cycle_core/` for shared config/path parsing, report bundle writing, subprocess JSON handling, context manifests, and provider health checks.
- Added `scripts/token-waste-audit.py` to flag raw artifacts, oversized distillates, and large context candidates while keeping raw data on disk.
- Added `scripts/perplexity-health.py` and `scripts/notebooklm-health.py` as report-only provider checks: persistent Perplexity app/browser mode, optional API, no password storage, and NotebookLM MCP/export fallback.
- Extended `task-router.py` and `context-pack.py` with a stable `context_manifest` contract: read-first files, blocked raw artifacts, source caps, and output paths.
- Wired token/provider reports into `setup-control-plane.py`, template policy files, validation defaults, and the existing-project upgrade assistant.
- Refactored vNext/control-plane helpers onto shared core without changing public CLI commands or artifact paths.

## [1.41.0] — 2026-06-06

### Live AI bot access check

- Added `scripts/ai-bot-access-check.py`, a report-only checker for robots.txt and real HTTP access across LLM, search, social, SEO-tool, and other crawler User-Agent strings.
- Added `seo/vnext/ai-bot-access-check.md/json` policy paths, template config, validation defaults, setup-control-plane artifact visibility, and upgrade assistant surfacing.
- Added local HTTP-server tests for robots blocks and WAF-like User-Agent blocks without external network calls.

## [1.40.0] — 2026-06-06

### SEO/AEO/GEO vNext report layer

- Added report-only vNext generators for AI Brand Audit, Answer Units, E-E-A-T evidence, GEO KPI, server log/AI bot audit, technical guardrails, snippets/sitemap, traffic drops, cannibalization, RU commerce/Yandex readiness, off-page risk, conversion/SXO, and expert source packs.
- Added shared `scripts/vnext_audit_core.py` with JSON/Markdown output, safe default guardrails, optional robots/log/CSV parsers, source attribution, and `seo/vnext/*.md/json` artifacts.
- Extended `config/project.template.yaml` with vNext config flags, output policy paths, source-pack settings, and vector record locations.
- Wired vNext into `setup-control-plane.py`, `project-upgrade-assistant.py`, `validate-config.py`, README, INSTALL, SKILL.md, Codex runtime docs, and a dedicated vNext runbook.
- Added smoke tests for all vNext generators, robots noindex detection, AI/search bot log parsing, traffic drop parsing, cannibalization parsing, and upgrade assistant surfacing.

## [1.39.0] — 2026-06-06

### NotebookLM knowledge bridge

- Added explicit `--notebooklm` support to `scripts/install-ai-toolchain.sh` for connecting NotebookLM MCP as a gated curated expert knowledge source.
- The installer appends a `notebooklm` MCP server to `~/.codex/config.toml` only when `--codex --notebooklm` is passed.
- Default NotebookLM MCP config uses the `standard` profile and disables cleanup/re-auth/source-ingestion/audio tools to keep the first integration read/query oriented.
- Documented NotebookLM as expert-synthesis input for SEO/AEO/GEO, requiring Google `setup_auth`, citations/source excerpts, and downstream fact-check before implementation.

## [1.38.0] — 2026-06-06

### Optional AI/dev support toolchain

- Added `scripts/install-ai-toolchain.sh` to install the approved local support stack: GitHub Spec Kit CLI, Microsoft MarkItDown, Graphify, and CodeGraph.
- The installer can also configure Codex integrations with `--codex`: Graphify skill under `~/.agents/skills/graphify` and CodeGraph MCP in `~/.codex/config.toml`.
- Documented when to use each tool: Spec Kit for large `seo-cycle` feature work, MarkItDown for trusted evidence ingestion, Graphify for mixed code/docs/research graphs, and CodeGraph for local code-symbol navigation.
- Explicitly excluded stealth/anti-bot browsers, paid APIs, and external memory services from the standard install path.
- Updated README, INSTALL, SKILL.md, GUIDE RU/EN, and `.gitignore` rules for local `.codegraph/` and `graphify-out/` caches.

## [1.37.0] — 2026-06-05

### Existing-project upgrades and access setup

- Added `scripts/project-upgrade-assistant.py` for existing projects: review-only feature comparison against the current template/control-plane surface, `upgrade-assistant.md/json`, and `upgrade-questionnaire.csv` with yes/no/defer choices.
- Added `scripts/access-key-assistant.py` for project-specific access setup: reads tool-stack decisions and `.env`, emits only needed Google/Yandex/Bing/NeuronWriter/AI key/token steps, and never prints secret values.
- `bootstrap-codex.sh` and `bootstrap-claude.sh` now preserve existing `seo-cycle.yaml` projects and run upgrade/access/control-plane assistants instead of reinitializing the project.
- `.env.example` and bootstraps now define runtime routing: Codex uses `SEO_RUNTIME=codex` + `SEO_SEARCH_RUNTIME=direct`; Claude uses `SEO_RUNTIME=claude` + `SEO_SEARCH_RUNTIME=codex_external`.
- Setup control plane, context pack, task router, onboarding proofs, template policy files, README, INSTALL, GUIDE, SKILL.md, Codex runtime docs, and OAuth docs now include the upgrade/access assistants.
- Switched project templates, prompt commands, and setup docs to the Codex-first canonical path `~/.codex/skills/seo-cycle`, while keeping Claude/agents compatibility symlinks documented.
- Added smoke tests for review-only project upgrades, secret-free access-key instructions, context-pack read order, and onboarding proofs.

## [1.36.0] — 2026-06-05

### Codex-first bootstrap

- Added `bootstrap-codex.sh` for one-command project setup from the project root: install/update core, dependencies, Codex symlinks, interactive project wizard, `.env`, `.gitignore`, and setup reports.
- Added `bootstrap-claude.sh` as the Claude Code variant; it uses the same Codex-first core and adds `CLAUDE.md` plus `SEO_RUNTIME=claude`.
- `install-codex.sh` now treats `~/.codex/skills/seo-cycle` as the canonical git checkout; `~/.claude/skills/seo-cycle` and `~/.agents/skills/seo-cycle` become compatibility symlinks to the Codex core.
- Updated README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs so new projects start with a single `curl ... bootstrap-codex.sh | bash` command.

## [1.35.0] — 2026-06-05

### Setup blueprint matrix

- Added `scripts/setup-blueprint.py` as a compact per-project setup matrix for countries, regions, search engines, business type, local/ecommerce flags, marketing/ads/tracking policy, tools, budgets, subscriptions, automations, guardrails, and first-read files.
- The blueprint writes `seo/setup-blueprint.generated.yaml`, `seo/setup/setup-blueprint.md/json`, `seo/setup/latest-setup-blueprint.md/json`, and `seo/setup/setup-matrix.csv`; it is secret-free and does not mutate project config.
- `setup-control-plane.py` now generates and summarizes the blueprint, `context-pack.py` and `task-router.py` include it in low-token read order, and onboarding proofs include `setup_blueprint` plus `setup_matrix_csv`.
- Project templates, validation, governance report, init wizard, README, GUIDE, SKILL.md, INSTALL, and Codex runtime docs now include the blueprint as the first detailed setup matrix after context pack.
- Added smoke tests proving RU ecommerce gets RF/paid guardrails and a compact decision matrix, while US local projects get Bing/local setup without RF-only guards.

## [1.34.0] — 2026-06-05

### Setup answer plan

- Added `scripts/setup-answer-plan.py` to read filled `seo/setup/setup-questionnaire.csv` rows and generate a review-only manual apply plan.
- The plan writes `seo/setup/setup-answer-plan.md/json/csv` and latest copies with target files, target paths, parsed proposed values, follow-up commands, and manual-review mode.
- Secret-like answers are rejected and never stored in the report; the script does not edit `seo-cycle.yaml` or `seo/project-intake.yaml`.
- Project templates, validation, governance report, context pack, task router, init wizard, README, GUIDE, SKILL.md, INSTALL, and Codex runtime docs now include the answer-plan step after questionnaire filling.
- Added smoke tests proving filled business/budget answers become manual plan entries and secret-looking answers are redacted/rejected.

## [1.33.0] — 2026-06-05

### Setup questionnaire worksheet

- `setup-gap-audit.py --write` now also generates `seo/setup/setup-questionnaire.md`, `setup-questionnaire.csv`, `setup-questionnaire.json`, and latest copies as a fillable owner worksheet for missing setup fields.
- Questionnaire rows include priority, field, category, severity, question, answer format, target file, follow-up command, empty answer, and notes; secret values are explicitly kept out.
- `setup-control-plane.py`, context pack read order, task router, onboarding proofs, project templates, validation, governance report, init wizard, README, GUIDE, SKILL.md, INSTALL, and Codex runtime docs now include the worksheet.
- Added smoke tests proving RU ecommerce and US local projects receive project-type-aware questionnaire rows without requiring irrelevant ecommerce feed fields for local-only projects.

## [1.32.0] — 2026-06-05

### Detailed setup gap audit

- Added `scripts/setup-gap-audit.py` to score detailed first-run readiness across market, business, marketing, local/ecommerce, tool stack, budget/subscriptions, spend guard, context pack, launch plan, and automation recommendations.
- The audit writes `seo/setup/setup-gap-audit.md/json` and `seo/setup/latest-setup-gap-audit.md/json`, keeps secrets out, and returns missing fields plus owner questions for details such as priority products/services, local profile URLs, ecommerce feed policy, and paid API caps.
- `setup-control-plane.py` now runs the audit, summarizes score/missing gaps, and adds a next action before broad execution while keeping `seo/setup/context-pack.md` as the first low-token entry point.
- Project templates, validation, governance report, onboarding, init wizard, README, GUIDE, SKILL.md, INSTALL, and Codex runtime docs now include setup gap audit as a standard first-run artifact.
- Added smoke tests for RU ecommerce and US local projects proving gap detection is project-type aware and does not require ecommerce feed policy for local-only sites.

## [1.31.0] — 2026-06-05

### Low-token context pack

- Added `scripts/context-pack.py` to generate a bounded first-read handoff from launch plan, latest task route, spend guard, tool-stack decisions, usage, growth roadmap, and automation recommendations.
- The pack writes `seo/setup/context-pack.md/json` and `seo/setup/latest-context-pack.md/json`, lists read order, do-not-load raw artifacts, approval gates, spend blockers, human-secret env names, and task-scoped next commands without exposing secret values.
- `setup-control-plane.py` now generates and summarizes the context pack, and makes `seo/setup/context-pack.md` the first next action before opening larger setup reports.
- Project templates, validation, governance report, init wizard, README, GUIDE, SKILL.md, INSTALL, and Codex runtime docs now include the context pack as the default low-token session entry point.
- Added smoke tests proving the pack stays within its char budget, preserves RF/paid-tool guards, excludes raw JSON artifacts, and is emitted by setup-control-plane.

## [1.30.0] — 2026-06-05

### Tool-aware automation matrix

- Expanded `scripts/automation-recommender.py` from a small automation set into a tool-aware matrix covering spend guard, technical indexability, search-console index status, Bing Webmaster, schema/Core Web Vitals, content decay refresh queues, AI visibility, ecommerce feeds, and local reputation.
- Recommendations now use generated tool-stack and spend-guard JSON signals, keep `create_schedules: false`, and preserve `tools` plus `approval_gates` when applied to `seo/automation-policy.yaml`.
- `automation-recommender.py --write/--apply --format json` now keeps stdout as clean JSON and sends write/apply status to stderr.
- `scripts/automation-plan.py` now has cron defaults and safe command templates for the expanded task IDs, including spend guard refresh, read-only GSC/Yandex fetches when env is present, Bing governance checks, schema/CWV candidate checks, and dry-run content refresh queues.
- Added automation smoke tests proving RU ecommerce and US local projects receive the correct guarded task matrix, applied policy retains gates/tools, and generated plan commands target the intended safe scripts.

## [1.29.0] — 2026-06-05

### Spend and subscription guard

- Added `scripts/spend-guard.py` to create a local spend/subscription control plane from `seo-cycle.yaml`, `seo/tool-budget.yaml`, tool-stack decisions, subscriptions, and `seo/usage/usage-ledger.jsonl`.
- The guard writes `seo/spend-guard.generated.yaml`, `seo/setup/spend-guard.md/json`, `seo/setup/latest-spend-guard.md/json`, and `seo/setup/spend-checklist.csv`; it never stores secret values.
- Service guards now show `allowed_now`, status, metric caps, reserves, remaining limits, approval gates, env names, and exact `usage-ledger.py check ... --fail-on-block` preflight commands for paid API, LLM, ads, and subscription tools.
- `setup-control-plane.py`, `launch-plan.py`, onboarding, project templates, validation, governance report, init wizard, and docs now include spend guard as part of first-run setup.
- Added smoke tests proving default RU projects block paid/LLM spend without approval and tuned projects report remaining NeuronWriter/OpenAI limits correctly.

## [1.28.0] — 2026-06-05

### Per-project launch plan contract

- Added `scripts/launch-plan.py` to generate a compact first-screen launch contract from project intake, tool-stack decisions, growth roadmap, onboarding, automation recommendations, and budget/subscription policy.
- The launch plan writes `seo/launch-plan.generated.yaml`, `seo/setup/launch-plan.md/json`, `seo/setup/latest-launch-plan.md/json`, and `seo/setup/launch-checklist.csv`; it never stores secret values.
- The report summarizes market/business matrix, low-token token contract, budget caps, subscription controls, tool packs, human-secret env names, approval gates, policy guards, automations, and bounded execution order.
- `setup-control-plane.py`, project templates, validation, governance report, init wizard, README, GUIDE, SKILL.md, INSTALL, and Codex runtime docs now include launch-plan as the first project setup screen.
- Added smoke tests proving RU ecommerce gets RF tracking guards, Google NLP/NeuronWriter budget controls, approval gates, and env-name-only inputs, while US local projects get Bing Webmaster, Bing Places, and Google Business Profile without RF-only guards.

## [1.27.0] — 2026-06-05

### Detailed setup onboarding playbook

- Added `scripts/setup-onboarding.py` to generate a detailed first-run setup playbook from `seo-cycle.yaml`, project intake, tool-stack decisions, growth roadmap, automation recommendations, and usage/budget posture.
- The playbook writes `seo/onboarding.generated.yaml`, `seo/setup/onboarding-playbook.md/json`, `seo/setup/latest-onboarding-playbook.md/json`, and `seo/setup/onboarding-checklist.csv`.
- Onboarding steps now have explicit owners (`agent`, `human_secret`, `review`, `approval`), commands, proof artifacts, env-name-only secret requirements, and approval gates for paid API, tracking, ads, schedules, config changes, and LLM spend.
- `setup-control-plane.py`, project templates, validation, governance report, init wizard, README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now include onboarding as part of first-run setup.
- Added smoke tests proving RU ecommerce receives RF tracking review, Google NLP/NeuronWriter budget guards, human-secret env names without values, and setup-control-plane commands, while US local projects receive Bing/local setup without RF-only guards.

## [1.26.0] — 2026-06-05

### Growth roadmap control layer

- Added `scripts/growth-roadmap.py` to turn project intake, generated tool stack, automation recommendations, usage posture, and budget policy into a compact top-N roadmap across technical SEO, search evidence, ecommerce revenue, local dominance, content/entities, AI visibility, marketing/CRO, and automation control.
- The roadmap writes `seo/growth-roadmap.generated.yaml`, `seo/setup/growth-roadmap.md/json`, and `seo/setup/latest-growth-roadmap.md/json`; it never fetches external data or prints secrets.
- `setup-control-plane.py` now generates and summarizes the growth roadmap as part of first-run readiness, so new projects start with priorities, not only setup checklists.
- Project templates, validation, governance report, init wizard, README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now include the roadmap artifacts and command.
- Added smoke tests proving RU ecommerce gets technical/ecommerce/content/entity/AI priorities with RF tracking guard and paid API approval gates, while US local business gets local/Bing/Google priorities without ecommerce actions.

## [1.25.0] — 2026-06-05

### Per-project tool stack recommender

- Added `scripts/tool-stack-recommender.py` to recommend a concrete Google/Yandex/Bing/Microsoft/NLP/AI/merchant/local/ads/tracking tool stack from country, engines, project type, local/ecommerce flags, budget caps, subscriptions, and RF tracking policy.
- The recommender writes `seo/tool-stack.generated.yaml`, `seo/setup/tool-stack-report.md/json`, and `seo/setup/latest-tool-stack.md/json`; default mode is non-destructive and secret-free.
- `--apply` creates a backup and only applies conservative source flags: free/read-only applicable sources may be enabled, region-inapplicable/disabled sources may be disabled, and paid/quota/LLM/index-submission/ads/tracking tools remain review/approval-gated.
- The catalog captures the setup work for Google Search Console/GA4/Merchant/Business Profile/YouTube/Gemini/NLP, Yandex Webmaster/Merchant/Metrica/Direct/Maps, Bing Webmaster/IndexNow/Places, Microsoft Clarity/Ads, NeuronWriter, Keys.so, Serpstat, DataForSEO, Perplexity, OpenAI/Claude/Gemini/DeepSeek, and robots AI Content-Signal checks.
- `setup-control-plane.py`, project templates, validation, governance report, init wizard, README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now include tool-stack recommendations as part of first-run setup and handoff.
- Added smoke tests for RU ecommerce and US local-business projects to prove RF foreign tracking stays disabled, paid NLP/content tools stay approval-gated by default, and relevant Bing/Google/Yandex/local/merchant tools are selected.

## [1.24.0] — 2026-06-05

### Per-project automation recommender

- Added `scripts/automation-recommender.py` to recommend planned automations from project intake, business type, market, search engines, local/ecommerce decisions, AI visibility tools, and current automation policy.
- The recommender writes `seo/automations/automation-recommendations.md/json` and `seo/automation-policy.generated.yaml`; `--apply` safely updates `seo/automation-policy.yaml` with backup.
- Schedule installation remains guarded: `--apply` does not set `create_schedules: true` unless `--allow-schedules` is explicitly passed, and `automation-plan.py --install-cron` still requires governance + policy + env gates.
- Added `usage_budget_watch` as a first-class safe report-only automation and wired it into `automation-plan.py`.
- `setup-control-plane.py`, project templates, validation, governance report, init wizard, README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now include automation recommendations as part of first-run setup.

## [1.23.0] — 2026-06-05

### Usage and budget ledger

- Added `scripts/usage-ledger.py` as the unified project-local ledger for tokens, LLM spend, paid API spend, ad spend, credits, units, rows, browser minutes, and subscription counters.
- The ledger supports `report`, `check`, and `record`: preflight estimates can block/require approval before spend, and append-only records are written to `seo/usage/usage-ledger.jsonl`.
- `setup-control-plane.py` now writes `seo/setup/latest-usage-ledger.md/json`, creates an empty ledger on first run, and includes usage status in readiness.
- `task-router.py` now includes current usage-ledger status and points the route context to `seo/setup/latest-usage-ledger.md`.
- `db-sync.py` now imports `seo/usage/usage-ledger.jsonl` into `api_usage` for dashboards, alongside older `_usage.json` files.
- Project templates, validation, governance report, and docs now include usage-ledger artifacts and monthly token/ad caps.

## [1.22.0] — 2026-06-05

### Low-token task router

- Added `scripts/task-router.py` to classify a concrete SEO/marketing task and produce a compact execution route: phases, sources, approval gates, blocked actions, automation recommendation, and context/token caps.
- The router is read-only by default and writes `seo/setup/latest-task-route.md/json` plus archived per-task routes only with `--write`.
- `setup-control-plane.py` now accepts `--task` and includes the latest task route in the readiness report, so first-run setup and handoffs start from a bounded execution plan.
- Project templates, validation, governance report, init wizard, README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now include the task route as part of the standard low-token workflow.

## [1.21.0] — 2026-06-04

### Setup control plane

- Added `scripts/setup-control-plane.py` as the single low-token first-run surface for intake, profile, source resolution, governance, validation, and automation readiness.
- `--write` refreshes safe generated artifacts and writes `seo/setup/setup-control-plane.md`, `setup-control-plane.json`, `latest-validation.txt`, `latest-governance.json`, and `latest-sources.json`.
- `--apply-profile` remains an explicit opt-in for applying generated profile changes to `seo-cycle.yaml` with backup.
- `init-project.sh` now creates the setup control-plane report after intake/profile generation, so every new project starts with a compact readiness report and next-action checklist.
- README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now include the setup control-plane command as the default post-init review step.

## [1.20.0] — 2026-06-04

### Detailed project intake wizard

- Added `scripts/project-intake-wizard.py` to create/refine `seo/project-intake.yaml` from `seo-cycle.yaml` in `--defaults` mode or through a detailed `--interactive` wizard.
- The wizard covers project type, business model, sales channels, priority products/services, audiences, conversion goals, countries, regions, languages, search engines, local platforms, marketing channels, paid ads policy, analytics tracking policy, guarded tools, AI visibility platforms, governance, automation mode, cache-first, and distillate requirements.
- `init-project.sh` now asks whether to run the detailed intake wizard; otherwise it auto-fills intake defaults from the generated `seo-cycle.yaml`.
- The setup now writes `seo/project-intake-report.md` before generating `seo/project-profile.generated.yaml` and `seo/project-profile-report.md`.
- `init-project.sh` now offers an explicit opt-in to apply the generated project profile to the fresh `seo-cycle.yaml` immediately, with the normal backup behavior.
- README, INSTALL, GUIDE, SKILL.md, and Codex runtime docs now route new-project setup through `project-intake-wizard.py` before `project-profile.py`.

## [1.19.0] — 2026-06-04

### Project profile overlay and intake applier

- Added `scripts/project-profile.py` to read `seo/project-intake.yaml` and generate project-specific engines, region profile, source overrides, marketing decisions, and governance recommendations.
- Default mode writes `seo/project-profile.generated.yaml` and `seo/project-profile-report.md`; `--apply` updates `seo-cycle.yaml` only after explicit review and creates a timestamped backup.
- `init-project.sh` now generates the initial project profile report/overlay after creating policy templates.
- `policy_files` now includes `project_profile`, and governance/Codex docs mention the generated overlay.
- Codex entrypoint and SKILL.md now route detailed per-project setup through `project-profile.py --write` before optional `--apply`.
- `docs/oauth-setup.md` now covers the broader access matrix from the setup work: Google NLP/Merchant/Business/YouTube, Bing Webmaster/IndexNow/Places, Yandex Merchant/Direct, and RF tracking-tag restrictions.

## [1.18.0] — 2026-06-04

### Safe scheduled automation planner

- Added `scripts/automation-plan.py` to generate `seo/automations/automation-plan.md`, `automation-plan.json`, `crontab.txt`, and launchd plist templates from `seo-cycle.yaml` + `seo/automation-policy.yaml`.
- Schedule installation is blocked unless both governance and automation policy set `create_schedules: true`, and `SEO_CYCLE_ALLOW_SCHEDULE_INSTALL=1` is present.
- Monthly automation now references the planner script and output directory in `config/project.template.yaml`.
- `init-project.sh` next steps now include safe automation-plan generation after governance report.
- `validate-config.py` now reminds projects with enabled schedule creation to generate/review schedule artifacts.
- Codex runtime docs and SKILL.md now require `automation-plan.py --write --include-disabled` before any real scheduled automation.

## [1.17.9] — 2026-06-04

### Token, budget, subscription, and automation governance

- Added `governance` to `config/project.template.yaml`: token policy, cache-first rules, monthly paid API/LLM caps, subscription caps, and automation approval gates.
- Added project-local policy templates: `seo/tool-budget.yaml`, `seo/automation-policy.yaml`, and `seo/project-intake.yaml`.
- Added `scripts/governance-report.py` to print active token/budget/tool/automation policy without exposing secrets.
- `init-project.sh` now asks for governance profile, paid API budget, LLM budget, automation mode, and schedule creation before image workflow questions.
- `validate-config.py` now checks governance sanity: raw data in context, cache-first, oversized phase context, active paid sources with zero budget, invalid automation modes, and missing automation policy.
- SKILL.md, Codex runtime docs, and Codex entrypoint now require governance report before expensive collection, browser work, publishing, or scheduled automations.

## [1.17.8] — 2026-06-04

### Project policy intake for paid/API SEO tools

- SKILL.md: `seo-cycle` now checks project-local policy files before phase selection, API calls, credit spend, indexing changes, or analytics/tracking changes.
- Added local contracts for `seo/neuronwriter-limits.yaml`, `seo/neuronwriter.md`, `seo/entities/google-nlp-policy.yaml`, `seo/seo-data-collection-map.md`, and `seo/access-setup-runbook.md`.
- NeuronWriter is treated as the primary SERP/NLP content editor when configured; Google Cloud Natural Language is treated only as a guarded technical entity audit layer with cache/unit caps.
- Added `scripts/google-nlp-audit.py` with project-local `.env` loading, policy defaults, cache, dry-run mode, and monthly unit guards.
- `install-codex.sh` now installs the Codex-first entrypoint skill via `~/.codex/skills/codex-primary-runtime` and includes `beautifulsoup4`/`google-auth` dependencies.
- `init-project.sh` now creates project `AGENTS.md` and policy templates for NeuronWriter, Google NLP, data access, setup runbooks, and AI visibility prompts.
- `validate-config.py` now checks policy-file presence and warns when NeuronWriter/Google NLP are configured without local guard files.
- Added source/env scaffolding for Bing Webmaster, IndexNow, Bing Places, Google Merchant/Business Profile/YouTube, Yandex Merchant, and Ads accounts as approval-only data sources.
- Added RF-site tracking guard: do not add foreign analytics/tracking tags or pixels without explicit project-policy approval.
- Added robots/Content-Signal policy handling: `search=yes, ai-input=yes, ai-train=no` is allowed as a training opt-out, while public `robots.txt` must be clean text without PHP warnings/HTML.
- `docs/codex-runtime.md` and GUIDE.md RU+EN now document the same Codex policy intake flow.

## [1.17.7] — 2026-06-02

### Configurable photo pipeline

- Добавлен штатный инструмент `scripts/wp-photo-image.py`: локальное фото/URL → crop по `images.aspect_ratios.*` → WebP → WordPress upload через SSH/WP-CLI → alt/caption/featured.
- `config/project.template.yaml`: секция `images` расширена до photo-first workflow с `tool`, `source_policy`, `visual_style`, `output`, `captions`, `alt`, `lazy_loading`, `upload` и `inline_min_per_post`.
- `scripts/init-project.sh`: wizard для нового проекта теперь спрашивает пропорции featured/inline, WebP width/quality, источник фото, visual style, минимум inline-картинок, caption policy и разрешение видимого текста.
- `validate-config.py` проверяет `images.*`: наличие tool scripts, featured/inline ratios и SSH/WP-CLI env для WordPress upload.
- Установочные инструкции и `install-codex.sh` теперь добавляют `pillow`, нужный для crop/WebP.
- GUIDE.md RU+EN и SKILL.md обновлены: image workflow теперь config-driven, `wp-photo-image.py` закреплён как основной photo-first инструмент.

## [1.17.6] — 2026-06-02

### WordPress REST publishing fallback

- SKILL.md: Phase 7 теперь фиксирует WordPress REST API + Application Password как основной независимый канал публикации.
- MCP/`emwoody-publish-*` остаются удобным интерфейсом, но не единственной точкой отказа.
- SSH/WP-CLI закреплён как fallback для backup, cache purge, REST meta limitations и серверных исправлений.
- GUIDE.md RU+EN обновлён в таблице фаз.

## [1.17.5] — 2026-06-02

### Scope для `skip-lazy`

- SKILL.md и GUIDE.md RU+EN: `skip-lazy`/`data-no-lazy` применяется только к первому или above-the-fold inline image, если оптимизатор показывает плейсхолдер.
- Inline images ниже первого экрана должны оставаться lazy-loaded, чтобы не раздувать начальную загрузку страницы.

## [1.17.4] — 2026-06-02

### Проверка lazy-load плейсхолдеров

- SKILL.md: Phase 7 verify теперь требует не только GET/HTML, но и браузерную проверку inline images после публикации.
- GUIDE.md RU+EN: lazy-load плейсхолдер вместо реального inline-фото считается blocker/exception.
- Зафиксирован способ исправления для критичных inline images: исключение из lazy-load через `skip-lazy`/`data-no-lazy` или CMS-аналог с повторным screenshot-check.

## [1.17.3] — 2026-06-02

### Визуальный gate для inline images

- SKILL.md: image QA теперь требует чистые тематические фото/визуалы в стиле проекта, без видимого SEO/AEO/GEO текста, схем, товарных описаний и каталоговых дисклеймеров на изображении.
- GUIDE.md RU+EN: зафиксировано, что inline images должны иметь естественный `alt` и короткий редакционный caption; товарные карточки/коллажи не используются как основной визуал без явного запроса.
- Публичная проверка теперь блокирует запрещённые тексты на/под изображениями и inline images без caption.

## [1.17.2] — 2026-06-02

### Обязательный alt-gate для изображений

- SKILL.md: добавлен Image alt check в Phase 6 QA и публичная проверка `<img>` без `alt` в Phase 7 Publishing.
- GUIDE.md RU+EN: зафиксировано, что featured, inline, OG/schema и product/category visuals должны иметь естественный alt без переспама ключами.
- Изображение без alt теперь считается publication blocker/exception, а не мелкой рекомендацией.

## [1.17.1] — 2026-06-02

### Обязательный evidence-gate для семантики, сущностей и фактчекинга

- SKILL.md: Antigravity CLI и Perplexity Deep Research теперь обязательны для Phase 2 (семантика), Phase 4 (Entity Map) и Phase 6 (fact-check перед публикацией), если инструменты доступны.
- Если Antigravity/Perplexity недоступны технически, цикл должен записать blocker/exception в артефакт; нельзя выдавать сбор или проверку за полные.
- GUIDE.md RU+EN обновлен: добавлены правила сохранения raw-ответов на диск, использования только distilled artifacts в контексте и QA-цепочка `stop-words → Perplexity+Antigravity fact-check → NW≥65`.

## [1.17.0] — 2026-05-30

### Установка одной командой (Codex + Claude)

- **`install-codex.sh`** — `curl -sL .../install-codex.sh | bash`: идемпотентно клонирует/обновляет ядро `seo-cycle` (+ `seo-keywords`), ставит зависимости (pyyaml/requests), создаёт симлинк `~/.codex/skills/seo-cycle` для Codex, чинит `AGENTS.md`, печатает следующие шаги (init-project + AGENTS.md + .env + SEO_RUNTIME=codex).
- README: one-command установка в TL;DR.

## [1.16.0] — 2026-05-30

### Оптимизация расхода Keys.so (Professional-тариф)

- **Кэш TTL 30→60 дней** в `keyso-fetch.py` и `competitor-discovery.py` — повторный сбор темы в пределах 60д = 0 обращений к API (главная экономия лимита).
- **Usage-трекер** в `keyso-fetch.py` — счётчик реальных запросов за месяц в `seo/research/keyso/_usage.json` (cache-hit не считается); печатает расход в stderr.
- Секция `keyso` в конфиге расширена: `plan: professional`, `cache_ttl_days: 60`, `rate_limit`, `monthly_request_budget` (впиши лимит из кабинета для guard).
- Принципы экономии задокументированы (keyword-info — 1 запрос/ключ без batch; competitor-discovery агрегирует топы за немного запросов; крупный per_page = больше данных за проверку).
- GUIDE.md (RU+EN) — обновлены ячейки Keys.so.

## [1.15.0] — 2026-05-30

### Кластеризация в Keys.so через браузер (clustering API закрыт)

Keys.so clustering недоступен через API (только UI) — добавлена полуавтоматическая загрузка.
- **`scripts/keyso-clustering-export.py`** — детерминированная подготовка файла ключей (из keyso-кэша / CSV / markdown-таблицы / списка) → `.txt` по ключу на строку, дедуп, фильтр по частоте/лимиту. Дёшево, без браузера.
- **`prompts/keyso-clustering-upload.md`** — runbook браузерной загрузки (Chrome MCP / Codex browser): создать проект → file_upload → запустить → экспорт в `<cycle>/03-clusters-keyso.md`. С предупреждением о расходе токенов и критериями «когда оправдано» (большие ядра) vs «наша кластеризация дешевле» (малые/средние).
- GUIDE.md (RU+EN) — export-скрипт в таблицах.

## [1.14.0] — 2026-05-30

### keyso-save.py — сохранение конкурентов в кабинет Keys.so (write-API)

- **`scripts/keyso-save.py`** — `group-report`: сохраняет группу доменов (свой + конкуренты) в кабинет Keys.so через `POST /report/group` (рабочий write-эндпоинт). `--from-config` берёт домены из `business_profile.competitors`. Возвращает rid отчёта.
- Разведка write-API Keys.so: реально доступен только групповой отчёт; `clustering/my_projects/position-monitoring` через API отвечают "Method not allowed" (только UI). Поэтому **семантика и кластеризация хранятся у нас** (seo/cycles + seo.db + Obsidian), в Keys.so сохраняется групповой отчёт конкурентов.
- GUIDE.md (RU+EN) — keyso-save в таблицах.

## [1.13.0] — 2026-05-30

### competitor-discovery.py — поиск максимально похожих конкурентов

- **`scripts/competitor-discovery.py`** — находит прямых бизнес-конкурентов через агрегацию топа выдачи Яндекса по коммерческим seed-ключам (Keys.so `keyword_dashboard.top[]`), а не через `concurents` по домену (который врёт, если сайт ранжируется блогом). Ранжирует по числу ключей в топе + видимости, помечает/исключает гигантов (`--exclude-giants`). Кэш, троттлинг 10/10сек.
- Обкатано на emwoody: топ похожих — shop.tn.ru, strd.ru, tstn.ru, msk.saturn.net; занесены в `business_profile.competitors`.
- GUIDE.md (RU+EN) — в таблицах источников.

## [1.12.0] — 2026-05-30

### Keys.so — Яндекс/РФ источник данных

- **`scripts/keyso-fetch.py`** — клиент Keys.so API (header `X-Keyso-TOKEN`, лимит 10 req/10сек + 429-retry, кэш 30 дней). Подкоманды: `keyword-info` (Wordstat-частоты ws/wsk/kei/cpc), `keywords` (ключи домена + позиции), `competitors` (видимость, топ-10/3, реклама), `lost` (потерянные ключи). Сильная сторона — **Яндекс-данные для РФ**, дополняет Wordstat (частоты) и Serpstat (Google).
- Добавлен в `region-profiles` ru + global (РФ-сервис; не eu/us), `seo-cycle.yaml` emwoody + `project.template.yaml`, `.env.example` (`KEYSO_API_TOKEN`).
- В `prompts/competitor-analysis.md` — Keys.so в источниках (конкуренты/частоты/lost).
- GUIDE.md (RU+EN) + CLAUDE.md emwoody — таблицы источников.

## [1.11.0] — 2026-05-30

### Маркетинг-слой: стратегия → результат (замыкает полноценный маркетинг)

Верхний слой над органикой — решение «куда вкладывать» и измерение результата в деньгах.
- **`scripts/roi-calc.py`** — воронка трафик→лиды→заказы→выручка + ROI/CAC/ДРР/AOV по каналам + вердикт «что окупается / нужна ли реклама». «Конечный результат» в деньгах.
- **`prompts/marketing-strategy.md`** — цели → оценка органика vs платка (на цифрах) → медиаплан/бюджет → KPI. Реклама только при дефиците объёма с ROI>0.
- **`prompts/distribution-channels.md`** — каналы РФ (email/Telegram/видео) + **товарные фиды/маркетплейсы** (Яндекс.Маркет, Озон, Google Merchant).
- **`prompts/orm.md`** — мониторинг отзывов + алерт на негатив (`notify.py`).
- **`prompts/marketing-calendar.md`** — единый план SEO+соцсети+email+реклама+акции.
- Секция `marketing.channels/marketplaces/measurement` в конфиге emwoody; мостик в Phase 0 SKILL; GUIDE.md (RU+EN) раздел 7.9.
- Отмечено внешнее (вне кода скилла): цели Метрики, коллтрекинг, CRM, кабинеты маркетплейсов, РФ ESP.

## [1.10.0] — 2026-05-30

### Закрытие пробелов охвата: потерянные ключи, бенчмарк, AI-visibility, реклама+соцсети

- **`scripts/lost-keywords.py`** — потерянные/просевшие ключи между двумя снапшотами (GSC/Вебмастер): LOST (выпал из топа) / DROPPED (просел) + потерянные клики. Детерминированно, без трат API.
- **`scripts/competitor-benchmark.py`** — медианный бенчмарк: для каждой метрики (ключи/бэклинки/отзывы/посты/фото) медиана топ-N конкурентов vs моё → статус 🔴/🟡/🟢 + разрыв %.
- **`prompts/ai-visibility.md`** — единый GEO-свод: присутствие в Яндекс Нейро / Google AI Overviews / ChatGPT / Perplexity (плагины `seo-geo`/`seo-seranking` + браузер). РФ-приоритет Нейро/GigaChat.
- **`prompts/ad-and-social.md`** — разведка рекламы конкурентов (SpyFu PPC / Serpstat ads / Директ) + генерация объявлений и соцпостов (Директ/VK/TG/Дзен) через `marketing-skills` с РФ-адаптацией и маркировкой рекламы.
- Мостики в Phase 9 SKILL.md; GUIDE.md (RU+EN) — новые скрипты в таблицах.

## [1.9.0] — 2026-05-30

### Конкурентный анализ + ICE-приоритизация

Из практики РФ-SEO (статья sostav): единый метод свести разрозненные конкурентные данные и приоритизировать находки.
- **`scripts/ice-score.py`** — приоритизация находок по ICE (Impact×Confidence×Ease, 1..10): сортировка + зоны 🔥 quick-win / ✅ do / ⏳ later. Вход CSV (`finding,impact,confidence,ease,source,note`).
- **`prompts/competitor-analysis.md`** — 7-шаговый метод: цель → конкуренты → источники (Serpstat/SpyFu/Keys.so/local/GSC, без дублирования сбора) → измерения → ICE → roadmap 1-6 мес → мониторинг. РФ-приоритет (Яндекс + Карты/2ГИС), инсайт «надёжность/экспертиза > цена».
- Мостик в Phase 1 SKILL.md (audit → конкурентный анализ + ICE → quick-wins в roadmap/keyword-queue).
- GUIDE.md (RU+EN): `ice-score.py` в таблицах инструментов.

(Остальное из присланного — ruflo/cybersecurity-skills/habr — оценено как оверинжиниринг / вне scope / уже реализовано; не внедрялось.)

## [1.8.0] — 2026-05-30

### Маркетинговые мостики (marketing-skills) + РФ-адаптация каналов

Связка с плагином `marketing-skills` (Corey Haines) — без дублирования его кода.
- **`docs/marketing-bridges.md`** — карта «фаза seo-cycle → релевантный marketing-skill» + **таблица РФ-замен каналов** (Google Ads→Яндекс.Директ, Meta→VK/Telegram, GA→Метрика, каталоги→2ГИС/Яндекс.Бизнес, Stripe→ЮKassa, отзывы→Яндекс.Карты/2ГИС, +RuStore). Что НЕ дублировать (SEO-скиллы плагина).
- **Секция `marketing`** в `seo-cycle.yaml` (emwoody: enabled + rf_adaptation + rf_channel_map + relevant_skills) и в `project.template.yaml` (opt-in).
- **Мостик в Phase 7** SKILL.md: после публикации → CRO через marketing-skills с РФ-адаптацией каналов.
- GUIDE.md (RU+EN): раздел 7.8.

## [1.7.0] — 2026-05-30

### Локальный SEO-модуль (карты: Google + Яндекс/2ГИС)

Парные тактики локального доминирования для обеих карт-экосистем (для РФ приоритет Яндекс.Карты + 2ГИС). Адаптировано из набора local-SEO приёмов.

- **`prompts/local/`** — `README` + `google-maps.md` + `yandex-maps.md`: 5 тактик парно (категории/рубрики gap, скорость отзывов, календарь постов, визуальное доминирование, локальная видимость). Оба рантайма (Chrome MCP / browser-skill).
- **`scripts/review-velocity.py`** — детерминированный расчёт плана догона лидера по отзывам (Google/Яндекс/2ГИС): темп/мес и срок.
- **`business_profile`** расширен: `gbp_url`, `yandex_business_url`, `2gis_url`, `target_local_keywords`, `competitors[{name,gbp,yandex,2gis}]` — «постоянный профиль», чтобы тактики брали конкурентов из конфига.
- **Чек-лист локального доминирования** встроен в Phase 1 (audit) и Phase 9 (monitoring): сравнение с топ-3 конкурентами по категориям/отзывам/постам/фото на обеих картах.
- GUIDE.md (RU+EN): раздел 7.7 Локальное SEO.
- Не дублируем уже покрытое: keyword gap (Serpstat/SpyFu), позиции 11-20 (triggers), бэклинки (seo-backlinks/ahrefs), общий GBP/NAP (плагин seo-maps/seo-local).

## [1.6.1] — 2026-05-30

### Дробление заморожено на пилоте (решение)

После обкатки пилота решено **не продолжать** дробление на фазовые скиллы — для текущего масштаба (1-2 проекта) overhead координации и дрейф логики не окупаются.
- Монолитный `seo-cycle` со всеми 10 фазами — **основной и рабочий**.
- Пилот (`cycle-state.py` + `seo-keywords`) оставлен как есть (аддитивен, обратим, опционален).
- Остальные фазы НЕ выносятся без явной потребности (продажа модулей / команда / переиспользование / параллелизм).
- Формулировки в SKILL.md и GUIDE.md обновлены: статус «заморожено», а не «по плану».

## [1.6.0] — 2026-05-30

### Модульная архитектура — пилот (фазовые скиллы + state-цепочка)

Начало перехода от монолитного оркестратора к независимым фазовым скиллам, координируемым через единый файл состояния. Эволюционно — без ломки текущего.

- **`scripts/cycle-state.py`** — контракт состояния цикла `seo/cycles/<тема>/_state.json`: `init`/`show`/`next`/`set`/`gate`. DAG из 11 фаз с `depends_on`; `next` вычисляет разблокированные фазы; `gate` проверяет готовность артефакта. Это «цепочка передачи» между скиллами.
- **Новый скилл `seo-keywords`** (`~/.claude/skills/seo-keywords/`) — самостоятельный фазовый скилл Phase 2-3 (сбор семантики + кластеризация): SKILL.md + README, читает/обновляет `_state.json`, использует core collector-скрипты. Шарибельный отдельно.
- `seo-cycle` SKILL.md: раздел «Модульная архитектура» — диспетчер ведёт цикл через `cycle-state.py`, проверяет quality-gate перед передачей, независимые фазы параллельно. «Улучшение» на данных, без авто-рефакторинга.
- GUIDE.md (RU+EN): раздел 6b + `cycle-state.py` в таблицах инструментов.

Дальше по плану: вынести `seo-entity-map`, `seo-writing`, `seo-publishing`, `seo-monitoring` по тому же образцу → затем `seo-cycle` станет чистым диспетчером (v2.0.0).

## [1.5.0] — 2026-05-29

### Полная двуязычная документация + AI-автоустановка

- **`GUIDE.md`** — подробное руководство **RU (сверху) + EN (полный перевод ниже)**: что это, преимущества, установка для человека и **для ИИ-агента (самостоятельный машинный сценарий)**, архитектура, оба рантайма, **все ~36 инструментов** (что делает / команда / какой результат), 10 фаз по шагам, агенты/делегаты, команды-шпаргалка, типовые сценарии.
- **Правило обновления документации** закреплено в `GUIDE.md`, `SKILL.md` и памяти: при любом изменении — обновить GUIDE (обе версии) + CHANGELOG + VERSION в том же коммите.
- README: ссылка на GUIDE как главную документацию.

## [1.4.0] — 2026-05-29

### Codex как основной мозг (гибридный двойной рантайм)

Полная адаптация под сценарий, когда оркестратор — Codex CLI, а не Claude. Принцип гибрида: наши скрипты для уникального (РФ-источники, Serpstat/SpyFu, кэш, guard'ы, публикация); нативные Codex-skills для изображений/браузера/делегирования; **без `codex exec` самовызовов**.

- **RUNTIME-режим:** `runtime: auto|claude|codex` в конфиге + env `SEO_RUNTIME`. Авто-детект Codex по env-признакам.
- **`llm-cli-collect.sh`** — RUNTIME-aware: в codex-режиме запускает только `agy`, печатает промпт для нативного сбора Codex (web_search), без вложенного `codex exec`.
- **`img-generate.sh`** — перенесён в скилл, RUNTIME-aware: claude → `codex exec` обёртка; codex → вывод `CODEX_NATIVE_IMAGE` для нативного `seo-image-gen`/`image`/`sora`. emwoody-версия стала тонким враппером.
- **`docs/codex-runtime.md`** — полный маппинг Claude↔Codex (изображения, браузер, делегирование, сбор, фазы) + детект режима.
- Заполнен `~/.codex/skills/codex-primary-runtime/SKILL.md` — точка входа для Codex-сессии.
- `runtime` добавлен в `project.template.yaml`; секция RUNTIME в `SKILL.md`.

## [1.3.0] — 2026-05-29

### Слой данных + уведомления (Этап 1 автоматизации — без n8n/Next.js)

После разбора «n8n vs Next.js vs CLI»: вместо тяжёлой инфры — тонкий слой к существующему ядру.
- **`scripts/db-sync.py`** — собирает CSV/JSON-артефакты (keyword-queue, source-attribution, publish-log, monitoring snapshots, api usage) в единую `seo/seo.db` (SQLite). Фундамент под дашборды (Obsidian/Metabase/Next.js) и алерты. Устойчив к отсутствию файлов, идемпотентен.
- **`scripts/notify.py`** — Telegram-уведомления одним скриптом (без n8n). Graceful no-op без токена (pipeline не ломается). `--test`, уровни info/warn/alert.
- Интеграция: `approval-gate.py` шлёт алерт при создании тикета; `monthly-runner.sh all` — при сбое проекта.
- Секции `data_store` + `notifications` в `project.template.yaml`, `.env.example` (TELEGRAM_*). `seo/seo.db` в .gitignore.

### SpyFu (новый источник Phase 2 — competitor/PPC для US/UK/EU)

- **`scripts/spyfu-fetch.py`** — клиент SpyFu API (Basic auth из `API_SpyFu_ID:API_SpyFu_secret_key`). Подкоманды: `usage`, `domain-stats` (latest/all), `raw`. ⚠ Покрывает только западные рынки (countryCode US/GB/DE/...), **RU отвергается** — поэтому в профилях us/eu/global, в ru → `sources_disable` с причиной.
- Защита $-бюджета (Pro $40/мес, pay-as-you-go): локальный usage-трекер с месячным сбросом + CPM-таблица по эндпоинтам, блок при достижении `--budget`. Кэш 30 дней, дистиллят → stdout.
- Добавлен в `region-profiles` (us/eu/global), `project.template.yaml`, `.env.example`, Phase 2 SKILL.

### Serpstat (новый источник Phase 2 — volume/KD/конкуренты для РФ/СНГ)

- **`scripts/serpstat-fetch.py`** — клиент Serpstat API v4 (JSON-RPC). Подкоманды: `stats` (бесплатно), `keywords-info`, `related`, `suggestions`, `domain-keywords`, `competitors`. Работает с `g_ru` — закрывает дыру Ahrefs/SEMrush в РФ.
- Защита кредитов (план Appsumo 1000/мес, 1 req/sec): pre-flight через getStats + `--min-credits` guard, `--size` лимит строк, кэш на диск (`--ttl 30`), rate-limit 1.1с/запрос. Сырьё → диск, дистиллят (md-таблица) → stdout.
- Добавлен в `region-profiles` (ru/eu/us/global), `project.template.yaml`, `.env.example` (`SERPSTAT_API_KEY`), Phase 2 SKILL.

### Региональные профили источников (универсальность по странам)

- **`config/region-profiles/{ru,eu,us,global}.yaml`** — пресет источников на регион. Проект задаёт одной строкой `region_profile: ru`. ru = Яндекс-приоритет + Google-инструменты доступные из РФ, Ahrefs/SEMrush выключены, DataForSEO через прокси. eu/us = Google-моно + полный западный SaaS, Яндекс off, ATP без перевода.
- **`scripts/resolve-sources.py`** — разворачивает профиль + локальные override → список активных/пропущенных источников с причиной + `seo/cycles/<date>/active-sources.json`. Legacy-режим для конфигов без `region_profile`.
- `validate-config.py` научен резолвить активность источников через профиль.

### Экономия токенов

- **`scripts/research-cache.py`** — TTL-кэш (`research_cache_ttl_days`, дефолт 14): дорогой сбор не перезапускается, если свежий результат на диске. Подключён в `llm-cli-collect.sh`.
- LLM-CLI **deep-режим**: Codex `model_reasoning_effort=xhigh` + `web_search=live` явно; Antigravity + Perplexity — через deep-преамбулы промптов.
- Правило в SKILL: «сырьё на диск, в контекст — только `*-merged-*.md` / дистилляты».

### E-E-A-T

- **`scripts/schema-org-build.py`** — канонический Organization/LocalBusiness узел из `business_profile` конфига (@id, trust-сигналы: address/telephone/openingHours/areaServed/knowsAbout/sameAs); `inject` переписывает author/publisher всех Article/Product на @id-референс (идемпотентно).
- **`scripts/eeat-render.py`** — из `fact_check_log` frontmatter рендерит видимый trust-блок «Источники» (только verdict достоверно/частично).
- **`scripts/source-attribution.py`** — замыкает петлю: какой источник семантики дал ключи в топ (джойн `source-attribution.csv` × snapshot) → рекомендации, какие источники отключить.
- `business_profile` + `region_profile` + `research_cache_ttl_days` добавлены в `project.template.yaml`.

### Масштабирование на N проектов

- **`config/projects-registry.yaml`** — реестр всех проектов (path/region_profile/cms/status/monthly_automation).
- `init-project.sh` — выбирает `region_profile` по стране и дозаписывает проект в реестр.
- `monthly-runner.sh all [subcmd]` — итерация по активным проектам реестра.

## [1.2.0] — 2026-05-28

### Step 10 — Monthly Automation (MVP + Full)

**4-system automated monthly workflow** заменяющий команду из 4 SEO-специалистов:
- System 1 — Keyword Research (replenish queue)
- System 2 — Weekly Publisher (Mon 9am, 4 posts/mo)
- System 3 — Monthly Site Audit (Week 2)
- System 4 — Refresh + Deindex Rescue (Week 3-4)

**Новые скрипты (5):**
- `scripts/keyword-queue.py` — FIFO очередь ключей (add/pop/approve/publish/status)
- `scripts/approval-gate.py` — file-based approval tickets (5 типов)
- `scripts/monthly-runner.sh` — auto-detect day/week → запуск операции; парсит расписание из yaml
- `scripts/deindex-detect.py` — sitemap vs GSC diff + HTTP classification (deindex/4xx/5xx/noindex/redirect)
- `scripts/monthly-dashboard.py` — auto-generated status dashboard в markdown

**Новые subagents (6 экспертов в `~/.claude/agents/`):**
- `seo-monthly-orchestrator` — top-level координатор расписания и approval gates
- `seo-keyword-queue-manager` — System 1 expert (replenish + Phase 2 research)
- `seo-weekly-publisher` — System 2 expert (pop → entity-map → write → QA → approval → publish)
- `seo-monthly-auditor` — System 3 expert (P0+P1 filter, approval перед фиксами)
- `seo-refresh-rescuer` — System 4 expert (refresh + полный deindex workflow)
- `seo-approval-gate` — helper для всех 5 approval точек

Все subagents в стандарте Anthropic Agent Skills (YAML frontmatter + markdown) — **работают в Claude Code и Codex CLI без модификаций**.

**Новые templates (1):**
- `templates/keyword-queue.template.csv` — стартовый шаблон очереди

**Новые prompts (1):**
- `prompts/page-rewrite-rescue.md` — diagnose + rewrite plan для деиндексированных страниц

**Новая документация (1):**
- `docs/automated-monthly.md` — полный workflow doc (setup cron, approval flow, troubleshooting, cross-platform notes для Codex)

**Обновления existing:**
- `config/project.template.yaml` — секция 21 `monthly_automation` (cron schedule, queue file, approval gates, refresh triggers, deindex)
- `scripts/monthly-runner.sh` — schedule parser из yaml (опц. override defaults)
- `agents/seo-refresh-rescuer.md` — полная реализация DEINDEX RESCUE workflow (вместо placeholder из MVP)

**Регрессия:**
- ✅ emwoody pilot активирован: `monthly_automation.enabled: true`, 5 approved keywords в очереди (minvata×2, shumoizolyacziya, plitochnyy-kley, xps)
- ✅ Все 26 скриптов имеют `--help`
- ✅ End-to-end: deindex-detect на dummy data → diff корректен (2 lost из 5 sitemap)
- ✅ Dashboard для emwoody генерится: TL;DR + queue + approvals + snapshot status

**Personal time (target ~2-3h/month):**
- Approve keyword research: 5 min × 1/mo
- Approve каждый пост: 2 min × 4/mo = 8 min
- Audit review + fixes: 30 min × 1/mo
- Refresh plan review: 10 min × 1/mo
- Deindex rewrite approve: 5 min × variable
- **Total: ~1.5-2 часа в месяц**

**Заменяет:**
- Content Strategist ($3-5k/mo)
- Content Writer ($2-4k/mo)
- Technical SEO ($2-3k/mo)
- Content Editor ($1.5-3k/mo)
- **Total команды: $8.5-15k/mo → Total системы: <$50/mo**

### Roadmap → v1.3

- [ ] `scripts/notification.py` — email на P0 audit findings (опц.)
- [ ] Schedule parser в monthly-runner.sh — полный (сейчас MVP: content + audit)
- [ ] WooCommerce auto-sync для stock-inventory.yaml
- [ ] Shopify / Webflow publish handlers (универсальные)
- [ ] Готовые Schema.org JSON-LD скелеты по project_type
- [ ] DataForSEO fallback для Wordstat
- [ ] Stop-words для DE/TR/PL/EN-более-расширенный

## [1.1.0] — 2026-05-27

### Production-ready upgrade: observability hub + actionable feedback engine

**Архитектурное:**

- Phase 9 переработана как **master observability hub** с единой schema snapshot.json
- Phase 10 = **actionable feedback engine** на декларативных правилах (`config/triggers.yaml`)
- Введён `mode: standard | migration | programmatic` для разных типов циклов
- Новые опц. секции конфига (back-compat): `monitoring`, `eeat`, `migration`, `backlinks`

**Новые скрипты (P0/P1/P2 = 12 шт):**

- `google-trends.py` — pytrends wrapper для сезонности
- `init-project.sh` — интерактивный wizard (7 вопросов → готовый yaml)
- `snapshot-build.py` — нормализатор аналитики в единую schema (5 источников: gsc/ga4/metrika/webmaster/psi)
- `triggers-eval.py` — оценщик правил Phase 10 → markdown action list
- `nw-cli.sh` — universal NeuronWriter wrapper
- `validate-entities.py` — universal entity registry checker
- `psi-fetch.py` — PageSpeed Insights API client (free, без OAuth)
- `gsc-fetch.py` — Search Console API client (service account)
- `ga4-fetch.py` — GA4 Data API client
- `metrika-fetch.py` — Я.Метрика API client (OAuth)
- `webmaster-fetch.py` — Я.Вебмастер API client (OAuth)
- `programmatic-template-gen.py` — data-driven генератор страниц
- `schema-validate.py` — JSON-LD валидатор

**Новые шаблоны:**

- `templates/monitoring-report.template.md` — snapshot отчёт
- `templates/cycle-plan.template.md` — content plan
- `templates/programmatic-page.template.md` — для PSEO
- `templates/hreflang-matrix.template.md` — мультирегион
- `templates/stock-inventory.template.yaml` — перенесён из scripts/, расширен примерами WooCommerce/Shopify

**Новый config:**

- `config/triggers.yaml` — 18 декларативных правил Phase 10

**Новая документация (9 docs):**

- `docs/oauth-setup.md` — единый OAuth setup (GCP + Яндекс), таблица всех env vars
- `docs/troubleshooting.md` — FAQ по типичным ошибкам
- `docs/migration-planner.md` — domain/CMS миграция
- `docs/eeat-audit.md` — E-E-A-T cross-cutting checklist
- `docs/backlink-research.md` — backlink workflow
- `docs/sxo-quality-gates.md` — SXO quality gates
- `docs/international-seo.md` — hreflang strategy
- `docs/image-seo.md` — image SEO checklist
- `docs/video-seo.md` — video SEO + VideoObject schema
- `docs/versioning-migration.md` — upgrade guide для v1.0 → v1.1

**Новые промпты:**

- `prompts/competitor-pages-analysis.md` — глубокий SERP-анализ топ-10

**Новые конфиг-файлы:**

- `.env.example` — шаблон env vars

**Обновления existing:**

- `SKILL.md` — Phase 0 (mode), Phase 9 (snapshot pipeline + единая schema), Phase 10 (triggers engine + декларативные правила)
- `INSTALL.md` — TL;DR Вариант A: интерактивный wizard
- `config/project.template.yaml` — schema v1.1, новые секции 17-20
- `scripts/validate-config.py` — поддержка v1.1 расширений + OAuth env vars check

**Регрессия:**

- ✅ Existing `emwoody/seo-cycle.yaml` валидируется без новых ошибок
- ✅ End-to-end pipeline: API → snapshot → triggers → markdown action list
- ✅ Все 7 P0 + 5 P1 fetcher скриптов имеют `--help`
- ✅ programmatic-template-gen + schema-validate тестируется на dummy данных

### Известные ограничения

- AnswerThePublic не поддерживает регион Россия — используем en/us для шаблонов с переводом
- LLM CLI (Antigravity / Codex) могут давать разный результат, нужен merge через `llm-cli-merge.py`
- Perplexity требует ручной установки Claude for Chrome extension — autosetup невозможен
- ATP может создать все провайдеры даже когда указан один — кредитный овершут возможен

### Roadmap → v1.2

- [ ] `scripts/stock-sync-woo.py` — авто-синк stock-inventory.yaml из WooCommerce
- [ ] `scripts/stock-sync-shopify.py` — то же для Shopify
- [ ] `scripts/backlinks-normalize.py` — нормализация backlinks export в snapshot
- [ ] `scripts/hreflang-validate.py` — валидация hreflang кросс-ссылок
- [ ] Shopify / Webflow publish handlers (универсальные)
- [ ] Schema.org templates по project_type (готовые JSON-LD скелеты)
- [ ] DataForSEO интеграция как fallback для Wordstat
- [ ] Поддержка немецкого / турецкого / польского tone of voice в `check-stop-words.py`

## [1.0.0] — 2026-05-26

### Initial release — универсальный SEO-цикл скилл

[см. предыдущую версию CHANGELOG ниже]

**Что внутри:**

- `SKILL.md` — оркестратор 10 фаз
- `INSTALL.md` — wizard для нового проекта
- `config/project.template.yaml` — полная схема конфига
- 4 универсальных промпта, 2 шаблона, 4 doc
- 7 переносимых скриптов (validate-config, check-stop-words, yandex/google suggest, atp-fetch, llm-cli×2, obsidian-sync)
- 16 sources в config (Yandex 8, Google 5, NW 1, LLM CLI 1, ATP 1)
- 12 делегатов через `~/.claude/agents/` и `claude-seo:*` plugin skills
- Obsidian-интеграция (через obsidian-native-mcp + obsidian-sync.py)
- 5 kepano-skills установлены параллельно
