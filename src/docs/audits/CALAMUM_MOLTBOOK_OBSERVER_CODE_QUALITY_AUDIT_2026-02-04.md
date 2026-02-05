title: Calamum Moltbook Observer code quality audit
status: open
generated: 2026-02-04
domain_scope: OPS / RUNTIME / GHOST_CONSOLE
classification: internal
operator: ORACL-Prime
repo_root: CodeSentinel-1/
ssot_path: docs/audit/reports/CALAMUM_MOLTBOOK_OBSERVER_CODE_QUALITY_AUDIT_2026-02-04.md
source_paths:
  - projects/calamum-moltbook-observer/src/
  - projects/calamum-moltbook-observer/launch_ghost_console.ps1
template: docs/audit/templates/AUDIT_REPORT_TEMPLATE.md

---

## Migration Ledger

This report is the SSOT audit document.

- Source legacy file (to be migrated section-by-section):
  - `projects/calamum-moltbook-observer/src/docs/audits/calamum_code_quality_audit_2026-02-04.md`
- Transfer rule: move one section at a time; do not bulk copy.

| Legacy section | Transferred? | Notes |
| --- | --- | --- |
| Executive Summary | yes | Transferred 2026-02-05 |
| Orphaned & Duplicated Code | yes | Transferred 2026-02-05 |
| Over-Engineering Analysis | yes | Transferred 2026-02-05 |
| "False Fixes" & Anomalies | yes | Transferred 2026-02-05 |
| Recommendations | yes | Transferred 2026-02-05 |
| Calamum Data Integrity Audit (Addendum) | yes | Transferred 2026-02-05 |
| Launcher Freshness / Dashboard Dev-Gap Diagnostic (Addendum) | yes | Transferred 2026-02-05 |

## Executive Summary

The codebase exhibits symptoms of integration drift: temporary test harnesses (`calamum_observer_agent.py`) have calcified alongside intended production components (`calamum_observer_daemon.py`). This duplication has compelled the `telemetry.py` reader to become increasingly defensive and over-engineered to handle variable file locking behavior on Windows, contributing to "blanking" artifacts observed in the UI.

The `launch_ghost_console.ps1` script has evolved from a simple launcher into a fragile process manager, implementing regex-based process hunting to compensate for the lack of a proper supervisor tree.

## Scope & Constraints

- In-scope: Ghost Console dashboard, telemetry ingestion, launcher process management, and the observer runtime artifact surfaces referenced by the legacy audit.
- Out-of-scope: Any live remediation, refactors, or behavior changes.
- Constraint: Audit-only; no live actions; preserve evidence fidelity.

## Evidence / Inputs

This SSOT report was migrated from a legacy audit document and therefore inherits the legacy document's evidence limits.

- Legacy audit source (migration input):
  - `projects/calamum-moltbook-observer/src/docs/audits/calamum_code_quality_audit_2026-02-04.md`
- Template used for canonical structure:
  - `docs/audit/templates/AUDIT_REPORT_TEMPLATE.md`
- Script evidence referenced by migrated addendum:
  - `semantics_staging/calamum_diag_launcher_gap.py`
- Code + launcher surfaces referenced in migrated content:
  - `projects/calamum-moltbook-observer/launch_ghost_console.ps1`
  - `projects/calamum-moltbook-observer/src/ops_dashboard.py`
  - `projects/calamum-moltbook-observer/src/ops/telemetry.py`

## Findings

### Legacy section transfer: 1. Orphaned & Duplicated Code

**Findings:**
A critical violation of logic separation exists between the "Agent" and "Daemon" scripts.

| Component | Status | Description |
| :--- | :--- | :--- |
| `src/calamum_observer_agent.py` | **Active** | Currently running in the active process list. Generates synthetic data. |
| `src/calamum_observer_daemon.py` | **Orphaned** | The "real" implementation with actual API clients (`moltbook_client`). It is present on disk but unused by the current launcher, creating confusion about which logic creates the `moltbook_canary_metrics.jsonl` artifact. |
| `src/calamum_sampler.py` | **Partial** | Imported by the Daemon for simulation logic, effectively triplicating the data generation definitions across the codebase. |

**Impact:** High. Future maintenance will likely patch `daemon.py` while the system actually runs `agent.py`, leading to "fix not working" scenarios.

### Legacy section transfer: 2. Over-Engineering Analysis

**Findings:**
Complexity has been added to *consumers* to handle simple deficiencies in *producers*.

*   **`src/ops/telemetry.py` (`_JsonlAppendCounter`)**:
  *   **Issue:** Implements a complex chunked binary reader with manual offset management, rotation detection, and now retry loops/persistence logic.
  *   **Critique:** For a local dashboard visualization, this is excessive. The robust "fix" (retrying `open()`) attempts to work around Windows file locking, which is a symptom of the writer keeping the file handle open or the reader being too aggressive. A simple `tail` approach or a database (SQLite) would eliminate this entire class of concurrency errors without 100 lines of custom buffering logic.
  *   **Verdict:** **False Complexity**. The "blanking" charts are a direct result of this complexity failing to gracefully handle standard filesystem behavior.

*   **`launch_ghost_console.ps1` ("Nuclear" Cleanup)**:
  *   **Issue:** The script now contains 60+ lines of regex-based process table analysis (`Get-CimInstance`, `Select-Object`, `Match`) to hunt down "zombie" processes.
  *   **Critique:** This is a "Band-Aid" pattern. The launcher should not need to perform forensic analysis of the OS process table to restart a dashboard. The fact that `Stop-OldGhostConsole` needs to be "NUCLEAR" indicates the application (`ops_dashboard.py`) does not handle shutdown signals (`SIGINT`/`SIGTERM`) cleanly, or that the Edge "App Mode" wrapper is detaching from its parent too easily.
  *   **Verdict:** **Fragile**. Changes to command line arguments or browser versions could break the regex matching, causing future launch loops.

### Legacy section transfer: 3. "False Fixes" & Anomalies

**Findings:**
Recent patches have addressed symptoms rather than root causes.

*   **Telemetry Persistence (`telemetry.py` patch)**:
  *   **Analysis:** The logic `if new_pick is None ... return self._active_jsonl_cache` prevents the *path* from becoming None, but if the file is locked, the read *operation* still returns 0 lines.
  *   **Result:** The UI receives "0 new records" and "0 Total records" (if stat fails), causing the charts to flatline (blank out) because the frontend interprets "no data" as "clear charts". The fix prevents the crash but not the data loss event.

*   **Process Double-Tap (`Stop-OldGhostConsole`)**:
  *   **Analysis:** Using `taskkill /F` after `Stop-Process` acknowledges that the application enters unrecoverable states. While functional, it masks *why* the Python backend hangs (likely a thread deadlock in `ops_dashboard.py` or the `telemetry` polling loop).

Normalization note: The findings above are transferred verbatim from the legacy report. They do not yet include per-finding evidence anchors (timestamps, logs, or captured command output) and therefore remain incomplete for automated validation.

## Completeness Assessment

This section tracks (a) completeness of each legacy section after transfer, and (b) the optimal order to complete sections that are not yet operationally actionable.

| Section (legacy) | Complete? | Missing | Recommended next step | Optimal completion order |
| --- | --- | --- | --- | ---: |
| Executive Summary | partial | Evidence anchors, acceptance criteria | Add citations to concrete evidence sources; add what "done" means for this audit | 7 |
| 1. Orphaned & Duplicated Code | no | Evidence of actual entrypoint(s) used, launcher references, acceptance criteria | Capture evidence: which script(s) the launcher starts, and which are active at runtime; then convert into finding IDs | 3 |
| 2. Over-Engineering Analysis | no | Measurements, repro steps, code anchors, alternatives tradeoffs | Add reproducible steps for the UI "blanking" and cite telemetry reader/writer behavior; tie to specific code paths | 5 |
| 3. "False Fixes" & Anomalies | no | Patch provenance (what changed), concrete failure modes and evidence | Identify the exact behaviors observed (and where), attach evidence (logs / metrics / screenshots optional) and normalize as findings | 6 |
| 4. Recommendations | no | Dependency ordering, per-item acceptance criteria, risk/stop conditions | Convert recommendations into a ranked backlog tied to specific findings and dependencies | 8 |
| Addendum: Calamum Data Integrity Audit | partial | Evidence anchors for artifact table, explicit status, missing/expected paths pinned | Pin concrete artifact roots + expected filenames, cite which files were inspected, and normalize findings (incl. Librarian gap) | 2 |
| Addendum: Launcher Freshness / Dashboard Dev-Gap Diagnostic | partial | Captured script output evidence (PIDs, port owner, timestamps), acceptance criteria for "fresh instance" | Attach the key diagnostic outputs (timestamps, PID/port ownership) and define deterministic freshness criteria | 1 |
| Evidence / Inputs (overall) | no | Consolidated evidence list, timestamps/window | Populate evidence section with file paths, time window, and scripts/tasks used | 4 |

## Remediation Backlog (If Applicable)

### Legacy section transfer: 4. Recommendations

#### Immediate Remediation (Cleanup)
1.  **Decommission `calamum_observer_daemon.py`** or promote it to active status. Do not keep both.
2.  **Simplify Telemetry**: Replace `_JsonlAppendCounter` with a simple "read last N lines" for the dashboard. The integrity exactness required for finance is not required for a "Canary" visualization.
3.  **Fix the Writer**: Ensure `calamum_observer_agent.py` opens, writes, and *closes* the file for every batch (atomic append). This eliminates the need for reader retry loops on Windows.

#### Architectural Correction
1.  **Use a Supervisor**: Instead of a PowerShell loop, use a proper `.pid` file check or a lightweight supervisor that actually owns the child processes.
2.  **Switch IPC**: For local dashboarding, use SQLite (WAL mode) instead of JSONL. WAL mode allows concurrent readers and writers without locking issues, solving the root cause of the UI "blanking".

PENDING (will be generated after findings normalization).

## Addenda

### Addendum - 2026-02-05 - Launcher Freshness / Dashboard Dev-Gap Diagnostic

**Date**: 2026-02-05
**Scope**: Ghost Console launcher behavior + dashboard instance freshness
**Auditor**: ORACL-Prime

#### 1. Scope

This addendum records evidence for a development gap: the Ops Dashboard UI did not reflect recent code changes.

No corrective edits are performed in this addendum.

#### 2. Evidence (script-first)

- Diagnostic script:
  - Path: `semantics_staging/calamum_diag_launcher_gap.py`
  - Purpose: Compare PID-file ownership vs port ownership, and compare process start time vs source `mtime`.

- Primary code + launcher surfaces:
  - `projects/calamum-moltbook-observer/launch_ghost_console.ps1`
  - `projects/calamum-moltbook-observer/src/ops_dashboard.py`

#### 3. Findings

##### F-DEVGAP-001 — Dashboard instance reuse (process start predates source edits)

The running dashboard process start time was observed to be **earlier** than the last modification time of `src/ops_dashboard.py`.

**Impact:** UI-based verification becomes non-authoritative; a “restart” may not actually be a restart.

##### F-DEVGAP-002 — PID file vs port owner mismatch (port 8899)

The dashboard PID recorded by the launcher did not match the process that owned the LISTEN socket on port `8899`.

**Impact:** PID-file lifecycle controls can target the wrong process; stale processes can persist.

##### F-DEVGAP-003 — Split-brain log roots (repo `logs/` vs observer `src/logs/`)

Both of these roots existed simultaneously during the diagnostic:

- Repo root: `logs/`
- Observer-local: `projects/calamum-moltbook-observer/src/logs/`

**Impact:** Operators can read/write/verify against different artifact trees than the running process uses.

##### F-DEVGAP-004 — Potential CLI flag drift (observer agent interval)

The running observer agent command line was observed with `--interval 2.0`.

**Impact:** If the agent CLI expects a different flag name (e.g., `--interval-sec`), cadence can silently fall back to defaults.

#### 4. Safety Posture

Until the launcher guarantees **fresh instance per launch** (or a deterministic “restart-if-stale” policy) and PID/port ownership is reconciled, the Ops Dashboard must be treated as **non-authoritative** for confirming behavior changes.

#### 5. Remediation Options (proposal only)

1. **Fresh-instance guarantee**: Stop prior dashboard instance(s) deterministically before starting a new one, or restart if `ops_dashboard.py` is newer than the process start time.
2. **PID correctness**: Only write PID files after confirming the child process is alive and (for the dashboard) has bound port `8899`.
3. **Log-root SSOT**: Choose and enforce a single log root (with explicit env-var override rules).
4. **CLI flag parity**: Align launcher arguments with the actual agent/librarian CLI parameters.

### Addendum - 2026-02-04 - Calamum Data Integrity Audit

**Date**: 2026-02-04
**Scope**: Generated Runtime Artifacts (v1.1.0)
**Auditor**: ORACL-Prime

#### 1. Process Inventory Rules

| Process | Role | Expected Status | Actual Status | Findings |
| :--- | :--- | :--- | :--- | :--- |
| **Ghost Console** | Visualization | **Active** | **Active** | backend listening on port 8899. |
| **Observer Agent** | Producer | **Active** | **Active (Zombie?)** | `moltbook_canary_metrics.jsonl` is receiving heartbeats, but the dashboard launcher does not explicitly spawn this process. Risk of unmanaged background process. |
| **Librarian** | Consumer | **Active** | **STOPPED** | The `calamum_librarian.py` daemon is NOT included in `launch_ghost_console.ps1`. |

#### 2. Artifact Validation Table

| Artifact | Path | Type | Validation Rules | Result | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Canary Stream** | `moltbook_canary_metrics.jsonl` | JSONL (Append) | 1. Valid JSON<br>2. `node_id` present<br>3. Signed (if non-heartbeat) | **PARTIAL** | File contains `heartbeat_sample` records (valid). No `obfuscated_content` records observed (Blindness). |
| **Rotation Policy**| `rotation_policy.json` | JSON (State) | 1. `max_bytes` defined<br>2. `observed_avg_bytes` updated | **FAIL** | File does not exist. Librarian is not running to generate it. |
| **Archives** | `archive/*.jsonl.gz` | GZip | 1. Valid GZip<br>2. Manifested | **FAIL** | No archives found. Pre-requisite (Librarian) missing. |
| **Legacy Samples** | `moltbook_samples_obfuscated.jsonl`| JSONL | N/A | **N/A** | Legacy artifact not verified in this run. |

#### 3. Data Methodology Validation

The system adheres to the **"Brutalist" Telemetry** principle but fails the **"Self-Correcting"** requirement due to the missing Librarian.

*   **Variable**: `CALAMUM_DATA_SIGNING_KEY`
  *   **Status**: Default Dev Key likely in use (`dev-key-do-not-use-in-prod`).
  *   **Risk**: Low (Local Simulation), High (Production).

*   **Variable**: `CALAMUM_ROTATION_LIMIT` (Implicit)
  *   **Status**: Defaulting to static code constant (50MB) because `rotation_policy.json` is missing.

#### 4. Recommendations

1.  **Integrate Librarian**: Update `launch_ghost_console.ps1` to spawn `calamum_librarian.py` as a background job.
2.  **Explicit Agent Spawn**: The launcher should explicitly start `calamum_observer_agent.py` rather than relying on an external/zombie process.
3.  **Key Injection**: Production deployments must inject `CALAMUM_DATA_SIGNING_KEY`.

Normalization note: This addendum is transferred verbatim from the legacy report and does not yet include a consolidated evidence list (which exact files were inspected, timestamps, and expected artifact roots).

## Appendix: Referenced Artifacts

- Template: `docs/audit/templates/AUDIT_REPORT_TEMPLATE.md`
- Legacy (migration source): `projects/calamum-moltbook-observer/src/docs/audits/calamum_code_quality_audit_2026-02-04.md`
