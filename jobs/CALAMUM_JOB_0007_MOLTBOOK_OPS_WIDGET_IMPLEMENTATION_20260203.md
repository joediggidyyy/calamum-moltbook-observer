# Calamum Job 0007: Moltbook Ops Widget Implementation

**Quest ID**: QS-CALAMUM-MOLTBOOK-OPS-WIDGET-20260203
**Frame ID**: QF-CALAMUM-MOLTBOOK-OPS-WIDGET-20260203
**Status**: ACTIVE
**Owner**: ORACL-Prime
**Date**: 2026-02-03

## Context
Implementation of the "Ghost Console" ops dashboard for the Calamum Moltbook Observer, providing a "Digital Brutalism" operational interface for monitoring the observer surface.

## Objectives
1. Build an independent GUI (no terminal window) suitable for Windows operator use.
2. Implement 'Integrity Diamond', 'Bio-Rhythm', and 'Density Histogram' charts with hover stats.
3. Establish a fail-closed Control Surface via file-based intents (no raw content).

## Execution Log
- [x] Phase 1: Foundation (Shell & Deps)
- [x] Phase 2: Live Wire (Data)
- [x] Phase 3: Control Surface
- [x] Phase 4: UX polish (fixed-size canvas, hidden scrollbars, readable system log)

## Artifacts
- UI backend: `src/ops_dashboard.py`
- Telemetry: `src/ops/telemetry.py`
- Control surface: `src/ops/controller.py`
- Local demo agent: `src/calamum_observer_agent.py`
- Launcher (Windows): `launch_ghost_console.ps1`
- Design: `planning/DESIGN_GHOST_CONSOLE_V2.md`

## Notes
- The UI is served by NiceGUI and launched using Edge app-mode to avoid native-window dependency issues.
- Density histogram is time-sliced (see `CALAMUM_DENSITY_SLICE_SEC`) to reduce twitchy bar motion.
