# Report Collections

Tracked reports are rebuilt as human-facing collection packets derived from the canonical untracked DS run spine.
Use this index to choose between synthesis, front-door packet routing, workflow-family rollups, threshold follow-through, and validation surfaces.
Machine-readable authority remains outside `docs/reports/` and is referenced from these collection surfaces rather than duplicated here.

## Summary

- Published runs: 13
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
- Run ID: `evaluate_20260413T073446087621Z`
- Workflow: evaluate
- Timestamp (UTC): 2026-04-13T07:34:46.351438Z
- Why open it now: Evaluation packet with current threshold and guardrail follow-through.
- Collection packet: [20260413T073446351438Z.collection.md](collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md)
- Latest stage report: [20260413T073446351438Z.eval.md](collections/liv-rd3bb/processing/eval/20260413T073446351438Z.eval.md)

## Workflow latest

| Workflow | Published runs | Collection alias | Latest run | Collection packet | Latest stage doc |
|---|---:|---|---|---|---|
| build | 3 | `liv-rd3bb` | `build_20260413T024620291292Z` | [collection packet](collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) | [20260413T024620493383Z.build.md](collections/liv-rd3bb/processing/build/20260413T024620493383Z.build.md) |
| evaluate | 4 | `liv-rd3bb` | `evaluate_20260413T073446087621Z` | [collection packet](collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) | [20260413T073446351438Z.eval.md](collections/liv-rd3bb/processing/eval/20260413T073446351438Z.eval.md) |
| score | 1 | `can-r0b70` | `score_20260412T182840525749Z` | [collection packet](collections/can-r0b70/collection/20260413T012801395015Z.collection.md) | [20260412T183143055972Z.score.md](collections/can-r0b70/processing/score/20260412T183143055972Z.score.md) |
| train | 5 | `liv-rd3bb` | `train_20260413T073259573965Z` | [collection packet](collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) | [20260413T073300032775Z.train.md](collections/liv-rd3bb/processing/train/20260413T073300032775Z.train.md) |

## Recent collections

| Timestamp (UTC) | Workflow | Collection alias | Run ID | Collection packet | Stage doc |
|---|---|---|---|---|---|
| 2026-04-13T07:34:46.351438Z | evaluate | `liv-rd3bb` | `evaluate_20260413T073446087621Z` | [collection packet](collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) | [20260413T073446351438Z.eval.md](collections/liv-rd3bb/processing/eval/20260413T073446351438Z.eval.md) |
| 2026-04-13T07:33:00.032775Z | train | `liv-rd3bb` | `train_20260413T073259573965Z` | [collection packet](collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) | [20260413T073300032775Z.train.md](collections/liv-rd3bb/processing/train/20260413T073300032775Z.train.md) |
| 2026-04-13T07:30:45.558853Z | evaluate | `liv-rd3bb` | `evaluate_20260413T073044783730Z` | [collection packet](collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) | [20260413T073045558853Z.eval.md](collections/liv-rd3bb/processing/eval/20260413T073045558853Z.eval.md) |
| 2026-04-13T02:47:01.872614Z | train | `liv-rd3bb` | `train_20260413T024701417065Z` | [collection packet](collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) | [20260413T024701872614Z.train.md](collections/liv-rd3bb/processing/train/20260413T024701872614Z.train.md) |
| 2026-04-13T02:46:20.493383Z | build | `liv-rd3bb` | `build_20260413T024620291292Z` | [collection packet](collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) | [20260413T024620493383Z.build.md](collections/liv-rd3bb/processing/build/20260413T024620493383Z.build.md) |
| 2026-04-13T02:41:19.308328Z | train | `liv-r8bc9` | `train_20260413T024114450707Z` | [collection packet](collections/liv-r8bc9/collection/20260413T024119308328Z.collection.md) | [20260413T024119308328Z.train.md](collections/liv-r8bc9/processing/train/20260413T024119308328Z.train.md) |
| 2026-04-13T02:40:35.957045Z | build | `liv-r8bc9` | `build_20260413T024035732993Z` | [collection packet](collections/liv-r8bc9/collection/20260413T024119308328Z.collection.md) | [20260413T024035957045Z.build.md](collections/liv-r8bc9/processing/build/20260413T024035957045Z.build.md) |
| 2026-04-13T01:28:01.395015Z | evaluate | `can-r0b70` | `evaluate_20260413T011803992045Z` | [collection packet](collections/can-r0b70/collection/20260413T012801395015Z.collection.md) | [20260413T012801395015Z.eval.md](collections/can-r0b70/processing/eval/20260413T012801395015Z.eval.md) |
| 2026-04-13T01:10:36.211963Z | train | `can-r0b70` | `train_20260413T010829031589Z` | [collection packet](collections/can-r0b70/collection/20260413T012801395015Z.collection.md) | [20260413T011036211963Z.train.md](collections/can-r0b70/processing/train/20260413T011036211963Z.train.md) |
| 2026-04-12T18:31:43.055972Z | score | `can-r0b70` | `score_20260412T182840525749Z` | [collection packet](collections/can-r0b70/collection/20260413T012801395015Z.collection.md) | [20260412T183143055972Z.score.md](collections/can-r0b70/processing/score/20260412T183143055972Z.score.md) |
