# Frame stack schema transfer validation — 2026-04-20

- Scope: `calamum-moltbook-observer` observer live lane plus disposable sandbox lane
- Task ID: `calamum-moltbook-observer-job-0001-docs_general-20260420`
- Objective: prove the new versioned `JOB.json -> QS.json -> QF.md` contract works in both a disposable sandbox and the real observer task

## Implemented contract changes

- `codesentinel/assets/VAULT_templates/jobpipeline/JOB_CREATE.json.template`
  - now emits `execution_plan.frame_stack_schema_version = "job-frame-stack/v1"`
  - now emits a richer `execution_plan.frames[]` scaffold
- `codesentinel/assets/VAULT_templates/jobpipeline/JOB_CREATE.md.template`
  - now points operators to `JOB.json -> execution_plan.frames`
- `codesentinel/cli/job_utils.py`
  - create fallback surfaces now preserve the same rich scaffold contract
- `codesentinel/cli/jobs_utils.py`
  - versioned frame contract now transfers into `QS.json`
  - richer `QF.md` section renderer now projects the transferred `QS.json` contract
- `tests/cli/test_job_utils.py`
  - targeted create-lane coverage for versioned scaffold + pointer note + fallback preservation
- `tests/cli/test_jobs_lifecycle.py`
  - lifecycle coverage for versioned transfer, placeholder upgrade, rich QF rendering, and legacy graceful degradation

## Pytest evidence

- `pytest tests/cli/test_job_utils.py -k "emits_versioned_frame_stack_scaffold_in_job_json or markdown_points_to_job_json_frame_scaffold or fallback_surfaces_preserve_frame_stack_contract"`
  - result: `3 passed`
- `pytest tests/cli/test_jobs_lifecycle.py`
  - result: `98 passed`

## Sandbox empirical validation (S4)

Primary sandbox packet:

- `report_tmp/frame_stack_schema_transfer/runs/20260420T183343Z_frame-stack-schema-transfer-s4-sandbox/sandbox_validation_summary.md`
- `report_tmp/frame_stack_schema_transfer/runs/20260420T183343Z_frame-stack-schema-transfer-s4-sandbox/sandbox_validation_summary.json`

Sandbox findings:

- a disposable workspace was seeded with the minimal native job environment
- the native `codesentinel job create` + `codesentinel job scaffold` path materialized a seven-frame `QS.json` and a rich `QF.md`
- a deliberate markdown bait string (`MARKDOWN TRAP FRAME`) was written into sandbox `JOB.md`
- the bait did not appear in sandbox `QS.json` or sandbox `QF.md`
- conclusion: the generator consumed `JOB.json -> execution_plan.frames` rather than scraping markdown prose

## Live empirical validation (S5)

Primary live packets:

- `report_tmp/frame_stack_schema_transfer/runs/20260420T185134Z_frame-stack-schema-transfer-s5-live-success/live_validation_summary.md`
- `report_tmp/frame_stack_schema_transfer/runs/20260420T185134Z_frame-stack-schema-transfer-s5-live-success/live_validation_summary.json`
- `report_tmp/frame_stack_schema_transfer/runs/20260420T185429Z_frame-stack-schema-transfer-s5-live/live_validation_summary.md`
- `report_tmp/frame_stack_schema_transfer/runs/20260420T185429Z_frame-stack-schema-transfer-s5-live/live_validation_summary.json`

Archived pre-rich live pair:

- `quarantine_legacy_archive/frame_stack_schema_transfer/observer_job_0001_pre_rich_regen_20260420T184900Z/QS.json`
- `quarantine_legacy_archive/frame_stack_schema_transfer/observer_job_0001_pre_rich_regen_20260420T184900Z/QF.md`

Live findings:

- the observer `JOB.json` was upgraded to the richer versioned scaffold while preserving the one-stack / seven-frame observer frame order
- first live probe exposed a native-surface limitation: `codesentinel job scaffold` did not upgrade the already-present non-placeholder thin `QS.json` / `QF.md` pair in place
- the thin live pair was archived non-destructively into `quarantine_legacy_archive/...`
- after the archived thin pair was removed, the native `codesentinel job scaffold` path regenerated the canonical live `QS.json` and `QF.md`
- the regenerated live `QS.json` now carries:
  - `frame_stack_schema_version = "job-frame-stack/v1"`
  - seven rich frame objects
  - transferred governance/test-scan/evidence-routing fields
  - active-frame-only micro-plan admission markers
- the regenerated live `QF.md` now carries the richer section profile, including:
  - governance and authority spine
  - containment rule and carry-in contract
  - full predeclared frame stack
  - per-frame next-action view
  - active-frame micro-plan / micro-frame sections
  - evidence and derived-report routing

## Current live canonical artifacts

- `projects/calamum-moltbook-observer/jobs/JOB_0001_CALAMUM-MOLTBOOK-OBSERVER_AUDIT_DOCS-GENERAL_20260420/JOB.json`
- `projects/calamum-moltbook-observer/jobs/JOB_0001_CALAMUM-MOLTBOOK-OBSERVER_AUDIT_DOCS-GENERAL_20260420/QS.json`
- `projects/calamum-moltbook-observer/jobs/JOB_0001_CALAMUM-MOLTBOOK-OBSERVER_AUDIT_DOCS-GENERAL_20260420/QF.md`

## Follow-up note

A native live-lane reconciliation gap remains visible from this validation:

- `codesentinel job scaffold` currently upgrades a missing or placeholder `QS/QF` pair, but does not upgrade an already-present non-placeholder thin pair in place from the richer `JOB.json` contract

That behavior should be treated as follow-up work for the live reconciliation path.
