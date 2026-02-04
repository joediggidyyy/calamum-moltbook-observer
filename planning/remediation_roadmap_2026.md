# Calamum Observer Remediation Roadmap

**Status:** Draft
**Based on:** [Code Quality Audit 2026-02-04](../audits/calamum_code_quality_audit_2026-02-04.md)
**Target System:** Calamum Observer (Ghost Console)
**Objective:** Eliminate concurrency-induced data loss ("blanking charts"), remove dead code, and stabilize the runtime environment.

---

## Overview

This roadmap enables an incoming engineer or agent to systematically address the fragility issues identified in the recent audit. The core problem is a mismatch between the storage mechanism (locked JSONL files on Windows) and the consumption pattern (high-frequency polling).

## Phase 1: Stabilization & Cleanup (High Priority)

**Goal:** Stop the bleeding. Ensure the current architecture works reliably enough for demo purposes before major refactoring.

### Task 1.1: Eliminate Code Duplication
*   **Action:** Archive and delete `src/calamum_observer_daemon.py`.
*   **Rationale:** It is orphaned code that confuses the development agent. Code archaeology confirms `calamum_observer_agent.py` is the active producer.
*   **Verification:** `grep -r "calamum_observer_daemon" .` returns no hits outside of git history.

### Task 1.2: Implement Atomic Writes
*   **Target:** `src/calamum_observer_agent.py`
*   **Action:** Refactor the main file writing loop.
    *   *Current:* Opens file at start, keeps handle open, flushes occasionally. (Causes locking).
    *   *Required:* context manager pattern (`with open(...) as f:`) for *each* batch write.
*   **Code Snippet Guidance:**
    ```python
    # New Pattern
    with open(self.file_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record) + "\n")
    # File is strictly closed here, releasing the Windows lock.
    ```

### Task 1.3: Simplify Telemetry Reader
*   **Target:** `src/ops/telemetry.py`
*   **Action:** Remove `_JsonlAppendCounter` complexity.
*   **Implementation:** Replace the custom binary reader/seeker with a naive but robust `tail` implementation or a simple full-read (if file size < 10MB).
    *   Remove `seek(0, 2)` logic that is prone to race conditions.
    *   Implement a retry decorator *only* for `PermissionError`, handling the split-second race where the atomic writer closes the file.

---

## Phase 2: Architectural Migration (Medium Priority)

**Goal:** Move to a production-grade local architecture that supports concurrency natively.

### Task 2.1: Migrate to SQLite (WAL Mode)
*   **Rationale:** JSONL on Windows is fundamentally hostile to multi-process read/write. SQLite in Write-Ahead Logging (WAL) mode is designed exactly for this.
*   **Steps:**
    1.  Create `src/storage/db.py` to handle `sqlite3` connection.
    2.  Update `calamum_observer_agent.py` to insert rows instead of writing lines.
    3.  Update `src/ops/telemetry.py` to run `SELECT count(*) FROM metrics...`.
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

1.  **Execute Task 1.1**: Clean the workspace immediately to prevent confusion.
2.  **Execute Task 1.2**: This fixes the "Root Cause" of the file locking.
3.  **Execute Task 1.3**: This removes the "Over-engineered" band-aids.
4.  *Validate stability.* If charts remain stable, Phase 2 can be deferred.

## Acceptance Criteria
*   Ghost Console runs for >1 hour without "blanking" charts.
*   `calamum_observer_daemon.py` does not exist.
*   Launching the console does not trigger 60 lines of PowerShell process analysis.
