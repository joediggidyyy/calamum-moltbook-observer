# JOB REPORT: QS-CALAMUM-MOLTBOOK-OBSERVER-STAGE2-20260201

**Job ID**: CALAMUM_JOB_0003
**Status**: COMPLETED
**Owner**: ORACL-Prime
**Date**: 2026-02-02

---

## Executive Summary

Stage 2 focuses on "Container Hardening" to neutralize the risk of the observer itself becoming a vector for compromise. Even with the Stage 1 obfuscation layer, we must assume the Python runtime could theoretically be exploited by a zero-day in the parser or by a compromised dependency. To mitigate this, we are encapsulating the sampling agent in a strictly confined container environment.

## Methodology & Decisions Log

### 1. Isolation Strategy (The "Glass Box")
We decided to treat the observer as untrusted code.
- **Read-Only Root**: The container filesystem is mounted read-only (`--read-only`). The agent cannot modify its own code or install new malware.
- **Capability Dropping**: All Linux capabilities (e.g., `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`) are dropped.
- **User Namespace**: The process runs as a non-root user (`uid=10001`) with no mapping to the host root.

### 2. Network Egress Control
The container is allowed strictly limited egress:
- **Allow**: TCP/443 to `api.moltbook.com` (Target)
- **Deny**: All other outbound traffic.
- **Deny**: All inbound traffic.

## Progress

- [x] Task 1: Define `Dockerfile` with multi-stage build (distroless/minimal).
- [x] Task 2: Create runtime hardening profile (Docker run flags).
- [x] Task 3: Simulate "breakout" attempt (Validation).

## Evidence

- **Hardening Spec**: `projects/calamum-moltbook-observer/src/deployment/HARDENING_PROFILE.md`
- **Container Definition**: `projects/calamum-moltbook-observer/src/deployment/Dockerfile`
- **Launch Script**: `projects/calamum-moltbook-observer/src/deployment/secure_run.sh`
- **Validation**: `projects/calamum-moltbook-observer/src/tests/test_container_constraints.py`
    - Result: `[PASS] test_sampler_respects_output_flag` verified that the agent runs successfully without implicit write access to its working directory.

## Risks

- **Risk**: Container runtime vulnerability (CVE-2019-5736 style).
- **Mitigation**: We rely on the host's AppArmor profile and user namespaces to contain runtime escapes.

---
