#!/usr/bin/env python3
"""Run the existing observer demo pipeline and summarize its artifacts."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Add src to path to import local modules
SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from obfuscator_lib import Obfuscator

from analysis.dataset_builder import main as dataset_main
from analysis.evaluation_harness import main as eval_main
from analysis.report_visuals import summarize_threshold_scores_csv, write_threshold_report
from analysis.score_unsupervised import score_dataset
from analysis.train_model import main as train_main


def _run_command(args: List[str], func: Callable[[Optional[List[str]]], int]) -> None:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        ret = func(args)
    if ret != 0:
        raise RuntimeError('command failed with exit code {0}: {1}'.format(ret, ' '.join(args)))


def _build_demo_records() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for i in range(50):
        records.append(Obfuscator.sign_record({
            'timestamp': '2026-02-10T09:00:{0:02d}Z'.format(i),
            'type': 'post',
            'author_hash': 'user_{0}'.format(i),
            'content_length': 20 + i,
            'has_code_block': False,
            'f_complexity': 0.1,
            'f_toxicity': 0,
            'tv_id': 'TV-0',
        }))
    for i in range(10):
        records.append(Obfuscator.sign_record({
            'timestamp': '2026-02-10T09:05:{0:02d}Z'.format(i),
            'type': 'post',
            'author_hash': 'bad_actor_{0}'.format(i),
            'content_length': 200,
            'has_code_block': True,
            'f_complexity': 0.8,
            'f_toxicity': 1,
            'tv_id': 'TV-3',
        }))
    return records


def run_demo(
    *,
    root_dir: Optional[Path] = None,
    dataset_seed: int = 123,
    model_seed: int = 42,
    max_fpr: float = 0.01,
    signing_key: str = 'demo-key',
    clean: bool = True,
) -> Dict[str, Any]:
    target_root = Path(root_dir) if root_dir is not None else Path('demo_output')
    if clean and target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault('CALAMUM_DATA_SIGNING_KEY', signing_key)

    input_path = target_root / 'telemetry_input.jsonl'
    records = _build_demo_records()
    with input_path.open('w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record) + '\n')

    dataset_dir = target_root / 'dataset'
    _run_command([
        '--input', str(input_path),
        '--out-dir', str(dataset_dir),
        '--seed', str(int(dataset_seed)),
    ], dataset_main)

    manifest_path = dataset_dir / 'dataset_manifest.json'
    if not manifest_path.exists():
        manifest_path = dataset_dir / 'manifest.json'
    if not manifest_path.exists():
        raise FileNotFoundError('dataset manifest not found after demo dataset build')

    model_sup_dir = target_root / 'models' / 'supervised'
    _run_command([
        '--dataset', str(manifest_path),
        '--out-dir', str(model_sup_dir),
        '--model-type', 'supervised',
        '--seed', str(int(model_seed)),
    ], train_main)

    model_unsup_dir = target_root / 'models' / 'unsupervised'
    _run_command([
        '--dataset', str(manifest_path),
        '--out-dir', str(model_unsup_dir),
        '--model-type', 'unsupervised',
        '--seed', str(int(model_seed)),
    ], train_main)

    with manifest_path.open('r', encoding='utf-8') as f:
        manifest = json.load(f)
    features_csv = dataset_dir / Path(manifest['features_csv']).name
    labels_csv = dataset_dir / Path(manifest['labels_csv']).name

    eval_dir = target_root / 'evaluation'
    _run_command([
        '--features-csv', str(features_csv),
        '--labels-csv', str(labels_csv),
        '--model-path', str(model_sup_dir / 'model.pkl'),
        '--max-fpr', str(float(max_fpr)),
        '--out-dir', str(eval_dir),
        '--run-id', 'demo_run_001',
    ], eval_main)

    scoring_dir = target_root / 'scoring'
    scores_csv = scoring_dir / 'scores.csv'
    score_summary = score_dataset(manifest_path, model_unsup_dir / 'train_manifest.json', scores_csv)
    threshold_summary = write_threshold_report(
        summarize_threshold_scores_csv(scores_csv, float(max_fpr)),
        scoring_dir,
    )

    run_json_path = eval_dir / 'run.json'
    run_payload: Dict[str, Any] = {}
    if run_json_path.exists():
        with run_json_path.open('r', encoding='utf-8') as f:
            run_payload = json.load(f)

    return {
        'root_dir': str(target_root),
        'record_count': int(len(records)),
        'dataset_manifest': str(manifest_path),
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'supervised_model_path': str(model_sup_dir / 'model.pkl'),
        'supervised_train_manifest': str(model_sup_dir / 'train_manifest.json'),
        'unsupervised_model_path': str(model_unsup_dir / 'model.pkl'),
        'unsupervised_train_manifest': str(model_unsup_dir / 'train_manifest.json'),
        'scores_csv': str(scores_csv),
        'score_column': str(score_summary.get('score_column', 'score_anomaly')),
        'threshold_report_json': str(threshold_summary.get('report_json', '')),
        'threshold_report_md': str(threshold_summary.get('report_md', '')),
        'threshold_summary': threshold_summary,
        'evaluation_run_json': str(run_json_path),
        'evaluation_run_md': str(eval_dir / 'run.md'),
        'max_fpr': float(max_fpr),
        'run_payload': run_payload,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Run the observer demo pipeline and emit a summary packet.')
    parser.add_argument('--out-dir', type=Path, default=Path('demo_output'))
    parser.add_argument('--dataset-seed', type=int, default=123)
    parser.add_argument('--model-seed', type=int, default=42)
    parser.add_argument('--max-fpr', type=float, default=0.01)
    args = parser.parse_args(argv)

    summary = run_demo(
        root_dir=args.out_dir,
        dataset_seed=args.dataset_seed,
        model_seed=args.model_seed,
        max_fpr=args.max_fpr,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
