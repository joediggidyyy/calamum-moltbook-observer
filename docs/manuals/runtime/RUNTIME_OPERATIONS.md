# Calamum Runtime Operations

Updated: 2026-04-03

This document is the command-level reference for routine runtime work.

## Runtime command families

| Command family | Use it for | Notes |
| --- | --- | --- |
| `observerctl ops *` | preflight, gate checks, mode state, transitions, and evidence packets | primary runtime control surface |
| `observerctl baseline *` | resource collection and readiness checks | baseline packets feed later comparison and readiness decisions |
| `observerctl librarian *` | runtime/store controls and retained-artifact census | useful when checking what the lane actually produced |
| `observerctl watchdog *` | heartbeat freshness, posture checks, and reason inspection | important when a gate denies on stale or invalid watchdog state |
| `observerctl health *` | quick or full runtime diagnostics | use during closeout and troubleshooting |
| `observerctl policy *` | read-only policy introspection | explains why the runtime is denying a move |
| `observerctl ds *` | downstream data-science workflows | use after runtime artifacts are ready for analysis |

## Exit-code contract

| Exit code | Meaning |
| --- | --- |
| `0` | success / go |
| `2` | fail-closed / no-go |
| `3` | schema or contract invalid |
| `4` | dependency or context missing |
| `5` | runtime I/O failure |

## Common playbooks

### Standard simulation run

1. `observerctl ops preflight --source sim --json`
2. `observerctl ops mode gate --to <watch|canary> --source sim --json`
3. `observerctl ops mode transition --to <watch|canary> --source sim --event <event> --json`
4. `observerctl ops evidence index --json`

### Production-like simulation run

Use the same sequence as above, but add explicit approval capture and verify that the output packet includes the linkage fields you expect for the run window.

### Real-source transition

Use a stricter review path:

1. confirm presence-checked dependencies and approvals
2. `observerctl ops preflight --source real --json`
3. `observerctl ops mode gate --to <mode> --source real --json`
4. only if the gate returns `decision = go`, run `observerctl ops mode transition ...`

## Evidence paths

| Evidence family | Canonical path |
| --- | --- |
| metrics stream | `logs/data/calamum/observer_derived/<source>/<mode>/moltbook_metrics.jsonl` |
| event packets | `logs/data/calamum/observer_derived/<source>/<mode>/evidence/observerctl_<event>_<timestamp>.json` |
| evidence index | `logs/data/calamum/observer_derived/<source>/<mode>/evidence/index.jsonl` |
| resource retention index | `logs/data/calamum/observer_derived/<source>/<mode>/resource/index.jsonl` |
| gate events | `logs/behavioral/gates/gate_events.jsonl` |
| quest logs | `logs/queststack/<QS-ID>_log.md` |
| quest evidence | `logs/queststack/<QS-ID>_evidence.jsonl` |

## Runtime roles

| Role | Responsibility |
| --- | --- |
| `joediggidyyy` | approval authority for execution windows |
| `ORACL-Prime` | prepares runbooks, executes approved commands, and records evidence |
| shared | maintain continuity between the runtime lane and its governance evidence |

## Dashboard and control surfaces

The Ghost Console is a presentation and operator interface layer. It is not the runtime authority.

Use it to inspect names-only telemetry and issue allowed control intents, but treat the runtime CLI, watchdog, and gate/evidence surfaces as the authoritative system state.

## Troubleshooting order

When something looks wrong, use this order:

1. check current state: `observerctl ops mode current --json`
2. inspect the latest gate/evidence packet: `observerctl ops evidence index --json`
3. inspect watchdog and health surfaces: `observerctl watchdog check --json`, `observerctl health full --json`
4. inspect the current lane census: `observerctl librarian stats --json`

## High-signal failure patterns

| Symptom | First thing to check |
| --- | --- |
| transition denied | `reason_codes` in the gate packet |
| evidence file appears missing | the lane-scoped `index.jsonl` in the matching source/mode scope |
| closure packet looks incomplete | `observerctl health full --json` plus current-state output |
| density or record counts look strange | separate active vs archived totals before drawing conclusions |
| dashboard view disagrees with the CLI | trust the CLI and retained packets first |

## Related documents

- [`RUNTIME_WORKFLOWS.md`](RUNTIME_WORKFLOWS.md)
- [`../reference/RUNTIME_TRANSITIONS.md`](../reference/RUNTIME_TRANSITIONS.md)
- [`../reference/SECURITY_MODEL.md`](../reference/SECURITY_MODEL.md)
- [`../data-science/DS_OPERATIONS.md`](../data-science/DS_OPERATIONS.md)
- [`../INDEX.md`](../INDEX.md)
