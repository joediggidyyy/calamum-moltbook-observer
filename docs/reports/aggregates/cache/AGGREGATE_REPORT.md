# Aggregate Report

**Document ID**: `CALAMUM_AGGREGATE_REPORT_20260324`
**Status**: Public aggregate report starter
**Owner**: ORACL-Prime
**Project**: Calamum Moltbook Observer
**Last updated**: 2026-03-24
**Aggregation window**: Current append-only ledger state observed through `2026-03-24T13:10:01.009365Z`
**Runtime observation point**: `2026-03-24T21:09:26.020961Z`
**Runtime source surfaces**: `observerctl health full --json`; `observerctl librarian stats --json`
**Source families**: `ops_parameters`, `runtime_artifacts`, `repo_health`, `implementation_drift`, `gui`
**Primary question**: What do the current runtime evidence surfaces show about active lane posture and record distribution, and how does that runtime picture relate to the surrounding audit/report-family corpus?

## Executive summary

This starter aggregate report now gives top billing to the current runtime evidence aggregate. The live runtime snapshot shows the active ingest lane is **`real:canary`**, with **45,610 session records** and **369,510 archived records**, for **415,120 displayed records** in the active lane. The named non-active modes (`watch`, `live`, and `honeypot`) currently show zero displayed records, while the archive manifest retains an additional **50 unclassified records**.

The runtime posture currently shows mixed health signals: the current gate posture is **`no-go`**, the baseline monitor is **stopped**, and the watchdog also reports **`no-go`**. Underneath that runtime headline, the audit/report-family corpus remains substantial: it contains **2,010 recorded entries**, of which **2,001** are snapshots and **9** are baselines. The latest-status distribution across the five included public audit/report families is **3 OK**, **1 WARN**, and **1 ERR**.

## Runtime evidence aggregate

| Metric | Value |
|---|---:|
| Active state | `real:canary` |
| Gate decision | `no-go` |
| Posture trigger | `isolation` |
| Active lane session records | 45,610 |
| Active lane archived records | 369,510 |
| Active lane total displayed records | 415,120 |
| Total archive manifest records | 369,560 |
| Unclassified archive records | 50 |

### Current lane census

| Mode | Source scope | Ingest active | Session records | Archived records | Total displayed records |
|---|---|---|---:|---:|---:|
| `watch` | `real` | No | 0 | 0 | 0 |
| `canary` | `real` | Yes | 45,610 | 369,510 | 415,120 |
| `live` | `real` | No | 0 | 0 | 0 |
| `honeypot` | `real` | No | 0 | 0 | 0 |

## Research question

This report asks two related questions. First, what does the current runtime evidence show about the active source/mode lane and its retained record distribution? Second, how does that runtime picture sit inside the broader audit/report-family corpus used for public interpretation?

## Corpus and selection rule

Included corpus:

- live `observerctl health full --json` runtime snapshot
- live `observerctl librarian stats --json` lane census and archive summary
- `local_untracked/audit_log/ops_parameters_report.jsonl`
- `local_untracked/audit_log/runtime_artifacts_audit.jsonl`
- `local_untracked/audit_log/repo_health_audit.jsonl`
- `local_untracked/audit_log/implementation_drift_audit.jsonl`
- `local_untracked/audit_log/gui_audit.jsonl`

Selection rule:

- treat current runtime evidence as the top-level snapshot for active lane posture and lane-level record distribution
- include report families that currently have a public-facing role in the generated reporting surface
- include only parseable append-only JSONL ledgers
- count both snapshot and baseline entries when present
- classify latest family status using the latest recorded summary field available in each family ledger

## Methods

The aggregation method is intentionally simple and auditable:

1. capture the current runtime snapshot from `observerctl health full --json`
2. capture the current per-mode lane census from `observerctl librarian stats --json`
3. count total entries per public audit/report-family ledger
4. count snapshot and baseline entries per family
5. identify the latest recorded run per family
6. classify the latest family summary into `OK`, `WARN`, or `ERR` when a summary token is present
7. compare run-volume concentration across runtime lanes and audit/report families

No raw runtime payloads are republished here. This document aggregates public-safe runtime lane statistics plus public audit/report-family statistics.

## Aggregate findings

### Audit and report-family corpus totals

| Metric | Value |
|---|---:|
| Report families included | 5 |
| Total recorded entries | 2,010 |
| Snapshot entries | 2,001 |
| Baseline entries | 9 |
| Entries in core operational families (`ops_parameters`, `runtime_artifacts`, `repo_health`) | 1,980 |
| Share of total entries in core operational families | 98.5% |

### Audit and report-family ledger totals

| Family id | Total entries | Snapshot entries | Baseline entries | Latest recorded run (UTC) | Latest summary |
|---|---:|---:|---:|---|---|
| `ops_parameters` | 658 | 658 | 0 | 2026-03-24T13:00:03.746231Z | ERR |
| `runtime_artifacts` | 658 | 658 | 0 | 2026-03-24T13:05:05.915572Z | OK |
| `repo_health` | 664 | 664 | 0 | 2026-03-24T13:10:01.009365Z | WARN |
| `implementation_drift` | 29 | 20 | 9 | 2026-02-22T05:56:13.749508Z | OK |
| `gui` | 1 | 1 | 0 | 2026-02-11T17:19:09.759675Z | OK |

### Audit-family latest-status distribution

| Latest status class | Family count |
|---|---:|
| `OK` | 3 |
| `WARN` | 1 |
| `ERR` | 1 |

### Interpretation

Three patterns stand out.

1. **The current runtime picture is concentrated, not diffuse.** The live snapshot is dominated by a single active ingest lane, `real:canary`, while the other named modes currently show zero displayed records.
2. **Runtime posture is more severe than the audit-family rollup alone would suggest.** Even with a substantial retained canary corpus, the gate posture is `no-go`, the watchdog is `no-go`, and the baseline monitor is stopped.
3. **The audit/report-family corpus provides longitudinal context for the runtime snapshot.** The three core operational families dominate the recorded reporting volume, while GUI and implementation-drift reporting contribute smaller supporting slices.

### Threshold calibration snapshot

This aggregate includes a compact threshold-calibration snapshot for the current anomaly-scoring configuration.

| Calibration metric | Value |
|---|---:|
| Source dataset | `canary_v1_iforest_scores.csv` |
| Target FPR | 1.00% |
| Logic | `ApexLab Isolation Forest (Higher Score = More Anomalous)` |
| Selected threshold | `-0.045089` |
| Observed FPR | `1.0005% (1339/133837 records)` |
| Distribution min | `-0.078014` |
| Distribution max | `0.133836` |
| Distribution mean | `0.059508` |
| Distribution median | `0.061537` |

Interpretation:

- scores greater than or equal to `-0.045089` are treated as anomalous in this calibration snapshot
- this calibration snapshot appears here as a compact reference subsection inside the aggregate report
- broader model-eval aggregation remains deferred until the observer has successfully run through each mode and the final pre-ship lockdown lane is complete

## Quality controls

This starter aggregate report satisfies the following controls:

- the runtime observation point and runtime source surfaces are explicitly named
- the current lane census is presented before the audit rollups
- the included families are explicitly named
- the authoritative ledgers are explicitly listed
- the aggregation method is simple and reproducible in principle
- no raw secret-bearing payloads are reproduced
- each aggregate claim can be traced back to a family ledger and, where needed, a latest evidence bundle

## Limitations

- This is a **starter aggregate** rather than a full release-quality synthesis campaign.
- The runtime evidence aggregate is a current-state snapshot, whereas the audit/report-family ledgers are longitudinal histories; those two time scales should not be over-collapsed.
- The aggregation window is defined by the currently observed ledger state.
- The threshold-calibration subsection is a single-run analytical snapshot. Broader model-eval aggregation remains deferred.
- Some latest-run evidence bundles report git provenance degradation caused by repository safe-directory restrictions under the executing context.
- The family-status interpretation currently uses the latest available summary token; a dedicated reporting ontology remains a future reporting enhancement.

## Provenance

Authoritative ledgers used for this aggregate report:

- live `observerctl health full --json` packet captured at `2026-03-24T21:09:26.020961Z`
- live `observerctl librarian stats --json` packet captured at `2026-03-24T21:09:16.281289Z`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/ops_parameters_report.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/runtime_artifacts_audit.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/repo_health_audit.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/implementation_drift_audit.jsonl`
- `projects/calamum-moltbook-observer/local_untracked/audit_log/gui_audit.jsonl`

Supporting latest-run evidence bundles consulted for selected current statistics:

- `projects/calamum-moltbook-observer/local_untracked/reports/ops_parameters/calamum_ops_parameters_report_20260324T130003746231Z.evidence.json`
- `projects/calamum-moltbook-observer/local_untracked/audits/runtime/calamum_runtime_artifacts_audit_20260324T130505915572Z.evidence.json`
- `projects/calamum-moltbook-observer/local_untracked/audits/repo_health/calamum_repo_health_audit_20260324T131001.009365Z.evidence.json`

## Related surfaces

- [`../INDEX.md`](../INDEX.md)
- [`PUBLIC_RUN_LEDGER.md`](PUBLIC_RUN_LEDGER.md)
- [`../reference/GENERATED_REPORT_SURFACES.md`](../reference/GENERATED_REPORT_SURFACES.md)
