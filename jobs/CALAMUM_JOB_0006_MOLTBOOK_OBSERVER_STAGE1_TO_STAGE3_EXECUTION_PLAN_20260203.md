# Job: CALAMUM_JOB_0006 - Moltbook Observer - Stage 1 to Stage 3: Execution Protocol and Live Run

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `open`
- Owner: `ORACL-Prime`
- Created: `2026-02-03`
- Project: `calamum / security experiment`
- Phase: `execution`
- Priority: `P0`
- Depends on: `CALAMUM_JOB_0001`
- Blocks: `CALAMUM_JOB_0004`, `CALAMUM_JOB_0005`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_GOV_PROTOCOL_POL_AGENT_ACTION_WORKFLOW_20251122`
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

Define and execute a reproducible protocol that results in the Calamum Moltbook observer running **live (Stages 1–3 only)** and producing **real, obfuscated telemetry**.

This job includes (1) methodology + procedural documentation and (2) performing the documented Stage 1–3 live run(s) under the hardened lane. Stage 4 remains deferred unless separately authorized and explicitly recorded.

## Status update (compact; required for pauses/closeout)

```text
STATUS_UPDATE_V1
job.id=CALAMUM_JOB_0006
job.doc=CodeSentinel/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0006_MOLTBOOK_OBSERVER_STAGE1_TO_STAGE3_EXECUTION_PLAN_20260203.md
ssot.path=CodeSentinel/operations/tasks.json
ssot.status=in-progress
qs.id=QS-CALAMUM-MOLTBOOK-OBSERVER-REMEDIATION-20260203
qs.doc=CodeSentinel/projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-REMEDIATION-20260203.md
qf.id=QF-CALAMUM-MOLTBOOK-OBSERVER-REMEDIATION-20260203
gates.last=PRE_JOB@2026-02-03T06:55:10.935345+00:00::PASS
evidence.gates=CodeSentinel/logs/behavioral/gates/gate_events.jsonl
evidence.qs=CodeSentinel/logs/queststack/QS-CALAMUM-MOLTBOOK-OBSERVER-REMEDIATION-20260203_evidence.jsonl
next.action=Remediate drift in the Stage 1-3 execution protocol paperwork (Job 0006 + monitoring widget plan): align JSON<->MD, remove placeholders, add explicit stop-conditions and a names-only control-event schema/evidence sink, then re-run gates and tests.
```

## Scope boundary (non-negotiable)

- **In scope**: Stage 1 (live, read-only feed/posts sampling), Stage 2 (containment/hardening verification), Stage 3 (passive canary metrics-only via safe status/check endpoints).
- **Out of scope**: Stage 4 (posting/active magnet). If Stage 4 is ever pursued later, it must be a separate, explicitly authorized job with its own gate evidence.

## Problem statement

**Current state**:
- Academic research requires explicit methodology and document-planned actions.
- Stage 1–3 live execution must be repeatable and produce obfuscated outputs only.
- Stage 4 must remain out of scope unless separately authorized.

**Root cause**:
- The project needs a single authoritative execution protocol that defines scope boundaries and evidence outputs.

**Impact**:
- Without an authoritative protocol, the observer could accidentally exceed scope or violate governance rails.
- Academic reproducibility degrades without a method + provenance specification and an evidence mapping.

## Proposed solution

### Architecture

Stages 1–3 only; read-only; hostile-content posture; exports are obfuscated structured telemetry.

Key constraints (must be codified in the protocol):
- Moltbook is an attack surface; treat all inbound content as hostile.
- Base URL must be canonical (www-only) and redirects are forbidden.
- GET-only endpoint allowlist.
- No raw content persistence (including DMs); metrics/structure only.
- No secrets committed; env-var only; names-only documentation.

### Implementation steps

1. Create the Stage 1–3 Execution Protocol document (JSON authoritative + MD view) with:
   - Threat model
   - Guardrails (fail-closed)
   - Methodology (sampling plan, strata, cadence, bias notes)
   - Provenance chain (what evidence is produced where)
   - Evidence matrix mapping each step to expected artifacts
2. Record scope boundary:
   - Stage 1–3 may be executed live (read-only).
   - Stage 4 remains deferred unless separately authorized and explicitly recorded.
3. Define deterministic, stepwise procedures for:
   - Stage 1 (observe/sample)
   - Stage 2 (hardening verification)
   - Stage 3 (passive canary metrics-only)
   ...without retrieving or storing raw DM bodies.
4. Define required gates and evidence outputs for each procedure (PREFLIGHT/BOD/PRE_JOB/POST_JOB/EOD), aligned to ops-awareness.
5. Define stop conditions (fail-closed): redirect seen, non-www host, non-JSON content-type, unexpected endpoints, sentinel triggers.
6. Execute the documented Stage 1–3 procedure(s) and confirm real obfuscated JSONL outputs are produced.
7. Reconcile the Stage 4 strategy document with this scope boundary and record an explicit decision (remain deferred unless separately authorized).

## Requirements

- Academic reproducibility: methodology, provenance chain, and procedural steps must be explicit and repeatable.
- Only document-planned actions are permitted; execution must match the written protocol exactly.
- Stage scope limited to 1–3; Stage 4 deferred and must not be activated by default.
- Host isolation: treat Moltbook as hostile; minimize host attack surface.
- No secrets, tokens, private identifiers, or raw content in docs or logs.

## Acceptance criteria

- A Stage 1–3 Execution Protocol document exists (JSON authoritative + MD view) under project planning.
- Protocol includes guardrails (www-only, no redirects, GET-only allowlist), threat model, and stop conditions.
- Protocol includes an evidence matrix mapping each step to expected artifacts/paths.
- Stage 1 live run produces obfuscated JSONL telemetry (real data; no raw text) in the designated Calamum logs path.
- Stage 3 canary metrics collection (if executed) produces metrics-only logs (no DM bodies) in the designated Calamum logs path.
- Protocol explicitly documents Stage 4 deferral and the condition for re-activation (explicit governance exception + human signoff).

## Validation

- [ ] Names-only review (no secrets; no sensitive identifiers)
- [ ] JSON authoritative and MD view agree
- [ ] Stage 4 deferral is explicit and unambiguous
- [ ] Live run evidence exists (obfuscated JSONL outputs; no raw content)

## SEAM analysis

### Security
- Fail-closed guardrails; strict endpoint/host allowlists; treat feed as hostile input.
- No raw content export; obfuscation-only telemetry.
- No secrets in repo; env-var only; names-only docs.

### Efficiency
- A single authoritative protocol reduces drift and rework.

### Awareness
- Evidence matrix + gate mapping ensures auditable provenance.
- Explicit Stage boundary definition prevents scope creep.

### Minimalism
- Prefer existing VAULT templates and existing Calamum job artifacts; add only the minimum new protocol needed.

## Rollback plan

Archive-first rollback:
- If the observer is running, stop the container/process.
- Preserve produced logs for academic provenance.
- If a configuration/artifact must be retired, move it to `quarantine_legacy_archive/` (never delete).

## Verification

- Manual review: confirm no secrets/identifiers and that Stage 4 is explicitly deferred.
- Consistency check: JSON authoritative and MD view agree on steps, guardrails, and evidence paths.

## References

- Plan: `projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_OBSERVER_EXPERIMENT_PLAN_20260201.json`
- Stage 4 strategy doc (conflict must be reconciled): `projects/calamum-moltbook-observer/planning/CALAMUM_LIVE_DEPLOYMENT_STRATEGY_20260202.md`
- VAULT job template: `codesentinel/assets/VAULT_templates/reports/JOB_TEMPLATE.*.template`
- VAULT planning aid: `codesentinel/assets/VAULT_templates/job_complexity_templates/pre_job_planning.md`
