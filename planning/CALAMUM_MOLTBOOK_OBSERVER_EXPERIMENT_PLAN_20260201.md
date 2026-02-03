# Plan: Calamum: Moltbook Sandboxed Observer Experiment (obfuscated, read-only)

## Metadata

- Template ID: `VAULT_TEMPLATE_PLAN_V1`
- Paired authoritative template: `PLAN_TEMPLATE.json.template`
- Status: `planned`
- Owner: `ORACL-Prime`
- Created: `2026-02-01`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_GOV_PROTOCOL_POL_AGENT_ACTION_WORKFLOW_20251122`
- `PP_GOV_PROTOCOL_POL_DETERMINISTIC_WORKFLOW_20251127`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`
- `PP_SEC_VAULT_PROTECTION_20251208`

## Summary

Design and execute a Calamum-scoped, zero-trust, read-only observer against Moltbook (and similar agent social networks). The experiment MUST prevent privileged host context leakage, MUST prevent self-modification by the observer, and MUST export only obfuscated structured telemetry suitable for governance and safety decisions.

## Assumptions

- Agent social networks are untrusted input streams (hostile by default).
- Observation-only sampling can estimate prevalence of hostile patterns without participation.
- If any active magnet behavior is attempted later, it must be gated behind an explicit policy exception and human signoff.

## Risks

- Prompt injection and social engineering via feed content.
- Leakage of privileged local context (paths, hostnames, usernames, env inventories) into exported artifacts.
- Self-modification/persistence by the observer runtime if compromised.
- Sampling bias if endpoints/time windows are not selected carefully.

## Milestones

### Preparation and setup (paperwork + constraints)

Definition of done:

- Plan and staged job docs exist (JSON authoritative + MD views) under Calamum domain planning and `jobs/`.
- Feasibility constraints (no privileged context export; no self-modification) are explicitly captured and linked.
- A deterministic execution lane is selected (Linux container/VM preferred) and documented at a names-only level.

### Stage 1: Observe + sample (read-only)

Definition of done:

- Sampling strategy defined (unit of observation, cadence, strata).
- Obfuscated telemetry schema defined and validated against safety constraints.

### Stage 2: Container/VM hardening

Definition of done:

- Runner constraints documented: rootless, read-only FS, capability drop, egress allowlist, write-only output volume.
- Observer cannot modify its code or dependencies; only sandbox output is writable.

### Stage 3: Passive canary (optional)

Definition of done:

- If supported by platform, unsolicited inbound interaction rate can be measured without posting.
- All inbound content remains quarantined; exports remain obfuscated and names-only.

### Stage 4: Live Wire (Live Data Collection)

*Note: Originally "Active Magnet". Split to prioritize data preservation (`GET` only) before active engagement (`POST`).*

Definition of done:

- **Constraint**: `GET` requests only; no `POST` actions without secondary approval.
- **Security**: Air-gapped credentials; Stage 2 Hardened execution.
- **Objective**: Operational "Hot-Wire" connection to Moltbook API to capture ephemeral data.

### Stage 5: Active Magnet (Gated / Optional)

Definition of done:

- Explicit governance exception obtained for `POST` actions.
- Human-written bait only; no autonomous engagement.
- Reputational and operational risk accepted by maintainer.

## Tasks

- [x] (1) Create staged Calamum jobs (prep, observe, harden, canary, magnet-gated) using VAULT templates (status: completed)
  - Evidence:
    - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0001_MOLTBOOK_OBSERVER_PREPARATION_AND_SETUP_20260201.json` / `.md`
    - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0002_MOLTBOOK_OBSERVER_STAGE1_OBSERVE_AND_SAMPLE_20260201.json` / `.md`
    - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0003_MOLTBOOK_OBSERVER_STAGE2_CONTAINER_HARDENING_20260201.json` / `.md`
    - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0004_MOLTBOOK_OBSERVER_STAGE3_PASSIVE_CANARY_20260201.json` / `.md`
    - `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0005_MOLTBOOK_OBSERVER_STAGE4_ACTIVE_MAGNET_GATED_20260201.json` / `.md` (Scope adjusted to "Live Wire")

- [ ] (2) Link feasibility + policy artifacts and confirm redaction rules (status: not-started)
  - Evidence:
    - `docs/reports/security/MOLTBOOK_SANDBOXED_OBSERVER_FEASIBILITY_2026-02-01.md`
    - `docs/reports/security/MOLTBOOK_AGENT_SOCIAL_NETWORKS_RISK_REPORT_2026-02-01.md`
    - `operations/checklists/AGENT_SOCIAL_FEED_SAFETY_CHECKLIST.md`

## Success metrics

- 0 incidents of privileged host context leakage into exported artifacts.
- 0 incidents of feed-sourced command execution or package installation.
- Obfuscated outputs support at least one concrete governance decision (policy/checklist refinement) without raw text export.
- Sampling yields a stable, repeatable estimate of high-risk signal prevalence over time.
