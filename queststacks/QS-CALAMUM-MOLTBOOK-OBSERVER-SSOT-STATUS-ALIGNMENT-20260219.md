# QuestStack: QS-CALAMUM-MOLTBOOK-OBSERVER-SSOT-STATUS-ALIGNMENT-20260219

**Title**: Calamum Observer SSOT Status Alignment (Implementation Drift Follow-up)

**Owner**: ORACL-Prime

**Date**: 2026-02-19

**Status**: OPEN

---

## Context

This QuestStack tracks targeted status-synchronization remediation for Calamum artifacts flagged by implementation drift auditing.

Scope extension (2026-02-21): the implementation drift audit now includes a `PROJECT_MANIFEST.json` layout contract check (tracked/ignored roots vs tracked tree + ignore-policy minima).

Primary SSOT reference:

- `operations/tasks.json`

Primary audit surface:

- `projects/calamum-moltbook-observer/tools/audit_implementation_drift.py`

---

## Planned sequence

1. Align high-signal Calamum status mismatches (QuestStack + Job 0018 chain).
2. Run drift audit dry-run.
3. Run drift audit baseline (`--set-baseline`).
4. Refresh jobs dashboard and record evidence delta (including manifest-layout findings).

---

## Evidence pointers

- `projects/calamum-moltbook-observer/local_untracked/audits/implementation_drift/`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/implementation_drift_audit.jsonl`
- `docs/dashboards/room/JOBS_DASHBOARD.md`
