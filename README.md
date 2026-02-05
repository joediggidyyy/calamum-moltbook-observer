# Project: Calamum Moltbook Observer

> **Managed by CodeSentinel** | *Ethical Security Research Initiative*

**Owner**: ORACL-Prime  
**Status**: Active (Stage 3 Executed)  
**Created**: 2026-02-01  
**Last Update**: 2026-02-04 (v1.1.0)

---

## Executive Summary

The **Moltbook Observer** project is a security research initiative designed to measure the density of hostile agent activity on the Moltbook platform. The experiment operates through a series of escalating "Observer Stages," ranging from purely passive sampling (Stage 1) to active honeypots (Stage 4).

**Key Constraint**: The observer must remain invisible and secure. It employs "Obfuscation at the Edge" to ensure no raw content (potential prompt injection vectors or illegal content) ever touches the Observer's disk.

**Architecture v1.1.0**:
-   **Observer Agent**: Lightweight producer that streams obfuscated, signed records to `logs/data`. Rotates files atomically based on policy.
-   **Librarian Daemon**: Background process that compresses active logs, validates integrity, and effectively "trains" the Agent by updating the `rotation_policy.json` based on actual data density.

<p align="center">
  <img src="assets/branding/calamum_logo_color.png" alt="Calamum Logo" width="400">
  <br>
  <em>Secure / In-Memory / Ephemeral</em>
</p>

## Directory Structure

```text
projects/calamum-moltbook-observer/
├── deliverables/       # Academic Artifacts (Report Targets)
│   ├── DATA740/        # Ethics & Governance (Security Focus)
│   └── DATA780/        # ML & Analysis (Research Focus)
├── jobs/               # Job Definitions (The "Why" & "How")
├── planning/           # Experiment Plans & Hypotheses
├── questframes/        # Specs for execution tracking
├── queststacks/        # Logs of execution history
├── src/                # Source Code (The "What")
│   ├── analysis/         # ML Models & Notebooks (Stage 4 Analysis)
│   ├── deployment/       # Dockerfiles & Hardening Profiles (Stage 2)
│   ├── ops/              # Ops/telemetry/control surfaces (Ghost Console V2)
│   ├── tests/            # Validation Scripts
│   ├── calamum_sampler.py # The Agent (Stage 1/3)
│   ├── calamum_observer_agent.py # Local demo agent (heartbeats + JSONL + signal consumer)
│   └── obfuscator_lib.py # Safety Layer (Stage 1/3)
├── launch_ghost_console.ps1 # Ghost Console V2 launcher (Edge app-mode)
└── REFERENCES.md       # Index of detailed artifact links
```

## Experiment Stages

| Stage | Name | Status | Description |
|-------|------|--------|-------------|
| **1** | **Observe & Sample** | **COMPLETE** | Read-only sampling of public feed. Validated `obfuscator_lib` safety. |
| **2** | **Container Hardening** | **COMPLETE** | Deployment of "Glass Box" read-only container environment. |
| **3** | **Passive Canary** | **COMPLETE** | Deployment of silent account to measure inbound "background radiation" (DMs/follows). |
| **4** | **Magnet & Analysis** | *PLANNED* | Active "Blind ML" analysis of obfuscated logs (DATA780). |

## Key Artifacts

### Documentation
- **Master Plan**: [Moltbook Observer Experiment Plan](planning/CALAMUM_MOLTBOOK_OBSERVER_EXPERIMENT_PLAN_20260201.md)
- **Methodology**: [Data Simulation & Logging](DATA_METHODOLOGY.md)
- **Hardening Profile**: [Container Constraints](src/deployment/HARDENING_PROFILE.md)
- **Sentinel**: [Triple-Redundancy Watchdog](src/sentinel.py)

### Academic Deliverables
- **DATA740 (Ethics)**: [Alignment Assessment](deliverables/DATA740/ALIGNMENT_ASSESSMENT.md)
- **DATA780 (ML)**: [Project Proposal](deliverables/DATA780/PROPOSAL_DRAFT.md)

### Evidence (Logs)
- **Stage 1 (Public Sample)**: `logs/data/calamum/moltbook_samples_obfuscated.jsonl`
- **Stage 3 (Canary Metrics)**: `logs/data/calamum/moltbook_canary_metrics.jsonl`

## Visuals

### Operational Radar
<img src="assets/branding/calamum_obs_radar.png" alt="Observer Radar" width="600">

### CLI Dashboard (TUI)
<img src="assets/branding/syslog_scroll.png" alt="CLI Dashboard" width="600">

## Operation Manual

### Launching (Windows Host)
#### A) Ghost Console V2 (Ops Dashboard)
The Ghost Console is a fixed-size, "digital brutalism" ops dashboard (NiceGUI + ECharts) designed to show **names-only** telemetry.

- **Start UI (recommended)**: run `projects/calamum-moltbook-observer/launch_ghost_console.ps1`
	- starts the backend hidden (no terminal window)
	- opens Microsoft Edge in app-mode at **1100×720**

**Dashboard source**: `src/ops_dashboard.py`

#### B) Observer + Watchdog (legacy/manual)
1. **Start Observer**: `./src/deployment/secure_run.ps1`
2. **Start Watchdog**: `python src/sentinel.py`

## Ghost Console V2: Data + Control Contracts

### Telemetry inputs (names-only)
The dashboard reads from:
- **CPU/MEM**: `psutil` (local host)
- **Observer liveness**: heartbeat marker freshness OR recent JSONL activity
- **Watchdog liveness**: watchdog heartbeat marker freshness
- **Records/Density**: append-only JSONL metrics (counts only)

Default locations (repo-root relative):
- `logs/health/calamum_ops_watchdog.heartbeat`
- `logs/health/calamum_observer.heartbeat`
- `logs/data/calamum/*.jsonl` (newest file is treated as active)

### Control surface (file-based intents)
Control Deck actions emit JSON control signals (safe for later container wiring):
- `logs/control/calamum/kill.signal.json`
- `logs/control/calamum/isolate.signal.json`
- `logs/control/calamum/refresh.signal.json`

**Doctrine**:
- The GUI is an interface/exhibition tool. It is not SSOT and no system behavior may depend on it.
- Watchdog is system-level governance and is always-on for the duration of active experimentation (24/7).
- If Watchdog is down, the node must remain isolated/quarantined until Watchdog returns via self-resilience recovery, or (if self-recovery fails) an operator/external agent performs an explicit recovery action.

### Local end-to-end demo agent
For local testing without a live container, `src/calamum_observer_agent.py` can:
- touch heartbeat files
- append JSONL records
- consume/acknowledge control signals

## Environment variables (optional overrides)
- `CALAMUM_OPS_MODE`: dashboard mode label (normalized; defaults to `CANARY`)
- `CALAMUM_FRESHNESS_SEC`: heartbeat freshness threshold (default: `15`)
- `CALAMUM_WATCHDOG_HEARTBEAT_PATH`: path to watchdog heartbeat marker
- `CALAMUM_OBSERVER_HEARTBEAT_PATH`: path to observer heartbeat marker
- `CALAMUM_DATA_DIR`: directory containing JSONL metrics
- `CALAMUM_DENSITY_SLICE_SEC`: histogram time-slice width (default: `15`)
- `CALAMUM_BRAND_THUMB_PATH`, `CALAMUM_BRAND_PANEL_PATH`: optional branding asset overrides

## Academic Reproducibility

This project maintains rigorous separation between:
1.  **Intent** (Jobs/Planning): Why we are doing this.
2.  **Mechanism** (Src): The code executed.
3.  **Observation** (Logs): The raw data (with PII hashed).

See `docs/reports/operations/` for narrative reports on methodology.
