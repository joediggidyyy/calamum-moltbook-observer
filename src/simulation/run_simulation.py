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
import observerctl as observerctl_module


FRAME4_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame4_metadata_contract_probe'
FRAME4_REGRESSION_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame4_metadata_contract_regression_probe'
JOB0022_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'job0022_baseline_monitor_runtime_probe'
FRAME5_LINEAGE_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame5_validation_cycle_lineage_probe'
FRAME6_RESTART_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame6_restart_continuity_probe'
FRAME6_RECOVERY_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frame6_state_recovery_probe'


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


def _touch(path: Path, content: str = '{"status":"ok"}\n') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def _write_pid(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding='utf-8')


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
        'baseline-monitor-runtime': run_baseline_monitor_runtime_probe,
        'validation-cycle-lineage': run_validation_cycle_lineage_probe,
        'baseline-monitor-restart-continuity': run_baseline_monitor_restart_continuity_probe,
        'baseline-monitor-state-recovery': run_baseline_monitor_state_recovery_probe,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run Calamum simulation or sandbox validation definitions.')
    parser.add_argument(
        'definition',
        nargs='?',
        default='feedback-loop',
        help='Definition to run: feedback-loop, metadata-contract, metadata-contract-regression, baseline-monitor-runtime, validation-cycle-lineage, baseline-monitor-restart-continuity, baseline-monitor-state-recovery',
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
            'baseline-monitor-runtime',
            'validation-cycle-lineage',
            'baseline-monitor-restart-continuity',
            'baseline-monitor-state-recovery',
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
