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

## Next Slices

1. Wrap the research package lane.
   - Stage: `research-package-quality.py`.
   - Repair: `research-package-repair.py`.
   - Rerun: `research-package-quality.py`.
   - Next: `page-outline-v3.py`.

2. Wrap the copywriting lane.
   - Stage: `page-outline-v3.py`.
   - Gate: `page-outline-quality.py --version v3`.
   - Stage: draft creation by human/agent.
   - Gate: `draft-quality-gate.py`.

3. Wrap setup readiness.
   - Stage: `setup-control-plane.py`.
   - Gate: project journey with `--fail-on-blocker`.
   - Repair: safe setup refreshes only, no secret writes.

4. Add project-local contract templates.
   - Suggested path: `seo/stages/*.yaml`.
   - Keep templates secret-free and approval-aware.

5. Add a small panel surface later.
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
