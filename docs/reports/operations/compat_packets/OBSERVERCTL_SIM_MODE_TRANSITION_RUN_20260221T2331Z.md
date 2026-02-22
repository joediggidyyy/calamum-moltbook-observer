# ObserverCTL Sim Mode Transition Run

**Status**: compatibility evidence packet (observer scoped)

**Canonical linkage**:
- Primary lane narrative: `JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221.md`
- This file remains as point-in-time transition execution evidence referenced by that lane.

## Metadata

- Template ID: `CALAMUM_OBSERVERCTL_MODE_TRANSITION_RUN_V1`
- Runtime CLI surface: `observerctl`
- Executed at: `2026-02-21T23:31Z`
- Executor: `ORACL-Prime`

## Transition intent

- From state (observed): `sim:watch`
- To state (requested): `sim:canary`
- Event tag: `sim-gate-canary`

## Command sequence (canonical)

1. `observerctl ops mode gate --to canary --source sim --json`
2. `observerctl ops mode transition --to canary --source sim --event sim-gate-canary --output local_untracked/observerctl/evidence/sim_transition_canary.json --json`
3. `observerctl ops mode current --json`

## Gate decision evidence

- decision: `go`
- reason_codes: `[]`
- profile: `GP-1`
- critical_checks: `paths.health_dir, heartbeat.watchdog, heartbeat.observer, env.signing_key, store.pointer_consistent, store.integrity_ok`

## Run linkage contract

- run_id: `observerctl-gate-20260221T233119Z`
- posture_trigger_id: `pt-canary-20260221T233119Z`
- posture_trigger: `isolation`
- security_report_ref: `projects/calamum-moltbook-observer/docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221.md`

## Triad evidence packet

- packet path: `local_untracked/observerctl/evidence/sim_transition_canary.json`
- packet sha256: `205e875e844c8248b3b6564a8bc7c2772c0adce4e3dfd9b4bf483442538834d6`
- provenance present: `yes`
- methodology present: `yes`
- process present: `yes`

## Completion checklist

- [x] gate executed and recorded
- [x] transition command executed
- [x] mode current confirms target mode during run
- [x] triad evidence packet written and indexed
- [x] fail-closed outcome documented where applicable

## Matrix gate summary

- Full sim command matrix: `PASS (28 commands)`
- Result artifact: `local_untracked/observerctl/evidence/sim_command_matrix_results.json`
- Notes: fail-closed denials were expected and accepted for commands with allowed exits `0,2`.
