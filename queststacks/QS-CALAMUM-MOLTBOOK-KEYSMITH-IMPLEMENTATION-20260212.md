# QuestStack: QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212

**Title**: Calamum Moltbook Observer - KEYSMITH (sandboxed key minting; claim-url-only humans) (Job 0018)

**Owner**: ORACL-Prime

**Primary stakeholder / approver**: joediggidyyy

**Date**: 2026-02-12

**Status**: COMPLETED

---

## Context

We need a policy-compliant path to obtain `MOLTBOOK_API_KEY` for LIVE collection where **humans never handle secrets**.

This QuestStack implements the Option-2 decision:

- KEYSMITH runs in a sandbox/container.
- KEYSMITH mints/obtains an agent `api_key` via the vendor registration endpoint.
- Humans may complete a vendor claim/verification ceremony via `claim_url` only (non-secret).
- The secret `api_key` is handled via a sandbox-contained sealed-drop flow with fail-closed output-root enforcement.
- Host import/persist helper-script workflows are not part of the approved KEYSMITH artifact surface.

Source proposal (analysis-only):
- `projects/calamum-moltbook-observer/docs/reports/CALAMUM_KEYSMITH_SANDBOXED_MOLTBOOK_KEY_MINTING_PROPOSAL_20260212.md`

---

## SessionMemory evidence inputs (ops expectations)

These artifacts are expected to exist and remain fresh during execution:

- Policy snapshot (machine): `.agent_session/policy_snapshot.json`
- Policy snapshot (markdown): `.agent_session/policy_snapshot.md`
- Ops-awareness (machine): `.agent_session/ops_awareness.json`
- Ops-awareness (markdown): `.agent_session/ops_awareness.md`

---

## Artifacts

### Job specs

- Job doc (project SSOT, Markdown): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212.md`
- Job doc (project SSOT, JSON): `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212.json`

### QuestFrame spec

- `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.json`

### Execution narrative

- `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`

### Canonical gate evidence stream

- `logs/behavioral/gates/gate_events.jsonl`

---

## Next actions (canonical execution expectations)

- Use the job orchestrator surface:
  - `codesentinel job start <task_id>`
  - `codesentinel job close <task_id>`
- Run `codesentinel memory health --json` after close.
- Treat all KEYSMITH outputs as allowlisted artifacts:
  - `claim_url` may be recorded in plaintext.
  - `api_key` must be sealed; never printed; never tracked; and output paths must remain within sandbox-approved roots.

---

## Stop conditions

Hard stop and escalate if any of the following occur:

- `api_key` is printed to stdout/stderr.
- `api_key` is written to a tracked path.
- any operator workflow requires copy/paste or viewing the `api_key`.
- the upstream host cannot be validated as canonical (redirect/unexpected host).
