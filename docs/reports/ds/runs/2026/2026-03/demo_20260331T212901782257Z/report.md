# Demo Pipeline Report: demo_20260331T212901782257Z

**Status**: `go`
**Workflow**: `demo`
**Created (UTC)**: `2026-03-31T21:29:02.286858Z`
**Runtime CLI surface**: `observerctl`
**Command path**: `observerctl ds run demo`

## Executive summary

Demo pipeline completed through observerctl ds.

## Run snapshot

| Field | Value |
| --- | --- |
| Run ID | demo_20260331T212901782257Z |
| Workflow | demo |
| Decision | go |
| Created UTC | 2026-03-31T21:29:02.286858Z |
| Runtime CLI Surface | observerctl |
| Command Path | observerctl ds run demo |

## Context

| Field | Value |
| --- | --- |
| Dataset Seed | 123 |
| Max FPR | 0.01 |
| Model Seed | 42 |
| Output Override | False |

## Result overview

| Field | Value |
| --- | --- |
| Max FPR | 0.01 |
| Run Mode | demo |
| Total Records | 60 |

### Metrics

| Metric | Value |
| --- | --- |
| F1 | 1.0 |
| FPR | 0.0 |
| Precision | 1.0 |
| Recall | 1.0 |

### Workflow steps

1. `generate`
2. `build`
3. `train-supervised`
4. `train-unsupervised`
5. `evaluate`

### Reason codes

- none

## Artifact index

| Artifact | Path |
| --- | --- |
| Dataset Manifest | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/dataset/dataset_manifest.json` |
| Evaluation Run JSON | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/evaluation/run.json` |
| Evaluation Run MD | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/evaluation/run.md` |
| Features CSV | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/dataset/features.csv` |
| Labels CSV | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/dataset/labels.csv` |
| Root Dir | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z` |
| Supervised Model Path | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/models/supervised/model.pkl` |
| Supervised Train Manifest | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/models/supervised/train_manifest.json` |
| Unsupervised Model Path | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/models/unsupervised/model.pkl` |
| Unsupervised Train Manifest | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/models/unsupervised/train_manifest.json` |

## Provenance

### Source lineage

| Field | Value |
| --- | --- |
| Source Run Root | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z` |

### Source Report Paths

| Surface | Path |
| --- | --- |
| JSON | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/report/report.json` |
| Manifest | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/report/manifest.json` |
| Markdown | `local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/report/report.md` |

## Report paths

| Surface | Path |
| --- | --- |
| JSON | `docs/reports/ds/runs/2026/2026-03/demo_20260331T212901782257Z/report.json` |
| Manifest | `docs/reports/ds/runs/2026/2026-03/demo_20260331T212901782257Z/manifest.json` |
| Markdown | `docs/reports/ds/runs/2026/2026-03/demo_20260331T212901782257Z/report.md` |
