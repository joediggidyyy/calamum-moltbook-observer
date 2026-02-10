# Model Training Narrative Report Structure - Calamum "Blind ML"

**Course anchors**: DATA780 (ML capstone) + DATA740 (ethics/governance)  
**Project**: Calamum Moltbook Observer ("Blind Sight")  
**Owner**: ORACL-Prime  
**Purpose**: A narrative + machine-friendly reporting structure to track and catalog training efforts so that academic project reports can be derived without reconstructing decisions after the fact.

This is intentionally *report-first*: each training run produces (1) a structured run record (JSON) and (2) a narrative write-up (Markdown) that cites dataset versions, feature contracts, and evaluation results.

---

## Design goals (non-negotiable)

1. **No semantic leakage**: reports must not include raw post/DM text. Only structural metadata and aggregate statistics.
2. **Reproducibility**: every run must specify dataset manifest hash + code version + random seeds.
3. **Governance traceability**: every threshold decision (especially for FPR < 1%) must be justified.
4. **Comparability**: reports should support side-by-side comparison across runs.

---

## Recommended artifact set per training run

For each run (a “training episode”), write two files:

1. `training_runs/<run_id>/run.json` - canonical machine-readable record.
2. `training_runs/<run_id>/run.md` - human narrative report.

Where:
- `run_id` is timestamped + short hash, e.g. `2026-02-10T2130Z_rf_v1_ab12cd`.

If you prefer to keep generated artifacts out of git, store them under `report_tmp/` and archive summaries per repo policy.

---

## `run.json` schema (suggested)

Minimum fields (expand as needed):

- **identity**
  - `run_id`
  - `created_at_utc`
  - `operator` (no secrets)
- **context**
  - `course_targets`: `["DATA780", "DATA740"]`
  - `objective`: e.g. `TV-3 vs not-TV-3` or `anomaly detection`
  - `constraints`: e.g. `{ "max_fpr": 0.01 }`
- **data**
  - `data_source`: `synthetic|canary|live`
  - `input_paths`: list of JSONL/CSV paths
  - `dataset_manifest`: path + hash
  - `schema_version`
  - `label_definition`: mapping of labels to meanings (or `null` for fully unsupervised)
  - `split`: seed + strategy + sizes + split indices hash
- **features**
  - `feature_list`: ordered list of feature names
  - `aggregation`: `none|windowed` plus window definition if applicable
  - `normalization`: scaler type + fit set
- **model**
  - `family`: `heuristic|logreg|rf|isoforest|lstm`
  - `hyperparameters`: object
  - `training_seed`
- **evaluation**
  - `primary_metric`: e.g. `f1_tv3`
  - `metrics`: object (accuracy, precision/recall/F1, AUROC if used)
  - `confusion_matrix`: optional
  - `fpr`: numeric
  - `thresholding`: how the cutoff was selected
  - `error_slices`: optional (by content_length buckets, time buckets, event_type)
- **governance** (DATA740 alignment)
  - `privacy_review`: pass/fail + notes
  - `risk_register`: key risks + mitigations
  - `poisoning_controls`: signature verification / ingestion validation policy
- **outputs**
  - `artifacts`: paths to model file(s), plots, and derived tables

---

## Narrative report (`run.md`) structure (template)

### 1) One-paragraph abstract
- What was trained/evaluated, on what data, and the key outcome.

### 2) Objective and hypotheses
- Objective definition (labels, target event types).
- Hypotheses (e.g., “metadata-only features can separate TV-3 with FPR < 1%”).

### 3) Data provenance and governance
- Dataset source: synthetic vs canary vs live.
- Schema invariants and validation steps.
- Ethics constraints: what was *not* collected (raw text), and why.

### 4) Dataset composition (tables)
Include only aggregate counts, such as:
- total records
- counts by `event_type` / `type`
- counts by label (if supervised)
- missingness rates per field

### 5) Feature contract
- Enumerate features used (e.g., `content_length`, `has_code_block`, `f_complexity`, …).
- Any windowing/aggregation (e.g., per `author_hash` per 10 minutes).
- Rationale for each feature (why it should help without leaking semantics).

### 6) Model and training protocol
- Model family, key hyperparameters, and seeds.
- Training procedure (class weighting, balancing, etc.).

### 7) Evaluation and constraint compliance
- Primary metric: F1 (TV-3) per proposal.
- Explicit FPR computation and whether it satisfies < 1%.
- Confusion matrix + per-class metrics.
- Threshold selection explanation (especially for anomaly scores).

### 8) Error analysis (privacy-safe)
- False positives/negatives by feature buckets (e.g., long content_length deciles).
- If possible: analyze *patterns* without quoting content.

### 9) Drift and robustness checks
- Compare feature distributions between synthetic and canary.
- Note any drift that invalidates thresholds.

### 10) Decisions and next actions
- What you will change next (data, features, model, thresholding).
- Risks introduced by the next step and mitigations.

---

## How this maps to course deliverables

- **DATA780**: Sections 2, 5–7 directly support the ML capstone narrative (method + evaluation).
- **DATA740**: Sections 3 and 10 provide explicit governance and ethical traceability.

---

## Recommended reporting cadence

- One `run.json` + `run.md` for every meaningful training attempt.
- A rolling `TRAINING_LEDGER.md` that links to runs and provides a short changelog.

If desired, generate a final NeurIPS-style write-up by selecting the best run and summarizing the ledger.
