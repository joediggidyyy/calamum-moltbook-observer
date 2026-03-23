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

## Canonical three-stage observer path

The observer path is intentionally narrow and threat-focused:

1. **Canary mode**
  - strict passive collection
  - establish an unsupervised baseline from names-only structural / temporal / behavioral signals
2. **Live mode**
  - make the local observer an active target
  - widen the baseline and measure new or emergent pattern deltas relative to canary
3. **Honeypot mode**
  - make the local observer an attractive target
  - measure higher-pressure deltas relative to live and canary

Research hypothesis:

- threat-relevant patterns can be identified from obfuscated structural / temporal / behavioral signals without direct ingestion of the threat-vector payload.

Scope exclusion:

- human-mimicry / larper detection is out of scope for this plan.

Scope-separation addendum (2026-02-21):

- Runtime CLI naming for this project is `observerctl`.
- `observerctl` is observer-scoped and standalone (no dependency on CodeSentinel runtime process surfaces).
- Historical CALAMUM identifiers remain for lineage only and do not define runtime interface naming.

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

### Stage 3: Canary mode

Definition of done:

- Strict passive collection sets the initial unsupervised baseline.
- All inbound content remains quarantined; exports remain obfuscated and names-only.

### Stage 4: Live mode

*Note: This is the active-target stage of the canonical observer path.*

Definition of done:

- **Constraint**: `GET` requests only; no `POST` actions without secondary approval.
- **Security**: Air-gapped credentials; Stage 2 Hardened execution.
- **Objective**: Make the observer an active target, capture ephemeral data, and compare live deltas against the canary baseline.

### Stage 5: Honeypot mode

Definition of done:

- Collection conditions make the observer an attractive target while preserving names-only outputs.
- Analysis focuses on threat deltas relative to live and canary baselines.
- Any baiting / `POST` exception is a separate, non-canonical governance lane and is not part of this plan.

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

## Publication-grade output requirements (observer doctoral lane)

All observer-scoped deliverables must include a publish-grade triad:

1. **Provenance**
  - artifact path, digest (SHA256), generation timestamp (UTC), producer identity, upstream dependency refs.
2. **Methodology**
  - sampling frame/cadence, constraints, invariants, failure semantics, reproducibility protocol.
3. **Process**
  - phase ledger, decision/rationale log, evidence references, approval checkpoints.

Gate readiness requires all three packets for each high-value transition (especially live collection go/no-go).
