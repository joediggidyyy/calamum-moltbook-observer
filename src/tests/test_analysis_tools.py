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
from analysis.evaluation_harness import evaluate
from analysis.validate_jsonl import validate_jsonl_file


@pytest.fixture(autouse=True)
def _set_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-key')


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r) + '\n')


def test_validate_jsonl_passes_signed_records(tmp_path: Path) -> None:
    rec = {
        'timestamp': '2026-02-10T00:00:00Z',
        'type': 'post',
        'author_hash': 'abcd' * 4,
        'content_length': 12,
        'has_code_block': False,
        'tags_count': 0,
        'mentions_count': 0,
        'f_complexity': 0.2,
        'f_code_density': 0.0,
        'f_toxicity': 0,
        'f_timestamp_epoch': 0.0,
    }
    signed = Obfuscator.sign_record(rec)
    p = tmp_path / 'input.jsonl'
    _write_jsonl(p, [signed])

    summary, errors = validate_jsonl_file(p, verify_signatures=True)
    assert summary.error_lines == 0
    assert errors == []
    assert summary.signature_present == 1
    assert summary.signature_verified == 1


def test_validate_jsonl_blocks_forbidden_payload_keys(tmp_path: Path) -> None:
    rec = {
        'timestamp': '2026-02-10T00:00:00Z',
        'type': 'post',
        'content': 'raw semantic payload is not allowed',
    }
    p = tmp_path / 'bad.jsonl'
    _write_jsonl(p, [rec])

    summary, errors = validate_jsonl_file(p)
    assert summary.error_lines == 1
    assert any('forbidden_raw_payload_key' in e for e in errors)


def test_build_dataset_deterministic_splits_and_eval(tmp_path: Path) -> None:
    # Create a small labeled synthetic dataset (tv_id) and sign it.
    records = []
    for i in range(8):
        r = {
            'timestamp': f'2026-02-10T00:00:{i:02d}Z',
            'type': 'post',
            'author_hash': f'{i:016d}',
            'content_length': 10,
            'has_code_block': False,
            'tags_count': 0,
            'mentions_count': 0,
            'f_complexity': 0.1,
            'f_code_density': 0.0,
            'f_toxicity': 0,
            'f_timestamp_epoch': float(i),
            'tv_id': 'TV-0',
        }
        records.append(Obfuscator.sign_record(r))

    for i in range(2):
        r = {
            'timestamp': f'2026-02-10T00:01:{i:02d}Z',
            'type': 'post',
            'author_hash': f'tv3{i:014d}',
            'content_length': 50,
            'has_code_block': True,
            'tags_count': 1,
            'mentions_count': 1,
            'f_complexity': 0.8,
            'f_code_density': 0.2,
            'f_toxicity': 2,
            'f_timestamp_epoch': float(100 + i),
            'tv_id': 'TV-3',
        }
        records.append(Obfuscator.sign_record(r))

    jsonl = tmp_path / 'synthetic.jsonl'
    _write_jsonl(jsonl, records)

    out1 = tmp_path / 'out1'
    out2 = tmp_path / 'out2'

    m1 = build_dataset([jsonl], out_dir=out1, seed=42)
    m2 = build_dataset([jsonl], out_dir=out2, seed=42)

    # Deterministic split mapping should match byte-for-byte (sorted by record_id)
    splits1 = (Path(m1.splits_csv)).read_text(encoding='utf-8')
    splits2 = (Path(m2.splits_csv)).read_text(encoding='utf-8')
    assert splits1 == splits2

    # Baseline evaluator should respect max_fpr constraint (easy synthetic separability here)
    res = evaluate(Path(m1.features_csv), labels_csv=Path(m1.labels_csv) if m1.labels_csv else None, max_fpr=0.01)
    assert res.has_labels is True
    assert res.metrics.get('fpr', 1.0) <= 0.01
