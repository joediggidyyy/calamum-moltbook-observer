from __future__ import annotations

import argparse
import csv
import json
import pickle
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apexlab.evaluation.metrics import classification_metrics
from apexlab.models import IsolationForest, RandomForestClassifier

from ._util import utc_now_iso


@dataclass
class TrainManifest:
    created_at_utc: str
    dataset_manifest_path: str
    model_type: str
    model_path: str
    metrics_path: str
    params: Dict[str, Any]
    metrics: Dict[str, Any]
    feature_columns: List[str]
    git_sha: Optional[str] = None


def _require_manifest_text(manifest: Dict[str, Any], key: str) -> str:
    value = str(manifest.get(key, '') or '').strip()
    if not value:
        raise ValueError('dataset manifest missing required field: {0}'.format(key))
    return value


def _require_manifest_list(manifest: Dict[str, Any], key: str) -> List[str]:
    value = manifest.get(key, [])
    if not isinstance(value, list):
        raise ValueError('dataset manifest missing required field: {0}'.format(key))
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if not cleaned:
        raise ValueError('dataset manifest missing required field: {0}'.format(key))
    return cleaned


def _resolve_manifest_artifact(manifest_path: Path, artifact_ref: str, key: str) -> Path:
    target = manifest_path.parent / Path(str(artifact_ref or '').strip()).name
    if not target.exists():
        raise ValueError('dataset manifest path missing: {0}'.format(key))
    return target


def load_dataset(manifest_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    """
    Load features and splits from the dataset manifest.
    Returns (features_list, record_id_to_split_map, label_map or None)
    """
    with manifest_path.open('r', encoding='utf-8') as f:
        manifest = json.load(f)

    if not isinstance(manifest, dict):
        raise ValueError('dataset manifest is not a JSON object')

    base_dir = manifest_path.parent
    
    # Load features
    features_path = _resolve_manifest_artifact(manifest_path, _require_manifest_text(manifest, 'features_csv'), 'features_csv')
    features = []
    with features_path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric columns
            for k, v in row.items():
                if k not in ('record_id',):
                    try:
                        row[k] = float(v)
                    except ValueError:
                        pass
            features.append(row)

    # Load splits
    splits_path = _resolve_manifest_artifact(manifest_path, _require_manifest_text(manifest, 'splits_csv'), 'splits_csv')
    record_split_map = {}
    with splits_path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            record_split_map[row['record_id']] = row['split']

    # Load labels if available
    labels_map = {}
    if manifest.get('labels_csv'):
        labels_path = _resolve_manifest_artifact(manifest_path, str(manifest.get('labels_csv', '') or '').strip(), 'labels_csv')
        if labels_path.exists():
            with labels_path.open('r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Support 'tv_id' or 'label' column
                    lbl = row.get('tv_id') or row.get('label')
                    if lbl:
                        labels_map[row['record_id']] = lbl

    return features, record_split_map, labels_map, _require_manifest_list(manifest, 'feature_columns')


def train_model(
    dataset_manifest_path: Path,
    *,
    out_dir: Path,
    model_type: str = 'supervised',
    seed: int = 42,
) -> TrainManifest:
    out_dir.mkdir(parents=True, exist_ok=True)

    features, split_map, label_map, feature_cols = load_dataset(dataset_manifest_path)
    if model_type == 'supervised' and not label_map:
        raise ValueError('supervised training requires labels_csv in the dataset manifest')
    train_cols = [c for c in feature_cols if c != 'record_id']

    X_train = []
    y_train = []
    X_val = []
    y_val = []

    for row in features:
        rid = row['record_id']
        split = split_map.get(rid)

        vec = [row[c] for c in train_cols]
        label = label_map.get(rid) if label_map else None
        if model_type == 'supervised' and label is None:
            continue

        label_value = 1 if label == 'TV-3' else 0

        if split == 'train':
            X_train.append(vec)
            if label is not None:
                y_train.append(label_value)
        elif split == 'val':
            X_val.append(vec)
            if label is not None:
                y_val.append(label_value)

    if not X_train:
        raise ValueError('dataset did not yield any training rows')

    model = None
    metrics: Dict[str, Any] = {}
    params = {'seed': int(seed), 'model_type': str(model_type)}

    if model_type == 'supervised':
        clf = RandomForestClassifier(n_estimators=100, random_state=seed)
        clf.fit(X_train, y_train)

        if X_val:
            y_pred = clf.predict(X_val)
            class_metrics = classification_metrics([str(value) for value in y_val], [str(value) for value in y_pred])
            metrics['accuracy'] = class_metrics['accuracy']
            report = class_metrics['classification_report']
            per_label_keys = [key for key in report.keys() if key != 'accuracy']
            if per_label_keys:
                metrics['f1_macro'] = sum(float(report[key]['f1-score']) for key in per_label_keys) / float(len(per_label_keys))
            else:
                metrics['f1_macro'] = 0.0
            metrics['report'] = report
            metrics['confusion_matrix'] = class_metrics['confusion_matrix']

        model = clf

    elif model_type == 'unsupervised':
        clf = IsolationForest(n_estimators=100, random_state=seed, contamination=0.1)
        clf.fit(X_train)
        model = clf

    model_path = out_dir / 'model.pkl'
    with model_path.open('wb') as f:
        pickle.dump(model, f)

    metrics_path = out_dir / 'metrics.json'
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding='utf-8')

    train_manifest = TrainManifest(
        created_at_utc=utc_now_iso(),
        dataset_manifest_path=str(dataset_manifest_path),
        model_type=model_type,
        model_path=str(model_path),
        metrics_path=str(metrics_path),
        params=params,
        metrics=metrics,
        feature_columns=feature_cols,
    )

    with (out_dir / 'train_manifest.json').open('w', encoding='utf-8') as f:
        json.dump(asdict(train_manifest), f, indent=2, sort_keys=True)

    return train_manifest


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description='Train Calamum Observer models.')
    p.add_argument('--dataset', required=True, type=Path, help='Path to dataset manifest.json')
    p.add_argument('--out-dir', required=True, type=Path, help='Output directory for model artifacts')
    p.add_argument('--model-type', choices=['supervised', 'unsupervised'], default='supervised')
    p.add_argument('--seed', type=int, default=42)
    
    args = p.parse_args(argv)
    
    print(f"Loading dataset from {args.dataset}...")
    train_manifest = train_model(
        args.dataset,
        out_dir=args.out_dir,
        model_type=args.model_type,
        seed=args.seed,
    )
    print(f"Saved model to {train_manifest.model_path}")
    print("Training complete.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
