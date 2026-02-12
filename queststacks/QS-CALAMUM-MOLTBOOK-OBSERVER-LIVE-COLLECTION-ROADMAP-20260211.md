# QuestStack: QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211

**Title**: Calamum Moltbook Observer - Live Collection Roadmap (Honeypot Activation) (Job 0017)

**Owner**: ORACL-Prime

**Primary stakeholder / approver**: joediggidyyy

**Date**: 2026-02-11

**Status**: OPEN (ops validation pending)

---

## Context

Job 0017 targets an operator-verified end-state where Calamum is in **LIVE COLLECTION** (honeypot active and collecting) with a file-based, names-only validation surface.

Primary validation signals:

- Observer chain alive (agent / librarian / watchdog / ghost console).
- Environment variables injected air-gapped (presence only).
- Canonical live metrics stream becomes **fresh and non-empty**.
- CRITICAL-only operator alerting is enabled for the live window.

---

## SessionMemory evidence inputs (ops expectations)

These artifacts are expected to exist and remain fresh during execution:

- Policy snapshot (machine): `.agent_session/policy_snapshot.json`
- Policy snapshot (markdown): `.agent_session/policy_snapshot.md`
- Ops-awareness (machine): `.agent_session/ops_awareness.json`
- Ops-awareness (markdown): `.agent_session/ops_awareness.md`

---

## Implementation delta (deviation record; names-only)

Job 0017 was originally scoped as **ops/config + validation only** (no backend source work). During execution, a minimal wiring change was made to align the local observer agent with the canonical live metrics filename referenced by Stage 4 / Job 0017 validation.

- Commit: `eeba7f35`
- Machine record: `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.json` (`implementation_delta`)

This delta requires explicit approver acknowledgment to close the job.

---

## Artifacts

### Job specs

- Job doc (project SSOT, Markdown): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.md`
- Job doc (project SSOT, JSON): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.json`

### Job report

- `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211.md`

### QuestStack provenance

- QuestStack log: `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211_log.md`
- QuestStack evidence: `logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211_evidence.jsonl`

---

## Next actions (canonical job execution expectations)

- (per job) Use the job orchestrator surface: `codesentinel job start <task_id>` and `codesentinel job close <task_id>`.
- (health) Run `codesentinel memory health --json` after close.
- (ops) Inject required env vars (presence only): `MOLTBOOK_API_KEY`.
  - Preferred path: KEYSMITH sealed drop + VAULT/OS import (claim-url only humans; humans never handle the key).
  - References:
    - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212.md`
    - `operations/checklists/CALAMUM_MOLTBOOK_OBSERVER_LIVE_COLLECTION_SECURITY_PREFLIGHT.md`
- (ops) Set non-CANARY mode and live source selector:
  - `CALAMUM_OPS_MODE` != `canary`
  - `CALAMUM_MOLTBOOK_SOURCE=live`
- (validate) Confirm freshness + non-empty:
  - `logs/data/calamum/moltbook_live_metrics.jsonl`
- (alerts) Run the CRITICAL watcher during the live window.
- (evidence) Capture a diagnostics bundle in `report_tmp/`.
