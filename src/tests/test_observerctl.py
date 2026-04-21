from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from obfuscator_lib import Obfuscator

import observerctl as observerctl_module
from calamum_librarian import Librarian
from observerctl_terminal import strip_ansi

from observerctl import (  # noqa: E402
    _default_output_path,
    _evidence_index_path,
    build_evidence_pack,
    collect_runtime_status,
    evaluate_gate_decision,
    main,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"status":"ok"}\n', encoding='utf-8')


def _resolve_reported_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return observerctl_module._project_root() / path


def _read_jsonl_rows(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8').splitlines():
        line = str(line).strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _latest_jsonl_row_for_stream(path: Path, stream_type: str) -> dict:
    for row in reversed(_read_jsonl_rows(path)):
        if str(row.get('stream_type', '')).strip().lower() == str(stream_type).strip().lower():
            return row
    return {}


def _latest_jsonl_row_for_event(path: Path, event: str) -> dict:
    for row in reversed(_read_jsonl_rows(path)):
        if str(row.get('event', '')).strip().lower() == str(event).strip().lower():
            return row
    return {}


def _write_watchdog_posture(control_dir: Path, posture: str, heartbeat_interval: float, baseline_interval: float) -> None:
    payload = {
        'posture_trigger': posture,
        'heartbeat_interval_seconds': heartbeat_interval,
        'baseline_validation_interval_seconds': baseline_interval,
    }
    (control_dir / 'watchdog_posture_state.json').write_text(json.dumps(payload), encoding='utf-8')


def _write_watchdog_resource(control_dir: Path, cpu_now: float, ram_now: float, cpu_p95: float, ram_p95: float, score: float, age_s: float) -> None:
    payload = {
        'cpu_pct_now': cpu_now,
        'ram_pct_now': ram_now,
        'cpu_p95_15m': cpu_p95,
        'ram_p95_15m': ram_p95,
        'resource_spike_score': score,
        'sample_age_seconds': age_s,
    }
    (control_dir / 'watchdog_resource_state.json').write_text(json.dumps(payload), encoding='utf-8')


def _set_security_report_ref(monkeypatch, base_dir: Path) -> Path:
    report = base_dir / 'security_report_test.md'
    report.write_text('# security report\n', encoding='utf-8')
    monkeypatch.setenv('CALAMUM_SECURITY_REPORT_REF', str(report))
    return report


def _set_signing_env(monkeypatch) -> None:
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.setenv('CALAMUM_REQUESTER_SIGNING_KEY', 'unit-test-requester-signing-key')
    monkeypatch.setenv('CALAMUM_LIBRARIAN_ATTESTATION_KEY', 'unit-test-librarian-attestation-key')
    monkeypatch.setenv('CALAMUM_SOURCE_RELEASE_KEY', 'unit-test-source-release-key')
    monkeypatch.setenv('CALAMUM_LIBRARIAN_VAULT_KEY', 'unit-test-vault-integrity-key')


def _seed_keysmith_surface(project_root: Path) -> None:
    (project_root / 'src').mkdir(parents=True, exist_ok=True)
    (project_root / 'src' / 'keysmith.py').write_text('# keysmith surface\n', encoding='utf-8')
    deployment_dir = project_root / 'deployment' / 'keysmith'
    deployment_dir.mkdir(parents=True, exist_ok=True)
    (deployment_dir / 'Dockerfile').write_text('FROM python:3.11\n', encoding='utf-8')
    (deployment_dir / 'requirements.txt').write_text('requests\n', encoding='utf-8')


def _write_signed_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(Obfuscator.sign_record(record)) + '\n')


def _seed_shipped_manual_report_surfaces(project_root: Path) -> None:
    source_project_root = SRC_DIR.parent
    source_paths = (
        ('docs/reports/reference/GENERATED_REPORT_SURFACES.md', 'docs/reports/reference/GENERATED_REPORT_SURFACES.md'),
        ('docs/reports/validations/INDEX.md', 'docs/reports/validations/INDEX.md'),
        ('docs/reports/validations/APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md', 'docs/reports/validations/APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md'),
        ('docs/reports/validations/APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html', 'docs/reports/validations/APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html'),
    )
    for source_rel, target_rel in source_paths:
        source_path = source_project_root / source_rel
        target_path = project_root / target_rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)


def _make_temp_observer_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# observerctl anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')
    return project_root, anchor


import contextlib
from unittest.mock import patch

@contextlib.contextmanager
def _bind_temp_observer_project_ctx(monkeypatch, tmp_path):
    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))
    yield project_root

import contextlib
from unittest.mock import patch

@contextlib.contextmanager
def _bind_temp_observer_project_ctx(monkeypatch, tmp_path):
    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))
    yield project_root

def _bind_temp_observer_project(monkeypatch: pytest.MonkeyPatch, project_root: Path, anchor: Path) -> None:
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))


def _seed_librarian_dataset_entry(
    anchor: Path,
    project_root: Path,
    *,
    slug: str,
    display_name: str,
    run_id: str,
    source: str,
    mode: str,
    recorded_at_utc: str,
    workflow: str = 'build',
    registration_kind: str = 'manual-register',
) -> tuple[dict, Path, Path, Path]:
    from calamum_librarian import _build_dataset_entry, _dataset_catalog_paths, _load_dataset_snapshot, _save_dataset_snapshot

    dataset_dir = project_root / 'datasets' / slug
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    entry = _build_dataset_entry(
        anchor,
        manifest_path,
        access_class='local',
        display_name=display_name,
        run_id=run_id,
        workflow=workflow,
        recorded_at_utc=recorded_at_utc,
        registration_kind=registration_kind,
        source=source,
        mode=mode,
        source_binding='{0}:{1}'.format(registration_kind, manifest_path.name),
    )
    paths = _dataset_catalog_paths(anchor)
    existing = _load_dataset_snapshot(paths)
    _save_dataset_snapshot(paths, [entry] + existing)
    return entry, manifest_path, features_csv, labels_csv


def _append_saved_ds_manifest(
    anchor: Path,
    workflow: str,
    run_id: str,
    *,
    timestamp_utc: str,
    artifact_paths: dict[str, Path],
    context: dict | None = None,
    lineage: dict | None = None,
    summary: str = '',
) -> None:
    from analysis.report_aggregate import append_ds_run_index
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    workflow_name = str(workflow).strip().lower()
    command_name = 'run demo' if workflow_name == 'demo' else workflow_name
    action_name = {
        'build': 'ds-build',
        'train': 'ds-train',
        'evaluate': 'ds-evaluate',
        'score': 'ds-score',
        'demo': 'ds-run',
        'pipeline': 'ds-run',
    }.get(workflow_name, 'ds-{0}'.format(workflow_name))
    bundle = prepare_report_bundle(anchor, workflow_name, run_id=run_id)
    report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': timestamp_utc,
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': action_name,
            'command_family': 'ds',
            'command_path': 'observerctl ds {0}'.format(command_name),
            'implementation_state': 'command-available',
            'underlying_surface': 'tests.saved-fixtures',
            'summary': summary or 'Retained DS artifact fixture.',
            'run_id': run_id,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths=artifact_paths,
        context=context or {},
        lineage=lineage or {},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=report_bundle['manifest'])


def _make_ds_records() -> list[dict]:
    records = []
    for i in range(8):
        records.append({
            'timestamp': f'2026-02-10T00:00:{i:02d}Z',
            'type': 'post',
            'author_hash': f'norm{i:012d}',
            'content_length': 10,
            'has_code_block': False,
            'tags_count': 0,
            'mentions_count': 0,
            'f_complexity': 0.1,
            'f_code_density': 0.0,
            'f_toxicity': 0,
            'f_timestamp_epoch': float(i),
            'tv_id': 'TV-0',
        })
    for i in range(4):
        records.append({
            'timestamp': f'2026-02-10T00:01:{i:02d}Z',
            'type': 'post',
            'author_hash': f'bad{i:013d}',
            'content_length': 500,
            'has_code_block': True,
            'tags_count': 1,
            'mentions_count': 1,
            'f_complexity': 0.8,
            'f_code_density': 0.2,
            'f_toxicity': 1,
            'f_timestamp_epoch': float(100 + i),
            'tv_id': 'TV-3',
        })
    return records


def _make_real_tv_review_records() -> list[dict]:
    return [
        {
            'timestamp': '2026-02-10T00:00:00Z',
            'type': 'post',
            'author_hash': 'good' * 4,
            'content_length': 48,
            'content_length_words': 8,
            'has_code_block': False,
            'code_block_count': 0,
            'has_link': False,
            'link_count': 0,
            'tags_count': 0,
            'mentions_count': 0,
            'line_count': 2,
            'question_count': 0,
            'exclamation_count': 0,
            'contains_ignore_previous': False,
            'contains_system_prompt_reference': False,
            'contains_developer_message_reference': False,
            'contains_env_var_reference': False,
            'prompt_injection_score': 0,
            'matched_pattern_count': 0,
            'f_complexity': 0.01,
            'f_code_density': 0.0,
            'f_toxicity': 0,
            'f_timestamp_epoch': 1.0,
        },
        {
            'timestamp': '2026-02-10T00:00:01Z',
            'type': 'post',
            'author_hash': 'risk' * 4,
            'content_length': 220,
            'content_length_words': 30,
            'has_code_block': True,
            'code_block_count': 1,
            'has_link': True,
            'link_count': 1,
            'tags_count': 1,
            'mentions_count': 1,
            'line_count': 6,
            'question_count': 1,
            'exclamation_count': 0,
            'contains_ignore_previous': True,
            'contains_system_prompt_reference': True,
            'contains_developer_message_reference': False,
            'contains_env_var_reference': False,
            'prompt_injection_score': 2,
            'matched_pattern_count': 1,
            'f_complexity': 0.7,
            'f_code_density': 0.3,
            'f_toxicity': 1,
            'f_timestamp_epoch': 2.0,
        },
    ]


def test_observerctl_top_level_help_exposes_ds_namespace(capsys) -> None:
    parser = observerctl_module._build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(['-h'])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert 'ds' in out
    assert 'Data-science operations namespace' in out


def test_ops_keysmith_status_reports_shipped_surfaces(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    _seed_keysmith_surface(project_root)
    monkeypatch.delenv('MOLTBOOK_API_KEY', raising=False)

    rc = main(['ops', 'keysmith', '--json'])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ops-keysmith'
    assert payload['decision'] == 'go'
    assert payload['venue'] == 'moltbook'
    assert payload['live_mint_authority'] == 'sandbox-only'
    assert payload['dry_run_authority'] == 'host-or-sandbox'
    assert payload['live_mint_ready'] is False
    assert payload['surface_status']['src_keysmith_py']['exists'] is True
    assert payload['surface_status']['deployment_keysmith_dockerfile']['exists'] is True
    assert payload['surface_status']['deployment_keysmith_requirements']['exists'] is True
    assert payload['env_presence']['moltbook_api_key'] is False
    assert 'keysmith_allow_unsandboxed' not in payload['env_presence']
    assert payload['artifacts']['default_output_dir'] != ''


def test_ops_runtime_status_returns_enriched_runtime_packet(monkeypatch) -> None:
    monkeypatch.setattr(observerctl_module, '_load_state', lambda: {'source': 'real', 'mode': 'live'})
    monkeypatch.setattr(
        observerctl_module,
        'collect_runtime_status',
        lambda source='real': {
            'checks': {
                'runtime.observer_service': {'state': 'active', 'status': 'ok'},
                'runtime.collection_state': {
                    'state': 'error',
                    'status': 'err',
                    'metrics_age_seconds': None,
                    'collecting_fresh_max_age_seconds': 40.0,
                },
                'runtime.source_fetch': {
                    'status': 'err',
                    'error_kind': 'http_404',
                    'endpoint': 'feed',
                    'recent_error': 'Network error on feed: 404',
                },
                'data.observer_metrics_current': {
                    'path': 'observer_derived/real/live/moltbook_metrics.jsonl',
                    'exists': False,
                },
                'runtime.baseline_monitor': {'state': 'active', 'status': 'ok'},
            }
        },
    )
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_observer_status',
        lambda max_age_sec=60.0: {
            'state': 'active',
            'pid': {'alive': True, 'value': 1234},
            'heartbeat': {'status': 'ok'},
        },
    )

    packet = observerctl_module._ops_runtime_status()

    assert packet['action'] == 'runtime-status'
    assert packet['decision'] == 'no-go'
    assert packet['source'] == 'real'
    assert packet['mode'] == 'live'
    assert packet['collection_state'] == 'error'
    assert packet['source_fetch_status'] == 'err'
    assert packet['source_fetch_error_kind'] == 'http_404'
    assert packet['source_fetch_endpoint'] == 'feed'
    assert 'critical_check_failed:runtime_collection_error' in packet['reason_codes']
    assert 'critical_check_failed:runtime_source_fetch_error' in packet['reason_codes']


def test_ops_runtime_status_human_render_surfaces_route_and_upstream(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, '_load_state', lambda: {'source': 'real', 'mode': 'live'})
    monkeypatch.setattr(
        observerctl_module,
        'collect_runtime_status',
        lambda source='real': {
            'checks': {
                'runtime.observer_service': {'state': 'active', 'status': 'ok'},
                'runtime.collection_state': {
                    'state': 'error',
                    'status': 'err',
                    'metrics_age_seconds': None,
                    'collecting_fresh_max_age_seconds': 40.0,
                },
                'runtime.source_fetch': {
                    'status': 'err',
                    'error_kind': 'http_404',
                    'endpoint': 'feed',
                    'recent_error': 'Network error on feed: 404',
                },
                'data.observer_metrics_current': {
                    'path': 'observer_derived/real/live/moltbook_metrics.jsonl',
                    'exists': False,
                },
                'runtime.baseline_monitor': {'state': 'active', 'status': 'ok'},
            }
        },
    )
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_observer_status',
        lambda max_age_sec=60.0: {
            'state': 'active',
            'pid': {'alive': True, 'value': 1234},
            'heartbeat': {'status': 'ok'},
        },
    )

    rc = main(['ops', 'runtime', 'status'])

    assert rc == 2
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Observer runtime status'
    assert 'Runtime' in rendered
    assert any('Route:' in strip_ansi(line) and 'REAL:LIVE' in strip_ansi(line) for line in rendered)
    assert any('Collection status:' in strip_ansi(line) and 'err' in strip_ansi(line) for line in rendered)
    assert any('Fresh max age s:' in strip_ansi(line) and '40.0' in strip_ansi(line) for line in rendered)
    assert 'Upstream' in rendered
    assert any('Fetch status:' in strip_ansi(line) and 'err' in strip_ansi(line) for line in rendered)
    assert any('Endpoint:' in strip_ansi(line) and 'feed' in strip_ansi(line) for line in rendered)
    assert any('Recent error:' in strip_ansi(line) and 'Network error on feed: 404' in strip_ansi(line) for line in rendered)


def test_ops_runtime_status_human_render_surfaces_healthy_real_fetch_state(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, '_load_state', lambda: {'source': 'real', 'mode': 'live'})
    monkeypatch.setattr(
        observerctl_module,
        'collect_runtime_status',
        lambda source='real': {
            'checks': {
                'runtime.observer_service': {'state': 'active', 'status': 'ok'},
                'runtime.collection_state': {
                    'state': 'collecting',
                    'status': 'ok',
                    'metrics_age_seconds': 0.4,
                    'collecting_fresh_max_age_seconds': 40.0,
                },
                'runtime.source_fetch': {
                    'status': 'ok',
                    'observed': True,
                },
                'data.observer_metrics_current': {
                    'path': 'observer_derived/real/live/moltbook_metrics.jsonl',
                    'exists': True,
                },
                'runtime.baseline_monitor': {'state': 'active', 'status': 'ok'},
            }
        },
    )
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_observer_status',
        lambda max_age_sec=60.0: {
            'state': 'active',
            'pid': {'alive': True, 'value': 1234},
            'heartbeat': {'status': 'ok'},
        },
    )

    rc = main(['ops', 'runtime', 'status'])

    assert rc == 0
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Observer runtime status'
    assert 'Upstream' in rendered
    assert any('Fetch status:' in strip_ansi(line) and 'ok' in strip_ansi(line) for line in rendered)
    assert any('Collection state:' in strip_ansi(line) and 'collecting' in strip_ansi(line) for line in rendered)
    assert any('Collection status:' in strip_ansi(line) and 'ok' in strip_ansi(line) for line in rendered)


def test_ops_bootstrap_creates_frozen_runtime_roots_without_publication_contamination(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    rc = main(['ops', 'bootstrap', '--json'])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ops-bootstrap'
    assert payload['decision'] == 'go'
    assert payload['check_only'] is False
    assert payload['counts']['missing_roots'] == 0
    assert payload['counts']['blocked_roots'] == 0
    assert payload['counts']['created_roots'] > 0

    status_by_id = {row['id']: row['status'] for row in payload['roots']}
    for root_id in (
        'analysis_root',
        'analysis_runs_root',
        'analysis_indexes_root',
        'analysis_drafts_root',
        'librarian_authority_root',
        'librarian_history_root',
        'librarian_delegated_access_root',
        'librarian_integrity_root',
        'librarian_quarantine_root',
        'reports_operations_root',
        'reports_ops_parameters_root',
        'reports_queststack_root',
        'reports_package_root',
        'reports_user_root',
        'keysmith_exports_root',
        'scheduler_root',
        'locks_root',
        'observerctl_root',
    ):
        assert status_by_id[root_id] in ('created', 'ready')

    assert (project_root / 'local_untracked' / 'analysis').is_dir()
    assert (project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'authority').is_dir()
    assert (project_root / 'local_untracked' / 'reports' / 'operations').is_dir()
    assert (project_root / 'local_untracked' / 'reports' / 'ops_parameters').is_dir()
    assert (project_root / 'local_untracked' / 'reports' / 'package').is_dir()
    assert (project_root / 'local_untracked' / 'reports' / 'user').is_dir()
    assert (project_root / 'local_untracked' / 'keysmith_exports').is_dir()
    assert (project_root / 'local_untracked' / 'scheduler').is_dir()
    assert (project_root / 'local_untracked' / 'locks').is_dir()
    assert (project_root / 'local_untracked' / 'observerctl').is_dir()
    assert (project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'integrity' / 'vault_control_state.json').exists()
    assert (project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'integrity' / 'vault_checksum.json').exists()
    assert not (project_root / 'docs' / 'reports').exists()


def test_ops_bootstrap_check_is_non_mutating_and_fails_closed_when_roots_are_missing(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    rc = main(['ops', 'bootstrap', '--check', '--json'])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ops-bootstrap'
    assert payload['decision'] == 'no-go'
    assert payload['check_only'] is True
    assert payload['counts']['created_roots'] == 0
    assert payload['counts']['missing_roots'] > 0
    assert (project_root / 'local_untracked').exists() is False
    assert not (project_root / 'docs' / 'reports').exists()


def test_ops_bootstrap_human_render_uses_sectioned_packet_layout(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    rc = main(['ops', 'bootstrap'])

    assert rc == 0
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Observer runtime bootstrap'
    assert 'Summary' in rendered
    assert 'Created roots' in rendered
    assert 'Evidence' in rendered
    assert 'Guidance' in rendered
    assert any('Mode:' in strip_ansi(line) and 'create-validate' in strip_ansi(line) for line in rendered)


def test_ops_keysmith_mint_dry_run_delegates_and_keeps_output_names_only(tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / 'keysmith_exports'

    rc = main(['ops', 'keysmith', 'mint', '--dry-run', '--output-dir', str(out_dir), '--json'])

    assert rc == 0
    out = capsys.readouterr().out
    assert 'DRY_RUN_PLACEHOLDER_DO_NOT_USE' not in out
    assert 'https://moltbook.com/claim/' not in out
    payload = json.loads(out)
    assert payload['action'] == 'ops-keysmith-mint'
    assert payload['decision'] == 'go'
    assert payload['venue'] == 'moltbook'
    assert payload['dry_run'] is True
    assert Path(payload['claim_url_path']).exists()
    assert Path(payload['sealed_drop_path']).exists()
    assert Path(payload['audit_path']).exists()
    assert Path(payload['result_json']).exists()
    assert Path(payload['import_helper_path']).exists()
    assert Path(payload['persist_user_env_helper_path']).exists()


def test_project_dotenv_loads_missing_env_without_overriding_existing(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'project'
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / '.env').write_text(
        '# local env\nCALAMUM_DATA_SIGNING_KEY=dotenv-signing-key\nMOLTBOOK_API_KEY=dotenv-molt-key\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.delenv('CALAMUM_DATA_SIGNING_KEY', raising=False)
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'existing-key')

    result = observerctl_module._load_project_dotenv()

    assert result['exists'] is True
    assert 'CALAMUM_DATA_SIGNING_KEY' in result['loaded_names']
    assert os.environ.get('CALAMUM_DATA_SIGNING_KEY') == 'dotenv-signing-key'
    assert os.environ.get('MOLTBOOK_API_KEY') == 'existing-key'


def test_project_dotenv_does_not_autoload_route_authority_env(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'project'
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / '.env').write_text(
        'CALAMUM_DATA_SIGNING_KEY=dotenv-signing-key\n'
        'CALAMUM_MOLTBOOK_SOURCE=real\n'
        'CALAMUM_OPS_MODE=canary\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.delenv('CALAMUM_DATA_SIGNING_KEY', raising=False)
    monkeypatch.delenv('CALAMUM_MOLTBOOK_SOURCE', raising=False)
    monkeypatch.delenv('CALAMUM_OPS_MODE', raising=False)

    result = observerctl_module._load_project_dotenv()

    assert 'CALAMUM_DATA_SIGNING_KEY' in result['loaded_names']
    assert 'CALAMUM_MOLTBOOK_SOURCE' not in result['loaded_names']
    assert 'CALAMUM_OPS_MODE' not in result['loaded_names']
    assert os.environ.get('CALAMUM_DATA_SIGNING_KEY') == 'dotenv-signing-key'
    assert not os.environ.get('CALAMUM_MOLTBOOK_SOURCE')
    assert not os.environ.get('CALAMUM_OPS_MODE')


def test_keysmith_env_import_defaults_to_current_process_only(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'project'
    project_root.mkdir(parents=True, exist_ok=True)
    env_path = project_root / '.env'
    env_path.write_text('MOLTBOOK_API_KEY=\n', encoding='utf-8')
    sealed_drop = tmp_path / 'sealed_drop.bin'
    sealed_drop.write_text('unit-test-live-key', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.delenv('MOLTBOOK_API_KEY', raising=False)

    result = observerctl_module._hydrate_moltbook_key_from_sealed_drop(sealed_drop)

    assert result['present'] is True
    assert result['current_process'] is True
    assert result['project_env_updated'] is False
    assert result['user_env_persisted'] is False
    assert os.environ.get('MOLTBOOK_API_KEY') == 'unit-test-live-key'
    assert env_path.read_text(encoding='utf-8') == 'MOLTBOOK_API_KEY=\n'


def test_ops_keysmith_mint_non_dry_run_requires_sandbox(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv('KEYSMITH_SANDBOX', raising=False)
    monkeypatch.delenv('KEYSMITH_ALLOW_UNSANDBOXED', raising=False)
    runner_path = tmp_path / 'Invoke-KeysmithSandbox.ps1'
    runner_path.write_text('# runner\n', encoding='utf-8')
    captured_imports: list[Path] = []

    monkeypatch.setattr(observerctl_module, '_keysmith_shell_path', lambda: 'powershell.exe')
    monkeypatch.setattr(observerctl_module, '_keysmith_sandbox_runner_path', lambda: runner_path)

    def _fake_hydrate(path):
        captured_imports.append(Path(path))
        return {
            'sealed_drop_path': str(path),
            'present': True,
            'current_process': True,
            'project_env_updated': False,
            'user_env_persisted': False,
        }

    monkeypatch.setattr(observerctl_module, '_hydrate_moltbook_key_from_sealed_drop', _fake_hydrate)

    def _fake_run(*args, **kwargs):
        out_dir = tmp_path / 'live_keysmith'
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            'claim_url.txt',
            'sealed_drop.bin',
            'Import-MoltbookApiKeyFromSealedDrop.ps1',
            'Persist-MoltbookApiKeyToUserEnv.ps1',
            'keysmith_audit.jsonl',
            'keysmith_result.json',
        ):
            (out_dir / name).write_text('ok\n', encoding='utf-8')

        class _Completed:
            returncode = 0
            stdout = ''
            stderr = ''

        return _Completed()

    monkeypatch.setattr(observerctl_module.subprocess, 'run', _fake_run)

    rc = main(['ops', 'keysmith', 'mint', '--output-dir', str(tmp_path / 'live_keysmith'), '--json'])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ops-keysmith-mint'
    assert payload['decision'] == 'go'
    assert payload['execution_lane'] == 'sandbox-runner'
    assert payload['sandbox'] is True
    assert Path(payload['claim_url_path']).exists()
    assert Path(payload['sealed_drop_path']).exists()
    assert Path(payload['import_helper_path']).exists()
    assert Path(payload['persist_user_env_helper_path']).exists()
    assert payload['env_import']['current_process'] is True
    assert payload['env_import']['project_env_updated'] is False
    assert payload['env_import']['user_env_persisted'] is False
    assert captured_imports == [Path(payload['sealed_drop_path'])]


def test_ops_keysmith_mint_non_dry_run_reports_docker_lane_blocker(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv('KEYSMITH_SANDBOX', raising=False)
    runner_path = tmp_path / 'Invoke-KeysmithSandbox.ps1'
    runner_path.write_text('# runner\n', encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_keysmith_shell_path', lambda: 'powershell.exe')
    monkeypatch.setattr(observerctl_module, '_keysmith_sandbox_runner_path', lambda: runner_path)
    monkeypatch.setattr(observerctl_module.shutil, 'which', lambda name: '' if name == 'docker' else 'powershell.exe')

    def _fake_run(*args, **kwargs):
        class _Completed:
            returncode = 1
            stdout = ''
            stderr = 'docker build failed'

        return _Completed()

    monkeypatch.setattr(observerctl_module.subprocess, 'run', _fake_run)

    rc = main(['ops', 'keysmith', 'mint', '--output-dir', str(tmp_path / 'live_keysmith'), '--json'])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ops-keysmith-mint'
    assert payload['decision'] == 'no-go'
    assert 'critical_check_failed:docker_missing' in payload['reason_codes']
    assert 'docker' in payload['summary'].lower()


def test_ops_keysmith_mint_non_dry_run_reports_vendor_rate_limit(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv('KEYSMITH_SANDBOX', raising=False)
    runner_path = tmp_path / 'Invoke-KeysmithSandbox.ps1'
    runner_path.write_text('# runner\n', encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_keysmith_shell_path', lambda: 'powershell.exe')
    monkeypatch.setattr(observerctl_module, '_keysmith_sandbox_runner_path', lambda: runner_path)
    monkeypatch.setattr(observerctl_module.shutil, 'which', lambda name: 'docker.exe' if name == 'docker' else 'powershell.exe')

    def _fake_run(*args, **kwargs):
        class _Completed:
            returncode = 1
            stdout = ''
            stderr = 'Registration request failed: url=https://www.moltbook.com/api/v1/agents/register status_code=429'

        return _Completed()

    monkeypatch.setattr(observerctl_module.subprocess, 'run', _fake_run)

    rc = main(['ops', 'keysmith', 'mint', '--output-dir', str(tmp_path / 'live_keysmith'), '--json'])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ops-keysmith-mint'
    assert payload['decision'] == 'no-go'
    assert 'environment_blocked:moltbook_rate_limited' in payload['reason_codes']
    assert 'rate limit' in payload['summary'].lower()


def test_ops_keysmith_status_human_render_uses_sectioned_operator_layout(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    _seed_keysmith_surface(project_root)
    monkeypatch.delenv('KEYSMITH_SANDBOX', raising=False)
    monkeypatch.delenv('MOLTBOOK_API_KEY', raising=False)

    rc = main(['ops', 'keysmith'])

    assert rc == 0
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'ObserverCTL KEYSMITH'
    assert 'Summary' in rendered
    assert 'Evidence' in rendered
    assert 'Guidance' in rendered
    assert any('Live mint authority:' in line and 'sandbox-only' in line for line in rendered)
    assert any('observerctl ops keysmith mint' in line for line in rendered)


def test_ops_keysmith_mint_human_denial_requires_container_lane(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.delenv('KEYSMITH_SANDBOX', raising=False)
    monkeypatch.delenv('KEYSMITH_ALLOW_UNSANDBOXED', raising=False)

    rc = main(['ops', 'keysmith', 'mint', '--output-dir', str(tmp_path / 'live_keysmith')])

    assert rc == 2
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'ObserverCTL KEYSMITH mint'
    assert 'Reasons' in rendered
    assert 'Guidance' in rendered
    assert any('sandbox/container lane' in line for line in rendered)


def test_ops_keysmith_mint_human_dry_run_stays_names_only(tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / 'keysmith_exports'

    rc = main(['ops', 'keysmith', 'mint', '--dry-run', '--output-dir', str(out_dir)])

    assert rc == 0
    rendered = capsys.readouterr().out
    assert 'ObserverCTL KEYSMITH mint' in rendered
    assert 'Summary' in rendered
    assert 'Evidence' in rendered
    assert 'Guidance' in rendered
    assert 'https://moltbook.com/claim/' not in rendered
    assert 'DRY_RUN_PLACEHOLDER_DO_NOT_USE' not in rendered


def test_ops_keysmith_unsupported_venue_fails_closed(capsys) -> None:
    rc = main(['ops', 'keysmith', '--venue', 'otherbook', '--json'])

    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ops-keysmith'
    assert payload['decision'] == 'no-go'
    assert payload['venue'] == 'otherbook'
    assert 'policy_denied:keysmith_venue_unsupported' in payload['reason_codes']


def test_observerctl_ds_help_exposes_frame1_command_family(capsys) -> None:
    parser = observerctl_module._build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(['ds', '-h'])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert 'build' in out
    assert 'train' in out
    assert 'evaluate' in out
    assert 'score' in out
    assert 'saved' in out
    assert 'run' in out
    assert 'wizard' in out
    assert '==SUPPRESS==' not in out
    assert 'runs' not in out
    assert 'baselines' not in out
    assert 'drafts' not in out


def test_observerctl_ds_saved_help_exposes_selector_families(capsys) -> None:
    parser = observerctl_module._build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(['ds', 'saved', '-h'])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert 'trained' in out
    assert 'runs' in out
    assert 'baselines' in out
    assert 'drafts' in out


def test_observerctl_ds_evaluate_help_preserves_direct_surface(capsys) -> None:
    parser = observerctl_module._build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(['ds', 'evaluate', '-h'])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert '--features-csv' in out
    assert '--labels-csv' in out
    assert '--dataset-manifest' in out
    assert '--model-path' in out
    assert '--max-fpr' in out
    assert '--baseline-analysis' not in out
    assert 'baseline_analysis_packet' not in out
    assert 'baseline_window_id' not in out


def test_observerctl_ds_wizard_help_preserves_baseline_hydration_surface(capsys) -> None:
    parser = observerctl_module._build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(['ds', 'wizard', '-h'])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert '--hydrate-baseline-analysis' in out
    assert '--hydrate-latest-context' in out
    assert '--workflow' in out
    assert 'build' in out
    assert 'train' in out
    assert 'evaluate' in out
    assert 'score' in out
    assert 'run-pipeline' in out


def test_ds_wizard_emits_frame4_shell_packet_with_workflow_filtering(capsys) -> None:
    rc = main(['ds', 'wizard', '--workflow', 'run-pipeline', '--json'])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['decision'] == 'go'
    assert payload['action'] == 'ds-wizard'
    assert payload['command_family'] == 'ds'
    assert payload['command_path'] == 'observerctl ds wizard'
    assert payload['implementation_state'] == 'wizard-available'
    assert 'delivery_frame' not in payload
    assert payload['workflow'] == 'run-pipeline'
    assert payload['current_page'] == 'landing'
    assert 'flow' in payload['visible_sections']
    assert 'in' not in payload['visible_sections']
    assert 'eval' not in payload['visible_sections']
    assert 'report' in payload['visible_sections']
    assert 'out' not in payload['visible_sections']
    assert payload['execution_state'] == 'blocked'
    assert 'home:' in payload['wizard_view']
    assert 'sections: flow, in, model, eval, report, cmd, check, run, exit' not in payload['wizard_view']


def test_ds_wizard_state_persists_across_section_navigation() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')
    observerctl_module._ds_wizard_set_value(state, 'input_paths', ['alpha.jsonl'])

    observerctl_module._ds_wizard_open_section(state, 'report')
    observerctl_module._ds_wizard_move_section(state, 'next')
    observerctl_module._ds_wizard_move_section(state, 'prev')

    assert state.active_section == 'report'
    assert state.active_page == 'configure'
    assert state.active_group == 'eval-report'
    assert state.values['input_paths'] == ['alpha.jsonl']


def test_ds_wizard_filters_sections_by_workflow() -> None:
    build_state = observerctl_module._ds_wizard_new_state('build')
    pipeline_state = observerctl_module._ds_wizard_new_state('run-pipeline')

    build_sections = observerctl_module._ds_wizard_visible_sections(build_state)
    pipeline_sections = observerctl_module._ds_wizard_visible_sections(pipeline_state)

    assert 'eval' not in build_sections
    assert 'report' in build_sections
    assert 'in' not in pipeline_sections
    assert 'model' not in pipeline_sections


def test_ds_wizard_workflow_sections_structural_constraints() -> None:
    train_sections = observerctl_module._ds_wizard_visible_sections(
        observerctl_module._ds_wizard_new_state('train'))
    build_sections = observerctl_module._ds_wizard_visible_sections(
        observerctl_module._ds_wizard_new_state('build'))
    eval_sections = observerctl_module._ds_wizard_visible_sections(
        observerctl_module._ds_wizard_new_state('evaluate'))
    score_sections = observerctl_module._ds_wizard_visible_sections(
        observerctl_module._ds_wizard_new_state('score'))
    pipeline_sections = observerctl_module._ds_wizard_visible_sections(
        observerctl_module._ds_wizard_new_state('run-pipeline'))

    # eval present only in evaluate
    for sections in (eval_sections,):
        assert 'eval' in sections
    for sections in (build_sections, train_sections, score_sections, pipeline_sections):
        assert 'eval' not in sections

    # report present in all workflows; out has been retired from visible navigation
    for sections in (build_sections, train_sections, eval_sections,
                     score_sections, pipeline_sections):
        assert 'report' in sections
        assert 'out' not in sections

    # in now stays only in build
    for sections in (build_sections,):
        assert 'in' in sections
    for sections in (train_sections, eval_sections, score_sections, pipeline_sections):
        assert 'in' not in sections


def test_ds_wizard_hydrates_saved_artifacts(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(tmp_path / 'features.csv'),
        'labels_csv': str(tmp_path / 'labels.csv'),
    }), encoding='utf-8')
    (tmp_path / 'features.csv').write_text('record_id\n', encoding='utf-8')
    (tmp_path / 'labels.csv').write_text('record_id,label\n', encoding='utf-8')

    train_manifest = tmp_path / 'train_manifest.json'
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(tmp_path / 'model.pkl'),
        'model_type': 'unsupervised',
    }), encoding='utf-8')
    (tmp_path / 'model.pkl').write_bytes(b'model')

    baseline_packet = tmp_path / 'baseline.json'
    baseline_packet.write_text(json.dumps({'baseline_window_id': 'frame4-window'}), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('score')
    observerctl_module._ds_wizard_hydrate_dataset_manifest(state, dataset_manifest)
    observerctl_module._ds_wizard_hydrate_train_manifest(state, train_manifest)
    observerctl_module._ds_wizard_hydrate_baseline_analysis(state, baseline_packet)

    assert state.values['dataset_manifest'] == str(dataset_manifest)
    assert state.values['features_csv'] == str(tmp_path / 'features.csv')
    assert state.values['model_path'] == str(tmp_path / 'model.pkl')
    assert state.values['model_type'] == 'unsupervised'
    assert state.values['baseline_window_id'] == 'frame4-window'


def test_ds_wizard_hydrate_train_manifest_prefers_librarian_alias_api(monkeypatch, tmp_path: Path) -> None:
    from calamum_librarian import register_librarian_dataset_packet
    import analysis.report_pack as report_pack_module

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    dataset_manifest = tmp_path / 'dataset_manifest.json'
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(tmp_path / 'features.csv'),
        'labels_csv': str(tmp_path / 'labels.csv'),
        'inputs': [
            {
                'path': str(project_root / 'logs' / 'data' / 'calamum' / 'archive' / 'resource_real_canary_fixture_train_alias_seg0001.jsonl.gz'),
                'records': 1,
            },
        ],
    }), encoding='utf-8')
    (tmp_path / 'features.csv').write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    (tmp_path / 'labels.csv').write_text('record_id,label\n1,1\n', encoding='utf-8')
    (tmp_path / 'model.pkl').write_bytes(b'model')

    dataset_packet = register_librarian_dataset_packet(
        anchor,
        dataset_manifest,
        access_class='local',
        display_name='Train Alias Authority',
        run_id='train-alias-authority',
    )
    expected_alias = str(dataset_packet['dataset']['display_alias'])

    train_manifest = tmp_path / 'train_manifest.json'
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(tmp_path / 'model.pkl'),
        'model_type': 'unsupervised',
    }), encoding='utf-8')

    def _unexpected_report_pack_fallback(*args, **kwargs):
        raise AssertionError('report-pack fallback should not be required when the Librarian API can answer authoritatively')

    monkeypatch.setattr(report_pack_module, 'resolve_collection_alias', _unexpected_report_pack_fallback)

    state = observerctl_module._ds_wizard_new_state('evaluate')
    state = observerctl_module._ds_wizard_hydrate_train_manifest(state, train_manifest)

    assert state.values['dataset_alias'] == expected_alias
    assert state.hydrated_from['dataset_alias'] == 'train_manifest'


def test_ds_comparison_baseline_packet_emission_uses_selector_backed_reviewed_authority(monkeypatch, tmp_path: Path) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    entry, manifest_path, features_csv, labels_csv = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_baseline_window1',
        display_name='Reviewed Baseline Window1',
        run_id='reviewed-baseline-window1',
        source='real',
        mode='honeypot',
        recorded_at_utc='2026-04-13T00:00:00Z',
    )
    review_policy_packet = project_root / 'local_untracked' / 'reports' / 'review_policy_packet.md'
    review_policy_packet.parent.mkdir(parents=True, exist_ok=True)
    review_policy_packet.write_text('# review policy\n', encoding='utf-8')

    emitted = observerctl_module._ds_emit_comparison_baseline_packet(
        entry,
        baseline_stage='honeypot_reviewed',
        companion_role='bounded cursory reviewed tv_id companion',
        review_policy_packet=str(review_policy_packet),
    )

    packet_path = _resolve_reported_path(emitted['packet_path'])
    payload = json.loads(packet_path.read_text(encoding='utf-8'))

    assert packet_path.exists()
    assert payload['artifact_family'] == 'ds_comparison_baseline'
    assert payload['baseline_window_id'] == 'reviewed-baseline-window1'
    assert payload['baseline_stage'] == 'honeypot_reviewed'
    assert payload['selector_entry_id'] == entry['entry_id']
    assert payload['selector_run_id'] == entry['run_id']
    assert payload['dataset_manifest_path'] == observerctl_module.normalize_repo_or_absolute_path(manifest_path, project_root)
    assert payload['features_csv_path'] == observerctl_module.normalize_repo_or_absolute_path(features_csv, project_root)
    assert payload['labels_csv_path'] == observerctl_module.normalize_repo_or_absolute_path(labels_csv, project_root)
    assert payload['review_policy_packet'] == observerctl_module.normalize_repo_or_absolute_path(review_policy_packet, project_root)
    assert payload['record_count'] == 1
    assert payload['has_labels'] is True
    assert payload['packet_path'].endswith('comparison_baseline_packet.json')


def test_ds_comparison_baseline_resolver_recovers_selector_view_and_resolves_existing_packet(monkeypatch, tmp_path: Path) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_resolver_window1',
        display_name='Reviewed Resolver Window1',
        run_id='reviewed-resolver-window1',
        source='real',
        mode='honeypot',
        recorded_at_utc='2026-04-13T00:05:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    review_policy_packet = project_root / 'local_untracked' / 'reports' / 'resolver_review_policy_packet.md'
    review_policy_packet.parent.mkdir(parents=True, exist_ok=True)
    review_policy_packet.write_text('# resolver review policy\n', encoding='utf-8')

    emitted = observerctl_module._ds_emit_comparison_baseline_packet(
        entry,
        baseline_stage='honeypot_reviewed',
        companion_role='bounded reviewed resolver companion',
        review_policy_packet=str(review_policy_packet),
    )

    selector_view = observerctl_module._ds_selector_entry_view(entry)
    resolved_path = observerctl_module._ds_resolve_comparison_baseline_packet(selector_view)

    assert selector_view['comparison_baseline_stage'] == 'honeypot_reviewed'
    assert observerctl_module._ds_is_eligible_comparison_baseline(selector_view) is True
    assert observerctl_module._ds_comparison_baseline_stage(selector_view) == 'honeypot_reviewed'
    assert resolved_path == _resolve_reported_path(emitted['packet_path'])


def test_ds_comparison_baseline_resolver_can_emit_missing_packet_for_explicit_reviewed_authority(monkeypatch, tmp_path: Path) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_emit_window1',
        display_name='Reviewed Emit Window1',
        run_id='reviewed-emit-window1',
        source='real',
        mode='honeypot',
        recorded_at_utc='2026-04-13T00:10:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    review_policy_packet = project_root / 'local_untracked' / 'reports' / 'emit_review_policy_packet.md'
    review_policy_packet.parent.mkdir(parents=True, exist_ok=True)
    review_policy_packet.write_text('# emit review policy\n', encoding='utf-8')

    selector_view = observerctl_module._ds_selector_entry_view(entry)
    resolved_path = observerctl_module._ds_resolve_comparison_baseline_packet(
        selector_view,
        emit_if_missing=True,
        companion_role='bounded reviewed emit companion',
        review_policy_packet=str(review_policy_packet),
    )

    assert resolved_path is not None
    assert resolved_path.exists()
    payload = json.loads(resolved_path.read_text(encoding='utf-8'))
    assert payload['artifact_family'] == 'ds_comparison_baseline'
    assert payload['selector_entry_id'] == entry['entry_id']
    assert payload['selector_run_id'] == entry['run_id']
    assert payload['baseline_stage'] == 'honeypot_reviewed'


def test_ds_comparison_baseline_eligibility_fails_closed_for_nonreviewed_or_unlabeled_entries(monkeypatch, tmp_path: Path) -> None:
    from calamum_librarian import _build_dataset_entry, _dataset_catalog_paths, _load_dataset_snapshot, _save_dataset_snapshot

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    nonreviewed_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='live_labeled_alpha',
        display_name='Live Labeled Alpha',
        run_id='live-labeled-alpha',
        source='real',
        mode='live',
        recorded_at_utc='2026-04-13T00:15:00Z',
        workflow='manual-register',
    )

    manual_named_reviewed_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='manual_named_reviewed_alpha',
        display_name='Reviewed Honeypot Manual Alpha',
        run_id='reviewed-honeypot-manual-alpha',
        source='real',
        mode='honeypot',
        recorded_at_utc='2026-04-13T00:17:00Z',
        workflow='manual-register',
    )

    unlabeled_dir = project_root / 'datasets' / 'reviewed_unlabeled_alpha'
    unlabeled_dir.mkdir(parents=True, exist_ok=True)
    unlabeled_manifest = unlabeled_dir / 'dataset_manifest.json'
    unlabeled_features = unlabeled_dir / 'features.csv'
    unlabeled_features.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    unlabeled_manifest.write_text(json.dumps({
        'features_csv': str(unlabeled_features),
        'total_records': 1,
        'has_labels': False,
    }), encoding='utf-8')
    unlabeled_entry = _build_dataset_entry(
        anchor,
        unlabeled_manifest,
        access_class='local',
        display_name='Reviewed Honeypot Unlabeled Alpha',
        run_id='reviewed-honeypot-unlabeled-alpha',
        workflow='manual-register',
        recorded_at_utc='2026-04-13T00:20:00Z',
        registration_kind='reviewed-closeout',
        source='real',
        mode='honeypot',
        source_binding='reviewed-closeout:dataset_manifest.json',
    )
    paths = _dataset_catalog_paths(anchor)
    existing = _load_dataset_snapshot(paths)
    _save_dataset_snapshot(paths, [unlabeled_entry] + existing)

    assert observerctl_module._ds_comparison_baseline_stage(nonreviewed_entry) == 'live_reviewed'
    assert observerctl_module._ds_is_eligible_comparison_baseline(nonreviewed_entry) is True

    assert observerctl_module._ds_comparison_baseline_stage(manual_named_reviewed_entry) == 'honeypot_reviewed'
    assert observerctl_module._ds_is_eligible_comparison_baseline(manual_named_reviewed_entry) is True

    assert unlabeled_entry['comparison_baseline_stage'] == 'honeypot_reviewed'
    assert observerctl_module._ds_comparison_baseline_stage(unlabeled_entry) == 'honeypot_reviewed'
    assert observerctl_module._ds_is_eligible_comparison_baseline(unlabeled_entry) is True
    assert observerctl_module._ds_resolve_comparison_baseline_packet(unlabeled_entry) is None


def test_ds_wizard_train_hydration_refreshes_stale_dataset_adjacent_paths(tmp_path: Path) -> None:
    stale_manifest = tmp_path / 'stale_dataset_manifest.json'
    stale_features = tmp_path / 'stale_features.csv'
    stale_labels = tmp_path / 'stale_labels.csv'
    fresh_manifest = tmp_path / 'fresh_dataset_manifest.json'
    fresh_features = tmp_path / 'fresh_features.csv'
    fresh_labels = tmp_path / 'fresh_labels.csv'
    train_manifest = tmp_path / 'fresh_train_manifest.json'
    model_path = tmp_path / 'model.pkl'

    stale_features.write_text('record_id,feature\na,0.1\n', encoding='utf-8')
    stale_labels.write_text('record_id,label\na,TV-0\n', encoding='utf-8')
    fresh_features.write_text('record_id,feature\nb,0.9\n', encoding='utf-8')
    fresh_labels.write_text('record_id,label\nb,TV-3\n', encoding='utf-8')
    stale_manifest.write_text(json.dumps({'features_csv': str(stale_features), 'labels_csv': str(stale_labels)}), encoding='utf-8')
    fresh_manifest.write_text(json.dumps({'features_csv': str(fresh_features), 'labels_csv': str(fresh_labels)}), encoding='utf-8')
    model_path.write_bytes(b'model')
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(fresh_manifest),
        'model_path': str(model_path),
        'model_type': 'unsupervised',
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_hydrate_dataset_manifest(state, stale_manifest)
    observerctl_module._ds_wizard_hydrate_train_manifest(state, train_manifest)

    assert state.values['dataset_manifest'] == str(fresh_manifest)
    assert state.values['features_csv'] == str(fresh_features)
    assert state.values['labels_csv'] == str(fresh_labels)
    assert state.values['model_path'] == str(model_path)
    assert state.hydrated_from['dataset_manifest'] == 'train_manifest'
    assert state.hydrated_from['features_csv'] == 'train_manifest'
    assert state.hydrated_from['labels_csv'] == 'train_manifest'


def test_ds_wizard_cli_hydration_packet_reports_ready_state_and_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    _set_signing_env(monkeypatch)

    dataset_manifest = tmp_path / 'dataset_manifest.json'
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    train_manifest = tmp_path / 'train_manifest.json'
    model_path = tmp_path / 'model.pkl'
    baseline_packet = tmp_path / 'baseline.json'

    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
    }), encoding='utf-8')
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(model_path),
        'model_type': 'unsupervised',
    }), encoding='utf-8')
    baseline_packet.write_text(json.dumps({'baseline_window_id': 'frame4-window'}), encoding='utf-8')

    dataset_packet = register_librarian_dataset_packet(
        anchor,
        dataset_manifest,
        access_class='local',
        display_name='Frame 4 Wizard Hydration',
        run_id='frame4-hydration',
    )

    assert dataset_packet['decision'] == 'go'

    rc = main([
        'ds',
        'wizard',
        '--workflow',
        'evaluate',
        '--hydrate-dataset',
        '1',
        '--hydrate-train',
        str(train_manifest),
        '--hydrate-baseline-analysis',
        str(baseline_packet),
        '--section',
        'report',
        '--json',
    ])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload['decision'] == 'go'
    assert payload['execution_state'] == 'ready'
    assert payload['current_section'] == 'report'
    assert payload['validation_issues'] == []
    assert payload['artifacts']['dataset_manifest'] == str(dataset_manifest)
    assert payload['artifacts']['train_manifest'] == str(train_manifest)
    assert payload['artifacts']['model_path'] == str(model_path)
    assert payload['artifacts']['baseline_analysis_packet'] == str(baseline_packet)
    assert payload['hydrated_from']['baseline_window_id'] == 'baseline_analysis'
    assert any(dataset_manifest.name in line for line in payload['wizard_view'])
    assert any(train_manifest.name in line for line in payload['wizard_view'])
    assert any(model_path.name in line for line in payload['wizard_view'])
    assert any('run.json' in line for line in payload['wizard_view'])


def test_ds_wizard_cli_train_hydration_refreshes_cross_wired_dataset_paths(tmp_path: Path, monkeypatch, capsys) -> None:
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    _set_signing_env(monkeypatch)

    stale_manifest = tmp_path / 'stale_dataset_manifest.json'
    stale_features = tmp_path / 'stale_features.csv'
    stale_labels = tmp_path / 'stale_labels.csv'
    fresh_manifest = tmp_path / 'fresh_dataset_manifest.json'
    fresh_features = tmp_path / 'fresh_features.csv'
    fresh_labels = tmp_path / 'fresh_labels.csv'
    train_manifest = tmp_path / 'fresh_train_manifest.json'
    model_path = tmp_path / 'model.pkl'

    stale_features.write_text('record_id,feature\na,0.1\n', encoding='utf-8')
    stale_labels.write_text('record_id,label\na,TV-0\n', encoding='utf-8')
    fresh_features.write_text('record_id,feature\nb,0.9\n', encoding='utf-8')
    fresh_labels.write_text('record_id,label\nb,TV-3\n', encoding='utf-8')
    stale_manifest.write_text(json.dumps({'features_csv': str(stale_features), 'labels_csv': str(stale_labels)}), encoding='utf-8')
    fresh_manifest.write_text(json.dumps({'features_csv': str(fresh_features), 'labels_csv': str(fresh_labels)}), encoding='utf-8')
    model_path.write_bytes(b'model')
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(fresh_manifest),
        'model_path': str(model_path),
        'model_type': 'unsupervised',
    }), encoding='utf-8')

    register_librarian_dataset_packet(
        anchor,
        stale_manifest,
        access_class='local',
        display_name='Stale Alpha',
        run_id='stale-alpha',
    )

    rc = main([
        'ds',
        'wizard',
        '--workflow',
        'evaluate',
        '--hydrate-dataset',
        '1',
        '--hydrate-train',
        str(train_manifest),
        '--section',
        'report',
        '--json',
    ])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload['decision'] == 'go'
    assert payload['execution_state'] == 'ready'
    assert payload['artifacts']['dataset_manifest'] == str(fresh_manifest)
    assert str(fresh_features) in payload['command_preview']
    assert str(fresh_labels) in payload['command_preview']
    assert str(stale_features) not in payload['command_preview']
    assert str(stale_labels) not in payload['command_preview']


def test_ds_wizard_cli_labeled_eval_with_label_column_stays_labeled(tmp_path: Path, monkeypatch, capsys) -> None:
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    _set_signing_env(monkeypatch)

    dataset_dir = project_root / 'datasets' / 'labeled_contract'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    splits_csv = dataset_dir / 'splits.csv'

    features_csv.write_text(
        'record_id,feature\nr1,0.0\nr2,0.1\nr3,0.9\nr4,1.0\n',
        encoding='utf-8',
    )
    labels_csv.write_text(
        'record_id,label\nr1,TV-0\nr2,TV-0\nr3,TV-3\nr4,TV-3\n',
        encoding='utf-8',
    )
    splits_csv.write_text(
        'record_id,split\nr1,train\nr2,val\nr3,train\nr4,val\n',
        encoding='utf-8',
    )
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'splits_csv': str(splits_csv),
        'feature_columns': ['feature'],
        'total_records': 4,
        'has_labels': True,
    }), encoding='utf-8')

    register_librarian_dataset_packet(
        anchor,
        dataset_manifest,
        access_class='local',
        display_name='Label Column Dataset',
        run_id='label-column-dataset',
    )

    train_packet = observerctl_module._ds_train(
        dataset=str(dataset_manifest),
        out_dir='',
        model_type='supervised',
        seed=42,
    )
    train_manifest = _resolve_reported_path(train_packet['artifacts']['train_manifest'])

    rc = main([
        'ds',
        'wizard',
        '--workflow',
        'evaluate',
        '--hydrate-dataset',
        '1',
        '--hydrate-train',
        str(train_manifest),
        '--execute',
        '--json',
    ])
    payload = json.loads(capsys.readouterr().out)
    run_json = json.loads(_resolve_reported_path(payload['artifacts']['run_json']).read_text(encoding='utf-8'))

    assert rc == 0
    assert payload['decision'] == 'go'
    assert payload['has_labels'] is True
    assert run_json['evaluation']['has_labels'] is True
    assert run_json['evaluation']['thresholding'] == 'fpr_constrained_best_f1'
    assert run_json['data']['labels_csv'] == str(labels_csv)


def test_ds_wizard_cli_hydrate_latest_context_keeps_missing_dataset_truthful(monkeypatch, tmp_path: Path, capsys) -> None:
    baseline_packet = tmp_path / 'baseline.json'
    baseline_packet.write_text(json.dumps({'baseline_window_id': 'frame4-window'}), encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_load_state', lambda: {'source': 'real', 'mode': 'canary'})
    monkeypatch.setattr(observerctl_module, '_ds_wizard_latest_baseline_analysis_path', lambda source, mode: baseline_packet)

    rc = main([
        'ds',
        'wizard',
        '--workflow',
        'evaluate',
        '--hydrate-latest-context',
        '--section',
        'check',
        '--json',
    ])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload['decision'] == 'go'
    assert payload['current_section'] == 'check'
    assert payload['execution_state'] == 'blocked'
    assert payload['hydrated_from']['source'] == 'latest_context'
    assert payload['hydrated_from']['mode'] == 'latest_context'
    assert payload['artifacts']['baseline_analysis_packet'] == str(baseline_packet)
    assert 'features_csv is required' in payload['validation_issues']


def test_ds_wizard_hydrates_prior_run_ledger(tmp_path: Path) -> None:
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    model_path = tmp_path / 'model.pkl'
    baseline_packet = tmp_path / 'baseline.json'
    run_json = tmp_path / 'run.json'

    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    baseline_packet.write_text(json.dumps({'baseline_window_id': 'frame6-ledger-baseline'}), encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
    }), encoding='utf-8')
    run_json.write_text(json.dumps({
        'identity': {'run_id': 'frame6-ledger-import'},
        'context': {
            'constraints': {'max_fpr': 0.02},
            'baseline_analysis_packet': str(baseline_packet),
            'baseline_window_id': 'frame6-ledger-baseline',
        },
        'data': {
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
            'dataset_manifest': str(dataset_manifest),
        },
        'model': {
            'family': 'trained_apexlab',
            'source': str(model_path),
        },
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_hydrate_run_ledger(state, run_json)

    assert state.run_ledger_path == str(run_json)
    assert state.values['run_id'] == 'frame6-ledger-import'
    assert state.values['max_fpr'] == 0.02
    assert state.values['dataset_manifest'] == str(dataset_manifest)
    assert state.values['features_csv'] == str(features_csv)
    assert state.values['labels_csv'] == str(labels_csv)
    assert state.values['model_path'] == str(model_path)
    assert state.values['baseline_analysis_packet'] == str(baseline_packet)
    assert state.values['baseline_window_id'] == 'frame6-ledger-baseline'
    assert state.hydrated_from['run_id'] == 'run_ledger'
    assert state.hydrated_from['max_fpr'] == 'run_ledger'
    assert state.hydrated_from['model_path'] == 'run_ledger'
    assert state.hydrated_from['baseline_analysis_packet'] == 'run_ledger'
    assert state.hydrated_from['baseline_window_id'] == 'run_ledger'


def test_ds_wizard_cli_draft_round_trip_preserves_run_context_and_report_preview(tmp_path: Path, capsys) -> None:
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    model_path = tmp_path / 'model.pkl'
    run_json = tmp_path / 'run.json'
    draft_path = tmp_path / 'wizard_draft.json'

    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
    }), encoding='utf-8')
    run_json.write_text(json.dumps({
        'identity': {'run_id': 'frame6-ledger-import'},
        'context': {'constraints': {'max_fpr': 0.02}},
        'data': {
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
            'dataset_manifest': str(dataset_manifest),
        },
        'model': {
            'family': 'trained_apexlab',
            'source': str(model_path),
        },
    }), encoding='utf-8')

    save_rc = main([
        'ds',
        'wizard',
        '--workflow',
        'evaluate',
        '--hydrate-run',
        str(run_json),
        '--section',
        'report',
        '--save-draft',
        str(draft_path),
        '--json',
    ])
    save_payload = json.loads(capsys.readouterr().out)

    load_rc = main([
        'ds',
        'wizard',
        '--load-draft',
        str(draft_path),
        '--json',
    ])
    load_payload = json.loads(capsys.readouterr().out)
    draft_payload = json.loads(draft_path.read_text(encoding='utf-8'))

    assert save_rc == 0
    assert load_rc == 0
    assert save_payload['decision'] == 'go'
    assert load_payload['decision'] == 'go'
    assert save_payload['execution_state'] == 'ready'
    assert load_payload['execution_state'] == 'ready'
    assert save_payload['current_section'] == 'report'
    assert load_payload['current_section'] == 'report'
    assert save_payload['artifacts']['run_ledger_path'] == str(run_json)
    assert load_payload['artifacts']['run_ledger_path'] == str(run_json)
    assert save_payload['artifacts']['draft_path'] == str(draft_path)
    assert load_payload['artifacts']['draft_path'] == str(draft_path)
    assert save_payload['validation_issues'] == []
    assert load_payload['validation_issues'] == []
    assert save_payload['command_preview'] == load_payload['command_preview']
    assert save_payload['hydrated_from'] == load_payload['hydrated_from']
    assert draft_payload['run_ledger_path'] == str(run_json)
    assert draft_payload['active_section'] == 'report'
    assert any(run_json.name in line for line in load_payload['wizard_view'])
    assert any(dataset_manifest.name in line for line in load_payload['wizard_view'])
    assert any(model_path.name in line for line in load_payload['wizard_view'])


def test_ds_wizard_reselection_supports_keep_clear_new() -> None:
    state = observerctl_module._ds_wizard_new_state('train')
    observerctl_module._ds_wizard_set_value(state, 'out_dir', 'alpha')

    observerctl_module._ds_wizard_apply_reselection(state, 'out_dir', 'keep')
    assert state.values['out_dir'] == 'alpha'

    observerctl_module._ds_wizard_apply_reselection(state, 'out_dir', 'clear')
    assert state.values['out_dir'] == ''

    observerctl_module._ds_wizard_apply_reselection(state, 'out_dir', 'new', 'beta')
    assert state.values['out_dir'] == 'beta'


def test_ds_wizard_execute_is_blocked_when_validation_has_not_passed() -> None:
    state = observerctl_module._ds_wizard_new_state('train')
    packet = observerctl_module._ds_wizard_attempt_execute(state)

    assert packet['decision'] == 'no-go'
    assert 'critical_check_failed:wizard_validation_blocked' in packet['reason_codes']
    assert 'dataset_manifest is required' in packet['validation_issues']


def test_ds_wizard_cli_blocked_execute_packet_is_truthful(capsys) -> None:
    rc = main(['ds', 'wizard', '--workflow', 'evaluate', '--execute', '--json'])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 2
    assert payload['decision'] == 'no-go'
    assert 'critical_check_failed:wizard_validation_blocked' in payload['reason_codes']
    assert 'features_csv is required' in payload['validation_issues']
    assert payload['wizard_workflow'] == 'evaluate'
    assert payload['command_preview'].startswith('observerctl ds evaluate')
    assert 'artifacts' not in payload or payload['artifacts'] == {}


def test_ds_wizard_execute_command_uses_one_line_transient_block_message() -> None:
    state = observerctl_module._ds_wizard_new_state('train')
    observerctl_module._ds_wizard_open_section(state, 'run')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'execute')

    assert packet is None
    assert should_exit is False
    assert observerctl_module._ds_wizard_transient_lines(state) == ['execute blocked: validate this workflow first']


def test_ds_wizard_execute_failure_stays_truthful_after_validation_passes(monkeypatch, tmp_path: Path) -> None:
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    features_csv = tmp_path / 'features.csv'
    model_path = tmp_path / 'model.pkl'
    train_manifest = tmp_path / 'train_manifest.json'

    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 1,
        'has_labels': False,
    }), encoding='utf-8')
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(model_path),
        'model_type': 'unsupervised',
    }), encoding='utf-8')

    def _fake_score(dataset: str, model: str, out_file: str, collection_alias: str = '') -> Dict[str, Any]:
        raise RuntimeError('synthetic score failure')

    monkeypatch.setattr(observerctl_module, '_ds_score', _fake_score)

    state = observerctl_module._ds_wizard_new_state('score')
    observerctl_module._ds_wizard_set_value(state, 'dataset_manifest', str(dataset_manifest))
    observerctl_module._ds_wizard_set_value(state, 'train_manifest', str(train_manifest))
    observerctl_module._ds_wizard_set_value(state, 'model_path', str(model_path))
    observerctl_module._ds_wizard_open_section(state, 'run')

    assert strip_ansi(observerctl_module._ds_wizard_left_rail_rows(state)[1]) == 'validate: ready'
    assert strip_ansi(observerctl_module._ds_wizard_left_rail_rows(state)[2]) == 'advance: no-go'

    derived_packet = observerctl_module._ds_wizard_attempt_execute(state)

    assert derived_packet['decision'] == 'no-go'
    assert 'critical_check_failed:wizard_execution_failed' in derived_packet['reason_codes']
    assert derived_packet['summary'] == 'Workflow execution failed before completion.'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'execute')

    assert packet is None
    assert should_exit is False
    assert observerctl_module._ds_wizard_transient_lines(state) == ['execute failed: workflow execution failed before completion']

    rendered = [' '.join(strip_ansi(line).split()) for line in observerctl_module._ds_wizard_render(state)]
    assert 'validate: ready' in rendered
    assert 'advance: no-go' in rendered
    assert 'processing: ready' in rendered
    assert all('validate this workflow first' not in line for line in rendered)


def test_ds_wizard_build_execute_marks_build_go_and_train_stays_no_go(tmp_path: Path, monkeypatch) -> None:
    dataset_dir = tmp_path / 'dataset'
    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    splits_csv = dataset_dir / 'splits.csv'
    split_manifest_json = dataset_dir / 'split_manifest.json'

    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    splits_csv.write_text('record_id,split\n1,train\n', encoding='utf-8')
    split_manifest_json.write_text('{"train": 1}\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'splits_csv': str(splits_csv),
        'split_manifest_json': str(split_manifest_json),
        'feature_columns': ['feature'],
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_set_value(state, 'dataset_manifest', str(dataset_manifest))
    observerctl_module._ds_wizard_open_section(state, 'run')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'execute')

    assert packet is None
    assert should_exit is False
    assert state.values['dataset_manifest'] != str(dataset_manifest)
    assert Path(str(state.values['dataset_manifest'])).exists()
    assert strip_ansi(observerctl_module._ds_wizard_left_rail_rows(state)[1]) == 'validate: ready'
    assert strip_ansi(observerctl_module._ds_wizard_left_rail_rows(state)[2]) == 'advance: go'
    assert observerctl_module._ds_wizard_run_gate_issues(state) == []
    assert observerctl_module._ds_wizard_transient_lines(state) == ['build complete: 1 record']

    run_lines = [' '.join(strip_ansi(line).split()) for line in observerctl_module._ds_wizard_render(state)]
    assert any(line == 'processing: complete' for line in run_lines)
    assert any(line == 'completion: build complete: 1 record' for line in run_lines)

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'train')

    assert packet is None
    assert should_exit is False
    assert state.workflow == 'train'
    assert observerctl_module._ds_wizard_run_gate_issues(state) == []
    assert strip_ansi(observerctl_module._ds_wizard_left_rail_rows(state)[1]) == 'validate: ready'
    assert strip_ansi(observerctl_module._ds_wizard_left_rail_rows(state)[2]) == 'advance: no-go'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'report')

    assert packet is None
    assert should_exit is False
    report_lines = [' '.join(strip_ansi(line).split()) for line in observerctl_module._ds_wizard_render(state)]
    assert any(line == 'dataset manifest: dataset_manifest.json' for line in report_lines)
    assert any(line == 'features csv: features.csv' for line in report_lines)


def test_ds_wizard_build_sync_preserves_collection_alias_from_build_packet(tmp_path: Path) -> None:
    features_csv = tmp_path / 'features.csv'
    dataset_manifest = tmp_path / 'dataset_manifest.json'

    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 1,
        'has_labels': False,
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('build')
    state.values['dataset_alias'] = ''

    synced = observerctl_module._ds_wizard_sync_execution_artifacts(
        state,
        {
            'artifacts': {'dataset_manifest': str(dataset_manifest)},
            'collection_alias': 'can-shared-build',
        },
    )

    assert synced.values['dataset_manifest'] == str(dataset_manifest)
    assert synced.values['dataset_alias'] == 'can-shared-build'
    assert synced.hydrated_from['dataset_manifest'] == 'wizard_execute'


def test_ds_wizard_train_sync_preserves_collection_alias_from_train_packet(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    model_path = tmp_path / 'model.pkl'
    train_manifest = tmp_path / 'train_manifest.json'

    dataset_manifest.write_text(json.dumps({'features_csv': str(tmp_path / 'features.csv')}), encoding='utf-8')
    (tmp_path / 'features.csv').write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(model_path),
        'model_type': 'unsupervised',
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('train')
    state.values['dataset_alias'] = ''

    synced = observerctl_module._ds_wizard_sync_execution_artifacts(
        state,
        {
            'artifacts': {'train_manifest': str(train_manifest)},
            'collection_alias': 'can-shared-train',
        },
    )

    assert synced.values['train_manifest'] == str(train_manifest)
    assert synced.values['dataset_manifest'] == str(dataset_manifest)
    assert synced.values['model_path'] == str(model_path)
    assert synced.values['dataset_alias'] == 'can-shared-train'
    assert synced.hydrated_from['train_manifest'] == 'wizard_execute'


def test_ds_wizard_attempt_execute_threads_collection_alias_to_downstream_workflows(tmp_path: Path, monkeypatch) -> None:
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    splits_csv = tmp_path / 'splits.csv'
    split_manifest_json = tmp_path / 'split_manifest.json'
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    model_path = tmp_path / 'model.pkl'
    train_manifest = tmp_path / 'train_manifest.json'

    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    splits_csv.write_text('record_id,split\n1,train\n', encoding='utf-8')
    split_manifest_json.write_text(json.dumps({'split': 'ok'}), encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'splits_csv': str(splits_csv),
        'split_manifest_json': str(split_manifest_json),
        'feature_columns': ['feature'],
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')
    model_path.write_bytes(b'model')
    train_manifest.write_text(json.dumps({'model_path': str(model_path)}), encoding='utf-8')

    captured_calls = []

    def _fake_train(dataset: str, out_dir: str, model_type: str, seed: int, collection_alias: str = '') -> Dict[str, Any]:
        captured_calls.append(('train', collection_alias, dataset))
        return {
            'timestamp_utc': '2026-04-12T12:00:00Z',
            'decision': 'go',
            'action': 'ds-train',
            'summary': 'train ok',
            'run_id': 'train-run-001',
            'artifacts': {},
            'reason_codes': [],
        }

    def _fake_evaluate(features_csv: str, labels_csv: str, dataset_manifest: str, max_fpr: float, out_dir: str, run_id: str, model_path: str, collection_alias: str = '', source: str = '', mode: str = '', baseline_window_id: str = '', baseline_analysis_packet: str = '') -> Dict[str, Any]:
        captured_calls.append(('evaluate', collection_alias, dataset_manifest))
        return {
            'timestamp_utc': '2026-04-12T12:01:00Z',
            'decision': 'go',
            'action': 'ds-evaluate',
            'summary': 'evaluate ok',
            'run_id': 'eval-run-001',
            'threshold': 0.42,
            'artifacts': {},
            'reason_codes': [],
        }

    def _fake_score(dataset: str, model: str, out_file: str, collection_alias: str = '') -> Dict[str, Any]:
        captured_calls.append(('score', collection_alias, dataset))
        return {
            'timestamp_utc': '2026-04-12T12:02:00Z',
            'decision': 'go',
            'action': 'ds-score',
            'summary': 'score ok',
            'run_id': 'score-run-001',
            'records_scored': 1,
            'artifacts': {},
            'reason_codes': [],
        }

    monkeypatch.setattr(observerctl_module, '_ds_train', _fake_train)
    monkeypatch.setattr(observerctl_module, '_ds_evaluate', _fake_evaluate)
    monkeypatch.setattr(observerctl_module, '_ds_score', _fake_score)

    train_state = observerctl_module._ds_wizard_new_state('train')
    train_state.values['dataset_manifest'] = str(dataset_manifest)
    train_state.values['dataset_alias'] = 'can-shared-build'
    train_packet = observerctl_module._ds_wizard_attempt_execute(train_state)

    evaluate_state = observerctl_module._ds_wizard_new_state('evaluate')
    evaluate_state.values['dataset_manifest'] = str(dataset_manifest)
    evaluate_state.values['features_csv'] = str(features_csv)
    evaluate_state.values['labels_csv'] = str(labels_csv)
    evaluate_state.values['model_path'] = str(model_path)
    evaluate_state.values['dataset_alias'] = 'can-shared-build'
    evaluate_packet = observerctl_module._ds_wizard_attempt_execute(evaluate_state)

    score_state = observerctl_module._ds_wizard_new_state('score')
    score_state.values['dataset_manifest'] = str(dataset_manifest)
    score_state.values['train_manifest'] = str(train_manifest)
    score_state.values['model_path'] = str(model_path)
    score_state.values['dataset_alias'] = 'can-shared-build'
    score_packet = observerctl_module._ds_wizard_attempt_execute(score_state)

    assert train_packet['decision'] == 'go'
    assert evaluate_packet['decision'] == 'go'
    assert score_packet['decision'] == 'go'
    assert captured_calls == [
        ('train', 'can-shared-build', str(dataset_manifest)),
        ('evaluate', 'can-shared-build', str(dataset_manifest)),
        ('score', 'can-shared-build', str(dataset_manifest)),
    ]


def test_ds_wizard_cli_publication_groups_build_train_evaluate_score_under_one_collection_alias(tmp_path: Path, monkeypatch, capsys) -> None:
    from analysis.dataset_builder import build_dataset
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    _set_signing_env(monkeypatch)

    input_path = tmp_path / 'authority_input.jsonl'
    authority_dataset_dir = project_root / 'datasets' / 'authority_alias_source'
    authority_manifest = authority_dataset_dir / 'dataset_manifest.json'

    _write_signed_jsonl(input_path, _make_ds_records())
    build_dataset(
        [input_path],
        out_dir=authority_dataset_dir,
        seed=123,
        split={
            'train': 0.7,
            'val': 0.15,
            'test': 0.15,
        },
        max_lines_per_file=None,
    )

    dataset_packet = register_librarian_dataset_packet(
        anchor,
        authority_manifest,
        access_class='local',
        display_name='Frame D Alias Coherence',
        run_id='frame-d-alias-coherence',
    )
    assert dataset_packet['decision'] == 'go'
    expected_alias = str(dataset_packet['dataset']['display_alias'])

    rc = main(['ds', 'wizard', '--workflow', 'build', '--hydrate-dataset', '1', '--execute', '--json'])
    assert rc == 0
    build_packet = json.loads(capsys.readouterr().out)

    rc = main(['ds', 'wizard', '--workflow', 'train', '--hydrate-dataset', '1', '--set', 'model_type=unsupervised', '--execute', '--json'])
    assert rc == 0
    train_packet = json.loads(capsys.readouterr().out)
    train_manifest_path = _resolve_reported_path(train_packet['artifacts']['train_manifest'])

    rc = main(['ds', 'wizard', '--workflow', 'evaluate', '--hydrate-dataset', '1', '--hydrate-train', str(train_manifest_path), '--execute', '--json'])
    assert rc == 0
    evaluate_packet = json.loads(capsys.readouterr().out)

    rc = main(['ds', 'wizard', '--workflow', 'score', '--hydrate-dataset', '1', '--hydrate-train', str(train_manifest_path), '--execute', '--json'])
    assert rc == 0
    score_packet = json.loads(capsys.readouterr().out)

    alias_root = project_root / 'docs' / 'reports' / 'collections' / expected_alias
    publication_root = project_root / 'docs' / 'reports' / 'collections'
    packets = {
        'build': build_packet,
        'train': train_packet,
        'evaluate': evaluate_packet,
        'score': score_packet,
    }

    for packet in packets.values():
        assert packet['decision'] == 'go'
        assert packet['collection_alias'] == expected_alias
        assert packet['publication']['decision'] == 'go'
        assert packet['publication']['current_run']['collection_alias'] == expected_alias

    assert alias_root.exists()
    assert (alias_root / 'processing' / 'build').exists()
    assert (alias_root / 'processing' / 'train').exists()
    assert (alias_root / 'processing' / 'eval').exists()
    assert (alias_root / 'processing' / 'score').exists()

    for workflow, packet in packets.items():
        processing_md = _resolve_reported_path(packet['publication']['current_run']['published_report_paths']['processing_markdown'])
        assert processing_md.exists()
        assert '**Collection alias**: `{0}`'.format(expected_alias) in processing_md.read_text(encoding='utf-8')
        assert not (publication_root / str(packet['run_id'])).exists()

    assert sorted(path.name for path in publication_root.iterdir() if path.is_dir()) == [expected_alias]


def test_ds_wizard_unlabeled_build_switches_train_to_unsupervised(tmp_path: Path) -> None:
    dataset_dir = tmp_path / 'dataset'
    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    splits_csv = dataset_dir / 'splits.csv'
    split_manifest_json = dataset_dir / 'split_manifest.json'

    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    splits_csv.write_text('record_id,split\n1,train\n', encoding='utf-8')
    split_manifest_json.write_text('{"train": 1}\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'splits_csv': str(splits_csv),
        'split_manifest_json': str(split_manifest_json),
        'feature_columns': ['feature'],
        'total_records': 1,
        'has_labels': False,
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_set_value(state, 'dataset_manifest', str(dataset_manifest))
    observerctl_module._ds_wizard_open_section(state, 'run')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'execute')

    assert packet is None
    assert should_exit is False

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'train')

    assert packet is None
    assert should_exit is False
    assert state.workflow == 'train'
    assert state.values['model_type'] == 'unsupervised'
    assert observerctl_module._ds_wizard_run_gate_issues(state) == []


def test_ds_wizard_completion_line_is_workflow_specific() -> None:
    assert observerctl_module._ds_wizard_packet_completion_line({'wizard_workflow': 'build', 'total_records': 1}) == 'build complete: 1 record'
    assert observerctl_module._ds_wizard_packet_completion_line({'wizard_workflow': 'train', 'model_type': 'supervised'}) == 'train complete: supervised model ready'
    assert observerctl_module._ds_wizard_packet_completion_line({'wizard_workflow': 'evaluate', 'threshold': 0.125}) == 'evaluate complete: threshold 0.125'
    assert observerctl_module._ds_wizard_packet_completion_line({'wizard_workflow': 'run-pipeline', 'model_type': 'unsupervised', 'total_records': 8}) == 'pipeline complete: unsupervised | 8 records'


def test_ds_wizard_build_validation_accepts_selected_dataset_without_input_paths(tmp_path: Path) -> None:
    dataset_dir = tmp_path / 'dataset'
    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    splits_csv = dataset_dir / 'splits.csv'
    split_manifest_json = dataset_dir / 'split_manifest.json'

    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    splits_csv.write_text('record_id,split\n1,train\n', encoding='utf-8')
    split_manifest_json.write_text('{"train": 1}\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'splits_csv': str(splits_csv),
        'split_manifest_json': str(split_manifest_json),
        'feature_columns': ['feature'],
        'total_records': 1,
        'has_labels': False,
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_set_value(state, 'dataset_manifest', str(dataset_manifest))

    issues = observerctl_module._ds_wizard_run_gate_issues(state)

    assert 'input_paths is required' not in issues
    assert 'approved dataset selection is required' not in issues


def test_ds_wizard_build_validation_requires_materializable_selected_dataset(tmp_path: Path) -> None:
    dataset_dir = tmp_path / 'dataset'
    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    splits_csv = dataset_dir / 'splits.csv'

    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    splits_csv.write_text('record_id,split\n1,train\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'splits_csv': str(splits_csv),
        'feature_columns': ['feature'],
        'total_records': 1,
        'has_labels': False,
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_set_value(state, 'dataset_manifest', str(dataset_manifest))

    issues = observerctl_module._ds_wizard_run_gate_issues(state)

    assert 'build dataset manifest missing required field: split_manifest_json' in issues


def test_ds_wizard_train_validation_requires_train_ready_dataset_manifest(tmp_path: Path) -> None:
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('train')
    observerctl_module._ds_wizard_set_value(state, 'dataset_manifest', str(dataset_manifest))

    issues = observerctl_module._ds_wizard_validation_issues(state)
    packet = observerctl_module._ds_wizard_attempt_execute(state)

    assert 'train dataset manifest missing required field: splits_csv' in issues
    assert 'train dataset manifest missing required field: feature_columns' in issues
    assert packet['decision'] == 'no-go'
    assert 'critical_check_failed:wizard_validation_blocked' in packet['reason_codes']
    assert 'train dataset manifest missing required field: splits_csv' in packet['validation_issues']


def test_ds_wizard_save_and_load_draft_round_trip(tmp_path: Path) -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'report')
    observerctl_module._ds_wizard_set_value(state, 'run_id', 'draft-run-001')
    observerctl_module._ds_wizard_set_value(state, 'max_fpr', '0.03')
    state.values['dataset_alias'] = ''
    state.source = 'real'
    state.mode = 'canary'
    state.values['source'] = 'real'
    state.values['mode'] = 'canary'
    state.hydrated_from['run_id'] = 'run_ledger'
    state.run_ledger_path = str(tmp_path / 'prior_run.json')

    draft_path = tmp_path / 'wizard_draft.json'
    observerctl_module._ds_wizard_save_draft(state, draft_path)
    loaded = observerctl_module._ds_wizard_load_draft(draft_path)

    assert draft_path.exists()
    assert loaded.workflow == 'evaluate'
    assert loaded.active_page == 'configure'
    assert loaded.active_group == 'eval-report'
    assert loaded.active_section == 'report'
    assert loaded.values['run_id'] == 'draft-run-001'
    assert loaded.values['max_fpr'] == 0.03
    assert 'dataset_alias' in loaded.values
    assert loaded.values['dataset_alias'] == ''
    assert loaded.source == 'real'
    assert loaded.mode == 'canary'
    assert loaded.hydrated_from['run_id'] == 'run_ledger'
    assert loaded.run_ledger_path == str(tmp_path / 'prior_run.json')
    assert loaded.draft_path == str(draft_path)


def test_ds_wizard_starts_on_sparse_landing_page() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')

    rendered = observerctl_module._ds_wizard_render(state)

    assert 'path: ds wizard > landing' in rendered
    assert rendered[3] == 'workflow: run-pipeline'
    assert rendered[4] == 'validate: blocked'
    assert rendered[5] == 'advance: no-go'
    assert rendered[6].strip() == 'family:'
    assert 'home:' in rendered
    assert '1. configure' in rendered
    assert '2. review and run' in rendered
    assert '3. command and utilities' in rendered
    assert '4. exit' in rendered
    assert not any(line.startswith('summary:') for line in rendered)
    assert not any(line.startswith('guided workflow:') for line in rendered)
    assert 'sections: flow, in, model, eval, report, cmd, check, run, exit' not in rendered
    assert not any(line.startswith('actions:') for line in rendered)
    assert not any(line.startswith('next:') for line in rendered)


def test_ds_wizard_scope_help_from_landing_shows_top_level_choices() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '?')

    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'help:' in rendered
    assert any('configure opens the workflow-specific pages and shared section rail.' in line for line in rendered)
    assert any('review and run keeps validate and status separate: validate answers can-run-now, status answers can-advance.' in line for line in rendered)
    assert any('command and utilities explains the CLI preview plus save/load/hydrate helpers.' in line for line in rendered)
    assert any('operator loop:' in line for line in rendered)
    assert any('report -> return there after execute to confirm artifact targets and results.' in line for line in rendered)
    assert not any('configure          guided workflow and configuration' in line for line in rendered)


def test_ds_wizard_stacked_render_hides_raw_section_scaffold_on_non_landing_pages(monkeypatch) -> None:
    monkeypatch.setattr(observerctl_module, '_ds_wizard_get_terminal_width', lambda: 90)
    state = observerctl_module._ds_wizard_new_state('run-pipeline')
    observerctl_module._ds_wizard_open_section(state, 'report')

    rendered = observerctl_module._ds_wizard_render(state)

    assert not any(line.startswith('sections:') for line in rendered)
    assert 'actions: prev | ? | next | exit' in rendered


def test_ds_wizard_landing_choices_route_to_top_level_pages() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '1')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'configure'
    assert state.active_section == 'flow'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'home')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'landing'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '2')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'review-run'
    assert state.active_section == 'check'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'home')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'landing'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '3')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'utilities'
    assert state.active_section == 'cmd'


def test_ds_wizard_configure_opens_guided_flow_surface_without_preselected_workflow() -> None:
    state = observerctl_module._ds_wizard_new_state('')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'configure')

    assert packet is None
    assert should_exit is False
    assert state.active_page == 'configure'
    assert state.active_section == 'flow'


def test_ds_wizard_defaults_to_build_workflow_when_unset() -> None:
    state = observerctl_module._ds_wizard_new_state('')

    assert state.workflow == 'build'
    assert state.values['workflow'] == 'build'
    assert observerctl_module._ds_wizard_landing_summary_rows(state)[0] == 'workflow: build'


def test_ds_wizard_header_values_stay_blank_without_dataset_context() -> None:
    state = observerctl_module._ds_wizard_new_state('build')

    left_rows = observerctl_module._ds_wizard_left_rail_rows(state)
    right_rows = observerctl_module._ds_wizard_right_pane_ops_rows(state)

    assert 'family: ' in left_rows[3]
    assert left_rows[3].strip() == 'family:'
    assert right_rows[0].strip() == 'dataset:  none'
    assert right_rows[1].strip() == 'source:'
    assert right_rows[2].strip() == 'mode:'


def test_ds_wizard_configure_restores_shared_section_rail() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')

    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'configure')
    assert state.active_page == 'configure'
    assert observerctl_module._ds_wizard_page_sections(state) == ['flow', 'report', 'cmd', 'check', 'run']
    assert observerctl_module._ds_wizard_action_line(state) == 'actions: prev | ? | next | exit'


def test_ds_wizard_non_landing_pages_share_navigation_only_action_bar() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')

    for section in ('flow', 'model', 'check'):
        observerctl_module._ds_wizard_open_section(state, section)
        assert observerctl_module._ds_wizard_action_line(state) == 'actions: prev | ? | next | exit'

    observerctl_module._ds_wizard_open_section(state, 'run')
    assert observerctl_module._ds_wizard_action_line(state) == 'actions: prev | ? | next | execute | exit'

    state.transient_view = 'picker'
    assert observerctl_module._ds_wizard_action_line(state) == 'actions: prev | ? | next | execute | exit'


def test_ds_wizard_scope_help_from_section_is_section_scoped() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '?')

    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'help: eval' in rendered
    assert any('mechanical validation thresholds' in line for line in rendered)
    assert any('verify:' in line for line in rendered)
    assert 'fields:' in rendered
    assert any('max FPR' in line and 'Maximum false-positive rate' in line for line in rendered)
    assert any('set max_fpr 0.02' in line for line in rendered)


def test_ds_wizard_report_help_explains_loaded_markers_and_results_block() -> None:
    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_open_section(state, 'report')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '?')

    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'help: report' in rendered
    assert any('canonical artifact targets' in line for line in rendered)
    assert any('Loaded markers mean the wizard already resolved the backing dataset, model, run, or draft reference' in line for line in rendered)
    assert any('After execute succeeds, return here to confirm the results block without leaving the wizard.' in line for line in rendered)
    assert any('cmd' in line and 'raw command preview' in line for line in rendered)


def test_ds_wizard_cmd_help_explains_preview_and_hydration_helpers() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'cmd')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '?')

    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'help: cmd' in rendered
    assert any('non-interactive CLI equivalent' in line for line in rendered)
    assert any('Placeholders stand in for resolved paths' in line for line in rendered)
    assert any('save draft [slot|path]' in line for line in rendered)
    assert any('hydrate dataset|train|run|baseline <selector>' in line for line in rendered)


def test_ds_wizard_status_help_explains_advance_gate() -> None:
    state = observerctl_module._ds_wizard_new_state('train')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '? status')

    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'peek: status' in rendered
    assert any('status is the advance gate for the current workflow.' in line for line in rendered)
    assert any('validate is separate: it answers whether this workflow can run now.' in line for line in rendered)


def test_ds_wizard_eval_page_surfaces_edit_guidance() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')

    rendered = observerctl_module._ds_wizard_render(state)

    assert 'Type 1 to edit max_fpr, or use set max_fpr <value>.' not in rendered
    assert not any(line.startswith('guide:') for line in rendered)


def test_ds_wizard_context_fields_are_wired_for_direct_updates() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')

    observerctl_module._ds_wizard_set_value(state, 'source', 'real')
    observerctl_module._ds_wizard_set_value(state, 'mode', 'canary')

    assert state.source == 'real'
    assert state.mode == 'canary'
    assert state.values['source'] == 'real'
    assert state.values['mode'] == 'canary'


def test_ds_wizard_context_summary_stays_hidden_without_dataset_metadata() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')

    observerctl_module._ds_wizard_set_value(state, 'source', 'real')
    observerctl_module._ds_wizard_set_value(state, 'mode', 'canary')

    assert not any(line.startswith('context:') for line in observerctl_module._ds_wizard_summary_rows(state))


def test_ds_wizard_clear_workflow_resets_to_build_and_clears_context() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    state.source = 'real'
    state.mode = 'canary'
    state.values['source'] = 'real'
    state.values['mode'] = 'canary'
    state.hydrated_from['context'] = 'saved_run'
    observerctl_module._ds_wizard_open_section(state, 'eval')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'clear workflow')

    assert packet is None
    assert should_exit is False
    assert state.workflow == 'build'
    assert state.values['workflow'] == 'build'
    assert state.active_section == 'flow'
    assert 'context' not in state.hydrated_from
    assert observerctl_module._ds_wizard_transient_lines(state) == ['workflow reset: build']
    assert not any(line.startswith('context:') for line in observerctl_module._ds_wizard_summary_rows(state))


def test_ds_wizard_flow_advanced_menu_gates_source_context_override(monkeypatch) -> None:
    monkeypatch.setattr(observerctl_module, '_load_state', lambda: {'source': 'sim', 'mode': 'watch'})
    state = observerctl_module._ds_wizard_new_state('evaluate')
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'configure')

    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(state)
    assert any('6. advanced' in line for line in rendered)
    assert not any('rare override and expert actions' in line for line in rendered)
    assert 'context overrides are high-risk' not in rendered

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '6')

    assert packet is None
    assert should_exit is False
    assert state.transient_view == 'picker'
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'advanced:' in rendered
    assert any('context overrides are high-risk' in line for line in rendered)
    assert '1. source context         current: sim' in rendered
    assert '2. mode context           current: watch' in rendered
    assert any('manual identifiers:' in line for line in rendered)
    assert any('run ID override' in line for line in rendered)

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '1')

    assert packet is None
    assert should_exit is False
    assert state.transient_view == 'picker'
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'source choices:' in rendered
    assert '1. [*] sim' in rendered
    assert '2. [ ] real' in rendered

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '2')

    assert packet is None
    assert should_exit is False
    assert state.source == 'real'
    assert state.values['source'] == 'real'
    assert 'updated context: source = real' in observerctl_module._ds_wizard_transient_lines(state)


def test_ds_wizard_run_id_override_requires_advanced_lane() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'model')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'set run_id custom-eval-001')

    assert packet is None
    assert should_exit is False
    assert state.values['run_id'] == ''
    rendered = observerctl_module._ds_wizard_render(state)
    assert any('run ID is locked behind advanced.' in line for line in rendered)
    assert '--run-id' not in observerctl_module._ds_wizard_command_preview(state)

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'open flow')
    assert packet is None
    assert should_exit is False
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '6')
    assert packet is None
    assert should_exit is False
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '3')

    assert packet is None
    assert should_exit is False
    assert state.transient_view == 'advanced-edit'
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'advanced override:' in rendered
    assert 'run ID override:' in rendered

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'set run_id custom-eval-001')

    assert packet is None
    assert should_exit is False
    assert state.values['run_id'] == 'custom-eval-001'
    assert '--run-id custom-eval-001' in observerctl_module._ds_wizard_command_preview(state)


def test_ds_wizard_out_dir_override_requires_advanced_lane(tmp_path: Path) -> None:
    state = observerctl_module._ds_wizard_new_state('train')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'set out_dir {0}'.format(tmp_path / 'override-root'))

    assert packet is None
    assert should_exit is False
    assert state.values['out_dir'] == ''
    rendered = observerctl_module._ds_wizard_render(state)
    assert any('output is locked behind advanced.' in line for line in rendered)

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'configure')
    assert packet is None
    assert should_exit is False
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '6')
    assert packet is None
    assert should_exit is False
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '4')

    assert packet is None
    assert should_exit is False
    assert state.transient_view == 'advanced-edit'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'set out_dir {0}'.format(tmp_path / 'override-root'))

    assert packet is None
    assert should_exit is False
    assert str(state.values['out_dir']).endswith('override-root')


def test_ds_wizard_hydrate_latest_explains_dataset_limit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(observerctl_module, '_load_state', lambda: {'source': 'real', 'mode': 'canary'})
    monkeypatch.setattr(observerctl_module, '_ds_wizard_latest_baseline_analysis_path', lambda source, mode: None)
    state = observerctl_module._ds_wizard_new_state('evaluate')

    observerctl_module._ds_wizard_hydrate_latest_context(state)

    lines = observerctl_module._ds_wizard_transient_lines(state)
    assert lines == ['latest context loaded: source=real, mode=canary']


def test_ds_wizard_item_peek_does_not_change_state() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')
    observerctl_module._ds_wizard_set_value(state, 'max_fpr', '0.05')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '? max_fpr')

    assert packet is None
    assert should_exit is False
    assert state.active_section == 'eval'
    assert state.values['max_fpr'] == 0.05
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'peek: max_fpr' in rendered
    assert 'Maximum false-positive rate' in rendered
    assert 'value: 0.05' in rendered


def test_ds_wizard_blank_input_dismisses_transient_help() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, '?')
    assert state.transient_view == 'scope-help'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '')

    assert packet is None
    assert should_exit is False
    assert state.transient_view == ''
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'help:' not in rendered


def test_ds_wizard_educational_flash_clears_after_interactive_emit(monkeypatch, capsys) -> None:
    state = observerctl_module._ds_wizard_new_state('')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'configure')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'run-pipeline')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_try_clear_terminal', lambda: False)

    observerctl_module._ds_wizard_emit_interactive_frame(state, redraw_count=0)

    out = capsys.readouterr().out
    assert 'workflow set:' not in out
    assert state.transient_view == ''


def test_ds_wizard_first_interactive_render_does_not_emit_transition_separator(monkeypatch, capsys) -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_try_clear_terminal', lambda: False)

    observerctl_module._ds_wizard_emit_interactive_frame(state, redraw_count=0)

    out = capsys.readouterr().out.splitlines()
    assert out[0] == 'ObserverCTL DS Wizard'
    assert 'next frame: ds wizard > configure > eval' not in out


def test_ds_wizard_interactive_redraw_uses_separator_when_clear_is_unavailable(monkeypatch, capsys) -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_try_clear_terminal', lambda: False)

    observerctl_module._ds_wizard_emit_interactive_frame(state, redraw_count=1)

    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith('=')
    assert out[1] == 'next frame: ds wizard > configure > eval'
    assert out[2].startswith('=')
    assert 'ObserverCTL DS Wizard' in out


def test_ds_wizard_interactive_redraw_skips_separator_when_clear_succeeds(monkeypatch, capsys) -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_try_clear_terminal', lambda: True)

    observerctl_module._ds_wizard_emit_interactive_frame(state, redraw_count=1)

    out = capsys.readouterr().out.splitlines()
    assert out[0] == 'ObserverCTL DS Wizard'
    assert 'next frame: ds wizard > configure > eval' not in out


def test_ds_wizard_datasets_command_lists_approved_selectors(monkeypatch, tmp_path: Path) -> None:
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'approved_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 12,
        'has_labels': True,
    }), encoding='utf-8')

    register_librarian_dataset_packet(
        anchor,
        manifest_path,
        access_class='local',
        display_name='Approved Alpha',
        run_id='alpha-run',
    )
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)

    state = observerctl_module._ds_wizard_new_state('evaluate')
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'datasets')

    assert packet is None
    assert should_exit is False
    assert state.transient_view == 'picker'
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'approved datasets:' in rendered
    assert any('Approved Alpha' in line for line in rendered)
    assert any('Selector:' in line and 'alpha-run' in line for line in rendered)
    assert any('Access:' in line and 'local' in line for line in rendered)
    assert any('Workflow:' in line and 'manual-register' in line for line in rendered)
    assert any('Records:' in line and '12' in line for line in rendered)
    assert 'guidance:' in rendered
    assert '  choose a number to load an approved dataset into the wizard' in rendered


def test_ds_wizard_dataset_picker_supports_numbered_open_and_apply(monkeypatch, tmp_path: Path) -> None:
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'picker_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    register_librarian_dataset_packet(
        anchor,
        manifest_path,
        access_class='local',
        display_name='Picker Alpha',
        run_id='picker-alpha-run',
    )
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)

    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'model')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'datasets')

    assert packet is None
    assert should_exit is False
    assert state.transient_view == 'picker'
    assert any('Picker Alpha' in line for line in observerctl_module._ds_wizard_render(state))

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '1')

    assert packet is None
    assert should_exit is False
    assert state.values['dataset_manifest'] == str(manifest_path)
    assert state.values['features_csv'] == str(features_csv)
    assert state.values['labels_csv'] == str(labels_csv)
    assert state.hydrated_from['dataset_manifest'] == 'librarian_dataset'


def test_ds_wizard_hydrate_dataset_selector_releases_protected_dataset(monkeypatch, tmp_path: Path) -> None:
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'protected_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    register_librarian_dataset_packet(
        anchor,
        manifest_path,
        access_class='protected-source',
        display_name='Protected Alpha',
        run_id='protected-alpha-run',
    )
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    state = observerctl_module._ds_wizard_new_state('evaluate')
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'hydrate dataset 1')

    assert packet is None
    assert should_exit is False
    assert state.values['dataset_manifest'] == str(manifest_path)
    assert state.values['features_csv'] == str(features_csv)
    assert state.values['labels_csv'] == str(labels_csv)
    assert state.hydrated_from['dataset_manifest'] == 'librarian_dataset'
    lines = observerctl_module._ds_wizard_transient_lines(state)
    assert lines == ['dataset loaded']
    access_receipts = sorted((project_root / 'local_untracked' / 'analysis' / 'indexes' / 'dataset_access').rglob('release_receipt.json'))
    assert access_receipts


def test_ds_wizard_hydrate_dataset_selector_attaches_baseline_context(monkeypatch, tmp_path: Path) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    reviewed_canary_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_canary_hydrate_window_001',
        display_name='Reviewed Canary Hydrate Alpha',
        run_id='reviewed-canary-hydrate-window-001',
        source='real',
        mode='canary',
        recorded_at_utc='2026-04-13T00:30:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    live_entry, manifest_path, features_csv, labels_csv = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='live_hydrate_target_window_001',
        display_name='Live Hydrate Target Alpha',
        run_id='live-hydrate-target-window-001',
        source='real',
        mode='live',
        recorded_at_utc='2026-04-13T00:35:00Z',
        workflow='manual-register',
    )
    review_policy_packet = project_root / 'local_untracked' / 'reports' / 'hydrate_review_policy_packet.md'
    review_policy_packet.parent.mkdir(parents=True, exist_ok=True)
    review_policy_packet.write_text('# hydrate review policy\n', encoding='utf-8')
    emitted_baseline = observerctl_module._ds_emit_comparison_baseline_packet(
        reviewed_canary_entry,
        baseline_stage='canary_reviewed',
        companion_role='bounded reviewed canary hydrate companion',
        review_policy_packet=str(review_policy_packet),
    )
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    state = observerctl_module._ds_wizard_new_state('evaluate')
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'hydrate dataset 1')

    assert packet is None
    assert should_exit is False
    assert state.values['dataset_manifest'] == str(manifest_path)
    assert state.values['features_csv'] == str(features_csv)
    assert state.values['labels_csv'] == str(labels_csv)
    assert live_entry['run_id'] == 'live-hydrate-target-window-001'
    assert state.values['baseline_window_id'] == 'reviewed-canary-hydrate-window-001'
    assert state.values['baseline_analysis_packet'] == _resolve_reported_path(emitted_baseline['packet_path']).__str__()
    assert state.hydrated_from['dataset_manifest'] == 'librarian_dataset'
    assert state.hydrated_from['baseline_window_id'] == 'librarian_dataset'
    assert state.hydrated_from['baseline_analysis_packet'] == 'librarian_dataset'
    lines = observerctl_module._ds_wizard_transient_lines(state)
    assert lines == ['dataset loaded; baseline context attached']


def test_librarian_dataset_cli_register_list_and_release(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'cli_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 3,
        'has_labels': True,
    }), encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    rc = main([
        'librarian',
        'dataset-register',
        str(manifest_path),
        '--access-class', 'protected-source',
        '--display-name', 'CLI Protected Alpha',
        '--run-id', 'cli-alpha-run',
        '--json',
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-dataset-register'
    assert payload['dataset']['display_name'] == 'CLI Protected Alpha'

    rc = main(['librarian', 'datasets', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-datasets'
    assert payload['count'] == 1
    assert payload['selector_entries'][0]['run_id'] == 'cli-alpha-run'

    rc = main(['librarian', 'dataset-release', '1', '--requester-id', 'test-suite', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-dataset-release'
    assert payload['release_mode'] == 'protected-source'
    assert payload['dataset_manifest_path'].endswith('dataset_manifest.json')
    assert payload['artifacts']['dataset_access_request_json'].endswith('request.json')
    assert payload['artifacts']['dataset_access_attestation_json'].endswith('attestation.json')
    assert payload['artifacts']['dataset_access_release_receipt_json'].endswith('release_receipt.json')


def test_librarian_dataset_human_list_surfaces_sectioned_output(monkeypatch, tmp_path: Path, capsys) -> None:
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'human_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 7,
        'has_labels': True,
    }), encoding='utf-8')

    register_librarian_dataset_packet(
        anchor,
        manifest_path,
        access_class='local',
        display_name='Human Alpha',
        run_id='human-alpha-run',
    )
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)

    rc = main(['librarian', 'datasets'])

    assert rc == 0
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Librarian datasets'
    assert 'Summary' in rendered
    assert 'Approved datasets' in rendered
    assert any('1. Human Alpha' in line for line in rendered)
    assert any('Selector:' in line and 'human-alpha-run' in line for line in rendered)
    assert any('Access:' in line and 'local' in line for line in rendered)
    assert any('Records:' in line and '7' in line for line in rendered)
    assert 'Evidence' in rendered
    assert 'Guidance' in rendered


def test_librarian_dataset_list_and_release_ignore_run_refresh_contamination(monkeypatch, tmp_path: Path, capsys) -> None:
    from calamum_librarian import _build_dataset_entry, _dataset_catalog_paths, _save_dataset_snapshot

    project_root, anchor = _make_temp_observer_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'authority_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n1,0.25\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    admitted = _build_dataset_entry(
        anchor,
        manifest_path,
        access_class='local',
        display_name='Authority Alpha',
        run_id='authority-alpha',
        workflow='manual-register',
        recorded_at_utc='2026-04-02T00:00:00Z',
        registration_kind='manual-register',
        source_binding='manual-register:dataset_manifest.json',
    )
    contaminated = dict(admitted)
    contaminated.update({
        'entry_id': 'dataset-build-20260401',
        'display_name': 'Build Drift',
        'run_id': 'build_20260401T203055450331Z',
        'workflow': 'build',
        'registration_kind': 'run-refresh',
        'source_binding': 'run-manifest:build_20260401T203055450331Z',
        'report_manifest_ref': 'C:/Users/tester/AppData/Local/Temp/pytest-of-user/report_manifest.json',
    })

    paths = _dataset_catalog_paths(anchor)
    _save_dataset_snapshot(paths, [contaminated, admitted])

    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)

    rc = main(['librarian', 'dataset', 'list', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['count'] == 1
    assert payload['selector_entries'][0]['run_id'] == 'authority-alpha'

    rc = main(['librarian', 'dataset', 'release', 'build_20260401T203055450331Z', '--json'])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert 'critical_check_failed:librarian_dataset_not_found' in payload['reason_codes']

    rc = main(['librarian', 'dataset', 'release', '1', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['dataset']['run_id'] == 'authority-alpha'
    assert payload['release_mode'] == 'local'


def test_librarian_dataset_release_human_surfaces_evidence_and_guidance(monkeypatch, tmp_path: Path, capsys) -> None:
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'human_protected_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 5,
        'has_labels': True,
    }), encoding='utf-8')

    register_librarian_dataset_packet(
        anchor,
        manifest_path,
        access_class='protected-source',
        display_name='Human Protected Alpha',
        run_id='human-protected-alpha-run',
    )
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    rc = main(['librarian', 'dataset-release', '1', '--requester-id', 'human-suite'])

    assert rc == 0
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Librarian dataset release'
    assert 'Summary' in rendered
    assert 'Dataset' in rendered
    assert any('Human Protected Alpha' in line for line in rendered)
    assert any('Release mode:' in line and 'protected-source' in line for line in rendered)
    assert 'Evidence' in rendered
    assert any('Release receipt:' in line for line in rendered)
    assert any('Dataset manifest:' in line for line in rendered)
    assert 'Guidance' in rendered


def test_librarian_dataset_release_human_denial_surfaces_reasons_and_guidance(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)

    rc = main(['librarian', 'dataset-release', 'missing-selector', '--requester-id', 'human-suite'])

    assert rc == 2
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Librarian dataset release'
    assert 'Reasons' in rendered
    assert any('critical_check_failed:librarian_dataset_not_found' in line for line in rendered)
    assert 'Guidance' in rendered
    assert any('review observerctl librarian dataset list' in line for line in rendered)


def test_librarian_nested_cli_dataset_and_vault_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'nested_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 2,
        'has_labels': True,
    }), encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.delenv('CALAMUM_DATA_SIGNING_KEY', raising=False)
    monkeypatch.setenv('CALAMUM_REQUESTER_SIGNING_KEY', 'requester-key')
    monkeypatch.setenv('CALAMUM_LIBRARIAN_ATTESTATION_KEY', 'librarian-key')
    monkeypatch.setenv('CALAMUM_SOURCE_RELEASE_KEY', 'source-key')
    monkeypatch.setenv('CALAMUM_LIBRARIAN_VAULT_KEY', 'vault-key')

    rc = main([
        'librarian',
        'dataset',
        'register',
        str(manifest_path),
        '--access-class', 'protected-source',
        '--display-name', 'Nested Alpha',
        '--run-id', 'nested-alpha',
        '--json',
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-dataset-register'

    rc = main(['librarian', 'dataset', 'list', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-datasets'
    assert payload['count'] == 1

    rc = main(['librarian', 'vault', 'status', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-vault-status'
    assert payload['locked'] is True
    assert payload['artifacts']['librarian_vault_baseline_json'].endswith('vault_checksum.json')
    assert payload['integrity']['tracked_file_count'] == 2
    assert payload['managed_surfaces']['authority_file_count'] == 2
    assert payload['managed_surfaces']['integrity_file_count'] == 3
    assert payload['managed_surfaces']['vault_file_count'] == 5
    assert payload['managed_surfaces']['catalog_entry_count'] == 1
    assert payload['managed_surfaces']['approved_selector_entry_count'] == 1

    rc = main(['librarian', 'dataset', 'release', '1', '--requester-id', 'nested-suite', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-dataset-release'
    assert payload['release_mode'] == 'protected-source'

    rc = main(['librarian', 'vault', 'unlock', '--reason', 'maintenance-window', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-vault-unlock'
    assert payload['locked'] is False

    rc = main(['librarian', 'dataset', 'register', str(manifest_path), '--json'])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert 'critical_check_failed:librarian_vault_maintenance_window_open' in payload['reason_codes']

    rc = main(['librarian', 'dataset', 'release', '1', '--requester-id', 'nested-suite', '--json'])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert 'critical_check_failed:librarian_vault_maintenance_window_open' in payload['reason_codes']

    rc = main(['librarian', 'vault', 'lock', '--reason', 'maintenance-complete', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-vault-lock'
    assert payload['locked'] is True

    rc = main(['librarian', 'vault', 'verify', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-vault-verify'
    assert payload['decision'] == 'go'


def test_librarian_store_reports_show_delete_and_purge(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    collections_root = project_root / 'docs' / 'reports' / 'collections'
    vault_quarantine_root = project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'quarantine' / 'tracked_reports' / project_root.name

    can_alpha_collection = collections_root / 'can-alpha' / 'collection'
    can_alpha_processing = collections_root / 'can-alpha' / 'processing' / 'build'
    can_beta_collection = collections_root / 'can-beta' / 'collection'
    can_beta_processing = collections_root / 'can-beta' / 'processing' / 'eval'

    can_alpha_collection.mkdir(parents=True, exist_ok=True)
    can_alpha_processing.mkdir(parents=True, exist_ok=True)
    can_beta_collection.mkdir(parents=True, exist_ok=True)
    can_beta_processing.mkdir(parents=True, exist_ok=True)

    (can_alpha_collection / '20260405T010101000000Z.collection.md').write_text('# alpha\n', encoding='utf-8')
    (can_alpha_processing / '20260405T010101000000Z.build.md').write_text('# alpha build\n', encoding='utf-8')
    (can_beta_collection / '20260405T020202000000Z.collection.md').write_text('# beta\n', encoding='utf-8')
    (can_beta_collection / 'report.md').write_text('# stale beta landing\n', encoding='utf-8')
    (can_beta_processing / '20260405T020202000000Z.eval.md').write_text('# beta eval\n', encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)

    rc = main(['librarian', 'store', 'reports', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-store-reports-show'
    assert payload['count'] == 2
    assert payload['stale_report_md_count'] == 1
    assert {row['collection_alias'] for row in payload['report_collections']} == {'can-alpha', 'can-beta'}

    rc = main(['librarian', 'store', 'reports', '--delete', 'can-alpha', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-store-reports-delete'
    assert payload['delete_alias'] == 'can-alpha'
    assert payload['archived_alias_count'] == 1
    assert payload['republish_required'] is True
    assert not (collections_root / 'can-alpha').exists()
    assert (collections_root / 'can-beta').exists()
    assert _resolve_reported_path(payload['artifacts']['vault_quarantine_manifest_json']).exists()
    assert _resolve_reported_path(payload['artifacts']['publication_control_json']).exists()
    assert _resolve_reported_path(payload['artifacts']['vault_quarantine_root']) == vault_quarantine_root

    rc = main(['librarian', 'store', 'reports', '--purge', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-store-reports-purge'
    assert payload['archived_alias_count'] == 1
    assert payload['republish_required'] is True
    assert payload['report_collections'] == []
    assert collections_root.exists()
    assert list(collections_root.iterdir()) == []
    assert _resolve_reported_path(payload['artifacts']['vault_quarantine_manifest_json']).exists()
    assert _resolve_reported_path(payload['artifacts']['vault_quarantine_root']) == vault_quarantine_root


def test_refresh_tracked_ds_publication_preserves_manual_reference_and_validation_surfaces(tmp_path: Path) -> None:
    from analysis.report_aggregate import refresh_tracked_ds_publication

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _seed_shipped_manual_report_surfaces(project_root)
    reference_doc = project_root / 'docs' / 'reports' / 'reference' / 'GENERATED_REPORT_SURFACES.md'
    validations_root = project_root / 'docs' / 'reports' / 'validations'
    validations_index_path = validations_root / 'INDEX.md'
    apex_md = validations_root / 'APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md'
    apex_html = validations_root / 'APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html'

    reference_doc.write_text(reference_doc.read_text(encoding='utf-8') + '\n<!-- frame-c-reference-sentinel -->\n', encoding='utf-8')
    validations_index_path.write_text(validations_index_path.read_text(encoding='utf-8') + '\n<!-- frame-c-validations-sentinel -->\n', encoding='utf-8')
    apex_md.write_text('# apex validation\n', encoding='utf-8')
    apex_html.write_text('<!DOCTYPE html><html><body>apex validation</body></html>\n', encoding='utf-8')

    publication = refresh_tracked_ds_publication(project_anchor=anchor)
    validations_index = validations_index_path.read_text(encoding='utf-8')
    reference_text = reference_doc.read_text(encoding='utf-8')

    assert publication['decision'] == 'go'
    assert '<!-- frame-c-reference-sentinel -->' in reference_text
    assert '<!-- frame-c-validations-sentinel -->' in validations_index
    assert apex_md.exists()
    assert apex_html.exists()
    assert 'APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md' in validations_index
    assert 'APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html' in validations_index


def test_librarian_store_reports_purge_clears_saved_selector_authority_and_resets_aggregate_files(monkeypatch, tmp_path: Path, capsys) -> None:
    from analysis.report_aggregate import refresh_tracked_ds_publication

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _seed_shipped_manual_report_surfaces(project_root)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    vault_quarantine_root = project_root / 'local_untracked' / 'analysis' / 'vaults' / 'librarian' / 'quarantine' / 'tracked_reports' / project_root.name

    dataset_dir = project_root / 'saved' / 'dataset'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    train_dir = project_root / 'saved' / 'model'
    train_dir.mkdir(parents=True, exist_ok=True)
    model_path = train_dir / 'model.pkl'
    train_manifest = train_dir / 'train_manifest.json'
    model_path.write_bytes(b'model')
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(model_path),
        'model_type': 'unsupervised',
    }), encoding='utf-8')
    _append_saved_ds_manifest(
        anchor,
        'train',
        'purge-train-001',
        timestamp_utc='2026-04-06T16:00:00Z',
        artifact_paths={
            'train_manifest': train_manifest,
            'model_path': model_path,
            'dataset_manifest': dataset_manifest,
        },
        context={'source': 'real', 'mode': 'canary'},
        summary='Saved train selector for purge regression.',
    )

    evaluation_dir = project_root / 'saved' / 'evaluation'
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    run_json = evaluation_dir / 'run.json'
    run_md = evaluation_dir / 'run.md'
    run_json.write_text(json.dumps({
        'identity': {'run_id': 'purge-eval-001'},
        'context': {'constraints': {'max_fpr': 0.02}},
        'data': {
            'dataset_manifest': str(dataset_manifest),
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
        },
        'model': {'source': str(model_path)},
    }), encoding='utf-8')
    run_md.write_text('# saved eval\n', encoding='utf-8')
    _append_saved_ds_manifest(
        anchor,
        'evaluate',
        'purge-eval-001',
        timestamp_utc='2026-04-06T16:05:00Z',
        artifact_paths={
            'run_json': run_json,
            'run_md': run_md,
        },
        context={'source': 'real', 'mode': 'canary', 'max_fpr': 0.02},
        lineage={'dataset_manifest': dataset_manifest},
        summary='Saved run selector for purge regression.',
    )

    publication = refresh_tracked_ds_publication(project_anchor=anchor)
    collections_root = project_root / 'docs' / 'reports' / 'collections'
    aggregates_root = project_root / 'docs' / 'reports' / 'aggregates'
    reference_root = project_root / 'docs' / 'reports' / 'reference'
    validations_root = project_root / 'docs' / 'reports' / 'validations'
    indexes_root = project_root / 'local_untracked' / 'analysis' / 'indexes'
    ledger_path = indexes_root / 'ds_run_index.jsonl'
    latest_index_path = indexes_root / 'ds_latest.json'
    internal_collections_root = indexes_root / 'ds_publication' / 'collections'
    apex_validation_md = validations_root / 'APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md'
    apex_validation_html = validations_root / 'APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html'

    validations_root.mkdir(parents=True, exist_ok=True)
    apex_validation_md.write_text('# apex validation\n', encoding='utf-8')
    apex_validation_html.write_text('<!DOCTYPE html><html><body>apex validation</body></html>\n', encoding='utf-8')

    assert publication['published_run_count'] == 2
    assert observerctl_module._ds_saved_train_entries()
    assert observerctl_module._ds_saved_run_entries()
    assert collections_root.exists()
    assert any(collections_root.iterdir())
    assert internal_collections_root.exists()
    assert any(internal_collections_root.iterdir())
    assert (aggregates_root / 'AGGREGATE_REPORT.md').exists()

    rc = main(['librarian', 'store', 'reports', '--purge', '--json'])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-store-reports-purge'
    assert payload['archived_alias_count'] >= 1
    assert payload['archived_auxiliary_count'] == 3
    assert payload['republish_required'] is True
    assert payload['report_collections'] == []
    assert _resolve_reported_path(payload['artifacts']['vault_quarantine_root']) == vault_quarantine_root
    assert _resolve_reported_path(payload['artifacts']['vault_quarantine_manifest_json']).exists()
    assert _resolve_reported_path(payload['artifacts']['librarian_vault_baseline_json']).exists()
    assert _resolve_reported_path(payload['artifacts']['librarian_vault_audit_jsonl']).exists()

    assert observerctl_module._ds_saved_train_entries() == []
    assert observerctl_module._ds_saved_run_entries() == []

    assert collections_root.exists()
    assert list(collections_root.iterdir()) == []
    assert internal_collections_root.exists()
    assert list(internal_collections_root.iterdir()) == []

    assert ledger_path.exists()
    assert ledger_path.read_text(encoding='utf-8') == ''
    latest_payload = json.loads(latest_index_path.read_text(encoding='utf-8'))
    assert latest_payload['latest_run'] == {}
    assert latest_payload['by_workflow'] == {}

    publication_control_path = _resolve_reported_path(payload['artifacts']['publication_control_json'])
    publication_control_payload = json.loads(publication_control_path.read_text(encoding='utf-8'))
    assert publication_control_payload['republish_required'] is True

    aggregate_report_md = aggregates_root / 'AGGREGATE_REPORT.md'
    latest_collections_md = aggregates_root / 'LATEST_COLLECTIONS.md'
    generated_surfaces_md = reference_root / 'GENERATED_REPORT_SURFACES.md'
    publication_index_md = project_root / 'docs' / 'reports' / 'INDEX.md'
    validations_index_md = validations_root / 'INDEX.md'
    archived_reports_root = vault_quarantine_root / next(path.name for path in vault_quarantine_root.iterdir() if path.is_dir()) / 'docs' / 'reports'

    assert aggregate_report_md.exists()
    assert latest_collections_md.exists()
    assert generated_surfaces_md.exists()
    assert publication_index_md.exists()
    assert validations_index_md.exists()
    assert apex_validation_md.exists()
    assert apex_validation_html.exists()
    assert (archived_reports_root / 'aggregates' / 'AGGREGATE_REPORT.md').exists()
    assert (archived_reports_root / 'INDEX.md').exists()
    assert not (archived_reports_root / 'reference' / generated_surfaces_md.name).exists()
    assert not (archived_reports_root / 'validations' / apex_validation_md.name).exists()
    assert not (archived_reports_root / 'validations' / apex_validation_html.name).exists()
    assert 'No published packets are available yet.' in aggregate_report_md.read_text(encoding='utf-8')
    assert '- Latest run: none published yet' in latest_collections_md.read_text(encoding='utf-8')
    assert 'Zero-state publication may leave `docs/reports/collections/` present but empty' in generated_surfaces_md.read_text(encoding='utf-8')
    assert 'No published collections are available yet.' in publication_index_md.read_text(encoding='utf-8')
    assert 'APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md' in validations_index_md.read_text(encoding='utf-8')
    assert 'APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html' in validations_index_md.read_text(encoding='utf-8')


def test_librarian_store_reports_delete_blocks_automatic_republish_until_explicit_restore(monkeypatch, tmp_path: Path, capsys) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-delete-blocked')
    evaluation_dir = bundle.artifact_dirs['evaluation']
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    run_json = evaluation_dir / 'run.json'
    run_md = evaluation_dir / 'run.md'
    run_json.write_text('{}\n', encoding='utf-8')
    run_md.write_text('# eval\n', encoding='utf-8')
    report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-04-06T18:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Evaluation completed through observerctl ds.',
            'run_id': bundle.run_id,
            'collection_alias': 'can-delete-blocked',
            'threshold': 0.42,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': run_json,
            'run_md': run_md,
        },
        context={'max_fpr': 0.01},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=report_bundle['manifest'])

    keep_bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-delete-keep')
    keep_eval_dir = keep_bundle.artifact_dirs['evaluation']
    keep_eval_dir.mkdir(parents=True, exist_ok=True)
    keep_run_json = keep_eval_dir / 'run.json'
    keep_run_md = keep_eval_dir / 'run.md'
    keep_run_json.write_text('{}\n', encoding='utf-8')
    keep_run_md.write_text('# keep eval\n', encoding='utf-8')
    keep_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=keep_bundle,
        packet={
            'timestamp_utc': '2026-04-06T18:10:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Evaluation kept through observerctl ds.',
            'run_id': keep_bundle.run_id,
            'collection_alias': 'can-keep',
            'threshold': 0.43,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': keep_run_json,
            'run_md': keep_run_md,
        },
        context={'max_fpr': 0.02},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=keep_report_bundle['manifest'])

    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=keep_report_bundle['manifest'])
    aggregates_root = project_root / 'docs' / 'reports' / 'aggregates'
    aggregate_report_md = aggregates_root / 'AGGREGATE_REPORT.md'
    public_run_ledger_md = aggregates_root / 'PUBLIC_RUN_LEDGER.md'
    latest_collections_md = aggregates_root / 'LATEST_COLLECTIONS.md'

    assert publication['decision'] == 'go'
    assert (project_root / 'docs' / 'reports' / 'collections' / 'can-delete-blocked').exists()
    assert (project_root / 'docs' / 'reports' / 'collections' / 'can-keep').exists()

    rc = main(['librarian', 'store', 'reports', '--delete', 'can-delete-blocked', '--json'])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'librarian-store-reports-delete'
    assert payload['republish_required'] is True
    assert not (project_root / 'docs' / 'reports' / 'collections' / 'can-delete-blocked').exists()
    assert (project_root / 'docs' / 'reports' / 'collections' / 'can-keep').exists()
    assert _resolve_reported_path(payload['artifacts']['aggregate_report_md']).exists()
    assert _resolve_reported_path(payload['artifacts']['public_run_ledger_md']).exists()

    aggregate_report_text = aggregate_report_md.read_text(encoding='utf-8')
    public_run_ledger_text = public_run_ledger_md.read_text(encoding='utf-8')
    latest_collections_text = latest_collections_md.read_text(encoding='utf-8')

    assert 'can-delete-blocked' not in aggregate_report_text
    assert 'can-delete-blocked' not in latest_collections_text
    assert 'can-keep' in aggregate_report_text
    assert 'can-keep' in latest_collections_text
    assert '| `can-keep` |' in public_run_ledger_text
    assert '## Librarian vault inventory' in public_run_ledger_text
    assert 'archive-and-delete-report-collection' in public_run_ledger_text
    assert 'can-delete-blocked' in public_run_ledger_text

    skipped_publication = refresh_tracked_ds_publication(project_anchor=anchor)

    assert skipped_publication['decision'] == 'skipped'
    assert skipped_publication['reason_codes'] == ['publication_skipped:republish_required']
    assert not (project_root / 'docs' / 'reports' / 'collections' / 'can-delete-blocked').exists()
    assert (project_root / 'docs' / 'reports' / 'collections' / 'can-keep').exists()


def test_ds_finalize_run_packet_publishes_current_build_under_republish_gate_without_reviving_deleted_history(monkeypatch, tmp_path: Path, capsys) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _seed_shipped_manual_report_surfaces(project_root)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    def _append_build_report_bundle(run_id: str, timestamp_utc: str, collection_alias: str) -> dict:
        bundle = prepare_report_bundle(anchor, 'build', run_id=run_id)
        dataset_dir = bundle.artifact_dirs['dataset']
        dataset_dir.mkdir(parents=True, exist_ok=True)
        dataset_manifest = dataset_dir / 'dataset_manifest.json'
        features_csv = dataset_dir / 'features.csv'
        features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
        dataset_manifest.write_text(json.dumps({
            'features_csv': str(features_csv),
            'total_records': 1,
            'has_labels': False,
        }), encoding='utf-8')
        report_bundle = write_report_bundle(
            project_anchor=anchor,
            bundle=bundle,
            packet={
                'timestamp_utc': timestamp_utc,
                'runtime_cli_surface': 'observerctl',
                'decision': 'go',
                'action': 'ds-build',
                'command_family': 'ds',
                'command_path': 'observerctl ds build',
                'implementation_state': 'command-available',
                'underlying_surface': 'analysis.dataset_builder',
                'summary': 'Dataset built through observerctl ds.',
                'run_id': bundle.run_id,
                'collection_alias': collection_alias,
                'artifacts': {},
                'reason_codes': [],
            },
            artifact_paths={
                'dataset_manifest': dataset_manifest,
                'features_csv': features_csv,
            },
            context={'output_override': False},
        )
        append_ds_run_index(project_anchor=anchor, manifest_payload=report_bundle['manifest'])
        return report_bundle

    deleted_report_bundle = _append_build_report_bundle(
        'build-delete-blocked',
        '2026-04-06T18:00:00Z',
        'can-delete-blocked',
    )
    keep_report_bundle = _append_build_report_bundle(
        'build-keep',
        '2026-04-06T18:10:00Z',
        'can-keep',
    )

    initial_publication = refresh_tracked_ds_publication(
        project_anchor=anchor,
        current_manifest_payload=keep_report_bundle['manifest'],
    )

    assert initial_publication['decision'] == 'go'
    assert (project_root / 'docs' / 'reports' / 'collections' / 'can-delete-blocked').exists()
    assert (project_root / 'docs' / 'reports' / 'collections' / 'can-keep').exists()

    rc = main(['librarian', 'store', 'reports', '--delete', 'can-delete-blocked', '--json'])

    assert rc == 0
    delete_payload = json.loads(capsys.readouterr().out)
    assert delete_payload['republish_required'] is True
    assert not (project_root / 'docs' / 'reports' / 'collections' / 'can-delete-blocked').exists()
    assert (project_root / 'docs' / 'reports' / 'collections' / 'can-keep').exists()

    fresh_bundle = prepare_report_bundle(anchor, 'build', run_id='build-fresh')
    fresh_dataset_dir = fresh_bundle.artifact_dirs['dataset']
    fresh_dataset_dir.mkdir(parents=True, exist_ok=True)
    fresh_dataset_manifest = fresh_dataset_dir / 'dataset_manifest.json'
    fresh_features_csv = fresh_dataset_dir / 'features.csv'
    fresh_features_csv.write_text('record_id,feature\n1,0.2\n', encoding='utf-8')
    fresh_dataset_manifest.write_text(json.dumps({
        'features_csv': str(fresh_features_csv),
        'total_records': 1,
        'has_labels': False,
    }), encoding='utf-8')

    final_packet = observerctl_module._ds_finalize_run_packet(
        {
            'timestamp_utc': '2026-04-06T18:20:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset built through observerctl ds.',
            'run_id': fresh_bundle.run_id,
            'collection_alias': 'can-fresh',
            'artifacts': {},
            'reason_codes': [],
        },
        bundle=fresh_bundle,
        artifact_paths={
            'dataset_manifest': fresh_dataset_manifest,
            'features_csv': fresh_features_csv,
        },
        context={'output_override': False},
        lineage={},
    )

    latest_collections_text = (project_root / final_packet['artifacts']['tracked_ds_latest_md']).read_text(encoding='utf-8')

    assert final_packet['decision'] == 'go'
    assert final_packet['publication']['decision'] == 'go'
    assert final_packet['publication']['republish_required'] is True
    assert final_packet['publication']['published_run_count'] == 2
    assert final_packet['publication']['current_run']['collection_alias'] == 'can-fresh'
    assert (project_root / 'docs' / 'reports' / 'collections' / 'can-keep').exists()
    assert (project_root / 'docs' / 'reports' / 'collections' / 'can-fresh').exists()
    assert not (project_root / 'docs' / 'reports' / 'collections' / 'can-delete-blocked').exists()
    assert _resolve_reported_path(final_packet['artifacts']['published_report_md']).exists()
    assert '`can-fresh`' in latest_collections_text
    assert 'can-delete-blocked' not in latest_collections_text


def test_librarian_store_reports_republish_rebuilds_publication_after_reset_gate(monkeypatch, tmp_path: Path, capsys) -> None:
    from analysis.report_aggregate import refresh_tracked_ds_publication
    from calamum_librarian import dataset_display_alias_for_manifest

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    dataset_dir = project_root / 'saved' / 'dataset'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    train_dir = project_root / 'saved' / 'model'
    train_dir.mkdir(parents=True, exist_ok=True)
    model_path = train_dir / 'model.pkl'
    train_manifest = train_dir / 'train_manifest.json'
    model_path.write_bytes(b'model')
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(model_path),
        'model_type': 'unsupervised',
    }), encoding='utf-8')

    rc = main(['librarian', 'store', 'reports', '--purge', '--json'])

    assert rc == 0
    purge_payload = json.loads(capsys.readouterr().out)
    assert purge_payload['action'] == 'librarian-store-reports-purge'
    assert purge_payload['republish_required'] is True

    _append_saved_ds_manifest(
        anchor,
        'train',
        'republish-train-001',
        timestamp_utc='2026-04-06T16:00:00Z',
        artifact_paths={
            'train_manifest': train_manifest,
            'model_path': model_path,
            'dataset_manifest': dataset_manifest,
        },
        context={'source': 'real', 'mode': 'canary'},
        summary='Saved train selector for explicit republish regression.',
    )

    skipped_publication = refresh_tracked_ds_publication(project_anchor=anchor)
    collections_root = project_root / 'docs' / 'reports' / 'collections'

    assert skipped_publication['decision'] == 'skipped'
    assert skipped_publication['reason_codes'] == ['publication_skipped:republish_required']
    assert skipped_publication['republish_required'] is True
    assert collections_root.exists()
    assert list(collections_root.iterdir()) == []

    rc = main(['librarian', 'store', 'reports', '--republish', '--json'])

    assert rc == 0
    republish_payload = json.loads(capsys.readouterr().out)
    collection_alias = dataset_display_alias_for_manifest(anchor, dataset_manifest)
    alias_root = collections_root / collection_alias

    assert republish_payload['action'] == 'librarian-store-reports-republish'
    assert republish_payload['published_run_count'] == 1
    assert republish_payload['count'] == 1
    assert republish_payload['republish_required'] is False
    assert republish_payload['current_run_id'] == ''
    assert republish_payload['report_collections'][0]['collection_alias'] == collection_alias
    assert alias_root.exists()
    assert (alias_root / 'collection').exists()
    assert (alias_root / 'processing' / 'train').exists()

    rc = main(['librarian', 'store', 'reports', '--json'])

    assert rc == 0
    show_payload = json.loads(capsys.readouterr().out)
    assert show_payload['count'] == 1
    assert show_payload['republish_required'] is False
    assert show_payload['report_collections'][0]['collection_alias'] == collection_alias


def test_librarian_store_reports_human_show_surfaces_sections(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    collection_dir = project_root / 'docs' / 'reports' / 'collections' / 'can-human' / 'collection'
    processing_dir = project_root / 'docs' / 'reports' / 'collections' / 'can-human' / 'processing' / 'score'
    collection_dir.mkdir(parents=True, exist_ok=True)
    processing_dir.mkdir(parents=True, exist_ok=True)
    (collection_dir / '20260405T030303000000Z.collection.md').write_text('# human\n', encoding='utf-8')
    (processing_dir / '20260405T030303000000Z.score.md').write_text('# human score\n', encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)

    rc = main(['librarian', 'store', 'reports', '--show'])
    assert rc == 0
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Librarian store reports'
    assert 'Summary' in rendered
    assert 'Collections' in rendered
    assert any('can-human' in line for line in rendered)
    assert 'Evidence' in rendered
    assert 'Guidance' in rendered


def test_ds_wizard_command_surface_supports_run_hydration_and_draft_round_trip(tmp_path: Path) -> None:
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    model_path = tmp_path / 'model.pkl'
    run_json = tmp_path / 'run.json'
    draft_path = tmp_path / 'wizard_draft.json'

    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
    }), encoding='utf-8')
    run_json.write_text(json.dumps({
        'identity': {'run_id': 'frame6-command-ledger'},
        'context': {'constraints': {'max_fpr': 0.015}},
        'data': {
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
            'dataset_manifest': str(dataset_manifest),
        },
        'model': {'source': str(model_path)},
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('evaluate')
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'hydrate run {0}'.format(run_json))
    assert packet is None
    assert should_exit is False
    assert state.values['run_id'] == 'frame6-command-ledger'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'save draft {0}'.format(draft_path))
    assert packet is None
    assert should_exit is False
    assert draft_path.exists()

    restored = observerctl_module._ds_wizard_new_state('evaluate')
    restored, packet, should_exit = observerctl_module._ds_wizard_handle_command(restored, 'load draft {0}'.format(draft_path))
    assert packet is None
    assert should_exit is False
    assert restored.values['run_id'] == 'frame6-command-ledger'
    assert restored.values['max_fpr'] == 0.015
    assert restored.draft_path == str(draft_path)


def test_ds_wizard_command_surface_drops_save_next_draft_menu_copy() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'cmd')

    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(state)

    assert not any('1. load saved draft' in line for line in rendered)
    assert not any('2. latest saved context' in line for line in rendered)
    assert not any('save next draft' in line for line in rendered)
    assert not any('persist current state to the next canonical slot' in line for line in rendered)
    assert not any('Direct save/load/hydrate file-path commands remain available outside the default guided lane.' in line for line in rendered)


def test_ds_wizard_wide_render_keeps_workflow_items_aligned_with_color(monkeypatch) -> None:
    from observerctl_terminal import strip_ansi

    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('OBSERVERCTL_COLOR', 'always')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_get_terminal_width', lambda: 120)

    state = observerctl_module._ds_wizard_new_state('')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'configure')
    rendered = observerctl_module._ds_wizard_render(state)

    build_line = next(line for line in rendered if '1. ' in line and 'build' in line)
    pipeline_line = next(line for line in rendered if '5. ' in line and 'run-pipeline' in line)
    advanced_line = next(line for line in rendered if '6. ' in line and 'advanced' in line)

    build_col = strip_ansi(build_line).index('1. ')
    pipeline_col = strip_ansi(pipeline_line).index('5. ')
    advanced_col = strip_ansi(advanced_line).index('6. ')

    assert build_col == pipeline_col == advanced_col


def test_ds_wizard_wide_render_separates_left_rail_and_right_pane_blocks(monkeypatch) -> None:
    from observerctl_terminal import strip_ansi

    monkeypatch.setenv('NO_COLOR', '1')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_get_terminal_width', lambda: 120)

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_set_value(state, 'max_fpr', 0.05)
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'configure')
    rendered = observerctl_module._ds_wizard_render(state)
    plain = [strip_ansi(line) for line in rendered]

    left_rail_width = 25
    left_col_texts = []
    right_col_texts = []
    for line in plain:
        left_part = line[:left_rail_width].strip()
        right_part = line[left_rail_width:].strip() if len(line) > left_rail_width else ''
        if left_part:
            left_col_texts.append(left_part)
        if right_part:
            right_col_texts.append(right_part)

    left_joined = ' '.join(left_col_texts)
    right_joined = ' '.join(right_col_texts)

    assert 'workflow:' in left_joined
    assert 'validate:' in left_joined
    assert 'advance:' in left_joined
    assert 'family:' in left_joined
    assert 'Menu' in left_joined

    assert 'path:' in right_joined
    assert 'dataset:' in right_joined
    assert 'source:' in right_joined
    assert 'mode:' in right_joined
    assert 'supervised' not in left_joined
    assert 'sim' not in right_joined
    assert 'watch' not in right_joined

    assert 'dataset:' not in left_joined
    assert 'source:' not in left_joined
    assert 'mode:' not in left_joined


def test_ds_wizard_forced_color_styles_only_breadcrumb_tail(monkeypatch) -> None:
    from observerctl_terminal import strip_ansi, style_heading

    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('OBSERVERCTL_COLOR', 'always')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_get_terminal_width', lambda: 90)

    state = observerctl_module._ds_wizard_new_state('build')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'configure')
    rendered = observerctl_module._ds_wizard_render(state)
    path_line = next(line for line in rendered if line.startswith('path: '))

    assert strip_ansi(path_line) == 'path: ds wizard > configure > flow'
    assert path_line == 'path: ds wizard > configure > {0}'.format(style_heading('flow'))


def test_ds_saved_selector_commands_and_wizard_hydration(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    log_dir = tmp_path / 'logs'
    (log_dir / 'health').mkdir(parents=True, exist_ok=True)
    (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
    (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    dataset_dir = project_root / 'saved' / 'dataset'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    model_dir = project_root / 'saved' / 'model'
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / 'model.pkl'
    train_manifest = model_dir / 'train_manifest.json'
    model_path.write_bytes(b'model')
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(model_path),
        'model_type': 'unsupervised',
    }), encoding='utf-8')
    _append_saved_ds_manifest(
        anchor,
        'train',
        'selector-train-001',
        timestamp_utc='2026-03-31T12:00:00Z',
        artifact_paths={
            'train_manifest': train_manifest,
            'model_path': model_path,
            'dataset_manifest': dataset_manifest,
        },
        context={'source': 'real', 'mode': 'canary'},
        summary='Retained train selector fixture.',
    )

    evaluation_dir = project_root / 'saved' / 'evaluation'
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    run_json = evaluation_dir / 'run.json'
    run_md = evaluation_dir / 'run.md'
    run_baseline_packet = evaluation_dir / 'baseline.json'
    run_baseline_packet.write_text(json.dumps({
        'baseline_window_id': 'canary-window-001',
    }), encoding='utf-8')
    run_json.write_text(json.dumps({
        'identity': {'run_id': 'selector-eval-001'},
        'context': {'constraints': {'max_fpr': 0.02}},
        'data': {
            'dataset_manifest': str(dataset_manifest),
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
        },
        'model': {'source': str(model_path)},
    }), encoding='utf-8')
    run_md.write_text('# saved run\n', encoding='utf-8')
    _append_saved_ds_manifest(
        anchor,
        'evaluate',
        'selector-eval-001',
        timestamp_utc='2026-03-31T12:05:00Z',
        artifact_paths={
            'run_json': run_json,
            'run_md': run_md,
        },
        context={
            'source': 'real',
            'mode': 'canary',
            'baseline_analysis_packet': str(run_baseline_packet),
            'baseline_window_id': 'canary-window-001',
            'max_fpr': 0.02,
        },
        lineage={'dataset_manifest': dataset_manifest},
        summary='Retained run selector fixture.',
    )

    demo_dir = project_root / 'saved' / 'demo'
    demo_dir.mkdir(parents=True, exist_ok=True)
    demo_run_json = demo_dir / 'run.json'
    demo_run_md = demo_dir / 'run.md'
    demo_supervised_model = demo_dir / 'supervised_model.pkl'
    demo_supervised_train = demo_dir / 'supervised_train_manifest.json'
    demo_unsupervised_model = demo_dir / 'unsupervised_model.pkl'
    demo_unsupervised_train = demo_dir / 'unsupervised_train_manifest.json'
    demo_run_json.write_text(json.dumps({'identity': {'run_id': 'demo-should-hide'}}), encoding='utf-8')
    demo_run_md.write_text('# demo run\n', encoding='utf-8')
    demo_supervised_model.write_bytes(b'supervised')
    demo_unsupervised_model.write_bytes(b'unsupervised')
    demo_supervised_train.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(demo_supervised_model),
        'model_type': 'supervised',
    }), encoding='utf-8')
    demo_unsupervised_train.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(demo_unsupervised_model),
        'model_type': 'unsupervised',
    }), encoding='utf-8')
    _append_saved_ds_manifest(
        anchor,
        'demo',
        'demo-should-hide',
        timestamp_utc='2026-04-04T00:00:00Z',
        artifact_paths={
            'evaluation_run_json': demo_run_json,
            'evaluation_run_md': demo_run_md,
            'supervised_train_manifest': demo_supervised_train,
            'supervised_model_path': demo_supervised_model,
            'unsupervised_train_manifest': demo_unsupervised_train,
            'unsupervised_model_path': demo_unsupervised_model,
            'dataset_manifest': dataset_manifest,
        },
        context={'source': 'real', 'mode': 'canary'},
        summary='Demo selector that should stay hidden.',
    )

    evidence_dir = log_dir / 'data' / 'calamum' / 'observer_derived' / 'real' / 'canary' / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    baseline_packet = evidence_dir / 'observerctl_baseline-analysis_saved.json'
    baseline_packet.write_text(json.dumps({
        'timestamp_utc': '2026-03-31T12:10:00Z',
        'decision': 'go',
        'summary': 'Retained baseline selector fixture.',
        'baseline_window_id': 'canary-window-001',
        'sample_counts': {'resource_normal': 5, 'resource_baseline': 5},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': '2026-03-31T12:10:00Z',
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet).replace('\\', '/'),
        'baseline_window_id': 'canary-window-001',
    }) + '\n', encoding='utf-8')

    reviewed_canary_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_canary_window1',
        display_name='Reviewed Canary Window1',
        run_id='reviewed-canary-window1',
        source='real',
        mode='canary',
        recorded_at_utc='2026-04-13T00:20:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    reviewed_live_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_live_window1',
        display_name='Reviewed Live Window1',
        run_id='reviewed-live-window1',
        source='real',
        mode='live',
        recorded_at_utc='2026-04-13T00:25:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    reviewed_entry, reviewed_manifest, reviewed_features, reviewed_labels = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_honeypot_window1',
        display_name='Reviewed Honeypot Window1',
        run_id='reviewed-honeypot-window1',
        source='real',
        mode='honeypot',
        recorded_at_utc='2026-04-13T00:30:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    review_policy_packet = project_root / 'local_untracked' / 'reports' / 'reviewed_honeypot_policy_packet.md'
    review_policy_packet.parent.mkdir(parents=True, exist_ok=True)
    review_policy_packet.write_text('# reviewed honeypot policy\n', encoding='utf-8')
    emitted_canary_baseline = observerctl_module._ds_emit_comparison_baseline_packet(
        reviewed_canary_entry,
        baseline_stage='canary_reviewed',
        companion_role='bounded reviewed canary companion',
        review_policy_packet=str(review_policy_packet),
    )
    emitted_live_baseline = observerctl_module._ds_emit_comparison_baseline_packet(
        reviewed_live_entry,
        baseline_stage='live_reviewed',
        companion_role='bounded reviewed live companion',
        review_policy_packet=str(review_policy_packet),
    )
    emitted_reviewed_baseline = observerctl_module._ds_emit_comparison_baseline_packet(
        reviewed_entry,
        baseline_stage='honeypot_reviewed',
        companion_role='bounded reviewed honeypot companion',
        review_policy_packet=str(review_policy_packet),
    )

    rc = main(['ds', 'saved', 'trained', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-saved-trained'
    assert payload['command_path'] == 'observerctl ds saved trained'
    assert payload['count'] == 1
    assert payload['selector_entries'][0]['run_id'] == 'selector-train-001'
    assert all(str(entry.get('run_id', '') or '').strip() != 'demo-should-hide' for entry in payload['selector_entries'])

    rc = main(['ds', 'saved', 'runs', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-saved-runs'
    assert payload['command_path'] == 'observerctl ds saved runs'
    assert payload['count'] == 1
    assert payload['selector_entries'][0]['run_id'] == 'selector-eval-001'
    assert all(str(entry.get('run_id', '') or '').strip() != 'demo-should-hide' for entry in payload['selector_entries'])

    rc = main(['ds', 'saved', 'baselines', '--source', 'real', '--mode', 'canary', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-saved-baselines'
    assert payload['command_path'] == 'observerctl ds saved baselines'
    assert payload['count'] == 0

    rc = main(['ds', 'saved', 'baselines', '--source', 'real', '--mode', 'live', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-saved-baselines'
    assert payload['command_path'] == 'observerctl ds saved baselines'
    assert payload['count'] == 1
    assert payload['selector_entries'][0]['baseline_window_id'] == 'reviewed-canary-window1'
    assert payload['selector_entries'][0]['baseline_stage'] == 'canary_reviewed'

    rc = main(['ds', 'saved', 'baselines', '--source', 'real', '--mode', 'honeypot', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-saved-baselines'
    assert payload['command_path'] == 'observerctl ds saved baselines'
    assert payload['count'] == 2
    assert {str(entry.get('baseline_stage', '') or '') for entry in payload['selector_entries']} == {'live_reviewed', 'honeypot_reviewed'}
    assert {str(entry.get('baseline_window_id', '') or '') for entry in payload['selector_entries']} == {'reviewed-live-window1', 'reviewed-honeypot-window1'}

    train_state = observerctl_module._ds_wizard_new_state('score')
    train_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(train_state, 'trained')
    assert packet is None
    assert should_exit is False
    assert 'saved trained:' in observerctl_module._ds_wizard_render(train_state)

    train_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(train_state, 'hydrate train 1')
    assert packet is None
    assert should_exit is False
    assert train_state.values['train_manifest'] == str(train_manifest)
    assert train_state.values['dataset_manifest'] == str(dataset_manifest)
    assert train_state.values['model_path'] == str(model_path)
    assert train_state.hydrated_from['train_manifest'] == 'saved_train'

    train_picker_state = observerctl_module._ds_wizard_new_state('score')
    train_picker_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(train_picker_state, 'trained')
    assert packet is None
    assert should_exit is False
    assert train_picker_state.transient_view == 'picker'
    train_picker_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(train_picker_state, '1')
    assert packet is None
    assert should_exit is False
    assert train_picker_state.values['train_manifest'] == str(train_manifest)
    assert train_picker_state.hydrated_from['train_manifest'] == 'saved_train'

    run_state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_set_value(run_state, 'source', 'real')
    observerctl_module._ds_wizard_set_value(run_state, 'mode', 'canary')

    run_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(run_state, 'runs')
    assert packet is None
    assert should_exit is False
    assert 'saved runs:' in observerctl_module._ds_wizard_render(run_state)

    run_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(run_state, 'hydrate run 1')
    assert packet is None
    assert should_exit is False
    assert run_state.values['run_id'] == 'selector-eval-001'
    assert run_state.values['max_fpr'] == 0.02
    assert run_state.values['baseline_analysis_packet'] == ''
    assert run_state.values['baseline_window_id'] == ''
    assert run_state.hydrated_from['run_id'] == 'saved_run'
    assert 'baseline_analysis_packet' not in run_state.hydrated_from
    assert 'baseline_window_id' not in run_state.hydrated_from

    observerctl_module._ds_wizard_set_value(run_state, 'mode', 'live')
    run_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(run_state, 'baselines')
    assert packet is None
    assert should_exit is False
    assert 'saved baselines:' in observerctl_module._ds_wizard_render(run_state)

    run_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(run_state, 'hydrate baseline 1')
    assert packet is None
    assert should_exit is False
    assert run_state.values['baseline_window_id'] == 'reviewed-canary-window1'
    assert run_state.values['baseline_analysis_packet'] == _resolve_reported_path(emitted_canary_baseline['packet_path']).__str__()
    assert run_state.hydrated_from['baseline_window_id'] == 'saved_baseline'

    observerctl_module._ds_wizard_set_value(run_state, 'mode', 'honeypot')
    run_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(run_state, 'baselines')
    assert packet is None
    assert should_exit is False
    assert 'saved baselines:' in observerctl_module._ds_wizard_render(run_state)

    run_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(run_state, 'hydrate baseline reviewed-live-window1')
    assert packet is None
    assert should_exit is False
    assert run_state.values['baseline_window_id'] == 'reviewed-live-window1'
    assert run_state.values['baseline_analysis_packet'] == _resolve_reported_path(emitted_live_baseline['packet_path']).__str__()
    assert run_state.hydrated_from['baseline_window_id'] == 'saved_baseline'

    report_picker_state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_set_value(report_picker_state, 'source', 'real')
    observerctl_module._ds_wizard_set_value(report_picker_state, 'mode', 'honeypot')
    observerctl_module._ds_wizard_open_section(report_picker_state, 'model')
    report_picker_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(report_picker_state, '1')
    assert packet is None
    assert should_exit is False
    assert report_picker_state.transient_view == 'picker'
    report_picker_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(report_picker_state, 'reviewed-live-window1')
    assert packet is None
    assert should_exit is False
    assert report_picker_state.values['baseline_window_id'] == 'reviewed-live-window1'
    assert report_picker_state.hydrated_from['baseline_window_id'] == 'saved_baseline'


def test_ds_wizard_canonical_draft_slots_and_output_preview(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_set_value(state, 'run_id', 'slot-draft-001')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'save draft')
    assert packet is None
    assert should_exit is False
    assert Path(state.draft_path).name == 'slot-001.json'
    assert Path(state.draft_path).exists()

    rc = main(['ds', 'saved', 'drafts', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-saved-drafts'
    assert payload['command_path'] == 'observerctl ds saved drafts'
    assert payload['count'] == 1
    assert payload['selector_entries'][0]['slot_id'] == 1

    restored = observerctl_module._ds_wizard_new_state('evaluate')
    restored, packet, should_exit = observerctl_module._ds_wizard_handle_command(restored, 'load draft 1')
    assert packet is None
    assert should_exit is False
    assert restored.values['run_id'] == 'slot-draft-001'
    assert Path(restored.draft_path).name == 'slot-001.json'

    list_state = observerctl_module._ds_wizard_new_state('evaluate')
    list_state, packet, should_exit = observerctl_module._ds_wizard_handle_command(list_state, 'drafts')
    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(list_state)
    assert 'saved draft slots:' in rendered
    assert any('slot-001' in line for line in rendered)

    report_state = observerctl_module._ds_wizard_new_state('train')
    observerctl_module._ds_wizard_open_section(report_state, 'report')
    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(report_state)]
    assert 'report:' in rendered
    assert any(line.strip().startswith('report json:') for line in rendered)
    assert any(line.strip().startswith('report md:') for line in rendered)
    assert any(line.strip().startswith('dataset manifest:') for line in rendered)
    assert any(line.strip().startswith('train manifest:') for line in rendered)
    assert any(line.strip().startswith('model artifact:') for line in rendered)
    assert not any('Canonical run root:' in line for line in rendered)
    assert not any('Effective run root:' in line for line in rendered)
    assert not any('Run root mode:' in line for line in rendered)
    assert not any('Input status:' in line for line in rendered)
    assert not any('Dataset status:' in line for line in rendered)
    assert not any('Override note:' in line for line in rendered)
    assert not any('Review the canonical run root, report bundle, and artifact targets before executing.' in line for line in rendered)
    assert '--out-dir' not in observerctl_module._ds_wizard_command_preview(report_state)

    build_report_state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_open_section(build_report_state, 'report')
    build_rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(build_report_state)]
    assert any(line.strip().startswith('report json:') for line in build_rendered)
    assert any(line.strip().startswith('dataset manifest:') for line in build_rendered)
    assert not any('Input status:' in line for line in build_rendered)

    observerctl_module._ds_wizard_set_value(report_state, 'out_dir', str(tmp_path / 'override-root'))
    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(report_state)]
    assert not any('Active override:' in line for line in rendered)

    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    model_path = tmp_path / 'model.pkl'
    run_json = tmp_path / 'run.json'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
    }), encoding='utf-8')
    run_json.write_text(json.dumps({
        'identity': {'run_id': 'report-eval-001'},
        'data': {
            'dataset_manifest': str(dataset_manifest),
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
        },
        'model': {'source': str(model_path)},
    }), encoding='utf-8')

    eval_report_state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_hydrate_run_ledger(eval_report_state, run_json)
    observerctl_module._ds_wizard_open_section(eval_report_state, 'report')
    eval_rendered = [' '.join(strip_ansi(line).split()) for line in observerctl_module._ds_wizard_render(eval_report_state)]
    assert any(line == 'dataset manifest: dataset_manifest.json' for line in eval_rendered)
    assert any(line == 'features csv: features.csv' for line in eval_rendered)
    assert any(line == 'labels csv: labels.csv' for line in eval_rendered)
    assert any(line == 'model artifact: model.pkl' for line in eval_rendered)
    assert any(line == 'run json: run.json' for line in eval_rendered)
    assert not any(str(tmp_path).replace('\\', '/') in line.replace('\\', '/') for line in eval_rendered)

    score_state = observerctl_module._ds_wizard_new_state('score')
    assert '--out-file' not in observerctl_module._ds_wizard_command_preview(score_state)


def test_ds_saved_baselines_materialize_missing_reviewed_packets_for_live_and_honeypot_lanes(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    reviewed_canary_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_canary_window2',
        display_name='Reviewed Canary Window2',
        run_id='reviewed-canary-window2',
        source='real',
        mode='canary',
        recorded_at_utc='2026-04-14T01:20:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    reviewed_live_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_live_window2',
        display_name='Reviewed Live Window2',
        run_id='reviewed-live-window2',
        source='real',
        mode='live',
        recorded_at_utc='2026-04-14T01:25:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    reviewed_honeypot_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_honeypot_window2',
        display_name='Reviewed Honeypot Window2',
        run_id='reviewed-honeypot-window2',
        source='real',
        mode='honeypot',
        recorded_at_utc='2026-04-14T01:30:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )

    canary_packet_path = observerctl_module._ds_comparison_baseline_packet_path(reviewed_canary_entry['entry_id'])
    live_packet_path = observerctl_module._ds_comparison_baseline_packet_path(reviewed_live_entry['entry_id'])
    honeypot_packet_path = observerctl_module._ds_comparison_baseline_packet_path(reviewed_honeypot_entry['entry_id'])
    assert not canary_packet_path.exists()
    assert not live_packet_path.exists()
    assert not honeypot_packet_path.exists()

    live_entries = observerctl_module._ds_saved_baseline_entries('real', 'live')
    honeypot_entries = observerctl_module._ds_saved_baseline_entries('real', 'honeypot')

    assert len(live_entries) == 1
    assert live_entries[0]['baseline_stage'] == 'canary_reviewed'
    assert live_entries[0]['baseline_window_id'] == 'reviewed-canary-window2'
    assert len(honeypot_entries) == 2
    assert {str(entry.get('baseline_stage', '') or '') for entry in honeypot_entries} == {'live_reviewed', 'honeypot_reviewed'}
    assert {str(entry.get('baseline_window_id', '') or '') for entry in honeypot_entries} == {'reviewed-live-window2', 'reviewed-honeypot-window2'}
    assert canary_packet_path.exists()
    assert live_packet_path.exists()
    assert honeypot_packet_path.exists()
    assert {
        _resolve_reported_path(str(entry['resolver']['baseline_analysis_packet']) or '')
        for entry in honeypot_entries
    } == {live_packet_path, honeypot_packet_path}

    rc = main(['ds', 'saved', 'baselines', '--source', 'real', '--mode', 'honeypot', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-saved-baselines'
    assert payload['count'] == 2
    assert {str(entry.get('baseline_stage', '') or '') for entry in payload['selector_entries']} == {'live_reviewed', 'honeypot_reviewed'}


def test_ds_saved_baselines_accept_historical_manual_register_packet_backfill(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    historical_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='historical_honeypot_window1',
        display_name='Historical Honeypot Window1',
        run_id='historical-honeypot-window1',
        source='real',
        mode='honeypot',
        recorded_at_utc='2026-04-14T02:00:00Z',
        workflow='manual-register',
    )
    review_policy_packet = project_root / 'local_untracked' / 'reports' / 'historical_honeypot_policy_packet.md'
    review_policy_packet.parent.mkdir(parents=True, exist_ok=True)
    review_policy_packet.write_text('# historical honeypot policy\n', encoding='utf-8')
    emitted = observerctl_module._ds_emit_comparison_baseline_packet(
        historical_entry,
        baseline_stage='honeypot_reviewed',
        companion_role='historical reviewed honeypot companion',
        review_policy_packet=str(review_policy_packet),
    )

    entries = observerctl_module._ds_saved_baseline_entries('real', 'honeypot')

    assert len(entries) == 1
    assert entries[0]['baseline_stage'] == 'honeypot_reviewed'
    assert entries[0]['baseline_window_id'] == 'historical-honeypot-window1'
    assert _resolve_reported_path(str(entries[0]['resolver']['baseline_analysis_packet']) or '') == _resolve_reported_path(emitted['packet_path'])

    rc = main(['ds', 'saved', 'baselines', '--source', 'real', '--mode', 'honeypot', '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['count'] == 1
    assert payload['selector_entries'][0]['baseline_stage'] == 'honeypot_reviewed'


def test_ds_wizard_partition_headers_render_on_frame3_surfaces() -> None:
    from observerctl_terminal import strip_ansi

    build_state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_open_section(build_state, 'in')
    build_rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(build_state)]

    assert 'load data:' in build_rendered
    assert any('1. simulation (sim)' in line for line in build_rendered)
    assert any('2. collected  (real)' in line for line in build_rendered)
    assert not any('cli-only' in line for line in build_rendered)
    assert not any('telemetry inputs' in line for line in build_rendered)
    assert not any('load configs:' in line for line in build_rendered)
    assert not any('inputs and sources:' in line for line in build_rendered)
    assert not any('optional' in line for line in build_rendered)
    assert not any('navigate:' in line for line in build_rendered)

    eval_state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(eval_state, 'model')
    eval_rendered = observerctl_module._ds_wizard_render(eval_state)

    assert 'load configs:' in eval_rendered
    assert any('load saved baseline' in line for line in eval_rendered)
    assert any('load previous' in line for line in eval_rendered)
    assert any('model artifact' in line for line in eval_rendered)
    assert 'load data:' not in eval_rendered
    assert not any('dataset is displayed in header only; no dataset loader here' in line for line in eval_rendered)
    assert not any('dataset artifact' in line for line in eval_rendered)


def test_ds_wizard_build_in_staged_selector_renders_mode_and_records_pages(monkeypatch, tmp_path: Path) -> None:
    from observerctl_terminal import strip_ansi

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='sim_canary_alpha',
        display_name='Sim Canary Alpha',
        run_id='sim-canary-alpha',
        source='sim',
        mode='canary',
        recorded_at_utc='2026-04-03T00:00:00Z',
        workflow='build',
    )

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_open_section(state, 'in')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '1')
    assert packet is None
    assert should_exit is False
    rendered = [observerctl_module.strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]
    assert any('simulation (sim)' in line for line in rendered)
    assert any('5. all' in line for line in rendered)
    assert any('navigate: date <yyyy-mm-dd>' in line for line in rendered)

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '2')
    assert packet is None
    assert should_exit is False
    rendered = [observerctl_module.strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]
    alias = observerctl_module._ds_wizard_build_in_alias({
        'mode': 'canary',
        'source': 'sim',
        'dataset_manifest_sha256': entry['resolver']['dataset_manifest_sha256'],
    })
    assert any('[ sim | canary ]' in line for line in rendered)
    assert any('page: 1 of 1         total: 1' in line for line in rendered)
    assert any(alias in line and 'build' in line and '2026-04-03' in line for line in rendered)
    assert any('navigate: < | > | page: <page#> | date: <yyyy-mm-dd>' in line for line in rendered)


def test_ds_wizard_build_in_staged_selector_supports_pagination_and_alias_hydration(monkeypatch, tmp_path: Path) -> None:
    from observerctl_terminal import strip_ansi

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    expected_alias = ''
    expected_manifest = None
    expected_features = None
    expected_labels = None
    for idx in range(11):
        entry, manifest_path, features_csv, labels_csv = _seed_librarian_dataset_entry(
            anchor,
            project_root,
            slug='sim_canary_{0:02d}'.format(idx + 1),
            display_name='Sim Canary {0:02d}'.format(idx + 1),
            run_id='sim-canary-{0:02d}'.format(idx + 1),
            source='sim',
            mode='canary',
            recorded_at_utc='2026-04-{0:02d}T00:00:00Z'.format(idx + 1),
            workflow=('train' if idx % 2 else 'build'),
        )
        if idx == 0:
            expected_alias = observerctl_module._ds_wizard_build_in_alias({
                'mode': 'canary',
                'source': 'sim',
                'dataset_manifest_sha256': entry['resolver']['dataset_manifest_sha256'],
            })
            expected_manifest = manifest_path
            expected_features = features_csv
            expected_labels = labels_csv

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_open_section(state, 'in')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'sim')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'canary')

    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]
    assert any('page: 1 of 2         total: 11' in line for line in rendered)

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '>')
    assert packet is None
    assert should_exit is False
    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]
    assert any('page: 2 of 2         total: 11' in line for line in rendered)

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'page 1')
    assert packet is None
    assert should_exit is False
    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]
    assert any('page: 1 of 2         total: 11' in line for line in rendered)

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, expected_alias)
    assert packet is None
    assert should_exit is False
    assert state.values['dataset_manifest'] == str(expected_manifest)
    assert state.values['features_csv'] == str(expected_features)
    assert state.values['labels_csv'] == str(expected_labels)
    assert state.values['dataset_alias'] == expected_alias
    assert state.hydrated_from['dataset_manifest'] == 'librarian_dataset'
    assert state.source == 'sim'
    assert state.mode == 'canary'
    assert strip_ansi(observerctl_module._ds_wizard_right_pane_ops_rows(state)[0]) == 'dataset:  {0}'.format(expected_alias)
    assert observerctl_module._ds_wizard_transient_lines(state) == ['dataset loaded']


def test_ds_wizard_build_in_navigation_footer_only_renders_on_in_surface(monkeypatch, tmp_path: Path) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_open_section(state, 'in')
    state.build_in_stage = 'records'
    state.build_in_family = 'sim'
    state.build_in_mode = 'canary'

    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]
    assert any('navigate: < | > | page: <page#> | date: <yyyy-mm-dd>' in line for line in rendered)

    observerctl_module._ds_wizard_open_section(state, 'report')
    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]
    assert not any('navigate:' in line for line in rendered)


def test_ds_wizard_baseline_surface_explains_optional_empty_live_lane(monkeypatch, tmp_path: Path) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_set_value(state, 'source', 'real')
    observerctl_module._ds_wizard_set_value(state, 'mode', 'live')

    lines = [strip_ansi(line) for line in observerctl_module._ds_wizard_baseline_selector_lines(state)]

    assert observerctl_module._ds_wizard_baseline_picker_current(state) == '<optional: none admitted>'
    assert any('canary_reviewed' in line for line in lines)
    assert any('baseline context remains optional for evaluate and run-pipeline.' in line for line in lines)
    assert any('evaluate can still run without a baseline packet' in line for line in lines)


def test_ds_wizard_build_in_records_rows_keep_spacing_before_date(monkeypatch, tmp_path: Path) -> None:
    from observerctl_terminal import strip_ansi

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='real_canary_spacing_alpha',
        display_name='Real Canary Spacing Alpha',
        run_id='real-canary-spacing-alpha',
        source='real',
        mode='canary',
        recorded_at_utc='2026-04-02T00:00:00Z',
        workflow='manual-register',
    )

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_open_section(state, 'in')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'real')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'canary')

    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]
    record_line = next(line for line in rendered if 'manual-register' in line and '2026-04-02' in line)

    assert 'manual-register  2026-04-02' in record_line


def test_ds_wizard_build_in_filters_legacy_unknown_scope_entries(monkeypatch, tmp_path: Path) -> None:
    from calamum_librarian import _build_dataset_entry, _dataset_catalog_paths, _save_dataset_snapshot

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    dataset_dir = project_root / 'datasets' / 'legacy_scope_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 1,
        'has_labels': False,
        'inputs': [
            {
                'path': str(project_root / 'logs' / 'data' / 'calamum' / 'archive' / 'resource_real_canary_normal_legacy_scope_seg0001.jsonl.gz'),
                'records': 1,
            }
        ],
    }), encoding='utf-8')

    entry = _build_dataset_entry(
        anchor,
        manifest_path,
        access_class='local',
        display_name='Legacy Scope Alpha',
        run_id='legacy-scope-alpha',
        workflow='manual-register',
        recorded_at_utc='2026-04-03T00:00:00Z',
        registration_kind='manual-register',
        source='unknown',
        mode='unknown',
        source_binding='manual-register:dataset_manifest.json',
    )
    entry['source'] = 'unknown'
    entry['mode'] = 'unknown'

    paths = _dataset_catalog_paths(anchor)
    _save_dataset_snapshot(paths, [entry])

    state = observerctl_module._ds_wizard_new_state('build')
    observerctl_module._ds_wizard_open_section(state, 'in')
    state.build_in_stage = 'records'
    state.build_in_family = 'real'
    state.build_in_mode = 'canary'
    state.build_in_page = 1

    summary = observerctl_module._ds_wizard_build_in_filtered_entries(state)

    assert summary['total_records'] == 1
    assert summary['visible_entries'][0]['source'] == 'real'
    assert summary['visible_entries'][0]['mode'] == 'canary'


def test_ds_wizard_workflow_menu_sections_match_agreed_contract() -> None:
    assert observerctl_module._ds_wizard_visible_sections(observerctl_module._ds_wizard_new_state('build')) == [
        'flow', 'in', 'report', 'cmd', 'check', 'run', 'exit'
    ]
    assert observerctl_module._ds_wizard_visible_sections(observerctl_module._ds_wizard_new_state('train')) == [
        'flow', 'model', 'report', 'cmd', 'check', 'run', 'exit'
    ]
    assert observerctl_module._ds_wizard_visible_sections(observerctl_module._ds_wizard_new_state('evaluate')) == [
        'flow', 'model', 'eval', 'report', 'cmd', 'check', 'run', 'exit'
    ]
    assert observerctl_module._ds_wizard_visible_sections(observerctl_module._ds_wizard_new_state('score')) == [
        'flow', 'report', 'cmd', 'check', 'run', 'exit'
    ]
    assert observerctl_module._ds_wizard_visible_sections(observerctl_module._ds_wizard_new_state('run-pipeline')) == [
        'flow', 'report', 'cmd', 'check', 'run', 'exit'
    ]


def test_ds_wizard_train_model_surface_keeps_prior_train_and_seed_only() -> None:
    state = observerctl_module._ds_wizard_new_state('train')
    observerctl_module._ds_wizard_open_section(state, 'model')

    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]

    assert any('load previous train' in line for line in rendered)
    assert any('model family' in line for line in rendered)
    assert any('seed' in line for line in rendered)
    assert not any('dataset artifact' in line for line in rendered)
    assert not any('validation split' in line for line in rendered)
    assert not any('test split' in line for line in rendered)


def test_ds_wizard_score_workflow_removes_redundant_model_surface() -> None:
    state = observerctl_module._ds_wizard_new_state('score')
    assert observerctl_module._ds_wizard_page_sections(state) == ['flow', 'report', 'cmd', 'check', 'run']
    assert 'model' not in observerctl_module._ds_wizard_visible_sections(state)


def test_ds_wizard_run_pipeline_menu_removes_duplicate_config_sections() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')
    assert observerctl_module._ds_wizard_page_sections(state) == ['flow', 'report', 'cmd', 'check', 'run']


def test_ds_wizard_cmd_surface_explains_execution_map() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_set_value(state, 'max_fpr', '0.03')
    observerctl_module._ds_wizard_open_section(state, 'cmd')

    rendered = observerctl_module._ds_wizard_render(state)

    assert 'execution map:' in rendered
    assert any('workflow lane: evaluate' in line for line in rendered)
    assert any('status: no-go (run this workflow to advance)' in line for line in rendered)
    assert any('evaluation guard: max_fpr = 0.03' in line for line in rendered)
    assert any('dataset artifact: pending' in line for line in rendered)
    assert any('model artifact: pending' in line for line in rendered)
    assert any('validate: blocked until check passes' in line for line in rendered)
    assert not any('report lane:' in line for line in rendered)
    assert not any('run root:' in line for line in rendered)


def test_ds_wizard_run_surface_uses_dataset_manifest_placeholder_in_render() -> None:
    state = observerctl_module._ds_wizard_new_state('train')
    observerctl_module._ds_wizard_set_value(state, 'dataset_manifest', r'C:\demo\datasets\alpha\dataset_manifest.json')
    observerctl_module._ds_wizard_set_value(state, 'model_type', 'unsupervised')
    observerctl_module._ds_wizard_open_section(state, 'run')

    rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]

    assert not any('--dataset <path to dataset_manifest.json>' in line for line in rendered)
    assert 'actions: prev | ? | next | execute | exit' in rendered
    assert any(line.startswith('blocked: ') for line in rendered)
    assert r'C:\demo\datasets\alpha\dataset_manifest.json' in observerctl_module._ds_wizard_command_preview(state)


def test_ds_wizard_standard_surfaces_render_loaded_markers_for_hydrated_paths(tmp_path: Path) -> None:
    baseline_packet = tmp_path / 'baseline.json'
    baseline_packet.write_text('{}\n', encoding='utf-8')
    train_manifest = tmp_path / 'train_manifest.json'
    train_manifest.write_text('{}\n', encoding='utf-8')

    eval_state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_set_value(eval_state, 'baseline_analysis_packet', str(baseline_packet))
    observerctl_module._ds_wizard_set_value(eval_state, 'baseline_window_id', 'baseline-window-001')
    observerctl_module._ds_wizard_open_section(eval_state, 'model')
    eval_rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(eval_state)]
    assert any('load saved baseline' in line and 'loaded' in line for line in eval_rendered)

    train_state = observerctl_module._ds_wizard_new_state('train')
    observerctl_module._ds_wizard_set_value(train_state, 'train_manifest', str(train_manifest))
    observerctl_module._ds_wizard_open_section(train_state, 'model')
    train_rendered = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(train_state)]
    assert any('load previous train' in line and 'loaded' in line for line in train_rendered)


def test_ds_wizard_cmd_surfaces_use_path_placeholders_across_workflows() -> None:
    build_state = observerctl_module._ds_wizard_new_state('build')
    build_state.values['input_paths'] = [r'C:\demo\inputs\alpha.jsonl']
    observerctl_module._ds_wizard_set_value(build_state, 'out_dir', r'C:\demo\outputs\build')
    build_preview = observerctl_module._ds_wizard_display_command_preview(build_state)
    assert '--input <path to input.jsonl>' in build_preview
    assert '--out-dir <path to output directory>' in build_preview
    assert r'C:\demo\inputs\alpha.jsonl' not in build_preview

    train_state = observerctl_module._ds_wizard_new_state('train')
    observerctl_module._ds_wizard_set_value(train_state, 'dataset_manifest', r'C:\demo\datasets\alpha\dataset_manifest.json')
    train_preview = observerctl_module._ds_wizard_display_command_preview(train_state)
    assert '--dataset <path to dataset_manifest.json>' in train_preview
    assert r'C:\demo\datasets\alpha\dataset_manifest.json' not in train_preview

    evaluate_state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_set_value(evaluate_state, 'features_csv', r'C:\demo\datasets\alpha\features.csv')
    observerctl_module._ds_wizard_set_value(evaluate_state, 'labels_csv', r'C:\demo\datasets\alpha\labels.csv')
    observerctl_module._ds_wizard_set_value(evaluate_state, 'dataset_manifest', r'C:\demo\datasets\alpha\dataset_manifest.json')
    evaluate_preview = observerctl_module._ds_wizard_display_command_preview(evaluate_state)
    assert '--features-csv <path to features.csv>' in evaluate_preview
    assert '--labels-csv <path to labels.csv>' in evaluate_preview
    assert '--dataset-manifest <path to dataset_manifest.json>' in evaluate_preview
    assert r'C:\demo\datasets\alpha\features.csv' not in evaluate_preview

    score_state = observerctl_module._ds_wizard_new_state('score')
    observerctl_module._ds_wizard_set_value(score_state, 'dataset_manifest', r'C:\demo\datasets\alpha\dataset_manifest.json')
    observerctl_module._ds_wizard_set_value(score_state, 'train_manifest', r'C:\demo\models\alpha\train_manifest.json')
    score_preview = observerctl_module._ds_wizard_display_command_preview(score_state)
    assert '--dataset <path to dataset_manifest.json>' in score_preview
    assert '--model <path to train_manifest.json>' in score_preview
    assert r'C:\demo\models\alpha\train_manifest.json' not in score_preview

    pipeline_state = observerctl_module._ds_wizard_new_state('run-pipeline')
    pipeline_state.values['input_paths'] = [r'C:\demo\inputs\alpha.jsonl']
    observerctl_module._ds_wizard_set_value(pipeline_state, 'out_dir', r'C:\demo\outputs\pipeline')
    pipeline_preview = observerctl_module._ds_wizard_display_command_preview(pipeline_state)
    assert '--input <path to input.jsonl>' in pipeline_preview
    assert '--out-dir <path to output directory>' in pipeline_preview
    assert r'C:\demo\outputs\pipeline' not in pipeline_preview


def test_ds_wizard_report_surface_only_renders_workflow_valid_rows() -> None:
    expected = {
        'build': {
            'present': ['report json:', 'report md:', 'dataset manifest:', 'features csv:'],
            'absent': ['train manifest:', 'metrics json:', 'run json:', 'scores csv:', 'threshold report json:'],
        },
        'train': {
            'present': ['report json:', 'report md:', 'dataset manifest:', 'train manifest:', 'model artifact:', 'metrics json:'],
            'absent': ['run json:', 'scores csv:', 'threshold report json:'],
        },
        'evaluate': {
            'present': ['report json:', 'report md:', 'dataset manifest:', 'features csv:', 'model artifact:', 'run json:', 'run md:'],
            'absent': ['metrics json:', 'threshold report json:', 'threshold report md:'],
        },
        'score': {
            'present': ['report json:', 'report md:', 'dataset manifest:', 'model artifact:', 'scores csv:'],
            'absent': ['metrics json:', 'run json:', 'threshold report json:', 'threshold report md:'],
        },
        'run-pipeline': {
            'present': ['report json:', 'report md:', 'dataset manifest:', 'features csv:', 'train manifest:', 'model artifact:', 'metrics json:', 'run json:', 'run md:'],
            'absent': ['threshold report json:', 'threshold report md:'],
        },
    }

    for workflow, contract in expected.items():
        state = observerctl_module._ds_wizard_new_state(workflow)
        observerctl_module._ds_wizard_open_section(state, 'report')
        rendered = [strip_ansi(line).strip() for line in observerctl_module._ds_wizard_render(state)]
        for label in contract['present']:
            assert any(line.startswith(label) for line in rendered)
        for label in contract['absent']:
            assert not any(line.startswith(label) for line in rendered)


def test_ds_wizard_report_surface_shows_unsupervised_evaluate_threshold_rows_when_available() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    state.completed_workflows['evaluate'] = {
        'packet_artifacts': {
            'scores_csv': r'C:\demo\runs\evaluate\score\scores.csv',
            'threshold_report_json': r'C:\demo\runs\evaluate\score\threshold_report.json',
            'threshold_report_md': r'C:\demo\runs\evaluate\score\threshold_report.md',
        }
    }

    observerctl_module._ds_wizard_open_section(state, 'report')
    rendered = [' '.join(strip_ansi(line).split()) for line in observerctl_module._ds_wizard_render(state)]

    assert 'scores csv: scores.csv' in rendered
    assert 'threshold report json: threshold_report.json' in rendered
    assert 'threshold report md: threshold_report.md' in rendered


def test_ds_wizard_score_execute_populates_report_results_and_completion_feedback(tmp_path: Path, monkeypatch) -> None:
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    train_manifest = tmp_path / 'train_manifest.json'
    model_path = tmp_path / 'model.pkl'
    scores_csv = tmp_path / 'scores.csv'
    dataset_manifest.write_text('{}\n', encoding='utf-8')
    train_manifest.write_text('{}\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    scores_csv.write_text('record_id,score_anomaly\n1,0.1\n', encoding='utf-8')

    def _fake_ds_score(dataset: str, model: str, out_file: str) -> dict:
        return {
            'timestamp_utc': '2026-04-04T12:00:00Z',
            'decision': 'go',
            'action': 'ds-score',
            'summary': 'Unsupervised scoring completed through observerctl ds.',
            'run_id': 'score-run-001',
            'records_scored': 12,
            'score_column': 'score_anomaly',
            'anomaly_direction': 'higher=worse',
            'artifacts': {
                'scores_csv': str(scores_csv),
            },
            'reason_codes': [],
        }

    monkeypatch.setattr(observerctl_module, '_ds_score', _fake_ds_score)

    state = observerctl_module._ds_wizard_new_state('score')
    observerctl_module._ds_wizard_set_value(state, 'dataset_manifest', str(dataset_manifest))
    observerctl_module._ds_wizard_set_value(state, 'train_manifest', str(train_manifest))
    observerctl_module._ds_wizard_set_value(state, 'model_path', str(model_path))
    observerctl_module._ds_wizard_open_section(state, 'run')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'execute')

    assert packet is None
    assert should_exit is False
    assert observerctl_module._ds_wizard_transient_lines(state) == ['score complete: 12 records scored | score_anomaly | higher=worse']

    run_rendered = [' '.join(strip_ansi(line).split()) for line in observerctl_module._ds_wizard_render(state)]
    assert any(line == 'processing: complete' for line in run_rendered)
    assert any(line == 'completion: score complete: 12 records scored | score_anomaly | higher=worse' for line in run_rendered)

    observerctl_module._ds_wizard_open_section(state, 'report')
    report_rendered = [' '.join(strip_ansi(line).split()) for line in observerctl_module._ds_wizard_render(state)]
    assert 'results:' in report_rendered
    assert any(line == 'scores csv: scores.csv' for line in report_rendered)
    assert any(line == 'records scored: 12' for line in report_rendered)
    assert any(line == 'score column: score_anomaly' for line in report_rendered)
    assert any(line == 'anomaly direction: higher=worse' for line in report_rendered)


def test_ds_run_demo_with_explicit_derived_reports_emits_local_report_bundle(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            try:
                import apexlab  # noqa: F401
            except ImportError:
                pytest.skip('ApexLab not installed')
        
            out_dir = tmp_path / 'demo_flow'
            rc = main(['ds', 'run', 'demo', '--out-dir', str(out_dir), '--derived-reports', '--json'])
        
            assert rc == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-run'
            assert payload['run_mode'] == 'demo'
            assert payload['implementation_state'] == 'automation-available'
            assert 'delivery_frame' not in payload
            assert payload['finalization']['derived_reports_enabled'] is True
            assert payload['publication']['decision'] == 'skipped'
            assert 'publication_skipped:workflow_not_publishable' in payload['publication']['reason_codes']
            assert payload['total_records'] == 60
            assert Path(payload['artifacts']['root_dir']).exists()
            assert Path(payload['artifacts']['dataset_manifest']).exists()
            assert Path(payload['artifacts']['supervised_model_path']).exists()
            assert Path(payload['artifacts']['unsupervised_model_path']).exists()
            assert Path(payload['artifacts']['evaluation_run_json']).exists()
            assert Path(payload['artifacts']['evaluation_run_md']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_md']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_manifest_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_run_index_jsonl']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_latest_json']).exists()
            assert 'tracked_ds_index_md' not in payload['artifacts']
            assert not (project_dir / 'docs' / 'reports' / 'collections').exists()


def test_ds_run_demo_defaults_to_no_derived_reports(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            try:
                import apexlab  # noqa: F401
            except ImportError:
                pytest.skip('ApexLab not installed')

            rc = main(['ds', 'run', 'demo', '--json'])

            assert rc == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-run'
            assert payload['run_mode'] == 'demo'
            assert payload['finalization']['derived_reports_enabled'] is False
            assert payload['publication']['decision'] == 'skipped'
            assert 'publication_skipped:derived_reports_disabled' in payload['publication']['reason_codes']
            assert Path(payload['artifacts']['root_dir']).exists()
            assert Path(payload['artifacts']['dataset_manifest']).exists()
            assert Path(payload['artifacts']['evaluation_run_json']).exists()
            assert 'report_json' not in payload['artifacts']
            assert 'report_md' not in payload['artifacts']
            assert 'report_manifest_json' not in payload['artifacts']
            assert 'ds_run_index_jsonl' not in payload['artifacts']
            assert not (project_dir / 'local_untracked' / 'analysis' / 'indexes' / 'ds_run_index.jsonl').exists()
            assert not (project_dir / 'docs' / 'reports' / 'collections').exists()


def test_ds_run_demo_no_derived_reports_skips_report_bundle_and_publication(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            try:
                import apexlab  # noqa: F401
            except ImportError:
                pytest.skip('ApexLab not installed')

            out_dir = tmp_path / 'demo_flow'
            rc = main(['ds', 'run', 'demo', '--out-dir', str(out_dir), '--no-derived-reports', '--json'])

            assert rc == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-run'
            assert payload['run_mode'] == 'demo'
            assert payload['publication']['decision'] == 'skipped'
            assert 'publication_skipped:derived_reports_disabled' in payload['publication']['reason_codes']
            assert Path(payload['artifacts']['root_dir']).exists()
            assert Path(payload['artifacts']['dataset_manifest']).exists()
            assert Path(payload['artifacts']['evaluation_run_json']).exists()
            assert 'report_json' not in payload['artifacts']
            assert 'report_md' not in payload['artifacts']
            assert 'report_manifest_json' not in payload['artifacts']
            assert 'ds_run_index_jsonl' not in payload['artifacts']
            assert 'tracked_ds_index_md' not in payload['artifacts']
            assert not (project_dir / 'docs' / 'reports' / 'ds').exists()


def test_ds_run_demo_human_render_uses_sectioned_terminal_layout(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        observerctl_module,
        '_ds_run_demo',
        lambda out_dir, dataset_seed, model_seed, max_fpr, derived_reports_enabled=False: {
            'timestamp_utc': '2026-04-09T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-run',
            'command_family': 'ds',
            'command_path': 'observerctl ds run demo',
            'implementation_state': 'automation-available',
            'underlying_surface': 'analysis.run_demo',
            'run_mode': 'demo',
            'summary': 'Demo pipeline completed through observerctl ds.',
            'run_id': 'demo-unit-001',
            'dataset_seed': 123,
            'model_seed': 42,
            'total_records': 60,
            'max_fpr': 0.01,
            'counts': {'tp': 1, 'fp': 0, 'tn': 58, 'fn': 1},
            'thresholding': {
                'threshold': 0.2,
                'target_fpr': 0.01,
                'actual_fpr': 0.0,
                'flagged_records': 1,
                'records_scored': 60,
            },
            'score_column': 'score_anomaly',
            'anomaly_direction': 'lower-is-more-anomalous',
            'artifacts': {
                'root_dir': 'local_untracked/analysis/runs/demo/demo-unit-001',
                'dataset_manifest': 'local_untracked/analysis/runs/demo/demo-unit-001/dataset/dataset_manifest.json',
                'supervised_model_path': 'local_untracked/analysis/runs/demo/demo-unit-001/models/supervised/model.pkl',
                'unsupervised_model_path': 'local_untracked/analysis/runs/demo/demo-unit-001/models/unsupervised/model.pkl',
                'evaluation_run_json': 'local_untracked/analysis/runs/demo/demo-unit-001/evaluation/run.json',
                'scores_csv': 'local_untracked/analysis/runs/demo/demo-unit-001/scoring/scores.csv',
            },
            'finalization': {
                'derived_reports_enabled': False,
                'step_order': [],
                'steps': {},
            },
            'publication': {
                'decision': 'skipped',
                'reason_codes': ['publication_skipped:derived_reports_disabled'],
            },
            'reason_codes': [],
        },
    )

    rc = main(['ds', 'run', 'demo'])

    assert rc == 0
    rendered = [strip_ansi(line) for line in capsys.readouterr().out.splitlines()]
    assert rendered[0] == 'ObserverCTL DS demo'
    assert 'Summary' in rendered
    assert 'Evaluation' in rendered
    assert 'Outputs' in rendered
    assert 'Guidance' in rendered
    assert any('Derived reports:' in line and 'disabled (default)' in line for line in rendered)
    assert any('Publication:' in line and 'skipped' in line for line in rendered)
    assert any('Root dir:' in line and 'local_untracked/analysis/runs/demo/demo-unit-001' in line for line in rendered)
    assert any('--derived-reports' in line for line in rendered)


def test_ds_run_pipeline_executes_supervised_flow_and_emits_artifact_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            try:
                import apexlab  # noqa: F401
            except ImportError:
                pytest.skip('ApexLab not installed')
        
            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)
        
            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
        
            input_path = tmp_path / 'input.jsonl'
            _write_signed_jsonl(input_path, _make_ds_records())
            out_dir = tmp_path / 'pipeline_flow'
        
            rc = main([
                'ds', 'run', 'pipeline',
                '--input', str(input_path),
                '--out-dir', str(out_dir),
                '--model-type', 'supervised',
                '--seed', '42',
                '--json',
            ])
        
            assert rc == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-run'
            assert payload['run_mode'] == 'pipeline'
            assert payload['implementation_state'] == 'automation-available'
            assert 'delivery_frame' not in payload
            assert payload['model_type'] == 'supervised'
            assert payload['has_labels'] is True
            assert payload['workflow_steps'] == ['build', 'train', 'evaluate']
            assert Path(payload['artifacts']['dataset_manifest']).exists()
            assert Path(payload['artifacts']['train_manifest']).exists()
            assert Path(payload['artifacts']['model_path']).exists()
            assert Path(payload['artifacts']['run_json']).exists()
            assert Path(payload['artifacts']['run_md']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_md']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_manifest_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_run_index_jsonl']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_latest_json']).exists()


def test_ds_run_pipeline_no_derived_reports_skips_report_bundle_and_publication(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            try:
                import apexlab  # noqa: F401
            except ImportError:
                pytest.skip('ApexLab not installed')

            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

            input_path = tmp_path / 'input.jsonl'
            _write_signed_jsonl(input_path, _make_ds_records())
            out_dir = tmp_path / 'pipeline_flow'

            rc = main([
                'ds', 'run', 'pipeline',
                '--input', str(input_path),
                '--out-dir', str(out_dir),
                '--model-type', 'supervised',
                '--seed', '42',
                '--no-derived-reports',
                '--json',
            ])

            assert rc == 0
            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-run'
            assert payload['run_mode'] == 'pipeline'
            assert payload['publication']['decision'] == 'skipped'
            assert 'publication_skipped:derived_reports_disabled' in payload['publication']['reason_codes']
            assert Path(payload['artifacts']['dataset_manifest']).exists()
            assert Path(payload['artifacts']['train_manifest']).exists()
            assert Path(payload['artifacts']['run_json']).exists()
            assert 'report_json' not in payload['artifacts']
            assert 'report_md' not in payload['artifacts']
            assert 'report_manifest_json' not in payload['artifacts']
            assert 'ds_run_index_jsonl' not in payload['artifacts']
            assert 'tracked_ds_index_md' not in payload['artifacts']
            assert not (project_dir / 'docs' / 'reports' / 'ds').exists()


def test_ds_build_executes_wrapper_and_emits_artifact_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)
        
            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
        
            input_path = tmp_path / 'input.jsonl'
            _write_signed_jsonl(input_path, _make_ds_records())
            out_dir = tmp_path / 'dataset'
        
            rc = main(['ds', 'build', '--input', str(input_path), '--out-dir', str(out_dir), '--seed', '123', '--json'])
            assert rc == 0
        
            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-build'
            assert payload['implementation_state'] == 'command-available'
            assert 'delivery_frame' not in payload
            assert Path(payload['artifacts']['dataset_manifest']).exists()
            assert Path(payload['artifacts']['features_csv']).exists()
            assert payload['has_labels'] is True
            assert int(payload['total_records']) == 12
            assert payload['visuals']['decision'] == 'go'
            assert {figure['id'] for figure in payload['visuals']['figures']} == {
                'split_balance',
                'input_slice_volume',
                'feature_family_breakdown',
            }
            assert _resolve_reported_path(payload['artifacts']['split_balance_png']).exists()
            assert _resolve_reported_path(payload['artifacts']['input_slice_volume_png']).exists()
            assert _resolve_reported_path(payload['artifacts']['feature_family_breakdown_png']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_md']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_manifest_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_run_index_jsonl']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_latest_json']).exists()


def test_ds_build_executes_from_registered_dataset_selector(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

            from analysis.dataset_builder import build_dataset

            input_path = tmp_path / 'input.jsonl'
            _write_signed_jsonl(input_path, _make_ds_records())
            registered_dataset_dir = tmp_path / 'registered_dataset'
            build_dataset([input_path], out_dir=registered_dataset_dir, seed=123)
            manifest_path = registered_dataset_dir / 'dataset_manifest.json'
            materialized_out_dir = tmp_path / 'materialized_dataset'

            reg_rc = main(['librarian', 'dataset-register', str(manifest_path), '--json'])
            assert reg_rc == 0
            reg_payload = json.loads(capsys.readouterr().out)
            dataset_token = str(reg_payload['dataset']['entry_id'])

            rc = main(['ds', 'build', '--dataset', dataset_token, '--out-dir', str(materialized_out_dir), '--json'])
            assert rc == 0

            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-build'
            assert payload['implementation_state'] == 'command-available'
            assert Path(payload['artifacts']['dataset_manifest']).exists()
            assert Path(payload['artifacts']['features_csv']).exists()
            assert Path(payload['artifacts']['splits_csv']).exists()
            assert Path(payload['artifacts']['split_manifest_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_md']).exists()


def test_ds_build_real_source_emits_tv_review_artifacts_and_manifest_labels(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path):
            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
            monkeypatch.setattr(observerctl_module, '_load_state', lambda: {'source': 'real', 'mode': 'honeypot'})

            input_path = tmp_path / 'real_source.jsonl'
            _write_signed_jsonl(input_path, _make_real_tv_review_records())
            out_dir = tmp_path / 'dataset'

            rc = main(['ds', 'build', '--input', str(input_path), '--out-dir', str(out_dir), '--json'])
            assert rc == 0

            payload = json.loads(capsys.readouterr().out)
            manifest_payload = json.loads((out_dir / 'dataset_manifest.json').read_text(encoding='utf-8'))

            assert payload['action'] == 'ds-build'
            assert payload['source'] == 'real'
            assert payload['tv_review']['decision'] == 'go'
            assert payload['tv_review']['labeled_unique_count'] == 2
            assert payload['has_labels'] is True
            assert Path(payload['artifacts']['tv_review_inventory_csv']).exists()
            assert Path(payload['artifacts']['tv_suggested_labels_csv']).exists()
            assert Path(payload['artifacts']['labels_csv']).exists()
            assert manifest_payload['has_labels'] is True
            assert Path(str(manifest_payload['labels_csv'])).name == 'labels.csv'


def test_ds_build_sim_source_skips_tv_review_runtime_branch(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path):
            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
            monkeypatch.setattr(observerctl_module, '_load_state', lambda: {'source': 'sim', 'mode': 'canary'})

            input_path = tmp_path / 'sim_source.jsonl'
            _write_signed_jsonl(input_path, _make_real_tv_review_records())
            out_dir = tmp_path / 'dataset'

            rc = main(['ds', 'build', '--input', str(input_path), '--out-dir', str(out_dir), '--json'])
            assert rc == 0

            payload = json.loads(capsys.readouterr().out)
            manifest_payload = json.loads((out_dir / 'dataset_manifest.json').read_text(encoding='utf-8'))

            assert payload['source'] == 'sim'
            assert payload['tv_review']['decision'] == 'skipped'
            assert payload['tv_review']['reason_codes'] == ['tv_review_skipped:source_not_real']
            assert 'tv_review_inventory_csv' not in payload['artifacts']
            assert 'tv_suggested_labels_csv' not in payload['artifacts']
            assert payload['has_labels'] is False
            assert manifest_payload['has_labels'] is False


def test_ds_train_executes_wrapper_and_emits_expected_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            try:
                import apexlab  # noqa: F401
            except ImportError:
                pytest.skip('ApexLab not installed')
        
            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)
        
            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
        
            from analysis.dataset_builder import build_dataset
        
            input_path = tmp_path / 'input.jsonl'
            _write_signed_jsonl(input_path, _make_ds_records())
            dataset_dir = tmp_path / 'dataset'
            build_dataset([input_path], out_dir=dataset_dir, seed=123)
            manifest_path = dataset_dir / 'dataset_manifest.json'
            model_dir = tmp_path / 'models'

            reg_rc = main(['librarian', 'dataset-register', str(manifest_path), '--json'])
            assert reg_rc == 0
            reg_payload = json.loads(capsys.readouterr().out)
            dataset_token = str(reg_payload['dataset']['entry_id'])

            rc = main(['ds', 'train', '--dataset', dataset_token, '--out-dir', str(model_dir), '--model-type', 'supervised', '--json'])
            assert rc == 0
        
            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-train'
            assert payload['model_type'] == 'supervised'
            assert Path(payload['artifacts']['train_manifest']).exists()
            assert Path(payload['artifacts']['model_path']).exists()
            assert Path(payload['artifacts']['metrics_path']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_md']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_manifest_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_run_index_jsonl']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_latest_json']).exists()


def test_ds_evaluate_executes_wrapper_and_emits_run_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)
        
            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
        
            from analysis.dataset_builder import build_dataset
        
            input_path = tmp_path / 'input.jsonl'
            _write_signed_jsonl(input_path, _make_ds_records())
            dataset_dir = tmp_path / 'dataset'
            manifest = build_dataset([input_path], out_dir=dataset_dir, seed=123)
            eval_dir = tmp_path / 'evaluation'
        
            rc = main([
                'ds', 'evaluate',
                '--features-csv', str(Path(manifest.features_csv)),
                '--labels-csv', str(Path(manifest.labels_csv)),
                '--dataset-manifest', str(dataset_dir / 'dataset_manifest.json'),
                '--out-dir', str(eval_dir),
                '--run-id', 'unit-eval',
                '--json',
            ])
            assert rc == 0
        
            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-evaluate'
            assert payload['run_id'] == 'unit-eval'
            assert Path(payload['artifacts']['run_json']).exists()
            assert Path(payload['artifacts']['run_md']).exists()
            assert payload['has_labels'] is True
            assert _resolve_reported_path(payload['artifacts']['report_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_md']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_manifest_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_run_index_jsonl']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_latest_json']).exists()


def test_ds_evaluate_unsupervised_emits_threshold_overlay_when_model_and_manifest_are_present(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path):
            try:
                import apexlab  # noqa: F401
            except ImportError:
                pytest.skip('ApexLab not installed')

            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

            from analysis.dataset_builder import build_dataset
            from analysis.train_model import train_model

            input_path = tmp_path / 'input.jsonl'
            _write_signed_jsonl(input_path, _make_ds_records())
            dataset_dir = tmp_path / 'dataset'
            build_dataset([input_path], out_dir=dataset_dir, seed=123)
            manifest_path = dataset_dir / 'dataset_manifest.json'
            model_dir = tmp_path / 'models_unsupervised'
            train_model(manifest_path, out_dir=model_dir, model_type='unsupervised', seed=42)
            eval_dir = tmp_path / 'evaluation'

            rc = main([
                'ds', 'evaluate',
                '--features-csv', str(dataset_dir / 'features.csv'),
                '--dataset-manifest', str(manifest_path),
                '--model-path', str(model_dir / 'train_manifest.json'),
                '--out-dir', str(eval_dir),
                '--run-id', 'unit-eval-unsup',
                '--json',
            ])
            assert rc == 0

            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-evaluate'
            assert payload['run_id'] == 'unit-eval-unsup'
            assert payload['anomaly_direction'] == 'lower-is-more-anomalous'
            assert payload['visuals']['decision'] == 'go'
            assert _resolve_reported_path(payload['artifacts']['scores_csv']).exists()
            assert _resolve_reported_path(payload['artifacts']['threshold_report_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['threshold_report_md']).exists()
            assert _resolve_reported_path(payload['artifacts']['threshold_selection_png']).exists()


def test_ds_score_executes_wrapper_and_emits_score_artifact_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    with _bind_temp_observer_project_ctx(monkeypatch, tmp_path) as project_dir:
            try:
                import apexlab  # noqa: F401
            except ImportError:
                pytest.skip('ApexLab not installed')
        
            log_dir = tmp_path / 'logs'
            (log_dir / 'health').mkdir(parents=True, exist_ok=True)
            (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
            (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)
        
            monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
            monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
        
            from analysis.dataset_builder import build_dataset
            from analysis.train_model import train_model
        
            input_path = tmp_path / 'input.jsonl'
            _write_signed_jsonl(input_path, _make_ds_records())
            dataset_dir = tmp_path / 'dataset'
            build_dataset([input_path], out_dir=dataset_dir, seed=123)
            manifest_path = dataset_dir / 'dataset_manifest.json'
            model_dir = tmp_path / 'models_unsupervised'
            train_model(manifest_path, out_dir=model_dir, model_type='unsupervised', seed=42)
        
            out_file = tmp_path / 'scores.csv'

            reg_rc = main(['librarian', 'dataset-register', str(manifest_path), '--json'])
            assert reg_rc == 0
            reg_payload = json.loads(capsys.readouterr().out)
            dataset_token = str(reg_payload['dataset']['entry_id'])

            rc = main([
                'ds', 'score',
                '--dataset', dataset_token,
                '--model', str(model_dir / 'train_manifest.json'),
                '--out-file', str(out_file),
                '--json',
            ])
            assert rc == 0
        
            payload = json.loads(capsys.readouterr().out)
            assert payload['action'] == 'ds-score'
            assert payload['records_scored'] == 12
            assert payload['score_column'] == 'score_anomaly'
            assert payload['anomaly_direction'] == 'lower-is-more-anomalous'
            assert payload['visuals']['decision'] == 'go'
            assert Path(payload['artifacts']['scores_csv']).exists()
            assert _resolve_reported_path(payload['artifacts']['score_distribution_png']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_md']).exists()
            assert _resolve_reported_path(payload['artifacts']['report_manifest_json']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_run_index_jsonl']).exists()
            assert _resolve_reported_path(payload['artifacts']['ds_latest_json']).exists()


def test_ds_finalize_run_packet_keeps_librarian_authority_unchanged(tmp_path: Path, monkeypatch) -> None:
    from analysis.report_pack import prepare_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))

    bundle = prepare_report_bundle(anchor, 'build', run_id='framec-build-refresh')
    dataset_dir = bundle.artifact_dirs['dataset']
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
        'source': 'real',
        'mode': 'watch',
    }), encoding='utf-8')

    final_packet = observerctl_module._ds_finalize_run_packet(
        {
            'timestamp_utc': '2026-03-31T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset built through observerctl ds.',
            'run_id': bundle.run_id,
            'total_records': 1,
            'has_labels': True,
            'artifacts': {},
            'reason_codes': [],
        },
        bundle=bundle,
        artifact_paths={
            'dataset_manifest': manifest_path,
            'features_csv': features_csv,
            'labels_csv': labels_csv,
        },
        context={'output_override': False},
        lineage={'input_paths': [project_root / 'input.jsonl']},
    )

    assert 'librarian_dataset_manifest_json' not in final_packet['artifacts']
    assert 'librarian_dataset_catalog_jsonl' not in final_packet['artifacts']
    assert _resolve_reported_path(final_packet['artifacts']['report_manifest_json']).exists()
    assert _resolve_reported_path(final_packet['artifacts']['ds_run_index_jsonl']).exists()
    assert _resolve_reported_path(final_packet['artifacts']['ds_latest_json']).exists()


def test_librarian_dataset_register_canary_runtime_baseline_context_does_not_create_saved_baseline(tmp_path: Path, monkeypatch) -> None:
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    evidence_dir = project_root / 'local_untracked' / 'analysis' / 'observer_derived' / 'real' / 'canary' / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    baseline_packet = evidence_dir / 'runtime_baseline_packet.json'
    baseline_packet.write_text(
        json.dumps(
            {
                'action': 'baseline-analyze',
                'decision': 'go',
                'baseline_window_id': 'runtime-canary-window1',
                'summary': 'Runtime canary baseline ready.',
                'sample_counts': {'normal': 12, 'baseline': 6},
            }
        ),
        encoding='utf-8',
    )
    (evidence_dir / 'index.jsonl').write_text(
        json.dumps(
            {
                'event': 'baseline_analysis',
                'timestamp_utc': '2026-04-14T16:00:00Z',
                'baseline_window_id': 'runtime-canary-window1',
                'packet_path': str(baseline_packet),
                'decision': 'go',
            }
        ) + '\n',
        encoding='utf-8',
    )

    dataset_dir = project_root / 'datasets' / 'unlabeled_canary_runtime'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\nr1,0.42\n', encoding='utf-8')
    manifest_path.write_text(
        json.dumps(
            {
                'features_csv': str(features_csv),
                'total_records': 1,
                'has_labels': False,
                'source': 'real',
                'mode': 'canary',
            }
        ),
        encoding='utf-8',
    )

    packet = register_librarian_dataset_packet(
        anchor,
        manifest_path,
        display_name='Unlabeled Canary Runtime Dataset',
        run_id='unlabeled-canary-runtime-window1',
    )
    saved_entries = observerctl_module._ds_saved_baseline_entries('real', 'live')

    assert packet['decision'] == 'go'
    assert packet['dataset']['source'] == 'real'
    assert packet['dataset']['mode'] == 'canary'
    assert packet['dataset']['has_labels'] is False
    assert packet['dataset']['registration_kind'] == 'manual-register'
    assert packet['dataset']['comparison_baseline_stage'] == 'canary_reviewed'
    assert packet['dataset']['baseline_window_id'] == 'runtime-canary-window1'
    assert packet['dataset']['baseline_decision_state'] == 'go'
    assert packet['dataset']['baseline_summary'] == 'Runtime canary baseline ready.'
    assert _resolve_reported_path(packet['dataset']['baseline_analysis_packet']) == baseline_packet
    assert _resolve_reported_path(packet['artifacts']['baseline_analysis_packet']) == baseline_packet
    assert _resolve_reported_path(packet['artifacts']['baseline_analysis_index_jsonl']) == evidence_dir / 'index.jsonl'
    assert len(saved_entries) == 1
    assert saved_entries[0]['baseline_stage'] == 'canary_reviewed'


def test_ds_finalize_run_packet_labeled_canary_build_admits_reviewed_closeout_and_emits_saved_baseline(tmp_path: Path, monkeypatch) -> None:
    from analysis.report_pack import prepare_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))

    bundle = prepare_report_bundle(anchor, 'build', run_id='framec-reviewed-canary-build')
    dataset_dir = bundle.artifact_dirs['dataset']
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n1,0.25\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
        'source': 'real',
        'mode': 'canary',
    }), encoding='utf-8')

    final_packet = observerctl_module._ds_finalize_run_packet(
        {
            'timestamp_utc': '2026-04-14T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Reviewed canary dataset built through observerctl ds.',
            'run_id': bundle.run_id,
            'source': 'real',
            'mode': 'canary',
            'total_records': 1,
            'has_labels': True,
            'artifacts': {},
            'reason_codes': [],
        },
        bundle=bundle,
        artifact_paths={
            'dataset_manifest': manifest_path,
            'features_csv': features_csv,
            'labels_csv': labels_csv,
        },
        context={
            'output_override': False,
            'source': 'real',
            'mode': 'canary',
        },
        lineage={'input_paths': [project_root / 'input.jsonl']},
    )

    comparison_baseline_path = _resolve_reported_path(final_packet['artifacts']['comparison_baseline_packet_json'])
    librarian_manifest_path = _resolve_reported_path(final_packet['artifacts']['librarian_dataset_manifest_json'])
    librarian_payload = json.loads(librarian_manifest_path.read_text(encoding='utf-8'))
    admitted_entries = [entry for entry in librarian_payload['entries'] if entry.get('registration_kind') == 'reviewed-closeout']
    saved_entries = observerctl_module._ds_saved_baseline_entries('real', 'live')

    assert final_packet['finalization']['steps']['librarian_dataset_catalog']['catalog_updated'] is True
    assert final_packet['finalization']['steps']['librarian_dataset_catalog']['comparison_baseline_emitted'] is True
    assert comparison_baseline_path.exists()
    assert admitted_entries
    assert admitted_entries[0]['run_id'] == 'framec-reviewed-canary-build'
    assert 'Reviewed Canary' in str(admitted_entries[0]['display_name'])
    assert saved_entries
    assert saved_entries[0]['baseline_stage'] == 'canary_reviewed'
    assert saved_entries[0]['baseline_window_id'] == 'framec-reviewed-canary-build'


def test_ds_finalize_run_packet_build_prefers_lineage_dataset_alias_over_materialized_manifest(tmp_path: Path, monkeypatch) -> None:
    from analysis.report_pack import prepare_report_bundle
    from analysis._util import sha256_path
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))

    authority_dir = project_root / 'datasets' / 'authority_live'
    authority_dir.mkdir(parents=True, exist_ok=True)
    authority_features_csv = authority_dir / 'features.csv'
    authority_manifest = authority_dir / 'dataset_manifest.json'
    authority_features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    authority_manifest.write_text(json.dumps({
        'features_csv': str(authority_features_csv),
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

    dataset_packet = register_librarian_dataset_packet(
        anchor,
        authority_manifest,
        display_name='Authority Live Dataset',
        run_id='authority-live-dataset',
    )
    assert dataset_packet['decision'] == 'go'
    expected_alias = str(dataset_packet['dataset']['display_alias'])

    bundle = prepare_report_bundle(anchor, 'build', run_id='frame-d3-build')
    dataset_dir = bundle.artifact_dirs['dataset']
    dataset_dir.mkdir(parents=True, exist_ok=True)
    materialized_features_csv = dataset_dir / 'features.csv'
    materialized_manifest = dataset_dir / 'dataset_manifest.json'
    materialized_features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    materialized_manifest.write_text(json.dumps({
        'features_csv': str(materialized_features_csv),
        'total_records': 13842,
        'has_labels': False,
    }), encoding='utf-8')

    final_packet = observerctl_module._ds_finalize_run_packet(
        {
            'timestamp_utc': '2026-04-11T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset built through observerctl ds.',
            'run_id': bundle.run_id,
            'total_records': 13842,
            'has_labels': False,
            'artifacts': {},
            'reason_codes': [],
        },
        bundle=bundle,
        artifact_paths={
            'dataset_manifest': materialized_manifest,
            'features_csv': materialized_features_csv,
        },
        context={'output_override': False},
        lineage={'dataset_manifest': authority_manifest},
    )

    report_payload = json.loads(_resolve_reported_path(final_packet['artifacts']['report_json']).read_text(encoding='utf-8'))

    assert final_packet['decision'] == 'go'
    assert final_packet['collection_alias'] == expected_alias
    assert report_payload['collection_alias'] == expected_alias
    assert final_packet['collection_alias'] != 'dataset-{0}'.format(sha256_path(materialized_manifest)[-6:])


def test_ds_finalize_run_packet_can_skip_derived_reporting_side_effects(tmp_path: Path, monkeypatch) -> None:
    from analysis.report_pack import prepare_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))

    bundle = prepare_report_bundle(anchor, 'pipeline', run_id='framec-pipeline-no-derived')
    dataset_dir = bundle.run_root / 'dataset'
    model_dir = bundle.run_root / 'models'
    evaluation_dir = bundle.run_root / 'evaluation'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)

    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    train_manifest = model_dir / 'train_manifest.json'
    run_json = evaluation_dir / 'run.json'
    dataset_manifest.write_text('{}\n', encoding='utf-8')
    train_manifest.write_text('{}\n', encoding='utf-8')
    run_json.write_text('{}\n', encoding='utf-8')

    final_packet = observerctl_module._ds_finalize_run_packet(
        {
            'timestamp_utc': '2026-03-31T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-run',
            'command_family': 'ds',
            'command_path': 'observerctl ds run pipeline',
            'implementation_state': 'automation-available',
            'underlying_surface': 'observerctl ds pipeline orchestration',
            'summary': 'Pipeline completed through observerctl ds.',
            'run_id': bundle.run_id,
            'run_mode': 'pipeline',
            'artifacts': {},
            'reason_codes': [],
        },
        bundle=bundle,
        artifact_paths={
            'dataset_manifest': dataset_manifest,
            'train_manifest': train_manifest,
            'run_json': run_json,
        },
        context={'output_override': False},
        lineage={'input_paths': [project_root / 'input.jsonl']},
        derived_reports_enabled=False,
    )

    assert final_packet['publication']['decision'] == 'skipped'
    assert 'publication_skipped:derived_reports_disabled' in final_packet['publication']['reason_codes']
    assert 'report_json' not in final_packet['artifacts']
    assert 'report_md' not in final_packet['artifacts']
    assert 'report_manifest_json' not in final_packet['artifacts']
    assert 'ds_run_index_jsonl' not in final_packet['artifacts']
    assert 'tracked_ds_index_md' not in final_packet['artifacts']
    assert not (project_root / 'local_untracked' / 'analysis' / 'indexes' / 'ds_run_index.jsonl').exists()
    assert not (project_root / 'docs' / 'reports' / 'ds').exists()


def test_ds_finalize_run_packet_exposes_explicit_finalization_order(tmp_path: Path, monkeypatch) -> None:
    import calamum_librarian as librarian_module
    from analysis import report_aggregate as report_aggregate_module
    from analysis import report_pack as report_pack_module
    from analysis.report_pack import prepare_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))

    bundle = prepare_report_bundle(anchor, 'build', run_id='frame1-order-build')
    call_order: list[str] = []

    def _fake_write_report_bundle(*, project_anchor, bundle, packet, artifact_paths, context=None, lineage=None):
        call_order.append('report_bundle')
        return {
            'paths': {
                'run_root': 'local_untracked/analysis/runs/build/frame1-order-build',
                'report_json': 'local_untracked/analysis/runs/build/frame1-order-build/report/report.json',
                'report_md': 'local_untracked/analysis/runs/build/frame1-order-build/report/report.md',
                'manifest_json': 'local_untracked/analysis/runs/build/frame1-order-build/report/manifest.json',
            },
            'manifest': {
                'workflow': 'build',
                'run_id': bundle.run_id,
                'collection_alias': 'can-frame1-order',
                'timestamp_utc': str(packet.get('timestamp_utc', '')),
                'decision': 'go',
                'summary': str(packet.get('summary', '')),
                'producer_command': str(packet.get('command_path', '')),
                'producer_entrypoint': 'projects/calamum-moltbook-observer/src/observerctl.py',
                'report_paths': {
                    'markdown': 'local_untracked/analysis/runs/build/frame1-order-build/report/report.md',
                    'json': 'local_untracked/analysis/runs/build/frame1-order-build/report/report.json',
                    'manifest': 'local_untracked/analysis/runs/build/frame1-order-build/report/manifest.json',
                },
                'run_root': 'local_untracked/analysis/runs/build/frame1-order-build',
                'result': {},
                'context': {},
                'lineage': {},
            },
        }

    def _fake_append_ds_run_index(*, project_anchor, manifest_payload):
        call_order.append('run_index')
        return {
            'ledger_path': 'local_untracked/analysis/indexes/ds_run_index.jsonl',
            'latest_index_path': 'local_untracked/analysis/indexes/ds_latest.json',
        }

    def _fake_refresh_librarian_dataset_catalog_from_run_manifest(project_anchor, manifest_payload):
        call_order.append('librarian_dataset_catalog')
        return {
            'catalog_updated': False,
            'snapshot_path': 'local_untracked/analysis/indexes/librarian_dataset_manifest.json',
            'catalog_path': 'local_untracked/analysis/indexes/librarian_dataset_catalog.jsonl',
        }

    def _fake_publication_eligibility_reasons(*, project_anchor, manifest_payload):
        call_order.append('publication_eligibility')
        return []

    def _fake_refresh_tracked_ds_publication(*, project_anchor, current_manifest_payload=None):
        call_order.append('tracked_publication')
        return {
            'decision': 'go',
            'reason_codes': [],
            'published_run_count': 1,
            'aggregate_paths': {},
            'current_run': {
                'run_id': 'frame1-order-build',
                'published_run_dir': 'docs/reports/collections/can-frame1-order',
                'published_report_paths': {
                    'json': 'docs/reports/internal/runs/frame1-order-build/publication_report.json',
                    'markdown': 'docs/reports/collections/can-frame1-order/collection/20260404T120000000000Z.collection.md',
                    'collection_history_markdown': 'docs/reports/collections/can-frame1-order/collection/20260404T120000000000Z.collection.md',
                    'manifest': 'docs/reports/internal/runs/frame1-order-build/publication_manifest.json',
                },
            },
        }

    monkeypatch.setattr(report_pack_module, 'write_report_bundle', _fake_write_report_bundle)
    monkeypatch.setattr(report_aggregate_module, 'append_ds_run_index', _fake_append_ds_run_index)
    monkeypatch.setattr(librarian_module, 'refresh_librarian_dataset_catalog_from_run_manifest', _fake_refresh_librarian_dataset_catalog_from_run_manifest)
    monkeypatch.setattr(report_aggregate_module, 'publication_eligibility_reasons', _fake_publication_eligibility_reasons)
    monkeypatch.setattr(report_aggregate_module, 'refresh_tracked_ds_publication', _fake_refresh_tracked_ds_publication)

    final_packet = observerctl_module._ds_finalize_run_packet(
        {
            'timestamp_utc': '2026-04-04T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset built through observerctl ds.',
            'collection_alias': 'can-frame1-order',
            'artifacts': {},
            'reason_codes': [],
        },
        bundle=bundle,
        artifact_paths={
            'dataset_manifest': project_root / 'dataset_manifest.json',
        },
        context={'output_override': False},
        lineage={'input_paths': [project_root / 'input.jsonl']},
    )

    assert call_order == [
        'report_bundle',
        'run_index',
        'librarian_dataset_catalog',
        'publication_eligibility',
        'tracked_publication',
    ]
    assert final_packet['finalization']['step_order'] == [
        'report_bundle',
        'run_index',
        'librarian_dataset_catalog',
        'publication_eligibility',
        'tracked_publication',
    ]
    assert final_packet['finalization']['steps']['report_bundle']['decision'] == 'go'
    assert final_packet['finalization']['steps']['run_index']['decision'] == 'go'
    assert final_packet['finalization']['steps']['librarian_dataset_catalog']['decision'] == 'go'
    assert final_packet['finalization']['steps']['publication_eligibility']['eligible'] is True
    assert final_packet['finalization']['steps']['tracked_publication']['decision'] == 'go'
    assert final_packet['publication']['decision'] == 'go'


def test_ds_finalize_run_packet_fails_closed_when_collection_alias_is_unresolved(tmp_path: Path, monkeypatch) -> None:
    from analysis.report_pack import prepare_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))

    bundle = prepare_report_bundle(anchor, 'evaluate', run_id='frame1-missing-alias')
    evaluation_dir = bundle.artifact_dirs['evaluation']
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    run_json = evaluation_dir / 'run.json'
    run_md = evaluation_dir / 'run.md'
    run_json.write_text('{}\n', encoding='utf-8')
    run_md.write_text('# eval\n', encoding='utf-8')

    final_packet = observerctl_module._ds_finalize_run_packet(
        {
            'timestamp_utc': '2026-04-04T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Evaluation completed through observerctl ds.',
            'artifacts': {},
            'reason_codes': [],
        },
        bundle=bundle,
        artifact_paths={
            'run_json': run_json,
            'run_md': run_md,
        },
        context={'max_fpr': 0.02},
        lineage={},
    )

    assert final_packet['decision'] == 'no-go'
    assert 'critical_check_failed:collection_alias_unresolved' in final_packet['reason_codes']
    assert final_packet['publication']['decision'] == 'skipped'
    assert final_packet['publication']['reason_codes'] == ['publication_skipped:collection_alias_missing']
    assert final_packet['finalization']['steps']['report_bundle']['decision'] == 'no-go'
    assert final_packet['finalization']['steps']['run_index']['decision'] == 'skipped'
    assert final_packet['finalization']['steps']['publication_eligibility']['eligible'] is False
    assert 'report_json' not in final_packet['artifacts']
    assert 'ds_run_index_jsonl' not in final_packet['artifacts']


def test_ds_finalize_run_packet_marks_all_finalization_steps_skipped_when_derived_reporting_is_disabled(tmp_path: Path, monkeypatch) -> None:
    from analysis.report_pack import prepare_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)
    monkeypatch.setattr(observerctl_module, '__file__', str(anchor))

    bundle = prepare_report_bundle(anchor, 'build', run_id='frame1-skip-build')
    final_packet = observerctl_module._ds_finalize_run_packet(
        {
            'timestamp_utc': '2026-04-04T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset built through observerctl ds.',
            'artifacts': {},
            'reason_codes': [],
        },
        bundle=bundle,
        artifact_paths={
            'dataset_manifest': project_root / 'dataset_manifest.json',
        },
        context={'output_override': False},
        lineage={'input_paths': [project_root / 'input.jsonl']},
        derived_reports_enabled=False,
    )

    assert final_packet['finalization']['derived_reports_enabled'] is False
    assert final_packet['finalization']['step_order'] == [
        'report_bundle',
        'run_index',
        'librarian_dataset_catalog',
        'publication_eligibility',
        'tracked_publication',
    ]
    for step_name in final_packet['finalization']['step_order']:
        step = final_packet['finalization']['steps'][step_name]
        assert step['decision'] == 'skipped'
        assert 'derived_reports_disabled' in step['reason_codes']


def test_ds_report_pack_defaults_to_canonical_run_root_and_repo_relative_index_paths(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    bundle = prepare_report_bundle(anchor, 'build')
    dataset_dir = bundle.artifact_dirs['dataset']
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / 'dataset_manifest.json').write_text('{}\n', encoding='utf-8')
    (dataset_dir / 'features.csv').write_text('record_id\n', encoding='utf-8')

    packet = {
        'timestamp_utc': '2026-03-31T12:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-build',
        'command_family': 'ds',
        'command_path': 'observerctl ds build',
        'implementation_state': 'command-available',
        'underlying_surface': 'analysis.dataset_builder',
        'summary': 'Dataset built through observerctl ds.',
        'run_id': bundle.run_id,
        'total_records': 1,
        'has_labels': False,
        'artifacts': {},
        'reason_codes': [],
    }
    report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet=packet,
        artifact_paths={
            'dataset_manifest': dataset_dir / 'dataset_manifest.json',
            'features_csv': dataset_dir / 'features.csv',
        },
        context={'output_override': False},
        lineage={'input_paths': [project_root / 'input.jsonl']},
    )
    aggregate = append_ds_run_index(project_anchor=anchor, manifest_payload=report_bundle['manifest'])

    assert report_bundle['paths']['run_root'].startswith('local_untracked/analysis/runs/build/')
    assert report_bundle['paths']['report_json'].startswith('local_untracked/analysis/runs/build/')
    assert aggregate['ledger_path'] == 'local_untracked/analysis/indexes/ds_run_index.jsonl'
    assert aggregate['latest_index_path'] == 'local_untracked/analysis/indexes/ds_latest.json'
    assert (project_root / report_bundle['paths']['report_json']).exists()
    assert (project_root / report_bundle['paths']['manifest_json']).exists()
    assert (project_root / aggregate['ledger_path']).exists()
    assert (project_root / aggregate['latest_index_path']).exists()


def test_ds_report_aggregate_appends_history_and_refreshes_latest_by_workflow(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    for run_id in ['eval-one', 'eval-two']:
        bundle = prepare_report_bundle(anchor, 'evaluate', run_id=run_id)
        evaluation_dir = bundle.artifact_dirs['evaluation']
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        (evaluation_dir / 'run.json').write_text('{"run_id":"%s"}\n' % run_id, encoding='utf-8')
        (evaluation_dir / 'run.md').write_text('# run\n', encoding='utf-8')
        report_bundle = write_report_bundle(
            project_anchor=anchor,
            bundle=bundle,
            packet={
                'timestamp_utc': '2026-03-31T12:00:00Z' if run_id == 'eval-one' else '2026-03-31T12:05:00Z',
                'runtime_cli_surface': 'observerctl',
                'decision': 'go',
                'action': 'ds-evaluate',
                'command_family': 'ds',
                'command_path': 'observerctl ds evaluate',
                'implementation_state': 'command-available',
                'underlying_surface': 'analysis.evaluation_harness',
                'summary': 'Evaluation completed through observerctl ds.',
                'run_id': bundle.run_id,
                'collection_alias': 'can-eval-history',
                'threshold': 0.5,
                'artifacts': {},
                'reason_codes': [],
            },
            artifact_paths={
                'run_json': evaluation_dir / 'run.json',
                'run_md': evaluation_dir / 'run.md',
            },
            context={'max_fpr': 0.01},
        )
        append_ds_run_index(project_anchor=anchor, manifest_payload=report_bundle['manifest'])

    ledger_path = project_root / 'local_untracked' / 'analysis' / 'indexes' / 'ds_run_index.jsonl'
    latest_path = project_root / 'local_untracked' / 'analysis' / 'indexes' / 'ds_latest.json'
    rows = _read_jsonl_rows(ledger_path)
    latest = json.loads(latest_path.read_text(encoding='utf-8'))

    assert [row['run_id'] for row in rows] == ['eval-one', 'eval-two']
    assert latest['latest_run']['run_id'] == 'eval-two'
    assert latest['by_workflow']['evaluate']['run_id'] == 'eval-two'


def test_ds_report_aggregate_preserves_collection_alias_in_latest_index(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-collection-alias')
    evaluation_dir = bundle.artifact_dirs['evaluation']
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    (evaluation_dir / 'run.json').write_text('{"run_id":"eval-collection-alias"}\n', encoding='utf-8')
    (evaluation_dir / 'run.md').write_text('# eval run\n', encoding='utf-8')

    report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-04-04T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Evaluation completed through observerctl ds.',
            'run_id': bundle.run_id,
            'collection_alias': 'can-frame1-alias',
            'threshold': 0.42,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': evaluation_dir / 'run.json',
            'run_md': evaluation_dir / 'run.md',
        },
        context={'max_fpr': 0.01},
    )

    aggregate = append_ds_run_index(project_anchor=anchor, manifest_payload=report_bundle['manifest'])
    ledger_rows = _read_jsonl_rows(project_root / aggregate['ledger_path'])
    latest = json.loads((project_root / aggregate['latest_index_path']).read_text(encoding='utf-8'))

    assert ledger_rows[0]['collection_alias'] == 'can-frame1-alias'
    assert latest['latest_run']['collection_alias'] == 'can-frame1-alias'
    assert latest['by_workflow']['evaluate']['collection_alias'] == 'can-frame1-alias'


def test_ds_report_publication_requires_canonical_run_root(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, publication_eligibility_reasons, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    explicit_run_root = project_root / 'custom_output' / 'build-run'
    bundle = prepare_report_bundle(anchor, 'build', explicit_run_root=explicit_run_root, run_id='explicit-build')
    dataset_dir = bundle.artifact_dirs['dataset']
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / 'dataset_manifest.json').write_text('{}\n', encoding='utf-8')
    (dataset_dir / 'features.csv').write_text('record_id\n', encoding='utf-8')

    report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset built through observerctl ds.',
            'run_id': bundle.run_id,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'dataset_manifest': dataset_dir / 'dataset_manifest.json',
            'features_csv': dataset_dir / 'features.csv',
        },
        context={'output_override': True},
    )

    reasons = publication_eligibility_reasons(project_anchor=anchor, manifest_payload=report_bundle['manifest'])
    assert 'publication_skipped:noncanonical_run_root' in reasons
    assert 'publication_skipped:run_root_outside_canonical_spine' in reasons
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    evaluate_bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-canonical')
    evaluation_dir = evaluate_bundle.artifact_dirs['evaluation']
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    (evaluation_dir / 'run.json').write_text('{"run_id":"eval-canonical"}\n', encoding='utf-8')
    (evaluation_dir / 'run.md').write_text('# eval run\n', encoding='utf-8')
    evaluate_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=evaluate_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Evaluation completed through observerctl ds.',
            'run_id': evaluate_bundle.run_id,
            'collection_alias': 'can-canonical',
            'threshold': 0.42,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': evaluation_dir / 'run.json',
            'run_md': evaluation_dir / 'run.md',
        },
        context={'max_fpr': 0.01},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=evaluate_report_bundle['manifest'])

    score_bundle = prepare_report_bundle(anchor, 'score', run_id='score-canonical')
    scoring_dir = score_bundle.artifact_dirs['scoring']
    scoring_dir.mkdir(parents=True, exist_ok=True)
    (scoring_dir / 'scores.csv').write_text('record_id,score_anomaly\n1,0.9\n', encoding='utf-8')
    score_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=score_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:05:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-score',
            'command_family': 'ds',
            'command_path': 'observerctl ds score',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.score_unsupervised',
            'summary': 'Unsupervised scoring completed through observerctl ds.',
            'run_id': score_bundle.run_id,
            'collection_alias': 'can-canonical',
            'records_scored': 1,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'scores_csv': scoring_dir / 'scores.csv',
        },
        context={'output_override': False},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=score_report_bundle['manifest'])

    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=score_report_bundle['manifest'])

    assert publication['decision'] == 'go'
    assert publication['published_run_count'] == 2
    assert publication['current_run']['run_id'] == 'score-canonical'
    assert (project_root / publication['aggregate_paths']['index_md']).exists()
    assert (project_root / publication['aggregate_paths']['aggregate_report_json']).exists()
    assert (project_root / publication['aggregate_paths']['aggregate_report_md']).exists()
    assert (project_root / publication['aggregate_paths']['public_run_ledger_json']).exists()
    assert (project_root / publication['aggregate_paths']['public_run_ledger_md']).exists()
    assert (project_root / publication['aggregate_paths']['latest_json']).exists()
    assert (project_root / publication['aggregate_paths']['thresholds_json']).exists()
    assert (project_root / publication['current_run']['published_report_paths']['markdown']).exists()

    thresholds_payload = json.loads((project_root / publication['aggregate_paths']['thresholds_json']).read_text(encoding='utf-8'))
    by_workflow_payload = json.loads((project_root / publication['aggregate_paths']['by_workflow_json']).read_text(encoding='utf-8'))
    latest_payload = json.loads((project_root / publication['aggregate_paths']['latest_json']).read_text(encoding='utf-8'))

    assert thresholds_payload['threshold_run_count'] == 1
    assert thresholds_payload['threshold_rows'][0]['run_id'] == 'eval-canonical'
    assert by_workflow_payload['workflows']['evaluate']['latest_run']['run_id'] == 'eval-canonical'
    assert by_workflow_payload['workflows']['score']['latest_run']['run_id'] == 'score-canonical'
    assert latest_payload['latest_run']['run_id'] == 'score-canonical'


def test_ds_report_publication_explicit_republish_allows_explicit_override_runs_inside_canonical_spine(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, publication_eligibility_reasons, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    explicit_run_root = project_root / 'local_untracked' / 'analysis' / 'runs' / 'score' / 'd4_projection_score'
    bundle = prepare_report_bundle(
        anchor,
        'score',
        explicit_run_root=explicit_run_root,
        run_id='score-d4-projection',
    )
    scoring_dir = bundle.artifact_dirs['scoring']
    scoring_dir.mkdir(parents=True, exist_ok=True)
    scores_csv = scoring_dir / 'scores.csv'
    scores_csv.write_text('record_id,score_anomaly\na,0.1\nb,0.9\n', encoding='utf-8')

    report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-04-11T04:24:59.318423Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-score',
            'command_family': 'ds',
            'command_path': 'observerctl ds score',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.score_unsupervised',
            'summary': 'Projected tracked publication for repaired local score run.',
            'run_id': bundle.run_id,
            'collection_alias': 'liv-r8bc9',
            'records_scored': 2,
            'anomaly_direction': 'lower-is-more-anomalous',
            'score_column': 'score_anomaly',
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'scores_csv': scores_csv,
        },
        context={'output_override': True},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=report_bundle['manifest'])

    reasons = publication_eligibility_reasons(project_anchor=anchor, manifest_payload=report_bundle['manifest'])
    skipped_publication = refresh_tracked_ds_publication(
        project_anchor=anchor,
        current_manifest_payload=report_bundle['manifest'],
    )
    explicit_publication = refresh_tracked_ds_publication(
        project_anchor=anchor,
        current_manifest_payload=report_bundle['manifest'],
        explicit_republish=True,
    )

    assert 'publication_skipped:noncanonical_run_root' in reasons
    assert 'publication_skipped:run_root_outside_canonical_spine' not in reasons
    assert skipped_publication['decision'] == 'go'
    assert skipped_publication['published_run_count'] == 0
    assert skipped_publication['current_run'] == {}

    assert explicit_publication['decision'] == 'go'
    assert explicit_publication['published_run_count'] == 1
    assert explicit_publication['current_run']['run_id'] == 'score-d4-projection'
    assert explicit_publication['current_run']['collection_alias'] == 'liv-r8bc9'
    assert explicit_publication['current_run']['source_run_root'] == report_bundle['manifest']['run_root']
    assert (project_root / explicit_publication['current_run']['published_run_dir']).exists()
    assert (project_root / explicit_publication['current_run']['published_report_paths']['processing_markdown']).exists()
    assert (project_root / 'docs' / 'reports' / 'collections' / 'liv-r8bc9' / 'processing' / 'score').exists()


def test_ds_report_publication_skips_ephemeral_dataset_manifest_lineage(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, publication_eligibility_reasons, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    build_bundle = prepare_report_bundle(anchor, 'build', run_id='build-temp-lineage')
    build_dataset_dir = build_bundle.artifact_dirs['dataset']
    build_dataset_dir.mkdir(parents=True, exist_ok=True)
    (build_dataset_dir / 'dataset_manifest.json').write_text('{}\n', encoding='utf-8')
    (build_dataset_dir / 'features.csv').write_text('record_id\n', encoding='utf-8')

    build_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=build_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset built through observerctl ds.',
            'run_id': build_bundle.run_id,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'dataset_manifest': build_dataset_dir / 'dataset_manifest.json',
            'features_csv': build_dataset_dir / 'features.csv',
        },
        context={'output_override': False},
        lineage={'dataset_manifest': 'C:/Users/tester/AppData/Local/Temp/pytest-of-user/test_ds_build/dataset_manifest.json'},
    )

    reasons = publication_eligibility_reasons(project_anchor=anchor, manifest_payload=build_report_bundle['manifest'])
    append_ds_run_index(project_anchor=anchor, manifest_payload=build_report_bundle['manifest'])
    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=build_report_bundle['manifest'])

    assert 'publication_skipped:dataset_manifest_ephemeral' in reasons
    assert publication['decision'] == 'go'
    assert publication['published_run_count'] == 0
    assert publication['current_run'] == {}
    assert not (project_root / 'docs' / 'reports' / 'collections' / 'build-temp-lineage').exists()


def test_ds_report_publication_refresh_copies_visual_figures_and_rewrites_links(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    score_bundle = prepare_report_bundle(anchor, 'score', run_id='score-visual')
    scoring_dir = score_bundle.artifact_dirs['scoring']
    scoring_dir.mkdir(parents=True, exist_ok=True)
    (scoring_dir / 'scores.csv').write_text('record_id,score_anomaly\na,0.1\nb,0.9\n', encoding='utf-8')
    figures_dir = score_bundle.run_root / 'figures'
    figures_dir.mkdir(parents=True, exist_ok=True)
    figure_path = figures_dir / 'score_distribution.png'
    figure_path.write_bytes(b'not-a-real-png-but-good-enough-for-copy')

    score_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=score_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:05:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-score',
            'command_family': 'ds',
            'command_path': 'observerctl ds score',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.score_unsupervised',
            'summary': 'Unsupervised scoring completed through observerctl ds.',
            'run_id': score_bundle.run_id,
            'collection_alias': 'can-score-visual',
            'anomaly_direction': 'lower-is-more-anomalous',
            'visuals': {
                'decision': 'go',
                'figure_count': 1,
                'anomaly_direction': 'lower-is-more-anomalous',
                'score_column': 'score_anomaly',
                'figures': [
                    {
                        'id': 'score_distribution',
                        'title': 'Score distribution',
                        'caption': 'Distribution of anomaly scores.',
                        'path': figure_path,
                        'kind': 'distribution',
                    }
                ],
            },
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'scores_csv': scoring_dir / 'scores.csv',
            'score_distribution_png': figure_path,
        },
        context={'output_override': False},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=score_report_bundle['manifest'])

    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=score_report_bundle['manifest'])

    published_report_md = project_root / publication['current_run']['published_report_paths']['processing_markdown']
    assert publication['decision'] == 'go'
    assert publication['current_run']['figure_count'] == 1
    assert (project_root / publication['current_run']['published_figures'][0]).exists()
    assert '](figures/20260331T120500000000Z.score/score_distribution.png)' in published_report_md.read_text(encoding='utf-8')
    assert '../figures/' not in published_report_md.read_text(encoding='utf-8')


def test_ds_report_publication_refresh_rewrites_tracked_report_paths_and_strips_absolute_path_noise(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    score_bundle = prepare_report_bundle(anchor, 'score', run_id='score-publication-clean')
    scoring_dir = score_bundle.artifact_dirs['scoring']
    scoring_dir.mkdir(parents=True, exist_ok=True)
    scores_csv = scoring_dir / 'scores.csv'
    threshold_report_json = scoring_dir / 'threshold_report.json'
    threshold_report_md = scoring_dir / 'threshold_report.md'
    scores_csv.write_text('record_id,score_anomaly\na,0.1\nb,0.9\n', encoding='utf-8')
    threshold_report_json.write_text('{}\n', encoding='utf-8')
    threshold_report_md.write_text('# threshold\n', encoding='utf-8')

    figures_dir = score_bundle.run_root / 'figures'
    figures_dir.mkdir(parents=True, exist_ok=True)
    figure_path = figures_dir / 'score_distribution.png'
    figure_path.write_bytes(b'not-a-real-png-but-good-enough-for-copy')

    score_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=score_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:05:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-score',
            'command_family': 'ds',
            'command_path': 'observerctl ds score',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.score_unsupervised',
            'summary': 'Unsupervised scoring completed through observerctl ds.',
            'run_id': score_bundle.run_id,
            'collection_alias': 'can-score-publication-clean',
            'records_scored': 2,
            'anomaly_direction': 'lower-is-more-anomalous',
            'score_column': 'score_anomaly',
            'thresholding': {
                'decision': 'go',
                'anomaly_direction': 'lower-is-more-anomalous',
                'flag_rule': 'score <= threshold',
                'threshold': 0.2,
                'target_fpr': 0.01,
                'actual_fpr': 0.0,
                'flagged_records': 1,
                'records_scored': 2,
                'report_json': str(threshold_report_json),
                'report_md': str(threshold_report_md),
                'scores_csv': str(scores_csv),
            },
            'visuals': {
                'decision': 'go',
                'figure_count': 1,
                'anomaly_direction': 'lower-is-more-anomalous',
                'score_column': 'score_anomaly',
                'figures': [
                    {
                        'id': 'score_distribution',
                        'title': 'Score distribution',
                        'caption': 'Distribution of anomaly scores.',
                        'path': str(figure_path),
                        'kind': 'distribution',
                    }
                ],
            },
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'scores_csv': scores_csv,
            'score_distribution_png': figure_path,
            'threshold_report_json': threshold_report_json,
            'threshold_report_md': threshold_report_md,
        },
        context={'output_override': False},
    )

    source_report_json_path = project_root / score_report_bundle['paths']['report_json']
    source_report_md_path = project_root / score_report_bundle['paths']['report_md']
    source_report_payload = json.loads(source_report_json_path.read_text(encoding='utf-8'))
    source_report_payload['result']['thresholding']['report_json'] = str(threshold_report_json).replace('\\', '/')
    source_report_payload['result']['thresholding']['report_md'] = str(threshold_report_md).replace('\\', '/')
    source_report_payload['result']['thresholding']['scores_csv'] = str(scores_csv).replace('\\', '/')
    source_report_payload['result']['visuals']['figures'][0]['path'] = str(figure_path).replace('\\', '/')
    source_report_json_path.write_text(json.dumps(source_report_payload, indent=2, sort_keys=True), encoding='utf-8')
    source_report_md_path.write_text(
        '# stale canonical markdown\n\n- leaked path: {0}\n'.format(str(figure_path).replace('\\', '/')),
        encoding='utf-8',
    )

    append_ds_run_index(project_anchor=anchor, manifest_payload=score_report_bundle['manifest'])
    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=score_report_bundle['manifest'])

    current_run = publication['current_run']
    published_report_md_path = project_root / current_run['published_report_paths']['processing_markdown']
    published_report_json_path = project_root / current_run['published_report_paths']['json']
    published_manifest_path = project_root / current_run['published_report_paths']['manifest']

    published_report_text = published_report_md_path.read_text(encoding='utf-8')
    published_report_payload = json.loads(published_report_json_path.read_text(encoding='utf-8'))
    published_manifest_payload = json.loads(published_manifest_path.read_text(encoding='utf-8'))
    project_root_prefix = str(project_root).replace('\\', '/')

    assert publication['decision'] == 'go'
    assert project_root_prefix not in published_report_text
    assert project_root_prefix not in json.dumps(published_report_payload, sort_keys=True)
    assert published_report_payload['report_paths'] == current_run['published_report_paths']
    assert published_manifest_payload['report_paths'] == current_run['published_report_paths']
    assert published_report_payload['source_report_paths'] == score_report_bundle['report']['report_paths']
    assert published_manifest_payload['source_report_paths'] == score_report_bundle['manifest']['report_paths']
    assert published_report_payload['source_run_root'] == score_report_bundle['manifest']['run_root']
    assert published_manifest_payload['source_run_root'] == score_report_bundle['manifest']['run_root']
    assert published_report_payload['published_run_dir'] == current_run['published_run_dir']
    assert published_manifest_payload['published_run_dir'] == current_run['published_run_dir']
    assert published_report_payload['result']['visuals']['figures'][0]['path'] == current_run['published_figures'][0]
    assert '## Score method' in published_report_text
    assert '## Related surfaces' in published_report_text
    assert '](figures/20260331T120500000000Z.score/score_distribution.png)' in published_report_text
    assert '../figures/' not in published_report_text
    assert 'scoring/threshold_report.json' in published_report_text


def test_next_processing_report_path_uses_canonical_utc_timestamp_and_rejects_suffix_fallback(tmp_path: Path) -> None:
    from analysis.report_aggregate import _next_processing_report_path

    processing_dir = tmp_path / 'processing' / 'eval'
    processing_dir.mkdir(parents=True, exist_ok=True)

    first_path = _next_processing_report_path(
        processing_dir=processing_dir,
        timestamp_utc='2026-03-31T12:05:00.000000Z',
        workflow='evaluate',
    )
    second_path = _next_processing_report_path(
        processing_dir=processing_dir,
        timestamp_utc='2026-03-31T12:05:00.123456Z',
        workflow='evaluate',
    )

    assert first_path.name == '20260331T120500000000Z.eval.md'
    assert second_path.name == '20260331T120500123456Z.eval.md'

    first_path.write_text('# existing\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Duplicate canonical processing report path'):
        _next_processing_report_path(
            processing_dir=processing_dir,
            timestamp_utc='2026-03-31T12:05:00.000000Z',
            workflow='evaluate',
        )


def test_ds_report_publication_refresh_prefers_declared_visual_registry_over_stray_figure_dir_files(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    score_bundle = prepare_report_bundle(anchor, 'score', run_id='score-declared-figures')
    scoring_dir = score_bundle.artifact_dirs['scoring']
    scoring_dir.mkdir(parents=True, exist_ok=True)
    (scoring_dir / 'scores.csv').write_text('record_id,score_anomaly\na,0.1\nb,0.9\n', encoding='utf-8')
    figures_dir = score_bundle.run_root / 'figures'
    figures_dir.mkdir(parents=True, exist_ok=True)
    figure_path = figures_dir / 'score_distribution.png'
    stray_path = figures_dir / 'unregistered_extra.png'
    figure_path.write_bytes(b'declared-figure')
    stray_path.write_bytes(b'stray-figure')

    score_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=score_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:05:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-score',
            'command_family': 'ds',
            'command_path': 'observerctl ds score',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.score_unsupervised',
            'summary': 'Unsupervised scoring completed through observerctl ds.',
            'run_id': score_bundle.run_id,
            'collection_alias': 'can-score-declared-figures',
            'anomaly_direction': 'lower-is-more-anomalous',
            'visuals': {
                'decision': 'go',
                'figure_count': 1,
                'anomaly_direction': 'lower-is-more-anomalous',
                'score_column': 'score_anomaly',
                'figures': [
                    {
                        'id': 'score_distribution',
                        'title': 'Score distribution',
                        'caption': 'Distribution of anomaly scores.',
                        'path': figure_path,
                        'kind': 'distribution',
                    }
                ],
            },
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'scores_csv': scoring_dir / 'scores.csv',
            'score_distribution_png': figure_path,
        },
        context={'output_override': False},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=score_report_bundle['manifest'])

    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=score_report_bundle['manifest'])

    assert publication['decision'] == 'go'
    assert publication['current_run']['figure_count'] == 1
    assert len(publication['current_run']['published_figures']) == 1
    assert publication['current_run']['published_figures'][0].endswith('score_distribution.png')
    assert not any('unregistered_extra.png' in path for path in publication['current_run']['published_figures'])
    published_run_dir = project_root / publication['current_run']['published_run_dir']
    assert not any(path.name == 'unregistered_extra.png' for path in published_run_dir.rglob('*'))


def test_ds_report_publication_groups_multiple_stage_runs_under_one_collection_alias(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _seed_shipped_manual_report_surfaces(project_root)

    first_bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-alpha')
    first_eval_dir = first_bundle.artifact_dirs['evaluation']
    first_eval_dir.mkdir(parents=True, exist_ok=True)
    first_run_json = first_eval_dir / 'run.json'
    first_run_md = first_eval_dir / 'run.md'
    first_run_json.write_text('{}\n', encoding='utf-8')
    first_run_md.write_text('# eval alpha\n', encoding='utf-8')
    first_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=first_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:05:00.000000Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'First evaluation completed through observerctl ds.',
            'run_id': first_bundle.run_id,
            'collection_alias': 'can-r1a2b',
            'threshold': 0.42,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': first_run_json,
            'run_md': first_run_md,
        },
        context={'max_fpr': 0.02},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=first_report_bundle['manifest'])

    second_bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-beta')
    second_eval_dir = second_bundle.artifact_dirs['evaluation']
    second_eval_dir.mkdir(parents=True, exist_ok=True)
    second_run_json = second_eval_dir / 'run.json'
    second_run_md = second_eval_dir / 'run.md'
    second_run_json.write_text('{}\n', encoding='utf-8')
    second_run_md.write_text('# eval beta\n', encoding='utf-8')
    second_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=second_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:05:00.123456Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Second evaluation completed through observerctl ds.',
            'run_id': second_bundle.run_id,
            'collection_alias': 'can-r1a2b',
            'threshold': 0.44,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': second_run_json,
            'run_md': second_run_md,
        },
        context={'max_fpr': 0.02},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=second_report_bundle['manifest'])

    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=second_report_bundle['manifest'])

    first_stage_doc = project_root / 'docs' / 'reports' / 'collections' / 'can-r1a2b' / 'processing' / 'eval' / '20260331T120500000000Z.eval.md'
    second_stage_doc = project_root / publication['current_run']['published_report_paths']['processing_markdown']
    collection_dir = project_root / 'docs' / 'reports' / 'collections' / 'can-r1a2b' / 'collection'
    collection_report = project_root / publication['current_run']['published_report_paths']['markdown']
    first_collection_doc = collection_dir / '20260331T120500000000Z.collection.md'
    second_collection_doc = project_root / publication['current_run']['published_report_paths']['collection_history_markdown']
    collection_packets = sorted(path.name for path in collection_dir.glob('*.collection.md'))
    latest_collections_md = project_root / publication['aggregate_paths']['latest_md']
    workflow_rollup_md = project_root / publication['aggregate_paths']['by_workflow_md']
    aggregate_report_md = project_root / publication['aggregate_paths']['aggregate_report_md']
    public_run_ledger_md = project_root / publication['aggregate_paths']['public_run_ledger_md']
    reports_index_md = project_root / publication['aggregate_paths']['index_md']
    generated_surfaces_md = project_root / publication['aggregate_paths']['generated_surfaces_md']

    assert publication['decision'] == 'go'
    assert publication['published_run_count'] == 2
    assert first_stage_doc.exists()
    assert second_stage_doc.exists()
    assert not first_collection_doc.exists()
    assert second_collection_doc.exists()
    assert collection_packets == ['20260331T120500123456Z.collection.md']
    assert second_stage_doc.name == '20260331T120500123456Z.eval.md'
    assert second_collection_doc.name == '20260331T120500123456Z.collection.md'
    assert collection_report.exists()
    assert collection_report.name.endswith('.collection.md')
    collection_report_text = collection_report.read_text(encoding='utf-8')
    latest_collections_text = latest_collections_md.read_text(encoding='utf-8')
    workflow_rollup_text = workflow_rollup_md.read_text(encoding='utf-8')
    aggregate_report_text = aggregate_report_md.read_text(encoding='utf-8')
    public_run_ledger_text = public_run_ledger_md.read_text(encoding='utf-8')
    reports_index_text = reports_index_md.read_text(encoding='utf-8')
    generated_surfaces_text = generated_surfaces_md.read_text(encoding='utf-8')
    assert '20260331T120500000000Z.eval.md' in collection_report_text
    assert '20260331T120500123456Z.eval.md' in collection_report_text
    assert '20260331T120500000000Z.collection.md' not in collection_report_text
    assert '## Collection identity' in collection_report_text
    assert '## Run summary' in collection_report_text
    assert '## Collection handoff map' in collection_report_text
    assert '## Collection method' in collection_report_text
    assert '## Retention summary' in collection_report_text
    assert '## Baseline readiness summary' in collection_report_text
    assert '## Watchdog telemetry summary' in collection_report_text
    assert '## Librarian accountability summary' in collection_report_text
    assert '## Security linkage summary' in collection_report_text
    assert '## Run implications' in collection_report_text
    assert '## Limits' in collection_report_text
    assert '## Processing run ledger' in collection_report_text
    assert 'Run IDs remain lineage context for `can-r1a2b`' in collection_report_text
    assert 'collection/report.md' not in latest_collections_text
    assert 'collection/report.md' not in workflow_rollup_text
    assert 'collection/report.md' not in reports_index_text
    assert '20260331T120500000000Z.collection.md' not in latest_collections_text
    assert '20260331T120500000000Z.collection.md' not in workflow_rollup_text
    assert '20260331T120500000000Z.collection.md' not in reports_index_text
    assert '# Aggregate Report' in aggregate_report_text
    assert '# Public Run Ledger' in public_run_ledger_text
    assert '## Librarian vault inventory' in public_run_ledger_text
    assert 'No tracked report archive inventories are currently present in the Librarian quarantine lane.' in public_run_ledger_text
    assert '## What to open first' in aggregate_report_text
    assert '## Current packet family at a glance' in aggregate_report_text
    assert 'Collection packets now act as reader-first entry surfaces rather than history-only routing stubs.' in aggregate_report_text
    assert 'AGGREGATE_REPORT.md' in public_run_ledger_text
    assert 'PUBLIC_RUN_LEDGER.md' in aggregate_report_text
    assert '20260331T120500123456Z.collection.md' in aggregate_report_text
    assert '20260331T120500123456Z.collection.md' in latest_collections_text
    assert '20260331T120500123456Z.collection.md' in workflow_rollup_text
    assert '20260331T120500123456Z.collection.md' in reports_index_text
    assert 'AGGREGATE_REPORT.md' in reports_index_text
    assert 'PUBLIC_RUN_LEDGER.md' in reports_index_text
    assert '## How to use this report family' in reports_index_text
    assert 'Flagship synthesis narrative' in reports_index_text
    assert '`can-r1a2b`' in latest_collections_text
    assert '| `can-r1a2b` |' in public_run_ledger_text
    assert 'AGGREGATE_REPORT.md' in generated_surfaces_text
    assert 'PUBLIC_RUN_LEDGER.md' in generated_surfaces_text
    assert '## Aggregate surface roles' in generated_surfaces_text
    assert 'Front-door collection routing' in generated_surfaces_text
    assert 'Aggregate-facing collection routes use the dated collection packet leaf' in generated_surfaces_text
    assert 'No stable `collection/report.md` landing page is part of the current tracked packet contract.' in generated_surfaces_text


def test_ds_report_publication_uses_registered_dataset_alias_when_manifest_collection_alias_is_blank(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle
    from calamum_librarian import register_librarian_dataset_packet

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _seed_shipped_manual_report_surfaces(project_root)

    dataset_dir = project_root / 'datasets' / 'presentation_demo'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    features_csv = dataset_dir / 'features.csv'
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 4,
        'has_labels': False,
    }), encoding='utf-8')

    dataset_packet = register_librarian_dataset_packet(
        anchor,
        manifest_path,
        display_name='Presentation Demo Dataset',
        run_id='presentation-demo',
    )
    assert dataset_packet['decision'] == 'go'

    train_bundle = prepare_report_bundle(anchor, 'train', run_id='train-presentation-demo')
    train_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=train_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-train',
            'command_family': 'ds',
            'command_path': 'observerctl ds train',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.train_unsupervised',
            'summary': 'Model training completed through observerctl ds.',
            'run_id': train_bundle.run_id,
            'artifacts': {},
            'reason_codes': [],
        },
        context={'seed': 42},
        lineage={'dataset_manifest': manifest_path},
    )
    assert train_report_bundle['manifest']['collection_alias'] == 'presentation-demo'
    append_ds_run_index(project_anchor=anchor, manifest_payload=train_report_bundle['manifest'])

    score_bundle = prepare_report_bundle(anchor, 'score', run_id='score-presentation-demo')
    score_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=score_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:05:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-score',
            'command_family': 'ds',
            'command_path': 'observerctl ds score',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.score_unsupervised',
            'summary': 'Unsupervised scoring completed through observerctl ds.',
            'run_id': score_bundle.run_id,
            'records_scored': 4,
            'anomaly_direction': 'lower-is-more-anomalous',
            'score_column': 'score_anomaly',
            'artifacts': {},
            'reason_codes': [],
        },
        context={'output_override': False},
        lineage={'dataset_manifest': manifest_path},
    )
    assert score_report_bundle['manifest']['collection_alias'] == 'presentation-demo'
    append_ds_run_index(project_anchor=anchor, manifest_payload=score_report_bundle['manifest'])

    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=score_report_bundle['manifest'])

    alias_root = project_root / 'docs' / 'reports' / 'collections' / 'presentation-demo'
    current_stage_doc = project_root / publication['current_run']['published_report_paths']['processing_markdown']
    reports_index_text = (project_root / publication['aggregate_paths']['index_md']).read_text(encoding='utf-8')
    generated_surfaces_text = (project_root / publication['aggregate_paths']['generated_surfaces_md']).read_text(encoding='utf-8')

    assert publication['decision'] == 'go'
    assert publication['published_run_count'] == 2
    assert publication['current_run']['collection_alias'] == 'presentation-demo'
    assert alias_root.exists()
    assert (alias_root / 'collection').exists()
    assert (alias_root / 'processing' / 'train').exists()
    assert (alias_root / 'processing' / 'score').exists()
    assert not (project_root / 'docs' / 'reports' / 'collections' / train_bundle.run_id).exists()
    assert not (project_root / 'docs' / 'reports' / 'collections' / score_bundle.run_id).exists()
    assert '`presentation-demo`' in reports_index_text
    assert '**Collection alias**: `presentation-demo`' in current_stage_doc.read_text(encoding='utf-8')
    assert '|        |- build/' in generated_surfaces_text
    assert '|        |- eval/' in generated_surfaces_text
    assert '|        |- score/' in generated_surfaces_text
    assert '|        `- train/' in generated_surfaces_text


def test_ds_report_bundle_prefers_existing_comparison_baseline_context_for_publication(monkeypatch, tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    reviewed_canary_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_canary_report_window1',
        display_name='Reviewed Canary Report Window1',
        run_id='reviewed-canary-report-window1',
        source='real',
        mode='canary',
        recorded_at_utc='2026-04-13T00:10:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    live_target_entry, manifest_path, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='live_report_target_window1',
        display_name='Live Report Target Window1',
        run_id='live-report-target-window1',
        source='real',
        mode='live',
        recorded_at_utc='2026-04-13T00:12:00Z',
        workflow='manual-register',
    )
    review_policy_packet = project_root / 'local_untracked' / 'reports' / 'report_review_policy_packet.md'
    review_policy_packet.parent.mkdir(parents=True, exist_ok=True)
    review_policy_packet.write_text('# report review policy\n', encoding='utf-8')
    emitted = observerctl_module._ds_emit_comparison_baseline_packet(
        reviewed_canary_entry,
        baseline_stage='canary_reviewed',
        companion_role='bounded reviewed canary report companion',
        review_policy_packet=str(review_policy_packet),
    )
    legacy_baseline_packet = project_root / 'local_untracked' / 'analysis' / 'evidence' / 'observerctl_baseline-analysis_legacy.json'
    legacy_baseline_packet.parent.mkdir(parents=True, exist_ok=True)
    legacy_baseline_packet.write_text(json.dumps({'baseline_window_id': 'reviewed-canary-report-window1'}), encoding='utf-8')

    bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-reviewed-report')
    evaluation_dir = bundle.artifact_dirs['evaluation']
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    run_json = evaluation_dir / 'run.json'
    run_md = evaluation_dir / 'run.md'
    run_json.write_text('{}\n', encoding='utf-8')
    run_md.write_text('# eval reviewed report\n', encoding='utf-8')

    report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-04-13T00:20:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Reviewed evaluation completed through observerctl ds.',
            'run_id': bundle.run_id,
            'collection_alias': 'hp-rpt1',
            'threshold': 0.37,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': run_json,
            'run_md': run_md,
        },
        context={
            'source': 'real',
            'mode': 'live',
            'baseline_analysis_packet': str(legacy_baseline_packet),
            'baseline_window_id': 'reviewed-canary-report-window1',
        },
        lineage={'dataset_manifest': manifest_path},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=report_bundle['manifest'])

    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=report_bundle['manifest'])

    comparison_baseline_path = _resolve_reported_path(emitted['packet_path'])
    manifest_context = report_bundle['manifest']['context']
    publication_context = publication['current_run']['context']
    collection_report_text = (project_root / publication['current_run']['published_report_paths']['markdown']).read_text(encoding='utf-8')

    assert publication['decision'] == 'go'
    assert _resolve_reported_path(str(manifest_context.get('baseline_analysis_packet', '') or '')) == comparison_baseline_path
    assert str(manifest_context.get('baseline_window_id', '') or '') == 'reviewed-canary-report-window1'
    assert _resolve_reported_path(str(publication_context.get('baseline_analysis_packet', '') or '')) == comparison_baseline_path
    assert str(publication_context.get('baseline_window_id', '') or '') == 'reviewed-canary-report-window1'
    assert 'baseline packet ref' in collection_report_text
    assert 'comparison_baseline_packet.json' in collection_report_text
    assert legacy_baseline_packet.name not in collection_report_text


def test_ds_report_bundle_materializes_missing_comparison_baseline_context_for_publication(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    reviewed_canary_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='reviewed_canary_report_window2',
        display_name='Reviewed Canary Report Window2',
        run_id='reviewed-canary-report-window2',
        source='real',
        mode='canary',
        recorded_at_utc='2026-04-14T00:10:00Z',
        workflow='manual-register',
        registration_kind='reviewed-closeout',
    )
    _, manifest_path, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='live_report_target_window2',
        display_name='Live Report Target Window2',
        run_id='live-report-target-window2',
        source='real',
        mode='live',
        recorded_at_utc='2026-04-14T00:12:00Z',
        workflow='manual-register',
    )
    comparison_baseline_path = observerctl_module._ds_comparison_baseline_packet_path(reviewed_canary_entry['entry_id'])
    assert not comparison_baseline_path.exists()

    legacy_baseline_packet = project_root / 'local_untracked' / 'analysis' / 'evidence' / 'observerctl_baseline-analysis_missing.json'
    legacy_baseline_packet.parent.mkdir(parents=True, exist_ok=True)
    legacy_baseline_packet.write_text(json.dumps({'baseline_window_id': 'reviewed-canary-report-window2'}), encoding='utf-8')

    bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-reviewed-report-materialized')
    evaluation_dir = bundle.artifact_dirs['evaluation']
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    run_json = evaluation_dir / 'run.json'
    run_md = evaluation_dir / 'run.md'
    run_json.write_text('{}\n', encoding='utf-8')
    run_md.write_text('# eval reviewed report materialized\n', encoding='utf-8')

    report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-04-14T00:20:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Reviewed evaluation completed through observerctl ds.',
            'run_id': bundle.run_id,
            'collection_alias': 'hp-rpt2',
            'threshold': 0.41,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': run_json,
            'run_md': run_md,
        },
        context={
            'source': 'real',
            'mode': 'live',
            'baseline_analysis_packet': str(legacy_baseline_packet),
            'baseline_window_id': 'reviewed-canary-report-window2',
        },
        lineage={'dataset_manifest': manifest_path},
    )

    manifest_context = report_bundle['manifest']['context']

    assert comparison_baseline_path.exists()
    assert _resolve_reported_path(str(manifest_context.get('baseline_analysis_packet', '') or '')) == comparison_baseline_path
    assert str(manifest_context.get('baseline_window_id', '') or '') == 'reviewed-canary-report-window2'


def test_ds_report_bundle_accepts_historical_manual_register_comparison_packet_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    historical_entry, _, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='historical_canary_report_window1',
        display_name='Historical Canary Report Window1',
        run_id='historical-canary-report-window1',
        source='real',
        mode='canary',
        recorded_at_utc='2026-04-14T02:10:00Z',
        workflow='manual-register',
    )
    _, manifest_path, _, _ = _seed_librarian_dataset_entry(
        anchor,
        project_root,
        slug='historical_live_report_target_window1',
        display_name='Historical Live Report Target Window1',
        run_id='historical-live-report-target-window1',
        source='real',
        mode='live',
        recorded_at_utc='2026-04-14T02:12:00Z',
        workflow='manual-register',
    )
    review_policy_packet = project_root / 'local_untracked' / 'reports' / 'historical_canary_report_policy_packet.md'
    review_policy_packet.parent.mkdir(parents=True, exist_ok=True)
    review_policy_packet.write_text('# historical canary report policy\n', encoding='utf-8')
    emitted = observerctl_module._ds_emit_comparison_baseline_packet(
        historical_entry,
        baseline_stage='canary_reviewed',
        companion_role='historical reviewed canary report companion',
        review_policy_packet=str(review_policy_packet),
    )
    legacy_baseline_packet = project_root / 'local_untracked' / 'analysis' / 'evidence' / 'observerctl_baseline-analysis_historical.json'
    legacy_baseline_packet.parent.mkdir(parents=True, exist_ok=True)
    legacy_baseline_packet.write_text(json.dumps({'baseline_window_id': 'historical-canary-report-window1'}), encoding='utf-8')

    bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-historical-report-context')
    evaluation_dir = bundle.artifact_dirs['evaluation']
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    run_json = evaluation_dir / 'run.json'
    run_md = evaluation_dir / 'run.md'
    run_json.write_text('{}\n', encoding='utf-8')
    run_md.write_text('# eval historical report context\n', encoding='utf-8')

    report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-04-14T02:20:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Historical evaluation completed through observerctl ds.',
            'run_id': bundle.run_id,
            'collection_alias': 'hist-rpt1',
            'threshold': 0.22,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': run_json,
            'run_md': run_md,
        },
        context={
            'source': 'real',
            'mode': 'live',
            'baseline_analysis_packet': str(legacy_baseline_packet),
            'baseline_window_id': 'historical-canary-report-window1',
        },
        lineage={'dataset_manifest': manifest_path},
    )

    manifest_context = report_bundle['manifest']['context']

    assert _resolve_reported_path(str(manifest_context.get('baseline_analysis_packet', '') or '')) == _resolve_reported_path(emitted['packet_path'])
    assert str(manifest_context.get('baseline_window_id', '') or '') == 'historical-canary-report-window1'


def test_ds_report_publication_repairs_stale_eval_alias_from_materialized_build_dataset(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    build_bundle = prepare_report_bundle(anchor, 'build', run_id='build-shared-canonical')
    dataset_dir = build_bundle.artifact_dirs['dataset']
    dataset_dir.mkdir(parents=True, exist_ok=True)
    materialized_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
    materialized_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'total_records': 1,
        'has_labels': False,
    }), encoding='utf-8')

    build_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=build_bundle,
        packet={
            'timestamp_utc': '2026-04-13T01:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'collection_alias': 'can-r0b70',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset build completed through observerctl ds.',
            'run_id': build_bundle.run_id,
            'reason_codes': [],
            'artifacts': {},
        },
        artifact_paths={
            'dataset_manifest': materialized_manifest,
            'features_csv': features_csv,
        },
        context={'dataset_seed': 42},
        lineage={'source_run_root': build_bundle.run_root},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=build_report_bundle['manifest'])

    eval_bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-stale-history')
    evaluation_dir = eval_bundle.artifact_dirs['evaluation']
    model_dir = eval_bundle.run_root / 'model'
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    run_json = evaluation_dir / 'run.json'
    run_md = evaluation_dir / 'run.md'
    model_path = model_dir / 'model.pkl'
    run_json.write_text('{"decision":"go"}\n', encoding='utf-8')
    run_md.write_text('# eval\n', encoding='utf-8')
    model_path.write_bytes(b'model')

    eval_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=eval_bundle,
        packet={
            'timestamp_utc': '2026-04-13T01:10:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'collection_alias': 'can-r0b70',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Evaluation completed through observerctl ds.',
            'run_id': eval_bundle.run_id,
            'threshold': 0.42,
            'reason_codes': [],
            'artifacts': {},
        },
        artifact_paths={
            'dataset_manifest': materialized_manifest,
            'run_json': run_json,
            'run_md': run_md,
            'model_path': model_path,
        },
        context={'max_fpr': 0.01},
        lineage={'dataset_manifest': materialized_manifest, 'model_path': model_path},
    )

    stale_manifest = dict(eval_report_bundle['manifest'])
    stale_manifest['collection_alias'] = 'can-r4ccf'
    manifest_path = project_root / eval_report_bundle['paths']['manifest_json']
    manifest_path.write_text(json.dumps(stale_manifest, indent=2, sort_keys=True), encoding='utf-8')
    append_ds_run_index(project_anchor=anchor, manifest_payload=stale_manifest)

    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=stale_manifest)

    canonical_eval_doc = project_root / 'docs' / 'reports' / 'collections' / 'can-r0b70' / 'processing' / 'eval' / '20260413T011000000000Z.eval.md'
    stale_alias_root = project_root / 'docs' / 'reports' / 'collections' / 'can-r4ccf'

    assert publication['decision'] == 'go'
    assert publication['current_run']['collection_alias'] == 'can-r0b70'
    assert canonical_eval_doc.exists()
    assert not stale_alias_root.exists()


def test_ds_report_publication_threshold_summary_only_uses_evaluate_packets_and_pairs_scores_by_alias(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    evaluate_bundle = prepare_report_bundle(anchor, 'evaluate', run_id='eval-threshold')
    evaluation_dir = evaluate_bundle.artifact_dirs['evaluation']
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    eval_run_json = evaluation_dir / 'run.json'
    eval_run_md = evaluation_dir / 'run.md'
    eval_run_json.write_text('{}\n', encoding='utf-8')
    eval_run_md.write_text('# eval threshold\n', encoding='utf-8')
    evaluate_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=evaluate_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-evaluate',
            'command_family': 'ds',
            'command_path': 'observerctl ds evaluate',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.evaluation_harness',
            'summary': 'Evaluation completed through observerctl ds.',
            'run_id': evaluate_bundle.run_id,
            'collection_alias': 'can-thresh',
            'threshold': 0.42,
            'anomaly_direction': 'lower-is-more-anomalous',
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'run_json': eval_run_json,
            'run_md': eval_run_md,
        },
        context={'max_fpr': 0.01},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=evaluate_report_bundle['manifest'])

    score_bundle = prepare_report_bundle(anchor, 'score', run_id='score-threshold')
    scoring_dir = score_bundle.artifact_dirs['scoring']
    scoring_dir.mkdir(parents=True, exist_ok=True)
    scores_csv = scoring_dir / 'scores.csv'
    scores_csv.write_text('record_id,score_anomaly\na,0.1\nb,0.9\n', encoding='utf-8')
    score_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=score_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:05:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-score',
            'command_family': 'ds',
            'command_path': 'observerctl ds score',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.score_unsupervised',
            'summary': 'Unsupervised scoring completed through observerctl ds.',
            'run_id': score_bundle.run_id,
            'collection_alias': 'can-thresh',
            'records_scored': 2,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'scores_csv': scores_csv,
        },
        context={'output_override': False},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=score_report_bundle['manifest'])

    pipeline_bundle = prepare_report_bundle(anchor, 'pipeline', run_id='pipeline-threshold')
    pipeline_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=pipeline_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:10:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-run',
            'command_family': 'ds',
            'command_path': 'observerctl ds run pipeline',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.run_pipeline',
            'summary': 'Pipeline completed through observerctl ds.',
            'run_id': pipeline_bundle.run_id,
            'collection_alias': 'can-thresh',
            'threshold': 0.51,
            'anomaly_direction': 'lower-is-more-anomalous',
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={'root_dir': pipeline_bundle.run_root},
        context={'max_fpr': 0.01},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=pipeline_report_bundle['manifest'])

    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=score_report_bundle['manifest'])
    thresholds_payload = json.loads((project_root / publication['aggregate_paths']['thresholds_json']).read_text(encoding='utf-8'))
    threshold_summary_md = (project_root / publication['aggregate_paths']['thresholds_md']).read_text(encoding='utf-8')

    assert publication['decision'] == 'go'
    assert thresholds_payload['threshold_run_count'] == 1
    assert len(thresholds_payload['threshold_rows']) == 1
    row = thresholds_payload['threshold_rows'][0]
    assert row['collection_alias'] == 'can-thresh'
    assert row['run_id'] == 'eval-threshold'
    assert row['workflow'] == 'evaluate'
    assert row['published_report_md'].endswith('20260331T120000000000Z.eval.md')
    assert row['paired_score_report_md'].endswith('20260331T120500000000Z.score.md')
    assert 'Packet workflow' not in threshold_summary_md
    assert '`pipeline-threshold`' not in threshold_summary_md


def test_ds_report_publication_zero_state_generated_surfaces_remains_truthful(tmp_path: Path) -> None:
    from analysis.report_aggregate import refresh_tracked_ds_publication

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _seed_shipped_manual_report_surfaces(project_root)

    publication = refresh_tracked_ds_publication(project_anchor=anchor)
    generated_surfaces_text = (project_root / publication['aggregate_paths']['generated_surfaces_md']).read_text(encoding='utf-8')

    assert publication['decision'] == 'go'
    assert publication['published_run_count'] == 0
    assert 'When published runs exist, they are rendered under `docs/reports/collections/<collection-alias>/`.' in generated_surfaces_text
    assert 'Zero-state publication may leave `docs/reports/collections/` present but empty' in generated_surfaces_text
    assert 'whenever packet families are materialized' in generated_surfaces_text
    assert 'Zero-state publication should remain honest' in generated_surfaces_text
    assert '## Aggregate surface roles' in generated_surfaces_text
    assert 'Runtime-safe population census' in generated_surfaces_text
    assert 'Published runs are rendered under `docs/reports/collections/<collection-alias>/`.' not in generated_surfaces_text


def test_ds_report_publication_excludes_demo_workflow_and_resets_cache(tmp_path: Path) -> None:
    from analysis.report_aggregate import append_ds_run_index, publication_eligibility_reasons, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    build_bundle = prepare_report_bundle(anchor, 'build', run_id='build-public')
    build_dataset_dir = build_bundle.artifact_dirs['dataset']
    build_dataset_dir.mkdir(parents=True, exist_ok=True)
    (build_dataset_dir / 'dataset_manifest.json').write_text('{}\n', encoding='utf-8')
    (build_dataset_dir / 'features.csv').write_text('record_id\n', encoding='utf-8')
    build_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=build_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset built through observerctl ds.',
            'run_id': build_bundle.run_id,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={
            'dataset_manifest': build_dataset_dir / 'dataset_manifest.json',
            'features_csv': build_dataset_dir / 'features.csv',
        },
        context={'output_override': False},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=build_report_bundle['manifest'])

    demo_bundle = prepare_report_bundle(anchor, 'demo', run_id='demo-blocked')
    demo_report_bundle = write_report_bundle(
        project_anchor=anchor,
        bundle=demo_bundle,
        packet={
            'timestamp_utc': '2026-03-31T12:05:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-run',
            'command_family': 'ds',
            'command_path': 'observerctl ds run demo',
            'implementation_state': 'automation-available',
            'underlying_surface': 'analysis.run_demo',
            'summary': 'Demo pipeline completed through observerctl ds.',
            'run_id': demo_bundle.run_id,
            'artifacts': {},
            'reason_codes': [],
        },
        artifact_paths={'root_dir': demo_bundle.run_root},
        context={'output_override': False},
    )
    append_ds_run_index(project_anchor=anchor, manifest_payload=demo_report_bundle['manifest'])

    stale_path = project_root / 'docs' / 'reports' / 'ds' / 'stale.md'
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text('stale\n', encoding='utf-8')

    reasons = publication_eligibility_reasons(project_anchor=anchor, manifest_payload=demo_report_bundle['manifest'])
    publication = refresh_tracked_ds_publication(project_anchor=anchor, current_manifest_payload=build_report_bundle['manifest'])
    by_workflow_payload = json.loads((project_root / publication['aggregate_paths']['by_workflow_json']).read_text(encoding='utf-8'))

    assert 'publication_skipped:workflow_not_publishable' in reasons
    assert publication['decision'] == 'go'
    assert publication['published_run_count'] == 1
    assert publication['current_run']['run_id'] == 'build-public'
    assert 'build' in by_workflow_payload['workflows']
    assert 'demo' not in by_workflow_payload['workflows']
    assert not stale_path.exists()
    assert (project_root / publication['current_run']['published_report_paths']['markdown']).exists()


def test_ds_run_pipeline_unsupervised_emits_visual_figures(monkeypatch, tmp_path: Path) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    input_path = tmp_path / 'input.jsonl'
    _write_signed_jsonl(input_path, _make_ds_records())

    payload = observerctl_module._ds_run_pipeline(
        [input_path],
        '',
        'unsupervised',
        123,
        0.7,
        0.15,
        0.15,
        0.01,
    )

    assert payload['decision'] == 'go'
    assert payload['anomaly_direction'] == 'lower-is-more-anomalous'
    assert payload['visuals']['decision'] == 'go'
    assert payload['thresholding']['anomaly_direction'] == 'lower-is-more-anomalous'
    figure_ids = [str(figure.get('id', '')) for figure in payload['visuals']['figures']]
    assert len(figure_ids) == len(set(figure_ids))
    for figure in payload['visuals']['figures']:
        assert {'id', 'title', 'caption', 'path', 'kind'}.issubset(set(figure.keys()))
        assert str(figure['path']).strip()
    assert (project_root / payload['artifacts']['score_distribution_png']).exists()
    assert (project_root / payload['artifacts']['threshold_selection_png']).exists()
    assert (project_root / payload['artifacts']['metric_comparison_png']).exists()
    assert (project_root / payload['artifacts']['workflow_summary_png']).exists()
    assert payload['publication']['decision'] == 'go'
    assert payload['publication']['current_run']['figure_count'] >= 1


def test_ds_build_with_canonical_run_root_publishes_tracked_ds_surfaces(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    input_path = tmp_path / 'input.jsonl'
    _write_signed_jsonl(input_path, _make_ds_records())

    rc = main(['ds', 'build', '--input', str(input_path), '--seed', '123', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['publication']['decision'] == 'go'
    assert payload['publication']['published_run_count'] == 1
    assert payload['publication']['current_run']['figure_count'] == 3
    assert any(str(path).endswith('split_balance.png') for path in payload['publication']['current_run']['published_figures'])
    assert (project_root / payload['artifacts']['tracked_ds_index_md']).exists()
    assert (project_root / payload['artifacts']['tracked_ds_latest_json']).exists()
    assert (project_root / payload['artifacts']['tracked_ds_by_workflow_json']).exists()
    assert (project_root / payload['artifacts']['published_report_md']).exists()
    assert (project_root / payload['artifacts']['published_report_manifest_json']).exists()


def test_sandbox_list_emits_definition_catalog_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_definitions', lambda: [
        {
            'id': 'metadata-contract',
            'title': 'Metadata contract probe',
            'summary': 'Validate metadata contract expectations.',
            'status': 'stable',
            'category': 'metadata-probe',
            'writes_to': 'report_tmp/frame4_metadata_contract_probe',
        }
    ])

    rc = main(['sandbox', 'list', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-list'
    assert payload['decision'] == 'go'
    assert payload['definitions'][0]['id'] == 'metadata-contract'


def test_sandbox_list_human_output_uses_structured_decision_block(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_definitions', lambda: [
        {
            'id': 'metadata-contract',
            'title': 'Metadata contract probe',
            'summary': 'Validate metadata contract expectations.',
            'status': 'stable',
            'category': 'metadata-probe',
            'writes_to': 'report_tmp/frame4_metadata_contract_probe',
        }
    ])

    rc = main(['sandbox', 'list'])
    assert rc == 0

    out = capsys.readouterr().out
    assert '[ ORACL-Prime :: observerctl ] SANDBOX/CATALOG' in out
    assert '[OK] SANDBOX_DEFINITIONS_LISTED' in out
    assert 'Template Class  : decision' in out
    assert 'Definition Count: 1' in out
    assert 'metadata-contract' in out
    assert 'Purpose         : Validate metadata contract expectations.' in out


def test_ds_wizard_exit_command_suppresses_post_exit_emit(capsys) -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'exit')

    assert should_exit is True
    assert packet is not None
    assert packet['suppress_human_emit'] is True

    observerctl_module._emit(packet, as_json=False)

    assert capsys.readouterr().out == ''


def test_ds_wizard_execute_blocked_stays_in_wizard_and_lists_blockers() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'run')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'execute')

    assert packet is None
    assert should_exit is False
    assert observerctl_module._ds_wizard_transient_lines(state) == ['execute blocked: validate this workflow first']


def test_ds_wizard_forced_color_keeps_prefix_plain_on_picker_lines(monkeypatch) -> None:
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('OBSERVERCTL_COLOR', 'always')
    line = observerctl_module._style_choice_label('1. [*] ', 'sim')

    assert line.startswith('1. [*] ')
    assert '\x1b[' in line[len('1. [*] '):]


def test_sandbox_show_emits_definition_detail_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_definition', lambda definition_id: {
        'id': definition_id,
        'title': 'Metadata contract probe',
        'summary': 'Validate metadata contract expectations.',
        'status': 'stable',
        'category': 'metadata-probe',
        'aliases': [],
        'selector_policy': 'exact-name-only',
        'writes_to': 'report_tmp/frame4_metadata_contract_probe',
        'purpose': 'Verify metadata contract fields.',
        'command': 'observerctl sandbox run metadata-contract',
        'run_index_path': 'report_tmp/frame4_metadata_contract_probe/run_index.jsonl',
    })

    rc = main(['sandbox', 'show', 'metadata-contract', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-show'
    assert payload['definition']['id'] == 'metadata-contract'
    assert payload['definition']['command'] == 'observerctl sandbox run metadata-contract'


def test_real_sandbox_registry_includes_ds_wizard_hydration_definition() -> None:
    definition = observerctl_module.sandbox_get_definition('ds-wizard-hydration')

    assert definition is not None
    assert definition['id'] == 'ds-wizard-hydration'
    assert definition['command'] == 'observerctl sandbox run ds-wizard-hydration'
    assert definition['run_index_path'].endswith('frame4_ds_wizard_hydration_probe/run_index.jsonl')


def test_real_sandbox_registry_includes_ds_wizard_durability_definition() -> None:
    definition = observerctl_module.sandbox_get_definition('ds-wizard-durability')

    assert definition is not None
    assert definition['id'] == 'ds-wizard-durability'
    assert definition['command'] == 'observerctl sandbox run ds-wizard-durability'
    assert definition['run_index_path'].endswith('frame6_ds_wizard_durability_probe/run_index.jsonl')


def test_real_sandbox_registry_includes_ds_wizard_execute_failure_truthfulness_definition() -> None:
    definition = observerctl_module.sandbox_get_definition('ds-wizard-execute-failure-truthfulness')

    assert definition is not None
    assert definition['id'] == 'ds-wizard-execute-failure-truthfulness'
    assert definition['command'] == 'observerctl sandbox run ds-wizard-execute-failure-truthfulness'
    assert definition['run_index_path'].endswith('frameb_ds_wizard_execute_failure_truthfulness_probe/run_index.jsonl')


def test_real_sandbox_registry_includes_ds_alias_coherence_definition() -> None:
    definition = observerctl_module.sandbox_get_definition('ds-alias-coherence')

    assert definition is not None
    assert definition['id'] == 'ds-alias-coherence'
    assert definition['command'] == 'observerctl sandbox run ds-alias-coherence'
    assert definition['run_index_path'].endswith('framed_ds_alias_coherence_probe/run_index.jsonl')


def test_real_sandbox_registry_includes_librarian_access_exchange_definition() -> None:
    definition = observerctl_module.sandbox_get_definition('librarian-access-exchange')

    assert definition is not None
    assert definition['id'] == 'librarian-access-exchange'
    assert definition['command'] == 'observerctl sandbox run librarian-access-exchange'
    assert definition['run_index_path'].endswith('librarian_access_exchange_probe/run_index.jsonl')


def test_real_sandbox_registry_includes_librarian_vault_controls_definition() -> None:
    definition = observerctl_module.sandbox_get_definition('librarian-vault-controls')

    assert definition is not None
    assert definition['id'] == 'librarian-vault-controls'
    assert definition['command'] == 'observerctl sandbox run librarian-vault-controls'
    assert definition['run_index_path'].endswith('librarian_vault_controls_probe/run_index.jsonl')


def test_sandbox_show_human_output_includes_alias_policy_and_trailing_contract(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_definition', lambda definition_id: {
        'id': definition_id,
        'title': 'Baseline monitor runtime probe',
        'summary': 'Validate baseline-monitor runtime liveness plus resource_normal retention continuity.',
        'status': 'stable',
        'category': 'runtime-probe',
        'aliases': [],
        'selector_policy': 'exact-name-only',
        'writes_to': 'report_tmp/job0022_baseline_monitor_runtime_probe',
        'purpose': 'Prove the sandboxed baseline-monitor runtime and saved evidence flow are intact.',
        'command': 'observerctl sandbox run baseline-monitor-runtime',
        'run_index_path': 'report_tmp/job0022_baseline_monitor_runtime_probe/run_index.jsonl',
    })

    rc = main(['sandbox', 'show', 'baseline-monitor-runtime'])
    assert rc == 0

    out = capsys.readouterr().out
    assert '[OK] SANDBOX_DEFINITION_READY' in out
    assert 'Selection' in out
    assert 'Aliases         : none (exact-name-only)' in out
    assert 'Guardrails' in out
    assert 'Contract' in out


def test_sandbox_show_missing_definition_human_output_guides_to_runs_review(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_definition', lambda definition_id: None)

    rc = main(['sandbox', 'show', 'metadata-contract-001'])
    assert rc == 2

    out = capsys.readouterr().out
    normalized = ' '.join(out.split())
    assert '[FAIL] SANDBOX_DEFINITION_NOT_FOUND' in out
    assert 'Sandbox definition details are unavailable for the requested identifier.' in out
    assert 'Requested       : metadata-contract-001' in out
    assert 'observerctl sandbox runs show metadata-contract-001' in normalized
    assert 'observerctl sandbox list' in out
    assert 'SANDBOX_DEFINITION_READY' not in out
    assert 'Definition details are available for review.' not in out


def test_sandbox_run_emits_execution_packet_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_run_definition', lambda definition_id: {
        'decision': 'go',
        'reason_codes': [],
        'definition_id': definition_id,
        'result': 'pass',
        'returncode': 0,
        'run_id': 'metadata-contract-001',
        'artifacts': {
            'report_json': 'report_tmp/frame4_metadata_contract_probe/metadata-contract-001/report.json',
            'run_index': 'report_tmp/frame4_metadata_contract_probe/run_index.jsonl',
        },
        'stdout_text': 'run_id=metadata-contract-001\n',
        'stderr_text': '',
        'next_review_command': 'observerctl sandbox runs show metadata-contract-001',
    })

    rc = main(['sandbox', 'run', 'metadata-contract', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-run'
    assert payload['definition_id'] == 'metadata-contract'
    assert payload['run_id'] == 'metadata-contract-001'


def test_sandbox_runs_list_emits_saved_runs_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_list_runs', lambda: [
        {
            'run_id': 'baseline-monitor-runtime-001',
            'definition_id': 'baseline-monitor-runtime',
            'timestamp_utc': '2026-03-23T00:00:00Z',
            'result': 'pass',
            'report_path': 'report_tmp/job0022_baseline_monitor_runtime_probe/baseline-monitor-runtime-001/report.json',
            'run_dir': 'report_tmp/job0022_baseline_monitor_runtime_probe/baseline-monitor-runtime-001',
            'index_path': 'report_tmp/job0022_baseline_monitor_runtime_probe/run_index.jsonl',
        }
    ])

    rc = main(['sandbox', 'runs', 'list', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-runs-list'
    assert payload['runs'][0]['definition_id'] == 'baseline-monitor-runtime'


def test_sandbox_runs_show_emits_run_review_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_run', lambda run_id: (
        {
            'run_id': run_id,
            'definition_id': 'metadata-contract',
            'timestamp_utc': '2026-03-23T00:00:00Z',
            'result': 'pass',
            'report_path': 'report_tmp/frame4_metadata_contract_probe/{0}/report.json'.format(run_id),
        },
        {
            'next_bite_result': 'pass',
            'all_sample_fields_present': True,
            'all_index_fields_present': True,
        },
    ))

    rc = main(['sandbox', 'runs', 'show', 'metadata-contract-001', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-runs-show'
    assert payload['run']['run_id'] == 'metadata-contract-001'
    assert payload['report']['all_sample_fields_present'] is True


def test_gate_check_go_in_sim_mode(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    observerctl_module._save_state('sim', 'watch')
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'go'
    assert gate['reason_codes'] == []


def test_canary_gate_marks_stage5_prerequisites_not_applicable(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    observerctl_module._save_state('sim', 'watch')
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')

    assert gate['decision'] == 'go'
    assert gate['stage5_prerequisites']['C22_baseline_validation_rate_escalated']['status'] == 'not_applicable'
    assert gate['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'not_applicable'
    assert gate['stage5_prerequisites']['C25_resource_baseline_window_ready']['status'] == 'not_applicable'
    assert gate['stage5_prerequisites']['baseline_monitor_runtime_ready']['status'] == 'not_applicable'
    assert gate['stage5_prerequisites']['overall']['status'] == 'not_applicable'


def test_gate_noop_transition_denied(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    observerctl_module._save_state('sim', 'watch')
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='watch')
    assert gate['decision'] == 'no-go'
    assert 'policy_denied:no_op_transition' in gate['reason_codes']


def test_gate_check_real_requires_api_key(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    monkeypatch.delenv('MOLTBOOK_API_KEY', raising=False)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='real')
    gate = evaluate_gate_decision(status)
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:env.moltbook_api_key' in gate['reason_codes']


def test_real_fetch_errors_mark_collection_error(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    (log_dir / 'calamum_agent.stderr.log').write_text(
        'ERROR:root:Network error on feed: 404 Client Error: Not Found for url: https://www.moltbook.com/api/v1/feed?limit=50\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'test-key')
    _set_security_report_ref(monkeypatch, log_dir)
    observerctl_module._save_state('real', 'watch')
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)

    status = collect_runtime_status(source='real')
    fetch_row = status['checks']['runtime.source_fetch']
    assert fetch_row['status'] == 'err'
    assert fetch_row['error_kind'] == 'http_404'
    assert fetch_row['endpoint'] == 'feed'
    assert status['checks']['runtime.collection_state']['state'] == 'error'
    assert status['checks']['runtime.collection_state']['status'] == 'err'

    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:collection_state_incoherent' in gate['reason_codes']


def test_gate_allows_idle_service_when_observer_heartbeat_stale(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    observer_hb = health / 'calamum_observer.heartbeat'
    stale_ts = 946684800.0  # 2000-01-01 UTC
    os.utime(observer_hb, (stale_ts, stale_ts))

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)

    status = collect_runtime_status(source='sim')
    assert status['checks']['runtime.observer_service']['status'] == 'ok'
    assert status['checks']['runtime.collection_state']['state'] in ('idle', 'warmup', 'stopped')

    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'go'
    assert 'critical_check_failed:observer_heartbeat_stale' not in gate.get('reason_codes', [])


def test_watchdog_check_stale_observer_heartbeat_is_advisory_when_service_alive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    observer_hb = health / 'calamum_observer.heartbeat'
    stale_ts = 946684800.0  # 2000-01-01 UTC
    os.utime(observer_hb, (stale_ts, stale_ts))

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)

    packet = observerctl_module._watchdog_check()
    assert packet.get('decision') == 'go'
    assert 'critical_check_failed:observer_heartbeat_stale' not in packet.get('reason_codes', [])
    assert 'major_check_failed:observer_heartbeat_stale_service_alive' in packet.get('advisory_reason_codes', [])


def test_evidence_pack_writes_publish_grade_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    output = tmp_path / 'evidence.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--output', str(output), '--json'])
    assert rc == 0
    assert output.exists()

    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['runtime_cli_surface'] == 'observerctl'
    assert 'provenance' in payload
    assert 'methodology' in payload
    assert 'process' in payload
    assert 'readiness_surfaces' in payload
    assert 'readiness_projection' in payload
    assert 'stage5_prerequisites' in payload
    assert payload['readiness_surfaces']['posture_receipt']['path'].endswith('watchdog_posture_state.json')
    assert payload['provenance']['artifact_sha256']


def test_evidence_pack_supports_non_activation_live_projection_and_saved_refs(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    segment_path = archive_dir / 'resource_sim_canary_normal_unit_seg0001.jsonl'
    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_window_proof_seg0001.jsonl'
    segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z","baseline_window_id":"baseline-proof-window"}\n', encoding='utf-8')
    resource_index = resource_dir / 'index.jsonl'
    resource_index.write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_normal',
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_baseline',
            'baseline_window_id': 'baseline-proof-window',
            'window_id': 'baseline-proof-window',
        }) + '\n',
        encoding='utf-8',
    )

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_test.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'baseline_window_id': 'baseline-proof-window',
        'sample_counts': {'resource_normal': 5, 'resource_baseline': 5},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    evidence_index = evidence_dir / 'index.jsonl'
    evidence_index.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-live-proof', '--output', str(output), '--json'])
    assert rc == 0
    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['gate_packet']['to_state'] == 'sim:live'
    assert payload['readiness_projection']['projection_mode'] == 'non-activation'
    assert payload['stage5_prerequisites']['C22_baseline_validation_rate_escalated']['status'] == 'ok'
    assert payload['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['C25_resource_baseline_window_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['baseline_monitor_runtime_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['overall']['status'] == 'ok'
    assert payload['readiness_surfaces']['baseline_monitor']['monitor_state_path'].endswith('baseline_monitor_state.json')
    assert payload['readiness_surfaces']['resource_stream_retention']['index_path'].endswith('resource/index.jsonl')
    assert payload['readiness_surfaces']['baseline_window']['packet_path'].endswith('observerctl_baseline-analysis_test.json')
    assert any(str(ref).endswith('baseline_monitor_state.json') for ref in payload['process']['evidence_refs'])


def test_non_activation_live_projection_keeps_c24_ready_when_collection_is_idle_with_fresh_resource_normal(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    segment_path = archive_dir / 'resource_sim_canary_normal_idle_seg0001.jsonl'
    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_idle_seg0001.jsonl'
    segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z","baseline_window_id":"frame8-idle-window"}\n', encoding='utf-8')
    (resource_dir / 'index.jsonl').write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(segment_path).replace('\\', '/'),
            'segment_records': 2,
            'stream_type': 'resource_normal',
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_baseline',
            'baseline_window_id': 'frame8-idle-window',
            'window_id': 'frame8-idle-window',
        }) + '\n',
        encoding='utf-8',
    )

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_idle_continuity.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'baseline_window_id': 'frame8-idle-window',
        'sample_counts': {'resource_normal': 2, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    status = collect_runtime_status(source='sim')
    assert status['checks']['runtime.observer_service']['status'] == 'ok'
    assert status['checks']['runtime.collection_state']['state'] in ('idle', 'warmup', 'stopped')
    assert status['checks']['watchdog.resource_stream_retention']['status'] == 'ok'
    assert status['checks']['watchdog.resource_stream_retention']['records_indexed'] == 2

    output = tmp_path / 'evidence_live_projection_idle_continuity.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-idle-continuity-proof', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['overall']['status'] == 'ok'


def test_non_activation_live_projection_denies_c24_when_only_baseline_stream_is_fresh(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_only_seg0001.jsonl'
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    (resource_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'segment_path': str(baseline_segment_path).replace('\\', '/'),
        'segment_records': 3,
        'stream_type': 'resource_baseline',
    }) + '\n', encoding='utf-8')

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_baseline_only.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'sample_counts': {'resource_normal': 0, 'resource_baseline': 3},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection_baseline_only.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-baseline-only-not-continuity', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    c24 = payload['stage5_prerequisites']['C24_resource_stream_retention_ready']
    assert c24['status'] == 'err'
    assert 'critical_check_failed:resource_stream_retention_unavailable' in c24['reason_codes']
    assert payload['stage5_prerequisites']['overall']['status'] == 'err'


def test_resource_stream_retention_resolves_archived_normal_segment_via_manifest(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame7-archived-normal',
        '--json',
    ]) == 0

    archive_dir = log_dir / 'data' / 'calamum' / 'archive'
    raw_segments_before = sorted(archive_dir.glob('resource_sim_canary_normal_frame7-archived-normal_seg*.jsonl'))
    assert len(raw_segments_before) >= 1

    Librarian(interval_sec=0.01).run_once()

    raw_segments_after = sorted(archive_dir.glob('resource_sim_canary_normal_frame7-archived-normal_seg*.jsonl'))
    archived_segments = sorted(archive_dir.glob('resource_sim_canary_normal_frame7-archived-normal_seg*.jsonl.gz'))
    assert raw_segments_after == []
    assert len(archived_segments) >= 1

    status = collect_runtime_status(source='sim')
    resource_row = status['checks']['watchdog.resource_stream_retention']
    assert resource_row['status'] == 'ok'
    assert resource_row['segment_exists'] is True
    assert resource_row['segment_resolution'] == 'archived'
    assert resource_row['resolved_segment_path'].endswith('.jsonl.gz')
    assert resource_row['archive_manifest_exists'] is True


def test_baseline_window_health_resolves_archived_baseline_segment_via_manifest(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame8-normal-support',
        '--json',
    ]) == 0

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'baseline',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame8-archived-baseline',
        '--json',
    ]) == 0

    Librarian(interval_sec=0.01).run_once()

    assert main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '1',
        '--min-normal-samples', '1',
        '--min-baseline-samples', '1',
        '--json',
    ]) == 0

    status = collect_runtime_status(source='sim')
    baseline_row = status['checks']['watchdog.resource_baseline_window']
    assert baseline_row['status'] == 'ok'
    assert baseline_row['baseline_window_id'] == 'frame8-archived-baseline'
    assert baseline_row['segment_count'] >= 1
    assert baseline_row['resolved_segment_count'] == baseline_row['segment_count']
    assert baseline_row['segment_resolution'] == 'archived'
    assert baseline_row['archive_manifest_exists'] is True
    assert any(str(ref).endswith('.jsonl.gz') for ref in baseline_row['resolved_segment_paths'])


def test_non_activation_live_projection_keeps_c24_ready_when_latest_normal_segment_is_archived(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame7-live-proof-archived',
        '--json',
    ]) == 0

    Librarian(interval_sec=0.01).run_once()

    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_frame7_archived.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'sample_counts': {'resource_normal': 2, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection_archived_normal.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-archived-normal-proof', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    resource_surface = payload['readiness_surfaces']['resource_stream_retention']
    c24 = payload['stage5_prerequisites']['C24_resource_stream_retention_ready']
    assert resource_surface['status'] == 'ok'
    assert resource_surface['segment_resolution'] == 'archived'
    assert resource_surface['resolved_segment_path'].endswith('.jsonl.gz')
    assert resource_surface['archive_manifest_path'].endswith('archive/manifest.json')
    assert c24['status'] == 'ok'
    assert c24['segment_resolution'] == 'archived'
    assert any(str(ref).endswith('archive/manifest.json') for ref in c24['evidence_refs'])
    assert any(str(ref).endswith('.jsonl.gz') for ref in c24['evidence_refs'])


def test_non_activation_live_projection_denies_c25_when_archived_baseline_artifact_is_missing(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame8-normal-continuity',
        '--json',
    ]) == 0

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'baseline',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame8-missing-baseline',
        '--json',
    ]) == 0

    Librarian(interval_sec=0.01).run_once()

    assert main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '1',
        '--min-normal-samples', '1',
        '--min-baseline-samples', '1',
        '--json',
    ]) == 0

    archive_dir = data / 'archive'
    archived_baseline_segments = sorted(archive_dir.glob('resource_sim_canary_baseline_frame8-missing-baseline_seg*.jsonl.gz'))
    assert archived_baseline_segments
    for path in archived_baseline_segments:
        path.unlink()

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection_missing_archived_baseline.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-missing-archived-baseline', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    c24 = payload['stage5_prerequisites']['C24_resource_stream_retention_ready']
    baseline_surface = payload['readiness_surfaces']['baseline_window']
    c25 = payload['stage5_prerequisites']['C25_resource_baseline_window_ready']
    assert c24['status'] == 'ok'
    assert baseline_surface['status'] == 'err'
    assert baseline_surface['baseline_window_id'] == 'frame8-missing-baseline'
    assert baseline_surface['segment_resolution'] == 'missing'
    assert baseline_surface['resolved_segment_count'] == 0
    assert any('frame8-missing-baseline' in str(ref) for ref in baseline_surface['missing_segment_paths'])
    assert c25['status'] == 'err'
    assert 'critical_check_failed:resource_baseline_window_incomplete' in c25['reason_codes']


def test_non_activation_live_projection_denies_c24_when_archived_manifest_artifact_is_missing(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    archive_dir = data / 'archive'
    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir.mkdir(parents=True, exist_ok=True)
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    raw_segment_path = archive_dir / 'resource_sim_canary_normal_frame7-missing-archive_seg0001.jsonl'
    manifest_path = archive_dir / 'manifest.json'
    manifest_path.write_text(json.dumps({
        raw_segment_path.name: {
            'artifact_path': 'resource_sim_canary_normal_frame7-missing-archive_seg0001.jsonl.gz',
            'records': 2,
            'uncompressed_bytes': 100,
        }
    }), encoding='utf-8')

    (resource_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'segment_path': str(raw_segment_path).replace('\\', '/'),
        'segment_records': 2,
        'stream_type': 'resource_normal',
    }) + '\n', encoding='utf-8')

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_frame7_missing_archive.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'sample_counts': {'resource_normal': 2, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection_missing_archived_normal.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-missing-archived-normal', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    resource_surface = payload['readiness_surfaces']['resource_stream_retention']
    c24 = payload['stage5_prerequisites']['C24_resource_stream_retention_ready']
    assert resource_surface['status'] == 'err'
    assert resource_surface['segment_resolution'] == 'missing'
    assert resource_surface['archive_manifest_path'].endswith('archive/manifest.json')
    assert c24['status'] == 'err'
    assert 'critical_check_failed:resource_stream_retention_unavailable' in c24['reason_codes']


def test_ops_mode_gate_and_set_flow(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    rc_gate = main(['ops', 'mode', 'gate', '--to', 'canary', '--source', 'sim', '--json'])
    assert rc_gate == 0

    rc_set = main(['ops', 'mode', 'set', '--to', 'canary', '--source', 'sim', '--json'])
    assert rc_set == 0

    rc_current = main(['ops', 'mode', 'current', '--json'])
    assert rc_current == 0


def test_ops_mode_transition_atomic_flow(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    observerctl_module._save_state('sim', 'watch')
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    out = tmp_path / 'transition_evidence.json'
    rc = main([
        'ops', 'mode', 'transition',
        '--to', 'canary',
        '--source', 'sim',
        '--event', 'unit-transition',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()


def test_ops_mode_transition_self_actuates_bounded_lockdown_blockers_before_mode_set(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control = log_dir / 'control' / 'calamum'
    data = log_dir / 'data' / 'calamum'
    for d in [log_dir / 'health', data, control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.delenv('CALAMUM_SECURITY_REPORT_REF', raising=False)

    observerctl_module._save_state('sim', 'canary')

    baseline_ready_receipt = tmp_path / 'baseline_ready_receipt.json'
    baseline_ready_receipt.write_text('{}\n', encoding='utf-8')

    call_counts = {'gate': 0, 'baseline_ready': 0}

    def _fake_collect_runtime_status(source: str = 'sim') -> dict:
        return {
            'timestamp_utc': observerctl_module._utc_now(),
            'runtime_cli_surface': 'observerctl',
            'source': source,
            'state_source': source,
            'mode': 'canary',
            'checks': {},
        }

    def _fake_gate(status: dict, target_mode: str = 'watch') -> dict:
        call_counts['gate'] += 1
        if call_counts['gate'] == 1:
            return {
                'timestamp_utc': observerctl_module._utc_now(),
                'runtime_cli_surface': 'observerctl',
                'decision': 'no-go',
                'reason_codes': [
                    'critical_check_failed:run_security_report_missing',
                    'critical_check_failed:lockdown_heartbeat_rate_not_escalated',
                    'critical_check_failed:lockdown_baseline_rate_not_escalated',
                    'critical_check_failed:resource_stream_retention_unavailable',
                    'critical_check_failed:resource_baseline_window_incomplete',
                ],
                'from_state': 'sim:canary',
                'to_state': 'sim:live',
                'profile': 'GP-4',
                'evidence_refs': ['pre-remediation-evidence'],
            }
        return {
            'timestamp_utc': observerctl_module._utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'reason_codes': [],
            'from_state': 'sim:canary',
            'to_state': 'sim:live',
            'profile': 'GP-4',
            'security_report_ref': str(os.getenv('CALAMUM_SECURITY_REPORT_REF', '') or ''),
            'evidence_refs': ['post-remediation-evidence'],
        }

    def _fake_baseline_ready(**kwargs) -> dict:
        call_counts['baseline_ready'] += 1
        return {
            'timestamp_utc': observerctl_module._utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'baseline-ready',
            'reason_codes': [],
            'validation_cycle_packet_path': str(baseline_ready_receipt).replace('\\', '/'),
            'evidence_refs': [str(baseline_ready_receipt).replace('\\', '/')],
            'gate_packet': {'decision': 'go', 'reason_codes': []},
        }

    def _fake_posture(source: str, mode: str, event: str = 'mode-set') -> dict:
        return {
            'timestamp_utc': observerctl_module._utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'posture-apply',
            'reason_codes': [],
            'source': source,
            'mode': mode,
            'readback_verified': True,
            'posture_trigger': observerctl_module._posture_for_mode(mode),
            'heartbeat_interval_seconds': 4.0 if mode == 'live' else 10.0,
            'baseline_validation_interval_seconds': 45.0 if mode == 'live' else 120.0,
            'posture_state_path': str(control / 'watchdog_posture_state.json').replace('\\', '/'),
            'receipt_path': str(tmp_path / 'posture_receipt.json').replace('\\', '/'),
        }

    def _fake_build_evidence(status: dict, gate: dict, event: str = 'manual') -> dict:
        return {
            'timestamp_utc': observerctl_module._utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': gate.get('decision', 'no-go'),
            'gate_packet': gate,
            'provenance': {
                'artifact_path': '',
                'artifact_sha256': '',
                'generated_at_utc': observerctl_module._utc_now(),
                'producer_process': 'test',
                'upstream_inputs': {},
            },
            'methodology': {},
            'process': {'evidence_refs': []},
        }

    monkeypatch.setattr(observerctl_module, 'collect_runtime_status', _fake_collect_runtime_status)
    monkeypatch.setattr(observerctl_module, 'evaluate_gate_decision', _fake_gate)
    monkeypatch.setattr(observerctl_module, '_baseline_ready', _fake_baseline_ready)
    monkeypatch.setattr(observerctl_module, '_apply_watchdog_posture', _fake_posture)
    monkeypatch.setattr(observerctl_module, 'build_evidence_pack', _fake_build_evidence)

    out = tmp_path / 'transition_self_actuated.json'
    packet = observerctl_module._ops_mode_transition(source='sim', to_mode='live', event='unit-transition-self-actuate', output=str(out))

    assert packet.get('decision') == 'go'
    assert call_counts['baseline_ready'] == 1
    assert packet.get('to_state') == 'sim:live'
    assert out.exists()

    remediation_packet = packet.get('remediation_packet') or {}
    assert remediation_packet.get('attempted') is True
    assert remediation_packet.get('decision') == 'go'
    assert (remediation_packet.get('security_report_packet') or {}).get('decision') == 'go'
    assert call_counts['gate'] >= 2

    security_report_ref = str(packet.get('security_report_ref', '') or '')
    assert security_report_ref
    assert Path(security_report_ref.replace('/', os.sep)).exists()

    run_context_path = control / 'observerctl_run_context.json'
    run_context = json.loads(run_context_path.read_text(encoding='utf-8'))
    assert run_context.get('security_report_ref') == security_report_ref

    state = observerctl_module._load_state()
    assert state.get('mode') == 'live'


def test_ops_mode_transition_does_not_self_actuate_nonremediable_gate_failure(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control = log_dir / 'control' / 'calamum'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.delenv('CALAMUM_SECURITY_REPORT_REF', raising=False)

    observerctl_module._save_state('sim', 'canary')

    baseline_ready_calls = {'count': 0}
    mode_set_calls = {'count': 0}

    monkeypatch.setattr(observerctl_module, 'collect_runtime_status', lambda source='sim': {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'source': source,
        'state_source': source,
        'mode': 'canary',
        'checks': {},
    })
    monkeypatch.setattr(observerctl_module, 'evaluate_gate_decision', lambda status, target_mode='watch': {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'reason_codes': ['critical_check_failed:observer_heartbeat_stale'],
        'from_state': 'sim:canary',
        'to_state': 'sim:live',
        'profile': 'GP-4',
        'evidence_refs': ['hard-fail-evidence'],
    })

    def _unexpected_baseline_ready(**kwargs) -> dict:
        baseline_ready_calls['count'] += 1
        return {'decision': 'go'}

    def _unexpected_mode_set(source: str, to_mode: str) -> dict:
        mode_set_calls['count'] += 1
        return {'decision': 'go'}

    monkeypatch.setattr(observerctl_module, '_baseline_ready', _unexpected_baseline_ready)
    monkeypatch.setattr(observerctl_module, '_ops_mode_set', _unexpected_mode_set)

    packet = observerctl_module._ops_mode_transition(source='sim', to_mode='live', event='unit-transition-hard-fail', output='')

    assert packet.get('decision') == 'no-go'
    assert packet.get('reason_codes') == ['critical_check_failed:observer_heartbeat_stale']
    remediation_packet = packet.get('remediation_packet') or {}
    assert remediation_packet.get('attempted') is False
    assert baseline_ready_calls['count'] == 0
    assert mode_set_calls['count'] == 0
    assert not (control / 'observerctl_run_context.json').exists()


def test_ops_mode_switch_fails_closed_when_self_actuation_does_not_clear_gate(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control = log_dir / 'control' / 'calamum'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.delenv('CALAMUM_SECURITY_REPORT_REF', raising=False)

    observerctl_module._save_state('sim', 'canary')

    call_counts = {'gate': 0, 'baseline_ready': 0, 'runtime_stop': 0, 'runtime_start': 0}

    monkeypatch.setattr(observerctl_module, 'collect_runtime_status', lambda source='sim': {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'source': source,
        'state_source': source,
        'mode': 'canary',
        'checks': {},
    })

    def _fake_gate(status: dict, target_mode: str = 'watch') -> dict:
        call_counts['gate'] += 1
        return {
            'timestamp_utc': observerctl_module._utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'reason_codes': [
                'critical_check_failed:run_security_report_missing',
                'critical_check_failed:lockdown_heartbeat_rate_not_escalated',
                'critical_check_failed:resource_stream_retention_unavailable',
            ],
            'from_state': 'sim:canary',
            'to_state': 'sim:live',
            'profile': 'GP-4',
            'security_report_ref': str(os.getenv('CALAMUM_SECURITY_REPORT_REF', '') or ''),
            'evidence_refs': ['still-blocked-evidence'],
        }

    def _fake_baseline_ready(**kwargs) -> dict:
        call_counts['baseline_ready'] += 1
        return {
            'timestamp_utc': observerctl_module._utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'baseline-ready',
            'reason_codes': ['critical_check_failed:lockdown_heartbeat_rate_not_escalated'],
            'validation_cycle_packet_path': str(tmp_path / 'baseline_ready_failed.json').replace('\\', '/'),
            'evidence_refs': [],
        }

    monkeypatch.setattr(observerctl_module, 'evaluate_gate_decision', _fake_gate)
    monkeypatch.setattr(observerctl_module, '_baseline_ready', _fake_baseline_ready)
    monkeypatch.setattr(observerctl_module, '_ops_runtime_stop', lambda timeout_sec=8.0: call_counts.__setitem__('runtime_stop', call_counts['runtime_stop'] + 1) or {'decision': 'go'})
    monkeypatch.setattr(observerctl_module, '_ops_runtime_start', lambda source, mode, interval_sec, timeout_sec: call_counts.__setitem__('runtime_start', call_counts['runtime_start'] + 1) or {'decision': 'go'})

    packet = observerctl_module._ops_mode_switch(
        source='sim',
        to_mode='live',
        event='unit-switch-fail-closed',
        output='',
        interval_sec=1.0,
        stop_timeout_sec=0.0,
        startup_probe_sec=0.0,
    )

    assert packet.get('decision') == 'no-go'
    assert 'critical_check_failed:lockdown_heartbeat_rate_not_escalated' in packet.get('reason_codes', [])
    remediation_packet = packet.get('remediation_packet') or {}
    assert remediation_packet.get('attempted') is True
    assert remediation_packet.get('decision') == 'no-go'
    assert call_counts['baseline_ready'] == 1
    assert call_counts['runtime_stop'] == 0
    assert call_counts['runtime_start'] == 0


def test_ops_mode_switch_single_action_syncs_runtime_and_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    observerctl_module._save_state('sim', 'watch')

    # Stabilize gate inputs without requiring real process lifecycle.
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_observer_status',
        lambda max_age_sec=60.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 1234, 'alive': True},
            'pending_stop_signal': False,
        },
    )
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_baseline_monitor_status',
        lambda max_age_sec=90.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 2222, 'alive': True},
            'monitor_state': {'mode': 'canary'},
        },
    )

    calls = {'stop': 0, 'start': 0}

    def _fake_runtime_status() -> dict:
        return {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 1234, 'alive': True},
            'pending_stop_signal': False,
        }

    def _fake_runtime_stop(timeout_sec: float = 8.0) -> dict:
        calls['stop'] += 1
        return {
            'timestamp_utc': '2026-01-01T00:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'runtime-stop',
            'reason_codes': [],
            'stopped_cleanly': True,
            'escalated_terminate': False,
        }

    def _fake_runtime_start(source: str, mode: str, interval_sec: float, timeout_sec: float) -> dict:
        calls['start'] += 1
        return {
            'timestamp_utc': '2026-01-01T00:00:01Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'runtime-start',
            'reason_codes': [],
            'startup_verified': True,
            'state': 'active',
            'pid': {'value': 5678, 'alive': True},
            'source': source,
            'mode': mode,
        }

    monkeypatch.setattr(observerctl_module, '_ops_runtime_status', _fake_runtime_status)
    monkeypatch.setattr(observerctl_module, '_ops_runtime_stop', _fake_runtime_stop)
    monkeypatch.setattr(observerctl_module, '_ops_runtime_start', _fake_runtime_start)

    rc = main(['ops', 'mode', 'switch', '--to', 'canary', '--json'])
    assert rc == 0

    state = observerctl_module._load_state()
    assert state.get('source') == 'sim'
    assert state.get('mode') == 'canary'
    assert calls['stop'] == 1
    assert calls['start'] == 1


def test_ops_mode_switch_defaults_source_from_ssot_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'test-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    observerctl_module._save_state('real', 'watch')

    monkeypatch.setattr(
        observerctl_module,
        '_runtime_observer_status',
        lambda max_age_sec=60.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 1111, 'alive': True},
            'pending_stop_signal': False,
        },
    )
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_baseline_monitor_status',
        lambda max_age_sec=90.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 3333, 'alive': True},
            'monitor_state': {'mode': 'canary'},
        },
    )
    monkeypatch.setattr(observerctl_module, '_ops_runtime_status', lambda: {
        'state': 'stopped',
        'heartbeat': {'status': 'err'},
        'pid': {'value': None, 'alive': False},
        'pending_stop_signal': False,
    })
    monkeypatch.setattr(observerctl_module, '_ops_runtime_stop', lambda timeout_sec=8.0: {
        'timestamp_utc': '2026-01-01T00:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'runtime-stop',
        'reason_codes': [],
    })

    seen = {'source': ''}

    def _fake_runtime_start(source: str, mode: str, interval_sec: float, timeout_sec: float) -> dict:
        seen['source'] = source
        return {
            'timestamp_utc': '2026-01-01T00:00:01Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'runtime-start',
            'reason_codes': [],
            'startup_verified': True,
            'state': 'active',
            'pid': {'value': 5678, 'alive': True},
        }

    monkeypatch.setattr(observerctl_module, '_ops_runtime_start', _fake_runtime_start)

    rc = main(['ops', 'mode', 'switch', '--to', 'canary', '--json'])
    assert rc == 0
    assert seen['source'] == 'real'



def test_ops_evidence_verify_schema_failure(tmp_path: Path, monkeypatch) -> None:
    bad_packet = tmp_path / 'bad_packet.json'
    bad_packet.write_text('{"timestamp_utc":"2026-02-21T00:00:00Z"}\n', encoding='utf-8')

    rc = main(['ops', 'evidence', 'verify', '--packet', str(bad_packet), '--json'])
    assert rc == 2


def test_baseline_librarian_watchdog_health_policy_commands(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    assert main(['baseline', 'status', '--json']) in (0, 2)
    assert main(['baseline', 'check', '--json']) in (0, 2)
    assert main(['baseline', 'set', '--id', 'baseline-ci', '--json']) == 0

    assert main(['librarian', 'stats', '--json']) == 0
    assert main(['librarian', 'stores', '--json']) == 0
    assert main(['librarian', 'rotate', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'compact', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'verify', '--mode', 'watch', '--json']) == 0

    assert main(['watchdog', 'status', '--json']) == 0
    assert main(['watchdog', 'check', '--json']) in (0, 2)
    assert main(['watchdog', 'reasons', '--json']) == 0
    assert main(['watchdog', 'ack', '--code', 'critical_check_failed:watchdog_heartbeat_stale', '--json']) == 0

    assert main(['health', 'quick', '--json']) in (0, 2)
    assert main(['health', 'full', '--json']) in (0, 2)
    assert main(['health', 'explain', '--code', 'critical_check_failed:real_key_missing', '--json']) == 0

    assert main(['policy', 'show', '--json']) == 0
    assert main(['policy', 'validate', '--json']) in (0, 2)


def test_baseline_collect_writes_publish_grade_packet_and_resource_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = tmp_path / 'baseline_collect_packet.json'
    rc = main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'unit-window-001',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-collect'
    assert packet.get('profile') == 'normal'
    assert int(packet.get('sample_count', 0)) >= 2
    assert packet.get('provenance', {}).get('artifact_sha256')
    assert 'interpretation_policy_ref' not in packet
    assert 'authorization_boundary_ref' not in packet
    assert 'recommendation_profile' not in packet

    resource_state = log_dir / 'control' / 'calamum' / 'watchdog_resource_state.json'
    assert resource_state.exists()
    resource_doc = json.loads(resource_state.read_text(encoding='utf-8'))
    assert float(resource_doc.get('sample_count', 0)) >= 2
    assert resource_doc.get('stream_type') == 'resource_normal'


def test_baseline_collect_preserves_frame4_metadata_contract_on_samples_and_index_rows(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    normal_out = tmp_path / 'baseline_collect_normal_packet.json'
    baseline_out = tmp_path / 'baseline_collect_baseline_packet.json'

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame4-normal-window',
        '--output', str(normal_out),
        '--json',
    ]) == 0

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'baseline',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame4-baseline-window',
        '--output', str(baseline_out),
        '--json',
    ]) == 0

    normal_packet = json.loads(normal_out.read_text(encoding='utf-8'))
    baseline_packet = json.loads(baseline_out.read_text(encoding='utf-8'))

    normal_segment_path = Path(str((normal_packet.get('segments', [{}])[0] or {}).get('path', '')).replace('/', os.sep))
    baseline_segment_path = Path(str((baseline_packet.get('segments', [{}])[0] or {}).get('path', '')).replace('/', os.sep))
    normal_sample = _read_jsonl_rows(normal_segment_path)[0]
    baseline_sample = _read_jsonl_rows(baseline_segment_path)[0]

    resource_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'resource' / 'index.jsonl'
    normal_index = _latest_jsonl_row_for_stream(resource_index, 'resource_normal')
    baseline_index = _latest_jsonl_row_for_stream(resource_index, 'resource_baseline')

    for row in (normal_sample, normal_index, baseline_sample, baseline_index):
        assert row.get('sampling_profile_id')
        assert row.get('mode_at_capture') == 'canary'
        assert row.get('source_axis') == 'sim'
        assert row.get('stream_type') in ('resource_normal', 'resource_baseline')

    assert normal_sample.get('sampling_profile_id') == 'resource_normal_v1'
    assert normal_index.get('sampling_profile_id') == 'resource_normal_v1'
    assert baseline_sample.get('sampling_profile_id') == 'resource_baseline_v1'
    assert baseline_index.get('sampling_profile_id') == 'resource_baseline_v1'

    assert normal_sample.get('baseline_window_id') == 'frame4-normal-window'
    assert 'baseline_window_id' not in normal_index
    assert baseline_sample.get('baseline_window_id') == 'frame4-baseline-window'
    assert baseline_index.get('baseline_window_id') == 'frame4-baseline-window'


def test_baseline_analyze_returns_go_when_minimums_met(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    # Build one normal stream sample set and one rapid stream sample set.
    assert main([
        'baseline', 'collect',
        '--source', 'sim', '--mode', 'canary', '--profile', 'normal',
        '--duration-sec', '0.02', '--interval-sec', '0.01', '--window-id', 'unit-window-normal', '--json',
    ]) == 0
    assert main([
        'baseline', 'collect',
        '--source', 'sim', '--mode', 'canary', '--profile', 'baseline',
        '--duration-sec', '0.02', '--interval-sec', '0.01', '--window-id', 'unit-window-baseline', '--json',
    ]) == 0

    out = tmp_path / 'baseline_analysis_packet.json'
    rc = main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '24',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('action') == 'baseline-analyze'
    assert packet.get('baseline_ready') is True
    assert packet.get('decision') == 'go'
    stats = packet.get('resource_statistics', {})
    assert 'cpu_p95' in stats
    assert 'cpu_rate_p95_per_s' in stats
    assert packet.get('provenance', {}).get('artifact_sha256')
    assert 'recommendation_profile' not in packet
    assert 'policy_snapshot_ref' not in packet
    assert 'identity_assurance' not in packet
    assert 'human_impersonation_risk' not in packet


def test_baseline_analyze_no_go_when_window_incomplete(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    # Create only normal samples; require both normal+rapid to force a fail-closed no-go.
    assert main([
        'baseline', 'collect',
        '--source', 'sim', '--mode', 'canary', '--profile', 'normal',
        '--duration-sec', '0.02', '--interval-sec', '0.01', '--window-id', 'unit-window-only-normal', '--json',
    ]) == 0

    out = tmp_path / 'baseline_analysis_incomplete.json'
    rc = main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '24',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
        '--output', str(out),
        '--json',
    ])
    assert rc == 2
    assert out.exists()
    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'no-go'
    assert 'critical_check_failed:resource_baseline_window_incomplete' in packet.get('reason_codes', [])
    assert 'recommendation_profile' not in packet


def test_baseline_overnight_plan_emits_publish_grade_schedule_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = tmp_path / 'overnight_plan_packet.json'
    rc = main([
        'baseline', 'overnight-plan',
        '--source', 'real',
        '--mode', 'canary',
        '--overnight-hours', '8',
        '--normal-interval-sec', '30',
        '--rapid-interval-sec', '2',
        '--rapid-phase-sec', '1800',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-overnight-plan'
    assert packet.get('schedule_model') == 'baseline_start_then_normal_overnight_then_baseline_end'
    assert packet.get('provenance', {}).get('artifact_sha256')
    cmds = packet.get('execution_commands', [])
    assert isinstance(cmds, list)
    assert len(cmds) == 4
    assert 'baseline collect' in cmds[0]
    assert 'profile baseline' in cmds[0]
    assert 'profile normal' in cmds[1]
    assert 'baseline analyze' in cmds[3]
    assert 'recommendation_profile' not in packet
    assert 'policy_snapshot_ref' not in packet
    assert 'identity_assurance' not in packet
    assert 'human_impersonation_risk' not in packet


def test_baseline_overnight_plan_flags_projection_when_thresholds_too_high(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main([
        'baseline', 'overnight-plan',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '1',
        '--normal-interval-sec', '60',
        '--rapid-interval-sec', '10',
        '--rapid-phase-sec', '300',
        '--min-normal-samples', '1000',
        '--min-rapid-samples', '1000',
        '--json',
    ])
    assert rc == 0

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl'
    assert evidence_index.exists()
    lines = [ln for ln in evidence_index.read_text(encoding='utf-8').splitlines() if ln.strip()]
    assert len(lines) >= 1
    latest = json.loads(lines[-1])
    plan_packet_path = Path(str(latest.get('packet_path', '')).replace('/', os.sep))
    assert plan_packet_path.exists()
    plan_packet = json.loads(plan_packet_path.read_text(encoding='utf-8'))

    projection = plan_packet.get('readiness_projection', {})
    assert projection.get('normal_requirement_met_by_plan') is False
    assert projection.get('rapid_requirement_met_by_plan') is False

def test_baseline_overnight_run_executes_all_phases_and_returns_go(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = tmp_path / 'overnight_run_packet.json'
    rc = main([
        'baseline', 'overnight-run',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '0.0006',
        '--normal-interval-sec', '0.05',
        '--rapid-interval-sec', '0.05',
        '--rapid-phase-sec', '0.5',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-overnight-run'
    checkpoints = packet.get('checkpoints', [])
    assert isinstance(checkpoints, list)
    assert len(checkpoints) == 4
    phases = [cp.get('phase') for cp in checkpoints]
    assert phases == ['baseline_start', 'normal_overnight', 'baseline_end', 'analysis']
    assert all(str(cp.get('decision', 'no-go')) == 'go' for cp in checkpoints)
    assert packet.get('provenance', {}).get('artifact_sha256')


def test_baseline_overnight_run_fails_closed_when_analysis_not_ready(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main([
        'baseline', 'overnight-run',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '0.0006',
        '--normal-interval-sec', '0.05',
        '--rapid-interval-sec', '0.05',
        '--rapid-phase-sec', '0.5',
        '--min-normal-samples', '1000',
        '--min-rapid-samples', '1000',
        '--json',
    ])
    assert rc == 2

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl'
    assert evidence_index.exists()
    lines = [ln for ln in evidence_index.read_text(encoding='utf-8').splitlines() if ln.strip()]
    run_entries = [json.loads(ln) for ln in lines if 'baseline_overnight_run' in ln]
    assert len(run_entries) >= 1
    latest = run_entries[-1]
    packet_path = Path(str(latest.get('packet_path', '')).replace('/', os.sep))
    assert packet_path.exists()
    packet = json.loads(packet_path.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'no-go'
    reasons = packet.get('reason_codes', [])
    assert any('resource_baseline_window_incomplete' in str(r) for r in reasons)


def test_baseline_overnight_run_emits_progress_lines_without_json(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main([
        'baseline', 'overnight-run',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '0.0006',
        '--normal-interval-sec', '0.05',
        '--rapid-interval-sec', '0.05',
        '--rapid-phase-sec', '0.5',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
    ])
    assert rc == 0

    captured = capsys.readouterr()
    err = captured.err
    assert 'baseline overnight run started' in err
    assert 'phase_start baseline_start' in err
    assert 'phase_complete analysis decision=go baseline_ready=True' in err
    assert 'baseline overnight run completed decision=go' in err


def test_ops_mode_set_persists_lockdown_posture_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    gate_doc = {
        'decision': 'go',
        'timestamp_utc': observerctl_module._utc_now(),
        'from_state': 'sim:canary',
        'to_state': 'sim:live',
    }
    (control / 'observerctl_last_gate.json').write_text(json.dumps(gate_doc), encoding='utf-8')

    packet = observerctl_module._ops_mode_set(source='sim', to_mode='live')
    assert packet.get('decision') == 'go'
    posture_packet = packet.get('posture_packet', {})
    assert posture_packet.get('decision') == 'go'
    assert posture_packet.get('readback_verified') is True
    assert posture_packet.get('posture_trigger') == 'lockdown'
    assert float(posture_packet.get('heartbeat_interval_seconds', 0)) == 4.0
    assert float(posture_packet.get('baseline_validation_interval_seconds', 0)) == 45.0

    posture_state_path = Path(str(posture_packet.get('posture_state_path', '')).replace('/', os.sep))
    receipt_path = Path(str(posture_packet.get('receipt_path', '')).replace('/', os.sep))
    assert posture_state_path.exists()
    assert receipt_path.exists()

    posture_doc = json.loads((control / 'watchdog_posture_state.json').read_text(encoding='utf-8'))
    assert posture_doc.get('posture_trigger') == 'lockdown'
    assert float(posture_doc.get('heartbeat_interval_seconds', 0)) == 4.0
    assert float(posture_doc.get('baseline_validation_interval_seconds', 0)) == 45.0
    assert posture_doc.get('readback_verified') is False

    receipt_doc = json.loads(receipt_path.read_text(encoding='utf-8'))
    assert receipt_doc.get('decision') == 'go'
    assert receipt_doc.get('action') == 'posture-apply'
    assert receipt_doc.get('mode') == 'live'
    assert (receipt_doc.get('posture') or {}).get('readback_verified') is True
    assert (receipt_doc.get('provenance') or {}).get('artifact_sha256')


def test_ops_mode_set_rolls_back_state_when_posture_apply_fails(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    gate_doc = {
        'decision': 'go',
        'timestamp_utc': observerctl_module._utc_now(),
        'from_state': 'sim:canary',
        'to_state': 'sim:live',
    }
    (control / 'observerctl_last_gate.json').write_text(json.dumps(gate_doc), encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_apply_watchdog_posture', lambda source, mode, event='mode-set': {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': 'posture-apply',
        'source': source,
        'mode': mode,
        'reason_codes': ['critical_check_failed:watchdog_posture_persist_failed'],
        'readback_verified': False,
        'posture_state_path': str(control / 'watchdog_posture_state.json').replace('\\', '/'),
        'receipt_path': '',
    })

    packet = observerctl_module._ops_mode_set(source='sim', to_mode='live')
    assert packet.get('decision') == 'no-go'
    assert 'critical_check_failed:watchdog_posture_persist_failed' in packet.get('reason_codes', [])
    assert packet.get('attempted_to_state') == 'sim:live'
    assert packet.get('rollback_anchor') == {'source': 'sim', 'mode': 'canary'}
    assert packet.get('rollback_applied') is True
    assert packet.get('restored_state') == {'source': 'sim', 'mode': 'canary'}
    assert packet.get('restored_readback_state') == {'source': 'sim', 'mode': 'canary'}

    state = observerctl_module._load_state()
    assert state.get('source') == 'sim'
    assert state.get('mode') == 'canary'


def test_ops_mode_transition_surfaces_mode_set_rollback_failure(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    observerctl_module._save_state('sim', 'canary')
    monkeypatch.setattr(observerctl_module, 'evaluate_gate_decision', lambda status, target_mode='watch': {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'phase': 'gate',
        'reason_codes': [],
        'advisory_reason_codes': [],
        'source': 'sim',
        'from_state': 'sim:canary',
        'to_state': 'sim:live',
        'target_mode': target_mode,
    })
    monkeypatch.setattr(observerctl_module, '_apply_watchdog_posture', lambda source, mode, event='mode-set': {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': 'posture-apply',
        'source': source,
        'mode': mode,
        'reason_codes': ['critical_check_failed:watchdog_posture_persist_failed'],
        'readback_verified': False,
        'posture_state_path': str(control / 'watchdog_posture_state.json').replace('\\', '/'),
        'receipt_path': '',
    })

    packet = observerctl_module._ops_mode_transition(source='sim', to_mode='live', event='unit-transition-rollback', output='')
    assert packet.get('decision') == 'no-go'
    assert 'critical_check_failed:watchdog_posture_persist_failed' in packet.get('reason_codes', [])
    assert (packet.get('gate_packet') or {}).get('decision') == 'go'
    mode_set_packet = packet.get('mode_set_packet') or {}
    assert mode_set_packet.get('decision') == 'no-go'
    assert mode_set_packet.get('rollback_applied') is True
    assert mode_set_packet.get('rollback_anchor') == {'source': 'sim', 'mode': 'canary'}
    assert any(str(ref).endswith('watchdog_posture_state.json') for ref in packet.get('evidence_refs', []))


def test_baseline_monitor_once_writes_state_and_normal_stream(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')

    rc = main([
        'baseline', 'monitor-once',
        '--source', 'sim',
        '--mode', 'canary',
        '--normal-interval-sec', '0.01',
        '--baseline-interval-sec', '45',
        '--baseline-window-sec', '0.2',
        '--baseline-sample-interval-sec', '0.05',
        '--min-normal-samples', '1',
        '--min-baseline-samples', '1',
        '--json',
    ])
    assert rc == 0

    monitor_state = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
    assert monitor_state.exists()
    monitor_doc = json.loads(monitor_state.read_text(encoding='utf-8'))
    assert monitor_doc.get('mode') == 'canary'
    assert monitor_doc.get('last_validation_cycle_event') == 'baseline_monitor_cycle'
    cycle_packet_path = Path(str(monitor_doc.get('last_validation_cycle_packet_path', '')).replace('/', os.sep))
    assert cycle_packet_path.exists()

    cycle_packet = json.loads(cycle_packet_path.read_text(encoding='utf-8'))
    assert cycle_packet.get('action') == 'baseline-monitor-cycle'
    assert cycle_packet.get('mode') == 'canary'
    assert cycle_packet.get('posture_trigger') == 'isolation'
    assert cycle_packet.get('baseline_window_id') == ''
    assert cycle_packet.get('normal_packet_path')
    assert cycle_packet.get('analysis_packet_path') == ''
    assert (cycle_packet.get('continuity') or {}).get('state') == 'fresh_start'

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl'
    cycle_row = _latest_jsonl_row_for_event(evidence_index, 'baseline_monitor_cycle')
    assert cycle_row.get('decision') == 'go'
    assert Path(str(cycle_row.get('packet_path', '')).replace('/', os.sep)).exists()

    resource_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'resource' / 'index.jsonl'
    assert resource_index.exists()
    latest = json.loads([ln for ln in resource_index.read_text(encoding='utf-8').splitlines() if ln.strip()][-1])
    assert latest.get('stream_type') == 'resource_normal'


def test_baseline_monitor_once_lockdown_cycle_emits_append_only_validation_record_with_baseline_linkage(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'live')

    packet = observerctl_module._baseline_monitor_once(
        source='sim',
        mode='live',
        normal_interval_sec=0.01,
        baseline_interval_sec=0.01,
        baseline_window_sec=0.2,
        baseline_sample_interval_sec=0.05,
        min_normal_samples=1,
        min_baseline_samples=1,
    )

    assert packet.get('decision') == 'go'
    assert packet.get('validation_cycle_event') == 'baseline_monitor_cycle'

    cycle_packet_path = Path(str(packet.get('validation_cycle_packet_path', '')).replace('/', os.sep))
    assert cycle_packet_path.exists()

    cycle_packet = json.loads(cycle_packet_path.read_text(encoding='utf-8'))
    assert cycle_packet.get('action') == 'baseline-monitor-cycle'
    assert cycle_packet.get('mode') == 'live'
    assert cycle_packet.get('posture_trigger') == 'lockdown'
    assert cycle_packet.get('baseline_window_id')
    assert cycle_packet.get('baseline_packet_path')
    assert cycle_packet.get('analysis_packet_path')
    assert cycle_packet.get('monitor_state_path').endswith('baseline_monitor_state.json')
    assert (cycle_packet.get('continuity') or {}).get('state') == 'fresh_start'

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'live' / 'evidence' / 'index.jsonl'
    cycle_row = _latest_jsonl_row_for_event(evidence_index, 'baseline_monitor_cycle')
    assert cycle_row.get('decision') == 'go'
    assert Path(str(cycle_row.get('packet_path', '')).replace('/', os.sep)).exists()

    monitor_state = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
    monitor_doc = json.loads(monitor_state.read_text(encoding='utf-8'))
    assert monitor_doc.get('last_validation_cycle_event') == 'baseline_monitor_cycle'
    assert monitor_doc.get('last_validation_cycle_decision') == 'go'
    assert monitor_doc.get('last_validation_cycle_packet_path') == str(cycle_packet_path).replace('\\', '/')
    assert monitor_doc.get('last_baseline_window_id') == cycle_packet.get('baseline_window_id')


def test_baseline_monitor_once_preserves_restart_continuity_anchors_between_cycles(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'live')

    observerctl_module._baseline_monitor_once(
        source='sim',
        mode='live',
        normal_interval_sec=0.01,
        baseline_interval_sec=0.01,
        baseline_window_sec=0.2,
        baseline_sample_interval_sec=0.05,
        min_normal_samples=1,
        min_baseline_samples=1,
    )

    monitor_state_path = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
    first_monitor_doc = json.loads(monitor_state_path.read_text(encoding='utf-8'))
    first_cycle_path = str(first_monitor_doc.get('last_validation_cycle_packet_path', '') or '')
    first_baseline_packet_path = str(first_monitor_doc.get('last_baseline_packet_path', '') or '')
    first_analysis_packet_path = str(first_monitor_doc.get('last_analysis_packet_path', '') or '')
    first_baseline_window_id = str(first_monitor_doc.get('last_baseline_window_id', '') or '')

    second_packet = observerctl_module._baseline_monitor_once(
        source='sim',
        mode='live',
        normal_interval_sec=999.0,
        baseline_interval_sec=999.0,
        baseline_window_sec=0.2,
        baseline_sample_interval_sec=0.05,
        min_normal_samples=1,
        min_baseline_samples=1,
    )

    second_cycle_path = str(second_packet.get('validation_cycle_packet_path', '') or '')
    assert second_cycle_path
    assert second_cycle_path != first_cycle_path

    second_cycle_doc = json.loads(Path(second_cycle_path.replace('/', os.sep)).read_text(encoding='utf-8'))
    continuity = second_cycle_doc.get('continuity') or {}
    assert continuity.get('state') == 'preserved'
    assert (continuity.get('previous_validation_cycle') or {}).get('packet_path') == first_cycle_path
    assert (continuity.get('previous_baseline') or {}).get('packet_path') == first_baseline_packet_path
    assert (continuity.get('previous_baseline') or {}).get('window_id') == first_baseline_window_id
    assert continuity.get('previous_analysis_packet_path') == first_analysis_packet_path
    assert second_cycle_doc.get('baseline_packet_path') == ''
    assert second_cycle_doc.get('analysis_packet_path') == ''
    assert first_cycle_path in ((second_cycle_doc.get('process') or {}).get('evidence_refs') or [])

    second_monitor_doc = json.loads(monitor_state_path.read_text(encoding='utf-8'))
    assert second_monitor_doc.get('last_baseline_packet_path') == first_baseline_packet_path
    assert second_monitor_doc.get('last_analysis_packet_path') == first_analysis_packet_path
    assert second_monitor_doc.get('last_baseline_window_id') == first_baseline_window_id


def test_baseline_monitor_once_degrades_explicitly_when_persisted_state_is_malformed(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')

    malformed_state_path = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
    malformed_state_path.write_text(json.dumps({
        'last_normal_sample_epoch_s': 'not-a-float',
        'last_validation_cycle_packet_path': 123,
        'last_validation_cycle_at_utc': 'definitely-not-utc',
        'last_baseline_packet_path': 456,
    }), encoding='utf-8')

    packet = observerctl_module._baseline_monitor_once(
        source='sim',
        mode='canary',
        normal_interval_sec=0.01,
        baseline_interval_sec=45.0,
        baseline_window_sec=0.2,
        baseline_sample_interval_sec=0.05,
        min_normal_samples=1,
        min_baseline_samples=1,
    )

    cycle_packet_path = Path(str(packet.get('validation_cycle_packet_path', '')).replace('/', os.sep))
    cycle_packet = json.loads(cycle_packet_path.read_text(encoding='utf-8'))
    continuity = cycle_packet.get('continuity') or {}
    assert continuity.get('state') == 'degraded'
    assert 'major_check_failed:baseline_monitor_state_malformed' in (continuity.get('reason_codes') or [])
    assert (continuity.get('detail_codes') or [])
    assert (continuity.get('previous_validation_cycle') or {}).get('packet_path') == '123'

    repaired_state = json.loads(malformed_state_path.read_text(encoding='utf-8'))
    assert repaired_state.get('last_normal_sample_epoch_s') != 'not-a-float'
    assert repaired_state.get('last_baseline_packet_path') == '456'


def test_baseline_monitor_status_cli_emits_truth_contract_fields(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    observerctl_module._save_state('sim', 'canary')
    _touch(log_dir / 'health' / 'calamum_baseline_monitor.heartbeat')
    observerctl_module._baseline_monitor_pid_path().write_text(str(os.getpid()), encoding='utf-8')
    (log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json').write_text(
        json.dumps({
            'source': 'sim',
            'mode': 'canary',
            'last_validation_cycle_event': 'baseline_ready',
            'last_validation_cycle_packet_path': 'logs/data/calamum/observer_derived/sim/canary/evidence/observerctl_baseline_ready.json',
        }),
        encoding='utf-8',
    )

    rc = main(['baseline', 'monitor-status', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload.get('decision') == 'go'
    assert payload.get('action') == 'baseline-monitor-status'
    assert payload.get('runtime_label') == 'baseline-monitor'
    assert payload.get('summary') == 'Baseline monitor runtime ready.'
    assert payload.get('reason_codes') == []
    assert payload.get('state') == 'active'
    assert ((payload.get('monitor_state') or {}).get('last_validation_cycle_event')) == 'baseline_ready'


def test_baseline_ready_writes_receipt_and_updates_monitor_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    _set_signing_env(monkeypatch)
    _set_security_report_ref(monkeypatch, log_dir)

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    observerctl_module._agent_pid_path().write_text(str(os.getpid()), encoding='utf-8')
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monkeypatch.setattr(observerctl_module, '_baseline_monitor_start', lambda **kwargs: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-start',
        'reason_codes': [],
        'state': 'active',
        'pid': {'value': os.getpid(), 'alive': True},
        'startup_verified': True,
    })

    packet = observerctl_module._baseline_ready(
        source='sim',
        mode='canary',
        target_mode='live',
        normal_interval_sec=0.01,
        baseline_window_sec=0.05,
        baseline_sample_interval_sec=0.01,
        min_normal_samples=1,
        min_baseline_samples=1,
        startup_probe_sec=0.0,
        timeout_sec=0.0,
    )

    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-ready'
    assert packet.get('mode') == 'canary'
    assert packet.get('target_mode') == 'live'
    assert packet.get('projection_mode') == 'non-activation'
    assert ((packet.get('gate_packet') or {}).get('decision')) == 'go'
    assert ((packet.get('stage5_prerequisites') or {}).get('overall', {}).get('status')) == 'ok'
    assert str((packet.get('normal_packet') or {}).get('artifact_path', '')).strip() != ''
    assert str((packet.get('baseline_packet') or {}).get('artifact_path', '')).strip() != ''
    assert str((packet.get('analysis_packet') or {}).get('artifact_path', '')).strip() != ''

    receipt_path = Path(str(packet.get('validation_cycle_packet_path', '')).replace('/', os.sep))
    assert receipt_path.exists()
    receipt_doc = json.loads(receipt_path.read_text(encoding='utf-8'))
    assert receipt_doc.get('decision') == 'go'
    assert receipt_doc.get('target_mode') == 'live'

    monitor_state_path = Path(str(packet.get('monitor_state_path', '')).replace('/', os.sep))
    monitor_state = json.loads(monitor_state_path.read_text(encoding='utf-8'))
    assert monitor_state.get('last_validation_cycle_event') == 'baseline_ready'
    assert monitor_state.get('last_validation_cycle_decision') == 'go'
    assert monitor_state.get('last_validation_cycle_packet_path') == str(receipt_path).replace('\\', '/')
    assert str(monitor_state.get('last_baseline_window_id', '')).strip() != ''

    evidence_index = data / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl'
    ready_row = _latest_jsonl_row_for_event(evidence_index, 'baseline_ready')
    assert ready_row.get('decision') == 'go'
    assert Path(str(ready_row.get('packet_path', '')).replace('/', os.sep)).exists()


def test_live_gate_accepts_fresh_baseline_ready_receipt_without_pretransition_lockdown_cadence(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    _set_signing_env(monkeypatch)
    _set_security_report_ref(monkeypatch, log_dir)

    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')
    observerctl_module._agent_pid_path().write_text(str(os.getpid()), encoding='utf-8')
    observerctl_module._baseline_monitor_pid_path().write_text(str(os.getpid()), encoding='utf-8')

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)
    (control / 'baseline_monitor_state.json').write_text(json.dumps({
        'source': 'sim',
        'mode': 'canary',
        'posture_trigger': 'isolation',
        'last_validation_cycle_event': 'baseline_ready',
    }), encoding='utf-8')

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    normal_segment_path = archive_dir / 'resource_sim_canary_normal_framec_gate_seg0001.jsonl'
    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_framec_gate_seg0001.jsonl'
    normal_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z","baseline_window_id":"framec-gate-window"}\n', encoding='utf-8')
    (resource_dir / 'index.jsonl').write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(normal_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_normal',
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_baseline',
            'baseline_window_id': 'framec-gate-window',
            'window_id': 'framec-gate-window',
        }) + '\n',
        encoding='utf-8',
    )

    baseline_analysis_path = evidence_dir / 'observerctl_baseline-analysis_framec_gate.json'
    baseline_ready_path = evidence_dir / 'observerctl_baseline_ready_framec_gate.json'
    baseline_analysis_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'baseline_window_id': 'framec-gate-window',
        'sample_counts': {'resource_normal': 1, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_analysis_path).replace('\\', '/')},
    }), encoding='utf-8')
    baseline_ready_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'action': 'baseline-ready',
        'source': 'sim',
        'mode': 'canary',
        'target_mode': 'live',
        'reason_codes': [],
        'summary': 'Baseline readiness is green for the target gate.',
        'provenance': {'artifact_path': str(baseline_ready_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'event': 'baseline_analysis',
            'packet_path': str(baseline_analysis_path).replace('\\', '/'),
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'event': 'baseline_ready',
            'packet_path': str(baseline_ready_path).replace('\\', '/'),
        }) + '\n',
        encoding='utf-8',
    )

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='live')

    assert gate['decision'] == 'go'
    assert gate['reason_codes'] == []
    assert gate['baseline_ready_receipt']['projection_authorized'] is True
    assert gate['baseline_ready_receipt']['path'] == str(baseline_ready_path).replace('\\', '/')
    assert gate['stage5_prerequisites']['C22_baseline_validation_rate_escalated']['status'] == 'ok'
    assert gate['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'ok'
    assert gate['stage5_prerequisites']['C25_resource_baseline_window_ready']['status'] == 'ok'
    assert gate['stage5_prerequisites']['overall']['status'] == 'ok'
    assert any(str(ref).endswith('observerctl_baseline_ready_framec_gate.json') for ref in gate['evidence_refs'])


def test_non_activation_live_projection_can_prove_c22_from_projected_lockdown_defaults(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'isolation'}), encoding='utf-8')

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    segment_path = archive_dir / 'resource_sim_canary_normal_projection_seg0001.jsonl'
    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_projection_seg0001.jsonl'
    segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z","baseline_window_id":"frame8-monitor-window"}\n', encoding='utf-8')
    (resource_dir / 'index.jsonl').write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_normal',
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_baseline',
            'baseline_window_id': 'frame8-monitor-window',
            'window_id': 'frame8-monitor-window',
        }) + '\n',
        encoding='utf-8',
    )

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_projection_test.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'baseline_window_id': 'frame8-monitor-window',
        'sample_counts': {'resource_normal': 1, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    output = tmp_path / 'evidence_live_projection_from_monitor.json'
    rc_pack = main([
        'ops', 'evidence', 'pack',
        '--source', 'sim',
        '--to', 'live',
        '--event', 'unit-live-proof-from-monitor',
        '--output', str(output),
        '--json',
    ])
    assert rc_pack == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['readiness_projection']['projection_mode'] == 'non-activation'
    assert payload['stage5_prerequisites']['C22_baseline_validation_rate_escalated']['status'] == 'ok'
    assert payload['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['C25_resource_baseline_window_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['overall']['status'] == 'ok'


def test_baseline_generate_and_check_filesystem_hashes(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('hello baseline\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    rc_generate = main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json'])
    assert rc_generate == 0
    assert baseline_path.exists()

    rc_check = main(['baseline', 'check', '--baseline', str(baseline_path), '--json'])
    assert rc_check == 0


def test_baseline_generate_start_routes_to_monitor_start_and_seed_cycle(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('sim', 'canary')

    monkeypatch.setattr(observerctl_module, '_runtime_baseline_monitor_status', lambda max_age_sec=90.0: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': 'baseline-monitor-status',
        'state': 'stopped',
        'reason_codes': ['critical_check_failed:baseline_monitor_runtime_inactive'],
        'monitor_state': {},
    })
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_start', lambda **kwargs: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-start',
        'reason_codes': [],
        'state': 'active',
        'pid': {'value': 2468, 'alive': True},
        'startup_verified': True,
    })
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_once', lambda **kwargs: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-once',
        'reason_codes': [],
        'validation_cycle_event': 'baseline_monitor_cycle',
        'validation_cycle_packet_path': str(tmp_path / 'seed_cycle.json').replace('\\', '/'),
        'validation_cycle_packet_decision': 'go',
    })

    rc = main(['baseline', 'generate', '--start', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload.get('decision') == 'go'
    assert payload.get('action') == 'baseline-generate'
    assert payload.get('generate_mode') == 'start'
    assert payload.get('repair_requested') is False
    assert payload.get('mode') == 'canary'
    assert payload.get('source') == 'sim'
    assert (payload.get('baseline_monitor_start_packet') or {}).get('action') == 'baseline-monitor-start'
    assert (payload.get('seed_packet') or {}).get('validation_cycle_event') == 'baseline_monitor_cycle'


def test_baseline_generate_start_repair_runs_repair_then_seed(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    control = log_dir / 'control' / 'calamum'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('sim', 'canary')
    (control / 'baseline_monitor_state.json').write_text(json.dumps({
        'last_normal_sample_epoch_s': 'bad-float',
    }), encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_runtime_baseline_monitor_status', lambda max_age_sec=90.0: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': 'baseline-monitor-status',
        'state': 'stopped',
        'reason_codes': ['critical_check_failed:baseline_monitor_runtime_inactive'],
        'monitor_state': {},
    })

    repair_calls = {'posture': 0, 'stop': 0}

    def _fake_posture(source: str, mode: str, event: str = 'mode-set') -> dict:
        repair_calls['posture'] += 1
        return {
            'timestamp_utc': observerctl_module._utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'posture-apply',
            'reason_codes': [],
            'source': source,
            'mode': mode,
            'receipt_path': str(tmp_path / 'repair_posture.json').replace('\\', '/'),
            'posture_state_path': str(control / 'watchdog_posture_state.json').replace('\\', '/'),
        }

    def _fake_stop(timeout_sec: float = 8.0) -> dict:
        repair_calls['stop'] += 1
        return {
            'timestamp_utc': observerctl_module._utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'baseline-monitor-stop',
            'reason_codes': [],
            'stopped_cleanly': True,
        }

    monkeypatch.setattr(observerctl_module, '_apply_watchdog_posture', _fake_posture)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_stop', _fake_stop)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_start', lambda **kwargs: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-start',
        'reason_codes': [],
        'state': 'active',
        'pid': {'value': 2468, 'alive': True},
        'startup_verified': True,
    })
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_once', lambda **kwargs: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-once',
        'reason_codes': [],
        'validation_cycle_event': 'baseline_monitor_cycle',
        'validation_cycle_packet_path': str(tmp_path / 'repair_seed_cycle.json').replace('\\', '/'),
        'validation_cycle_packet_decision': 'go',
    })

    rc = main(['baseline', 'generate', '--start', '--repair', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload.get('decision') == 'go'
    assert payload.get('generate_mode') == 'start-repair'
    assert payload.get('repair_requested') is True
    assert repair_calls['posture'] == 1
    assert repair_calls['stop'] == 1
    assert (payload.get('repair_packet') or {}).get('action') == 'posture-apply'
    assert (payload.get('repair_stop_packet') or {}).get('action') == 'baseline-monitor-stop'


def test_baseline_generate_repair_requires_start(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main(['baseline', 'generate', '--repair', '--json'])
    assert rc == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload.get('decision') == 'no-go'
    assert payload.get('action') == 'baseline-generate'
    assert 'policy_denied:baseline_generate_repair_requires_start' in payload.get('reason_codes', [])


def test_baseline_status_uses_runtime_validation_cycle_not_chunked_catalog(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    control = log_dir / 'control' / 'calamum'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('sim', 'canary')

    cycle_path = tmp_path / 'baseline_cycle.json'
    cycle_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'action': 'baseline-monitor-cycle',
        'reason_codes': [],
    }), encoding='utf-8')

    monitor_state = {
        'last_validation_cycle_packet_path': str(cycle_path).replace('\\', '/'),
        'last_validation_cycle_decision': 'go',
        'last_validation_cycle_event': 'baseline_monitor_cycle',
        'last_validation_cycle_at_utc': observerctl_module._utc_now(),
        'last_normal_sample_epoch_s': float(observerctl_module.time.time()),
    }
    (control / 'baseline_monitor_state.json').write_text(json.dumps(monitor_state), encoding='utf-8')

    def _legacy_catalog_guard() -> dict:
        raise AssertionError('legacy chunked catalog should not be consulted')

    monkeypatch.setattr(observerctl_module, '_load_baselines', _legacy_catalog_guard)
    monkeypatch.setattr(observerctl_module, '_runtime_baseline_monitor_status', lambda max_age_sec=90.0: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-status',
        'state': 'active',
        'reason_codes': [],
        'heartbeat': {'status': 'ok'},
        'pid': {'value': 2468, 'alive': True},
        'monitor_state': monitor_state,
    })

    rc = main(['baseline', 'status', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload.get('decision') == 'go'
    assert payload.get('baseline_type') == 'observer_runtime'
    assert (payload.get('validation_cycle') or {}).get('exists') is True
    assert (payload.get('validation_cycle') or {}).get('decision') == 'go'


def test_baseline_check_uses_runtime_validation_cycle_not_chunked_catalog(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    control = log_dir / 'control' / 'calamum'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('sim', 'canary')

    cycle_path = tmp_path / 'baseline_cycle.json'
    cycle_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'action': 'baseline-monitor-cycle',
        'reason_codes': [],
    }), encoding='utf-8')

    monitor_state = {
        'last_validation_cycle_packet_path': str(cycle_path).replace('\\', '/'),
        'last_validation_cycle_decision': 'go',
        'last_validation_cycle_event': 'baseline_monitor_cycle',
        'last_validation_cycle_at_utc': observerctl_module._utc_now(),
        'last_normal_sample_epoch_s': float(observerctl_module.time.time()),
    }
    (control / 'baseline_monitor_state.json').write_text(json.dumps(monitor_state), encoding='utf-8')

    def _legacy_catalog_guard() -> dict:
        raise AssertionError('legacy chunked catalog should not be consulted')

    monkeypatch.setattr(observerctl_module, '_load_baselines', _legacy_catalog_guard)
    monkeypatch.setattr(observerctl_module, '_runtime_baseline_monitor_status', lambda max_age_sec=90.0: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-status',
        'state': 'active',
        'reason_codes': [],
        'heartbeat': {'status': 'ok'},
        'pid': {'value': 2468, 'alive': True},
        'monitor_state': monitor_state,
    })

    rc = main(['baseline', 'check', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload.get('decision') == 'go'
    assert payload.get('baseline_type') == 'observer_runtime'
    assert (payload.get('validation_cycle') or {}).get('exists') is True
    assert (payload.get('validation_cycle') or {}).get('decision') == 'go'


def test_baseline_status_human_output_surfaces_chunked_graph_contract_and_evidence(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    control = log_dir / 'control' / 'calamum'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('sim', 'canary')

    cycle_path = tmp_path / 'baseline_cycle.json'
    cycle_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'action': 'baseline-monitor-cycle',
        'reason_codes': [],
    }), encoding='utf-8')

    baseline_packet_path = tmp_path / 'baseline_analysis.json'
    baseline_packet_path.write_text(json.dumps({'decision': 'go'}), encoding='utf-8')
    analysis_packet_path = tmp_path / 'baseline_window.json'
    analysis_packet_path.write_text(json.dumps({'decision': 'go'}), encoding='utf-8')

    monitor_state = {
        'source': 'sim',
        'mode': 'canary',
        'last_validation_cycle_packet_path': str(cycle_path).replace('\\', '/'),
        'last_validation_cycle_decision': 'go',
        'last_validation_cycle_event': 'baseline-monitor-cycle',
        'last_validation_cycle_at_utc': observerctl_module._utc_now(),
        'last_normal_sample_epoch_s': float(observerctl_module.time.time()),
        'last_baseline_window_id': 'framec-ready-window',
        'last_baseline_packet_path': str(baseline_packet_path).replace('\\', '/'),
        'last_analysis_packet_path': str(analysis_packet_path).replace('\\', '/'),
    }
    monitor_state_path = control / 'baseline_monitor_state.json'
    monitor_state_path.write_text(json.dumps(monitor_state), encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_runtime_baseline_monitor_status', lambda max_age_sec=90.0: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-status',
        'summary': 'Baseline monitor runtime ready.',
        'reason_codes': [],
        'source': 'sim',
        'mode': 'canary',
        'runtime_label': 'baseline-monitor',
        'state': 'active',
        'heartbeat': {'status': 'ok', 'age_seconds': 1.0, 'max_age_seconds': 90.0},
        'pid': {'value': 2468, 'alive': True},
        'monitor_state': monitor_state,
        'monitor_state_path': str(monitor_state_path).replace('\\', '/'),
    })

    rc = main(['baseline', 'status'])
    assert rc == 0

    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Observer baseline status'
    assert 'Contract' in rendered
    assert any('Graph architecture:' in line and 'chunked resource_normal/resource_baseline segments + resource index + archive continuity' in line for line in rendered)
    assert 'Validation cycle' in rendered
    assert any('Resource index:' in line and 'canary/resource/index.jsonl' in line for line in rendered)
    assert any('Evidence index:' in line and 'canary/evidence/index.jsonl' in line for line in rendered)
    assert any('Validation cycle:' in line and 'baseline_cycle.json' in line for line in rendered)
    assert any('Monitor state:' in line and 'control/calamum/baseline_monitor_state.json' in line for line in rendered)
    assert 'Guidance' in rendered


def test_baseline_status_human_output_surfaces_fail_closed_runtime_reasons(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    control = log_dir / 'control' / 'calamum'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('real', 'canary')

    monitor_state_path = control / 'baseline_monitor_state.json'
    monitor_state_path.write_text('{}\n', encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_runtime_baseline_monitor_status', lambda max_age_sec=90.0: {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': 'baseline-monitor-status',
        'summary': 'Baseline monitor runtime stopped.',
        'reason_codes': ['critical_check_failed:baseline_monitor_runtime_inactive'],
        'source': 'real',
        'mode': 'canary',
        'runtime_label': 'baseline-monitor',
        'state': 'stopped',
        'heartbeat': {'status': 'err', 'max_age_seconds': 90.0},
        'pid': {'value': None, 'alive': False},
        'monitor_state': {},
        'monitor_state_path': str(monitor_state_path).replace('\\', '/'),
    })

    rc = main(['baseline', 'status'])
    assert rc == 2

    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Observer baseline status'
    assert 'Reasons' in rendered
    assert any('critical_check_failed:baseline_monitor_runtime_inactive' in line for line in rendered)
    assert any('critical_check_failed:baseline_validation_cycle_missing' in line for line in rendered)
    assert 'Guidance' in rendered
    assert any('chunked baseline graph lane' in line for line in rendered)


def test_baseline_monitor_status_human_output_surfaces_joined_chunked_graph_guidance(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)

    observerctl_module._save_state('sim', 'canary')
    _touch(log_dir / 'health' / 'calamum_baseline_monitor.heartbeat')
    observerctl_module._baseline_monitor_pid_path().write_text(str(os.getpid()), encoding='utf-8')
    (log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json').write_text(
        json.dumps({
            'source': 'sim',
            'mode': 'canary',
            'last_validation_cycle_event': 'baseline_ready',
            'last_validation_cycle_packet_path': 'logs/data/calamum/observer_derived/sim/canary/evidence/observerctl_baseline_ready.json',
            'last_validation_cycle_at_utc': observerctl_module._utc_now(),
            'last_baseline_window_id': 'framec-monitor-window',
        }),
        encoding='utf-8',
    )

    rc = main(['baseline', 'monitor-status'])
    assert rc == 0

    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Observer baseline monitor status'
    assert 'Contract' in rendered
    assert any('Graph architecture:' in line and 'joined by observerctl baseline status/check' in line for line in rendered)
    assert 'Runtime' in rendered
    assert any('Monitor state:' in line and 'control/calamum/baseline_monitor_state.json' in line for line in rendered)
    assert 'Guidance' in rendered


def test_baseline_status_human_output_for_explicit_filesystem_snapshot(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('hello baseline\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    assert main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json']) == 0
    _ = capsys.readouterr().out

    rc = main(['baseline', 'status', '--baseline', str(baseline_path)])
    assert rc == 0

    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Observer baseline status'
    assert 'Contract' in rendered
    assert any('Integrity model:' in line and 'explicit filesystem-hash snapshot' in line for line in rendered)
    assert 'Statistics' in rendered
    assert any('Baseline path:' in line and 'fs_baseline.json' in line for line in rendered)
    assert 'Guidance' in rendered


def test_baseline_check_detects_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('v1\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    assert main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json']) == 0

    tracked.write_text('v2\n', encoding='utf-8')
    rc_check = main(['baseline', 'check', '--baseline', str(baseline_path), '--json'])
    assert rc_check == 2


def test_baseline_check_ignores_local_untracked_runtime_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('stable\n', encoding='utf-8')

    runtime_state = tmp_path / 'local_untracked' / 'scheduler' / 'watchdog_schedule_state.json'
    runtime_state.parent.mkdir(parents=True, exist_ok=True)
    runtime_state.write_text('{"tick":1}\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    assert main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json']) == 0

    # Runtime state mutates between baseline/check cycles; baseline should ignore it.
    runtime_state.write_text('{"tick":2}\n', encoding='utf-8')
    rc_check = main(['baseline', 'check', '--baseline', str(baseline_path), '--json'])
    assert rc_check == 0


def test_librarian_rotate_compact_verify_operational(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'watch'
    store.mkdir(parents=True, exist_ok=True)

    active = store / 'active.jsonl'
    active.write_text('{"x":1}\n{"x":2}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    control = log_dir / 'control' / 'calamum'
    control.mkdir(parents=True, exist_ok=True)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    assert main(['librarian', 'rotate', '--mode', 'watch', '--json']) == 0

    manifest_path = store / 'manifest.json'
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert isinstance(manifest.get('archives'), list)

    # Create another segment then compact archives.
    active.write_text('{"x":3}\n', encoding='utf-8')
    assert main(['librarian', 'rotate', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'compact', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'verify', '--mode', 'watch', '--json']) == 0

    manifest_after = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest_after.get('archives') == []
    assert len(manifest_after.get('compacted_files', [])) >= 1

    # Ensure former marker-stub artifacts are not used.
    assert list(store.glob('*.marker')) == []


def test_librarian_stats_reports_archive_manifest_by_mode(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'canary'
    archive_dir = data / 'archive'

    store.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Session-active records in the store pointer.
    active = store / 'active.jsonl'
    active.write_text('{"x":1}\n{"x":2}\n', encoding='utf-8')

    # Archive manifest bundles (compressed artifacts + metadata) by mode.
    bundle_file = archive_dir / 'moltbook_canary_20260222T000000.jsonl.gz'
    bundle_file.write_text('compressed-bytes-placeholder', encoding='utf-8')
    manifest_payload = {
        'moltbook_canary_20260222T000000.jsonl': {
            'artifact_path': bundle_file.name,
            'records': 123,
            'uncompressed_bytes': 4567,
        }
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest_payload), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    stats = observerctl_module._librarian_stats()
    assert stats.get('runtime_cli_surface') == 'observerctl'

    summary = stats.get('archive_manifest_summary', {})
    assert summary.get('manifest_exists') is True
    assert (summary.get('totals') or {}).get('records') == 123

    stores = stats.get('stores', [])
    canary_row = next((row for row in stores if row.get('mode') == 'canary'), None)
    assert canary_row is not None
    assert canary_row.get('session_records') == 2
    assert canary_row.get('archive_bundle_count') == 1
    assert canary_row.get('archive_records') == 123
    assert canary_row.get('records_total_display') == 125


def test_librarian_stats_human_output_without_json_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'canary'
    archive_dir = data / 'archive'

    store.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    (store / 'active.jsonl').write_text('{"x":1}\n', encoding='utf-8')
    bundle_file = archive_dir / 'moltbook_canary_20260222T010000.jsonl.gz'
    bundle_file.write_text('x', encoding='utf-8')
    manifest_payload = {
        'moltbook_canary_20260222T010000.jsonl': {
            'artifact_path': bundle_file.name,
            'records': 7,
            'uncompressed_bytes': 77,
        }
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest_payload), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main(['librarian', 'stats'])
    assert rc == 0

    out = capsys.readouterr().out
    assert 'Librarian stats' in out
    assert 'archive_totals:' in out
    assert 'per_mode:' in out
    assert '- CANARY' in out
    assert 'session_records_display:' in out


def test_librarian_stats_prefers_derived_session_display_counts(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'canary'
    archive_dir = data / 'archive'
    derived_canary = data / 'observer_derived' / 'sim' / 'canary'

    store.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    derived_canary.mkdir(parents=True, exist_ok=True)

    # Empty store pointer but populated derived ingest lane.
    (store / 'active.jsonl').write_text('', encoding='utf-8')
    (derived_canary / 'moltbook_metrics.jsonl').write_text('{"x":1}\n{"x":2}\n{"x":3}\n', encoding='utf-8')

    bundle_file = archive_dir / 'moltbook_canary_20260222T010000.jsonl.gz'
    bundle_file.write_text('x', encoding='utf-8')
    manifest_payload = {
        'moltbook_canary_20260222T010000.jsonl': {
            'artifact_path': bundle_file.name,
            'records': 7,
            'uncompressed_bytes': 77,
        }
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest_payload), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('sim', 'canary')

    stats = observerctl_module._librarian_stats()
    stores = stats.get('stores', [])
    canary_row = next((row for row in stores if row.get('mode') == 'canary'), None)
    assert canary_row is not None
    assert canary_row.get('session_records') == 0
    assert canary_row.get('ingest_session_records') == 3
    assert canary_row.get('session_records_display') == 3
    assert canary_row.get('records_total_display') == 10


def test_librarian_stats_ignores_non_active_lane_derived_sessions(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    archive_dir = data / 'archive'
    derived_sim_live = data / 'observer_derived' / 'sim' / 'live'
    derived_real_canary = data / 'observer_derived' / 'real' / 'canary'

    archive_dir.mkdir(parents=True, exist_ok=True)
    derived_sim_live.mkdir(parents=True, exist_ok=True)
    derived_real_canary.mkdir(parents=True, exist_ok=True)

    (derived_sim_live / 'moltbook_metrics.jsonl').write_text('{"x":1}\n{"x":2}\n{"x":3}\n', encoding='utf-8')
    (derived_real_canary / 'moltbook_metrics.jsonl').write_text('{"x":10}\n{"x":11}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('real', 'canary')

    stats = observerctl_module._librarian_stats()
    stores = stats.get('stores', [])
    live_row = next((row for row in stores if row.get('mode') == 'live'), None)
    canary_row = next((row for row in stores if row.get('mode') == 'canary'), None)

    assert live_row is not None
    assert canary_row is not None

    assert live_row.get('ingest_mode_active') is False
    assert live_row.get('ingest_session_records') == 0
    assert live_row.get('session_records_display') == 0

    assert canary_row.get('ingest_mode_active') is True
    assert canary_row.get('ingest_source_scope') == 'real'
    assert canary_row.get('ingest_session_records') == 2
    assert canary_row.get('session_records_display') == 2


def test_gate_denies_when_security_report_link_missing(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.delenv('CALAMUM_SECURITY_REPORT_REF', raising=False)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:run_security_report_missing' in gate['reason_codes']


def test_gate_denies_when_security_report_link_unresolvable(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.setenv('CALAMUM_SECURITY_REPORT_REF', str(log_dir / 'missing_security_report.md'))
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:run_security_report_missing' in gate['reason_codes']


def test_health_quick_human_output_explains_missing_security_report_link(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.delenv('CALAMUM_SECURITY_REPORT_REF', raising=False)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)
    observerctl_module._save_state('sim', 'canary')

    rc = main(['health', 'quick'])

    assert rc == 2
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'ObserverCTL health quick'
    assert 'Security linkage' in rendered
    assert any('Requirement:' in line and 'CALAMUM_SECURITY_REPORT_REF' in line for line in rendered)
    assert any('Configured ref:' in line and '<missing>' in line for line in rendered)
    assert any('run_context.security_report_ref' in line for line in rendered)


def test_health_explain_human_output_surfaces_current_security_report_ref_status(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_SECURITY_REPORT_REF', str(log_dir / 'missing_security_report.md'))
    observerctl_module._save_state('sim', 'canary')

    rc = main(['health', 'explain', '--code', 'critical_check_failed:run_security_report_missing'])

    assert rc == 0
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'ObserverCTL health explain'
    assert 'Security linkage' in rendered
    assert any('Ref source:' in line and 'env:CALAMUM_SECURITY_REPORT_REF' in line for line in rendered)
    assert any('Resolved path:' in line and 'missing_security_report.md' in line for line in rendered)
    assert any('Exists on disk:' in line and 'no' in line for line in rendered)
    assert 'Guidance' in rendered


def test_live_gate_denies_when_baseline_monitor_runtime_inactive_but_surfaces_saved_evidence(tmp_path: Path, monkeypatch) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    segment_path = archive_dir / 'resource_sim_canary_normal_frame9_gate_seg0001.jsonl'
    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_frame9_gate_seg0001.jsonl'
    segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z","baseline_window_id":"frame9-gate-window"}\n', encoding='utf-8')
    (resource_dir / 'index.jsonl').write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_normal',
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_baseline',
            'baseline_window_id': 'frame9-gate-window',
            'window_id': 'frame9-gate-window',
        }) + '\n',
        encoding='utf-8',
    )

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_frame9_gate.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'baseline_window_id': 'frame9-gate-window',
        'sample_counts': {'resource_normal': 2, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='live')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:baseline_monitor_runtime_inactive' in gate['reason_codes']
    assert gate['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'ok'
    assert gate['stage5_prerequisites']['C25_resource_baseline_window_ready']['status'] == 'ok'
    assert gate['stage5_prerequisites']['baseline_monitor_runtime_ready']['status'] == 'err'
    assert any(str(ref).endswith('watchdog_posture_state.json') for ref in gate['evidence_refs'])
    assert any(str(ref).endswith('resource/index.jsonl') for ref in gate['evidence_refs'])
    assert any(str(ref).endswith('observerctl_baseline-analysis_frame9_gate.json') for ref in gate['evidence_refs'])


def test_live_gate_reason_codes_follow_deterministic_activation_order(tmp_path: Path, monkeypatch) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    _bind_temp_observer_project(monkeypatch, project_root, anchor)
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='live')
    assert gate['decision'] == 'no-go'
    assert gate['reason_codes'] == [
        'critical_check_failed:lockdown_heartbeat_rate_not_escalated',
        'critical_check_failed:lockdown_baseline_rate_not_escalated',
        'critical_check_failed:baseline_monitor_runtime_inactive',
        'critical_check_failed:resource_stream_retention_unavailable',
        'critical_check_failed:resource_baseline_window_incomplete',
    ]


def test_live_lockdown_requires_escalated_cadence(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'test-key')

    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)
    status = collect_runtime_status(source='real')
    gate = evaluate_gate_decision(status, target_mode='live')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:lockdown_heartbeat_rate_not_escalated' in gate['reason_codes']
    assert 'critical_check_failed:lockdown_baseline_rate_not_escalated' in gate['reason_codes']


def test_lockdown_cpu_spike_denies_live_and_honeypot_same_standard(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'test-key')

    # Cadence escalated correctly for lockdown; denial should come from spike standard.
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=80, ram_now=70, cpu_p95=50, ram_p95=55, score=0.6, age_s=3)

    live_status = collect_runtime_status(source='real')
    live_gate = evaluate_gate_decision(live_status, target_mode='live')
    honeypot_gate = evaluate_gate_decision(live_status, target_mode='honeypot')

    assert live_gate['decision'] == 'no-go'
    assert honeypot_gate['decision'] == 'no-go'
    assert 'critical_check_failed:cpu_spike_lockdown' in live_gate['reason_codes']
    assert 'critical_check_failed:cpu_spike_lockdown' in honeypot_gate['reason_codes']


def test_ops_mode_set_denies_stale_gate_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.setenv('CALAMUM_GATE_PACKET_MAX_AGE_SEC', '1')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    assert main(['ops', 'mode', 'gate', '--to', 'canary', '--source', 'sim', '--json']) == 0

    gate_path = control / 'observerctl_last_gate.json'
    gate_doc = json.loads(gate_path.read_text(encoding='utf-8'))
    gate_doc['timestamp_utc'] = '2000-01-01T00:00:00Z'
    gate_path.write_text(json.dumps(gate_doc), encoding='utf-8')

    assert main(['ops', 'mode', 'set', '--to', 'canary', '--source', 'sim', '--json']) == 2


def test_default_evidence_paths_use_canonical_data_cache(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data_dir = log_dir / 'data' / 'calamum'
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = _default_output_path(source='sim', mode='canary', event='unit-test')
    idx = _evidence_index_path(source='sim', mode='canary')

    expected_dir = data_dir / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    assert out.parent == expected_dir
    assert out.name.startswith('observerctl_unit-test_evidence_')
    assert out.suffix == '.json'
    assert idx == expected_dir / 'index.jsonl'


def test_ops_runtime_stop_writes_kill_signal(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control_dir = log_dir / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main(['ops', 'runtime', 'stop', '--json'])
    assert rc == 0

    signal_path = control_dir / 'kill.signal.json'
    assert signal_path.exists()
    payload = json.loads(signal_path.read_text(encoding='utf-8'))
    assert payload.get('signal') == 'kill'
    assert payload.get('requested_by') == 'observerctl'


def test_ops_runtime_stop_cleans_stale_pidfile(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control_dir = log_dir / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    pid_file = tmp_path / 'calamum_agent.pid'
    pid_file.write_text('424242', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_pid_alive', lambda _pid: False)

    packet = observerctl_module._ops_runtime_stop(timeout_sec=0.0)
    assert packet['decision'] == 'go'
    assert packet['stopped_cleanly'] is True
    assert packet['escalated_terminate'] is False
    assert not pid_file.exists()


def test_ops_runtime_stop_escalates_when_process_persists(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control_dir = log_dir / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    pid_file = tmp_path / 'calamum_agent.pid'
    pid_file.write_text('424242', encoding='utf-8')

    calls = {'pid_alive': 0, 'terminate': 0}

    def _fake_pid_alive(_pid):
        calls['pid_alive'] += 1
        # Alive during initial check(s), then false after terminate path has run.
        if calls['terminate'] == 0:
            return True
        return False

    def _fake_terminate(_pid, graceful_timeout_sec=2.0):
        calls['terminate'] += 1
        return True

    monkeypatch.setattr(observerctl_module, '_pid_alive', _fake_pid_alive)
    monkeypatch.setattr(observerctl_module, '_terminate_pid_best_effort', _fake_terminate)

    packet = observerctl_module._ops_runtime_stop(timeout_sec=0.0)
    assert packet['decision'] == 'go'
    assert packet['stopped_cleanly'] is True
    assert packet['escalated_terminate'] is True
    assert calls['terminate'] == 1


def test_ops_runtime_status_reports_active_when_heartbeat_and_pid_alive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    _touch(health / 'calamum_observer.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)
    (tmp_path / 'calamum_agent.pid').write_text(str(os.getpid()), encoding='utf-8')

    packet = observerctl_module._ops_runtime_status()
    assert packet['state'] == 'active'
    assert packet['heartbeat']['status'] == 'ok'
    assert packet['pid']['alive'] is True


def test_librarian_status_reports_active_when_heartbeat_and_pid_alive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)
    (tmp_path / 'calamum_librarian.pid').write_text(str(os.getpid()), encoding='utf-8')

    packet = observerctl_module._librarian_status()
    assert packet['decision'] == 'go'
    assert packet['state'] == 'active'
    assert packet['heartbeat']['status'] == 'ok'
    assert packet['pid']['alive'] is True


def test_librarian_check_go_when_runtime_active_and_store_ok(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    health = log_dir / 'health'
    for d in [data, health]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_runtime_librarian_status', lambda max_age_sec=120.0: {
        'state': 'active',
        'heartbeat': {'status': 'ok'},
        'pid': {'value': 123, 'alive': True},
    })

    rc = main(['librarian', 'check', '--mode', 'watch', '--json'])
    assert rc == 0


def test_librarian_restart_starts_process_and_reports_go(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    (log_dir / 'health').mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    src_dir = tmp_path / 'src'
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / 'calamum_librarian.py').write_text('print("ok")\n', encoding='utf-8')

    class _DummyProc:
        pid = 12345

    monkeypatch.setattr(observerctl_module.subprocess, 'Popen', lambda *args, **kwargs: _DummyProc())

    states = [
        {'state': 'degraded', 'heartbeat': {'status': 'warn'}, 'pid': {'value': 12345, 'alive': True}},
        {'state': 'active', 'heartbeat': {'status': 'ok'}, 'pid': {'value': 12345, 'alive': True}},
    ]

    def _fake_status(max_age_sec=120.0):
        if len(states) > 1:
            return states.pop(0)
        return states[0]

    monkeypatch.setattr(observerctl_module, '_runtime_librarian_status', _fake_status)

    packet = observerctl_module._librarian_restart(timeout_sec=0.0, startup_probe_sec=0.2)
    assert packet['decision'] == 'go'
    assert int(packet['new_pid']) == 12345


def test_pid_alive_uses_psutil_when_os_kill_unreliable(monkeypatch) -> None:
    class _FakeProc:
        def is_running(self):
            return True

        def status(self):
            return 'running'

    monkeypatch.setattr(observerctl_module.psutil, 'Process', lambda _pid: _FakeProc())
    monkeypatch.setattr(observerctl_module.os, 'kill', lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError('unsupported')))

    assert observerctl_module._pid_alive(4242) is True


def test_ops_runtime_start_delegates_launcher_non_interactive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    launcher = tmp_path / 'launch_ghost_console.ps1'
    launcher.write_text('# test launcher\n', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    class _DummyProc:
        pid = 12345

    def _fake_popen(cmd, env, cwd, stdin, stdout, stderr, creationflags):
        (tmp_path / 'calamum_agent.pid').write_text(str(os.getpid()), encoding='utf-8')
        _touch(health / 'calamum_observer.heartbeat')
        return _DummyProc()

    monkeypatch.setattr(observerctl_module.subprocess, 'Popen', _fake_popen)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_start', lambda **kwargs: {
        'timestamp_utc': '2026-01-01T00:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-start',
        'reason_codes': [],
        'state': 'active',
        'pid': {'value': 2468, 'alive': True},
        'startup_verified': True,
    })

    rc = main([
        'ops', 'runtime', 'start',
        '--source', 'sim',
        '--mode', 'canary',
        '--interval-sec', '1.0',
        '--timeout-sec', '2',
        '--json',
    ])
    assert rc == 0


def test_ops_runtime_start_gui_omits_browser_skip_env(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_SKIP_BROWSER', '1')

    launcher = tmp_path / 'launch_ghost_console.ps1'
    launcher.write_text('# test launcher\n', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    captured = {'env': {}}

    class _DummyProc:
        pid = 12345

    def _fake_popen(cmd, env, cwd, stdin, stdout, stderr, creationflags):
        captured['env'] = dict(env)
        (tmp_path / 'calamum_agent.pid').write_text(str(os.getpid()), encoding='utf-8')
        _touch(health / 'calamum_observer.heartbeat')
        return _DummyProc()

    monkeypatch.setattr(observerctl_module.subprocess, 'Popen', _fake_popen)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_start', lambda **kwargs: {
        'timestamp_utc': '2026-01-01T00:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-start',
        'reason_codes': [],
        'state': 'active',
        'pid': {'value': 2468, 'alive': True},
        'startup_verified': True,
    })

    rc = main([
        'ops', 'runtime', 'start',
        '--source', 'sim',
        '--mode', 'canary',
        '--interval-sec', '1.0',
        '--timeout-sec', '0',
        '--gui',
        '--json',
    ])
    assert rc == 0
    assert captured['env'].get('CALAMUM_GUI_AUTOSTART_OBSERVER') == '1'
    assert 'CALAMUM_SKIP_BROWSER' not in captured['env']


def test_ops_runtime_start_gui_no_verify_skips_post_launch_checks(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    launcher = tmp_path / 'launch_ghost_console.ps1'
    launcher.write_text('# test launcher\n', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    captured = {'env': {}}

    class _DummyProc:
        pid = 12345

    def _fake_popen(cmd, env, cwd, stdin, stdout, stderr, creationflags):
        captured['env'] = dict(env)
        return _DummyProc()

    def _boom(**kwargs):
        raise AssertionError('baseline monitor should not start when --gui --no-verify is used')

    monkeypatch.setattr(observerctl_module.subprocess, 'Popen', _fake_popen)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_start', _boom)

    rc = main([
        'ops', 'runtime', 'start',
        '--source', 'sim',
        '--mode', 'canary',
        '--interval-sec', '1.0',
        '--timeout-sec', '2',
        '--gui',
        '--no-verify',
        '--json',
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['decision'] == 'go'
    assert payload['gui_requested'] is True
    assert payload['no_verify_requested'] is True
    assert payload['verification_skipped'] is True
    assert payload['baseline_monitor_packet'] == {}
    assert captured['env'].get('CALAMUM_GUI_AUTOSTART_OBSERVER') == '1'
    assert 'CALAMUM_SKIP_BROWSER' not in captured['env']


def test_ops_runtime_start_no_verify_requires_gui(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    rc = main([
        'ops', 'runtime', 'start',
        '--source', 'sim',
        '--mode', 'canary',
        '--no-verify',
        '--json',
    ])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload['decision'] == 'no-go'
    assert 'policy_denied:runtime_no_verify_requires_gui' in payload['reason_codes']


def test_librarian_vault_status_human_labels_integrity_scope_and_managed_surfaces(monkeypatch, tmp_path: Path, capsys) -> None:
    project_root, anchor = _make_temp_observer_project(tmp_path)
    dataset_dir = project_root / 'datasets' / 'vault_alpha'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    labels_csv = dataset_dir / 'labels.csv'
    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    manifest_path.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
        'total_records': 1,
        'has_labels': True,
    }), encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_project_root', lambda: project_root)
    monkeypatch.setattr(observerctl_module, '_project_anchor', lambda: anchor)

    rc = main([
        'librarian',
        'dataset',
        'register',
        str(manifest_path),
        '--access-class', 'protected-source',
        '--display-name', 'Vault Alpha',
        '--run-id', 'vault-alpha',
        '--json',
    ])
    assert rc == 0
    _ = json.loads(capsys.readouterr().out)

    rc = main(['librarian', 'vault', 'status'])
    assert rc == 0
    rendered = capsys.readouterr().out.splitlines()
    assert rendered[0] == 'Librarian vault status'
    assert any('Integrity-tracked files:' in line for line in rendered)
    assert any('Vault-managed files:' in line for line in rendered)
    assert any('Projection-managed files:' in line for line in rendered)
    assert 'Managed surfaces' in rendered
    assert any('Authority files:' in line for line in rendered)
    assert any('Integrity files:' in line for line in rendered)


def test_ops_runtime_start_fails_closed_when_monitor_start_fails(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    launcher = tmp_path / 'launch_ghost_console.ps1'
    launcher.write_text('# test launcher\n', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    class _DummyProc:
        pid = 12345

    def _fake_popen(cmd, env, cwd, stdin, stdout, stderr, creationflags):
        (tmp_path / 'calamum_agent.pid').write_text(str(os.getpid()), encoding='utf-8')
        _touch(health / 'calamum_observer.heartbeat')
        return _DummyProc()

    monkeypatch.setattr(observerctl_module.subprocess, 'Popen', _fake_popen)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_start', lambda **kwargs: {
        'timestamp_utc': '2026-01-01T00:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': 'baseline-monitor-start',
        'reason_codes': ['critical_check_failed:baseline_monitor_startup_unverified'],
        'state': 'stopped',
        'pid': {'value': None, 'alive': False},
        'startup_verified': False,
    })

    rc = main([
        'ops', 'runtime', 'start',
        '--source', 'sim',
        '--mode', 'canary',
        '--interval-sec', '1.0',
        '--timeout-sec', '2',
        '--json',
    ])
    assert rc == 2


def test_ops_mode_switch_fails_when_postflight_monitor_inactive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    observerctl_module._save_state('sim', 'watch')

    monkeypatch.setattr(
        observerctl_module,
        '_runtime_observer_status',
        lambda max_age_sec=60.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 1111, 'alive': True},
            'pending_stop_signal': False,
        },
    )
    monkeypatch.setattr(observerctl_module, '_ops_runtime_status', lambda: {
        'state': 'active',
        'heartbeat': {'status': 'ok'},
        'pid': {'value': 1111, 'alive': True},
        'pending_stop_signal': False,
    })
    monkeypatch.setattr(observerctl_module, '_ops_runtime_stop', lambda timeout_sec=8.0: {
        'timestamp_utc': '2026-01-01T00:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'runtime-stop',
        'reason_codes': [],
    })
    monkeypatch.setattr(observerctl_module, '_ops_runtime_start', lambda source, mode, interval_sec, timeout_sec: {
        'timestamp_utc': '2026-01-01T00:00:01Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'runtime-start',
        'reason_codes': [],
        'startup_verified': True,
        'state': 'active',
        'pid': {'value': 5678, 'alive': True},
    })
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_baseline_monitor_status',
        lambda max_age_sec=90.0: {
            'state': 'stopped',
            'heartbeat': {'status': 'err'},
            'pid': {'value': None, 'alive': False},
            'monitor_state': {},
        },
    )

    rc = main(['ops', 'mode', 'switch', '--to', 'canary', '--json'])
    assert rc == 2
