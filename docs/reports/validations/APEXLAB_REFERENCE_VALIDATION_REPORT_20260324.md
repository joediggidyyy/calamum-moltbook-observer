# ApexLab Reference Validation Report — 2026-03-24

<p align="center">
	<img src="../../../assets/branding/apexlab_logo.png" alt="ApexLab logo" width="160">
</p>

*ApexLab presents lightweight numerical tooling with transparent validation, practical reproducibility, and a reviewer-friendly analytical surface.*

**Status:** Pass  
**Consumer repo:** Calamum Moltbook Observer  
**Canonical source repo:** ApexLab  
**Validation landing page:** [INDEX.md](./INDEX.md)  
**Canonical validation runner:** `projects/apexlab/examples/reference_validation_run.py`  
**Canonical machine-readable artifact:** `projects/apexlab/logs/metrics/reference_validation_20260324.json`  
**Browser-friendly report:** [APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html](./APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html)

## Abstract

This report documents the public-facing interpretation of the 2026-03-24 ApexLab reference-validation run. The objective was to test whether the lightweight analytical surfaces now depended on by the Observer data-science lane remain numerically aligned with established reference implementations while preserving ApexLab's low-dependency design.

The validation run compared three capability groups against external baselines:

1. nonparametric and parametric statistical tests,
2. ordinary least squares (OLS) regression, and
3. binary logistic regression.

All three sections passed their declared acceptance criteria. Statistic-level deltas for the statistical-comparison helpers and OLS lane were effectively at machine precision. The logistic lane also passed, achieving perfect classification agreement on the fixture and strong probability-shape agreement with the reference model, while explicitly reporting that the capped gradient-descent run did not declare convergence by the configured stopping rule. That non-convergence flag is operationally important and should be preserved as a diagnostic signal rather than hidden behind a pass/fail simplification.

## Why this report exists

The browser-friendly HTML version in this folder is useful for quick public review, but it is not sufficient for a graduate-level data-science workflow review. This report fills that gap by recording:

- the validation question,
- the experimental design,
- the quantitative acceptance thresholds,
- the observed results,
- the interpretation boundaries, and
- the current Observer integration context.

The presentation of this document is intentionally restrained: it keeps the validation story technical and transparent while using a small amount of branded visual structure so the report reads like a maintained publication rather than an internal scratch note.

## Related public surfaces

- [Validation landing page](./INDEX.md)
- [Browser-friendly report](./APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html)
- [Observer security validation dossier](./CALAMUM_OBSERVER_SECURITY_VALIDATION_REPORT_20260421.md)

## Validation question

The operative question for this run was:

> Are the current lightweight ApexLab comparison and regression helpers numerically close enough to trusted SciPy and scikit-learn references to support the Observer integration lane without adding heavyweight runtime dependencies?

A passing answer requires the tested sections to remain inside explicit numeric tolerance bands rather than merely "looking reasonable."

## Materials and methods

### Validation runner and references

The canonical runner is `projects/apexlab/examples/reference_validation_run.py`.

Reference libraries used by that runner:

- `scipy.stats` for Mann-Whitney U, two-sample KS, and Welch's $t$-test baselines,
- `sklearn.linear_model.LinearRegression` for OLS comparison,
- `sklearn.linear_model.LogisticRegression` for logistic-regression comparison.

### Sections tested

| Section | ApexLab surface | Reference surface | Acceptance style |
|---|---|---|---|
| Statistical comparison | `mann_whitney_u`, `ks_two_sample`, `welch_t_test`, `cohens_d` | SciPy plus analytical Cohen's $d$ reference | Absolute deltas must remain within declared thresholds |
| OLS regression | `ols_fit` | scikit-learn `LinearRegression` | Coefficient and prediction deltas must remain near zero |
| Logistic regression | `logistic_fit` | scikit-learn `LogisticRegression` | Classification quality, probability agreement, and coefficient-sign agreement must pass bounded checks |

### Acceptance thresholds

The canonical JSON artifact declares the following thresholds:

| Check | Threshold |
|---|---:|
| Mann-Whitney statistic delta | $1 \times 10^{-9}$ |
| Mann-Whitney $p$-value delta | $5 \times 10^{-2}$ |
| KS statistic delta | $1 \times 10^{-9}$ |
| KS $p$-value delta | $5 \times 10^{-2}$ |
| Welch $t$ delta | $1 \times 10^{-9}$ |
| Welch $p$-value delta | $5 \times 10^{-2}$ |
| Cohen's $d$ delta | $1 \times 10^{-9}$ |
| OLS coefficient max abs delta | $1 \times 10^{-9}$ |
| OLS prediction max abs delta | $1 \times 10^{-9}$ |
| Logistic accuracy delta | $\leq 0.05$ |
| Logistic prediction agreement | $\geq 0.90$ |
| Logistic probability MAE | $\leq 0.12$ |
| Logistic probability correlation | $\geq 0.98$ |
| Logistic coefficient sign match | `true` |

### Important methodological note

The validation runner explicitly allows looser tolerance on some $p$-value comparisons because ApexLab intentionally uses SciPy-free approximation methods in its own analytical implementation. That is not a loophole; it is the correct way to evaluate a low-dependency design whose inferential statistics are intentionally approximate while still requiring the test statistics themselves to agree tightly.

## Results

### 1) Statistical-comparison layer

The statistical-comparison section passed cleanly.

| Test | ApexLab result | Reference result | Absolute delta | Threshold | Pass |
|---|---|---|---:|---:|---|
| Mann-Whitney U statistic | `0.0` | `0.0` | `0.0` | `1e-9` | Yes |
| Mann-Whitney $p$-value | `0.00018267179110953435` | `0.00018267179110955002` | `1.5667e-17` | `0.05` | Yes |
| KS statistic $D$ | `1.0` | `1.0` | `0.0` | `1e-9` | Yes |
| KS $p$-value | `1.8879793657162556e-05` | `0.0` | `1.88798e-05` | `0.05` | Yes |
| Welch $t$ statistic | `6.847018410831535` | `6.847018410831535` | `0.0` | `1e-9` | Yes |
| Welch $p$-value | `7.540634783254063e-12` | `3.209558497791793e-06` | `3.20955e-06` | `0.05` | Yes |
| Cohen's $d$ | `3.062079721962379` | `3.0620797219623794` | `4.44089e-16` | `1e-9` | Yes |

### Interpretation

This is the cleanest section in the run. The test statistics themselves matched exactly or to machine precision on the chosen fixtures, while the approximation-based $p$-value differences remained far inside the declared tolerance bands. For the Observer lane, this means the lightweight comparison helpers are not just directionally correct; on the validation fixtures they are numerically faithful enough to support defensible lane-to-lane comparison work.

### 2) OLS regression layer

The OLS section also passed with effectively negligible error.

| Metric | Observed value | Threshold | Pass |
|---|---:|---:|---|
| Maximum absolute coefficient delta | `6.661338147750939e-15` | `1e-9` | Yes |
| Maximum absolute prediction delta | `7.105427357601002e-15` | `1e-9` | Yes |
| ApexLab $R^2$ | `1.0` | Informational | — |
| ApexLab RMSE | `6.898884543774767e-15` | Informational | — |

ApexLab OLS coefficients:

- intercept: `2.4999999999999916`
- feature 1: `1.7500000000000007`
- feature 2: `-0.40000000000000013`

Reference OLS coefficients:

- intercept: `2.4999999999999982`
- feature 1: `1.75`
- feature 2: `-0.399999999999999`

### Interpretation

This section behaved exactly the way a publishable validation lane should behave: the fitted coefficients and predictions are so close to the reference implementation that the residual differences are dominated by floating-point precision rather than algorithmic drift. In practical terms, the Observer lane can treat the current ApexLab OLS implementation as validated for the tested fixture class.

### 3) Logistic-regression layer

The logistic section passed, but its pass deserves a more careful reading than the earlier two sections.

| Metric | Observed value | Threshold | Pass |
|---|---:|---:|---|
| Accuracy delta | `0.0` | `0.05` | Yes |
| Prediction agreement | `1.0` | `0.90` | Yes |
| Probability MAE | `0.03230342561928962` | `0.12` | Yes |
| Probability correlation | `0.9912416474961214` | `0.98` | Yes |
| Coefficient sign match | `true` | `true` | Yes |
| ApexLab convergence flag | `false` | Informational | — |
| Iterations used | `12000` | Informational | — |
| ApexLab accuracy | `1.0` | Informational | — |
| ApexLab pseudo-$R^2$ | `0.9493130814508287` | Informational | — |
| ApexLab log loss | `0.0351334946836297` | Informational | — |

ApexLab logistic coefficients:

- intercept: `-15.512864538686669`
- feature 1: `6.326241197206793`
- feature 2: `1.071511617730478`

### Interpretation

The logistic lane passed on the metrics that matter for this validation frame:

- predictions matched the reference model perfectly on the test fixture,
- probability outputs tracked the reference probabilities closely enough to satisfy the declared MAE and correlation thresholds, and
- coefficient directions matched exactly.

However, the optimization history did **not** declare convergence within the configured `12000`-iteration cap. That matters. The correct interpretation is not "everything is perfect"; it is that the current implementation is already producing high-quality classification behavior on the chosen fixture, while the convergence diagnostic remains a real engineering signal for future optimization and conditioning work.

That is precisely the kind of nuance a mature data-science report should preserve.

## Figure panel — Observer integration context

The three figures already retained beside this report are relevant to the Observer integration context because they show the current canary anomaly-score landscape that depends on the same broader ApexLab-backed analytical lane. They are not direct outputs of `reference_validation_run.py`; they are companion Observer-side figures that help situate why validation quality matters.

### Figure 1. Canary anomaly-score distribution (log-count scale)

![Figure 1 — Canary anomaly-score distribution on log-count scale](../../../assets/plots/canary_v1_dist.png)

**Reading:** the canary score distribution is broad and multi-modal, with a long left tail reaching into the anomaly region. The log-scale count view is especially useful for seeing low-frequency score regions that would otherwise be visually flattened.

### Figure 2. Threshold impact analysis at the current false-positive operating point

![Figure 2 — Threshold impact analysis](../../../assets/plots/canary_v1_thresh.png)

**Reading:** the current threshold is approximately `-0.0450`, flagging `1364` of `133837` samples for an observed FPR near `1.0192%`. This matters because the Observer lane uses thresholded score interpretation operationally; numerical trust in the underlying analytical helpers therefore carries direct downstream consequences.

### Figure 3. Canary anomaly-score distribution (linear-count view)

![Figure 3 — Canary anomaly-score distribution on linear count scale](../../../assets/plots/canary_v1_test_nolog.png)

**Reading:** the linear-count view highlights the dense central mass and the higher-score concentration that the log view visually compresses. Together, Figures 1 and 3 provide complementary intuition for how the current threshold slices the empirical score landscape.

## Discussion

### What passed

The report supports four strong claims:

1. ApexLab's statistical-comparison helpers are numerically aligned with trusted references on the current fixtures.
2. ApexLab's OLS surface reproduces reference coefficients and predictions to near machine precision on the validation design matrix.
3. ApexLab's logistic surface is operationally credible on the validation fixture, with excellent agreement on classification outputs and strong probability alignment.
4. The Observer lane can cite this validation as evidence that its low-dependency analytical foundation has been externally checked rather than accepted on faith.

### What did not magically disappear

Two limitations remain important:

- The validation fixtures are deliberately small and deterministic. They are appropriate for reference alignment, but they are not a substitute for every downstream real-data behavior check.
- The logistic optimizer's non-convergence flag should remain visible in future reports, because suppressing that diagnostic would weaken rather than strengthen the credibility of the lane.

### Why the pass still matters

A good validation report is not trying to prove universal perfection. It is trying to show that the implementation behaves credibly, transparently, and within predeclared tolerance bands on known fixtures. By that standard, this run is strong.

## Conclusion

The 2026-03-24 ApexLab reference-validation run passed all declared sections and provides defensible evidence that the current lightweight comparison and regression surfaces are suitable for the present Observer integration lane. The strongest results came from the statistical-comparison and OLS sections, which matched their references to effectively exact precision. The logistic section also passed and is fit for present use, but its non-convergence diagnostic should remain part of the recorded story.

For the Observer project, the correct conclusion is therefore:

> the current ApexLab-backed analytical lane is validated strongly enough to support the active integration work, while still preserving honest visibility into the optimizer behavior that future frames may tighten.

## Evidence pointers

- `projects/apexlab/examples/reference_validation_run.py`
- `projects/apexlab/logs/metrics/reference_validation_20260324.json`
- `projects/calamum-moltbook-observer/assets/plots/canary_v1_dist.png`
- `projects/calamum-moltbook-observer/assets/plots/canary_v1_thresh.png`
- `projects/calamum-moltbook-observer/assets/plots/canary_v1_test_nolog.png`
