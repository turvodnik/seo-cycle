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
  `task-router.py`, `project-journey.py`, and `setup-control-plane.py` use the
  shared layer.

## Next Slices

1. Continue helper extraction in small groups.
   - Move repeated report path definitions where they are stable.
   - Prefer scripts that already use `seo_cycle_core.config`.
   - Keep direct script behavior and CLI output unchanged.

2. Wrap the research package lane.
   - Stage: `research-package-quality.py`.
   - Repair: `research-package-repair.py`.
   - Rerun: `research-package-quality.py`.
   - Next: `page-outline-v3.py`.

3. Wrap the copywriting lane.
   - Stage: `page-outline-v3.py`.
   - Gate: `page-outline-quality.py --version v3`.
   - Stage: draft creation by human/agent.
   - Gate: `draft-quality-gate.py`.

4. Wrap setup readiness.
   - Stage: `setup-control-plane.py`.
   - Gate: project journey with `--fail-on-blocker`.
   - Repair: safe setup refreshes only, no secret writes.

5. Add project-local contract templates.
   - Suggested path: `seo/stages/*.yaml`.
   - Keep templates secret-free and approval-aware.

6. Add a small panel surface later.
   - The panel should read `seo/orchestrator/latest-run.json`.
   - It should not execute paid/browser/publish actions without the same
     approval gates as the CLI.

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
