# Design Spec: Calamum Sandbox Ops Widget (Ghost Console) V2

**Date**: 2026-02-03
**Status**: ACTIVE
**Tech Stack**: Python (NiceGUI), Tailwind CSS, Plotly/ECharts

## 1. Overview
A high-fidelity operational dashboard for the Calamum Moltbook Observer container.
**Style**: Digital Brutalism / Ghost Console / Cyberpunk TUI-in-Web.
**Visuals**: Black background, Neon Green/Amber text, thick borders, monospace fonts.

## 2. Visual Language
- **Palette**:
    - Build: `bg-black`
    - Foreground: `text-green-500` (or amber/cyan variants)
    - Accents: `border-2`, `border-green-500`
- **Typography**: Monospace (Courier, Fira Code, or similar system mono).
- **Layout**: Grid-based, heavy borders, visible "structure".

## 3. Capabilities Components

### A. The "Integrity Diamond" (Radar Chart)
- **Tech**: Plotly/ECharts (via NiceGUI).
- **Metrics**: 
    1. Availability (Uptime)
    2. Integrity (File hashes matched)
    3. Capacity (Disk/Mem buffer)
    4. Freshness (Time since last snapshot)
- **Behavior**: Real-time updates via binding loop.

### B. The "Bio-Rhythm" (Time Series)
- **Visual**: Scrolling line chart (ECG style).
- **Data**: CPU/Memory usage of the target container.

### C. Control Deck (Sidebar)
- **Triggers**:
    - `KILL`: Immediate container stop.
    - `RESTART`: Docker restart.
    - `FLUSH`: Clear logs.
- **Style**: Big blocky buttons (`w-full`), hover effects (`hover:bg-green-500 hover:text-black`).

## 4. Architecture
- **Backend**: `src/ops_dashboard.py` runs a FastAPI server (wrapped by NiceGUI).
- **Frontend**: Served automatically by NiceGUI.
- **Docker Interface**: Uses `docker` python SDK to fetch stats and execute commands.
- **Launch Mode**: `ui.run(native=True)` attempts to open a standalone window (via pywebview), failing over to default browser.

## 5. Security & Auditing
- **Names-Only**: The widget displays counts and statuses, never message content.
- **Audit Log**: Every control action is logged to `logs/behavioral/control_surface/CALAMUM_MOLTBOOK_OBSERVER_WIDGET_CONTROL_EVENTS.jsonl`.
