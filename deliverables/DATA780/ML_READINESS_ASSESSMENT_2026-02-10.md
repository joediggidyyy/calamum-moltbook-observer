# ML Readiness Assessment (Supervised + Unsupervised) - Calamum Moltbook Observer ("Blind Sight")

**Course**: DATA780 — Machine Learning Capstone  
**Project**: Calamum Moltbook Observer ("Blind Sight")  
**Date**: 2026-02-10  
**Assessor**: ORACL-Prime  
**Scope**: Identify *planning* and *implemented artifact* gaps required to execute supervised and unsupervised learning tactics using the project’s privacy-preserving (“Blind ML”) telemetry.

---

## Executive summary

The project has a strong **privacy-preserving telemetry pipeline** suitable for ML experimentation (edge-side feature extraction, hashed identifiers, JSONL logging). However, it is **not yet training-ready** for either supervised or unsupervised methods because it lacks (1) a **ground-truth labeling artifact** for synthetic data, (2) a **dataset build + versioning pipeline**, (3) an **analysis/training workspace** (`src/analysis/` is referenced in deliverables but not present), and (4) **evaluation + threshold selection artifacts** to satisfy the stated DATA780 constraint of **FPR < 1%**.

The biggest immediate unlock is to formalize a **dataset contract** (schema + invariants + signature verification), then implement a **synthetic labeling strategy** aligned with the Threat Vector taxonomy (TV-0..TV-3) described in `DATA_METHODOLOGY.md`.

---

## Stated project parameters (deliverables)

### DATA780 proposal requirements (what we are building toward)
Source: `deliverables/DATA780/PROPOSAL_DRAFT.md`

- Goal: classify hostile/toxic activity *without raw text* (“Blind ML”).
- Data: synthetic datasets (target 100k records) with ground truth separating TV-0 vs TV-3.
- Methods:
  - baseline heuristics
  - supervised Random Forest
  - unsupervised Isolation Forest
  - (stretch) LSTM
- Evaluation:
  - primary metric: F1 on TV-3 detection
  - constraint: false positive rate (FPR) < 1%

### DATA740 governance constraints (must constrain ML work)
Source: `deliverables/DATA740/ALIGNMENT_ASSESSMENT.md` and `DATA_METHODOLOGY.md`

- “Obfuscation at the edge” and “Dreaming Mode” (synthetic-first) are core ethical commitments.
- “Zero semantic leakage” is a hard constraint for scientific telemetry.
- Safety and governance artifacts (watchdog/sentinel architecture) imply the ML pipeline must be robust against poisoning and must not reintroduce sensitive content.

---

## What exists today (ML-relevant artifacts)

### Telemetry schema primitives (implemented)
Source: `src/obfuscator_lib.py`

- `Obfuscator.obfuscate_sample(sample)` outputs structural metadata only:
  - `timestamp`, `type`, `content_length`, `has_code_block`, `author_hash`, `tags_count`, `mentions_count`
- `Obfuscator.obfuscate_notification(notification)` outputs:
  - `timestamp`, `event_type`, `sender_hash`, plus `content_length` and `has_link` *only if content is present*
- Signing primitives exist (`sign_record`, `verify_record`) but are not currently used in the sampling pipeline.

### Feature extraction (implemented, scalar-only)
Source: `src/stage4_features.py`

- `extract_stage4_features(content, timestamp_str, last_timestamp=None)` returns only scalar fields:
  - `f_complexity`, `f_code_density`, `f_toxicity`, `f_timestamp_epoch`
- Importantly: “NO RAW CONTENT IS RETURNED.”

### Synthetic generation (implemented, but not labeled)
Source: `src/calamum_sampler.py`

- Synthetic feed generator: `simulate_moltbook_feed()`
- Synthetic notifications generator: `simulate_moltbook_notifications()`
- Current synthetic generators do **not** emit Threat Vector labels (TV-0..TV-3) despite the taxonomy defined in `DATA_METHODOLOGY.md`.

### Deliverables expectation mismatch
Source: `deliverables/DATA780/README.md`

- README states: “Analysis Code will reside in `../../src/analysis/`.”
- No `projects/calamum-moltbook-observer/src/analysis/` directory was found during inspection.

---

## Readiness for supervised learning (Random Forest / Logistic Regression baseline)

### What supervised ML requires (minimum viable)

1. **A label $y$** per record (or per window) for training/evaluation.
2. A stable **feature vector** $x$ (already mostly present via `obfuscator_lib` + `stage4_features`).
3. A deterministic **train/val/test split** (and the ability to reproduce it).
4. A reporting layer that explicitly measures:
   - confusion matrix
   - per-class precision/recall/F1
   - FPR and the FPR < 1% constraint

### Current gaps for supervised ML

#### Gap S1 — No ground truth labels in generated training data
- The proposal and methodology reference threat vectors (TV-0..TV-3), but the synthetic generators do not emit a TV label.
- Without labels, supervised training is blocked.

**Recommended artifact:** a deterministic label field (e.g., `tv_id` or `tv_class`) emitted only for synthetic/dreaming datasets.

#### Gap S2 — Dataset build pipeline absent
- There is no script to:
  - collect JSONL records
  - validate schema invariants (and reject malformed lines)
  - convert JSONL → feature matrix (CSV/NPY/parquet) suitable for modeling
  - version the dataset (hash + manifest)

**Recommended artifact:** `dataset_build.py` (or equivalent) producing:
- `dataset_manifest.json` with counts, schema version, and hashes
- `features.csv` (or `X.npy` + `y.csv`)

#### Gap S3 — Record authenticity / poisoning defense not wired into dataset ingestion
- `obfuscator_lib` supports HMAC signatures, but the sampler does not sign records.
- For a security-focused experiment, a training pipeline should either:
  - verify signatures on ingestion (preferred), or
  - explicitly document why signatures are omitted (and what alternative anti-poisoning controls exist)

**Recommended artifact:** “dataset ingestion policy” + signature verification step (at least for any live-mode data).

#### Gap S4 — Evaluation artifacts not present
- No evaluation harness exists to enforce/report the FPR < 1% constraint.

**Recommended artifact:** a model evaluation report per run, including threshold selection to hit FPR constraints.

---

## Readiness for unsupervised learning (Isolation Forest / anomaly detection)

### What unsupervised ML requires (minimum viable)

Even without labels, anomaly detection needs:

1. A stable feature set and scaling/normalization decisions.
2. A definition of “anomaly” suitable for evaluation. Common options:
   - synthetic ground truth labels (best for an academic capstone)
   - precision@k on a held-out labeled subset
   - distribution drift metrics + operator review sampling
3. A thresholding policy to control false positives (again: < 1%).

### Current gaps for unsupervised ML

#### Gap U1 — No evaluation plan for anomaly scoring
- Isolation Forest can output anomaly scores, but the system currently has no artifact that:
  - chooses a threshold
  - reports the implied FPR under expected TV-0/TV-1 distributions

**Recommended artifact:** “threshold selection report” (e.g., choose score cutoff at 99th percentile on benign baseline).

#### Gap U2 — Dataset windowing / time-series features are not implemented
- The proposal mentions “time-series features from JSONL logs,” but there is no implemented window aggregation (sliding windows per `author_hash` / `sender_hash`, per time bucket, etc.).

**Recommended artifact:** a feature aggregation step producing window-level rows (e.g., counts per actor per 5 minutes).

---

## Schema and documentation alignment risks

### Risk A — Documentation schema vs. code schema drift
`DATA_METHODOLOGY.md` lists `has_link` in a generic schema example.

- In code today:
  - `has_link` is emitted for notifications only.
  - `obfuscate_sample()` does not emit `has_link`.

This is not fatal, but it creates uncertainty for the “Blind ML” feature contract.

**Recommended artifact:** a single canonical schema spec for ML (and a validator).

### Risk B — Mock client is placeholder
Source: `src/moltbook_client.py`

- `MockMoltbookClient` currently yields a single minimal “simulation” object and does not implement the TV taxonomy.

**Recommended artifact:** either expand `MockMoltbookClient` to generate labeled TVs, or explicitly standardize on the `simulate_moltbook_*` generators and treat the mock client as a stub.

---

## Minimal set of missing artifacts (the “Training-Ready Checklist”)

### Must-have (blocks training)

1. **Dataset contract + schema version** (document + machine validator).
2. **Synthetic label emission** aligned with `TV-0..TV-3`.
3. **Dataset build pipeline** (JSONL → features + labels) + dataset manifest.
4. **Train/test split artifact** (deterministic) + split manifest.
5. **Evaluation harness** with explicit FPR accounting and threshold selection.

### Should-have (enables quality + governance)

6. **Experiment registry** (run IDs, model params, dataset version) + narrative reports.
7. **Signature verification / poisoning controls** for any non-synthetic datasets.
8. **Drift checks** when moving from synthetic → canary distribution.

### Nice-to-have (stretch)

9. **Deep model (LSTM)** only after the above are stable; otherwise it adds complexity without governance maturity.

---

## Suggested file layout to satisfy deliverables cleanly

To align with `deliverables/DATA780/README.md`:

- `projects/calamum-moltbook-observer/src/analysis/`
  - `README.md` (how to run training end-to-end)
  - `build_dataset.py`
  - `train_supervised.py`
  - `train_unsupervised.py`
  - `evaluate.py`
  - `reports/` (generated, gitignored or archived per policy)

If training scripts are introduced, confirm dependency policy (new deps require maintainer approval).

---

## Notes on leveraging existing repo assets

The workspace contains a reusable script library under `projects/data-science-script-library/scripts/ml/` that already includes:

- deterministic split tooling (`train_test_split_cli.py`)
- evaluation report generation (`model_eval_report.py`)

These can accelerate implementation without inventing new reporting formats.

---

## Appendix: Mapping gaps to proposal timeline

Proposal timeline vs current state:

- Week 1–2 (synthetic 100k labeled): **blocked** (no labels / dataset build pipeline).
- Week 3–4 (feature engineering time-series): **partially ready** (base scalar features exist; window aggregation missing).
- Week 5–6 (train models): **blocked** until datasets/splits/eval harness exist.
- Week 7 (evaluate canary drift): **not ready** (no drift/eval artifacts yet).
