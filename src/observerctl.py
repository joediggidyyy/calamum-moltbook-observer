"""observerctl: standalone observer-scoped runtime operations CLI.

Normative constraints:
- observerctl is an observer runtime/security-operations surface.
- It must not depend on CodeSentinel runtime process orchestration.
- Output is names-only, deterministic, and fail-closed compatible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import psutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from calamum_config import get_calamum_control_dir, get_calamum_data_dir, get_calamum_health_dir


MODES = ('watch', 'canary', 'live', 'honeypot')
SOURCES = ('sim', 'real')
REASON_MAP = {
    'critical_check_failed:heartbeat.watchdog': 'critical_check_failed:watchdog_heartbeat_stale',
    'critical_check_failed:heartbeat.observer': 'critical_check_failed:observer_heartbeat_stale',
}
STATE_FILE = 'observerctl_state.json'
LAST_GATE_FILE = 'observerctl_last_gate.json'
POLICY_FILE = 'observerctl_policy.json'
ACK_LOG_FILE = 'watchdog_ack.jsonl'
RUN_CONTEXT_FILE = 'observerctl_run_context.json'
WATCHDOG_POSTURE_FILE = 'watchdog_posture_state.json'
WATCHDOG_RESOURCE_FILE = 'watchdog_resource_state.json'
GATE_PACKET_MAX_AGE_SEC = float(os.getenv('CALAMUM_GATE_PACKET_MAX_AGE_SEC', '300'))
AGENT_PID_FILE = 'calamum_agent.pid'


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_env_presence(name: str) -> bool:
    return bool((os.getenv(name) or '').strip())


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _normalize_source(source: str) -> str:
    s = str(source or '').strip().lower()
    return s if s in SOURCES else 'sim'


def _posture_for_mode(mode: str) -> str:
    return 'lockdown' if mode in ('live', 'honeypot') else 'isolation'


def _control_file(name: str) -> Path:
    return get_calamum_control_dir() / name


def _observer_metrics_path(source: str, mode: str) -> Path:
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'
    return get_calamum_data_dir() / 'observer_derived' / src / m / 'moltbook_metrics.jsonl'


def _load_json_file(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                return raw
    except Exception:
        pass
    return dict(default)


def _write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def _state_default() -> Dict[str, Any]:
    return {
        'source': _normalize_source(os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim')),
        'mode': str((os.getenv('CALAMUM_OPS_MODE', 'watch') or 'watch')).strip().lower(),
        'updated_at_utc': _utc_now(),
    }


def _load_state() -> Dict[str, Any]:
    state = _load_json_file(_control_file(STATE_FILE), _state_default())
    mode = str(state.get('mode', 'watch')).strip().lower()
    if mode not in MODES:
        mode = 'watch'
    source = _normalize_source(str(state.get('source', 'sim')))
    state['mode'] = mode
    state['source'] = source
    return state


def _save_state(source: str, mode: str) -> Dict[str, Any]:
    payload = {
        'source': _normalize_source(source),
        'mode': str(mode).strip().lower(),
        'updated_at_utc': _utc_now(),
    }
    _write_json_file(_control_file(STATE_FILE), payload)
    return payload


def _policy_default() -> Dict[str, Any]:
    return {
        'policy_profile': 'default',
        'allowed_modes': list(MODES),
        'source_axis': list(SOURCES),
        'forbidden_transitions': [],
        'lockdown_required_modes': ['live', 'honeypot'],
        'isolation_required_modes': ['watch', 'canary'],
    }


def _load_policy() -> Dict[str, Any]:
    policy = _load_json_file(_control_file(POLICY_FILE), _policy_default())
    if not isinstance(policy.get('allowed_modes'), list):
        policy['allowed_modes'] = list(MODES)
    if not isinstance(policy.get('forbidden_transitions'), list):
        policy['forbidden_transitions'] = []
    return policy


def _transition_id(from_source: str, from_mode: str, to_source: str, to_mode: str) -> str:
    return '{0}:{1}->{2}:{3}'.format(from_source, from_mode, to_source, to_mode)


def _file_age_seconds(path: Path) -> Optional[float]:
    try:
        return max(0.0, time.time() - float(path.stat().st_mtime))
    except Exception:
        return None


def _check_heartbeat(path: Path, max_age_sec: float) -> Dict[str, Any]:
    exists = path.exists()
    age_s = _file_age_seconds(path) if exists else None
    status = 'ok'
    if not exists:
        status = 'err'
    elif age_s is None:
        status = 'warn'
    elif age_s > float(max_age_sec):
        status = 'err'
    return {
        'path': str(path),
        'exists': exists,
        'age_seconds': None if age_s is None else round(float(age_s), 3),
        'max_age_seconds': float(max_age_sec),
        'status': status,
    }


def _to_float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _parse_utc_iso8601(value: Any) -> Optional[datetime]:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _is_gate_packet_fresh(packet: Dict[str, Any], max_age_sec: float) -> bool:
    ts = _parse_utc_iso8601(packet.get('timestamp_utc'))
    if ts is None:
        return False
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age >= 0.0 and age <= float(max_age_sec)


def _is_resolvable_report_ref(ref: str) -> bool:
    target = str(ref or '').strip()
    if not target:
        return False
    path = Path(target)
    if not path.is_absolute():
        path = _project_root() / target
    return path.exists()


def _load_run_context() -> Dict[str, Any]:
    return _load_json_file(_control_file(RUN_CONTEXT_FILE), {})


def _agent_pid_path() -> Path:
    return _project_root() / AGENT_PID_FILE


def _read_pid(path: Path) -> Optional[int]:
    try:
        if not path.exists():
            return None
        raw = str(path.read_text(encoding='utf-8')).strip()
        if not raw or not raw.isdigit():
            return None
        return int(raw)
    except Exception:
        return None


def _pid_alive(pid: Optional[int]) -> bool:
    if pid is None or pid <= 0:
        return False

    pid_i = int(pid)

    # Primary check: psutil is cross-platform and reliable on Windows where
    # os.kill(pid, 0) can report false negatives.
    try:
        proc = psutil.Process(pid_i)
        if not proc.is_running():
            return False
        try:
            if proc.status() == psutil.STATUS_ZOMBIE:
                return False
        except Exception:
            # Status may not be available on all platforms; treat as alive if running.
            pass
        return True
    except psutil.NoSuchProcess:
        return False
    except Exception:
        # Fall back to os.kill for environments where psutil cannot inspect.
        pass

    try:
        os.kill(pid_i, 0)
        return True
    except Exception:
        return False


def _terminate_pid_best_effort(pid: Optional[int], graceful_timeout_sec: float = 2.0) -> bool:
    if pid is None or int(pid) <= 0:
        return True
    pid_i = int(pid)
    try:
        proc = psutil.Process(pid_i)
    except Exception:
        return not _pid_alive(pid_i)

    try:
        proc.terminate()
    except Exception:
        pass

    deadline = time.time() + max(0.0, float(graceful_timeout_sec))
    while time.time() <= deadline:
        if not _pid_alive(pid_i):
            return True
        time.sleep(0.1)

    try:
        proc.kill()
    except Exception:
        pass

    deadline = time.time() + 1.0
    while time.time() <= deadline:
        if not _pid_alive(pid_i):
            return True
        time.sleep(0.1)
    return not _pid_alive(pid_i)


def _runtime_observer_status(max_age_sec: float = 60.0) -> Dict[str, Any]:
    hb = _check_heartbeat(get_calamum_health_dir() / 'calamum_observer.heartbeat', max_age_sec=max_age_sec)
    pid_path = _agent_pid_path()
    pid = _read_pid(pid_path)
    pid_alive = _pid_alive(pid)

    signal_path = _control_file('kill.signal.json')
    signal_pending = False
    if signal_path.exists():
        signal_doc = _load_json_file(signal_path, {})
        signal_pending = isinstance(signal_doc, dict) and (not bool(signal_doc.get('handled_at')))

    if hb.get('status') == 'ok' and pid_alive:
        state = 'active'
    elif hb.get('status') == 'ok' or pid_alive:
        state = 'degraded'
    else:
        state = 'stopped'

    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'runtime_label': 'observer',
        'state': state,
        'heartbeat': hb,
        'pid': {
            'path': str(pid_path).replace('\\', '/'),
            'value': pid,
            'alive': pid_alive,
        },
        'pending_stop_signal': bool(signal_pending),
    }


def _ops_runtime_status() -> Dict[str, Any]:
    return _runtime_observer_status()


def _ops_runtime_stop(timeout_sec: float = 8.0) -> Dict[str, Any]:
    payload = {
        'ts': _utc_now(),
        'signal': 'kill',
        'requested_by': 'observerctl',
        'payload': {'requested_at': _utc_now()},
    }
    signal_path = _control_file('kill.signal.json')
    _write_json_file(signal_path, payload)

    pid_path = _agent_pid_path()
    pid_value = _read_pid(pid_path)
    deadline = time.time() + max(0.0, float(timeout_sec))
    while time.time() <= deadline:
        if not _pid_alive(pid_value):
            break
        time.sleep(0.25)

    stopped_cleanly = not _pid_alive(pid_value)
    escalated_terminate = False
    if not stopped_cleanly:
        escalated_terminate = True
        stopped_cleanly = _terminate_pid_best_effort(pid_value, graceful_timeout_sec=2.0)

    if not _pid_alive(pid_value):
        try:
            if pid_path.exists():
                pid_path.unlink()
        except Exception:
            pass

    if stopped_cleanly:
        try:
            hb_path = get_calamum_health_dir() / 'calamum_observer.heartbeat'
            if hb_path.exists():
                hb_path.unlink()
        except Exception:
            pass
        try:
            signal_doc = _load_json_file(signal_path, {})
            if isinstance(signal_doc, dict) and not signal_doc.get('handled_at'):
                signal_doc['handled_at'] = _utc_now()
                signal_doc['handled_by'] = 'observerctl'
                _write_json_file(signal_path, signal_doc)
        except Exception:
            pass

    reasons: List[str] = []
    if not stopped_cleanly:
        reasons.append('critical_check_failed:runtime_stop_timeout')

    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if stopped_cleanly else 'no-go',
        'action': 'runtime-stop',
        'reason_codes': reasons,
        'signal_path': str(signal_path).replace('\\', '/'),
        'stop_timeout_sec': float(timeout_sec),
        'observer_pid': pid_value,
        'stopped_cleanly': bool(stopped_cleanly),
        'escalated_terminate': bool(escalated_terminate),
    }


def _ops_runtime_start(source: str, mode: str, interval_sec: float, timeout_sec: float) -> Dict[str, Any]:
    launcher_path = _project_root() / 'launch_ghost_console.ps1'
    if not launcher_path.exists():
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'runtime-start',
            'reason_codes': ['critical_check_failed:launcher_missing'],
            'launcher_path': str(launcher_path).replace('\\', '/'),
        }

    source_norm = _normalize_source(source)
    mode_norm = str(mode or 'watch').strip().lower()
    if mode_norm not in MODES:
        mode_norm = 'watch'

    env = os.environ.copy()
    env['CALAMUM_SKIP_BROWSER'] = '1'
    env['CALAMUM_GUI_AUTOSTART_OBSERVER'] = '1'
    env['CALAMUM_MOLTBOOK_SOURCE'] = source_norm
    env['CALAMUM_OPS_MODE'] = mode_norm
    env['CALAMUM_AGENT_INTERVAL_SEC'] = str(interval_sec)

    cmd = [
        'powershell.exe',
        '-NoProfile',
        '-NonInteractive',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        str(launcher_path),
    ]

    # Non-interactive launch semantics: start detached, then perform a short
    # bounded readiness probe so terminals return promptly.
    timeout_s = max(0.0, float(timeout_sec))
    creationflags = 0
    if os.name == 'nt':
        creationflags = int(getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)) | int(getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    start_stdout_path = _project_root() / 'logs' / 'observerctl_runtime_start.stdout.log'
    start_stderr_path = _project_root() / 'logs' / 'observerctl_runtime_start.stderr.log'
    start_stdout_path.parent.mkdir(parents=True, exist_ok=True)

    out_f = None
    err_f = None
    try:
        out_f = start_stdout_path.open('a', encoding='utf-8')
        err_f = start_stderr_path.open('a', encoding='utf-8')
    except Exception:
        out_f = None
        err_f = None

    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(_project_root()),
            stdin=subprocess.DEVNULL,
            stdout=(out_f if out_f is not None else subprocess.DEVNULL),
            stderr=(err_f if err_f is not None else subprocess.DEVNULL),
            creationflags=creationflags,
        )
    except Exception:
        try:
            if out_f is not None:
                out_f.close()
            if err_f is not None:
                err_f.close()
        except Exception:
            pass
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'runtime-start',
            'reason_codes': ['critical_check_failed:launcher_exec_failed'],
            'launcher_path': str(launcher_path).replace('\\', '/'),
        }

    try:
        if out_f is not None:
            out_f.close()
        if err_f is not None:
            err_f.close()
    except Exception:
        pass

    if timeout_s <= 0.0:
        status = _runtime_observer_status()
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'runtime-start',
            'reason_codes': [],
            'launcher_path': str(launcher_path).replace('\\', '/'),
            'launcher_pid': int(getattr(proc, 'pid', 0) or 0),
            'launcher_stdout_log': str(start_stdout_path).replace('\\', '/'),
            'launcher_stderr_log': str(start_stderr_path).replace('\\', '/'),
            'startup_verified': bool(str(status.get('state', '')) == 'active'),
            'state': status.get('state', 'degraded'),
            'pid': status.get('pid', {}),
        }

    deadline = time.time() + timeout_s
    while time.time() <= deadline:
        status = _runtime_observer_status()
        if str(status.get('state', '')) == 'active':
            return {
                'timestamp_utc': _utc_now(),
                'runtime_cli_surface': 'observerctl',
                'decision': 'go',
                'action': 'runtime-start',
                'reason_codes': [],
                'launcher_path': str(launcher_path).replace('\\', '/'),
                'launcher_pid': int(getattr(proc, 'pid', 0) or 0),
                'launcher_stdout_log': str(start_stdout_path).replace('\\', '/'),
                'launcher_stderr_log': str(start_stderr_path).replace('\\', '/'),
                'startup_verified': True,
                'state': status.get('state', 'degraded'),
                'pid': status.get('pid', {}),
            }
        time.sleep(0.25)

    final_status = _runtime_observer_status()
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'runtime-start',
        'reason_codes': [],
        'advisory_reason_codes': ['startup_pending:observer_not_active_within_probe_window'],
        'launcher_path': str(launcher_path).replace('\\', '/'),
        'launcher_pid': int(getattr(proc, 'pid', 0) or 0),
        'launcher_stdout_log': str(start_stdout_path).replace('\\', '/'),
        'launcher_stderr_log': str(start_stderr_path).replace('\\', '/'),
        'startup_verified': False,
        'state': final_status.get('state', 'degraded'),
        'pid': final_status.get('pid', {}),
    }


def _resource_thresholds_for_posture(posture: str) -> Dict[str, float]:
    p = str(posture or '').strip().lower()
    if p == 'lockdown':
        # Honeypot-grade lockdown standard applies equally to live + honeypot.
        return {
            'cpu_warn_abs': 60.0,
            'cpu_critical_abs': 75.0,
            'ram_warn_abs': 72.0,
            'ram_critical_abs': 85.0,
            'cpu_rel_delta': 12.0,
            'ram_rel_delta': 10.0,
            'score_critical': 0.70,
            'sampling_fresh_max_age': 10.0,
        }
    # Isolation profile (watch/canary)
    return {
        'cpu_warn_abs': 70.0,
        'cpu_critical_abs': 85.0,
        'ram_warn_abs': 78.0,
        'ram_critical_abs': 90.0,
        'cpu_rel_delta': 15.0,
        'ram_rel_delta': 12.0,
        'score_critical': 0.70,
        'sampling_fresh_max_age': 30.0,
    }


def _resolve_run_linkage(mode: str, event: str) -> Dict[str, str]:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    ctx = _load_run_context()
    run_id_env = str(os.getenv('CALAMUM_RUN_ID', '') or '').strip()
    run_id = run_id_env or str(ctx.get('run_id', '') or '').strip() or 'observerctl-{event}-{ts}'.format(
        event=str(event).strip().lower().replace(' ', '-'),
        ts=ts,
    )

    posture_trigger_id_env = str(os.getenv('CALAMUM_POSTURE_TRIGGER_ID', '') or '').strip()
    posture_trigger_id = posture_trigger_id_env or str(ctx.get('posture_trigger_id', '') or '').strip() or 'pt-{mode}-{ts}'.format(
        mode=mode,
        ts=ts,
    )

    security_report_ref_env = str(os.getenv('CALAMUM_SECURITY_REPORT_REF', '') or '').strip()
    security_report_ref = security_report_ref_env or str(ctx.get('security_report_ref', '') or '').strip()

    return {
        'run_id': run_id,
        'posture_trigger_id': posture_trigger_id,
        'posture_trigger': _posture_for_mode(mode),
        'security_report_ref': security_report_ref,
    }


def _make_run_linkage(mode: str, event: str) -> Dict[str, str]:
    return _resolve_run_linkage(mode=mode, event=event)


def collect_runtime_status(source: str = 'sim') -> Dict[str, Any]:
    source_norm = _normalize_source(source)
    state = _load_state()
    mode = str(state.get('mode', 'watch'))
    health_dir = get_calamum_health_dir()
    data_dir = get_calamum_data_dir()
    control_dir = get_calamum_control_dir()

    hb_watchdog = health_dir / 'calamum_ops_watchdog.heartbeat'
    hb_observer = health_dir / 'calamum_observer.heartbeat'
    hb_librarian = health_dir / 'calamum_librarian.heartbeat'
    store_packet = _store_integrity_packet(mode)
    check_watchdog = _check_heartbeat(hb_watchdog, max_age_sec=45.0)
    check_observer = _check_heartbeat(hb_observer, max_age_sec=60.0)
    check_librarian = _check_heartbeat(hb_librarian, max_age_sec=120.0)

    signing_ok = _read_env_presence('CALAMUM_DATA_SIGNING_KEY') or _read_env_presence('CALAMUM_ALLOW_DEV_SIGNING_KEY')
    checks: Dict[str, Dict[str, Any]] = {
        'paths.health_dir': {
            'path': str(health_dir),
            'exists': health_dir.exists(),
            'status': 'ok' if health_dir.exists() else 'err',
        },
        'paths.data_dir': {
            'path': str(data_dir),
            'exists': data_dir.exists(),
            'status': 'ok' if data_dir.exists() else 'warn',
        },
        'paths.control_dir': {
            'path': str(control_dir),
            'exists': control_dir.exists(),
            'status': 'ok' if control_dir.exists() else 'warn',
        },
        'heartbeat.watchdog': check_watchdog,
        'heartbeat.observer': check_observer,
        'heartbeat.librarian': check_librarian,
        'env.signing_key': {
            'names': ['CALAMUM_DATA_SIGNING_KEY', 'CALAMUM_ALLOW_DEV_SIGNING_KEY'],
            'present': bool(signing_ok),
            'status': 'ok' if signing_ok else 'err',
        },
    }

    if source_norm == 'real':
        live_key_ok = _read_env_presence('MOLTBOOK_API_KEY')
        checks['env.moltbook_api_key'] = {
            'names': ['MOLTBOOK_API_KEY'],
            'present': bool(live_key_ok),
            'status': 'ok' if live_key_ok else 'err',
        }

    current_metrics = _observer_metrics_path(source_norm, mode)
    checks['data.observer_metrics_current'] = {
        'path': str(current_metrics),
        'exists': current_metrics.exists(),
        'status': 'ok' if current_metrics.exists() else 'warn',
        'scope': {'source': source_norm, 'mode': mode},
    }
    checks['store.pointer_consistent'] = {
        'active_store_pointer': store_packet.get('active_store_pointer', ''),
        'status': 'ok' if store_packet.get('status') == 'ok' else 'err',
    }
    checks['store.integrity_ok'] = {
        'issues': list(store_packet.get('issues', [])),
        'archive_count': int(store_packet.get('archive_count', 0)),
        'compacted_count': int(store_packet.get('compacted_count', 0)),
        'retention_state': str(store_packet.get('retention_state', 'normal')),
        'status': 'ok' if store_packet.get('status') == 'ok' else 'err',
    }

    posture_doc = _load_json_file(_control_file(WATCHDOG_POSTURE_FILE), {})
    posture_value = str(posture_doc.get('posture_trigger', '') or '').strip().lower()
    hb_interval = _to_float_or_none(posture_doc.get('heartbeat_interval_seconds'))
    baseline_interval = _to_float_or_none(posture_doc.get('baseline_validation_interval_seconds'))

    checks['watchdog.trigger_posture'] = {
        'path': str(_control_file(WATCHDOG_POSTURE_FILE)),
        'posture_trigger': posture_value,
        'status': 'ok' if posture_value in ('isolation', 'lockdown') else 'err',
    }
    checks['watchdog.heartbeat_interval_seconds'] = {
        'value': hb_interval,
        'status': 'ok' if hb_interval is not None else 'err',
    }
    checks['watchdog.baseline_validation_interval_seconds'] = {
        'value': baseline_interval,
        'status': 'ok' if baseline_interval is not None else 'err',
    }

    resource_doc = _load_json_file(_control_file(WATCHDOG_RESOURCE_FILE), {})
    cpu_now = _to_float_or_none(resource_doc.get('cpu_pct_now'))
    ram_now = _to_float_or_none(resource_doc.get('ram_pct_now'))
    cpu_p95 = _to_float_or_none(resource_doc.get('cpu_p95_15m'))
    ram_p95 = _to_float_or_none(resource_doc.get('ram_p95_15m'))
    spike_score = _to_float_or_none(resource_doc.get('resource_spike_score'))
    sample_age_s = _to_float_or_none(resource_doc.get('sample_age_seconds'))

    checks['watchdog.resource_metrics'] = {
        'path': str(_control_file(WATCHDOG_RESOURCE_FILE)),
        'cpu_pct_now': cpu_now,
        'ram_pct_now': ram_now,
        'cpu_p95_15m': cpu_p95,
        'ram_p95_15m': ram_p95,
        'resource_spike_score': spike_score,
        'sample_age_seconds': sample_age_s,
        'status': 'ok' if all(v is not None for v in [cpu_now, ram_now, cpu_p95, ram_p95, spike_score, sample_age_s]) else 'err',
    }

    return {
        'timestamp_utc': _utc_now(),
        'runtime_label': 'observer',
        'runtime_cli_surface': 'observerctl',
        'source': source_norm,
        'state_source': str(state.get('source', source_norm)),
        'mode': mode,
        'checks': checks,
    }


def evaluate_gate_decision(status_packet: Dict[str, Any], target_mode: Optional[str] = None) -> Dict[str, Any]:
    checks = status_packet.get('checks', {}) if isinstance(status_packet, dict) else {}
    source = _normalize_source(str(status_packet.get('source', 'sim')))
    from_source = _normalize_source(str(status_packet.get('state_source', source)))
    mode = str(status_packet.get('mode', 'watch')).strip().lower()
    to_mode = str(target_mode or mode).strip().lower()
    if to_mode not in MODES:
        return {
            'timestamp_utc': _utc_now(),
            'decision': 'no-go',
            'reason_codes': ['policy_denied:target_mode_unsupported'],
            'critical_checks': [],
            'from_state': '{0}:{1}'.format(from_source, mode),
            'to_state': '{0}:{1}'.format(source, to_mode),
            'profile': 'GP-X',
        }

    reasons: List[str] = []
    advisories: List[str] = []
    if from_source == source and mode == to_mode:
        reasons.append('policy_denied:no_op_transition')

    policy = _load_policy()
    forbidden = set(str(x) for x in list(policy.get('forbidden_transitions', [])))
    transition_key = _transition_id(from_source, mode, source, to_mode)
    if transition_key in forbidden:
        reasons.append('policy_denied:transition_forbidden')

    critical_keys = [
        'paths.health_dir',
        'heartbeat.watchdog',
        'heartbeat.observer',
        'env.signing_key',
        'store.pointer_consistent',
        'store.integrity_ok',
    ]
    if source == 'real':
        critical_keys.append('env.moltbook_api_key')

    for key in critical_keys:
        row = checks.get(key, {}) if isinstance(checks, dict) else {}
        state = str(row.get('status', 'err')).lower()
        if state != 'ok':
            reasons.append('critical_check_failed:{0}'.format(key))

    linkage = _make_run_linkage(to_mode, event='gate')
    posture_required = _posture_for_mode(to_mode)
    runtime_posture = str((checks.get('watchdog.trigger_posture') or {}).get('posture_trigger', '')).strip().lower()
    if runtime_posture != posture_required:
        reasons.append('critical_check_failed:watchdog_trigger_posture_invalid')

    # C20 run linkage reference must exist and resolve to a real artifact path (names-only).
    if not linkage['security_report_ref'] or not _is_resolvable_report_ref(str(linkage.get('security_report_ref', ''))):
        reasons.append('critical_check_failed:run_security_report_missing')

    # C21/C22 lockdown checks for live/honeypot target.
    if posture_required == 'lockdown':
        hb_interval = _to_float_or_none((checks.get('watchdog.heartbeat_interval_seconds') or {}).get('value'))
        baseline_interval = _to_float_or_none((checks.get('watchdog.baseline_validation_interval_seconds') or {}).get('value'))
        hb_escalated = hb_interval is not None and 3.0 <= hb_interval <= 5.0
        baseline_escalated = baseline_interval is not None and 30.0 <= baseline_interval <= 60.0
        if not hb_escalated:
            reasons.append('critical_check_failed:lockdown_heartbeat_rate_not_escalated')
        if not baseline_escalated:
            reasons.append('critical_check_failed:lockdown_baseline_rate_not_escalated')

    resource_metrics = checks.get('watchdog.resource_metrics') or {}
    cpu_now = _to_float_or_none(resource_metrics.get('cpu_pct_now'))
    ram_now = _to_float_or_none(resource_metrics.get('ram_pct_now'))
    cpu_p95 = _to_float_or_none(resource_metrics.get('cpu_p95_15m'))
    ram_p95 = _to_float_or_none(resource_metrics.get('ram_p95_15m'))
    spike_score = _to_float_or_none(resource_metrics.get('resource_spike_score'))
    sample_age_s = _to_float_or_none(resource_metrics.get('sample_age_seconds'))
    thresholds = _resource_thresholds_for_posture(posture_required)

    baseline_valid = all(v is not None for v in [cpu_now, ram_now, cpu_p95, ram_p95, spike_score, sample_age_s])
    if not baseline_valid:
        reasons.append('critical_check_failed:resource_baseline_invalid')
    else:
        sample_fresh = float(sample_age_s) <= float(thresholds['sampling_fresh_max_age'])
        if not sample_fresh:
            reasons.append('critical_check_failed:resource_sampling_stale')

        cpu_warn = float(cpu_now) >= float(thresholds['cpu_warn_abs']) or float(cpu_now) > (float(cpu_p95) + float(thresholds['cpu_rel_delta']))
        ram_warn = float(ram_now) >= float(thresholds['ram_warn_abs']) or float(ram_now) > (float(ram_p95) + float(thresholds['ram_rel_delta']))
        score_critical = float(spike_score) >= float(thresholds['score_critical'])
        cpu_critical = float(cpu_now) >= float(thresholds['cpu_critical_abs'])
        ram_critical = float(ram_now) >= float(thresholds['ram_critical_abs'])

        if cpu_warn:
            advisories.append('major_check_failed:cpu_spike_detected')
        if ram_warn:
            advisories.append('major_check_failed:ram_spike_detected')
        if score_critical:
            advisories.append('major_check_failed:resource_spike_score_elevated')

        if posture_required == 'lockdown':
            if cpu_critical or (float(cpu_now) > (float(cpu_p95) + float(thresholds['cpu_rel_delta']))):
                reasons.append('critical_check_failed:cpu_spike_lockdown')
            if ram_critical or (float(ram_now) > (float(ram_p95) + float(thresholds['ram_rel_delta']))):
                reasons.append('critical_check_failed:ram_spike_lockdown')
            if score_critical:
                reasons.append('critical_check_failed:resource_spike_score_critical')

    normalized = [REASON_MAP.get(r, r) for r in reasons]
    deduped = []
    for r in normalized:
        if r not in deduped:
            deduped.append(r)

    profile = 'GP-4' if to_mode in ('live', 'honeypot') or source == 'real' else 'GP-1'
    decision = 'go' if not deduped else 'no-go'
    packet = {
        'timestamp_utc': _utc_now(),
        'decision': decision,
        'reason_codes': deduped,
        'critical_checks': critical_keys,
        'from_state': '{0}:{1}'.format(from_source, mode),
        'to_state': '{0}:{1}'.format(source, to_mode),
        'profile': profile,
        'runtime_label': 'observer',
        'runtime_cli_surface': 'observerctl',
        'advisory_reason_codes': advisories,
    }
    packet.update(linkage)
    return packet


def build_evidence_pack(status_packet: Dict[str, Any], gate_packet: Dict[str, Any], event: str = 'manual') -> Dict[str, Any]:
    checks = status_packet.get('checks', {}) if isinstance(status_packet, dict) else {}
    evidence_refs = [
        str((checks.get('heartbeat.watchdog') or {}).get('path', '')),
        str((checks.get('heartbeat.observer') or {}).get('path', '')),
        str((checks.get('heartbeat.librarian') or {}).get('path', '')),
    ]
    evidence_refs = [p for p in evidence_refs if p]
    store_ref = str((checks.get('store.pointer_consistent') or {}).get('active_store_pointer', '')).strip()
    if store_ref:
        evidence_refs.append(store_ref)

    methodology = {
        'sampling_strategy': 'names-only runtime posture sampling from health/data/control artifacts',
        'runtime_constraints': [
            'standalone observer scope only',
            'no CodeSentinel runtime process dependency',
            'fail-closed gate semantics',
        ],
        'data_handling_invariants': [
            'no secret value output',
            'path/presence/age-based evidence only',
            'deterministic JSON packet schemas',
        ],
        'failure_modes': [
            'watchdog_heartbeat_stale',
            'observer_heartbeat_stale',
            'missing_signing_key_context',
            'missing_real_api_key_when_real_source',
        ],
        'repro_steps': [
            'observerctl ops preflight --json',
            'observerctl ops gate-check --json',
            'observerctl ops evidence pack --event <event> --json',
        ],
    }

    process = {
        'phase': 'observerctl_runtime_gate_evaluation',
        'event': str(event),
        'decision': gate_packet.get('decision', 'no-go'),
        'rationale': 'critical-check policy evaluation over observer runtime posture',
        'reason_codes': gate_packet.get('reason_codes', []),
        'evidence_refs': evidence_refs,
        'approver_checkpoint': 'required_for_live_transition',
    }

    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_label': 'observer',
        'runtime_cli_surface': 'observerctl',
        'status_packet': status_packet,
        'gate_packet': gate_packet,
        'provenance': {
            'artifact_path': 'stdout',
            'artifact_sha256': '',
            'generated_at_utc': _utc_now(),
            'producer_process': 'observerctl ops evidence pack',
            'upstream_inputs': {
                'env_presence_keys': ['CALAMUM_DATA_SIGNING_KEY', 'CALAMUM_ALLOW_DEV_SIGNING_KEY', 'MOLTBOOK_API_KEY'],
                'paths': evidence_refs,
            },
        },
        'methodology': methodology,
        'process': process,
    }
    for key in ('run_id', 'posture_trigger_id', 'posture_trigger', 'security_report_ref'):
        packet[key] = gate_packet.get(key, '')
    return packet


def _write_packet(packet: Dict[str, Any], output: Path) -> Dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(packet, indent=2, sort_keys=True) + '\n'
    output.write_text(text, encoding='utf-8')
    sha = _sha256_text(text)
    packet['provenance']['artifact_path'] = str(output).replace('\\', '/')
    packet['provenance']['artifact_sha256'] = sha
    output.write_text(json.dumps(packet, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return packet


def _default_output_path(source: str = 'sim', mode: str = 'watch', event: str = 'manual') -> Path:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'
    ev = str(event or 'manual').strip().lower().replace(' ', '-')
    return get_calamum_data_dir() / 'observer_derived' / src / m / 'evidence' / 'observerctl_{0}_evidence_{1}.json'.format(ev, ts)


def _evidence_index_path(source: str, mode: str) -> Path:
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'
    return get_calamum_data_dir() / 'observer_derived' / src / m / 'evidence' / 'index.jsonl'


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, sort_keys=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def _emit(packet: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(packet, indent=2, sort_keys=True))
        return
    decision = ((packet.get('gate_packet') or {}).get('decision') if isinstance(packet, dict) else None) or packet.get('decision', '')
    reasons = ((packet.get('gate_packet') or {}).get('reason_codes') if isinstance(packet, dict) else None) or packet.get('reason_codes', [])
    if decision:
        print('observerctl decision: {0}'.format(decision))
        for reason in reasons:
            print('- {0}'.format(reason))
        return

    rendered = False
    ordered_keys = [
        'source',
        'mode',
        'posture_trigger',
        'active_baseline_id',
        'status',
        'index_path',
        'packet',
        'code',
        'explanation',
        'policy_profile',
    ]
    for key in ordered_keys:
        if key not in packet:
            continue
        value = packet.get(key)
        if value in (None, '', [], {}):
            continue
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, sort_keys=True)
        else:
            value_text = str(value)
        print('{0}: {1}'.format(key, value_text))
        rendered = True

    if not rendered and isinstance(packet, dict):
        for key in sorted(packet.keys()):
            if key in ('timestamp_utc', 'runtime_cli_surface'):
                continue
            value = packet.get(key)
            if value in (None, '', [], {}):
                continue
            if isinstance(value, (dict, list)):
                value_text = json.dumps(value, sort_keys=True)
            else:
                value_text = str(value)
            print('{0}: {1}'.format(key, value_text))
            rendered = True

    if not rendered:
        print('observerctl: ok')


def _baseline_catalog_path() -> Path:
    return _project_root() / 'local_untracked' / 'observerctl' / 'baselines' / 'catalog.json'


def _load_baselines() -> Dict[str, Any]:
    default = {
        'active': 'baseline-default',
        'items': [
            {'id': 'baseline-default', 'created_at_utc': _utc_now(), 'status': 'ready'},
        ],
    }
    path = _baseline_catalog_path()
    data = _load_json_file(path, default)
    if not path.exists():
        _write_json_file(path, data)
    return data


def _save_baselines(payload: Dict[str, Any]) -> None:
    _write_json_file(_baseline_catalog_path(), payload)


def _ops_preflight(source: str) -> Dict[str, Any]:
    status = collect_runtime_status(source=source)
    linkage = _make_run_linkage(str(status.get('mode', 'watch')), event='preflight')
    status.update(linkage)
    return status


def _ops_gate(source: str, to_mode: str) -> Dict[str, Any]:
    status = collect_runtime_status(source=source)
    gate = evaluate_gate_decision(status, target_mode=to_mode)
    _write_json_file(_control_file(LAST_GATE_FILE), gate)
    return gate


def _ops_mode_current() -> Dict[str, Any]:
    state = _load_state()
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'source': state['source'],
        'mode': state['mode'],
        'posture_trigger': _posture_for_mode(state['mode']),
    }


def _ops_mode_list() -> Dict[str, Any]:
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'source_axis': list(SOURCES),
        'mode_axis': list(MODES),
        'posture_map': {m: _posture_for_mode(m) for m in MODES},
    }


def _ops_mode_set(source: str, to_mode: str) -> Dict[str, Any]:
    gate = _load_json_file(_control_file(LAST_GATE_FILE), {})
    to_state = str(gate.get('to_state', ''))
    expected_to_state = '{0}:{1}'.format(_normalize_source(source), to_mode)
    if gate.get('decision') != 'go' or to_state != expected_to_state or (not _is_gate_packet_fresh(gate, max_age_sec=GATE_PACKET_MAX_AGE_SEC)):
        return {
            'timestamp_utc': _utc_now(),
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:gate_packet_missing_or_stale'],
            'runtime_cli_surface': 'observerctl',
        }
    state = _save_state(source=source, mode=to_mode)
    response = {
        'timestamp_utc': _utc_now(),
        'decision': 'go',
        'runtime_cli_surface': 'observerctl',
        'from_state': gate.get('from_state', ''),
        'to_state': '{0}:{1}'.format(state['source'], state['mode']),
        'rollback_anchor': {
            'source': str(gate.get('from_state', 'sim:watch')).split(':')[0],
            'mode': str(gate.get('from_state', 'sim:watch')).split(':')[-1],
        },
    }
    response.update(_make_run_linkage(state['mode'], event='mode-set'))
    return response


def _ops_mode_transition(source: str, to_mode: str, event: str, output: str) -> Dict[str, Any]:
    status_before = collect_runtime_status(source=source)
    gate = evaluate_gate_decision(status_before, target_mode=to_mode)
    _write_json_file(_control_file(LAST_GATE_FILE), gate)
    if gate.get('decision') != 'go':
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'phase': 'mode-transition',
            'gate_packet': gate,
            'reason_codes': gate.get('reason_codes', []),
        }

    mode_set = _ops_mode_set(source, to_mode)
    if mode_set.get('decision') != 'go':
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'phase': 'mode-transition',
            'gate_packet': gate,
            'mode_set_packet': mode_set,
            'reason_codes': mode_set.get('reason_codes', ['critical_check_failed:mode_set_failed']),
        }

    evidence = build_evidence_pack(status_before, gate, event=event)
    out_path = Path(str(output).strip()) if str(output).strip() else _default_output_path(source=source, mode=to_mode, event=event)
    evidence = _write_packet(evidence, out_path)
    _append_jsonl(_evidence_index_path(source, to_mode), {
        'timestamp_utc': _utc_now(),
        'packet_path': str(out_path).replace('\\', '/'),
        'decision': gate.get('decision', 'no-go'),
        'run_id': evidence.get('run_id', ''),
        'scope': {'source': _normalize_source(source), 'mode': to_mode},
    })
    evidence_decision = str(((evidence.get('gate_packet') or {}).get('decision')) or evidence.get('decision', 'no-go')).lower()
    if evidence_decision != 'go':
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'phase': 'mode-transition',
            'gate_packet': gate,
            'mode_set_packet': mode_set,
            'evidence_packet': evidence,
            'reason_codes': ((evidence.get('gate_packet') or {}).get('reason_codes') or evidence.get('reason_codes') or ['critical_check_failed:evidence_gate_failed']),
        }

    result = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'phase': 'mode-transition',
        'gate_packet': gate,
        'mode_set_packet': mode_set,
        'evidence_packet': {
            'provenance': evidence.get('provenance', {}),
            'process': evidence.get('process', {}),
        },
        'from_state': gate.get('from_state', ''),
        'to_state': mode_set.get('to_state', gate.get('to_state', '')),
        'reason_codes': [],
    }
    for key in ('run_id', 'posture_trigger_id', 'posture_trigger', 'security_report_ref'):
        result[key] = mode_set.get(key, gate.get(key, ''))
    return result


def _ops_gate_check(source: str) -> Dict[str, Any]:
    status = collect_runtime_status(source=source)
    gate = evaluate_gate_decision(status, target_mode=str(status.get('mode', 'watch')))
    _write_json_file(_control_file(LAST_GATE_FILE), gate)
    return gate


def _ops_evidence_pack(source: str, event: str, output: str) -> Dict[str, Any]:
    status = collect_runtime_status(source=source)
    gate = evaluate_gate_decision(status, target_mode=str(status.get('mode', 'watch')))
    packet = build_evidence_pack(status, gate, event=event)
    mode = str(status.get('mode', 'watch')).strip().lower()
    out_path = Path(str(output).strip()) if str(output).strip() else _default_output_path(source=source, mode=mode, event=event)
    packet = _write_packet(packet, out_path)
    _append_jsonl(_evidence_index_path(source, mode), {
        'timestamp_utc': _utc_now(),
        'packet_path': str(out_path).replace('\\', '/'),
        'decision': gate.get('decision', 'no-go'),
        'run_id': packet.get('run_id', ''),
        'scope': {'source': _normalize_source(source), 'mode': mode},
    })
    return packet


def _ops_evidence_verify(packet_path: str) -> Dict[str, Any]:
    path = Path(packet_path)
    if not path.exists():
        return {
            'timestamp_utc': _utc_now(),
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:packet_missing'],
            'runtime_cli_surface': 'observerctl',
        }
    data = json.loads(path.read_text(encoding='utf-8'))
    needed = ['provenance', 'methodology', 'process', 'run_id', 'posture_trigger_id', 'posture_trigger', 'security_report_ref']
    missing = [k for k in needed if k not in data]
    if missing:
        return {
            'timestamp_utc': _utc_now(),
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:packet_schema_invalid'],
            'missing': missing,
            'runtime_cli_surface': 'observerctl',
        }
    return {
        'timestamp_utc': _utc_now(),
        'decision': 'go',
        'reason_codes': [],
        'runtime_cli_surface': 'observerctl',
        'packet': str(path).replace('\\', '/'),
    }


def _ops_evidence_index() -> Dict[str, Any]:
    state = _load_state()
    source = str(state.get('source', 'sim'))
    mode = str(state.get('mode', 'watch'))
    idx = _evidence_index_path(source, mode)
    count = 0
    latest = None
    if idx.exists():
        lines = [ln for ln in idx.read_text(encoding='utf-8').splitlines() if ln.strip()]
        count = len(lines)
        if lines:
            latest = json.loads(lines[-1])
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'index_path': str(idx).replace('\\', '/'),
        'scope': {'source': _normalize_source(source), 'mode': mode},
        'records': count,
        'latest': latest,
    }


def _baseline_status() -> Dict[str, Any]:
    catalog = _load_baselines()
    active_id = catalog.get('active', 'baseline-default')
    active = next((it for it in catalog.get('items', []) if it.get('id') == active_id), None)
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'active_baseline_id': active_id,
        'status': str((active or {}).get('status', 'ready')),
    }


def _baseline_graph() -> Dict[str, Any]:
    graph = _project_root() / 'semantics_vault' / 'oracl_index' / 'weighted_graph_index.json'
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'graph_path': str(graph).replace('\\', '/'),
        'exists': graph.exists(),
        'status': 'ok' if graph.exists() else 'warn',
    }


def _baseline_check() -> Dict[str, Any]:
    status = _baseline_status()
    graph = _baseline_graph()
    reasons = []
    if status.get('status') != 'ready':
        reasons.append('critical_check_failed:baseline_not_ready')
    if graph.get('exists') is not True:
        reasons.append('major_check_failed:graph_integrity_failed')
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if not reasons else 'no-go',
        'reason_codes': reasons,
        'active_baseline_id': status.get('active_baseline_id'),
    }


def _baseline_list() -> Dict[str, Any]:
    catalog = _load_baselines()
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'items': catalog.get('items', []),
    }


def _baseline_set(baseline_id: str) -> Dict[str, Any]:
    catalog = _load_baselines()
    items = catalog.get('items', [])
    found = any(str(it.get('id')) == baseline_id for it in items)
    if not found:
        items.append({'id': baseline_id, 'created_at_utc': _utc_now(), 'status': 'ready'})
    catalog['items'] = items
    catalog['active'] = baseline_id
    _save_baselines(catalog)
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'active_baseline_id': baseline_id,
    }


def _store_dir_for_mode(mode: str) -> Path:
    return get_calamum_data_dir() / 'stores' / mode


def _store_manifest_path(mode: str) -> Path:
    return _store_dir_for_mode(mode) / 'manifest.json'


def _store_default_manifest(mode: str) -> Dict[str, Any]:
    return {
        'mode': mode,
        'active_file': 'active.jsonl',
        'archives': [],
        'compacted_files': [],
        'retention_state': 'normal',
        'updated_at_utc': _utc_now(),
    }


def _load_store_manifest(mode: str) -> Dict[str, Any]:
    if mode not in MODES:
        mode = 'watch'
    store_dir = _store_dir_for_mode(mode)
    store_dir.mkdir(parents=True, exist_ok=True)
    path = _store_manifest_path(mode)
    manifest = _load_json_file(path, _store_default_manifest(mode))
    if not path.exists():
        _write_json_file(path, manifest)
    if not isinstance(manifest.get('archives'), list):
        manifest['archives'] = []
    if not isinstance(manifest.get('compacted_files'), list):
        manifest['compacted_files'] = []
    if not manifest.get('active_file'):
        manifest['active_file'] = 'active.jsonl'
    if not manifest.get('retention_state'):
        manifest['retention_state'] = 'normal'
    active_path = _store_dir_for_mode(mode) / str(manifest.get('active_file', 'active.jsonl'))
    active_path.parent.mkdir(parents=True, exist_ok=True)
    if not active_path.exists():
        active_path.touch()
        _save_store_manifest(mode, manifest)
    return manifest


def _save_store_manifest(mode: str, manifest: Dict[str, Any]) -> None:
    manifest['mode'] = mode
    manifest['updated_at_utc'] = _utc_now()
    _write_json_file(_store_manifest_path(mode), manifest)


def _store_paths(mode: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    store_dir = _store_dir_for_mode(mode)
    active_rel = str(manifest.get('active_file', 'active.jsonl'))
    active_path = store_dir / active_rel
    archives = [store_dir / str(name) for name in list(manifest.get('archives', []))]
    compacted = [store_dir / str(name) for name in list(manifest.get('compacted_files', []))]
    return {
        'store_dir': store_dir,
        'active_path': active_path,
        'archives': archives,
        'compacted': compacted,
    }


def _count_jsonl_records(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _store_integrity_packet(mode: str) -> Dict[str, Any]:
    manifest = _load_store_manifest(mode)
    paths = _store_paths(mode, manifest)
    active_exists = paths['active_path'].exists()
    missing_archives = [str(p.name) for p in paths['archives'] if not p.exists()]
    missing_compacted = [str(p.name) for p in paths['compacted'] if not p.exists()]
    issues: List[str] = []
    if not active_exists:
        issues.append('missing_active_file')
    if missing_archives:
        issues.append('missing_archive_files')
    if missing_compacted:
        issues.append('missing_compacted_files')
    return {
        'mode': mode,
        'store_path': str(paths['store_dir']).replace('\\', '/'),
        'manifest_path': str(_store_manifest_path(mode)).replace('\\', '/'),
        'active_store_pointer': str(paths['active_path']).replace('\\', '/'),
        'archive_count': len(paths['archives']),
        'compacted_count': len(paths['compacted']),
        'retention_state': str(manifest.get('retention_state', 'normal')),
        'issues': issues,
        'status': 'ok' if len(issues) == 0 else 'err',
    }


def _librarian_stats() -> Dict[str, Any]:
    items = []
    for mode in MODES:
        packet = _store_integrity_packet(mode)
        manifest = _load_store_manifest(mode)
        paths = _store_paths(mode, manifest)
        record_count = _count_jsonl_records(paths['active_path'])
        for p in paths['archives']:
            record_count += _count_jsonl_records(p)
        for p in paths['compacted']:
            record_count += _count_jsonl_records(p)
        items.append({
            'mode': mode,
            'store_path': packet['store_path'],
            'active_store_pointer': packet['active_store_pointer'],
            'record_count': record_count,
            'archive_count': packet['archive_count'],
            'manifest_integrity': packet['status'],
            'retention_state': packet['retention_state'],
        })
    return {'timestamp_utc': _utc_now(), 'runtime_cli_surface': 'observerctl', 'stores': items}


def _librarian_stores() -> Dict[str, Any]:
    state = _load_state()
    stores = []
    for mode in MODES:
        packet = _store_integrity_packet(mode)
        stores.append({
            'mode': mode,
            'path': packet['store_path'],
            'manifest_path': packet['manifest_path'],
            'active_store_pointer': packet['active_store_pointer'],
            'exists': Path(packet['store_path']).exists(),
            'active': mode == state.get('mode'),
            'retention_state': packet['retention_state'],
        })
    return {'timestamp_utc': _utc_now(), 'runtime_cli_surface': 'observerctl', 'stores': stores}


def _librarian_action(action: str, mode: str) -> Dict[str, Any]:
    if mode not in MODES:
        return {'timestamp_utc': _utc_now(), 'runtime_cli_surface': 'observerctl', 'decision': 'no-go', 'reason_codes': ['policy_denied:target_mode_unsupported']}
    manifest = _load_store_manifest(mode)
    paths = _store_paths(mode, manifest)
    paths['store_dir'].mkdir(parents=True, exist_ok=True)
    paths['active_path'].parent.mkdir(parents=True, exist_ok=True)
    if not paths['active_path'].exists():
        paths['active_path'].touch()

    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    if action == 'rotate':
        before_pointer = str(paths['active_path']).replace('\\', '/')
        archive_name = 'archive_{0}.jsonl'.format(ts)
        archive_path = paths['store_dir'] / archive_name
        if paths['active_path'].exists() and paths['active_path'].stat().st_size > 0:
            paths['active_path'].replace(archive_path)
            manifest['archives'] = list(manifest.get('archives', [])) + [archive_name]
        else:
            archive_name = ''
        paths['active_path'].touch()
        _save_store_manifest(mode, manifest)
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': action,
            'mode': mode,
            'before_store_pointer': before_pointer,
            'after_store_pointer': str(paths['active_path']).replace('\\', '/'),
            'archive_artifact': str(archive_path).replace('\\', '/') if archive_name else '',
        }

    if action == 'compact':
        archive_names = [str(x) for x in list(manifest.get('archives', []))]
        if len(archive_names) == 0:
            return {
                'timestamp_utc': _utc_now(),
                'runtime_cli_surface': 'observerctl',
                'decision': 'go',
                'action': action,
                'mode': mode,
                'compacted_files': 0,
                'compacted_records': 0,
                'compact_artifact': '',
            }

        compact_name = 'compact_{0}.jsonl'.format(ts)
        compact_path = paths['store_dir'] / compact_name
        compacted_files = 0
        compacted_records = 0
        with compact_path.open('w', encoding='utf-8') as out_f:
            for rel_name in archive_names:
                p = paths['store_dir'] / rel_name
                if not p.exists():
                    continue
                with p.open('r', encoding='utf-8', errors='ignore') as in_f:
                    for line in in_f:
                        if line.strip():
                            out_f.write(line.rstrip('\n') + '\n')
                            compacted_records += 1
                p.unlink()
                compacted_files += 1

        manifest['archives'] = []
        manifest['compacted_files'] = list(manifest.get('compacted_files', [])) + [compact_name]
        _save_store_manifest(mode, manifest)
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': action,
            'mode': mode,
            'compacted_files': compacted_files,
            'compacted_records': compacted_records,
            'compact_artifact': str(compact_path).replace('\\', '/'),
        }

    if action == 'verify':
        packet = _store_integrity_packet(mode)
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go' if packet['status'] == 'ok' else 'no-go',
            'action': action,
            'mode': mode,
            'store_path': packet['store_path'],
            'manifest_path': packet['manifest_path'],
            'active_store_pointer': packet['active_store_pointer'],
            'archive_count': packet['archive_count'],
            'compacted_count': packet['compacted_count'],
            'retention_state': packet['retention_state'],
            'reason_codes': [] if packet['status'] == 'ok' else ['critical_check_failed:store_integrity_invalid'],
            'issues': packet['issues'],
        }

    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'reason_codes': ['critical_check_failed:unknown_librarian_action'],
        'action': action,
        'mode': mode,
    }


def _watchdog_status() -> Dict[str, Any]:
    hb_watchdog = _check_heartbeat(get_calamum_health_dir() / 'calamum_ops_watchdog.heartbeat', max_age_sec=45.0)
    hb_observer = _check_heartbeat(get_calamum_health_dir() / 'calamum_observer.heartbeat', max_age_sec=60.0)
    state = _load_state()
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'mode': state.get('mode'),
        'posture_trigger': _posture_for_mode(str(state.get('mode', 'watch'))),
        'checks': {'watchdog': hb_watchdog, 'observer': hb_observer},
    }


def _watchdog_check() -> Dict[str, Any]:
    status = _watchdog_status()
    reasons = []
    if str((status.get('checks', {}).get('watchdog') or {}).get('status', 'err')) != 'ok':
        reasons.append('critical_check_failed:watchdog_heartbeat_stale')
    if str((status.get('checks', {}).get('observer') or {}).get('status', 'err')) != 'ok':
        reasons.append('critical_check_failed:observer_heartbeat_stale')
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if not reasons else 'no-go',
        'reason_codes': reasons,
    }


def _watchdog_reasons() -> Dict[str, Any]:
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'reasons': [
            'critical_check_failed:watchdog_trigger_posture_invalid',
            'critical_check_failed:lockdown_heartbeat_rate_not_escalated',
            'critical_check_failed:lockdown_baseline_rate_not_escalated',
            'critical_check_failed:run_security_report_missing',
            'critical_check_failed:watchdog_heartbeat_stale',
            'critical_check_failed:observer_heartbeat_stale',
        ],
    }


def _watchdog_ack(code: str) -> Dict[str, Any]:
    payload = {'timestamp_utc': _utc_now(), 'runtime_cli_surface': 'observerctl', 'ack_code': code}
    _append_jsonl(_control_file(ACK_LOG_FILE), payload)
    return payload


def _health_quick() -> Dict[str, Any]:
    gate = _ops_gate_check(source=_load_state().get('source', 'sim'))
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': gate.get('decision'),
        'reason_codes': gate.get('reason_codes', []),
    }


def _health_full() -> Dict[str, Any]:
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'ops': _ops_gate_check(source=_load_state().get('source', 'sim')),
        'baseline': _baseline_check(),
        'librarian': _librarian_stats(),
        'watchdog': _watchdog_check(),
        'policy': _policy_validate(),
    }


def _health_explain(code: str) -> Dict[str, Any]:
    explanations = {
        'critical_check_failed:watchdog_trigger_posture_invalid': 'Target mode posture mismatch; enforce isolation for watch/canary or lockdown for live/honeypot.',
        'critical_check_failed:run_security_report_missing': 'Run linkage missing security_report_ref.',
        'critical_check_failed:real_key_missing': 'MOLTBOOK_API_KEY is required when source=real.',
    }
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'code': code,
        'explanation': explanations.get(code, 'Unknown reason code'),
    }


def _policy_show() -> Dict[str, Any]:
    policy = _load_policy()
    policy['timestamp_utc'] = _utc_now()
    policy['runtime_cli_surface'] = 'observerctl'
    return policy


def _policy_validate() -> Dict[str, Any]:
    policy = _load_policy()
    reasons = []
    if 'allowed_modes' not in policy or not isinstance(policy.get('allowed_modes'), list):
        reasons.append('critical_check_failed:policy_not_loaded')
    missing_modes = [m for m in MODES if m not in list(policy.get('allowed_modes', []))]
    if missing_modes:
        reasons.append('critical_check_failed:policy_transition_disallowed')
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if not reasons else 'no-go',
        'reason_codes': reasons,
        'policy_profile': policy.get('policy_profile', 'default'),
    }


def _exit_from_packet(packet: Dict[str, Any], schema_error: bool = False, dependency_error: bool = False, io_error: bool = False) -> int:
    if schema_error:
        return 3
    if dependency_error:
        return 4
    if io_error:
        return 5
    if 'decision' not in packet:
        reasons = packet.get('reason_codes', [])
        if isinstance(reasons, list) and len(reasons) == 0:
            return 0
    decision = str(packet.get('decision', '')).lower()
    return 0 if decision in ('go', 'ok', 'pass', 'success') else 2


def _dispatch(args: argparse.Namespace) -> Dict[str, Any]:
    cmd = str(args.command)
    if cmd == 'ops':
        if args.ops_cmd == 'preflight':
            return _ops_preflight(args.source)
        if args.ops_cmd == 'gate-check':
            return _ops_gate_check(args.source)
        if args.ops_cmd == 'runtime-status':
            return _ops_runtime_status()
        if args.ops_cmd == 'runtime-stop':
            return _ops_runtime_stop(args.timeout_sec)
        if args.ops_cmd == 'runtime-start':
            return _ops_runtime_start(args.source, args.mode, args.interval_sec, args.timeout_sec)
        if args.ops_cmd == 'mode-current':
            return _ops_mode_current()
        if args.ops_cmd == 'mode-list':
            return _ops_mode_list()
        if args.ops_cmd == 'mode-gate':
            return _ops_gate(args.source, args.to)
        if args.ops_cmd == 'mode-set':
            return _ops_mode_set(args.source, args.to)
        if args.ops_cmd == 'mode-transition':
            return _ops_mode_transition(args.source, args.to, args.event, args.output)
        if args.ops_cmd == 'evidence-pack':
            return _ops_evidence_pack(args.source, args.event, args.output)
        if args.ops_cmd == 'evidence-verify':
            return _ops_evidence_verify(args.packet)
        if args.ops_cmd == 'evidence-index':
            return _ops_evidence_index()

    if cmd == 'baseline':
        if args.base_cmd == 'status':
            return _baseline_status()
        if args.base_cmd == 'graph':
            return _baseline_graph()
        if args.base_cmd == 'check':
            return _baseline_check()
        if args.base_cmd == 'list':
            return _baseline_list()
        if args.base_cmd == 'set':
            return _baseline_set(args.id)

    if cmd == 'librarian':
        if args.lib_cmd == 'stats':
            return _librarian_stats()
        if args.lib_cmd == 'stores':
            return _librarian_stores()
        if args.lib_cmd == 'rotate':
            return _librarian_action('rotate', args.mode)
        if args.lib_cmd == 'compact':
            return _librarian_action('compact', args.mode)
        if args.lib_cmd == 'verify':
            return _librarian_action('verify', args.mode)

    if cmd == 'watchdog':
        if args.wd_cmd == 'status':
            return _watchdog_status()
        if args.wd_cmd == 'check':
            return _watchdog_check()
        if args.wd_cmd == 'reasons':
            return _watchdog_reasons()
        if args.wd_cmd == 'ack':
            return _watchdog_ack(args.code)

    if cmd == 'health':
        if args.health_cmd == 'quick':
            return _health_quick()
        if args.health_cmd == 'full':
            return _health_full()
        if args.health_cmd == 'explain':
            return _health_explain(args.code)

    if cmd == 'policy':
        if args.policy_cmd == 'show':
            return _policy_show()
        if args.policy_cmd == 'validate':
            return _policy_validate()

    return {'timestamp_utc': _utc_now(), 'decision': 'no-go', 'reason_codes': ['critical_check_failed:unknown_command']}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='observerctl standalone runtime operations surface (observer scope)')
    sub = parser.add_subparsers(dest='command', required=True)

    ops = sub.add_parser('ops', help='Observer runtime operations gate surface')
    ops_sub = ops.add_subparsers(dest='ops_cmd', required=True)

    op_pre = ops_sub.add_parser('preflight', help='Emit observer runtime status packet')
    op_pre.add_argument('--source', choices=['sim', 'real'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))

    op_gatecheck = ops_sub.add_parser('gate-check', help='Evaluate go/no-go over current state')
    op_gatecheck.add_argument('--source', choices=['sim', 'real'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))

    op_runtime = ops_sub.add_parser('runtime', help='Observer lifecycle controls')
    op_runtime_sub = op_runtime.add_subparsers(dest='runtime_cmd', required=True)
    op_runtime_sub.add_parser('status', help='Show observer runtime status')
    op_runtime_stop = op_runtime_sub.add_parser('stop', help='Request observer stop (kill signal) and wait for clean exit')
    op_runtime_stop.add_argument('--timeout-sec', type=float, default=8.0, help='Seconds to wait for clean observer shutdown before escalation')
    op_runtime_start = op_runtime_sub.add_parser('start', help='Start observer via delegated launcher path')
    op_runtime_start.add_argument('--source', choices=['sim', 'real'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))
    op_runtime_start.add_argument('--mode', choices=list(MODES), default=os.getenv('CALAMUM_OPS_MODE', 'watch'))
    op_runtime_start.add_argument('--interval-sec', type=float, default=float(os.getenv('CALAMUM_AGENT_INTERVAL_SEC', '2.0')))
    op_runtime_start.add_argument('--timeout-sec', type=float, default=0.0, help='Readiness probe timeout after detached launch (0 = no probe)')

    op_mode = ops_sub.add_parser('mode', help='Mode controls')
    op_mode_sub = op_mode.add_subparsers(dest='mode_cmd', required=True)
    op_mode_sub.add_parser('current', help='Show current mode/source')
    op_mode_sub.add_parser('list', help='List modes and posture mapping')
    op_gate = op_mode_sub.add_parser('gate', help='Evaluate transition gate to target mode')
    op_gate.add_argument('--to', choices=list(MODES), required=True)
    op_gate.add_argument('--source', choices=['sim', 'real'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))
    op_set = op_mode_sub.add_parser('set', help='Set target mode after successful gate packet')
    op_set.add_argument('--to', choices=list(MODES), required=True)
    op_set.add_argument('--source', choices=['sim', 'real'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))
    op_transition = op_mode_sub.add_parser('transition', help='Atomic mode transition: gate + set + evidence')
    op_transition.add_argument('--to', choices=list(MODES), required=True)
    op_transition.add_argument('--source', choices=['sim', 'real'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))
    op_transition.add_argument('--event', default='mode-transition')
    op_transition.add_argument('--output', default='')

    op_ev = ops_sub.add_parser('evidence', help='Evidence packet operations')
    op_ev_sub = op_ev.add_subparsers(dest='evidence_cmd', required=True)
    op_ev_pack = op_ev_sub.add_parser('pack', help='Emit publication-grade evidence packet')
    op_ev_pack.add_argument('--source', choices=['sim', 'real'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))
    op_ev_pack.add_argument('--event', default='manual')
    op_ev_pack.add_argument('--output', default='')
    op_ev_verify = op_ev_sub.add_parser('verify', help='Verify packet schema and linkage fields')
    op_ev_verify.add_argument('--packet', required=True)
    op_ev_sub.add_parser('index', help='Show evidence index summary')

    baseline = sub.add_parser('baseline', help='Baseline and graph readiness namespace')
    baseline_sub = baseline.add_subparsers(dest='base_cmd', required=True)
    baseline_sub.add_parser('status')
    baseline_sub.add_parser('graph')
    baseline_sub.add_parser('check')
    baseline_sub.add_parser('list')
    baseline_set = baseline_sub.add_parser('set')
    baseline_set.add_argument('--id', required=True)

    librarian = sub.add_parser('librarian', help='Mode-store operations')
    librarian_sub = librarian.add_subparsers(dest='lib_cmd', required=True)
    librarian_sub.add_parser('stats')
    librarian_sub.add_parser('stores')
    lib_rot = librarian_sub.add_parser('rotate')
    lib_rot.add_argument('--mode', choices=list(MODES), required=True)
    lib_compact = librarian_sub.add_parser('compact')
    lib_compact.add_argument('--mode', choices=list(MODES), required=True)
    lib_verify = librarian_sub.add_parser('verify')
    lib_verify.add_argument('--mode', choices=list(MODES), required=True)

    watchdog = sub.add_parser('watchdog', help='Watchdog posture namespace')
    watchdog_sub = watchdog.add_subparsers(dest='wd_cmd', required=True)
    watchdog_sub.add_parser('status')
    watchdog_sub.add_parser('check')
    watchdog_sub.add_parser('reasons')
    wd_ack = watchdog_sub.add_parser('ack')
    wd_ack.add_argument('--code', required=True)

    health = sub.add_parser('health', help='Diagnostics namespace')
    health_sub = health.add_subparsers(dest='health_cmd', required=True)
    health_sub.add_parser('quick')
    health_sub.add_parser('full')
    health_ex = health_sub.add_parser('explain')
    health_ex.add_argument('--code', required=True)

    policy = sub.add_parser('policy', help='Policy introspection namespace')
    policy_sub = policy.add_subparsers(dest='policy_cmd', required=True)
    policy_sub.add_parser('show')
    policy_sub.add_parser('validate')

    parser.add_argument('--json', action='store_true', help='Emit JSON output')
    return parser


def _normalize_nested_aliases(args: argparse.Namespace) -> argparse.Namespace:
    if args.command == 'ops' and args.ops_cmd == 'mode':
        if args.mode_cmd == 'current':
            args.ops_cmd = 'mode-current'
        elif args.mode_cmd == 'list':
            args.ops_cmd = 'mode-list'
        elif args.mode_cmd == 'gate':
            args.ops_cmd = 'mode-gate'
        elif args.mode_cmd == 'set':
            args.ops_cmd = 'mode-set'
        elif args.mode_cmd == 'transition':
            args.ops_cmd = 'mode-transition'
    if args.command == 'ops' and args.ops_cmd == 'runtime':
        if args.runtime_cmd == 'status':
            args.ops_cmd = 'runtime-status'
        elif args.runtime_cmd == 'stop':
            args.ops_cmd = 'runtime-stop'
        elif args.runtime_cmd == 'start':
            args.ops_cmd = 'runtime-start'
    if args.command == 'ops' and args.ops_cmd == 'evidence':
        if args.evidence_cmd == 'pack':
            args.ops_cmd = 'evidence-pack'
        elif args.evidence_cmd == 'verify':
            args.ops_cmd = 'evidence-verify'
        elif args.evidence_cmd == 'index':
            args.ops_cmd = 'evidence-index'
    return args


def _extract_json_flag(argv: Optional[List[str]]) -> Tuple[List[str], bool]:
    raw_argv = list(sys.argv[1:]) if argv is None else list(argv)
    cleaned: List[str] = []
    as_json = False
    for token in raw_argv:
        if token == '--json':
            as_json = True
            continue
        cleaned.append(token)
    return cleaned, as_json


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    normalized_argv, forced_json = _extract_json_flag(argv)
    args = _normalize_nested_aliases(parser.parse_args(normalized_argv))
    if forced_json:
        setattr(args, 'json', True)

    try:
        packet = _dispatch(args)
    except json.JSONDecodeError:
        packet = {
            'timestamp_utc': _utc_now(),
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:schema_invalid'],
            'runtime_cli_surface': 'observerctl',
        }
        _emit(packet, as_json=bool(getattr(args, 'json', False)))
        return _exit_from_packet(packet, schema_error=True)
    except (FileNotFoundError, PermissionError):
        packet = {
            'timestamp_utc': _utc_now(),
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:dependency_missing'],
            'runtime_cli_surface': 'observerctl',
        }
        _emit(packet, as_json=bool(getattr(args, 'json', False)))
        return _exit_from_packet(packet, dependency_error=True)
    except OSError:
        packet = {
            'timestamp_utc': _utc_now(),
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:io_failure'],
            'runtime_cli_surface': 'observerctl',
        }
        _emit(packet, as_json=bool(getattr(args, 'json', False)))
        return _exit_from_packet(packet, io_error=True)

    _emit(packet, as_json=bool(getattr(args, 'json', False)))
    return _exit_from_packet(packet)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
