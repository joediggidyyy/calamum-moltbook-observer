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
- Published runs: 2
- Collection aliases represented: 2
- Workflow families represented: 2
- Threshold-bearing packets: 0
- Latest packet: [liv-rd3bb](../collections/liv-rd3bb/collection/20260414T094516753389Z.collection.md)

## Current lane census

| Workflow | Published packets | Latest collection | Latest packet |
|---|---:|---|---|
| score | 1 | `can-r0b70` | [20260414T094015247284Z.score.md](../collections/can-r0b70/processing/score/20260414T094015247284Z.score.md) |
| train | 1 | `liv-rd3bb` | [20260414T094516753389Z.train.md](../collections/liv-rd3bb/processing/train/20260414T094516753389Z.train.md) |

## Publication-family census

| Collection alias | Source / mode | Published packets | Latest packet date | Latest stages | Collection packet |
|---|---|---:|---|---|---|
| `liv-rd3bb` | runtime-unspecified | 1 | 2026-04-14T09:45:16.753389Z | train | [collection packet](../collections/liv-rd3bb/collection/20260414T094516753389Z.collection.md) |
| `can-r0b70` | runtime-unspecified | 1 | 2026-04-14T09:40:15.247284Z | score | [collection packet](../collections/can-r0b70/collection/20260414T094015247284Z.collection.md) |

## Publication-source census

| Source | Mode | Published packets |
|---|---|---:|
| unspecified | unspecified | 2 |

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
- Archive inventories currently visible: 8

| Archived at (UTC) | Action | Archived aliases | Archive manifest |
|---|---|---|---|
| 2026-04-13T21:18:25.652639Z | archive-and-reset-report-collections | `can-r0b70` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260413T211825Z/archive_manifest.json) |
| 2026-04-13T21:17:28.353226Z | archive-and-delete-report-collection | `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_liv-rd3bb_20260413T211728Z/archive_manifest.json) |
| 2026-04-13T21:16:41.968582Z | archive-and-delete-report-collection | `liv-r8bc9` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_liv-r8bc9_20260413T211641Z/archive_manifest.json) |
| 2026-04-13T17:17:40.782891Z | archive-and-delete-report-collection | `liv-rd3bb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_liv-rd3bb_20260413T171740Z/archive_manifest.json) |
| 2026-04-11T03:45:58.236289Z | archive-and-reset-report-collections | `INDEX.md`, `aggregates`, `reference`, `collections` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260411T034558Z/archive_manifest.json) |
| 2026-04-11T03:44:50.481570Z | archive-and-delete-report-collection | `p3-demo-current-20260406` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_p3-demo-current-20260406_20260411T034450Z/archive_manifest.json) |
| 2026-04-11T03:44:40.491440Z | archive-and-delete-report-collection | `dataset-d7c0eb` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collection_delete_dataset-d7c0eb_20260411T034440Z/archive_manifest.json) |
| 2026-04-10T15:30:44.549261Z | archive-and-reset-report-collections | `p3-demo-current-20260406` | [archive_manifest.json](../../../local_untracked/analysis/vaults/librarian/quarantine/tracked_reports/calamum-moltbook-observer/report_collections_reset_20260410T153044Z/archive_manifest.json) |
