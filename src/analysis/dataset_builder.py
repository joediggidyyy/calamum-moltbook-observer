from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ._util import (
    default_analysis_dir,
    deterministic_split_bucket,
    find_project_root,
    iter_jsonl,
    sha256_path,
    stable_record_id,
    try_get_git_sha,
    utc_now_iso,
)


SCHEMA_VERSION = 'obfuscated_record_v1'


FEATURE_COLUMNS: List[str] = [
    'record_id',
    'ts_epoch',
    'content_length',
    'has_code_block',
    'has_link',
    'tags_count',
    'mentions_count',
    'f_complexity',
    'f_code_density',
    'f_toxicity',
    'is_canary',
    'type_post',
    'type_reply',
    'type_repost',
    'type_dm',
    'type_follow',
    'type_mention',
    'type_unknown',
]


@dataclass
class InputFileMeta:
    path: str
    sha256: str
    bytes: int
    mtime: float
    records: int


@dataclass
class DatasetManifest:
    created_at_utc: str
    schema_version: str
    git_sha: Optional[str]
    inputs: List[InputFileMeta]
    total_records: int
    features_csv: str
    labels_csv: Optional[str]
    splits_csv: str
    split_manifest_json: str
    feature_columns: List[str]
    has_labels: bool
    seed: int
    split: Dict[str, float]


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        if val is None:
            return default
        return int(val)
    except Exception:
        return default


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        return float(val)
    except Exception:
        return default


def _safe_bool(val: Any) -> int:
    return 1 if bool(val) else 0


def _event_type(rec: Dict[str, Any]) -> str:
    t = rec.get('type')
    if isinstance(t, str) and t:
        return t.strip().lower()
    et = rec.get('event_type')
    if isinstance(et, str) and et:
        return et.strip().lower()
    return 'unknown'


def _is_canary(rec: Dict[str, Any]) -> bool:
    m = rec.get('mode')
    if isinstance(m, str) and m.strip().upper() == 'CANARY':
        return True
    k = rec.get('kind')
    if isinstance(k, str) and 'inbound' in k:
        return True
    et = _event_type(rec)
    return et in {'dm', 'mention', 'follow'}


def _ts_epoch(rec: Dict[str, Any]) -> float:
    # Prefer stage-4 feature
    if 'f_timestamp_epoch' in rec:
        return _safe_float(rec.get('f_timestamp_epoch'), 0.0)

    # Best-effort parse Z timestamps without external deps
    ts = rec.get('ts') or rec.get('timestamp')
    if not isinstance(ts, str) or not ts:
        return 0.0
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return float(dt.timestamp())
    except Exception:
        return 0.0


def _one_hot_type(t: str) -> Dict[str, int]:
    t = (t or '').strip().lower()
    vocab = {'post', 'reply', 'repost', 'dm', 'follow', 'mention'}
    if t not in vocab:
        t = 'unknown'
    out = {
        'type_post': 0,
        'type_reply': 0,
        'type_repost': 0,
        'type_dm': 0,
        'type_follow': 0,
        'type_mention': 0,
        'type_unknown': 0,
    }
    key = f'type_{t}'
    if key in out:
        out[key] = 1
    else:
        out['type_unknown'] = 1
    return out


def _extract_feature_row(rec: Dict[str, Any]) -> Dict[str, Any]:
    rid = stable_record_id(rec)
    t = _event_type(rec)
    oht = _one_hot_type(t)
    row: Dict[str, Any] = {
        'record_id': rid,
        'ts_epoch': _ts_epoch(rec),
        'content_length': _safe_int(rec.get('content_length'), 0),
        'has_code_block': _safe_bool(rec.get('has_code_block')),
        'has_link': _safe_bool(rec.get('has_link')),
        'tags_count': _safe_int(rec.get('tags_count'), 0),
        'mentions_count': _safe_int(rec.get('mentions_count'), 0),
        'f_complexity': _safe_float(rec.get('f_complexity'), 0.0),
        'f_code_density': _safe_float(rec.get('f_code_density'), 0.0),
        'f_toxicity': _safe_int(rec.get('f_toxicity'), 0),
        'is_canary': 1 if _is_canary(rec) else 0,
    }
    row.update(oht)
    return row


def _assign_split(bucket: float, split: Dict[str, float]) -> str:
    train = float(split.get('train', 0.7))
    val = float(split.get('val', 0.15))
    test = float(split.get('test', 0.15))
    s = train + val + test
    if s <= 0:
        return 'train'
    # Normalize
    train /= s
    val /= s
    test /= s
    if bucket < train:
        return 'train'
    if bucket < (train + val):
        return 'val'
    return 'test'


def build_dataset(
    input_paths: Sequence[Path],
    *,
    out_dir: Path,
    seed: int = 1337,
    split: Optional[Dict[str, float]] = None,
    max_lines_per_file: Optional[int] = None,
) -> DatasetManifest:
    """Build a feature dataset from one or more JSONL telemetry inputs.

    This is intentionally lightweight and stdlib-only.
    """
    if split is None:
        split = {'train': 0.7, 'val': 0.15, 'test': 0.15}

    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir = out_dir

    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    splits_csv = dataset_dir / 'splits.csv'
    split_manifest_json = dataset_dir / 'split_manifest.json'
    manifest_json = dataset_dir / 'dataset_manifest.json'

    inputs_meta: List[InputFileMeta] = []
    all_rows: List[Dict[str, Any]] = []
    labels: List[Tuple[str, str]] = []

    for p in input_paths:
        records = 0
        for jl in iter_jsonl(p, max_lines=max_lines_per_file):
            if jl.obj is None or jl.error is not None:
                continue
            rec = jl.obj
            row = _extract_feature_row(rec)
            all_rows.append(row)
            records += 1
            tv = rec.get('tv_id')
            if isinstance(tv, str) and tv:
                labels.append((row['record_id'], tv))

        try:
            st = p.stat()
            inputs_meta.append(InputFileMeta(
                path=str(p),
                sha256=sha256_path(p),
                bytes=int(st.st_size),
                mtime=float(st.st_mtime),
                records=int(records),
            ))
        except Exception:
            inputs_meta.append(InputFileMeta(
                path=str(p),
                sha256='',
                bytes=0,
                mtime=0.0,
                records=int(records),
            ))

    # Write features CSV
    with features_csv.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=FEATURE_COLUMNS)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r.get(k, '') for k in FEATURE_COLUMNS})

    has_labels = bool(labels)
    labels_path: Optional[str] = None
    if has_labels:
        # Write labels CSV (record_id,tv_id)
        with labels_csv.open('w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['record_id', 'tv_id'])
            for rid, tv in labels:
                w.writerow([rid, tv])
        labels_path = str(labels_csv)

    # Deterministic split manifest based on record_id hashing
    split_rows: List[Dict[str, Any]] = []
    counts = {'train': 0, 'val': 0, 'test': 0}
    for r in all_rows:
        rid = str(r['record_id'])
        b = deterministic_split_bucket(rid, seed)
        bucket = _assign_split(b, split)
        counts[bucket] = int(counts.get(bucket, 0) + 1)
        split_rows.append({'record_id': rid, 'split': bucket})

    # Write auditable mapping (stable order)
    split_rows_sorted = sorted(split_rows, key=lambda d: str(d.get('record_id', '')))
    with splits_csv.open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['record_id', 'split'])
        for row in split_rows_sorted:
            w.writerow([row.get('record_id', ''), row.get('split', '')])

    split_doc = {
        'created_at_utc': utc_now_iso(),
        'seed': int(seed),
        'split': dict(split),
        'counts': counts,
        'splits_csv': str(splits_csv),
        'splits_sha256': sha256_path(splits_csv),
    }
    split_manifest_json.write_text(json.dumps(split_doc, indent=2, sort_keys=True), encoding='utf-8')

    project_root = find_project_root(out_dir)
    git_sha = try_get_git_sha(project_root)

    manifest = DatasetManifest(
        created_at_utc=utc_now_iso(),
        schema_version=SCHEMA_VERSION,
        git_sha=git_sha,
        inputs=inputs_meta,
        total_records=int(len(all_rows)),
        features_csv=str(features_csv),
        labels_csv=labels_path,
        splits_csv=str(splits_csv),
        split_manifest_json=str(split_manifest_json),
        feature_columns=list(FEATURE_COLUMNS),
        has_labels=has_labels,
        seed=int(seed),
        split=dict(split),
    )

    manifest_json.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True), encoding='utf-8')

    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description='Build a Blind-ML feature dataset from Calamum JSONL telemetry.')
    p.add_argument('--input', action='append', required=True, type=Path, help='JSONL input path (repeatable)')
    p.add_argument('--out-dir', type=Path, default=None, help='Output dataset directory')
    p.add_argument('--seed', type=int, default=1337, help='Deterministic split seed')
    p.add_argument('--split-train', type=float, default=0.7)
    p.add_argument('--split-val', type=float, default=0.15)
    p.add_argument('--split-test', type=float, default=0.15)
    p.add_argument('--max-lines-per-file', type=int, default=None)
    args = p.parse_args(argv)

    out_dir = args.out_dir
    if out_dir is None:
        base = default_analysis_dir(Path(__file__))
        out_dir = base / 'datasets' / f'dataset_{utc_now_iso().replace(":", "").replace("-", "")}'

    split = {'train': float(args.split_train), 'val': float(args.split_val), 'test': float(args.split_test)}
    manifest = build_dataset(
        args.input,
        out_dir=out_dir,
        seed=int(args.seed),
        split=split,
        max_lines_per_file=args.max_lines_per_file,
    )

    print(json.dumps(asdict(manifest), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
