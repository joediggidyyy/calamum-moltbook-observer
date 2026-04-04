# Calamum Runtime Workflows

Updated: 2026-04-03

This document is the practical operating path for the Calamum observer stack.

## Start here

| Stage | Goal | Primary command surfaces |
| --- | --- | --- |
| Prepare | confirm environment, approvals, and evidence expectations | `observerctl ops preflight`, `observerctl policy *` |
| Baseline | collect and validate the resource baseline for the target lane | `observerctl baseline collect`, `observerctl baseline analyze` |
| Execute | move into the requested runtime state through a guarded transition | `observerctl ops mode gate`, `observerctl ops mode transition` |
| Close | verify current state, evidence emission, and runtime health | `observerctl ops mode current`, `observerctl ops evidence index`, `observerctl health full` |
| Hand off | route retained artifacts into analysis and reporting work | `observerctl librarian stats`, `observerctl ds *`, `docs/reports/INDEX.md` |

## Before touching the system

Use this short checklist before you start a run:

| Check | Why it matters |
| --- | --- |
| Python environment is active and `observerctl` resolves in that shell | keeps the command surface and installed dependencies aligned |
| If the run will hand off into `observerctl ds *`, the `ds` extra is installed in that environment | the supported DS lane depends on the ApexLab/reporting stack rather than the minimal core install |
| Local operator configuration and required environment variables are present | stricter lanes fail closed when dependencies or credentials are missing |
| You know whether the lane is `sim` or `real` | source changes alter the required safety bar |
| You know whether the target mode is `watch`, `canary`, `live`, or `honeypot` | the mode determines the trigger posture and gate rules |
| You are prepared to keep runtime evidence local | public docs describe the contract; runtime artifacts remain local working evidence |

Default first-contact rule: prefer a simulation-first path unless a stricter lane has already been justified and approved.

## Baseline preparation

A baseline is the retained resource reference used by later readiness and comparison checks.

### Collect the baseline window

Use one baseline-focused collection window and one normal collection window for the same source and mode.

- Baseline collection: `observerctl baseline collect --source <sim|real> --mode <watch|canary|live|honeypot> --profile baseline --duration-sec <seconds> --interval-sec <seconds> --window-id <window_id> --json`
- Normal collection: `observerctl baseline collect --source <sim|real> --mode <watch|canary|live|honeypot> --profile normal --duration-sec <seconds> --interval-sec <seconds> --window-id <window_id> --json`

### Analyze the baseline

Use the analysis packet to decide whether the baseline is ready to support later comparison work.

- Analysis command: `observerctl baseline analyze --source <sim|real> --mode <watch|canary|live|honeypot> --hours <lookback_hours> --min-normal-samples <count> --min-baseline-samples <count> --json`

Treat the baseline as ready only when the analysis packet returns a `go` decision, reports `baseline_ready = true`, and confirms that the required normal and baseline-window sample counts were satisfied.

## First safe execution path

For most readers, the safest first full run is `sim:canary`.

### 1. Run preflight

- `observerctl ops preflight --source sim --json`

Confirm that the runtime packet is readable and that the current surfaces are coherent enough for a transition decision.

### 2. Run the gate check

- `observerctl ops mode gate --to canary --source sim --json`

If the gate returns `no-go`, stop there, read the `reason_codes`, and fix the blocking condition before you try again.

### 3. Perform the guarded transition

- `observerctl ops mode transition --to canary --source sim --event first-safe-run --json`

The transition command is the preferred path because it performs gate, state change, and evidence emission as one guarded workflow.

### 4. Verify closure

Use the three checks below before you treat the run as complete.

| Check | Command | What a healthy result looks like |
| --- | --- | --- |
| current runtime state | `observerctl ops mode current --json` | the packet reflects the intended source/mode tuple |
| evidence surface | `observerctl ops evidence index --json` | the latest retained evidence includes the run you just performed |
| closure health | `observerctl health full --json` | runtime, baseline, watchdog, librarian, and policy surfaces remain readable |

## Retained outputs for analysis

When a run closes cleanly, the analysis handoff set is usually the lane-scoped runtime stream plus the corresponding evidence and baseline packets.

| Output family | Canonical surface | Use it for |
| --- | --- | --- |
| lane metrics stream | `logs/data/calamum/observer_derived/<source>/<mode>/moltbook_metrics.jsonl` | names-only runtime telemetry for the executed lane |
| evidence index | `logs/data/calamum/observer_derived/<source>/<mode>/evidence/index.jsonl` | quick confirmation of the latest retained packets |
| per-event evidence packets | `logs/data/calamum/observer_derived/<source>/<mode>/evidence/observerctl_<event>_<timestamp>.json` | detailed gate, transition, and closeout evidence |
| baseline packets | lane `evidence/` output from `observerctl baseline analyze` | readiness and comparison framing |
| reader-facing reports | `docs/reports/` | tracked summaries and publication-oriented material |

## Quick operating paths

### Background simulation

1. `observerctl ops preflight --source sim --json`
2. `observerctl ops mode gate --to <watch|canary> --source sim --json`
3. `observerctl ops mode transition --to <watch|canary> --source sim --event <event> --json`
4. `observerctl ops evidence index --json`

### Real-source lane

1. confirm required environment variables and approvals are already in place
2. `observerctl ops preflight --source real --json`
3. `observerctl ops mode gate --to <mode> --source real --json`
4. only proceed to `observerctl ops mode transition ...` if the gate packet returns `decision = go`

## When to stop instead of pushing through

Stop and resolve the issue first when any of the following are true:

- preflight output is incomplete or incoherent
- the gate returns `no-go`
- the runtime state cannot be inferred cleanly
- the evidence packet does not appear in the expected lane
- the baseline packet reports insufficient coverage for the intended next step

Fail-closed behavior is part of the product, not a suggestion that you should improvise harder.

## Related documents

- [`RUNTIME_OPERATIONS.md`](RUNTIME_OPERATIONS.md)
- [`../reference/RUNTIME_TRANSITIONS.md`](../reference/RUNTIME_TRANSITIONS.md)
- [`../reference/SECURITY_MODEL.md`](../reference/SECURITY_MODEL.md)
- [`../data-science/DS_OPERATIONS.md`](../data-science/DS_OPERATIONS.md)
- [`../INDEX.md`](../INDEX.md)
