from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from obfuscator_lib import Obfuscator
from analysis.dataset_builder import build_dataset


@pytest.fixture(autouse=True)
def _set_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-key')


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r) + '\n')


def test_end_to_end_model_training_and_eval(tmp_path: Path) -> None:
    # Skip if ApexLab is not installed in the active environment.
    try:
        import apexlab  # noqa: F401
    except ImportError:
        pytest.skip("ApexLab not installed")

    from analysis.train_model import main as train_main
    from analysis.evaluation_harness import main as eval_main

    # 1. Generate synthetic data
    records = []
    # Normal records (TV-0)
    for i in range(20):
        r = {
            'timestamp': f'2026-02-10T00:00:{i:02d}Z',
            'type': 'post',
            'author_hash': f'norm{i:012d}',
            'content_length': 10,
            'has_code_block': False,
            'f_complexity': 0.1,
            'f_toxicity': 0,
            'tv_id': 'TV-0',
        }
        records.append(Obfuscator.sign_record(r))

    # Anomaly records (TV-3) - make them distinct so model learns
    for i in range(5):
        r = {
            'timestamp': f'2026-02-10T00:01:{i:02d}Z',
            'type': 'post',
            'author_hash': f'bad{i:013d}',
            'content_length': 1000,
            'has_code_block': True,
            'f_complexity': 0.9,
            'f_toxicity': 1,
            'tv_id': 'TV-3',
        }
        records.append(Obfuscator.sign_record(r))

    input_path = tmp_path / 'input.jsonl'
    _write_jsonl(input_path, records)

    # 2. Build Dataset
    dataset_dir = tmp_path / 'dataset'
    manifest = build_dataset(
        [input_path],
        out_dir=dataset_dir,
        seed=123,
        split={'train': 0.6, 'val': 0.2, 'test': 0.2}
    )
    manifest_path = dataset_dir / 'dataset_manifest.json'
    assert manifest_path.exists()

    # 3. Train Model (Supervised)
    model_dir = tmp_path / 'models_supervised'
    res = train_main([
        '--dataset', str(manifest_path),
        '--out-dir', str(model_dir),
        '--model-type', 'supervised',
        '--seed', '42'
    ])
    assert res == 0
    assert (model_dir / 'model.pkl').exists()
    assert (model_dir / 'train_manifest.json').exists()

    # 4. Train Model (Unsupervised)
    model_unsup_dir = tmp_path / 'models_unsupervised'
    res = train_main([
        '--dataset', str(manifest_path),
        '--out-dir', str(model_unsup_dir),
        '--model-type', 'unsupervised',
        '--seed', '42'
    ])
    assert res == 0
    assert (model_unsup_dir / 'model.pkl').exists()

    # 5. Evaluate (Supervised Model)
    # Use features from build_dataset (located in features_csv)
    # Check that eval harness runs with the model
    eval_out = tmp_path / 'eval_supervised'
    res = eval_main([
        '--features-csv', str(dataset_dir / Path(manifest.features_csv).name),
        '--labels-csv', str(dataset_dir / Path(manifest.labels_csv).name),
        '--model-path', str(model_dir / 'model.pkl'),
        '--out-dir', str(eval_out),
        '--run-id', 'test_run'
    ])
    assert res == 0
    assert (eval_out / 'run.json').exists()
    
    run_json = json.loads((eval_out / 'run.json').read_text(encoding='utf-8'))
    assert run_json['model']['family'] == 'trained_apexlab'
    assert run_json['model']['class'] == 'RandomForestClassifier'
