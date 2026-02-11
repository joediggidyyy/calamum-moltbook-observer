# Job 0008: Calamum Data Integrity & Signing Remediation

**ID**: `CALAMUM_JOB_0008`  
**Status**: `pending`  
**Date**: 2026-02-04  
**Driver**: `joediggidyyy` (Agent: `ORACL-Prime`)  

## Overview
This job addresses the "Ghost Data" anomaly discovered during the 2026-02-04 audit. It transitions the Calamum Observer from a placeholder simulation loop to an active, signed intelligence gathering system.

## Objectives
1.  **Retire Ghost Data**: Archive the existing 50k "heartbeat" records.
2.  **Integrity**: Implement HMAC-SHA256 signing for all data records.
3.  **Operation**: Wire `calamum_sampler.py` into `calamum_observer_agent.py`.
4.  **Clarity**: Separate Health (Heartbeats) from Intelligence (Data).

## Task List

### 1. Archive Ghost Data
- [ ] Stop any running agents.
- [ ] Move `projects/calamum-moltbook-observer/src/logs/data/calamum/moltbook_canary_metrics.jsonl` to `.../archive/ghost_data_20260204.jsonl`.
- [ ] Verify `logs/data/calamum/` is clean.

### 2. Implement Data Signing in `obfuscator_lib.py`
- [ ] Add `DATA_SIGNING_KEY` handling (env var).
- [ ] Implement `sign_record(record, secret)` -> `record_with_signature`.
- [ ] Ensure non-repudiation of field content.

### 3. Upgrade Agent Logic (`calamum_observer_agent.py`)
- [ ] Import `calamum_sampler`, `obfuscator_lib`, `moltbook_client`.
- [ ] Replace `while True:` heartbeat loop with `sampler.get_feed()` iteration.
- [ ] Apply obfuscation + signing to every record.
- [ ] Write to `moltbook_canary_metrics.jsonl`.

### 4. Separate Health Streams
- [ ] Ensure heartbeats are written to `logs/health/` or treated as ephemeral status updates (metadate-only log).
- [ ] Stop mixing `kind: heartbeat_sample` into the main intelligence file.

### 5. Verification
- [ ] Execute `calamum_observer_agent.py`.
- [ ] Inspect output JSONL: must have `signature`, `author_hash`, variable `content_length`.
- [ ] Check Ops Dashboard: "Records" count should start at 0 and increment slowly (per sample rate).

## Artifacts
- **Audit**: `docs/reports/audit/CALAMUM_MOLTBOOK_OBSERVER_PLANNING_ARTIFACTS_AUDIT_20260203.md` (Addendum)
- **Job JSON**: `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0008_MOLTBOOK_OBSERVER_DATA_INTEGRITY_REMEDIATION_20260204.json`
