# Report Index

**Document ID**: `CALAMUM_REPORT_INDEX_20260324`  
**Status**: Public report catalog  
**Owner**: ORACL-Prime  
**Project**: Calamum Moltbook Observer  
**Last updated**: 2026-03-24

## Purpose

This index catalogs the tracked report surfaces that are intentionally part of the public documentation set.

Reports are distinct from manuals:

- **manuals** explain stable contracts and operating models
- **reports** preserve curated findings, evaluation outputs, or publishable review artifacts
- **report references** explain generated runtime report families without checking routine run artifacts into the repo

## Report catalog

| Report | Topic | Status | Relation to manuals |
|---|---|---|---|
| [`ds/INDEX.md`](ds/INDEX.md) | Curated dataset-science report packs and aggregate rollups derived from the canonical DS run spine | Tracked | Gives readers one DS-specific route into published per-run report packs and aggregate summaries without replacing the broader report catalog. |
| [`GENERATED_REPORT_SURFACES.md`](GENERATED_REPORT_SURFACES.md) | Generated report families explained in terms of when they run, why they exist, and how they are produced | Tracked | Explains the generated report families that sit beside the manuals and public reports without replacing either surface. |
| [`PUBLIC_RUN_LEDGER.md`](PUBLIC_RUN_LEDGER.md) | Starter public ledger foregrounding current runtime evidence and lane census before audit/report-family census data | Tracked | Provides the runtime-first public snapshot that later cross-run synthesis can cite without publishing routine runtime payloads. |
| [`AGGREGATE_REPORT.md`](AGGREGATE_REPORT.md) | Starter aggregate report foregrounding runtime evidence aggregates before audit/report-family synthesis, with a compact threshold-calibration subsection | Tracked | Provides a public synthesis surface that leads with active runtime posture and includes the current threshold-calibration snapshot. |
| [`AGGREGATE_REPORT_SCHEMA.md`](AGGREGATE_REPORT_SCHEMA.md) | Schema and methodological contract for future public aggregate reports | Tracked | Defines how multi-run public synthesis should be structured so it remains analytically legible and methodologically disciplined. |
| [`APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md`](APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md) | Scientific report for the 2026-03-24 ApexLab reference-validation run used by the Observer analysis lane | Tracked | Preserves the quantitative validation interpretation in tracked Observer docs while the figure-bearing authoring copy remains in the local report lane. |

## How reports relate to manuals

Use reports after you understand the core project surfaces:

1. [`../INDEX.md`](../INDEX.md) for overall docs routing
2. [`../../README.md`](../../README.md) for project orientation
3. [`../../DATA_METHODOLOGY.md`](../../DATA_METHODOLOGY.md) for telemetry and packet-contract context
4. specific reports for curated evidence or evaluation artifacts