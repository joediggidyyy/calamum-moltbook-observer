# Job: CALAMUM_JOB_0001 - Moltbook Observer - Preparation and Setup (Calamum, read-only, obfuscated)

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `completed`
- Owner: `ORACL-Prime`
- Created: `2026-02-01`
- Project: `calamum / security experiment`
- Phase: `preparation`
- Priority: `P0`
- Depends on: `(none)`
- Blocks: `CALAMUM_JOB_0002`, `CALAMUM_JOB_0003`, `CALAMUM_JOB_0004`, `CALAMUM_JOB_0005`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_GOV_PROTOCOL_POL_AGENT_ACTION_WORKFLOW_20251122`
- `PP_GOV_PROTOCOL_POL_JOB_COMPLEXITY_REQUIREMENT_20251126`
- `PP_GOV_PROTOCOL_POL_DETERMINISTIC_WORKFLOW_20251127`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`
- `PP_SEC_VAULT_PROTECTION_20251208`

## Redaction palette (use these placeholders)

Never paste private IPs, MAC addresses, org-internal hostnames/domains, or tokens into job docs.

Use placeholders consistently:
- Network endpoints:
	- `<edge_host_ip>` / `<edge_secure_ip>` / `<edge_parent_net_ip>`
	- `<core_host_ip>` / `<core_secure_ip>`
	- `<port>`
	- `<secure_subnet>` / `<parent_net_subnet>`
- DNS:
	- `<dashboard_dns_name>` / `<optional_api_dns_name>`
- Secrets:
	- `<redacted_password>` / `<redacted_token>` / `<redacted>`
- Identifiers:
	- `<mac_redacted>` / `<host_redacted>`

## Summary

Set up the Calamum-scoped Moltbook observer experiment with zero-trust constraints: no privileged host context export, no self-modification, strict egress allowlisting, and obfuscated structured outputs only. This job is paperwork + setup and explicitly reviews the job execution pipeline requirements (PREFLIGHT/PRE_JOB/POST_JOB).

## Status update (compact; required for pauses/closeout)

```text
STATUS_UPDATE_V1
job.id=calamum-moltbook-observer-prep-20260201
job.doc=CodeSentinel/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0001_MOLTBOOK_OBSERVER_PREPARATION_AND_SETUP_20260201.md
ssot.path=CodeSentinel/operations/tasks.json
ssot.status=completed
qs.id=
qs.doc=
qf.id=
gates.last=NONE@::SKIP
evidence.gates=CodeSentinel/logs/behavioral/gates/gate_events.jsonl
evidence.qs=
next.action=Draft the stage job documents (JSON+MD) and identify the minimal QuestStack scaffolding needed to satisfy PRE_JOB before any live connector work.
```

## Problem statement

**Current state**:
- We have feasibility + safety posture, but Calamum execution paperwork (domain plan + staged job specs) must be created before running any connector.
- The job execution pipeline requires SSOT task ids and QuestStack scaffolding for PRE_JOB.

**Root cause**:
- Untrusted social feed input demands stronger isolation, redaction discipline, and deterministic gates than ad-hoc scripts.
- Without staged jobs and explicit constraints, later implementation can drift into unsafe defaults.

**Impact**:
- Increased risk of privileged context leakage if artifacts are not constrained.
- Increased risk of workflow drift if pipeline requirements are not surfaced early.

## Proposed solution

### Architecture

```
Calamum experiment (Moltbook observer)

prep/setup
-> observe+sample (offline)
-> container/VM hardening
-> passive canary (optional)
-> active magnet (gated)

Execution surface:
- codesentinel job begin/finish (PREFLIGHT + PRE_JOB + POST_JOB)
- evidence: logs/behavioral/gates/gate_events.jsonl

Exports:
- obfuscated summaries only (no raw text; no privileged host context)
```

### Implementation steps

1. Create Calamum domain planning artifacts (plan + jobs) using VAULT templates.
2. Review job automation pipeline requirements:
   - `docs/operations/guides/JOB_AUTOMATION_PIPELINE_TRANSITION_SCENARIOS_20260108.md`
   - `tools/codesentinel/gates/gate_pre_job.py` scaffold expectations
3. Confirm "no privileged host context export" and "no self-modification" constraints are explicit and referenced by stage jobs.

## Requirements

- Names-only documentation (no secrets, no private identifiers).
- Read-only observer posture (no posting/engagement).
- No privileged host context export (paths, usernames, hostnames, env inventories).
- No self-modification: code and runtime must be immutable; only sandbox output is writable.
- Job execution must respect gates (PREFLIGHT/PRE_JOB/POST_JOB/EOD as applicable).

## Acceptance criteria

- Calamum domain planning plan exists (JSON authoritative + MD view).
- Stage job docs exist (JSON authoritative + MD views) and reference the same safety constraints.
- Job docs explicitly reference the job execution pipeline and required evidence surfaces.
- No privileged identifiers are introduced in the new paperwork.

## Validation

- [ ] Names-only env var presence checks (do not echo values)
- [ ] Smoke test(s): N/A (paperwork-only job)
- [ ] Gate evidence updated (PREFLIGHT/BOD/EOD/POST_JOB as applicable): N/A

## SEAM analysis

### Security
- Zero-trust: assume the observer may be compromised; constrain exports and permissions.
- No secrets in repo; env-var only; names-only docs.
- No privileged host context export.

### Efficiency
- Stage work into deterministic jobs so later implementation is not ad-hoc.

### Awareness
- Explicitly reference gate pipeline and evidence surfaces early.

### Minimalism
- Prefer existing CodeSentinel gate and job patterns; avoid inventing new paperwork formats.

## Rollback plan

No runtime changes are performed in this job; rollback is archive-first retirement of paperwork if needed.

## Verification

- Confirm new documents are names-only and contain no privileged endpoints or host identifiers.
- Confirm job docs link to the Calamum plan and feasibility artifacts.

## References

- Plan: `projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_OBSERVER_EXPERIMENT_PLAN_20260201.json`
- Feasibility: `docs/reports/security/MOLTBOOK_SANDBOXED_OBSERVER_FEASIBILITY_2026-02-01.md`
- Checklist: `operations/checklists/AGENT_SOCIAL_FEED_SAFETY_CHECKLIST.md`
- Pipeline guide: `docs/operations/guides/JOB_AUTOMATION_PIPELINE_TRANSITION_SCENARIOS_20260108.md`
