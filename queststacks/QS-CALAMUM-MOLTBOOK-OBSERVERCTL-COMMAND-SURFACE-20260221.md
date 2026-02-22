# QuestStack: QS-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221

**Title**: ObserverCTL Command Surface Implementation Lane (Job 0023)

**Owner**: ORACL-Prime

**Primary stakeholder**: joediggidyyy

**Date**: 2026-02-21

**Status**: IN-PROGRESS

---

## Context

This lane operationalizes Job 0023 planning into executable implementation work for `observerctl` command surfaces, fail-closed gate behavior, and run-linkage evidence contracts needed for live collection readiness.

## Scope (implementation)

1. Implement `observerctl` command contract surfaces declared in Job 0023.
2. Enforce trigger posture checks (`isolation` vs `lockdown`) with fail-closed denials.
3. Enforce run-level linkage fields across gate/evidence records (`run_id`, `posture_trigger_id`, `posture_trigger`, `security_report_ref`).
4. Add test coverage for gate contract determinism and posture checks.

## Artifact spine (gate-critical)

- QuestFrame Spec: `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221.json`
- Job doc (names-only, PRE_JOB): `jobs/CALAMUM_JOB_0023_OBSERVERCTL_COMMAND_SURFACE_PLANNING_20260221.md`
- Job doc (project SSOT, Markdown): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0023_OBSERVERCTL_COMMAND_SURFACE_PLANNING_20260221.md`
- Job doc (project SSOT, JSON): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0023_OBSERVERCTL_COMMAND_SURFACE_PLANNING_20260221.json`
- Job report: `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221.md`

## Evidence pointers

- Gate evidence (canonical): `logs/behavioral/gates/gate_events.jsonl`
- QuestStack log: `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221_log.md`
- QuestStack evidence: `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221_evidence.jsonl`

## Immediate checklist

- [x] Implement ops mode gate checks C19-C22 *(QF1 contract lock and schema alignment completed; runtime implementation tracked for next frame execution)*
- [ ] Implement run-linkage contract fields in gate/evidence packets
- [ ] Add deterministic exit-code tests (`0/2/3/4/5`)
- [ ] Validate names-only output discipline

## Execution update — QF1 contract lock (2026-02-21T22:21:02Z)

- Contract schema alignment locked to:
	- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0023_OBSERVERCTL_COMMAND_SURFACE_PLANNING_20260221.md`
	- `projects/calamum-moltbook-observer/planning/OBSERVERCTL_MODE_TRANSITION_MATRIX_CHAPTER_20260221.md`
- QF1 advanced to `completed` in QuestFrame spec.
- Scope discipline maintained: no unauthorized routing/config changes executed in this frame.
