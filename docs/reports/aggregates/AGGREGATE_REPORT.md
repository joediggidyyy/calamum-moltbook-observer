# Aggregate Report

This synthesis page summarizes the strongest current reader-facing conclusions across the tracked report family.

## Executive summary

- Published packets: 4
- Collection aliases represented: 2
- Workflow families represented: 4
- Threshold-bearing packets: 1
- Current front-door packet: [can-r4ccf](../collections/can-r4ccf/collection/20260412T183143055972Z.collection.md)

## Why this aggregate exists

The tracked report family now has multiple reader roles: packet entry, workflow rollup, threshold interpretation, population census, and synthesis. This page provides the flagship narrative view over that family.

## Runtime-safe current picture

- Latest published workflow: score
- Latest packet timestamp (UTC): 2026-04-12T18:31:43.055972Z
- Latest packet summary: Unsupervised scoring completed through observerctl ds.

## What to open first

| Collection alias | Current packet date | Latest stages | Current focus | Collection packet |
|---|---|---|---|---|
| `can-r4ccf` | 2026-04-12T18:31:43.055972Z | evaluate, score, train | Score-stage packet with figure-backed anomaly-surface context. | [collection packet](../collections/can-r4ccf/collection/20260412T183143055972Z.collection.md) |
| `can-r0b70` | 2026-04-12T18:11:42.763215Z | build | Build-stage packet for current dataset-materialization readiness. | [collection packet](../collections/can-r0b70/collection/20260412T181142763215Z.collection.md) |

## Current packet family at a glance

- Collections with figure-backed packets: 2
- Collections with threshold-bearing packets: 1
- Current packet summary: Unsupervised scoring completed through observerctl ds.
- Current front-door packet: [can-r4ccf](../collections/can-r4ccf/collection/20260412T183143055972Z.collection.md)

## Strongest findings

- The tracked report family is now organized around 2 collection aliases instead of a single cache-shaped run list.
- Collection packets now act as reader-first entry surfaces rather than history-only routing stubs.
- Workflow coverage is currently spread across `build`, `evaluate`, `score`, `train`.
- Threshold-bearing packets remain visible as dated packet leaves, with the latest threshold summary routed through `THRESHOLD_SUMMARY.md`.

## Workflow and threshold synthesis

| Workflow family | Published packets | Latest collection | Current contribution |
|---|---:|---|---|
| build | 1 | `can-r0b70` | Defines the dataset packet baseline. |
| evaluate | 1 | `can-r4ccf` | Captures validation and threshold interpretation. |
| score | 1 | `can-r4ccf` | Captures scored anomaly output for reader follow-through. |
| train | 1 | `can-r4ccf` | Carries the latest model-training outcome. |

| Threshold-bearing packet | Threshold | Target guardrail | Eval packet |
|---|---:|---:|---|
| `can-r4ccf` / `evaluate_20260412T181954946962Z` | 0.434329 | 0.01 | [eval packet](../collections/can-r4ccf/processing/eval/20260412T182621255204Z.eval.md) |

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
