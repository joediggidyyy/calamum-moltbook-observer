# QuestStack: QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220

**Title**: Calamum baseline integration lane (watchdog-authoritative posture hookup)

**Owner**: ORACL-Prime

**Primary stakeholder**: joediggidyyy

**Date**: 2026-02-20

**Status**: IN_PROGRESS

---

## Context

This lane executes second in order, after local CodeSentinel baseline stabilization. It binds baseline readiness evidence into Calamum observer/Keymaster governance without changing role boundaries.

Authoritative references:

- `projects/calamum-moltbook-observer/docs/plans/CALAMUM_MOLTBOOK_OBSERVER_BASELINE_INTEGRATION_SCAFFOLD_20260220.md`
- `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-KEYMASTER-RETRIEVAL-READINESS-20260219.md`
- `docs/operations/ssot/CIDS_MULTISCOPE_INTEGRITY_GRAPH_STRATEGY_SSOT_20260220.md`

## Scope

1. Consume baseline posture inputs from the CodeSentinel lane.
2. Wire watchdog posture receipt contract for readiness gating.
3. Preserve two-plane model: watchdog control plane, distributed observability plane.
4. Keep failure semantics fail-closed for stale/missing baseline signals.
5. Canonize terminal lane hygiene controls for multi-window sessions (protected registration + fail-closed prune).

## Safety rules

- Names-only evidence everywhere.
- Watchdog remains authorization authority.
- Observability events cannot self-authorize risky action.
- Live Keymaster execution remains blocked until all readiness criteria are satisfied.

---

## Artifact spine

- QuestFrame spec: `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220.json`
- Root job stub: `jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
- Project job doc (Markdown): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.md`
- Project job doc (JSON): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220.json`
- Project canonical report: `projects/calamum-moltbook-observer/docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220.md`
- Root report pointer: `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220.md`
- QuestStack log: `logs/queststack/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220_log.md`
- QuestStack evidence: `logs/queststack/QS-CALAMUM-MOLTBOOK-BASELINE-INTEGRATION-20260220_evidence.jsonl`
- Incident report: `projects/calamum-moltbook-observer/docs/reports/operations/INCIDENT_REPORT_TERMINAL_GUARD_MULTI_WINDOW_CANON_20260220.md`

---

## Acceptance criteria

- Baseline-ready contract is explicitly evaluated before readiness progression.
- Watchdog posture receipt fields are present and evidence-linked.
- Go/no-go logic is fail-closed on baseline stale/failure/timeout states.
- Lane closure records final SessionMemory health and gate evidence pointers.
