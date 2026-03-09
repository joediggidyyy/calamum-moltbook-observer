# Job Report: QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220

**Status**: closed

## Scope

Execution report for integrating CodeSentinel baseline readiness with Calamum observer/watchdog/Keymaster governance lanes.

## Acceptance checklist

- [x] Terminal lane guard canonized for multi-window safety (protected registration + fail-closed prune)
- [x] One-shot helper added to auto-register current agent lane and print operator registration command
- [x] Baseline-ready contract evaluated before transitions
- [x] Watchdog posture receipt fields present (`posture_state`, `reason_codes[]`, `watchdog_receipt_id`, `expires_at_utc`, `evidence_refs[]`)
- [x] Fail-closed denial path validated for stale/failed baseline
- [x] Control-plane vs observability-plane boundaries preserved
- [x] Final SessionMemory health evidence captured

## Evidence pointers

- Gate events: `logs/behavioral/gates/gate_events.jsonl`
- QuestStack log: `logs/queststack/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220_log.md`
- QuestStack evidence: `logs/queststack/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220_evidence.jsonl`
- Terminal guard scripts:
	- `semantics_staging/ops_prune_vscode_pwsh_shells.ps1`
	- `semantics_staging/ops_register_terminal_lanes.ps1`
- Incident report: `projects/calamum-moltbook-observer/docs/reports/operations/INCIDENT_REPORT_TERMINAL_GUARD_MULTI_WINDOW_CANON_20260220.md`
- Publish-grade packet: `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_integration/baseline_integration_publish_grade_20260221T082452Z.json`
- Watchdog posture receipt: `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_integration/watchdog_posture_receipt_20260221T082534Z.json`
- Final SessionMemory health capture: `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_integration/baseline_integration_memory_health_20260221T082538Z.json`

## Completion summary

Baseline integration lane acceptance is fully satisfied with publish-grade evidence artifacts and names-only linkage fields (`run_id`, `posture_trigger_id`, `posture_trigger`, `security_report_ref`) recorded in quest evidence.

## Metadata

- Updated By: `joediggidyyy`
- Last Transition (UTC): `2026-02-28T13:11:17.600438Z`
- Status Authority: `operations/tasks.json`
- Task ID: `calamum-moltbook-baseline-integration-20260220`
- Status: `open`
