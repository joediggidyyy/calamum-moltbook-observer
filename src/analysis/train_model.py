from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import joblib
    from sklearn.ensemble import IsolationForest, RandomForestClassifier
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )
except ImportError:
    print("Error: scikit-learn is required. Install it with: pip install scikit-learn")
    print("Note: If working in Calamum environment, ensure src/requirements.txt is installed.")
    sys.exit(1)


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


def load_dataset(manifest_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    """
    Load features and splits from the dataset manifest.
    Returns (features_list, record_id_to_split_map, label_map or None)
    """
    with manifest_path.open('r', encoding='utf-8') as f:
        manifest = json.load(f)

    base_dir = manifest_path.parent
    
    # Load features
    features_path = base_dir / Path(manifest['features_csv']).name
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
    splits_path = base_dir / Path(manifest['splits_csv']).name
    record_split_map = {}
    with splits_path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            record_split_map[row['record_id']] = row['split']

    # Load labels if available
    labels_map = {}
    if manifest.get('labels_csv'):
        labels_path = base_dir / Path(manifest['labels_csv']).name
        if labels_path.exists():
            with labels_path.open('r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    labels_map[row['record_id']] = row['label']

    return features, record_split_map, labels_map, manifest['feature_columns']


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description='Train Calamum Observer models.')
    p.add_argument('--dataset', required=True, type=Path, help='Path to dataset manifest.json')
    p.add_argument('--out-dir', required=True, type=Path, help='Output directory for model artifacts')
    p.add_argument('--model-type', choices=['supervised', 'unsupervised'], default='supervised')
    p.add_argument('--seed', type=int, default=42)
    
    args = p.parse_args(argv)
    
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading dataset from {args.dataset}...")
    features, split_map, label_map, feature_cols = load_dataset(args.dataset)
    
    # Filter columns to only those used for training (exclude record_id)
    train_cols = [c for c in feature_cols if c != 'record_id']
    
    # Prepare X and y
    X_train = []
    y_train = []
    X_val = []
    y_val = []
    
    for row in features:
        rid = row['record_id']
        split = split_map.get(rid)
        
        vec = [row[c] for c in train_cols]
        label = label_map.get(rid) if label_map else None
        
        # If supervised, skip if no label
        if args.model_type == 'supervised' and label is None:
            continue
            
        if split == 'train':
            X_train.append(vec)
            if label is not None:
                y_train.append(label)
        elif split == 'val':
            X_val.append(vec)
            if label is not None:
                y_val.append(label)
                
    print(f"Training set: {len(X_train)} samples")
    print(f"Validation set: {len(X_val)} samples")
    
    model = None
    metrics = {}
    params = {'seed': args.seed, 'model_type': args.model_type}
    
    if args.model_type == 'supervised':
        print("Training Random Forest (Supervised)...")
        clf = RandomForestClassifier(n_estimators=100, random_state=args.seed)
        clf.fit(X_train, y_train)
        
        # Validation
        if X_val:
            y_pred = clf.predict(X_val)
            metrics['accuracy'] = accuracy_score(y_val, y_pred)
            metrics['f1_macro'] = f1_score(y_val, y_pred, average='macro')
            metrics['report'] = classification_report(y_val, y_pred, output_dict=True)
            print(f"Validation Accuracy: {metrics['accuracy']:.4f}")
        
        model = clf
        
    elif args.model_type == 'unsupervised':
        print("Training Isolation Forest (Unsupervised)...")
        # For IF, we train on logical 'normal' data if we knew it, or just all train data
        # Here we train on X_train (unlabeled or labeled, doesn't matter)
        clf = IsolationForest(n_estimators=100, random_state=args.seed, contamination=0.1)
        clf.fit(X_train)
        
        # Validation for unsupervised is tricky without ground truth. 
        # If we have labels, we can treat anomalies as one class.
        # But broadly we just save the model.
        if X_val and y_val:
             # simple heuristic check if we have implementation details
             # (This is a gap in unsupervised eval spec, so we just skip specific metrics for now)
             pass
        
        model = clf

    # Save artifacts
    model_path = out_dir / 'model.joblib'
    joblib.dump(model, model_path)
    print(f"Saved model to {model_path}")
    
    train_manifest = TrainManifest(
        created_at_utc=utc_now_iso(),
        dataset_manifest_path=str(args.dataset),
        model_type=args.model_type,
        model_path=str(model_path),
        metrics_path=str(out_dir / 'metrics.json'),
        params=params,
        metrics=metrics,
        feature_columns=feature_cols
    )
    
    with (out_dir / 'train_manifest.json').open('w', encoding='utf-8') as f:
        json.dump(asdict(train_manifest), f, indent=2, sort_keys=True)
        
    print("Training complete.")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
