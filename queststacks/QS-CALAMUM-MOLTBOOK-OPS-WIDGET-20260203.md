# QuestStack: QS-CALAMUM-MOLTBOOK-OPS-WIDGET-20260203

**Title**: Calamum Ops Widget: Ghost Console (TUI)
**Owner**: ORACL-Prime
**Date**: 2026-02-03
**Status**: DRAFT
**Context**: Implementation of the "Digital Brutalism" TUI console for Calamum Observer.

---

## 1. Context & Objectives

**Goal**: Provide a high-fidelity, "Hacker/Sentinel" aesthetic Terminal User Interface (TUI) for monitoring the Calamum Moltbook Observer.
**Reference**: [DESIGN_CALAMUM_SANDBOX_OPS_WIDGET.md](../planning/DESIGN_CALAMUM_SANDBOX_OPS_WIDGET.md)

**Key Components**:
1.  **Ghost Console**: A `textual` app running in the terminal.
2.  **Integrity Diamond**: `plotext` radar chart for health visualization.
3.  **Control Deck**: Slide-out panel for safe operator interventions (`SIGKILL`, `PAUSE`).

---

## 2. QuestFrame Sequence

### Phase 1: Foundation (The Shell)
*   **Frame**: `QF-CALAMUM-MOLTBOOK-OPS-WIDGET-20260203.json`
*   **Focus**: Dependencies, App Skeleton, and Layout.
*   **Tasks**:
    1.  Install `textual` and `plotext`.
    2.  Create `src/ops_console.py` with the "Ghost Console" layout (Header, Main Grid, Log Footer).
    3.  Implement the static "Integrity Diamond" chart placeholder.

### Phase 2: The "Live Wire" (Data Connection)
*   **Focus**: Wiring charts to real data.
*   **Tasks**:
    1.  Connect `Integrity Diamond` to mocked or real container stats.
    2.  Implement `Bio-Rhythm` scrolling ECG (Heartbeat).
    3.  Implement `Density Histogram` (Collection Volume).

### Phase 3: Control Surface (Interaction)
*   **Focus**: Operator Controls.
*   **Tasks**:
    1.  Implement `Shift+K` (Kill Switch) with confirmation modal.
    2.  Implement `P` (Pause/Resume).
    3.  Implement Slide-Out "Control Deck" Overlay.

---

## 3. Acceptance Criteria

*   [ ] Application launches via `python src/ops_console.py`.
*   [ ] TUI renders correctly in VS Code Integrated Terminal (Dark Mode).
*   [ ] "Integrity Diamond" renders as a diamond shape using Braille characters.
*   [ ] Kill Switch successfully stops the Docker container (simulated or real).
