# Staged Orchestrator

`seo-cycle-run.py` is the v1.63 Pifagor SEO skill pilot. It gives the old
seo-cycle scripts a small control shell:

```text
stage -> gate -> repair -> rerun -> next stage
```

It does not rewrite the old commands and does not auto-publish, submit
indexing, spend paid API credits, or store secrets. A stage is allowed to do
only what its command contract says.

## Quick Start

Run the built-in goal pilot from a project root:

```bash
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py \
  --goal "собрать research package" \
  --write
```

This currently runs two stages:

1. `task_route` — calls `task-router.py --task <goal> --write`.
2. `project_journey` — calls `project-journey.py --goal <goal> --write`,
   gates through `project-journey.py --fail-on-blocker`, and repairs once with
   `setup-control-plane.py --task <goal> --write --skip-intake`.

Dry-run the plan without executing commands:

```bash
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py \
  --goal "собрать research package"
```

Run a contract file:

```bash
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py \
  --stage-file seo/stages/research-package.yaml \
  --write \
  --format json
```

Create project-local contract templates:

```bash
python3 ./.codex/skills/seo-cycle/scripts/stage-template-export.py --write
```

This writes:

- `seo/stages/setup-readiness.yaml`
- `seo/stages/research-package.yaml`
- `seo/stages/copywriting-draft.yaml`
- `seo/stages/stage-template-export.md/json`

`setup-control-plane.py --write` runs the exporter automatically. Existing
YAML files are kept untouched unless the exporter is run with `--force`, so
project-specific edits are not overwritten during setup refreshes.

Run the built-in setup readiness lane:

```bash
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py \
  --stage-template setup-readiness \
  --goal "first SEO setup" \
  --write
```

This template runs one stage:

1. `setup_control_plane` — `setup-control-plane.py --task <goal> --write`,
   command gate through `project-journey.py --goal <goal>
   --fail-on-blocker`, and one safe repair refresh through
   `setup-control-plane.py --task <goal> --write --skip-intake
   --skip-automation`.

The setup repair refresh does not apply project profiles, write secret values,
run paid APIs, publish content, submit indexing, or install schedules. If
`project-journey.py` is still blocked after the refresh, the orchestrator writes
a blocker report with the missing human fields, access setup, or approval gates.

Run the built-in research package lane:

```bash
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py \
  --stage-template research-package \
  --package seo/research-package \
  --write
```

This template runs:

1. `research_quality_gate` — `research-package-quality.py --write`, command
   gate through `research-package-quality.py`, repair through
   `research-package-repair.py --write`, up to five repair attempts.
2. `deep_page_briefs_v3` — `page-outline-v3.py --all-mvp --write`, gated by
   generated `copywriter-ready`, `page-outlines-v3`, and vector triplets.
3. `page_outline_quality_v3` — `page-outline-quality.py --version v3 --write`,
   command gate through `page-outline-quality.py --version v3`, repair by
   regenerating v3 briefs, up to five repair attempts.

Run the built-in copywriting lane for one existing draft:

```bash
python3 ./.codex/skills/seo-cycle/scripts/seo-cycle-run.py \
  --stage-template copywriting \
  --package seo/research-package \
  --draft seo/research-package/drafts/sample.md \
  --outline seo/research-package/page-outlines-v3/sample.json \
  --write
```

If `--outline` is omitted, the template uses
`<package>/page-outlines-v3/<draft-stem>.json`. This lane runs
`draft-quality-gate.py --fail-on-error`, writes the draft gate reports next to
the draft, and blocks when error/critical findings remain. It does not create
or rewrite the draft; the repair action is human/agent revision from the
copywriter-ready brief.

## Stage Contract

JSON and YAML are both accepted. YAML requires PyYAML to be installed; JSON
works with the Python standard library.

```yaml
stages:
  - id: research_quality
    title: Research package quality
    required_inputs:
      - seo/research-package/semantic-architecture-final.json
    commands:
      - ["python3", "./.codex/skills/seo-cycle/scripts/research-package-quality.py", "seo/research-package", "--write"]
    outputs:
      - seo/research-package/research-package-quality.json
    gate: {}
    repair_commands:
      - ["python3", "./.codex/skills/seo-cycle/scripts/research-package-repair.py", "seo/research-package", "--write"]
    max_attempts: 5
    approval_required: false
    stop_conditions:
      - Reviewed SERP evidence is still missing.
    next_stage: deep_page_briefs
```

Fields:

- `id` — required stable stage id.
- `title` — human title; defaults to `id`.
- `required_inputs` — files that must already exist before commands run.
- `commands` — main stage commands, in order.
- `outputs` — expected artifacts; used as the gate if no command gate exists.
- `gate.command` — optional command gate. Exit codes in `pass_codes` pass.
  If `gate` is empty, the orchestrator uses an output-existence gate.
- `repair_commands` — commands to run after a failed gate.
- `max_attempts` — maximum repair attempts. Default is `5`.
- `approval_required` — stops the stage until rerun with `--approve`.
- `stop_conditions` — human-readable conditions copied into blocker reports.
- `next_stage` — metadata for the next stage.

Use list-form commands for anything non-trivial. String commands are split with
`shlex`, but list-form avoids quoting surprises.

## Runtime Behavior

For each stage:

1. Check `approval_required`.
2. Check `required_inputs`.
3. Run `commands`.
4. Evaluate `gate.command`, or check that all `outputs` exist.
5. If gate passes, write a stage report and move to the next stage.
6. If gate fails and attempts remain, run `repair_commands`, rerun the stage,
   and gate again.
7. If attempts are exhausted, write a blocker report and stop the run.

`max_attempts` counts repair attempts, not total stage runs. With
`max_attempts: 2`, the sequence is:

```text
stage -> gate -> repair -> stage -> gate -> repair -> stage -> gate -> blocked
```

## Artifacts

With `--write`, reports are written under the current project root:

- `seo/orchestrator/latest-run.md`
- `seo/orchestrator/latest-run.json`
- `seo/orchestrator/<stage-id>-report.md`
- `seo/orchestrator/<stage-id>-report.json`
- `seo/orchestrator/<stage-id>-blocker.md`
- `seo/orchestrator/<stage-id>-blocker.json`

Reports include command exit codes, redacted stdout/stderr, gate attempts,
repair attempts, missing inputs, missing outputs and stop conditions.

## Safety Rules

- No secret values in contracts. Use environment variables through the existing
  project scripts.
- Keep project-local contracts under `seo/stages/`; use `stage-template-export.py
  --write` for safe defaults and edit the YAML per project.
- Keep paid APIs, browser actions, indexing submission and publishing behind
  existing approval gates.
- Use `draft-quality-gate.py --fail-on-error` only when a pipeline needs a
  non-zero exit for error/critical findings; legacy calls without the flag keep
  their historical exit behavior.
- Prefer stage wrappers around proven scripts instead of moving business logic
  into the orchestrator.
- Treat blocker reports as a handoff to a human or a later agent step, not as a
  reason to keep looping.

## Where The Code Lives

- `scripts/seo-cycle-run.py` — CLI entrypoint.
- `scripts/seo_cycle_core/stages.py` — immutable stage/gate contracts.
- `scripts/seo_cycle_core/gates.py` — output and command gate evaluation.
- `scripts/seo_cycle_core/repair.py` — repair command runner.
- `scripts/seo_cycle_core/orchestrator.py` — stage loop, reports and blockers.
- `tests/test_orchestrator_core.py` — regression tests for the pilot contract.
