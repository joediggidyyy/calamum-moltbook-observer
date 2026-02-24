# JOB: Calamum/Moltbook Observer - Inference & Threshold Implementation (Phase 6)

**Job ID**: CALAMUM_JOB_0013_MOLTBOOK_OBSERVER_INFERENCE_IMPL_20260210
**Date**: 2026-02-10
**Status**: COMPLETED
**Owner**: ORACL-Prime
**Frame**: 0013

---

## 1. Objectives

Execute Phase 6 of the Calamum Blind ML Plan by implementing the inference and thresholding logic for "Hostile Agent" detection:

1) **Enable Inference**
   - Implement `src/analysis/score_unsupervised.py` to load trained models and apply them to new datasets (synthetic or canary) to generate anomaly scores.

2) **Enforce FPR Constraint**
   - Implement `src/analysis/threshold_selection.py` to automatically calculate the optimal anomaly score threshold that keeps the False Positive Rate (FPR) below 1% on benign data.

3) **Formal Reporting**
   - Establish the `TRAINING_LEDGER.md` to track reproducible experiments.
   - Generate a "Threshold Selection Report" proving the <1% FPR.

---

## 2. Scope

### 2.1 In-scope components
Located under: `projects/calamum-moltbook-observer/src/analysis/`

- `score_unsupervised.py` (New): Scorer application.
- `threshold_selection.py` (New): Calibration logic.
- `deliverables/DATA780/TRAINING_LEDGER.md` (New): Experiment ledger.

### 2.2 Planning References
- `planning/CALAMUM_BLIND_ML_EXECUTION_PLAN_2026-02-10.md` (Phase 6, 8)

---

## 3. Execution Ledger

### 3.1 Changes
- Implemented `Scorer` class using `joblib` and `pandas`.
- Implemented `ThresholdSelector` using `numpy.percentile`.
- Run calibration against `canary_v1` dataset.

### 3.2 Results (Run 001)
- **Dataset**: `canary_v1` (133,837 records)
- **Model**: `canary_v1_isolation_forest` (Job 12)
- **Objective**: Determine threshold for < 1% FPR.
- **Outcome**: 
  - Threshold: `-0.045089`
  - Observed FPR: `1.0005%` (1339 anomalies / 133837 total)
  - Report: `docs/reports/model_eval/THRESHOLD_SELECTION_REPORT_20260210.md`
   - Operator override: accepted variance of `+0.0005%` relative to the strict `<=1.0%` target and authorized close without post-mortem gate reruns (`2026-02-24T18:09:39Z`).

---

## 4. Acceptance Criteria

- [x] `score_unsupervised.py` outputs anomaly scores for input JSONL/CSV.
- [x] `threshold_selection.py` outputs a specific threshold value and an FPR report.
- [x] The reported FPR on the benign validation set is accepted for closure via explicit operator override (`1.0005%`, variance `+0.0005%`).
- [x] `TRAINING_LEDGER.md` contains at least one entry linking to a `run.json`.
