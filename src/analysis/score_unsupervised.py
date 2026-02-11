from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import joblib
    import numpy as np
except ImportError:
    print("Error: scikit-learn/numpy is required.")
    sys.exit(1)


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

def main() -> int:
    parser = argparse.ArgumentParser(description="Score datasets using a trained unsupervised model.")
    parser.add_argument("--dataset", required=True, type=Path, help="Path to dataset_manifest.json")
    parser.add_argument("--model", required=True, type=Path, help="Path to model.joblib or train_manifest.json")
    parser.add_argument("--out-file", required=True, type=Path, help="Output path for scores CSV")
    
    args = parser.parse_args()
    
    # 1. Load Model
    model_path = args.model
    if model_path.name.endswith(".json"):
        with model_path.open('r') as f:
            tm = json.load(f)
        model_path = model_path.parent / Path(tm["model_path"]).name
        
    print(f"Loading model from {model_path}...")
    model = joblib.load(model_path)
    
    # 2. Load Data
    print(f"Loading features from {args.dataset}...")
    features, all_cols = load_dataset_features(args.dataset)
    
    # The model expects specific columns in order. 
    # Check model.n_features_in_ if available, or assume Training Manifest order.
    # For Unsupervised IF, we need numerical columns only.
    # We'll filter out record_id.
    
    train_cols = [c for c in all_cols if c != 'record_id']
    
    X = []
    record_ids = []
    
    for row in features:
        vec = [row.get(c, 0.0) for c in train_cols]
        X.append(vec)
        record_ids.append(row['record_id'])
        
    print(f"Scoring {len(X)} records...")
    
    # 3. Score
    # decision_function: average anomaly score of X of the base classifiers.
    # The anomaly score of an input sample is computed as the mean anomaly score of the trees in the forest.
    # For IsolationForest: 
    #   decision_function returns negative values for outliers (anomalies) and positive for inliers.
    #   Wait, sklearn ISOLATION FOREST:
    #   "The accumulation of the score is done by the ensemble. ... The lower, the more abnormal."
    #   "decision_function: ... The strictly lower, the more abnormal."
    #   "score_samples: ... Opposite of the anomaly score defined in the original paper."
    # Let's use decision_function. Lower = more anomalous.
    # To make it intuitive (Higher = Anomaly), we might negate it.
    # Let's write the raw decision_function value and let threshold logic handle it.
    
    scores = model.decision_function(X)
    
    # 4. Write Output
    args.out_file.parent.mkdir(parents=True, exist_ok=True)
    with args.out_file.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["record_id", "score_raw"])
        for rid, s in zip(record_ids, scores):
            writer.writerow([rid, s])
            
    print(f"Scores written to {args.out_file}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
