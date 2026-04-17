from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import joblib
except ImportError:
    joblib = None


def load_dataset_features(manifest_path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Load features from the dataset manifest.
    Returns (features_list_of_dicts, feature_columns_ordered)
    """
    with manifest_path.open('r', encoding='utf-8') as f:
        manifest = json.load(f)

    base_dir = manifest_path.parent
    features_path = base_dir / Path(manifest['features_csv']).name
    
    features = []
    feature_columns = manifest['feature_columns']
    
    with features_path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed = {}
            # Keep record_id as string
            parsed['record_id'] = row['record_id']
            # Parse numeric features
            for c in feature_columns:
                if c != 'record_id' and c in row:
                    try:
                        parsed[c] = float(row[c])
                    except ValueError:
                        parsed[c] = 0.0
            
            # Carry over labels if present in features (e.g. from debug columns)
            # But usually labels are in labels.csv. We'll join them later if needed.
            features.append(parsed)
            
    return features, feature_columns


def score_dataset(dataset_manifest_path: Path, model_reference: Path, out_file: Path) -> Dict[str, Any]:
    model_path = model_reference
    if model_path.name.endswith('.json'):
        with model_path.open('r', encoding='utf-8') as f:
            tm = json.load(f)
        model_path = model_path.parent / Path(tm['model_path']).name

    try:
        with model_path.open('rb') as f:
            model = pickle.load(f)
    except Exception as pickle_error:
        if joblib is None:
            raise RuntimeError('could not load model via pickle and joblib is unavailable ({0})'.format(pickle_error))
        model = joblib.load(model_path)

    features, all_cols = load_dataset_features(dataset_manifest_path)
    train_cols = [c for c in all_cols if c not in ('record_id', 'is_canary')]

    X = []
    record_ids = []
    for row in features:
        vec = [row.get(c, 0.0) for c in train_cols]
        X.append(vec)
        record_ids.append(row['record_id'])

    if hasattr(model, 'score_samples'):
        scores = [float(score) for score in model.score_samples(X)]
    elif hasattr(model, 'decision_function'):
        scores = [float(score) for score in model.decision_function(X)]
    else:
        raise RuntimeError('model does not expose a supported anomaly scoring surface')

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['record_id', 'score_anomaly'])
        for rid, score in zip(record_ids, scores):
            writer.writerow([rid, score])

    return {
        'dataset_manifest_path': str(dataset_manifest_path),
        'model_reference_path': str(model_reference),
        'resolved_model_path': str(model_path),
        'out_file': str(out_file),
        'records_scored': int(len(record_ids)),
        'score_column': 'score_anomaly',
        'anomaly_direction': 'lower-is-more-anomalous',
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Score datasets using a trained unsupervised model.")
    parser.add_argument("--dataset", required=True, type=Path, help="Path to dataset_manifest.json")
    parser.add_argument("--model", required=True, type=Path, help="Path to model.joblib or train_manifest.json")
    parser.add_argument("--out-file", required=True, type=Path, help="Output path for scores CSV")
    
    args = parser.parse_args(argv)

    summary = score_dataset(args.dataset, args.model, args.out_file)
    print(f"Scores written to {summary['out_file']}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
