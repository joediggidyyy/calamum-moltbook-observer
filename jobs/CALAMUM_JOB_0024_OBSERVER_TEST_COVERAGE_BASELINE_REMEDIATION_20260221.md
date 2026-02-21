# Job 0024: Observer Test-Coverage Baseline Remediation (Deferred Incident Lane)

> **ID**: CALAMUM_JOB_0024_OBSERVER_TEST_COVERAGE_BASELINE_REMEDIATION_20260221
> **State**: DEFERRED (queued for later session)
> **Owner**: ORACL-Prime
> **Date**: 2026-02-21

## Incident context
Baseline validation identified coverage-risk drift and naming-alignment ambiguity in observer test surfaces.

Evidence references (local, untracked):
- `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_test_coverage/test_presence_baseline_20260221T184324Z.json`
- `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_test_coverage/coverage_baseline_20260221.json`
- `projects/calamum-moltbook-observer/local_untracked/evidence/baseline_test_coverage/coverage_baseline_summary_20260221T184439Z.md`

## Defer reason (explicit)
This lane is intentionally deferred to keep the current session focused on **live collection readiness and execution**. Any work that does not directly accelerate live collection is out-of-scope for today.

## Planned remediation scope (later session)
1. Naming-convention audit for module-to-test mapping in `src/` and `tools/`.
2. Alias-map policy for legacy test names to reduce false-positive drift alerts.
3. Priority test implementation for zero-coverage and low-coverage high-risk files.
4. Ratcheting baseline policy proposal (no regression from baseline; staged increase targets).

## Success criteria (later session)
- Canonical module-test mapping documented and machine-validated.
- Drift audit heuristic updated to use approved aliases.
- Coverage baseline policy checkpoint established and enforced in audit output.
- Incident lane artifacts linked in QuestStack/job report before closure.

## Current session boundary
- Live collection progression remains primary objective.
- Job 0024 remains deferred until explicitly activated in a future session.
