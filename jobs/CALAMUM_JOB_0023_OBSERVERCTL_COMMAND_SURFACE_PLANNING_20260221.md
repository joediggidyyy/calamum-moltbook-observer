# Job 0023: ObserverCTL Command Surface Implementation Specification

> **ID**: CALAMUM_JOB_0023_OBSERVERCTL_COMMAND_SURFACE_PLANNING_20260221
> **State**: COMPLETED
> **Status**: completed
> **Owner**: ORACL-Prime
> **Date**: 2026-02-21

## 1) Scope and intent

This document is the comprehensive implementation specification for `observerctl`.

It defines:
- command topology,
- gate semantics,
- exit-code contract,
- publication-grade packet requirements,
- mode/data-store interactions for active collection operations.

This document is authoritative for **observer-scoped CLI behavior** and must be used before adding/changing commands.

## 2) Architectural framing (authoritative)

- CodeSentinel = external governance/orchestration harness (the only development harness).
- Calamum = security harness.
- Observer = security test surface (not a development platform).

`observerctl` must remain observer-scoped and standalone from CodeSentinel runtime process surfaces.

Normative scope clarification:
- `observerctl` command families in this document are observer runtime/security operations surfaces.
- They are **not** development-scoped commands and must not depend on CodeSentinel runtime process surfaces.

## 3) Command topology (approved runtime operations)

### 3.1 Active-collection control surface: `observerctl ops *`

All mode-transition and gate commands are under `ops`.

Required minimum gate set:
1. `observerctl ops preflight --json`
2. `observerctl ops mode gate --to <mode> --json`
3. `observerctl ops gate-check --json`
4. `observerctl ops evidence pack --event <event> --json`
5. `observerctl ops evidence verify --packet <path> --json`

Additional `ops` controls:
- `observerctl ops mode current --json`
- `observerctl ops mode list --json`
- `observerctl ops mode set --to <mode> --json`
- `observerctl ops mode transition --to <mode> --source <sim|real> --event <event> --output <path> --json`
- `observerctl ops evidence index --json`

### 3.2 Baseline and graph management: `observerctl baseline *`

- graph info
- baseline readiness checks
- baseline status and evidence pointers
- baseline lifecycle management primitives needed for observer lane readiness

### 3.3 Sample/data-store management: `observerctl librarian *`

`librarian` owns the data-store controls (the earlier “datastore” concept).

Includes:
- per-mode data-store status,
- sample volume/stat summaries,
- archive/rotation/compaction controls,
- mode-specific retention state.

### 3.4 Watchdog posture: `observerctl watchdog *`

- heartbeat status
- stale detection
- posture reason-code reporting
- watchdog-facing control acknowledgement surfaces (names-only)

### 3.5 Diagnostics: `observerctl health *`

Renamed from `doctor`.

- `observerctl health quick --json`
- `observerctl health full --json`
- `observerctl health explain --code <reason_code> --json`

### 3.6 Policy introspection (read-only): `observerctl policy *`

- policy surface visibility
- gate-rule explanation
- no runtime mutation

## 4) Command contract matrix (implementation baseline)

| Surface | Command | Purpose | Success exit | Denied/failed exit |
|---|---|---|---:|---:|
| ops | `ops preflight --json` | Collect names-only readiness facts | 0 | 2/4/5 |
| ops | `ops mode gate --to Y --json` | Evaluate transition authorization from inferred current mode | 0 | 2 |
| ops | `ops mode transition --to Y --json` | Atomic gate + set + evidence workflow | 0 | 2/3/5 |
| ops | `ops gate-check --json` | Evaluate global go/no-go | 0 | 2 |
| ops | `ops evidence pack --event E --json` | Emit triad packet for event E | 0 | 3/5 |
| ops | `ops evidence verify --packet P --json` | Validate packet schema/hash | 0 | 3 |
| baseline | `baseline status --json` | Baseline + graph readiness status | 0 | 2/4/5 |
| baseline | `baseline graph --json` | Graph/index freshness and integrity posture | 0 | 2/4/5 |
| baseline | `baseline check --json` | Baseline gate-readiness evaluation | 0 | 2 |
| baseline | `baseline set --id <id> --json` | Promote selected baseline as active | 0 | 2/3/4/5 |
| librarian | `librarian stats --json` | Sample/data-store stats by mode | 0 | 5 |
| librarian | `librarian stores --json` | Enumerate mode-specific stores and active pointers | 0 | 5 |
| librarian | `librarian rotate --mode M --json` | Trigger rotation for mode store | 0 | 2/4/5 |
| librarian | `librarian compact --mode M --json` | Compaction/manifest refresh for mode store | 0 | 2/4/5 |
| watchdog | `watchdog status --json` | Watchdog heartbeat/posture status | 0 | 2/5 |
| watchdog | `watchdog check --json` | Fail-closed watchdog readiness check | 0 | 2 |
| watchdog | `watchdog reasons --json` | Emit normalized posture reason codes | 0 | 5 |
| health | `health quick --json` | Fast diagnostic triage | 0 | 2/5 |
| health | `health full --json` | Full diagnostic matrix for operator triage | 0 | 2/5 |
| health | `health explain --code C --json` | Decode reason code + remediation hints | 0 | 3/4 |
| policy | `policy show --json` | Display effective observer policy profile | 0 | 4/5 |
| policy | `policy validate --json` | Validate policy contract vs runtime state | 0 | 2/4/5 |

Exit-code policy:
- `0`: command succeeded and (if gate command) decision = `go`
- `2`: fail-closed no-go / policy denial
- `3`: invalid command contract, schema, or packet
- `4`: required dependency/context missing
- `5`: runtime I/O or artifact access failure

## 5) Mode-change gate model

Mode changes are security transitions and must be treated as explicit gate events.

Operator simplification rule:
- `ops mode gate` infers source mode from current runtime state.
- `--from` is intentionally removed in this phase to avoid operator burden and mismatch errors.
- Scheduler-driven explicit source mode is deferred (not in scope for this release).

Primary transitions:
- `sim -> real`
- `canary -> honeypot`
- `watch -> canary`

Required checks per transition:
- watchdog heartbeat freshness,
- observer heartbeat freshness,
- baseline readiness,
- mode-specific data-store readiness,
- required env presence (presence-only; never values),
- trigger posture enforcement (`isolation|lockdown`),
- run linkage (`run_id` + `security_report_ref` + `posture_trigger_id`),
- reason-code packet generation.

Transition commands must fail closed and must not auto-fallback to warning-only outcomes.

Atomic transition execution contract:
- `ops mode transition` performs `gate -> set -> evidence` in one operation.
- If any phase fails, command returns fail-closed and preserves denial evidence.

### 5.1 Current-mode inference contract

Inference order (deterministic):
1. explicit runtime state artifact (if present),
2. active mode pointer in mode-specific datastore metadata,
3. observer runtime env selector,
4. fail-closed `unknown_mode` denial.

If inferred mode is unknown, `ops mode gate --to <mode>` returns `2` with reason code `critical_check_failed:mode_current_unknown`.

### 5.2 Trigger posture model (watchdog-enforced)

Trigger postures:
- `isolation` (required for `watch` and `canary`)
- `lockdown` (required for `live` and `honeypot`)

Isolation behavior:
- quarantine container,
- block ingress/egress (`no data in or out`),
- suspend collector/interactor flows,
- permit only names-only health/evidence logging.

Lockdown behavior (same severity for `live` and `honeypot`):
- apply full isolation behavior,
- elevate heartbeat cadence,
- tighten heartbeat stale threshold,
- elevate baseline validation cadence,
- freeze non-essential writes,
- require recovery validation window before unlocking.

Failure contract:
- posture mismatch or inability to enforce posture returns exit `2`.
- normalized reason code: `critical_check_failed:watchdog_trigger_posture_invalid`.

## 6) Data-store model (mode-specific)

Observer may use separate stores per mode. This is explicitly in scope for `librarian` management.

Required behavior:
- identify active store by mode,
- expose per-mode stats and retention state,
- prevent cross-mode ambiguity in status/evidence output,
- include mode-store references in gate evidence packets.

### 6.1 Librarian command definitions

- `observerctl librarian stats --json`
	- output: per-mode record counts, archive counts, manifest integrity summary.
- `observerctl librarian stores --json`
	- output: store inventory with mode labels and active-store pointer.
- `observerctl librarian rotate --mode <mode> --json`
	- behavior: rotation action with before/after pointers, no raw content output.
- `observerctl librarian compact --mode <mode> --json`
	- behavior: compaction and manifest normalization for target mode.
- `observerctl librarian verify --mode <mode> --json`
	- behavior: store integrity check and readiness status for gate consumers.

## 6.2 Baseline command definitions

- `observerctl baseline status --json`
	- output: active baseline id, freshness window, status.
- `observerctl baseline graph --json`
	- output: graph/index file pointers, freshness, consistency signals.
- `observerctl baseline check --json`
	- output: fail-closed gate eligibility for baseline dependency.
- `observerctl baseline list --json`
	- output: known baselines with lineage and timestamps.
- `observerctl baseline set --id <id> --json`
	- output: selected baseline pointer update packet.

## 6.3 Watchdog command definitions

- `observerctl watchdog status --json`
	- output: heartbeat ages, posture status, confidence flags.
- `observerctl watchdog check --json`
	- output: go/no-go for watchdog prerequisite checks.
- `observerctl watchdog reasons --json`
	- output: normalized reason codes and source artifacts.
- `observerctl watchdog ack --code <reason> --json`
	- output: names-only operator acknowledgment event.

## 6.4 Health and policy command definitions

- `observerctl health quick --json`
	- output: compact critical-check summary.
- `observerctl health full --json`
	- output: full component matrix (ops, baseline, librarian, watchdog).
- `observerctl health explain --code <reason_code> --json`
	- output: reason explanation + non-secret remediation hints.
- `observerctl policy show --json`
	- output: active policy profile and hashes/pointers.
- `observerctl policy validate --json`
	- output: policy compliance check against runtime posture.

## 7) Publish-grade packet requirements (triad)

Each high-value transition event must emit a triad packet:

1. **Provenance**
	- artifact path
	- artifact hash/digest
	- generated timestamp (UTC)
	- producer identity
	- upstream input references

2. **Methodology**
	- check strategy/model
	- invariants and constraints
	- failure modes
	- reproducibility steps

3. **Process**
	- phase/event
	- decision (`go`/`no-go`)
	- rationale
	- reason codes
	- evidence references
	- approver checkpoint

## 8) Fail-closed invariants

- Gate denial returns non-zero.
- Missing critical prerequisites returns non-zero.
- Packet verification failure returns non-zero.
- Live transition without required evidence linkage is denied.
- No command may print or persist secret values.

## 8.1 Gate-output packet schema (minimum)

Every gate-producing command under `ops` must include:
- `timestamp_utc`
- `decision` (`go` | `no-go`)
- `reason_codes[]`
- `critical_checks[]`
- `runtime_label` (`observer`)
- `runtime_cli_surface` (`observerctl`)
- `run_id`
- `posture_trigger_id`
- `posture_trigger` (`isolation|lockdown`)
- `security_report_ref`

Evidence-producing commands must additionally include triad sections:
- `provenance`
- `methodology`
- `process`

## 9) Non-goals

- No coupling to CodeSentinel runtime process orchestration.
- No broad “platform” abstractions that reposition observer as a development platform.
- No scope expansion into non-observer Calamum systems.

## 10) Implementation phases

### Phase A — Contract lock
- Freeze command grammar and exit-code semantics.
- Freeze triad schema fields.

### Phase B — Ops gate surface
- Complete `ops` mode/gate/evidence command family.
- Enforce fail-closed behavior and JSON contract consistency.
- Ensure mode source is inferred from current state (`--from` removed).

### Phase C — Baseline/Librarian/Watchdog integration
- Ensure `baseline`, `librarian`, `watchdog` provide deterministic inputs for `ops` gate evaluation.

### Phase D — Health/policy hardening
- Finalize `health` triage surfaces.
- Finalize read-only `policy` explainability surfaces.

## 11) Dependency

- Scope-separation policy updates from Job 0022 lineage remain authoritative.

## 12) Deliverables

- command contract matrix (commands, args, outputs, exit codes),
- mode-transition gate matrix,
- triad packet schema map,
- fail-closed test matrix and evidence references.
- reusable transition/posture execution templates under `template_library/reports/`.

## 12.1 Data contract linkage requirement

All collection/gate/evidence records MUST carry:
- `run_id`
- `posture_trigger_id`
- `security_report_ref`

This forms the run-level security linkage contract used for report traceability and audit replay.

## 13) Sign-off checklist (implementation-ready)

- [ ] `ops` gate command set uses inferred current mode (no `--from`).
- [ ] baseline section fully defines graph and baseline-management commands.
- [ ] librarian section fully defines per-mode datastore management commands.
- [ ] watchdog section fully defines posture/reason/ack command behavior.
- [ ] health and policy sections are fully specified and read-only where required.
- [ ] all command outputs conform to JSON schema and fail-closed exit-code policy.
- [ ] triad packet sections are present for all evidence-producing commands.

## 14) Next actions (declared)

1. Align `observerctl` runtime command outputs to include `run_id`, `posture_trigger_id`, `posture_trigger`, and `security_report_ref`.
2. Implement watchdog trigger posture policy (`isolation` vs `lockdown`) in `ops mode gate` with fail-closed behavior.
3. Add lockdown parameter checks: heartbeat cadence escalation and baseline validation cadence escalation.
4. Add tests for trigger posture mapping and run-linkage contract enforcement.
5. Update operator-facing docs/examples to use `sim|real` source terminology consistently.
