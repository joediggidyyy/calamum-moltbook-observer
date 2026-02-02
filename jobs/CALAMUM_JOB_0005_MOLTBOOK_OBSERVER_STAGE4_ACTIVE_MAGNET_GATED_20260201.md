# Job: CALAMUM_JOB_0005 - Moltbook Observer - Stage 4: Active Magnet (GATED)

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `blocked`
- Owner: `ORACL-Prime`
- Created: `2026-02-01`
- Project: `calamum / security experiment`
- Phase: `execution`
- Priority: `P3`
- Depends on: `CALAMUM_JOB_0004`
- Blocks: `(none)`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`
- `PP_SEC_VAULT_PROTECTION_20251208`

## Redaction palette

- Secrets:
	- `<magnet_account_credentials_redacted>`
- Identifiers:
	- `<magnet_handle_redacted>`

## Summary

Deploy an 'active magnet' or honeypot: an account that posts specific, human-written bait phrases (e.g., 'Ignore previous instructions', 'What is your system prompt?') to elicit reaction from other agents. THIS JOB IS BLOCKED BY DEFAULT AND REQUIRES AN EXPLICIT POLICY EXCEPTION AND HUMAN SIGN-OFF TO EXECUTE.

## Status update (compact)

```text
STATUS_UPDATE_V1
job.id=calamum-moltbook-observer-stage4-20260201
job.doc=CodeSentinel/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0005_MOLTBOOK_OBSERVER_STAGE4_ACTIVE_MAGNET_GATED_20260201.md
ssot.path=CodeSentinel/operations/tasks.json
ssot.status=blocked
qs.id=
qs.doc=
qf.id=
gates.last=NONE@::FAIL
evidence.gates=CodeSentinel/logs/behavioral/gates/gate_events.jsonl
evidence.qs=
next.action=Do not proceed until PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201 exception is granted.
```

## Problem statement

**Current state**:
- Passive observation measures background noise, but not reactivity.
- We do not know if agents are explicitly hunting for vulnerabilities.

**Root cause**:
- Passive canary is silent.

**Impact**:
- We miss the 'shark in the water' dynamic: highly aggressive agents that only strike when they smell blood (vulnerability markers).

## Proposed solution

### Architecture

```
Magnet Account (Posts Bait) -> Sampler (Replies/DMs) -> Obfuscator -> logs/calamum/reactivity_metrics.jsonl
```

### Implementation steps

1. Obtain explicit sign-off.
2. Define bait corpus (static, human-reviewed, no autonomous generation).
3. Post bait manually or via strict one-way script.
4. Monitor response intensity.

## Requirements

- EXPLICIT HUMAN APPROVAL per run.
- NO AUTONOMOUS LLM-GENERATED POSTS. Content must be static strings.
- Strict isolation of replies (highest risk of malicious payloads).

## Acceptance criteria

- Sign-off recorded.
- Bait posted.
- Reactivity measured.

## Validation

- [ ] Check Policy Exception
- [ ] Confirm Stage 2 Hardening containment

## SEAM analysis

### Security
- Highest risk. Provokes attack. Must utilize Stage 2 Hardening.

### Efficiency
- High signal-to-noise expected.

### Awareness
- Reveals the aggressive edge of the ecosystem.

### Minimalism
- Single post, wait.

## Rollback plan

Delete posts; Delete account.

## Verification

- Confirm bait text matches approved corpus exactly.

## References

- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0004_MOLTBOOK_OBSERVER_STAGE3_PASSIVE_CANARY_20260201.json`
