# Job: CALAMUM_JOB_0004 - Moltbook Observer - Stage 3: Passive Canary

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `open`
- Owner: `ORACL-Prime`
- Created: `2026-02-01`
- Project: `calamum / security experiment`
- Phase: `execution`
- Priority: `P2`
- Depends on: `CALAMUM_JOB_0003`
- Blocks: `CALAMUM_JOB_0005`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`
- `PP_SEC_VAULT_PROTECTION_20251208`

## Redaction palette

- Secrets:
	- `<canary_account_credentials_redacted>`
- Identifiers:
	- `<canary_handle_redacted>`

## Summary

Deploy a 'passive canary' presence: a registered account that takes NO action (no posts, no replies, no follows) but monitors unsolicited inbound interactions (DMs, mentions, follows). This measures background radiation of the hostile network: how quickly is a silent agent targeted by bots or scanners?

## Status update (compact)

```text
STATUS_UPDATE_V2
job.id=calamum-moltbook-observer-stage3-20260201
job.doc=CodeSentinel/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0004_MOLTBOOK_OBSERVER_STAGE3_PASSIVE_CANARY_20260201.md
ssot.path=CodeSentinel/operations/tasks.json
ssot.status=completed
qs.id=QS-CALAMUM-MOLTBOOK-OBSERVER-STAGE3-20260201
qs.doc=projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-STAGE3-20260201.md
qf.id=QF-CALAMUM-MOLTBOOK-OBSERVER-STAGE3-20260201
gates.last=POST_JOB@2026-02-03
evidence.gates=CodeSentinel/logs/behavioral/gates/gate_events.jsonl
evidence.qs=logs/data/calamum/moltbook_canary_metrics.jsonl
next.action=Proceed to Stage 4 (Active/Magnet).
```

## Problem statement

**Current state**:
- We know the feed is hostile, but not the targeted attack surface for a specific agent identity.
- Is the network scanning for new agents?

**Root cause**:
- Passive observation ignores targeted inbound vectors.

**Impact**:
- We may underestimate risk if attacks are primarily directed (DMs/Mentions) rather than broadcast.

## Proposed solution

### Architecture

```
Canary Account (Silent) -> Sampler (Notification Polling) -> Obfuscator -> logs/calamum/inbound_metrics.jsonl
```

### Implementation steps

1. Register 'silent' account.
2. Update sampler to poll notification/inbox endpoint (read-only).
3. Log inbound event types (follow/mention/dm) without content.

## Requirements

- ABSOLUTELY NO OUTBOUND ACTIVITY. Zero posts.
- Strict content quarantine for inbound DMs (high risk of injection).
- Metric collection only (count of events, type of event).

## Acceptance criteria

- Canary exists for > 48h.
- Outbound activity is verified 0.
- Inbound activity is logged with obfuscation.

## Validation

- [ ] Verify notification fetching logic
- [ ] Confirm no outbound posts in platform history

## SEAM analysis

### Security
- Higher risk than passive sampling (authentication required). Account credentials must be VAULT-protected.

### Efficiency
- Low impact; polling only.

### Awareness
- Measures 'background radiation' of the platform.

### Minimalism
- Do nothing, see who knocks.

## Rollback plan

Delete canary account; Archive logs.

## Verification

- Confirm no outbound posts in platform history.

## References

- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0003_MOLTBOOK_OBSERVER_STAGE2_CONTAINER_HARDENING_20260201.json`
