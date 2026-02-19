# QuestStack: QS-CALAMUM-MOLTBOOK-OPS-WIDGET-20260203

> DEPRECATION NOTICE: The terminal TUI plan is deprecated. The Ghost Console is implemented as a browser-rendered ops dashboard (NiceGUI + ECharts) launched via Edge app-mode.

**Title**: Calamum Ops Widget: Ghost Console (Web UI)
**Owner**: ORACL-Prime
**Date**: 2026-02-03
**Status**: OPEN
**Context**: Implementation and hardening of the "Digital Brutalism" ops dashboard for Calamum Observer.

---

## 1. Context & Objectives

**Goal**: Provide a fixed-size, high-fidelity "Digital Brutalism" ops dashboard for monitoring the Calamum Moltbook Observer (names-only telemetry).
**Reference**: [DESIGN_CALAMUM_SANDBOX_OPS_WIDGET.md](../planning/DESIGN_CALAMUM_SANDBOX_OPS_WIDGET.md)

**Key Components**:
1.  **Ghost Console UI**: NiceGUI + ECharts (browser-rendered, Edge app-mode).
2.  **Integrity Diamond**: Radar chart health visualization.
3.  **Control Deck**: Slide-out panel for safe operator interventions via file-based intents.

---

## 2. QuestFrame Sequence

### Phase 1: Foundation (Backend + Layout)
*   **Focus**: Dependencies, app skeleton, fixed-size layout, and clean labels.
*   **Primary artifacts**:
    *   `src/ops_dashboard.py`
    *   `src/ops/telemetry.py`
    *   `launch_ghost_console.ps1`

### Phase 2: The "Live Wire" (Data Connection)
*   **Focus**: Wire charts to real signals (names-only).
*   **Tasks**:
    1.  Implement Integrity Diamond from computed indicators.
    2.  Implement Bio-Rhythm heartbeat and freshness.
    3.  Implement Density Histogram from JSONL metrics (counts only).

### Phase 3: Control Surface (Interaction)
*   **Focus**: Operator controls via file-based intents (fail-closed).
*   **Tasks**:
    1.  Implement kill/isolate/refresh intents as JSON control signals under `logs/control/calamum/`.
    2.  Ensure UI remains non-authoritative (not SSOT) and never fabricates liveness.

---

## 3. Acceptance Criteria

*   [ ] UI launches via `projects/calamum-moltbook-observer/launch_ghost_console.ps1`.
*   [ ] Dashboard renders as a fixed-size canvas (no scrollbars) in Edge app-mode.
*   [ ] "Integrity Diamond", "Bio-Rhythm", and "Density Histogram" render with names-only labels.
*   [ ] Control Deck emits file-based intents (no raw content) and is fail-closed.
