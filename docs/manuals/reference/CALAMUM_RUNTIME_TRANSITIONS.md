# Calamum Runtime Transitions

Updated: 2026-04-03

This document defines the public transition contract for the runtime CLI.

## Canonical runtime state

A runtime state is the tuple $(source, mode)$.

| Axis | Allowed values |
| --- | --- |
| `source` | `sim`, `real` |
| `mode` | `watch`, `canary`, `live`, `honeypot` |

Useful introspection commands:

- `observerctl ops mode current --json`
- `observerctl ops mode list --json`

## Posture mapping

| Mode | Trigger posture |
| --- | --- |
| `watch` | `isolation` |
| `canary` | `isolation` |
| `live` | `lockdown` |
| `honeypot` | `lockdown` |

## Public command set

| Command | Role |
| --- | --- |
| `observerctl ops preflight --source <sim|real> --json` | read-only readiness snapshot before a move |
| `observerctl ops mode gate --to <mode> --source <sim|real> --json` | fail-closed go/no-go decision for the requested state |
| `observerctl ops mode set --to <mode> --source <sim|real> --json` | direct state change after a fresh successful gate |
| `observerctl ops mode transition --to <mode> --source <sim|real> --event <event> --json` | guarded gate → set → evidence workflow |
| `observerctl ops gate-check --source <sim|real> --json` | source-scoped gating packet |
| `observerctl ops evidence pack --source <sim|real> --event <event> --json` | explicit packet generation for the current lane |

## Transition classes

| Class | Meaning |
| --- | --- |
| no-op | current state already matches the requested state |
| lateral | source stays the same while mode changes |
| source escalation | `sim` to `real` |
| source de-escalation | `real` to `sim` |

Any request targeting `live` or `honeypot`, or promoting from `sim` to `real`, should be treated as a stricter path.

## Gate expectations

A successful gate depends on the runtime being able to infer state and validate the target move without ambiguity.

Typical checks include:

- observer heartbeat freshness
- watchdog heartbeat freshness
- baseline readiness
- runtime state coherence
- target mode support
- real-source dependency presence checks
- trigger-posture validity
- output path writability when an evidence packet is requested

## Fail-closed denial reasons

Common normalized denial reasons include:

- `policy_denied:no_state_change_requested`
- `policy_denied:target_mode_unsupported`
- `critical_check_failed:mode_current_unknown`
- `critical_check_failed:observer_service_heartbeat_stale`
- `critical_check_failed:watchdog_heartbeat_stale`
- `critical_check_failed:baseline_not_ready`
- `critical_check_failed:real_key_missing`
- `critical_check_failed:watchdog_trigger_posture_invalid`
- `critical_check_failed:gate_packet_missing_or_stale`
- `critical_check_failed:run_security_report_missing`
- `critical_check_failed:lockdown_heartbeat_rate_not_escalated`
- `critical_check_failed:lockdown_baseline_rate_not_escalated`

## Evidence contract

Transition and evidence packets remain names-only.

Minimum public evidence fields include:

| Field | Why it matters |
| --- | --- |
| `timestamp_utc` | when the decision was made |
| `runtime_cli_surface` | which surface produced the packet |
| `decision` | go or no-go outcome |
| `from_state` | prior runtime state |
| `to_state` | requested destination |
| `reason_codes` | normalized explanation of the decision |
| `run_id` | run linkage |
| `posture_trigger_id` | posture linkage identifier |
| `posture_trigger` | posture used for the transition |
| `security_report_ref` | security linkage for stricter lanes |

## Recommended operating order

1. run `observerctl ops preflight --source <sim|real> --json`
2. run `observerctl ops mode gate --to <mode> --source <sim|real> --json`
3. if `decision = go`, run `observerctl ops mode transition ...`
4. confirm the resulting packet through `observerctl ops evidence index --json`

## Related documents

- [`CALAMUM_SECURITY_MODEL.md`](CALAMUM_SECURITY_MODEL.md)
- [`../runtime/CALAMUM_RUNTIME_WORKFLOWS.md`](../runtime/CALAMUM_RUNTIME_WORKFLOWS.md)
- [`../runtime/CALAMUM_RUNTIME_OPERATIONS.md`](../runtime/CALAMUM_RUNTIME_OPERATIONS.md)
- [`../INDEX.md`](../INDEX.md)
