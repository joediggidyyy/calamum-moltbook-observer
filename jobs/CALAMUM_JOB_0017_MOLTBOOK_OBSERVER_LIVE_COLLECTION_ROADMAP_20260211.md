# Job: CALAMUM_JOB_0017 - Moltbook Observer - Live Collection Roadmap (Honeypot Activation)

## Metadata

- Template ID: `VAULT_TEMPLATE_JOB_V1`
- Paired authoritative template: `JOB_TEMPLATE.json.template`
- Status: `open`
- Owner: `ORACL-Prime`
- Created: `2026-02-11`
- Project: `calamum / moltbook observer`
- Phase: `execution`
- Priority: `P0`
- Depends on:
  - `CALAMUM_JOB_0015` (Stage 4 Activation)
  - `CALAMUM_JOB_0005` (Stage 4 Live Wire strategy)
- Blocks: `(none)`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`

## Summary

Bring the backend into **LIVE COLLECTION** mode today ("honeypot active and collecting"). This is an **ops/config + validation** job: no new backend source work is authorized. The deliverable is a verified state where:

- Observer chain is alive (agent/librarian/watchdog/ghost console).
- Live ingestion is enabled via env var injection (air-gapped).
- Live metrics/samples are flowing and fresh.
- Critical failures (security trigger, observer down, watchdog down) generate **Windows popup alerts**.

## Operator intent note (future GUI pivot)

When we pivot back to Calamum GUI:

- Add a thin UI border that **glows faint yellow** when WARN signals are active.
- Border **flashes red** when CRITICAL.

(Implementation deferred; record only.)

## Current state (evidence)

- Backend processes running and heartbeats updating, but **agent is in CANARY mode**.
- Live credentials/config were not present in environment at time of audit.

Evidence artifacts:
- `report_tmp/calamum_moltbook_backend_diag_20260211T184713Z.md`
- `report_tmp/calamum_job_status_audit_20260211T190142Z.md`

## Preflight checklist (no code changes)

1) Confirm this environment is intended to run LIVE today.
2) Confirm the operator has access to air-gapped credentials for `MOLTBOOK_API_KEY`.
3) Confirm network constraints are understood (ICMP disabled; use TCP/SSH checks only).

## Execution steps

### Step 1 — Resolve “pipeline jobs complete?” mismatch (paperwork clarity)

Run the job status audit and record results:
- `semantics_staging/calamum_job_status_audit.py`

As of 2026-02-11, the following are **not recorded as complete/closed**:
- `CALAMUM_JOB_0007_MOLTBOOK_OBSERVER_REMEDIATION_EXECUTION` (missing status)
- `CALAMUM_JOB_0007_MOLTBOOK_OPS_WIDGET_IMPLEMENTATION_20260203` (status=active)
- `CALAMUM_JOB_0011_ACTIVE_LOGGING_KEEPALIVE_AND_BLIND_ML_EXECUTION_20260210` (status=OPEN)
- `CALAMUM_JOB_0013_MOLTBOOK_OBSERVER_INFERENCE_IMPL_20260210` (status=OPEN)

Decision needed:
- If these are *truly complete*, update their statuses in their job docs.
- If these are *out of scope* for live collection, explicitly mark them as non-blocking for this job.

### Step 2 — Inject live-collection env vars (air-gapped)

Required (presence only; never commit values):
- `MOLTBOOK_API_KEY`

Recommended:
- `MOLTBOOK_HOST` (if non-default is required)
- `CALAMUM_ACTIVE_MAGNET_THRESHOLD` (if Stage 4 threshold gating is in effect)

Notes:
- A project `.env.example` exists; Calamum does **not** auto-load dotenv.
- Use operator-controlled env export / vault tooling to load env vars.

### Step 3 — Validate backend flips out of CANARY mode

Observe:
- `projects/calamum-moltbook-observer/logs/calamum_agent.stdout.log` should stop reporting `mode=CANARY`.

Validate fresh data:
- `projects/calamum-moltbook-observer/logs/data/calamum/moltbook_live_metrics.jsonl` becomes non-empty and updates.
- `projects/calamum-moltbook-observer/logs/data/calamum/moltbook_samples_obfuscated.jsonl` continues updating.

### Step 4 — Enable CRITICAL-only Windows popup alerts

Use the alert watcher in loop mode for the live window:
- `semantics_staging/calamum_proactive_alert_watch.py --loop --interval-sec 30 --freshness-sec 600 --popup-critical`

CRITICAL conditions targeted:
- Security trigger (intrusion log updated recently)
- Watchdog heartbeat stale/missing
- Required process missing

### Step 5 — Capture an end-state diagnostics bundle

Run:
- `semantics_staging/calamum_moltbook_backend_diag.py`

Attach resulting `report_tmp/` artifacts to the execution report.

## Acceptance criteria

- [ ] `MOLTBOOK_API_KEY` present in env at runtime (presence check)
- [ ] Agent mode is not CANARY
- [ ] Live metrics file is non-empty and fresh
- [ ] No CRITICAL alerts during steady-state (or CRITICAL alert is investigated and explained)
- [ ] A diagnostics report exists in `report_tmp/` proving the state

## Deliverables

- Evidence reports under `report_tmp/`:
  - backend diag JSON+MD
  - job status audit JSON+MD
  - alert outbox JSONL (if used)
- (Optional) Execution report for this job once completed
