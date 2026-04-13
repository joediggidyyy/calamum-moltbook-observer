# Report Collections

Tracked reports are rebuilt as human-facing collection packets derived from the canonical untracked DS run spine.
Use this index to choose between synthesis, front-door packet routing, workflow-family rollups, threshold follow-through, and validation surfaces.
Machine-readable authority remains outside `docs/reports/` and is referenced from these collection surfaces rather than duplicated here.

## Summary

- Published runs: 4
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

- Collection alias: `can-r4ccf`
- Run ID: `score_20260412T182840525749Z`
- Workflow: score
- Timestamp (UTC): 2026-04-12T18:31:43.055972Z
- Why open it now: Score-stage packet with figure-backed anomaly-surface context.
- Collection packet: [20260412T183143055972Z.collection.md](collections/can-r4ccf/collection/20260412T183143055972Z.collection.md)
- Latest stage report: [20260412T183143055972Z.score.md](collections/can-r4ccf/processing/score/20260412T183143055972Z.score.md)

## Workflow latest

| Workflow | Published runs | Collection alias | Latest run | Collection packet | Latest stage doc |
|---|---:|---|---|---|---|
| build | 1 | `can-r0b70` | `build_20260412T181141515764Z` | [collection packet](collections/can-r0b70/collection/20260412T181142763215Z.collection.md) | [20260412T181142763215Z.build.md](collections/can-r0b70/processing/build/20260412T181142763215Z.build.md) |
| evaluate | 1 | `can-r4ccf` | `evaluate_20260412T181954946962Z` | [collection packet](collections/can-r4ccf/collection/20260412T183143055972Z.collection.md) | [20260412T182621255204Z.eval.md](collections/can-r4ccf/processing/eval/20260412T182621255204Z.eval.md) |
| score | 1 | `can-r4ccf` | `score_20260412T182840525749Z` | [collection packet](collections/can-r4ccf/collection/20260412T183143055972Z.collection.md) | [20260412T183143055972Z.score.md](collections/can-r4ccf/processing/score/20260412T183143055972Z.score.md) |
| train | 1 | `can-r4ccf` | `train_20260412T181433425502Z` | [collection packet](collections/can-r4ccf/collection/20260412T183143055972Z.collection.md) | [20260412T181602715320Z.train.md](collections/can-r4ccf/processing/train/20260412T181602715320Z.train.md) |

## Recent collections

| Timestamp (UTC) | Workflow | Collection alias | Run ID | Collection packet | Stage doc |
|---|---|---|---|---|---|
| 2026-04-12T18:31:43.055972Z | score | `can-r4ccf` | `score_20260412T182840525749Z` | [collection packet](collections/can-r4ccf/collection/20260412T183143055972Z.collection.md) | [20260412T183143055972Z.score.md](collections/can-r4ccf/processing/score/20260412T183143055972Z.score.md) |
| 2026-04-12T18:26:21.255204Z | evaluate | `can-r4ccf` | `evaluate_20260412T181954946962Z` | [collection packet](collections/can-r4ccf/collection/20260412T183143055972Z.collection.md) | [20260412T182621255204Z.eval.md](collections/can-r4ccf/processing/eval/20260412T182621255204Z.eval.md) |
| 2026-04-12T18:16:02.715320Z | train | `can-r4ccf` | `train_20260412T181433425502Z` | [collection packet](collections/can-r4ccf/collection/20260412T183143055972Z.collection.md) | [20260412T181602715320Z.train.md](collections/can-r4ccf/processing/train/20260412T181602715320Z.train.md) |
| 2026-04-12T18:11:42.763215Z | build | `can-r0b70` | `build_20260412T181141515764Z` | [collection packet](collections/can-r0b70/collection/20260412T181142763215Z.collection.md) | [20260412T181142763215Z.build.md](collections/can-r0b70/processing/build/20260412T181142763215Z.build.md) |
