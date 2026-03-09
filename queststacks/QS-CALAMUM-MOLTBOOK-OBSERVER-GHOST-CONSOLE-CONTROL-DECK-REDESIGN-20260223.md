# QuestStack: QS-CALAMUM-MOLTBOOK-OBSERVER-GHOST-CONSOLE-CONTROL-DECK-REDESIGN-20260223

**Title**: Ghost Console Control Deck Redesign

**Owner**: ORACL-Prime

**Date**: 2026-02-23

**Status**: 7

---

## Context

Focused UI/UX refactor of the Ghost Console Control Deck in `ops_dashboard.py`.
Operator requirements:
- Deterministic bin-width steps: `OFF`, then `2, 4, 6, 8, 10, 12, 14, 16, 18, 20` seconds
- Remove redundant visible status/explanatory text; move to hover tooltips
- Clear primary/secondary button hierarchy above the kill switch
- Scroll-free Control Deck in standard operator window
- Logo/header visibility unobstructed

Primary SSOT:
- `operations/tasks.json`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0027_GHOST_CONSOLE_CONTROL_DECK_REDESIGN_20260223.md`

---

## Planned sequence

1. Implement bin-width redesign (OFF + 2s increments) and tooltip migration in `ops_dashboard.py`.
2. Reframe top button cluster / kill switch hierarchy.
3. Validate via targeted tests and snapshot endpoints.
4. Run memory health check and close gate.

---

## Evidence pointers

- `logs/behavioral/gates/gate_events.jsonl`
- `projects/calamum-moltbook-observer/src/tests/test_ops_dashboard.py`
- `projects/calamum-moltbook-observer/local_untracked/ghost_console_js_errors.jsonl` *(if present)*

## Job paperwork (autogen)

- QuestFrame spec (QF1/QF2/QF3): `docs/planning/questframes/qs_calamum_moltbook_observer_ghost_console_control_deck_redesign_20260223.json`

- QuestFrame spec: `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-OBSERVER-GHOST-CONSOLE-CONTROL-DECK-REDESIGN-20260223.json`
- Job doc: `jobs/CALAMUM_JOB_0027_GHOST_CONSOLE_CONTROL_DECK_REDESIGN_20260223.md`
- Job report: `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVER-GHOST-CONSOLE-CONTROL-DECK-REDESIGN-20260223.md`

## Metadata

- Updated By: `ORACL-Prime`
- Last Transition (UTC): `2026-03-02T05:47:34.850299Z`
- Status authority: `operations/tasks.json`
- Task ID: `calamum-job-0027-ghost-console-control-deck-redesign-20260223`
- Status: `on-hold`
