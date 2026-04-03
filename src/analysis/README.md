# Calamum Blind ML (DATA780) - Analysis Home

This directory contains **privacy-preserving** dataset and evaluation tooling for the Calamum Moltbook Observer.

## Non-negotiables

- **No semantic leakage**: inputs and outputs must not contain raw message bodies.
- **Names-only evidence**: reports/manifests must not embed secrets, tokens, or internal endpoints.
- **Reproducibility**: dataset manifests and deterministic splits are first-class artifacts.
- **Approved package lane**: ApexLab `1.2.0` is the preferred training/evaluation surface for the supported observer ML path.

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
- `train_model.py` - train ApexLab models (Supervised or Unsupervised)
- `evaluation_harness.py` - evaluate models and generate run ledgers

## Current migration note

- the supported observer model lane now targets ApexLab-owned estimators for supervised and unsupervised training
- unsupervised anomaly semantics in the DS report lane are: **lower score = more anomalous**
- old sklearn-oriented wording in historical planning docs should be treated as background context rather than current execution authority

## Reader-facing DS documentation

Use these tracked docs when you want the public-facing command and reporting route:

- `../../docs/manuals/data-science/DS_OPERATIONS.md`
- `../../docs/manuals/data-science/DS_WIZARD.md`
- `../../docs/reports/ds/INDEX.md`

Historical planning context remains available in:

- `../../planning/CALAMUM_BLIND_ML_EXECUTION_PLAN_2026-02-10.md`
- `../../planning/CALAMUM_MODEL_TRAINING_GAP_ANALYSIS_20260210.md`
