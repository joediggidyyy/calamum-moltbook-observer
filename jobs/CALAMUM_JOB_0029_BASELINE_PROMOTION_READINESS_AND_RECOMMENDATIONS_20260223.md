# Job 0029: Baseline Promotion Readiness and Recommendations

> **ID**: CALAMUM_JOB_0029_BASELINE_PROMOTION_READINESS_AND_RECOMMENDATIONS_20260223
> **Task ID (for traversal)**: `calamum-job-0029-baseline-promotion-readiness-and-recommendations-20260223`
> **State**: OPEN
> **Status**: open
> **Owner**: ORACL-Prime
> **Date**: 2026-02-23
> **Scope Root**: `projects/calamum-moltbook-observer`

## Objective
Formalize baseline readiness posture for real/canary collection and convert analysis outputs into operator-ready recommendation profiles (rehearsal vs promotion).

## Policy + awareness alignment (reviewed)
- `.agent_session/policy_snapshot.{json,md}`
- `.agent_session/ops_awareness.{json,md}`
- `operations/checklists/CALAMUM_MOLTBOOK_OBSERVER_LIVE_COLLECTION_SECURITY_PREFLIGHT.md`
- `operations/checklists/OPENING_CHECKLIST.md`
- `operations/checklists/CLOSING_CHECKLIST.md`

## Gate traversal contract (exclusive)
This job uses only:
- `codesentinel job start calamum-job-0029-baseline-promotion-readiness-and-recommendations-20260223`
- `codesentinel job close calamum-job-0029-baseline-promotion-readiness-and-recommendations-20260223`

## Systems + documents touched
- `projects/calamum-moltbook-observer/src/observerctl.py` (baseline analyze / overnight planning / profile wiring)
- `projects/calamum-moltbook-observer/src/tests/test_observerctl.py`
- `projects/calamum-moltbook-observer/docs/reports/operations/*baseline*`
- Optional policy/runbook updates under `operations/checklists/` if promotion criteria are clarified.

## Problem statement
- Strict baseline thresholds currently fail in short windows despite successful relaxed profile checks.
- Operators need deterministic recommendation paths for:
  - immediate rehearsal readiness,
  - overnight strict promotion readiness,
  - explicit NO-GO reasons when windows are incomplete.

## Planned implementation
1. Codify profile semantics (`rehearsal`, `promotion`) and decision criteria.
2. Ensure observerctl outputs provide clear reason codes for baseline NO-GO conditions.
3. Publish recommendation flow for collection schedule selection (rapid/normal phases).
4. Add/update tests to lock profile behavior and expected decisions.
5. Update reports/runbook pointers for operator handoff.

## Acceptance criteria
- Baseline guidance is deterministic and reproducible from CLI outputs.
- Rehearsal profile can produce immediate actionable guidance without weakening promotion policy.
- Promotion profile preserves strict threshold enforcement and clear evidence requirements.
- Recommendation docs are names-only and policy-compliant.

## Validation plan
- Targeted observerctl baseline test coverage.
- Runtime checks using baseline status/analyze/overnight-plan command surface.
- Evidence path checks:
  - `projects/calamum-moltbook-observer/logs/data/calamum/observer_derived/*/resource/index.jsonl`
  - `logs/behavioral/gates/gate_events.jsonl`
- Final health confirmation: `codesentinel memory health --json`

## Evidence capture
- Baseline decision packets (strict and relaxed profiles)
- Overnight projection packet with expected sample counts
- Final recommendation summary tied to GO/NO-GO policy posture

## Risks and rollback
- Risk: over-fitting profile defaults to one host/runtime pattern.
- Mitigation: keep thresholds explicit and configurable; log assumptions in reports.
- Rollback: revert profile wiring while preserving current baseline command behavior.

## Completion definition
Job is complete when baseline recommendation profiles are documented and validated with tests/evidence, and close traversal succeeds with health+gate artifacts.
