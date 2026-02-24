# Job 0027: Ghost Console Control Deck Redesign

> **ID**: CALAMUM_JOB_0027_GHOST_CONSOLE_CONTROL_DECK_REDESIGN_20260223
> **Task ID (for traversal)**: `calamum-job-0027-ghost-console-control-deck-redesign-20260223`
> **State**: OPEN
> **Status**: open
> **Owner**: ORACL-Prime
> **Date**: 2026-02-23
> **Scope Root**: `projects/calamum-moltbook-observer`

## Objective
Execute a focused UI/UX refactor of the Ghost Console Control Deck so operators can run mode/runtime operations without visual clutter, overflow drift, or redundant controls.

## Policy + awareness alignment (reviewed)
- `.agent_session/policy_snapshot.{json,md}`
- `.agent_session/ops_awareness.{json,md}`
- `operations/checklists/OPENING_CHECKLIST.md`
- `operations/checklists/CLOSING_CHECKLIST.md`
- `operations/checklists/JOBS_EXECUTION_GUIDE_CHECKLIST_20251226.md`

## Gate traversal contract (exclusive)
This job uses only:
- `codesentinel job start calamum-job-0027-ghost-console-control-deck-redesign-20260223`
- `codesentinel job close calamum-job-0027-ghost-console-control-deck-redesign-20260223`

No manual per-job gate traversal commands are required in normal flow; BOD/EOD remain daily standalone operations.

## Systems + documents touched
- `projects/calamum-moltbook-observer/src/ops_dashboard.py`
- `projects/calamum-moltbook-observer/launch_ghost_console.ps1` *(only if launch defaults or deck behavior toggles require parity)*
- `projects/calamum-moltbook-observer/src/tests/test_ops_dashboard.py`
- `projects/calamum-moltbook-observer/docs/reports/operations/*` (validation notes)

## Problem statement
- Control Deck currently carries redundant visible status text and explanatory text that should be tooltip-only.
- Operator request calls for deterministic bin-width steps (2-second increments + OFF) and cleaner button hierarchy near the kill zone.
- Layout should avoid unnecessary scrolling and preserve logo/header visibility under normal viewport conditions.

## Planned implementation
1. Rationalize Control Deck controls and remove redundant/duplicative on-panel status text.
2. Move explanatory copy to hover tooltips where appropriate.
3. Make bin width deterministic: `OFF`, then `2,4,6,8,10,12,14,16,18,20` seconds.
4. Reframe the top button cluster above kill switch into clear primary/secondary intent groups.
5. Validate no regressions in render/update loops (ECharts + polling).

## Acceptance criteria
- No right-drift/overflow regressions introduced.
- Header/logo remains visible and unobstructed.
- Control Deck is functionally scroll-free in standard operator window target.
- Bin-width behavior matches required increments and OFF state.
- Existing mode-switch workflow remains functional (`ops mode switch`).

## Validation plan
- Targeted tests: `projects/calamum-moltbook-observer/src/tests/test_ops_dashboard.py`
- Runtime verification via launcher and snapshot endpoints:
  - `/_ghost_console/snapshot`
  - `/_ghost_console/js_error_tail`
- Gate evidence path: `logs/behavioral/gates/gate_events.jsonl`
- Session close health check: `codesentinel memory health --json`

## Evidence capture
- Job start/close orchestration events (gate JSONL)
- Before/after screenshots or concise operator notes (names-only)
- Any UI diagnostic events (if present) from `ghost_console_js_errors.jsonl`

## Risks and rollback
- Risk: UI layout clamp changes can regress chart mounting positions.
- Rollback: revert control deck CSS/JS deltas in `ops_dashboard.py` and re-run targeted dashboard tests.

## Completion definition
Job is complete when UI cleanup requirements are met, targeted tests pass, gate close succeeds, and final memory health evidence is recorded.
