# Job: CALAMUM_JOB_0019 - Observer SSOT Status Alignment (Implementation Drift Follow-up)

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Status: `open`
- Owner: `ORACL-Prime`
- Created: `2026-02-19`
- Project: `calamum / moltbook observer`
- Phase: `remediation`
- Priority: `P0`
- Depends on:
  - `CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212`
- Blocks:
  - closure of implementation-drift status mismatch findings in Calamum high-signal surfaces

## Summary

Open a focused remediation lane to reduce SSOT/document status drift surfaced by `audit_implementation_drift.py`, starting with high-signal Calamum artifacts (QuestStack + Job 0018 chain + dashboard-derived mismatches).

## Scope

### In scope

- Align status fields to `operations/tasks.json` for selected Calamum artifacts.
- Re-run implementation drift audit (`--dry-run`, then `--set-baseline`).
- Refresh Jobs dashboard and record reduction evidence.

### Out of scope

- Broad repository-wide status migration in a single pass.
- Any secret handling or runtime behavior changes.

## Acceptance criteria

- [ ] Calamum high-signal status mismatches are reduced vs prior baseline.
- [ ] New dry-run and baseline evidence paths are recorded.
- [ ] Jobs dashboard refreshed after status changes.
- [ ] Follow-up reduction evidence appended to active operation report.

## Evidence pointers

- `projects/calamum-moltbook-observer/local_untracked/audits/implementation_drift/`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/implementation_drift_audit.jsonl`
- `docs/dashboards/room/JOBS_DASHBOARD.md`
