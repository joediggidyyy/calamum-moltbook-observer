# Design Spec: Calamum Sandbox Ops Widget (Ghost Console) V2

**Date**: 2026-02-03
**Status**: ACTIVE
**Tech Stack**: Python (NiceGUI), Tailwind CSS, ECharts

## 1. Overview
A high-fidelity operational dashboard for the Calamum Moltbook Observer container.
**Style**: Digital Brutalism / Ghost Console / Cyberpunk TUI-in-Web.
**Visuals**: Black background, Neon Green/Amber text, thick borders, monospace fonts.

**Doctrine**:
- The GUI is an interface/exhibition tool. It is not SSOT and no system behavior may depend on it.
- Watchdog is system-level governance and is always-on for the duration of active experimentation (24/7).

## 2. Visual Language
- **Palette**:
    - Build: `bg-black`
    - Foreground: `text-green-500` (or amber/cyan variants)
    - Accents: `border-2`, `border-green-500`
- **Typography**: Monospace (Courier, Fira Code, or similar system mono).
- **Layout**: Grid-based, heavy borders, visible "structure".

## 3. Capabilities Components

### A. The "Integrity Diamond" (Radar Chart)
- **Tech**: ECharts (via NiceGUI).
- **Metrics**: 
    1. Availability (Uptime)
    2. Integrity (File hashes matched)
    3. Capacity (Disk/Mem buffer)
    4. Freshness (Time since last snapshot)
- **Behavior**:
    - Real-time updates (2Hz)
    - Hover tooltips show exact values
    - Hover-reveal numbers on the four label strip

### B. The "Bio-Rhythm" (Time Series)
- **Visual**: Scrolling line chart (ECG style).
- **Data**: CPU/Memory usage of the host (psutil).
- **Behavior**: Hover tooltips show exact CPU% and MEM%.

### C. Control Deck (Sidebar)
- **Triggers**:
    - `KILL`: Immediate container stop.
    - `ISOLATE`: Stage an ingress isolation intent.
    - `REFRESH`: Operator-initiated supervisory action (fallback).
        - Primary behavior is Watchdog self-resilience and recovery.
        - If Watchdog self-recovery fails and Watchdog is down: an explicit operator recovery action may attempt to relaunch Watchdog.
        - If Watchdog is up: Watchdog orchestrates any safe refresh/reload actions for the stack.
- **Style**: Big blocky buttons (`w-full`), hover effects (`hover:bg-green-500 hover:text-black`).

### D. Density Histogram
- **Meaning**: relative collection volume across the last 12 time slices.
- **Behavior**:
    - Time-sliced aggregation (defaults to 15s slices) to reduce twitchy bars.
    - Hover tooltip shows raw counts and slice width (e.g., "12 rec / 15s").
    - Bin width is a UI-only view control (pending wiring).

## 4. Architecture
- **Backend**: `src/ops_dashboard.py` runs the NiceGUI server.
- **Frontend**: Served automatically by NiceGUI.
- **Telemetry**: `src/ops/telemetry.py` (psutil + heartbeat freshness + JSONL append counting).
- **Control surface**: `src/ops/controller.py` emits file-based intents under `logs/control/calamum/`.
- **Demo agent**: `src/calamum_observer_agent.py` can generate heartbeats/JSONL and consume signals for end-to-end testing.
- **Launch Mode**: Windows uses Edge app-mode via `launch_ghost_console.ps1` to avoid native-window dependencies.
    - Backend starts hidden
    - Window size is fixed at 1100×720

## 5. Security & Auditing
- **Names-Only**: The widget displays counts and statuses, never message content.
- **Audit Log (Control Intents)**: File-based control intents are written to `logs/control/calamum/*.signal.json`.

## 6. Configuration (Environment Variables)
- `CALAMUM_FRESHNESS_SEC` (default: 15)
- `CALAMUM_DATA_DIR` (default: `logs/data/calamum`)
- `CALAMUM_DENSITY_SLICE_SEC` (default: 15)
- Heartbeat paths:
    - `CALAMUM_WATCHDOG_HEARTBEAT_PATH`
    - `CALAMUM_OBSERVER_HEARTBEAT_PATH`
