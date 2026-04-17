"""
Simulation and sandbox runner for Calamum observer workflows.

This module is the canonical entrypoint for simulation-oriented validation lanes.
It keeps the original feedback-loop simulation while also collecting observerctl
sandbox probes behind a single definition dispatcher.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import threading
import time
from concurrent import futures
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
PROJECT_ROOT = CURRENT_DIR.parents[1]
REPO_ROOT = CURRENT_DIR.parents[3]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from calamum_librarian import Librarian
from calamum_observer_agent import append_record
from obfuscator_lib import Obfuscator, verify_detached_payload
import observerctl as observerctl_module
from observerctl_terminal import strip_ansi


FRAME4_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame4_metadata_contract_probe'
FRAME4_REGRESSION_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame4_metadata_contract_regression_probe'
FRAME4_DS_WIZARD_HYDRATION_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame4_ds_wizard_hydration_probe'
FRAMEB_DS_WIZARD_STALE_STATE_CONTINUITY_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frameb_ds_wizard_stale_state_continuity_probe'
JOB0022_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'job0022_baseline_monitor_runtime_probe'
FRAME5_LINEAGE_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame5_validation_cycle_lineage_probe'
FRAME6_DS_WIZARD_DURABILITY_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame6_ds_wizard_durability_probe'
FRAMEB_DS_WIZARD_LABELED_EVAL_CONTRACT_COHERENCE_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frameb_ds_wizard_labeled_eval_contract_coherence_probe'
FRAMEB_DS_WIZARD_BLOCKED_EXECUTE_TRUTHFULNESS_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frameb_ds_wizard_blocked_execute_truthfulness_probe'
FRAMEB_DS_WIZARD_EXECUTE_FAILURE_TRUTHFULNESS_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frameb_ds_wizard_execute_failure_truthfulness_probe'
FRAMED_DS_ALIAS_COHERENCE_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'framed_ds_alias_coherence_probe'
FRAME6_RESTART_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame6_restart_continuity_probe'
FRAME6_RECOVERY_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame6_state_recovery_probe'
LIBRARIAN_ACCESS_EXCHANGE_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'librarian_access_exchange_probe'
LIBRARIAN_VAULT_CONTROLS_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'librarian_vault_controls_probe'


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _rel_to_repo(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace('\\', '/')
    except Exception:
        return str(path).replace('\\', '/')


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, sort_keys=True) + '\n')


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = str(line).strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _read_jsonl_last(path: Path) -> Dict[str, Any]:
    rows = _read_jsonl(path)
    return rows[-1] if rows else {}


def _read_jsonl_rows_for_event(path: Path, event: str) -> List[Dict[str, Any]]:
    expected = str(event or '').strip().lower()
    return [
        row for row in _read_jsonl(path)
        if str(row.get('event', '')).strip().lower() == expected
    ]


def _read_jsonl_latest_matching(path: Path, key: str, expected: str) -> Dict[str, Any]:
    for row in reversed(_read_jsonl(path)):
        if str(row.get(key, '')).strip().lower() == str(expected).strip().lower():
            return row
    return {}


def _field_presence(row: Dict[str, Any], required_fields: List[str]) -> Dict[str, bool]:
    return {field: field in row and str(row.get(field, '')).strip() != '' for field in required_fields}


def _read_first_segment_row(packet: Dict[str, Any]) -> Dict[str, Any]:
    segments = packet.get('segments', []) if isinstance(packet.get('segments', []), list) else []
    if not segments:
        return {}
    first = segments[0] if isinstance(segments[0], dict) else {}
    segment_path = Path(str(first.get('path', '')).replace('/', os.sep))
    rows = _read_jsonl(segment_path)
    return rows[0] if rows else {}


def _run_observerctl_cli(args: List[str]) -> Dict[str, Any]:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            rc = observerctl_module.main(args)
        except SystemExit as exc:
            code = exc.code
            rc = int(code) if isinstance(code, int) else 1
    stdout_text = stdout_buffer.getvalue()
    stderr_text = stderr_buffer.getvalue()
    stdout_json: Dict[str, Any] = {}
    if stdout_text.strip():
        try:
            parsed = json.loads(stdout_text)
            if isinstance(parsed, dict):
                stdout_json = parsed
        except Exception:
            stdout_json = {
                'stdout_parse_error': True,
                'stdout_text': stdout_text,
            }
    return {
        'args': args,
        'returncode': int(rc),
        'stdout_text': stdout_text,
        'stderr_text': stderr_text,
        'stdout_json': stdout_json,
    }


def _command_stdout_json(command_result: Dict[str, Any]) -> Dict[str, Any]:
    stdout_json = command_result.get('stdout_json', {}) if isinstance(command_result.get('stdout_json', {}), dict) else {}
    return dict(stdout_json)


def _wizard_packet_artifact(command_result: Dict[str, Any], key: str) -> str:
    packet = _command_stdout_json(command_result)
    artifacts = packet.get('artifacts', {}) if isinstance(packet.get('artifacts', {}), dict) else {}
    return str(artifacts.get(key, '') or '').strip()


def _wizard_packet_validation_issues(command_result: Dict[str, Any]) -> List[str]:
    packet = _command_stdout_json(command_result)
    raw_issues = packet.get('validation_issues', []) if isinstance(packet.get('validation_issues', []), list) else []
    return [str(issue) for issue in raw_issues if str(issue).strip()]


def _wizard_packet_view(command_result: Dict[str, Any]) -> List[str]:
    packet = _command_stdout_json(command_result)
    raw_view = packet.get('wizard_view', []) if isinstance(packet.get('wizard_view', []), list) else []
    return [str(line) for line in raw_view]


def _wizard_packet_view_contains(command_result: Dict[str, Any], *tokens: str) -> bool:
    haystack = '\n'.join(_wizard_packet_view(command_result))
    expected_tokens = [str(token) for token in tokens if str(token or '').strip()]
    return bool(expected_tokens) and all(token in haystack for token in expected_tokens)


def _seed_probe_environment(run_dir: Path, signing_key: str, security_report_title: str) -> Tuple[Path, Path, Dict[str, Optional[str]], Any]:
    sandbox_root = run_dir / 'sandbox_root'
    sandbox_log_dir = run_dir / 'sandbox_logs'
    sandbox_root.mkdir(parents=True, exist_ok=True)
    sandbox_log_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    for key, value in {
        'CALAMUM_LOG_DIR': str(sandbox_log_dir),
        'CALAMUM_DATA_SIGNING_KEY': signing_key,
        'CALAMUM_SECURITY_REPORT_REF': str(run_dir / 'security_report.md'),
    }.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    original_env['MOLTBOOK_API_KEY'] = os.environ.get('MOLTBOOK_API_KEY')
    os.environ.pop('MOLTBOOK_API_KEY', None)

    (run_dir / 'security_report.md').write_text(security_report_title, encoding='utf-8')

    original_project_root = observerctl_module._project_root
    observerctl_module._project_root = lambda: sandbox_root
    return sandbox_root, sandbox_log_dir, original_env, original_project_root


def _restore_probe_environment(original_env: Dict[str, Optional[str]], original_project_root: Any) -> None:
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    observerctl_module._project_root = original_project_root


def _override_env_vars(original_env: Dict[str, Optional[str]], updates: Dict[str, Optional[str]]) -> None:
    for key, value in updates.items():
        if key not in original_env:
            original_env[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _seed_probe_project_root(project_root: Path) -> Path:
    src_dir = project_root / 'src'
    src_dir.mkdir(parents=True, exist_ok=True)
    anchor = src_dir / 'observerctl.py'
    if not anchor.exists():
        anchor.write_text('# sandbox observerctl anchor\n', encoding='utf-8')
    manifest = project_root / 'PROJECT_MANIFEST.json'
    if not manifest.exists():
        manifest.write_text('{}\n', encoding='utf-8')
    return anchor


def _resolve_probe_artifact_path(project_root: Path, reported_path: str) -> Path:
    raw = str(reported_path or '').strip()
    if not raw:
        return Path()
    path = Path(raw.replace('/', os.sep))
    if path.is_absolute():
        return path
    return project_root / path


def _touch(path: Path, content: str = '{"status":"ok"}\n') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _write_pid(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding='utf-8')


def _bind_probe_observer_project(project_root: Path) -> Tuple[Path, Any, str]:
    anchor = _seed_probe_project_root(project_root)
    original_project_anchor = observerctl_module._project_anchor
    original_file = str(getattr(observerctl_module, '__file__', '') or '')
    observerctl_module._project_anchor = lambda: anchor
    observerctl_module.__file__ = str(anchor)
    return anchor, original_project_anchor, original_file


def _restore_probe_observer_project(original_project_anchor: Any, original_file: str) -> None:
    observerctl_module._project_anchor = original_project_anchor
    observerctl_module.__file__ = str(original_file)


def _write_signed_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(Obfuscator.sign_record(record)) + '\n')


def _make_ds_records() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for i in range(8):
        records.append({
            'timestamp': '2026-02-10T00:00:{0:02d}Z'.format(i),
            'type': 'post',
            'author_hash': 'norm{0:012d}'.format(i),
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
            'timestamp': '2026-02-10T00:01:{0:02d}Z'.format(i),
            'type': 'post',
            'author_hash': 'bad{0:013d}'.format(i),
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


def _seed_runtime_liveness(sandbox_root: Path, log_dir: Path) -> Dict[str, str]:
    health_dir = log_dir / 'health'
    _touch(health_dir / 'calamum_ops_watchdog.heartbeat')
    _touch(health_dir / 'calamum_observer.heartbeat')
    _touch(health_dir / 'calamum_librarian.heartbeat')
    _touch(health_dir / 'calamum_baseline_monitor.heartbeat')

    agent_pid = sandbox_root / 'calamum_agent.pid'
    librarian_pid = sandbox_root / 'calamum_librarian.pid'
    baseline_monitor_pid = sandbox_root / 'calamum_baseline_monitor.pid'
    _write_pid(agent_pid)
    _write_pid(librarian_pid)
    _write_pid(baseline_monitor_pid)

    return {
        'agent_pid': _rel_to_repo(agent_pid),
        'librarian_pid': _rel_to_repo(librarian_pid),
        'baseline_monitor_pid': _rel_to_repo(baseline_monitor_pid),
    }


def run_feedback_loop_simulation() -> int:
    print('[Sim] Starting Calamum Architecture Simulation...')

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        data_dir = root / 'data'
        control_dir = root / 'control'
        health_dir = root / 'health'

        os.environ['CALAMUM_DATA_DIR'] = str(data_dir)
        os.environ['CALAMUM_CONTROL_DIR'] = str(control_dir)
        os.environ['CALAMUM_HEALTH_DIR'] = str(health_dir)

        data_dir.mkdir()
        control_dir.mkdir()
        health_dir.mkdir()

        initial_policy = {
            'max_bytes': 2048,
            'reason': 'Simulation Seed',
        }
        (control_dir / 'rotation_policy.json').write_text(json.dumps(initial_policy), encoding='utf-8')
        print('[Sim] Seeded Policy: Max Bytes = 2048')

        def agent_thread_func(stop_event: threading.Event) -> None:
            print('[Agent] Started.')
            jsonl_path = data_dir / 'moltbook_stream.jsonl'
            node_id = 'sim-node-01'

            iterations = 0
            while not stop_event.is_set():
                append_record(jsonl_path, node_id, 'active', control_dir, data_dir)
                iterations += 1
                if iterations % 50 == 0:
                    time.sleep(0.1)
            print('[Agent] Stopped.')

        def librarian_thread_func(stop_event: threading.Event) -> None:
            print('[Librarian] Started.')
            lib = Librarian(interval_sec=0.5)

            while not stop_event.is_set():
                try:
                    lib.run_once()
                    lib._touch_heartbeat('ok')
                except Exception as exc:
                    print(f'[Librarian] Error: {exc}')
                time.sleep(0.5)
            print('[Librarian] Stopped.')

        stop_event = threading.Event()

        with futures.ThreadPoolExecutor(max_workers=3) as executor:
            _agent_future = executor.submit(agent_thread_func, stop_event)
            _lib_future = executor.submit(librarian_thread_func, stop_event)

            print('[Sim] Monitoring for 5 seconds...')
            for i in range(10):
                time.sleep(0.5)
                try:
                    policy = json.loads((control_dir / 'rotation_policy.json').read_text(encoding='utf-8'))
                    limit = policy.get('max_bytes')
                    reason = policy.get('reason', '')

                    archives = list((data_dir / 'archive').glob('*.jsonl.gz'))
                    pending = list((data_dir / 'archive').glob('*.jsonl'))

                    print(f'[T+{i * 0.5}s] Policy Limit: {limit} ({reason[:20]}...) | archives: {len(archives)} | pending: {len(pending)}')

                    if limit > 2048 and 'Adaptive' in reason:
                        print('SUCCESS: Feedback loop active! Policy increased.')
                except Exception:
                    pass

            stop_event.set()
            print('[Sim] Stopping threads...')

    print('[Sim] Complete.')
    return 0


def run_simulation() -> int:
    return run_feedback_loop_simulation()


def _render_metadata_contract_markdown(report: Dict[str, Any]) -> str:
    lines = [
        '# Frame 4 Metadata Contract Probe',
        '',
        '- Run id: `{0}`'.format(report.get('run_id', '')),
        '- Probe dir: `{0}`'.format(report.get('probe_dir', '')),
        '- Phase: `{0}`'.format(report.get('phase', '')),
        '',
        '## Command results',
        '',
    ]
    for name, result in report.get('command_runs', {}).items():
        lines.append('### {0}'.format(name))
        lines.append('- returncode: `{0}`'.format(result.get('returncode', '')))
        lines.append('- args: `{0}`'.format(' '.join(result.get('args', []))))
        stderr_text = str(result.get('stderr_text', '') or '').strip()
        lines.append('- stderr: `{0}`'.format(stderr_text if stderr_text else '(empty)'))
        lines.append('')

    lines.extend([
        '## Metadata findings',
        '',
    ])
    for stream_name, details in report.get('metadata_findings', {}).items():
        lines.append('### {0}'.format(stream_name))
        lines.append('- sample row path: `{0}`'.format(details.get('sample_row_path', '')))
        lines.append('- index path: `{0}`'.format(details.get('index_path', '')))
        lines.append('- sample field presence: `{0}`'.format(json.dumps(details.get('sample_field_presence', {}), sort_keys=True)))
        lines.append('- index field presence: `{0}`'.format(json.dumps(details.get('index_field_presence', {}), sort_keys=True)))
        lines.append('')

    lines.extend([
        '## Summary',
        '',
        '- `all_sample_fields_present`: `{0}`'.format(report.get('all_sample_fields_present')),
        '- `all_index_fields_present`: `{0}`'.format(report.get('all_index_fields_present')),
        '- `baseline_window_id_required_only_for_baseline`: `{0}`'.format(report.get('baseline_window_id_required_only_for_baseline')),
        '',
    ])
    return '\n'.join(lines) + '\n'


def run_ds_wizard_hydration_probe() -> int:
    run_id = 'frame4-ds-wizard-hydration-{0}'.format(_utc_stamp())
    run_dir = FRAME4_DS_WIZARD_HYDRATION_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAME4_DS_WIZARD_HYDRATION_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        _sandbox_root, sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frame4-ds-wizard-hydration-signing-key',
            security_report_title='# Frame 4 DS wizard hydration probe security report\n',
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(_sandbox_root)

        artifacts_dir = run_dir / 'artifacts'
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        dataset_dir = _sandbox_root / 'datasets' / 'approved_hydration'
        dataset_dir.mkdir(parents=True, exist_ok=True)
        dataset_manifest = dataset_dir / 'dataset_manifest.json'
        features_csv = dataset_dir / 'features.csv'
        labels_csv = dataset_dir / 'labels.csv'
        train_manifest = artifacts_dir / 'train_manifest.json'
        model_path = artifacts_dir / 'model.pkl'
        baseline_packet = sandbox_log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'baseline_analysis_probe.json'
        baseline_index = baseline_packet.parent / 'index.jsonl'

        features_csv.write_text('record_id,feature\n', encoding='utf-8')
        labels_csv.write_text('record_id,label\n', encoding='utf-8')
        model_path.write_bytes(b'model')
        dataset_manifest.write_text(json.dumps({
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
        }, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        train_manifest.write_text(json.dumps({
            'dataset_manifest_path': str(dataset_manifest),
            'model_path': str(model_path),
            'model_type': 'unsupervised',
        }, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        _write_json(baseline_packet, {
            'timestamp_utc': observerctl_module._utc_now(),
            'decision': 'go',
            'baseline_window_id': 'frame4-ds-hydration-window',
            'provenance': {'artifact_path': str(baseline_packet).replace('\\', '/')},
        })
        _append_jsonl(baseline_index, {
            'timestamp_utc': observerctl_module._utc_now(),
            'event': 'baseline_analysis',
            'packet_path': str(baseline_packet).replace('\\', '/'),
        })
        observerctl_module._save_state('sim', 'canary')

        command_runs = {
            'register_hydration_dataset': _run_observerctl_cli([
                'librarian',
                'dataset',
                'register',
                str(dataset_manifest),
                '--access-class',
                'local',
                '--display-name',
                'Frame 4 Wizard Hydration',
                '--run-id',
                'frame4-ds-hydration',
                '--json',
            ]),
            'wizard_hydrate_saved_artifacts': _run_observerctl_cli([
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
            ]),
            'wizard_hydrate_latest_context': _run_observerctl_cli([
                'ds',
                'wizard',
                '--workflow',
                'evaluate',
                '--hydrate-latest-context',
                '--section',
                'check',
                '--json',
            ]),
        }

        hydrated_packet = _command_stdout_json(command_runs['wizard_hydrate_saved_artifacts'])
        latest_packet = _command_stdout_json(command_runs['wizard_hydrate_latest_context'])
        latest_validation_issues = _wizard_packet_validation_issues(command_runs['wizard_hydrate_latest_context'])
        register_packet = _command_stdout_json(command_runs['register_hydration_dataset'])

        result_matrix = {
            'approved_dataset_registered': int(command_runs['register_hydration_dataset'].get('returncode', 1)) == 0 and str(register_packet.get('decision', '')).strip().lower() == 'go',
            'hydrate_cli_returncode_zero': int(command_runs['wizard_hydrate_saved_artifacts'].get('returncode', 1)) == 0,
            'hydrate_packet_go': str(hydrated_packet.get('decision', '')).strip().lower() == 'go' and str(hydrated_packet.get('action', '')).strip() == 'ds-wizard',
            'hydrate_execution_ready': str(hydrated_packet.get('execution_state', '')).strip().lower() == 'ready',
            'hydrate_report_section_opened': str(hydrated_packet.get('current_section', '')).strip().lower() == 'report',
            'hydrate_validation_clear': not _wizard_packet_validation_issues(command_runs['wizard_hydrate_saved_artifacts']),
            'dataset_manifest_imported': _wizard_packet_artifact(command_runs['wizard_hydrate_saved_artifacts'], 'dataset_manifest') == str(dataset_manifest),
            'train_manifest_imported': _wizard_packet_artifact(command_runs['wizard_hydrate_saved_artifacts'], 'train_manifest') == str(train_manifest),
            'model_path_imported': _wizard_packet_artifact(command_runs['wizard_hydrate_saved_artifacts'], 'model_path') == str(model_path),
            'baseline_packet_imported': _wizard_packet_artifact(command_runs['wizard_hydrate_saved_artifacts'], 'baseline_analysis_packet') == str(baseline_packet),
            'baseline_context_marked_hydrated': str((hydrated_packet.get('hydrated_from', {}) if isinstance(hydrated_packet.get('hydrated_from', {}), dict) else {}).get('baseline_window_id', '')).strip() == 'baseline_analysis',
            'report_preview_lists_dataset_and_model_artifacts': _wizard_packet_view_contains(
                command_runs['wizard_hydrate_saved_artifacts'],
                dataset_manifest.name,
                train_manifest.name,
                model_path.name,
                'run.json',
                'run.md',
            ),
            'latest_context_cli_returncode_zero': int(command_runs['wizard_hydrate_latest_context'].get('returncode', 1)) == 0,
            'latest_context_packet_go': str(latest_packet.get('decision', '')).strip().lower() == 'go' and str(latest_packet.get('action', '')).strip() == 'ds-wizard',
            'latest_context_source_marked': str((latest_packet.get('hydrated_from', {}) if isinstance(latest_packet.get('hydrated_from', {}), dict) else {}).get('source', '')).strip() == 'latest_context',
            'latest_context_mode_marked': str((latest_packet.get('hydrated_from', {}) if isinstance(latest_packet.get('hydrated_from', {}), dict) else {}).get('mode', '')).strip() == 'latest_context',
            'latest_context_baseline_imported': _wizard_packet_artifact(command_runs['wizard_hydrate_latest_context'], 'baseline_analysis_packet') == str(baseline_packet),
            'latest_context_check_section_opened': str(latest_packet.get('current_section', '')).strip().lower() == 'check',
            'latest_context_execution_truthful': str(latest_packet.get('execution_state', '')).strip().lower() == 'blocked' and 'features_csv is required' in latest_validation_issues,
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAME4_DS_WIZARD_HYDRATION_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map({
                'dataset_manifest': dataset_manifest,
                'features_csv': features_csv,
                'labels_csv': labels_csv,
                'train_manifest': train_manifest,
                'model_path': model_path,
                'baseline_packet': baseline_packet,
                'baseline_index': baseline_index,
            }),
            'artifact_snapshots': {
                'registration_packet': register_packet,
                'hydrated_packet': hydrated_packet,
                'latest_context_packet': latest_packet,
            },
            'result_matrix': result_matrix,
            'findings': {
                'hydrated_sources': hydrated_packet.get('hydrated_from', {}),
                'hydrated_view': _wizard_packet_view(command_runs['wizard_hydrate_saved_artifacts']),
                'latest_sources': latest_packet.get('hydrated_from', {}),
                'latest_validation_issues': latest_validation_issues,
            },
        }

        report_json = run_dir / 'frame4_ds_wizard_hydration_probe.json'
        report_md = run_dir / 'frame4_ds_wizard_hydration_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame 4 DS Wizard Hydration Probe', report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': report['next_bite_result'],
            'latest_context_mode': str((latest_packet.get('hydrated_from', {}) if isinstance(latest_packet.get('hydrated_from', {}), dict) else {}).get('mode', '')),
        })

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_anchor is not None:
            _restore_probe_observer_project(original_project_anchor, original_file)
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_ds_wizard_durability_probe() -> int:
    run_id = 'frame6-ds-wizard-durability-{0}'.format(_utc_stamp())
    run_dir = FRAME6_DS_WIZARD_DURABILITY_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAME6_DS_WIZARD_DURABILITY_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        _sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frame6-ds-wizard-durability-signing-key',
            security_report_title='# Frame 6 DS wizard durability probe security report\n',
        )

        artifacts_dir = run_dir / 'artifacts'
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        features_csv = artifacts_dir / 'features.csv'
        labels_csv = artifacts_dir / 'labels.csv'
        dataset_manifest = artifacts_dir / 'dataset_manifest.json'
        model_path = artifacts_dir / 'model.pkl'
        run_ledger = artifacts_dir / 'run.json'
        draft_path = artifacts_dir / 'wizard_draft.json'

        features_csv.write_text('record_id,feature\n', encoding='utf-8')
        labels_csv.write_text('record_id,label\n', encoding='utf-8')
        model_path.write_bytes(b'model')
        _write_json(dataset_manifest, {
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
        })
        _write_json(run_ledger, {
            'identity': {
                'run_id': 'frame6-durability-ledger',
                'created_at_utc': observerctl_module._utc_now(),
                'operator': 'ORACL-Prime',
            },
            'context': {
                'constraints': {'max_fpr': 0.02},
            },
            'data': {
                'features_csv': str(features_csv),
                'labels_csv': str(labels_csv),
                'dataset_manifest': str(dataset_manifest),
            },
            'model': {
                'family': 'trained_apexlab',
                'name': 'model.pkl',
                'source': str(model_path),
            },
        })

        command_runs = {
            'wizard_hydrate_run_and_save_draft': _run_observerctl_cli([
                'ds',
                'wizard',
                '--workflow',
                'evaluate',
                '--hydrate-run',
                str(run_ledger),
                '--section',
                'report',
                '--save-draft',
                str(draft_path),
                '--json',
            ]),
            'wizard_load_saved_draft': _run_observerctl_cli([
                'ds',
                'wizard',
                '--load-draft',
                str(draft_path),
                '--json',
            ]),
        }

        save_packet = _command_stdout_json(command_runs['wizard_hydrate_run_and_save_draft'])
        load_packet = _command_stdout_json(command_runs['wizard_load_saved_draft'])
        draft_payload = _read_json(draft_path)

        result_matrix = {
            'hydrate_run_cli_returncode_zero': int(command_runs['wizard_hydrate_run_and_save_draft'].get('returncode', 1)) == 0,
            'load_draft_cli_returncode_zero': int(command_runs['wizard_load_saved_draft'].get('returncode', 1)) == 0,
            'save_packet_go': str(save_packet.get('decision', '')).strip().lower() == 'go' and str(save_packet.get('action', '')).strip() == 'ds-wizard',
            'load_packet_go': str(load_packet.get('decision', '')).strip().lower() == 'go' and str(load_packet.get('action', '')).strip() == 'ds-wizard',
            'save_execution_ready': str(save_packet.get('execution_state', '')).strip().lower() == 'ready',
            'load_execution_ready': str(load_packet.get('execution_state', '')).strip().lower() == 'ready',
            'run_ledger_path_tracked': _wizard_packet_artifact(command_runs['wizard_hydrate_run_and_save_draft'], 'run_ledger_path') == str(run_ledger) and _wizard_packet_artifact(command_runs['wizard_load_saved_draft'], 'run_ledger_path') == str(run_ledger),
            'draft_path_tracked': _wizard_packet_artifact(command_runs['wizard_hydrate_run_and_save_draft'], 'draft_path') == str(draft_path) and _wizard_packet_artifact(command_runs['wizard_load_saved_draft'], 'draft_path') == str(draft_path),
            'save_report_section_opened': str(save_packet.get('current_section', '')).strip().lower() == 'report',
            'load_report_section_persisted': str(load_packet.get('current_section', '')).strip().lower() == 'report',
            'draft_saved': draft_path.exists(),
            'draft_payload_tracks_run_context': str(draft_payload.get('run_ledger_path', '') or '').strip() == str(run_ledger) and str(draft_payload.get('active_section', '') or '').strip().lower() == 'report' and str(draft_payload.get('workflow', '') or '').strip() == 'evaluate',
            'draft_round_trip_command_preview': str(save_packet.get('command_preview', '') or '').strip() == str(load_packet.get('command_preview', '') or '').strip(),
            'draft_round_trip_hydration': dict(save_packet.get('hydrated_from', {}) if isinstance(save_packet.get('hydrated_from', {}), dict) else {}) == dict(load_packet.get('hydrated_from', {}) if isinstance(load_packet.get('hydrated_from', {}), dict) else {}),
            'validation_clear_after_load': not _wizard_packet_validation_issues(command_runs['wizard_hydrate_run_and_save_draft']) and not _wizard_packet_validation_issues(command_runs['wizard_load_saved_draft']),
            'report_preview_lists_run_dataset_and_model_artifacts': _wizard_packet_view_contains(
                command_runs['wizard_load_saved_draft'],
                run_ledger.name,
                dataset_manifest.name,
                model_path.name,
            ),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAME6_DS_WIZARD_DURABILITY_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map({
                'run_ledger': run_ledger,
                'dataset_manifest': dataset_manifest,
                'features_csv': features_csv,
                'labels_csv': labels_csv,
                'draft_path': draft_path,
                'model_path': model_path,
            }),
            'artifact_snapshots': {
                'save_packet': save_packet,
                'load_packet': load_packet,
                'draft_payload': draft_payload,
            },
            'result_matrix': result_matrix,
            'findings': {
                'save_hydrated_sources': save_packet.get('hydrated_from', {}),
                'load_hydrated_sources': load_packet.get('hydrated_from', {}),
                'load_view': _wizard_packet_view(command_runs['wizard_load_saved_draft']),
            },
        }

        report_json = run_dir / 'frame6_ds_wizard_durability_probe.json'
        report_md = run_dir / 'frame6_ds_wizard_durability_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame 6 DS Wizard Durability Probe', report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': report['next_bite_result'],
            'draft_path': str(draft_path).replace('\\', '/'),
        })

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_ds_alias_coherence_probe() -> int:
    from analysis.dataset_builder import build_dataset
    from analysis.report_pack import prepare_report_bundle

    run_id = 'framed-ds-alias-coherence-{0}'.format(_utc_stamp())
    run_dir = FRAMED_DS_ALIAS_COHERENCE_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMED_DS_ALIAS_COHERENCE_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='framed-ds-alias-coherence-signing-key',
            security_report_title='# Frame D DS alias coherence probe security report\n',
        )
        anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)

        artifacts_dir = run_dir / 'artifacts'
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        input_path = artifacts_dir / 'authority_input.jsonl'
        authority_dataset_dir = sandbox_root / 'datasets' / 'authority_alias_source'
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

        command_runs: Dict[str, Dict[str, Any]] = {
            'register_authority_dataset': _run_observerctl_cli([
                'librarian',
                'dataset',
                'register',
                str(authority_manifest),
                '--access-class',
                'local',
                '--display-name',
                'Frame D Alias Coherence',
                '--run-id',
                'frame-d-alias-coherence',
                '--json',
            ]),
            'wizard_build_preview': _run_observerctl_cli([
                'ds',
                'wizard',
                '--workflow',
                'build',
                '--hydrate-dataset',
                '1',
                '--section',
                'report',
                '--json',
            ]),
            'wizard_build': _run_observerctl_cli([
                'ds',
                'wizard',
                '--workflow',
                'build',
                '--hydrate-dataset',
                '1',
                '--execute',
                '--json',
            ]),
            'wizard_train_preview': _run_observerctl_cli([
                'ds',
                'wizard',
                '--workflow',
                'train',
                '--hydrate-dataset',
                '1',
                '--set',
                'model_type=unsupervised',
                '--section',
                'report',
                '--json',
            ]),
            'wizard_train': _run_observerctl_cli([
                'ds',
                'wizard',
                '--workflow',
                'train',
                '--hydrate-dataset',
                '1',
                '--set',
                'model_type=unsupervised',
                '--execute',
                '--json',
            ]),
        }

        register_packet = command_runs['register_authority_dataset'].get('stdout_json', {}) if isinstance(command_runs['register_authority_dataset'].get('stdout_json', {}), dict) else {}
        build_preview_packet = _command_stdout_json(command_runs['wizard_build_preview'])
        build_packet = command_runs['wizard_build'].get('stdout_json', {}) if isinstance(command_runs['wizard_build'].get('stdout_json', {}), dict) else {}
        train_preview_packet = _command_stdout_json(command_runs['wizard_train_preview'])
        train_packet = command_runs['wizard_train'].get('stdout_json', {}) if isinstance(command_runs['wizard_train'].get('stdout_json', {}), dict) else {}

        expected_alias = str(((register_packet.get('dataset', {}) if isinstance(register_packet.get('dataset', {}), dict) else {}).get('display_alias', '')) or '').strip()
        train_manifest_path = _resolve_probe_artifact_path(sandbox_root, str((train_packet.get('artifacts', {}) if isinstance(train_packet.get('artifacts', {}), dict) else {}).get('train_manifest', '') or ''))

        command_runs['wizard_evaluate_preview'] = _run_observerctl_cli([
            'ds',
            'wizard',
            '--workflow',
            'evaluate',
            '--hydrate-dataset',
            '1',
            '--hydrate-train',
            str(train_manifest_path),
            '--section',
            'report',
            '--json',
        ])
        command_runs['wizard_evaluate'] = _run_observerctl_cli([
            'ds',
            'wizard',
            '--workflow',
            'evaluate',
            '--hydrate-dataset',
            '1',
            '--hydrate-train',
            str(train_manifest_path),
            '--execute',
            '--json',
        ])
        command_runs['wizard_score_preview'] = _run_observerctl_cli([
            'ds',
            'wizard',
            '--workflow',
            'score',
            '--hydrate-dataset',
            '1',
            '--hydrate-train',
            str(train_manifest_path),
            '--section',
            'report',
            '--json',
        ])
        command_runs['wizard_score'] = _run_observerctl_cli([
            'ds',
            'wizard',
            '--workflow',
            'score',
            '--hydrate-dataset',
            '1',
            '--hydrate-train',
            str(train_manifest_path),
            '--execute',
            '--json',
        ])

        evaluate_preview_packet = _command_stdout_json(command_runs['wizard_evaluate_preview'])
        evaluate_packet = command_runs['wizard_evaluate'].get('stdout_json', {}) if isinstance(command_runs['wizard_evaluate'].get('stdout_json', {}), dict) else {}
        score_preview_packet = _command_stdout_json(command_runs['wizard_score_preview'])
        score_packet = command_runs['wizard_score'].get('stdout_json', {}) if isinstance(command_runs['wizard_score'].get('stdout_json', {}), dict) else {}

        alias_root = sandbox_root / 'docs' / 'reports' / 'collections' / expected_alias
        publication_root = sandbox_root / 'docs' / 'reports' / 'collections'
        collection_directory_names = sorted(path.name for path in publication_root.iterdir() if path.is_dir()) if publication_root.exists() else []

        workflow_packets = {
            'build': build_packet,
            'train': train_packet,
            'evaluate': evaluate_packet,
            'score': score_packet,
        }
        published_stage_paths: Dict[str, Path] = {}
        stage_alias_texts: Dict[str, str] = {}
        for workflow, packet in workflow_packets.items():
            publication = packet.get('publication', {}) if isinstance(packet.get('publication', {}), dict) else {}
            current_run = publication.get('current_run', {}) if isinstance(publication.get('current_run', {}), dict) else {}
            published_paths = current_run.get('published_report_paths', {}) if isinstance(current_run.get('published_report_paths', {}), dict) else {}
            stage_path = _resolve_probe_artifact_path(sandbox_root, str(published_paths.get('processing_markdown', '') or ''))
            published_stage_paths[workflow] = stage_path
            if str(stage_path) and stage_path.is_file():
                stage_alias_texts[workflow] = stage_path.read_text(encoding='utf-8')

        unresolved_bundle = prepare_report_bundle(anchor, 'evaluate', run_id='frame-d-missing-alias')
        unresolved_eval_dir = unresolved_bundle.artifact_dirs['evaluation']
        unresolved_eval_dir.mkdir(parents=True, exist_ok=True)
        unresolved_run_json = unresolved_eval_dir / 'run.json'
        unresolved_run_md = unresolved_eval_dir / 'run.md'
        unresolved_run_json.write_text('{}\n', encoding='utf-8')
        unresolved_run_md.write_text('# unresolved alias\n', encoding='utf-8')
        unresolved_packet = observerctl_module._ds_finalize_run_packet(
            {
                'timestamp_utc': observerctl_module._utc_now(),
                'runtime_cli_surface': 'observerctl',
                'decision': 'go',
                'action': 'ds-evaluate',
                'command_family': 'ds',
                'command_path': 'observerctl ds evaluate',
                'implementation_state': 'command-available',
                'underlying_surface': 'analysis.evaluation_harness',
                'summary': 'Unresolved alias negative path probe.',
                'artifacts': {},
                'reason_codes': [],
            },
            bundle=unresolved_bundle,
            artifact_paths={
                'run_json': unresolved_run_json,
                'run_md': unresolved_run_md,
            },
            context={'max_fpr': 0.02},
            lineage={},
        )
        unresolved_fallback_dir = sandbox_root / 'docs' / 'reports' / 'collections' / 'frame-d-missing-alias'

        result_matrix = {
            'authority_dataset_registered': int(command_runs['register_authority_dataset'].get('returncode', 1)) == 0 and bool(expected_alias),
            'build_preview_ready': int(command_runs['wizard_build_preview'].get('returncode', 1)) == 0 and str(build_preview_packet.get('execution_state', '')).strip().lower() == 'ready',
            'train_preview_ready': int(command_runs['wizard_train_preview'].get('returncode', 1)) == 0 and str(train_preview_packet.get('execution_state', '')).strip().lower() == 'ready',
            'evaluate_preview_ready': int(command_runs['wizard_evaluate_preview'].get('returncode', 1)) == 0 and str(evaluate_preview_packet.get('execution_state', '')).strip().lower() == 'ready',
            'score_preview_ready': int(command_runs['wizard_score_preview'].get('returncode', 1)) == 0 and str(score_preview_packet.get('execution_state', '')).strip().lower() == 'ready',
            'preview_packets_display_registered_alias': all(
                _wizard_packet_view_contains(command_runs[name], expected_alias)
                for name in ('wizard_build_preview', 'wizard_train_preview', 'wizard_evaluate_preview', 'wizard_score_preview')
            ),
            'build_packet_go': str(build_packet.get('decision', '')).strip().lower() == 'go',
            'train_packet_go': str(train_packet.get('decision', '')).strip().lower() == 'go',
            'evaluate_packet_go': str(evaluate_packet.get('decision', '')).strip().lower() == 'go',
            'score_packet_go': str(score_packet.get('decision', '')).strip().lower() == 'go',
            'build_alias_matches_registered_alias': str(build_packet.get('collection_alias', '') or '').strip() == expected_alias,
            'train_alias_matches_registered_alias': str(train_packet.get('collection_alias', '') or '').strip() == expected_alias,
            'evaluate_alias_matches_registered_alias': str(evaluate_packet.get('collection_alias', '') or '').strip() == expected_alias,
            'score_alias_matches_registered_alias': str(score_packet.get('collection_alias', '') or '').strip() == expected_alias,
            'publications_all_go': all(
                str(((packet.get('publication', {}) if isinstance(packet.get('publication', {}), dict) else {}).get('decision', '') or '')).strip().lower() == 'go'
                for packet in workflow_packets.values()
            ),
            'publication_alias_root_exists': alias_root.exists(),
            'publication_alias_root_has_all_workflow_dirs': all((alias_root / 'processing' / lane).exists() for lane in ('build', 'train', 'eval', 'score')),
            'stage_reports_include_registered_alias': all(
                ('**Collection alias**: `{0}`'.format(expected_alias) in stage_alias_texts.get(workflow, ''))
                for workflow in workflow_packets.keys()
            ),
            'no_run_id_fallback_directories_created': all(
                not (publication_root / str(packet.get('run_id', '') or '').strip()).exists()
                for packet in workflow_packets.values()
                if str(packet.get('run_id', '') or '').strip()
            ),
            'only_registered_alias_directory_present': collection_directory_names == [expected_alias],
            'missing_alias_fails_closed': str(unresolved_packet.get('decision', '')).strip().lower() == 'no-go' and 'critical_check_failed:collection_alias_unresolved' in list(unresolved_packet.get('reason_codes', []) or []),
            'missing_alias_skips_publication_and_artifacts': str(((unresolved_packet.get('publication', {}) if isinstance(unresolved_packet.get('publication', {}), dict) else {}).get('decision', '') or '')).strip().lower() == 'skipped' and 'report_json' not in dict(unresolved_packet.get('artifacts', {}) or {}) and 'ds_run_index_jsonl' not in dict(unresolved_packet.get('artifacts', {}) or {}),
            'missing_alias_creates_no_fallback_directory': not unresolved_fallback_dir.exists(),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMED_DS_ALIAS_COHERENCE_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map({
                'authority_input': input_path,
                'authority_manifest': authority_manifest,
                'train_manifest': train_manifest_path,
                'alias_root': alias_root,
                'build_stage_report': published_stage_paths.get('build', Path()),
                'train_stage_report': published_stage_paths.get('train', Path()),
                'evaluate_stage_report': published_stage_paths.get('evaluate', Path()),
                'score_stage_report': published_stage_paths.get('score', Path()),
            }),
            'artifact_snapshots': {
                'registered_dataset': register_packet.get('dataset', {}) if isinstance(register_packet.get('dataset', {}), dict) else {},
                'preview_packets': {
                    'build': build_preview_packet,
                    'train': train_preview_packet,
                    'evaluate': evaluate_preview_packet,
                    'score': score_preview_packet,
                },
                'workflow_summary': {
                    workflow: {
                        'run_id': str(packet.get('run_id', '') or ''),
                        'collection_alias': str(packet.get('collection_alias', '') or ''),
                        'publication_decision': str(((packet.get('publication', {}) if isinstance(packet.get('publication', {}), dict) else {}).get('decision', '') or '')),
                        'processing_markdown': _rel_to_repo(published_stage_paths.get(workflow, Path())) if str(published_stage_paths.get(workflow, Path())) else '',
                    }
                    for workflow, packet in workflow_packets.items()
                },
                'unresolved_alias_packet': {
                    'decision': str(unresolved_packet.get('decision', '') or ''),
                    'reason_codes': list(unresolved_packet.get('reason_codes', []) or []),
                    'publication': unresolved_packet.get('publication', {}),
                    'finalization': unresolved_packet.get('finalization', {}),
                },
            },
            'result_matrix': result_matrix,
            'findings': {
                'expected_alias': expected_alias,
                'collection_directory_names': collection_directory_names,
                'published_stage_paths': _report_path_map(published_stage_paths),
            },
        }

        report_json = run_dir / 'framed_ds_alias_coherence_probe.json'
        report_md = run_dir / 'framed_ds_alias_coherence_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame D DS Alias Coherence Probe', report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': report['next_bite_result'],
            'collection_alias': expected_alias,
        })

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_anchor is not None:
            _restore_probe_observer_project(original_project_anchor, original_file)
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_ds_wizard_stale_state_continuity_probe() -> int:
    from calamum_librarian import register_librarian_dataset_packet

    run_id = 'frameb-ds-wizard-stale-state-continuity-{0}'.format(_utc_stamp())
    run_dir = FRAMEB_DS_WIZARD_STALE_STATE_CONTINUITY_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEB_DS_WIZARD_STALE_STATE_CONTINUITY_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frameb-ds-wizard-stale-state-continuity-signing-key',
            security_report_title='# Frame B DS wizard stale-state continuity probe security report\n',
        )
        anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)

        artifacts_dir = run_dir / 'artifacts'
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        dataset_a_dir = sandbox_root / 'datasets' / 'stale_alpha'
        dataset_b_dir = sandbox_root / 'datasets' / 'fresh_beta'
        dataset_a_dir.mkdir(parents=True, exist_ok=True)
        dataset_b_dir.mkdir(parents=True, exist_ok=True)

        dataset_a_manifest = dataset_a_dir / 'dataset_manifest.json'
        dataset_a_features = dataset_a_dir / 'features_alpha.csv'
        dataset_a_labels = dataset_a_dir / 'labels_alpha.csv'
        dataset_b_manifest = dataset_b_dir / 'dataset_manifest.json'
        dataset_b_features = dataset_b_dir / 'features_beta.csv'
        dataset_b_labels = dataset_b_dir / 'labels_beta.csv'
        train_manifest = artifacts_dir / 'fresh_beta_train_manifest.json'
        model_path = artifacts_dir / 'fresh_beta_model.pkl'

        dataset_a_features.write_text('record_id,feature\na-1,0.1\n', encoding='utf-8')
        dataset_a_labels.write_text('record_id,label\na-1,TV-0\n', encoding='utf-8')
        dataset_b_features.write_text('record_id,feature\nb-1,0.9\n', encoding='utf-8')
        dataset_b_labels.write_text('record_id,label\nb-1,TV-3\n', encoding='utf-8')
        model_path.write_bytes(b'model')

        _write_json(
            dataset_a_manifest,
            {
                'features_csv': str(dataset_a_features),
                'labels_csv': str(dataset_a_labels),
                'has_labels': True,
            },
        )
        _write_json(
            dataset_b_manifest,
            {
                'features_csv': str(dataset_b_features),
                'labels_csv': str(dataset_b_labels),
                'has_labels': True,
            },
        )
        _write_json(
            train_manifest,
            {
                'dataset_manifest_path': str(dataset_b_manifest),
                'model_path': str(model_path),
                'model_type': 'unsupervised',
            },
        )

        register_packet = register_librarian_dataset_packet(
            anchor,
            dataset_a_manifest,
            access_class='local',
            display_name='Frame B Stale Alpha',
            run_id='frameb-stale-alpha',
        )

        state = observerctl_module._ds_wizard_new_state('evaluate')
        observerctl_module._ds_wizard_hydrate_dataset_reference(state, '1')
        observerctl_module._ds_wizard_hydrate_train_reference(state, str(train_manifest))

        command_runs = {
            'wizard_cross_hydrate_preview': _run_observerctl_cli([
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
            ]),
        }

        preview_packet = _command_stdout_json(command_runs['wizard_cross_hydrate_preview'])
        preview_view = _wizard_packet_view(command_runs['wizard_cross_hydrate_preview'])
        command_preview = str(preview_packet.get('command_preview', '') or '').strip()
        packet_artifacts = preview_packet.get('artifacts', {}) if isinstance(preview_packet.get('artifacts', {}), dict) else {}

        result_matrix = {
            'authority_dataset_registered': str(register_packet.get('decision', '')).strip().lower() == 'go',
            'direct_train_hydration_refreshes_dataset_manifest': str(state.values.get('dataset_manifest', '') or '').strip() == str(dataset_b_manifest),
            'direct_train_hydration_refreshes_features_csv': str(state.values.get('features_csv', '') or '').strip() == str(dataset_b_features),
            'direct_train_hydration_refreshes_labels_csv': str(state.values.get('labels_csv', '') or '').strip() == str(dataset_b_labels),
            'direct_train_hydration_refreshes_model_path': str(state.values.get('model_path', '') or '').strip() == str(model_path),
            'preview_cli_returncode_zero': int(command_runs['wizard_cross_hydrate_preview'].get('returncode', 1)) == 0,
            'preview_execution_ready': str(preview_packet.get('execution_state', '')).strip().lower() == 'ready',
            'preview_dataset_manifest_matches_train_context': str(packet_artifacts.get('dataset_manifest', '') or '').strip() == str(dataset_b_manifest),
            'preview_command_uses_refreshed_features': str(dataset_b_features) in command_preview and str(dataset_a_features) not in command_preview,
            'preview_command_uses_refreshed_labels': str(dataset_b_labels) in command_preview and str(dataset_a_labels) not in command_preview,
            'preview_view_lists_refreshed_dataset_and_model': dataset_b_manifest.name in '\n'.join(preview_view) and model_path.name in '\n'.join(preview_view),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEB_DS_WIZARD_STALE_STATE_CONTINUITY_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map(
                {
                    'dataset_a_manifest': dataset_a_manifest,
                    'dataset_a_features': dataset_a_features,
                    'dataset_a_labels': dataset_a_labels,
                    'dataset_b_manifest': dataset_b_manifest,
                    'dataset_b_features': dataset_b_features,
                    'dataset_b_labels': dataset_b_labels,
                    'train_manifest': train_manifest,
                    'model_path': model_path,
                }
            ),
            'artifact_snapshots': {
                'registered_dataset': register_packet,
                'direct_state_after_cross_hydration': {
                    'dataset_manifest': str(state.values.get('dataset_manifest', '') or ''),
                    'features_csv': str(state.values.get('features_csv', '') or ''),
                    'labels_csv': str(state.values.get('labels_csv', '') or ''),
                    'model_path': str(state.values.get('model_path', '') or ''),
                    'hydrated_from': dict(state.hydrated_from),
                },
                'preview_packet': preview_packet,
            },
            'result_matrix': result_matrix,
            'findings': {
                'preview_command': command_preview,
                'preview_view': preview_view,
                'hydrated_from': dict(state.hydrated_from),
            },
        }

        report_json = run_dir / 'frameb_ds_wizard_stale_state_continuity_probe.json'
        report_md = run_dir / 'frameb_ds_wizard_stale_state_continuity_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame B DS Wizard Stale-State Continuity Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'dataset_manifest': str(packet_artifacts.get('dataset_manifest', '') or ''),
            },
        )

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_anchor is not None:
            _restore_probe_observer_project(original_project_anchor, original_file)
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_ds_wizard_labeled_eval_contract_coherence_probe() -> int:
    from calamum_librarian import register_librarian_dataset_packet

    run_id = 'frameb-ds-wizard-labeled-eval-contract-coherence-{0}'.format(_utc_stamp())
    run_dir = FRAMEB_DS_WIZARD_LABELED_EVAL_CONTRACT_COHERENCE_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEB_DS_WIZARD_LABELED_EVAL_CONTRACT_COHERENCE_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frameb-ds-wizard-labeled-eval-contract-coherence-signing-key',
            security_report_title='# Frame B DS wizard labeled eval contract coherence probe security report\n',
        )
        anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)

        artifacts_dir = run_dir / 'artifacts'
        dataset_dir = sandbox_root / 'datasets' / 'labeled_contract'
        dataset_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

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
        _write_json(
            dataset_manifest,
            {
                'features_csv': str(features_csv),
                'labels_csv': str(labels_csv),
                'splits_csv': str(splits_csv),
                'feature_columns': ['feature'],
                'total_records': 4,
                'has_labels': True,
            },
        )

        register_packet = register_librarian_dataset_packet(
            anchor,
            dataset_manifest,
            access_class='local',
            display_name='Frame B Labeled Contract',
            run_id='frameb-labeled-contract',
        )
        train_packet = observerctl_module._ds_train(
            dataset=str(dataset_manifest),
            out_dir='',
            model_type='supervised',
            seed=42,
        )
        train_artifacts = dict(train_packet.get('artifacts', {}) or {}) if isinstance(train_packet.get('artifacts', {}), dict) else {}
        train_manifest = _resolve_probe_artifact_path(sandbox_root, str(train_artifacts.get('train_manifest', '') or ''))

        command_runs = {
            'wizard_labeled_eval_execute': _run_observerctl_cli([
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
            ]),
        }

        evaluate_packet = _command_stdout_json(command_runs['wizard_labeled_eval_execute'])
        evaluate_artifacts = dict(evaluate_packet.get('artifacts', {}) or {}) if isinstance(evaluate_packet.get('artifacts', {}), dict) else {}
        run_json_path = _resolve_probe_artifact_path(sandbox_root, str(evaluate_artifacts.get('run_json', '') or ''))
        run_json = _read_json(run_json_path) if run_json_path.exists() else {}
        evaluation = run_json.get('evaluation', {}) if isinstance(run_json.get('evaluation', {}), dict) else {}
        data = run_json.get('data', {}) if isinstance(run_json.get('data', {}), dict) else {}

        result_matrix = {
            'authority_dataset_registered': str(register_packet.get('decision', '')).strip().lower() == 'go',
            'supervised_train_succeeds_on_label_column': str(train_packet.get('decision', '')).strip().lower() == 'go' and train_manifest.exists(),
            'wizard_eval_execute_returncode_zero': int(command_runs['wizard_labeled_eval_execute'].get('returncode', 1)) == 0,
            'wizard_eval_packet_go': str(evaluate_packet.get('decision', '')).strip().lower() == 'go',
            'wizard_eval_packet_has_labels_true': bool(evaluate_packet.get('has_labels', False)) is True,
            'wizard_eval_run_json_written': run_json_path.exists(),
            'run_json_has_labels_true': bool(evaluation.get('has_labels', False)) is True,
            'run_json_thresholding_is_labeled_mode': str(evaluation.get('thresholding', '') or '').strip() == 'fpr_constrained_best_f1',
            'run_json_preserves_label_path': str(data.get('labels_csv', '') or '').strip() == str(labels_csv),
            'run_json_preserves_dataset_manifest': str(data.get('dataset_manifest', '') or '').strip() == str(dataset_manifest),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEB_DS_WIZARD_LABELED_EVAL_CONTRACT_COHERENCE_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map(
                {
                    'dataset_manifest': dataset_manifest,
                    'features_csv': features_csv,
                    'labels_csv': labels_csv,
                    'splits_csv': splits_csv,
                    'train_manifest': train_manifest,
                    'run_json': run_json_path,
                }
            ),
            'artifact_snapshots': {
                'register_packet': register_packet,
                'train_packet': train_packet,
                'evaluate_packet': evaluate_packet,
                'run_json': run_json,
            },
            'result_matrix': result_matrix,
            'findings': {
                'evaluation_summary': str(evaluate_packet.get('summary', '') or ''),
                'evaluation_metrics': evaluation.get('metrics', {}),
                'evaluation_counts': evaluation.get('counts', {}),
            },
        }

        report_json = run_dir / 'frameb_ds_wizard_labeled_eval_contract_coherence_probe.json'
        report_md = run_dir / 'frameb_ds_wizard_labeled_eval_contract_coherence_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame B DS Wizard Labeled Eval Contract Coherence Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'has_labels': bool(evaluate_packet.get('has_labels', False)),
            },
        )

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_anchor is not None:
            _restore_probe_observer_project(original_project_anchor, original_file)
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_ds_wizard_blocked_execute_truthfulness_probe() -> int:
    run_id = 'frameb-ds-wizard-blocked-execute-truthfulness-{0}'.format(_utc_stamp())
    run_dir = FRAMEB_DS_WIZARD_BLOCKED_EXECUTE_TRUTHFULNESS_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEB_DS_WIZARD_BLOCKED_EXECUTE_TRUTHFULNESS_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        _sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frameb-ds-wizard-blocked-execute-truthfulness-signing-key',
            security_report_title='# Frame B DS wizard blocked execute truthfulness probe security report\n',
        )

        command_runs = {
            'wizard_blocked_preview': _run_observerctl_cli([
                'ds',
                'wizard',
                '--workflow',
                'evaluate',
                '--section',
                'check',
                '--json',
            ]),
            'wizard_blocked_execute': _run_observerctl_cli([
                'ds',
                'wizard',
                '--workflow',
                'evaluate',
                '--execute',
                '--json',
            ]),
        }

        preview_packet = _command_stdout_json(command_runs['wizard_blocked_preview'])
        execute_packet = _command_stdout_json(command_runs['wizard_blocked_execute'])
        execute_artifacts = execute_packet.get('artifacts', {}) if isinstance(execute_packet.get('artifacts', {}), dict) else {}
        validation_issues = _wizard_packet_validation_issues(command_runs['wizard_blocked_execute'])

        result_matrix = {
            'preview_cli_returncode_zero': int(command_runs['wizard_blocked_preview'].get('returncode', 1)) == 0,
            'preview_reports_blocked_execution_state': str(preview_packet.get('execution_state', '')).strip().lower() == 'blocked',
            'execute_packet_no_go': str(execute_packet.get('decision', '')).strip().lower() == 'no-go',
            'execute_reason_code_is_validation_block': 'critical_check_failed:wizard_validation_blocked' in list(execute_packet.get('reason_codes', []) or []),
            'execute_validation_issues_are_operator_legible': 'features_csv is required' in validation_issues,
            'execute_packet_carries_command_preview': bool(str(execute_packet.get('command_preview', '') or '').strip()),
            'execute_packet_claims_no_success_artifacts': not any(str(value or '').strip() for value in execute_artifacts.values()),
            'execute_packet_stays_in_evaluate_lane': str(execute_packet.get('wizard_workflow', '')).strip() == 'evaluate',
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEB_DS_WIZARD_BLOCKED_EXECUTE_TRUTHFULNESS_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map({}),
            'artifact_snapshots': {
                'preview_packet': preview_packet,
                'execute_packet': execute_packet,
            },
            'result_matrix': result_matrix,
            'findings': {
                'validation_issues': validation_issues,
                'reason_codes': list(execute_packet.get('reason_codes', []) or []),
                'command_preview': str(execute_packet.get('command_preview', '') or ''),
            },
        }

        report_json = run_dir / 'frameb_ds_wizard_blocked_execute_truthfulness_probe.json'
        report_md = run_dir / 'frameb_ds_wizard_blocked_execute_truthfulness_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame B DS Wizard Blocked Execute Truthfulness Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'decision': str(execute_packet.get('decision', '') or ''),
            },
        )

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_ds_wizard_execute_failure_truthfulness_probe() -> int:
    run_id = 'frameb-ds-wizard-execute-failure-truthfulness-{0}'.format(_utc_stamp())
    run_dir = FRAMEB_DS_WIZARD_EXECUTE_FAILURE_TRUTHFULNESS_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEB_DS_WIZARD_EXECUTE_FAILURE_TRUTHFULNESS_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    original_ds_score = None
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frameb-ds-wizard-execute-failure-truthfulness-signing-key',
            security_report_title='# Frame B DS wizard execute failure truthfulness probe security report\n',
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)

        artifacts_dir = run_dir / 'artifacts'
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        dataset_manifest = artifacts_dir / 'dataset_manifest.json'
        features_csv = artifacts_dir / 'features.csv'
        model_path = artifacts_dir / 'model.pkl'
        train_manifest = artifacts_dir / 'train_manifest.json'

        features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
        model_path.write_bytes(b'model')
        _write_json(
            dataset_manifest,
            {
                'features_csv': str(features_csv),
                'total_records': 1,
                'has_labels': False,
            },
        )
        _write_json(
            train_manifest,
            {
                'dataset_manifest_path': str(dataset_manifest),
                'model_path': str(model_path),
                'model_type': 'unsupervised',
            },
        )

        def _failing_score(dataset: str, model: str, out_file: str, collection_alias: str = '') -> Dict[str, Any]:
            raise RuntimeError('synthetic score failure for truthfulness probe')

        original_ds_score = observerctl_module._ds_score
        observerctl_module._ds_score = _failing_score

        state = observerctl_module._ds_wizard_new_state('score')
        state.values['dataset_manifest'] = str(dataset_manifest)
        state.values['train_manifest'] = str(train_manifest)
        state.values['model_path'] = str(model_path)
        state.values['dataset_alias'] = 'synthetic-score-failure'
        observerctl_module._ds_wizard_open_section(state, 'run')

        pre_execute_validate = strip_ansi(observerctl_module._ds_wizard_left_rail_rows(state)[1])
        pre_execute_advance = strip_ansi(observerctl_module._ds_wizard_left_rail_rows(state)[2])
        derived_packet = observerctl_module._ds_wizard_attempt_execute(state)
        state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'execute')
        rendered_lines = [strip_ansi(line) for line in observerctl_module._ds_wizard_render(state)]
        transient_lines = observerctl_module._ds_wizard_transient_lines(state)

        result_matrix = {
            'pre_execute_validate_ready': pre_execute_validate == 'validate: ready',
            'pre_execute_advance_no_go': pre_execute_advance == 'advance: no-go',
            'derived_packet_no_go': str(derived_packet.get('decision', '')).strip().lower() == 'no-go',
            'derived_reason_code_is_execution_failure': 'critical_check_failed:wizard_execution_failed' in list(derived_packet.get('reason_codes', []) or []),
            'terminal_transient_mentions_execute_failed': transient_lines == ['execute failed: workflow execution failed before completion'],
            'terminal_transient_avoids_validation_blame': all('validate this workflow first' not in line for line in transient_lines),
            'render_keeps_validate_ready': any(line == 'validate: ready' for line in rendered_lines),
            'render_keeps_processing_ready': any('processing: ready' == ' '.join(line.split()) for line in rendered_lines),
            'command_handler_keeps_wizard_open': packet is None and should_exit is False,
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEB_DS_WIZARD_EXECUTE_FAILURE_TRUTHFULNESS_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': {
                'wizard_execute_failure_packet': {
                    'args': ['ds', 'wizard', 'score', 'attempt-execute'],
                    'returncode': 2 if str(derived_packet.get('decision', '')).strip().lower() != 'go' else 0,
                    'stderr_text': '',
                    'stdout_text': '',
                    'stdout_json': derived_packet,
                },
                'wizard_execute_failure_render': {
                    'args': ['ds', 'wizard', 'score', 'render-run-pane'],
                    'returncode': 0,
                    'stderr_text': '',
                    'stdout_text': '',
                    'stdout_json': {
                        'wizard_view': rendered_lines,
                        'transient_lines': transient_lines,
                    },
                },
            },
            'artifact_paths': _report_path_map(
                {
                    'dataset_manifest': dataset_manifest,
                    'features_csv': features_csv,
                    'train_manifest': train_manifest,
                    'model_path': model_path,
                }
            ),
            'artifact_snapshots': {
                'derived_packet': derived_packet,
                'rendered_lines': rendered_lines,
                'transient_lines': transient_lines,
            },
            'result_matrix': result_matrix,
            'findings': {
                'derived_summary': str(derived_packet.get('summary', '') or ''),
                'derived_reason_codes': list(derived_packet.get('reason_codes', []) or []),
                'rendered_run_lines': rendered_lines,
                'transient_lines': transient_lines,
            },
        }

        report_json = run_dir / 'frameb_ds_wizard_execute_failure_truthfulness_probe.json'
        report_md = run_dir / 'frameb_ds_wizard_execute_failure_truthfulness_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame B DS Wizard Execute Failure Truthfulness Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'derived_decision': str(derived_packet.get('decision', '') or ''),
            },
        )

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_ds_score is not None:
            observerctl_module._ds_score = original_ds_score
        if original_project_anchor is not None:
            _restore_probe_observer_project(original_project_anchor, original_file)
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_metadata_contract_probe() -> int:
    run_id = 'frame4-metadata-contract-{0}'.format(_utc_stamp())
    run_dir = FRAME4_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAME4_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        _sandbox_root, sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frame4-probe-signing-key',
            security_report_title='# Frame 4 metadata probe security report\n',
        )

        command_runs = {
            'collect_normal': _run_observerctl_cli([
                'baseline', 'collect',
                '--source', 'sim',
                '--mode', 'canary',
                '--profile', 'normal',
                '--duration-sec', '0.02',
                '--interval-sec', '0.01',
                '--window-id', 'frame4_probe_normal',
                '--output', str(run_dir / 'collect_normal.json'),
                '--json',
            ]),
            'collect_baseline': _run_observerctl_cli([
                'baseline', 'collect',
                '--source', 'sim',
                '--mode', 'canary',
                '--profile', 'baseline',
                '--duration-sec', '0.02',
                '--interval-sec', '0.01',
                '--window-id', 'frame4_probe_baseline',
                '--output', str(run_dir / 'collect_baseline.json'),
                '--json',
            ]),
        }

        normal_packet = _read_json(run_dir / 'collect_normal.json')
        baseline_packet = _read_json(run_dir / 'collect_baseline.json')
        resource_index = sandbox_log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'resource' / 'index.jsonl'

        normal_sample_row = _read_first_segment_row(normal_packet)
        baseline_sample_row = _read_first_segment_row(baseline_packet)
        normal_index_row = _read_jsonl_latest_matching(resource_index, 'stream_type', 'resource_normal')
        baseline_index_row = _read_jsonl_latest_matching(resource_index, 'stream_type', 'resource_baseline')

        common_fields = ['stream_type', 'sampling_profile_id', 'mode_at_capture', 'source_axis', 'timestamp_utc']
        baseline_fields = common_fields + ['baseline_window_id']

        metadata_findings = {
            'resource_normal': {
                'sample_row_path': str((normal_packet.get('segments', [{}])[0] or {}).get('path', '')),
                'index_path': str(resource_index).replace('\\', '/'),
                'sample_field_presence': _field_presence(normal_sample_row, common_fields),
                'index_field_presence': _field_presence(normal_index_row, common_fields),
                'sample_row': normal_sample_row,
                'index_row': normal_index_row,
            },
            'resource_baseline': {
                'sample_row_path': str((baseline_packet.get('segments', [{}])[0] or {}).get('path', '')),
                'index_path': str(resource_index).replace('\\', '/'),
                'sample_field_presence': _field_presence(baseline_sample_row, baseline_fields),
                'index_field_presence': _field_presence(baseline_index_row, baseline_fields),
                'sample_row': baseline_sample_row,
                'index_row': baseline_index_row,
            },
        }

        all_sample_fields_present = all(all(v for v in details['sample_field_presence'].values()) for details in metadata_findings.values())
        all_index_fields_present = all(all(v for v in details['index_field_presence'].values()) for details in metadata_findings.values())

        next_bite_result = 'pass' if (bool(all_sample_fields_present) and bool(all_index_fields_present)) else 'review'

        report = {
            'run_id': run_id,
            'phase': 'pre_edit_probe',
            'probe_dir': _rel_to_repo(FRAME4_PROBE_DIR),
            'run_dir': _rel_to_repo(run_dir),
            'script': _rel_to_repo(Path(__file__)),
            'command_runs': command_runs,
            'metadata_findings': metadata_findings,
            'all_sample_fields_present': bool(all_sample_fields_present),
            'all_index_fields_present': bool(all_index_fields_present),
            'baseline_window_id_required_only_for_baseline': True,
            'next_bite_result': next_bite_result,
        }
        review_json = run_dir / 'frame4_metadata_probe.json'
        review_md = run_dir / 'frame4_metadata_probe.md'
        _write_json(review_json, report)
        review_md.write_text(_render_metadata_contract_markdown(report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'review_json': _rel_to_repo(review_json),
            'review_md': _rel_to_repo(review_md),
            'all_sample_fields_present': bool(all_sample_fields_present),
            'all_index_fields_present': bool(all_index_fields_present),
            'next_bite_result': next_bite_result,
        })

        print('run_id={0}'.format(run_id))
        print('run_dir={0}'.format(_rel_to_repo(run_dir)))
        print('review_json={0}'.format(_rel_to_repo(review_json)))
        print('review_md={0}'.format(_rel_to_repo(review_md)))
        print('next_bite_result={0}'.format(next_bite_result))
        print('all_sample_fields_present={0}'.format(all_sample_fields_present))
        print('all_index_fields_present={0}'.format(all_index_fields_present))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_metadata_contract_regression_probe() -> int:
    run_id = 'frame4-metadata-contract-regression-{0}'.format(_utc_stamp())
    run_dir = FRAME4_REGRESSION_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAME4_REGRESSION_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        _sandbox_root, sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frame4-regression-probe-signing-key',
            security_report_title='# Frame 4 metadata regression probe security report\n',
        )

        resource_archive_dir = sandbox_log_dir / 'data' / 'calamum' / 'archive'
        resource_index = sandbox_log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'resource' / 'index.jsonl'
        resource_archive_dir.mkdir(parents=True, exist_ok=True)
        resource_index.parent.mkdir(parents=True, exist_ok=True)

        normal_segment_path = resource_archive_dir / 'resource_sim_canary_normal_regression_seg0001.jsonl'
        baseline_segment_path = resource_archive_dir / 'resource_sim_canary_baseline_regression_seg0001.jsonl'

        normal_sample_row = {
            'record_class': 'resource_telemetry',
            'run_id': 'frame4-regression-normal-seed',
            'stream_type': 'resource_normal',
            'sampling_profile_id': 'resource_normal_v1',
            'source_axis': 'sim',
            'timestamp_utc': '2026-03-23T00:00:00Z',
            'baseline_window_id': 'frame4_regression_normal',
            'cpu_pct_now': 20.0,
            'ram_pct_now': 40.0,
        }
        baseline_sample_row = {
            'record_class': 'resource_telemetry',
            'run_id': 'frame4-regression-baseline-seed',
            'stream_type': 'resource_baseline',
            'sampling_profile_id': 'resource_baseline_v1',
            'mode_at_capture': 'canary',
            'source_axis': 'sim',
            'timestamp_utc': '2026-03-23T00:00:01Z',
            'cpu_pct_now': 30.0,
            'ram_pct_now': 42.0,
        }
        normal_index_row = {
            'run_id': 'frame4-regression-normal-seed',
            'stream_type': 'resource_normal',
            'mode_at_capture': 'canary',
            'source_axis': 'sim',
            'timestamp_utc': '2026-03-23T00:00:00Z',
            'segment_path': str(normal_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'window_id': 'frame4_regression_normal',
        }
        baseline_index_row = {
            'run_id': 'frame4-regression-baseline-seed',
            'stream_type': 'resource_baseline',
            'sampling_profile_id': 'resource_baseline_v1',
            'mode_at_capture': 'canary',
            'source_axis': 'sim',
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'window_id': 'frame4_regression_baseline',
        }

        _append_jsonl(normal_segment_path, normal_sample_row)
        _append_jsonl(baseline_segment_path, baseline_sample_row)
        _append_jsonl(resource_index, normal_index_row)
        _append_jsonl(resource_index, baseline_index_row)

        common_fields = ['stream_type', 'sampling_profile_id', 'mode_at_capture', 'source_axis', 'timestamp_utc']
        baseline_fields = common_fields + ['baseline_window_id']

        metadata_findings = {
            'resource_normal': {
                'sample_row_path': str(normal_segment_path).replace('\\', '/'),
                'index_path': str(resource_index).replace('\\', '/'),
                'sample_field_presence': _field_presence(normal_sample_row, common_fields),
                'index_field_presence': _field_presence(normal_index_row, common_fields),
                'sample_row': normal_sample_row,
                'index_row': normal_index_row,
            },
            'resource_baseline': {
                'sample_row_path': str(baseline_segment_path).replace('\\', '/'),
                'index_path': str(resource_index).replace('\\', '/'),
                'sample_field_presence': _field_presence(baseline_sample_row, baseline_fields),
                'index_field_presence': _field_presence(baseline_index_row, baseline_fields),
                'sample_row': baseline_sample_row,
                'index_row': baseline_index_row,
            },
        }

        missing_fields = {
            stream_name: {
                'sample_missing': sorted([field for field, present in details['sample_field_presence'].items() if not present]),
                'index_missing': sorted([field for field, present in details['index_field_presence'].items() if not present]),
            }
            for stream_name, details in metadata_findings.items()
        }

        result_matrix = {
            'normal_sample_regression_detected': bool(missing_fields['resource_normal']['sample_missing']),
            'normal_index_regression_detected': bool(missing_fields['resource_normal']['index_missing']),
            'baseline_sample_regression_detected': bool(missing_fields['resource_baseline']['sample_missing']),
            'baseline_index_regression_detected': bool(missing_fields['resource_baseline']['index_missing']),
            'baseline_window_only_required_for_baseline': ('baseline_window_id' not in missing_fields['resource_normal']['sample_missing']) and ('baseline_window_id' in missing_fields['resource_baseline']['sample_missing']),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAME4_REGRESSION_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': {
                'seed_known_bad_contract': {
                    'args': ['synthetic-known-bad-contract'],
                    'returncode': 0,
                    'stderr_text': '',
                    'stdout_text': '',
                    'stdout_json': {'seeded': True},
                },
            },
            'artifact_paths': _report_path_map({
                'resource_index': resource_index,
                'resource_normal_segment': normal_segment_path,
                'resource_baseline_segment': baseline_segment_path,
            }),
            'artifact_snapshots': {
                'metadata_findings': metadata_findings,
                'missing_fields': missing_fields,
            },
            'result_matrix': result_matrix,
            'findings': {
                'metadata_findings': metadata_findings,
                'missing_fields': missing_fields,
            },
        }

        report_json = run_dir / 'frame4_metadata_contract_regression_probe.json'
        report_md = run_dir / 'frame4_metadata_contract_regression_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame 4 Metadata Contract Regression Probe', report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': report['next_bite_result'],
            'regression_fields_detected': missing_fields,
        })

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def _objective_matrix(evidence_packet: Dict[str, Any], monitor_state: Dict[str, Any], resource_latest: Dict[str, Any], resource_normal_latest: Dict[str, Any], segment_exists: bool) -> Dict[str, bool]:
    status_packet = evidence_packet.get('status_packet', {}) if isinstance(evidence_packet.get('status_packet', {}), dict) else {}
    readiness_surfaces = evidence_packet.get('readiness_surfaces', {}) if isinstance(evidence_packet.get('readiness_surfaces', {}), dict) else {}
    stage5 = evidence_packet.get('stage5_prerequisites', {}) if isinstance(evidence_packet.get('stage5_prerequisites', {}), dict) else {}
    checks = status_packet.get('checks', {}) if isinstance(status_packet.get('checks', {}), dict) else {}

    return {
        'observer_runtime_present': str(((checks.get('runtime.observer_service') or {}).get('status', 'err'))).lower() == 'ok',
        'baseline_monitor_runtime_present': str(((readiness_surfaces.get('baseline_monitor') or {}).get('status', 'err'))).lower() == 'ok',
        'monitor_state_written': bool(monitor_state),
        'resource_normal_stream_written': str(resource_normal_latest.get('stream_type', '')).strip().lower() == 'resource_normal',
        'resource_segment_exists': bool(segment_exists),
        'evidence_packet_has_readiness_surfaces': bool(readiness_surfaces),
        'evidence_packet_has_stage5_prereqs': bool(stage5),
        'resource_stream_retention_ready': str(((stage5.get('C24_resource_stream_retention_ready') or {}).get('status', 'err'))).lower() == 'ok',
        'non_activation_probe_kept_source_sim': str(status_packet.get('source', '')).strip().lower() == 'sim',
        'non_activation_probe_kept_current_mode_canary': str(status_packet.get('mode', '')).strip().lower() == 'canary',
    }


def _representation_matrix(evidence_packet: Dict[str, Any], paths: Dict[str, Path], monitor_state: Dict[str, Any], resource_latest: Dict[str, Any]) -> Dict[str, bool]:
    return {
        'status_packet_present': isinstance(evidence_packet.get('status_packet'), dict),
        'gate_packet_present': isinstance(evidence_packet.get('gate_packet'), dict),
        'readiness_surfaces_present': isinstance(evidence_packet.get('readiness_surfaces'), dict),
        'stage5_prerequisites_present': isinstance(evidence_packet.get('stage5_prerequisites'), dict),
        'baseline_monitor_state_present': bool(monitor_state),
        'watchdog_posture_state_present': paths['watchdog_posture'].exists(),
        'watchdog_resource_state_present': paths['watchdog_resource'].exists(),
        'resource_index_present': paths['resource_index'].exists(),
        'resource_index_latest_present': bool(resource_latest),
        'analysis_packet_present': paths['analysis_packet'].exists(),
        'evidence_output_present': paths['evidence_output'].exists(),
    }


def _render_baseline_monitor_runtime_markdown(report: Dict[str, Any]) -> str:
    objective_matrix = report.get('objective_matrix', {})
    representation_matrix = report.get('representation_matrix', {})
    command_runs = report.get('command_runs', {})
    remaining_gaps = report.get('remaining_gaps', {})
    lines = [
        '# Job 0022 Baseline Monitor Runtime Probe',
        '',
        '- Run id: `{0}`'.format(report.get('run_id', '')),
        '- Overall next-bite result: `{0}`'.format(report.get('next_bite_result', 'review')),
        '- Probe scope: sandboxed `observerctl` operations test for baseline-monitor runtime and `resource_normal` retention continuity.',
        '- Run dir: `{0}`'.format(report.get('run_dir', '')),
        '',
        '## Command results',
        '',
    ]
    for name, command in command_runs.items():
        lines.append('### {0}'.format(name))
        lines.append('- returncode: `{0}`'.format(command.get('returncode', '')))
        lines.append('- args: `{0}`'.format(' '.join(command.get('args', []))))
        stderr_text = str(command.get('stderr_text', '') or '').strip()
        lines.append('- stderr: `{0}`'.format(stderr_text if stderr_text else '(empty)'))
        lines.append('')

    lines.extend([
        '## Next-bite objective matrix',
        '',
    ])
    for key, value in objective_matrix.items():
        lines.append('- `{0}`: `{1}`'.format(key, value))

    lines.extend([
        '',
        '## Report coverage matrix',
        '',
    ])
    for key, value in representation_matrix.items():
        lines.append('- `{0}`: `{1}`'.format(key, value))

    lines.extend([
        '',
        '## Remaining gaps surfaced by the same evidence packet',
        '',
    ])
    for key, value in remaining_gaps.items():
        lines.append('- `{0}`: `{1}`'.format(key, json.dumps(value, sort_keys=True)))

    lines.extend([
        '',
        '## Interpretation',
        '',
        '- This bite is considered **successful** when the baseline monitor runtime surface is alive in the sandbox, `resource_normal` retention continuity is real, and the evidence packet includes all major readiness/reporting sections.',
        '- It is acceptable for later Stage 5 classes to remain red in this probe if they belong to later bites (for example, lockdown cadence proof or complete baseline-window proof for non-activation promotion).',
        '',
    ])
    return '\n'.join(lines) + '\n'


def _render_result_matrix_markdown(title: str, report: Dict[str, Any], matrix_heading: str = 'Result matrix') -> str:
    lines = [
        '# {0}'.format(title),
        '',
        '- Run id: `{0}`'.format(report.get('run_id', '')),
        '- Probe dir: `{0}`'.format(report.get('probe_dir', '')),
        '- Run dir: `{0}`'.format(report.get('run_dir', '')),
        '- Overall result: `{0}`'.format(report.get('next_bite_result', 'review')),
        '',
        '## Command results',
        '',
    ]
    for name, command in report.get('command_runs', {}).items():
        lines.append('### {0}'.format(name))
        lines.append('- returncode: `{0}`'.format(command.get('returncode', '')))
        lines.append('- args: `{0}`'.format(' '.join(command.get('args', []))))
        stderr_text = str(command.get('stderr_text', '') or '').strip()
        lines.append('- stderr: `{0}`'.format(stderr_text if stderr_text else '(empty)'))
        lines.append('')

    lines.extend([
        '## {0}'.format(matrix_heading),
        '',
    ])
    for key, value in report.get('result_matrix', {}).items():
        lines.append('- `{0}`: `{1}`'.format(key, value))

    lines.extend([
        '',
        '## Artifact paths',
        '',
    ])
    for key, value in report.get('artifact_paths', {}).items():
        lines.append('- `{0}`: `{1}`'.format(key, value))

    findings = report.get('findings', {}) if isinstance(report.get('findings', {}), dict) else {}
    if findings:
        lines.extend([
            '',
            '## Findings',
            '',
        ])
        for key, value in findings.items():
            lines.append('- `{0}`: `{1}`'.format(key, json.dumps(value, sort_keys=True)))

    return '\n'.join(lines) + '\n'


def _probe_result(matrix: Dict[str, bool]) -> str:
    return 'pass' if matrix and all(bool(value) for value in matrix.values()) else 'review'


def _command_stdout_path(command_result: Dict[str, Any], key: str) -> str:
    stdout_json = command_result.get('stdout_json', {}) if isinstance(command_result.get('stdout_json', {}), dict) else {}
    return str(stdout_json.get(key, '') or '').strip()


def _json_from_text_path(path_text: str) -> Dict[str, Any]:
    path = Path(str(path_text or '').replace('/', os.sep)) if str(path_text or '').strip() else Path()
    return _read_json(path) if path and path.exists() else {}


def _report_path_map(paths: Dict[str, Path]) -> Dict[str, str]:
    return {key: _rel_to_repo(value) if str(value) else '' for key, value in paths.items()}


def run_librarian_access_exchange_probe() -> int:
    run_id = 'librarian-access-exchange-{0}'.format(_utc_stamp())
    run_dir = LIBRARIAN_ACCESS_EXCHANGE_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = LIBRARIAN_ACCESS_EXCHANGE_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='unused-shared-signing-root',
            security_report_title='# Librarian access exchange probe security report\n',
        )
        _seed_probe_project_root(sandbox_root)
        _override_env_vars(
            original_env,
            {
                'CALAMUM_DATA_SIGNING_KEY': None,
                'CALAMUM_REQUESTER_SIGNING_KEY': 'probe-requester-key',
                'CALAMUM_LIBRARIAN_ATTESTATION_KEY': 'probe-librarian-key',
                'CALAMUM_SOURCE_RELEASE_KEY': 'probe-source-key',
                'CALAMUM_LIBRARIAN_VAULT_KEY': 'probe-vault-key',
            },
        )

        artifacts_dir = run_dir / 'artifacts'
        dataset_dir = artifacts_dir / 'datasets' / 'protected_exchange'
        dataset_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = dataset_dir / 'dataset_manifest.json'
        features_csv = dataset_dir / 'features.csv'
        labels_csv = dataset_dir / 'labels.csv'
        features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
        labels_csv.write_text('record_id,label\n1,1\n', encoding='utf-8')
        _write_json(
            manifest_path,
            {
                'features_csv': str(features_csv),
                'labels_csv': str(labels_csv),
                'total_records': 1,
                'has_labels': True,
            },
        )

        command_runs = {
            'register_protected_dataset': _run_observerctl_cli([
                'librarian',
                'dataset',
                'register',
                str(manifest_path),
                '--access-class',
                'protected-source',
                '--display-name',
                'Probe Protected Dataset',
                '--run-id',
                'probe-protected-dataset',
                '--json',
            ]),
            'release_protected_dataset': _run_observerctl_cli([
                'librarian',
                'dataset',
                'release',
                '1',
                '--requester-id',
                'sandbox-probe',
                '--json',
            ]),
        }

        register_packet = command_runs['register_protected_dataset'].get('stdout_json', {}) if isinstance(command_runs['register_protected_dataset'].get('stdout_json', {}), dict) else {}
        release_packet = command_runs['release_protected_dataset'].get('stdout_json', {}) if isinstance(command_runs['release_protected_dataset'].get('stdout_json', {}), dict) else {}
        release_artifacts = dict(release_packet.get('artifacts', {}) or {}) if isinstance(release_packet.get('artifacts', {}), dict) else {}

        request_path = _resolve_probe_artifact_path(sandbox_root, str(release_artifacts.get('dataset_access_request_json', '') or ''))
        attestation_path = _resolve_probe_artifact_path(sandbox_root, str(release_artifacts.get('dataset_access_attestation_json', '') or ''))
        release_receipt_path = _resolve_probe_artifact_path(sandbox_root, str(release_artifacts.get('dataset_access_release_receipt_json', '') or ''))
        baseline_path = _resolve_probe_artifact_path(sandbox_root, str(release_artifacts.get('librarian_vault_baseline_json', '') or ''))
        audit_path = _resolve_probe_artifact_path(sandbox_root, str(release_artifacts.get('librarian_vault_audit_jsonl', '') or ''))

        request_doc = _read_json(request_path) if request_path.exists() else {}
        attestation_doc = _read_json(attestation_path) if attestation_path.exists() else {}
        release_receipt_doc = _read_json(release_receipt_path) if release_receipt_path.exists() else {}

        request_payload = dict(request_doc.get('packet', {}) or {}) if isinstance(request_doc.get('packet', {}), dict) else {}
        attestation_payload = dict(attestation_doc.get('packet', {}) or {}) if isinstance(attestation_doc.get('packet', {}), dict) else {}
        release_receipt_payload = dict(release_receipt_doc.get('packet', {}) or {}) if isinstance(release_receipt_doc.get('packet', {}), dict) else {}

        result_matrix = {
            'protected_dataset_registered': int(command_runs['register_protected_dataset'].get('returncode', 1)) == 0 and str(register_packet.get('action', '')).strip() == 'librarian-dataset-register',
            'protected_dataset_released': int(command_runs['release_protected_dataset'].get('returncode', 1)) == 0 and str(release_packet.get('release_mode', '')).strip() == 'protected-source',
            'shared_signing_root_not_required': not bool(str(os.environ.get('CALAMUM_DATA_SIGNING_KEY', '') or '').strip()),
            'request_signature_verified': verify_detached_payload(
                request_payload,
                dict(request_doc.get('detached_signature', {}) or {}),
                expected_role='requester',
                expected_purpose='dataset_access_request',
            ),
            'attestation_signature_verified': verify_detached_payload(
                attestation_payload,
                dict(attestation_doc.get('detached_signature', {}) or {}),
                expected_role='librarian',
                expected_purpose='dataset_access_attestation',
            ),
            'release_receipt_signature_verified': verify_detached_payload(
                release_receipt_payload,
                dict(release_receipt_doc.get('detached_signature', {}) or {}),
                expected_role='source',
                expected_purpose='dataset_access_release',
            ),
            'delegated_access_projection_written': all(path.exists() for path in [request_path, attestation_path, release_receipt_path]),
            'vault_baseline_written': baseline_path.exists(),
            'vault_audit_written': audit_path.exists(),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(LIBRARIAN_ACCESS_EXCHANGE_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map(
                {
                    'dataset_manifest': manifest_path,
                    'request_packet': request_path,
                    'attestation_packet': attestation_path,
                    'release_receipt': release_receipt_path,
                    'vault_baseline': baseline_path,
                    'vault_audit': audit_path,
                }
            ),
            'artifact_snapshots': {
                'register_packet': register_packet,
                'release_packet': release_packet,
                'request_document': request_doc,
                'attestation_document': attestation_doc,
                'release_receipt_document': release_receipt_doc,
            },
            'result_matrix': result_matrix,
            'findings': {
                'requester_id': str(request_payload.get('requester_id', '') or ''),
                'request_role': str((request_doc.get('detached_signature', {}) or {}).get('role', '') or ''),
                'attestation_role': str((attestation_doc.get('detached_signature', {}) or {}).get('role', '') or ''),
                'release_role': str((release_receipt_doc.get('detached_signature', {}) or {}).get('role', '') or ''),
            },
        }

        report_json = run_dir / 'librarian_access_exchange_probe.json'
        report_md = run_dir / 'librarian_access_exchange_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Librarian Access Exchange Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'requester_id': str(request_payload.get('requester_id', '') or ''),
            },
        )

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_librarian_vault_controls_probe() -> int:
    run_id = 'librarian-vault-controls-{0}'.format(_utc_stamp())
    run_dir = LIBRARIAN_VAULT_CONTROLS_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = LIBRARIAN_VAULT_CONTROLS_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='librarian-vault-controls-signing-key',
            security_report_title='# Librarian vault controls probe security report\n',
        )
        _seed_probe_project_root(sandbox_root)
        _override_env_vars(original_env, {'CALAMUM_LIBRARIAN_VAULT_KEY': 'probe-vault-key'})

        artifacts_dir = run_dir / 'artifacts'
        first_dataset_dir = artifacts_dir / 'datasets' / 'vault_primary'
        second_dataset_dir = artifacts_dir / 'datasets' / 'vault_secondary'
        first_dataset_dir.mkdir(parents=True, exist_ok=True)
        second_dataset_dir.mkdir(parents=True, exist_ok=True)

        first_manifest_path = first_dataset_dir / 'dataset_manifest.json'
        second_manifest_path = second_dataset_dir / 'dataset_manifest.json'
        first_features_csv = first_dataset_dir / 'features.csv'
        second_features_csv = second_dataset_dir / 'features.csv'
        first_features_csv.write_text('record_id,feature\n1,0.1\n', encoding='utf-8')
        second_features_csv.write_text('record_id,feature\n2,0.2\n', encoding='utf-8')
        _write_json(first_manifest_path, {'features_csv': str(first_features_csv), 'total_records': 1, 'has_labels': False})
        _write_json(second_manifest_path, {'features_csv': str(second_features_csv), 'total_records': 1, 'has_labels': False})

        command_runs = {
            'register_seed_dataset': _run_observerctl_cli([
                'librarian',
                'dataset',
                'register',
                str(first_manifest_path),
                '--display-name',
                'Vault Primary Dataset',
                '--run-id',
                'vault-primary',
                '--json',
            ]),
            'vault_status': _run_observerctl_cli(['librarian', 'vault', 'status', '--json']),
            'vault_lock': _run_observerctl_cli(['librarian', 'vault', 'lock', '--reason', 'sandbox-maintenance', '--json']),
            'register_while_locked': _run_observerctl_cli([
                'librarian',
                'dataset',
                'register',
                str(second_manifest_path),
                '--display-name',
                'Vault Secondary Dataset',
                '--run-id',
                'vault-secondary',
                '--json',
            ]),
            'vault_unlock': _run_observerctl_cli(['librarian', 'vault', 'unlock', '--reason', 'sandbox-complete', '--json']),
            'vault_rebaseline': _run_observerctl_cli(['librarian', 'vault', 'rebaseline', '--reason', 'sandbox-refresh', '--json']),
            'vault_verify': _run_observerctl_cli(['librarian', 'vault', 'verify', '--json']),
        }

        status_packet = command_runs['vault_status'].get('stdout_json', {}) if isinstance(command_runs['vault_status'].get('stdout_json', {}), dict) else {}
        lock_packet = command_runs['vault_lock'].get('stdout_json', {}) if isinstance(command_runs['vault_lock'].get('stdout_json', {}), dict) else {}
        locked_register_packet = command_runs['register_while_locked'].get('stdout_json', {}) if isinstance(command_runs['register_while_locked'].get('stdout_json', {}), dict) else {}
        unlock_packet = command_runs['vault_unlock'].get('stdout_json', {}) if isinstance(command_runs['vault_unlock'].get('stdout_json', {}), dict) else {}
        rebaseline_packet = command_runs['vault_rebaseline'].get('stdout_json', {}) if isinstance(command_runs['vault_rebaseline'].get('stdout_json', {}), dict) else {}
        verify_packet = command_runs['vault_verify'].get('stdout_json', {}) if isinstance(command_runs['vault_verify'].get('stdout_json', {}), dict) else {}

        status_artifacts = dict(status_packet.get('artifacts', {}) or {}) if isinstance(status_packet.get('artifacts', {}), dict) else {}
        audit_path = _resolve_probe_artifact_path(sandbox_root, str(status_artifacts.get('librarian_vault_audit_jsonl', '') or ''))
        baseline_path = _resolve_probe_artifact_path(sandbox_root, str(status_artifacts.get('librarian_vault_baseline_json', '') or ''))
        control_state_path = _resolve_probe_artifact_path(sandbox_root, str(status_artifacts.get('librarian_vault_control_state_json', '') or ''))
        control_state = _read_json(control_state_path) if control_state_path.exists() else {}
        audit_rows = _read_jsonl(audit_path)
        audit_actions = [str(row.get('action', '') or '') for row in audit_rows]

        result_matrix = {
            'seed_dataset_registered': int(command_runs['register_seed_dataset'].get('returncode', 1)) == 0,
            'vault_status_reported': int(command_runs['vault_status'].get('returncode', 1)) == 0 and str(status_packet.get('action', '')).strip() == 'librarian-vault-status',
            'vault_lock_succeeded': int(command_runs['vault_lock'].get('returncode', 1)) == 0 and bool(lock_packet.get('locked', False)) is True,
            'locked_register_denied': int(command_runs['register_while_locked'].get('returncode', 0)) != 0 and 'critical_check_failed:librarian_vault_locked' in list(locked_register_packet.get('reason_codes', []) or []),
            'vault_unlock_succeeded': int(command_runs['vault_unlock'].get('returncode', 1)) == 0 and bool(unlock_packet.get('locked', True)) is False,
            'vault_rebaseline_succeeded': int(command_runs['vault_rebaseline'].get('returncode', 1)) == 0 and str(rebaseline_packet.get('action', '')).strip() == 'librarian-vault-rebaseline',
            'vault_verify_succeeded': int(command_runs['vault_verify'].get('returncode', 1)) == 0 and str(verify_packet.get('decision', '')).strip() == 'go',
            'vault_control_state_written': control_state_path.exists() and bool(control_state) and bool(control_state.get('locked', True)) is False,
            'vault_audit_records_control_actions': all(action in audit_actions for action in ['librarian-vault-lock', 'librarian-vault-unlock', 'librarian-vault-rebaseline']) and baseline_path.exists(),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(LIBRARIAN_VAULT_CONTROLS_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map(
                {
                    'seed_manifest': first_manifest_path,
                    'locked_manifest': second_manifest_path,
                    'vault_audit': audit_path,
                    'vault_baseline': baseline_path,
                    'vault_control_state': control_state_path,
                }
            ),
            'artifact_snapshots': {
                'vault_status_packet': status_packet,
                'vault_lock_packet': lock_packet,
                'locked_register_packet': locked_register_packet,
                'vault_unlock_packet': unlock_packet,
                'vault_rebaseline_packet': rebaseline_packet,
                'vault_verify_packet': verify_packet,
                'vault_control_state': control_state,
                'vault_audit_rows': audit_rows,
            },
            'result_matrix': result_matrix,
            'findings': {
                'audit_actions': audit_actions,
                'verify_integrity_status': str(verify_packet.get('integrity_status', '') or ''),
                'locked_reason_codes': list(locked_register_packet.get('reason_codes', []) or []),
            },
        }

        report_json = run_dir / 'librarian_vault_controls_probe.json'
        report_md = run_dir / 'librarian_vault_controls_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Librarian Vault Controls Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'integrity_status': str(verify_packet.get('integrity_status', '') or ''),
            },
        )

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_baseline_monitor_runtime_probe() -> int:
    run_id = 'job0022-baseline-monitor-runtime-{0}'.format(_utc_stamp())
    run_dir = JOB0022_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = JOB0022_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='job0022-probe-signing-key',
            security_report_title='# Job 0022 probe security report\n',
        )
        pid_paths = _seed_runtime_liveness(sandbox_root, log_dir)

        observerctl_module._save_state('sim', 'canary')

        evidence_packet_path = run_dir / 'live_projection_packet.json'

        command_runs = {
            'baseline_monitor_once': _run_observerctl_cli([
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
            ]),
            'baseline_collect_projection_window': _run_observerctl_cli([
                'baseline', 'collect',
                '--source', 'sim',
                '--mode', 'canary',
                '--profile', 'baseline',
                '--duration-sec', '0.2',
                '--interval-sec', '0.05',
                '--window-id', 'job0022_projection_window',
                '--json',
            ]),
            'baseline_analyze_projection_window': _run_observerctl_cli([
                'baseline', 'analyze',
                '--source', 'sim',
                '--mode', 'canary',
                '--hours', '1',
                '--min-normal-samples', '1',
                '--min-baseline-samples', '1',
                '--json',
            ]),
            'live_projection_evidence_pack': _run_observerctl_cli([
                'ops', 'evidence', 'pack',
                '--source', 'sim',
                '--to', 'live',
                '--event', 'job0022-next-bite',
                '--output', str(evidence_packet_path),
                '--json',
            ]),
        }

        paths = {
            'monitor_state': log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json',
            'watchdog_posture': log_dir / 'control' / 'calamum' / 'watchdog_posture_state.json',
            'watchdog_resource': log_dir / 'control' / 'calamum' / 'watchdog_resource_state.json',
            'resource_index': log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'resource' / 'index.jsonl',
            'evidence_index': log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl',
            'analysis_packet': Path(),
            'evidence_output': evidence_packet_path,
        }

        monitor_state = _read_json(paths['monitor_state']) if paths['monitor_state'].exists() else {}
        resource_latest = _read_jsonl_last(paths['resource_index'])
        resource_normal_latest = _read_jsonl_latest_matching(paths['resource_index'], 'stream_type', 'resource_normal')
        evidence_latest = _read_jsonl_last(paths['evidence_index'])
        analysis_packet_ref = str(monitor_state.get('last_analysis_packet_path', '') or '').strip()
        if analysis_packet_ref:
            paths['analysis_packet'] = Path(analysis_packet_ref.replace('/', os.sep))

        evidence_packet = _read_json(evidence_packet_path) if evidence_packet_path.exists() else {}
        latest_segment_path = Path(str(resource_normal_latest.get('segment_path', '') or '').replace('/', os.sep)) if resource_normal_latest else Path()
        objective_matrix = _objective_matrix(
            evidence_packet=evidence_packet,
            monitor_state=monitor_state,
            resource_latest=resource_latest,
            resource_normal_latest=resource_normal_latest,
            segment_exists=bool(latest_segment_path and latest_segment_path.exists()),
        )
        representation_matrix = _representation_matrix(
            evidence_packet=evidence_packet,
            paths=paths,
            monitor_state=monitor_state,
            resource_latest=resource_latest,
        )
        stage5 = evidence_packet.get('stage5_prerequisites', {}) if isinstance(evidence_packet.get('stage5_prerequisites', {}), dict) else {}
        remaining_gaps = {
            'C22_baseline_validation_rate_escalated': stage5.get('C22_baseline_validation_rate_escalated', {}),
            'C24_resource_stream_retention_ready': stage5.get('C24_resource_stream_retention_ready', {}),
            'C25_resource_baseline_window_ready': stage5.get('C25_resource_baseline_window_ready', {}),
            'baseline_monitor_runtime_ready': stage5.get('baseline_monitor_runtime_ready', {}),
            'overall': stage5.get('overall', {}),
        }

        next_bite_result = 'pass' if all(objective_matrix.values()) else 'review'
        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(JOB0022_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': next_bite_result,
            'bite_scope': {
                'job': 'CALAMUM_JOB_0022_MOLTBOOK_BASELINE_INTEGRATION_20260220',
                'focus': 'baseline monitor runtime liveness plus resource_normal retention continuity',
                'non_goals': [
                    'live activation',
                    'broad observerctl refactor',
                    'final Stage 5 closure',
                ],
            },
            'sandbox': {
                'sandbox_root': _rel_to_repo(sandbox_root),
                'sandbox_log_dir': _rel_to_repo(log_dir),
                'pid_paths': pid_paths,
                'security_report_ref': _rel_to_repo(run_dir / 'security_report.md'),
            },
            'command_runs': command_runs,
            'artifact_paths': {key: _rel_to_repo(value) if str(value) else '' for key, value in paths.items()},
            'artifact_snapshots': {
                'monitor_state': monitor_state,
                'watchdog_posture_state': _read_json(paths['watchdog_posture']) if paths['watchdog_posture'].exists() else {},
                'watchdog_resource_state': _read_json(paths['watchdog_resource']) if paths['watchdog_resource'].exists() else {},
                'resource_index_latest': resource_latest,
                'resource_index_latest_normal': resource_normal_latest,
                'resource_segment_exists': bool(latest_segment_path and latest_segment_path.exists()),
                'evidence_index_latest': evidence_latest,
                'evidence_packet': evidence_packet,
            },
            'objective_matrix': objective_matrix,
            'representation_matrix': representation_matrix,
            'remaining_gaps': remaining_gaps,
        }

        report_json = run_dir / 'job0022_baseline_monitor_runtime_probe.json'
        report_md = run_dir / 'job0022_baseline_monitor_runtime_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_baseline_monitor_runtime_markdown(report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': next_bite_result,
            'objective_pass_count': sum(1 for value in objective_matrix.values() if value),
            'objective_total': len(objective_matrix),
        })

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(next_bite_result))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_validation_cycle_lineage_probe() -> int:
    run_id = 'frame5-validation-cycle-lineage-{0}'.format(_utc_stamp())
    run_dir = FRAME5_LINEAGE_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAME5_LINEAGE_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        _sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frame5-lineage-probe-signing-key',
            security_report_title='# Frame 5 validation-cycle lineage probe security report\n',
        )
        observerctl_module._save_state('sim', 'live')

        command_runs = {
            'cycle_a': _run_observerctl_cli([
                'baseline', 'monitor-once',
                '--source', 'sim',
                '--mode', 'live',
                '--normal-interval-sec', '0.01',
                '--baseline-interval-sec', '0.01',
                '--baseline-window-sec', '0.2',
                '--baseline-sample-interval-sec', '0.05',
                '--min-normal-samples', '1',
                '--min-baseline-samples', '1',
                '--json',
            ]),
        }
        time.sleep(1.05)
        command_runs['cycle_b'] = _run_observerctl_cli([
            'baseline', 'monitor-once',
            '--source', 'sim',
            '--mode', 'live',
            '--normal-interval-sec', '0.01',
            '--baseline-interval-sec', '0.01',
            '--baseline-window-sec', '0.2',
            '--baseline-sample-interval-sec', '0.05',
            '--min-normal-samples', '1',
            '--min-baseline-samples', '1',
            '--json',
        ])

        evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'live' / 'evidence' / 'index.jsonl'
        cycle_rows = _read_jsonl_rows_for_event(evidence_index, 'baseline_monitor_cycle')
        first_cycle_path = _command_stdout_path(command_runs['cycle_a'], 'validation_cycle_packet_path')
        second_cycle_path = _command_stdout_path(command_runs['cycle_b'], 'validation_cycle_packet_path')
        first_cycle_doc = _json_from_text_path(first_cycle_path)
        second_cycle_doc = _json_from_text_path(second_cycle_path)
        second_continuity = second_cycle_doc.get('continuity', {}) if isinstance(second_cycle_doc.get('continuity', {}), dict) else {}
        second_process = second_cycle_doc.get('process', {}) if isinstance(second_cycle_doc.get('process', {}), dict) else {}
        latest_cycle_row = cycle_rows[-1] if cycle_rows else {}

        result_matrix = {
            'two_cycle_rows_present': len(cycle_rows) >= 2,
            'cycle_packet_paths_distinct': bool(first_cycle_path and second_cycle_path and first_cycle_path != second_cycle_path),
            'latest_cycle_links_previous_validation': str((second_continuity.get('previous_validation_cycle') or {}).get('packet_path', '') or '') == first_cycle_path,
            'latest_cycle_links_previous_baseline': str((second_continuity.get('previous_baseline') or {}).get('packet_path', '') or '') == str(first_cycle_doc.get('baseline_packet_path', '') or ''),
            'latest_cycle_links_previous_analysis': str(second_continuity.get('previous_analysis_packet_path', '') or '') == str(first_cycle_doc.get('analysis_packet_path', '') or ''),
            'latest_cycle_process_refs_include_prior_cycle': first_cycle_path in list(second_process.get('evidence_refs', []) or []),
            'latest_cycle_has_current_baseline_analysis_refs': bool(second_cycle_doc.get('baseline_packet_path') and second_cycle_doc.get('analysis_packet_path')),
            'evidence_index_latest_matches_latest_cycle': str(latest_cycle_row.get('packet_path', '') or '') == second_cycle_path,
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAME5_LINEAGE_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map({
                'evidence_index': evidence_index,
                'first_cycle_packet': Path(first_cycle_path.replace('/', os.sep)) if first_cycle_path else Path(),
                'second_cycle_packet': Path(second_cycle_path.replace('/', os.sep)) if second_cycle_path else Path(),
                'monitor_state': log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json',
            }),
            'artifact_snapshots': {
                'cycle_rows': cycle_rows,
                'first_cycle_packet': first_cycle_doc,
                'second_cycle_packet': second_cycle_doc,
            },
            'result_matrix': result_matrix,
            'findings': {
                'cycle_row_count': len(cycle_rows),
                'first_cycle_baseline_packet_path': str(first_cycle_doc.get('baseline_packet_path', '') or ''),
                'first_cycle_analysis_packet_path': str(first_cycle_doc.get('analysis_packet_path', '') or ''),
                'second_cycle_previous_validation': second_continuity.get('previous_validation_cycle', {}),
                'second_cycle_previous_baseline': second_continuity.get('previous_baseline', {}),
            },
        }

        report_json = run_dir / 'frame5_validation_cycle_lineage_probe.json'
        report_md = run_dir / 'frame5_validation_cycle_lineage_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame 5 Validation Cycle Lineage Probe', report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': report['next_bite_result'],
            'cycle_row_count': len(cycle_rows),
        })

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_baseline_monitor_restart_continuity_probe() -> int:
    run_id = 'frame6-restart-continuity-{0}'.format(_utc_stamp())
    run_dir = FRAME6_RESTART_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAME6_RESTART_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        _sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frame6-restart-probe-signing-key',
            security_report_title='# Frame 6 restart continuity probe security report\n',
        )
        observerctl_module._save_state('sim', 'live')

        command_runs = {
            'seed_cycle': _run_observerctl_cli([
                'baseline', 'monitor-once',
                '--source', 'sim',
                '--mode', 'live',
                '--normal-interval-sec', '0.01',
                '--baseline-interval-sec', '0.01',
                '--baseline-window-sec', '0.2',
                '--baseline-sample-interval-sec', '0.05',
                '--min-normal-samples', '1',
                '--min-baseline-samples', '1',
                '--json',
            ]),
            'resume_cycle': _run_observerctl_cli([
                'baseline', 'monitor-once',
                '--source', 'sim',
                '--mode', 'live',
                '--normal-interval-sec', '999',
                '--baseline-interval-sec', '999',
                '--baseline-window-sec', '0.2',
                '--baseline-sample-interval-sec', '0.05',
                '--min-normal-samples', '1',
                '--min-baseline-samples', '1',
                '--json',
            ]),
        }

        monitor_state_path = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
        resumed_cycle_path = _command_stdout_path(command_runs['resume_cycle'], 'validation_cycle_packet_path')
        resumed_cycle_doc = _json_from_text_path(resumed_cycle_path)
        final_monitor_state = _read_json(monitor_state_path) if monitor_state_path.exists() else {}

        seed_cycle_path = _command_stdout_path(command_runs['seed_cycle'], 'validation_cycle_packet_path')
        seed_cycle_doc = _json_from_text_path(seed_cycle_path)
        continuity = resumed_cycle_doc.get('continuity', {}) if isinstance(resumed_cycle_doc.get('continuity', {}), dict) else {}
        previous_validation = continuity.get('previous_validation_cycle', {}) if isinstance(continuity.get('previous_validation_cycle', {}), dict) else {}
        previous_baseline = continuity.get('previous_baseline', {}) if isinstance(continuity.get('previous_baseline', {}), dict) else {}

        result_matrix = {
            'continuity_state_preserved': str(continuity.get('state', '')).strip().lower() == 'preserved',
            'previous_validation_cycle_retained': str(previous_validation.get('packet_path', '') or '') == seed_cycle_path,
            'previous_baseline_packet_retained': str(previous_baseline.get('packet_path', '') or '') == str(seed_cycle_doc.get('baseline_packet_path', '') or ''),
            'previous_analysis_packet_retained': str(continuity.get('previous_analysis_packet_path', '') or '') == str(seed_cycle_doc.get('analysis_packet_path', '') or ''),
            'previous_baseline_window_id_retained': str(previous_baseline.get('window_id', '') or '') == str(seed_cycle_doc.get('baseline_window_id', '') or ''),
            'resume_cycle_suppressed_new_baseline_artifact': str(resumed_cycle_doc.get('baseline_packet_path', '') or '') == '',
            'resume_cycle_suppressed_new_analysis_artifact': str(resumed_cycle_doc.get('analysis_packet_path', '') or '') == '',
            'final_state_retains_anchor_paths': str(final_monitor_state.get('last_baseline_packet_path', '') or '') == str(seed_cycle_doc.get('baseline_packet_path', '') or ''),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAME6_RESTART_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map({
                'monitor_state': monitor_state_path,
                'seed_cycle_packet': Path(seed_cycle_path.replace('/', os.sep)) if seed_cycle_path else Path(),
                'resume_cycle_packet': Path(resumed_cycle_path.replace('/', os.sep)) if resumed_cycle_path else Path(),
            }),
            'artifact_snapshots': {
                'seed_cycle_packet': seed_cycle_doc,
                'resume_cycle_packet': resumed_cycle_doc,
                'monitor_state': final_monitor_state,
            },
            'result_matrix': result_matrix,
            'findings': {
                'resume_continuity': continuity,
                'seed_baseline_window_id': str(seed_cycle_doc.get('baseline_window_id', '') or ''),
                'final_monitor_anchor_paths': {
                    'last_baseline_packet_path': str(final_monitor_state.get('last_baseline_packet_path', '') or ''),
                    'last_analysis_packet_path': str(final_monitor_state.get('last_analysis_packet_path', '') or ''),
                    'last_baseline_window_id': str(final_monitor_state.get('last_baseline_window_id', '') or ''),
                },
            },
        }

        report_json = run_dir / 'frame6_restart_continuity_probe.json'
        report_md = run_dir / 'frame6_restart_continuity_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame 6 Restart Continuity Probe', report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': report['next_bite_result'],
            'continuity_state': str(continuity.get('state', '') or ''),
        })

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def run_baseline_monitor_state_recovery_probe() -> int:
    run_id = 'frame6-state-recovery-{0}'.format(_utc_stamp())
    run_dir = FRAME6_RECOVERY_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAME6_RECOVERY_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        _sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frame6-recovery-probe-signing-key',
            security_report_title='# Frame 6 state recovery probe security report\n',
        )
        observerctl_module._save_state('sim', 'canary')

        monitor_state_path = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
        malformed_state = {
            'last_normal_sample_epoch_s': 'not-a-float',
            'last_validation_cycle_packet_path': 123,
            'last_validation_cycle_at_utc': 'definitely-not-utc',
            'last_baseline_packet_path': 456,
        }
        _write_json(monitor_state_path, malformed_state)

        command_runs = {
            'recovery_cycle': _run_observerctl_cli([
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
            ]),
        }

        cycle_packet_path = _command_stdout_path(command_runs['recovery_cycle'], 'validation_cycle_packet_path')
        cycle_packet = _json_from_text_path(cycle_packet_path)
        repaired_state = _read_json(monitor_state_path) if monitor_state_path.exists() else {}
        continuity = cycle_packet.get('continuity', {}) if isinstance(cycle_packet.get('continuity', {}), dict) else {}
        previous_validation = continuity.get('previous_validation_cycle', {}) if isinstance(continuity.get('previous_validation_cycle', {}), dict) else {}

        result_matrix = {
            'continuity_marked_degraded': str(continuity.get('state', '')).strip().lower() == 'degraded',
            'malformed_reason_code_emitted': 'major_check_failed:baseline_monitor_state_malformed' in list(continuity.get('reason_codes', []) or []),
            'detail_codes_present': bool(list(continuity.get('detail_codes', []) or [])),
            'previous_validation_path_stringified': str(previous_validation.get('packet_path', '') or '') == '123',
            'repaired_numeric_anchor_normalized': isinstance(repaired_state.get('last_normal_sample_epoch_s'), (int, float)),
            'repaired_text_anchor_preserved': str(repaired_state.get('last_baseline_packet_path', '') or '') == '456',
            'new_cycle_written_back': bool(str(repaired_state.get('last_validation_cycle_packet_path', '') or '').strip()),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAME6_RECOVERY_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map({
                'monitor_state': monitor_state_path,
                'cycle_packet': Path(cycle_packet_path.replace('/', os.sep)) if cycle_packet_path else Path(),
                'evidence_index': log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl',
            }),
            'artifact_snapshots': {
                'malformed_state_seed': malformed_state,
                'cycle_packet': cycle_packet,
                'repaired_state': repaired_state,
            },
            'result_matrix': result_matrix,
            'findings': {
                'continuity': continuity,
                'repaired_state_anchor_subset': {
                    'last_normal_sample_epoch_s': repaired_state.get('last_normal_sample_epoch_s'),
                    'last_baseline_packet_path': repaired_state.get('last_baseline_packet_path'),
                    'last_validation_cycle_packet_path': repaired_state.get('last_validation_cycle_packet_path'),
                },
            },
        }

        report_json = run_dir / 'frame6_state_recovery_probe.json'
        report_md = run_dir / 'frame6_state_recovery_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame 6 State Recovery Probe', report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': report['next_bite_result'],
            'continuity_state': str(continuity.get('state', '') or ''),
        })

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_project_root is not None:
            _restore_probe_environment(original_env, original_project_root)


def _definition_registry() -> Dict[str, Callable[[], int]]:
    return {
        'feedback-loop': run_feedback_loop_simulation,
        'metadata-contract': run_metadata_contract_probe,
        'metadata-contract-regression': run_metadata_contract_regression_probe,
        'ds-wizard-hydration': run_ds_wizard_hydration_probe,
        'ds-wizard-stale-state-continuity': run_ds_wizard_stale_state_continuity_probe,
        'ds-wizard-durability': run_ds_wizard_durability_probe,
        'ds-wizard-labeled-eval-contract-coherence': run_ds_wizard_labeled_eval_contract_coherence_probe,
        'ds-wizard-blocked-execute-truthfulness': run_ds_wizard_blocked_execute_truthfulness_probe,
        'ds-wizard-execute-failure-truthfulness': run_ds_wizard_execute_failure_truthfulness_probe,
        'ds-alias-coherence': run_ds_alias_coherence_probe,
        'baseline-monitor-runtime': run_baseline_monitor_runtime_probe,
        'validation-cycle-lineage': run_validation_cycle_lineage_probe,
        'baseline-monitor-restart-continuity': run_baseline_monitor_restart_continuity_probe,
        'baseline-monitor-state-recovery': run_baseline_monitor_state_recovery_probe,
        'librarian-access-exchange': run_librarian_access_exchange_probe,
        'librarian-vault-controls': run_librarian_vault_controls_probe,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run Calamum simulation or sandbox validation definitions.')
    parser.add_argument(
        'definition',
        nargs='?',
        default='feedback-loop',
        help='Definition to run: feedback-loop, metadata-contract, metadata-contract-regression, ds-wizard-hydration, ds-wizard-stale-state-continuity, ds-wizard-durability, ds-wizard-labeled-eval-contract-coherence, ds-wizard-blocked-execute-truthfulness, ds-wizard-execute-failure-truthfulness, ds-alias-coherence, baseline-monitor-runtime, validation-cycle-lineage, baseline-monitor-restart-continuity, baseline-monitor-state-recovery, librarian-access-exchange, librarian-vault-controls',
    )
    parser.add_argument(
        '--list-definitions',
        action='store_true',
        help='List available simulation/sandbox definitions and exit.',
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    registry = _definition_registry()

    if args.list_definitions:
        for name in [
            'feedback-loop',
            'metadata-contract',
            'metadata-contract-regression',
            'ds-wizard-hydration',
            'ds-wizard-stale-state-continuity',
            'ds-wizard-durability',
            'ds-wizard-labeled-eval-contract-coherence',
            'ds-wizard-blocked-execute-truthfulness',
            'ds-wizard-execute-failure-truthfulness',
            'ds-alias-coherence',
            'baseline-monitor-runtime',
            'validation-cycle-lineage',
            'baseline-monitor-restart-continuity',
            'baseline-monitor-state-recovery',
            'librarian-access-exchange',
            'librarian-vault-controls',
        ]:
            print(name)
        return 0

    definition = str(args.definition).strip().lower()
    runner = registry.get(definition)
    if runner is None:
        parser.error('unknown definition: {0}'.format(args.definition))
    return int(runner())


if __name__ == '__main__':
    raise SystemExit(main())
