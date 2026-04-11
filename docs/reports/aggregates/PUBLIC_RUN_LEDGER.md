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
- Published runs: 3
- Collection aliases represented: 1
- Workflow families represented: 3
- Threshold-bearing packets: 0
- Latest packet: [liv-r8bc9](../collections/liv-r8bc9/collection/20260411T042459318423Z.collection.md)

## Current lane census

| Workflow | Published packets | Latest collection | Latest packet |
|---|---:|---|---|
| build | 1 | `liv-r8bc9` | [20260411T042409067088Z.build.md](../collections/liv-r8bc9/processing/build/20260411T042409067088Z.build.md) |
| score | 1 | `liv-r8bc9` | [20260411T042459318423Z.score.md](../collections/liv-r8bc9/processing/score/20260411T042459318423Z.score.md) |
| train | 1 | `liv-r8bc9` | [20260411T042436698004Z.train.md](../collections/liv-r8bc9/processing/train/20260411T042436698004Z.train.md) |

## Publication-family census

| Collection alias | Source / mode | Published packets | Latest packet date | Latest stages | Collection packet |
|---|---|---:|---|---|---|
| `liv-r8bc9` | runtime-unspecified | 3 | 2026-04-11T04:24:59.318423Z | build, score, train | [collection packet](../collections/liv-r8bc9/collection/20260411T042459318423Z.collection.md) |

## Publication-source census

| Source | Mode | Published packets |
|---|---|---:|
| unspecified | unspecified | 3 |

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
