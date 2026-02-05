# JOB: Calamum/Moltbook Observer - System Recovery and Stabilization

**Job ID**: CALAMUM_JOB_0009_MOLTBOOK_OBSERVER_RECOVERY_AND_STABILIZATION_20260205  
**Date**: 2026-02-05  
**Status**: OPEN  
**Owner**: ORACL-Prime  
**Frame**: 0009  

---

## 1. Objectives
Restoration of the `calamum-moltbook-observer` system to full operational status following host reboot and "integration drift" incidents. This job enforces a strict "correctness first" policy to eliminate "fix-until-broken" cycles.

### 1.1 Core Directives
1.  **Decommission Orphaned Code**: Eliminate `calamum_observer_daemon.py` references to enforce Single Source of Truth (SSOT).
2.  **Stabilize Telemetry**: Replace complex/fragile buffering logic in `telemetry.py` with simple, robust tailing to fix UI blanking on Windows.
3.  **Restore Pipeline Integrity**:
    *   Integrate `calamum_librarian.py` into the lifecycle (missing rotation policy).
    *   Explicitly spawn `calamum_observer_agent.py` in the launcher.
    *   Protect against "Nuclear" launcher logic (regex fragility).
4.  **UX Enhancements**:
    *   Fix missing data feeds (downstream of telemetry fix).
    *   Implement zebra-striping in Syslog UI for readability.

### 1.2 Inspection Protocol (Per-Frame parameter)
At the end of *each* execution frame, the operator (ORACL) MUST manual inspect:
1.  **Process Tree**: Verify Agent, Librarian, and Dashboard are running.
2.  **Artifacts**: 
    *   `moltbook_canary_metrics.jsonl` (fresh content).
    *   `rotation_policy.json` (exists/updated).
    *   `archive/` (archives present if rotation triggered).
3.  **UI**: Verify "Live Data" feeds are incrementing and Syslog striping is visible.

---

## 2. Execution Plan

### 2.1 Codebase Purification
- [ ] **Check**: Verify absence/removal of `src/calamum_observer_daemon.py`.
- [ ] **Audit**: Scan codebase for imports of `calamum_observer_daemon`.

### 2.2 Telemetry Hardening
- [ ] **Refactor**: Rewrite `src/ops/telemetry.py::_JsonlAppendCounter`.
    -   *Logic*: Use simple file tailing (last N bytes/lines) instead of stateful offset tracking.
    -   *Locking*: Implement robust retry-on-lock for Windows filesystem.
    -   *Goal*: Eliminate "0 records" returns when file is busy.

### 2.3 Librarian Integration
- [ ] **Edit**: Update `src/calamum_librarian.py` if needed (currently seems okay, just needs running).
- [ ] **Edit**: Update `launch_ghost_console.ps1` to spawn `src/calamum_librarian.py`.

### 2.4 Launcher Stabilization
- [ ] **Rewire**: Rewrite `launch_ghost_console.ps1`.
    -   Replace `Get-CimInstance | Match` with explicit PID file management.
    -   Add `Start-Process` for `calamum_observer_agent.py`.
    -   Add `Start-Process` for `calamum_librarian.py`.
    -   Ensure graceful shutdown of child processes.

### 2.5 UX Polish & Enhanced Observability
*Rationale: To support scholarly verification of the experiment, the observer interface must provide granular introspection into the system state, reducing "black box" behavior.*

- [ ] **Librarian Integration (UI)**:
    -   Add **LIB** (Librarian) status badge to the header.
    -   Logic: Monitor `calamum_librarian.heartbeat` via Telemetry.
- [ ] **Data Introspection (Tooltips)**:
    -   **WD/OBS/LIB Indicators**: Hovering reveals detailed entity state (PID, Heartbeat age, Path).
    -   **Clock**: Hovering reveals **Host Uptime** (via `psutil.boot_time()`) or Service Runtime.
    -   **Record Counter**: Hovering reveals breakdown: `Session (Volatile): <N> | Archive (Secured): <M>`.
    -   **Mode Label**: Hovering reveals active parameters (e.g., `Interval: 5s`, `Features: [Canary, Log]`) instead of generic mode definitions.
- [ ] **Syslog "Realism" & Readability**:
    -   **Visual**: Implement CSS zebra-striping (alternating subtle background colors) for the log feed.
    -   **Content**: Inject operational events into the scrolling feed (e.g., "Librarian compressed batch X", "Agent heartbeat acknowledged", "Rotation triggered").
    -   *Methodology*: Telemetry provider will infer these events by monitoring file system state changes.

---

## 3. Verification & Sign-off

### 3.1 Pre-Verification
- [ ] Clear `logs/data/calamum` (optional, to test clean start).
- [ ] Clear `ghost_console.pid`.

### 3.2 Post-Execution Inspection
- [ ] **System Integrity**: All components green in `codesentinel oracall`.
- [ ] **Data Flow**: `moltbook_canary_metrics.jsonl` growing.
- [ ] **UI**: No "blanking" artifacts. Log striping visible.

---

*Verified by ORACL-Prime*
