# Aggregate Report

This synthesis page summarizes the strongest current reader-facing conclusions across the tracked report family.

## Executive summary

- Published packets: 5
- Collection aliases represented: 1
- Workflow families represented: 4
- Threshold-bearing packets: 1
- Current front-door packet: [p3-demo-current-20260406](../collections/p3-demo-current-20260406/collection/20260406T213205644819Z.collection.md)

## Why this aggregate exists

The tracked report family now has multiple reader roles: packet entry, workflow rollup, threshold interpretation, population census, and synthesis. This page provides the flagship narrative view over that family.

## Runtime-safe current picture

- Latest published workflow: build
- Latest packet timestamp (UTC): 2026-04-06T21:32:05.644819Z
- Latest packet summary: Approved dataset materialized through observerctl ds.

## What to open first

| Collection alias | Current packet date | Latest stages | Current focus | Collection packet |
|---|---|---|---|---|
| `p3-demo-current-20260406` | 2026-04-06T21:32:05.644819Z | build, evaluate, score, train | Build-stage packet for current dataset-materialization readiness. | [collection packet](../collections/p3-demo-current-20260406/collection/20260406T213205644819Z.collection.md) |

## Current packet family at a glance

- Collections with figure-backed packets: 1
- Collections with threshold-bearing packets: 1
- Current packet summary: Approved dataset materialized through observerctl ds.
- Current front-door packet: [p3-demo-current-20260406](../collections/p3-demo-current-20260406/collection/20260406T213205644819Z.collection.md)

## Strongest findings

- The tracked report family is now organized around 1 collection aliases instead of a single cache-shaped run list.
- Collection packets now act as reader-first entry surfaces rather than history-only routing stubs.
- Workflow coverage is currently spread across `build`, `evaluate`, `score`, `train`.
- Threshold-bearing packets remain visible as dated packet leaves, with the latest threshold summary routed through `THRESHOLD_SUMMARY.md`.

## Workflow and threshold synthesis

| Workflow family | Published packets | Latest collection | Current contribution |
|---|---:|---|---|
| build | 2 | `p3-demo-current-20260406` | Defines the dataset packet baseline. |
| evaluate | 1 | `p3-demo-current-20260406` | Captures validation and threshold interpretation. |
| score | 1 | `p3-demo-current-20260406` | Captures scored anomaly output for reader follow-through. |
| train | 1 | `p3-demo-current-20260406` | Carries the latest model-training outcome. |

| Threshold-bearing packet | Threshold | Target guardrail | Eval packet |
|---|---:|---:|---|
| `p3-demo-current-20260406` / `evaluate_20260406T211232484108Z` | 0 | 0.01 | [eval packet](../collections/p3-demo-current-20260406/processing/eval/20260406T211246486478Z.eval.md) |

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
