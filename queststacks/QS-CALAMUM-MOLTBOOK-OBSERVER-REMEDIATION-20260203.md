# QuestStack: QS-CALAMUM-MOLTBOOK-OBSERVER-REMEDIATION-20260203

**Title**: Moltbook Observer - Remediation: Planning Artifact Alignment

**Owner**: ORACL-Prime

**Date**: 2026-02-03

**Status**: IN_PROGRESS

---

## Context

Remediation workstream to resolve cross-file drift vectors identified in the official audit report for Calamum Moltbook observer planning artifacts.

Execution is authorized and in-progress under the canonical gated workflow (names-only, fail-closed). Corrective edits are being applied to the target paired artifacts with gate evidence recorded.

Evidence anchors:

- Gate events (canonical): `logs/behavioral/gates/gate_events.jsonl`
- QuestStack log: `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-REMEDIATION-20260203_log.md`
- QuestStack evidence: `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-REMEDIATION-20260203_evidence.jsonl`

---

## Artifacts

- QuestFrame Spec: `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-OBSERVER-REMEDIATION-20260203.json`

Audit inputs / authority:
- Audit report (Markdown): `docs/reports/audit/CALAMUM_MOLTBOOK_OBSERVER_PLANNING_ARTIFACTS_AUDIT_20260203.md`
- Audit report (JSON): `docs/reports/audit/CALAMUM_MOLTBOOK_OBSERVER_PLANNING_ARTIFACTS_AUDIT_20260203.json`

Targets (paired artifacts to align):
- Widget plan (JSON): `projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_OBSERVER_MONITORING_WIDGET_PLAN_20260203.json`
- Widget plan (Markdown): `projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_OBSERVER_MONITORING_WIDGET_PLAN_20260203.md`
- Job 0006 (JSON): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0006_MOLTBOOK_OBSERVER_STAGE1_TO_STAGE3_EXECUTION_PLAN_20260203.json`
- Job 0006 (Markdown): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0006_MOLTBOOK_OBSERVER_STAGE1_TO_STAGE3_EXECUTION_PLAN_20260203.md`

## Remediation checklist scope (from audit)

- R-01 (CRIT) Enforce widget plan task parity (MD mirrors JSON task IDs 1–6)
- R-02 (CRIT) Align Job 0006 status_update.next_action (live run vs doc-only)
- R-03 (CRIT) Fix Job 0006 status_update job.doc filename reference
- R-04 (HIGH) Resolve Job 0006 phase mismatch (JSON vs MD)
- R-05 (HIGH) Add control-surface assumption/risk language to widget plan MD
- R-06 (HIGH) Specify explicit stop-conditions allowlist (job protocol + widget)
- R-07 (HIGH) Define names-only control-event schema + evidence path for widget controls
- R-08 (MED) Normalize evidence references for widget task 1
- R-09 (MED) Remove/formalize placeholders (related_proposals, <PATH_OR_EMPTY>)
- R-10 (MED) Specify acknowledge-alert persistence model
- R-11 (MED) Pin default time windows + sparse-data semantics
- R-12 (MED) Pin Calamum log roots + filename patterns
- R-13 (LOW) Add Stage 4 strategy reconciliation decision point
- R-14 (LOW) Style harmonization pass after substantive fixes

## Job paperwork (autogen)

- Job report: `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVER-REMEDIATION-20260203.md`
\n### Tertiary Audit: MVP Hardening (Executed)\n- **Context**: Added as QF-CALAMUM-OPS-WIDGET-POLISH-20260204 to validate dashboard stability against file locking.\n- **Status**: CLOSED (Verified Stable).\n- **Findings**: 'Blanking' caused by Windows file locking (glob misses + false zero-size reads). Patched with monotonic guards.
