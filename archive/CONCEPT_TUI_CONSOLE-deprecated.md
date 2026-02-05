# Concept: Calamum "Ghost Console" (TUI)

**Theme**: "Sentinel Hacker / NOC Room"
**Library Stack**: `Textual` (Layout/App) + `Plotext` (Charts)
**Design Philosophy**: "Digital Brutalism" - High information density, low chroma, motion conveys status.

## 1. The "Visual Nuance" Strategy
Instead of reading "Status: OK", the operator *feels* the system state through motion and shape.

### A. The "Bio-Rhythm" (Heartbeat & Latency)
*   **Visual**: A continuous, scrolling ECG-style line graph (using Braille characters via `plotext`).
*   **Nuance**:
    *   **Normal**: Smooth, rhythmic sine wave.
    *   **Lag/Stress**: Jagged, high-frequency spikes.
    *   **Dead**: Flatline.
*   **No Words**: The line *is* the status.

### B. The "Integrity Diamond" (Radar Chart)
*   **Visual**: A 4-axis Radar Chart.
*   **Philosophy**: "Full Shape = Full Health". Any deformation points immediately to the failing subsystem.
*   **Axes**:
    1.  **Top: Availability** (Can we reach the API?)
    2.  **Right: Integrity** (Are payloads valid JSON?)
    3.  **Bottom: Capacity** (CPU/Memory headroom)
    4.  **Left: Freshness** (Time since last successful packet)
*   **Nuance**:
    *   **Perfect**: A large, symmetrical diamond.
    *   **Network Fail**: Top corner collapses.
    *   **Parser Fail**: Right corner collapses.
    *   **Load Spike**: Bottom corner collapses.
*   **Usability**: Operator doesn't read numbers. They just check if the "shield" is holding its shape.

### C. The "Density Histogram" (Collection Volume)
*   **Visual**: A scrolling timeline (sparkline) of vertical bars.
*   **Nuance**:
    *   Height = **Volume** (Items/sec).
    *   Color/Shading = **Type** (e.g., standard vs. high-value).
*   **Why**: Replaces the "Matrix" gimmick with a standard, readable histogram that still looks dense and active. It answers "Are we collecting?" instantly.

## 2. Layout (Mental Mockup)

```text
┌──────────────────────────────────────────────────────────────┐
│  📡 GHOST_CONSOLE v1.0  ::  MODE: [ CANARY ]  ::  [=====]    │ < Battery/Res
├──────────────────────────────┬───────────────────────────────┤
│                              │  LATENCY (ms)                 │
│      (RADAR CHART)           │  ⡀⠄⠂⠁⠁⠂⠄⡀⡀⠄⠂⠁⠁⠂⠄     │ < Smooth Wave
│           CPU                │                               │
│        .   |   .             ├───────────────────────────────┤
│         \  |  /              │  FLOW RATE (msg/s)            │
│  MEM ----(   )---- VOL       │  ⣿⣿⣿⣿⣦⣀⣀                   │ < Sparkline
│         /  |  \              │  ⣿⣿⣿⣿⣿⣿⣿⣄                  │
│        '   |   '             │                               │
│           ERR                │                               │
│                              │                               │
└──────────────────────────────┴───────────────────────────────┘
│ >_ SYSTEM LOG:                                               │
│ 14:00 [INF] Sentinel initialized loop [hash:x89a]            │
│ 14:01 [WRN] Pulse lag detected (+40ms)                       │
└──────────────────────────────────────────────────────────────┘
```

## 3. Libraries & Feasibility

*   **`Textual`**: Handles the layout, keybindings (Kill Switch = Press 'K'), and refresh loop.
*   **`Plotext`**: Renders the Radar Chart and Sine Waves into strings that Textual displays. It uses standard terminal colors and "Braille" unicode (⣿ ⡇ ⠓) to create high-resolution curves in a text grid.

## 4. Why this fits "Sentinel"
It looks like the software an operator in a cyberpunk movie uses to monitor a subnet. It doesn't look like a SaaS web page. It feels raw, connected, and immediate.
