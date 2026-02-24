# JOB: Calamum/Moltbook Observer - Active Logging Keepalive + Blind ML Execution

**Job ID**: CALAMUM_JOB_0011_ACTIVE_LOGGING_KEEPALIVE_AND_BLIND_ML_EXECUTION_20260210  
**Date**: 2026-02-10  
**Status**: COMPLETED  
**Owner**: ORACL-Prime  
**Frame**: 0011  

---

## 1. Objectives

Execute two closely related upgrades for the Calamum Moltbook Observer:

1) **Active logging keepalive (stdout/stderr liveness)**
- Make redirected service logs (e.g., `*.stdout.log`) carry *low-rate* liveness signals so operators can confirm health without opening JSONL telemetry.

2) **Blind ML execution plan (DATA780)**
- Convert the existing ML readiness + execution planning artifacts into an executable, reproducible workflow: dataset build, feature windows, splits, evaluation harness, and run-ledger reporting.

This job is intentionally names-only and policy-aligned: no secrets, no internal endpoints, and no raw Moltbook content.

---

## 2. Scope

### 2.1 In-scope components (Calamum stack)

Located under: `projects/calamum-moltbook-observer/src/`

- `calamum_observer_agent.py` (primary collector; writes JSONL telemetry + heartbeat)
- `calamum_librarian.py` (rollups/archival workflows)
- `calamum_watchdog.py` (heartbeat monitoring and alerting)
- `ops_dashboard.py` (Ghost Console NiceGUI dashboard)
- Logging/config helpers:
  - `calamum_config.py` (canonical path routing and env overrides)

### 2.2 In-scope planning + deliverables (DATA780)

Located under:
- `projects/calamum-moltbook-observer/deliverables/DATA780/`
- `projects/calamum-moltbook-observer/planning/`

Key inputs:
- `deliverables/DATA780/ML_READINESS_ASSESSMENT_2026-02-10.md`
- `deliverables/DATA780/MODEL_TRAINING_NARRATIVE_REPORT_STRUCTURE.md`
- `planning/CALAMUM_BLIND_ML_EXECUTION_PLAN_2026-02-10.md`

### 2.3 Explicit out-of-scope

- Any runtime credential material (must remain environment variable managed).
- Any raw Moltbook semantic payload handling (Blind ML is metadata-only).
- Adding new third-party dependencies without explicit approval (see dependency gate below).

---

## 3. Core Directives

1. **No secrets / names-only**: never print or persist credential values; never embed internal endpoints.
2. **Telemetry remains authoritative**: JSONL telemetry + heartbeat are still the ground truth; stdout keepalive is an operator convenience layer.
3. **Rate-limit stdout**: keepalive output must be bounded (default conservative; no tight loops).
4. **UTC correctness**: replace deprecated/ambiguous UTC calls (e.g., `datetime.utcnow()`) with timezone-aware UTC timestamps.
5. **Reproducibility**: ML pipeline must be deterministic enough to reproduce metrics when re-running against the same frozen dataset manifest.
6. **Dependency gate**: ML modeling libraries (e.g., scikit-learn) are not added until explicitly approved by the maintainer (joediggidyyy).

---

## 4. Work Items

### 4.1 Active logging keepalive (stdout)

- Add a small, shared helper for **rate-limited** liveness prints.
- Emit one compact status line per service at a controlled cadence (e.g., every 30-120 seconds), containing only safe values:
  - timestamp_utc
  - service name
  - iteration counters (if available)
  - last heartbeat age seconds (if available)
  - last write path (names-only) and record counts (if cheap)

**Non-goals**:
- Do not print raw telemetry rows.
- Do not tail or print whole log contents.

### 4.2 ML pipeline execution scaffolding (no new deps)

- Establish analysis home (DATA780 expectation): `projects/calamum-moltbook-observer/src/analysis/`.
- Create dataset build workflow that:
  - reads canonical telemetry JSONL inputs (obfuscated samples, canary metrics, heartbeat)
  - builds windowed feature frames
  - writes dataset artifacts with a manifest (hashes, row counts, schema version)
  - creates deterministic splits (train/val/test) and stores split manifest

- Create an evaluation harness that:
  - computes core metrics for baseline heuristics (no third-party deps)
  - stores per-run `run.json` + `run.md` narrative per `MODEL_TRAINING_NARRATIVE_REPORT_STRUCTURE.md`

### 4.3 ML modeling (dependency-gated)

- Upon explicit approval, add scikit-learn to support:
  - supervised baseline (e.g., RandomForestClassifier)
  - unsupervised baseline (e.g., IsolationForest)
- Implement threshold selection targeting the project constraint (e.g., FPR < 1%) and log chosen threshold + resulting metrics.

---

## 5. Acceptance Criteria

### 5.1 Active logging keepalive

- Each long-running Calamum service emits a bounded liveness line to stdout on a rate limit.
- Keepalive can be disabled (default-off or via env), and does not flood logs.
- Any datetime warnings in the keepalive path are resolved using timezone-aware UTC.

### 5.2 ML execution plan

- `src/analysis/` exists and contains a clear entry point and README (names-only).
- Dataset builder produces:
  - dataset file(s)
  - manifest JSON with hashes/counts
  - split manifest
- Evaluation harness produces run artifacts:
  - `run.json` (machine)
  - `run.md` (narrative)

### 5.3 Policy + governance

- No secrets are introduced; evidence remains names-only.
- Gate evidence pointers are updated during execution.
- SessionMemory health check is recorded at closeout.

---

## 6. Evidence Anchors

- Project manifest: `projects/calamum-moltbook-observer/PROJECT_MANIFEST.json`
- SessionMemory snapshots:
  - `.agent_session/policy_snapshot.json`
  - `.agent_session/ops_awareness.json`
- Gate evidence: `logs/behavioral/gates/gate_events.jsonl`

---

## 7. Closure Note

- Closed by operator directive on `2026-02-24T18:09:39Z`.
- Post-mortem gate reruns explicitly waived by operator for this closure.

*Planned by ORACL-Prime.*
