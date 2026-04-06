# Report Collections

Tracked reports are rebuilt as human-facing collection packets derived from the canonical untracked DS run spine.
Use this index to choose between synthesis, front-door packet routing, workflow-family rollups, threshold follow-through, and validation surfaces.
Machine-readable authority remains outside `docs/reports/` and is referenced from these collection surfaces rather than duplicated here.

## Summary

- Published runs: 5
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

- Collection alias: `p3-demo-current-20260406`
- Run ID: `build_20260406T213204617082Z`
- Workflow: build
- Timestamp (UTC): 2026-04-06T21:32:05.644819Z
- Why open it now: Build-stage packet for current dataset-materialization readiness.
- Collection packet: [20260406T213205644819Z.collection.md](collections/p3-demo-current-20260406/collection/20260406T213205644819Z.collection.md)
- Latest stage report: [20260406T213205644819Z.build.md](collections/p3-demo-current-20260406/processing/build/20260406T213205644819Z.build.md)

## Workflow latest

| Workflow | Published runs | Collection alias | Latest run | Collection packet | Latest stage doc |
|---|---:|---|---|---|---|
| build | 2 | `p3-demo-current-20260406` | `build_20260406T213204617082Z` | [collection packet](collections/p3-demo-current-20260406/collection/20260406T213205644819Z.collection.md) | [20260406T213205644819Z.build.md](collections/p3-demo-current-20260406/processing/build/20260406T213205644819Z.build.md) |
| evaluate | 1 | `p3-demo-current-20260406` | `evaluate_20260406T211232484108Z` | [collection packet](collections/p3-demo-current-20260406/collection/20260406T211246486478Z.collection.md) | [20260406T211246486478Z.eval.md](collections/p3-demo-current-20260406/processing/eval/20260406T211246486478Z.eval.md) |
| score | 1 | `p3-demo-current-20260406` | `score_20260406T170017731886Z` | [collection packet](collections/p3-demo-current-20260406/collection/20260406T170030764817Z.collection.md) | [20260406T170030764817Z.score.md](collections/p3-demo-current-20260406/processing/score/20260406T170030764817Z.score.md) |
| train | 1 | `p3-demo-current-20260406` | `train_20260406T165940271708Z` | [collection packet](collections/p3-demo-current-20260406/collection/20260406T165945654317Z.collection.md) | [20260406T165945654317Z.train.md](collections/p3-demo-current-20260406/processing/train/20260406T165945654317Z.train.md) |

## Recent collections

| Timestamp (UTC) | Workflow | Collection alias | Run ID | Collection packet | Stage doc |
|---|---|---|---|---|---|
| 2026-04-06T21:32:05.644819Z | build | `p3-demo-current-20260406` | `build_20260406T213204617082Z` | [collection packet](collections/p3-demo-current-20260406/collection/20260406T213205644819Z.collection.md) | [20260406T213205644819Z.build.md](collections/p3-demo-current-20260406/processing/build/20260406T213205644819Z.build.md) |
| 2026-04-06T21:31:27.083135Z | build | `p3-demo-current-20260406` | `build_20260406T213126205385Z` | [collection packet](collections/p3-demo-current-20260406/collection/20260406T213127083135Z.collection.md) | [20260406T213127083135Z.build.md](collections/p3-demo-current-20260406/processing/build/20260406T213127083135Z.build.md) |
| 2026-04-06T21:12:46.486478Z | evaluate | `p3-demo-current-20260406` | `evaluate_20260406T211232484108Z` | [collection packet](collections/p3-demo-current-20260406/collection/20260406T211246486478Z.collection.md) | [20260406T211246486478Z.eval.md](collections/p3-demo-current-20260406/processing/eval/20260406T211246486478Z.eval.md) |
| 2026-04-06T17:00:30.764817Z | score | `p3-demo-current-20260406` | `score_20260406T170017731886Z` | [collection packet](collections/p3-demo-current-20260406/collection/20260406T170030764817Z.collection.md) | [20260406T170030764817Z.score.md](collections/p3-demo-current-20260406/processing/score/20260406T170030764817Z.score.md) |
| 2026-04-06T16:59:45.654317Z | train | `p3-demo-current-20260406` | `train_20260406T165940271708Z` | [collection packet](collections/p3-demo-current-20260406/collection/20260406T165945654317Z.collection.md) | [20260406T165945654317Z.train.md](collections/p3-demo-current-20260406/processing/train/20260406T165945654317Z.train.md) |
