# Gap Analysis: Calamum Model Training Implementation (Phase 5)

## Metadata

- Title: Calamum Model Training Gap Analysis
- Owner: ORACL-Prime
- Stakeholders: joediggidyyy
- Date: 2026-02-10
- Expected Window: 2026-02-10 (Immediate)
- Referenced Plan: `planning/CALAMUM_BLIND_ML_EXECUTION_PLAN_2026-02-10.md`

## 1. Context

The Calamum Observer project has successfully implemented the "Blind ML" scaffolding (Dataset Builder, Evaluation Harness) under Job 0011. However, the actual **Model Training** capability (Phase 5) was blocked due to a missing dependency decision regarding `scikit-learn`.

**Status Update**: `scikit-learn` has been explicitly approved for inclusion (2026-02-10).

## 2. Gap Identification

The current codebase (`src/analysis/`) lacks the following components required to execute Phase 5:

1.  **Training Entrypoint**: No script exists to consume the dataset and produce a serialized model.
    *   *Requirement*: `src/analysis/train_supervised.py`
2.  **Unsupervised Logic**: No script exists for Isolation Forest (anomaly detection) training.
    *   *Requirement*: `src/analysis/train_unsupervised.py` (or consolidated into `train_supervised` modes).
3.  **Dependencies**: `scikit-learn` is not in `requirements.txt`.
4.  **Model Registry**: No defined path/schema for saving trained artifacts (`.joblib`, `.pkl`) alongside the `run.json`.

## 3. Implementation Plan (Job 0012)

We will execute **Job 0012: Calamum Model Training Implementation** to close these gaps.

### 3.1 Dependencies
- Add `scikit-learn` to `projects/calamum-moltbook-observer/src/requirements.txt`.

### 3.2 Code Artifacts
- **`src/analysis/train_model.py`**:
    - Unified entrypoint for Supervised (RandomForest) and Unsupervised (IsolationForest) training.
    - Inputs: `dataset/manifest.json`, `split_manifest.json`
    - Outputs: `models/<run_id>/model.joblib`, `models/<run_id>/metadata.json`
- **Updates to `evaluation_harness.py`**:
    - Add capability to load a trained model and run it against the Test split (currently only runs heuristics).

### 3.3 Privacy & Policy
- **Constraint**: Models must NOT be trained on raw message content (enforced by Dataset Builder schema).
- **Constraint**: Training runs must be deterministic (fixed seed).

## 4. Estimator Inputs

- size: 2 files (~300 LOC)
- integration_points: 2 (Dataset generic reader -> Model -> Eval generic writer)
- tests_needed: 2 (`test_train_smoke`, `test_model_persistence`)
- docs_needed: yes (Update `src/analysis/README.md`)
- approvals_needed: 1 (Post-job review)
- risk: 2 (Low - Offline analysis only)
