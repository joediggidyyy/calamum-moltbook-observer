# ObserverCTL Implementation Gap Audit (Official) — 2026-02-21

**Document ID**: `OBSERVERCTL_IMPLEMENTATION_GAP_AUDIT_20260221`  
**Owner**: ORACL-Prime  
**Approver**: joediggidyyy  
**Status**: OFFICIAL AUDIT (OPEN FINDINGS, EXECUTION COMPLETE)  
**Scope**: `projects/calamum-moltbook-observer/`  
**Policy mode**: names-only, fail-closed

---

## Audit objective

Convert the 2026-02-21 informal observerctl implementation review into an official operations audit artifact, classify implementation gaps against Job0023 + execution-expectations contracts, and establish explicit chain links to the most recent implementation-drift audit records.

---

## Primary requirement baselines audited

- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0023_OBSERVERCTL_COMMAND_SURFACE_PLANNING_20260221.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0023_OBSERVERCTL_COMMAND_SURFACE_PLANNING_20260221.json`
- `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md`
- `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.json`

## Implementation surfaces audited

- `projects/calamum-moltbook-observer/src/observerctl.py`
- `projects/calamum-moltbook-observer/src/tests/test_observerctl.py`
- `projects/calamum-moltbook-observer/src/calamum_observer_agent.py`

Validation evidence in-session:
- `pytest projects/calamum-moltbook-observer/src/tests/test_observerctl.py -q` -> pass (`9 passed`)

---

## Drift-chain pointers (most recent implementation_drift documents)

### Prior checkpoint (tracked)

- `projects/calamum-moltbook-observer/docs/reports/operations/audits/IMPLEMENTATION_DRIFT_AUDIT_CLOSURE_20260221.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/audits/IMPLEMENTATION_DRIFT_AUDIT_CLOSURE_20260221.json`

### Prior checkpoint evidence pointers (untracked/local audit lane)

- `projects/calamum-moltbook-observer/local_untracked/audits/implementation_drift/implementation_drift_audit_20260221T235840.626604Z.md`
- `projects/calamum-moltbook-observer/local_untracked/audits/implementation_drift/implementation_drift_audit_20260221T235840.626604Z.evidence.json`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/implementation_drift_audit.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/audit_index.json`

### Consecutive-link role

This audit is the immediate follow-on to `IMPLEMENTATION_DRIFT_AUDIT_CLOSURE_20260221` and serves as the next node in the observer drift-governance chain.

---

## Official findings

| ID | Gap | Severity | Evidence anchor | Recommended remediation |
|---|---|---|---|---|
| OGA-01 | Trigger-posture validation is self-derived, so mismatch cannot be detected in practice. | BLOCKER | `evaluate_gate_decision()` computes and compares posture from target mode only. | Validate against an external/runtime watchdog posture source and deny on mismatch. |
| OGA-02 | Lockdown escalation checks do not verify cadence escalation semantics. | BLOCKER | Lockdown path checks heartbeat status + graph presence, not escalation rates. | Add explicit cadence checks (heartbeat + baseline validation) and enforce fail-closed reason codes. |
| OGA-03 | `security_report_ref` linkage is static, not run-bound. | BLOCKER | `_default_security_report_ref()` constant + non-empty check only. | Bind report reference to run context and verify run-linkage continuity. |
| OGA-04 | Collection records do not carry full run-linkage envelope. | BLOCKER | `calamum_observer_agent` output lacks required linkage fields. | Add `run_id`, `posture_trigger_id`, `posture_trigger`, `security_report_ref` to collection records. |
| OGA-05 | Unknown mode handling coerces to `watch` instead of fail-closed `unknown_mode`. | MAJOR | `_load_state()` normalizes invalid modes to `watch`. | Preserve unknown state and deny with normalized reason code. |
| OGA-06 | `ops mode set` does not enforce freshness window on prior gate packet. | MAJOR | Packet checked for decision/to_state only; no TTL guard. | Add gate packet age threshold and deny stale packets. |
| OGA-07 | Schema/contract-invalid paths do not consistently map to exit code `3`. | MAJOR | verify failure path currently exits as no-go (`2`) semantics. | Route schema-invalid errors to contract-invalid exit path (`3`) and test explicitly. |
| OGA-08 | Source-axis vocabulary drift (`sim|real` vs `sim|live`) across runtime scripts. | MAJOR | observerctl vs related runtime producer CLI mismatch. | Canonicalize to `sim|real`; retain alias only if formally documented. |
| OGA-09 | Baseline-plan examples include stale command forms in places. | MINOR | older top-level command examples. | Update docs/examples to canonical `observerctl ops ...` forms. |

---

## Decision

- Audit execution: **COMPLETE**
- Findings state: **OPEN FOR REMEDIATION**
- Gate posture for live-readiness claims: **DO NOT CLAIM FULL CONTRACT-COMPLIANT LIVE READINESS** until all BLOCKER findings are closed.

---

## Mandatory next actions

1. Remediate BLOCKER findings OGA-01..OGA-04 in implementation and tests.
2. Enforce exit-code contract determinism (`0/2/3/4/5`) for schema/dependency/runtime failure classes.
3. Re-run drift audit lane and publish next closure checkpoint linked back to this report.

---

## Recovered unofficial audit detail (now formally persisted)

This section preserves the higher-detail content previously emitted in interactive output during the informal audit pass and is now made part of the official report record.

### Additional audited files (grouped)

#### Planning / policy / requirements

- `projects/calamum-moltbook-observer/planning/OBSERVERCTL_MODE_TRANSITION_MATRIX_CHAPTER_20260221.md`
- `projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_OBSERVER_BASELINE_INTEGRATION_SCAFFOLD_20260220.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0024_OBSERVER_TEST_COVERAGE_BASELINE_REMEDIATION_20260221.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0024_OBSERVER_TEST_COVERAGE_BASELINE_REMEDIATION_20260221.json`

#### Quest artifacts

- `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221.md`
- `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221.json`

### Command-surface completeness snapshot

The command family topology is implemented in `observerctl.py` across the required namespaces:

- `ops`: `preflight`, `mode (current/list/gate/set/transition)`, `gate-check`, `evidence (pack/verify/index)`
- `baseline`: `status`, `graph`, `check`, `list`, `set`
- `librarian`: `stats`, `stores`, `rotate`, `compact`, `verify`
- `watchdog`: `status`, `check`, `reasons`, `ack`
- `health`: `quick`, `full`, `explain`
- `policy`: `show`, `validate`

Interpretation: topology and parser coverage are broadly complete; principal residual risk is semantic contract-enforcement depth for posture/cadence/run-linkage.

### Contextual confidence note from informal lane

- Confidence: **medium-high**
- Basis:
	- full required spec + expectations pair reviewed (`.md` + `.json`),
	- implementation + tests reviewed,
	- observerctl suite revalidated in-session (`9 passed`).

### Informal-to-official conversion note

Any previously chat-only summary language for the informal audit is superseded by this persisted section and the official findings matrix above.

---

Prepared by ORACL-Prime for joediggidyyy.
