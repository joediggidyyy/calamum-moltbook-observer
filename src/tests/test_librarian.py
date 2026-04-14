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
    dataset_authority_entry_for_manifest,
    dataset_authority_entry_for_selector,
    dataset_display_alias_for_manifest,
    librarian_vault_lock_packet,
    librarian_vault_verify_packet,
    register_librarian_dataset_packet,
)
from analysis._util import normalize_repo_or_absolute_path, sha256_path


def _make_temp_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# observerctl anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')
    return project_root, anchor


def _write_dataset_manifest(
    project_root: Path,
    slug: str,
    *,
    total_records: int = 1,
    has_labels: bool = False,
    source: str = '',
    mode: str = '',
) -> Path:
    dataset_dir = project_root / 'datasets' / slug
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    if has_labels:
        labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    manifest_payload = {
        'features_csv': str(features_csv),
        'total_records': int(total_records),
        'has_labels': bool(has_labels),
    }
    source_token = str(source or '').strip().lower()
    mode_token = str(mode or '').strip().lower()
    if source_token and mode_token:
        manifest_payload['inputs'] = [
            {
                'path': str(
                    project_root
                    / 'logs'
                    / 'data'
                    / 'calamum'
                    / 'archive'
                    / 'resource_{0}_{1}_fixture_{2}_seg0001.jsonl.gz'.format(source_token, mode_token, slug)
                ),
                'records': int(total_records),
            },
        ]
    if has_labels:
        manifest_payload['labels_csv'] = str(labels_csv)
    manifest_path.write_text(json.dumps(manifest_payload), encoding='utf-8')
    return manifest_path

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


def test_register_dataset_infers_source_and_mode_from_manifest_inputs(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'scope_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 2,
        'has_labels': False,
        'inputs': [
            {
                'path': str(project_root / 'logs' / 'data' / 'calamum' / 'archive' / 'resource_real_canary_normal_scope_probe_seg0001.jsonl.gz'),
                'records': 2,
            },
            {
                'path': str(project_root / 'logs' / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'moltbook_metrics.jsonl'),
                'records': 1,
            },
        ],
    }), encoding='utf-8')

    packet = register_librarian_dataset_packet(anchor, manifest_path, display_name='Scope Alpha', run_id='scope-alpha')

    assert packet['decision'] == 'go'
    assert packet['dataset']['source'] == 'real'
    assert packet['dataset']['mode'] == 'canary'


def test_register_dataset_uses_dominant_mixed_input_scope_for_display_alias(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'dominant_scope_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 13842,
        'has_labels': False,
        'inputs': [
            {
                'path': str(project_root / 'local_untracked' / 'analysis' / 'observer_derived' / 'real' / 'live' / 'real_live_recent_20260405T000000Z.jsonl'),
                'records': 13718,
            },
            {
                'path': str(project_root / 'local_untracked' / 'analysis' / 'observer_derived' / 'sim' / 'canary' / 'sim_canary_recent_20260406T155800Z.jsonl'),
                'records': 124,
            },
        ],
    }), encoding='utf-8')

    packet = register_librarian_dataset_packet(
        anchor,
        manifest_path,
        display_name='Dominant Scope Alpha',
        run_id='dominant-scope-alpha',
    )

    expected_alias = 'liv-r{0}'.format(sha256_path(manifest_path)[-4:])

    assert packet['decision'] == 'go'
    assert packet['dataset']['source'] == 'real'
    assert packet['dataset']['mode'] == 'live'
    assert packet['dataset']['display_alias'] == expected_alias
    assert dataset_display_alias_for_manifest(anchor, manifest_path) == expected_alias


def test_dataset_display_alias_for_manifest_falls_back_to_registered_run_id_when_scope_alias_missing(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'presentation_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 3,
        'has_labels': False,
    }), encoding='utf-8')

    packet = register_librarian_dataset_packet(
        anchor,
        manifest_path,
        display_name='Presentation Alpha',
        run_id='presentation-alpha',
    )

    assert packet['decision'] == 'go'
    assert packet['dataset']['display_alias'] == 'presentation-alpha'
    assert dataset_display_alias_for_manifest(anchor, manifest_path) == 'presentation-alpha'


def test_dataset_display_alias_for_manifest_uses_stable_manifest_fallback_when_unregistered(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'unregistered_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 2,
        'has_labels': False,
    }), encoding='utf-8')

    alias = dataset_display_alias_for_manifest(anchor, manifest_path)

    assert alias == 'dataset-{0}'.format(sha256_path(manifest_path)[-6:])


def test_dataset_authority_api_treats_router_as_hash_hint_not_authority(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    alpha_manifest = _write_dataset_manifest(project_root, 'authority_alpha', total_records=2, has_labels=False, source='real', mode='live')
    beta_manifest = _write_dataset_manifest(project_root, 'authority_beta', total_records=4, has_labels=False, source='real', mode='canary')

    alpha_packet = register_librarian_dataset_packet(
        anchor,
        alpha_manifest,
        access_class='local',
        display_name='Authority Alpha',
        run_id='authority-alpha',
    )
    beta_packet = register_librarian_dataset_packet(
        anchor,
        beta_manifest,
        access_class='local',
        display_name='Authority Beta',
        run_id='authority-beta',
    )

    router_path = project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'authority' / 'librarian_dataset_routing_map.json'
    router = json.loads(router_path.read_text(encoding='utf-8'))
    beta_terminal = 'sha256:{0}'.format(beta_packet['dataset']['dataset_manifest_sha256'])
    router['token_index']['selector_run_id:{0}'.format(alpha_packet['dataset']['run_id'])] = [beta_terminal]
    router['token_index']['manifest_sha256:{0}'.format(alpha_packet['dataset']['dataset_manifest_sha256'])] = [beta_terminal]
    router_path.write_text(json.dumps(router, indent=2, sort_keys=True), encoding='utf-8')

    selector_entry = dataset_authority_entry_for_selector(anchor, alpha_packet['dataset']['run_id'])
    manifest_entry = dataset_authority_entry_for_manifest(anchor, alpha_manifest)

    assert selector_entry['entry_id'] == alpha_packet['dataset']['entry_id']
    assert manifest_entry['entry_id'] == alpha_packet['dataset']['entry_id']
    assert dataset_display_alias_for_manifest(anchor, alpha_manifest) == alpha_packet['dataset']['display_alias']


def test_register_dataset_links_latest_baseline_context_for_inferred_scope(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'baseline_link_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 2,
        'has_labels': False,
        'inputs': [
            {
                'path': str(project_root / 'logs' / 'data' / 'calamum' / 'archive' / 'resource_real_canary_normal_baseline_link_seg0001.jsonl.gz'),
                'records': 2,
            },
        ],
    }), encoding='utf-8')

    evidence_dir = project_root / 'local_untracked' / 'analysis' / 'observer_derived' / 'real' / 'canary' / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    baseline_packet = evidence_dir / 'observerctl_baseline-analysis_dataset_link.json'
    baseline_packet.write_text(json.dumps({
        'timestamp_utc': '2026-04-06T12:00:00Z',
        'decision': 'go',
        'summary': 'Latest baseline context for the dataset admission link.',
        'baseline_window_id': 'dataset-link-window-001',
        'sample_counts': {'resource_normal': 5, 'resource_baseline': 7},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': '2026-04-06T12:00:00Z',
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet).replace('\\', '/'),
        'baseline_window_id': 'dataset-link-window-001',
    }) + '\n', encoding='utf-8')

    packet = register_librarian_dataset_packet(anchor, manifest_path, display_name='Baseline Link Alpha', run_id='baseline-link-alpha')

    assert packet['decision'] == 'go'
    assert packet['dataset']['source'] == 'real'
    assert packet['dataset']['mode'] == 'canary'
    assert packet['dataset']['baseline_window_id'] == 'dataset-link-window-001'
    assert packet['dataset']['baseline_analysis_packet'].endswith('observerctl_baseline-analysis_dataset_link.json')
    assert packet['dataset']['baseline_sample_counts'] == {'resource_normal': 5, 'resource_baseline': 7}
    assert packet['artifacts']['baseline_analysis_packet'].endswith('observerctl_baseline-analysis_dataset_link.json')


def test_register_dataset_emits_librarian_router_with_shipped_v1_contract(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    manifest_path = _write_dataset_manifest(project_root, 'router_contract_alpha', total_records=4, has_labels=False)

    packet = register_librarian_dataset_packet(
        anchor,
        manifest_path,
        access_class='local',
        display_name='Router Contract Alpha',
        run_id='router-contract-alpha',
    )

    router_path = project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'authority' / 'librarian_dataset_routing_map.json'
    router = json.loads(router_path.read_text(encoding='utf-8'))
    terminal = 'sha256:{0}'.format(packet['dataset']['dataset_manifest_sha256'])
    collections_id = '{0}:{1}'.format(packet['dataset']['source'], packet['dataset']['mode'])
    authority_manifest_ref = normalize_repo_or_absolute_path(
        project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'authority' / 'librarian_dataset_manifest.json',
        project_root,
    )

    assert router_path.exists()
    assert router['schema_version'] == '1.0'
    assert router['authoritative'] is False
    assert router['router_kind'] == 'librarian_dataset_router_v1'
    assert router['authority_refs'] == {'manifest': authority_manifest_ref}
    assert set(router['action_classes'].keys()) == {'scope_actions', 'selector_actions', 'alias_actions'}
    assert 'packet_actions' not in router['action_classes']
    assert 'packet_join' not in router['authority_refs']
    assert router['token_index']['selector_index:1'] == [terminal]
    assert router['token_index']['entry_id:{0}'.format(packet['dataset']['entry_id'])] == [terminal]
    assert router['token_index']['selector_run_id:{0}'.format(packet['dataset']['run_id'])] == [terminal]
    assert router['token_index']['display_name:{0}'.format(packet['dataset']['display_name'])] == [terminal]
    assert router['token_index']['manifest_sha256:{0}'.format(packet['dataset']['dataset_manifest_sha256'])] == [terminal]
    assert router['token_index']['alias_id:{0}'.format(packet['dataset']['display_alias'])] == [terminal]
    assert router['token_index']['collections_id:{0}'.format(collections_id)] == [terminal]
    assert router['deref'][terminal] == 'manifest:#/entries/0'


def test_router_emission_tracks_manifest_parity_for_scope_tokens_and_deref(tmp_path: Path) -> None:
    project_root, anchor = _make_temp_project(tmp_path)
    live_alpha_manifest = _write_dataset_manifest(project_root, 'router_live_alpha', total_records=3, has_labels=False, source='real', mode='live')
    live_beta_manifest = _write_dataset_manifest(project_root, 'router_live_beta', total_records=5, has_labels=True, source='real', mode='live')
    canary_manifest = _write_dataset_manifest(project_root, 'router_canary_gamma', total_records=7, has_labels=False, source='real', mode='canary')

    live_alpha_packet = register_librarian_dataset_packet(
        anchor,
        live_alpha_manifest,
        access_class='local',
        display_name='Router Live Alpha',
        run_id='router-live-alpha',
        )
    live_beta_packet = register_librarian_dataset_packet(
        anchor,
        live_beta_manifest,
        access_class='local',
        display_name='Router Live Beta',
        run_id='router-live-beta',
    )
    canary_packet = register_librarian_dataset_packet(
        anchor,
        canary_manifest,
        access_class='local',
        display_name='Router Canary Gamma',
        run_id='router-canary-gamma',
    )

    snapshot_path = project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'authority' / 'librarian_dataset_manifest.json'
    router_path = project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'authority' / 'librarian_dataset_routing_map.json'
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    router = json.loads(router_path.read_text(encoding='utf-8'))

    approved_entries = [
        entry for entry in snapshot['entries']
        if entry.get('status') == 'approved'
        and entry.get('readiness') == 'ready'
        and entry.get('registration_kind') == 'manual-register'
    ]
    manifest_indexes = {
        str(entry.get('entry_id', '')): index
        for index, entry in enumerate(snapshot['entries'])
    }
    expected_live_terminals = [
        'sha256:{0}'.format(entry['resolver']['dataset_manifest_sha256'])
        for entry in approved_entries
        if '{0}:{1}'.format(entry.get('source', ''), entry.get('mode', '')) == 'real:live'
    ]
    expected_live_alias_nodes = {
        live_alpha_packet['dataset']['display_alias']: ['sha256:{0}'.format(live_alpha_packet['dataset']['dataset_manifest_sha256'])],
        live_beta_packet['dataset']['display_alias']: ['sha256:{0}'.format(live_beta_packet['dataset']['dataset_manifest_sha256'])],
    }

    assert router['token_index']['collections_id:real:live'] == expected_live_terminals
    assert router['action_classes']['scope_actions']['scopes']['real:live']['dataset_hashes'] == expected_live_terminals
    assert router['action_classes']['selector_actions']['scopes']['real:live']['dataset_hashes'] == expected_live_terminals
    assert router['action_classes']['alias_actions']['scopes']['real:live']['alias_nodes'] == expected_live_alias_nodes
    assert router['token_index']['collections_id:real:canary'] == [
        'sha256:{0}'.format(canary_packet['dataset']['dataset_manifest_sha256'])
    ]

    for selector_index, entry in enumerate(approved_entries, start=1):
        dataset_hash = str(entry['resolver']['dataset_manifest_sha256'])
        terminal = 'sha256:{0}'.format(dataset_hash)
        entry_id = str(entry.get('entry_id', ''))
        run_id = str(entry.get('run_id', ''))
        display_name = str(entry.get('display_name', ''))
        manifest_index = manifest_indexes[entry_id]

        assert router['token_index']['selector_index:{0}'.format(selector_index)] == [terminal]
        assert router['token_index']['entry_id:{0}'.format(entry_id)] == [terminal]
        assert router['token_index']['selector_run_id:{0}'.format(run_id)] == [terminal]
        assert router['token_index']['display_name:{0}'.format(display_name)] == [terminal]
        assert router['token_index']['manifest_sha256:{0}'.format(dataset_hash)] == [terminal]
        assert router['deref'][terminal] == 'manifest:#/entries/{0}'.format(manifest_index)

