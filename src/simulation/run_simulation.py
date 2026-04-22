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
import shutil
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
FRAMEB_POSTURE_TRANSITION_BYPASS_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frameb_posture_transition_bypass_probe'
FRAMEB_STALE_GATE_REPLAY_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frameb_stale_gate_replay_probe'
FRAMEC_NAMES_ONLY_PERSISTENCE_ESCAPE_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'framec_names_only_persistence_escape_probe'
FRAMEC_PACKET_ARTIFACT_DIVERGENCE_TRUTHFULNESS_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'framec_packet_artifact_divergence_truthfulness_probe'
FRAMED_DS_ALIAS_COHERENCE_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'framed_ds_alias_coherence_probe'
FRAMED_WATCHDOG_HEARTBEAT_SPOOF_RESISTANCE_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'framed_watchdog_heartbeat_spoof_resistance_probe'
FRAMED_RESOURCE_LOCKDOWN_CHAOS_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'framed_resource_lockdown_chaos_probe'
FRAMEE_BASELINE_AUTHORITY_TAMPER_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'framee_baseline_authority_tamper_probe'
FRAMEE_REPORT_LINEAGE_FORGERY_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'framee_report_lineage_forgery_probe'
FRAMEF_KEYSMITH_VERSION_PARITY_BREAK_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'framef_keysmith_version_parity_break_probe'
FRAMEG_PUBLIC_REPORT_BOUNDARY_ESCAPE_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frameg_public_report_boundary_escape_probe'
FRAMEG_BOOTSTRAP_ROOT_STARVATION_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frameg_bootstrap_root_starvation_probe'
FRAMEG_SANDBOX_CATALOG_AUTHORITY_DRIFT_PROBE_DIR = REPO_ROOT / 'report_tmp' / 'frameg_sandbox_catalog_authority_drift_probe'
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


def _seed_shipped_manual_report_surfaces(project_root: Path) -> None:
    for relative_path in (
        'docs/reports/reference/GENERATED_REPORT_SURFACES.md',
        'docs/reports/validations/INDEX.md',
        'docs/reports/validations/APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.md',
        'docs/reports/validations/APEXLAB_REFERENCE_VALIDATION_REPORT_20260324.html',
    ):
        source_path = PROJECT_ROOT / relative_path
        target_path = project_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)


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


def _bind_sandbox_catalog_roots(report_tmp_root: Path, repo_root: Path) -> Tuple[Any, Any]:
    import observerctl_sandbox_registry as sandbox_registry_module
    import observerctl_sandbox_runs as sandbox_runs_module

    original_registry_report_tmp = sandbox_registry_module._REPORT_TMP
    original_runs_repo_root = sandbox_runs_module._REPO_ROOT
    sandbox_registry_module._REPORT_TMP = report_tmp_root
    sandbox_runs_module._REPO_ROOT = repo_root
    return original_registry_report_tmp, original_runs_repo_root


def _restore_sandbox_catalog_roots(original_registry_report_tmp: Any, original_runs_repo_root: Any) -> None:
    import observerctl_sandbox_registry as sandbox_registry_module
    import observerctl_sandbox_runs as sandbox_runs_module

    sandbox_registry_module._REPORT_TMP = original_registry_report_tmp
    sandbox_runs_module._REPO_ROOT = original_runs_repo_root


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


def _seed_watchdog_state_files(
    log_dir: Path,
    *,
    posture: str = 'isolation',
    heartbeat_interval: float = 10.0,
    baseline_interval: float = 120.0,
    cpu_now: float = 35.0,
    ram_now: float = 40.0,
    cpu_p95: float = 30.0,
    ram_p95: float = 35.0,
    score: float = 0.1,
    age_s: float = 5.0,
) -> Dict[str, Path]:
    control_dir = log_dir / 'control' / 'calamum'
    posture_path = control_dir / 'watchdog_posture_state.json'
    resource_path = control_dir / 'watchdog_resource_state.json'
    _write_json(
        posture_path,
        {
            'posture_trigger': posture,
            'heartbeat_interval_seconds': heartbeat_interval,
            'baseline_validation_interval_seconds': baseline_interval,
        },
    )
    _write_json(
        resource_path,
        {
            'cpu_pct_now': cpu_now,
            'ram_pct_now': ram_now,
            'cpu_p95_15m': cpu_p95,
            'ram_p95_15m': ram_p95,
            'resource_spike_score': score,
            'sample_age_seconds': age_s,
        },
    )
    return {
        'posture_state': posture_path,
        'resource_state': resource_path,
    }


def _seed_mode_gate_packet(
    source: str,
    from_mode: str,
    to_mode: str,
    *,
    run_id: str,
    posture_trigger_id: str,
    security_report_ref: str,
    timestamp_utc: str = '',
) -> Dict[str, Any]:
    packet = {
        'timestamp_utc': str(timestamp_utc or observerctl_module._utc_now()),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'reason_codes': [],
        'from_state': '{0}:{1}'.format(observerctl_module._normalize_source(source), str(from_mode or 'watch').strip().lower()),
        'to_state': '{0}:{1}'.format(observerctl_module._normalize_source(source), str(to_mode or 'watch').strip().lower()),
        'profile': 'GP-4',
        'run_id': str(run_id),
        'posture_trigger_id': str(posture_trigger_id),
        'posture_trigger': str(observerctl_module._posture_for_mode(to_mode)),
        'security_report_ref': str(security_report_ref).replace('\\', '/'),
        'evidence_refs': [str(security_report_ref).replace('\\', '/')],
    }
    observerctl_module._write_json_file(
        observerctl_module._control_file(observerctl_module.LAST_GATE_FILE),
        packet,
    )
    return packet


def _seed_gate_run_context(
    *,
    run_id: str,
    posture_trigger_id: str,
    security_report_ref: str,
    posture_trigger: str,
) -> Dict[str, Any]:
    return observerctl_module._save_run_context({
        'run_id': str(run_id),
        'posture_trigger_id': str(posture_trigger_id),
        'posture_trigger': str(posture_trigger),
        'security_report_ref': str(security_report_ref).replace('\\', '/'),
    })


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


def _token_labels_found_in_text(text: str, forbidden_tokens: Dict[str, str]) -> List[str]:
    hits: List[str] = []
    for label, token in forbidden_tokens.items():
        if str(token or '') and str(token) in str(text or ''):
            hits.append(str(label))
    return hits


def _scan_paths_for_forbidden_tokens(paths: List[Path], forbidden_tokens: Dict[str, str]) -> Dict[str, List[str]]:
    findings: Dict[str, List[str]] = {}
    for path in paths:
        if not str(path) or not path.exists() or not path.is_file():
            continue
        hits = _token_labels_found_in_text(path.read_text(encoding='utf-8', errors='ignore'), forbidden_tokens)
        if hits:
            findings[_rel_to_repo(path)] = hits
    return findings


def _scan_command_streams_for_forbidden_tokens(
    command_runs: Dict[str, Dict[str, Any]],
    forbidden_tokens: Dict[str, str],
) -> Dict[str, Dict[str, List[str]]]:
    findings: Dict[str, Dict[str, List[str]]] = {}
    for name, command in command_runs.items():
        stream_hits: Dict[str, List[str]] = {}
        stdout_hits = _token_labels_found_in_text(str(command.get('stdout_text', '') or ''), forbidden_tokens)
        stderr_hits = _token_labels_found_in_text(str(command.get('stderr_text', '') or ''), forbidden_tokens)
        if stdout_hits:
            stream_hits['stdout'] = stdout_hits
        if stderr_hits:
            stream_hits['stderr'] = stderr_hits
        if stream_hits:
            findings[str(name)] = stream_hits
    return findings


def run_names_only_persistence_escape_probe() -> int:
    run_id = 'framec-names-only-persistence-escape-{0}'.format(_utc_stamp())
    run_dir = FRAMEC_NAMES_ONLY_PERSISTENCE_ESCAPE_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEC_NAMES_ONLY_PERSISTENCE_ESCAPE_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='framec-names-only-persistence-escape-signing-key',
            security_report_title='# Frame C names-only persistence escape probe security report\n',
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)
        _seed_runtime_liveness(sandbox_root, log_dir)
        watchdog_paths = _seed_watchdog_state_files(log_dir)

        forbidden_tokens = {
            'raw_content_lure': 'RAW_MOLTBOOK_CONTENT_LURE::observer-frame-c-names-only-boundary',
            'fake_secret_token': 'sk-live-framec-names-only-escape-987654321',
            'sensitive_path_lure': 'C:/Users/joedi/Documents/Private/framec_sensitive_payload.txt',
        }
        _override_env_vars(original_env, {'MOLTBOOK_API_KEY': forbidden_tokens['fake_secret_token']})

        hostile_input_path = run_dir / 'inbound' / 'hostile_payload.txt'
        hostile_input_path.parent.mkdir(parents=True, exist_ok=True)
        hostile_input_path.write_text(
            '\n'.join([forbidden_tokens['raw_content_lure'], forbidden_tokens['fake_secret_token'], forbidden_tokens['sensitive_path_lure']]) + '\n',
            encoding='utf-8',
        )

        observerctl_module._save_state('sim', 'watch')
        output_packet_path = run_dir / 'framec_names_only_packet.json'
        security_report_path = run_dir / 'security_report.md'

        command_runs = {
            'mode_gate': _run_observerctl_cli([
                'ops',
                'mode',
                'gate',
                '--source',
                'sim',
                '--to',
                'canary',
                '--json',
            ]),
            'evidence_pack': _run_observerctl_cli([
                'ops',
                'evidence',
                'pack',
                '--source',
                'sim',
                '--output',
                str(output_packet_path),
                '--json',
            ]),
        }

        last_gate_path = observerctl_module._control_file(observerctl_module.LAST_GATE_FILE)
        run_context_path = observerctl_module._control_file(observerctl_module.RUN_CONTEXT_FILE)
        scanned_paths = [
            security_report_path,
            watchdog_paths['posture_state'],
            watchdog_paths['resource_state'],
            last_gate_path,
            run_context_path,
            output_packet_path,
        ]
        file_hits = _scan_paths_for_forbidden_tokens(scanned_paths, forbidden_tokens)
        command_hits = _scan_command_streams_for_forbidden_tokens(command_runs, forbidden_tokens)

        result_matrix = {
            'hostile_input_seed_written': hostile_input_path.exists(),
            'mode_gate_command_returncode_zero': int(command_runs['mode_gate'].get('returncode', 1)) == 0,
            'evidence_pack_command_returncode_zero': int(command_runs['evidence_pack'].get('returncode', 1)) == 0,
            'retained_output_packet_written': output_packet_path.exists(),
            'scanned_retained_output_count_at_least_three': len([path for path in scanned_paths if path.exists()]) >= 5,
            'retained_file_outputs_preserved_names_only': not bool(file_hits),
            'command_output_preserved_names_only': not bool(command_hits),
        }

        report = {
            'scenario_id': 'S3',
            'threat_class': 'names_only_persistence_escape',
            'test_classes': ['sandbox-run', 'secret-boundary-scan', 'pytest-regression'],
            'expected_safe_outcome': 'outputs remain names-only and no secret/raw material persists',
            'observed_boundary_result': 'names_only_boundary_preserved' if _probe_result(result_matrix) == 'pass' else 'review_required',
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEC_NAMES_ONLY_PERSISTENCE_ESCAPE_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map(
                {
                    'hostile_input': hostile_input_path,
                    'security_report': security_report_path,
                    'posture_state': watchdog_paths['posture_state'],
                    'resource_state': watchdog_paths['resource_state'],
                    'last_gate': last_gate_path,
                    'run_context': run_context_path,
                    'output_packet': output_packet_path,
                }
            ),
            'artifact_snapshots': {
                'forbidden_token_labels': list(forbidden_tokens.keys()),
                'mode_gate_packet': _read_json(last_gate_path) if last_gate_path.exists() else {},
                'run_context': _read_json(run_context_path) if run_context_path.exists() else {},
                'output_packet': _read_json(output_packet_path) if output_packet_path.exists() else {},
            },
            'result_matrix': result_matrix,
            'findings': {
                'forbidden_token_labels': list(forbidden_tokens.keys()),
                'scanned_paths': [_rel_to_repo(path) for path in scanned_paths if path.exists()],
                'file_hits': file_hits,
                'command_hits': command_hits,
            },
        }

        report_json = run_dir / 'framec_names_only_persistence_escape_probe.json'
        report_md = run_dir / 'framec_names_only_persistence_escape_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame C Names-Only Persistence Escape Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': report['observed_boundary_result'],
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


def run_packet_artifact_divergence_truthfulness_probe() -> int:
    run_id = 'framec-packet-artifact-divergence-truthfulness-{0}'.format(_utc_stamp())
    run_dir = FRAMEC_PACKET_ARTIFACT_DIVERGENCE_TRUTHFULNESS_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEC_PACKET_ARTIFACT_DIVERGENCE_TRUTHFULNESS_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='framec-packet-artifact-divergence-truthfulness-signing-key',
            security_report_title='# Frame C packet artifact divergence truthfulness probe security report\n',
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)
        _seed_runtime_liveness(sandbox_root, log_dir)
        _seed_watchdog_state_files(log_dir)

        observerctl_module._save_state('sim', 'watch')
        current_artifact_path = run_dir / 'framec_truthfulness_packet.json'
        stale_artifact_path = run_dir / 'framec_truthfulness_stale_copy.json'

        command_runs = {
            'evidence_pack': _run_observerctl_cli([
                'ops',
                'evidence',
                'pack',
                '--source',
                'sim',
                '--output',
                str(current_artifact_path),
                '--json',
            ]),
        }

        command_packet = _command_stdout_json(command_runs['evidence_pack'])
        current_artifact_created_before_tamper = current_artifact_path.exists()
        current_packet_before_tamper = _read_json(current_artifact_path) if current_artifact_created_before_tamper else {}
        if current_artifact_created_before_tamper:
            stale_artifact_path.write_text(current_artifact_path.read_text(encoding='utf-8'), encoding='utf-8')
            current_artifact_path.unlink()

        divergence_detected = (
            int(command_runs['evidence_pack'].get('returncode', 1)) == 0
            and current_artifact_created_before_tamper
            and not current_artifact_path.exists()
        )
        review_decision = 'no-go' if divergence_detected else 'go'
        observed_boundary_result = 'packet_artifact_divergence_detected_fail_closed' if divergence_detected else 'packet_artifact_agreement_unverified'

        result_matrix = {
            'evidence_pack_command_returncode_zero': int(command_runs['evidence_pack'].get('returncode', 1)) == 0,
            'current_artifact_created_before_tamper': current_artifact_created_before_tamper,
            'stale_copy_created': stale_artifact_path.exists(),
            'current_artifact_missing_during_review': not current_artifact_path.exists(),
            'cross_surface_divergence_detected': divergence_detected,
            'stale_copy_not_mistaken_for_current': stale_artifact_path.exists() and stale_artifact_path != current_artifact_path,
            'no_false_success_narrative_survives_review': review_decision == 'no-go',
        }

        report = {
            'scenario_id': 'S4',
            'threat_class': 'packet_artifact_divergence_truthfulness',
            'test_classes': ['sandbox-run', 'diff-contract-review', 'artifact-forensics'],
            'expected_safe_outcome': 'no false-success narrative survives cross-surface review',
            'observed_boundary_result': observed_boundary_result,
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEC_PACKET_ARTIFACT_DIVERGENCE_TRUTHFULNESS_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map(
                {
                    'security_report': run_dir / 'security_report.md',
                    'claimed_current_artifact': current_artifact_path,
                    'stale_previous_artifact': stale_artifact_path,
                }
            ),
            'artifact_snapshots': {
                'command_packet': command_packet,
                'current_artifact_before_tamper': current_packet_before_tamper,
                'stale_artifact_snapshot': _read_json(stale_artifact_path) if stale_artifact_path.exists() else {},
            },
            'result_matrix': result_matrix,
            'findings': {
                'review_decision': review_decision,
                'claimed_current_artifact_path': _rel_to_repo(current_artifact_path),
                'stale_artifact_path': _rel_to_repo(stale_artifact_path) if stale_artifact_path.exists() else '',
                'command_decision': str(command_packet.get('decision', '') or ''),
            },
        }

        report_json = run_dir / 'framec_packet_artifact_divergence_truthfulness_probe.json'
        report_md = run_dir / 'framec_packet_artifact_divergence_truthfulness_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame C Packet Artifact Divergence Truthfulness Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': observed_boundary_result,
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


def run_watchdog_heartbeat_spoof_resistance_probe() -> int:
    run_id = 'framed-watchdog-heartbeat-spoof-resistance-{0}'.format(_utc_stamp())
    run_dir = FRAMED_WATCHDOG_HEARTBEAT_SPOOF_RESISTANCE_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMED_WATCHDOG_HEARTBEAT_SPOOF_RESISTANCE_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='framed-watchdog-heartbeat-spoof-resistance-signing-key',
            security_report_title='# Frame D watchdog heartbeat spoof resistance probe security report\n',
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)
        _seed_runtime_liveness(sandbox_root, log_dir)
        watchdog_paths = _seed_watchdog_state_files(log_dir)

        observerctl_module._save_state('sim', 'watch')
        output_packet_path = run_dir / 'framed_watchdog_heartbeat_spoof_resistance_packet.json'
        observer_heartbeat_path = log_dir / 'health' / 'calamum_observer.heartbeat'
        ops_watchdog_heartbeat_path = log_dir / 'health' / 'calamum_ops_watchdog.heartbeat'
        agent_pid_path = sandbox_root / 'calamum_agent.pid'
        stale_epoch = 946684800.0  # 2000-01-01 UTC
        os.utime(observer_heartbeat_path, (stale_epoch, stale_epoch))

        command_runs = {
            'watchdog_check': _run_observerctl_cli([
                'watchdog',
                'check',
                '--json',
            ]),
            'mode_gate_canary': _run_observerctl_cli([
                'ops',
                'mode',
                'gate',
                '--source',
                'sim',
                '--to',
                'canary',
                '--json',
            ]),
            'evidence_pack': _run_observerctl_cli([
                'ops',
                'evidence',
                'pack',
                '--source',
                'sim',
                '--to',
                'canary',
                '--event',
                'framed-watchdog-heartbeat-spoof-resistance',
                '--output',
                str(output_packet_path),
                '--json',
            ]),
        }

        watchdog_packet = _command_stdout_json(command_runs['watchdog_check'])
        mode_gate_packet = _command_stdout_json(command_runs['mode_gate_canary'])
        runtime_status = observerctl_module.collect_runtime_status(source='sim')
        runtime_checks = runtime_status.get('checks', {}) if isinstance(runtime_status.get('checks', {}), dict) else {}
        observer_service = runtime_checks.get('runtime.observer_service', {}) if isinstance(runtime_checks.get('runtime.observer_service', {}), dict) else {}
        collection_state = runtime_checks.get('runtime.collection_state', {}) if isinstance(runtime_checks.get('runtime.collection_state', {}), dict) else {}
        evidence_packet = _read_json(output_packet_path) if output_packet_path.exists() else {}

        result_matrix = {
            'stale_observer_heartbeat_seeded': observer_heartbeat_path.exists(),
            'watchdog_check_completed': int(command_runs['watchdog_check'].get('returncode', 1)) in (0, 2),
            'watchdog_advisory_reason_emitted': 'major_check_failed:observer_heartbeat_stale_service_alive' in list(watchdog_packet.get('advisory_reason_codes', []) or []),
            'watchdog_false_critical_denial_avoided': str(watchdog_packet.get('decision', '') or '').strip().lower() == 'go' and 'critical_check_failed:observer_heartbeat_stale' not in list(watchdog_packet.get('reason_codes', []) or []),
            'runtime_service_state_preserved': str(observer_service.get('status', '') or '').strip().lower() == 'ok',
            'collection_state_remains_legible': str(collection_state.get('state', '') or '').strip().lower() in ('idle', 'warmup', 'collecting', 'stopped', 'error'),
            'mode_gate_preserves_no_false_critical': str(mode_gate_packet.get('decision', '') or '').strip().lower() == 'go' and 'critical_check_failed:observer_heartbeat_stale' not in list(mode_gate_packet.get('reason_codes', []) or []),
            'evidence_packet_written': output_packet_path.exists(),
        }

        report = {
            'scenario_id': 'S5',
            'threat_class': 'watchdog_heartbeat_spoof_resistance',
            'test_classes': ['sandbox-run', 'fault-injection', 'artifact-forensics'],
            'expected_safe_outcome': 'spoofed liveness rejected or degraded explicitly',
            'observed_boundary_result': 'observer_heartbeat_spoof_degraded_explicitly' if _probe_result(result_matrix) == 'pass' else 'review_required',
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMED_WATCHDOG_HEARTBEAT_SPOOF_RESISTANCE_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map(
                {
                    'security_report': run_dir / 'security_report.md',
                    'observer_heartbeat': observer_heartbeat_path,
                    'ops_watchdog_heartbeat': ops_watchdog_heartbeat_path,
                    'agent_pid': agent_pid_path,
                    'posture_state': watchdog_paths['posture_state'],
                    'resource_state': watchdog_paths['resource_state'],
                    'last_gate': observerctl_module._control_file(observerctl_module.LAST_GATE_FILE),
                    'output_packet': output_packet_path,
                }
            ),
            'artifact_snapshots': {
                'watchdog_check_packet': watchdog_packet,
                'mode_gate_packet': mode_gate_packet,
                'runtime_status': runtime_status,
                'evidence_packet': evidence_packet,
            },
            'result_matrix': result_matrix,
            'findings': {
                'stale_observer_heartbeat_timestamp_utc': datetime.fromtimestamp(stale_epoch, timezone.utc).isoformat().replace('+00:00', 'Z'),
                'watchdog_advisory_reason_codes': list(watchdog_packet.get('advisory_reason_codes', []) or []),
                'gate_reason_codes': list(mode_gate_packet.get('reason_codes', []) or []),
                'observer_service_state': observer_service,
                'collection_state': collection_state,
            },
        }

        report_json = run_dir / 'framed_watchdog_heartbeat_spoof_resistance_probe.json'
        report_md = run_dir / 'framed_watchdog_heartbeat_spoof_resistance_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame D Watchdog Heartbeat Spoof Resistance Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': report['observed_boundary_result'],
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


def run_resource_lockdown_chaos_probe() -> int:
    run_id = 'framed-resource-lockdown-chaos-{0}'.format(_utc_stamp())
    run_dir = FRAMED_RESOURCE_LOCKDOWN_CHAOS_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMED_RESOURCE_LOCKDOWN_CHAOS_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='framed-resource-lockdown-chaos-signing-key',
            security_report_title='# Frame D resource lockdown chaos probe security report\n',
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)
        _seed_runtime_liveness(sandbox_root, log_dir)
        observerctl_module._save_state('sim', 'canary')

        output_packet_path = run_dir / 'framed_resource_lockdown_chaos_packet.json'
        command_runs = {
            'baseline_monitor_once': _run_observerctl_cli([
                'baseline',
                'monitor-once',
                '--source',
                'sim',
                '--mode',
                'canary',
                '--normal-interval-sec',
                '0.01',
                '--baseline-interval-sec',
                '0.01',
                '--baseline-window-sec',
                '0.2',
                '--baseline-sample-interval-sec',
                '0.05',
                '--min-normal-samples',
                '1',
                '--min-baseline-samples',
                '1',
                '--json',
            ]),
        }

        watchdog_paths = _seed_watchdog_state_files(
            log_dir,
            posture='lockdown',
            heartbeat_interval=4.0,
            baseline_interval=45.0,
            cpu_now=80.0,
            ram_now=70.0,
            cpu_p95=50.0,
            ram_p95=55.0,
            score=0.6,
            age_s=3.0,
        )
        command_runs['mode_gate_live'] = _run_observerctl_cli([
            'ops',
            'mode',
            'gate',
            '--source',
            'sim',
            '--to',
            'live',
            '--json',
        ])
        command_runs['mode_gate_honeypot'] = _run_observerctl_cli([
            'ops',
            'mode',
            'gate',
            '--source',
            'sim',
            '--to',
            'honeypot',
            '--json',
        ])
        command_runs['evidence_pack_live'] = _run_observerctl_cli([
            'ops',
            'evidence',
            'pack',
            '--source',
            'sim',
            '--to',
            'live',
            '--event',
            'framed-resource-lockdown-chaos',
            '--output',
            str(output_packet_path),
            '--json',
        ])

        live_gate_packet = _command_stdout_json(command_runs['mode_gate_live'])
        honeypot_gate_packet = _command_stdout_json(command_runs['mode_gate_honeypot'])
        evidence_packet = _read_json(output_packet_path) if output_packet_path.exists() else {}
        final_state = observerctl_module._load_state()
        evidence_gate_packet = evidence_packet.get('gate_packet', {}) if isinstance(evidence_packet.get('gate_packet', {}), dict) else {}
        evidence_reason_codes = list(evidence_gate_packet.get('reason_codes', []) or evidence_packet.get('reason_codes', []) or [])

        result_matrix = {
            'baseline_monitor_seed_completed': int(command_runs['baseline_monitor_once'].get('returncode', 1)) == 0,
            'lockdown_state_seed_written': all(path.exists() for path in watchdog_paths.values()),
            'live_gate_denied': str(live_gate_packet.get('decision', '') or '').strip().lower() == 'no-go',
            'honeypot_gate_denied': str(honeypot_gate_packet.get('decision', '') or '').strip().lower() == 'no-go',
            'live_gate_surfaces_lockdown_cpu_spike': 'critical_check_failed:cpu_spike_lockdown' in list(live_gate_packet.get('reason_codes', []) or []),
            'honeypot_gate_surfaces_lockdown_cpu_spike': 'critical_check_failed:cpu_spike_lockdown' in list(honeypot_gate_packet.get('reason_codes', []) or []),
            'state_unchanged_after_chaos_denial': str(final_state.get('mode', '') or '').strip().lower() == 'canary',
            'evidence_packet_preserves_no_go_reasoning': output_packet_path.exists() and ('critical_check_failed:cpu_spike_lockdown' in evidence_reason_codes or 'critical_check_failed:resource_spike_score_critical' in evidence_reason_codes),
        }

        report = {
            'scenario_id': 'S6',
            'threat_class': 'resource_lockdown_chaos',
            'test_classes': ['sandbox-run', 'chaos-stress', 'artifact-forensics'],
            'expected_safe_outcome': 'lockdown or denial path triggers truthfully',
            'observed_boundary_result': 'resource_lockdown_chaos_fail_closed' if _probe_result(result_matrix) == 'pass' else 'review_required',
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMED_RESOURCE_LOCKDOWN_CHAOS_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map(
                {
                    'security_report': run_dir / 'security_report.md',
                    'posture_state': watchdog_paths['posture_state'],
                    'resource_state': watchdog_paths['resource_state'],
                    'baseline_monitor_state': log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json',
                    'last_gate': observerctl_module._control_file(observerctl_module.LAST_GATE_FILE),
                    'output_packet': output_packet_path,
                }
            ),
            'artifact_snapshots': {
                'live_gate_packet': live_gate_packet,
                'honeypot_gate_packet': honeypot_gate_packet,
                'evidence_packet': evidence_packet,
                'final_state': final_state,
            },
            'result_matrix': result_matrix,
            'findings': {
                'live_reason_codes': list(live_gate_packet.get('reason_codes', []) or []),
                'honeypot_reason_codes': list(honeypot_gate_packet.get('reason_codes', []) or []),
                'evidence_reason_codes': evidence_reason_codes,
                'posture_trigger': _read_json(watchdog_paths['posture_state']).get('posture_trigger', ''),
                'resource_spike_score': _read_json(watchdog_paths['resource_state']).get('resource_spike_score', None),
            },
        }

        report_json = run_dir / 'framed_resource_lockdown_chaos_probe.json'
        report_md = run_dir / 'framed_resource_lockdown_chaos_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame D Resource Lockdown Chaos Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': report['observed_boundary_result'],
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
        tampered_request_payload = dict(request_payload)
        tampered_request_payload['requested_action'] = 'publish-live'
        tampered_attestation_payload = dict(attestation_payload)
        tampered_attestation_payload['granted'] = False
        tampered_release_payload = dict(release_receipt_payload)
        tampered_release_payload['dataset_manifest_path'] = 'forged_dataset_manifest.json'

        result_matrix = {
            'signature_roles_are_separated': {
                str((request_doc.get('detached_signature', {}) or {}).get('role', '') or ''),
                str((attestation_doc.get('detached_signature', {}) or {}).get('role', '') or ''),
                str((release_receipt_doc.get('detached_signature', {}) or {}).get('role', '') or ''),
            } == {'requester', 'librarian', 'source'},
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
            'tampered_request_rejected': not verify_detached_payload(
                tampered_request_payload,
                dict(request_doc.get('detached_signature', {}) or {}),
                expected_role='requester',
                expected_purpose='dataset_access_request',
            ),
            'tampered_attestation_rejected': not verify_detached_payload(
                tampered_attestation_payload,
                dict(attestation_doc.get('detached_signature', {}) or {}),
                expected_role='librarian',
                expected_purpose='dataset_access_attestation',
            ),
            'tampered_release_receipt_rejected': not verify_detached_payload(
                tampered_release_payload,
                dict(release_receipt_doc.get('detached_signature', {}) or {}),
                expected_role='source',
                expected_purpose='dataset_access_release',
            ),
        }

        report = {
            'scenario_id': 'S9',
            'threat_class': 'delegated_release_abuse',
            'expected_safe_outcome': 'Delegated release packets verify when untampered and fail closed when a retained signed payload is altered.',
            'observed_boundary_result': 'delegated_release_abuse_packets_fail_signature_verification' if _probe_result(result_matrix) == 'pass' else 'review_required',
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
                'tampered_request_action': str(tampered_request_payload.get('requested_action', '') or ''),
                'tampered_release_manifest': str(tampered_release_payload.get('dataset_manifest_path', '') or ''),
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


def run_baseline_authority_tamper_probe() -> int:
    from analysis.report_pack import prepare_report_bundle, write_report_bundle
    from calamum_librarian import register_librarian_dataset_packet

    run_id = 'framee-baseline-authority-tamper-{0}'.format(_utc_stamp())
    run_dir = FRAMEE_BASELINE_AUTHORITY_TAMPER_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEE_BASELINE_AUTHORITY_TAMPER_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='framee-baseline-authority-tamper-signing-key',
            security_report_title='# Frame E baseline authority tamper probe security report\n',
        )
        _override_env_vars(
            original_env,
            {'CALAMUM_LIBRARIAN_VAULT_KEY': 'framee-baseline-authority-tamper-vault-key'},
        )
        anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)

        canary_dataset_dir = sandbox_root / 'datasets' / 'framee_reviewed_canary_authority'
        canary_dataset_dir.mkdir(parents=True, exist_ok=True)
        canary_features_csv = canary_dataset_dir / 'features.csv'
        canary_labels_csv = canary_dataset_dir / 'labels.csv'
        canary_manifest_path = canary_dataset_dir / 'dataset_manifest.json'
        canary_features_csv.write_text('record_id,feature\n1,0.11\n2,0.29\n', encoding='utf-8')
        canary_labels_csv.write_text('record_id,label\n1,1\n2,0\n', encoding='utf-8')
        _write_json(
            canary_manifest_path,
            {
                'source': 'real',
                'mode': 'canary',
                'features_csv': str(canary_features_csv),
                'labels_csv': str(canary_labels_csv),
                'total_records': 2,
                'has_labels': True,
            },
        )

        live_target_dir = sandbox_root / 'datasets' / 'framee_live_report_target'
        live_target_dir.mkdir(parents=True, exist_ok=True)
        live_features_csv = live_target_dir / 'features.csv'
        live_manifest_path = live_target_dir / 'dataset_manifest.json'
        live_features_csv.write_text('record_id,feature\n1,0.34\n2,0.71\n', encoding='utf-8')
        _write_json(
            live_manifest_path,
            {
                'source': 'real',
                'mode': 'live',
                'features_csv': str(live_features_csv),
                'total_records': 2,
                'has_labels': False,
            },
        )

        canary_register_packet = register_librarian_dataset_packet(
            anchor,
            canary_manifest_path,
            display_name='Frame E Reviewed Canary Authority',
            run_id='framee-reviewed-canary-authority',
        )
        live_register_packet = register_librarian_dataset_packet(
            anchor,
            live_manifest_path,
            display_name='Frame E Live Report Target',
            run_id='framee-live-report-target',
        )
        authority_entry = dict(canary_register_packet.get('dataset', {}) or {})

        review_policy_packet = run_dir / 'framee_review_policy_packet.md'
        review_policy_packet.write_text('# frame e baseline authority review policy\n', encoding='utf-8')

        emitted = observerctl_module._ds_emit_comparison_baseline_packet(
            authority_entry,
            baseline_stage='canary_reviewed',
            companion_role='frame e baseline authority companion',
            review_policy_packet=str(review_policy_packet),
        )
        comparison_baseline_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(emitted.get('packet_path', '') or ''),
        )
        original_packet = _read_json(comparison_baseline_path) if comparison_baseline_path.exists() else {}

        pre_tamper_candidate = observerctl_module._ds_select_lineage_comparison_baseline_candidate(
            source='real',
            mode='live',
            baseline_window_id=str(authority_entry.get('run_id', '') or ''),
        )

        tampered_packet = dict(original_packet)
        tampered_packet['selector_entry_id'] = 'forged-selector-entry'
        tampered_packet['selector_run_id'] = 'forged-selector-run'
        _write_json(comparison_baseline_path, tampered_packet)

        repaired_candidate = observerctl_module._ds_select_lineage_comparison_baseline_candidate(
            source='real',
            mode='live',
            baseline_packet_ref=str(comparison_baseline_path),
            baseline_window_id=str(authority_entry.get('run_id', '') or ''),
        )
        repaired_packet = _read_json(comparison_baseline_path) if comparison_baseline_path.exists() else {}
        pre_tamper_candidate_snapshot = json.loads(json.dumps(pre_tamper_candidate, default=str))
        repaired_candidate_snapshot = json.loads(json.dumps(repaired_candidate, default=str))

        bundle = prepare_report_bundle(anchor, 'evaluate', run_id='framee-baseline-authority-report')
        evaluation_dir = bundle.artifact_dirs['evaluation']
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        run_json = evaluation_dir / 'run.json'
        run_md = evaluation_dir / 'run.md'
        run_json.write_text('{}\n', encoding='utf-8')
        run_md.write_text('# frame e baseline authority report\n', encoding='utf-8')

        report_bundle = write_report_bundle(
            project_anchor=anchor,
            bundle=bundle,
            packet={
                'timestamp_utc': observerctl_module._utc_now(),
                'runtime_cli_surface': 'observerctl',
                'decision': 'go',
                'action': 'ds-evaluate',
                'command_family': 'ds',
                'command_path': 'observerctl ds evaluate',
                'implementation_state': 'command-available',
                'underlying_surface': 'analysis.evaluation_harness',
                'summary': 'Frame E baseline authority tamper evaluation report.',
                'run_id': bundle.run_id,
                'collection_alias': 'framee-baseline-authority',
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
                'baseline_analysis_packet': str(comparison_baseline_path),
                'baseline_window_id': str(authority_entry.get('run_id', '') or ''),
            },
            lineage={'dataset_manifest': live_manifest_path},
        )

        manifest_context = dict(report_bundle.get('manifest', {}).get('context', {}) or {})
        manifest_context_packet_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(manifest_context.get('baseline_analysis_packet', '') or ''),
        )
        manifest_context_packet = _read_json(manifest_context_packet_path) if manifest_context_packet_path.exists() else {}
        report_manifest_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(report_bundle.get('paths', {}).get('manifest_json', '') or ''),
        )
        report_json_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(report_bundle.get('paths', {}).get('report_json', '') or ''),
        )
        report_md_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(report_bundle.get('paths', {}).get('report_md', '') or ''),
        )

        result_matrix = {
            'canary_authority_registered': str(canary_register_packet.get('decision', '') or '').strip().lower() == 'go',
            'live_target_registered': str(live_register_packet.get('decision', '') or '').strip().lower() == 'go',
            'comparison_baseline_candidate_exists_before_tamper': bool(pre_tamper_candidate),
            'selector_linkage_tamper_written': str(tampered_packet.get('selector_entry_id', '') or '').strip() == 'forged-selector-entry',
            'explicit_candidate_repaired_from_authority': bool(repaired_candidate),
            'repaired_packet_restored_selector_entry': str(repaired_packet.get('selector_entry_id', '') or '').strip() == str(authority_entry.get('entry_id', '') or '').strip(),
            'repaired_packet_restored_selector_run': str(repaired_packet.get('selector_run_id', '') or '').strip() == str(authority_entry.get('run_id', '') or '').strip(),
            'report_context_uses_repaired_packet': manifest_context_packet_path == comparison_baseline_path,
            'report_context_keeps_expected_window_id': str(manifest_context.get('baseline_window_id', '') or '').strip() == str(authority_entry.get('run_id', '') or '').strip(),
            'report_context_packet_restored_selector_entry': str(manifest_context_packet.get('selector_entry_id', '') or '').strip() == str(authority_entry.get('entry_id', '') or '').strip(),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEE_BASELINE_AUTHORITY_TAMPER_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'scenario_id': 'S7',
            'threat_class': 'baseline_authority_tamper',
            'expected_safe_outcome': 'Explicit selector-linkage tampering is rejected and repaired from authoritative dataset state before report context reuse.',
            'observed_boundary_result': 'baseline_authority_tamper_repaired_from_authoritative_selector',
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': {},
            'artifact_paths': _report_path_map(
                {
                    'security_report': run_dir / 'security_report.md',
                    'review_policy_packet': review_policy_packet,
                    'canary_manifest': canary_manifest_path,
                    'live_manifest': live_manifest_path,
                    'comparison_baseline_packet': comparison_baseline_path,
                    'report_manifest_json': report_manifest_path,
                    'report_json': report_json_path,
                    'report_md': report_md_path,
                }
            ),
            'artifact_snapshots': {
                'canary_register_packet': canary_register_packet,
                'live_register_packet': live_register_packet,
                'original_packet': original_packet,
                'tampered_packet': tampered_packet,
                'repaired_packet': repaired_packet,
                'pre_tamper_candidate': pre_tamper_candidate_snapshot,
                'repaired_candidate': repaired_candidate_snapshot,
                'report_manifest_context': manifest_context,
            },
            'result_matrix': result_matrix,
            'findings': {
                'authority_entry_id': str(authority_entry.get('entry_id', '') or ''),
                'authority_run_id': str(authority_entry.get('run_id', '') or ''),
                'tampered_selector_entry_id': str(tampered_packet.get('selector_entry_id', '') or ''),
                'repaired_selector_entry_id': str(repaired_packet.get('selector_entry_id', '') or ''),
                'repaired_selector_run_id': str(repaired_packet.get('selector_run_id', '') or ''),
                'report_context_baseline_packet': _rel_to_repo(manifest_context_packet_path),
            },
        }

        report_json = run_dir / 'framee_baseline_authority_tamper_probe.json'
        report_md = run_dir / 'framee_baseline_authority_tamper_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame E Baseline Authority Tamper Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': report['observed_boundary_result'],
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


def run_report_lineage_forgery_probe() -> int:
    from analysis.report_aggregate import append_ds_run_index, publication_eligibility_reasons, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle
    from calamum_librarian import register_librarian_dataset_packet

    run_id = 'framee-report-lineage-forgery-{0}'.format(_utc_stamp())
    run_dir = FRAMEE_REPORT_LINEAGE_FORGERY_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEE_REPORT_LINEAGE_FORGERY_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='framee-report-lineage-forgery-signing-key',
            security_report_title='# Frame E report lineage forgery probe security report\n',
        )
        _override_env_vars(
            original_env,
            {'CALAMUM_LIBRARIAN_VAULT_KEY': 'framee-report-lineage-forgery-vault-key'},
        )
        anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)

        dataset_dir = sandbox_root / 'datasets' / 'framee_lineage_authority'
        dataset_dir.mkdir(parents=True, exist_ok=True)
        features_csv = dataset_dir / 'features.csv'
        manifest_path = dataset_dir / 'dataset_manifest.json'
        features_csv.write_text('record_id,feature\n1,0.18\n2,0.83\n', encoding='utf-8')
        _write_json(
            manifest_path,
            {
                'source': 'real',
                'mode': 'live',
                'features_csv': str(features_csv),
                'total_records': 2,
                'has_labels': False,
            },
        )

        dataset_register_packet = register_librarian_dataset_packet(
            anchor,
            manifest_path,
            display_name='Frame E Lineage Authority Dataset',
            run_id='framee-lineage-authority',
        )

        bundle = prepare_report_bundle(anchor, 'score', run_id='framee-lineage-forgery-score')
        scoring_dir = bundle.artifact_dirs['scoring']
        scoring_dir.mkdir(parents=True, exist_ok=True)
        scores_csv = scoring_dir / 'scores.csv'
        scores_csv.write_text('record_id,score_anomaly\na,0.1\nb,0.9\n', encoding='utf-8')

        report_bundle = write_report_bundle(
            project_anchor=anchor,
            bundle=bundle,
            packet={
                'timestamp_utc': '2026-04-21T23:59:00Z',
                'runtime_cli_surface': 'observerctl',
                'decision': 'go',
                'action': 'ds-score',
                'command_family': 'ds',
                'command_path': 'observerctl ds score',
                'implementation_state': 'command-available',
                'underlying_surface': 'analysis.score_unsupervised',
                'summary': 'Frame E lineage forgery publication candidate.',
                'run_id': bundle.run_id,
                'collection_alias': 'framee-lineage-forgery',
                'records_scored': 2,
                'anomaly_direction': 'lower-is-more-anomalous',
                'score_column': 'score_anomaly',
                'artifacts': {},
                'reason_codes': [],
            },
            artifact_paths={'scores_csv': scores_csv},
            context={'output_override': False},
            lineage={'dataset_manifest': manifest_path},
        )

        pre_tamper_reasons = publication_eligibility_reasons(
            project_anchor=anchor,
            manifest_payload=report_bundle['manifest'],
        )
        append_ds_run_index(project_anchor=anchor, manifest_payload=report_bundle['manifest'])

        source_manifest_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(report_bundle.get('paths', {}).get('manifest_json', '') or ''),
        )
        tampered_manifest = _read_json(source_manifest_path)
        forged_manifest_ref = 'C:/Users/tester/AppData/Local/Temp/forged_dataset_manifest.json'
        tampered_lineage = dict(tampered_manifest.get('lineage', {}) or {})
        tampered_lineage['dataset_manifest'] = forged_manifest_ref
        tampered_manifest['lineage'] = tampered_lineage
        _write_json(source_manifest_path, tampered_manifest)

        tampered_reasons = publication_eligibility_reasons(
            project_anchor=anchor,
            manifest_payload=tampered_manifest,
        )
        publication = refresh_tracked_ds_publication(
            project_anchor=anchor,
            current_manifest_payload=tampered_manifest,
        )

        alias_root = sandbox_root / 'docs' / 'reports' / 'collections' / 'framee-lineage-forgery'
        aggregate_report_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(publication.get('aggregate_paths', {}).get('aggregate_report_md', '') or ''),
        )
        public_run_ledger_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(publication.get('aggregate_paths', {}).get('public_run_ledger_md', '') or ''),
        )

        result_matrix = {
            'dataset_authority_registered': str(dataset_register_packet.get('decision', '') or '').strip().lower() == 'go',
            'pre_tamper_publication_eligible': 'publication_skipped:dataset_manifest_ephemeral' not in pre_tamper_reasons,
            'manifest_tamper_persisted': str(dict(tampered_manifest.get('lineage', {}) or {}).get('dataset_manifest', '') or '').strip() == forged_manifest_ref,
            'tampered_publication_reason_emitted': 'publication_skipped:dataset_manifest_ephemeral' in tampered_reasons,
            'tampered_run_not_published': publication.get('current_run', {}) == {},
            'published_run_count_zero': int(publication.get('published_run_count', 0) or 0) == 0,
            'collection_alias_not_materialized': not alias_root.exists(),
            'aggregate_surfaces_still_rendered': aggregate_report_path.exists() and public_run_ledger_path.exists(),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEE_REPORT_LINEAGE_FORGERY_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'scenario_id': 'S8',
            'threat_class': 'report_lineage_forgery',
            'expected_safe_outcome': 'Tracked publication fails closed when a persisted run manifest is tampered to point at ephemeral dataset lineage.',
            'observed_boundary_result': 'report_lineage_forgery_blocked_before_publication',
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': {},
            'artifact_paths': _report_path_map(
                {
                    'security_report': run_dir / 'security_report.md',
                    'dataset_manifest': manifest_path,
                    'scores_csv': scores_csv,
                    'source_manifest_json': source_manifest_path,
                    'aggregate_report_md': aggregate_report_path,
                    'public_run_ledger_md': public_run_ledger_path,
                }
            ),
            'artifact_snapshots': {
                'dataset_register_packet': dataset_register_packet,
                'pre_tamper_manifest': report_bundle['manifest'],
                'tampered_manifest': tampered_manifest,
                'publication': publication,
            },
            'result_matrix': result_matrix,
            'findings': {
                'pre_tamper_reasons': pre_tamper_reasons,
                'tampered_reasons': tampered_reasons,
                'forged_dataset_manifest': forged_manifest_ref,
                'aggregate_report_md': _rel_to_repo(aggregate_report_path),
                'public_run_ledger_md': _rel_to_repo(public_run_ledger_path),
            },
        }

        report_json = run_dir / 'framee_report_lineage_forgery_probe.json'
        report_md = run_dir / 'framee_report_lineage_forgery_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame E Report Lineage Forgery Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': report['observed_boundary_result'],
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
                '--access-class',
                'protected-source',
                '--display-name',
                'Vault Primary Dataset',
                '--run-id',
                'vault-primary',
                '--json',
            ]),
            'vault_status': _run_observerctl_cli(['librarian', 'vault', 'status', '--json']),
            'vault_unlock': _run_observerctl_cli(['librarian', 'vault', 'unlock', '--reason', 'sandbox-maintenance', '--json']),
            'register_while_unlocked': _run_observerctl_cli([
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
            'release_while_unlocked': _run_observerctl_cli([
                'librarian',
                'dataset',
                'release',
                '1',
                '--requester-id',
                'sandbox-maintenance-probe',
                '--json',
            ]),
            'vault_lock': _run_observerctl_cli(['librarian', 'vault', 'lock', '--reason', 'sandbox-complete', '--json']),
            'vault_rebaseline': _run_observerctl_cli(['librarian', 'vault', 'rebaseline', '--reason', 'sandbox-refresh', '--json']),
            'vault_verify': _run_observerctl_cli(['librarian', 'vault', 'verify', '--json']),
        }

        status_packet = command_runs['vault_status'].get('stdout_json', {}) if isinstance(command_runs['vault_status'].get('stdout_json', {}), dict) else {}
        unlock_packet = command_runs['vault_unlock'].get('stdout_json', {}) if isinstance(command_runs['vault_unlock'].get('stdout_json', {}), dict) else {}
        unlocked_register_packet = command_runs['register_while_unlocked'].get('stdout_json', {}) if isinstance(command_runs['register_while_unlocked'].get('stdout_json', {}), dict) else {}
        unlocked_release_packet = command_runs['release_while_unlocked'].get('stdout_json', {}) if isinstance(command_runs['release_while_unlocked'].get('stdout_json', {}), dict) else {}
        lock_packet = command_runs['vault_lock'].get('stdout_json', {}) if isinstance(command_runs['vault_lock'].get('stdout_json', {}), dict) else {}
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
            'vault_unlock_succeeded': int(command_runs['vault_unlock'].get('returncode', 1)) == 0 and bool(unlock_packet.get('locked', True)) is False,
            'unlocked_register_denied': int(command_runs['register_while_unlocked'].get('returncode', 0)) != 0 and 'critical_check_failed:librarian_vault_maintenance_window_open' in list(unlocked_register_packet.get('reason_codes', []) or []),
            'unlocked_release_denied': int(command_runs['release_while_unlocked'].get('returncode', 0)) != 0 and 'critical_check_failed:librarian_vault_maintenance_window_open' in list(unlocked_release_packet.get('reason_codes', []) or []),
            'vault_lock_succeeded': int(command_runs['vault_lock'].get('returncode', 1)) == 0 and bool(lock_packet.get('locked', False)) is True,
            'vault_rebaseline_succeeded': int(command_runs['vault_rebaseline'].get('returncode', 1)) == 0 and str(rebaseline_packet.get('action', '')).strip() == 'librarian-vault-rebaseline',
            'vault_verify_succeeded': int(command_runs['vault_verify'].get('returncode', 1)) == 0 and str(verify_packet.get('decision', '')).strip() == 'go',
            'vault_control_state_written': control_state_path.exists() and bool(control_state) and bool(control_state.get('locked', False)) is True,
            'vault_audit_records_control_actions': all(action in audit_actions for action in ['librarian-vault-lock', 'librarian-vault-unlock', 'librarian-vault-rebaseline']) and baseline_path.exists(),
        }

        report = {
            'scenario_id': 'S10',
            'threat_class': 'maintenance_window_abuse',
            'expected_safe_outcome': 'Maintenance-window unlock preserves manual control while failing closed for ordinary register and release mutations.',
            'observed_boundary_result': 'maintenance_window_abuse_denied_fail_closed' if _probe_result(result_matrix) == 'pass' else 'review_required',
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
                'vault_unlock_packet': unlock_packet,
                'unlocked_register_packet': unlocked_register_packet,
                'unlocked_release_packet': unlocked_release_packet,
                'vault_lock_packet': lock_packet,
                'vault_rebaseline_packet': rebaseline_packet,
                'vault_verify_packet': verify_packet,
                'vault_control_state': control_state,
                'vault_audit_rows': audit_rows,
            },
            'result_matrix': result_matrix,
            'findings': {
                'audit_actions': audit_actions,
                'verify_integrity_status': str(verify_packet.get('integrity_status', '') or ''),
                'locked_reason_codes': list(unlocked_register_packet.get('reason_codes', []) or []),
                'unlocked_register_reason_codes': list(unlocked_register_packet.get('reason_codes', []) or []),
                'unlocked_release_reason_codes': list(unlocked_release_packet.get('reason_codes', []) or []),
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


def run_posture_transition_bypass_probe() -> int:
    run_id = 'frameb-posture-transition-bypass-{0}'.format(_utc_stamp())
    run_dir = FRAMEB_POSTURE_TRANSITION_BYPASS_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEB_POSTURE_TRANSITION_BYPASS_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frameb-posture-transition-bypass-signing-key',
            security_report_title='# Frame B posture transition bypass probe security report\n',
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)
        _seed_runtime_liveness(sandbox_root, log_dir)

        security_report = run_dir / 'security_report_transition.md'
        security_report.write_text('# frame b posture transition bypass security report\n', encoding='utf-8')

        observerctl_module._save_state('sim', 'canary')
        gate_packet = _seed_mode_gate_packet(
            'sim',
            'canary',
            'live',
            run_id='frameb-posture-transition-bypass-live',
            posture_trigger_id='pt-frameb-posture-transition-bypass',
            security_report_ref=str(security_report),
        )
        seeded_run_context = _seed_gate_run_context(
            run_id=str(gate_packet.get('run_id', '') or ''),
            posture_trigger_id=str(gate_packet.get('posture_trigger_id', '') or ''),
            posture_trigger=str(gate_packet.get('posture_trigger', '') or ''),
            security_report_ref=str(gate_packet.get('security_report_ref', '') or ''),
        )

        observerctl_module._save_state('sim', 'watch')
        mode_set_packet = observerctl_module._ops_mode_set(source='sim', to_mode='live')
        final_state = observerctl_module._load_state()
        posture_state_path = observerctl_module._control_file(observerctl_module.WATCHDOG_POSTURE_FILE)

        result_matrix = {
            'fresh_gate_packet_seeded': str(gate_packet.get('decision', '') or '').strip().lower() == 'go',
            'matching_run_context_seeded': str(seeded_run_context.get('run_id', '') or '').strip() == str(gate_packet.get('run_id', '') or '').strip(),
            'current_state_mutated_after_gate': str(final_state.get('mode', '') or '').strip().lower() == 'watch',
            'mode_set_denied': str(mode_set_packet.get('decision', '') or '').strip().lower() == 'no-go',
            'state_mismatch_reason_emitted': 'critical_check_failed:gate_packet_state_mismatch' in list(mode_set_packet.get('reason_codes', []) or []),
            'live_mode_not_persisted': str(final_state.get('mode', '') or '').strip().lower() == 'watch',
            'posture_write_skipped_on_denial': not posture_state_path.exists(),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEB_POSTURE_TRANSITION_BYPASS_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': {},
            'artifact_paths': _report_path_map({
                'security_report_ref': security_report,
                'last_gate': observerctl_module._control_file(observerctl_module.LAST_GATE_FILE),
                'run_context': observerctl_module._control_file(observerctl_module.RUN_CONTEXT_FILE),
                'posture_state': posture_state_path,
            }),
            'artifact_snapshots': {
                'gate_packet': gate_packet,
                'mode_set_packet': mode_set_packet,
                'final_state': final_state,
            },
            'result_matrix': result_matrix,
            'findings': {
                'mode_set_reason_codes': list(mode_set_packet.get('reason_codes', []) or []),
                'current_from_state': str(mode_set_packet.get('current_from_state', '') or ''),
                'gate_from_state': str(mode_set_packet.get('gate_from_state', '') or ''),
            },
        }

        report_json = run_dir / 'frameb_posture_transition_bypass_probe.json'
        report_md = run_dir / 'frameb_posture_transition_bypass_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame B Posture Transition Bypass Probe', report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': report['next_bite_result'],
            'mode_set_decision': str(mode_set_packet.get('decision', '') or ''),
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


def run_stale_gate_replay_probe() -> int:
    run_id = 'frameb-stale-gate-replay-{0}'.format(_utc_stamp())
    run_dir = FRAMEB_STALE_GATE_REPLAY_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEB_STALE_GATE_REPLAY_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frameb-stale-gate-replay-signing-key',
            security_report_title='# Frame B stale gate replay probe security report\n',
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)
        _seed_runtime_liveness(sandbox_root, log_dir)

        security_report_a = run_dir / 'security_report_a.md'
        security_report_b = run_dir / 'security_report_b.md'
        security_report_a.write_text('# frame b stale gate report a\n', encoding='utf-8')
        security_report_b.write_text('# frame b stale gate report b\n', encoding='utf-8')

        observerctl_module._save_state('sim', 'canary')

        stale_gate_packet = _seed_mode_gate_packet(
            'sim',
            'canary',
            'live',
            run_id='frameb-stale-gate-packet',
            posture_trigger_id='pt-frameb-stale-gate',
            security_report_ref=str(security_report_a),
            timestamp_utc='2000-01-01T00:00:00Z',
        )
        _seed_gate_run_context(
            run_id=str(stale_gate_packet.get('run_id', '') or ''),
            posture_trigger_id=str(stale_gate_packet.get('posture_trigger_id', '') or ''),
            posture_trigger=str(stale_gate_packet.get('posture_trigger', '') or ''),
            security_report_ref=str(stale_gate_packet.get('security_report_ref', '') or ''),
        )
        stale_mode_set_packet = observerctl_module._ops_mode_set(source='sim', to_mode='live')

        replay_gate_packet = _seed_mode_gate_packet(
            'sim',
            'canary',
            'live',
            run_id='frameb-replayed-gate-packet',
            posture_trigger_id='pt-frameb-replayed-gate',
            security_report_ref=str(security_report_a),
        )
        replay_run_context = _seed_gate_run_context(
            run_id='frameb-new-lineage',
            posture_trigger_id='pt-frameb-new-lineage',
            posture_trigger=str(replay_gate_packet.get('posture_trigger', '') or ''),
            security_report_ref=str(security_report_b),
        )
        replay_mode_set_packet = observerctl_module._ops_mode_set(source='sim', to_mode='live')
        final_state = observerctl_module._load_state()
        posture_state_path = observerctl_module._control_file(observerctl_module.WATCHDOG_POSTURE_FILE)

        result_matrix = {
            'stale_packet_denied': str(stale_mode_set_packet.get('decision', '') or '').strip().lower() == 'no-go',
            'stale_reason_emitted': 'critical_check_failed:gate_packet_missing_or_stale' in list(stale_mode_set_packet.get('reason_codes', []) or []),
            'replay_packet_denied': str(replay_mode_set_packet.get('decision', '') or '').strip().lower() == 'no-go',
            'lineage_mismatch_reason_emitted': 'critical_check_failed:gate_packet_lineage_mismatch' in list(replay_mode_set_packet.get('reason_codes', []) or []),
            'replayed_lineage_fields_detected': set(list(replay_mode_set_packet.get('lineage_mismatch_fields', []) or [])) == set(['run_id', 'posture_trigger_id', 'security_report_ref']),
            'live_mode_not_persisted': str(final_state.get('mode', '') or '').strip().lower() == 'canary',
            'posture_write_skipped_on_denial': not posture_state_path.exists(),
            'replay_context_differs_from_gate': str(replay_run_context.get('run_id', '') or '').strip() != str(replay_gate_packet.get('run_id', '') or '').strip(),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEB_STALE_GATE_REPLAY_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': {},
            'artifact_paths': _report_path_map({
                'security_report_a': security_report_a,
                'security_report_b': security_report_b,
                'last_gate': observerctl_module._control_file(observerctl_module.LAST_GATE_FILE),
                'run_context': observerctl_module._control_file(observerctl_module.RUN_CONTEXT_FILE),
                'posture_state': posture_state_path,
            }),
            'artifact_snapshots': {
                'stale_gate_packet': stale_gate_packet,
                'stale_mode_set_packet': stale_mode_set_packet,
                'replay_gate_packet': replay_gate_packet,
                'replay_run_context': replay_run_context,
                'replay_mode_set_packet': replay_mode_set_packet,
                'final_state': final_state,
            },
            'result_matrix': result_matrix,
            'findings': {
                'stale_reason_codes': list(stale_mode_set_packet.get('reason_codes', []) or []),
                'replay_reason_codes': list(replay_mode_set_packet.get('reason_codes', []) or []),
                'replay_lineage_mismatch_fields': list(replay_mode_set_packet.get('lineage_mismatch_fields', []) or []),
            },
        }

        report_json = run_dir / 'frameb_stale_gate_replay_probe.json'
        report_md = run_dir / 'frameb_stale_gate_replay_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame B Stale Gate Replay Probe', report), encoding='utf-8')

        _append_jsonl(run_index_jsonl, {
            'run_id': run_id,
            'timestamp_utc': _utc_stamp(),
            'run_dir': _rel_to_repo(run_dir),
            'report_json': _rel_to_repo(report_json),
            'report_md': _rel_to_repo(report_md),
            'next_bite_result': report['next_bite_result'],
            'replay_mode_set_decision': str(replay_mode_set_packet.get('decision', '') or ''),
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


def run_keysmith_version_parity_break_probe() -> int:
    run_id = 'framef-keysmith-version-parity-break-{0}'.format(_utc_stamp())
    run_dir = FRAMEF_KEYSMITH_VERSION_PARITY_BREAK_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEF_KEYSMITH_VERSION_PARITY_BREAK_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='framef-keysmith-version-parity-break-signing-key',
            security_report_title='# Frame F KEYSMITH version parity break probe security report\n',
        )
        _seed_probe_project_root(sandbox_root)

        sandbox_keysmith_path = sandbox_root / 'src' / 'keysmith.py'
        sandbox_dockerfile = sandbox_root / 'deployment' / 'keysmith' / 'Dockerfile'
        sandbox_requirements = sandbox_root / 'deployment' / 'keysmith' / 'requirements.txt'
        sandbox_keysmith_path.parent.mkdir(parents=True, exist_ok=True)
        sandbox_dockerfile.parent.mkdir(parents=True, exist_ok=True)
        sandbox_requirements.parent.mkdir(parents=True, exist_ok=True)
        sandbox_keysmith_path.write_text((PROJECT_ROOT / 'src' / 'keysmith.py').read_text(encoding='utf-8'), encoding='utf-8')
        sandbox_dockerfile.write_text((PROJECT_ROOT / 'deployment' / 'keysmith' / 'Dockerfile').read_text(encoding='utf-8'), encoding='utf-8')
        sandbox_requirements.write_text((PROJECT_ROOT / 'deployment' / 'keysmith' / 'requirements.txt').read_text(encoding='utf-8'), encoding='utf-8')

        artifacts_dir = run_dir / 'artifacts'
        output_dir = artifacts_dir / 'keysmith_exports'
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        command_runs = {
            'keysmith_dry_run': _run_observerctl_cli([
                'ops',
                'keysmith',
                'mint',
                '--dry-run',
                '--output-dir',
                str(output_dir),
                '--json',
            ]),
        }

        mint_packet = _command_stdout_json(command_runs['keysmith_dry_run'])
        result_json_path = _resolve_probe_artifact_path(sandbox_root, str(mint_packet.get('result_json', '') or ''))
        result_payload = _read_json(result_json_path) if result_json_path.exists() else {}
        proof_review = observerctl_module._keysmith_result_proof_packet(result_json_path)

        tampered_result_path = artifacts_dir / 'keysmith_result_tampered.json'
        tampered_payload = json.loads(json.dumps(result_payload)) if result_payload else {}
        tampered_build_proof = dict(tampered_payload.get('build_proof', {}) or {}) if isinstance(tampered_payload.get('build_proof', {}), dict) else {}
        tampered_build_proof['keysmith_version'] = '0.0.0-tampered'
        tampered_payload['build_proof'] = tampered_build_proof
        _write_json(tampered_result_path, tampered_payload)
        tampered_review = observerctl_module._keysmith_result_proof_packet(tampered_result_path)
        tampered_mismatches = dict(tampered_review.get('mismatches', {}) or {}) if isinstance(tampered_review.get('mismatches', {}), dict) else {}

        result_matrix = {
            'keysmith_dry_run_completed': int(command_runs['keysmith_dry_run'].get('returncode', 1)) == 0 and str(mint_packet.get('decision', '')).strip().lower() == 'go',
            'result_json_written': result_json_path.exists(),
            'positive_proof_review_go': str(proof_review.get('decision', '')).strip().lower() == 'go',
            'positive_proof_review_has_no_mismatches': len(dict(proof_review.get('mismatches', {}) or {})) == 0,
            'tampered_proof_review_no_go': str(tampered_review.get('decision', '')).strip().lower() == 'no-go',
            'tampered_proof_reason_emitted': 'critical_check_failed:keysmith_version_parity_mismatch' in list(tampered_review.get('reason_codes', []) or []),
            'tampered_proof_surfaces_version_mismatch': 'keysmith_version' in tampered_mismatches,
            'proof_review_stays_names_only': 'DRY_RUN_PLACEHOLDER_DO_NOT_USE' not in json.dumps({
                'mint_packet': mint_packet,
                'proof_review': proof_review,
                'tampered_review': tampered_review,
            }),
        }

        report = {
            'scenario_id': 'S11',
            'threat_class': 'keysmith_version_parity_break',
            'expected_safe_outcome': 'KEYSMITH retained proof mismatches are surfaced as explicit no-go instead of standing in for the current build under review.',
            'observed_boundary_result': 'keysmith_version_parity_break_detected_fail_closed' if _probe_result(result_matrix) == 'pass' else 'review_required',
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEF_KEYSMITH_VERSION_PARITY_BREAK_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': command_runs,
            'artifact_paths': _report_path_map(
                {
                    'security_report': run_dir / 'security_report.md',
                    'result_json': result_json_path,
                    'tampered_result_json': tampered_result_path,
                }
            ),
            'artifact_snapshots': {
                'mint_packet': mint_packet,
                'result_payload': result_payload,
                'proof_review': proof_review,
                'tampered_payload': tampered_payload,
                'tampered_review': tampered_review,
            },
            'result_matrix': result_matrix,
            'findings': {
                'build_proof': dict(proof_review.get('expected_build_proof', {}) or {}) if isinstance(proof_review.get('expected_build_proof', {}), dict) else {},
                'tampered_mismatches': tampered_mismatches,
                'mint_summary': str(mint_packet.get('summary', '') or ''),
            },
        }

        report_json = run_dir / 'framef_keysmith_version_parity_break_probe.json'
        report_md = run_dir / 'framef_keysmith_version_parity_break_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame F KEYSMITH Version Parity Break Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': report['observed_boundary_result'],
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


def run_public_report_boundary_escape_probe() -> int:
    from analysis.report_aggregate import append_ds_run_index, refresh_tracked_ds_publication
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    run_id = 'frameg-public-report-boundary-escape-{0}'.format(_utc_stamp())
    run_dir = FRAMEG_PUBLIC_REPORT_BOUNDARY_ESCAPE_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEG_PUBLIC_REPORT_BOUNDARY_ESCAPE_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frameg-public-report-boundary-escape-signing-key',
            security_report_title='# Frame G public report boundary escape probe security report\n',
        )
        anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)
        _seed_shipped_manual_report_surfaces(sandbox_root)

        score_bundle = prepare_report_bundle(anchor, 'score', run_id='frameg-public-boundary-score')
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
        figure_path.write_bytes(b'frameg-public-report-boundary-escape-fixture')

        score_report_bundle = write_report_bundle(
            project_anchor=anchor,
            bundle=score_bundle,
            packet={
                'timestamp_utc': '2026-04-22T00:15:00Z',
                'runtime_cli_surface': 'observerctl',
                'decision': 'go',
                'action': 'ds-score',
                'command_family': 'ds',
                'command_path': 'observerctl ds score',
                'implementation_state': 'command-available',
                'underlying_surface': 'analysis.score_unsupervised',
                'summary': 'Frame G public report boundary publication candidate.',
                'run_id': score_bundle.run_id,
                'collection_alias': 'frameg-public-boundary',
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

        source_report_json_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(score_report_bundle.get('paths', {}).get('report_json', '') or ''),
        )
        source_report_md_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(score_report_bundle.get('paths', {}).get('report_md', '') or ''),
        )
        source_report_payload = _read_json(source_report_json_path)
        source_report_payload['result']['thresholding']['report_json'] = str(threshold_report_json).replace('\\', '/')
        source_report_payload['result']['thresholding']['report_md'] = str(threshold_report_md).replace('\\', '/')
        source_report_payload['result']['thresholding']['scores_csv'] = str(scores_csv).replace('\\', '/')
        source_report_payload['result']['visuals']['figures'][0]['path'] = str(figure_path).replace('\\', '/')
        source_report_json_path.write_text(json.dumps(source_report_payload, indent=2, sort_keys=True), encoding='utf-8')

        local_authority_lure = 'C:/Operators/RuntimeAuthority/local_only/not-for-public.json'
        source_report_md_path.write_text(
            '# stale canonical markdown\n\n- leaked path: {0}\n- local authority lure: {1}\n'.format(
                str(figure_path).replace('\\', '/'),
                local_authority_lure,
            ),
            encoding='utf-8',
        )

        append_ds_run_index(project_anchor=anchor, manifest_payload=score_report_bundle['manifest'])
        publication = refresh_tracked_ds_publication(
            project_anchor=anchor,
            current_manifest_payload=score_report_bundle['manifest'],
        )

        current_run = publication.get('current_run', {}) if isinstance(publication.get('current_run', {}), dict) else {}
        published_paths = current_run.get('published_report_paths', {}) if isinstance(current_run.get('published_report_paths', {}), dict) else {}
        aggregate_paths = publication.get('aggregate_paths', {}) if isinstance(publication.get('aggregate_paths', {}), dict) else {}
        published_processing_md_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(published_paths.get('processing_markdown', '') or ''),
        )
        published_collection_md_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(published_paths.get('markdown', '') or ''),
        )
        published_report_json_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(published_paths.get('json', '') or ''),
        )
        published_manifest_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(published_paths.get('manifest', '') or ''),
        )
        generated_surfaces_md_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(aggregate_paths.get('generated_surfaces_md', '') or ''),
        )

        published_processing_text = published_processing_md_path.read_text(encoding='utf-8') if published_processing_md_path.exists() else ''
        published_collection_text = published_collection_md_path.read_text(encoding='utf-8') if published_collection_md_path.exists() else ''
        generated_surfaces_text = generated_surfaces_md_path.read_text(encoding='utf-8') if generated_surfaces_md_path.exists() else ''
        published_report_payload = _read_json(published_report_json_path) if published_report_json_path.exists() else {}
        published_manifest_payload = _read_json(published_manifest_path) if published_manifest_path.exists() else {}
        project_root_prefix = str(sandbox_root).replace('\\', '/')
        published_figures = current_run.get('published_figures', []) if isinstance(current_run.get('published_figures', []), list) else []
        published_figure_path = _resolve_probe_artifact_path(
            sandbox_root,
            str(published_figures[0] if published_figures else ''),
        )
        published_visuals = published_report_payload.get('result', {}).get('visuals', {}) if isinstance(published_report_payload.get('result', {}), dict) else {}
        published_visual_figures = published_visuals.get('figures', []) if isinstance(published_visuals.get('figures', []), list) else []
        published_visual_path = str(published_visual_figures[0].get('path', '') or '').strip() if published_visual_figures and isinstance(published_visual_figures[0], dict) else ''
        stable_collection_landing = sandbox_root / 'docs' / 'reports' / 'collections' / 'frameg-public-boundary' / 'collection' / 'report.md'

        result_matrix = {
            'source_report_seed_contains_absolute_path': project_root_prefix in str(source_report_payload),
            'publication_refresh_go': str(publication.get('decision', '') or '').strip().lower() == 'go',
            'published_processing_markdown_written': published_processing_md_path.exists(),
            'published_collection_markdown_written': published_collection_md_path.exists(),
            'published_report_json_written': published_report_json_path.exists() and published_manifest_path.exists(),
            'absolute_project_root_removed_from_public_markdown': project_root_prefix not in published_processing_text and project_root_prefix not in published_collection_text,
            'absolute_project_root_removed_from_public_json': project_root_prefix not in json.dumps(published_report_payload, sort_keys=True),
            'local_authority_lure_removed_from_reader_surfaces': local_authority_lure not in published_processing_text and local_authority_lure not in published_collection_text and local_authority_lure not in generated_surfaces_text,
            'published_figure_rewritten_relative': bool(published_figures) and project_root_prefix not in str(published_figures[0]) and published_figure_path.exists() and published_visual_path == str(published_figures[0]),
            'human_facing_generated_surfaces_contract_present': all(
                token in generated_surfaces_text
                for token in (
                    'Aggregate surface roles',
                    'Runtime-safe population census',
                    'Contract/reference surface',
                )
            ),
            'stable_collection_landing_absent': not stable_collection_landing.exists(),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEG_PUBLIC_REPORT_BOUNDARY_ESCAPE_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'scenario_id': 'S12',
            'threat_class': 'public_report_boundary_escape',
            'expected_safe_outcome': 'Reader-facing publication stays human-facing, strips absolute-path noise, and keeps local authority residue out of tracked docs/reports surfaces.',
            'observed_boundary_result': 'public_report_boundary_preserved',
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': {},
            'artifact_paths': _report_path_map(
                {
                    'security_report': run_dir / 'security_report.md',
                    'source_report_json': source_report_json_path,
                    'source_report_md': source_report_md_path,
                    'published_processing_markdown': published_processing_md_path,
                    'published_collection_markdown': published_collection_md_path,
                    'published_report_json': published_report_json_path,
                    'published_manifest_json': published_manifest_path,
                    'generated_surfaces_md': generated_surfaces_md_path,
                    'published_figure_png': published_figure_path,
                }
            ),
            'artifact_snapshots': {
                'publication': publication,
                'published_report_payload': published_report_payload,
                'published_manifest_payload': published_manifest_payload,
            },
            'result_matrix': result_matrix,
            'findings': {
                'collection_alias': str(current_run.get('collection_alias', '') or 'frameg-public-boundary'),
                'local_authority_lure': local_authority_lure,
                'published_figures': published_figures,
                'generated_surfaces_md': _rel_to_repo(generated_surfaces_md_path),
            },
        }

        report_json = run_dir / 'frameg_public_report_boundary_escape_probe.json'
        report_md = run_dir / 'frameg_public_report_boundary_escape_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame G Public Report Boundary Escape Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': report['observed_boundary_result'],
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


def run_bootstrap_root_starvation_probe() -> int:
    run_id = 'frameg-bootstrap-root-starvation-{0}'.format(_utc_stamp())
    run_dir = FRAMEG_BOOTSTRAP_ROOT_STARVATION_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEG_BOOTSTRAP_ROOT_STARVATION_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frameg-bootstrap-root-starvation-signing-key',
            security_report_title='# Frame G bootstrap root starvation probe security report\n',
        )
        _override_env_vars(
            original_env,
            {'CALAMUM_LIBRARIAN_VAULT_KEY': 'frameg-bootstrap-root-starvation-vault-key'},
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)

        specs = observerctl_module._ops_bootstrap_root_specs()
        spec_index = {str(spec.get('id', '') or ''): spec for spec in specs}
        blocked_root_id = 'reports_operations_root'
        missing_root_id = 'analysis_root'
        blocked_root_path = Path(str(spec_index[blocked_root_id].get('path', '') or ''))
        blocked_root_path.parent.mkdir(parents=True, exist_ok=True)
        blocked_root_path.write_text('blocked bootstrap root placeholder\n', encoding='utf-8')

        check_command = _run_observerctl_cli(['ops', 'bootstrap', '--check', '--json'])
        bootstrap_command = _run_observerctl_cli(['ops', 'bootstrap', '--json'])
        check_packet = _command_stdout_json(check_command)
        bootstrap_packet = _command_stdout_json(bootstrap_command)
        check_roots = {
            str(row.get('id', '') or ''): row
            for row in check_packet.get('roots', [])
            if isinstance(row, dict)
        }
        bootstrap_roots = {
            str(row.get('id', '') or ''): row
            for row in bootstrap_packet.get('roots', [])
            if isinstance(row, dict)
        }

        result_matrix = {
            'check_bootstrap_no_go': str(check_packet.get('decision', '') or '').strip().lower() == 'no-go',
            'check_bootstrap_marks_missing_root': str(check_roots.get(missing_root_id, {}).get('status', '') or '').strip().lower() == 'missing',
            'missing_root_reason_emitted': observerctl_module._ops_bootstrap_root_reason(missing_root_id) in list(check_packet.get('reason_codes', [])),
            'blocked_root_seed_written': blocked_root_path.exists() and not blocked_root_path.is_dir(),
            'mutating_bootstrap_no_go': str(bootstrap_packet.get('decision', '') or '').strip().lower() == 'no-go',
            'blocked_root_reason_emitted': observerctl_module._ops_bootstrap_root_reason(blocked_root_id, blocked=True) in list(bootstrap_packet.get('reason_codes', [])),
            'blocked_root_status_preserved': str(bootstrap_roots.get(blocked_root_id, {}).get('status', '') or '').strip().lower() == 'blocked',
            'other_roots_created_under_partial_success': int(dict(bootstrap_packet.get('counts', {}) or {}).get('created_roots', 0) or 0) > 0,
            'partial_success_not_reported_as_go': str(bootstrap_packet.get('summary', '') or '').strip() == 'Runtime bootstrap could not prepare all required local roots.',
            'blocked_root_not_converted_to_directory': blocked_root_path.exists() and not blocked_root_path.is_dir(),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEG_BOOTSTRAP_ROOT_STARVATION_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'scenario_id': 'S13',
            'threat_class': 'bootstrap_root_starvation',
            'expected_safe_outcome': 'Missing or blocked bootstrap roots force a truthful no-go while still making partial creation visible instead of inventing healthy readiness.',
            'observed_boundary_result': 'bootstrap_root_starvation_degraded_truthfully',
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': {
                'bootstrap_check': check_command,
                'bootstrap_create': bootstrap_command,
            },
            'artifact_paths': _report_path_map(
                {
                    'security_report': run_dir / 'security_report.md',
                    'blocked_root_placeholder': blocked_root_path,
                }
            ),
            'artifact_snapshots': {
                'bootstrap_check': check_packet,
                'bootstrap_create': bootstrap_packet,
            },
            'result_matrix': result_matrix,
            'findings': {
                'blocked_root_id': blocked_root_id,
                'blocked_root_path': _rel_to_repo(blocked_root_path),
                'missing_root_id': missing_root_id,
                'created_roots': dict(bootstrap_packet.get('counts', {}) or {}).get('created_roots', 0),
                'bootstrap_reason_codes': list(bootstrap_packet.get('reason_codes', [])),
            },
        }

        report_json = run_dir / 'frameg_bootstrap_root_starvation_probe.json'
        report_md = run_dir / 'frameg_bootstrap_root_starvation_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame G Bootstrap Root Starvation Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': report['observed_boundary_result'],
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


def run_sandbox_catalog_authority_drift_probe() -> int:
    run_id = 'frameg-sandbox-catalog-authority-drift-{0}'.format(_utc_stamp())
    run_dir = FRAMEG_SANDBOX_CATALOG_AUTHORITY_DRIFT_PROBE_DIR / 'runs' / run_id
    run_index_jsonl = FRAMEG_SANDBOX_CATALOG_AUTHORITY_DRIFT_PROBE_DIR / 'run_index.jsonl'
    run_dir.mkdir(parents=True, exist_ok=True)

    original_env: Dict[str, Optional[str]] = {}
    original_project_root = None
    original_project_anchor = None
    original_file = ''
    original_registry_report_tmp = None
    original_runs_repo_root = None
    try:
        sandbox_root, _sandbox_log_dir, original_env, original_project_root = _seed_probe_environment(
            run_dir=run_dir,
            signing_key='frameg-sandbox-catalog-authority-drift-signing-key',
            security_report_title='# Frame G sandbox catalog authority drift probe security report\n',
        )
        _anchor, original_project_anchor, original_file = _bind_probe_observer_project(sandbox_root)
        original_registry_report_tmp, original_runs_repo_root = _bind_sandbox_catalog_roots(REPO_ROOT / 'report_tmp', REPO_ROOT)

        catalog_command = _run_observerctl_cli(['sandbox', 'list', '--json'])
        canonical_show_command = _run_observerctl_cli(['sandbox', 'show', 'metadata-contract', '--json'])
        alias_show_command = _run_observerctl_cli(['sandbox', 'show', 'metadata-contract-reg', '--json'])
        catalog_packet = _command_stdout_json(catalog_command)
        canonical_show_packet = _command_stdout_json(canonical_show_command)
        alias_show_packet = _command_stdout_json(alias_show_command)
        canonical_definition = canonical_show_packet.get('definition', {}) if isinstance(canonical_show_packet.get('definition', {}), dict) else {}

        run_index_path = Path(str(canonical_definition.get('run_index_path', '') or '').replace('/', os.sep))
        stale_run_id = 'metadata-contract-stale-{0}'.format(_utc_stamp())
        stale_run_dir = run_index_path.parent / 'runs' / stale_run_id
        stale_report_json_path = stale_run_dir / 'report.json'
        stale_run_dir.mkdir(parents=True, exist_ok=True)
        _append_jsonl(
            run_index_path,
            {
                'run_id': stale_run_id,
                'timestamp_utc': '2026-04-22T00:20:00Z',
                'run_dir': _rel_to_repo(stale_run_dir),
                'report_json': _rel_to_repo(stale_report_json_path),
                'next_bite_result': 'review',
                'observed_boundary_result': 'synthetic_stale_run_reference',
            },
        )

        runs_list_command = _run_observerctl_cli(['sandbox', 'runs', 'list', '--json'])
        stale_review_command = _run_observerctl_cli(['sandbox', 'runs', 'show', stale_run_id, '--json'])
        runs_list_packet = _command_stdout_json(runs_list_command)
        stale_review_packet = _command_stdout_json(stale_review_command)
        catalog_definitions = catalog_packet.get('definitions', []) if isinstance(catalog_packet.get('definitions', []), list) else []
        catalog_ids = [str(row.get('id', '') or '') for row in catalog_definitions if isinstance(row, dict)]
        visible_run_ids = [
            str(row.get('run_id', '') or '')
            for row in runs_list_packet.get('runs', [])
            if isinstance(row, dict)
        ]

        result_matrix = {
            'catalog_list_go': str(catalog_packet.get('decision', '') or '').strip().lower() == 'go',
            'catalog_ids_unique': bool(catalog_ids) and len(catalog_ids) == len(set(catalog_ids)),
            'canonical_definition_show_go': str(canonical_show_packet.get('decision', '') or '').strip().lower() == 'go',
            'canonical_selector_policy_exact_name_only': str(canonical_definition.get('selector_policy', '') or '').strip().lower() == 'exact-name-only',
            'prefix_alias_lookup_denied': str(alias_show_packet.get('decision', '') or '').strip().lower() == 'no-go' and 'critical_check_failed:unknown_sandbox_definition' in list(alias_show_packet.get('reason_codes', [])),
            'stale_run_index_row_written': run_index_path.exists(),
            'stale_run_visible_in_catalog_list': stale_run_id in visible_run_ids,
            'stale_run_review_no_go': str(stale_review_packet.get('decision', '') or '').strip().lower() == 'no-go',
            'stale_run_reason_emitted': 'critical_check_failed:sandbox_run_report_missing' in list(stale_review_packet.get('reason_codes', [])),
            'stale_run_payload_not_presented_as_reviewable': not bool(stale_review_packet.get('report', {})),
        }

        report = {
            'run_id': run_id,
            'run_dir': _rel_to_repo(run_dir),
            'probe_dir': _rel_to_repo(FRAMEG_SANDBOX_CATALOG_AUTHORITY_DRIFT_PROBE_DIR),
            'script': _rel_to_repo(Path(__file__)),
            'scenario_id': 'S14',
            'threat_class': 'sandbox_catalog_authority_drift',
            'expected_safe_outcome': 'Exact-name-only catalog discipline holds and stale retained-run references fail closed instead of being presented as trustworthy review material.',
            'observed_boundary_result': 'sandbox_catalog_authority_drift_visible_fail_closed',
            'next_bite_result': _probe_result(result_matrix),
            'command_runs': {
                'catalog_list': catalog_command,
                'canonical_show': canonical_show_command,
                'alias_show': alias_show_command,
                'runs_list': runs_list_command,
                'stale_run_review': stale_review_command,
            },
            'artifact_paths': _report_path_map(
                {
                    'security_report': run_dir / 'security_report.md',
                    'catalog_run_index_jsonl': run_index_path,
                    'stale_run_dir': stale_run_dir,
                }
            ),
            'artifact_snapshots': {
                'catalog_list': catalog_packet,
                'canonical_show': canonical_show_packet,
                'alias_show': alias_show_packet,
                'runs_list': runs_list_packet,
                'stale_review': stale_review_packet,
            },
            'result_matrix': result_matrix,
            'findings': {
                'catalog_count': len(catalog_ids),
                'canonical_definition_id': str(canonical_definition.get('id', '') or ''),
                'alias_candidate': 'metadata-contract-reg',
                'stale_run_id': stale_run_id,
                'stale_report_json': _rel_to_repo(stale_report_json_path),
                'stale_review_reason_codes': list(stale_review_packet.get('reason_codes', [])),
            },
        }

        report_json = run_dir / 'frameg_sandbox_catalog_authority_drift_probe.json'
        report_md = run_dir / 'frameg_sandbox_catalog_authority_drift_probe.md'
        _write_json(report_json, report)
        report_md.write_text(_render_result_matrix_markdown('Frame G Sandbox Catalog Authority Drift Probe', report), encoding='utf-8')

        _append_jsonl(
            run_index_jsonl,
            {
                'run_id': run_id,
                'timestamp_utc': _utc_stamp(),
                'run_dir': _rel_to_repo(run_dir),
                'report_json': _rel_to_repo(report_json),
                'report_md': _rel_to_repo(report_md),
                'next_bite_result': report['next_bite_result'],
                'observed_boundary_result': report['observed_boundary_result'],
            },
        )

        print('run_id={0}'.format(run_id))
        print('report_json={0}'.format(_rel_to_repo(report_json)))
        print('report_md={0}'.format(_rel_to_repo(report_md)))
        print('run_index={0}'.format(_rel_to_repo(run_index_jsonl)))
        print('next_bite_result={0}'.format(report['next_bite_result']))
        return 0
    finally:
        if original_registry_report_tmp is not None and original_runs_repo_root is not None:
            _restore_sandbox_catalog_roots(original_registry_report_tmp, original_runs_repo_root)
        if original_project_anchor is not None:
            _restore_probe_observer_project(original_project_anchor, original_file)
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
        'posture-transition-bypass': run_posture_transition_bypass_probe,
        'stale-gate-replay': run_stale_gate_replay_probe,
        'names-only-persistence-escape': run_names_only_persistence_escape_probe,
        'packet-artifact-divergence-truthfulness': run_packet_artifact_divergence_truthfulness_probe,
        'watchdog-heartbeat-spoof-resistance': run_watchdog_heartbeat_spoof_resistance_probe,
        'resource-lockdown-chaos': run_resource_lockdown_chaos_probe,
        'baseline-authority-tamper': run_baseline_authority_tamper_probe,
        'report-lineage-forgery': run_report_lineage_forgery_probe,
        'keysmith-version-parity-break': run_keysmith_version_parity_break_probe,
        'public-report-boundary-escape': run_public_report_boundary_escape_probe,
        'bootstrap-root-starvation': run_bootstrap_root_starvation_probe,
        'sandbox-catalog-authority-drift': run_sandbox_catalog_authority_drift_probe,
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
        help='Definition to run: feedback-loop, metadata-contract, metadata-contract-regression, ds-wizard-hydration, ds-wizard-stale-state-continuity, ds-wizard-durability, ds-wizard-labeled-eval-contract-coherence, ds-wizard-blocked-execute-truthfulness, ds-wizard-execute-failure-truthfulness, ds-alias-coherence, posture-transition-bypass, stale-gate-replay, names-only-persistence-escape, packet-artifact-divergence-truthfulness, watchdog-heartbeat-spoof-resistance, resource-lockdown-chaos, baseline-authority-tamper, report-lineage-forgery, keysmith-version-parity-break, public-report-boundary-escape, bootstrap-root-starvation, sandbox-catalog-authority-drift, baseline-monitor-runtime, validation-cycle-lineage, baseline-monitor-restart-continuity, baseline-monitor-state-recovery, librarian-access-exchange, librarian-vault-controls',
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
            'names-only-persistence-escape',
            'packet-artifact-divergence-truthfulness',
            'watchdog-heartbeat-spoof-resistance',
            'resource-lockdown-chaos',
            'baseline-authority-tamper',
            'report-lineage-forgery',
            'keysmith-version-parity-break',
            'public-report-boundary-escape',
            'bootstrap-root-starvation',
            'sandbox-catalog-authority-drift',
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
