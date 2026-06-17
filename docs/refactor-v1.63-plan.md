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
  `seo_cycle_core.reports` now owns artifact writes/path stringification,
  `seo_cycle_core.subprocesses` now owns command-step capture/JSON parsing, and
  `task-router.py`, `project-journey.py`, `setup-control-plane.py`, and
  `setup-blueprint.py` use the shared layer.
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
