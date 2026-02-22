# Job 0022: Moltbook Baseline Integration

> **ID**: CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220
> **State**: COMPLETED
> **Status**: completed
> **Owner**: ORACL-Prime
> **Date**: 2026-02-20

## Scope
Bind baseline readiness outputs from CodeSentinel into observer/Keymaster operational gates under watchdog-authoritative posture control.

## Required integration outputs
- Baseline-ready contract checks embedded in lane decisions.
- Watchdog posture receipt fields bound and evidence-linked.
- Fail-closed denial path for stale/failed/timeout baseline conditions.

## Dependency
- `codesentinel-baseline-local-stabilization-20260220` must provide `baseline_posture_inputs_v0` references before this lane transitions from planned to in-progress.

## 2026-02-20 implementation notes
- Added canonical terminal lane registration helper: `semantics_staging/ops_register_terminal_lanes.ps1`
- Fail-closed terminal prune behavior is active in: `semantics_staging/ops_prune_vscode_pwsh_shells.ps1`
- Incident trace and policy canonization linked in lane report.

## 2026-02-21 completion notes
- Baseline-ready contract evaluated and recorded in publish-grade packet:
	- `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_integration/baseline_integration_publish_grade_20260221T082452Z.json`
- Watchdog posture receipt fields captured (names-only):
	- `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_integration/watchdog_posture_receipt_20260221T082534Z.json`
- Final SessionMemory health evidence captured:
	- `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_integration/baseline_integration_memory_health_20260221T082538Z.json`
- Quest evidence ledger updated with run linkage (`run_id`, `posture_trigger_id`, `posture_trigger`, `security_report_ref`).
