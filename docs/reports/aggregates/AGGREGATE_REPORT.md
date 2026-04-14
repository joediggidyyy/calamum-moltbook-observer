# Aggregate Report

This synthesis page summarizes the strongest current reader-facing conclusions across the tracked report family.

## Executive summary

- Published packets: 2
- Collection aliases represented: 2
- Workflow families represented: 2
- Threshold-bearing packets: 0
- Current front-door packet: [liv-rd3bb](../collections/liv-rd3bb/collection/20260414T094516753389Z.collection.md)

## Why this aggregate exists

The tracked report family now has multiple reader roles: packet entry, workflow rollup, threshold interpretation, population census, and synthesis. This page provides the flagship narrative view over that family.

## Runtime-safe current picture

- Latest published workflow: train
- Latest packet timestamp (UTC): 2026-04-14T09:45:16.753389Z
- Latest packet summary: Model training completed through observerctl ds.

## What to open first

| Collection alias | Current packet date | Latest stages | Current focus | Collection packet |
|---|---|---|---|---|
| `liv-rd3bb` | 2026-04-14T09:45:16.753389Z | train | Training handoff packet for the current model-publication lane. | [collection packet](../collections/liv-rd3bb/collection/20260414T094516753389Z.collection.md) |
| `can-r0b70` | 2026-04-14T09:40:15.247284Z | score | Score-stage packet with figure-backed anomaly-surface context. | [collection packet](../collections/can-r0b70/collection/20260414T094015247284Z.collection.md) |

## Current packet family at a glance

- Collections with figure-backed packets: 1
- Collections with threshold-bearing packets: 0
- Current packet summary: Model training completed through observerctl ds.
- Current front-door packet: [liv-rd3bb](../collections/liv-rd3bb/collection/20260414T094516753389Z.collection.md)

## Strongest findings

- The tracked report family is now organized around 2 collection aliases instead of a single cache-shaped run list.
- Collection packets now act as reader-first entry surfaces rather than history-only routing stubs.
- Workflow coverage is currently spread across `score`, `train`.
- No threshold-bearing packets are currently present in the tracked family.

## Workflow and threshold synthesis

| Workflow family | Published packets | Latest collection | Current contribution |
|---|---:|---|---|
| score | 1 | `can-r0b70` | Captures scored anomaly output for reader follow-through. |
| train | 1 | `liv-rd3bb` | Carries the latest model-training outcome. |

## Limits and caution notes

- This page is derived and reader-facing; it does not replace the machine-readable authority surfaces.
- Row-completeness and deeper truthfulness audits remain a downstream concern when packet content needs further repair.
- Missing links fail closed rather than inventing synthetic packet routes.

## Related surfaces

- Publish root: `docs/reports`
- Public run ledger: [PUBLIC_RUN_LEDGER.md](PUBLIC_RUN_LEDGER.md)
- Latest collections: [LATEST_COLLECTIONS.md](LATEST_COLLECTIONS.md)
- Workflow rollup: [WORKFLOW_ROLLUP.md](WORKFLOW_ROLLUP.md)
- Threshold summary: [THRESHOLD_SUMMARY.md](THRESHOLD_SUMMARY.md)
- Generated report surfaces: [GENERATED_REPORT_SURFACES.md](../reference/GENERATED_REPORT_SURFACES.md)

## Reader next steps

- Open [LATEST_COLLECTIONS.md](LATEST_COLLECTIONS.md) for the fastest packet-entry lane.
- Open [WORKFLOW_ROLLUP.md](WORKFLOW_ROLLUP.md) for workflow-family routing.
- Open [THRESHOLD_SUMMARY.md](THRESHOLD_SUMMARY.md) for threshold-bearing packet follow-through.
