# Strategic Analysis: Live Deployment of Calamum Observer (Phase 4 Readiness)

**Date**: 2026-02-02  
**Author**: ORACL-Prime  
**Status**: APPROVED for Immediate Execution  
**Project**: Calamum Moltbook Observer  

---

## 1. Executive Summary

This document mandates the immediate transition of the Calamum Observer from **Stage 3 (Simulation)** to **Stage 4 (Live Data Collection)**. 

### Strategic Justification
The target platform ("Moltbook") exhibits signs of high volatility typical of early-stage or controversial social networks. The risk of platform evaporation (shutdown, seizure, or collapse) creates a high urgency for data preservation. *Historical data* capture is prioritized over perfect feature completeness. **"Smash and Grab"** tactics are authorized under the existing safety constraints.

## 2. Operational Readiness Assessment (ORA)

We have evaluated the system components against the "Safety Onion" architecture required for handling potentially hostile Live Fire data.

| Component | Status | Analysis |
| :--- | :--- | :--- |
| **Safety Core (`obfuscator_lib`)** | :white_check_mark: **PASSED** | Validated in 'Dreaming Mode'. Proven to strip PII/Malware strings before disk write. |
| **Containment (`deployment/`)** | :white_check_mark: **PASSED** | Immutable Container with Read-Only Rootfs prevents persistence of inbound malware. |
| **Governance (`sentinel.py`)** | :white_check_mark: **PASSED** | Fail-Closed Watchdog is active. Tested against synthetic toxic vectors. |
| **Connectivity (`moltbook_client`)** | :warning: **PENDING** | Client is currently a simulation stub. Requires "Hot-Wire" integration to REST API. |

**Verdict**: The system is safe to deploy. The only blocker is the Interface implementation.

## 3. Deployment Protocol (The "Hot-Wire" Plan)

To execute this transition while maintaining academic reproducibility, we will follow this strict sequence:

### Step 1: Interface Activation
The `src/moltbook_client.py` simulation stub must be replaced with a live REST adapter.
*   **Methodology**: Replace random data generation with `requests.get()` calls to the target API endpoints.
*   **Constraint**: The client must strictly strictly adhere to `GET` requests only. No `POST` methods are permitted in the Observer configuration (prevents accidental interaction).

### Step 2: Credential Injection (Air-Gapped)
Real credentials must never be committed to the repository.
*   **Artifact**: Create a local-only `.env` file in `projects/calamum-moltbook-observer/src/`.
*   **Content**: `MOLTBOOK_API_KEY=...`
*   **Validation**: The `.gitignore` ruleset already excludes `.env` files.

### Step 3: Execution (Glass Box)
The system will be launched using the existing Stage 2 containment script.
*   **Command**: `deployment/secure_run.ps1 -Mode live`
*   **Behavior**:
    1.  Container builds from fresh cache.
    2.  Sentinel Watchdog attaches to `stdout`.
    3.  Client utilizes injected credentials to poll feed.
    4.  `obfuscator_lib` sanitizes payloads.
    5.  Sanitized logs are written to host via volume mount.

## 4. Methodological Deviations
*   **From**: Deterministic Synthetic Data (TV-0/1/2/3 mixed probabilistically).
*   **To**: Stochastic Live Data (Unknown distributions).
*   **Impact**: Analysis models (DATA780) must now account for irregular arrival times and potentially unknown vector classes (TV-4?).

## 5. Artifacts & Logging
No changes to the logging schema are required. The *Live* data will flow into the existing `logs/data/calamum/*.jsonl` channels, maintaining compatibility with the analytics pipeline.

---
*Signed by ORACL-Prime, 2026-02-02.*
