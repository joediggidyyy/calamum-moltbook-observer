# Aggregate Report

This synthesis page summarizes the strongest current reader-facing conclusions across the tracked report family.

## Executive summary

- Published packets: 13
- Collection aliases represented: 3
- Workflow families represented: 4
- Threshold-bearing packets: 4
- Current front-door packet: [liv-rd3bb](../collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md)

## Why this aggregate exists

The tracked report family now has multiple reader roles: packet entry, workflow rollup, threshold interpretation, population census, and synthesis. This page provides the flagship narrative view over that family.

## Runtime-safe current picture

- Latest published workflow: evaluate
- Latest packet timestamp (UTC): 2026-04-13T07:34:46.351438Z
- Latest packet summary: Evaluation completed through observerctl ds.

## What to open first

| Collection alias | Current packet date | Latest stages | Current focus | Collection packet |
|---|---|---|---|---|
| `liv-rd3bb` | 2026-04-13T07:34:46.351438Z | build, evaluate, train | Evaluation packet with current threshold and guardrail follow-through. | [collection packet](../collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md) |
| `liv-r8bc9` | 2026-04-13T02:41:19.308328Z | build, train | Training handoff packet for the current model-publication lane. | [collection packet](../collections/liv-r8bc9/collection/20260413T024119308328Z.collection.md) |
| `can-r0b70` | 2026-04-13T01:28:01.395015Z | build, evaluate, score, train | Evaluation packet with current threshold and guardrail follow-through. | [collection packet](../collections/can-r0b70/collection/20260413T012801395015Z.collection.md) |

## Current packet family at a glance

- Collections with figure-backed packets: 3
- Collections with threshold-bearing packets: 2
- Current packet summary: Evaluation completed through observerctl ds.
- Current front-door packet: [liv-rd3bb](../collections/liv-rd3bb/collection/20260413T073446351438Z.collection.md)

## Strongest findings

- The tracked report family is now organized around 3 collection aliases instead of a single cache-shaped run list.
- Collection packets now act as reader-first entry surfaces rather than history-only routing stubs.
- Workflow coverage is currently spread across `build`, `evaluate`, `score`, `train`.
- Threshold-bearing packets remain visible as dated packet leaves, with the latest threshold summary routed through `THRESHOLD_SUMMARY.md`.

## Workflow and threshold synthesis

| Workflow family | Published packets | Latest collection | Current contribution |
|---|---:|---|---|
| build | 3 | `liv-rd3bb` | Defines the dataset packet baseline. |
| evaluate | 4 | `liv-rd3bb` | Captures validation and threshold interpretation. |
| score | 1 | `can-r0b70` | Captures scored anomaly output for reader follow-through. |
| train | 5 | `liv-rd3bb` | Carries the latest model-training outcome. |

| Threshold-bearing packet | Threshold | Target guardrail | Eval packet |
|---|---:|---:|---|
| `liv-rd3bb` / `evaluate_20260413T073446087621Z` | 0 | 0.01 | [eval packet](../collections/liv-rd3bb/processing/eval/20260413T073446351438Z.eval.md) |
| `liv-rd3bb` / `evaluate_20260413T073044783730Z` | 0 | 0.01 | [eval packet](../collections/liv-rd3bb/processing/eval/20260413T073045558853Z.eval.md) |
| `can-r0b70` / `evaluate_20260413T011803992045Z` | 0.434329 | 0.01 | [eval packet](../collections/can-r0b70/processing/eval/20260413T012801395015Z.eval.md) |
| `can-r0b70` / `evaluate_20260412T181954946962Z` | 0.434329 | 0.01 | [eval packet](../collections/can-r0b70/processing/eval/20260412T182621255204Z.eval.md) |

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
