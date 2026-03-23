# JOB REPORT: QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211

**Job ID**: CALAMUM_JOB_0017  
**Status**: IN-PROGRESS (ops activation pending)  
**Owner**: ORACL-Prime  
**Approver**: joediggidyyy  
**Date**: 2026-02-11

**Format note**: names-only (no secrets; evidence minimized: no raw HTTP bodies or raw Moltbook content).

---

## Executive Summary

This job targets a verified LIVE COLLECTION state for the Calamum Moltbook observer stack. During execution, a minimal observer-agent wiring adjustment was made to align the canonical validation target (`moltbook_live_metrics.jsonl`) with Stage 4 / Job 0017 acceptance checks.

Operational activation (air-gapped env injection + non-CANARY mode flip + alert watcher + diagnostics bundle) remains pending.

### 2026-03-20 integrity baseline engine audit summary

- Introductory summary: a brief non-invasive audit was run against the observer integrity baseline engine to verify path targeting and rebuild behavior before resuming the integrity-baseline/key-retrieval lane.
- Result: the engine logic is operating as designed, but the inherited operator shell was mispointing observerctl through `CALAMUM_LOG_DIR` to `report_tmp/observerctl_contract_probe/logs`, which falsely redirected default baseline checks away from the active Calamum project tree.
- In a clean project-scoped environment, path resolution correctly landed on `projects/calamum-moltbook-observer/logs/{control,data,health}`, the canonical baseline file was found at `logs/control/calamum/observerctl_fs_baseline.json`, and the default check failed for real drift reasons (`59` modified, `17` new) rather than path-resolution failure.
- A non-canonical temporary rebuild was then generated at `report_tmp/observer_baseline_engine_audit/observerctl_fs_baseline.audit.json`; follow-up `baseline status` and `baseline check` returned `decision=go`, confirming the rebuild/check loop works when aimed at the intended project surface.
- Evidence: `report_tmp/observer_baseline_engine_audit/observer_baseline_engine_audit.json`
- Operational implication: before future observer integrity or readiness audits, explicitly clear inherited Calamum path overrides or set `CALAMUM_REPO_ROOT` and `CALAMUM_LOG_DIR` to the active project paths so observerctl does not grade the old contract-probe sandbox by accident.

### 2026-03-19 external impact linkage

- Impact assessment: `projects/calamum-moltbook-observer/docs/reports/operations/audits/CURRENT_EVENTS_IMPACT_ASSESSMENT_BASELINE_AND_LIVE_MODE_20260319.md`
- Interpretation update: current-events review supports continued live-mode preparation but raises the evidence bar for real-mode entry, specifically around operator liability, policy snapshotting, and explicit identity-assurance disclaimers.

### 2026-03-19 historical authorization clarification

- This report records an older live-collection roadmap and implementation delta; it must not be treated as current authorization to advance `source=real`.
- Current execution driver for baseline/readiness planning sits with Job 0022 (`CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220`); Job 0026 remains Stage 5 decision-gate context only, and Job 0029 is archived/non-authoritative.
- Terminology note: interpret legacy “live collection” wording in this report through the current policy distinction of `source=real` plus mode/posture labels `live|honeypot`.

---

## Changes Implemented (names-only)

### Live source selector + canonical live metrics stream

- Local observer agent now supports selecting source `sim` vs `live`.
- When `source=live` and mode is not CANARY, metrics are written to the canonical path:
  - `logs/data/calamum/moltbook_live_metrics.jsonl`

### Import safety for optional UI dependency

- `nicegui` is treated as optional so minimal test environments can import the dashboard module without installing GUI dependencies.

---

## Deviation record (governance)

Job 0017 was initially scoped as ops/config only (no backend source changes). The wiring adjustment is recorded as an explicit implementation delta:

- Commit: `eeba7f35`
- Authoritative machine record: `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.json` (`implementation_delta`)

Approval remains **PENDING** until explicit approver acknowledgment is recorded.

---

## Validation

- Unit tests:
  - `pytest projects/calamum-moltbook-observer/src/tests -q` => pass

Ops validation (acceptance criteria) is not yet satisfied in this report; it requires a live window and air-gapped env injection.

---

## Evidence Pointers

- Job spec (md/json):
  - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.md`
  - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.json`

- QuestStack provenance:
  - `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211.md`
  - `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211_log.md`
  - `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211_evidence.jsonl`

- Canonical gate evidence stream:
  - `logs/behavioral/gates/gate_events.jsonl`

---

*Prepared by ORACL-Prime.*
