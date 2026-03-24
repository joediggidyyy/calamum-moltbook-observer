# Observer Security Model

**Document ID**: `OBSERVER_SECURITY_MODEL_20260324`  
**Status**: Public security manual  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Last updated**: 2026-03-24

## Purpose and scope

This manual defines the security architecture for **Calamum Moltbook Observer**.

It explains how the observer uses posture control, guarded transitions, baseline monitoring, watchdog supervision, and names-only evidence discipline to keep hostile-input handling inside a fail-closed operating model.

Related reference surfaces include [`../../SECURITY.md`](../../SECURITY.md), [`../../DATA_METHODOLOGY.md`](../../DATA_METHODOLOGY.md), and [`OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md).

## Security architecture summary

The observer security model is built around a small set of reinforcing controls:

- all input is treated as potentially hostile from the start,
- persistence is reduced to names-only telemetry rather than raw payload content,
- posture state governs how strict the runtime must be,
- baseline monitoring acts as a live safety check rather than a decorative metric,
- watchdog enforcement surfaces provide fail-closed pressure when runtime behavior degrades.

The goal is not merely to collect data safely. The goal is to ensure that higher-risk operating modes remain conditional on current safety state, not on operator optimism.

## Canonical posture states

The public posture model uses two canonical trigger postures.

### `isolation`

`isolation` is the default guarded posture for lower-risk observer states. It emphasizes containment, restricted movement, and stable names-only observation without granting the system broader trust than it has earned.

### `lockdown`

`lockdown` is the stricter posture used for higher-risk operating states. It requires stronger heartbeat expectations, stronger readiness discipline, and a tighter baseline-monitoring contract before the system should be treated as safe to continue.

## Mode-to-posture mapping

The current public mapping is:

| Mode | Trigger posture |
|---|---|
| `watch` | `isolation` |
| `canary` | `isolation` |
| `live` | `lockdown` |
| `honeypot` | `lockdown` |

This mapping is part of the public security architecture. It is not a cosmetic label system.

## Guarded transition model

The observer does not treat mode changes as casual toggles. Transition into a new runtime state is intended to remain guarded by preflight checks, gate evaluation, and names-only evidence emission.

At a high level, the security model expects:

1. current state to be known,
2. prerequisite safety conditions to be evaluated before transition,
3. invalid or incomplete conditions to deny cleanly, and
4. resulting state changes to remain evidence-linked.

The command-level transition workflow, denial reasons, and packet semantics are defined in [`OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md). This manual focuses on why those guarded transitions exist and what security work they are doing.

## Baseline monitoring as a security control

Baseline monitoring is part of the security model because higher-risk modes should not rely on static trust. They require current evidence that the runtime remains within the expected operating envelope.

In public terms, that means:

- normal resource behavior should remain observable,
- higher-risk modes should require stronger baseline validation discipline,
- readiness should depend on current retained evidence rather than assumed health,
- denial should occur when baseline-monitoring prerequisites are stale, missing, or incoherent.

This is especially important for `live` and `honeypot`, where `lockdown` posture is not meaningful unless the system can still prove that its runtime state is both current and constrained.

## Watchdog enforcement responsibilities

The security model relies on independent enforcement surfaces rather than a single trusting process.

### Core watchdog responsibilities

The watchdog is responsible for supervising runtime health signals, posture continuity, and fail-closed reaction when required control surfaces become stale or invalid. In security terms, it helps prevent the system from silently drifting from a guarded state into an unsafe one.

### Fail-signature stop layer (`sentinel.py`)

The `sentinel.py` runtime acts as the narrower fail-signature stop layer within that watchdog enforcement model. Its role is to detect forbidden runtime conditions and force a stop rather than allowing suspicious or broken behavior to continue on vibes alone.

### Presentation-layer distinction

Neither the watchdog enforcement layer nor `sentinel.py` should be confused with the presentation layer. Dashboards and operator interfaces may summarize state, but the safety model depends on the enforcement surfaces themselves.

## Readiness and denial model

The public security model expects denial to be normal when prerequisites are not satisfied. A denied action is often evidence that the safety model is functioning correctly.

Typical readiness concerns include:

- stale observer heartbeat,
- stale watchdog heartbeat,
- invalid target posture,
- incomplete baseline readiness,
- missing required security linkage,
- stale or missing gate/evidence state for stricter transitions.

In practice, `lockdown`-class modes must satisfy a stricter readiness bar than `isolation`-class modes. This is why the project treats baseline monitoring, posture validity, and evidence linkage as security controls rather than as after-the-fact reporting conveniences.

## Evidence boundary and public/private separation

The project deliberately separates:

- public documentation and stable manuals,
- local runtime evidence,
- local control state,
- local operator execution residue.

Public documents may describe evidence families and contract expectations, but they do not convert local runtime artifacts into public tracked evidence.

This distinction is part of the security model. It reduces the chance that useful runtime detail becomes accidental long-term public retention.

## Related surfaces

- [`../../README.md`](../../README.md)
- [`../../SECURITY.md`](../../SECURITY.md)
- [`../../DATA_METHODOLOGY.md`](../../DATA_METHODOLOGY.md)
- [`OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md)
- [`OBSERVERCTL_CLI_TRANSITION_OPERATOR_GUIDE_20260221.md`](OBSERVERCTL_CLI_TRANSITION_OPERATOR_GUIDE_20260221.md)
- [`INDEX.md`](INDEX.md)
- [`../INDEX.md`](../INDEX.md)
