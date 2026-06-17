# v1.63 Refactor Plan

This plan keeps the seo-cycle refactor small and reversible. The goal is not to
replace the existing command surface, but to add a staged control layer that can
gradually wrap high-risk flows.

## Current Slice

Status: implemented as the v1.63 pilot.

- Add a tiny `seo_cycle_core` package with stage contracts, gates, repairs and
  orchestrator reports.
- Add `seo-cycle-run.py` as the CLI wrapper.
- Keep all existing scripts callable directly.
- Add regression tests for defaults, repair/rerun, blocker reports and CLI JSON
  execution.
- Document the contract and artifacts.
- Start shared helper extraction without a large rewrite:
  `seo_cycle_core.reports` now owns artifact writes/path stringification and
  sorted JSON output when a legacy report requires it,
  `seo_cycle_core.subprocesses` now owns command-step capture/JSON parsing, and
  `task-router.py`, `project-journey.py`, `setup-control-plane.py`,
  `setup-blueprint.py`, `launch-plan.py`, `spend-guard.py`,
  `tool-stack-recommender.py`, `setup-onboarding.py`, and
  `growth-roadmap.py`, `project-upgrade-assistant.py`,
  `access-key-assistant.py`, `setup-answer-plan.py`, and
  `setup-gap-audit.py`, `context-pack.py`, `project-upgrade-apply.py`,
  `automation-recommender.py`, `stage-template-export.py`,
  `usage-ledger.py`, `orchestrator-panel.py`, `automation-plan.py`,
  `vnext_audit_core.py`, `ai-bot-access-check.py`,
  `research-package-quality.py`, `page-outline-quality.py`, and
  `draft-quality-gate.py`, `semantic-core-clean.py`,
  `semantic-core-resync.py`, `entity-map-sync.py`,
  `google-nlp-aggregate.py`, `orphan-url-resolver.py`,
  `serp-validation-plan.py`, `serp-validation-import.py`,
  `spoke-opportunity-audit.py`, `entity-graph-quality.py`, and
  `research-package-repair.py`, `writerzen-browser-collect.py`, and
  `project-intake-wizard.py` use the shared report layer.
- Move `project-intake-wizard.py` onto shared `seo_cycle_core.config`
  config/path/YAML helpers as the first post-report helper extraction.
- Move setup surface scripts onto shared `seo_cycle_core.config`
  config/path/policy helpers: `setup-blueprint.py`, `launch-plan.py`,
  `spend-guard.py`, `setup-onboarding.py`, `growth-roadmap.py`,
  `setup-answer-plan.py`, and `setup-gap-audit.py`.
- Move runtime/control scripts onto shared `seo_cycle_core.config`
  config/path/policy helpers: `automation-plan.py`,
  `automation-recommender.py`, `usage-ledger.py`, and
  `tool-stack-recommender.py`.
- Move legacy setup/config scripts onto shared `seo_cycle_core.config`
  config/path/policy helpers: `governance-report.py`,
  `project-profile.py`, `project-upgrade-assistant.py`, and
  `access-key-assistant.py`.
- Move technical discovery scripts onto shared `seo_cycle_core.config`
  config discovery/YAML helpers: `validate-config.py`,
  `resolve-sources.py`, `schema-org-build.py`, and `wp-photo-image.py`.
- Add a built-in research package lane template:
  `seo-cycle-run.py --stage-template research-package --package <path>` wraps
  quality -> repair/rerun -> v3 briefs -> v3 outline quality without requiring
  users to hand-write a stage YAML first.
- Add a built-in copywriting lane template:
  `seo-cycle-run.py --stage-template copywriting --draft <draft.md>` wraps
  `draft-quality-gate.py --fail-on-error` for one existing draft while keeping
  the legacy draft gate exit behavior unchanged unless the flag is used.
- Add a built-in setup readiness lane template:
  `seo-cycle-run.py --stage-template setup-readiness --goal <task>` wraps
  `setup-control-plane.py --write` behind `project-journey.py
  --fail-on-blocker`, with one safe repair refresh and a blocker report when
  human setup fields, access setup or approvals are still missing.
- Add project-local contract templates:
  `stage-template-export.py --write` creates editable
  `seo/stages/setup-readiness.yaml`, `seo/stages/research-package.yaml` and
  `seo/stages/copywriting-draft.yaml`; `setup-control-plane.py --write`
  refreshes them without overwriting manual edits.
- Add a small read-only panel surface:
  `orchestrator-panel.py` reads `seo/orchestrator/latest-run.json`, summarizes
  current stage/blockers and writes `seo/orchestrator/panel.md/json` on demand
  without executing commands or exposing raw command logs.

## Next Slices

1. Continue helper extraction in small groups.
   - Move repeated report path definitions where they are stable.
   - Prefer scripts that already use `seo_cycle_core.config`.
   - Keep direct script behavior and CLI output unchanged.

2. Keep the panel read-only while iterating on display fields.
   - It should keep reading `seo/orchestrator/latest-run.json`.
   - It should not execute paid/browser/publish actions.

## Non-Goals For v1.63

- No full UI.
- No autonomous publishing.
- No automatic indexing submission.
- No secret storage.
- No migration of all scripts into one framework.
- No deletion of legacy commands.

## Quality Gates

Every slice should keep these checks:

- New behavior gets a failing test first.
- `python3 -m unittest tests/test_orchestrator_core.py`.
- `python3 -m unittest discover -s tests`.
- `git diff` review.
- Secret scan before commit/push.
