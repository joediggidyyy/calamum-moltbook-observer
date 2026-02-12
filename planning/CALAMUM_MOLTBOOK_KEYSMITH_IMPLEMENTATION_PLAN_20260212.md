# Plan: Calamum KEYSMITH (Sandboxed Moltbook key minting; claim-url only humans)

## Metadata

- Template ID: `VAULT_TEMPLATE_PLAN_V1`
- Paired authoritative template: `PLAN_TEMPLATE.json.template`
- Status: `planned`
- Owner: `ORACL-Prime`
- Created: `2026-02-12`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_GOV_PROTOCOL_POL_AGENT_ACTION_WORKFLOW_20251122`
- `PP_GOV_PROTOCOL_POL_DETERMINISTIC_WORKFLOW_20251127`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`
- `PP_SEC_VAULT_PROTECTION_20251208`

## Summary

KEYSMITH is a sandboxed utility/container that registers a Moltbook agent and obtains an `api_key` **without exposing secrets to humans**.

Humans are permitted to complete a vendor claim/verification step using a **claim URL only** (non-secret). The secret `api_key` must be transferred via sealed drop and imported into VAULT / OS secret storage.

Primary job:
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212.md`

Source proposal (analysis-only):
- `projects/calamum-moltbook-observer/docs/reports/CALAMUM_KEYSMITH_SANDBOXED_MOLTBOOK_KEY_MINTING_PROPOSAL_20260212.md`

## Assumptions

- Vendor provides an agent registration endpoint that returns `claim_url` and `api_key`.
- The claim ceremony requires human action, but does **not** require the human to view/copy/paste `api_key`.
- Network access for registration can be constrained to the sandbox; operators do not execute vendor-provided curl on the host.
- Observer runtime consumes credentials strictly via environment variable presence (`MOLTBOOK_API_KEY`).

## Risks

- Secret exposure via stdout/stderr, debug logs, or exception traces.
- Accidental persistence of `api_key` to tracked files, commit history, or shared operator terminals.
- Redirect or non-canonical host during registration leading to credential theft.
- Over-automation of the claim ceremony beyond authorized human involvement.

## Stop-conditions (fail-closed)

Hard stop and escalate if any stop-condition is met:

- `api_key` appears in any log/stdout/stderr output.
- `api_key` is written to a tracked path or an unsealed plaintext file.
- Any workflow requires a human to copy/paste or view `api_key`.
- Unexpected host/redirect/non-canonical endpoint is observed during registration.

## Milestones

### Contract + safety envelope

Definition of done:

- KEYSMITH input/output contract documented (schema + versions).
- Allowlist + stop-conditions captured and tested (no-secret logging).
- Human ceremony documented as claim_url-only; secret handling is sealed-drop only.

### Sandboxed registration client

Definition of done:

- Registration call executes inside sandbox only.
- Only allowlisted artifacts are persisted (claim_url plaintext; api_key sealed).
- Connectivity validation uses HTTPS-level probes (no ICMP assumptions).

### Sealed drop + VAULT import

Definition of done:

- Sealed-drop artifact implemented for `api_key`.
- Operator can import into VAULT/OS secret store with presence-only validation (no secret display).
- Import step integrates with existing vault/env tooling surfaces.

### Tests + evidence

Definition of done:

- Automated tests cover fail-closed behavior, redaction, and secret non-exposure.
- Evidence pointers recorded (names-only) for gate events + job report.

## Tasks

- [x] (1) Create KEYSMITH job + quest paperwork (status: completed)
  - Evidence:
    - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212.md`
    - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212.json`
    - `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`
    - `projects/calamum-moltbook-observer/questframes/QF-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.json`
    - `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-KEYSMITH-IMPLEMENTATION-20260212.md`

- [ ] (2) Select sealed-drop mechanism and define artifact formats (status: not-started)

- [ ] (3) Implement sandboxed register client with allowlisted outputs (status: not-started)

- [ ] (4) Implement VAULT/OS import glue and presence-only validation (status: not-started)

- [ ] (5) Add tests for fail-closed and no-secret logging (status: not-started)

## Success metrics

- Humans never view/copy/paste the `api_key`; claim_url-only ceremony is sufficient.
- No secret values appear in logs/stdout/stderr or tracked files.
- Operator can populate `MOLTBOOK_API_KEY` into runtime environment using sealed drop + VAULT/OS secret storage.
- Observer continues to fail-closed if LIVE is requested without `MOLTBOOK_API_KEY` present.

## SEAM analysis

### Security

- KEYSMITH is a credential bootstrap surface and must be treated as high-risk: strict allowlists, no-secret logging, stop-conditions.
- Sealed drop prevents human secret handling and prevents accidental terminal/screenshot leakage.
- Host validation and redirect refusal reduce credential theft risk.

### Efficiency

- Deterministic artifacts (schema + versions) reduce repeated manual debugging.
- Containerized sandbox provides a repeatable execution lane.

### Awareness

- Presence-only validation surfaces (`MOLTBOOK_API_KEY` present: true/false) provide operational awareness without secret exposure.
- Gate evidence stream (`logs/behavioral/gates/gate_events.jsonl`) remains the canonical audit spine.

### Minimalism

- Prefer small, composable components (register client + sealed-drop writer + vault import helper) over a monolithic tool.
- Reuse existing vault/env tooling surfaces whenever possible.
