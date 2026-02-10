# Calamum Blind ML (DATA780) - Analysis Home

This directory contains **privacy-preserving** dataset and evaluation tooling for the Calamum Moltbook Observer.

## Non-negotiables

- **No semantic leakage**: inputs and outputs must not contain raw message bodies.
- **Names-only evidence**: reports/manifests must not embed secrets, tokens, or internal endpoints.
- **Reproducibility**: dataset manifests and deterministic splits are first-class artifacts.
- **Approved dependencies**: `scikit-learn` (v1.6+) is authorized for Model Training (Phase 5).

## What this tooling does

1. Validate JSONL telemetry against a safe schema contract (and optionally verify signatures).
2. Build a simple feature dataset (CSV) from telemetry records.
3. Produce deterministic train/val/test splits.
4. Train supervised (Random Forest) or unsupervised (Isolation Forest) models.
5. Evaluate models and emit run-ledger artifacts (`run.json` + `run.md`).

## Where inputs come from

Default Calamum telemetry location is (project-local):

- `logs/data/calamum/*.jsonl`

Common inputs:

- `logs/data/calamum/moltbook_canary_metrics.jsonl`
- `logs/data/calamum/moltbook_sampler_metrics.jsonl`

## Where outputs go

Outputs default to project-local ignored storage:

- `local_untracked/analysis/`

This is gitignored by design.

## Entry points

- `validate_jsonl.py` - validate records (and optionally verify HMAC signatures)
- `dataset_builder.py` - build features + manifest + deterministic splits
- `train_model.py` - train scikit-learn models (Supervised or Unsupervised)
- `evaluation_harness.py` - evaluate models and generate run ledgers

See the ML execution plan:

- `../../planning/CALAMUM_BLIND_ML_EXECUTION_PLAN_2026-02-10.md`
- `../../planning/CALAMUM_MODEL_TRAINING_GAP_ANALYSIS_20260210.md`
