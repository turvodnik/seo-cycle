# Research Package Quality + Page Outline v2

This runbook turns the comparison of two SEO tools into a repeatable `seo-cycle`
workflow.

## Why

Site-level research packages are strong at deciding **what to build**:
semantic core, clusters, page types, URL architecture, internal links, entity map,
technical requirements.

Single-page outlines are strong at deciding **how to write one page**:
H2/H3 structure, word counts, entities per section, intro/conclusion, visual
blocks, copywriter notes, copywriting playbook, writer prompt packet, source
slots, acceptance criteria, Answer Units, FAQ, and E-E-A-T tone.

`seo-cycle` now requires both layers for important pages.

## Quality Gate

Run before handing a package to content, design, development, or an agent:

```bash
python3 scripts/research-package-quality.py ./research-package --write
```

For a short startup checklist without the full audit body:

```bash
python3 scripts/research-package-quality.py ./research-package --format plan
```

`--write` now saves:

- `research-package-quality.md`;
- `research-package-quality.json`;
- `research-package-action-plan.md`.

The report includes a 10-criterion scorecard:

- structure and architecture;
- keyword universe and cleanliness;
- SERP and intent validation;
- cluster and URL mapping;
- entity and semantic coverage;
- copywriter-ready brief depth;
- E-E-A-T and proof layer;
- GEO/AEO/AI citability;
- technical implementation readiness;
- internal consistency and handoff.

Each finding becomes a remediation step with priority, target files, mode,
command, and definition of done.

The gate fails on critical issues:

- missing required package files;
- empty SERP validation for MVP/checked keywords;
- semantic-core URL or cluster drift after reclustering.

High-priority cleanup:

- prompt/spam-like GSC rows;
- duplicate `page-briefs.md` and `mvp-page-briefs.md`;
- orphan internal URLs;
- shallow page briefs.

Medium findings:

- entity-map markdown/yaml drift;
- raw, duplicated Google NLP output not aggregated;
- collected `ai_overview` features not used in GEO/page requirements.
- missing E-E-A-T/evidence layer in briefs/specs.

## Repair Layer

Run the repair wrapper after `research-package-quality.py` finds cleanup or
consistency issues, and before generating fresh page outlines:

```bash
python3 scripts/research-package-repair.py ./research-package --write
```

The wrapper runs the full repair pack and writes
`research-package-repair.md/json`. For targeted reruns, use the exact commands
from `research-package-action-plan.md`:

```bash
python3 scripts/semantic-core-clean.py ./research-package --write
python3 scripts/semantic-core-resync.py ./research-package --write
python3 scripts/entity-map-sync.py ./research-package --write
python3 scripts/google-nlp-aggregate.py ./research-package --write
python3 scripts/orphan-url-resolver.py ./research-package --write
python3 scripts/serp-validation-plan.py ./research-package --write
python3 scripts/serp-validation-import.py ./research-package --input-json serp-export.json --write
python3 scripts/spoke-opportunity-audit.py ./research-package --write
python3 scripts/entity-graph-quality.py ./research-package --write
```

Outputs:

- `research-package-repair.md/json` summarizes all repair steps, their status,
  commands, stderr snippets and expected outputs.
- `semantic-core.cleaned.csv` and `semantic-core.rejected.csv` separate
  prompt/spam-like GSC rows from usable keyword rows.
- `semantic-core.resynced.csv` aligns old cluster IDs and URLs to the final
  architecture after reclustering.
- `entity-map.md` is rendered from `entity-map.yaml`, so Markdown/YAML cannot
  silently diverge.
- `entity_coverage.jsonl` aggregates Google NLP mentions, salience, variants
  and types into a compact downstream entity-coverage layer.
- `content-plan.orphan-backlog.csv` turns referenced-but-missing URLs into
  reviewable backlog rows or remove/replace-link actions.
- `serp-validation-plan.csv` lists queries whose page-type decisions still need
  SERP evidence.
- `serp-validation-import.md/json` records reviewed DataForSEO, Serpstat, or
  manual SERP exports imported back into `semantic-architecture-final.json`.
  The importer is guarded: it only reads explicit `--input-json`/`--input-csv`
  files and preserves non-empty validation unless `--force` is used.
- `spoke-opportunities.csv` promotes measured long-tail demand into phase-2
  hub-and-spoke opportunities.
- `entity-graph-quality.md/json` catches duplicate triples, orphan relation
  endpoints and entity weights without an explicit source.

After repair, rerun:

```bash
python3 scripts/research-package-quality.py ./research-package --write
```

Treat remaining critical findings as blockers for outline generation.

## Deep Page Brief

After the package passes the gate, generate one deep outline per MVP/P1 page:

```bash
python3 scripts/page-outline-v2.py ./research-package \
  --page "/tools/virtual-hair-color-try-on/" \
  --write
```

Batch modes:

```bash
python3 scripts/page-outline-v2.py ./research-package --all-mvp --write
python3 scripts/page-outline-v2.py ./research-package --priority P1 --write
python3 scripts/page-outline-v2.py ./research-package --all-mvp --write --archive-legacy-briefs
```

Use `--archive-legacy-briefs` only after reviewing the generated v2 outlines.
It moves duplicate `page-briefs.md` and `mvp-page-briefs.md` into
`archive/legacy-briefs/`; without that explicit flag, legacy files stay in
place.

The output includes:

- computed word-count totals from sections;
- metrics rollup from the preferred semantic core: volume, clicks, impressions,
  priority score, matched rows, and top supporting keywords so writers do not
  need to open CSV files;
- intro and conclusion briefs with word-count ranges, hook/recap strategy, CTA,
  constraints, and internal-link priorities;
- SEO meta: title tag, meta description, slug, canonical, and alt-text guidance;
- answer-first Key Takeaways;
- FAQ answer units ready for FAQPage review;
- numbered visual plan with placement and dedupe keys;
- section bridges so the page reads as one funnel, not isolated blocks;
- writer handoff with must-do, must-not, fact-check queue, and safe memorable lines;
- `copywriting_playbook`: page job, before/after reader state, tone contract,
  angle stack, draft sequence, banned patterns, and revision checklist;
- `writer_prompt_packet`: low-token role, input/output contracts, forbidden
  actions, acceptance gate, and starter prompt for the next writing agent;
- deterministic H3 subsection plans under every H2, where H3 word counts add up
  to the parent H2 range;
- section copywriting details: reader question, opening angle, do-write,
  do-not-write, safe phrases, CTA, source slots, and acceptance criteria;
- entities and keywords per section;
- visual elements;
- copywriter notes;
- Answer Unit requirements;
- evidence requirements;
- schema;
- internal links;
- GEO requirements;
- synthetic AI prompts;
- E-E-A-T guard that blocks invented first-person expertise by default.

Use `--expert-author` only when the project has a real named expert/author and
the page can prove that expertise.

## Page Outline Quality Gate

Run immediately after generating MVP/P1 outlines and before writing, design,
schema, approvals, or publishing:

```bash
python3 scripts/page-outline-quality.py ./research-package --write --format markdown
```

`--write` saves:

- `page-outline-quality.md`;
- `page-outline-quality.json`;
- `latest-page-outline-quality.md`;
- `latest-page-outline-quality.json`.

The gate uses a 10-criterion scorecard for:

- word-count integrity;
- H3/H2 word-count allocation;
- SERP/page-type and intent lock;
- entity coverage and graph usefulness;
- copywriter actionability;
- E-E-A-T no-fabrication safety;
- GEO/AEO Answer Units;
- technical SEO wrapper;
- internal links and cannibalization guard;
- visual/UX guidance;
- machine-readable handoff.

Critical findings block downstream writing/publishing. High/medium findings
become action-plan steps and should be accepted only after review.

The gate now also blocks outlines that look complete at the macro level but are
still weak for copywriting: missing intro/conclusion briefs, missing H3
subsections, H3 totals that drift from the parent H2, vague section writing
instructions, missing source slots, missing acceptance criteria, missing
copywriting playbook, missing revision checklist, or missing writer prompt
packet.

This combines the useful competitor-outline advantages with the stronger
seo-cycle architecture: micro-level copywriter guidance is generated only after
SERP/page-type, URL, cluster, internal-link, entity and no-fabrication context is
locked by the research package.

## Draft Quality Gate

After a draft is written from `copywriting_playbook` and
`writer_prompt_packet`, validate it against the exact outline:

```bash
python3 scripts/draft-quality-gate.py ./draft.md \
  --outline ./research-package/page-outlines-v2/page.json \
  --write
```

The gate flags missing H2/H3 sections, required internal links, proof/source
slots, FAQ mismatches and unsafe first-person expertise claims. It is a final
copywriting safety check before schema, CMS publishing or approval.

## Pipeline

1. Build or receive a research package.
2. Run `research-package-quality.py`.
3. Open `research-package-action-plan.md` and follow the automatic steps.
4. Run `research-package-repair.py --write`, or the targeted repair commands
   from the action plan when only one layer needs rerun.
5. If SERP was checked outside seo-cycle, import the reviewed export with
   `serp-validation-import.py --input-json/--input-csv --write`.
6. Rerun `research-package-quality.py --write` and fix remaining critical/high
   findings.
7. Generate `page-outline-v2.py --all-mvp` or `--priority P1`.
8. Run `page-outline-quality.py --write` and follow its action plan.
9. Rerun `project-journey.py --write`; proceed only when the current stage
   moves past `deep_page_briefs`.
10. For drafting, pass only the page outline plus its `copywriting_playbook` and
   `writer_prompt_packet` into the active LLM context.
11. Run `draft-quality-gate.py` on the finished draft.
12. Review the generated outline before writing, design, schema, or approval.
13. Keep raw data on disk; open raw CSV/JSON/SERP only when a source slot or
    fact-check queue item asks for a specific source.

`project-journey.py` treats `research-package-repair.json` newer than
`research-package-quality.json` as a blocker. Rerun the quality gate after any
repair/import before generating or trusting page outlines.

## Updating Existing Projects

From an already bootstrapped project root:

```bash
curl -fsSL https://raw.githubusercontent.com/turvodnik/seo-cycle/main/bootstrap-codex.sh | bash -s -- --skip-init
python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-assistant.py --write
python3 ./.codex/skills/seo-cycle/scripts/project-upgrade-apply.py --write
python3 ./.codex/skills/seo-cycle/scripts/setup-control-plane.py --write
```

Review `seo/setup/upgrade-questionnaire.csv` before any `--apply`. The updater
does not add secrets, paid API approval, tracking tags, publishing, or schedule
installation automatically.
