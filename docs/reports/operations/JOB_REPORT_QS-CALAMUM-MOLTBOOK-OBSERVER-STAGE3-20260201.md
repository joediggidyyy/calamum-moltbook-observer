# JOB REPORT: QS-CALAMUM-MOLTBOOK-OBSERVER-STAGE3-20260201

**Job ID**: CALAMUM_JOB_0004
**Status**: COMPLETED
**Owner**: ORACL-Prime
**Date**: 2026-02-02

---

## Executive Summary

Stage 3 ("Passive Canary") establishes a "Targeted Inbound" measuring instrument. Unlike Stage 1 (which samples the public feed), Stage 3 deploys a registered account that *does nothing* (zero posts) but monitors its own notifications. This measures the "background radiation" of the network: how fast do bots/scanners find and target a silent, new account?

## Methodology & Decisions Log

### 1. Zero-Emission Policy
The canary must be scientifically invisible on the feed.
- **Rule**: No posts, replies, or reposts.
- **Validation**: The sampler must effectively "crash" if it attempts to generate an outbound action for the canary user.

### 2. High-Risk Inbound Vectors (DMs)
Direct Messages (DMs) are the highest risk vector for prompt injection because they often bypass standard "public feed" filtering in human minds.
- **Decision**: DMs are treated as "Toxic Waste".
- **Implementation**: The `obfuscator_lib` will be updated to handle `notification` objects. DM content is *never* read; only the metadata (sender hash, timestamp, length) is logged.

## Progress

- [x] Task 1: Update `obfuscator_lib.py` to support `notification` schema.
- [x] Task 2: Update `calamum_sampler.py` to support `--mode=canary`.
- [x] Task 3: Validate "Zero Emission" rule (Simulator assertion).

## Evidence

- **Sampler Code**: `projects/calamum-moltbook-observer/src/calamum_sampler.py`
- **Canary Metrics**: `logs/data/calamum/moltbook_canary_metrics.jsonl`
    - Verified output contains `sender_hash`, `content_length`, `has_link` but **NO raw content**.
    - DM Content: "Hey check this out..." -> Discarded.
    - Link Detection: `has_link: true` preserved for threat metrics.

## Risks

- **Risk**: Canary account gets banned for "bot-like behavior" (lurking).
- **Mitigation**: Low. Lurking is normal. We simply log the ban if it happens.

---
