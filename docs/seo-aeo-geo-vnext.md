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

## Commands

Run the full report pack:

```bash
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
```

## Output

Reports are written to `seo/vnext/*.md` and `seo/vnext/*.json`.

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
| Expert sources | `expert-source-pack.py` | NotebookLM/articles/videos source queue |
| AI Brand Audit | `ai-brand-audit.py` | AI prompt pack and brand gap checks |
| Answer Units | `answer-units-audit.py` | Citation-ready paragraph contract |
| E-E-A-T Evidence | `eeat-evidence-map.py` | Evidence/schema/trust map |
| GEO KPI | `geo-kpi-model.py` | AI mention/citation/accuracy KPI model |
| Server logs | `log-bot-audit.py` | Search/AI bot and crawl waste summary |
| AI bot access | `ai-bot-access-check.py` | Live robots.txt + HTTP User-Agent access report |
| Technical guardrails | `technical-guardrails-audit.py` | robots/indexability/AJAX/schema checks |
| Snippet/sitemap | `snippet-sitemap-audit.py` | XML/HTML sitemap and snippet controls |
| Traffic drops | `traffic-drop-diagnostics.py` | traffic-loss playbook |
| Cannibalization | `cannibalization-audit.py` | query to URL conflict detection |
| RU commerce | `ru-commerce-readiness.py` | Yandex Merchant/YCP/Alice readiness |
| Off-page risk | `offpage-risk-audit.py` | donor/acceptor/content island/PBN risk |
| SXO/conversion | `conversion-sxo-audit.py` | CR, pricing UX, trust, FAQ, lead blocks |
