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
python3 ~/.codex/skills/seo-cycle/scripts/lighthouse-audit.py seo-cycle.yaml --input-json lighthouse.json --url https://example.com/ --write
python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action basic-info --report-id 123456 --write
python3 ~/.codex/skills/seo-cycle/scripts/labrika-source-pack.py seo-cycle.yaml --export-file labrika-export.md --write
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
SERPSTAT_API_KEY=... python3 ~/.codex/skills/seo-cycle/scripts/serpstat-audit.py seo-cycle.yaml --action start --project-id 123 --live --write
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
| Broken links | `link-audit.py` | linkinator export/live distillate for 4xx/5xx, redirects, HTTP links |
| Redirect maps | `redirect-map-audit.py` | CSV redirect-map chains, loops, missing targets, optional live check |
| Lighthouse/CWV | `lighthouse-audit.py` | Lighthouse JSON/live distillate for performance, SEO, accessibility, CWV |
| Serpstat Site Audit | `serpstat-audit.py` | guarded project/list/create/start/basic-info/category API adapter |
| Labrika export | `labrika-source-pack.py` | manual/browser export ingestion until public API is confirmed |
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
- `serpstat-audit.py` is guarded. Without `--live` and `SERPSTAT_API_KEY`, it writes a planned request only. `create-project` consumes one project credit; `start` consumes audit credits by checked pages.
- `labrika-source-pack.py` treats Labrika as manual/browser export evidence. Do not assume API automation until Labrika support provides public API/export details.
