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
- Published runs: 5
- Collection aliases represented: 2
- Workflow families represented: 4
- Threshold-bearing packets: 1
- Latest packet: [can-r7af3](../collections/can-r7af3/collection/20260405T044605627549Z.collection.md)

## Current lane census

| Workflow | Published packets | Latest collection | Latest packet |
|---|---:|---|---|
| build | 2 | `can-r7af3` | [20260405T042201056997Z.build.md](../collections/can-r7af3/processing/build/20260405T042201056997Z.build.md) |
| evaluate | 1 | `can-r7af3` | [20260405T043759419248Z.eval.md](../collections/can-r7af3/processing/eval/20260405T043759419248Z.eval.md) |
| score | 1 | `can-r7af3` | [20260405T044605627549Z.score.md](../collections/can-r7af3/processing/score/20260405T044605627549Z.score.md) |
| train | 1 | `can-r7af3` | [20260405T042505512273Z.train.md](../collections/can-r7af3/processing/train/20260405T042505512273Z.train.md) |

## Publication-family census

| Collection alias | Source / mode | Published packets | Latest packet date | Latest stages | Collection packet |
|---|---|---:|---|---|---|
| `can-r7af3` | runtime-unspecified | 4 | 2026-04-05T04:46:05.627549Z | build, evaluate, score, train | [collection packet](../collections/can-r7af3/collection/20260405T044605627549Z.collection.md) |
| `can-r305f` | runtime-unspecified | 1 | 2026-04-05T04:20:49.878075Z | build | [collection packet](../collections/can-r305f/collection/20260405T042049878075Z.collection.md) |

## Publication-source census

| Source | Mode | Published packets |
|---|---|---:|
| unspecified | unspecified | 5 |

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
