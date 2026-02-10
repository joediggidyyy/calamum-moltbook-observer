# Remediation Plan: Calamum/Moltbook Observer Analysis Tooling Unification

## Metadata

- Template ID: `VAULT_TEMPLATE_REMEDIATION_PLAN_V1`
- Instigating Analysis: `projects/calamum-moltbook-observer/src/docs/audits/CALAMUM_MOLTBOOK_OBSERVER_CODE_QUALITY_AUDIT_2026-02-10.md`
- Status: APPROVED
- Owner: ORACL-Prime
- Created: 2026-02-10
- Target Component: `projects/calamum-moltbook-observer/src/analysis/`

## 1. Problem Statement

The Code Quality Audit (2026-02-10) identified high-severity code duplication in the `src/analysis/` module. Two competing implementations exist for the core ML workflow:

1.  **Dataset Construction**: `build_dataset.py` (Robust, uses `_util`) vs `dataset_builder.py` (Plan-compliant name, less code).
2.  **Evaluation Harness**: `evaluate_baseline.py` (Robust, uses `_util`) vs `evaluation_harness.py` (Plan-compliant name, less code).

- **Source Issue**: Divergent implementation of ML tooling (Split Brain).
- **Severity**: HIGH
- **Evidence**: Audit Report `CALAMUM_MOLTBOOK_OBSERVER_CODE_QUALITY_AUDIT_2026-02-10.md`

## 2. Remediation Strategy

**"Adopt the robust implementation, Enforce the planned nomenclature."**

We will retain the code logic from the `build_*` / `evaluate_*` variants (which utilize the shared `_util` library) but rename them to match the canonical Job 0011 architectural names (`dataset_builder.py`, `evaluation_harness.py`).

### 2.1 Artifact Selection / Change Matrix

| Target | Current State | Proposed State | Action |
| :--- | :--- | :--- | :--- |
| `src/analysis/dataset_builder.py` | Stub Implementation | Deleted | DELETE |
| `src/analysis/build_dataset.py` | Robust Implementation | `dataset_builder.py` | RENAME |
| `src/analysis/evaluation_harness.py` | Stub Implementation | Deleted | DELETE |
| `src/analysis/evaluate_baseline.py` | Robust Implementation | `evaluation_harness.py` | RENAME |

## 3. Execution Steps

1.  **Safety**: Verify git state is clean.
2.  **Action**: Remove `src/analysis/dataset_builder.py` (the stub/divergent version).
3.  **Action**: Remove `src/analysis/evaluation_harness.py` (the stub/divergent version).
4.  **Action**: Rename `src/analysis/build_dataset.py` -> `src/analysis/dataset_builder.py`.
5.  **Action**: Rename `src/analysis/evaluate_baseline.py` -> `src/analysis/evaluation_harness.py`.
6.  **Action**: Scan and Update imports in `src/tests/test_analysis_tools.py` and `src/analysis/__init__.py`.
7.  **Verification**: Run `python -m src.analysis.dataset_builder --help` and `pytest src/tests/test_analysis_tools.py`.

## 4. Job/Plan Alignment

- [ ] Job Update Required: N/A
- [ ] Plan Update Required: N/A
- [x] No Doc Updates (Maintenance Only) - Aligns code to existing Job 0011 spec.

## 5. Risk Assessment

- **Risk**: Breaking imports in `test_analysis_tools.py`.
- **Mitigation**: Step 6 explicitly includes scanning and fixing tests.
- **Estimator**:
    - complexity: 2
    - tests_needed: 1

---

**Approval Required**: joediggidyyy (Maintainer)
