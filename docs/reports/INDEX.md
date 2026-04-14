# Report Collections

Tracked reports are rebuilt as human-facing collection packets derived from the canonical untracked DS run spine.
Use this index to choose between synthesis, front-door packet routing, workflow-family rollups, threshold follow-through, and validation surfaces.
Machine-readable authority remains outside `docs/reports/` and is referenced from these collection surfaces rather than duplicated here.

## Summary

- Published runs: 2
- Aggregate report: [AGGREGATE_REPORT.md](aggregates/AGGREGATE_REPORT.md)
- Public run ledger: [PUBLIC_RUN_LEDGER.md](aggregates/PUBLIC_RUN_LEDGER.md)
- Latest collections: [LATEST_COLLECTIONS.md](aggregates/LATEST_COLLECTIONS.md)
- Workflow rollup: [WORKFLOW_ROLLUP.md](aggregates/WORKFLOW_ROLLUP.md)
- Threshold summary: [THRESHOLD_SUMMARY.md](aggregates/THRESHOLD_SUMMARY.md)
- Generated-report reference: [GENERATED_REPORT_SURFACES.md](reference/GENERATED_REPORT_SURFACES.md)
- Validation index: [validations/INDEX.md](validations/INDEX.md)

## How to use this report family

| Surface | Reader role | Open this when |
|---|---|---|
| `AGGREGATE_REPORT.md` | Flagship synthesis narrative | You need the strongest current packet-level conclusions first. |
| `LATEST_COLLECTIONS.md` | Front-door collection routing | You want the fastest route into the current dated collection packets. |
| `WORKFLOW_ROLLUP.md` | Workflow-family overview | You need to compare the latest build / train / evaluate / score packet families. |
| `THRESHOLD_SUMMARY.md` | Threshold-bearing packet follow-through | You need evaluation-led threshold and guardrail context. |
| `PUBLIC_RUN_LEDGER.md` | Runtime-safe population census | You need counts, current coverage, and publication-family composition. |
| `GENERATED_REPORT_SURFACES.md` | Contract/reference surface | You need the tracked packet filesystem contract and fail-closed routing rules. |
| `validations/INDEX.md` | Validation routing | You need public validation surfaces rather than collection packets. |

## Latest collection

- Collection alias: `liv-rd3bb`
- Run ID: `train_20260414T094501184301Z`
- Workflow: train
- Timestamp (UTC): 2026-04-14T09:45:16.753389Z
- Why open it now: Training handoff packet for the current model-publication lane.
- Collection packet: [20260414T094516753389Z.collection.md](collections/liv-rd3bb/collection/20260414T094516753389Z.collection.md)
- Latest stage report: [20260414T094516753389Z.train.md](collections/liv-rd3bb/processing/train/20260414T094516753389Z.train.md)

## Workflow latest

| Workflow | Published runs | Collection alias | Latest run | Collection packet | Latest stage doc |
|---|---:|---|---|---|---|
| score | 1 | `can-r0b70` | `score_20260414T093711179367Z` | [collection packet](collections/can-r0b70/collection/20260414T094015247284Z.collection.md) | [20260414T094015247284Z.score.md](collections/can-r0b70/processing/score/20260414T094015247284Z.score.md) |
| train | 1 | `liv-rd3bb` | `train_20260414T094501184301Z` | [collection packet](collections/liv-rd3bb/collection/20260414T094516753389Z.collection.md) | [20260414T094516753389Z.train.md](collections/liv-rd3bb/processing/train/20260414T094516753389Z.train.md) |

## Recent collections

| Timestamp (UTC) | Workflow | Collection alias | Run ID | Collection packet | Stage doc |
|---|---|---|---|---|---|
| 2026-04-14T09:45:16.753389Z | train | `liv-rd3bb` | `train_20260414T094501184301Z` | [collection packet](collections/liv-rd3bb/collection/20260414T094516753389Z.collection.md) | [20260414T094516753389Z.train.md](collections/liv-rd3bb/processing/train/20260414T094516753389Z.train.md) |
| 2026-04-14T09:40:15.247284Z | score | `can-r0b70` | `score_20260414T093711179367Z` | [collection packet](collections/can-r0b70/collection/20260414T094015247284Z.collection.md) | [20260414T094015247284Z.score.md](collections/can-r0b70/processing/score/20260414T094015247284Z.score.md) |
