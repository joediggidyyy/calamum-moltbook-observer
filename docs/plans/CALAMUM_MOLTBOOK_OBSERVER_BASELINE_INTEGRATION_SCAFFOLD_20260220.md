# Plan: Calamum Moltbook Observer — Baseline Integration Scaffold

> Canonical strategy SSOT: `docs/operations/ssot/CIDS_MULTISCOPE_INTEGRITY_GRAPH_STRATEGY_SSOT_20260220.md`
>
> Calamum execution policy: `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md`
>
> Active high-value lane: `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-KEYMASTER-RETRIEVAL-READINESS-20260219.md`
>
> Status registry: `operations/tasks.json`

## Metadata

- Status: planned
- Owner: ORACL-Prime
- Stakeholder: joediggidyyy
- Date (UTC): 2026-02-20
- Scope: integrate CodeSentinel baseline health into observer readiness operations with standalone `observerctl` scope boundaries

## Purpose

Provide implementation-ready scaffolding to integrate CodeSentinel baseline posture into observer operational lanes without violating project locality or gate semantics.

## Integration objective

Enable Keymaster/observer operations to consume baseline readiness as a deterministic dependency signal:

- baseline state is healthy and recent,
- evidence is names-only and gate-linked,
- local/project runtime separation remains policy-correct.

Additional scope boundary:

- observer runtime CLI surface is `observerctl` (standalone, observer-scoped),
- `observerctl` must not depend on CodeSentinel runtime process surfaces.

## Existing doctrine alignment (authoritative sources)

This scaffold is aligned to existing observer governance and does not replace it:

- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0009_MOLTBOOK_OBSERVER_RECOVERY_AND_STABILIZATION_20260205.md`
- `projects/calamum-moltbook-observer/docs/KEEPALIVE_CONFIG_ANALYSIS.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0020_MOLTBOOK_OBSERVER_STAGE4_RUNTIME_PROVENANCE_LANE_20260219.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0021_MOLTBOOK_KEYMASTER_RETRIEVAL_READINESS_20260219.md`

Doctrine summary preserved here:

- watchdog is authoritative for runtime control posture,
- observer/librarian/watchdog telemetry remains distributed for awareness fidelity,
- dashboard/UI surfaces are non-authoritative and must not fabricate liveness.

## Proposed task scaffold (to register in `operations/tasks.json`)

```text
id: calamum-moltbook-baseline-integration-20260220
summary: Integrate CodeSentinel baseline readiness with Calamum observer and Keymaster operational gates
path: projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220.md
category: governance
owner: ORACL-Prime
sandbox: calamum
priority: P0
status: planned
```

## Gate-critical artifact scaffold

- QuestStack: `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220.md`
- QuestFrame: `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220.json`
- Job stub (repo-root): `jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
- Project job docs:
  - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
  - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.json`
- Job report: `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220.md`
- Quest evidence artifacts:
  - `logs/queststack/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220_log.md`
  - `logs/queststack/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220_evidence.jsonl`
- Gate evidence stream: `logs/behavioral/gates/gate_events.jsonl`

## Required dependency inputs (from CodeSentinel baseline lane)

- `baseline_scope_contract_v0`
- `baseline_chunk_envelope_v0`
- `baseline_evidence_event_shape_v0`
- `known_limits_and_budget_profile_20260220`

These should be referenced names-only in Calamum paperwork and must not embed secret values or internal host identifiers.

## Integration phases

### Phase 1 — Paperwork and contract binding

- Add baseline dependency references to integration QuestStack/QuestFrame.
- Record exact acceptance criteria for "baseline-ready" signal.
- Link to active Keymaster lane for readiness gating.
- Register observerctl scope contract and naming policy in lane docs.

Exit criteria:

- PRE_JOB parse surface includes all required artifacts.
- No KEYSMITH/KEYMASTER role-boundary drift.

### Phase 2 — Runtime policy hookup

- Define pre-step that checks baseline evidence freshness before Keymaster readiness transitions.
- Keep Calamum runtime outputs project-local while retaining root-level governance evidence.
- Bind watchdog control decisions to baseline posture inputs (`baseline_posture_inputs_v0`).
- Preserve distributed keepalive telemetry as observability signals (not authorization artifacts).
- Define `observerctl preflight` and `observerctl gate-check` output schemas (names-only).

Exit criteria:

- Baseline readiness check is deterministic and names-only.
- Policy locality rules remain intact.
- Control-plane and observability-plane boundaries are explicit in lane artifacts.

### Phase 3 — Validation and failure semantics

- Validate successful path (healthy baseline).
- Validate failure path (stale/failed baseline) with explicit stop condition.
- Ensure close-gate behavior denies completion if dependencies are unsatisfied.
- Produce publication-grade methodology/provenance/process packets for each gate decision.

Exit criteria:

- Go/no-go decisions can cite explicit evidence pointers.
- Failure path is fail-closed and auditable.

## Baseline-ready acceptance contract (for Moltbook lane)

A run is baseline-ready when all are true:

1. Latest baseline event indicates success (no timeout/partial checkpoint failure).
2. Baseline scope confirms `local_codesentinel` policy compliance.
3. Freshness is within lane-defined budget window.
4. Gate evidence and quest evidence pointers are present and cross-linked.

If any condition fails, Keymaster live execution remains blocked.

## Posture gate contract (watchdog-authoritative; observer scope)

### Two-plane model (normative)

- **Control plane:** watchdog-issued posture decisions and quarantine/unquarantine authority.
- **Observability plane:** distributed keepalive/heartbeat emissions from observer, librarian, and watchdog.

Observability events can trigger review/escalation but cannot self-authorize risky actions.

### Posture states

1. `NORMAL`
   - Stage 4 active-gated monitoring permitted under existing lane bounds.
2. `HEIGHTENED_AWARENESS`
   - Entered on key movements (Keymaster analyze/dry-run/validate transitions, source/mode flips, baseline rebaseline events).
   - Tighter freshness thresholds and denser runtime checks.
3. `PROVENANCE_LOCK`
   - Requires contiguous evidence packet quality before advancing high-value steps.
4. `HIGH_ALERT_QUARANTINE`
   - Fail-closed posture on stale/missing watchdog heartbeat, baseline failure/timeout, role-boundary drift, or critical security triggers.

### Minimum watchdog posture receipt fields (names-only)

- `posture_state`
- `reason_codes[]`
- `watchdog_receipt_id`
- `baseline_freshness_sec`
- `topology_state` (expected deterministic runtime topology)
- `expires_at_utc`
- `evidence_refs[]`

### Keymaster progression guard

For Job 0021 live eligibility, all must hold:

- Action sequence complete (`Analyze -> Dry-run -> Validate`),
- posture receipt not in `HIGH_ALERT_QUARANTINE`,
- baseline readiness contract satisfied,
- explicit stakeholder go/no-go checkpoint recorded.

## Validation matrix

- PRE_JOB pass with complete artifact spine.
- PREFLIGHT/BOD/POST_JOB evidence present for lane window.
- SessionMemory health recorded at close.
- Names-only discipline maintained throughout reports and logs.
- observerctl standalone contract validated (no CodeSentinel runtime-process dependency).
- Publish-grade packet triad present (provenance, methodology, process).

## Observerctl gated execution prep (implementation checklist)

- [ ] Define observerctl command contract:
  - `observerctl preflight --json`
  - `observerctl gate-check --json`
  - `observerctl evidence-pack --json`
- [ ] Ensure outputs reference artifact paths only (no secrets).
- [ ] Ensure every go/no-go decision includes reason codes and evidence refs.
- [ ] Ensure reproducibility notes map methodology -> process -> evidence.
- [ ] Ensure gate-facing packet links are written into QuestStack evidence.

## Risks and mitigations

- **Risk**: Baseline freshness ambiguity blocks readiness decisions.
  - **Mitigation**: explicit freshness field + acceptance threshold in report checklist.
- **Risk**: Locality conflict between project logs and root evidence.
  - **Mitigation**: enforce policy split from Calamum execution expectations.
- **Risk**: Role boundary drift (KEYSMITH vs KEYMASTER) in integration docs.
  - **Mitigation**: explicit role-boundary validation checkpoint.

## Implementation notes (operator-facing)

- This scaffold is planning-only; it does not execute live retrieval.
- It is designed to plug into the existing Keymaster readiness lane as a dependency module.

## Change log

- 2026-02-20: Initial implementation-ready scaffolding created for Moltbook baseline integration.
- 2026-02-20: Added project-grounded watchdog authority model, two-plane boundary, and posture gate contract.
