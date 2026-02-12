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
  - `CALAMUM_JOB_0018` (KEYSMITH: sandboxed key minting; humans never handle secrets)
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

## Implementation delta (deviation record; names-only)

This job was scoped as **ops/config + validation only** (no source changes). During execution, a minimal observer-agent wiring change was performed to align validation with the canonical live metrics filename expected by Stage 4 / this job.

Machine record (authoritative):
- `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0017_MOLTBOOK_OBSERVER_LIVE_COLLECTION_ROADMAP_20260211.json` (`implementation_delta`)

Recorded commit (names-only):
- `eeba7f35`

Validation noted (names-only):
- Project test suite passed under `projects/calamum-moltbook-observer/src/tests`

Narrative + provenance (publish-grade pointers):
- QuestStack: `projects/calamum-moltbook-observer/queststacks/QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211.md`
- Job report: `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVER-LIVE-COLLECTION-ROADMAP-20260211.md`

External links visited (public):

- Durable ledger (SSOT): `docs/external/AGENT_EXTERNAL_LINKS_VISITED_LEDGER.md` (see 2026-02-11 entries)
- Links provided by primary stakeholder (captured 2026-02-11):
  - https://www.technologyreview.com/2026/02/09/1132537/a-lesson-from-pokemon/
  - https://www.webpronews.com/moltbook-and-the-grand-illusion-how-a-social-network-for-bots-became-the-internets-most-revealing-mirror/
  - https://www.msn.com/en-in/money/topstories/moltbook-hype-unravels-viral-posts-were-human-written-not-ai-finds-mit-technology-review/ar-AA1VTUsR?apiversion=v2&domshim=1&noservercache=1&noservertelemetry=1&batchservertelemetry=1&renderwebcomponents=1&wcseo=1
  - https://github.com/openclaw/openclaw
  - https://steipete.me/
  - https://openclaw.ai/

Safety note: the stakeholder reported a PowerShell script download prompt was blocked/rejected while reviewing OpenClaw install guidance. Treat any one-liner installer that downloads a script as executable code; do not run `iwr ... | iex` without inspection.

## Preflight checklist (no code changes)

1) Confirm this environment is intended to run LIVE today.
2) Confirm the operator has access to a **non-human secret handling path** for `MOLTBOOK_API_KEY` (KEYSMITH + sealed drop + VAULT/OS import).
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
- `MOLTBOOK_API_KEY` (populated via KEYSMITH sealed drop + VAULT/OS import; humans must not view/copy/paste the key)

Recommended:
- `MOLTBOOK_HOST` (if non-default is required)
- `CALAMUM_ACTIVE_MAGNET_THRESHOLD` (if Stage 4 threshold gating is in effect)

Notes:
- A project `.env.example` exists; Calamum does **not** auto-load dotenv.
- Use operator-controlled VAULT/env tooling to load env vars.
- KEYSMITH flow (claim-url only humans; sealed secret handoff):
  - Job: `projects/calamum-moltbook-observer/jobs/CALAMUM_JOB_0018_MOLTBOOK_KEYSMITH_IMPLEMENTATION_20260212.md`
  - Plan: `projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_KEYSMITH_IMPLEMENTATION_PLAN_20260212.md`

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
