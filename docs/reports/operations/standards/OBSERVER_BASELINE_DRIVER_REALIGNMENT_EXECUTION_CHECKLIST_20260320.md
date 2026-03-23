# Observer Baseline Driver Realignment — Execution Roadmap Checklist (2026-03-20)

**Owner**: ORACL-Prime  
**Approver**: joediggidyyy  
**Scope**: `projects/calamum-moltbook-observer/` with one explicit cross-scope session-snapshot correction under `.agent_session/`  
**Status**: active execution checklist / handoff surface

---

## Purpose

This checklist records the execution roadmap for cleaning up observer baseline authority surfaces so downstream work is guided by the correct driver, not by stale or duplicate paperwork.

Current governing intent:

- `CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220` is the execution driver.
- `CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223` is archived historical material, not an anchor.
- The global `.agent_session/ops_awareness.{json,md}` `up_next` field is a known false-pointer surface and may require manual clearing until the core remediation lane is resumed.
- `observerctl.py` remains monolithic for now by explicit operator direction; no CLI refactor is bundled into this cleanup lane.

---

## Action ledger (completed in this pass)

- [x] Manually cleared `.agent_session/ops_awareness.json` `up_next.line` and aligned `.agent_session/ops_awareness.md` to remove the false pointer from the CLI-facing snapshot surface.
- [x] Archived the full pre-cleanup `Job 0029` markdown/json payloads under:
  - `quarantine_legacy_archive/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223_archive_20260320.md`
  - `quarantine_legacy_archive/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223_archive_20260320.json`
- [x] Stripped live `Job 0029` surfaces down to archived-tombstone notices.
- [x] Updated downstream authority references so active execution points to `Job 0022` instead of `Job 0029`.
- [x] Added this checklist as the current handoff/reference surface for the cleanup and continuation lane.
- [x] Added a dedicated integrity-baseline update assessment / action-log surface:
  - `projects/calamum-moltbook-observer/docs/reports/operations/audits/OBSERVER_INTEGRITY_BASELINE_UPDATE_TASK_ASSESSMENT_20260320.md`
- [x] *(2026-03-20)* Implemented baseline command-surface cutover in `observerctl.py`:
  - `_baseline_status()` and `_baseline_check()` now route to chunked/dynamic catalog by default
  - Explicit `--baseline <path>` flag still routes to legacy filesystem-hash (integrity/drift use case preserved)
  - 43 observer tests passed; no regressions
  - Evidence: `projects/calamum-moltbook-observer/src/tests/test_observerctl.py` (43 passed, 2026-03-20)
- [x] *(2026-03-20)* Prepared detailed phased execution handoff for baseline-monitoring uplift:
  - `projects/calamum-moltbook-observer/docs/reports/operations/standards/OBSERVER_BASELINE_MONITORING_EXECUTION_HANDOFF_20260320.md`
  - documents exact code surfaces, contract mismatch (`resource_baseline` vs `resource_rapid`), execution order, lock decisions, validation obligations, and non-goals

---

## Execution roadmap

### Phase 1 — Session-awareness hygiene

- [x] Confirm the false `up_next` pointer is only a snapshot artifact, not the authoritative driver.
- [x] Manually clear the advertised `up_next` value in `.agent_session/ops_awareness.{json,md}`.
- [ ] Re-clear the snapshot if a later SessionMemory refresh reintroduces the false pointer before the core fix lands.
- [ ] When the core remediation lane resumes, replace manual clearing with the canonical fix and retire this workaround note.

### Phase 2 — Authority cleanup

- [x] Reconfirm the driver job is `CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220`.
- [x] Archive unique `Job 0029` content before neutralizing the live path.
- [x] Strip live `Job 0029` surfaces so they cannot be mistaken for active execution authority.
- [x] Update known downstream docs/reports that still pointed at `Job 0029`.
- [ ] Sweep for any newly discovered `Job 0029` references before future closeout.

### Phase 3 — Observer-dev continuation guidance

- [x] Keep active observer implementation work tied to `Job 0022`, the baseline cutover inventory, and the approved observer execution/report surfaces.
- [ ] Treat `Job 0029` as history only; never use it as a resume prompt, traversal target, or authority citation.
- [ ] Keep the current scope focused on observer development completion and baseline-surface cleanup; do not bundle the deferred `observerctl.py` refactor into this lane.
- [x] Lock the baseline-monitoring implementation choices before code mutation:
  - canonical term: `resource_baseline`
  - owner: `observerctl`-managed monitor process
  - retention: existing `archive/` conventions
  - lockdown defaults: heartbeat `4s`, baseline validation `45s`
- [x] Harden runtime transition ownership for the baseline monitor:
  - `runtime-start` now fails closed when monitor startup is not verified
  - `mode-switch` now fails closed when postflight monitor health is inactive
  - focused observer validation updated to cover these cases
- [x] Strengthen non-activation operator proof surfaces:
  - `ops evidence pack --to <mode>` now supports target-mode readiness projection without activation
  - evidence packets now expose retained readiness surfaces (posture/resource/monitor/stream/window/librarian refs)
  - focused observer validation updated to cover these proof packets
- [x] Map non-activation proof packets to Stage 5 prerequisite classes:
  - explicit packet rows now interpret retained surfaces as `C22`, `C24`, `C25`, monitor-runtime, and overall prerequisite status
  - proof packet is now easier to review as a pre-live decision artifact without activation

### Phase 4 — Baseline implementation follow-through (when approved)

- [x] Rewire `projects/calamum-moltbook-observer/src/observerctl.py` — cutover implemented 2026-03-20.
- [x] Promote the chunked/dynamic baseline path as the operator-facing readiness surface — done.
- [x] Demote the legacy filesystem-hash baseline to explicit integrity/drift handling only — done (explicit `--baseline` arg path preserved).
- [x] Tests verified: 43 passed, no regressions (`test_observerctl.py`, 2026-03-20).
- [ ] Archive generated legacy baseline artifacts listed in `report_tmp/calamum_baseline_cutover_inventory/calamum_baseline_cutover_inventory.md` — pending operator approval.

### Phase 5 — Validation and downstream handoff

- [x] Re-run targeted observer tests — 43 passed 2026-03-20.
- [x] Re-run targeted observer tests after runtime monitor transition hardening — 47 passed 2026-03-22.
- [x] Re-run targeted observer tests after non-activation readiness evidence projection — 48 passed 2026-03-22.
- [x] Refresh assessment memo and checklist with evidence paths and decision notes — done in this pass.
- [ ] Archive legacy runtime audit artifacts (cutover inventory list) once operator approves.
- [ ] Capture final concise handoff note after archive step completes:
  - what changed: `_baseline_status`/`_baseline_check` now route to `chunked_dynamic` catalog by default
  - what remains deferred: legacy artifact archival; `baseline rebaseline` command (design not yet documented)
  - next driver: `CALAMUM_JOB_0027` (Ghost Console) or `CALAMUM_JOB_0019` (SSOT drift)
  - evidence: `test_observerctl.py` 43 passed 2026-03-20

---

## Current authority map

### Active driver

- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.json`
- SSOT task id: `calamum-moltbook-baseline-integration-20260220`

### Archived duplicate surface

- Live tombstone:
  - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223.md`
  - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223.json`
- Archived payload:
  - `quarantine_legacy_archive/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223_archive_20260320.md`
  - `quarantine_legacy_archive/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223_archive_20260320.json`

### Related reference surfaces

- `projects/calamum-moltbook-observer/docs/CALAMUM_CODESENTINEL_JOB_EXECUTION_EXPECTATIONS.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/audits/CURRENT_EVENTS_IMPACT_ASSESSMENT_BASELINE_AND_LIVE_MODE_20260319.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/audits/OBSERVER_INTEGRITY_BASELINE_UPDATE_TASK_ASSESSMENT_20260320.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/standards/OBSERVER_BASELINE_MONITORING_EXECUTION_HANDOFF_20260320.md`
- `projects/calamum-moltbook-observer/docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211.md`
- `report_tmp/calamum_baseline_cutover_inventory/calamum_baseline_cutover_inventory.md`

---

## Notes for downstream us

- The `up_next` bug is currently operational, not conceptual. Treat the snapshot as convenience output only when it conflicts with SSOT task surfaces.
- `Job 0029` should now be treated as a quarantined historical record. If a future agent tries to resurrect it as current authority, this checklist is the correction surface.
- The observer baseline lane still needs implementation work, but the authority confusion has now been flattened into a much cleaner map. A rare paperwork win — we take those.
