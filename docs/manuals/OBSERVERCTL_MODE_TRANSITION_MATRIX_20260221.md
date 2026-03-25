# ObserverCTL Mode Transition Matrix

**Document ID**: `OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221`  
**Project**: Calamum Moltbook Observer  
**CLI Surface**: `observerctl`  
**Status**: Public runtime manual  
**Last updated**: 2026-03-24

---

## Purpose

This manual defines the public-facing runtime transition model for `observerctl` mode and source changes.

It covers:

- canonical runtime states,
- posture mapping,
- gate and transition commands,
- fail-closed behavior,
- evidence expectations, and
- normalized denial reasons.

## Canonical runtime state

A runtime state is the tuple:

$$
(source, mode)
$$

Where:

- `source ∈ {sim, real}`
- `mode ∈ {watch, canary, live, honeypot}`

Available introspection commands:

- `observerctl ops mode current --json`
- `observerctl ops mode list --json`

## Posture mapping

ObserverCTL derives trigger posture from the target mode:

| Mode | Trigger posture |
|---|---|
| `watch` | `isolation` |
| `canary` | `isolation` |
| `live` | `lockdown` |
| `honeypot` | `lockdown` |

Posture is reflected in runtime packets and transition evidence.

## Public command set

The public transition surface is:

- `observerctl ops preflight --source <sim|real> --json`
- `observerctl ops mode gate --to <mode> --source <sim|real> --json`
- `observerctl ops mode set --to <mode> --source <sim|real> --json`
- `observerctl ops mode transition --to <mode> --source <sim|real> --event <event> --output <path> --json`
- `observerctl ops gate-check --source <sim|real> --json`
- `observerctl ops evidence pack --source <sim|real> --event <event> --json`

Behavioral contract:

- `gate` is read-only and fail-closed
- `set` requires a fresh successful gate packet
- `transition` performs gate → set → evidence as one guarded workflow
- unsupported or incoherent requests deny deterministically

## Transition classes

Transitions are interpreted in four broad classes:

| Transition class | Meaning |
|---|---|
| **No-op** | Current state already matches the requested state. |
| **Lateral** | Source stays the same while mode changes. |
| **Source escalation** | `sim` to `real`. |
| **Source de-escalation** | `real` to `sim`. |

Any transition targeting `live` or `honeypot`, or promoting from `sim` to `real`, is treated as a stricter safety path.

## Gate expectations

A successful gate decision depends on current runtime health, policy compatibility, and output/evidence readiness.

Typical gate considerations include:

- observer heartbeat freshness,
- watchdog heartbeat freshness,
- baseline readiness,
- runtime state coherence,
- target mode support,
- real-source credential presence checks,
- trigger-posture validity,
- evidence/output path writability.

If the current state cannot be inferred deterministically, the gate denies the request.

## Fail-closed denial model

ObserverCTL uses a fail-closed decision model.

Typical denial reasons include:

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

- `timestamp_utc`
- `runtime_cli_surface`
- `decision`
- `from_state`
- `to_state`
- `reason_codes`
- `run_id`
- `posture_trigger_id`
- `posture_trigger`
- `security_report_ref`

Evidence commands write structured packets without exposing secrets or raw target payloads.

## Output and persistence notes

Project-local runtime outputs remain outside the public-tracked surface. Public documentation describes the contract and command behavior, while runtime evidence is produced locally during execution.

This separation is intentional:

- public repo = code, manuals, stable reports
- local runtime = evidence, logs, control state, and execution history

## Operational guidance

Recommended operator sequence for a guarded transition:

1. `observerctl ops preflight --source <sim|real> --json`
2. `observerctl ops mode gate --to <mode> --source <sim|real> --json`
3. if `decision=go`, run `observerctl ops mode transition ...`
4. review the resulting evidence packet and reason codes

Do not bypass a denied gate without an explicit external governance process.

## Related surfaces

- [`../../README.md`](../../README.md)
- [`../../SECURITY.md`](../../SECURITY.md)
- [`../../DATA_METHODOLOGY.md`](../../DATA_METHODOLOGY.md)
- [`OBSERVER_SECURITY_MODEL_20260324.md`](OBSERVER_SECURITY_MODEL_20260324.md)
- [`OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md`](OBSERVERCTL_RUNTIME_OPERATOR_GUIDE_20260221.md)
- [`INDEX.md`](INDEX.md)
- [`../INDEX.md`](../INDEX.md)
