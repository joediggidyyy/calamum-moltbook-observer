# Calamum Ops Parameters Report - Schema Notes

This document describes the *computed fields* and *derived tables* emitted by the Calamum operations parameters report:

- Generator: `projects/calamum-moltbook-observer/tools/report_ops_parameters.py`
- Template: `projects/calamum-moltbook-observer/template_library/reports/CALAMUM_OPS_PARAMETERS_REPORT_TEMPLATE.md.template`

## Safety constraints

- **Names-only**: the report may include counts, sizes, mtimes/ages, and hashes, but must not include semantic payload content.
- **No secrets**: environment variables are reported as names-only signals (presence + mode). Values are never printed.
- **Project-local output**: output is constrained under `projects/calamum-moltbook-observer/local_untracked/`.

## Tables in the markdown report

## Environment section

The report includes an **Environment** block rendered from `{{ env_vars_block }}`.

Semantics:
- Calamum path variables are treated as **optional overrides**. If not set, the report will show `default` and include the **effective** resolved path.
- Moltbook variables are treated as **feature flags**:
  - If `MOLTBOOK_API_KEY` is not set, Moltbook is considered **disabled**.
  - If Moltbook is enabled, `MOLTBOOK_HOST` should be set; otherwise the report emits a WARN note.

This section is designed to be useful for **scheduled runs**: it confirms which configuration/profile the job actually executed under without exposing secret values.

### Figures of interest

Rendered from `{{ figures_of_interest_block }}`.

Metrics are computed from:
- `logs/data/calamum/*.jsonl` (active telemetry)
- `logs/data/calamum/archive/manifest.json` (archived telemetry)
- `logs/health/*.heartbeat` (liveness)

Current fields:
- **Active telemetry records (sum)**: sum of newline-counted records across `*.jsonl` in the active data directory.
- **Archived telemetry records**: sum of `records` across `archive/manifest.json` entries.
- **Total telemetry records**: active + archived.
- **Active telemetry size**: sum of sizes of active `*.jsonl`.
- **Active bytes/record**: `active_bytes_total / active_records_total` (active only).
- **Freshest/Stalest telemetry age_s**: min/max age since last modification (mtime-derived) across active `*.jsonl`.
- **Archive manifest entries**: number of entries in `archive/manifest.json`.
- **Freshest/Stalest heartbeat age_s**: min/max age since last modification across heartbeat files.
- **Stray artifacts (scout)**: number of suspicious artifacts found under the project tree, excluding `logs/` and `local_untracked/`.

### Collection density (derived)

Rendered from `{{ collection_density_block }}`.

Definition:
- **Collection density** here means *records per second* estimated from the delta between two report runs.

Computation:
- The report maintains a local provenance log at `local_untracked/audit_log/ops_parameters_report.jsonl`.
- Each run appends a `kind="snapshot"` record with a small `metrics` object.
- If a prior snapshot exists *and includes metrics*, the report computes:
  - $\Delta\text{active\_records} / \Delta t$ (active-only rate)
  - $\Delta\text{total\_records} / \Delta t$ (active+archived rate)
- If a baseline exists (`--set-baseline`), the report also computes since-baseline rates.

Caveats:
- Rates are **report-to-report** estimates, not an exact real-time ingestion rate.
- If the provenance file contains older snapshots without metrics (from earlier tool versions), density will show `(n/a)` until a metrics-carrying snapshot has been written.

### Future data points (placeholders)

Rendered from `{{ future_placeholders_block }}`.

These are intentionally `TBD` rows that reserve space for metrics expected in later phases (labeling coverage, signature verification, model baseline performance, drift, anomaly rates). They are placeholders only and should not be interpreted as missing data unless the corresponding pipeline stage is active.

## Evidence JSON fields

The evidence bundle written alongside the report includes:

- `derived_metrics` (dict)
  - `active_records_total`
  - `archived_records_total`
  - `total_records`
  - `active_bytes_total`
  - `active_bytes_per_record`
  - `freshest_telemetry_age_s`, `stalest_telemetry_age_s`
  - `freshest_heartbeat_age_s`, `stalest_heartbeat_age_s`
  - `active_records_by_file` (counts keyed by filename)
  - `density_since_previous` (derived delta object)
  - `density_since_baseline` (derived delta object)

## Provenance JSONL schema

Each run appends:

- `kind="snapshot"` with:
  - `timestamp_utc`, `run_id`, `auditor`
  - `report`, `evidence`, `overall_status`
  - `metrics`:
    - `active_records_total`, `archived_records_total`, `total_records`
    - `active_bytes_total`
    - `active_records_by_file`

If invoked with `--set-baseline`, the run additionally appends:

- `kind="baseline"` (same fields + `baseline_id`)
