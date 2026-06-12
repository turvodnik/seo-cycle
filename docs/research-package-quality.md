# Research Package Quality + Page Outline v2

This runbook turns the comparison of two SEO tools into a repeatable `seo-cycle`
workflow.

## Why

Site-level research packages are strong at deciding **what to build**:
semantic core, clusters, page types, URL architecture, internal links, entity map,
technical requirements.

Single-page outlines are strong at deciding **how to write one page**:
H2/H3 structure, word counts, entities per section, intro/conclusion, visual
blocks, copywriter notes, source slots, acceptance criteria, Answer Units, FAQ,
and E-E-A-T tone.

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
```

The output includes:

- computed word-count totals from sections;
- intro and conclusion briefs with word-count ranges, hook/recap strategy, CTA,
  constraints, and internal-link priorities;
- SEO meta: title tag, meta description, slug, canonical, and alt-text guidance;
- answer-first Key Takeaways;
- FAQ answer units ready for FAQPage review;
- numbered visual plan with placement and dedupe keys;
- section bridges so the page reads as one funnel, not isolated blocks;
- writer handoff with must-do, must-not, fact-check queue, and safe memorable lines;
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
instructions, missing source slots, or missing acceptance criteria.

This combines the useful competitor-outline advantages with the stronger
seo-cycle architecture: micro-level copywriter guidance is generated only after
SERP/page-type, URL, cluster, internal-link, entity and no-fabrication context is
locked by the research package.

## Pipeline

1. Build or receive a research package.
2. Run `research-package-quality.py`.
3. Open `research-package-action-plan.md` and follow the automatic steps.
4. Fix critical/high findings.
5. Generate `page-outline-v2.py --all-mvp` or `--priority P1`.
6. Run `page-outline-quality.py --write` and follow its action plan.
7. Rerun `project-journey.py --write`; proceed only when the current stage
   moves past `deep_page_briefs`.
8. Review the generated outline before writing, design, schema, or approval.
9. Keep raw data on disk; pass only quality reports and page outlines into the
   active LLM context.
