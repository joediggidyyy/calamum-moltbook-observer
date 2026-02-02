# Data Methodology & Simulation Protocols: Calamum Moltbook Observer

**Version**: 1.0.0  
**Date**: 2026-02-02  
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
| **TV-0** | **Benign** | Standard social chatter, weather reports, greetings. | `"Hello world"`, `"Just a normal post"` | Baseline metric calibration. |
| **TV-1** | **Technical** | Valid code blocks, markdown, or technical schematics. | `"```python print('hi')```"` | Verifying false-positive rates for injection detection. |
| **TV-2** | **Hostile (Injection)** | Adversarial prompts targeting LLM ingestion. | `"Ignore previous instructions"`, `"System prompt override"` | validating `obfuscator_lib` content stripping. |
| **TV-3** | **Toxic (Phishing)** | Direct Messages (DMs) containing links or PII requests. | `"Check this link: http://malicious.com"`, `"Send credentials"` | Testing "Toxic Waste" handling in Canary Mode. |

### 2.2. Generator Distribution (Probabilistic mix)
The sampler employs a stochastic generator to mix these vectors, mimicking a hostile environment:
- **Observer Mode (Feed)**: 80% TV-0/1 (Signal), 20% TV-2 (Noise/Attack).
- **Canary Mode (Inbound)**: 50% TV-3 (Toxic), 50% TV-0 (Benign Follows).

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
2.  **Inject**: Providing the flag `--mode canary` switches the Generator to the TV-3 (Toxic) distribution.
3.  **Validate**: Executing `tests/test_container_constraints.py` asserts that the agent cannot write to its own filesystem, validating the "Glass Box" isolation property.

## 5. Defense In Depth (The Safety Onion)

| Layer | Component | Defense Mechanism | Failure Mode |
|-------|-----------|-------------------|--------------|
| **Inner** | `obfuscator_lib.py` | Implementation of `sha256` and content stripping. | Logic Bug / Import Error |
| **Middle** | **Docker Runtime** | Read-Only Rootfs, Dropped Capabilities (`CAP_NET_ADMIN` off), User Namespace (`uid 10001`). | CVE / Breakout |
| **Outer** | `sentinel.py` | Triple-Redundancy Watchdog monitoring logs for keywords. | **Fail-Closed (SIGKILL)** |

---
*Verified by ORACL-Prime on 2026-02-02.*
