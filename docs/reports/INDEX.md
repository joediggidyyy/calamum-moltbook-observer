# Report Collections

Tracked reports are rebuilt as human-facing collection packets derived from the canonical untracked DS run spine.
Use this index to choose between synthesis, front-door packet routing, workflow-family rollups, threshold follow-through, and validation surfaces.
Machine-readable authority remains outside `docs/reports/` and is referenced from these collection surfaces rather than duplicated here.

## Summary

- Published runs: 3
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

- Collection alias: `liv-r8bc9`
- Run ID: `score_20260411T042449359583Z`
- Workflow: score
- Timestamp (UTC): 2026-04-11T04:24:59.318423Z
- Why open it now: Score-stage packet with figure-backed anomaly-surface context.
- Collection packet: [20260411T042459318423Z.collection.md](collections/liv-r8bc9/collection/20260411T042459318423Z.collection.md)
- Latest stage report: [20260411T042459318423Z.score.md](collections/liv-r8bc9/processing/score/20260411T042459318423Z.score.md)

## Workflow latest

| Workflow | Published runs | Collection alias | Latest run | Collection packet | Latest stage doc |
|---|---:|---|---|---|---|
| build | 1 | `liv-r8bc9` | `build_20260411T042407214529Z` | [collection packet](collections/liv-r8bc9/collection/20260411T042459318423Z.collection.md) | [20260411T042409067088Z.build.md](collections/liv-r8bc9/processing/build/20260411T042409067088Z.build.md) |
| score | 1 | `liv-r8bc9` | `score_20260411T042449359583Z` | [collection packet](collections/liv-r8bc9/collection/20260411T042459318423Z.collection.md) | [20260411T042459318423Z.score.md](collections/liv-r8bc9/processing/score/20260411T042459318423Z.score.md) |
| train | 1 | `liv-r8bc9` | `train_20260411T042431425146Z` | [collection packet](collections/liv-r8bc9/collection/20260411T042459318423Z.collection.md) | [20260411T042436698004Z.train.md](collections/liv-r8bc9/processing/train/20260411T042436698004Z.train.md) |

## Recent collections

| Timestamp (UTC) | Workflow | Collection alias | Run ID | Collection packet | Stage doc |
|---|---|---|---|---|---|
| 2026-04-11T04:24:59.318423Z | score | `liv-r8bc9` | `score_20260411T042449359583Z` | [collection packet](collections/liv-r8bc9/collection/20260411T042459318423Z.collection.md) | [20260411T042459318423Z.score.md](collections/liv-r8bc9/processing/score/20260411T042459318423Z.score.md) |
| 2026-04-11T04:24:36.698004Z | train | `liv-r8bc9` | `train_20260411T042431425146Z` | [collection packet](collections/liv-r8bc9/collection/20260411T042459318423Z.collection.md) | [20260411T042436698004Z.train.md](collections/liv-r8bc9/processing/train/20260411T042436698004Z.train.md) |
| 2026-04-11T04:24:09.067088Z | build | `liv-r8bc9` | `build_20260411T042407214529Z` | [collection packet](collections/liv-r8bc9/collection/20260411T042459318423Z.collection.md) | [20260411T042409067088Z.build.md](collections/liv-r8bc9/processing/build/20260411T042409067088Z.build.md) |
