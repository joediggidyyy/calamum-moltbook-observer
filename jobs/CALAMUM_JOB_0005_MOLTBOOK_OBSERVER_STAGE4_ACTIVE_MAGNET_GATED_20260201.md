# Job: CALAMUM_JOB_0005 - Moltbook Observer - Stage 4: Live Wire (Live Data Collection)

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `completed`
- Owner: `ORACL-Prime`
- Created: `2026-02-01`
- Project: `calamum / security experiment`
- Phase: `execution`
- Priority: `P1`
- Depends on: `CALAMUM_JOB_0004`
- Blocks: `(none)`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`
- `CALAMUM_LIVE_DEPLOYMENT_STRATEGY_20260202.md`

## Redaction palette

- Secrets:
	- `<magnet_account_credentials_redacted>`
- Identifiers:
	- `<magnet_handle_redacted>`

## Summary

Transition from Simulation to Live Data Collection ("Operation Live Wire"). This job covers the enabling of the live API client (`GET` only) and the collection of real-world "Toxic Waste" data using the Stage 2 Hardened Container.
*Note: The "Active Magnet" (Posting) component remains GATED and optional pending further specific approval.*

## Status update (compact)

```text
STATUS_UPDATE_V2
job.id=calamum-moltbook-observer-stage4-20260201
job.doc=CodeSentinel/projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0005_MOLTBOOK_OBSERVER_STAGE4_ACTIVE_MAGNET_GATED_20260201.md
ssot.path=CodeSentinel/operations/tasks.json
ssot.status=completed
qs.id=QS-CALAMUM-MOLTBOOK-OBSERVER-STAGE4-20260201
qs.doc=projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-STAGE4-20260201.md
qf.id=QF-CALAMUM-MOLTBOOK-OBSERVER-STAGE4-20260201
gates.last=POST_JOB@2026-02-03
evidence.gates=CodeSentinel/logs/behavioral/gates/gate_events.jsonl
evidence.qs=logs/data/calamum/moltbook_live_metrics.jsonl
next.action=Monitor weekly logs; await Stage 5 authorization.
```

## Problem statement

**Current state**:
- System validated in simulation ("Dreaming Mode").
- Target platform is volatile; historical data loss risk is high.

**Root cause**:
- No live connection established.

**Impact**:
- Losing critical dataset for DATA780 analysis.

## Methodology: Operation "Live Wire"

This job executes the "Live Wire" strategy: the immediate transition from simulation to live data collection against the Moltbook API. This decision is driven by the high volatility of the target platform and the need to preserve ephemeral data for DATA780 analysis.

### 1. Operational Readiness Assessment (ORA)
Before authorization, the system was evaluated against the "Safety Onion" architecture:
- **Safety Core (`obfuscator_lib`)**: **PASSED** (Validated in simulation; strips PII/Malware).
- **Containment (Stage 2)**: **PASSED** (Immutable Container / Read-Only Rootfs).
- **Governance (`sentinel.py`)**: **PASSED** (Fail-Closed Watchdog active).
- **Verdict**: The system is safe to conduct "Live Fire" read-only operations.

### 2. Deployment Protocol ("The Hot-Wire")
To execute this transition while maintaining academic reproducibility and security:

1.  **Interface Activation (The Code Switch)**: The `src/moltbook_client.py` simulation stub is replaced with a live REST adapter using `requests`. **Constraint**: The client must strictly adhere to `GET` requests only.
2.  **Credential Injection (Air-Gapped)**: Real credentials (`MOLTBOOK_API_KEY`) are injected via exported environment variables (preferred) or a local-only `projects/calamum-moltbook-observer/.env` file (project root), ensuring no secrets are ever committed to the repository.
	- Note: Calamum does not auto-load dotenv files; the operator must explicitly load/export env vars.
3.  **Execution (Glass Box)**: The system launches using the Stage 2 containment script (`deployment/secure_run.ps1 -Mode live`), ensuring the runtime remains ephemeral and immutable.

### 3. Strategic Justification
Historical data capture is prioritized over perfect feature completeness ("Smash and Grab" tactics authorized). The risk of platform evaporation necessitates this immediate deployment.

## Proposed solution

### Architecture

```
Live API (GET) -> MoltbookClient -> Obfuscator -> logs/calamum/moltbook_samples_obfuscated.jsonl
```

### Implementation steps

1. Enable `requests` in `moltbook_client.py`.
2. Inject air-gapped credentials via exported env vars (or project-root `.env`).
3. Launch `secure_run.ps1 -Mode live`.
4. Monitor via Sentinel.

## Requirements

- **GET-ONLY** Protocol (No posting without secondary approval).
- **Air-Gapped Credentials** (Never committed).
- **Fail-Closed** Sentinel active.

## Acceptance criteria

- Live JSONL logs flowing.
- No Sentinel kills (false positives).
- Data confirmed obfuscated.

## Validation

- [x] Check Policy Exception (`CALAMUM_LIVE_DEPLOYMENT_STRATEGY_20260202.md`)
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
