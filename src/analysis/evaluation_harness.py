"""
Calamum Blind ML Evaluation Harness

Runs standardized evaluations on processed datasets (produced by dataset_builder.py).

Features:
- Baseline Heuristic: "Length Threshold" (Classify as TV-3/Adversarial if length > N)
- Baseline Heuristic: "Code Block" (Classify as TV-3 if has_code_block)
- (Future) Random Forest classification (requires scikit-learn).
- Metrics: Accuracy, Precision, Recall, FPR (False Positive Rate).
- Output: `run.json` and `run.md` (Human readable report).

Policy:
- FPR < 1% is the critical success metric for TV-3 detection (per DATA780).
- No new dependencies (using stats/math standard lib unless scikit-learn verified installed).
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

class Metrics:
    @staticmethod
    def compute(y_true: List[int], y_pred: List[int]) -> Dict[str, float]:
        tp = 0
        tn = 0
        fp = 0
        fn = 0
        
        for t, p in zip(y_true, y_pred):
            if t == 1 and p == 1: tp += 1
            if t == 0 and p == 0: tn += 1
            if t == 0 and p == 1: fp += 1
            if t == 1 and p == 0: fn += 1
            
        total = tp + tn + fp + fn
        if total == 0:
            return {"acc": 0.0, "fpr": 0.0, "prec": 0.0, "rec": 0.0}
            
        acc = (tp + tn) / total
        
        # FPR = FP / (FP + TN)
        negatives = fp + tn
        fpr = fp / negatives if negatives > 0 else 0.0
        
        # Precision = TP / (TP + FP)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        
        # Recall = TP / (TP + FN)
        positives = tp + fn
        rec = tp / positives if positives > 0 else 0.0
        
        return {
            "accuracy": round(acc, 4),
            "fpr": round(fpr, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "counts": {"tp": tp, "tn": tn, "fp": fp, "fn": fn}
        }

class BaselineModels:
    @staticmethod
    def predict_length_heuristic(data: List[Dict], threshold: int = 200) -> List[int]:
        """Predict 1 (Adversarial) if content_length > threshold."""
        return [1 if d.get("feat_len", 0) > threshold else 0 for d in data]

    @staticmethod
    def predict_code_heuristic(data: List[Dict]) -> List[int]:
        """Predict 1 (Adversarial) if has_code_block is true."""
        return [1 if d.get("feat_code", 0) == 1 else 0 for d in data]

class EvaluationHarness:
    def __init__(self):
        self.results = {}

    def load_dataset_file(self, path: Path) -> List[Dict]:
        if not path.exists():
            return []
        with path.open('r', encoding='utf-8') as f:
            return json.load(f)

    def run(self, test_data: List[Dict]):
        if not test_data:
            print("[Harness] No test data provided.")
            return

        y_true = [d.get("label", 0) for d in test_data]
        
        # Model 1: Length Heuristic (>200 chars)
        y_pred_len = BaselineModels.predict_length_heuristic(test_data, threshold=200)
        self.results["baseline_length_gt200"] = Metrics.compute(y_true, y_pred_len)
        
        # Model 2: Code Block Heuristic
        y_pred_code = BaselineModels.predict_code_heuristic(test_data)
        self.results["baseline_has_code"] = Metrics.compute(y_true, y_pred_code)
        
        # Model 3: Random Guess (Control) -- 10% prob
        import random
        random.seed(42)
        y_pred_rnd = [1 if random.random() < 0.1 else 0 for _ in test_data]
        self.results["control_random_10pct"] = Metrics.compute(y_true, y_pred_rnd)

    def generate_report(self, output_dir: Path, run_id: str):
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON Artifact
        report_json = {
            "run_id": run_id,
            "timestamp": _utc_now_iso(),
            "results": self.results
        }
        json_path = output_dir / f"run_{run_id}.json"
        with json_path.open('w', encoding='utf-8') as f:
            json.dump(report_json, f, indent=2)
            
        # Markdown Narrative
        md_lines = [
            f"# Evaluation Report: {run_id}",
            f"**Date**: {_utc_now_iso()}",
            "",
            "## Summary of Results",
            "",
            "| Model | Accuracy | FPR | Precision | Recall |",
            "|---|---|---|---|---|",
        ]
        
        for name, m in self.results.items():
            row = f"| {name} | {m['accuracy']} | **{m['fpr']}** | {m['precision']} | {m['recall']} |"
            md_lines.append(row)
            
        md_lines.append("")
        md_lines.append("## Analysis")
        md_lines.append(f"- **FPR Compliance**: {self._analyze_fpr(self.results)}")
        
        md_path = output_dir / f"run_{run_id}.md"
        with md_path.open('w', encoding='utf-8') as f:
            f.write("\n".join(md_lines))
            
        print(f"[Harness] Reports generated in {output_dir}")

    def _analyze_fpr(self, results: Dict) -> str:
        best_model = None
        min_fpr = 1.0
        
        for name, m in results.items():
            if m['fpr'] < min_fpr:
                min_fpr = m['fpr']
                best_model = name
                
        if min_fpr < 0.01:
            return f"PASS ({best_model} achieved FPR {min_fpr} < 1.0%)"
        else:
            return f"FAIL (Best FPR was {min_fpr} by {best_model})"

def main():
    parser = argparse.ArgumentParser(description="Blind ML Evaluation Harness")
    parser.add_argument('--test-set', required=True, help="Path to dataset_test.json")
    parser.add_argument('--out-dir', required=True, help="Directory for report outputs")
    parser.add_argument('--run-id', default="eval_001", help="Identifier for this run")
    
    args = parser.parse_args()
    
    harness = EvaluationHarness()
    
    print(f"[Harness] Loading test set {args.test_set}...")
    data = harness.load_dataset_file(Path(args.test_set))
    print(f"[Harness] Loaded {len(data)} examples.")
    
    harness.run(data)
    harness.generate_report(Path(args.out_dir), args.run_id)

if __name__ == "__main__":
    main()
