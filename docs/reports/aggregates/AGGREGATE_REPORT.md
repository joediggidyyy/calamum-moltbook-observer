# Aggregate Report

This synthesis page summarizes the strongest current reader-facing conclusions across the tracked report family.

## Executive summary

- Published packets: 5
- Collection aliases represented: 2
- Workflow families represented: 4
- Threshold-bearing packets: 1
- Current front-door packet: [can-r7af3](../collections/can-r7af3/collection/20260405T044605627549Z.collection.md)

## Why this aggregate exists

The tracked report family now has multiple reader roles: packet entry, workflow rollup, threshold interpretation, population census, and synthesis. This page provides the flagship narrative view over that family.

## Runtime-safe current picture

- Latest published workflow: score
- Latest packet timestamp (UTC): 2026-04-05T04:46:05.627549Z
- Latest packet summary: Unsupervised scoring completed through observerctl ds.

## Aggregate cohort at a glance

| Collection alias | Current packet date | Latest stages | Why it matters now | Collection packet |
|---|---|---|---|---|
| `can-r7af3` | 2026-04-05T04:46:05.627549Z | build, evaluate, score, train | Scoring packet with the latest anomaly output. | [collection packet](../collections/can-r7af3/collection/20260405T044605627549Z.collection.md) |
| `can-r305f` | 2026-04-05T04:20:49.878075Z | build | Dataset-build packet for the latest materialized collection. | [collection packet](../collections/can-r305f/collection/20260405T042049878075Z.collection.md) |

## Strongest findings

- The tracked report family is now organized around 2 collection aliases instead of a single cache-shaped run list.
- Workflow coverage is currently spread across `build`, `evaluate`, `score`, `train`.
- Threshold-bearing packets remain visible as dated packet leaves, with the latest threshold summary routed through `THRESHOLD_SUMMARY.md`.

## Threshold, workflow, and packet synthesis

| Workflow family | Published packets | Latest collection | Current contribution |
|---|---:|---|---|
| build | 2 | `can-r7af3` | Defines the dataset packet baseline. |
| evaluate | 1 | `can-r7af3` | Captures validation and threshold interpretation. |
| score | 1 | `can-r7af3` | Captures scored anomaly output for reader follow-through. |
| train | 1 | `can-r7af3` | Carries the latest model-training outcome. |

| Threshold-bearing packet | Threshold | Target guardrail | Eval packet |
|---|---:|---:|---|
| `can-r7af3` / `evaluate_20260405T043000438719Z` | 0.434329 | 0.01 | [eval packet](../collections/can-r7af3/processing/eval/20260405T043759419248Z.eval.md) |

## Limits and caution notes

- This page is derived and reader-facing; it does not replace the machine-readable authority surfaces.
- Row-completeness and deeper truthfulness audits remain a downstream concern when packet content needs further repair.
- Missing links fail closed rather than inventing synthetic packet routes.

## Related authority and lineage

- Publish root: `docs/reports`
- Public run ledger: [PUBLIC_RUN_LEDGER.md](PUBLIC_RUN_LEDGER.md)
- Generated report surfaces: [GENERATED_REPORT_SURFACES.md](../reference/GENERATED_REPORT_SURFACES.md)

## Reader next steps

- Open [LATEST_COLLECTIONS.md](LATEST_COLLECTIONS.md) for the fastest packet-entry lane.
- Open [WORKFLOW_ROLLUP.md](WORKFLOW_ROLLUP.md) for workflow-family routing.
- Open [THRESHOLD_SUMMARY.md](THRESHOLD_SUMMARY.md) for threshold-bearing packet follow-through.
