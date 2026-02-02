# Project: Calamum Moltbook Observer

**Owner**: ORACL-Prime  
**Status**: Active (Stage 3 Executed)  
**Created**: 2026-02-01  
**Last Update**: 2026-02-02

---

## Executive Summary

The **Moltbook Observer** project is a security research initiative designed to measure the density of hostile agent activity on the Moltbook platform. The experiment operates through a series of escalating "Observer Stages," ranging from purely passive sampling (Stage 1) to active honeypots (Stage 4).

**Key Constraint**: The observer must remain invisible and secure. It employs "Obfuscation at the Edge" to ensure no raw content (potential prompt injection vectors or illegal content) ever touches the Observer's disk.

## Directory Structure

```text
projects/calamum-moltbook-observer/
├── jobs/           # Job Definitions (The "Why" & "How")
├── planning/       # Experiment Plans & Hypotheses
├── questframes/    # Specs for execution tracking
├── queststacks/    # Logs of execution history
├── src/            # Source Code (The "What")
│   ├── deployment/       # Dockerfiles & Hardening Profiles (Stage 2)
│   ├── tests/            # Validation Scripts
│   ├── calamum_sampler.py # The Agent (Stage 1/3)
│   └── obfuscator_lib.py # Safety Layer (Stage 1/3)
└── REFERENCES.md   # Index of detailed artifact links
```

## Experiment Stages

| Stage | Name | Status | Description |
|-------|------|--------|-------------|
| **1** | **Observe & Sample** | **COMPLETE** | Read-only sampling of public feed. Validated `obfuscator_lib` safety. |
| **2** | **Container Hardening** | **COMPLETE** | Deployment of "Glass Box" read-only container environment. |
| **3** | **Passive Canary** | **COMPLETE** | Deployment of silent account to measure inbound "background radiation" (DMs/follows). |
| **4** | Active Magnet | *BLOCKED* | Active posting to attract attention (Requires Policy Exception). |

## Key Artifacts

### Documentation
- **Master Plan**: [Moltbook Observer Experiment Plan](planning/CALAMUM_MOLTBOOK_OBSERVER_EXPERIMENT_PLAN_20260201.md)
- **Hardening Profile**: [Container Constraints](src/deployment/HARDENING_PROFILE.md)

### Evidence (Logs)
- **Stage 1 (Public Sample)**: `logs/data/calamum/moltbook_samples_obfuscated.jsonl`
- **Stage 3 (Canary Metrics)**: `logs/data/calamum/moltbook_canary_metrics.jsonl`

## Academic Reproducibility

This project maintains rigorous separation between:
1.  **Intent** (Jobs/Planning): Why we are doing this.
2.  **Mechanism** (Src): The code executed.
3.  **Observation** (Logs): The raw data (with PII hashed).

See `docs/reports/operations/` for narrative reports on methodology.
