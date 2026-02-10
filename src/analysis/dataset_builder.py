"""
Calamum Dataset Builder

Responsible for converting raw JSONL telemetry logs into versioned, deterministic datasets
ready for ML training or evaluation.

Strict adherence to DATA780:
- Reads obfuscated JSONL inputs.
- Validates structural integrity (optionally via Obfuscator.verify_record).
- Extracts features into a windowed or tabular format (e.g., JSON list of feature vectors).
- Generates deterministic splits (Train/Val/Test).
- Writes a dataset manifest (hash, counts, version).

Features extracted (names-only/metadata-only):
- Content length
- Mentions/Tags count
- Time of day / Day of week
- (Synthetic only) TV-Labels if present
"""

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Helper to find src root for imports if needed
src_root = Path(__file__).resolve().parents[1]
if str(src_root) not in sys.path:
    sys.path.append(str(src_root))

try:
    import obfuscator_lib
except ImportError:
    obfuscator_lib = None

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def calculate_file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()

class DatasetBuilder:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.records: List[Dict[str, Any]] = []
        random.seed(self.seed)

    def load_jsonl(self, input_paths: List[Path], verify_signatures: bool = False):
        """Load and parse records from one or more JSONL files."""
        for p in input_paths:
            if not p.exists():
                print(f"[WARN] Input not found: {p}", file=sys.stderr)
                continue
            
            with p.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if verify_signatures and obfuscator_lib:
                            if not obfuscator_lib.Obfuscator.verify_record(record):
                                # Skip invalid signatures silently or log?
                                # For strict builder, maybe skip.
                                continue
                        self.records.append(record)
                    except json.JSONDecodeError:
                        continue

    def extract_features(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a raw log record into a feature vector.
        
        Input Schema (Typical Obfuscated):
        {
          "content_length": int,
          "has_code_block": bool,
          "tags_count": int,
          "mentions_count": int,
          "timestamp": iso_str,
          "type": str,
          "tv_id": str (Optional - Synthetic only)
        }
        """
        # Time features
        ts_str = record.get('timestamp')
        hour = 0
        dow = 0
        if ts_str:
            try:
                # Handle varying formats if needed, but assuming ISO8601 from agent
                dt = datetime.fromisoformat(str(ts_str).replace('Z', '+00:00'))
                hour = dt.hour
                dow = dt.weekday()
            except Exception:
                pass

        # TV Label (Target)
        # 1 if TV-3 (Adversarial), 0 otherwise. 
        # Only present if synthetic generator emitted 'tv_id'.
        tv_id = record.get('tv_id', 'TV-0')
        label = 1 if tv_id == 'TV-3' else 0

        # Numeric features vector
        features = {
            "feat_len": record.get("content_length", 0),
            "feat_code": 1 if record.get("has_code_block") else 0,
            "feat_tags": record.get("tags_count", 0),
            "feat_mentions": record.get("mentions_count", 0),
            "feat_hour": hour,
            "feat_dow": dow,
            "label": label,  # Supervised target
            "tv_id": tv_id   # Categorical for analysis
        }
        return features

    def build_dataset(self, test_split: float = 0.2, val_split: float = 0.1) -> Dict[str, List[Dict]]:
        """
        Transform loaded records into features and split them.
        Returns: {'train': [...], 'val': [...], 'test': [...]}
        """
        processed = []
        for r in self.records:
            processed.append(self.extract_features(r))
        
        # Deterministic shuffle
        random.shuffle(processed)
        
        total = len(processed)
        n_test = int(total * test_split)
        n_val = int(total * val_split)
        
        test_data = processed[:n_test]
        val_data = processed[n_test : n_test + n_val]
        train_data = processed[n_test + n_val :]
        
        return {
            "train": train_data,
            "val": val_data,
            "test": test_data
        }

    def save_artifact(self, output_dir: Path, dataset_name: str, splits: Dict[str, List[Dict]]) -> None:
        """Writes dataset files and manifest."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        manifest = {
            "dataset_name": dataset_name,
            "created_at": _utc_now_iso(),
            "seed": self.seed,
            "splits": {},
            "total_records": sum(len(d) for d in splits.values())
        }
        
        for name, data in splits.items():
            filename = f"{dataset_name}_{name}.json"
            path = output_dir / filename
            
            # Write data
            with path.open('w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Update manifest
            manifest["splits"][name] = {
                "file": filename,
                "count": len(data),
                "sha256": calculate_file_hash(path)
            }
            
        # Write Manifest
        manifest_path = output_dir / f"{dataset_name}_manifest.json"
        with manifest_path.open('w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)
            
        print(f"[DatasetBuilder] Artifact saved to {manifest_path}")

def main():
    parser = argparse.ArgumentParser(description="Deterministic Dataset Builder")
    parser.add_argument('--inputs', nargs='+', required=True, help="Input .jsonl files")
    parser.add_argument('--out-dir', required=True, help="Output directory for dataset artifacts")
    parser.add_argument('--name', default="calamum_ds_v1", help="Dataset artifact name")
    parser.add_argument('--seed', type=int, default=42, help="RNG seed for strict reproducibility")
    parser.add_argument('--verify-sigs', action='store_true', help="Verify HMAC signatures of inputs")
    
    args = parser.parse_args()
    
    builder = DatasetBuilder(seed=args.seed)
    
    input_paths = [Path(p) for p in args.inputs]
    print(f"[DatasetBuilder] Loading {len(input_paths)} input files...")
    builder.load_jsonl(input_paths, verify_signatures=args.verify_sigs)
    print(f"[DatasetBuilder] Loaded {len(builder.records)} raw records.")
    
    if not builder.records:
        print("[DatasetBuilder] No records found. Exiting.")
        sys.exit(0)
        
    print("[DatasetBuilder] processing and splitting...")
    splits = builder.build_dataset()
    
    out_dir = Path(args.out_dir)
    builder.save_artifact(out_dir, args.name, splits)
    print("[DatasetBuilder] Done.")

if __name__ == "__main__":
    main()
