# Calamum Blind ML (DATA780) - Analysis Home

This directory contains **privacy-preserving** dataset and evaluation tooling for the Calamum Moltbook Observer.

## Non-negotiables

- **No semantic leakage**: inputs and outputs must not contain raw message bodies.
- **Names-only evidence**: reports/manifests must not embed secrets, tokens, or internal endpoints.
- **Reproducibility**: dataset manifests and deterministic splits are first-class artifacts.
- **No new dependencies**: this tooling uses only the Python standard library unless explicitly approved.

## What this tooling does

1. Validate JSONL telemetry against a safe schema contract (and optionally verify signatures).
2. Build a simple feature dataset (CSV) from telemetry records.
3. Produce deterministic train/val/test splits.
4. Run a **baseline** heuristic scorer and emit run-ledger artifacts (`run.json` + `run.md`).

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
- `build_dataset.py` - build features + manifest + deterministic splits
- `evaluate_baseline.py` - baseline evaluation + run ledger artifacts

See the ML execution plan:

- `../../planning/CALAMUM_BLIND_ML_EXECUTION_PLAN_2026-02-10.md`
