# Demo Pipeline Report: demo_20260331T212901782257Z

- Workflow: demo
- Created (UTC): 2026-03-31T21:29:02.286858Z
- Decision: go
- Summary: Demo pipeline completed through observerctl ds.

## Context

- dataset_seed: 123
- max_fpr: 0.01
- model_seed: 42
- output_override: False

## Result

- max_fpr: 0.01
- metrics:
  - f1: 1.0
  - fpr: 0.0
  - precision: 1.0
  - recall: 1.0
- reason_codes: []
- run_mode: demo
- total_records: 60
- workflow_steps: ["generate", "build", "train-supervised", "train-unsupervised", "evaluate"]

## Artifacts

- dataset_manifest: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/dataset/dataset_manifest.json
- evaluation_run_json: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/evaluation/run.json
- evaluation_run_md: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/evaluation/run.md
- features_csv: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/dataset/features.csv
- labels_csv: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/dataset/labels.csv
- root_dir: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z
- supervised_model_path: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/models/supervised/model.pkl
- supervised_train_manifest: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/models/supervised/train_manifest.json
- unsupervised_model_path: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/models/unsupervised/model.pkl
- unsupervised_train_manifest: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/models/unsupervised/train_manifest.json

## Lineage

- source_report_paths:
  - json: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/report/report.json
  - manifest: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/report/manifest.json
  - markdown: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z/report/report.md
- source_run_root: local_untracked/analysis/runs/demo/demo_20260331T212901782257Z

## Report paths

- json: docs/reports/ds/runs/2026/2026-03/demo_20260331T212901782257Z/report.json
- manifest: docs/reports/ds/runs/2026/2026-03/demo_20260331T212901782257Z/manifest.json
- markdown: docs/reports/ds/runs/2026/2026-03/demo_20260331T212901782257Z/report.md
