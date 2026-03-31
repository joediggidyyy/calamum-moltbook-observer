# Generated Report Surfaces

**Document ID**: `CALAMUM_GENERATED_REPORT_SURFACES_20260324`
**Status**: Public generated-report reference
**Owner**: ORACL-Prime
**Project**: Calamum Moltbook Observer
**Last updated**: 2026-03-24

## Purpose

This document explains the generated report families used by Calamum Moltbook Observer.

It is the public **when / why / how** reference for generated reporting.

It is the public-facing contract for:

- which report families exist
- when each family is produced
- why each family exists
- how each family is produced and retained
- how untracked runtime ledgers should be structured

Most generated report artifacts remain untracked runtime outputs. The DS lane also publishes a curated tracked reader subtree under `docs/reports/ds/` derived from the canonical untracked DS run spine.

Use the companion report references alongside this document:

- [`ds/INDEX.md`](ds/INDEX.md) for curated DS report packs and DS aggregate rollups derived from the canonical DS run spine
- [`PUBLIC_RUN_LEDGER.md`](PUBLIC_RUN_LEDGER.md) for the public register of run families and authoritative evidence surfaces
- [`AGGREGATE_REPORT_SCHEMA.md`](AGGREGATE_REPORT_SCHEMA.md) for the schema governing future public aggregate reports

When runtime lane data is available, the public reporting surfaces should foreground runtime evidence aggregates before audit-family rollups.

## Retention model

Calamum uses three distinct report surfaces:

| Surface | Role | Retention model |
|---|---|---|
| Tracked public reports | Publishable, reader-facing reference artifacts | Committed under `docs/reports/` |
| Tracked DS publication packs | Curated per-run DS report packs plus DS aggregate rollups derived from the canonical DS run spine | Committed under `docs/reports/ds/` |
| Untracked generated reports | Per-run operational, audit, and probe outputs | Written under `local_untracked/` or `report_tmp/` |
| Runtime ledgers | Append-only run history for generated report families | Written as JSONL under the family output root |

## DS publication lane

The DS reporting lane now uses a dual-surface publication model:

| DS surface | Role | Authority |
|---|---|---|
| Canonical untracked DS run bundle | Per-run operational source of truth for report payloads, manifests, and runtime artifacts | `local_untracked/analysis/runs/<workflow>/<run_id>/` |
| DS run ledger and latest pointer | Append-only history plus convenience latest surface for DS runs | `local_untracked/analysis/indexes/ds_run_index.jsonl` and `local_untracked/analysis/indexes/ds_latest.json` |
| Curated tracked DS report packs | Reader-facing per-run report packs and aggregate rollups | `docs/reports/ds/` derived from the canonical DS run spine |

Tracked DS publication stays reader-facing and derived. It does not replace the canonical untracked DS run bundle or the append-only DS run ledger.

## Runtime evidence aggregate sources

These sources are not long-horizon family ledgers, but they are the highest-value public-safe inputs for reporting the current live posture of the collection system. Public-facing aggregate reports should place these runtime evidence summaries near the top of the document, above audit-family synthesis.

| Runtime source | When it is produced | Why it exists | How it is produced |
|---|---|---|---|
| `observerctl health full --json` | On demand during runtime inspection | To report current source/mode posture, gate readiness, watchdog state, baseline-monitor state, and critical readiness surfaces | `src/observerctl.py` composes live runtime status, gate posture, baseline readiness, librarian state, watchdog status, and policy validation into a single public-safe snapshot |
| `observerctl librarian stats --json` | On demand during runtime inspection | To report per-mode record counts, archive totals, retention posture, and current ingest-lane distribution | `src/observerctl.py` calculates store, archive, and derived-session counts per mode and emits a public-safe JSON census |
| `logs/data/calamum/observer_derived/<source>/<mode>/...` | Continuously during observer activity | To retain the machine-readable evidence packets and metrics streams that the runtime summaries are describing | Observer runtime and baseline-monitor flows write lane-scoped evidence under the `observer_derived/<source>/<mode>/` tree |

## Threshold calibration coverage

Threshold calibration currently appears as a compact subsection inside [`AGGREGATE_REPORT.md`](AGGREGATE_REPORT.md).

Current public direction:

- publish the threshold, FPR, and score-distribution summary inside [`AGGREGATE_REPORT.md`](AGGREGATE_REPORT.md)
- treat threshold calibration as part of the aggregate report surface
- defer broader model-eval aggregation until the observer has successfully run in each mode and the final pre-ship lockdown lane is complete

## Generated operational report families

These families write human-readable Markdown plus machine-readable evidence bundles and append-only provenance logs.

| Report family | Primary outputs | When it is produced | Why it exists | How it is produced |
|---|---|---|---|---|
| Operations parameters report | `local_untracked/reports/ops_parameters/calamum_ops_parameters_report_<timestamp>.md` plus `.evidence.json` | During runtime review, profile verification, or scheduled operational checks | To capture the effective runtime profile, heartbeat posture, telemetry density, path safety, and output discipline without printing secrets | `tools/report_ops_parameters.py` writes the report and evidence, appends a snapshot or baseline entry to `local_untracked/audit_log/ops_parameters_report.jsonl`, and refreshes the latest pointer in `local_untracked/audit_log/audit_index.json` |
| Runtime artifacts audit | `local_untracked/audits/runtime/calamum_runtime_artifacts_audit_<timestamp>.md` plus `.evidence.json` | During runtime artifact inspection or watchdog health review | To inventory runtime heartbeats, telemetry files, control signals, service logs, output safety, and optional stray-artifact findings | `tools/audit_runtime_artifacts.py` writes the report and evidence, appends to `local_untracked/audit_log/runtime_artifacts_audit.jsonl`, and updates `audit_index.json` |
| Repo health audit | `local_untracked/audits/repo_health/calamum_repo_health_audit_<timestamp>.md` plus `.evidence.json` | During repo hygiene, layout, and policy verification | To verify tracked-versus-untracked boundaries, ignore-policy expectations, manifest presence, and status-sync hygiene | `tools/audit_repo_health.py` writes the report and evidence, appends to `local_untracked/audit_log/repo_health_audit.jsonl`, and updates `audit_index.json` |
| Implementation drift audit | `local_untracked/audits/implementation_drift/implementation_drift_audit_<timestamp>.md` plus `.evidence.json` | During contract and status drift review | To compare declared behavior against actual repo state, including SSOT status sync, watchdog script integrity, instruction-pair integrity, manifest layout, and changed-file unit-test presence | `tools/audit_implementation_drift.py` writes the report and evidence, appends to `local_untracked/audit_log/implementation_drift_audit.jsonl`, and updates `audit_index.json` |
| GUI audit | `local_untracked/audits/gui/calamum_gui_audit_<timestamp>.md` plus `.evidence.json` | During dashboard reachability or presentation verification | To verify dashboard availability, diagnostics endpoints, branding tile presence, and network-safe probe results | `tools/audit_calamum_gui.py` writes the report and evidence, appends to `local_untracked/audit_log/gui_audit.jsonl`, and updates `audit_index.json` |

## Generated sandbox and probe report families

These families produce per-run validation packets under `report_tmp/`. Each family keeps its own append-only `run_index.jsonl` ledger.

| Report family | Primary outputs | When it is produced | Why it exists | How it is produced |
|---|---|---|---|---|
| Metadata contract probe | `report_tmp/frame4_metadata_contract_probe/runs/<run_id>/frame4_metadata_probe.json` and `.md` | When validating normal and baseline metadata contract fields | To prove the retained metadata contract is present for the expected resource rows and indexes | `src/simulation/run_simulation.py` via `observerctl sandbox run metadata-contract`; the family ledger is `report_tmp/frame4_metadata_contract_probe/run_index.jsonl` |
| Metadata contract regression probe | `report_tmp/frame4_metadata_contract_regression_probe/runs/<run_id>/frame4_metadata_contract_regression_probe.json` and `.md` | When validating negative-path regression detection | To prove known-bad metadata rows are flagged as contract regressions | `src/simulation/run_simulation.py` via `observerctl sandbox run metadata-contract-regression`; the family ledger is `report_tmp/frame4_metadata_contract_regression_probe/run_index.jsonl` |
| Baseline monitor runtime probe | `report_tmp/job0022_baseline_monitor_runtime_probe/runs/<run_id>/job0022_baseline_monitor_runtime_probe.json` and `.md` | When validating sandboxed baseline-monitor runtime continuity | To prove baseline-monitor runtime liveness and retained `resource_normal` continuity | `src/simulation/run_simulation.py` via `observerctl sandbox run baseline-monitor-runtime`; the family ledger is `report_tmp/job0022_baseline_monitor_runtime_probe/run_index.jsonl` |
| Validation cycle lineage probe | `report_tmp/frame5_validation_cycle_lineage_probe/runs/<run_id>/frame5_validation_cycle_lineage_probe.json` and `.md` | When validating append-only validation-cycle growth | To prove later validation cycles correctly reference earlier cycles, baseline packets, and analysis packets | `src/simulation/run_simulation.py` via `observerctl sandbox run validation-cycle-lineage`; the family ledger is `report_tmp/frame5_validation_cycle_lineage_probe/run_index.jsonl` |
| Restart continuity probe | `report_tmp/frame6_restart_continuity_probe/runs/<run_id>/frame6_restart_continuity_probe.json` and `.md` | When validating resumed monitor continuity | To prove continuity anchors survive restart and resume flows without inventing replacement baseline artifacts | `src/simulation/run_simulation.py` via `observerctl sandbox run baseline-monitor-restart-continuity`; the family ledger is `report_tmp/frame6_restart_continuity_probe/run_index.jsonl` |
| State recovery probe | `report_tmp/frame6_state_recovery_probe/runs/<run_id>/frame6_state_recovery_probe.json` and `.md` | When validating degraded-state recovery behavior | To prove malformed persisted monitor state is surfaced explicitly and normalized on writeback | `src/simulation/run_simulation.py` via `observerctl sandbox run baseline-monitor-state-recovery`; the family ledger is `report_tmp/frame6_state_recovery_probe/run_index.jsonl` |

## Canonical runtime ledger model

The existing codebase already follows a good pattern:

1. emit a per-run human-readable report
2. emit a machine-readable evidence bundle
3. append a JSONL ledger entry for history
4. refresh a latest-pointer index for convenience

That pattern should remain the standard.

### Authoritative surfaces

Use the following authority order:

1. **Per-family append-only JSONL ledger** is the authoritative run history
2. **Per-run evidence JSON** is the authoritative machine-readable run payload
3. **Per-run report Markdown or JSON** is the reader-facing run summary
4. **`audit_index.json`** is a convenience latest-pointer surface, not the historical authority

### Required ledger fields

Every generated report family should expose the following core fields in its append-only ledger entries, even if some families also carry family-specific fields.

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Version of the ledger contract used for the entry |
| `kind` | string | Entry kind such as `snapshot`, `baseline`, or `run` |
| `family_id` | string | Stable family identifier such as `ops_parameters`, `runtime_artifacts`, or `metadata_contract_probe` |
| `category` | string | High-level class such as `ops-report`, `audit`, `probe`, or `model-eval` |
| `timestamp_utc` | string | RFC 3339 UTC timestamp for the run |
| `run_id` | string | Stable per-run identifier |
| `producer_command` | string | Canonical command surface used to produce the run |
| `producer_entrypoint` | string | Script or module path that emitted the run |
| `report_paths` | object | Repo-relative paths for the human-readable report and any machine-readable companions |
| `ledger_path` | string | Repo-relative path of the append-only family ledger |
| `latest_index_path` | string | Repo-relative path of the latest-pointer index when one exists |
| `git` | object | `head`, `branch`, and `is_dirty` for provenance |
| `result` | object | Outcome summary such as `status`, `summary`, `overall_status`, or `next_bite_result` |
| `context` | object | Runtime context such as `source`, `mode`, `event`, `profile`, or `window_id` when applicable |
| `lineage` | object | Optional links to prior run ids, baseline ids, or prior packet paths |

### Recommended family identifiers

Use stable snake-case identifiers for cross-family consistency:

- `threshold_selection`
- `ops_parameters`
- `runtime_artifacts`
- `repo_health`
- `implementation_drift`
- `gui`
- `metadata_contract_probe`
- `metadata_contract_regression_probe`
- `baseline_monitor_runtime_probe`
- `validation_cycle_lineage_probe`
- `restart_continuity_probe`
- `state_recovery_probe`

### Recommended JSON shape

A professional default entry shape is:

- keep paths repo-relative with forward slashes
- keep timestamps UTC and RFC 3339
- keep history append-only
- keep the latest-pointer index separate from the historical ledger
- add family-specific metrics under `result` or `context` instead of inventing parallel top-level schemas per family

Example shape:

```json
{
  "schema_version": "1.0",
  "kind": "snapshot",
  "family_id": "ops_parameters",
  "category": "ops-report",
  "timestamp_utc": "2026-03-24T13:00:03.746231Z",
  "run_id": "c3817e6424f3422387e1daae9b4421eb",
  "producer_command": "python projects/calamum-moltbook-observer/tools/report_ops_parameters.py",
  "producer_entrypoint": "projects/calamum-moltbook-observer/tools/report_ops_parameters.py",
  "report_paths": {
    "markdown": "projects/calamum-moltbook-observer/local_untracked/reports/ops_parameters/calamum_ops_parameters_report_20260324T130003746231Z.md",
    "evidence": "projects/calamum-moltbook-observer/local_untracked/reports/ops_parameters/calamum_ops_parameters_report_20260324T130003746231Z.evidence.json"
  },
  "ledger_path": "projects/calamum-moltbook-observer/local_untracked/audit_log/ops_parameters_report.jsonl",
  "latest_index_path": "projects/calamum-moltbook-observer/local_untracked/audit_log/audit_index.json",
  "git": {
    "head": "<sha>",
    "branch": "main",
    "is_dirty": false
  },
  "result": {
    "status": "err",
    "summary": "effective runtime profile captured"
  },
  "context": {
    "source": "scheduled",
    "mode": "runtime-audit"
  },
  "lineage": {}
}
```

## Recommended operational rules

- Keep generated reports untracked.
- Keep family ledgers append-only.
- Keep `audit_index.json` as a convenience latest-pointer surface only.
- Keep evidence JSON machine-readable and report Markdown reader-friendly.
- Keep filenames timestamped and family-specific.
- Keep family ids stable so dashboards and future automation can rely on them.

## Related surfaces

- [`INDEX.md`](INDEX.md)
- [`ds/INDEX.md`](ds/INDEX.md)
- [`PUBLIC_RUN_LEDGER.md`](PUBLIC_RUN_LEDGER.md)
- [`AGGREGATE_REPORT_SCHEMA.md`](AGGREGATE_REPORT_SCHEMA.md)
- [`../manuals/INDEX.md`](../manuals/INDEX.md)
- [`../../README.md`](../../README.md)
- [`../../DATA_METHODOLOGY.md`](../../DATA_METHODOLOGY.md)
