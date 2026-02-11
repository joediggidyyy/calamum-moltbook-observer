# Calamum Blind ML Visualization Strategy

> **Identity Directive:** This document governs the visualization implementation for the Calamum Blind ML pipeline.
> **Classification:** Internal Use Only
> **Project:** Calamum Moltbook Observer
> **Date:** 2026-02-10
> **Status:** DRAFT

## 1. Executive Summary
This plan outlines the implementation of visualization tools for the Blind ML scoring system. By visualizing score distributions and threshold cutoffs using `matplotlib` and `seaborn`, we will enable human validation of the machine learning model's behavior without exposing raw text content.

## 2. Objectives
1.  **Dependency Management**: Integrate `matplotlib` and `seaborn` into the project environment.
2.  **Distribution Analysis**: Create scripts to plot histograms and KDEs of anomaly scores.
3.  **Threshold Validation**: Visualize the separation between benign and anomalous data points relative to the calculated threshold.
4.  **Reporting**: Generate static image assets (`.png`) for inclusion in audit reports.

## 3. Technical Strategy

### 3.1 Dependencies
The following libraries are authorized and will be added to `requirements.txt`:
*   `matplotlib`
*   `seaborn`

### 3.2 Script Architecture
New module `src/vis/` will contain:
*   `plot_distributions.py`: Input `scores.csv`, Output `distribution_plot.png`.
    *   Features: Histogram of scores, KDE overlay, logarithmic scale option, statistical summary annotation.
*   `visualize_threshold.py`: Input `scores.csv` + threshold value, Output `threshold_impact.png`.
    *   Features: Color-coded regions (Safe vs Flagged), vertical line at threshold, annotation of False Positive Rate.

### 3.3 Data Flow
1.  `src/analysis/score_unsupervised.py` -> `local_untracked/runs/{run_id}/scores.csv`
2.  `src/analysis/threshold_selection.py` -> Threshold Value
3.  **Visualization Scripts** -> Read CSV -> Generate Plots -> Save to `local_untracked/runs/{run_id}/plots/`

## 4. Implementation Steps
1.  **Environment Update**: Add dependencies and rebuild environment.
2.  **Module Creation**: Initialize `src/vis/` package.
3.  **Distribution Script**: Implement `plot_distributions.py`.
4.  **Threshold Script**: Implement `visualize_threshold.py`.
5.  **Integration**: Update pipeline documentation to include visualization steps.

## 5. Verification Plan
*   **Unit Tests**: Verify plotting functions run without error (mocking display backend).
*   **Artifact Inspection**: Manually inspect generated PNGs for clarity and correctness.
*   **FPR Validation**: Visual check that the threshold line aligns with the reported statistics.

## 6. Risk Assessment
*   **Risk**: Dependency bloat.
    *   *Mitigation*: These are standard data science libraries; overhead is acceptable for this analysis-heavy project.
*   **Risk**: Data leakage in labels.
    *   *Mitigation*: Axis labels must only refer to "Scores" and "Counts", never raw text content or PII.
