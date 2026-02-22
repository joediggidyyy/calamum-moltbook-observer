# Observer Resource Spike Lockdown Standard (Official) — 2026-02-21

**Document ID**: `OBSERVER_RESOURCE_SPIKE_LOCKDOWN_STANDARD_20260221`  
**Owner**: ORACL-Prime  
**Approver**: joediggidyyy  
**Status**: OFFICIAL STANDARD (ACTIVE)  
**Scope**: `projects/calamum-moltbook-observer/`  
**Policy mode**: names-only, fail-closed

---

## Purpose

Define official CPU/RAM spike surveillance and trigger policy for watchdog elevated posture, including dense trend-analysis and ML-oriented scoring guidance.

This standard is binding for gate semantics where resource instability may indicate hostile pressure, runtime degradation, or emerging posture risk.

---

## Non-negotiable posture caveat (official)

Security posture has **two modes only**:

1. `isolation` (watch/canary)
2. `lockdown` (live/honeypot)

### Critical rule

`live` receives the **same scrutiny and reactions as honeypot**.

- All lockdown adjustments are made **up to honeypot standards**.
- Do **not** reduce honeypot thresholds to meet live “in the middle”.
- No midpoint averaging, no relaxation downgrades for `live`.

---

## Data-science monitoring model

### Feature stream

At each watchdog sample interval, compute:

- `cpu_pct_now`
- `ram_pct_now`
- `cpu_pct_ema_short` (e.g., 30s EMA)
- `ram_pct_ema_short` (e.g., 30s EMA)
- `cpu_pct_ema_long` (e.g., 5m EMA)
- `ram_pct_ema_long` (e.g., 5m EMA)
- `cpu_slope_30s` (linear slope over last 30s)
- `ram_slope_30s` (linear slope over last 30s)
- `cpu_p95_15m`, `ram_p95_15m`
- `cpu_zscore_15m`, `ram_zscore_15m`
- `sample_freshness_sec`

All values remain names-only telemetry metrics with no secret-bearing payload.

### Baseline windows

- short window: 30s
- medium window: 5m
- baseline window: 15m rolling

### Composite spike score (interpretable)

Define:

$$
S = w_1\cdot I_{abs} + w_2\cdot I_{rel} + w_3\cdot I_{trend} + w_4\cdot I_{z}
$$

Where:

- $I_{abs}$: absolute-threshold indicator
- $I_{rel}$: baseline-relative jump indicator
- $I_{trend}$: slope/EMA divergence indicator
- $I_{z}$: z-score anomaly indicator

Recommended starter weights:

- $w_1=0.40$, $w_2=0.25$, $w_3=0.20$, $w_4=0.15$

Interpretation bands:

- `S < 0.40`: normal
- `0.40 ≤ S < 0.70`: elevated (warn)
- `S ≥ 0.70`: critical (lockdown action)

---

## Official trigger points

## Isolation profile (`watch`, `canary`)

Warn (sustained 20s):

- CPU ≥ 70%
- RAM ≥ 78%
- or relative jump: CPU > `cpu_p95_15m + 15`, RAM > `ram_p95_15m + 12`

Critical (sustained 30s):

- CPU ≥ 85%
- RAM ≥ 90%
- or `S ≥ 0.70`

Reaction:

- maintain `isolation`
- increase sampling cadence
- emit major/critical reason codes as applicable

## Lockdown profile (Honeypot standard applied to both `live` and `honeypot`)

Warn (sustained 10s):

- CPU ≥ 60%
- RAM ≥ 72%
- or relative jump: CPU > `cpu_p95_15m + 12`, RAM > `ram_p95_15m + 10`

Critical (sustained 10s):

- CPU ≥ 75%
- RAM ≥ 85%
- or `S ≥ 0.70`

Reaction:

- enforce/maintain `lockdown`
- freeze non-essential writes (append-only evidence remains)
- deny promotions until recovery criteria are met

**Live parity clause**: `live` uses this exact lockdown profile with no relaxed thresholds.

---

## Gate checks and reason codes

Required checks:

- `watchdog.resource_sampling_fresh`
- `watchdog.cpu_spike_within_limits`
- `watchdog.ram_spike_within_limits`
- `watchdog.resource_baseline_valid`
- `watchdog.resource_spike_score_within_limits`

Normalized denial reason codes:

- `critical_check_failed:resource_sampling_stale`
- `critical_check_failed:cpu_spike_lockdown`
- `critical_check_failed:ram_spike_lockdown`
- `critical_check_failed:resource_baseline_invalid`
- `critical_check_failed:resource_spike_score_critical`

Warn-level reason codes (non-denial unless policy escalates):

- `major_check_failed:cpu_spike_detected`
- `major_check_failed:ram_spike_detected`
- `major_check_failed:resource_spike_score_elevated`

---

## Recovery and hysteresis

To avoid oscillation:

- isolation modes require 3 consecutive clean windows to downgrade alert state.
- lockdown modes require 5 consecutive clean windows to downgrade alert state.
- promotion gates remain denied while critical resource reasons are active.

---

## ML integration notes (dense documentation requirement)

### Supervised track (optional)

- Label windows as `normal`, `elevated`, `critical` using incident evidence.
- Candidate models: gradient boosting / calibrated logistic classifier.
- Primary objective: minimize false-negative critical windows.

### Unsupervised track (always-on candidate)

- Rolling Isolation Forest or robust Mahalanobis on standardized feature vectors.
- Use unsupervised anomaly score as additive signal in $I_z$ or $I_{trend}$.

### Drift handling

- Monitor population drift for CPU/RAM distributions by posture mode.
- Recompute baseline quantiles daily or after significant workload shifts.
- Track model score calibration in `sim` before applying to `real` policy influence.

### Explainability

Every critical decision should emit top contributors:

- `top_feature_1`, `top_feature_2`, `top_feature_3`
- `score_components` (`abs`, `rel`, `trend`, `z`)

This keeps audits publication-grade and reproducible.

---

## Linkage to active remediation lane

- Job lane report: `docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVERCTL-IMPLEMENTATION-GAP-REMEDIATION-20260221.md`
- Official audit source: `projects/calamum-moltbook-observer/docs/reports/operations/OBSERVERCTL_IMPLEMENTATION_GAP_AUDIT_20260221.md`

---

## Compact evidence schema template snippet (observer-scoped reports)

For observer-scoped qualifying reports, append JSONL events in this compact publication-grade shape:

`{"timestamp_utc":"<ISO-8601>","event":"<event_name>","status":"ok|warn|fail","actor":"ORACL-Prime","artifacts":["<repo-relative-path>"],"policy_refs":["OBSERVER_RESOURCE_SPIKE_LOCKDOWN_STANDARD_20260221"],"validation":{"type":"<check_type>","target":"<target>","result":"<summary>"},"rationale":"<falsifiable_why>","uncertainty_notes":"<known_limits_or_confounders>"}`

Optional observer enrichments:

- `posture_mode`
- `source_mode`
- `reason_codes`
- `measurement_context`
- `replay_inputs`

---

Prepared by ORACL-Prime for joediggidyyy.
