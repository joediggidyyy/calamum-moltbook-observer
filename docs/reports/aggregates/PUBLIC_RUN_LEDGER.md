# Public Run Ledger

This ledger defines the current public reporting population and provides a runtime-safe census of the tracked report family.

## Purpose

- Count what currently exists in the tracked report family.
- Keep the reader-facing population separate from the machine-authoritative run ledger.
- Route readers to synthesis and packet-entry surfaces without pretending this ledger is the authority plane.

## How to read this ledger

- Use `AGGREGATE_REPORT.md` for the flagship synthesis narrative.
- Use `LATEST_COLLECTIONS.md` when you need the fastest packet-entry route.
- Use `WORKFLOW_ROLLUP.md` and `THRESHOLD_SUMMARY.md` when you need family-specific rollups.

## Current runtime-safe headline

- Publish root: `docs/reports`
- Published runs: 2
- Collection aliases represented: 2
- Workflow families represented: 2
- Threshold-bearing packets: 0
- Latest packet: [score_20260406T170017731886Z](../collections/score_20260406T170017731886Z/collection/20260406T170030764817Z.collection.md)

## Current lane census

| Workflow | Published packets | Latest collection | Latest packet |
|---|---:|---|---|
| score | 1 | `score_20260406T170017731886Z` | [20260406T170030764817Z.score.md](../collections/score_20260406T170017731886Z/processing/score/20260406T170030764817Z.score.md) |
| train | 1 | `train_20260406T165940271708Z` | [20260406T165945654317Z.train.md](../collections/train_20260406T165940271708Z/processing/train/20260406T165945654317Z.train.md) |

## Publication-family census

| Collection alias | Source / mode | Published packets | Latest packet date | Latest stages | Collection packet |
|---|---|---:|---|---|---|
| `score_20260406T170017731886Z` | runtime-unspecified | 1 | 2026-04-06T17:00:30.764817Z | score | [collection packet](../collections/score_20260406T170017731886Z/collection/20260406T170030764817Z.collection.md) |
| `train_20260406T165940271708Z` | runtime-unspecified | 1 | 2026-04-06T16:59:45.654317Z | train | [collection packet](../collections/train_20260406T165940271708Z/collection/20260406T165945654317Z.collection.md) |

## Publication-source census

| Source | Mode | Published packets |
|---|---|---:|
| unspecified | unspecified | 2 |

## Interpretive notes

- This ledger is deliberately derived and runtime-safe; it summarizes the tracked publication family without replacing the canonical machine-readable run records.
- Absence here means the packet did not enter the tracked publication family; it does not imply the underlying machine artifacts do not exist.

## Provenance

- Machine-readable authority remains outside `docs/reports/`.
- The tracked report family is rebuilt from the canonical untracked DS run spine and packetized collection surfaces.

## Related surfaces

- Aggregate report: [AGGREGATE_REPORT.md](AGGREGATE_REPORT.md)
- Latest collections: [LATEST_COLLECTIONS.md](LATEST_COLLECTIONS.md)
- Workflow rollup: [WORKFLOW_ROLLUP.md](WORKFLOW_ROLLUP.md)
- Threshold summary: [THRESHOLD_SUMMARY.md](THRESHOLD_SUMMARY.md)
