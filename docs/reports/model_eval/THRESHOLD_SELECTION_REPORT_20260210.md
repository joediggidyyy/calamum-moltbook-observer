# Threshold Selection Report

**Date**: New
**Dataset**: canary_v1_iforest_scores.csv
**Target FPR**: 1.00%
**Logic**: Isolation Forest (Lower Score = More Anomalous)

## Result
- **Selected Threshold**: `-0.045089`
- **Observed FPR**: 1.0005% (1339/133837 records)

## Override Note

- Strict target threshold was `<= 1.0000%` FPR.
- Observed variance is `+0.0005%`.
- Operator override approved by `joediggidyyy` on `2026-02-24T18:09:39Z`; closure authorized without post-mortem gate reruns.

## Distribution Stats
- Min: -0.078014
- Max: 0.133836
- Mean: 0.059508
- Median: 0.061537

## Usage
Scores **lower** than `-0.045089` should be flagged as Anomalies.
