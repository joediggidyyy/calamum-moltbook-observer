# Observer Integrity Baseline Update Task Assessment (2026-03-20)

**Owner**: ORACL-Prime  
**Approver**: joediggidyyy  
**Status**: active assessment / audit surface  
**Scope**: `projects/calamum-moltbook-observer/` integrity-baseline update lane with adjacent-system review of CodeSentinel integrity and VAULT baseline surfaces

---

## Purpose

This document records a scoped assessment of the **observer integrity baseline update tasks** so the lane can proceed with a clean authority map, bounded implementation expectations, and a transparent action log.

This assessment is intentionally narrow:

- it treats **`CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211`** as the **parent roadmap driver**;
- it treats **`CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220`** as the **current task focus lane**;
- it treats integrity-baseline update work as a **specific follow-through lane**, not as a license to reopen unrelated audit/remediation drift surfaces;
- it does **not** claim that planned implementation has already occurred.

---

## Authority and scope map

### Parent roadmap authority

- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.md`

### Current task focus

- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220.md`

### Current observer baseline cleanup / continuation surface

- `projects/calamum-moltbook-observer/docs/reports/operations/standards/OBSERVER_BASELINE_DRIVER_REALIGNMENT_EXECUTION_CHECKLIST_20260320.md`
- `report_tmp/calamum_baseline_cutover_inventory/calamum_baseline_cutover_inventory.md`

### Historical but non-authoritative observer baseline surface

- `quarantine_legacy_archive/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223_archive_20260320.md`

Working rule:

- For this lane, **integrity baseline** means the observer-side baseline command/update surface that still exposes legacy filesystem-hash baseline behavior inside `observerctl`.
- It must **not** be silently conflated with:
  - observer collection baseline,
  - resource/recommendation baseline,
  - operational-readiness baseline,
  - CodeSentinel global file-integrity baseline,
  - VAULT credential-store integrity baseline.

---

## Documents and adjacent systems reviewed

### Observer-scoped documents

- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/standards/OBSERVER_BASELINE_DRIVER_REALIGNMENT_EXECUTION_CHECKLIST_20260320.md`
- `projects/calamum-moltbook-observer/docs/OBSERVERCTL_CLI_TRANSITION_OPERATOR_GUIDE_20260221.md`
- `report_tmp/calamum_baseline_cutover_inventory/calamum_baseline_cutover_inventory.md`
- `quarantine_legacy_archive/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223_archive_20260320.md`

### Adjacent CodeSentinel integrity surfaces

- `codesentinel/cli/integrity_utils.py`
- `docs/cli/help/integrity_help.md`
- `docs/guides/VAULT_CREDENTIAL_LOADING_GUIDE.md`

### Observer implementation surface inspected

- `projects/calamum-moltbook-observer/src/observerctl.py` (baseline command family)

---

## Findings

### 1. The observer integrity-baseline update lane is real, and is now implemented

**Update 2026-03-20**: The command-surface cutover has been executed.

- `projects/calamum-moltbook-observer/src/observerctl.py` rewired — `_baseline_status()` and `_baseline_check()` now route to `_baseline_chunked_status()` / `_baseline_chunked_check()` by default
- Legacy filesystem-hash path preserved under explicit `--baseline <path>` argument
- 43 observer tests passed with no regressions
- Remaining open item: archive of generated legacy baseline artifacts from cutover inventory (pending operator approval)

### 2. ~~The current `observerctl` baseline status/check path still routes through filesystem-hash helpers~~ — RESOLVED 2026-03-20

Prior state (at time of original assessment):
- `_baseline_status()` → `_baseline_hash_status()`
- `_baseline_check()` → `_baseline_hash_check()`

Current state after cutover:
- `_baseline_status()` → `_baseline_chunked_status()` (default, no explicit path arg)
- `_baseline_check()` → `_baseline_chunked_check()` (default, no explicit path arg)
- `_baseline_status(baseline=<path>)` → `_baseline_hash_status()` (explicit path arg, integrity/drift use case)
- `_baseline_check(baseline=<path>)` → `_baseline_hash_check()` (explicit path arg, integrity/drift use case)
- Output field `baseline_type` now emits `chunked_dynamic` on default calls

### 3. Observer integrity baseline is adjacent to, but distinct from, CodeSentinel global integrity

Adjacent core review shows:

- CodeSentinel global file integrity uses `codesentinel integrity ...` via `codesentinel/cli/integrity_utils.py`
- that system maintains a repo/workspace file-hash baseline and supports `verify`, `rebaseline`, and `ops` sidecar regeneration
- VAULT guidance separately treats credential-store baseline/integrity as a protected store concern (`vault lock`, `vault rebaseline`, edit-window discipline)

Therefore:

- observer integrity-baseline update work should borrow **clarity of terminology** from adjacent systems,
- but should **not** silently collapse into CodeSentinel global integrity or VAULT baseline semantics.

### 4. The current safest interpretation of the observer task is a narrow command-surface cutover

The smallest justified implementation scope remains:

1. change observer baseline **status/check authority presentation**;
2. keep legacy filesystem-hash capability available only as explicit integrity/drift handling;
3. update tests and evidence notes accordingly;
4. avoid bundling larger `observerctl` refactors.

---

## Scoped task decomposition

### Task A — authority-preserving implementation cutover

- Rewire observer baseline command behavior so default readiness semantics no longer present `filesystem_hash` as the primary operator-facing baseline surface.
- Preserve explicit legacy/integrity handling rather than deleting it.

### Task B — focused test alignment

- Update only the targeted `observerctl` baseline tests required to reflect the cutover.
- Do not use this lane to broaden unrelated observer test remediation.

### Task C — artifact and handoff hygiene

- After code/test cutover is validated, archive generated legacy observer baseline artifacts named in the cutover inventory.
- Refresh the relevant observer report surfaces with evidence references and a concise handoff note.

---

## Approved change set in this pass

This pass is **documentation and audit-surface only**.

Actions intentionally taken:

1. created this assessment document to record the integrity-baseline task map, adjacent-system distinctions, and scoped next actions;
2. linked this assessment from the active observer baseline realignment checklist;
3. did **not** modify `observerctl.py` implementation semantics in this pass;
4. did **not** mark the baseline cutover implementation as completed.

Rationale:

- the operator requested deliberate, measured changes;
- the repository recently suffered from rogue drift and remediation/audit churn;
- the safest current move is to improve **traceability and scope control** before touching implementation.

---

## Transparent action log

### 2026-03-20T00:00Z-ish review actions (original pass)

- Reviewed observer roadmap authority and task-focus surfaces.
- Reviewed baseline cutover checklist and inventory.
- Reviewed archived baseline ambiguity notes from former `Job 0029` content.
- Reviewed adjacent CodeSentinel integrity and VAULT baseline documentation.
- Inspected current `observerctl` baseline implementation path.
- Added this audit memo.
- Added a link from the active continuation checklist to this memo.

### 2026-03-20 implementation pass

- Implemented baseline command-surface cutover in `projects/calamum-moltbook-observer/src/observerctl.py`:
  - added `_baseline_chunked_status()` — reads active baseline from catalog, returns `chunked_dynamic` readiness packet
  - added `_baseline_chunked_check()` — same catalog logic, fail-closed reason codes
  - rewired `_baseline_status()` — routes to chunked by default; falls back to `_baseline_hash_status()` only when explicit `--baseline` path provided
  - rewired `_baseline_check()` — same dispatch logic
- Ran `pytest projects/calamum-moltbook-observer/src/tests/test_observerctl.py -q`: **43 passed, 0 failed**
- Updated checklist (Phase 4 and 5), this memo (Findings 1 and 2), and Job 0022 (2026-03-20 completion note)

### Explicit non-actions (implementation pass)

- No legacy runtime audit artifacts archived yet (pending operator approval per cutover inventory).
- No `baseline rebaseline` CLI command added (design not yet documented; deferred).
- No `test_observerctl.py` modifications required — existing tests already covered the cutover paths and all 43 passed.

---

## Recommended next implementation bite

When approved, the next questframe-sized implementation bite should be:

1. update `projects/calamum-moltbook-observer/src/observerctl.py` so default baseline readiness surfaces point to the chunked/dynamic path;
2. keep filesystem-hash baseline available only as an explicit integrity/drift path;
3. update the focused `observerctl` baseline tests;
4. run targeted validation and append evidence/handoff notes.

Exit criteria for that future bite:

- operator-facing baseline status/check output no longer treats `filesystem_hash` as the default readiness authority;
- legacy integrity/drift behavior remains explicit and bounded;
- tests pass;
- report surfaces record what changed and what remains deferred.

---

Prepared by ORACL for joediggidyyy.
