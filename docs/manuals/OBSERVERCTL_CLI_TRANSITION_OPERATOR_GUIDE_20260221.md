# ObserverCTL CLI Operator Guide

**Document ID**: `OBSERVERCTL_CLI_TRANSITION_OPERATOR_GUIDE_20260221`  
**Status**: Public operator guide  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Last updated**: 2026-03-24

## Purpose

This guide is the day-to-day operator reference for CLI-driven observer runtime work.

It covers:

- runtime execution workflow and evidence checkpoints,
- observer operations through `observerctl`,
- transition safety across `sim` and `real`,
- posture-aware execution expectations, and
- practical command families used during approved runtime work.

Primary reference surfaces:

- [`../../README.md`](../../README.md)
- [`../../SECURITY.md`](../../SECURITY.md)
- [`../../DATA_METHODOLOGY.md`](../../DATA_METHODOLOGY.md)
- [`OBSERVER_SECURITY_MODEL_20260324.md`](OBSERVER_SECURITY_MODEL_20260324.md)
- [`OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md)

## Core guardrails

1. Runtime source axis is `sim | real`.
2. Runtime mode axis is `watch | canary | live | honeypot`.
3. Outputs remain names-only.
4. `observerctl` is the runtime command surface for this repository.
5. Simulations and real-source transitions remain approval-sensitive operations.

Simulation policy:

- background simulations are allowed for low-risk validation,
- production-like simulations require explicit approval and a controlled runtime window.

## Operating model

| Role | Responsibility |
|---|---|
| **joediggidyyy** | Approval authority for execution windows. |
| **ORACL-Prime** | Prepares runbooks, executes approved CLI work, and captures evidence. |
| **Both** | Maintain evidence continuity across the runtime and governance surfaces used during an approved lane. |

## Standard runtime workflow

Use this sequence for active CLI-driven runtime work:

1. record task start in the approved execution log or equivalent runtime record,
2. execute runtime work through `observerctl`,
3. keep evidence, logs, and report surfaces current while work proceeds,
4. record task close in the same execution record,
5. capture closure health evidence from the observer runtime surfaces.

If closure checks fail, treat the lane as still open until the fail-closed conditions are resolved or an explicit approved override exists.

## ObserverCTL command families

| Command family | Primary use |
|---|---|
| `observerctl ops *` | Preflight, gate checks, mode transition, and evidence packets. |
| `observerctl baseline *` | Baseline and readiness checks. |
| `observerctl librarian *` | Runtime and mode-store controls. |
| `observerctl watchdog *` | Heartbeat, posture, and reason-catalog checks. |
| `observerctl health *` | Quick/full diagnostics and reason explanation. |
| `observerctl policy *` | Read-only policy introspection. |

Exit-code contract:

| Exit code | Meaning |
|---|---|
| `0` | success/go |
| `2` | fail-closed/no-go |
| `3` | schema/contract invalid |
| `4` | dependency/context missing |
| `5` | runtime I/O failure |

## Runtime transition playbooks

### Background simulation

Use for lower-risk validation while other observer activity may remain online.

Recommended flow:

1. `observerctl ops preflight --source sim --json`
2. `observerctl ops mode gate --to <watch|canary> --source sim --json`
3. `observerctl ops mode transition --to <watch|canary> --source sim --event <event> --json`
4. `observerctl ops evidence index --json`

### Full life-like simulation

Use for production-like simulation windows.

Mandatory controls:

1. approval checkpoint recorded,
2. active observer feed shutdown checkpoint recorded,
3. transition and evidence commands executed,
4. run-linkage fields verified in output (`run_id`, `posture_trigger_id`, `posture_trigger`, `security_report_ref`).

Recommended flow:

1. record go/no-go approval,
2. stop active observer feed and log the shutdown checkpoint,
3. `observerctl ops preflight --source sim --json`,
4. `observerctl ops mode gate --to canary --source sim --json`,
5. `observerctl ops mode transition --to canary --source sim --event full-lifelike-sim --json`,
6. `observerctl ops evidence pack --source sim --event full-lifelike-sim --json`,
7. `observerctl ops evidence index --json`.

### Real-source transitions

For `source=real` transitions, confirm the required runtime dependencies and presence checks before attempting mode changes.

Never bypass fail-closed denials without an explicit operator decision and recorded rationale.

## Posture expectations by mode

| Mode set | Trigger posture |
|---|---|
| `watch`, `canary` | `isolation` |
| `live`, `honeypot` | `lockdown` |

If posture mismatches target mode, transition must deny with normalized reason codes.

For lockdown transitions, cadence-escalation checks must be satisfied.

## Canonical output and evidence paths

| Evidence family | Canonical path |
|---|---|
| Observer-derived metrics | `logs/data/calamum/observer_derived/<source>/<mode>/moltbook_metrics.jsonl` |
| Observerctl evidence packets | `logs/data/calamum/observer_derived/<source>/<mode>/evidence/observerctl_<event>_evidence_<timestamp>.json` |
| Observerctl evidence index | `logs/data/calamum/observer_derived/<source>/<mode>/evidence/index.jsonl` |

Governance evidence lives in the following local paths:

| Governance surface | Canonical path |
|---|---|
| Gate events | `logs/behavioral/gates/gate_events.jsonl` |
| Quest log | `logs/queststack/<QS-ID>_log.md` |
| Quest evidence | `logs/queststack/<QS-ID>_evidence.jsonl` |

Dashboard snapshot counters (`/_ghost_console/snapshot`) schema:

| Field | Meaning |
|---|---|
| `total_records` | Raw stream total. |
| `records_total_display` | Display-safe aggregate from telemetry layer. |
| `display_main_records` | Primary banner counter value. |
| `records_breakdown` | Session/archive display breakdown plus raw values. |
| `records_breakdown_display` | Explicit UI-facing cache contract. |

## Data-volume interpretation and density sanity

When density appears unusually high, do not assume current-run throughput.

Interpret the surface in this order:

1. verify current source/mode scope,
2. separate active versus archived totals,
3. validate whether reported density is window-based rather than direct ingestion rate,
4. check whether mixed historical streams or rotated archives are influencing the view.

Use evidence/index and manifest-backed counts to ground conclusions.

## Troubleshooting quick-reference

If transition returns `no-go`:

1. do not force transition,
2. inspect `reason_codes`,
3. resolve posture, linkage, or dependency checks,
4. re-run gate before set/transition.

If an evidence file appears missing:

1. confirm canonical source/mode/evidence path,
2. check the corresponding `index.jsonl` in the same scope,
3. confirm the event tag and timestamp window.

If closure gates fail:

1. check memory health and working tree state,
2. resolve fail-closed checks first,
3. use override only when explicitly approved and fully documented.

## Related surfaces

- [`../../README.md`](../../README.md)
- [`../../SECURITY.md`](../../SECURITY.md)
- [`../../DATA_METHODOLOGY.md`](../../DATA_METHODOLOGY.md)
- [`INDEX.md`](INDEX.md)
- [`OBSERVER_SECURITY_MODEL_20260324.md`](OBSERVER_SECURITY_MODEL_20260324.md)
- [`OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md`](OBSERVERCTL_MODE_TRANSITION_MATRIX_20260221.md)
- [`../INDEX.md`](../INDEX.md)

## Closing note

This guide is the operator-facing companion to the security model and transition manual. It is intended to keep day-to-day runtime work crisp, repeatable, and fail-closed.