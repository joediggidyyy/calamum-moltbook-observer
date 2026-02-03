# Plan: Calamum Moltbook Observer: Monitoring Widget (Observer + Sentinel Status and Statistics)

## Metadata

- Template ID: `VAULT_TEMPLATE_PLAN_V1`
- Paired authoritative template: `PLAN_TEMPLATE.json.template`
- Status: `planned`
- Owner: `ORACL-Prime`
- Created: `2026-02-03`

## Policy links

- `PP_GOV_PROTOCOL_POL_CORE_POLICY_20251122`
- `PP_GOV_PROTOCOL_POL_AGENT_ACTION_WORKFLOW_20251122`
- `PP_GOV_PROTOCOL_POL_DETERMINISTIC_WORKFLOW_20251127`
- `PP_SEC_PROTOCOL_POL_AGENT_SOCIAL_NETWORKS_20260201`
- `PP_SEC_VAULT_PROTECTION_20251208`

## Summary

Design a monitoring widget that provides at-a-glance status and statistics for the Calamum Moltbook observer and its watchdog sentinel. The widget must be telemetry-only (no raw content display), must be reproducible, and must integrate cleanly with existing CodeSentinel dashboard/reporting patterns.

## Assumptions

- Observer outputs are written as obfuscated JSONL telemetry under the Calamum logs path.
- Sentinel (watchdog) emits deterministic status signals via logs/stdout suitable for aggregation.
- The operator view should be generated from local artifacts (logs) without any direct interaction with Moltbook.
- Widget controls are local-only operator actions (kill switch, pause/resume, bounded cadence changes) and must be fail-closed with names-only audit events.

## Risks

- Accidental display of raw inbound content (prevent via strict field allowlists).
- Metric drift if log formats evolve without versioning (require schema/version fields and compatibility note).
- Operator overconfidence if the widget reports “healthy” while sampling is stale (must include freshness signals).
- Control-surface risk: kill switch and cadence controls can disrupt collection or mask failures if not designed as explicit, bounded, audited actions.

## Milestones

### Metric inventory and schema

Definition of done:

- A versioned metric schema is defined for observer + sentinel outputs (allowed fields only).
- Each metric is mapped to a concrete source artifact/path and update cadence.

### Widget specification

Definition of done:

- Widget layout and fields are specified (at-a-glance, one screen/panel).
- Redaction and safety constraints are written as acceptance criteria (no raw content; names-only).

### Dashboard integration plan

Definition of done:

- A concrete integration path is selected: a CodeSentinel dashboard panel writer that emits a markdown panel under `docs/dashboards/room/`.
- A target name, output filename, and update trigger strategy are defined.

## Widget requirements (telemetry-only)

### Stop-conditions (fail-closed)

If any stop-condition is met, the widget must fail closed: refuse further control actions, emit a names-only control-event audit record, and surface a clear operator alert.

- Any attempt to display raw inbound content or external identifiers.
- Any non-allowlisted field appears in widget input parsing.
- Freshness exceeds the defined stale threshold while the widget reports “healthy”.
- Any unexpected endpoint/redirect/non-canonical host is detected in upstream telemetry.
- Any out-of-bounds control request (e.g., cadence below min or above max).

### Control-event logging (names-only)

All widget controls are treated as a **high-risk control surface** and must emit structured, names-only audit events.

- Audit sink (JSONL): `logs/behavioral/control_surface/CALAMUM_MOLTBOOK_OBSERVER_WIDGET_CONTROL_EVENTS.jsonl`
- Allowed events (enum):
  - `kill_switch_requested`, `kill_switch_confirmed`
  - `pause_requested`, `resume_requested`
  - `sampling_interval_changed`
  - `rotate_outputs_requested`
  - `export_status_snapshot_requested`
  - `sentinel_alert_acknowledged`
- Disallowed events (never implement): `post_to_moltbook`, `render_raw_content`, `modify_remote_state`

Minimum schema (names-only):

- `ts_utc` (ISO-8601)
- `event` (enum)
- `control_id` (string)
- `requested_by` (`operator` | `system`)
- `confirmed` (bool)
- `reason_code` (allowlisted enum)
- `previous_state` (object; names-only)
- `new_state` (object; names-only)
- `notes` (optional; names-only)

### Controls (base set; proposed)

Controls are local-only operator actions. They must not post to Moltbook, must not render raw inbound content, and must be designed to be fail-closed.

- **Kill switch (required)**: immediate stop of observer + sentinel runtime.
  - Intent: emergency halt if suspicious behavior, unexpected endpoints, or policy violations are detected.
  - Notes: should require an explicit confirmation step and record a names-only audit event (no secrets, no raw content).

- **Pause sampling / Resume sampling**: stop polling without stopping the container/process.
  - Intent: freeze collection while preserving runtime context for debugging.

- **Set sampling interval (bounded)**: adjust polling cadence within a documented safe range.
  - Intent: manage rate limits and resource usage.
  - Notes: enforce min/max bounds; record change as a configuration event.

- **Rotate outputs (safe)**: request a new output shard/file boundary (no deletion).
  - Intent: improve provenance and analysis batching.
  - Notes: archive-first; never delete; maintain monotonic shard numbering.

- **Export status snapshot (telemetry-only)**: write a single, deterministic snapshot record.
  - Intent: lightweight checkpoint for academic provenance.
  - Notes: allowlist fields only.

- **Acknowledge sentinel event (UI-only)**: mark an alert as reviewed.
  - Intent: operator workflow control.
  - Notes: UI-only by default (ephemeral; resets on restart). If persistence is required later, persist names-only acknowledgement state locally and record the write as a structured control-event.

### Display fields (proposed)

Observer:
- Run state: `<running|stopped|unknown>`
- Mode: `<simulation|live>`
- Last sample timestamp (UTC)
- Freshness: seconds since last sample
- Sampling rate (samples/min over a documented window)
- Error rate (errors/min over the same window)
- Output path(s) (repo-relative, names-only)

Sentinel:
- Run state: `<running|stopped|unknown>`
- Last heartbeat timestamp (UTC)
- Kill events count (last 1h / 24h)
- Last kill reason code (allowlisted enum; no raw log lines)

### Time windows and sparse-data semantics (defaults)

To keep outputs deterministic and to avoid over-interpreting tiny samples:

- Sampling rate window: last 10 minutes (rolling).
- Error rate window: last 10 minutes (rolling).
- Kill event windows: last 1 hour and last 24 hours.
- Freshness stale threshold (default): $\max(10\ \text{minutes},\ 3\times\text{sampling_interval})$.

Sparse-data rules:

- If fewer than 3 samples exist in the sampling-rate window, display `insufficient_data` rather than a computed rate.
- If no heartbeat exists within the stale threshold, sentinel state must display `stale` (not `healthy`).

### Non-goals

- No raw Moltbook text or message bodies.
- No rendering of usernames/handles or external identifiers.
- No secrets or credential presence beyond names-only (e.g., `MOLTBOOK_API_KEY` present: true/false).

## Data sources (proposed)

- Observer obfuscated JSONL telemetry: `logs/data/calamum/` (exact filenames to be documented in the execution protocol).
- Sentinel status/kill events: sentinel output stream (to be mapped to a stable metrics JSONL or summarized by a dashboard writer).
- Gate evidence (optional cross-check): `logs/behavioral/gates/gate_events.jsonl`.

### Log roots + filename patterns (pinned)

- Observer telemetry root: `logs/data/calamum/`
  - Suggested pattern: `moltbook_*_obfuscated*.jsonl` (to be finalized in Job 0006 execution protocol).
- Control-event audit sink (widget controls): `logs/behavioral/control_surface/CALAMUM_MOLTBOOK_OBSERVER_WIDGET_CONTROL_EVENTS.jsonl`

## Tasks

- [ ] (1) Define data sources and freshness rules (status: not-started)
  - Evidence:
    - `projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_OBSERVER_MONITORING_WIDGET_PLAN_20260203.json`
    - `projects/calamum-moltbook-observer/planning/CALAMUM_MOLTBOOK_OBSERVER_MONITORING_WIDGET_PLAN_20260203.md`

- [ ] (2) Define metric allowlist (observer + sentinel) (status: not-started)
  - Evidence:
    - (in-document) Metric allowlist + acceptance criteria to be captured in this plan pair.

- [ ] (3) Specify widget layout and panel output (status: not-started)
  - Evidence:
    - (in-document) Widget layout + output contract to be captured in this plan pair.

- [ ] (4) Plan dashboard CLI integration (status: not-started)
  - Evidence:
    - (in-document) Integration notes + output filename/trigger strategy.

- [ ] (5) Specify base control set and safety constraints (status: not-started)
  - Evidence:
    - `logs/behavioral/control_surface/CALAMUM_MOLTBOOK_OBSERVER_WIDGET_CONTROL_EVENTS.jsonl`

- [ ] (6) Complete SEAM analysis and stop-conditions (status: not-started)
  - Evidence:
    - (in-document) Stop-conditions section + SEAM analysis section.

## Success metrics

- Operator can determine within 10 seconds: running/not-running, last successful sample time, sample rate, error rate, and sentinel status.
- Widget displays only aggregated/obfuscated telemetry (no raw Moltbook text; no secrets; no sensitive identifiers).
- Widget includes freshness signals (seconds since last sample and last sentinel heartbeat).
- Widget output is deterministic given the same input artifacts (time window rules documented).

## Notes on integration

- CodeSentinel dashboards live under `docs/dashboards/room/` and are generated via `codesentinel dashboard`.
- Dashboard markdown files in `docs/dashboards/room/` are live-only human outputs and are exempt from the markdown/JSON pair rule.
- This plan defines the widget spec; implementation should follow a separate job with explicit evidence and gates.

## SEAM analysis

### Security

- This widget is a high-risk control surface because it can stop/alter collection. Controls must be fail-closed, require explicit confirmation, and emit names-only audit events.
- Strict metric allowlists prevent accidental display of raw hostile input or sensitive identifiers.
- Any operator-controlled config changes (pause/resume/cadence) must be bounded and logged as structured events.

### Efficiency

- At-a-glance health reduces time-to-detection and avoids manual log forensics for routine checks.
- Bounded controls (pause/resume/cadence) reduce needless restarts and keep runs reproducible.

### Awareness

- Freshness signals (seconds since last sample / last heartbeat) prevent false confidence.
- Kill events and error-rate summaries provide immediate awareness of containment stress or policy guard triggers.

### Minimalism

- Prefer integrating as a single CodeSentinel dashboard panel output rather than introducing new UI frameworks.
- Prefer existing log-derived metrics and stable schemas over bespoke runtime instrumentation.
