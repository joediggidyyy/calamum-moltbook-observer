# Generated Report Surfaces

This reference describes the active human-facing report schema for tracked publication under `docs/reports/`.

## Contract

- All Markdown inside `docs/reports/` is human-facing.
- Machine-readable authority remains outside this tree and is referenced from these reader surfaces rather than duplicated here.
- When published runs exist, they are rendered under `docs/reports/collections/<collection-alias>/`.
- Zero-state publication may leave `docs/reports/collections/` present but empty until a fresh canonical publication pass materializes collection packets.
- Aggregate-facing collection routes use the dated collection packet leaf under `docs/reports/collections/<collection-alias>/collection/YYYYMMDDTHHMMSSffffffZ.collection.md` when that packet family exists.
- No stable `collection/report.md` landing page is part of the current tracked packet contract.

## Layout

```text
docs/reports/
|- aggregates/
|- collections/
|  `- <collection-alias>/
|     |- collection/
|     |  `- YYYYMMDDTHHMMSSffffffZ.collection.md
|     `- processing/
|        |- build/
|        |  |- YYYYMMDDTHHMMSSffffffZ.build.md
|        |  `- figures/
|        |     `- <packet-stem>/...
|        |- eval/
|        |  |- YYYYMMDDTHHMMSSffffffZ.eval.md
|        |  `- figures/
|        |     `- <packet-stem>/...
|        |- score/
|        |  |- YYYYMMDDTHHMMSSffffffZ.score.md
|        |  `- figures/
|        |     `- <packet-stem>/...
|        `- train/
|           |- YYYYMMDDTHHMMSSffffffZ.train.md
|           `- figures/
|              `- <packet-stem>/...
|- reference/
|- validations/
`- INDEX.md
```

The `processing/<stage>/figures/<packet-stem>/...` subtree is optional and appears only when the relevant stage emits figure artifacts.

## Aggregate report family

- `docs/reports/aggregates/AGGREGATE_REPORT.md`
- `docs/reports/aggregates/PUBLIC_RUN_LEDGER.md`
- `docs/reports/aggregates/LATEST_COLLECTIONS.md`
- `docs/reports/aggregates/WORKFLOW_ROLLUP.md`
- `docs/reports/aggregates/THRESHOLD_SUMMARY.md`

## Aggregate surface roles

| Surface                        | Reader role                              |
| ------------------------------ | ---------------------------------------- |
| `AGGREGATE_REPORT.md`          | Flagship synthesis narrative             |
| `PUBLIC_RUN_LEDGER.md`         | Runtime-safe population census           |
| `LATEST_COLLECTIONS.md`        | Front-door collection routing            |
| `WORKFLOW_ROLLUP.md`           | Workflow-family overview                 |
| `THRESHOLD_SUMMARY.md`         | Evaluation-only threshold follow-through |
| `GENERATED_REPORT_SURFACES.md` | Contract/reference surface               |

## Tracked packet family

When collection packets are materialized:

- `docs/reports/collections/<collection-alias>/collection/YYYYMMDDTHHMMSSffffffZ.collection.md`
- `docs/reports/collections/<collection-alias>/processing/<stage>/YYYYMMDDTHHMMSSffffffZ.<stage>.md`
- `docs/reports/collections/<collection-alias>/processing/<stage>/figures/<packet-stem>/...` when that stage emits figure artifacts for the dated stage packet identified by `<packet-stem>`
- `<stage>` currently materializes as `build`, `eval`, `score`, or `train` in the tracked packet family.
- `docs/reports/collections/<collection-alias>/processing/build/YYYYMMDDTHHMMSSffffffZ.build.md`
- `docs/reports/collections/<collection-alias>/processing/eval/YYYYMMDDTHHMMSSffffffZ.eval.md`
- `docs/reports/collections/<collection-alias>/processing/score/YYYYMMDDTHHMMSSffffffZ.score.md`
- `docs/reports/collections/<collection-alias>/processing/train/YYYYMMDDTHHMMSSffffffZ.train.md`

## Canonical derived report samples

When active tracked publication is in zero-state, use this archived sample packet family as the canonical reader-shape example set:

- Collection packet sample: [20260404.collection.md](../../../local_untracked/quarantine_legacy_archive/reports_surface_reset_20260404/collections/sample/collection/20260404.collection.md)
- Build packet sample: [20260404.build.md](../../../local_untracked/quarantine_legacy_archive/reports_surface_reset_20260404/collections/sample/processing/build/20260404.build.md)
- Eval packet sample: [20260404.eval.md](../../../local_untracked/quarantine_legacy_archive/reports_surface_reset_20260404/collections/sample/processing/eval/20260404.eval.md)
- Score packet sample: [20260404.score.md](../../../local_untracked/quarantine_legacy_archive/reports_surface_reset_20260404/collections/sample/processing/score/20260404.score.md)
- Train packet sample: [20260404.train.md](../../../local_untracked/quarantine_legacy_archive/reports_surface_reset_20260404/collections/sample/processing/train/20260404.train.md)

These archived sample packets are reference examples for packet shape and routing. They do not override the live tracked publication state under `docs/reports/`.

## Reader routes

- Aggregate report: [AGGREGATE_REPORT.md](../aggregates/AGGREGATE_REPORT.md)
- Public run ledger: [PUBLIC_RUN_LEDGER.md](../aggregates/PUBLIC_RUN_LEDGER.md)
- Latest collections: [LATEST_COLLECTIONS.md](../aggregates/LATEST_COLLECTIONS.md)
- Workflow rollup: [WORKFLOW_ROLLUP.md](../aggregates/WORKFLOW_ROLLUP.md)
- Threshold summary: [THRESHOLD_SUMMARY.md](../aggregates/THRESHOLD_SUMMARY.md)
- Validation index: [validations/INDEX.md](../validations/INDEX.md)

## Aggregate-consumer route authority

- `LATEST_COLLECTIONS.md` and aggregate-facing collection links should target the dated collection packet leaf directly whenever packet families are materialized.
- Workflow and threshold routes should target real dated processing packet leaves and fail closed when those packet routes are missing.
- Zero-state publication should remain honest: keep the aggregate family readable while leaving packet-route sections empty rather than implying packet leaves that do not yet exist.
