# Calamum Observer: Training Ledger

A verifiable log of model training experiments, tracking data snapshots, code versions, and governance constraints.

**Governance Authority**: `ORACL-Prime`
**Constraint**: BLIND-ML (No Raw Payloads)
**Target**: <1.0% False Positive Rate (Unsupervised)

| Run ID | Date | Model Type | Dataset Hash (Manifest) | Git SHA | Result / Status | Artifacts |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **000 (Demo)** | 2026-02-10 | IsolationForest | `dataset/canary_v1` | `(Current)` | **PASS** (Synthetic) | `local_untracked/...` |

## Ledger Entries

### Run 000: Initial Capability Demo
- **Date**: 2026-02-10
- **Purpose**: Validation of pipeline capability (Job 0012).
- **Outcome**: Successful execution of `train_model.py` and `evaluation_harness.py`.
- **Metrics**: 100% Accuracy (Synthetic/Trivial data).
- **Artifacts**: `local_untracked/analysis/models/supervised/train_manifest.json`

### Run 001: Canary Unsupervised Calibration (Job 0013)
- **Date**: 2026-02-10
- **Model**: `canary_v1_isolation_forest` (Job 0012 Artifact)
- **Task**: Anomaly Scoring & Threshold Selection
- **Outcome**: **PASS** (<1% FPR Enforced)
- **Metrics**: Threshold `-0.045089` yields `1.00%` FPR on 133,837 samples.
- **Report**: `projects/calamum-moltbook-observer/deliverables/DATA780/CANARY_V1_INFERENCE_REPORT_20260210.md`

---

*New entries append above.*
