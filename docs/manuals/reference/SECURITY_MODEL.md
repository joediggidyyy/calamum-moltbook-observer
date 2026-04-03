# Calamum Security Model

Updated: 2026-04-03

This document explains the public security architecture for the Calamum observer stack.

## Core idea

The system treats upstream inputs as hostile by default and keeps runtime work inside a fail-closed, names-only operating model.

## Security model in one table

| Control | What it does |
| --- | --- |
| names-only persistence | keeps raw content out of normal retained artifacts |
| posture control | raises or lowers the allowed runtime envelope based on the target mode |
| baseline monitoring | proves current operating conditions instead of assuming they are healthy |
| watchdog enforcement | stops the system from quietly drifting away from guarded operation |
| evidence-linked transitions | ties state changes to retained decision packets |

## Canonical posture mapping

| Mode | Trigger posture |
| --- | --- |
| `watch` | `isolation` |
| `canary` | `isolation` |
| `live` | `lockdown` |
| `honeypot` | `lockdown` |

This mapping is part of the operating contract. It is not a cosmetic label system.

## Why baseline monitoring matters

Higher-risk modes should not run on optimism alone.

Baseline monitoring is a security control because it answers whether the runtime still looks current, coherent, and bounded enough to justify the requested move. If baseline inputs are stale, incomplete, or incoherent, the system is expected to deny the next escalation.

## Watchdog responsibilities

The watchdog layer is responsible for supervising heartbeat freshness, posture continuity, and fail-closed reactions when required surfaces become stale or invalid.

The key distinction is simple:

- dashboards summarize state
- watchdog and runtime controls enforce state

Treat the CLI and retained packets as authoritative when a dashboard view and a runtime packet disagree.

## Readiness and denial

A denied action is often evidence that the safety model is working.

Typical denial drivers include:

- stale observer heartbeat
- stale watchdog heartbeat
- invalid target posture
- incomplete baseline readiness
- missing linkage or security report context
- missing dependencies for stricter transitions

## Evidence boundary

The public documentation set explains the contract. Runtime evidence stays local.

| Public tracked surfaces | Local runtime surfaces |
| --- | --- |
| stable docs, code, curated reports | evidence packets, logs, control state, and execution residue |

This separation helps preserve both auditability and containment.

## Operator expectations

| Expectation | Meaning in practice |
| --- | --- |
| do not bypass a denied gate casually | fix the blocking condition or obtain explicit approval |
| keep evidence local and linked | use public docs for routing and local surfaces for execution proof |
| treat lockdown as stricter by design | `live` and `honeypot` require more than the simulation lanes |
| keep the runtime authority clear | the CLI, watchdog, and retained packets outrank the presentation layer |

## Related documents

- [`RUNTIME_TRANSITIONS.md`](RUNTIME_TRANSITIONS.md)
- [`../runtime/RUNTIME_WORKFLOWS.md`](../runtime/RUNTIME_WORKFLOWS.md)
- [`../runtime/RUNTIME_OPERATIONS.md`](../runtime/RUNTIME_OPERATIONS.md)
- [`../INDEX.md`](../INDEX.md)
- [`../../INDEX.md`](../../INDEX.md)
