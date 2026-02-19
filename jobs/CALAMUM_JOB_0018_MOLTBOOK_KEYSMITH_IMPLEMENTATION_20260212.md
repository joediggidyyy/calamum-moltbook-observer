# Job: CALAMUM_JOB_0018 - Moltbook KEYSMITH Implementation (sandboxed key minting; claim-url only humans)

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Status: `completed`
- Owner: `ORACL-Prime`
- Created: `2026-02-12`
- Project: `calamum / moltbook observer`
- Phase: `execution`
- Priority: `P0`
- Depends on:
  - `CALAMUM_JOB_0017` (Live Collection Roadmap: requires a non-human secret handling path)
- Blocks:
  - Live collection operations that require `MOLTBOOK_API_KEY` but must keep humans away from secrets.

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_GOV_PROTOCOL_POL_AGENT_ACTION_WORKFLOW_20251122`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`
- `PP_SEC_VAULT_PROTECTION_20251208`

## Summary

Implement **KEYSMITH**: a sandboxed utility/container that registers a Moltbook agent and obtains an `api_key` **without exposing the secret to humans**.

Humans are permitted to complete a vendor claim/verification step using a **claim URL only** (non-secret). The secret must be transferred via a sealed-drop mechanism and then imported into VAULT / OS secret storage.

This job is the implementation counterpart to the analysis/proposal:
- `projects/calamum-moltbook-observer/docs/reports/CALAMUM_KEYSMITH_SANDBOXED_MOLTBOOK_KEY_MINTING_PROPOSAL_20260212.md`

## Scope

### In scope

- A deterministic KEYSMITH interface:
  - inputs: host selector, agent metadata (names-only), output directory, "dry-run" mode
  - outputs: claim URL artifact, sealed secret artifact, names-only audit log
- Sandboxed key minting (network access only inside sandbox)
- Sealed-drop handoff for `api_key` (never printed; never tracked)
- VAULT / OS secret-store import glue (presence-only verification)
- Tests: fail-closed, redaction, no-secret logging guarantees

### Out of scope

- Any observer sampling logic changes (unless explicitly added via a documented scope expansion)
- Any automation that completes the vendor claim step without human authorization
- Any workflow that requires a human to copy/paste or view the `api_key`

## Constraints (non-negotiable)

- **No secrets in repo** (tracked or untracked).
- **No secret printing** (stdout/stderr/log files).
- **Names-only evidence**: logs can indicate presence and success/failure without values.
- **Fail-closed**:
  - If LIVE is requested but `MOLTBOOK_API_KEY` is not present (or cannot be imported), the observer must refuse to run.

## Execution steps (high level)

1) Define KEYSMITH contract
- Identify exact inputs required by vendor registration endpoint.
- Define a stable output contract:
  - `claim_url` artifact (non-secret)
  - sealed drop artifact containing `api_key` (secret)
  - names-only audit record (no secret values)

2) Implement sandboxed register client
- Perform `POST /agents/register` (or vendor equivalent) **from inside sandbox**.
- Persist only allowlisted outputs.

3) Implement sealed-drop handoff
- Choose a sealed-drop implementation suitable for Windows operators and Linux sandbox execution.
- Ensure the operator can import into VAULT/OS secret storage without seeing the key.

4) Implement VAULT import glue (names-only)
- Add a deterministic import path:
  - sealed drop -> env var injection into target runtime
  - validate with presence-only checks

5) Add tests
- Prove no secret values are written/printed.
- Prove fail-closed behavior if key missing.

## Acceptance criteria

- [ ] KEYSMITH produces a `claim_url` artifact (non-secret) suitable for a human claim ceremony.
- [ ] KEYSMITH produces a sealed-drop artifact containing the secret `api_key` without exposing it.
- [ ] A deterministic import step populates `MOLTBOOK_API_KEY` into the operator environment/VAULT without human secret handling.
- [ ] Automated tests verify:
  - no-secret logging/printing
  - fail-closed behavior
  - schema/versioned artifacts

## Deliverables (paths)

- Job SSOT:
  - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212.md`
  - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212.json`

- Quest provenance:
  - QuestStack: `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`
  - QuestFrame: `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.json`

- Execution narrative:
  - `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`

## Evidence pointers

- Gate events (canonical): `logs/behavioral/gates/gate_events.jsonl`
- SessionMemory policy + ops-awareness snapshots:
  - `.agent_session/policy_snapshot.json`
  - `.agent_session/ops_awareness.json`
