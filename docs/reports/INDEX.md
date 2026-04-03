# Report Index

Updated: 2026-04-03

This index catalogs the tracked report surfaces that are intentionally part of the public documentation set.

## How reports fit into the docs set

| Surface type | Purpose |
| --- | --- |
| manuals | explain stable contracts and operating models |
| reports | preserve curated findings, evaluation outputs, and publication-ready artifacts |
| report references | explain generated report families without checking routine run residue into the repo |

## Report catalog

| Report | Topic | Relation to the manuals |
| --- | --- | --- |
| [`ds/INDEX.md`](ds/INDEX.md) | tracked data-science report packs and aggregate rollups | sits beside [`../manuals/data-science/CALAMUM_DS_OPERATIONS.md`](../manuals/data-science/CALAMUM_DS_OPERATIONS.md) as the publication-facing DS route |
| [`GENERATED_REPORT_SURFACES.md`](GENERATED_REPORT_SURFACES.md) | generated report families and when they run | complements the runtime and DS manuals without replacing them |
| [`PUBLIC_RUN_LEDGER.md`](PUBLIC_RUN_LEDGER.md) | runtime-first public ledger of current evidence and lane census | gives readers a concise evidence-first snapshot |
| [`AGGREGATE_REPORT.md`](AGGREGATE_REPORT.md) | tracked aggregate synthesis of runtime evidence and threshold calibration | provides a public synthesis layer after readers understand the operating model |
| [`AGGREGATE_REPORT_SCHEMA.md`](AGGREGATE_REPORT_SCHEMA.md) | schema and structure for future public aggregate reports | keeps future cross-run summaries methodologically aligned |
| [`APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md`](APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md) | reference-validation report for the ApexLab evaluation lane | preserves the quantitative interpretation inside the tracked report set |

## Suggested order

1. [`../INDEX.md`](../INDEX.md) for the documentation map
2. [`../../README.md`](../../README.md) for project orientation
3. [`../manuals/data-science/CALAMUM_DS_OPERATIONS.md`](../manuals/data-science/CALAMUM_DS_OPERATIONS.md) for the DS command and artifact model
4. specific reports for curated evidence or evaluation artifacts