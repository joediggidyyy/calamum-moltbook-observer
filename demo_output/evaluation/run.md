# Training Run: demo_run_001

**Created (UTC)**: 2026-02-10T18:14:27.489305Z  
**Operator**: ORACL-Prime  

## Abstract
Evaluation run artifacts.

## Data provenance and governance
- Inputs are obfuscated JSONL telemetry (no raw message bodies).
- Reports are names-only; no secrets or internal endpoints are included.

## Model
- Family: trained_sklearn
- Name: model.joblib
- Threshold: 1.0

## Evaluation
- Labeled mode: yes
- Max FPR constraint: 0.01

### Metrics
- f1: 1.0
- fpr: 0.0
- precision: 1.0
- recall: 1.0

### Counts
- fn: 0
- fp: 0
- tn: 50
- tp: 10

## Next actions
- Add synthetic `tv_id` labels (TV-0..TV-3) for supervised evaluation (dependency-free).
- Introduce modeling dependencies only with explicit approval.

