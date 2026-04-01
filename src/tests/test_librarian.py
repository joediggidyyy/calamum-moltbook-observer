"""Tests for Calamum Librarian Daemon."""

import json
import os
import gzip
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import sys

# Setup Path
current_dir = Path(__file__).resolve().parent
src_dir = current_dir.parent
if str(src_dir) not in sys.path:
    sys.path.append(str(src_dir))

from calamum_librarian import (
    Librarian,
    librarian_vault_lock_packet,
    librarian_vault_verify_packet,
    register_librarian_dataset_packet,
)


def _make_temp_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# observerctl anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')
    return project_root, anchor

@pytest.fixture
def librarian_env():
    """Create a temporary environment for the librarian."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Mock the directory getters in config
        with patch('calamum_librarian.get_calamum_data_dir', return_value=tmp_path / 'data'), \
             patch('calamum_librarian.get_calamum_control_dir', return_value=tmp_path / 'control'), \
             patch('calamum_librarian.get_calamum_health_dir', return_value=tmp_path / 'health'):
            
            lib = Librarian(interval_sec=0.1)
            yield lib

def test_librarian_initialization(librarian_env):
    """Test that directories are created."""
    assert librarian_env.archive_dir.exists()
    assert librarian_env.quarantine_dir.exists()
    assert librarian_env.control_dir.exists()
    assert librarian_env.health_dir.exists()

def test_process_valid_file(librarian_env):
    """Test compression and manifest update for a valid JSONL file."""
    # Create a dummy JSONL file
    raw_path = librarian_env.archive_dir / "test.jsonl"
    data = [{"id": 1}, {"id": 2, "msg": "hello"}]
    
    with open(raw_path, 'w', encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item) + "\n")
            
    # Run once
    librarian_env.run_once()
    
    # Input should be gone
    assert not raw_path.exists()
    
    # Artifact should exist
    gz_path = librarian_env.archive_dir / "test.jsonl.gz"
    assert gz_path.exists()
    
    # Manifest should be updated
    manifest = json.loads(librarian_env.manifest_path.read_text())
    assert "test.jsonl" in manifest
    entry = manifest["test.jsonl"]
    assert entry["records"] == 2
    assert entry["uncompressed_bytes"] > 0
    assert "artifact_sha256" in entry

    # Verify GZ content
    with gzip.open(gz_path, 'rt', encoding='utf-8') as f:
        lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[1])["msg"] == "hello"

def test_process_corrupt_file(librarian_env):
    """Test quarantine of corrupt files."""
    # Create corrupt file
    bad_path = librarian_env.archive_dir / "bad.jsonl"
    bad_path.write_text('{"valid": 1}\n{broken json\n', encoding='utf-8')
    
    librarian_env.run_once()
    
    # Should be moved to quarantine
    assert not bad_path.exists()
    quarantine_path = librarian_env.quarantine_dir / "bad.jsonl"
    assert quarantine_path.exists()
    
    # Manifest should NOT have it (or maybe partial? current logic skips/fails)
    # Current logic: _process_file returns None on error, so it's NOT in manifest.
    if librarian_env.manifest_path.exists():
        manifest = json.loads(librarian_env.manifest_path.read_text())
        assert "bad.jsonl" not in manifest

def test_heartbeat_creation(librarian_env):
    """Test that heartbeat and status files are touched."""
    # run_once() logic does NOT call _touch_heartbeat in loop(), so we must call it manually or simulate loop
    librarian_env._touch_heartbeat("ok", {"msg": "test"})
    
    assert librarian_env.heartbeat_path.exists()
    assert librarian_env.status_path.exists()
    
    status = json.loads(librarian_env.status_path.read_text())
    assert status["status"] == "ok"
    assert "version" in status

def test_policy_feedback(librarian_env):
    """Test that rotation policy is updated based on average bytes."""
    # Create large-ish records
    raw_path = librarian_env.archive_dir / "dense.jsonl"
    # 100 records of 100 bytes each (approx)
    record = {"data": "x" * 90} # ~100+ bytes JSON
    content = (json.dumps(record) + "\n") * 100
    raw_path.write_text(content, encoding='utf-8')
    
    librarian_env.run_once()
    
    assert librarian_env.policy_path.exists()
    policy = json.loads(librarian_env.policy_path.read_text())
    
    # Expect avg ~100 bytes. Target 100k records -> ~10MB
    assert policy["observed_avg_bytes"] > 90
    assert policy["max_bytes"] > 9_000_000

def test_manifest_corruption_recovery(librarian_env):
    """Test that a corrupt manifest is backed up and a new one started."""
    # Write a corrupt manifest
    librarian_env.manifest_path.write_text("{broken json", encoding='utf-8')
    
    # Process a file (triggers load_manifest)
    raw_path = librarian_env.archive_dir / "recovery.jsonl"
    raw_path.write_text('{"id": 1}\n', encoding='utf-8')
    
    librarian_env.run_once()
    
    # The corrupt manifest should have been backed up
    backup = librarian_env.manifest_path.with_suffix('.bak')
    assert backup.exists()
    assert backup.read_text(encoding='utf-8') == "{broken json"
    
    # A new valid manifest should exist
    assert librarian_env.manifest_path.exists()
    manifest = json.loads(librarian_env.manifest_path.read_text())
    assert "recovery.jsonl" in manifest


def test_register_dataset_bootstraps_vault_and_projection_surfaces(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'vault_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 4,
        'has_labels': True,
    }), encoding='utf-8')

    packet = register_librarian_dataset_packet(
        anchor,
        manifest_path,
        access_class='protected-source',
        display_name='Vault Alpha',
        run_id='vault-alpha',
    )

    assert packet['decision'] == 'go'

    vault_root = project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian'
    assert (vault_root / 'authority' / 'librarian_dataset_manifest.json').exists()
    assert (vault_root / 'history' / 'librarian_dataset_catalog.jsonl').exists()
    assert (vault_root / 'integrity' / 'vault_checksum.json').exists()
    assert (vault_root / 'integrity' / 'vault_audit.jsonl').exists()

    assert (project_root / 'local_untracked' / 'analysis' / 'indexes' / 'librarian_dataset_manifest.json').exists()
    assert (project_root / 'local_untracked' / 'analysis' / 'indexes' / 'librarian_dataset_catalog.jsonl').exists()

    verify_packet = librarian_vault_verify_packet(anchor)
    assert verify_packet['decision'] == 'go'
    assert verify_packet['artifacts']['librarian_vault_baseline_json'].endswith('vault_checksum.json')


def test_vault_lock_denies_ordinary_dataset_registration(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'locked_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 1,
        'has_labels': False,
    }), encoding='utf-8')

    lock_packet = librarian_vault_lock_packet(anchor, reason='unit-test-lock')
    assert lock_packet['decision'] == 'go'

    packet = register_librarian_dataset_packet(anchor, manifest_path)

    assert packet['decision'] == 'no-go'
    assert 'critical_check_failed:librarian_vault_locked' in packet['reason_codes']

