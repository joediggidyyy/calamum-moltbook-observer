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
- Published runs: 10
- Collection aliases represented: 6
- Workflow families represented: 4
- Threshold-bearing packets: 1
- Latest packet: [can-r7af3](../collections/can-r7af3/collection/20260406T072118262659Z.collection.md)

## Current lane census

| Workflow | Published packets | Latest collection | Latest packet |
|---|---:|---|---|
| build | 6 | `build_20260406T023758094814Z` | [20260406T023758115802Z.build.md](../collections/build_20260406T023758094814Z/processing/build/20260406T023758115802Z.build.md) |
| evaluate | 1 | `can-r7af3` | [20260405T043759419248Z.eval.md](../collections/can-r7af3/processing/eval/20260405T043759419248Z.eval.md) |
| score | 1 | `can-r7af3` | [20260405T044605627549Z.score.md](../collections/can-r7af3/processing/score/20260405T044605627549Z.score.md) |
| train | 2 | `can-r7af3` | [20260406T072118262659Z.train.md](../collections/can-r7af3/processing/train/20260406T072118262659Z.train.md) |

## Publication-family census

| Collection alias | Source / mode | Published packets | Latest packet date | Latest stages | Collection packet |
|---|---|---:|---|---|---|
| `can-r7af3` | runtime-unspecified | 5 | 2026-04-06T07:21:18.262659Z | build, evaluate, score, train | [collection packet](../collections/can-r7af3/collection/20260406T072118262659Z.collection.md) |
| `build_20260406T023758094814Z` | runtime-unspecified | 1 | 2026-04-06T02:37:58.115802Z | build | [collection packet](../collections/build_20260406T023758094814Z/collection/20260406T023758115802Z.collection.md) |
| `build_20260406T023756969475Z` | runtime-unspecified | 1 | 2026-04-06T02:37:56.987764Z | build | [collection packet](../collections/build_20260406T023756969475Z/collection/20260406T023756987764Z.collection.md) |
| `build_20260405T081918876049Z` | runtime-unspecified | 1 | 2026-04-05T08:19:18.888509Z | build | [collection packet](../collections/build_20260405T081918876049Z/collection/20260405T081918888509Z.collection.md) |
| `build_20260405T081918058977Z` | runtime-unspecified | 1 | 2026-04-05T08:19:18.074431Z | build | [collection packet](../collections/build_20260405T081918058977Z/collection/20260405T081918074431Z.collection.md) |
| `can-r305f` | runtime-unspecified | 1 | 2026-04-05T04:20:49.878075Z | build | [collection packet](../collections/can-r305f/collection/20260405T042049878075Z.collection.md) |

## Publication-source census

| Source | Mode | Published packets |
|---|---|---:|
| unspecified | unspecified | 10 |

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
