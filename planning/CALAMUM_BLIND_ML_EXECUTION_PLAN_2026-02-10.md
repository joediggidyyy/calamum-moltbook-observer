# Plan: Calamum “Blind ML” Execution Plan (Supervised + Unsupervised)

**Project**: Calamum Moltbook Observer ("Blind Sight")  
**Date**: 2026-02-10  
**Author**: ORACL-Prime  
**Owner**: joediggidyyy  
**Purpose**: Convert the gaps identified in the ML readiness assessment into an implementable, auditable sequence of artifacts.

## Canonical observer path and hypothesis anchor

- **Canary**: passive baseline collection and unsupervised pattern discovery
- **Live**: active-target collection and delta analysis relative to canary
- **Honeypot**: attractive-target collection and delta analysis relative to live and canary

Threat-only hypothesis:

- threat-relevant patterns can be identified from obfuscated structural / temporal / behavioral signals without direct ingestion of the threat-vector payload.

Scope exclusion:

- human-mimicry / larper detection is out of scope for this execution plan.

## Canonical references

- Readiness assessment (gaps inventory):
  - `deliverables/DATA780/ML_READINESS_ASSESSMENT_2026-02-10.md`
- Training narrative / experiment reporting structure:
  - `deliverables/DATA780/MODEL_TRAINING_NARRATIVE_REPORT_STRUCTURE.md`
- DATA780 proposal parameters (metrics + constraint):
  - `deliverables/DATA780/PROPOSAL_DRAFT.md`
- DATA740 governance anchors:
  - `deliverables/DATA740/ALIGNMENT_ASSESSMENT.md`
  - `DATA_METHODOLOGY.md`

---

## Non-negotiables (constraints)

1. **No semantic leakage**: training data and reports must not contain raw text or message bodies.
2. **Reproducibility**: dataset version + code version + RNG seeds must be captured for every run.
3. **FPR constraint**: for TV-3 detection, enforce **FPR < 1%** as a first-class requirement.
4. **Poisoning / integrity posture**:
   - For any data beyond synthetic/dreaming, ingestion must validate schema and (ideally) verify signatures.
5. **Dependency policy**: introducing new dependencies requires maintainer approval. If scikit-learn/pytorch are used for DATA780 modeling, explicitly request approval and record the decision.

---

## Phase 0 - Decide the "analysis home" and artifact boundaries

### Deliverable
- Create and document an analysis workspace consistent with DATA780 README expectations:
  - `projects/calamum-moltbook-observer/src/analysis/` (new)

### Acceptance criteria
- A `src/analysis/README.md` exists describing:
  - dataset build command(s)
  - training command(s)
  - evaluation command(s)
  - where outputs/reports go

### Notes
- This phase is structural, but it prevents tool sprawl and ambiguity.

---

## Phase 1 - Dataset contract (schema + invariants + validator)

### Problem addressed
- Current docs and code have minor drift (e.g., `has_link` appears in doc schema example but is not present in all record types).

### Deliverables
1. **Schema spec** (human + machine readable):
   - `src/analysis/schema/obfuscated_record_schema_v1.json` (or similar)
   - `src/analysis/schema/README.md` describing event types and required/optional fields
2. **Validator**:
   - `src/analysis/validate_jsonl.py` that:
     - reads JSONL
     - enforces required fields and types
     - rejects lines with unexpected raw content fields
     - optionally verifies HMAC signatures (if present)

### Acceptance criteria
- Validator exits non-zero on malformed JSONL.
- Validator can output summary counts (records, missing fields, event_type/type distribution).

### Governance tie-in (DATA740)
- This artifact is the enforceable "no semantic leakage" gate.

---

## Phase 2 - Synthetic labeling strategy (TV taxonomy wired into data)

### Problem addressed
- No ground-truth labels exist in generated synthetic data despite TV-0..TV-3 taxonomy in `DATA_METHODOLOGY.md`.

### Adopted TV contract
- `TV-0`: benign baseline-consistent activity
- `TV-1`: irregular but low-concern deviation from baseline
- `TV-2`: suspicious activity with likely-hostile structural patterns
- `TV-3`: high-risk activity that justifies the strongest level of concern

For the midway study, the primary supervised boundary remains `TV-0` versus `TV-3`, while `TV-1` and `TV-2` remain intermediate categories for nuisance structure, ambiguity, and later evaluation design.

### Deliverables
1. **Label definition doc**:
   - `src/analysis/labels.md` defining:
    - `tv_id` in {TV-0, TV-1, TV-2, TV-3}
    - the adopted meaning of each TV class
    - primary supervised target mapping (e.g., `y = 1` iff TV-3)
    - any optional secondary mapping (e.g., `y = 1` iff TV >= 2`) must be documented as a separate experiment rather than silently replacing the primary target
2. **Synthetic generator emits labels** (one of the following approaches):
   - Option A (preferred): extend the synthetic generation functions in `src/calamum_sampler.py` to emit `tv_id` in-memory (never emitted in live mode).
   - Option B: implement a post-generation labeling step for synthetic-only datasets that is deterministic and documented.

### Acceptance criteria
- Synthetic datasets include a `tv_id` field.
- Live/canary datasets do not invent labels; they remain unlabeled unless a separate safe labeling mechanism is defined.
- Labeling docs explain why the main midway comparison is `TV-0` versus `TV-3` even though the full four-level ladder is retained.

---

## Phase 3 - Dataset build + versioning pipeline (JSONL -> features + manifests)

### Problem addressed
- No dataset build script exists; no dataset manifest/versioning; no deterministic splits.

### Deliverables
1. **Dataset builder**:
   - `src/analysis/build_dataset.py`:
     - input: JSONL path(s)
     - output: `dataset/` directory containing:
       - `dataset_manifest.json` (hashes, counts, schema version, time range)
       - `features.csv` (or `X.npy`) with a stable, documented column order
       - `labels.csv` (if supervised) or `labels.json` (mapping)
2. **Split artifact**:
   - deterministic train/val/test split that produces:
     - `split_manifest.json`
     - optional split indices file for auditability

### Implementation accelerators available in repo
- `projects/data-science-script-library/scripts/ml/train_test_split_cli.py` already implements deterministic splitting for CSV.

### Acceptance criteria
- Running the dataset builder twice with the same inputs yields identical manifests and splits.

---

## Phase 4 - Feature engineering: baseline + windowed aggregation

### Problem addressed
- Proposal mentions time-series features, but only per-record scalar features exist today.

### Deliverables
1. **Feature contract document**:
   - `src/analysis/features.md` enumerating all features, their types, and privacy rationale.
2. **Optional windowed aggregation**:
   - `src/analysis/aggregate_windows.py` that can transform record-level JSONL into window-level rows:
     - grouping keys: `author_hash` / `sender_hash` / `node_id`
     - window size: e.g., 5 minutes or N events
     - outputs: counts, rates, mean/variance of scalar features

### Acceptance criteria
- Aggregation produces stable outputs and never includes raw content.

---

## Phase 5 - Modeling (Supervised)

### Objectives
- Baselines first:
  - heuristic rules (no new deps)
  - logistic regression / random forest (may require scikit-learn approval)

### Deliverables
1. `src/analysis/train_supervised.py`
2. `src/analysis/predict_supervised.py`
3. A saved model artifact format decision:
   - if sklearn: `joblib` or `pickle` (document security implications)

### Evaluation
- Must output:
  - confusion matrix
  - per-class precision/recall/F1
  - explicit FPR and whether < 1%

### Existing accelerator
- `projects/data-science-script-library/scripts/ml/model_eval_report.py` can generate JSON + Markdown from `y_true.csv` and `y_pred.csv`.

---

## Phase 6 - Modeling (Unsupervised)

### Objectives
- Isolation Forest / anomaly scoring, but with an explicit threshold policy.

### Deliverables
1. `src/analysis/train_unsupervised.py` (fit on benign baseline)
2. `src/analysis/score_unsupervised.py`
3. `src/analysis/threshold_selection.py`

### Acceptance criteria
- Threshold selection produces a report explaining how the cutoff enforces the < 1% FPR constraint on a benign baseline.

---

## Phase 7 - Drift checks: synthetic -> canary -> live -> honeypot

### Problem addressed
- Proposal plans evaluation on "Canary Mode" distributions; drift can break thresholds.

### Deliverables
1. `src/analysis/drift_report.py` that compares feature distributions between:
   - synthetic dataset
  - canary dataset
  - live dataset
  - honeypot dataset

### Acceptance criteria
- Drift report summarizes which features shifted across the three-stage observer path and whether threshold recalibration is required.

---

## Phase 8 - Experiment reporting and ledger

### Objective
- Make it impossible to "lose" modeling decisions.

### Deliverables
- Adopt the reporting structure in:
  - `deliverables/DATA780/MODEL_TRAINING_NARRATIVE_REPORT_STRUCTURE.md`
- Add a rolling ledger:
  - `deliverables/DATA780/TRAINING_LEDGER.md` linking to each run’s `run.json` and `run.md`

### Acceptance criteria
- Every run records:
  - dataset manifest hash
  - code version (git SHA)
  - seeds
  - metrics + constraint compliance
  - governance notes

---

## Optional: Service logs "not receiving data" (ops-quality improvement)

### Observation
The files like:
- `logs/calamum_agent.stdout.log`
- `logs/calamum_librarian.stdout.log`
- `logs/calamum_watchdog.stdout.log`

exist because `launch_ghost_console.ps1` starts each service with stdout/stderr redirected into these files.

They appear "not wired" because:
- the **agent** does almost all of its work by writing JSONL telemetry and heartbeat files, and only prints on control-signal events
- the **watchdog** prints primarily on startup and only emits stderr output on alerts
- the **librarian** prints on startup and only prints again when it finds archive candidates

If desired, add a periodic one-line status print (rate-limited) to each service to keep stdout logs visibly alive without spamming.

---

## Definition of done

The plan is complete when we can:

1. Generate a labeled synthetic dataset (TV-0..TV-3) with a manifest.
2. Build deterministic splits.
3. Train a baseline supervised model and produce an evaluation report that explicitly verifies FPR < 1%.
4. Train an unsupervised model and produce a threshold selection report.
5. Produce a drift report for synthetic vs canary.
6. Produce at least one full training narrative run record (`run.json` + `run.md`) and link it from `TRAINING_LEDGER.md`.
