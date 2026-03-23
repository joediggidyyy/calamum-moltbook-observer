"""observerctl: standalone observer-scoped runtime operations CLI.

Normative constraints:
- observerctl is an observer runtime/security-operations surface.
- It must not depend on CodeSentinel runtime process orchestration.
- Output is names-only, deterministic, and fail-closed compatible.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import psutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from calamum_config import get_calamum_control_dir, get_calamum_data_dir, get_calamum_health_dir
from observerctl_sandbox_registry import get_definition as sandbox_get_definition
from observerctl_sandbox_registry import get_definitions as sandbox_get_definitions
from observerctl_sandbox_registry import run_definition as sandbox_run_definition
from observerctl_sandbox_render import render_human_packet as render_sandbox_human_packet
from observerctl_sandbox_runs import get_run as sandbox_get_run
from observerctl_sandbox_runs import list_runs as sandbox_list_runs


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
BASELINE_MONITOR_PID_FILE = 'calamum_baseline_monitor.pid'
BASELINE_MONITOR_STATE_FILE = 'baseline_monitor_state.json'
RESOURCE_PROFILES = ('normal', 'baseline')
RESOURCE_PROFILE_ALIASES = {
    'normal': 'normal',
    'baseline': 'baseline',
    'rapid': 'baseline',
}
RESOURCE_PROFILE_CLI_CHOICES = ('normal', 'baseline', 'rapid')
ISOLATION_HEARTBEAT_INTERVAL_SEC = 10.0
ISOLATION_BASELINE_VALIDATION_INTERVAL_SEC = 120.0
LOCKDOWN_HEARTBEAT_INTERVAL_SEC = 4.0
LOCKDOWN_BASELINE_VALIDATION_INTERVAL_SEC = 45.0
RESOURCE_NORMAL_INTERVAL_SEC = float(os.getenv('CALAMUM_RESOURCE_NORMAL_INTERVAL_SEC', '30.0'))
RESOURCE_BASELINE_INTERVAL_SEC = float(os.getenv('CALAMUM_RESOURCE_BASELINE_INTERVAL_SEC', '2.0'))
RESOURCE_BASELINE_WINDOW_SEC = float(os.getenv('CALAMUM_RESOURCE_BASELINE_WINDOW_SEC', '10.0'))
RESOURCE_BASELINE_STREAM_MAX_AGE_SEC = float(os.getenv('CALAMUM_RESOURCE_STREAM_MAX_AGE_SEC', '180.0'))
RESOURCE_BASELINE_WINDOW_MAX_AGE_SEC = float(os.getenv('CALAMUM_RESOURCE_BASELINE_WINDOW_MAX_AGE_SEC', '180.0'))
RESOURCE_BASELINE_MIN_NORMAL_SAMPLES = int(os.getenv('CALAMUM_RESOURCE_BASELINE_MIN_NORMAL_SAMPLES', '2'))
RESOURCE_BASELINE_MIN_BASELINE_SAMPLES = int(os.getenv('CALAMUM_RESOURCE_BASELINE_MIN_BASELINE_SAMPLES', '3'))
FS_BASELINE_FILE = 'observerctl_fs_baseline.json'
FS_BASELINE_EXCLUDE = {
    '.git',
    '__pycache__',
    '.pytest_cache',
    '.mypy_cache',
    '.venv',
    '.venv-core',
    'venv',
    'node_modules',
    'logs',
    'archive',
    'quarantine_legacy_archive',
    'semantics_vault',
    'semantics_staging',
    'staging_fs',
    'report_tmp',
    'local_untracked',
}


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


def _normalize_resource_profile(profile: str) -> str:
    p = str(profile or '').strip().lower()
    return RESOURCE_PROFILE_ALIASES.get(p, 'normal')


def _resource_stream_type(profile: str) -> str:
    return 'resource_{0}'.format(_normalize_resource_profile(profile))


def _resource_profile_matches(stream_type: str, profile: str) -> bool:
    stream = str(stream_type or '').strip().lower()
    canonical = _normalize_resource_profile(profile)
    if canonical == 'baseline':
        return stream in ('resource_baseline', 'resource_rapid')
    return stream == _resource_stream_type(canonical)


def _posture_cadence_defaults(mode: str) -> Dict[str, Any]:
    posture = _posture_for_mode(mode)
    if posture == 'lockdown':
        return {
            'posture_trigger': 'lockdown',
            'heartbeat_interval_seconds': float(LOCKDOWN_HEARTBEAT_INTERVAL_SEC),
            'baseline_validation_interval_seconds': float(LOCKDOWN_BASELINE_VALIDATION_INTERVAL_SEC),
        }
    return {
        'posture_trigger': 'isolation',
        'heartbeat_interval_seconds': float(ISOLATION_HEARTBEAT_INTERVAL_SEC),
        'baseline_validation_interval_seconds': float(ISOLATION_BASELINE_VALIDATION_INTERVAL_SEC),
    }


def _is_lockdown_baseline_cadence(value: Any) -> bool:
    interval = _to_float_or_none(value)
    return bool(interval is not None and 30.0 <= float(interval) <= 60.0)


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


def _state_default_source() -> str:
    """CLI default source from SSOT state."""
    try:
        return _normalize_source(str(_load_state().get('source', 'sim')))
    except Exception:
        return 'sim'


def _state_default_mode() -> str:
    """CLI default mode from SSOT state."""
    try:
        mode = str(_load_state().get('mode', 'watch')).strip().lower()
        if mode in MODES:
            return mode
    except Exception:
        pass
    return 'watch'


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


def _infer_collection_state(observer_runtime: Dict[str, Any], metrics_path: Path) -> Dict[str, Any]:
    runtime_state = str(observer_runtime.get('state', 'stopped')).strip().lower()
    pid_alive = bool(((observer_runtime.get('pid', {}) or {}).get('alive')))
    hb_status = str((observer_runtime.get('heartbeat', {}) or {}).get('status', 'err')).strip().lower()
    metrics_exists = bool(metrics_path.exists())
    metrics_age_s = _file_age_seconds(metrics_path) if metrics_exists else None

    interval_s = _to_float_or_none(os.getenv('CALAMUM_AGENT_INTERVAL_SEC'))
    if interval_s is None or interval_s <= 0:
        interval_s = 2.0
    collecting_fresh_max_age_s = max(20.0, float(interval_s) * 20.0)

    state = 'error'
    if runtime_state == 'stopped' and (not pid_alive):
        state = 'stopped'
    elif metrics_exists and metrics_age_s is not None and float(metrics_age_s) <= float(collecting_fresh_max_age_s):
        state = 'collecting'
    elif runtime_state in ('active', 'degraded') and pid_alive:
        # Service is alive, but collection stream freshness may legitimately be idle/warmup.
        state = 'idle' if hb_status in ('ok', 'warn', 'err') else 'warmup'
    elif runtime_state in ('active', 'degraded'):
        state = 'warmup'
    elif runtime_state == 'stopped':
        state = 'stopped'

    status = 'ok'
    if state == 'error':
        status = 'err'
    elif state == 'collecting' and runtime_state == 'stopped':
        status = 'err'
    elif state not in ('idle', 'warmup', 'collecting', 'stopped', 'error'):
        status = 'err'

    return {
        'state': state,
        'status': status,
        'runtime_state': runtime_state,
        'observer_pid_alive': bool(pid_alive),
        'observer_heartbeat_status': hb_status,
        'metrics_path': str(metrics_path),
        'metrics_exists': bool(metrics_exists),
        'metrics_age_seconds': None if metrics_age_s is None else round(float(metrics_age_s), 3),
        'collecting_fresh_max_age_seconds': float(collecting_fresh_max_age_s),
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


def _librarian_pid_path() -> Path:
    return _project_root() / 'calamum_librarian.pid'


def _baseline_monitor_pid_path() -> Path:
    return _project_root() / BASELINE_MONITOR_PID_FILE


def _baseline_monitor_state_path() -> Path:
    return _control_file(BASELINE_MONITOR_STATE_FILE)


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


def _runtime_librarian_status(max_age_sec: float = 120.0) -> Dict[str, Any]:
    hb = _check_heartbeat(get_calamum_health_dir() / 'calamum_librarian.heartbeat', max_age_sec=max_age_sec)
    pid_path = _librarian_pid_path()
    pid = _read_pid(pid_path)
    pid_alive = _pid_alive(pid)

    if hb.get('status') == 'ok' and pid_alive:
        state = 'active'
    elif hb.get('status') == 'ok' or pid_alive:
        state = 'degraded'
    else:
        state = 'stopped'

    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'runtime_label': 'librarian',
        'state': state,
        'heartbeat': hb,
        'pid': {
            'path': str(pid_path).replace('\\', '/'),
            'value': pid,
            'alive': pid_alive,
        },
    }


def _runtime_baseline_monitor_status(max_age_sec: float = 90.0) -> Dict[str, Any]:
    hb = _check_heartbeat(get_calamum_health_dir() / 'calamum_baseline_monitor.heartbeat', max_age_sec=max_age_sec)
    pid_path = _baseline_monitor_pid_path()
    pid = _read_pid(pid_path)
    pid_alive = _pid_alive(pid)
    state_doc = _load_json_file(_baseline_monitor_state_path(), {})

    if hb.get('status') == 'ok' and pid_alive:
        state = 'active'
    elif hb.get('status') == 'ok' or pid_alive:
        state = 'degraded'
    else:
        state = 'stopped'

    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'runtime_label': 'baseline-monitor',
        'state': state,
        'heartbeat': hb,
        'pid': {
            'path': str(pid_path).replace('\\', '/'),
            'value': pid,
            'alive': pid_alive,
        },
        'monitor_state': state_doc,
    }


def _posture_receipt_output_path(source: str, mode: str, event: str) -> Path:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'
    ev = str(event or 'posture').strip().lower().replace(' ', '-').replace('_', '-')
    return get_calamum_data_dir() / 'observer_derived' / src / m / 'evidence' / 'observerctl_{0}_{1}.json'.format(ev, ts)


def _apply_watchdog_posture(source: str, mode: str, event: str = 'posture-apply') -> Dict[str, Any]:
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'

    linkage = _make_run_linkage(m, event=event)
    defaults = _posture_cadence_defaults(m)
    existing = _load_json_file(_control_file(WATCHDOG_POSTURE_FILE), {})
    posture_state_path = str(_control_file(WATCHDOG_POSTURE_FILE)).replace('\\', '/')
    receipt_path = ''
    payload = {
        'updated_at_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'source': src,
        'mode': m,
        'posture_trigger': defaults['posture_trigger'],
        'heartbeat_interval_seconds': defaults['heartbeat_interval_seconds'],
        'baseline_validation_interval_seconds': defaults['baseline_validation_interval_seconds'],
        'writer': 'observerctl',
        'reason': event,
        'readback_verified': False,
    }
    payload.update(linkage)
    _write_json_file(_control_file(WATCHDOG_POSTURE_FILE), payload)
    readback = _load_json_file(_control_file(WATCHDOG_POSTURE_FILE), {})
    readback_verified = (
        str(readback.get('posture_trigger', '')).strip().lower() == str(payload['posture_trigger']).strip().lower()
        and _to_float_or_none(readback.get('heartbeat_interval_seconds')) == float(payload['heartbeat_interval_seconds'])
        and _to_float_or_none(readback.get('baseline_validation_interval_seconds')) == float(payload['baseline_validation_interval_seconds'])
        and str(readback.get('mode', '')).strip().lower() == m
        and _normalize_source(str(readback.get('source', 'sim'))) == src
    )
    payload['readback_verified'] = bool(readback_verified)
    if readback_verified and payload != existing:
        out_path = _posture_receipt_output_path(src, m, event)
        receipt_path = str(out_path).replace('\\', '/')
        receipt = {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'posture-apply',
            'source': src,
            'mode': m,
            'posture': payload,
            'reason_codes': [],
            'provenance': {
                'generated_at_utc': _utc_now(),
                'producer_process': 'observerctl {0}'.format(event),
                'artifact_path': '',
                'artifact_sha256': '',
                'upstream_inputs': {
                    'watchdog_posture_state': posture_state_path,
                },
            },
            'methodology': {
                'sampling_strategy': 'deterministic posture write plus readback verification',
                'runtime_constraints': ['names-only outputs', 'observerctl standalone surface'],
            },
            'process': {
                'phase': 'posture_application',
                'event': event,
                'decision': 'go',
                'reason_codes': [],
                'evidence_refs': [posture_state_path],
            },
        }
        receipt.update(linkage)
        receipt = _write_packet(receipt, out_path)
        _append_jsonl(_evidence_index_path(src, m), {
            'timestamp_utc': _utc_now(),
            'packet_path': str(out_path).replace('\\', '/'),
            'decision': 'go',
            'run_id': receipt.get('run_id', ''),
            'scope': {'source': src, 'mode': m},
            'event': event,
        })
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if readback_verified else 'no-go',
        'action': 'posture-apply',
        'source': src,
        'mode': m,
        'posture_trigger': payload['posture_trigger'],
        'heartbeat_interval_seconds': payload['heartbeat_interval_seconds'],
        'baseline_validation_interval_seconds': payload['baseline_validation_interval_seconds'],
        'reason_codes': [] if readback_verified else ['critical_check_failed:watchdog_posture_persist_failed'],
        'readback_verified': bool(readback_verified),
        'posture_state_path': posture_state_path,
        'receipt_path': receipt_path,
    }


def _resource_index_health(source: str, mode: str, max_age_sec: float) -> Dict[str, Any]:
    idx = _resource_index_path(source, mode)
    latest_record: Optional[Dict[str, Any]] = None
    total_records = 0
    expected_stream_type = 'resource_normal'
    if idx.exists():
        try:
            with idx.open('r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = str(line or '').strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if str(row.get('stream_type', '')).strip().lower() != expected_stream_type:
                        continue
                    latest_record = row
                    try:
                        total_records += int(row.get('segment_records', 0) or 0)
                    except Exception:
                        total_records += 0
        except Exception:
            latest_record = None
    latest_ts = _parse_utc_iso8601((latest_record or {}).get('timestamp_utc')) if latest_record else None
    age_seconds = None if latest_ts is None else max(0.0, (datetime.now(timezone.utc) - latest_ts).total_seconds())
    segment_path = Path(str((latest_record or {}).get('segment_path', '') or '')) if latest_record else None
    segment_exists = bool(segment_path and segment_path.exists())
    ready = bool(idx.exists() and latest_record and segment_exists and age_seconds is not None and age_seconds <= float(max_age_sec))
    return {
        'path': str(idx).replace('\\', '/'),
        'exists': idx.exists(),
        'expected_stream_type': expected_stream_type,
        'latest_record': latest_record or {},
        'segment_exists': bool(segment_exists),
        'age_seconds': None if age_seconds is None else round(float(age_seconds), 3),
        'max_age_seconds': float(max_age_sec),
        'records_indexed': int(total_records),
        'status': 'ok' if ready else 'err',
    }


def _latest_baseline_analysis(source: str, mode: str) -> Dict[str, Any]:
    idx = _evidence_index_path(source, mode)
    latest_packet: Dict[str, Any] = {}
    if not idx.exists():
        return latest_packet
    try:
        lines = [ln for ln in idx.read_text(encoding='utf-8', errors='ignore').splitlines() if ln.strip()]
    except Exception:
        return latest_packet
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        if str(row.get('event', '')).strip().lower() != 'baseline_analysis':
            continue
        packet_path = Path(str(row.get('packet_path', '') or '').replace('/', os.sep))
        if not packet_path.exists():
            continue
        packet = _load_json_file(packet_path, {})
        if packet:
            latest_packet = packet
            break
    return latest_packet


def _baseline_window_health(source: str, mode: str, max_age_sec: float) -> Dict[str, Any]:
    packet = _latest_baseline_analysis(source, mode)
    ts = _parse_utc_iso8601(packet.get('timestamp_utc')) if packet else None
    age_seconds = None if ts is None else max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    decision = str(packet.get('decision', 'no-go')).strip().lower() if packet else 'no-go'
    ready = bool(packet and decision == 'go' and age_seconds is not None and age_seconds <= float(max_age_sec))
    return {
        'packet_path': str(((packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
        'decision': decision,
        'age_seconds': None if age_seconds is None else round(float(age_seconds), 3),
        'max_age_seconds': float(max_age_sec),
        'sample_counts': packet.get('sample_counts', {}) if isinstance(packet.get('sample_counts', {}), dict) else {},
        'status': 'ok' if ready else 'err',
    }


def _librarian_status() -> Dict[str, Any]:
    status = _runtime_librarian_status()
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'librarian-status',
        'decision': 'go' if str(status.get('state', 'stopped')) in ('active', 'degraded') else 'no-go',
        'state': status.get('state', 'stopped'),
        'heartbeat': status.get('heartbeat', {}),
        'pid': status.get('pid', {}),
        'reason_codes': [] if str(status.get('state', 'stopped')) in ('active', 'degraded') else ['critical_check_failed:librarian_not_running'],
    }


def _librarian_check(mode: str) -> Dict[str, Any]:
    status = _runtime_librarian_status()
    store_packet = _store_integrity_packet(mode if mode in MODES else 'watch')
    reasons: List[str] = []
    if str(status.get('state', 'stopped')) != 'active':
        reasons.append('critical_check_failed:librarian_runtime_inactive')
    if str(store_packet.get('status', 'err')) != 'ok':
        reasons.append('critical_check_failed:store_integrity_invalid')
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'librarian-check',
        'mode': mode if mode in MODES else 'watch',
        'decision': 'go' if len(reasons) == 0 else 'no-go',
        'reason_codes': reasons,
        'runtime_state': status,
        'store_integrity': store_packet,
    }


def _librarian_restart(timeout_sec: float = 8.0, startup_probe_sec: float = 6.0) -> Dict[str, Any]:
    pid_path = _librarian_pid_path()
    old_pid = _read_pid(pid_path)
    stopped_cleanly = True
    if old_pid and _pid_alive(old_pid):
        stopped_cleanly = _terminate_pid_best_effort(old_pid, graceful_timeout_sec=max(0.0, float(timeout_sec)))

    if not stopped_cleanly:
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'action': 'librarian-restart',
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:librarian_stop_timeout'],
            'old_pid': old_pid,
        }

    try:
        if pid_path.exists() and not _pid_alive(old_pid):
            pid_path.unlink()
    except Exception:
        pass

    script_path = _project_root() / 'src' / 'calamum_librarian.py'
    if not script_path.exists():
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'action': 'librarian-restart',
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:librarian_script_missing'],
            'script_path': str(script_path).replace('\\', '/'),
        }

    env = os.environ.copy()
    env['CALAMUM_REPO_ROOT'] = str(_project_root())
    env['CALAMUM_LOG_DIR'] = str(_project_root() / 'logs')

    creationflags = 0
    if os.name == 'nt':
        creationflags = int(getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)) | int(getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    stdout_path = _project_root() / 'logs' / 'calamum_librarian.stdout.log'
    stderr_path = _project_root() / 'logs' / 'calamum_librarian.stderr.log'
    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    out_f = None
    err_f = None
    try:
        out_f = stdout_path.open('a', encoding='utf-8')
        err_f = stderr_path.open('a', encoding='utf-8')
        proc = subprocess.Popen(
            [sys.executable, '-u', str(script_path)],
            env=env,
            cwd=str(_project_root()),
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
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
            'action': 'librarian-restart',
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:librarian_start_failed'],
        }

    try:
        if out_f is not None:
            out_f.close()
        if err_f is not None:
            err_f.close()
    except Exception:
        pass

    new_pid = int(getattr(proc, 'pid', 0) or 0)
    if new_pid > 0:
        try:
            pid_path.write_text(str(new_pid), encoding='utf-8')
        except Exception:
            pass

    deadline = time.time() + max(0.0, float(startup_probe_sec))
    final_status = _runtime_librarian_status()
    while time.time() <= deadline:
        final_status = _runtime_librarian_status()
        if str(final_status.get('state', 'stopped')) == 'active':
            break
        time.sleep(0.25)

    decision = 'go' if str(final_status.get('state', 'stopped')) in ('active', 'degraded') else 'no-go'
    reasons = [] if decision == 'go' else ['critical_check_failed:librarian_startup_unverified']
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'librarian-restart',
        'decision': decision,
        'reason_codes': reasons,
        'old_pid': old_pid,
        'new_pid': int((final_status.get('pid', {}) or {}).get('value') or new_pid),
        'state': final_status.get('state', 'stopped'),
        'heartbeat': final_status.get('heartbeat', {}),
    }


def _baseline_monitor_stop(timeout_sec: float = 8.0) -> Dict[str, Any]:
    pid_path = _baseline_monitor_pid_path()
    old_pid = _read_pid(pid_path)
    stopped_cleanly = True
    if old_pid and _pid_alive(old_pid):
        stopped_cleanly = _terminate_pid_best_effort(old_pid, graceful_timeout_sec=max(0.0, float(timeout_sec)))

    if stopped_cleanly:
        try:
            if pid_path.exists():
                pid_path.unlink()
        except Exception:
            pass
        try:
            hb = get_calamum_health_dir() / 'calamum_baseline_monitor.heartbeat'
            if hb.exists():
                hb.unlink()
        except Exception:
            pass

    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'baseline-monitor-stop',
        'decision': 'go' if stopped_cleanly else 'no-go',
        'reason_codes': [] if stopped_cleanly else ['critical_check_failed:baseline_monitor_stop_timeout'],
        'old_pid': old_pid,
        'stopped_cleanly': bool(stopped_cleanly),
    }


def _baseline_monitor_once(
    source: str,
    mode: str,
    normal_interval_sec: float,
    baseline_interval_sec: float,
    baseline_window_sec: float,
    baseline_sample_interval_sec: float,
    min_normal_samples: int,
    min_baseline_samples: int,
) -> Dict[str, Any]:
    state = _load_state()
    src = _normalize_source(str(state.get('source', source or 'sim')))
    m = str(state.get('mode', mode or 'watch')).strip().lower()
    if m not in MODES:
        m = 'watch'

    posture_packet = _apply_watchdog_posture(src, m, event='baseline-monitor-cycle')
    now = time.time()
    monitor_state = _load_json_file(_baseline_monitor_state_path(), {})
    last_normal_epoch = _to_float_or_none(monitor_state.get('last_normal_sample_epoch_s')) or 0.0
    last_baseline_epoch = _to_float_or_none(monitor_state.get('last_baseline_window_epoch_s')) or 0.0
    last_analysis_epoch = _to_float_or_none(monitor_state.get('last_analysis_epoch_s')) or 0.0

    normal_packet: Dict[str, Any] = {}
    baseline_packet: Dict[str, Any] = {}
    analysis_packet: Dict[str, Any] = {}

    if last_normal_epoch <= 0.0 or (now - last_normal_epoch) >= float(max(1.0, normal_interval_sec)):
        normal_packet = _baseline_collect(
            source=src,
            mode=m,
            profile='normal',
            duration_sec=0.0,
            interval_sec=float(max(0.1, normal_interval_sec)),
            segment_records=1000,
            window_id='monitor_normal_{0}'.format(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')),
            output='',
        )
        last_normal_epoch = now

    if _posture_for_mode(m) == 'lockdown' and (last_analysis_epoch <= 0.0 or (now - last_analysis_epoch) >= float(max(1.0, baseline_interval_sec))):
        baseline_packet = _baseline_collect(
            source=src,
            mode=m,
            profile='baseline',
            duration_sec=float(max(0.1, baseline_window_sec)),
            interval_sec=float(max(0.05, baseline_sample_interval_sec)),
            segment_records=1000,
            window_id='monitor_baseline_{0}'.format(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')),
            output='',
        )
        analysis_packet = _baseline_analyze(
            source=src,
            mode=m,
            hours=max(1.0, float(max(RESOURCE_BASELINE_WINDOW_MAX_AGE_SEC, baseline_interval_sec * 2.0)) / 3600.0),
            profile='all',
            min_normal_samples=int(max(1, min_normal_samples)),
            min_rapid_samples=int(max(1, min_baseline_samples)),
            output='',
        )
        last_baseline_epoch = now
        last_analysis_epoch = now

    monitor_payload = {
        'updated_at_utc': _utc_now(),
        'source': src,
        'mode': m,
        'posture_trigger': _posture_for_mode(m),
        'last_normal_sample_epoch_s': float(last_normal_epoch),
        'last_baseline_window_epoch_s': float(last_baseline_epoch),
        'last_analysis_epoch_s': float(last_analysis_epoch),
        'normal_interval_sec': float(normal_interval_sec),
        'baseline_validation_interval_seconds': float(baseline_interval_sec),
        'baseline_window_sec': float(baseline_window_sec),
        'baseline_sample_interval_sec': float(baseline_sample_interval_sec),
        'min_normal_samples': int(max(1, min_normal_samples)),
        'min_baseline_samples': int(max(1, min_baseline_samples)),
        'last_normal_packet_path': str(((normal_packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
        'last_baseline_packet_path': str(((baseline_packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
        'last_analysis_packet_path': str(((analysis_packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
        'last_analysis_decision': str(analysis_packet.get('decision', '')) if analysis_packet else '',
        'watchdog_posture_apply_decision': str(posture_packet.get('decision', 'no-go')),
    }
    _write_json_file(_baseline_monitor_state_path(), monitor_payload)

    hb = get_calamum_health_dir() / 'calamum_baseline_monitor.heartbeat'
    hb.parent.mkdir(parents=True, exist_ok=True)
    hb.touch(exist_ok=True)

    decision = 'go'
    reasons: List[str] = []
    if str(posture_packet.get('decision', 'no-go')) != 'go':
        decision = 'no-go'
        reasons.extend(list(posture_packet.get('reason_codes', [])))
    if analysis_packet and str(analysis_packet.get('decision', 'no-go')) != 'go':
        decision = 'no-go'
        reasons.extend(list(analysis_packet.get('reason_codes', [])))

    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': decision,
        'action': 'baseline-monitor-once',
        'reason_codes': reasons,
        'source': src,
        'mode': m,
        'posture_packet': posture_packet,
        'normal_packet': {'decision': normal_packet.get('decision', ''), 'artifact_path': str(((normal_packet.get('provenance', {}) or {}).get('artifact_path', '')) or '')} if normal_packet else {},
        'baseline_packet': {'decision': baseline_packet.get('decision', ''), 'artifact_path': str(((baseline_packet.get('provenance', {}) or {}).get('artifact_path', '')) or '')} if baseline_packet else {},
        'analysis_packet': {'decision': analysis_packet.get('decision', ''), 'artifact_path': str(((analysis_packet.get('provenance', {}) or {}).get('artifact_path', '')) or '')} if analysis_packet else {},
        'monitor_state_path': str(_baseline_monitor_state_path()).replace('\\', '/'),
    }


def _baseline_monitor_loop(
    source: str,
    mode: str,
    normal_interval_sec: float,
    baseline_interval_sec: float,
    baseline_window_sec: float,
    baseline_sample_interval_sec: float,
    min_normal_samples: int,
    min_baseline_samples: int,
    run_once: bool,
) -> Dict[str, Any]:
    pid_path = _baseline_monitor_pid_path()
    try:
        pid_path.write_text(str(os.getpid()), encoding='utf-8')
    except Exception:
        pass

    loop_sleep_sec = min(float(max(0.25, normal_interval_sec)), float(max(0.25, baseline_interval_sec)), 1.0)
    last_packet: Dict[str, Any] = {}
    while True:
        last_packet = _baseline_monitor_once(
            source=source,
            mode=mode,
            normal_interval_sec=normal_interval_sec,
            baseline_interval_sec=baseline_interval_sec,
            baseline_window_sec=baseline_window_sec,
            baseline_sample_interval_sec=baseline_sample_interval_sec,
            min_normal_samples=min_normal_samples,
            min_baseline_samples=min_baseline_samples,
        )
        if run_once:
            return last_packet
        _safe_sleep(loop_sleep_sec)


def _baseline_monitor_start(
    source: str,
    mode: str,
    normal_interval_sec: float,
    baseline_interval_sec: float,
    baseline_window_sec: float,
    baseline_sample_interval_sec: float,
    min_normal_samples: int,
    min_baseline_samples: int,
    startup_probe_sec: float = 3.0,
) -> Dict[str, Any]:
    status = _runtime_baseline_monitor_status(max_age_sec=max(90.0, float(normal_interval_sec) * 3.0))
    if str(status.get('state', 'stopped')) in ('active', 'degraded'):
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'baseline-monitor-start',
            'reason_codes': [],
            'state': status.get('state', 'active'),
            'pid': status.get('pid', {}),
            'startup_verified': True,
        }

    script_path = Path(__file__).resolve()
    env = os.environ.copy()
    env['CALAMUM_REPO_ROOT'] = str(_project_root())
    env['CALAMUM_LOG_DIR'] = str(_project_root() / 'logs')

    creationflags = 0
    if os.name == 'nt':
        creationflags = int(getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)) | int(getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    stdout_path = _project_root() / 'logs' / 'calamum_baseline_monitor.stdout.log'
    stderr_path = _project_root() / 'logs' / 'calamum_baseline_monitor.stderr.log'
    stdout_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        '-u',
        str(script_path),
        'baseline',
        'monitor-loop',
        '--source', str(_normalize_source(source)),
        '--mode', str(mode),
        '--normal-interval-sec', str(normal_interval_sec),
        '--baseline-interval-sec', str(baseline_interval_sec),
        '--baseline-window-sec', str(baseline_window_sec),
        '--baseline-sample-interval-sec', str(baseline_sample_interval_sec),
        '--min-normal-samples', str(min_normal_samples),
        '--min-baseline-samples', str(min_baseline_samples),
    ]

    out_f = None
    err_f = None
    try:
        out_f = stdout_path.open('a', encoding='utf-8')
        err_f = stderr_path.open('a', encoding='utf-8')
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(_project_root()),
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
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
            'action': 'baseline-monitor-start',
            'reason_codes': ['critical_check_failed:baseline_monitor_start_failed'],
        }

    try:
        if out_f is not None:
            out_f.close()
        if err_f is not None:
            err_f.close()
    except Exception:
        pass

    try:
        _baseline_monitor_pid_path().write_text(str(int(getattr(proc, 'pid', 0) or 0)), encoding='utf-8')
    except Exception:
        pass

    deadline = time.time() + max(0.0, float(startup_probe_sec))
    final_status = _runtime_baseline_monitor_status(max_age_sec=max(90.0, float(normal_interval_sec) * 3.0))
    while time.time() <= deadline:
        final_status = _runtime_baseline_monitor_status(max_age_sec=max(90.0, float(normal_interval_sec) * 3.0))
        if str(final_status.get('state', 'stopped')) == 'active':
            break
        time.sleep(0.25)

    startup_verified = str(final_status.get('state', 'stopped')) in ('active', 'degraded')
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if startup_verified else 'no-go',
        'action': 'baseline-monitor-start',
        'reason_codes': [] if startup_verified else ['critical_check_failed:baseline_monitor_startup_unverified'],
        'pid': final_status.get('pid', {}),
        'state': final_status.get('state', 'stopped'),
        'startup_verified': bool(startup_verified),
        'stdout_log': str(stdout_path).replace('\\', '/'),
        'stderr_log': str(stderr_path).replace('\\', '/'),
    }


def _ops_runtime_status() -> Dict[str, Any]:
    return _runtime_observer_status()


def _ops_runtime_stop(timeout_sec: float = 8.0) -> Dict[str, Any]:
    baseline_monitor_packet = _baseline_monitor_stop(timeout_sec=max(0.0, float(timeout_sec)))
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
    if str(baseline_monitor_packet.get('decision', 'go')) != 'go':
        reasons.extend(list(baseline_monitor_packet.get('reason_codes', [])))

    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if (stopped_cleanly and str(baseline_monitor_packet.get('decision', 'go')) == 'go') else 'no-go',
        'action': 'runtime-stop',
        'reason_codes': reasons,
        'signal_path': str(signal_path).replace('\\', '/'),
        'stop_timeout_sec': float(timeout_sec),
        'observer_pid': pid_value,
        'stopped_cleanly': bool(stopped_cleanly),
        'escalated_terminate': bool(escalated_terminate),
        'baseline_monitor_packet': baseline_monitor_packet,
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
        monitor_packet = _baseline_monitor_start(
            source=source_norm,
            mode=mode_norm,
            normal_interval_sec=float(RESOURCE_NORMAL_INTERVAL_SEC),
            baseline_interval_sec=float(_posture_cadence_defaults(mode_norm)['baseline_validation_interval_seconds']),
            baseline_window_sec=float(RESOURCE_BASELINE_WINDOW_SEC),
            baseline_sample_interval_sec=float(RESOURCE_BASELINE_INTERVAL_SEC),
            min_normal_samples=int(RESOURCE_BASELINE_MIN_NORMAL_SAMPLES),
            min_baseline_samples=int(RESOURCE_BASELINE_MIN_BASELINE_SAMPLES),
            startup_probe_sec=3.0,
        )
        reasons = []
        if str(monitor_packet.get('decision', 'go')) != 'go':
            reasons.extend(list(monitor_packet.get('reason_codes', ['critical_check_failed:baseline_monitor_start_failed'])))
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'go' if len(reasons) == 0 else 'no-go',
            'action': 'runtime-start',
            'reason_codes': reasons,
            'launcher_path': str(launcher_path).replace('\\', '/'),
            'launcher_pid': int(getattr(proc, 'pid', 0) or 0),
            'launcher_stdout_log': str(start_stdout_path).replace('\\', '/'),
            'launcher_stderr_log': str(start_stderr_path).replace('\\', '/'),
            'startup_verified': bool(str(status.get('state', '')) == 'active'),
            'state': status.get('state', 'degraded'),
            'pid': status.get('pid', {}),
            'baseline_monitor_packet': monitor_packet,
        }

    deadline = time.time() + timeout_s
    while time.time() <= deadline:
        status = _runtime_observer_status()
        if str(status.get('state', '')) == 'active':
            monitor_packet = _baseline_monitor_start(
                source=source_norm,
                mode=mode_norm,
                normal_interval_sec=float(RESOURCE_NORMAL_INTERVAL_SEC),
                baseline_interval_sec=float(_posture_cadence_defaults(mode_norm)['baseline_validation_interval_seconds']),
                baseline_window_sec=float(RESOURCE_BASELINE_WINDOW_SEC),
                baseline_sample_interval_sec=float(RESOURCE_BASELINE_INTERVAL_SEC),
                min_normal_samples=int(RESOURCE_BASELINE_MIN_NORMAL_SAMPLES),
                min_baseline_samples=int(RESOURCE_BASELINE_MIN_BASELINE_SAMPLES),
                startup_probe_sec=3.0,
            )
            reasons = []
            if str(monitor_packet.get('decision', 'go')) != 'go':
                reasons.extend(list(monitor_packet.get('reason_codes', ['critical_check_failed:baseline_monitor_start_failed'])))
            return {
                'timestamp_utc': _utc_now(),
                'runtime_cli_surface': 'observerctl',
                'decision': 'go' if len(reasons) == 0 else 'no-go',
                'action': 'runtime-start',
                'reason_codes': reasons,
                'launcher_path': str(launcher_path).replace('\\', '/'),
                'launcher_pid': int(getattr(proc, 'pid', 0) or 0),
                'launcher_stdout_log': str(start_stdout_path).replace('\\', '/'),
                'launcher_stderr_log': str(start_stderr_path).replace('\\', '/'),
                'startup_verified': True,
                'state': status.get('state', 'degraded'),
                'pid': status.get('pid', {}),
                'baseline_monitor_packet': monitor_packet,
            }
        time.sleep(0.25)

    final_status = _runtime_observer_status()
    monitor_packet = _baseline_monitor_start(
        source=source_norm,
        mode=mode_norm,
        normal_interval_sec=float(RESOURCE_NORMAL_INTERVAL_SEC),
        baseline_interval_sec=float(_posture_cadence_defaults(mode_norm)['baseline_validation_interval_seconds']),
        baseline_window_sec=float(RESOURCE_BASELINE_WINDOW_SEC),
        baseline_sample_interval_sec=float(RESOURCE_BASELINE_INTERVAL_SEC),
        min_normal_samples=int(RESOURCE_BASELINE_MIN_NORMAL_SAMPLES),
        min_baseline_samples=int(RESOURCE_BASELINE_MIN_BASELINE_SAMPLES),
        startup_probe_sec=3.0,
    )
    reasons = []
    if str(monitor_packet.get('decision', 'go')) != 'go':
        reasons.extend(list(monitor_packet.get('reason_codes', ['critical_check_failed:baseline_monitor_start_failed'])))
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if len(reasons) == 0 else 'no-go',
        'action': 'runtime-start',
        'reason_codes': reasons,
        'advisory_reason_codes': ['startup_pending:observer_not_active_within_probe_window'],
        'launcher_path': str(launcher_path).replace('\\', '/'),
        'launcher_pid': int(getattr(proc, 'pid', 0) or 0),
        'launcher_stdout_log': str(start_stdout_path).replace('\\', '/'),
        'launcher_stderr_log': str(start_stderr_path).replace('\\', '/'),
        'startup_verified': False,
        'state': final_status.get('state', 'degraded'),
        'pid': final_status.get('pid', {}),
        'baseline_monitor_packet': monitor_packet,
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
    observer_runtime = _runtime_observer_status()
    observer_runtime_state = str(observer_runtime.get('state', 'stopped'))
    current_metrics = _observer_metrics_path(source_norm, mode)
    collection_state = _infer_collection_state(observer_runtime, current_metrics)

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
        'runtime.observer_service': {
            'state': observer_runtime_state,
            'status': 'ok' if observer_runtime_state in ('active', 'degraded') else 'err',
        },
        'runtime.collection_state': collection_state,
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

    monitor_status = _runtime_baseline_monitor_status(max_age_sec=max(90.0, RESOURCE_NORMAL_INTERVAL_SEC * 3.0))
    checks['runtime.baseline_monitor'] = {
        'state': monitor_status.get('state', 'stopped'),
        'status': 'ok' if str(monitor_status.get('state', 'stopped')) in ('active', 'degraded') else 'err',
        'heartbeat': monitor_status.get('heartbeat', {}),
        'pid': monitor_status.get('pid', {}),
        'monitor_state': monitor_status.get('monitor_state', {}),
    }

    resource_health = _resource_index_health(source_norm, mode, max_age_sec=max(RESOURCE_BASELINE_STREAM_MAX_AGE_SEC, RESOURCE_NORMAL_INTERVAL_SEC * 3.0))
    checks['watchdog.resource_stream_retention'] = resource_health

    defaults = _posture_cadence_defaults(mode)
    baseline_window_health = _baseline_window_health(
        source_norm,
        mode,
        max_age_sec=max(RESOURCE_BASELINE_WINDOW_MAX_AGE_SEC, float(defaults['baseline_validation_interval_seconds']) * 2.0),
    )
    checks['watchdog.resource_baseline_window'] = baseline_window_health

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
        'runtime.observer_service',
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

    collection_row = checks.get('runtime.collection_state', {}) if isinstance(checks, dict) else {}
    collection_status = str(collection_row.get('status', 'err')).lower()
    collection_state = str(collection_row.get('state', 'error')).lower()
    if collection_status == 'err':
        reasons.append('critical_check_failed:collection_state_incoherent')
    elif collection_state not in ('idle', 'warmup', 'collecting', 'stopped', 'error'):
        advisories.append('major_check_failed:collection_state_semantics_invalid')

    linkage = _make_run_linkage(to_mode, event='gate')
    posture_required = _posture_for_mode(to_mode)
    runtime_posture = str((checks.get('watchdog.trigger_posture') or {}).get('posture_trigger', '')).strip().lower()
    posture_transition_pending = bool(mode != to_mode and runtime_posture != posture_required)
    if runtime_posture != posture_required and not posture_transition_pending:
        reasons.append('critical_check_failed:watchdog_trigger_posture_invalid')
    elif posture_transition_pending:
        advisories.append('major_check_failed:watchdog_posture_transition_pending')

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

        resource_stream_health = checks.get('watchdog.resource_stream_retention') or {}
        if str(resource_stream_health.get('status', 'err')).lower() != 'ok':
            reasons.append('critical_check_failed:resource_stream_retention_unavailable')

        baseline_window_health = checks.get('watchdog.resource_baseline_window') or {}
        if str(baseline_window_health.get('status', 'err')).lower() != 'ok':
            reasons.append('critical_check_failed:resource_baseline_window_incomplete')

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
        'major_checks': ['runtime.collection_state'],
        'from_state': '{0}:{1}'.format(from_source, mode),
        'to_state': '{0}:{1}'.format(source, to_mode),
        'profile': profile,
        'runtime_label': 'observer',
        'runtime_cli_surface': 'observerctl',
        'advisory_reason_codes': advisories,
    }
    packet.update(linkage)
    return packet


def _collect_evidence_refs(checks: Dict[str, Any]) -> List[str]:
    refs: List[str] = []

    def _add(value: Any) -> None:
        text = str(value or '').strip()
        if text and text not in refs:
            refs.append(text)

    _add((checks.get('heartbeat.watchdog') or {}).get('path', ''))
    _add((checks.get('heartbeat.observer') or {}).get('path', ''))
    _add((checks.get('heartbeat.librarian') or {}).get('path', ''))
    _add((checks.get('watchdog.trigger_posture') or {}).get('path', ''))
    _add((checks.get('watchdog.resource_metrics') or {}).get('path', ''))
    _add((checks.get('store.pointer_consistent') or {}).get('active_store_pointer', ''))

    monitor_row = checks.get('runtime.baseline_monitor') or {}
    _add((monitor_row.get('heartbeat') or {}).get('path', ''))
    _add((monitor_row.get('pid') or {}).get('path', ''))
    _add(str(_baseline_monitor_state_path()).replace('\\', '/'))

    resource_row = checks.get('watchdog.resource_stream_retention') or {}
    _add(resource_row.get('path', ''))
    latest_record = resource_row.get('latest_record', {}) if isinstance(resource_row.get('latest_record', {}), dict) else {}
    _add(latest_record.get('segment_path', ''))

    baseline_row = checks.get('watchdog.resource_baseline_window') or {}
    _add(baseline_row.get('packet_path', ''))

    return refs


def _build_readiness_surfaces(status_packet: Dict[str, Any], gate_packet: Dict[str, Any]) -> Dict[str, Any]:
    checks = status_packet.get('checks', {}) if isinstance(status_packet, dict) else {}
    target_state = str(gate_packet.get('to_state', ''))
    target_mode = target_state.split(':')[-1] if ':' in target_state else str(status_packet.get('mode', 'watch'))
    current_mode = str(status_packet.get('mode', 'watch')).strip().lower()

    monitor_row = checks.get('runtime.baseline_monitor') or {}
    resource_row = checks.get('watchdog.resource_stream_retention') or {}
    baseline_row = checks.get('watchdog.resource_baseline_window') or {}
    monitor_state = monitor_row.get('monitor_state', {}) if isinstance(monitor_row.get('monitor_state', {}), dict) else {}
    projection_mode = 'non-activation' if target_mode != current_mode else 'current-state'
    projected_defaults = _posture_cadence_defaults(target_mode)

    return {
        'target_state': target_state,
        'target_mode': target_mode,
        'current_mode': current_mode,
        'projection_mode': projection_mode,
        'target_posture': _posture_for_mode(target_mode),
        'gate_decision': str(gate_packet.get('decision', 'no-go')).lower(),
        'gate_reason_codes': list(gate_packet.get('reason_codes', [])) if isinstance(gate_packet.get('reason_codes', []), list) else [],
        'posture_receipt': {
            'status': str((checks.get('watchdog.trigger_posture') or {}).get('status', 'err')).lower(),
            'path': str((checks.get('watchdog.trigger_posture') or {}).get('path', '')),
            'posture_trigger': str((checks.get('watchdog.trigger_posture') or {}).get('posture_trigger', '')),
            'heartbeat_interval_seconds': (checks.get('watchdog.heartbeat_interval_seconds') or {}).get('value'),
            'baseline_validation_interval_seconds': (checks.get('watchdog.baseline_validation_interval_seconds') or {}).get('value'),
        },
        'projected_posture_receipt': {
            'status': 'ok' if projection_mode == 'non-activation' else 'not_applicable',
            'projection_basis': 'target_mode_defaults' if projection_mode == 'non-activation' else 'current-state',
            'posture_trigger': str(projected_defaults.get('posture_trigger', '')),
            'heartbeat_interval_seconds': projected_defaults.get('heartbeat_interval_seconds'),
            'baseline_validation_interval_seconds': projected_defaults.get('baseline_validation_interval_seconds'),
        },
        'resource_metrics': {
            'status': str((checks.get('watchdog.resource_metrics') or {}).get('status', 'err')).lower(),
            'path': str((checks.get('watchdog.resource_metrics') or {}).get('path', '')),
            'sample_age_seconds': (checks.get('watchdog.resource_metrics') or {}).get('sample_age_seconds'),
        },
        'baseline_monitor': {
            'status': str(monitor_row.get('status', 'err')).lower(),
            'state': str(monitor_row.get('state', 'stopped')),
            'heartbeat_path': str((monitor_row.get('heartbeat') or {}).get('path', '')),
            'pid_path': str((monitor_row.get('pid') or {}).get('path', '')),
            'monitor_state_path': str(_baseline_monitor_state_path()).replace('\\', '/'),
            'monitor_state': monitor_state,
        },
        'resource_stream_retention': {
            'status': str(resource_row.get('status', 'err')).lower(),
            'index_path': str(resource_row.get('path', '')),
            'latest_segment_path': str(((resource_row.get('latest_record', {}) or {}).get('segment_path', '')) if isinstance(resource_row.get('latest_record', {}), dict) else ''),
            'records_indexed': int(resource_row.get('records_indexed', 0) or 0),
        },
        'baseline_window': {
            'status': str(baseline_row.get('status', 'err')).lower(),
            'packet_path': str(baseline_row.get('packet_path', '')),
            'decision': str(baseline_row.get('decision', 'no-go')),
            'sample_counts': baseline_row.get('sample_counts', {}) if isinstance(baseline_row.get('sample_counts', {}), dict) else {},
        },
        'librarian_retention': {
            'status': str((checks.get('store.integrity_ok') or {}).get('status', 'err')).lower(),
            'active_store_pointer': str((checks.get('store.pointer_consistent') or {}).get('active_store_pointer', '')),
            'retention_state': str((checks.get('store.integrity_ok') or {}).get('retention_state', '')),
        },
    }


def _build_stage5_prerequisites(readiness_surfaces: Dict[str, Any]) -> Dict[str, Any]:
    target_posture = str(readiness_surfaces.get('target_posture', '')).strip().lower()
    posture_receipt = readiness_surfaces.get('posture_receipt', {}) if isinstance(readiness_surfaces.get('posture_receipt', {}), dict) else {}
    projected_posture_receipt = readiness_surfaces.get('projected_posture_receipt', {}) if isinstance(readiness_surfaces.get('projected_posture_receipt', {}), dict) else {}
    resource_stream = readiness_surfaces.get('resource_stream_retention', {}) if isinstance(readiness_surfaces.get('resource_stream_retention', {}), dict) else {}
    baseline_window = readiness_surfaces.get('baseline_window', {}) if isinstance(readiness_surfaces.get('baseline_window', {}), dict) else {}
    baseline_monitor = readiness_surfaces.get('baseline_monitor', {}) if isinstance(readiness_surfaces.get('baseline_monitor', {}), dict) else {}
    projection_mode = str(readiness_surfaces.get('projection_mode', 'current-state')).strip().lower()

    cadence_source = posture_receipt
    cadence_evidence_refs: List[str] = [str(posture_receipt.get('path', ''))] if str(posture_receipt.get('path', '')).strip() else []
    if target_posture == 'lockdown' and projection_mode == 'non-activation':
        cadence_source = projected_posture_receipt
        cadence_evidence_refs = [str(posture_receipt.get('path', ''))] if str(posture_receipt.get('path', '')).strip() else []

    hb_interval = _to_float_or_none(cadence_source.get('heartbeat_interval_seconds'))
    baseline_interval = _to_float_or_none(cadence_source.get('baseline_validation_interval_seconds'))
    cadence_ready = bool(
        target_posture == 'lockdown'
        and hb_interval is not None and 3.0 <= hb_interval <= 5.0
        and _is_lockdown_baseline_cadence(baseline_interval)
    )
    resource_ready = str(resource_stream.get('status', 'err')).lower() == 'ok'
    baseline_ready = (
        str(baseline_window.get('status', 'err')).lower() == 'ok'
        and str(baseline_window.get('decision', 'no-go')).lower() == 'go'
    )
    monitor_ready = str(baseline_monitor.get('status', 'err')).lower() == 'ok'

    prereqs = {
        'C22_baseline_validation_rate_escalated': {
            'status': 'ok' if cadence_ready else ('not_applicable' if target_posture != 'lockdown' else 'err'),
            'reason_codes': [] if cadence_ready or target_posture != 'lockdown' else ['critical_check_failed:lockdown_baseline_rate_not_escalated'],
            'expected_heartbeat_interval_seconds_band': [3, 5],
            'expected_baseline_validation_interval_seconds_band': [30, 60],
            'actual_heartbeat_interval_seconds': hb_interval,
            'actual_baseline_validation_interval_seconds': baseline_interval,
            'projection_mode': projection_mode,
            'evidence_refs': cadence_evidence_refs,
        },
        'C24_resource_stream_retention_ready': {
            'status': 'ok' if resource_ready else 'err',
            'reason_codes': [] if resource_ready else ['critical_check_failed:resource_stream_retention_unavailable'],
            'records_indexed': int(resource_stream.get('records_indexed', 0) or 0),
            'evidence_refs': [
                ref for ref in [
                    str(resource_stream.get('index_path', '')),
                    str(resource_stream.get('latest_segment_path', '')),
                ] if ref.strip()
            ],
        },
        'C25_resource_baseline_window_ready': {
            'status': 'ok' if baseline_ready else 'err',
            'reason_codes': [] if baseline_ready else ['critical_check_failed:resource_baseline_window_incomplete'],
            'decision': str(baseline_window.get('decision', 'no-go')),
            'sample_counts': baseline_window.get('sample_counts', {}) if isinstance(baseline_window.get('sample_counts', {}), dict) else {},
            'evidence_refs': [str(baseline_window.get('packet_path', ''))] if str(baseline_window.get('packet_path', '')).strip() else [],
        },
        'baseline_monitor_runtime_ready': {
            'status': 'ok' if monitor_ready else 'err',
            'reason_codes': [] if monitor_ready else ['critical_check_failed:baseline_monitor_runtime_inactive'],
            'state': str(baseline_monitor.get('state', 'stopped')),
            'evidence_refs': [
                ref for ref in [
                    str(baseline_monitor.get('heartbeat_path', '')),
                    str(baseline_monitor.get('pid_path', '')),
                    str(baseline_monitor.get('monitor_state_path', '')),
                ] if ref.strip()
            ],
        },
    }

    overall_ready = all(
        str((row or {}).get('status', 'err')).lower() == 'ok'
        for row in prereqs.values()
        if isinstance(row, dict) and str((row or {}).get('status', 'err')).lower() != 'not_applicable'
    )
    prereqs['overall'] = {
        'status': 'ok' if overall_ready else 'err',
        'target_posture': target_posture,
        'evaluated_classes': ['C22_baseline_validation_rate_escalated', 'C24_resource_stream_retention_ready', 'C25_resource_baseline_window_ready', 'baseline_monitor_runtime_ready'],
    }
    return prereqs


def build_evidence_pack(status_packet: Dict[str, Any], gate_packet: Dict[str, Any], event: str = 'manual') -> Dict[str, Any]:
    checks = status_packet.get('checks', {}) if isinstance(status_packet, dict) else {}
    evidence_refs = _collect_evidence_refs(checks)
    readiness_surfaces = _build_readiness_surfaces(status_packet, gate_packet)
    stage5_prerequisites = _build_stage5_prerequisites(readiness_surfaces)

    methodology = {
        'sampling_strategy': 'names-only runtime posture and retained-readiness sampling from health/data/control artifacts',
        'runtime_constraints': [
            'standalone observer scope only',
            'no CodeSentinel runtime process dependency',
            'fail-closed gate semantics',
            'non-activation readiness projection supported via target-mode gate evaluation',
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
            'observerctl ops evidence pack --to <mode> --event <event> --json',
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
        'readiness_surfaces': readiness_surfaces,
        'stage5_prerequisites': stage5_prerequisites,
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


def _resolve_min_baseline_samples(args: argparse.Namespace, default: int) -> int:
    canonical = getattr(args, 'min_baseline_samples', None)
    legacy = getattr(args, 'min_rapid_samples', None)

    try:
        canonical_i = None if canonical is None else int(canonical)
    except Exception:
        canonical_i = None
    try:
        legacy_i = None if legacy is None else int(legacy)
    except Exception:
        legacy_i = None

    if canonical_i is not None and canonical_i != int(default):
        return canonical_i
    if legacy_i is not None and legacy_i > 0:
        return legacy_i
    if canonical_i is not None:
        return canonical_i
    return int(default)


def _resolve_cli_min_baseline_samples(args: argparse.Namespace) -> int:
    return _resolve_min_baseline_samples(args, 300)


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


def _fs_baseline_path() -> Path:
    return _control_file(FS_BASELINE_FILE)


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open('rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ''


def _fs_should_exclude(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except Exception:
        return True
    parts = set(rel.parts)
    for token in FS_BASELINE_EXCLUDE:
        if token in parts:
            return True
    name = path.name.lower()
    if name.endswith('.pyc') or name.endswith('.pyo'):
        return True
    return False


def _iter_fs_files(root: Path, max_files: int) -> List[Path]:
    out: List[Path] = []
    limit = max(1, int(max_files or 20000))
    try:
        for p in sorted(root.rglob('*')):
            if len(out) >= limit:
                break
            try:
                if not p.is_file():
                    continue
            except Exception:
                continue
            if _fs_should_exclude(p, root):
                continue
            out.append(p)
    except Exception:
        return out
    return out


def _baseline_hash_generate(max_files: int, output: str) -> Dict[str, Any]:
    root = _project_root()
    files = _iter_fs_files(root, max_files=max_files)
    records: Dict[str, Dict[str, Any]] = {}
    skipped = 0
    for p in files:
        try:
            rel = p.relative_to(root).as_posix()
        except Exception:
            skipped += 1
            continue
        digest = _file_sha256(p)
        if not digest:
            skipped += 1
            continue
        records[rel] = {
            'hash': digest,
            'size': int(_safe_file_size(p)),
            'modified_epoch': float(p.stat().st_mtime),
        }

    payload = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'baseline_type': 'filesystem_hash',
        'workspace_root': str(root).replace('\\', '/'),
        'files': records,
        'statistics': {
            'tracked_files': int(len(records)),
            'skipped_files': int(skipped),
            'max_files': int(max(1, int(max_files or 20000))),
            'safety_limit_hit': bool(len(files) >= max(1, int(max_files or 20000))),
        },
    }

    out_path = Path(str(output).strip()) if str(output).strip() else _fs_baseline_path()
    _write_json_file(out_path, payload)
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-generate',
        'baseline_path': str(out_path).replace('\\', '/'),
        'statistics': payload.get('statistics', {}),
        'reason_codes': [],
    }


def _baseline_hash_status(baseline: str) -> Dict[str, Any]:
    path = Path(str(baseline).strip()) if str(baseline).strip() else _fs_baseline_path()
    exists = path.exists()
    payload = _load_json_file(path, {}) if exists else {}
    stats = payload.get('statistics', {}) if isinstance(payload.get('statistics', {}), dict) else {}
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'baseline-status',
        'baseline_type': 'filesystem_hash',
        'baseline_path': str(path).replace('\\', '/'),
        'exists': bool(exists),
        'generated_at_utc': str(payload.get('timestamp_utc', '')) if exists else '',
        'statistics': stats,
        'decision': 'go' if exists else 'no-go',
        'reason_codes': [] if exists else ['critical_check_failed:fs_baseline_missing'],
    }


def _baseline_hash_check(baseline: str) -> Dict[str, Any]:
    root = _project_root()
    path = Path(str(baseline).strip()) if str(baseline).strip() else _fs_baseline_path()
    if not path.exists():
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'baseline-check',
            'baseline_type': 'filesystem_hash',
            'baseline_path': str(path).replace('\\', '/'),
            'reason_codes': ['critical_check_failed:fs_baseline_missing'],
            'statistics': {
                'files_checked': 0,
                'files_modified': 0,
                'files_missing': 0,
                'files_new': 0,
            },
        }

    baseline_doc = _load_json_file(path, {})
    baseline_files = baseline_doc.get('files', {}) if isinstance(baseline_doc.get('files', {}), dict) else {}

    modified: List[Dict[str, str]] = []
    missing: List[str] = []
    baseline_paths = set(baseline_files.keys())

    for rel, info in baseline_files.items():
        p = root / rel
        if not p.exists():
            missing.append(rel)
            continue
        current = _file_sha256(p)
        expected = str((info or {}).get('hash', ''))
        if current != expected:
            modified.append({'file': rel, 'expected_hash': expected, 'actual_hash': current})

    current_files = set()
    for p in _iter_fs_files(root, max_files=max(1, len(baseline_paths) + 5000)):
        try:
            rel = p.relative_to(root).as_posix()
        except Exception:
            continue
        current_files.add(rel)

    new_files = sorted(list(current_files - baseline_paths))
    try:
        rel_baseline = path.relative_to(root).as_posix()
        new_files = [x for x in new_files if x != rel_baseline]
    except Exception:
        pass

    reasons: List[str] = []
    if modified:
        reasons.append('critical_check_failed:fs_hash_mismatch')
    if missing:
        reasons.append('critical_check_failed:fs_baseline_file_missing')
    if new_files:
        reasons.append('major_check_failed:fs_new_files_detected')

    decision = 'go' if len(reasons) == 0 else 'no-go'
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': decision,
        'action': 'baseline-check',
        'baseline_type': 'filesystem_hash',
        'baseline_path': str(path).replace('\\', '/'),
        'reason_codes': reasons,
        'statistics': {
            'files_checked': int(len(baseline_files)),
            'files_modified': int(len(modified)),
            'files_missing': int(len(missing)),
            'files_new': int(len(new_files)),
        },
        'violations': {
            'modified': modified[:25],
            'missing': missing[:25],
            'new_files': new_files[:25],
        },
    }


def _resource_index_path(source: str, mode: str) -> Path:
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'
    return get_calamum_data_dir() / 'observer_derived' / src / m / 'resource' / 'index.jsonl'


def _resource_evidence_output_path(source: str, mode: str, event: str) -> Path:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'
    ev = str(event or 'baseline').strip().lower().replace(' ', '-').replace('_', '-')
    return get_calamum_data_dir() / 'observer_derived' / src / m / 'evidence' / 'observerctl_{0}_{1}.json'.format(ev, ts)


def _resource_archive_dir() -> Path:
    p = get_calamum_data_dir() / 'archive'
    p.mkdir(parents=True, exist_ok=True)
    return p


def _resource_segment_prefix(source: str, mode: str, profile: str, window_id: str) -> str:
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'
    prof = _normalize_resource_profile(profile)
    wid = str(window_id or '').strip() or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return 'resource_{0}_{1}_{2}_{3}'.format(src, m, prof, wid)


def _resource_segment_path(source: str, mode: str, profile: str, window_id: str, segment_id: int) -> Path:
    prefix = _resource_segment_prefix(source, mode, profile, window_id)
    name = '{0}_seg{1:04d}.jsonl'.format(prefix, int(max(1, segment_id)))
    return _resource_archive_dir() / name


def _safe_sleep(seconds: float) -> None:
    s = max(0.0, float(seconds or 0.0))
    if s <= 0.0:
        return
    time.sleep(s)


def _emit_progress(message: str, enabled: bool = True) -> None:
    """Emit a bounded operator progress line to stderr.

    This is intentionally stderr-only so JSON packet output on stdout remains
    machine-parseable.
    """
    if not bool(enabled):
        return
    try:
        line = '[observerctl] {0} {1}'.format(_utc_now(), str(message or '').strip())
        print(line, file=sys.stderr, flush=True)
    except Exception:
        # Progress output must never break command execution semantics.
        return


def _touch_observer_service_heartbeat() -> None:
    try:
        hb = get_calamum_health_dir() / 'calamum_observer.heartbeat'
        hb.parent.mkdir(parents=True, exist_ok=True)
        hb.touch(exist_ok=True)
    except Exception:
        pass


def _resource_sample() -> Dict[str, Any]:
    cpu_now = 0.0
    ram_now = 0.0
    try:
        # Use non-blocking CPU sampling to avoid introducing interval delay coupling.
        cpu_now = float(psutil.cpu_percent(interval=None))
    except Exception:
        cpu_now = 0.0
    try:
        ram_now = float(psutil.virtual_memory().percent)
    except Exception:
        ram_now = 0.0
    return {
        'timestamp_utc': _utc_now(),
        'epoch_s': float(time.time()),
        'cpu_pct_now': float(cpu_now),
        'ram_pct_now': float(ram_now),
    }


def _percentile(values: List[float], pct: float) -> float:
    vals = [float(v) for v in values if v is not None]
    if len(vals) == 0:
        return 0.0
    vals.sort()
    p = max(0.0, min(100.0, float(pct)))
    if len(vals) == 1:
        return float(vals[0])
    rank = (p / 100.0) * (len(vals) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(vals[lo])
    frac = rank - float(lo)
    return float(vals[lo] * (1.0 - frac) + vals[hi] * frac)


def _parse_jsonl_lines(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    try:
        if path.suffix.lower() == '.gz':
            with gzip.open(path, 'rt', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    ln = str(line or '').strip()
                    if not ln:
                        continue
                    try:
                        row = json.loads(ln)
                    except Exception:
                        continue
                    if isinstance(row, dict):
                        out.append(row)
            return out

        with path.open('r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                ln = str(line or '').strip()
                if not ln:
                    continue
                try:
                    row = json.loads(ln)
                except Exception:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except Exception:
        return out
    return out


def _resource_candidate_files(source: str, mode: str, profile: Optional[str] = None) -> List[Path]:
    archive_dir = _resource_archive_dir()
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'
    prof = _normalize_resource_profile(profile) if str(profile or '').strip() else ''
    pattern_prefix = 'resource_{0}_{1}_'.format(src, m)

    files: List[Path] = []
    for p in sorted(archive_dir.glob('resource_{0}_{1}_*.jsonl'.format(src, m))):
        name = p.name.lower()
        if not name.startswith(pattern_prefix):
            continue
        if prof == 'baseline':
            if ('_baseline_' not in name) and ('_rapid_' not in name):
                continue
        elif prof and ('_{0}_'.format(prof) not in name):
            continue
        files.append(p)
    for p in sorted(archive_dir.glob('resource_{0}_{1}_*.jsonl.gz'.format(src, m))):
        name = p.name.lower()
        if not name.startswith(pattern_prefix):
            continue
        if prof == 'baseline':
            if ('_baseline_' not in name) and ('_rapid_' not in name):
                continue
        elif prof and ('_{0}_'.format(prof) not in name):
            continue
        files.append(p)
    return files


def _fmt_int(value: Any) -> str:
    try:
        return '{0:,}'.format(int(value or 0))
    except Exception:
        return '0'


def _fmt_bytes(value: Any) -> str:
    try:
        n = float(value or 0)
    except Exception:
        n = 0.0
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    idx = 0
    while n >= 1024.0 and idx < len(units) - 1:
        n /= 1024.0
        idx += 1
    if idx == 0:
        return '{0} {1}'.format(int(n), units[idx])
    return '{0:.1f} {1}'.format(n, units[idx])


def _render_librarian_stats_human(packet: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    lines.append('Librarian stats')
    ts = str(packet.get('timestamp_utc', '') or '').strip()
    if ts:
        lines.append('generated_at_utc: {0}'.format(ts))

    summary = packet.get('archive_manifest_summary', {}) if isinstance(packet.get('archive_manifest_summary', {}), dict) else {}
    totals = summary.get('totals', {}) if isinstance(summary.get('totals', {}), dict) else {}
    manifest_path = str(summary.get('manifest_path', '') or '').strip()
    manifest_exists = bool(summary.get('manifest_exists', False))

    lines.append('archive_manifest: {0}'.format('present' if manifest_exists else 'missing'))
    if manifest_path:
        lines.append('archive_manifest_path: {0}'.format(manifest_path))
    lines.append(
        'archive_totals: bundles={0} records={1} compressed={2} uncompressed={3}'.format(
            _fmt_int(totals.get('bundle_count', 0)),
            _fmt_int(totals.get('records', 0)),
            _fmt_bytes(totals.get('compressed_bytes', 0)),
            _fmt_bytes(totals.get('uncompressed_bytes', 0)),
        )
    )

    stores = packet.get('stores', []) if isinstance(packet.get('stores', []), list) else []
    lines.append('')
    lines.append('per_mode:')
    for row in stores:
        if not isinstance(row, dict):
            continue
        mode = str(row.get('mode', 'unknown')).upper()
        lines.append('- {0}'.format(mode))
        lines.append(
            '  session_records_display: {0} ({1})'.format(
                _fmt_int(row.get('session_records_display', row.get('session_records', 0))),
                _fmt_bytes(row.get('session_bytes_display', row.get('session_bytes', 0))),
            )
        )
        lines.append(
            '  archive_records: {0} | archive_bundles: {1}'.format(
                _fmt_int(row.get('archive_records', 0)),
                _fmt_int(row.get('archive_bundle_count', 0)),
            )
        )
        lines.append(
            '  compressed_archive_size: {0} | uncompressed_archive_size: {1}'.format(
                _fmt_bytes(row.get('archive_compressed_bytes', 0)),
                _fmt_bytes(row.get('archive_uncompressed_bytes', 0)),
            )
        )
        lines.append(
            '  compacted_bundles: {0} | total_records_display: {1}'.format(
                _fmt_int(row.get('compacted_bundle_count', 0)),
                _fmt_int(row.get('records_total_display', row.get('record_count', 0))),
            )
        )
    return lines


def _render_librarian_stores_human(packet: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    lines.append('Librarian stores')
    ts = str(packet.get('timestamp_utc', '') or '').strip()
    if ts:
        lines.append('generated_at_utc: {0}'.format(ts))
    stores = packet.get('stores', []) if isinstance(packet.get('stores', []), list) else []
    for row in stores:
        if not isinstance(row, dict):
            continue
        mode = str(row.get('mode', 'unknown'))
        is_active = bool(row.get('active', False))
        exists = bool(row.get('exists', False))
        retention = str(row.get('retention_state', 'unknown'))
        path = str(row.get('path', ''))
        lines.append(
            '- {0}{1}: exists={2} retention={3} path={4}'.format(
                mode,
                ' [active]' if is_active else '',
                'yes' if exists else 'no',
                retention,
                path,
            )
        )
    return lines


def _render_human_known_packet(packet: Dict[str, Any]) -> Optional[List[str]]:
    if not isinstance(packet, dict):
        return None
    sandbox_lines = render_sandbox_human_packet(packet)
    if isinstance(sandbox_lines, list) and len(sandbox_lines) > 0:
        return sandbox_lines
    stores = packet.get('stores', [])
    if not isinstance(stores, list):
        return None
    # librarian stats
    if isinstance(packet.get('archive_manifest_summary', None), dict):
        return _render_librarian_stats_human(packet)
    # librarian stores
    if stores and isinstance(stores[0], dict) and ('active' in stores[0] or 'manifest_path' in stores[0]):
        return _render_librarian_stores_human(packet)
    return None


def _emit(packet: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(packet, indent=2, sort_keys=True))
        return

    rendered = _render_human_known_packet(packet)
    if isinstance(rendered, list) and len(rendered) > 0:
        for line in rendered:
            print(line)
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


def _sandbox_list() -> Dict[str, Any]:
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'sandbox-list',
        'template_class': 'decision',
        'template_variant': 'catalog',
        'decision': 'go',
        'definitions': [
            {
                'id': str(row.get('id', '') or ''),
                'title': str(row.get('title', '') or ''),
                'summary': str(row.get('summary', '') or ''),
                'status': str(row.get('status', '') or ''),
                'category': str(row.get('category', '') or ''),
                'writes_to': str(row.get('writes_to', '') or ''),
            }
            for row in sandbox_get_definitions()
        ],
    }


def _sandbox_show(definition_id: str) -> Dict[str, Any]:
    definition = sandbox_get_definition(definition_id)
    if definition is None:
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'action': 'sandbox-show',
            'template_class': 'validation',
            'template_variant': 'definition_detail',
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:unknown_sandbox_definition'],
            'definition_id': str(definition_id or ''),
        }
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'sandbox-show',
        'template_class': 'validation',
        'template_variant': 'definition_detail',
        'decision': 'go',
        'definition': {
            key: value
            for key, value in definition.items()
            if key != 'runner'
        },
    }


def _sandbox_run(definition_id: str) -> Dict[str, Any]:
    packet = sandbox_run_definition(definition_id)
    packet.update({
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'sandbox-run',
        'template_class': 'transition',
        'template_variant': 'execution',
    })
    return packet


def _sandbox_runs_list() -> Dict[str, Any]:
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'sandbox-runs-list',
        'template_class': 'validation',
        'template_variant': 'run_catalog',
        'decision': 'go',
        'runs': sandbox_list_runs(),
    }


def _sandbox_runs_show(run_id: str) -> Dict[str, Any]:
    found = sandbox_get_run(run_id)
    if found is None:
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'action': 'sandbox-runs-show',
            'template_class': 'validation',
            'template_variant': 'run_review',
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:sandbox_run_not_found'],
            'run_id': str(run_id or ''),
        }
    run_row, report_payload = found
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'sandbox-runs-show',
        'template_class': 'validation',
        'template_variant': 'run_review',
        'decision': 'go',
        'run': run_row,
        'report': report_payload,
    }


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
    prior_state = _load_state()
    rollback_anchor = {
        'source': str(prior_state.get('source', 'sim')),
        'mode': str(prior_state.get('mode', 'watch')),
    }
    state = _save_state(source=source, mode=to_mode)
    posture_packet = _apply_watchdog_posture(state['source'], state['mode'], event='mode-set')
    if posture_packet.get('decision') != 'go':
        restored_state = _save_state(source=rollback_anchor['source'], mode=rollback_anchor['mode'])
        restored_readback = _load_state()
        rollback_verified = (
            _normalize_source(str(restored_readback.get('source', 'sim'))) == _normalize_source(rollback_anchor['source'])
            and str(restored_readback.get('mode', 'watch')).strip().lower() == str(rollback_anchor['mode']).strip().lower()
        )
        reason_codes = list(posture_packet.get('reason_codes', ['critical_check_failed:watchdog_posture_persist_failed']))
        if not rollback_verified and 'critical_check_failed:mode_set_rollback_unverified' not in reason_codes:
            reason_codes.append('critical_check_failed:mode_set_rollback_unverified')
        return {
            'timestamp_utc': _utc_now(),
            'decision': 'no-go',
            'reason_codes': reason_codes,
            'runtime_cli_surface': 'observerctl',
            'from_state': gate.get('from_state', ''),
            'attempted_to_state': expected_to_state,
            'rollback_anchor': rollback_anchor,
            'rollback_applied': bool(rollback_verified),
            'restored_state': {
                'source': str(restored_state.get('source', 'sim')),
                'mode': str(restored_state.get('mode', 'watch')),
            },
            'restored_readback_state': {
                'source': str(restored_readback.get('source', 'sim')),
                'mode': str(restored_readback.get('mode', 'watch')),
            },
            'posture_packet': posture_packet,
        }
    response = {
        'timestamp_utc': _utc_now(),
        'decision': 'go',
        'runtime_cli_surface': 'observerctl',
        'from_state': gate.get('from_state', ''),
        'to_state': '{0}:{1}'.format(state['source'], state['mode']),
        'rollback_anchor': rollback_anchor,
        'posture_packet': posture_packet,
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


def _ops_mode_switch(
    source: str,
    to_mode: str,
    event: str,
    output: str,
    interval_sec: float,
    stop_timeout_sec: float,
    startup_probe_sec: float,
) -> Dict[str, Any]:
    """Single-action mode switch: validate + gate + set + runtime sync + verify."""
    source_norm = _normalize_source(source)
    mode_norm = str(to_mode or '').strip().lower()
    if mode_norm not in MODES:
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'phase': 'mode-switch',
            'reason_codes': ['policy_denied:target_mode_unsupported'],
        }

    status_before = collect_runtime_status(source=source_norm)
    gate = evaluate_gate_decision(status_before, target_mode=mode_norm)
    _write_json_file(_control_file(LAST_GATE_FILE), gate)
    if gate.get('decision') != 'go':
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'phase': 'mode-switch',
            'reason_codes': gate.get('reason_codes', []),
            'gate_packet': gate,
        }

    mode_set = _ops_mode_set(source_norm, mode_norm)
    if mode_set.get('decision') != 'go':
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'phase': 'mode-switch',
            'reason_codes': mode_set.get('reason_codes', ['critical_check_failed:mode_set_failed']),
            'gate_packet': gate,
            'mode_set_packet': mode_set,
        }

    runtime_before = _ops_runtime_status()
    runtime_stop_packet: Optional[Dict[str, Any]] = None
    runtime_before_state = str(runtime_before.get('state', 'stopped')).strip().lower()
    if runtime_before_state in ('active', 'degraded'):
        runtime_stop_packet = _ops_runtime_stop(timeout_sec=float(stop_timeout_sec))
        if runtime_stop_packet.get('decision') != 'go':
            return {
                'timestamp_utc': _utc_now(),
                'runtime_cli_surface': 'observerctl',
                'decision': 'no-go',
                'phase': 'mode-switch',
                'reason_codes': runtime_stop_packet.get('reason_codes', ['critical_check_failed:runtime_stop_failed']),
                'gate_packet': gate,
                'mode_set_packet': mode_set,
                'runtime_before': runtime_before,
                'runtime_stop_packet': runtime_stop_packet,
            }

    runtime_start_packet = _ops_runtime_start(
        source=source_norm,
        mode=mode_norm,
        interval_sec=float(interval_sec),
        timeout_sec=float(startup_probe_sec),
    )
    if runtime_start_packet.get('decision') != 'go':
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'phase': 'mode-switch',
            'reason_codes': runtime_start_packet.get('reason_codes', ['critical_check_failed:runtime_start_failed']),
            'gate_packet': gate,
            'mode_set_packet': mode_set,
            'runtime_before': runtime_before,
            'runtime_stop_packet': runtime_stop_packet,
            'runtime_start_packet': runtime_start_packet,
        }

    post_status = collect_runtime_status(source=source_norm)
    post_reasons: List[str] = []

    post_state_source = _normalize_source(str(post_status.get('state_source', source_norm)))
    post_mode = str(post_status.get('mode', '') or '').strip().lower()
    if post_state_source != source_norm or post_mode != mode_norm:
        post_reasons.append('critical_check_failed:ssot_state_not_applied')

    post_checks = post_status.get('checks', {}) if isinstance(post_status.get('checks', {}), dict) else {}
    observer_service_status = str((post_checks.get('runtime.observer_service') or {}).get('status', 'err')).lower()
    if observer_service_status != 'ok':
        post_reasons.append('critical_check_failed:runtime_sync_inactive')
    baseline_monitor_status = str((post_checks.get('runtime.baseline_monitor') or {}).get('status', 'err')).lower()
    if baseline_monitor_status != 'ok':
        post_reasons.append('critical_check_failed:baseline_monitor_runtime_inactive')

    evidence = build_evidence_pack(status_before, gate, event=event)
    out_path = Path(str(output).strip()) if str(output).strip() else _default_output_path(source=source_norm, mode=mode_norm, event=event)
    evidence = _write_packet(evidence, out_path)
    _append_jsonl(_evidence_index_path(source_norm, mode_norm), {
        'timestamp_utc': _utc_now(),
        'packet_path': str(out_path).replace('\\', '/'),
        'decision': 'go' if len(post_reasons) == 0 else 'no-go',
        'run_id': evidence.get('run_id', ''),
        'scope': {'source': source_norm, 'mode': mode_norm},
        'event': str(event or 'mode-switch').strip().lower().replace(' ', '-'),
    })

    result: Dict[str, Any] = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if len(post_reasons) == 0 else 'no-go',
        'phase': 'mode-switch',
        'reason_codes': post_reasons,
        'from_state': gate.get('from_state', ''),
        'to_state': '{0}:{1}'.format(source_norm, mode_norm),
        'gate_packet': gate,
        'mode_set_packet': mode_set,
        'runtime_before': runtime_before,
        'runtime_stop_packet': runtime_stop_packet,
        'runtime_start_packet': runtime_start_packet,
        'postflight_status': post_status,
        'evidence_packet': {
            'provenance': evidence.get('provenance', {}),
            'process': evidence.get('process', {}),
        },
    }

    advisory: List[str] = []
    if not bool(runtime_start_packet.get('startup_verified', False)):
        advisory.append('startup_pending:observer_not_active_within_probe_window')
    if advisory:
        result['advisory_reason_codes'] = advisory

    for key in ('run_id', 'posture_trigger_id', 'posture_trigger', 'security_report_ref'):
        result[key] = mode_set.get(key, gate.get(key, ''))
    return result


def _ops_gate_check(source: str) -> Dict[str, Any]:
    status = collect_runtime_status(source=source)
    gate = evaluate_gate_decision(status, target_mode=str(status.get('mode', 'watch')))
    _write_json_file(_control_file(LAST_GATE_FILE), gate)
    return gate
def _ops_evidence_pack(source: str, event: str, output: str, target_mode: str = '') -> Dict[str, Any]:
    status = collect_runtime_status(source=source)
    target = str(target_mode or status.get('mode', 'watch')).strip().lower()
    gate = evaluate_gate_decision(status, target_mode=target)
    packet = build_evidence_pack(status, gate, event=event)
    mode = target if target in MODES else str(status.get('mode', 'watch')).strip().lower()
    packet['readiness_projection'] = {
        'projection_mode': 'non-activation' if mode != str(status.get('mode', 'watch')).strip().lower() else 'current-state',
        'evaluated_target_mode': mode,
        'evaluated_target_state': '{0}:{1}'.format(_normalize_source(source), mode),
    }
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


def _baseline_chunked_status() -> Dict[str, Any]:
    catalog = _load_baselines()
    active_id = str(catalog.get('active', ''))
    items = catalog.get('items', [])
    active_item = next((it for it in items if str(it.get('id', '')) == active_id), None)
    exists = active_item is not None
    item_status = str((active_item or {}).get('status', '')) if exists else ''
    ready = exists and item_status == 'ready'
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'baseline-status',
        'baseline_type': 'chunked_dynamic',
        'active_baseline_id': active_id,
        'exists': exists,
        'created_at_utc': str((active_item or {}).get('created_at_utc', '')) if exists else '',
        'item_status': item_status,
        'decision': 'go' if ready else 'no-go',
        'reason_codes': [] if ready else (
            ['critical_check_failed:chunked_baseline_not_ready'] if exists
            else ['critical_check_failed:chunked_baseline_missing']
        ),
    }


def _baseline_chunked_check() -> Dict[str, Any]:
    catalog = _load_baselines()
    active_id = str(catalog.get('active', ''))
    items = catalog.get('items', [])
    active_item = next((it for it in items if str(it.get('id', '')) == active_id), None)
    exists = active_item is not None
    item_status = str((active_item or {}).get('status', '')) if exists else ''
    ready = exists and item_status == 'ready'
    reasons: List[str] = []
    if not exists:
        reasons.append('critical_check_failed:chunked_baseline_missing')
    elif item_status != 'ready':
        reasons.append('critical_check_failed:chunked_baseline_not_ready')
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'action': 'baseline-check',
        'baseline_type': 'chunked_dynamic',
        'active_baseline_id': active_id,
        'exists': exists,
        'item_status': item_status,
        'decision': 'go' if ready else 'no-go',
        'reason_codes': reasons,
    }


def _baseline_status(baseline: str = '') -> Dict[str, Any]:
    if str(baseline).strip():
        return _baseline_hash_status(baseline)
    return _baseline_chunked_status()


def _baseline_graph() -> Dict[str, Any]:
    graph = _project_root() / 'semantics_vault' / 'oracl_index' / 'weighted_graph_index.json'
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'graph_path': str(graph).replace('\\', '/'),
        'exists': graph.exists(),
        'status': 'ok' if graph.exists() else 'warn',
    }


def _baseline_check(baseline: str = '') -> Dict[str, Any]:
    if str(baseline).strip():
        return _baseline_hash_check(baseline)
    return _baseline_chunked_check()


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


def _baseline_collect(source: str, mode: str, profile: str, duration_sec: float, interval_sec: float, segment_records: int, window_id: str, output: str) -> Dict[str, Any]:
    src = _normalize_source(source)
    m = str(mode or 'canary').strip().lower()
    if m not in MODES:
        m = 'canary'
    profile_input = str(profile or 'normal').strip().lower()
    prof = _normalize_resource_profile(profile_input)

    default_interval = float(RESOURCE_NORMAL_INTERVAL_SEC) if prof == 'normal' else float(RESOURCE_BASELINE_INTERVAL_SEC)
    interval = float(interval_sec) if float(interval_sec or 0.0) > 0.0 else default_interval
    duration = max(0.0, float(duration_sec or 0.0))
    seg_limit = max(1, int(segment_records or 1000))
    wid = str(window_id or '').strip() or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    samples_target = 1
    if duration > 0.0 and interval > 0.0:
        samples_target = max(1, int(math.ceil(duration / interval)))

    linkage = _make_run_linkage(m, event='baseline-collect-{0}'.format(prof))
    segment_id = 1
    records_in_segment = 0
    segment_files: Dict[str, int] = {}
    cpu_vals: List[float] = []
    ram_vals: List[float] = []

    for idx in range(samples_target):
        _touch_observer_service_heartbeat()
        sample = _resource_sample()
        sample['stream_type'] = _resource_stream_type(prof)
        sample['sampling_profile_id'] = 'resource_{0}_v1'.format(prof)
        sample['mode_at_capture'] = m
        sample['source_axis'] = src
        sample['baseline_window_id'] = wid
        sample['sample_index'] = idx + 1
        sample['runtime_cli_surface'] = 'observerctl'
        sample['record_class'] = 'resource_telemetry'
        sample.update(linkage)

        seg_path = _resource_segment_path(src, m, prof, wid, segment_id)
        seg_path.parent.mkdir(parents=True, exist_ok=True)
        with seg_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(sample, sort_keys=True) + '\n')
        records_in_segment += 1
        segment_files[str(seg_path).replace('\\', '/')] = int(segment_files.get(str(seg_path).replace('\\', '/'), 0) + 1)

        cpu_vals.append(float(sample.get('cpu_pct_now', 0.0) or 0.0))
        ram_vals.append(float(sample.get('ram_pct_now', 0.0) or 0.0))

        if records_in_segment >= seg_limit:
            segment_id += 1
            records_in_segment = 0

        if idx < samples_target - 1:
            _safe_sleep(interval)

    # Publish resource index entries for downstream analytics/replay.
    idx_path = _resource_index_path(src, m)
    for p, count in segment_files.items():
        _append_jsonl(idx_path, {
            'timestamp_utc': _utc_now(),
            'stream_type': _resource_stream_type(prof),
            'window_id': wid,
            'source': src,
            'mode': m,
            'segment_path': p,
            'segment_records': int(count),
            'run_id': linkage.get('run_id', ''),
        })

    # Update control resource state for gate consumers.
    if cpu_vals and ram_vals:
        state_payload = {
            'updated_at_utc': _utc_now(),
            'baseline_window_id': wid,
            'stream_type': _resource_stream_type(prof),
            'cpu_pct_now': float(cpu_vals[-1]),
            'ram_pct_now': float(ram_vals[-1]),
            'cpu_p95_15m': float(_percentile(cpu_vals, 95.0)),
            'ram_p95_15m': float(_percentile(ram_vals, 95.0)),
            'resource_spike_score': float(max(0.0, (_percentile(cpu_vals, 99.0) - _percentile(cpu_vals, 50.0)) / 100.0, (_percentile(ram_vals, 99.0) - _percentile(ram_vals, 50.0)) / 100.0)),
            'sample_age_seconds': 0.0,
            'sample_count': int(len(cpu_vals)),
            'source': src,
            'mode': m,
            'run_id': linkage.get('run_id', ''),
        }
        _write_json_file(_control_file(WATCHDOG_RESOURCE_FILE), state_payload)

    baseline_id = 'baseline-{0}-{1}-{2}-{3}'.format(src, m, prof, wid)
    catalog = _load_baselines()
    items = list(catalog.get('items', [])) if isinstance(catalog.get('items', []), list) else []
    items.append({
        'id': baseline_id,
        'status': 'ready' if len(cpu_vals) >= 2 else 'collecting',
        'created_at_utc': _utc_now(),
        'source': src,
        'mode': m,
        'profile': prof,
        'window_id': wid,
        'sample_count': int(len(cpu_vals)),
    })
    catalog['items'] = items
    catalog['active'] = baseline_id
    _save_baselines(catalog)

    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-collect',
        'source': src,
        'mode': m,
        'profile': prof,
        'profile_input': profile_input,
        'window_id': wid,
        'sample_count': int(len(cpu_vals)),
        'interval_sec': float(interval),
        'duration_sec': float(duration),
        'segment_records_limit': int(seg_limit),
        'segments': [{'path': p, 'records': int(c)} for p, c in sorted(segment_files.items())],
        'resource_summary': {
            'cpu_p50': float(_percentile(cpu_vals, 50.0)),
            'cpu_p95': float(_percentile(cpu_vals, 95.0)),
            'cpu_p99': float(_percentile(cpu_vals, 99.0)),
            'ram_p50': float(_percentile(ram_vals, 50.0)),
            'ram_p95': float(_percentile(ram_vals, 95.0)),
            'ram_p99': float(_percentile(ram_vals, 99.0)),
        },
        'provenance': {
            'generated_at_utc': _utc_now(),
            'producer_process': 'observerctl baseline collect',
            'artifact_path': '',
            'artifact_sha256': '',
            'upstream_inputs': {
                'watchdog_resource_state': str(_control_file(WATCHDOG_RESOURCE_FILE)).replace('\\', '/'),
                'resource_index': str(idx_path).replace('\\', '/'),
            },
        },
        'methodology': {
            'sampling_strategy': 'fixed-interval resource telemetry sampling via psutil cpu/ram probes',
            'runtime_constraints': ['names-only outputs', 'observerctl standalone surface'],
            'failure_modes': ['resource_sample_missing', 'archive_write_failure'],
        },
        'process': {
            'phase': 'baseline_collection',
            'event': 'baseline_collect_{0}'.format(prof),
            'decision': 'go',
            'reason_codes': [],
            'approver_checkpoint': 'required_for_live_transition',
            'evidence_refs': [str(idx_path).replace('\\', '/')] + sorted(segment_files.keys()),
        },
    }
    packet.update(linkage)

    out_path = Path(str(output).strip()) if str(output).strip() else _resource_evidence_output_path(src, m, 'baseline_collect_{0}'.format(prof))
    packet = _write_packet(packet, out_path)
    _append_jsonl(_evidence_index_path(src, m), {
        'timestamp_utc': _utc_now(),
        'packet_path': str(out_path).replace('\\', '/'),
        'decision': packet.get('decision', 'no-go'),
        'run_id': packet.get('run_id', ''),
        'scope': {'source': src, 'mode': m},
        'event': 'baseline_collect_{0}'.format(prof),
    })
    return packet


def _baseline_analyze(source: str, mode: str, hours: float, profile: str, min_normal_samples: int, min_rapid_samples: int, output: str) -> Dict[str, Any]:
    src = _normalize_source(source)
    m = str(mode or 'canary').strip().lower()
    if m not in MODES:
        m = 'canary'
    prof = str(profile or 'all').strip().lower()
    profile_filter: Optional[str] = None if prof in ('all', '*', '') else _normalize_resource_profile(prof)
    lookback_s = max(60.0, float(hours or 24.0) * 3600.0)
    cutoff = time.time() - lookback_s

    rows: List[Dict[str, Any]] = []
    for p in _resource_candidate_files(src, m, profile=profile_filter):
        for row in _parse_jsonl_lines(p):
            ts = _parse_utc_iso8601(row.get('timestamp_utc'))
            if ts is None:
                continue
            if ts.timestamp() < cutoff:
                continue
            rows.append(row)

    rows.sort(key=lambda r: str(r.get('timestamp_utc', '')))
    cpu_vals = [float(r.get('cpu_pct_now', 0.0) or 0.0) for r in rows]
    ram_vals = [float(r.get('ram_pct_now', 0.0) or 0.0) for r in rows]
    normal_count = sum(1 for r in rows if str(r.get('stream_type', '')) == 'resource_normal')
    baseline_count = sum(1 for r in rows if _resource_profile_matches(r.get('stream_type', ''), 'baseline'))

    cpu_rate_vals: List[float] = []
    ram_rate_vals: List[float] = []
    prev_ts = None
    prev_cpu = None
    prev_ram = None
    for r in rows:
        ts = _parse_utc_iso8601(r.get('timestamp_utc'))
        if ts is None:
            continue
        cur_ts = float(ts.timestamp())
        cur_cpu = float(r.get('cpu_pct_now', 0.0) or 0.0)
        cur_ram = float(r.get('ram_pct_now', 0.0) or 0.0)
        if prev_ts is not None and cur_ts > prev_ts:
            dt = cur_ts - prev_ts
            cpu_rate_vals.append((cur_cpu - float(prev_cpu)) / dt)
            ram_rate_vals.append((cur_ram - float(prev_ram)) / dt)
        prev_ts = cur_ts
        prev_cpu = cur_cpu
        prev_ram = cur_ram

    baseline_ready = bool(len(rows) >= max(2, int(min_normal_samples) + int(min_rapid_samples)) and normal_count >= int(min_normal_samples) and baseline_count >= int(min_rapid_samples))
    linkage = _make_run_linkage(m, event='baseline-analyze')
    analyze_reason_codes = [] if baseline_ready else ['critical_check_failed:resource_baseline_window_incomplete']

    if cpu_vals and ram_vals:
        state_payload = {
            'updated_at_utc': _utc_now(),
            'stream_type': 'resource_baseline_analysis',
            'cpu_pct_now': float(cpu_vals[-1]),
            'ram_pct_now': float(ram_vals[-1]),
            'cpu_p95_15m': float(_percentile(cpu_vals, 95.0)),
            'ram_p95_15m': float(_percentile(ram_vals, 95.0)),
            'resource_spike_score': float(max(0.0, (_percentile(cpu_vals, 99.0) - _percentile(cpu_vals, 50.0)) / 100.0, (_percentile(ram_vals, 99.0) - _percentile(ram_vals, 50.0)) / 100.0)),
            'sample_age_seconds': 0.0,
            'sample_count': int(len(cpu_vals)),
            'source': src,
            'mode': m,
            'run_id': linkage.get('run_id', ''),
        }
        _write_json_file(_control_file(WATCHDOG_RESOURCE_FILE), state_payload)

    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if baseline_ready else 'no-go',
        'action': 'baseline-analyze',
        'source': src,
        'mode': m,
        'lookback_hours': float(hours),
        'profile_filter': profile_filter or 'all',
        'sample_counts': {
            'total': int(len(rows)),
            'resource_normal': int(normal_count),
            'resource_baseline': int(baseline_count),
            'resource_rapid_legacy_alias': int(baseline_count),
        },
        'minimum_requirements': {
            'resource_normal': int(min_normal_samples),
            'resource_baseline': int(min_rapid_samples),
            'resource_rapid_legacy_alias': int(min_rapid_samples),
        },
        'baseline_ready': bool(baseline_ready),
        'resource_statistics': {
            'cpu_p50': float(_percentile(cpu_vals, 50.0)),
            'cpu_p95': float(_percentile(cpu_vals, 95.0)),
            'cpu_p99': float(_percentile(cpu_vals, 99.0)),
            'ram_p50': float(_percentile(ram_vals, 50.0)),
            'ram_p95': float(_percentile(ram_vals, 95.0)),
            'ram_p99': float(_percentile(ram_vals, 99.0)),
            'cpu_rate_p95_per_s': float(_percentile(cpu_rate_vals, 95.0)),
            'ram_rate_p95_per_s': float(_percentile(ram_rate_vals, 95.0)),
        },
        'reason_codes': analyze_reason_codes,
        'provenance': {
            'generated_at_utc': _utc_now(),
            'producer_process': 'observerctl baseline analyze',
            'artifact_path': '',
            'artifact_sha256': '',
            'upstream_inputs': {
                'resource_archive_dir': str(_resource_archive_dir()).replace('\\', '/'),
                'watchdog_resource_state': str(_control_file(WATCHDOG_RESOURCE_FILE)).replace('\\', '/'),
            },
        },
        'methodology': {
            'sampling_strategy': 'lookback-window aggregation over resource_normal/resource_baseline telemetry segments',
            'runtime_constraints': ['names-only outputs', 'publish-grade packet with linkage fields'],
            'failure_modes': ['insufficient_baseline_samples', 'archive_parse_failure'],
            'calculus': ['percentiles (p50/p95/p99)', 'first-order rate-of-change per second'],
        },
        'process': {
            'phase': 'baseline_analysis',
            'event': 'baseline_analyze',
            'decision': 'go' if baseline_ready else 'no-go',
            'reason_codes': analyze_reason_codes,
            'approver_checkpoint': 'required_for_live_transition',
            'evidence_refs': [str(_resource_archive_dir()).replace('\\', '/'), str(_resource_index_path(src, m)).replace('\\', '/')],
        },
    }
    packet.update(linkage)

    out_path = Path(str(output).strip()) if str(output).strip() else _resource_evidence_output_path(src, m, 'baseline_analysis')
    packet = _write_packet(packet, out_path)
    _append_jsonl(_evidence_index_path(src, m), {
        'timestamp_utc': _utc_now(),
        'packet_path': str(out_path).replace('\\', '/'),
        'decision': packet.get('decision', 'no-go'),
        'run_id': packet.get('run_id', ''),
        'scope': {'source': src, 'mode': m},
        'event': 'baseline_analysis',
    })
    return packet


def _baseline_overnight_plan(
    source: str,
    mode: str,
    overnight_hours: float,
    normal_interval_sec: float,
    rapid_interval_sec: float,
    rapid_phase_sec: float,
    min_normal_samples: int,
    min_rapid_samples: int,
    output: str,
) -> Dict[str, Any]:
    src = _normalize_source(source)
    m = str(mode or 'canary').strip().lower()
    if m not in MODES:
        m = 'canary'

    overnight_h = max(0.25, float(overnight_hours or 8.0))
    normal_interval = max(1.0, float(normal_interval_sec or 30.0))
    rapid_interval = max(0.2, float(rapid_interval_sec or 2.0))
    rapid_phase = max(1.0, float(rapid_phase_sec or 1800.0))

    total_window_sec = overnight_h * 3600.0
    normal_window_sec = max(0.0, total_window_sec - (2.0 * rapid_phase))
    if normal_window_sec < 1.0:
        normal_window_sec = 1.0

    rapid_samples_per_leg = max(1, int(math.ceil(rapid_phase / rapid_interval)))
    normal_samples = max(1, int(math.ceil(normal_window_sec / normal_interval)))
    rapid_total = int(rapid_samples_per_leg * 2)

    now = datetime.now(timezone.utc)
    start_iso = now.isoformat().replace('+00:00', 'Z')
    t1 = now.timestamp() + rapid_phase
    t2 = t1 + normal_window_sec
    end_ts = t2 + rapid_phase

    transition_1 = datetime.fromtimestamp(t1, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
    transition_2 = datetime.fromtimestamp(t2, tz=timezone.utc).isoformat().replace('+00:00', 'Z')
    end_iso = datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat().replace('+00:00', 'Z')

    linkage = _make_run_linkage(m, event='baseline-overnight-plan')
    window_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    commands = [
        'observerctl baseline collect --source {0} --mode {1} --profile baseline --duration-sec {2:.0f} --interval-sec {3:.3f} --window-id overnight_baseline_start_{4} --json'.format(src, m, rapid_phase, rapid_interval, window_id),
        'observerctl baseline collect --source {0} --mode {1} --profile normal --duration-sec {2:.0f} --interval-sec {3:.3f} --window-id overnight_normal_{4} --json'.format(src, m, normal_window_sec, normal_interval, window_id),
        'observerctl baseline collect --source {0} --mode {1} --profile baseline --duration-sec {2:.0f} --interval-sec {3:.3f} --window-id overnight_baseline_end_{4} --json'.format(src, m, rapid_phase, rapid_interval, window_id),
        'observerctl baseline analyze --source {0} --mode {1} --hours {2:.2f} --min-normal-samples {3} --min-baseline-samples {4} --json'.format(src, m, overnight_h + 1.0, int(min_normal_samples), int(min_rapid_samples)),
    ]

    readiness_projection = {
        'normal_samples_expected': int(normal_samples),
        'rapid_samples_expected_total': int(rapid_total),
        'minimum_normal_required': int(min_normal_samples),
        'minimum_rapid_required': int(min_rapid_samples),
        'normal_requirement_met_by_plan': bool(normal_samples >= int(min_normal_samples)),
        'rapid_requirement_met_by_plan': bool(rapid_total >= int(min_rapid_samples)),
    }
    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-overnight-plan',
        'source': src,
        'mode': m,
        'schedule_model': 'baseline_start_then_normal_overnight_then_baseline_end',
        'window': {
            'start_utc': start_iso,
            'rapid_to_normal_utc': transition_1,
            'normal_to_rapid_utc': transition_2,
            'end_utc': end_iso,
            'overnight_hours': float(overnight_h),
            'rapid_phase_sec_each': float(rapid_phase),
            'normal_phase_sec': float(normal_window_sec),
        },
        'sampling': {
            'normal_interval_sec': float(normal_interval),
            'rapid_interval_sec': float(rapid_interval),
            'expected_normal_samples': int(normal_samples),
            'expected_rapid_samples_each': int(rapid_samples_per_leg),
            'expected_rapid_samples_total': int(rapid_total),
        },
        'readiness_projection': readiness_projection,
        'execution_commands': commands,
        'provenance': {
            'generated_at_utc': _utc_now(),
            'producer_process': 'observerctl baseline overnight-plan',
            'artifact_path': '',
            'artifact_sha256': '',
            'upstream_inputs': {
                'state_file': str(_control_file(STATE_FILE)).replace('\\', '/'),
                'resource_index': str(_resource_index_path(src, m)).replace('\\', '/'),
            },
        },
        'methodology': {
            'sampling_strategy': 'front-loaded rapid capture, long normal stability capture, tail rapid capture',
            'runtime_constraints': ['plan-only command (no collection side effects)', 'publish-grade packet for operator handoff'],
            'calculus': ['expected sample counts from duration/interval arithmetic'],
        },
        'process': {
            'phase': 'baseline_schedule_planning',
            'event': 'baseline_overnight_plan',
            'decision': 'go',
            'reason_codes': [],
            'approver_checkpoint': 'operator_ack_before_execution',
            'evidence_refs': [str(_resource_index_path(src, m)).replace('\\', '/')],
        },
    }
    packet.update(linkage)

    out_path = Path(str(output).strip()) if str(output).strip() else _resource_evidence_output_path(src, m, 'baseline_overnight_plan')
    packet = _write_packet(packet, out_path)
    _append_jsonl(_evidence_index_path(src, m), {
        'timestamp_utc': _utc_now(),
        'packet_path': str(out_path).replace('\\', '/'),
        'decision': packet.get('decision', 'no-go'),
        'run_id': packet.get('run_id', ''),
        'scope': {'source': src, 'mode': m},
        'event': 'baseline_overnight_plan',
    })
    return packet


def _baseline_overnight_run(
    source: str,
    mode: str,
    overnight_hours: float,
    normal_interval_sec: float,
    rapid_interval_sec: float,
    rapid_phase_sec: float,
    min_normal_samples: int,
    min_rapid_samples: int,
    output: str,
    emit_progress: bool = False,
) -> Dict[str, Any]:
    src = _normalize_source(source)
    m = str(mode or 'canary').strip().lower()
    if m not in MODES:
        m = 'canary'

    overnight_h = max(0.0001, float(overnight_hours or 8.0))
    normal_interval = max(0.05, float(normal_interval_sec or 30.0))
    rapid_interval = max(0.05, float(rapid_interval_sec or 2.0))
    rapid_phase = max(0.05, float(rapid_phase_sec or 1800.0))

    total_window_sec = overnight_h * 3600.0
    normal_window_sec = max(0.05, total_window_sec - (2.0 * rapid_phase))

    _emit_progress(
        'baseline overnight run started source={0} mode={1} overnight_hours={2:.3f} rapid_phase_sec={3:.3f} normal_phase_sec={4:.3f}'.format(
            src,
            m,
            float(overnight_h),
            float(rapid_phase),
            float(normal_window_sec),
        ),
        enabled=emit_progress,
    )

    linkage = _make_run_linkage(m, event='baseline-overnight-run')
    window_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

    checkpoints: List[Dict[str, Any]] = []

    def _record_checkpoint(phase: str, packet: Dict[str, Any]) -> None:
        checkpoints.append({
            'phase': phase,
            'timestamp_utc': _utc_now(),
            'decision': str(packet.get('decision', 'no-go')).lower(),
            'reason_codes': list(packet.get('reason_codes', [])) if isinstance(packet.get('reason_codes', []), list) else [],
            'packet_path': str((packet.get('provenance', {}) or {}).get('artifact_path', '') or ''),
            'sample_count': int(packet.get('sample_count', 0) or 0),
            'action': str(packet.get('action', '') or ''),
        })

    _emit_progress('phase_start baseline_start', enabled=emit_progress)
    rapid_start = _baseline_collect(
        source=src,
        mode=m,
        profile='baseline',
        duration_sec=float(rapid_phase),
        interval_sec=float(rapid_interval),
        segment_records=1000,
        window_id='overnight_baseline_start_{0}'.format(window_id),
        output='',
    )
    _record_checkpoint('baseline_start', rapid_start)
    _emit_progress(
        'phase_complete baseline_start decision={0} samples={1}'.format(
            str(rapid_start.get('decision', 'no-go')).lower(),
            int(rapid_start.get('sample_count', 0) or 0),
        ),
        enabled=emit_progress,
    )

    _emit_progress('phase_start normal_overnight', enabled=emit_progress)
    normal_run = _baseline_collect(
        source=src,
        mode=m,
        profile='normal',
        duration_sec=float(normal_window_sec),
        interval_sec=float(normal_interval),
        segment_records=1000,
        window_id='overnight_normal_{0}'.format(window_id),
        output='',
    )
    _record_checkpoint('normal_overnight', normal_run)
    _emit_progress(
        'phase_complete normal_overnight decision={0} samples={1}'.format(
            str(normal_run.get('decision', 'no-go')).lower(),
            int(normal_run.get('sample_count', 0) or 0),
        ),
        enabled=emit_progress,
    )

    _emit_progress('phase_start baseline_end', enabled=emit_progress)
    rapid_end = _baseline_collect(
        source=src,
        mode=m,
        profile='baseline',
        duration_sec=float(rapid_phase),
        interval_sec=float(rapid_interval),
        segment_records=1000,
        window_id='overnight_baseline_end_{0}'.format(window_id),
        output='',
    )
    _record_checkpoint('baseline_end', rapid_end)
    _emit_progress(
        'phase_complete baseline_end decision={0} samples={1}'.format(
            str(rapid_end.get('decision', 'no-go')).lower(),
            int(rapid_end.get('sample_count', 0) or 0),
        ),
        enabled=emit_progress,
    )

    _emit_progress('phase_start analysis', enabled=emit_progress)
    analyze_packet = _baseline_analyze(
        source=src,
        mode=m,
        hours=max(1.0, float(overnight_h) + 1.0),
        profile='all',
        min_normal_samples=int(min_normal_samples),
        min_rapid_samples=int(min_rapid_samples),
        output='',
    )
    _record_checkpoint('analysis', analyze_packet)
    _emit_progress(
        'phase_complete analysis decision={0} baseline_ready={1}'.format(
            str(analyze_packet.get('decision', 'no-go')).lower(),
            bool(analyze_packet.get('baseline_ready', False)),
        ),
        enabled=emit_progress,
    )

    phase_failures = [cp for cp in checkpoints if str(cp.get('decision', 'no-go')) != 'go']
    reason_codes: List[str] = []
    for cp in phase_failures:
        phase = str(cp.get('phase', 'unknown'))
        cp_reasons = cp.get('reason_codes', []) if isinstance(cp.get('reason_codes', []), list) else []
        if cp_reasons:
            for code in cp_reasons:
                reason_codes.append('{0}:{1}'.format(phase, code))
        else:
            reason_codes.append('{0}:critical_check_failed:phase_failed'.format(phase))

    decision = 'go' if len(reason_codes) == 0 else 'no-go'
    if len(reason_codes) == 0 and str(analyze_packet.get('decision', 'no-go')) != 'go':
        decision = 'no-go'

    executed_commands = [
        'observerctl baseline collect --source {0} --mode {1} --profile baseline --duration-sec {2:.3f} --interval-sec {3:.3f} --window-id overnight_baseline_start_{4} --json'.format(src, m, rapid_phase, rapid_interval, window_id),
        'observerctl baseline collect --source {0} --mode {1} --profile normal --duration-sec {2:.3f} --interval-sec {3:.3f} --window-id overnight_normal_{4} --json'.format(src, m, normal_window_sec, normal_interval, window_id),
        'observerctl baseline collect --source {0} --mode {1} --profile baseline --duration-sec {2:.3f} --interval-sec {3:.3f} --window-id overnight_baseline_end_{4} --json'.format(src, m, rapid_phase, rapid_interval, window_id),
        'observerctl baseline analyze --source {0} --mode {1} --hours {2:.3f} --min-normal-samples {3} --min-baseline-samples {4} --json'.format(src, m, max(1.0, float(overnight_h) + 1.0), int(min_normal_samples), int(min_rapid_samples)),
    ]

    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': decision,
        'action': 'baseline-overnight-run',
        'source': src,
        'mode': m,
        'window_id': window_id,
        'schedule_model': 'baseline_start_then_normal_overnight_then_baseline_end',
        'sampling': {
            'overnight_hours': float(overnight_h),
            'rapid_phase_sec_each': float(rapid_phase),
            'normal_phase_sec': float(normal_window_sec),
            'normal_interval_sec': float(normal_interval),
            'rapid_interval_sec': float(rapid_interval),
        },
        'minimum_requirements': {
            'resource_normal': int(min_normal_samples),
            'resource_baseline': int(min_rapid_samples),
        },
        'checkpoints': checkpoints,
        'analysis_summary': {
            'decision': analyze_packet.get('decision', 'no-go'),
            'baseline_ready': bool(analyze_packet.get('baseline_ready', False)),
            'sample_counts': analyze_packet.get('sample_counts', {}),
            'resource_statistics': analyze_packet.get('resource_statistics', {}),
        },
        'execution_commands': executed_commands,
        'reason_codes': reason_codes,
        'provenance': {
            'generated_at_utc': _utc_now(),
            'producer_process': 'observerctl baseline overnight-run',
            'artifact_path': '',
            'artifact_sha256': '',
            'upstream_inputs': {
                'resource_index': str(_resource_index_path(src, m)).replace('\\', '/'),
                'evidence_index': str(_evidence_index_path(src, m)).replace('\\', '/'),
            },
        },
        'methodology': {
            'sampling_strategy': 'execute rapid-start, normal-mid, rapid-end collection and then analyze baseline readiness',
            'runtime_constraints': ['single-command orchestration', 'checkpointed phase evidence', 'fail-closed final decision'],
            'calculus': ['analysis phase computes p50/p95/p99 and first-order rate-of-change'],
        },
        'process': {
            'phase': 'baseline_orchestration',
            'event': 'baseline_overnight_run',
            'decision': decision,
            'reason_codes': reason_codes,
            'approver_checkpoint': 'required_for_live_transition',
            'evidence_refs': [str(_resource_index_path(src, m)).replace('\\', '/'), str(_evidence_index_path(src, m)).replace('\\', '/')],
        },
    }
    packet.update(linkage)

    out_path = Path(str(output).strip()) if str(output).strip() else _resource_evidence_output_path(src, m, 'baseline_overnight_run')
    packet = _write_packet(packet, out_path)
    _append_jsonl(_evidence_index_path(src, m), {
        'timestamp_utc': _utc_now(),
        'packet_path': str(out_path).replace('\\', '/'),
        'decision': packet.get('decision', 'no-go'),
        'run_id': packet.get('run_id', ''),
        'scope': {'source': src, 'mode': m},
        'event': 'baseline_overnight_run',
    })
    _emit_progress(
        'baseline overnight run completed decision={0} packet_path={1}'.format(
            str(packet.get('decision', 'no-go')).lower(),
            str((packet.get('provenance', {}) or {}).get('artifact_path', '') or ''),
        ),
        enabled=emit_progress,
    )
    return packet


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


def _safe_file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except Exception:
        return 0


def _classify_archive_mode(name: str) -> str:
    candidate = str(name or '').strip().lower()
    if 'honeypot' in candidate:
        return 'honeypot'
    if 'canary' in candidate:
        return 'canary'
    if 'watch' in candidate:
        return 'watch'
    if 'live' in candidate:
        return 'live'
    return 'unclassified'


def _archive_manifest_stats() -> Dict[str, Any]:
    archive_dir = get_calamum_data_dir() / 'archive'
    manifest_path = archive_dir / 'manifest.json'

    by_mode: Dict[str, Dict[str, int]] = {
        'watch': {'bundle_count': 0, 'records': 0, 'uncompressed_bytes': 0, 'compressed_bytes': 0},
        'canary': {'bundle_count': 0, 'records': 0, 'uncompressed_bytes': 0, 'compressed_bytes': 0},
        'live': {'bundle_count': 0, 'records': 0, 'uncompressed_bytes': 0, 'compressed_bytes': 0},
        'honeypot': {'bundle_count': 0, 'records': 0, 'uncompressed_bytes': 0, 'compressed_bytes': 0},
        'unclassified': {'bundle_count': 0, 'records': 0, 'uncompressed_bytes': 0, 'compressed_bytes': 0},
    }

    payload = _load_json_file(manifest_path, {})
    if not isinstance(payload, dict):
        payload = {}

    for bundle_name, row in payload.items():
        if not isinstance(row, dict):
            continue
        mode = _classify_archive_mode(str(bundle_name))
        bucket = by_mode.get(mode, by_mode['unclassified'])

        records = 0
        uncompressed_bytes = 0
        try:
            records = int(row.get('records', 0) or 0)
        except Exception:
            records = 0
        try:
            uncompressed_bytes = int(row.get('uncompressed_bytes', 0) or 0)
        except Exception:
            uncompressed_bytes = 0

        artifact_rel = str(row.get('artifact_path', '') or '').strip()
        artifact_size = 0
        if artifact_rel:
            artifact_size = _safe_file_size(archive_dir / artifact_rel)

        bucket['bundle_count'] += 1
        bucket['records'] += records
        bucket['uncompressed_bytes'] += uncompressed_bytes
        bucket['compressed_bytes'] += artifact_size

    totals = {'bundle_count': 0, 'records': 0, 'uncompressed_bytes': 0, 'compressed_bytes': 0}
    for row in by_mode.values():
        totals['bundle_count'] += int(row.get('bundle_count', 0))
        totals['records'] += int(row.get('records', 0))
        totals['uncompressed_bytes'] += int(row.get('uncompressed_bytes', 0))
        totals['compressed_bytes'] += int(row.get('compressed_bytes', 0))

    return {
        'manifest_path': str(manifest_path).replace('\\', '/'),
        'manifest_exists': bool(manifest_path.exists()),
        'totals': totals,
        'by_mode': by_mode,
    }


def _derived_session_stats(source: str, mode: str) -> Dict[str, int]:
    data_dir = get_calamum_data_dir()
    source_norm = _normalize_source(source)
    mode_norm = str(mode or 'watch').strip().lower()
    if mode_norm not in MODES:
        mode_norm = 'watch'

    p = data_dir / 'observer_derived' / source_norm / mode_norm / 'moltbook_metrics.jsonl'
    if not p.exists():
        return {'records': 0, 'bytes': 0, 'file_count': 0}

    return {
        'records': int(_count_jsonl_records(p)),
        'bytes': int(_safe_file_size(p)),
        'file_count': 1,
    }


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
    state = _load_state()
    active_source = _normalize_source(str(state.get('source', 'sim')))
    active_mode = str(state.get('mode', 'watch')).strip().lower()
    if active_mode not in MODES:
        active_mode = 'watch'

    archive_summary = _archive_manifest_stats()
    by_mode = archive_summary.get('by_mode', {}) if isinstance(archive_summary, dict) else {}
    items = []
    for mode in MODES:
        packet = _store_integrity_packet(mode)
        manifest = _load_store_manifest(mode)
        paths = _store_paths(mode, manifest)
        session_records = _count_jsonl_records(paths['active_path'])
        session_bytes = _safe_file_size(paths['active_path'])

        store_archive_records = 0
        store_archive_bytes = 0
        for p in paths['archives']:
            store_archive_records += _count_jsonl_records(p)
            store_archive_bytes += _safe_file_size(p)

        compacted_records = 0
        compacted_bytes = 0
        for p in paths['compacted']:
            compacted_records += _count_jsonl_records(p)
            compacted_bytes += _safe_file_size(p)

        record_count = int(session_records + store_archive_records + compacted_records)
        archive_mode_bucket = by_mode.get(mode, {}) if isinstance(by_mode, dict) else {}
        archive_bundle_count = int(archive_mode_bucket.get('bundle_count', 0) or 0)
        archive_records = int(archive_mode_bucket.get('records', 0) or 0)
        archive_uncompressed_bytes = int(archive_mode_bucket.get('uncompressed_bytes', 0) or 0)
        archive_compressed_bytes = int(archive_mode_bucket.get('compressed_bytes', 0) or 0)
        if mode == active_mode:
            derived_session = _derived_session_stats(active_source, mode)
        else:
            derived_session = {'records': 0, 'bytes': 0, 'file_count': 0}
        ingest_session_records = int(derived_session.get('records', 0))
        ingest_session_bytes = int(derived_session.get('bytes', 0))
        ingest_session_file_count = int(derived_session.get('file_count', 0))
        session_records_display = int(ingest_session_records if ingest_session_records > 0 else session_records)
        session_bytes_display = int(ingest_session_bytes if ingest_session_records > 0 else session_bytes)

        items.append({
            'mode': mode,
            'store_path': packet['store_path'],
            'active_store_pointer': packet['active_store_pointer'],
            'record_count': record_count,
            'session_records': int(session_records),
            'session_bytes': int(session_bytes),
            'ingest_source_scope': active_source,
            'ingest_mode_active': bool(mode == active_mode),
            'ingest_session_records': ingest_session_records,
            'ingest_session_bytes': ingest_session_bytes,
            'ingest_session_file_count': ingest_session_file_count,
            'session_records_display': session_records_display,
            'session_bytes_display': session_bytes_display,
            'store_archive_segment_count': int(len(paths['archives'])),
            'store_archive_records': int(store_archive_records),
            'store_archive_bytes': int(store_archive_bytes),
            'compacted_bundle_count': int(len(paths['compacted'])),
            'compacted_records': int(compacted_records),
            'compacted_bytes': int(compacted_bytes),
            'archive_bundle_count': archive_bundle_count,
            'archive_records': archive_records,
            'archive_uncompressed_bytes': archive_uncompressed_bytes,
            'archive_compressed_bytes': archive_compressed_bytes,
            'records_total_display': int(session_records_display + archive_records),
            'archive_count': packet['archive_count'],
            'manifest_integrity': packet['status'],
            'retention_state': packet['retention_state'],
        })
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'archive_manifest_summary': archive_summary,
        'stores': items,
    }


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
    source = _normalize_source(str(state.get('source', 'sim')))
    mode = str(state.get('mode', 'watch')).strip().lower()
    if mode not in MODES:
        mode = 'watch'
    observer_runtime = _runtime_observer_status()
    observer_runtime_state = str(observer_runtime.get('state', 'stopped')).strip().lower()
    observer_service = {
        'state': observer_runtime_state,
        'status': 'ok' if observer_runtime_state in ('active', 'degraded') else 'err',
    }
    collection_state = _infer_collection_state(observer_runtime, _observer_metrics_path(source, mode))
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'mode': state.get('mode'),
        'posture_trigger': _posture_for_mode(str(state.get('mode', 'watch'))),
        'checks': {
            'watchdog': hb_watchdog,
            'observer': hb_observer,
            'observer_service': observer_service,
            'collection_state': collection_state,
        },
    }


def _watchdog_check() -> Dict[str, Any]:
    status = _watchdog_status()
    reasons = []
    advisories = []
    if str((status.get('checks', {}).get('watchdog') or {}).get('status', 'err')) != 'ok':
        reasons.append('critical_check_failed:watchdog_heartbeat_stale')
    observer_hb_status = str((status.get('checks', {}).get('observer') or {}).get('status', 'err')).lower()
    observer_service_status = str((status.get('checks', {}).get('observer_service') or {}).get('status', 'err')).lower()
    if observer_hb_status != 'ok' and observer_service_status != 'ok':
        reasons.append('critical_check_failed:observer_heartbeat_stale')
    elif observer_hb_status != 'ok' and observer_service_status == 'ok':
        advisories.append('major_check_failed:observer_heartbeat_stale_service_alive')
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go' if not reasons else 'no-go',
        'reason_codes': reasons,
        'advisory_reason_codes': advisories,
    }


def _watchdog_reasons() -> Dict[str, Any]:
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'reasons': [
            'critical_check_failed:watchdog_trigger_posture_invalid',
            'critical_check_failed:lockdown_heartbeat_rate_not_escalated',
            'critical_check_failed:lockdown_baseline_rate_not_escalated',
            'critical_check_failed:resource_stream_retention_unavailable',
            'critical_check_failed:resource_baseline_window_incomplete',
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
    if cmd == 'sandbox':
        if args.sandbox_cmd == 'list':
            return _sandbox_list()
        if args.sandbox_cmd == 'show':
            return _sandbox_show(args.definition)
        if args.sandbox_cmd == 'run':
            return _sandbox_run(args.definition)
        if args.sandbox_cmd == 'runs-list':
            return _sandbox_runs_list()
        if args.sandbox_cmd == 'runs-show':
            return _sandbox_runs_show(args.run_id)

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
        if args.ops_cmd == 'mode-switch':
            return _ops_mode_switch(
                source=args.source,
                to_mode=args.to,
                event=args.event,
                output=args.output,
                interval_sec=args.interval_sec,
                stop_timeout_sec=args.stop_timeout_sec,
                startup_probe_sec=args.startup_probe_sec,
            )
        if args.ops_cmd == 'evidence-pack':
            return _ops_evidence_pack(args.source, args.event, args.output, args.to)
        if args.ops_cmd == 'evidence-verify':
            return _ops_evidence_verify(args.packet)
        if args.ops_cmd == 'evidence-index':
            return _ops_evidence_index()

    if cmd == 'baseline':
        if args.base_cmd == 'status':
            return _baseline_status(args.baseline)
        if args.base_cmd == 'graph':
            return _baseline_graph()
        if args.base_cmd == 'check':
            return _baseline_check(args.baseline)
        if args.base_cmd == 'generate':
            return _baseline_hash_generate(max_files=args.max_files, output=args.output)
        if args.base_cmd == 'list':
            return _baseline_list()
        if args.base_cmd == 'set':
            return _baseline_set(args.id)
        if args.base_cmd == 'collect':
            return _baseline_collect(
                source=args.source,
                mode=args.mode,
                profile=args.profile,
                duration_sec=args.duration_sec,
                interval_sec=args.interval_sec,
                segment_records=args.segment_records,
                window_id=args.window_id,
                output=args.output,
            )
        if args.base_cmd == 'analyze':
            min_baseline_samples = _resolve_cli_min_baseline_samples(args)
            return _baseline_analyze(
                source=args.source,
                mode=args.mode,
                hours=args.hours,
                profile=args.profile,
                min_normal_samples=args.min_normal_samples,
                min_rapid_samples=min_baseline_samples,
                output=args.output,
            )
        if args.base_cmd == 'overnight-plan':
            min_baseline_samples = _resolve_cli_min_baseline_samples(args)
            return _baseline_overnight_plan(
                source=args.source,
                mode=args.mode,
                overnight_hours=args.overnight_hours,
                normal_interval_sec=args.normal_interval_sec,
                rapid_interval_sec=args.rapid_interval_sec,
                rapid_phase_sec=args.rapid_phase_sec,
                min_normal_samples=args.min_normal_samples,
                min_rapid_samples=min_baseline_samples,
                output=args.output,
            )
        if args.base_cmd == 'overnight-run':
            min_baseline_samples = _resolve_cli_min_baseline_samples(args)
            return _baseline_overnight_run(
                source=args.source,
                mode=args.mode,
                overnight_hours=args.overnight_hours,
                normal_interval_sec=args.normal_interval_sec,
                rapid_interval_sec=args.rapid_interval_sec,
                rapid_phase_sec=args.rapid_phase_sec,
                min_normal_samples=args.min_normal_samples,
                min_rapid_samples=min_baseline_samples,
                output=args.output,
                emit_progress=not bool(getattr(args, 'json', False)),
            )
        if args.base_cmd == 'monitor-status':
            return _runtime_baseline_monitor_status(max_age_sec=max(90.0, float(args.normal_interval_sec) * 3.0))
        if args.base_cmd == 'monitor-stop':
            return _baseline_monitor_stop(timeout_sec=args.timeout_sec)
        if args.base_cmd == 'monitor-start':
            return _baseline_monitor_start(
                source=args.source,
                mode=args.mode,
                normal_interval_sec=args.normal_interval_sec,
                baseline_interval_sec=args.baseline_interval_sec,
                baseline_window_sec=args.baseline_window_sec,
                baseline_sample_interval_sec=args.baseline_sample_interval_sec,
                min_normal_samples=args.min_normal_samples,
                min_baseline_samples=args.min_baseline_samples,
                startup_probe_sec=args.startup_probe_sec,
            )
        if args.base_cmd == 'monitor-once':
            return _baseline_monitor_once(
                source=args.source,
                mode=args.mode,
                normal_interval_sec=args.normal_interval_sec,
                baseline_interval_sec=args.baseline_interval_sec,
                baseline_window_sec=args.baseline_window_sec,
                baseline_sample_interval_sec=args.baseline_sample_interval_sec,
                min_normal_samples=args.min_normal_samples,
                min_baseline_samples=args.min_baseline_samples,
            )
        if args.base_cmd == 'monitor-loop':
            return _baseline_monitor_loop(
                source=args.source,
                mode=args.mode,
                normal_interval_sec=args.normal_interval_sec,
                baseline_interval_sec=args.baseline_interval_sec,
                baseline_window_sec=args.baseline_window_sec,
                baseline_sample_interval_sec=args.baseline_sample_interval_sec,
                min_normal_samples=args.min_normal_samples,
                min_baseline_samples=args.min_baseline_samples,
                run_once=False,
            )

    if cmd == 'librarian':
        if args.lib_cmd == 'status':
            return _librarian_status()
        if args.lib_cmd == 'check':
            return _librarian_check(args.mode)
        if args.lib_cmd == 'restart':
            return _librarian_restart(args.timeout_sec, args.startup_probe_sec)
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

    sandbox = sub.add_parser('sandbox', help='Sandbox validation namespace')
    sandbox_sub = sandbox.add_subparsers(dest='sandbox_cmd', required=True)
    sandbox_sub.add_parser('list', help='List available sandbox definitions')
    sandbox_show = sandbox_sub.add_parser('show', help='Show one sandbox definition in detail')
    sandbox_show.add_argument('definition')
    sandbox_run = sandbox_sub.add_parser('run', help='Run one sandbox definition')
    sandbox_run.add_argument('definition')
    sandbox_runs = sandbox_sub.add_parser('runs', help='Inspect retained sandbox runs')
    sandbox_runs_sub = sandbox_runs.add_subparsers(dest='sandbox_runs_cmd', required=True)
    sandbox_runs_sub.add_parser('list', help='List retained sandbox runs')
    sandbox_runs_show = sandbox_runs_sub.add_parser('show', help='Show one retained sandbox run')
    sandbox_runs_show.add_argument('run_id')

    ops = sub.add_parser('ops', help='Observer runtime operations gate surface')
    ops_sub = ops.add_subparsers(dest='ops_cmd', required=True)

    op_pre = ops_sub.add_parser('preflight', help='Emit observer runtime status packet')
    op_pre.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())

    op_gatecheck = ops_sub.add_parser('gate-check', help='Evaluate go/no-go over current state')
    op_gatecheck.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())

    op_runtime = ops_sub.add_parser('runtime', help='Observer lifecycle controls')
    op_runtime_sub = op_runtime.add_subparsers(dest='runtime_cmd', required=True)
    op_runtime_sub.add_parser('status', help='Show observer runtime status')
    op_runtime_stop = op_runtime_sub.add_parser('stop', help='Request observer stop (kill signal) and wait for clean exit')
    op_runtime_stop.add_argument('--timeout-sec', type=float, default=8.0, help='Seconds to wait for clean observer shutdown before escalation')
    op_runtime_start = op_runtime_sub.add_parser('start', help='Start observer via delegated launcher path')
    op_runtime_start.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    op_runtime_start.add_argument('--mode', choices=list(MODES), default=_state_default_mode())
    op_runtime_start.add_argument('--interval-sec', type=float, default=float(os.getenv('CALAMUM_AGENT_INTERVAL_SEC', '2.0')))
    op_runtime_start.add_argument('--timeout-sec', type=float, default=0.0, help='Readiness probe timeout after detached launch (0 = no probe)')

    op_mode = ops_sub.add_parser('mode', help='Mode controls')
    op_mode_sub = op_mode.add_subparsers(dest='mode_cmd', required=True)
    op_mode_sub.add_parser('current', help='Show current mode/source')
    op_mode_sub.add_parser('list', help='List modes and posture mapping')
    op_gate = op_mode_sub.add_parser('gate', help='Evaluate transition gate to target mode')
    op_gate.add_argument('--to', choices=list(MODES), required=True)
    op_gate.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    op_set = op_mode_sub.add_parser('set', help='Set target mode after successful gate packet')
    op_set.add_argument('--to', choices=list(MODES), required=True)
    op_set.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    op_transition = op_mode_sub.add_parser('transition', help='Atomic mode transition: gate + set + evidence')
    op_transition.add_argument('--to', choices=list(MODES), required=True)
    op_transition.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    op_transition.add_argument('--event', default='mode-transition')
    op_transition.add_argument('--output', default='')

    op_switch = op_mode_sub.add_parser('switch', help='Single-action mode switch: validate + gate + set + runtime sync + postflight')
    op_switch.add_argument('--to', choices=list(MODES), required=True)
    op_switch.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    op_switch.add_argument('--interval-sec', type=float, default=float(os.getenv('CALAMUM_AGENT_INTERVAL_SEC', '2.0')), help='Observer interval for runtime sync start')
    op_switch.add_argument('--stop-timeout-sec', type=float, default=8.0, help='Seconds to wait for clean observer shutdown before escalation')
    op_switch.add_argument('--startup-probe-sec', type=float, default=6.0, help='Seconds to probe observer readiness after runtime sync start')
    op_switch.add_argument('--event', default='mode-switch')
    op_switch.add_argument('--output', default='')

    op_ev = ops_sub.add_parser('evidence', help='Evidence packet operations')
    op_ev_sub = op_ev.add_subparsers(dest='evidence_cmd', required=True)
    op_ev_pack = op_ev_sub.add_parser('pack', help='Emit publication-grade evidence packet')
    op_ev_pack.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    op_ev_pack.add_argument('--to', choices=list(MODES), default='', help='Optional target mode for non-activation readiness projection')
    op_ev_pack.add_argument('--event', default='manual')
    op_ev_pack.add_argument('--output', default='')
    op_ev_verify = op_ev_sub.add_parser('verify', help='Verify packet schema and linkage fields')
    op_ev_verify.add_argument('--packet', required=True)
    op_ev_sub.add_parser('index', help='Show evidence index summary')

    baseline = sub.add_parser('baseline', help='Baseline and graph readiness namespace')
    baseline_sub = baseline.add_subparsers(dest='base_cmd', required=True)
    baseline_status = baseline_sub.add_parser('status')
    baseline_status.add_argument('--baseline', default='', help='Optional path to filesystem baseline file')
    baseline_sub.add_parser('graph')
    baseline_check = baseline_sub.add_parser('check')
    baseline_check.add_argument('--baseline', default='', help='Optional path to filesystem baseline file')
    baseline_generate = baseline_sub.add_parser('generate')
    baseline_generate.add_argument('--max-files', type=int, default=20000, help='Maximum files to include in hash baseline')
    baseline_generate.add_argument('--output', default='', help='Optional output path for filesystem baseline file')
    baseline_sub.add_parser('list')
    baseline_set = baseline_sub.add_parser('set')
    baseline_set.add_argument('--id', required=True)
    baseline_collect = baseline_sub.add_parser('collect')
    baseline_collect.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    baseline_collect.add_argument('--mode', choices=list(MODES), default=_state_default_mode())
    baseline_collect.add_argument('--profile', choices=list(RESOURCE_PROFILE_CLI_CHOICES), default='normal')
    baseline_collect.add_argument('--duration-sec', type=float, default=0.0, help='Collection duration in seconds (0 captures one sample)')
    baseline_collect.add_argument('--interval-sec', type=float, default=0.0, help='Sampling interval seconds (default by profile)')
    baseline_collect.add_argument('--segment-records', type=int, default=1000, help='Max records per raw segment before rolling to a new segment file')
    baseline_collect.add_argument('--window-id', default='', help='Optional baseline window id for sample grouping')
    baseline_collect.add_argument('--output', default='', help='Optional path for publish-grade collection packet')

    baseline_analyze = baseline_sub.add_parser('analyze')
    baseline_analyze.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    baseline_analyze.add_argument('--mode', choices=list(MODES), default=_state_default_mode())
    baseline_analyze.add_argument('--hours', type=float, default=24.0, help='Lookback window in hours for baseline analysis')
    baseline_analyze.add_argument('--profile', choices=['all'] + list(RESOURCE_PROFILE_CLI_CHOICES), default='all')
    baseline_analyze.add_argument('--min-normal-samples', type=int, default=120, help='Minimum normal stream samples required for readiness')
    baseline_analyze.add_argument('--min-baseline-samples', dest='min_baseline_samples', type=int, default=300, help='Minimum baseline-window samples required for readiness')
    baseline_analyze.add_argument('--min-rapid-samples', dest='min_rapid_samples', type=int, default=0, help='Legacy alias for --min-baseline-samples')
    baseline_analyze.add_argument('--output', default='', help='Optional path for publish-grade analysis packet')

    baseline_plan = baseline_sub.add_parser('overnight-plan')
    baseline_plan.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    baseline_plan.add_argument('--mode', choices=list(MODES), default=_state_default_mode())
    baseline_plan.add_argument('--overnight-hours', type=float, default=8.0, help='Total schedule window in hours')
    baseline_plan.add_argument('--normal-interval-sec', type=float, default=30.0, help='Normal sampling interval in seconds')
    baseline_plan.add_argument('--rapid-interval-sec', type=float, default=2.0, help='Legacy alias cadence for baseline-window sampling in seconds')
    baseline_plan.add_argument('--rapid-phase-sec', type=float, default=1800.0, help='Legacy alias duration of each baseline-window phase (start/end) in seconds')
    baseline_plan.add_argument('--min-normal-samples', type=int, default=120, help='Minimum normal samples required by readiness gate')
    baseline_plan.add_argument('--min-baseline-samples', dest='min_baseline_samples', type=int, default=300, help='Minimum baseline-window samples required by readiness gate')
    baseline_plan.add_argument('--min-rapid-samples', dest='min_rapid_samples', type=int, default=0, help='Legacy alias for --min-baseline-samples')
    baseline_plan.add_argument('--output', default='', help='Optional path for publish-grade schedule packet')

    baseline_run = baseline_sub.add_parser('overnight-run')
    baseline_run.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
    baseline_run.add_argument('--mode', choices=list(MODES), default=_state_default_mode())
    baseline_run.add_argument('--overnight-hours', type=float, default=8.0, help='Total schedule window in hours')
    baseline_run.add_argument('--normal-interval-sec', type=float, default=30.0, help='Normal sampling interval in seconds')
    baseline_run.add_argument('--rapid-interval-sec', type=float, default=2.0, help='Legacy alias cadence for baseline-window sampling in seconds')
    baseline_run.add_argument('--rapid-phase-sec', type=float, default=1800.0, help='Legacy alias duration of each baseline-window phase (start/end) in seconds')
    baseline_run.add_argument('--min-normal-samples', type=int, default=120, help='Minimum normal samples required by readiness gate')
    baseline_run.add_argument('--min-baseline-samples', dest='min_baseline_samples', type=int, default=300, help='Minimum baseline-window samples required by readiness gate')
    baseline_run.add_argument('--min-rapid-samples', dest='min_rapid_samples', type=int, default=0, help='Legacy alias for --min-baseline-samples')
    baseline_run.add_argument('--output', default='', help='Optional path for publish-grade orchestration packet')

    baseline_monitor_status = baseline_sub.add_parser('monitor-status')
    baseline_monitor_status.add_argument('--normal-interval-sec', type=float, default=float(RESOURCE_NORMAL_INTERVAL_SEC))

    baseline_monitor_stop = baseline_sub.add_parser('monitor-stop')
    baseline_monitor_stop.add_argument('--timeout-sec', type=float, default=8.0)

    def _add_monitor_args(p):
        p.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
        p.add_argument('--mode', choices=list(MODES), default=_state_default_mode())
        p.add_argument('--normal-interval-sec', type=float, default=float(RESOURCE_NORMAL_INTERVAL_SEC))
        p.add_argument('--baseline-interval-sec', type=float, default=float(LOCKDOWN_BASELINE_VALIDATION_INTERVAL_SEC))
        p.add_argument('--baseline-window-sec', type=float, default=float(RESOURCE_BASELINE_WINDOW_SEC))
        p.add_argument('--baseline-sample-interval-sec', type=float, default=float(RESOURCE_BASELINE_INTERVAL_SEC))
        p.add_argument('--min-normal-samples', type=int, default=int(RESOURCE_BASELINE_MIN_NORMAL_SAMPLES))
        p.add_argument('--min-baseline-samples', type=int, default=int(RESOURCE_BASELINE_MIN_BASELINE_SAMPLES))

    baseline_monitor_start = baseline_sub.add_parser('monitor-start')
    _add_monitor_args(baseline_monitor_start)
    baseline_monitor_start.add_argument('--startup-probe-sec', type=float, default=3.0)

    baseline_monitor_once = baseline_sub.add_parser('monitor-once')
    _add_monitor_args(baseline_monitor_once)

    baseline_monitor_loop = baseline_sub.add_parser('monitor-loop')
    _add_monitor_args(baseline_monitor_loop)

    librarian = sub.add_parser('librarian', help='Mode-store operations')
    librarian_sub = librarian.add_subparsers(dest='lib_cmd', required=True)
    librarian_sub.add_parser('status')
    lib_check = librarian_sub.add_parser('check')
    lib_check.add_argument('--mode', choices=list(MODES), default=_state_default_mode())
    lib_restart = librarian_sub.add_parser('restart')
    lib_restart.add_argument('--timeout-sec', type=float, default=8.0, help='Seconds to wait for librarian stop before escalation')
    lib_restart.add_argument('--startup-probe-sec', type=float, default=6.0, help='Seconds to probe for librarian heartbeat after restart')
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
    if args.command == 'sandbox' and args.sandbox_cmd == 'runs':
        if args.sandbox_runs_cmd == 'list':
            args.sandbox_cmd = 'runs-list'
        elif args.sandbox_runs_cmd == 'show':
            args.sandbox_cmd = 'runs-show'
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
        elif args.mode_cmd == 'switch':
            args.ops_cmd = 'mode-switch'
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
