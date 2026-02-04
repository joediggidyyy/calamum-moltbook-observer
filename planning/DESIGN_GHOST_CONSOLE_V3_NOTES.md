# Ghost Console V3 Notes (Build Targets)

**Date**: 2026-02-03
**Status**: DRAFT / NOTES

This document captures the next (V3) build targets for the Calamum Ghost Console.
It is intentionally implementation-oriented and avoids secrets.

---

## 1) Wire in planned modes (real behavior, not just a label)

Current V2 state:
- UI displays `MODE: [ CANARY ]` with a tooltip listing planned modes.
- Mode is normalized from `CALAMUM_OPS_MODE`.

V3 target:
- Make modes change **what the system does**, not only what it displays.
- Define a single, canonical mode registry and ensure:
  - UI mode label
  - telemetry sampling policy
  - control surface availability
  - log verbosity
  all derive from that registry.

Suggested mode semantics:
- **CANARY**: current safe default; low-volume sampling; conservative controls.
- **PASSIVE_LISTENER**: disable any active triggers; telemetry is read-only.
- **HONEYPOT**: enable higher interaction triggers (guardrails required).
- **REPLAY_SIMULATION**: drive charts/log feed from replayed JSONL windows.
- **CHAOS_MODE**: inject faults/latency to validate watchdog + resilience.

Acceptance criteria:
- Changing `CALAMUM_OPS_MODE` measurably changes sampling/logging behavior.
- Mode-specific controls are enabled/disabled (greyed + tooltip rationale).
- A visible audit line is emitted when mode changes.

---

## 2) Variable / adjustable histogram binning

Current V2 state:
- Density histogram is 12 bins.
- Bars represent time-sliced aggregate counts.
- Slice width is adjustable via `CALAMUM_DENSITY_SLICE_SEC`.

V3 targets:
- Make histogram bin count **configurable** and/or user-adjustable:
  - env var (e.g. `CALAMUM_DENSITY_BINS=12`)
  - optional UI control (guarded; persisted client-side only)

Design considerations:
- If bin count changes, keep ECharts data + axis consistent and stable.
- Ensure dashboard stays fixed-size with no layout drift.
- Tooltips should continue to show raw counts + slice width per bin.

Acceptance criteria:
- Bin count changes without breaking rendering.
- Density aggregation stays performant (no full rescans).
- Existing tests extended to validate both default bins and a non-default bin count.
