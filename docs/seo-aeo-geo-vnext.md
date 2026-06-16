# SEO/AEO/GEO vNext report layer

The vNext layer adds report-only diagnostics and data contracts on top of the
classic `seo-cycle` phases. It is designed for SEO, AEO, GEO, local SEO,
Russian ecommerce, AI visibility, and source-backed content planning.

## Safety defaults

- No publishing.
- No index submission.
- No tracking tag installation.
- No paid API calls.
- No ads or billing-dependent actions.
- Raw logs, transcripts, and exports stay on disk; reports use distillates and
  JSONL records.
- Perplexity and NotebookLM are provider layers, not required hard dependencies:
  check health first, cache raw outputs, and pass only distillates with
  citations to downstream prompts.

## Commands

Run the full report pack:

```bash
python3 ~/.codex/skills/seo-cycle/scripts/token-waste-audit.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/perplexity-health.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/notebooklm-health.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/perplexity-collect.py seo-cycle.yaml --topic "Плита ОСП" --write
python3 ~/.codex/skills/seo-cycle/scripts/notebooklm-source-pack.py seo-cycle.yaml --topic "SEO evidence" --export-file notebook.md --write
python3 ~/.codex/skills/seo-cycle/scripts/expert-source-pack.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/ai-brand-audit.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/answer-units-audit.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/eeat-evidence-map.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/geo-kpi-model.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/technical-guardrails-audit.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/snippet-sitemap-audit.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/traffic-drop-diagnostics.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/cannibalization-audit.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/log-bot-audit.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/ai-bot-access-check.py seo-cycle.yaml --url https://example.com/ --write
python3 ~/.codex/skills/seo-cycle/scripts/link-audit.py seo-cycle.yaml --input-json linkinator.json --url https://example.com/ --write
python3 ~/.codex/skills/seo-cycle/scripts/redirect-map-audit.py seo-cycle.yaml --input redirects.csv --base-url https://example.com --write
python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py seo-cycle.yaml --input-json gsc-url-inspection.json --url https://example.com/ --site-url sc-domain:example.com --write
python3 ~/.codex/skills/seo-cycle/scripts/gsc-indexing-export-browser.py seo-cycle.yaml --issue-url "<GSC Pages issue URL>" --manual-fallback-seconds 120 --build-queue --write
python3 ~/.codex/skills/seo-cycle/scripts/gsc-indexing-queue.py seo-cycle.yaml --gsc-discovered-file exports/discovered.csv --gsc-performance-file exports/gsc-performance.json --woocommerce-file exports/woocommerce.csv --technical-check --top 20 --write
python3 ~/.codex/skills/seo-cycle/scripts/gsc-request-indexing-browser.py seo-cycle.yaml --queue-file seo/technical/gsc-indexing-request-queue.csv --max 10 --auto-click --write
python3 ~/.codex/skills/seo-cycle/scripts/gsc-indexing-recheck.py seo-cycle.yaml --submitted-log seo/technical/gsc-indexing-submit.json --gsc-discovered-file exports/discovered-after-7d.csv --gsc-performance-file exports/gsc-performance-after-7d.json --write
python3 ~/.codex/skills/seo-cycle/scripts/indexnow-submit.py seo-cycle.yaml --queue-file seo/technical/gsc-indexing-request-queue.csv --priority P0,P1 --max 100 --live --write
python3 ~/.codex/skills/seo-cycle/scripts/yandex-recrawl-submit.py seo-cycle.yaml --queue-file seo/technical/gsc-indexing-request-queue.csv --priority P0,P1 --max 20 --live --write
python3 ~/.codex/skills/seo-cycle/scripts/yandex-recrawl-submit.py seo-cycle.yaml --mode status --live --write
python3 ~/.codex/skills/seo-cycle/scripts/bing-url-inspection.py seo-cycle.yaml --input-json bing-url-info.json --url https://example.com/ --site-url https://example.com/ --write
python3 ~/.codex/skills/seo-cycle/scripts/technical-mcp-health.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/lighthouse-audit.py seo-cycle.yaml --input-json lighthouse.json --url https://example.com/ --write
python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action basic-info --report-id 123456 --write
python3 ~/.codex/skills/seo-cycle/scripts/labrika-source-pack.py seo-cycle.yaml --export-file labrika-export.md --write
python3 ~/.codex/skills/seo-cycle/scripts/labrika-health.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/technical-site-audit.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/ru-commerce-readiness.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/offpage-risk-audit.py seo-cycle.yaml --write
python3 ~/.codex/skills/seo-cycle/scripts/conversion-sxo-audit.py seo-cycle.yaml --write
```

Optional inputs:

```bash
python3 ~/.codex/skills/seo-cycle/scripts/technical-guardrails-audit.py seo-cycle.yaml --robots robots.txt --write
python3 ~/.codex/skills/seo-cycle/scripts/log-bot-audit.py seo-cycle.yaml --log access.log --write
python3 ~/.codex/skills/seo-cycle/scripts/ai-bot-access-check.py seo-cycle.yaml --url https://example.com/ --categories llm,search --write
python3 ~/.codex/skills/seo-cycle/scripts/traffic-drop-diagnostics.py seo-cycle.yaml --input traffic.csv --write
python3 ~/.codex/skills/seo-cycle/scripts/cannibalization-audit.py seo-cycle.yaml --input cannibalization.csv --write
python3 ~/.codex/skills/seo-cycle/scripts/link-audit.py seo-cycle.yaml --live --url https://example.com/ --write
python3 ~/.codex/skills/seo-cycle/scripts/lighthouse-audit.py seo-cycle.yaml --live --url https://example.com/ --write
GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN=... python3 ~/.codex/skills/seo-cycle/scripts/gsc-url-inspection.py seo-cycle.yaml --url https://example.com/ --site-url sc-domain:example.com --live --write
BING_WEBMASTER_API_KEY=... python3 ~/.codex/skills/seo-cycle/scripts/bing-url-inspection.py seo-cycle.yaml --url https://example.com/ --site-url https://example.com/ --live --write
SERPSTAT_API_KEY=... python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action start --project-id 123 --live --write
SERPSTAT_API_KEY=... python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action set-settings --project-id 123 --settings-json serpstat-settings.json --live --write
SERPSTAT_API_KEY=... python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action issue-report --report-id 456 --live --write
```

## Output

Reports are written to `seo/vnext/*.md`, `seo/vnext/*.json`, `seo/technical/*.md`, and `seo/technical/*.json`.

Vector-ready records are expected under:

```text
seo/research/vnext/vector/
├── entities.jsonl
├── relations.jsonl
├── triplets.jsonl
├── sub_intents.jsonl
├── answer_units.jsonl
├── synthetic_prompts.jsonl
├── entity_coverage.jsonl
├── eeat_evidence.jsonl
├── local_seo_signals.jsonl
├── commercial_factors.jsonl
├── ai_visibility_checks.jsonl
├── traffic_diagnostics.jsonl
└── source_pack.jsonl
```

`seo-keywords/scripts/vectorize-records.py` reads these records together with
the classic multi-pass files to build `similarity.jsonl` and
`neighbor-report.md`.

## Module map

| Module | Script | Primary output |
| --- | --- | --- |
| Token efficiency | `token-waste-audit.py` | raw/large artifact findings and distillate requirements |
| Perplexity provider | `perplexity-health.py`, `perplexity-collect.py` | persistent app/browser/API/fallback readiness, raw/distillate/vector evidence cache |
| NotebookLM provider | `notebooklm-health.py`, `notebooklm-source-pack.py` | MCP/export fallback readiness, curated expert source-pack ingestion |
| Expert sources | `expert-source-pack.py` | NotebookLM/articles/videos source queue |
| AI Brand Audit | `ai-brand-audit.py` | AI prompt pack and brand gap checks |
| Answer Units | `answer-units-audit.py` | Citation-ready paragraph contract |
| E-E-A-T Evidence | `eeat-evidence-map.py` | Evidence/schema/trust map |
| GEO KPI | `geo-kpi-model.py` | AI mention/citation/accuracy KPI model |
| Server logs | `log-bot-audit.py` | Search/AI bot and crawl waste summary |
| AI bot access | `ai-bot-access-check.py` | Live robots.txt + HTTP User-Agent access report |
| Technical guardrails | `technical-guardrails-audit.py` | robots/indexability/AJAX/schema checks |
| Technical rollup | `technical-site-audit.py` | Aggregates latest technical reports into one bounded rollup; no live calls |
| Broken links | `link-audit.py` | linkinator export/live distillate for 4xx/5xx, redirects, HTTP links |
| Redirect maps | `redirect-map-audit.py` | CSV redirect-map chains, loops, missing targets, optional live check |
| Lighthouse/CWV | `lighthouse-audit.py` | Lighthouse JSON/live distillate for performance, SEO, accessibility, CWV |
| Google URL Inspection | `gsc-url-inspection.py` | guarded URL Inspection JSON/live read-only adapter |
| GSC indexing export | `gsc-indexing-export-browser.py` | captures GSC Pages issue CSV/XLSX downloads through a persistent browser profile |
| GSC indexing queue | `gsc-indexing-queue.py` | builds P0/P1 queue from discovered/not-indexed export + sitemap + WooCommerce + GSC impressions; filters junk and technical blockers |
| GSC request indexing helper | `gsc-request-indexing-browser.py` | opens Search Console URL Inspection in a persistent browser profile; `--auto-click` is explicit and guarded |
| GSC indexing recheck | `gsc-indexing-recheck.py` | 3-7 day follow-up from fresh GSC exports/search data |
| IndexNow submit | `indexnow-submit.py` | guarded bulk POST to IndexNow/Bing-compatible endpoint using `INDEXNOW_KEY` and queue CSV |
| Yandex recrawl | `yandex-recrawl-submit.py` | guarded Yandex Webmaster `/recrawl/queue` submit and status check |
| Bing URL Inspection | `bing-url-inspection.py` | guarded Bing Webmaster `GetUrlInfo` JSON/live read-only adapter |
| Technical MCP health | `technical-mcp-health.py` | optional readiness check for mcp-gsc, Google Analytics MCP and Lighthouse MCP |
| Serpstat Site Audit | `serpstat-audit.py` | guarded project/list/create/start/settings/issue reports/export/basic-info/category API adapter |
| Labrika export/health | `labrika-source-pack.py`, `labrika-health.py` | manual/browser export ingestion and API readiness until public API is confirmed |
| Snippet/sitemap | `snippet-sitemap-audit.py` | XML/HTML sitemap and snippet controls |
| Traffic drops | `traffic-drop-diagnostics.py` | traffic-loss playbook |
| Cannibalization | `cannibalization-audit.py` | query to URL conflict detection |
| RU commerce | `ru-commerce-readiness.py` | Yandex Merchant/YCP/Alice readiness |
| Off-page risk | `offpage-risk-audit.py` | donor/acceptor/content island/PBN risk |
| SXO/conversion | `conversion-sxo-audit.py` | CR, pricing UX, trust, FAQ, lead blocks |

## Technical site tools policy

- `link-audit.py` accepts `--input-json` from `linkinator` by default. `--live` runs `npx -y linkinator` and sends public HTTP requests.
- `redirect-map-audit.py` reads CSV exports with `old_url/new_url`, `source/target`, or `from/to`; live checks are explicit.
- `lighthouse-audit.py` prefers a local Lighthouse JSON report or optional Lighthouse MCP workflow. `--live` runs Lighthouse through `npx`.
- `gsc-url-inspection.py` is read-only. Without `--live` and `GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN`, it writes a planned request only.
- `gsc-indexing-export-browser.py` is a browser download helper for the GSC Pages issue export. If `--issue-url` is omitted or the UI changes, use `--manual-fallback-seconds 120`: the browser stays open, you click Export CSV, and the script captures/imports the file.
- `gsc-indexing-queue.py` is the required pre-submit gate for Google request indexing: export “Discovered - currently not indexed” from GSC, cross it with sitemap, WooCommerce and Search Analytics, filter editor/API/cart/feed/preview URLs, optionally run `--technical-check`, then submit only P0/P1.
- `gsc-request-indexing-browser.py` uses the Search Console UI, not a hidden API. It stores no passwords and uses `~/.codex/browser-profiles/gsc`. `--auto-click` must be passed explicitly; otherwise it opens the URL Inspection pages and writes a manual-action report.
- `gsc-indexing-recheck.py` should run after 3-7 days with fresh GSC exports. URLs still in discovered/not-indexed should not be resubmitted blindly; improve content, internal links, sitemap/canonical signals, then rebuild the queue.
- `indexnow-submit.py` is the stronger automation path for Bing/Yandex-compatible discovery: it sends queue URLs to IndexNow only with explicit `--live` and `INDEXNOW_KEY`; the key value is never written to reports. HTTP 200 means the URL was received, not guaranteed indexed.
- `yandex-recrawl-submit.py` sends queue URLs to Yandex Webmaster API v4 `/recrawl/queue` only with explicit `--live`, `YANDEX_OAUTH_TOKEN`, `YANDEX_USER_ID`, and `YANDEX_WEBMASTER_HOST_ID`. Use `--mode status` to check the queue later.
- `bing-url-inspection.py` is read-only. Without `--live` and `BING_WEBMASTER_API_KEY`, it writes a planned request only.
- `technical-mcp-health.py` only checks optional MCP readiness and never installs servers or reads secret values.
- `serpstat-audit.py` is guarded. Without `--live` and `SERPSTAT_API_KEY`, it writes a planned request only. `create-project` consumes one project credit; `start` consumes audit credits by checked pages; settings/issues/export stay approval-gated.
- `labrika-source-pack.py` treats Labrika as manual/browser export evidence. `labrika-health.py` records support questions. Do not assume API automation until Labrika support provides public API/export details.
- `technical-site-audit.py` reads existing latest technical JSON reports and produces a single rollup; it does not run live checks by itself.
