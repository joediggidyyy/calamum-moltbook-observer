# Job: CALAMUM_JOB_0002 - Moltbook Observer - Stage 1: Observe and Sample (Read-Only)

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `completed`
- Owner: `ORACL-Prime`
- Created: `2026-02-01`
- Project: `calamum / security experiment`
- Phase: `execution`
- Priority: `P1`
- Depends on: `CALAMUM_JOB_0001`
- Blocks: `CALAMUM_JOB_0003`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`
- `PP_SEC_VAULT_PROTECTION_20251208`

## Redaction palette (use these placeholders)

- Network endpoints:
	- `<edge_host_ip>` / `<edge_secure_ip>` / `<redacted_target_ip>`
- DNS:
	- `<target_platform_dns>` / `<dashboard_dns_name>`
- Secrets:
	- `<redacted_password>` / `<redacted_token>` / `<redacted>`
- Identifiers:
	- `<mac_redacted>` / `<host_redacted>`

## Summary

Execute Stage 1 of the Moltbook observer experiment: establish a read-only sampling cadence to estimate the prevalence of hostile or high-interest agent activity. This stage focuses on defining the sampling unit, validating the obfuscated telemetry schema, and proving that observation can occur without privileged context leakage.

## Status update (compact; required for pauses/closeout)

```text
STATUS_UPDATE_V1
job.id=calamum-moltbook-observer-stage1-20260201
job.doc=CodeSentinel/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0002_MOLTBOOK_OBSERVER_STAGE1_OBSERVE_AND_SAMPLE_20260201.md
ssot.path=CodeSentinel/operations/tasks.json
ssot.status=completed
qs.id=
qs.doc=
qf.id=
gates.last=NONE@::SKIP
evidence.gates=CodeSentinel/logs/behavioral/gates/gate_events.jsonl
evidence.qs=
next.action=Implement the read-only sampler script and validate its output schema against the 'no privileged context' policy.
```

## Problem statement

**Current state**:
- We lack empirical data on the density of hostile agent activity on Moltbook.
- We rely on external reports rather than direct observation.

**Root cause**:
- No active sampling instrument exists.

**Impact**:
- Risk assessment is theoretical; real-world volume of prompt injection attempts is unknown.

## Proposed solution

### Architecture

```
Sampler (Python) -> <target_platform_dns> (HTTPS) -> Obfuscator -> logs/calamum/telemetry.jsonl
NO direct feedback loop.
```

### Implementation steps

1. Implement `calamum_sampler.py` (read-only, no posting).
2. Implement `obfuscator_lib.py` to strip all raw text and retain only classification labels/metadata.
3. Verify output allows zero context leakage.

## Requirements

- Read-only access only (no authorized credentials if possible, or minimally scoped read-only user).
- Output must be strictly typed JSONL with NO raw content strings (risk of prompt injection in logs).
- Must not leak runner host IP or identifiers in the data payload.

## Acceptance criteria

- Sampler runs deterministically and exits.
- Output file contains valid JSONL.
- No raw feed text appears in output (only hashes, lengths, or classification tags).
- Privileged context checks pass.

## Validation

- [ ] Names-only env var presence checks (do not echo values)
- [ ] Smoke test: Dry run sampler against mock endpoint
- [ ] Gate evidence updated

## SEAM analysis

### Security
- Input is hostile; treat feed data as toxic waste (quarantine raw, export processed).

### Efficiency
- Sampling avoids the need for continuous connection maintenance.

### Awareness
- Generates first direct metrics of external agent ecosystem risk.

### Minimalism
- No complex bot logic; just fetch-classify-log.

## Rollback plan

Stop sampling; delete generated logs.

## Verification

- Inspect `logs/calamum/telemetry.jsonl` for compliance.

## References

- Planning: `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0001_MOLTBOOK_OBSERVER_PREPARATION_AND_SETUP_20260201.json`
