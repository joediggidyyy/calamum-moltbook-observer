# Filesystem Schema Audit: Calamum Observer

**Date**: 2026-02-10  
**Reviewer**: ORACL-Prime  
**Status**: APPROVED WITH FINDINGS

---

## 1. Assessment

The current filesystem configuration (`projects/calamum-moltbook-observer/`) has been audited for semantic correctness, separation of concerns, and SEAM compliance.

**Verdict**: The configuration is **Mostly Compliant**, but exhibits "Mixed Concerns" in specific operational directories.

### 1.1 Separation of Concerns (Data & Logic)
| Component | Location | Status | Rationale |
| :--- | :--- | :--- | :--- |
| **Code & Logic** | `src/analysis/` | **Tracked** | Source of truth for processing logic. |
| **Data Schemas** | `src/analysis/schema/` | **Tracked** | Defines the contract for valid data (`obfuscated_record_v1`). |
| **Raw Inputs** | `local_untracked/analysis/data_archive/` | **Untracked** | High-volume, immutable logs (GZIP). Privacy boundary. |
| **Derived Features** | `local_untracked/analysis/datasets/` | **Untracked** | Regenerable artifacts (`features.csv`, `splits.csv`). Avoids git bloat. |
| **Model Artifacts** | `local_untracked/analysis/models/` | **Untracked** | Binary outputs (`.joblib`) and training metadata. |

## 2. Findings & Violations

### 2.1 Jobs Directory (`jobs/`)
**Policy**: Must contain only *Product Feature Increments*. Audit logs and remediation records are out of scope.
*   **[RESOLVED] Duplicate ID**: Job `0007` was claimed by `CALAMUM_JOB_0007_MOLTBOOK_OBSERVER_REMEDIATION_EXECUTION.md` (Invalid). **Action**: Moved to `src/docs/audits/`.
*   **[RESOLVED] Mixed Concerns**:
    *   `CALAMUM_JOB_0007_...`: Moved to `src/docs/audits/`.
    *   `CALAMUM_JOB_0008_...`: Moved to `src/docs/audits/`. JSON metadata archived.

### 2.2 Planning Directory (`planning/`)
**Policy**: Must contain *Forward-Looking Plans* and *Approvals*. Execution reports belong in `docs/`.
*   **[RESOLVED] Misplaced Report**: `STAGE_5_READINESS_REPORT_20260210.md` moved to `docs/reports/`.

### 2.3 Quest Artifact Provenance
The tracking of QuestStacks (`queststacks/*.json`, `queststacks/*.md`) and QuestFrames (`questframes/*.md`) is **VALID** and **MANDATORY**.
*   **Rationale**: These artifacts form the "Legislative Record". While runtime data is untracked, the *decisions* must be preserved in git.

## 3. Recommendation

**Execute the following remediation plan:**

1.  **Migrate Remediation Logs**: Move `jobs/*REMEDIATION*` files to `src/docs/audits/`.
2.  **Migrate Readiness Reports**: Move `planning/*READINESS_REPORT*` to `docs/reports/`.
3.  **Enforce Job ID Uniqueness**: strictly strictly sequential IDs for Feature increments only.
4.  **Maintain Data Hygiene**: Continue strict `local_untracked` usage for all data/models.

No further structural changes are required for the `src` or `data` separation. The project logic/data split is aligned with CodeSentinel governance.
