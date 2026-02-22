# QuestStack Log — QS-CALAMUM-MOLTBOOK-OBSERVER-RECOVERY-AND-STABILIZATION-20260205

- Initialized: 2026-02-05T23:01:56.642029Z
- Notes: (names-only)

## Frame 0009-A — Baseline (names-only)

- ts_utc: 2026-02-05T23:02:00Z (job start window)
- task_id: `calamum-moltbook-observer-recovery-and-stabilization-20260205`

### Evidence surfaces (canonical)

- Gate evidence: `logs/behavioral/gates/gate_events.jsonl`
- Job events: `logs/behavioral/jobs/job_events.jsonl`
- QuestStack evidence: `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-RECOVERY-AND-STABILIZATION-20260205_evidence.jsonl`

### Expected processes (declared)

- WD (watchdog supervisor): always-on governance (24/7) during active experimentation
- OBS (observer agent): should be spawned explicitly by launcher
- LIB (librarian): should be spawned explicitly by launcher (rotation policy lifecycle)
- DASH (ghost console backend/UI): interface only; not SSOT

### Current state (to be measured)

- Process tree (script-name match via Win32_Process):
	- `calamum_watchdog.py`: pids observed = `31108`, `23608` (multiple instances)
	- `calamum_librarian.py`: pids observed = `18240`, `29024` (multiple instances)
	- `ops_dashboard.py`: pids observed = `31564`, `29932` (multiple instances)
	- `calamum_observer_agent.py`: pids observed = `24596`, `25568` (multiple instances)
- Log freshness (LastWriteTimeUtc):
	- `logs/calamum_watchdog.stdout.log`: `2026-02-05T21:22:04Z`
	- `logs/calamum_librarian.stdout.log`: `2026-02-05T21:22:04Z`
	- `logs/calamum_dashboard.stdout.log`: `2026-02-05T21:22:06Z`
	- `logs/ghost_console_backend.runtime.jsonl`: `2026-02-05T21:42:29Z`
- Data flow (LastWriteTimeUtc / non-empty check):
	- `logs/data/calamum/moltbook_canary_metrics.jsonl`: non-empty; last write `2026-02-05T23:33:05Z`
	- `logs/data/calamum/moltbook_live_metrics.jsonl`: size `0`; last write `2026-02-03T09:53:53Z`
	- `logs/data/calamum/moltbook_samples_obfuscated.jsonl`: non-empty; last write `2026-02-02T08:49:20Z`
- UI readiness marker:
	- NiceGUI reports ready on `localhost:8899` (additional interfaces redacted in log baseline)
- Risk note:
	- Multiple concurrent instances are present for WD/LIB/DASH/AGENT; launcher stabilization must enforce single-instance semantics and graceful shutdown.

### Next action

- Collect baseline measurements (names-only) from existing logs/heartbeats, then proceed to Job 0009 §2.1 (codebase purification) and §2.2 (telemetry hardening).

### Purification check (daemon SSOT)

- `projects/calamum-moltbook-observer/src/calamum_observer_daemon.py`: not present (expected absence)
- `projects/calamum-moltbook-observer/src/simulation/calamum_observer_daemon.py`: present (simulation/legacy surface)
- Imports: no `import calamum_observer_daemon` / `from calamum_observer_daemon ...` found in repo Python sources

## Frame 0009-B — Telemetry + launcher hardening (names-only)

- ts_utc: 2026-02-06T00:54:10Z
- scope:
	- Codebase purification follow-up: remove misleading references to `src/calamum_observer_daemon.py` in audit/planning artifacts; align to legacy `src/simulation/calamum_observer_daemon.py`.
	- Telemetry hardening: refactor `_JsonlAppendCounter` to tail-sampling (no offset tracking) with retry + monotonic guard.
	- Launcher stabilization: enforce single-instance semantics (orphan cleanup) + fix agent CLI flag drift (`--interval-sec`).

### Files changed (names-only)

- `projects/calamum-moltbook-observer/src/ops/telemetry.py`
- `projects/calamum-moltbook-observer/launch_ghost_console.ps1`
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0009_MOLTBOOK_OBSERVER_RECOVERY_AND_STABILIZATION_20260205.md`
- `projects/calamum-moltbook-observer/src/docs/audits/CALAMUM_MOLTBOOK_OBSERVER_CODE_QUALITY_AUDIT_2026-02-04.md`
- `docs/audit/reports/CALAMUM_MOLTBOOK_OBSERVER_CODE_QUALITY_AUDIT_2026-02-04.md`
- `projects/calamum-moltbook-observer/queststacks/QS_CALAMUM_REMEDIATION_20260204.json`
- `docs/planning/questframes/qs_calamum_remediation_20260204.json`

### Validation (names-only)

- Unit tests:
	- `pytest projects/calamum-moltbook-observer/src/tests/test_ops_telemetry.py -q` => pass
- PowerShell syntax parse:
	- `launch_ghost_console.ps1` parse => OK

## Frame 0009-C — Dashboard readiness reconciliation (names-only)

- ts_utc: 2026-02-06T01:02:05Z
- scope:
	- Launcher fix: reconcile dashboard pidfile with port-owner BEFORE orphan cleanup; restart dashboard if pidfile exists but port is not LISTENing; allow a single restart attempt if port 8899 does not come online in the initial window.
	- Add a durable PowerShell parser check helper under `semantics_staging/` to avoid quoting/escaping failures during validation.

### Files changed (names-only)

- `projects/calamum-moltbook-observer/launch_ghost_console.ps1`
- `semantics_staging/ps_parse_check_launcher.ps1`

### Validation (names-only)

- PowerShell syntax parse:
	- `launch_ghost_console.ps1` parse => OK
- Runtime verification:
	- Launcher run => SUCCESS; dashboard port-owner reconciliation observed (pidfile != port_owner) and orphan parent process terminated; port 8899 LISTEN confirmed.

## Frame 0009-D — Broad-footprint tests + diagnostics artifacts (names-only)

- ts_utc: 2026-02-06T03:26:39Z
- scope:
	- Add broad-footprint smoke coverage so CI fails when the Ghost Console backend is non-operational (no TCP LISTEN / no HTTP response), even if unit tests pass.
	- Add provenance-grade diagnostic script artifact to capture pidfiles, port listeners/owners, process details, and log tails into a timestamped JSON report.
	- Validate end-to-end: full repository test run + launcher run + short and 10-minute diagnostic watch windows.

### Files added/changed (names-only)

- Diagnostics:
	- `semantics_staging/calamum_diag_ghost_console_health.ps1`
- Broad tests (repo-root suite):
	- `tests/test_calamum_ops_dashboard_smoke.py`
	- `tests/test_calamum_launcher_script_safety.py`
- Dashboard runtime configurability (env-driven port/host):
	- `projects/calamum-moltbook-observer/src/ops_dashboard.py`

### Validation (names-only)

- Full test suite:
	- `python run_tests.py` => 705 passed, 1 skipped
- Launcher runtime:
	- `projects/calamum-moltbook-observer/launch_ghost_console.ps1` => SUCCESS (dashboard pidfile vs port-owner reconciliation observed; orphan parent dashboard process terminated; OPERATIONAL reported)
- Diagnostic reports written (JSON artifacts):
	- `report_tmp/calamum_diag_ghost_console_health_20260206T020029Z.json` (30s window)
	- `report_tmp/calamum_diag_ghost_console_health_20260206T024902Z.json` (600s window)

### Test determinism note (names-only)

- NiceGUI under pytest may require `NICEGUI_SCREEN_TEST_PORT` for deterministic bind behavior; smoke coverage sets this explicitly.
