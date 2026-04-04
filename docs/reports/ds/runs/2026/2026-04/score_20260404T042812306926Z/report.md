# Scoring Report: score_20260404T042812306926Z

**Status**: `go`
**Workflow**: `score`
**Created (UTC)**: `2026-04-04T04:31:17.363104Z`
**Runtime CLI surface**: `observerctl`
**Command path**: `observerctl ds score`

## Executive summary

Unsupervised scoring completed through observerctl ds.

## Run snapshot

| Field | Value |
| --- | --- |
| Run ID | score_20260404T042812306926Z |
| Workflow | score |
| Decision | go |
| Created UTC | 2026-04-04T04:31:17.363104Z |
| Runtime CLI Surface | observerctl |
| Command Path | observerctl ds score |

## Context

| Field | Value |
| --- | --- |
| Output Override | False |

## Result overview

| Field | Value |
| --- | --- |
| Anomaly Direction | lower-is-more-anomalous |
| Records Scored | 412340 |
| Score Column | score_anomaly |

### Reason codes

- none

## Visuals

### Visual summary

| Field | Value |
| --- | --- |
| Anomaly Direction | lower-is-more-anomalous |
| Figure Count | 1 |

### Score distribution

Distribution of anomaly scores. Lower scores indicate more anomalous records.

![Score distribution](figures/score_distribution.png)

## Artifact index

| Artifact | Path |
| --- | --- |
| Resolved Model Path | `local_untracked/analysis/runs/train/train_20260404T041211146010Z/model/model.pkl` |
| Score Distribution PNG | `docs/reports/ds/runs/2026/2026-04/score_20260404T042812306926Z/figures/score_distribution.png` |
| Scores CSV | `local_untracked/analysis/runs/score/score_20260404T042812306926Z/scoring/scores.csv` |

## Provenance

### Source lineage

| Field | Value |
| --- | --- |
| Dataset Manifest | `local_untracked/analysis/runs/build/build_20260404T040910794598Z/dataset/dataset_manifest.json` |
| Model Reference | `local_untracked/analysis/runs/train/train_20260404T041211146010Z/model/train_manifest.json` |
| Source Run Root | `local_untracked/analysis/runs/score/score_20260404T042812306926Z` |

### Source Report Paths

| Surface | Path |
| --- | --- |
| JSON | `local_untracked/analysis/runs/score/score_20260404T042812306926Z/report/report.json` |
| Manifest | `local_untracked/analysis/runs/score/score_20260404T042812306926Z/report/manifest.json` |
| Markdown | `local_untracked/analysis/runs/score/score_20260404T042812306926Z/report/report.md` |

## Report paths

| Surface | Path |
| --- | --- |
| JSON | `docs/reports/ds/runs/2026/2026-04/score_20260404T042812306926Z/report.json` |
| Manifest | `docs/reports/ds/runs/2026/2026-04/score_20260404T042812306926Z/manifest.json` |
| Markdown | `docs/reports/ds/runs/2026/2026-04/score_20260404T042812306926Z/report.md` |
