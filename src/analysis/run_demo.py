#!/usr/bin/env python3
"""
Job 0012 Demonstration Script.
Generates synthetic data and executes the full Blind ML pipeline:
1. Data Generation (Input JSONL)
2. Dataset Building (Manifest creation)
3. Model Training (Supervised + Unsupervised)
4. Evaluation (metrics generation)
"""

import sys
import shutil
import json
from pathlib import Path

# Add src to path to import local modules
SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from obfuscator_lib import Obfuscator
    from analysis.dataset_builder import main as dataset_main
    from analysis.train_model import main as train_main
    from analysis.evaluation_harness import main as eval_main
except ImportError as e:
    print(f"Import Error: {e}")
    print("Ensure you are running from the project root or have python path set.")
    sys.exit(1)

def run_command(args: list[str], func) -> None:
    print(f"CMD: {' '.join(args)}")
    ret = func(args)
    if ret != 0:
        print(f"Command failed with exit code {ret}")
        sys.exit(ret)

def main():
    root_dir = Path("demo_output")
    if root_dir.exists():
        shutil.rmtree(root_dir)
    root_dir.mkdir()
    
    print("=== 1. Generating Synthetic Data ===")
    input_path = root_dir / "telemetry_input.jsonl"
    
    # We need to set a signing key environment variable for the Obfuscator to work identically
    import os
    os.environ['CALAMUM_DATA_SIGNING_KEY'] = 'demo-key'
    
    records = []
    # Generate 50 'normal' posts (TV-0)
    for i in range(50):
        records.append(Obfuscator.sign_record({
            'timestamp': f'2026-02-10T09:00:{i:02d}Z',
            'type': 'post',
            'author_hash': f'user_{i}',
            'content_length': 20 + i,
            'has_code_block': False,
            'f_complexity': 0.1,
            'f_toxicity': 0,
            'tv_id': 'TV-0'
        }))
        
    # Generate 10 'toxic' posts (TV-3)
    for i in range(10):
        records.append(Obfuscator.sign_record({
            'timestamp': f'2026-02-10T09:05:{i:02d}Z',
            'type': 'post',
            'author_hash': f'bad_actor_{i}',
            'content_length': 200,
            'has_code_block': True,
            'f_complexity': 0.8,
            'f_toxicity': 1,
            'tv_id': 'TV-3'
        }))
        
    with input_path.open('w') as f:
        for r in records:
            f.write(json.dumps(r) + '\n')
    print(f"Generated {len(records)} records to {input_path}")
    
    print("\n=== 2. Building Dataset ===")
    dataset_dir = root_dir / "dataset"
    run_command([
        '--input', str(input_path),
        '--out-dir', str(dataset_dir),
        '--seed', '123'
    ], dataset_main)
    
    manifest_path = dataset_dir / "dataset_manifest.json"
    if not manifest_path.exists():
        # Fallback for flexibility
        manifest_path = dataset_dir / "manifest.json"
        
    if not manifest_path.exists():
        print("Dataset manifest not found!")
        sys.exit(1)
        
    print(f"Dataset built at {dataset_dir}")
    
    print("\n=== 3. Training Supervised Model (Random Forest) ===")
    model_sup_dir = root_dir / "models" / "supervised"
    run_command([
        '--dataset', str(manifest_path),
        '--out-dir', str(model_sup_dir),
        '--model-type', 'supervised',
        '--seed', '42'
    ], train_main)
    
    print("\n=== 4. Training Unsupervised Model (Isolation Forest) ===")
    model_unsup_dir = root_dir / "models" / "unsupervised"
    run_command([
        '--dataset', str(manifest_path),
        '--out-dir', str(model_unsup_dir),
        '--model-type', 'unsupervised',
        '--seed', '42'
    ], train_main)
    
    print("\n=== 5. Evaluating Supervised Model ===")
    # Extract csv paths from manifest
    with manifest_path.open() as f:
        m = json.load(f)
        feat_csv = dataset_dir / Path(m['features_csv']).name
        lbl_csv = dataset_dir / Path(m['labels_csv']).name
        
    eval_dir = root_dir / "evaluation"
    run_command([
        '--features-csv', str(feat_csv),
        '--labels-csv', str(lbl_csv),
        '--model-path', str(model_sup_dir / "model.pkl"),
        '--out-dir', str(eval_dir),
        '--run-id', 'demo_run_001'
    ], eval_main)
    
    print("\n=== DEMO COMPLETE ===")
    print(f"Artifacts located in {root_dir.absolute()}")
    print("Run JSON:")
    run_json_path = eval_dir / "run.json"
    if run_json_path.exists():
        print(run_json_path.read_text())

if __name__ == "__main__":
    print("DEBUG: Main block started")
    main()
