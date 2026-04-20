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
- Published runs: 0
- Collection aliases represented: 0
- Workflow families represented: 0
- Threshold-bearing packets: 0

## Current lane census

No workflow families are published yet.

## Publication-family census

No collection packets are published yet.

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

## Librarian vault inventory

This bottom section is human-facing and summarizes tracked report archive inventories currently held in the Librarian quarantine lane.
Machine-readable authority remains in the underlying archive manifests and audit surfaces; this table is only a routing view over those retained artifacts.

- Vault inventory root: `local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer`
- Archive inventories currently visible: 22

| Archived at (UTC) | Action | Archived aliases | Archive manifest |
|---|---|---|---|
| 2026-04-15T20:58:23.853691Z | archive-and-reset-report-collections | `can-r0b70`, `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260415T205823Z/archive_manifest.json) |
| 2026-04-15T20:06:39.433459Z | archive-and-reset-report-collections | `can-r0b70`, `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260415T200639Z/archive_manifest.json) |
| 2026-04-15T18:49:45.362463Z | archive-and-reset-report-collections | `can-r0b70`, `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260415T184945Z/archive_manifest.json) |
| 2026-04-15T17:59:57.386794Z | archive-and-reset-report-collections | `can-r0b70` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260415T175957Z/archive_manifest.json) |
| 2026-04-15T17:13:34.753632Z | archive-and-reset-report-collections | `can-r0b70`, `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260415T171334Z/archive_manifest.json) |
| 2026-04-15T04:58:40.332772Z | archive-and-reset-report-collections | `can-r0b70`, `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260415T045840Z/archive_manifest.json) |
| 2026-04-14T22:22:27.846171Z | archive-and-reset-report-collections | `can-r0b70` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260414T222227Z/archive_manifest.json) |
| 2026-04-14T21:09:43.427428Z | archive-and-reset-report-collections | `can-r0b70`, `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260414T210943Z/archive_manifest.json) |
| 2026-04-14T20:18:30.406059Z | archive-and-reset-report-collections | `can-r0b70`, `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260414T201830Z/archive_manifest.json) |
| 2026-04-14T17:26:14.836625Z | archive-and-reset-report-collections | `can-r0b70`, `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260414T172614Z/archive_manifest.json) |
| 2026-04-14T17:22:05.153843Z | archive-and-delete-report-collection | `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_liv-rd3bb_20260414T172205Z/archive_manifest.json) |
| 2026-04-14T15:36:28.350779Z | archive-and-reset-report-collections | `can-r0b70`, `can-r659b` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260414T153628Z/archive_manifest.json) |
| 2026-04-14T15:33:44.076951Z | archive-and-reset-report-collections | `can-r0b70` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260414T153343Z/archive_manifest.json) |
| 2026-04-14T15:31:35.919255Z | archive-and-delete-report-collection | `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_liv-rd3bb_20260414T153135Z/archive_manifest.json) |
| 2026-04-13T21:18:25.652639Z | archive-and-reset-report-collections | `can-r0b70` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260413T211825Z/archive_manifest.json) |
| 2026-04-13T21:17:28.353226Z | archive-and-delete-report-collection | `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_liv-rd3bb_20260413T211728Z/archive_manifest.json) |
| 2026-04-13T21:16:41.968582Z | archive-and-delete-report-collection | `liv-r8bc9` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_liv-r8bc9_20260413T211641Z/archive_manifest.json) |
| 2026-04-13T17:17:40.782891Z | archive-and-delete-report-collection | `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_liv-rd3bb_20260413T171740Z/archive_manifest.json) |
| 2026-04-11T03:45:58.236289Z | archive-and-reset-report-collections | `INDEX.md`, `aggregates`, `reference`, `collections` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260411T034558Z/archive_manifest.json) |
| 2026-04-11T03:44:50.481570Z | archive-and-delete-report-collection | `p3-demo-current-20260406` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_p3-demo-current-20260406_20260411T034450Z/archive_manifest.json) |
| 2026-04-11T03:44:40.491440Z | archive-and-delete-report-collection | `dataset-d7c0eb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_dataset-d7c0eb_20260411T034440Z/archive_manifest.json) |
| 2026-04-10T15:30:44.549261Z | archive-and-reset-report-collections | `p3-demo-current-20260406` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260410T153044Z/archive_manifest.json) |
