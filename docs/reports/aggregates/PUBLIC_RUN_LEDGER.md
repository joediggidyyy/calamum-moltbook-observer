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
- Published runs: 4
- Collection aliases represented: 2
- Workflow families represented: 4
- Threshold-bearing packets: 1
- Latest packet: [can-r4ccf](../collections/can-r4ccf/collection/20260412T183143055972Z.collection.md)

## Current lane census

| Workflow | Published packets | Latest collection | Latest packet |
|---|---:|---|---|
| build | 1 | `can-r0b70` | [20260412T181142763215Z.build.md](../collections/can-r0b70/processing/build/20260412T181142763215Z.build.md) |
| evaluate | 1 | `can-r4ccf` | [20260412T182621255204Z.eval.md](../collections/can-r4ccf/processing/eval/20260412T182621255204Z.eval.md) |
| score | 1 | `can-r4ccf` | [20260412T183143055972Z.score.md](../collections/can-r4ccf/processing/score/20260412T183143055972Z.score.md) |
| train | 1 | `can-r4ccf` | [20260412T181602715320Z.train.md](../collections/can-r4ccf/processing/train/20260412T181602715320Z.train.md) |

## Publication-family census

| Collection alias | Source / mode | Published packets | Latest packet date | Latest stages | Collection packet |
|---|---|---:|---|---|---|
| `can-r4ccf` | runtime-unspecified | 3 | 2026-04-12T18:31:43.055972Z | evaluate, score, train | [collection packet](../collections/can-r4ccf/collection/20260412T183143055972Z.collection.md) |
| `can-r0b70` | runtime-unspecified | 1 | 2026-04-12T18:11:42.763215Z | build | [collection packet](../collections/can-r0b70/collection/20260412T181142763215Z.collection.md) |

## Publication-source census

| Source | Mode | Published packets |
|---|---|---:|
| unspecified | unspecified | 4 |

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
