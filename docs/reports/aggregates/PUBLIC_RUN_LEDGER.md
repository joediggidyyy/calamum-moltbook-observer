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
- Published runs: 13
- Collection aliases represented: 3
- Workflow families represented: 4
- Threshold-bearing packets: 4
- Latest packet: [liv-rd3bb](../collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md)

## Current lane census

| Workflow | Published packets | Latest collection | Latest packet |
|---|---:|---|---|
| build | 3 | `liv-rd3bb` | [20260413T024620493383Z.build.md](../collections/liv-rd3bb/processing/build/20260413T024620493383Z.build.md) |
| evaluate | 4 | `liv-rd3bb` | [20260413T073446351438Z.eval.md](../collections/liv-rd3bb/processing/eval/20260413T073446351438Z.eval.md) |
| score | 1 | `can-r0b70` | [20260412T183143055972Z.score.md](../collections/can-r0b70/processing/score/20260412T183143055972Z.score.md) |
| train | 5 | `liv-rd3bb` | [20260413T073300032775Z.train.md](../collections/liv-rd3bb/processing/train/20260413T073300032775Z.train.md) |

## Publication-family census

| Collection alias | Source / mode | Published packets | Latest packet date | Latest stages | Collection packet |
|---|---|---:|---|---|---|
| `liv-rd3bb` | runtime-unspecified | 5 | 2026-04-13T07:34:46.351438Z | build, evaluate, train | [collection packet](../collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) |
| `liv-r8bc9` | runtime-unspecified | 2 | 2026-04-13T02:41:19.308328Z | build, train | [collection packet](../collections/liv-r8bc9/collection/20260413T024119308328Z.collection.md) |
| `can-r0b70` | runtime-unspecified | 6 | 2026-04-13T01:28:01.395015Z | build, evaluate, score, train | [collection packet](../collections/can-r0b70/collection/20260413T012801395015Z.collection.md) |

## Publication-source census

| Source | Mode | Published packets |
|---|---|---:|
| unspecified | unspecified | 13 |

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
