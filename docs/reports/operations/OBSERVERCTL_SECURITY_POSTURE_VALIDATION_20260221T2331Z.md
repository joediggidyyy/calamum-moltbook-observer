# ObserverCTL Security Posture Validation (Sim)

## Metadata

- Template ID: `CALAMUM_OBSERVERCTL_SECURITY_POSTURE_VALIDATION_V1`
- Runtime CLI surface: `observerctl`
- Validation timestamp (UTC): `2026-02-21T23:31Z`

## Target posture validation

- Source axis: `sim`
- Mode target: `canary`
- Expected posture: `isolation`

## Commands run

- `observerctl watchdog status --json`
- `observerctl watchdog check --json`
- `observerctl ops mode gate --to canary --source sim --json`
- `observerctl health full --json`

## Required critical checks

- `watchdog_trigger_posture_valid`
- `run_security_report_linked`
- `heartbeat_rate_escalated` (lockdown only)
- `baseline_validation_rate_escalated` (lockdown only)

## Evidence

- watchdog status packet ref: command matrix output (`watchdog status` rc=0)
- gate packet ref: `local_untracked/observerctl/evidence/sim_transition_canary.json`
- health packet ref: command matrix output (`health full` rc=0)
- reason_codes observed in transition gate: `[]`

## Decision

- final decision: `go` for `sim:watch -> sim:canary`
- denial reason codes (if any): `[]`
- containment action taken: `none`

## Acceptance checklist

- [x] posture mapping matches mode target
- [x] fail-closed behavior verified
- [x] run linkage fields present
- [x] lockdown escalation checks recorded when applicable (N/A in isolation target)
- [x] evidence references captured
