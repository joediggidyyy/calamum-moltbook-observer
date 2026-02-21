# Job Report: QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220

**Status**: open

## Scope

Execution report for integrating CodeSentinel baseline readiness with Calamum observer/watchdog/Keymaster governance lanes.

## Acceptance checklist

- [x] Terminal lane guard canonized for multi-window safety (protected registration + fail-closed prune)
- [x] One-shot helper added to auto-register current agent lane and print operator registration command
- [ ] Baseline-ready contract evaluated before transitions
- [ ] Watchdog posture receipt fields present (`posture_state`, `reason_codes[]`, `watchdog_receipt_id`, `expires_at_utc`, `evidence_refs[]`)
- [ ] Fail-closed denial path validated for stale/failed baseline
- [ ] Control-plane vs observability-plane boundaries preserved
- [ ] Final SessionMemory health evidence captured

## Evidence pointers

- Gate events: `logs/behavioral/gates/gate_events.jsonl`
- QuestStack log: `logs/queststack/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220_log.md`
- QuestStack evidence: `logs/queststack/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220_evidence.jsonl`
- Terminal guard scripts:
	- `semantics_staging/ops_prune_vscode_pwsh_shells.ps1`
	- `semantics_staging/ops_register_terminal_lanes.ps1`
- Incident report: `projects/calamum-moltbook-observer/docs/reports/operations/INCIDENT_REPORT_TERMINAL_GUARD_MULTI_WINDOW_CANON_20260220.md`
