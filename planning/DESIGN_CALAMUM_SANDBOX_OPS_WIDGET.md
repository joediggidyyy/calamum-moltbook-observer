# Design Proposal: Calamum Sandbox Ops Widget

**Date**: 2026-02-03
**Status**: DRAFT
**Based on Plan**: `CALAMUM_MOLTBOOK_OBSERVER_MONITORING_WIDGET_PLAN_20260203`

## 1. Overview

This document outlines the design for the **Calamum Sandbox Ops Widget**, a dashboard component designed to provide real-time visibility and operational control over the Calamum Moltbook Observer and its Sentinel watchdog.

As the Observer operates in a simulated "Sandbox" environment (initially aiming for air-gapped stability before live deployment), this widget serves as the primary interface for the operator to verify health without inspecting raw data.

**Future Mode Capabilities**:
To support evolving operational requirements, the UI layout should anticipate switching between:
- `CANARY` (Current): Test flight, limited sampling.
- `HONEYPOT`: High-interaction mode for attracting adverse actors.
- `PASSIVE_LISTENER`: Silent recording of traffic without active probing.
- `REPLAY_SIMULATION`: Re-running captured traffic for regression testing.
- `CHAOS_MODE`: Intentionally introducing faults to test Sentinel resilience.

## 2. Goals

1.  **Observability**: Provide "at-a-glance" status through shape and motion (Digital Brutalism).
2.  **Safety**: Ensure NO raw content is ever displayed; data is visualized abstractly.
3.  **Control**: Provide a "Control Surface" for safe, audited operator interventions via keyboard shortcuts.
4.  **Experience**: Implement a specialized TUI (Terminal User Interface) matching the "Sentinel/Hacker" aesthetic.

## 3. Visual Design: The "Ghost Console" (TUI)

The UI will be a Terminal App (Textual) featuring high-contrast data visualization.

**Layout Concept**:

```text
┌──────────────────────────────────────────────────────────────┐
│  📡 CALAMUM_OPS v1.0    ::  MODE: [ CANARY ]  ::  [=====]    │
├──────────────────────────────┬───────────────────────────────┤
│                              │  BIO-RHYTHM (Heartbeat/Lag)   │
│      INTEGRITY DIAMOND       │  ⡀⠄⠂⠁⠁⠂⠄⡀⡀⠄⠂⠁⠁⠂⠄     │
│       (Radar Chart)          │       (Smooth = Good)         │
│                              ├───────────────────────────────┤
│    [Availability] ^          │  DENSITY HISTOGRAM (Vol/Type) │
│                   |          │  ⣿⣿⣿⣿⣦⣀⣀                   │
│   [Freshness] <---+---> [Int]│  ⣿⣿⣿⣿⣿⣿⣿⣄                  │
│                   |          │  (Height = Vol, Color = Type) │
│               [Capacity]     │                               │
└──────────────────────────────┴───────────────────────────────┘
│ >_ SYSTEM LOG:                                    [CTRL] >   │
│ 14:00 [INF] Sentinel initialized loop [hash:x89a]            │
│ 14:01 [WRN] Pulse lag detected (+40ms)                       │
└──────────────────────────────────────────────────────────────┘
```

**Visual Nuance Strategy**:
1.  **Integrity Diamond**: A 4-axis radar chart using `plotext`.
    *   **Axes**: Availability (Top), Integrity (Right), Capacity (Bottom), Freshness (Left).
    *   **Logic**: "Full Shape = Full Health". Any deformation points to the specific failure domain.
2.  **Bio-Rhythm**: A scrolling sine-wave representing heartbeat/latency. Jagged = Stress.
3.  **Density Histogram**: Sparkline bars showing collection volume without "Matrix" clichés.

## 4. Architecture

### 4.1 Data Sources
- **Telemetry Logs**: `logs/data/calamum/moltbook_live_metrics.jsonl` (Counts)
- **Heartbeat Files**: `projects/calamum-moltbook-observer/src/.heartbeat` (Timestamp)
- **Docker Status**: `docker ps` (Container State) via local process check.

### 4.2 Application Component
A dedicated Python TUI application `projects/calamum-moltbook-observer/src/ops_console.py`:
-   **Library**: `Textual` (App framework), `Plotext` (Terminal charting).
-   **Refresh Rate**: 1Hz (Real-time feel).
-   **Snapshotter**: Optionally exports a static frame to `docs/dashboards/room/CALAMUM_OPS_WIDGET.md` for backward compatibility.

### 5. Control Surface Implementation

Controls are available via keyboard shortcuts OR a slide-out "Control Deck" panel.

#### 5.1 Slide-Out Control Deck
*   **Trigger**: Click `[CTRL] >` or press `Space`.
*   **Behavior**: A modal panel slides in from the right, overlaying the logs.
*   **Elements**: Large, clickable ASCII buttons with status indicators.

```text
┌──────────────┐
│ CONTROL DECK │
├──────────────┤
│ [ 🛑 KILL  ] │ <- (Red w/ Confirmation)
│              │
│ [ ⏸️ PAUSE ] │ <- (Toggles to ▶️ RESUME)
│              │
│ [ 🔄 ROTATE] │
└──────────────┘
```

#### 5.2 Interaction Map

| Control | Key | Button Label | Implementation |
| :--- | :--- | :--- | :--- |
| **KILL SWITCH** | `Shift+K` | `[SIGKILL]` | `python src/ops/kill_switch.py` |
| **PAUSE/RESUME**| `P` | `[PAUSE]` | Touch/Rm `src/.pause_signal` |
| **ROTATE LOGS** | `R` | `[ROTATE]` | Triggers log rotation script. |
| **TOGGLE DECK** | `Space` | `[CTRL] >` | Opens/Closes Control Deck. |

## 6. Security & Auditing

- **Names-Only**: The widget displays counts and statuses, never message content.
- **Audit Log**: Every control action is logged to `logs/behavioral/control_surface/CALAMUM_MOLTBOOK_OBSERVER_WIDGET_CONTROL_EVENTS.jsonl`.
- **Fail-Closed**: If the telemetry file is corrupted or the Docker daemon is unreachable (as seen in recent outages), the widget reports `CRITICAL / UNKNOWN` and defaults to an alert state.

## 7. Next Steps

1.  Create `src/dashboard_writer.py`.
2.  Register the writer in the CodeSentinel dashboard loop.
3.  Implement the `kill_switch.py` script.
