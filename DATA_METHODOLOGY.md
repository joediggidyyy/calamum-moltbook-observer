# Data Methodology & Simulation Protocols: Calamum Moltbook Observer

**Version**: 1.1.0  
**Date**: 2026-03-21  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Classification**: PUBLIC / ACADEMIC OPEN  

---

## 1. Abstract

This document articulates the data generation, simulation, and logging methodologies employed in the *Calamum Moltbook Observer* experiment. To ensure ethical compliance and rigorous safety during the "Observer" phase, the system initially operates in a "Dreaming" state—processing strictly typed synthetic data. This approach allows us to validate the efficacy of our **Obfuscation at the Edge** pipeline and our **Triple-Redundancy Safety** architecture before exposing the instrumentation to live, potentially hostile vectors.

## 2. Data Simulation Techniques (The "Dreaming" Engine)

The simulation layer (`MockMoltbookClient`) serves as a deterministic digital twin of the target environment. It generates synthetic artifacts categorized into four distinct Threat Vectors (TVs).

### 2.1. Vector Classification

| ID | Class | Description | Simulation Pattern | Purpose |
|----|-------|-------------|--------------------|---------|
| **TV-0** | **Benign** | Baseline-consistent ordinary activity with structural patterns that remain within expected low-risk bounds. | ordinary posts, routine follows, baseline message timing | Baseline metric calibration. |
| **TV-1** | **Irregular** | Low-concern deviations from baseline, including unusual but non-actionable technical or format-heavy activity. | code-dense but benign posts, atypical markdown bursts, harmless structural outliers | Stress-testing false positives against non-benign-looking but still low-risk activity. |
| **TV-2** | **Suspicious** | Structurally abnormal activity whose timing, density, or interaction profile supports a likely-hostile interpretation. | override-like bursts, unusual link/script concentration, repeated abnormal interaction patterns | Evaluating whether metadata-only features can isolate likely-hostile structure before strongest-risk labeling. |
| **TV-3** | **High-Risk** | Patterns that justify the strongest level of concern under the privacy-preserving labeling policy. | credential-solicitation DM simulations, concentrated malicious-link clusters, severe hostile-contact patterns | Testing highest-risk handling and intervention-grade alerting logic. |

For the current DATA780 midway framing, the primary empirical boundary remains **TV-0 versus TV-3**. **TV-1** and **TV-2** are retained as intermediate categories so the project can represent nuisance structure, ambiguity, and escalation without collapsing every non-benign deviation into the highest-risk class.

### 2.2. Generator Distribution (Probabilistic mix)
The sampler employs a stochastic generator to mix these vectors, mimicking a hostile environment:
- **Observer Mode (Feed)**: 80% TV-0/1 (baseline + low-concern irregular activity), 20% TV-2 (suspicious activity).
- **Canary Mode (Inbound)**: 50% TV-3 (high-risk activity), 50% TV-0 (benign follows).

## 3. Exhaustive Logging Protocol (Trimodal Strategy)

Our logging architecture enforces strict separation of concerns across three distinct channels to prevent semantic contamination.

### Channel A: Scientific Telemetry (The Data)
* **Goal**: Statistical analysis of network density.
* **Storage**: `logs/data/calamum/*.jsonl`
* **Constraint**: **Zero Semantic Leakage**. No raw strings. Strict Schema.
* **Schema**:
    ```json
    {
      "timestamp": "ISO8601",
      "type": "post|dm|follow",
      "author_hash": "sha256(uid)[:16]",  // Longitudinal tracking, irreversible
      "content_length": 142,              // Payload size metric
      "has_code_block": true,             // Feature extraction (Boolean)
      "has_link": false,                  // Feature extraction (Boolean)
      "tags_count": 2                     // Complexity metric
    }
    ```
* **Verification**: Files are machine-parsable JSON Lines. Any deviation triggers a validator failure.

### Channel B: Runtime Diagnostics (The Container)
* **Goal**: Debugging agent liveness, connection states, and crash dumps.
* **Storage**: Docker `stdout`/`stderr` (Ephemeral).
* **Content**:
    - Application state transitions (`Starting...`, `Processed N records`).
    - Python `Traceback` on failure (caught by Sentinel).
* **Privacy**: Credentials are redacted in memory before printing.

### Channel C: Operational Governance (The Sentinel)
* **Goal**: Safety enforcement and "Fail-Closed" auditing.
* **Storage**: Host-side process logs.
* **Mechanism**: The **Sentinel** (`sentinel.py`) operates in "Ring -1" (Host). It attaches to the container stream and patterns-matches for Forbidden Keywords.
    - `Traceback`: Immediate Kill.
    - `Permission denied`: Immediate Kill (Breach attempt).
    - `Leaking`: Immediate Kill (Safety assertion violation).

## 4. Operational Reproducibility

Reproducing the experiment requires no access to the live target, ensuring academic peer review safety.

1.  **Build**: `deployment/secure_run.ps1` builds the immutable container image `calamum-observer:stage2`.
2.  **Inject**: Providing the flag `--mode canary` switches the Generator to the TV-3 (High-Risk) distribution.
3.  **Validate**: Executing `tests/test_container_constraints.py` asserts that the agent cannot write to its own filesystem, validating the "Glass Box" isolation property.

## 5. Defense In Depth (The Safety Onion)

| Layer | Component | Defense Mechanism | Failure Mode |
|-------|-----------|-------------------|--------------|
| **Inner** | `obfuscator_lib.py` | Implementation of `sha256` and content stripping. | Logic Bug / Import Error |
| **Middle** | **Docker Runtime** | Read-Only Rootfs, Dropped Capabilities (`CAP_NET_ADMIN` off), User Namespace (`uid 10001`). | CVE / Breakout |
| **Outer** | `sentinel.py` | Triple-Redundancy Watchdog monitoring logs for keywords. | **Fail-Closed (SIGKILL)** |

---

## 6. Live Collection Methodology (GET-only; names-only)

When the project is transitioned from simulation to live collection, the system must preserve the same safety contract:

- **GET-only** network behavior (no mutation calls)
- **Names-only** persistence (no raw Moltbook content written to disk)
- **Credentials via environment variables** only (presence checks; never commit values)

### 6.1 Source selection

The local observer agent supports selecting a data source:

- `CALAMUM_MOLTBOOK_SOURCE=sim` (default): deterministic synthetic generator
- `CALAMUM_MOLTBOOK_SOURCE=live`: Moltbook API client (requires `MOLTBOOK_API_KEY`)

### 6.2 Canonical output streams

This project has two collection entry points that produce different (but compatible) streams:

1) **Sampler (`calamum_sampler.py`)**
     - Stage 1/2: produces obfuscated sample records at:
         - `logs/data/calamum/moltbook_samples_obfuscated.jsonl`
     - Stage 3: produces inbound-canary metrics at:
         - `logs/data/calamum/moltbook_canary_metrics.jsonl`

2) **Local observer agent (`calamum_observer_agent.py`)**
     - For Stage 4 / Job 0017 live validation (live + non-CANARY), the canonical metrics stream is:
         - `logs/data/calamum/moltbook_live_metrics.jsonl`

This file is the primary “freshness + non-empty” proof used by current ops diagnostics and acceptance checks for the live-collection roadmap.

### 6.3 Rate limiting + empty backoff

To avoid hammering a dead endpoint (or a network-restricted environment), live collection supports:

- `CALAMUM_LIVE_BATCH_LIMIT` (default `50`; clamped): cap feed fetch size
- `CALAMUM_LIVE_EMPTY_BACKOFF_SEC` (default `10`; clamped): sleep/backoff window when a live fetch yields no items

### 6.4 Failure posture

If `CALAMUM_MOLTBOOK_SOURCE=live` is selected but `MOLTBOOK_API_KEY` is absent, the observer must fail closed for live ingest (no crash; no secret prompts) and continue to operate safely in a no-write posture for live items.

---
*Verified by ORACL-Prime on 2026-03-21.*
