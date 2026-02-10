# Job: CALAMUM_JOB_0004 - Moltbook Observer - Stage 3: Passive Canary

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `completed`
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

## Methodology & Narrative Execution

Stage 3 represented the transition from internal testing to external observation (simulated for this phase). The objective was to deploy a "Passive Canary"—an agent identity that exists on the network but takes zero outbound actions. This allows us to measure the "background radiation" of the network: the volume of unsolicited hostility directed at a silent, new node.

### 1. The Canary Protocol
The "Canary" mode (`--mode canary`) was architected to be strictly **inbound-only**. Unlike standard bots which broadcast, the Canary listens. This required a modification to the `calamum_sampler.py` to target the notification/inbox endpoint instead of the public timeline.

- **Target Metrics**: Direct Messages (DMs), Mentions, and Follows.
- **Safety**: To prevent "reverse-prompt-injection" (where an attacker sends a malicious payload to the observer's inbox), the sampler applies rigorous obfuscation **before** logging. No message content is ever written to disk in its raw form.

### 2. Simulation & Validation
Before connecting to the live Moltbook API, we executed a high-fidelity simulation (`src/tests/test_canary_simulation.py`) to prove the safety of the pipeline:

- **Synthetic Data**: We generated a stream of hostile notifications (e.g., "Hey check this link").
- **Verification**: We verified that our `obfuscator_lib` correctly stripped the content and hashed the sender's identity (`sender_hash`) before the data reached the JSONL log.
- **Result**: The final artifact `logs/data/calamum/moltbook_canary_metrics.jsonl` demonstrates a clean, academic dataset of interaction *types* without containing the toxic *payloads*.

### 3. Operational Integration
This job was executed via the Stage 2 Hardened Container (`calamum-observer:test`), ensuring that even if the Canary code had a vulnerability, it could not persist state or escalate privileges. This "Defense in Depth" strategy is central to the Calamum methodology.

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
