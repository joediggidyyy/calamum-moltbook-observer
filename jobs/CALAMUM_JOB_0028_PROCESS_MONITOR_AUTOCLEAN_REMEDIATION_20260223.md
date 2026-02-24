# Job 0028: Process Monitor Autoclean Remediation

> **ID**: CALAMUM_JOB_0028_PROCESS_MONITOR_AUTOCLEAN_REMEDIATION_20260223
> **Task ID (for traversal)**: `calamum-job-0028-process-monitor-autoclean-remediation-20260223`
> **State**: OPEN
> **Status**: open
> **Owner**: ORACL-Prime
> **Date**: 2026-02-23
> **Scope Root**: `CodeSentinel-1`

## Objective
Upgrade process monitoring from detection-heavy behavior to safe, deterministic remediation for known orphaned CodeSentinel/Calamum process patterns.

## Policy + awareness alignment (reviewed)
- `.agent_session/policy_snapshot.{json,md}`
- `.agent_session/ops_awareness.{json,md}`
- `operations/checklists/OPENING_CHECKLIST.md`
- `operations/checklists/CLOSING_CHECKLIST.md`
- `operations/checklists/JOBS_EXECUTION_GUIDE_CHECKLIST_20251226.md`

## Gate traversal contract (exclusive)
This job uses only:
- `codesentinel job start calamum-job-0028-process-monitor-autoclean-remediation-20260223`
- `codesentinel job close calamum-job-0028-process-monitor-autoclean-remediation-20260223`

## Systems + documents touched
- `codesentinel/utils/process_monitor.py`
- `codesentinel/cli/process_utils.py`
- `codesentinel/cli/__init__.py` and/or `codesentinel/cli/legacy_cli.py` *(if command surface wiring changes)*
- `tests/*process*` (targeted test additions/updates)
- `docs/operations/runbooks/*` (operator-safe remediation guidance)

## Problem statement
- Current CLI diagnostics can identify orphan candidates but remediation is operator-manual in common flows.
- In-memory tracked PID state is invocation-bound and may not capture cross-invocation residues.
- We need safe cleanup logic that does not kill legitimate host/parent processes.

## Planned implementation
1. Define orphan classification tiers (safe-to-kill vs inspect-only).
2. Add guarded autoclean routine for deterministic, known-safe orphan signatures.
3. Preserve names-only logs and explicit cleanup history records.
4. Add CLI feedback that reports what was remediated vs only detected.
5. Add/extend tests for parent-protection, false-positive prevention, and cleanup event logging.

## Acceptance criteria
- `memory process status` surface reflects remediation outcomes (not detection-only) where applicable.
- Cleanup logic protects expected host parents and active service lineage.
- No uncontrolled force-kill behavior introduced.
- Cleanup events are visible in monitor history and domain activity logs.

## Validation plan
- Targeted process monitor tests and any relevant CLI process command tests.
- Runtime verification using:
  - `codesentinel memory process status`
  - `codesentinel memory process history`
  - `codesentinel memory process anomalies`
- Post-close session health verification:
  - `codesentinel memory health --json`
- Gate evidence path: `logs/behavioral/gates/gate_events.jsonl`

## Evidence capture
- Before/after orphan candidate counts (names-only)
- Cleanup history event samples (timestamps + actions only)
- Test run outputs and pass/fail summary

## Risks and rollback
- Risk: aggressive cleanup policy could terminate valid long-running workflows.
- Mitigation: strict allowlist/denylist + parent protection checks + dry-run option where feasible.
- Rollback: revert cleanup-specific logic while retaining passive detection/reporting.

## Completion definition
Job is complete when process monitor supports safe remediation for targeted orphan classes, tests pass, and close traversal records PASS evidence.
