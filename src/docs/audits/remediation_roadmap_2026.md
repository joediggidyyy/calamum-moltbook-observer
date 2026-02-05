# Calamum Observer Remediation Roadmap (Integrated)

**Status:** REDEFINED
**Date:** 2026-02-04
**Based on:** 
- [Code Quality Audit 2026-02-04](../audits/calamum_code_quality_audit_2026-02-04.md)
- [Job 0008: Data Integrity & Signing](../jobs/CALAMUM_JOB_0008_MOLTBOOK_OBSERVER_DATA_INTEGRITY_REMEDIATION_20260204.md)
**Target System:** Calamum Observer (Ghost Console)
**Objective:** Unified remediation of architectural fragility (file locking) and data integrity (missing signatures/wiring).

---

## Overview

This roadmap supersedes previous drafts. It combines the need for **Atomic Writes** (to fix "blanking charts") with the need for **Data Integrity** (HMAC-SHA256 signing + Real Data Wiring).

**Constraint Checklist**:
- [ ] **Pathing**: All intelligence logs MUST reside in `logs/data/calamum/` (NOT root `logs/data/`).
- [ ] **Signing**: All records MUST be explicitly signed via `obfuscator_lib`.
- [ ] **Concurrency**: File handles MUST NOT be held open; use atomic `with open(...)` append.
- [ ] **Hygiene**: Heartbeats MUST be separated from Data.

---

## Phase 1: Stabilization & Integrity (Immediate)

**Goal:** Restore system trust. Ensure the observer generates valid, signed, atomic records in the correct location, and that the dashboard can read them without crashing.

### Task 1.1: Config & Path Enforcement
*   **Target:** `src/calamum_config.py`, `src/calamum_observer_agent.py`
*   **Action:**
    *   Enforce `get_calamum_data_dir()` returns `.../logs/data/calamum` (or ensure agent appends subdomain).
    *   Ensure strict separation:
        *   **Health**: `logs/health/calamum_observer.heartbeat.jsonl`
        *   **Data**: `logs/data/calamum/moltbook_canary_metrics.jsonl`
*   **Rationale:** `DESIGN_GHOST_CONSOLE_V2.md` specifies `logs/data/calamum`. Deviating breaks telemetry discovery.

### Task 1.2: Agent Logic Upgrade (Atomic + Signed)
*   **Target:** `src/calamum_observer_agent.py`
*   **Action:** Rewrite the main loop.
    1.  **Wiring**: Connect `calamum_sampler` (Sim/Client) -> `obfuscator_lib` -> Writer.
    2.  **Signing**: Implement `Obfuscator.sign_sample(record)` in `src/obfuscator_lib.py`.
    3.  **Atomic Write**:
        ```python
        # CORRECT PATTERN
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(signed_record) + "\n")
        ```
    4.  **Loop**: Remove the "hold handle open" anti-pattern.

### Task 1.3: Telemetry Reader Robustness
*   **Target:** `src/ops/telemetry.py`
*   **Action:** Implement "Brutalist" Record Counting.
    *   **Active Session**: Pure **Byte Estimation** (`file_size / AVG_BYTES`). No physical counting. This makes the UI click-free and fast even with large active files.
    *   **Total History**: Sum of `Active Session` + `Archive Count` (retrieved from a manifest/cache).
    *   **Benefits**: Zero I/O blocking. Occasional count correction (jumping +/- when file rotates and hard count is finalized) is accepted design behavior.

### Task 1.4: Retire Ghost Data
*   **Action:** Archive `logs/data/calamum/moltbook_canary_metrics.jsonl` (containing 50k empty heartbeats) to `.../archive/`.
*   **Status:** *Partially executed via CLI, needs verification.*

### Task 1.5: Active Log Rotation (Adaptive)
*   **Target:** `src/calamum_observer_agent.py` & `src/calamum_config.py`
*   **Action:** Implement "Hot Rotation" with dynamic sizing.
    *   **Base Config**: Start with safe default (e.g. 35MB ≈ 100k @ 350b/rec) in `CALAMUM_LOG_MAX_BYTES`.
    *   **Logic**:
        ```python
        # Agent reads config on every loop or batch
        limit = utils.get_dynamic_rotation_limit() 
        if file_size > limit:
            utils.rotate_file(file_path, archive_dir)
        ```

### Task 1.6: The Librarian (Compression, Manifest & Feedback)
*   **Target:** `src/calamum_librarian.py` (New Component)
*   **Role**: Async background daemon.
*   **Duties**:
    1.  **Compress**: `archive/*.jsonl` -> `.jsonl.gz`.
    2.  **Validate**: Integrity check.
    3.  **Manifest**: Update `archive/manifest.json`.
    4.  **Feedback Loop (New)**: 
        *   Calculate `avg_bytes_per_record` from the just-compressed file.
        *   Derive `new_limit = avg_bytes_per_record * 100_000`.
        *   Write `new_limit` to `logs/control/calamum/rotation_policy.json` (or similar shared config state).
        *   Agent reads this policy to self-correct `MAX_FILE_SIZE`.

---

## Phase 2: Architectural Migration (Medium Priority)

**Goal:** Elimination of file locking via SQLite WAL mode.

### Task 2.1: Migrate to SQLite (WAL Mode)
*   **Rationale:** JSONL on Windows is effectively hostile to high-frequency concurrent read/write.
*   **Steps:**
    1.  Create `src/storage/db.py` (SQLite schema).
    2.  Update Agent to `INSERT`.
    3.  Update Telemetry to `SELECT count(*)`.
*   **Benefit:** Zero locking errors. Charts will never blank out due to "file in use".

### Task 2.2: Standardize Process Management
*   **Target:** `launch_ghost_console.ps1`
*   **Action:** Remove "Nuclear" Regex process hunting.
*   **Implementation:**
    *   Update Python scripts to write a `.pid` file on startup.
    *   Update PowerShell to read `.pid`, check existence, and `kill` by ID only.
    *   Add a standard `SIGTERM` handler in Python to ensure clean shutdown.

---

## Execution Order

1.  **Execute Phase 1**:
    *   Fix `obfuscator_lib.py` (Add Signing).
    *   Refactor `calamum_observer_agent.py` (Atomic Writes + Signing + Correct Paths).
    *   Verify `calamum_config.py` aligns with paths.
    *   Verify `telemetry.py` can read the new output.
2.  **Validate**: Run dashboard + agent.
3.  **Plan Phase 2**: Schedule SQLite migration if file locking remains an issue.

## Acceptance Criteria
*   **Schema**: Records have `signature`, `author_hash`, `content_length`.
*   **Location**: Records appear in `logs/data/calamum/`.
*   **Stability**: Dashboard charts do not "blank" or crash.
*   **Code**: No `while True: f.write(...)` patterns.
