# Report Index

Updated: 2026-04-04

This index catalogs the tracked report surfaces that are intentionally part of the public documentation set.

## How reports fit into the docs set

| Surface type | Purpose |
| --- | --- |
| manuals | explain stable contracts and operating models |
| collections | publish reader-facing DS collection packets derived from canonical runs |
| aggregates | route readers through the current tracked collection set |
| references | explain generated report families and the tracked packet contract |
| validations | preserve tracked validation packets when a validation family intentionally publishes one |

## Report catalog

| Report | Topic | Relation to the manuals |
| --- | --- | --- |
| [`aggregates/LATEST_COLLECTIONS.md`](aggregates/LATEST_COLLECTIONS.md) | latest tracked collection landing pages | gives readers the current collection-first entry point into the DS publication lane |
| [`aggregates/WORKFLOW_ROLLUP.md`](aggregates/WORKFLOW_ROLLUP.md) | latest tracked packets grouped by workflow | complements the DS manuals with workflow-aware publication routing |
| [`aggregates/THRESHOLD_SUMMARY.md`](aggregates/THRESHOLD_SUMMARY.md) | threshold-bearing tracked packets | preserves threshold-facing tracked interpretation without widening the public packet tree |
| [`reference/GENERATED_REPORT_SURFACES.md`](reference/GENERATED_REPORT_SURFACES.md) | generated report families and tracked packet layout | complements the runtime and DS manuals without replacing them |
| [`validations/INDEX.md`](validations/INDEX.md) | tracked validation-publication entry point | keeps validation-facing reader routes inside the same public report tree |

## Suggested order

1. [`../INDEX.md`](../INDEX.md) for the documentation map
2. [`../../README.md`](../../README.md) for project orientation
3. [`../manuals/data-science/DS_OPERATIONS.md`](../manuals/data-science/DS_OPERATIONS.md) for the DS command and artifact model
4. [`aggregates/LATEST_COLLECTIONS.md`](aggregates/LATEST_COLLECTIONS.md) for the latest tracked collection landing pages
5. [`reference/GENERATED_REPORT_SURFACES.md`](reference/GENERATED_REPORT_SURFACES.md) for the generated-surface contract