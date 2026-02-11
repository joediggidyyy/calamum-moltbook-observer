from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List

try:
    import numpy as np
except ImportError:
    print("Error: numpy is required.")
    sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate anomaly threshold for target FPR.")
    parser.add_argument("--scores", required=True, type=Path, help="Path to scores.csv (record_id, score_raw)")
    parser.add_argument("--target-fpr", type=float, default=0.01, help="Target False Positive Rate e.g. 0.01 for 1 percent")
    parser.add_argument("--out-report", required=True, type=Path, help="Path to output markdown report")
    
    args = parser.parse_args()
    
    # 1. Load Scores
    scores = []
    with args.scores.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                scores.append(float(row['score_raw']))
            except ValueError:
                pass
                
    if not scores:
        print("Error: No scores found.")
        sys.exit(1)
        
    n = len(scores)
    print(f"Loaded {n} scores.")
    
    # 2. Determine Threshold
    # Logic: IsolationForest decision_function -> Lower is more abnormal.
    # Anomaly = score < T
    # We assume 'scores' comes from a Benign dataset (or mostly benign).
    # We want FPR < target.
    # FPR = Fraction of Benign samples classified as Anomaly.
    # Fraction(score < T) < target_fpr.
    # T = percentile(scores, target_fpr * 100)
    
    scores_np = np.array(scores)
    target_percentile = args.target_fpr * 100.0
    threshold = np.percentile(scores_np, target_percentile)
    
    # Verify
    n_fp = np.sum(scores_np < threshold)
    actual_fpr = n_fp / n
    
    print(f"Target FPR: {args.target_fpr:.4f}")
    print(f"Calculated Threshold: {threshold:.6f}")
    print(f"Actual FPR on this set: {actual_fpr:.6f} ({n_fp}/{n})")
    
    # 3. Generate Report
    report = f"""# Threshold Selection Report

**Date**: {Path(args.out_report).stat().st_mtime if args.out_report.exists() else 'New'}
**Dataset**: {args.scores.name}
**Target FPR**: {args.target_fpr * 100:.2f}%
**Logic**: Isolation Forest (Lower Score = More Anomalous)

## Result
- **Selected Threshold**: `{threshold:.6f}`
- **Observed FPR**: {actual_fpr * 100:.4f}% ({n_fp}/{n} records)

## Distribution Stats
- Min: {np.min(scores_np):.6f}
- Max: {np.max(scores_np):.6f}
- Mean: {np.mean(scores_np):.6f}
- Median: {np.median(scores_np):.6f}

## Usage
Scores **lower** than `{threshold:.6f}` should be flagged as Anomalies.
"""
    
    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    with args.out_report.open('w', encoding='utf-8') as f:
        f.write(report)
        
    # Also write a JSON sidecar for machine consumption
    meta = {
        "threshold": float(threshold),
        "target_fpr": args.target_fpr,
        "actual_fpr": float(actual_fpr),
        "n_samples": n,
        "algo": "iforest_lower_is_anomaly"
    }
    
    json_path = args.out_report.with_suffix('.json')
    with json_path.open('w') as f:
        json.dump(meta, f, indent=2)
        
    print(f"Report written to {args.out_report}")
    print(f"Metadata written to {json_path}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
