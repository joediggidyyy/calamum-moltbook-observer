# Public Run Ledger

**Document ID**: `CALAMUM_PUBLIC_RUN_LEDGER_20260324`
**Status**: Public ledger starter
**Owner**: ORACL-Prime
**Project**: Calamum Moltbook Observer
**Last updated**: 2026-03-24
**Observation point**: `2026-03-24T21:09:26.020961Z`
**Runtime snapshot source surfaces**: `observerctl health full --json`; `observerctl librarian stats --json`

## Purpose

This starter ledger makes the current reporting surface legible without checking routine runtime artifacts into git. It foregrounds the current runtime evidence aggregate first and then places audit-family and report-family rollups underneath that runtime headline.

The authoritative histories remain the append-only ledgers in `local_untracked/audit_log/`. This tracked document provides a disciplined public snapshot of those histories.

## How to read this ledger

This ledger has two jobs.

1. It shows the **current runtime evidence aggregate** for the live collection surface.
2. It summarizes the **current lane census** across the runtime modes.
3. It then records the **size and current posture** of the public audit/report-family ledgers so later aggregate reporting has a stable citation point.

The table below should be read as a selected public snapshot, not as a substitute for the full append-only histories.

## Current runtime evidence aggregate

| Metric | Value |
|---|---|
| Runtime snapshot observed at | `2026-03-24T21:09:26.020961Z` |
| Current state | `real:canary` |
| Gate decision | `no-go` |
| Posture trigger | `isolation` |
| Active ingest lane | `real:canary` |
| Active lane session records | `45610` |
| Active lane archived records | `369510` |
| Active lane total records displayed | `415120` |
| Archive manifest total records | `369560` |
| Non-mode archive bucket | `unclassified=50` |
| Baseline monitor state | `stopped` |
| Watchdog decision | `no-go` |

## Current runtime lane census

| Mode | Source scope | Ingest active | Session records | Archived records | Total records displayed | Manifest integrity |
|---|---|---|---:|---:|---:|---|
| `watch` | `real` | No | 0 | 0 | 0 | `ok` |
| `canary` | `real` | Yes | 45610 | 369510 | 415120 | `ok` |
| `live` | `real` | No | 0 | 0 | 0 | `ok` |
| `honeypot` | `real` | No | 0 | 0 | 0 | `ok` |

## Audit and report-family ledger census

| Family id | Class | Total entries | Snapshot entries | Baseline entries | Authoritative runtime ledger | Aggregate-ready |
|---|---|---:|---:|---:|---|---|
| `ops_parameters` | ops-report | 658 | 658 | 0 | `local_untracked/audit_log/ops_parameters_report.jsonl` | Yes |
| `runtime_artifacts` | audit | 658 | 658 | 0 | `local_untracked/audit_log/runtime_artifacts_audit.jsonl` | Yes |
| `repo_health` | audit | 664 | 664 | 0 | `local_untracked/audit_log/repo_health_audit.jsonl` | Yes |
| `implementation_drift` | audit | 29 | 20 | 9 | `local_untracked/audit_log/implementation_drift_audit.jsonl` | Yes |
| `gui` | audit | 1 | 1 | 0 | `local_untracked/audit_log/gui_audit.jsonl` | Yes |

## Audit and report-family aggregate summary

Across the five currently summarized public audit/report families, the reporting corpus contains **2,010 total recorded entries**. Of these, **2,001** are snapshots and **9** are baselines.

The latest-status distribution is currently:

- `OK`: 3 families
- `WARN`: 1 family
- `ERR`: 1 family

This means the public reporting surface is neither empty nor cosmetically flattened. It conveys a concrete runtime posture at the top and then a mixed audit-family posture underneath it.

## Interpretive notes

- The highest-value public headline is now the current runtime lane picture: the active ingest lane is `real:canary`, while `watch`, `live`, and `honeypot` currently show zero displayed records.
- The reporting corpus underneath that runtime headline is dominated by the three core operational families: `ops_parameters`, `runtime_artifacts`, and `repo_health`.
- `implementation_drift` and `gui` remain useful public families, but their latest recorded runs are materially older than the March 24 operational cycle.
- Some latest evidence bundles report degraded git metadata because the executing context hit a repository `safe.directory` restriction. Those provenance gaps affect selected git-derived fields, not the run-family counts shown here.
- Probe families remain documented in [`GENERATED_REPORT_SURFACES.md`](GENERATED_REPORT_SURFACES.md), but they are not included in this starter ledger because the present public surface is intended to foreground the main publishable report families.
- The current live runtime evidence shows `real:canary` as the active lane.

## Provenance

Authoritative runtime ledgers:

- `projects/calamum-moltbook-observer/local_untracked/audit_log/ops_parameters_report.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/runtime_artifacts_audit.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/repo_health_audit.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/implementation_drift_audit.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/gui_audit.jsonl`

Supporting latest-run evidence bundles consulted for selected statistics:

- live `observerctl health full --json` packet captured at `2026-03-24T21:09:26.020961Z`
- live `observerctl librarian stats --json` packet captured at `2026-03-24T21:09:16.281289Z`
- `projects/calamum-moltbook-observer/local_untracked/reports/ops_parameters/calamum_ops_parameters_report_20260324T130003746231Z.evidence.json`
- `projects/calamum-moltbook-observer/local_untracked/audits/runtime/calamum_runtime_artifacts_audit_20260324T130505915572Z.evidence.json`
- `projects/calamum-moltbook-observer/local_untracked/audits/repo_health/calamum_repo_health_audit_20260324T131001.009365Z.evidence.json`

## Related surfaces

- [`INDEX.md`](INDEX.md)
- [`AGGREGATE_REPORT.md`](AGGREGATE_REPORT.md)
- [`AGGREGATE_REPORT_SCHEMA.md`](AGGREGATE_REPORT_SCHEMA.md)
- [`GENERATED_REPORT_SURFACES.md`](GENERATED_REPORT_SURFACES.md)
