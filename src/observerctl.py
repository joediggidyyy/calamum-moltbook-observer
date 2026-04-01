"""observerctl: standalone observer-scoped runtime operations CLI.

Normative constraints:
- observerctl is an observer runtime/security-operations surface.
- It must not depend on CodeSentinel runtime process orchestration.
- Output is names-only, deterministic, and fail-closed compatible.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
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
from typing import Any, Dict, List, Mapping, Optional, Tuple

from calamum_config import get_calamum_control_dir, get_calamum_data_dir, get_calamum_health_dir
from observerctl_sandbox_registry import get_definition as sandbox_get_definition
from observerctl_sandbox_registry import get_definitions as sandbox_get_definitions
from observerctl_sandbox_registry import run_definition as sandbox_run_definition
from observerctl_sandbox_render import render_human_packet as render_sandbox_human_packet
from observerctl_sandbox_runs import get_run as sandbox_get_run
from observerctl_sandbox_runs import list_runs as sandbox_list_runs
from observerctl_terminal import ljust_ansi, rjust_ansi, strip_ansi, style_heading, style_text


MODES = ('watch', 'canary', 'live', 'honeypot')
SOURCES = ('sim', 'real')
REASON_MAP = {
    'critical_check_failed:heartbeat.watchdog': 'critical_check_failed:watchdog_heartbeat_stale',
    'critical_check_failed:heartbeat.observer': 'critical_check_failed:observer_heartbeat_stale',
}
ACTIVATION_REASON_PRIORITY = [
    'critical_check_failed:watchdog_heartbeat_stale',
    'critical_check_failed:observer_heartbeat_stale',
    'critical_check_failed:env.signing_key',
    'critical_check_failed:env.moltbook_api_key',
    'critical_check_failed:watchdog_trigger_posture_invalid',
    'critical_check_failed:run_security_report_missing',
    'critical_check_failed:lockdown_heartbeat_rate_not_escalated',
    'critical_check_failed:lockdown_baseline_rate_not_escalated',
    'critical_check_failed:baseline_monitor_runtime_inactive',
    'critical_check_failed:resource_stream_retention_unavailable',
    'critical_check_failed:resource_baseline_window_incomplete',
    'critical_check_failed:resource_baseline_invalid',
    'critical_check_failed:resource_sampling_stale',
    'critical_check_failed:cpu_spike_lockdown',
    'critical_check_failed:ram_spike_lockdown',
    'critical_check_failed:resource_spike_score_critical',
]
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


def _utc_compact_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _project_anchor() -> Path:
    return _project_root() / 'src' / 'observerctl.py'


def _read_env_presence(name: str) -> bool:
    return bool((os.getenv(name) or '').strip())


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _merge_evidence_refs(*collections: Any) -> List[str]:
    refs: List[str] = []
    for collection in collections:
        if isinstance(collection, list):
            for item in collection:
                text = str(item or '').strip()
                if text and text not in refs:
                    refs.append(text)
        else:
            text = str(collection or '').strip()
            if text and text not in refs:
                refs.append(text)
    return refs


def _order_reason_codes(reason_codes: List[str], for_activation_path: bool = False) -> List[str]:
    if not for_activation_path:
        return list(reason_codes)
    priority = {code: idx for idx, code in enumerate(ACTIVATION_REASON_PRIORITY)}
    indexed = list(enumerate(reason_codes))
    indexed.sort(key=lambda item: (priority.get(str(item[1]), len(priority)), item[0]))
    return [str(code) for _, code in indexed]


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


def _monitor_state_text(raw: Dict[str, Any], key: str, issues: List[str]) -> str:
    value = raw.get(key, '')
    if value in ('', None):
        return ''
    if not isinstance(value, str):
        issues.append('invalid_type:{0}'.format(key))
    return str(value).strip()


def _monitor_state_float(raw: Dict[str, Any], key: str, issues: List[str]) -> float:
    value = raw.get(key, 0.0)
    if value in ('', None):
        return 0.0
    parsed = _to_float_or_none(value)
    if parsed is None or float(parsed) < 0.0:
        issues.append('invalid_float:{0}'.format(key))
        return 0.0
    return float(parsed)


def _load_monitor_continuity(raw_state: Dict[str, Any]) -> Dict[str, Any]:
    raw = raw_state if isinstance(raw_state, dict) else {}
    issues: List[str] = []

    anchors = {
        'last_normal_sample_epoch_s': _monitor_state_float(raw, 'last_normal_sample_epoch_s', issues),
        'last_baseline_window_epoch_s': _monitor_state_float(raw, 'last_baseline_window_epoch_s', issues),
        'last_analysis_epoch_s': _monitor_state_float(raw, 'last_analysis_epoch_s', issues),
        'last_normal_packet_path': _monitor_state_text(raw, 'last_normal_packet_path', issues),
        'last_baseline_packet_path': _monitor_state_text(raw, 'last_baseline_packet_path', issues),
        'last_analysis_packet_path': _monitor_state_text(raw, 'last_analysis_packet_path', issues),
        'last_validation_cycle_packet_path': _monitor_state_text(raw, 'last_validation_cycle_packet_path', issues),
        'last_validation_cycle_decision': _monitor_state_text(raw, 'last_validation_cycle_decision', issues),
        'last_validation_cycle_event': _monitor_state_text(raw, 'last_validation_cycle_event', issues),
        'last_validation_cycle_at_utc': _monitor_state_text(raw, 'last_validation_cycle_at_utc', issues),
        'last_baseline_window_id': _monitor_state_text(raw, 'last_baseline_window_id', issues),
    }

    ts_text = anchors['last_validation_cycle_at_utc']
    if ts_text and _parse_utc_iso8601(ts_text) is None:
        issues.append('invalid_timestamp:last_validation_cycle_at_utc')
        anchors['last_validation_cycle_at_utc'] = ''

    if not anchors['last_baseline_window_id'] and anchors['last_baseline_packet_path']:
        baseline_packet = _load_json_file(Path(anchors['last_baseline_packet_path'].replace('/', os.sep)), {})
        derived_window_id = str(baseline_packet.get('window_id', '') or '').strip()
        if derived_window_id:
            anchors['last_baseline_window_id'] = derived_window_id

    prior_cycle_present = bool(anchors['last_validation_cycle_packet_path'])
    if issues:
        state = 'degraded'
        reason_codes = ['major_check_failed:baseline_monitor_state_malformed']
    elif prior_cycle_present:
        state = 'preserved'
        reason_codes = []
    else:
        state = 'fresh_start'
        reason_codes = []

    return {
        'state': state,
        'reason_codes': reason_codes,
        'detail_codes': issues,
        'anchors': anchors,
    }


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
    ts = _utc_compact_stamp()
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
    expected_stream_type = 'resource_normal'
    index_rows = _load_resource_index_rows(source, mode, stream_type=expected_stream_type)
    latest_record = index_rows[-1] if index_rows else None
    total_records = 0
    for row in index_rows:
        try:
            total_records += int(row.get('segment_records', 0) or 0)
        except Exception:
            total_records += 0
    latest_ts = _parse_utc_iso8601((latest_record or {}).get('timestamp_utc')) if latest_record else None
    age_seconds = None if latest_ts is None else max(0.0, (datetime.now(timezone.utc) - latest_ts).total_seconds())

    manifest_path = _resource_archive_dir() / 'manifest.json'
    manifest_payload = _load_json_file(manifest_path, {}) if manifest_path.exists() else {}
    resolution = _resolve_resource_segment(str((latest_record or {}).get('segment_path', '') or ''), manifest_payload)

    ready = bool(idx.exists() and latest_record and bool(resolution.get('segment_exists')) and age_seconds is not None and age_seconds <= float(max_age_sec))
    return {
        'path': str(idx).replace('\\', '/'),
        'exists': idx.exists(),
        'expected_stream_type': expected_stream_type,
        'latest_record': latest_record or {},
        'archive_manifest_path': str(manifest_path).replace('\\', '/'),
        'archive_manifest_exists': bool(manifest_path.exists()),
        'segment_resolution': str(resolution.get('segment_resolution', 'missing')),
        'resolved_segment_path': str(resolution.get('resolved_segment_path', '')),
        'archived_artifact_path': str(resolution.get('archived_artifact_path', '')),
        'segment_exists': bool(resolution.get('segment_exists')),
        'age_seconds': None if age_seconds is None else round(float(age_seconds), 3),
        'max_age_seconds': float(max_age_sec),
        'records_indexed': int(total_records),
        'status': 'ok' if ready else 'err',
    }


def _load_resource_index_rows(
    source: str,
    mode: str,
    stream_type: str = '',
    baseline_window_id: str = '',
) -> List[Dict[str, Any]]:
    idx = _resource_index_path(source, mode)
    rows: List[Dict[str, Any]] = []
    if not idx.exists():
        return rows

    expected_stream_type = str(stream_type or '').strip().lower()
    expected_window_id = str(baseline_window_id or '').strip()
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
                row_stream_type = str(row.get('stream_type', '')).strip().lower()
                if expected_stream_type and row_stream_type != expected_stream_type:
                    continue
                row_window_id = str(row.get('baseline_window_id') or row.get('window_id') or '').strip()
                if expected_window_id and row_window_id != expected_window_id:
                    continue
                rows.append(row)
    except Exception:
        return []
    return rows


def _resolve_resource_segment(raw_segment_path_text: str, manifest_payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_segment_path = Path(str(raw_segment_path_text or '').replace('/', os.sep)) if str(raw_segment_path_text or '').strip() else None
    archived_artifact_path = ''
    segment_exists = False
    resolved_segment_path = ''
    segment_resolution = 'missing'

    if raw_segment_path and raw_segment_path.exists():
        segment_exists = True
        resolved_segment_path = str(raw_segment_path).replace('\\', '/')
        segment_resolution = 'raw'
    elif raw_segment_path:
        manifest_row = manifest_payload.get(raw_segment_path.name, {}) if isinstance(manifest_payload, dict) else {}
        artifact_rel = str((manifest_row or {}).get('artifact_path', '') or '').strip() if isinstance(manifest_row, dict) else ''
        if artifact_rel:
            artifact_path = _resource_archive_dir() / artifact_rel
            archived_artifact_path = str(artifact_path).replace('\\', '/')
            if artifact_path.exists():
                segment_exists = True
                resolved_segment_path = archived_artifact_path
                segment_resolution = 'archived'

    return {
        'segment_path': str(raw_segment_path_text or '').strip(),
        'segment_exists': bool(segment_exists),
        'resolved_segment_path': resolved_segment_path,
        'archived_artifact_path': archived_artifact_path,
        'segment_resolution': segment_resolution,
    }


def _summarize_segment_resolutions(segment_rows: List[Dict[str, Any]]) -> str:
    if not segment_rows:
        return 'missing'
    resolutions = {str(row.get('segment_resolution', 'missing')).strip().lower() or 'missing' for row in segment_rows}
    if resolutions == {'raw'}:
        return 'raw'
    if resolutions == {'archived'}:
        return 'archived'
    if 'missing' in resolutions:
        return 'missing'
    return 'mixed'


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

    idx = _resource_index_path(source, mode)
    manifest_path = _resource_archive_dir() / 'manifest.json'
    manifest_payload = _load_json_file(manifest_path, {}) if manifest_path.exists() else {}
    all_baseline_rows = _load_resource_index_rows(source, mode, stream_type='resource_baseline')

    baseline_window_id = str(packet.get('baseline_window_id') or packet.get('window_id') or '').strip()
    if not baseline_window_id and all_baseline_rows:
        baseline_window_id = str((all_baseline_rows[-1].get('baseline_window_id') or all_baseline_rows[-1].get('window_id') or '')).strip()

    baseline_rows = _load_resource_index_rows(source, mode, stream_type='resource_baseline', baseline_window_id=baseline_window_id) if baseline_window_id else []
    resolved_segments = [_resolve_resource_segment(str(row.get('segment_path', '') or ''), manifest_payload) for row in baseline_rows]
    resolved_segment_paths = [str(row.get('resolved_segment_path', '')) for row in resolved_segments if str(row.get('resolved_segment_path', '')).strip()]
    raw_segment_paths = [str(row.get('segment_path', '') or '').strip() for row in baseline_rows if str(row.get('segment_path', '') or '').strip()]
    archived_artifact_paths = [str(row.get('archived_artifact_path', '')) for row in resolved_segments if str(row.get('archived_artifact_path', '')).strip()]
    missing_segment_paths = [
        str(row.get('segment_path', '') or '').strip()
        for row, resolved in zip(baseline_rows, resolved_segments)
        if not bool(resolved.get('segment_exists'))
    ]
    segment_resolution = _summarize_segment_resolutions(resolved_segments)
    resolved_segment_count = sum(1 for row in resolved_segments if bool(row.get('segment_exists')))

    ready = bool(
        packet
        and decision == 'go'
        and age_seconds is not None
        and age_seconds <= float(max_age_sec)
        and baseline_window_id
        and baseline_rows
        and resolved_segment_count == len(resolved_segments)
    )
    return {
        'packet_path': str(((packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
        'decision': decision,
        'age_seconds': None if age_seconds is None else round(float(age_seconds), 3),
        'max_age_seconds': float(max_age_sec),
        'sample_counts': packet.get('sample_counts', {}) if isinstance(packet.get('sample_counts', {}), dict) else {},
        'baseline_window_id': baseline_window_id,
        'index_path': str(idx).replace('\\', '/'),
        'archive_manifest_path': str(manifest_path).replace('\\', '/'),
        'archive_manifest_exists': bool(manifest_path.exists()),
        'segment_count': int(len(resolved_segments)),
        'resolved_segment_count': int(resolved_segment_count),
        'segment_resolution': segment_resolution,
        'segment_paths': raw_segment_paths,
        'latest_segment_path': raw_segment_paths[-1] if raw_segment_paths else '',
        'resolved_segment_paths': resolved_segment_paths,
        'archived_artifact_paths': archived_artifact_paths,
        'missing_segment_paths': missing_segment_paths,
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
    continuity = _load_monitor_continuity(monitor_state)
    continuity_anchors = continuity['anchors']
    last_normal_epoch = float(continuity_anchors.get('last_normal_sample_epoch_s', 0.0) or 0.0)
    last_baseline_epoch = float(continuity_anchors.get('last_baseline_window_epoch_s', 0.0) or 0.0)
    last_analysis_epoch = float(continuity_anchors.get('last_analysis_epoch_s', 0.0) or 0.0)

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
            window_id='monitor_normal_{0}'.format(_utc_compact_stamp()),
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
            window_id='monitor_baseline_{0}'.format(_utc_compact_stamp()),
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

    current_normal_packet_path = str(((normal_packet.get('provenance', {}) or {}).get('artifact_path', '')) or '')
    current_baseline_packet_path = str(((baseline_packet.get('provenance', {}) or {}).get('artifact_path', '')) or '')
    current_analysis_packet_path = str(((analysis_packet.get('provenance', {}) or {}).get('artifact_path', '')) or '')
    current_baseline_window_id = str(baseline_packet.get('window_id', '') or '').strip() if baseline_packet else ''

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
        'last_normal_packet_path': current_normal_packet_path or str(continuity_anchors.get('last_normal_packet_path', '') or ''),
        'last_baseline_packet_path': current_baseline_packet_path or str(continuity_anchors.get('last_baseline_packet_path', '') or ''),
        'last_analysis_packet_path': current_analysis_packet_path or str(continuity_anchors.get('last_analysis_packet_path', '') or ''),
        'last_baseline_window_id': current_baseline_window_id or str(continuity_anchors.get('last_baseline_window_id', '') or ''),
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

    baseline_window_id = current_baseline_window_id

    cycle_event = 'baseline_monitor_cycle'
    cycle_output_event = 'baseline_validation_cycle'
    cycle_packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': decision,
        'action': 'baseline-monitor-cycle',
        'source': src,
        'mode': m,
        'posture_trigger': _posture_for_mode(m),
        'baseline_window_id': baseline_window_id,
        'result': 'pass' if decision == 'go' else 'fail',
        'reason_codes': reasons,
        'posture_packet_path': str(posture_packet.get('receipt_path', '') or ''),
        'normal_packet_path': str(((normal_packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
        'baseline_packet_path': str(((baseline_packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
        'analysis_packet_path': str(((analysis_packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
        'monitor_state_path': str(_baseline_monitor_state_path()).replace('\\', '/'),
        'continuity': {
            'state': str(continuity.get('state', 'fresh_start')),
            'reason_codes': list(continuity.get('reason_codes', [])),
            'detail_codes': list(continuity.get('detail_codes', [])),
            'previous_validation_cycle': {
                'event': str(continuity_anchors.get('last_validation_cycle_event', '') or ''),
                'decision': str(continuity_anchors.get('last_validation_cycle_decision', '') or ''),
                'timestamp_utc': str(continuity_anchors.get('last_validation_cycle_at_utc', '') or ''),
                'packet_path': str(continuity_anchors.get('last_validation_cycle_packet_path', '') or ''),
            },
            'previous_baseline': {
                'packet_path': str(continuity_anchors.get('last_baseline_packet_path', '') or ''),
                'window_id': str(continuity_anchors.get('last_baseline_window_id', '') or ''),
            },
            'previous_analysis_packet_path': str(continuity_anchors.get('last_analysis_packet_path', '') or ''),
            'previous_normal_packet_path': str(continuity_anchors.get('last_normal_packet_path', '') or ''),
        },
        'provenance': {
            'generated_at_utc': _utc_now(),
            'producer_process': 'observerctl baseline monitor-once',
            'artifact_path': '',
            'artifact_sha256': '',
            'upstream_inputs': {
                'watchdog_posture_state': str(_control_file(WATCHDOG_POSTURE_FILE)).replace('\\', '/'),
                'baseline_monitor_state': str(_baseline_monitor_state_path()).replace('\\', '/'),
                'resource_index': str(_resource_index_path(src, m)).replace('\\', '/'),
                'evidence_index': str(_evidence_index_path(src, m)).replace('\\', '/'),
            },
        },
        'methodology': {
            'sampling_strategy': 'single baseline-monitor cycle composed from posture apply, continuous resource sampling, optional baseline window, and saved analysis',
            'runtime_constraints': ['names-only outputs', 'append-only validation-cycle evidence'],
            'failure_modes': ['posture_apply_failed', 'baseline_analysis_failed', 'cycle_packet_write_failed'],
        },
        'process': {
            'phase': 'baseline_monitor_validation_cycle',
            'event': cycle_event,
            'decision': decision,
            'reason_codes': reasons,
            'approver_checkpoint': 'required_for_live_transition',
            'evidence_refs': [
                str(_baseline_monitor_state_path()).replace('\\', '/'),
            ] + [
                ref for ref in [
                    str(continuity_anchors.get('last_validation_cycle_packet_path', '') or ''),
                    str(continuity_anchors.get('last_baseline_packet_path', '') or ''),
                    str(posture_packet.get('receipt_path', '') or ''),
                    str(((normal_packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
                    str(((baseline_packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
                    str(((analysis_packet.get('provenance', {}) or {}).get('artifact_path', '')) or ''),
                ] if str(ref).strip()
            ],
        },
    }
    cycle_packet.update(_make_run_linkage(m, event=cycle_event))
    cycle_output_path = _resource_evidence_output_path(src, m, cycle_output_event)
    cycle_packet = _write_packet(cycle_packet, cycle_output_path)
    _append_jsonl(_evidence_index_path(src, m), {
        'timestamp_utc': _utc_now(),
        'packet_path': str(cycle_output_path).replace('\\', '/'),
        'decision': cycle_packet.get('decision', 'no-go'),
        'run_id': cycle_packet.get('run_id', ''),
        'scope': {'source': src, 'mode': m},
        'event': cycle_event,
    })

    monitor_payload['last_validation_cycle_packet_path'] = str(cycle_output_path).replace('\\', '/')
    monitor_payload['last_validation_cycle_decision'] = str(cycle_packet.get('decision', decision))
    monitor_payload['last_validation_cycle_event'] = cycle_event
    monitor_payload['last_validation_cycle_at_utc'] = str(cycle_packet.get('timestamp_utc', ''))
    _write_json_file(_baseline_monitor_state_path(), monitor_payload)

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
        'validation_cycle_packet_path': str(cycle_output_path).replace('\\', '/'),
        'validation_cycle_packet_decision': str(cycle_packet.get('decision', decision)),
        'validation_cycle_event': cycle_event,
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
    from obfuscator_lib import signing_env_presence

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

    signing_presence = signing_env_presence(['requester', 'librarian', 'source', 'vault'])
    signing_ok = bool(signing_presence.get('present', False))
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
            'names': list(signing_presence.get('names', [])),
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

        baseline_monitor_runtime = checks.get('runtime.baseline_monitor') or {}
        if str(baseline_monitor_runtime.get('status', 'err')).lower() != 'ok':
            reasons.append('critical_check_failed:baseline_monitor_runtime_inactive')

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
    deduped = _order_reason_codes(deduped, for_activation_path=bool(posture_required == 'lockdown'))

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
    packet['evidence_refs'] = _collect_evidence_refs(checks)
    readiness_surfaces = _build_readiness_surfaces(status_packet, packet)
    packet['readiness_surfaces'] = readiness_surfaces
    packet['stage5_prerequisites'] = _build_stage5_prerequisites(readiness_surfaces)
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
    _add(resource_row.get('archive_manifest_path', ''))
    _add(resource_row.get('resolved_segment_path', ''))
    latest_record = resource_row.get('latest_record', {}) if isinstance(resource_row.get('latest_record', {}), dict) else {}
    _add(latest_record.get('segment_path', ''))

    baseline_row = checks.get('watchdog.resource_baseline_window') or {}
    _add(baseline_row.get('packet_path', ''))
    _add(baseline_row.get('index_path', ''))
    _add(baseline_row.get('archive_manifest_path', ''))
    _add(baseline_row.get('latest_segment_path', ''))
    for ref in baseline_row.get('resolved_segment_paths', []) if isinstance(baseline_row.get('resolved_segment_paths', []), list) else []:
        _add(ref)
    for ref in baseline_row.get('segment_paths', []) if isinstance(baseline_row.get('segment_paths', []), list) else []:
        _add(ref)

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
            'resolved_segment_path': str(resource_row.get('resolved_segment_path', '')),
            'segment_resolution': str(resource_row.get('segment_resolution', 'missing')),
            'archive_manifest_path': str(resource_row.get('archive_manifest_path', '')),
            'archived_artifact_path': str(resource_row.get('archived_artifact_path', '')),
            'records_indexed': int(resource_row.get('records_indexed', 0) or 0),
        },
        'baseline_window': {
            'status': str(baseline_row.get('status', 'err')).lower(),
            'packet_path': str(baseline_row.get('packet_path', '')),
            'decision': str(baseline_row.get('decision', 'no-go')),
            'baseline_window_id': str(baseline_row.get('baseline_window_id', '')),
            'sample_counts': baseline_row.get('sample_counts', {}) if isinstance(baseline_row.get('sample_counts', {}), dict) else {},
            'index_path': str(baseline_row.get('index_path', '')),
            'archive_manifest_path': str(baseline_row.get('archive_manifest_path', '')),
            'archive_manifest_exists': bool(baseline_row.get('archive_manifest_exists')),
            'segment_count': int(baseline_row.get('segment_count', 0) or 0),
            'resolved_segment_count': int(baseline_row.get('resolved_segment_count', 0) or 0),
            'segment_resolution': str(baseline_row.get('segment_resolution', 'missing')),
            'latest_segment_path': str(baseline_row.get('latest_segment_path', '')),
            'segment_paths': list(baseline_row.get('segment_paths', [])) if isinstance(baseline_row.get('segment_paths', []), list) else [],
            'resolved_segment_paths': list(baseline_row.get('resolved_segment_paths', [])) if isinstance(baseline_row.get('resolved_segment_paths', []), list) else [],
            'missing_segment_paths': list(baseline_row.get('missing_segment_paths', [])) if isinstance(baseline_row.get('missing_segment_paths', []), list) else [],
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
            'segment_resolution': str(resource_stream.get('segment_resolution', 'missing')),
            'evidence_refs': [
                ref for ref in [
                    str(resource_stream.get('index_path', '')),
                    str(resource_stream.get('latest_segment_path', '')),
                    str(resource_stream.get('resolved_segment_path', '')),
                    str(resource_stream.get('archive_manifest_path', '')),
                ] if ref.strip()
            ],
        },
        'C25_resource_baseline_window_ready': {
            'status': 'ok' if baseline_ready else 'err',
            'reason_codes': [] if baseline_ready else ['critical_check_failed:resource_baseline_window_incomplete'],
            'decision': str(baseline_window.get('decision', 'no-go')),
            'baseline_window_id': str(baseline_window.get('baseline_window_id', '')),
            'sample_counts': baseline_window.get('sample_counts', {}) if isinstance(baseline_window.get('sample_counts', {}), dict) else {},
            'segment_count': int(baseline_window.get('segment_count', 0) or 0),
            'resolved_segment_count': int(baseline_window.get('resolved_segment_count', 0) or 0),
            'segment_resolution': str(baseline_window.get('segment_resolution', 'missing')),
            'evidence_refs': [
                ref for ref in (
                    [
                        str(baseline_window.get('packet_path', '')),
                        str(baseline_window.get('index_path', '')),
                        str(baseline_window.get('latest_segment_path', '')),
                        str(baseline_window.get('archive_manifest_path', '')),
                    ]
                    + list(baseline_window.get('resolved_segment_paths', []))
                )
                if str(ref).strip()
            ],
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
        'sampling_strategy': 'names-only runtime posture and saved-readiness sampling from health/data/control artifacts',
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

    from obfuscator_lib import signing_env_presence

    signing_presence = signing_env_presence(['requester', 'librarian', 'source', 'vault'])
    env_presence_keys = list(signing_presence.get('names', []))
    if 'MOLTBOOK_API_KEY' not in env_presence_keys:
        env_presence_keys.append('MOLTBOOK_API_KEY')

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
                'env_presence_keys': env_presence_keys,
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
    ts = _utc_compact_stamp()
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
    lines.append(style_heading('Librarian stores'))
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
        if len(lines) > (2 if ts else 1):
            lines.append('')
        lines.append(_style_structural_label('{0}'.format(mode + (' [active]' if is_active else ''))))
        lines.extend(
            _render_human_kv_rows(
                [
                    ('Exists', _yes_no_text(exists)),
                    ('Retention', retention),
                    ('Path', path),
                ],
                min_label_width=10,
                max_label_width=12,
                indent='  ',
            )
        )
    return lines


def _style_structural_label(text: str) -> str:
    return style_text(str(text or ''), 'structure')


def _style_section_title(title: str) -> str:
    return style_heading(str(title or ''))


def _style_decision_value(value: str) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in ('go', 'ok', 'pass', 'success'):
        return style_text(str(value or ''), 'positive')
    if normalized in ('no-go', 'fail', 'failed', 'err', 'error'):
        return style_text(str(value or ''), 'negative')
    return style_text(str(value or ''), 'advisory')


def _style_readiness_value(value: str) -> str:
    normalized = str(value or '').strip().lower()
    if normalized == 'ready':
        return style_text(str(value or ''), 'positive')
    if normalized in ('needs-input', 'blocked'):
        return style_text(str(value or ''), 'advisory')
    return str(value or '')


def _style_blocked_value(blocked: bool) -> str:
    return style_text('yes' if blocked else 'no', 'negative' if blocked else 'positive')


def _yes_no_text(value: bool) -> str:
    return 'yes' if bool(value) else 'no'


def _style_choice_label(prefix: str, label: str, role: str = 'structure') -> str:
    return '{0}{1}'.format(str(prefix or ''), style_text(str(label or ''), role))


def _style_padded_choice_label(prefix: str, label: str, width: int, role: str = 'structure') -> str:
    prefix_text = str(prefix or '')
    content = '{0}{1}'.format(prefix_text, style_text(str(label or ''), role))
    return ljust_ansi(content, len(prefix_text) + int(width))


def _style_section_line(label: str) -> str:
    return '{0}:'.format(style_heading(str(label or '')))


def _render_human_path_tail(value: Any) -> str:
    text = str(value or '').strip().replace('\\', '/')
    if not text:
        return ''
    parts = [part for part in text.split('/') if part]
    if not parts:
        return text
    lowered = [part.lower() for part in parts]
    for anchor in ('dataset_access', 'indexes', 'reports'):
        if anchor in lowered:
            return '/'.join(parts[lowered.index(anchor):])
    if 'local_untracked' in lowered:
        idx = lowered.index('local_untracked') + 1
        tail = parts[idx:]
        if tail:
            return '/'.join(tail[-4:] if len(tail) > 4 else tail)
    if len(parts) >= 3:
        return '/'.join(parts[-3:])
    if len(parts) >= 2:
        return '/'.join(parts[-2:])
    return parts[-1]


def _render_human_kv_rows(
    rows: List[Tuple[str, Any]],
    min_label_width: int = 12,
    max_label_width: int = 28,
    indent: str = '',
) -> List[str]:
    cleaned: List[Tuple[str, str]] = []
    for label, value in rows:
        label_text = str(label or '').strip()
        value_text = str(value or '').strip()
        if not label_text or not value_text:
            continue
        cleaned.append((label_text, value_text))
    if not cleaned:
        return []
    label_width = max(min_label_width, min(max_label_width, max(len(label) for label, _ in cleaned)))
    lines: List[str] = []
    for label_text, value_text in cleaned:
        chunks = [chunk.rstrip() for chunk in value_text.splitlines()] or ['']
        lines.append('{0}{1:<{2}} {3}'.format(indent, label_text + ':', label_width + 1, chunks[0]))
        continuation_prefix = indent + (' ' * (label_width + 2))
        for chunk in chunks[1:]:
            lines.append('{0}{1}'.format(continuation_prefix, chunk))
    return lines


def _append_human_section(lines: List[str], title: str, body_lines: List[str]) -> None:
    body = [str(line).rstrip() for line in body_lines]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    if not body:
        return
    if lines and str(lines[-1]).strip():
        lines.append('')
    lines.append(_style_section_title(title))
    lines.extend(body)


def _render_librarian_dataset_heading(row: Dict[str, Any], include_index: bool = True) -> str:
    label = str(row.get('display_name', '') or row.get('entry_id', '') or 'dataset').strip()
    index_value = int(row.get('index', 0) or 0)
    if include_index and index_value > 0:
        return _style_choice_label('{0}. '.format(index_value), label)
    return _style_structural_label(label)


def _render_librarian_dataset_metadata_rows(row: Dict[str, Any]) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    selector = str(row.get('run_id', '') or row.get('entry_id', '') or '').strip()
    if selector:
        rows.append(('Selector', selector))
    rows.append(('Access', str(row.get('access_class', 'local'))))
    rows.append(('Workflow', str(row.get('workflow', 'unknown'))))
    rows.append(('Records', str(int(row.get('record_count', 0) or 0))))
    status = str(row.get('status', '') or '').strip()
    if status and status != 'unknown':
        rows.append(('Status', status))
    readiness = str(row.get('readiness', '') or '').strip()
    if readiness and readiness != 'unknown':
        rows.append(('Readiness', readiness))
    source = str(row.get('source', '') or '').strip()
    if source and source != 'unknown':
        rows.append(('Source', source))
    mode = str(row.get('mode', '') or '').strip()
    if mode and mode != 'unknown':
        rows.append(('Mode', mode))
    if bool(row.get('has_labels', False)):
        rows.append(('Labels', 'yes'))
    return rows


def _render_librarian_dataset_block(row: Dict[str, Any], include_index: bool = True, indent: str = '') -> List[str]:
    lines = ['{0}{1}'.format(indent, _render_librarian_dataset_heading(row, include_index=include_index))]
    lines.extend(
        _render_human_kv_rows(
            _render_librarian_dataset_metadata_rows(row),
            min_label_width=12,
            max_label_width=18,
            indent=indent + '  ',
        )
    )
    return lines


def _render_librarian_dataset_action_guidance_lines(packet: Dict[str, Any]) -> List[str]:
    action = str(packet.get('action', '') or '').strip().lower()
    decision = str(packet.get('decision', '') or '').strip().lower()
    reason_codes = packet.get('reason_codes', []) if isinstance(packet.get('reason_codes', []), list) else []
    release_mode = str(packet.get('release_mode', '') or '').strip().lower()
    if decision == 'go':
        if action == 'librarian-dataset-register':
            return [
                'Next: review the approved list with observerctl librarian dataset list or release the dataset by selector when needed.',
            ]
        if release_mode == 'protected-source':
            return [
                'Next: use the released dataset manifest in the next DS step or hydrate the same selector in the wizard.',
            ]
        return [
            'Next: use the resolved dataset manifest in the next DS step or hydrate the same selector in the wizard.',
        ]
    if 'critical_check_failed:librarian_dataset_not_found' in reason_codes:
        return ['Next: review observerctl librarian dataset list and retry with a valid selector.']
    if 'critical_check_failed:librarian_dataset_not_ready' in reason_codes:
        return ['Next: repair the missing dataset artifacts or choose a ready approved dataset.']
    if 'critical_check_failed:librarian_dataset_manifest_missing' in reason_codes:
        return ['Next: provide an existing dataset_manifest.json path and retry the action.']
    if 'critical_check_failed:librarian_vault_locked' in reason_codes:
        return ['Next: review observerctl librarian vault status or unlock the vault before retrying ordinary dataset mutations.']
    if (
        'critical_check_failed:librarian_dataset_request_invalid' in reason_codes
        or 'critical_check_failed:librarian_dataset_attestation_invalid' in reason_codes
    ):
        return ['Next: retry the release with a fresh selector request after reviewing the delegated access artifacts.']
    return ['Next: review the reasons above and retry with a ready approved dataset.']


def _render_librarian_dataset_selector_line(row: Dict[str, Any]) -> str:
    label = str(row.get('display_name', '') or row.get('entry_id', '') or 'dataset').strip()
    return '{0}. {1} | access={2} | workflow={3} | records={4}'.format(
        int(row.get('index', 0) or 0),
        label,
        str(row.get('access_class', 'local')),
        str(row.get('workflow', 'unknown')),
        int(row.get('record_count', 0) or 0),
    )


def _render_librarian_datasets_human(packet: Dict[str, Any]) -> List[str]:
    lines: List[str] = [_style_section_title('Librarian datasets')]
    ts = str(packet.get('timestamp_utc', '') or '').strip()
    if ts:
        lines.append('generated_at_utc: {0}'.format(ts))
    decision = str(packet.get('decision', '') or '').strip().lower()
    summary = str(packet.get('summary', '') or '').strip()
    entries = packet.get('selector_entries', []) if isinstance(packet.get('selector_entries', []), list) else []
    if decision or summary:
        if summary:
            lines.append('decision: {0} - {1}'.format(_style_decision_value(decision or 'go'), summary))
        else:
            lines.append('decision: {0}'.format(_style_decision_value(decision)))

    _append_human_section(
        lines,
        'Summary',
        _render_human_kv_rows(
            [
                ('Count', str(int(packet.get('count', len(entries)) or 0))),
                ('Authority', 'librarian-approved dataset snapshot'),
                ('Availability', 'ready' if entries else 'empty'),
            ],
            indent='  ',
        ),
    )

    dataset_lines: List[str] = []
    if entries:
        for row in entries:
            if not isinstance(row, dict):
                continue
            if dataset_lines:
                dataset_lines.append('')
            dataset_lines.extend(_render_librarian_dataset_block(row, include_index=True, indent='  '))
    else:
        dataset_lines.append('  No approved datasets are registered yet.')
    _append_human_section(lines, 'Approved datasets', dataset_lines)

    artifacts = packet.get('artifacts', {}) if isinstance(packet.get('artifacts', {}), dict) else {}
    evidence_lines: List[str] = []
    for label, key in (
        ('Approved snapshot', 'librarian_dataset_manifest_json'),
        ('Catalog ledger', 'librarian_dataset_catalog_jsonl'),
    ):
        value = _render_human_path_tail(artifacts.get(key, ''))
        if value:
            evidence_lines.extend(_render_human_kv_rows([(label, value)], indent='  ', min_label_width=14, max_label_width=16))
    _append_human_section(lines, 'Evidence', evidence_lines)

    if entries:
        guidance = [
            'Next: choose a dataset by index or run_id, then release it here or hydrate the same selector in the wizard.',
        ]
    else:
        guidance = [
            'Next: register a dataset manifest with observerctl librarian dataset register <manifest> to seed the approved list.',
        ]
    _append_human_section(lines, 'Guidance', ['  {0}'.format(line) for line in guidance])
    return lines


def _render_librarian_dataset_action_human(packet: Dict[str, Any]) -> List[str]:
    action = str(packet.get('action', '') or '').strip().lower()
    title = {
        'librarian-dataset-register': 'Librarian dataset register',
        'librarian-dataset-release': 'Librarian dataset release',
    }.get(action, 'Librarian dataset action')

    lines: List[str] = [_style_section_title(title)]
    ts = str(packet.get('timestamp_utc', '') or '').strip()
    if ts:
        lines.append('generated_at_utc: {0}'.format(ts))
    decision = str(packet.get('decision', '') or '').strip().lower()
    summary = str(packet.get('summary', '') or '').strip()
    if decision or summary:
        if summary:
            lines.append('decision: {0} - {1}'.format(_style_decision_value(decision or 'no-go'), summary))
        else:
            lines.append('decision: {0}'.format(_style_decision_value(decision)))
    release_mode = str(packet.get('release_mode', '') or '').strip()

    _append_human_section(
        lines,
        'Summary',
        _render_human_kv_rows(
            [
                ('Action', 'dataset register' if action == 'librarian-dataset-register' else 'dataset release'),
                ('Release mode', release_mode),
            ],
            indent='  ',
        ),
    )

    dataset = packet.get('dataset', {}) if isinstance(packet.get('dataset', {}), dict) else {}
    if dataset:
        _append_human_section(
            lines,
            'Dataset',
            _render_librarian_dataset_block(dataset, include_index=False, indent='  '),
        )

    manifest_path = str(packet.get('dataset_manifest_path', '') or '').strip()
    reason_codes = packet.get('reason_codes', []) if isinstance(packet.get('reason_codes', []), list) else []

    artifacts = packet.get('artifacts', {}) if isinstance(packet.get('artifacts', {}), dict) else {}
    evidence_lines: List[str] = []
    seen_evidence: set = set()
    evidence_pairs: List[Tuple[str, str]] = [
        ('Release receipt', str(artifacts.get('dataset_access_release_receipt_json', '') or '').strip()),
        ('Dataset manifest', manifest_path or str(artifacts.get('dataset_manifest_path', '') or '').strip()),
        ('Request packet', str(artifacts.get('dataset_access_request_json', '') or '').strip()),
        ('Librarian attestation', str(artifacts.get('dataset_access_attestation_json', '') or '').strip()),
        ('Approved snapshot', str(artifacts.get('librarian_dataset_manifest_json', '') or '').strip()),
        ('Catalog ledger', str(artifacts.get('librarian_dataset_catalog_jsonl', '') or '').strip()),
    ]
    for label, raw_value in evidence_pairs:
        rendered_value = _render_human_path_tail(raw_value)
        if not rendered_value:
            continue
        marker = (label, rendered_value)
        if marker in seen_evidence:
            continue
        seen_evidence.add(marker)
        evidence_lines.extend(_render_human_kv_rows([(label, rendered_value)], indent='  ', min_label_width=18, max_label_width=20))
    _append_human_section(lines, 'Evidence', evidence_lines)

    if reason_codes:
        _append_human_section(lines, 'Reasons', ['  {0}'.format(reason) for reason in reason_codes])

    _append_human_section(
        lines,
        'Guidance',
        ['  {0}'.format(line) for line in _render_librarian_dataset_action_guidance_lines(packet)],
    )
    return lines


def _render_librarian_vault_guidance_lines(packet: Dict[str, Any]) -> List[str]:
    action = str(packet.get('action', '') or '').strip().lower()
    integrity_status = str(packet.get('integrity_status', '') or '').strip().lower()
    if action == 'librarian-vault-lock':
        return ['Next: run observerctl librarian vault status to confirm the maintenance lock, then unlock when the control-plane lane is complete.']
    if action == 'librarian-vault-unlock':
        return ['Next: ordinary signed dataset mutations may resume; keep explicit vault commands for integrity or maintenance lanes only.']
    if action == 'librarian-vault-rebaseline':
        return ['Next: re-run observerctl librarian vault verify if you want an explicit post-rebaseline integrity confirmation.']
    if action == 'librarian-vault-verify' and integrity_status != 'ok':
        return ['Next: inspect the vault audit trail and rebaseline only after confirming the authority-state drift is expected.']
    if integrity_status not in ('', 'ok'):
        return ['Next: review observerctl librarian vault verify and inspect the audit trail before treating the vault as settled.']
    return ['Next: keep ordinary dataset writes on the dataset family and reserve the vault family for integrity, lock state, and rebaseline controls.']


def _render_librarian_vault_human(packet: Dict[str, Any]) -> List[str]:
    action = str(packet.get('action', '') or '').strip().lower()
    title = {
        'librarian-vault-status': 'Librarian vault status',
        'librarian-vault-verify': 'Librarian vault verify',
        'librarian-vault-lock': 'Librarian vault lock',
        'librarian-vault-unlock': 'Librarian vault unlock',
        'librarian-vault-rebaseline': 'Librarian vault rebaseline',
    }.get(action, 'Librarian vault')

    lines: List[str] = [_style_section_title(title)]
    ts = str(packet.get('timestamp_utc', '') or '').strip()
    if ts:
        lines.append('generated_at_utc: {0}'.format(ts))
    decision = str(packet.get('decision', '') or '').strip().lower()
    summary = str(packet.get('summary', '') or '').strip()
    if decision or summary:
        if summary:
            lines.append('decision: {0} - {1}'.format(_style_decision_value(decision or 'go'), summary))
        else:
            lines.append('decision: {0}'.format(_style_decision_value(decision)))

    integrity = packet.get('integrity', {}) if isinstance(packet.get('integrity', {}), dict) else {}
    _append_human_section(
        lines,
        'Summary',
        _render_human_kv_rows(
            [
                ('Lock state', str(packet.get('lock_state', '') or 'unknown')),
                ('Integrity', str(packet.get('integrity_status', '') or 'unknown')),
                ('Tracked files', str(int(integrity.get('tracked_file_count', 0) or 0))),
            ],
            indent='  ',
        ),
    )

    _append_human_section(
        lines,
        'Integrity',
        _render_human_kv_rows(
            [
                ('Current checksum', str(integrity.get('current_checksum_sha256', '') or '').strip()),
                ('Baseline checksum', str(integrity.get('baseline_checksum_sha256', '') or '').strip()),
            ],
            indent='  ',
        ),
    )

    artifacts = packet.get('artifacts', {}) if isinstance(packet.get('artifacts', {}), dict) else {}
    evidence_lines: List[str] = []
    for label, key in (
        ('Vault root', 'librarian_vault_root'),
        ('Authority manifest', 'librarian_vault_authority_manifest_json'),
        ('Catalog ledger', 'librarian_vault_catalog_jsonl'),
        ('Access root', 'librarian_vault_access_root'),
        ('Checksum baseline', 'librarian_vault_baseline_json'),
        ('Audit log', 'librarian_vault_audit_jsonl'),
        ('Control state', 'librarian_vault_control_state_json'),
    ):
        value = _render_human_path_tail(artifacts.get(key, ''))
        if value:
            evidence_lines.extend(_render_human_kv_rows([(label, value)], indent='  ', min_label_width=18, max_label_width=20))
    _append_human_section(lines, 'Evidence', evidence_lines)

    reason_codes = packet.get('reason_codes', []) if isinstance(packet.get('reason_codes', []), list) else []
    if reason_codes:
        _append_human_section(lines, 'Reasons', ['  {0}'.format(reason) for reason in reason_codes])

    _append_human_section(
        lines,
        'Guidance',
        ['  {0}'.format(line) for line in _render_librarian_vault_guidance_lines(packet)],
    )
    return lines


def _render_ds_saved_heading(row: Dict[str, Any], include_index: bool = True) -> str:
    label = str(row.get('display_name', '') or row.get('entry_id', '') or 'saved item').strip()
    index_value = int(row.get('index', 0) or 0)
    if include_index and index_value > 0:
        return _style_choice_label('{0}. '.format(index_value), label)
    return _style_structural_label(label)


def _render_ds_saved_metadata_rows(row: Dict[str, Any]) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    selector_token = str(row.get('selector_token', '') or row.get('entry_id', '') or '').strip()
    if selector_token:
        rows.append(('Selector', selector_token))
    workflow = str(row.get('workflow', '') or '').strip()
    if workflow:
        rows.append(('Workflow', workflow))
    model_type = str(row.get('model_type', '') or '').strip()
    if model_type:
        rows.append(('Model', model_type))
    max_fpr = row.get('max_fpr')
    if max_fpr not in ('', None):
        rows.append(('Max FPR', str(max_fpr)))
    baseline_window_id = str(row.get('baseline_window_id', '') or '').strip()
    if baseline_window_id:
        rows.append(('Window', baseline_window_id))
    slot_id = int(row.get('slot_id', 0) or 0)
    if slot_id > 0:
        rows.append(('Slot', _ds_wizard_draft_slot_label(slot_id)))
    run_id = str(row.get('run_id', '') or '').strip()
    if run_id:
        rows.append(('Run ID', run_id))
    source = str(row.get('source', '') or '').strip()
    if source and source != 'unknown':
        rows.append(('Source', source))
    mode = str(row.get('mode', '') or '').strip()
    if mode and mode != 'unknown':
        rows.append(('Mode', mode))
    status = str(row.get('status', '') or '').strip()
    if status:
        rows.append(('Status', status))
    readiness = str(row.get('readiness', '') or '').strip()
    if readiness:
        rows.append(('Readiness', readiness))
    recorded_at_utc = str(row.get('recorded_at_utc', '') or '').strip()
    if recorded_at_utc:
        rows.append(('Recorded', recorded_at_utc))
    counts = row.get('sample_counts', {}) if isinstance(row.get('sample_counts', {}), dict) else {}
    if counts:
        rendered_counts = []
        for key in ('resource_normal', 'resource_baseline', 'total'):
            if key in counts:
                rendered_counts.append('{0}={1}'.format(key, counts.get(key)))
        if rendered_counts:
            rows.append(('Samples', ', '.join(rendered_counts)))
    summary = str(row.get('summary', '') or '').strip()
    if summary:
        rows.append(('Summary', summary))
    return rows


def _render_ds_saved_block(row: Dict[str, Any], include_index: bool = True, indent: str = '') -> List[str]:
    lines = ['{0}{1}'.format(indent, _render_ds_saved_heading(row, include_index=include_index))]
    lines.extend(
        _render_human_kv_rows(
            _render_ds_saved_metadata_rows(row),
            min_label_width=12,
            max_label_width=18,
            indent=indent + '  ',
        )
    )
    return lines


def _render_ds_saved_guidance_lines(packet: Dict[str, Any]) -> List[str]:
    action = str(packet.get('action', '') or '').strip().lower()
    if action == 'ds-saved-trained':
        return ['Next: hydrate train <index|run_id|selector> in the wizard, or use a train_manifest path directly only when intentionally bypassing selector discovery.']
    if action == 'ds-saved-runs':
        return ['Next: hydrate run <index|run_id|selector> in the wizard, or use a run.json path directly only when intentionally bypassing selector discovery.']
    if action == 'ds-saved-baselines':
        return ['Next: hydrate baseline <index|window_id|selector> in the wizard, or use a baseline packet path directly only when intentionally bypassing selector discovery.']
    if action == 'ds-saved-drafts':
        return ['Next: load draft <slot> in the wizard, or save draft with no argument to use the next canonical slot automatically.']
    return ['Next: choose a saved selector by index or stable selector token.']


def _render_ds_saved_selectors_human(packet: Dict[str, Any]) -> List[str]:
    action = str(packet.get('action', '') or '').strip().lower()
    title = {
        'ds-saved-trained': 'Retained train selectors',
        'ds-saved-runs': 'Retained run selectors',
        'ds-saved-baselines': 'Retained baseline selectors',
        'ds-saved-drafts': 'Retained draft slots',
    }.get(action, 'Retained DS selectors')

    lines: List[str] = [_style_section_title(title)]
    ts = str(packet.get('timestamp_utc', '') or '').strip()
    if ts:
        lines.append('generated_at_utc: {0}'.format(ts))
    decision = str(packet.get('decision', '') or '').strip().lower()
    summary = str(packet.get('summary', '') or '').strip()
    if decision or summary:
        if summary:
            lines.append('decision: {0} - {1}'.format(_style_decision_value(decision or 'go'), summary))
        else:
            lines.append('decision: {0}'.format(_style_decision_value(decision)))

    entries = packet.get('selector_entries', []) if isinstance(packet.get('selector_entries', []), list) else []
    authority = 'canonical DS run/report spine'
    if action == 'ds-saved-baselines':
        authority = 'source/mode baseline-analysis evidence index'
    elif action == 'ds-saved-drafts':
        authority = 'canonical wizard draft slot root'

    scope_text = ''
    if action == 'ds-saved-baselines':
        scope_text = '{0} / {1}'.format(str(packet.get('source', 'sim') or 'sim'), str(packet.get('mode', 'watch') or 'watch'))

    summary_rows: List[Tuple[str, str]] = [
        ('Count', str(int(packet.get('count', len(entries)) or 0))),
        ('Authority', authority),
        ('Availability', 'ready' if entries else 'empty'),
    ]
    if scope_text:
        summary_rows.append(('Scope', scope_text))
    _append_human_section(lines, 'Summary', _render_human_kv_rows(summary_rows, indent='  '))

    entry_lines: List[str] = []
    if entries:
        for row in entries:
            if not isinstance(row, dict):
                continue
            if entry_lines:
                entry_lines.append('')
            entry_lines.extend(_render_ds_saved_block(row, include_index=True, indent='  '))
    else:
        entry_lines.append('  No saved selectors are available yet.')
    _append_human_section(lines, 'Selectors', entry_lines)

    artifacts = packet.get('artifacts', {}) if isinstance(packet.get('artifacts', {}), dict) else {}
    evidence_lines: List[str] = []
    evidence_labels = {
        'ds_run_index_jsonl': 'Run ledger',
        'ds_latest_json': 'Latest pointer',
        'evidence_index_jsonl': 'Evidence index',
        'draft_root': 'Draft root',
    }
    for key in ('ds_run_index_jsonl', 'ds_latest_json', 'evidence_index_jsonl', 'draft_root'):
        value = _render_human_path_tail(artifacts.get(key, ''))
        if value:
            evidence_lines.extend(
                _render_human_kv_rows(
                    [(evidence_labels.get(key, key), value)],
                    indent='  ',
                    min_label_width=12,
                    max_label_width=14,
                )
            )
    _append_human_section(lines, 'Evidence', evidence_lines)

    _append_human_section(lines, 'Guidance', ['  {0}'.format(line) for line in _render_ds_saved_guidance_lines(packet)])
    return lines


def _render_ds_generalized_location(value: Any) -> str:
    text = str(value or '').strip().replace('\\', '/')
    if not text:
        return ''
    parts = [part for part in text.split('/') if part]
    if not parts:
        return text
    lowered = [part.lower() for part in parts]
    if 'reports' in lowered:
        start = lowered.index('reports')
        return '/'.join(parts[start:])
    if len(parts) >= 2:
        return '/'.join(parts[-2:])
    return parts[-1]


def _render_ds_report_artifact_pairs(artifacts: Dict[str, Any]) -> List[Tuple[str, str]]:
    report_keys = {
        'run_json',
        'run_md',
        'evaluation_run_json',
        'evaluation_run_md',
        'threshold_report_json',
        'threshold_report_md',
    }
    pairs: List[Tuple[str, str]] = []
    for key in report_keys:
        value = artifacts.get(key)
        text = str(value or '').strip()
        if not text:
            continue
        pairs.append((Path(text).name, _render_ds_generalized_location(text)))
    return sorted(pairs, key=lambda item: item[0])


def _render_ds_human(packet: Dict[str, Any]) -> List[str]:
    wizard_view = packet.get('wizard_view', []) if isinstance(packet.get('wizard_view', []), list) else []
    if str(packet.get('action', '')).strip().lower() == 'ds-wizard' and wizard_view:
        return [str(line) for line in wizard_view]
    lines: List[str] = []
    lines.append(_style_section_title('ObserverCTL DS'))
    lines.append('action: {0}'.format(str(packet.get('action', '') or 'ds')))
    decision = str(packet.get('decision', packet.get('state', '')) or '').strip()
    if decision:
        lines.append('decision: {0}'.format(_style_decision_value(decision)))
    workflow = str(packet.get('wizard_workflow', '') or packet.get('run_mode', '') or '').strip()
    if workflow:
        lines.append('workflow: {0}'.format(workflow))
    summary = str(packet.get('summary', '') or '').strip()
    if summary:
        lines.append('summary: {0}'.format(summary))
    workflow_steps = packet.get('workflow_steps', []) if isinstance(packet.get('workflow_steps', []), list) else []
    if workflow_steps:
        lines.append('steps: {0}'.format(', '.join([str(step) for step in workflow_steps if str(step).strip()])))
    command_preview = str(packet.get('command_preview', '') or '').strip()
    if command_preview:
        lines.append('command: {0}'.format(command_preview))
    validation_issues = packet.get('validation_issues', []) if isinstance(packet.get('validation_issues', []), list) else []
    if validation_issues:
        lines.append(_style_section_line('validation'))
        for issue in validation_issues:
            lines.append('  - {0}'.format(issue))
    report_context = packet.get('report_context', {}) if isinstance(packet.get('report_context', {}), dict) else {}
    if report_context:
        lines.append(_style_section_line('report context'))
        for key in sorted(report_context.keys()):
            value = report_context.get(key)
            if value in ('', None):
                continue
            lines.extend(_render_human_kv_rows([(key, value)], indent='  ', min_label_width=12, max_label_width=18))
    metrics = packet.get('metrics', {}) if isinstance(packet.get('metrics', {}), dict) else {}
    if metrics:
        lines.append(_style_section_line('metrics'))
        for key in sorted(metrics.keys()):
            lines.extend(_render_human_kv_rows([(key, metrics.get(key))], indent='  ', min_label_width=12, max_label_width=18))
    counts = packet.get('counts', {}) if isinstance(packet.get('counts', {}), dict) else {}
    if counts:
        lines.append(_style_section_line('counts'))
        for key in sorted(counts.keys()):
            lines.extend(_render_human_kv_rows([(key, counts.get(key))], indent='  ', min_label_width=12, max_label_width=18))
    error_detail = str(packet.get('error_detail', '') or '').strip()
    if error_detail:
        lines.append('error: {0}'.format(error_detail))
    reason_codes = packet.get('reason_codes', []) if isinstance(packet.get('reason_codes', []), list) else []
    if reason_codes:
        lines.append(_style_section_line('reason codes'))
        for reason in reason_codes:
            lines.append('  {0}'.format(reason))
    artifacts = packet.get('artifacts', {}) if isinstance(packet.get('artifacts', {}), dict) else {}
    if artifacts:
        report_pairs = _render_ds_report_artifact_pairs(artifacts)
        if report_pairs:
            lines.append(_style_section_line('reports created'))
            for filename, location in report_pairs:
                lines.append('  {0} ({1})'.format(filename, location))
        other_pairs: List[Tuple[str, str]] = []
        for key in sorted(artifacts.keys()):
            value = artifacts.get(key)
            if value in (None, '', [], {}):
                continue
            if key in {'run_json', 'run_md', 'evaluation_run_json', 'evaluation_run_md', 'threshold_report_json', 'threshold_report_md'}:
                continue
            other_pairs.append((key, _render_ds_generalized_location(value)))
        if other_pairs:
            lines.append(_style_section_line('outputs'))
            for key, location in other_pairs:
                lines.extend(_render_human_kv_rows([(key, location)], indent='  ', min_label_width=12, max_label_width=18))
    return lines


def _render_human_known_packet(packet: Dict[str, Any]) -> Optional[List[str]]:
    if not isinstance(packet, dict):
        return None
    action = str(packet.get('action', '') or '').strip().lower()
    if action.startswith('ds-saved-'):
        return _render_ds_saved_selectors_human(packet)
    if str(packet.get('command_family', '')).strip().lower() == 'ds':
        return _render_ds_human(packet)
    if action.startswith('librarian-vault-'):
        return _render_librarian_vault_human(packet)
    if action == 'librarian-datasets':
        return _render_librarian_datasets_human(packet)
    if action in ('librarian-dataset-register', 'librarian-dataset-release'):
        return _render_librarian_dataset_action_human(packet)
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

    if bool((packet or {}).get('suppress_human_emit', False)):
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
            'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', [])),
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
            'evidence_refs': _merge_evidence_refs(
                gate.get('evidence_refs', []),
                str(posture_packet.get('posture_state_path', '') or ''),
                str(posture_packet.get('receipt_path', '') or ''),
            ),
        }
    response = {
        'timestamp_utc': _utc_now(),
        'decision': 'go',
        'runtime_cli_surface': 'observerctl',
        'from_state': gate.get('from_state', ''),
        'to_state': '{0}:{1}'.format(state['source'], state['mode']),
        'rollback_anchor': rollback_anchor,
        'posture_packet': posture_packet,
        'readiness_surfaces': gate.get('readiness_surfaces', {}),
        'stage5_prerequisites': gate.get('stage5_prerequisites', {}),
        'evidence_refs': _merge_evidence_refs(
            gate.get('evidence_refs', []),
            str(posture_packet.get('posture_state_path', '') or ''),
            str(posture_packet.get('receipt_path', '') or ''),
        ),
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
            'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', [])),
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
            'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', []), mode_set.get('evidence_refs', [])),
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
            'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', []), mode_set.get('evidence_refs', []), ((evidence.get('process') or {}).get('evidence_refs') or [])),
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
        'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', []), mode_set.get('evidence_refs', []), ((evidence.get('process') or {}).get('evidence_refs') or [])),
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
            'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', [])),
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
            'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', []), mode_set.get('evidence_refs', [])),
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
                'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', []), mode_set.get('evidence_refs', [])),
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
            'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', []), mode_set.get('evidence_refs', [])),
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
        'evidence_refs': _merge_evidence_refs(gate.get('evidence_refs', []), mode_set.get('evidence_refs', []), ((evidence.get('process') or {}).get('evidence_refs') or [])),
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
        index_row = {
            'timestamp_utc': _utc_now(),
            'stream_type': _resource_stream_type(prof),
            'window_id': wid,
            'source': src,
            'mode': m,
            'sampling_profile_id': 'resource_{0}_v1'.format(prof),
            'mode_at_capture': m,
            'source_axis': src,
            'segment_path': p,
            'segment_records': int(count),
            'run_id': linkage.get('run_id', ''),
        }
        if prof == 'baseline':
            index_row['baseline_window_id'] = wid
        _append_jsonl(idx_path, index_row)

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
    latest_baseline_window_id = ''
    for row in reversed(rows):
        if not _resource_profile_matches(row.get('stream_type', ''), 'baseline'):
            continue
        latest_baseline_window_id = str(row.get('baseline_window_id') or row.get('window_id') or '').strip()
        if latest_baseline_window_id:
            break

    baseline_index_rows = _load_resource_index_rows(src, m, stream_type='resource_baseline', baseline_window_id=latest_baseline_window_id) if latest_baseline_window_id else []
    manifest_path = _resource_archive_dir() / 'manifest.json'
    manifest_payload = _load_json_file(manifest_path, {}) if manifest_path.exists() else {}
    baseline_segment_rows = [_resolve_resource_segment(str(row.get('segment_path', '') or ''), manifest_payload) for row in baseline_index_rows]
    baseline_segment_resolution = _summarize_segment_resolutions(baseline_segment_rows)
    baseline_window_evidence_refs: List[str] = [str(_resource_index_path(src, m)).replace('\\', '/')]
    if manifest_path.exists():
        baseline_window_evidence_refs.append(str(manifest_path).replace('\\', '/'))
    for row in baseline_segment_rows:
        resolved_ref = str(row.get('resolved_segment_path', '') or '').strip()
        raw_ref = str(row.get('segment_path', '') or '').strip()
        if resolved_ref and resolved_ref not in baseline_window_evidence_refs:
            baseline_window_evidence_refs.append(resolved_ref)
        elif raw_ref and raw_ref not in baseline_window_evidence_refs:
            baseline_window_evidence_refs.append(raw_ref)

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
        'baseline_window_id': latest_baseline_window_id,
        'baseline_window_segment_count': int(len(baseline_segment_rows)),
        'baseline_window_segment_resolution': baseline_segment_resolution,
        'baseline_window_segment_paths': [str(row.get('segment_path', '') or '').strip() for row in baseline_index_rows if str(row.get('segment_path', '') or '').strip()],
        'baseline_window_resolved_segment_paths': [str(row.get('resolved_segment_path', '') or '').strip() for row in baseline_segment_rows if str(row.get('resolved_segment_path', '') or '').strip()],
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
                'resource_index': str(_resource_index_path(src, m)).replace('\\', '/'),
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
            'evidence_refs': [str(_resource_archive_dir()).replace('\\', '/')] + baseline_window_evidence_refs,
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


def _librarian_datasets() -> Dict[str, Any]:
    from calamum_librarian import list_librarian_datasets_packet

    return list_librarian_datasets_packet(_project_anchor())


def _librarian_dataset_register(dataset_manifest: str, access_class: str, display_name: str, run_id: str) -> Dict[str, Any]:
    from calamum_librarian import register_librarian_dataset_packet

    return register_librarian_dataset_packet(
        _project_anchor(),
        Path(str(dataset_manifest or '').strip()),
        access_class=str(access_class or '').strip(),
        display_name=str(display_name or '').strip(),
        run_id=str(run_id or '').strip(),
    )


def _librarian_dataset_release(dataset: str, requester_id: str, requested_action: str) -> Dict[str, Any]:
    from calamum_librarian import release_librarian_dataset_packet

    return release_librarian_dataset_packet(
        _project_anchor(),
        str(dataset or '').strip(),
        requester_id=str(requester_id or 'observerctl').strip() or 'observerctl',
        requested_action=str(requested_action or 'hydrate-dataset').strip() or 'hydrate-dataset',
    )


def _librarian_vault_status() -> Dict[str, Any]:
    from calamum_librarian import librarian_vault_status_packet

    return librarian_vault_status_packet(_project_anchor())


def _librarian_vault_verify() -> Dict[str, Any]:
    from calamum_librarian import librarian_vault_verify_packet

    return librarian_vault_verify_packet(_project_anchor())


def _librarian_vault_lock(reason: str) -> Dict[str, Any]:
    from calamum_librarian import librarian_vault_lock_packet

    return librarian_vault_lock_packet(_project_anchor(), reason=str(reason or '').strip())


def _librarian_vault_unlock(reason: str) -> Dict[str, Any]:
    from calamum_librarian import librarian_vault_unlock_packet

    return librarian_vault_unlock_packet(_project_anchor(), reason=str(reason or '').strip())


def _librarian_vault_rebaseline(reason: str) -> Dict[str, Any]:
    from calamum_librarian import librarian_vault_rebaseline_packet

    return librarian_vault_rebaseline_packet(_project_anchor(), reason=str(reason or '').strip())


def _ds_saved_manifest_records() -> List[Dict[str, Any]]:
    from analysis.report_aggregate import load_ds_run_manifest_records

    return load_ds_run_manifest_records(project_anchor=_project_anchor())


def _ds_selector_sort_entries(entries: List[Dict[str, Any]], reverse: bool = True) -> List[Dict[str, Any]]:
    return sorted(
        [entry for entry in entries if isinstance(entry, dict)],
        key=lambda entry: (
            str(entry.get('recorded_at_utc', '')),
            str(entry.get('selector_token', '') or entry.get('entry_id', '')),
        ),
        reverse=bool(reverse),
    )


def _ds_assign_selector_indexes(entries: List[Dict[str, Any]], preserve_existing: bool = False) -> List[Dict[str, Any]]:
    assigned: List[Dict[str, Any]] = []
    next_index = 1
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        row = dict(entry)
        existing_index = int(row.get('index', 0) or 0)
        if preserve_existing and existing_index > 0:
            row['index'] = existing_index
        else:
            row['index'] = next_index
        assigned.append(row)
        next_index += 1
    return assigned


def _ds_selector_entry_view(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {str(key): value for key, value in entry.items() if str(key) != 'resolver'}


def _ds_resolve_selector_entry(entries: List[Dict[str, Any]], selector: str) -> Dict[str, Any]:
    token = str(selector or '').strip()
    if not token:
        return {'status': 'missing'}

    if token.isdigit():
        idx = int(token)
        matches = [entry for entry in entries if int(entry.get('index', 0) or 0) == idx]
        if len(matches) == 1:
            return {'status': 'ok', 'entry': dict(matches[0])}
        return {'status': 'missing'}

    lowered = token.lower()
    matches: List[Dict[str, Any]] = []
    for entry in entries:
        candidates = {
            str(entry.get('entry_id', '') or '').strip().lower(),
            str(entry.get('selector_token', '') or '').strip().lower(),
            str(entry.get('display_name', '') or '').strip().lower(),
            str(entry.get('run_id', '') or '').strip().lower(),
            str(entry.get('display_alias', '') or '').strip().lower(),
        }
        candidates = {candidate for candidate in candidates if candidate}
        if lowered in candidates:
            matches.append(dict(entry))

    if len(matches) == 1:
        return {'status': 'ok', 'entry': matches[0]}
    if len(matches) > 1:
        return {
            'status': 'ambiguous',
            'matches': [_ds_selector_entry_view(entry) for entry in matches],
        }
    return {'status': 'missing'}


def _ds_saved_summary_fallback(workflow: str, run_id: str, summary: str) -> str:
    text = str(summary or '').strip()
    if text:
        return text
    if str(run_id or '').strip():
        return str(run_id or '').strip()
    if str(workflow or '').strip():
        return str(workflow or '').strip()
    return 'saved-selector'


def _ds_model_variant_token(run_id: str, variant: str, fallback: str) -> str:
    base = str(run_id or '').strip()
    suffix = str(variant or '').strip().lower()
    if base and suffix:
        return '{0}:{1}'.format(base, suffix)
    if base:
        return base
    return str(fallback or '').strip()


def _generate_short_alias(run_id: str) -> str:
    raw = str(run_id or '').strip()
    if not raw:
        return ''
    if '_' in raw:
        parts = raw.split('_')
        if len(parts[-1]) >= 8 and any(c.isdigit() for c in parts[-1]):
            return parts[-1]
    if '-' in raw and len(raw.split('-')[-1]) >= 8:
        return raw.split('-')[-1]
    if len(raw) > 12:
        return raw[:8]
    return raw


def _ds_saved_train_entries() -> List[Dict[str, Any]]:
    from analysis._util import sanitize_run_id

    entries: List[Dict[str, Any]] = []
    for record in _ds_saved_manifest_records():
        manifest = dict(record.get('manifest_payload', {}) or {}) if isinstance(record.get('manifest_payload', {}), dict) else {}
        if not manifest:
            continue

        artifacts = dict(manifest.get('artifacts', {}) or {}) if isinstance(manifest.get('artifacts', {}), dict) else {}
        result = dict(manifest.get('result', {}) or {}) if isinstance(manifest.get('result', {}), dict) else {}
        lineage = dict(manifest.get('lineage', {}) or {}) if isinstance(manifest.get('lineage', {}), dict) else {}
        context = dict(manifest.get('context', {}) or {}) if isinstance(manifest.get('context', {}), dict) else {}

        workflow = str(manifest.get('workflow', '') or '').strip() or str(((record.get('entry', {}) if isinstance(record.get('entry', {}), dict) else {}).get('workflow', '')) or '').strip()
        run_id = str(manifest.get('run_id', '') or '').strip() or str(((record.get('entry', {}) if isinstance(record.get('entry', {}), dict) else {}).get('run_id', '')) or '').strip()
        recorded_at_utc = str(manifest.get('timestamp_utc', '') or '').strip() or str(((record.get('entry', {}) if isinstance(record.get('entry', {}), dict) else {}).get('timestamp_utc', '')) or '').strip()
        summary = _ds_saved_summary_fallback(workflow, run_id, str(manifest.get('summary', '') or ''))
        report_manifest_path = str(record.get('manifest_path', '') or '').strip()

        variants: List[Tuple[str, str, str, str]] = [
            ('', 'train_manifest', 'model_path', str(result.get('model_type', '') or '').strip()),
            ('supervised', 'supervised_train_manifest', 'supervised_model_path', 'supervised'),
            ('unsupervised', 'unsupervised_train_manifest', 'unsupervised_model_path', 'unsupervised'),
        ]

        for variant_key, train_key, model_key, model_hint in variants:
            train_ref = str(artifacts.get(train_key, '') or '').strip()
            model_ref = str(artifacts.get(model_key, '') or '').strip()
            if not train_ref and not model_ref:
                continue

            train_path = _resolve_existing_project_path(train_ref) if train_ref else None
            model_path = _resolve_existing_project_path(model_ref) if model_ref else None
            train_manifest_payload = _load_json_file(train_path, {}) if train_path is not None else {}

            dataset_manifest_ref = str(
                train_manifest_payload.get('dataset_manifest_path', '')
                or lineage.get('dataset_manifest', '')
                or artifacts.get('dataset_manifest', '')
                or ''
            ).strip()
            model_type = str(train_manifest_payload.get('model_type', '') or model_hint or '').strip() or 'trained'

            readiness_issues: List[str] = []
            if train_path is None:
                readiness_issues.append('missing_train_manifest')
            if model_path is None:
                readiness_issues.append('missing_model_artifact')

            selector_token = _ds_model_variant_token(run_id, variant_key, summary)
            display_base = _ds_saved_summary_fallback(workflow, run_id, summary)
            display_name = '{0} ({1})'.format(display_base, model_type) if str(variant_key or '').strip() else display_base
            entry_id = 'saved-train-{0}'.format(sanitize_run_id(selector_token or display_name or workflow) or 'train')
            source = str(context.get('source', '') or '').strip()
            mode = str(context.get('mode', '') or '').strip()

            entries.append(
                {
                    'family': 'train-model',
                    'entry_id': entry_id,
                    'selector_token': selector_token,
                    'display_name': display_name,
                    'recorded_at_utc': recorded_at_utc,
                    'workflow': workflow,
                    'run_id': run_id,
                    'display_alias': _generate_short_alias(run_id),
                    'model_type': model_type,
                    'status': 'approved' if len(readiness_issues) == 0 else 'held',
                    'readiness': 'ready' if len(readiness_issues) == 0 else 'artifact-missing',
                    'summary': summary,
                    'source': source,
                    'mode': mode,
                    'resolver': {
                        'report_manifest_path': report_manifest_path,
                        'train_manifest_path': train_ref,
                        'model_path': model_ref,
                        'dataset_manifest_path': dataset_manifest_ref,
                    },
                }
            )

    return _ds_assign_selector_indexes(_ds_selector_sort_entries(entries))


def _ds_saved_run_entries() -> List[Dict[str, Any]]:
    from analysis._util import sanitize_run_id

    entries: List[Dict[str, Any]] = []
    for record in _ds_saved_manifest_records():
        manifest = dict(record.get('manifest_payload', {}) or {}) if isinstance(record.get('manifest_payload', {}), dict) else {}
        if not manifest:
            continue

        artifacts = dict(manifest.get('artifacts', {}) or {}) if isinstance(manifest.get('artifacts', {}), dict) else {}
        context = dict(manifest.get('context', {}) or {}) if isinstance(manifest.get('context', {}), dict) else {}
        workflow = str(manifest.get('workflow', '') or '').strip() or str(((record.get('entry', {}) if isinstance(record.get('entry', {}), dict) else {}).get('workflow', '')) or '').strip()
        run_id = str(manifest.get('run_id', '') or '').strip() or str(((record.get('entry', {}) if isinstance(record.get('entry', {}), dict) else {}).get('run_id', '')) or '').strip()
        recorded_at_utc = str(manifest.get('timestamp_utc', '') or '').strip() or str(((record.get('entry', {}) if isinstance(record.get('entry', {}), dict) else {}).get('timestamp_utc', '')) or '').strip()
        summary = _ds_saved_summary_fallback(workflow, run_id, str(manifest.get('summary', '') or ''))
        run_json_ref = str(artifacts.get('run_json', '') or artifacts.get('evaluation_run_json', '') or '').strip()
        if not run_json_ref:
            continue

        run_json_path = _resolve_existing_project_path(run_json_ref)
        run_payload = _load_json_file(run_json_path, {}) if run_json_path is not None else {}
        identity = dict(run_payload.get('identity', {}) or {}) if isinstance(run_payload.get('identity', {}), dict) else {}
        constraints = dict(((run_payload.get('context', {}) if isinstance(run_payload.get('context', {}), dict) else {}).get('constraints', {})) or {})
        selector_token = str(run_id or identity.get('run_id', '') or summary).strip()
        entry_id = 'saved-run-{0}'.format(sanitize_run_id(selector_token or workflow) or 'run')
        max_fpr_value = constraints.get('max_fpr', context.get('max_fpr', ''))
        baseline_window_id = str(context.get('baseline_window_id', '') or '').strip()

        entries.append(
            {
                'family': 'run-context',
                'entry_id': entry_id,
                'selector_token': selector_token,
                'display_name': _ds_saved_summary_fallback(workflow, selector_token, summary),
                'display_alias': _generate_short_alias(run_id),
                'display_alias': _generate_short_alias(run_id),
                'recorded_at_utc': recorded_at_utc,
                'workflow': workflow,
                'run_id': selector_token,
                'status': 'approved' if run_json_path is not None else 'held',
                'readiness': 'ready' if run_json_path is not None else 'artifact-missing',
                'summary': summary,
                'max_fpr': max_fpr_value,
                'baseline_window_id': baseline_window_id,
                'resolver': {
                    'report_manifest_path': str(record.get('manifest_path', '') or '').strip(),
                    'run_json_path': run_json_ref,
                },
            }
        )

    return _ds_assign_selector_indexes(_ds_selector_sort_entries(entries))


def _ds_saved_baseline_entries(source: str, mode: str) -> List[Dict[str, Any]]:
    from analysis._util import sanitize_run_id

    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'

    index_path = _evidence_index_path(src, m)
    if not index_path.exists():
        return []

    seen: set = set()
    entries: List[Dict[str, Any]] = []
    for line in reversed(index_path.read_text(encoding='utf-8').splitlines()):
        text = str(line or '').strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        if str(row.get('event', '') or '').strip().lower() != 'baseline_analysis':
            continue

        packet_ref = str(row.get('packet_path', '') or '').strip()
        packet_path = _resolve_existing_project_path(packet_ref) if packet_ref else None
        packet = _load_json_file(packet_path, {}) if packet_path is not None else {}
        recorded_at_utc = str(packet.get('timestamp_utc', '') or '').strip() or str(row.get('timestamp_utc', '') or '').strip()
        baseline_window_id = str(packet.get('baseline_window_id', '') or row.get('baseline_window_id', '') or '').strip()
        selector_token = baseline_window_id or 'baseline-{0}'.format(_utc_compact_stamp())
        entry_id = 'saved-baseline-{0}'.format(sanitize_run_id(selector_token or recorded_at_utc) or 'baseline')
        if entry_id in seen:
            continue
        seen.add(entry_id)

        decision = str(packet.get('decision', row.get('decision', 'no-go')) or 'no-go').strip().lower()
        readiness = 'ready' if packet_path is not None and decision == 'go' else 'artifact-missing'
        counts = dict(packet.get('sample_counts', {}) or {}) if isinstance(packet.get('sample_counts', {}), dict) else {}
        entries.append(
            {
                'family': 'baseline-context',
                'entry_id': entry_id,
                'selector_token': selector_token,
                'display_name': baseline_window_id or str(packet.get('summary', '') or selector_token or 'baseline-analysis').strip(),
                'display_alias': _generate_short_alias(selector_token),
                'recorded_at_utc': recorded_at_utc,
                'workflow': 'baseline-analysis',
                'run_id': '',
                'status': 'approved' if readiness == 'ready' else 'held',
                'readiness': readiness,
                'summary': str(packet.get('summary', '') or 'Retained baseline analysis packet.').strip(),
                'source': src,
                'mode': m,
                'decision_state': decision,
                'baseline_window_id': baseline_window_id,
                'sample_counts': counts,
                'resolver': {
                    'baseline_analysis_packet': packet_ref,
                    'evidence_index_path': str(index_path).replace('\\', '/'),
                },
            }
        )

    return _ds_assign_selector_indexes(_ds_selector_sort_entries(entries))


def _ds_wizard_draft_root() -> Path:
    from analysis._util import ds_drafts_dir

    root = ds_drafts_dir(Path(__file__)) / 'wizard'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ds_wizard_draft_slot_id(path: Path) -> int:
    stem = str(path.stem or '').strip().lower()
    if stem.startswith('slot-') and stem[5:].isdigit():
        return int(stem[5:])
    return 0


def _ds_wizard_draft_slot_label(slot_id: int) -> str:
    return 'slot-{0:03d}'.format(max(1, int(slot_id or 1)))


def _ds_wizard_draft_slot_path(slot_id: int) -> Path:
    return _ds_wizard_draft_root() / '{0}.json'.format(_ds_wizard_draft_slot_label(slot_id))


def _ds_wizard_parse_slot_token(token: str) -> int:
    text = str(token or '').strip().lower()
    if text.isdigit():
        return int(text)
    if text.startswith('slot-') and text[5:].isdigit():
        return int(text[5:])
    return 0


def _ds_wizard_draft_entries() -> List[Dict[str, Any]]:
    root = _ds_wizard_draft_root()
    paths = sorted(root.glob('slot-*.json'), key=_ds_wizard_draft_slot_id)
    entries: List[Dict[str, Any]] = []
    for path in paths:
        slot_id = _ds_wizard_draft_slot_id(path)
        payload = _load_json_file(path, {})
        workflow = str(payload.get('workflow', '') or '').strip()
        source = _normalize_source(str(payload.get('source', 'sim') or 'sim'))
        mode = str(payload.get('mode', 'watch') or 'watch').strip().lower()
        if mode not in MODES:
            mode = 'watch'
        run_id = ''
        readiness = 'invalid'
        status = 'held'
        try:
            state = _ds_wizard_load_draft(path)
            readiness = _ds_wizard_decision_state(state)
            status = 'saved'
            run_id = str(state.values.get('run_id', '') or '').strip()
        except Exception:
            values = payload.get('values', {}) if isinstance(payload.get('values', {}), dict) else {}
            run_id = str(values.get('run_id', '') or '').strip()

        entries.append(
            {
                'family': 'wizard-draft',
                'index': int(slot_id or 0),
                'slot_id': int(slot_id or 0),
                'entry_id': _ds_wizard_draft_slot_label(slot_id),
                'selector_token': _ds_wizard_draft_slot_label(slot_id),
                'display_name': _ds_wizard_draft_slot_label(slot_id),
                'recorded_at_utc': str(payload.get('saved_at_utc', '') or '').strip(),
                'workflow': workflow or 'unset',
                'run_id': run_id,
                'status': status,
                'readiness': readiness,
                'source': source,
                'mode': mode,
                'summary': 'Wizard draft slot',
                'resolver': {
                    'draft_path': str(path).replace('\\', '/'),
                },
            }
        )
    return _ds_assign_selector_indexes(entries, preserve_existing=True)


def _ds_wizard_next_draft_slot_id(entries: Optional[List[Dict[str, Any]]] = None) -> int:
    current = entries if isinstance(entries, list) else _ds_wizard_draft_entries()
    used = {int(entry.get('slot_id', 0) or 0) for entry in current if int(entry.get('slot_id', 0) or 0) > 0}
    slot_id = 1
    while slot_id in used:
        slot_id += 1
    return slot_id


def _ds_wizard_current_draft_slot_id(state: _DSWizardState) -> int:
    draft_path = str(state.draft_path or '').strip()
    if not draft_path:
        return 0
    path = Path(draft_path)
    try:
        resolved = path.resolve()
    except Exception:
        resolved = path
    root = _ds_wizard_draft_root()
    try:
        resolved.relative_to(root)
    except Exception:
        return 0
    return _ds_wizard_draft_slot_id(resolved)


def _ds_train_selectors() -> Dict[str, Any]:
    from analysis._util import ds_indexes_dir, normalize_repo_or_absolute_path

    entries = _ds_saved_train_entries()
    project_root = _project_root()
    indexes_dir = ds_indexes_dir(Path(__file__))
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-saved-trained',
        'command_family': 'ds',
        'command_path': 'observerctl ds saved trained',
        'family': 'train-model',
        'summary': 'Retained train/model selector surface ready.' if entries else 'No saved train/model selectors are available yet.',
        'count': int(len(entries)),
        'selector_entries': [_ds_selector_entry_view(entry) for entry in entries],
        'artifacts': {
            'ds_run_index_jsonl': normalize_repo_or_absolute_path(indexes_dir / 'ds_run_index.jsonl', project_root),
            'ds_latest_json': normalize_repo_or_absolute_path(indexes_dir / 'ds_latest.json', project_root),
        },
        'reason_codes': [],
    }


def _ds_run_selectors() -> Dict[str, Any]:
    from analysis._util import ds_indexes_dir, normalize_repo_or_absolute_path

    entries = _ds_saved_run_entries()
    project_root = _project_root()
    indexes_dir = ds_indexes_dir(Path(__file__))
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-saved-runs',
        'command_family': 'ds',
        'command_path': 'observerctl ds saved runs',
        'family': 'run-context',
        'summary': 'Retained run-context selector surface ready.' if entries else 'No saved run-context selectors are available yet.',
        'count': int(len(entries)),
        'selector_entries': [_ds_selector_entry_view(entry) for entry in entries],
        'artifacts': {
            'ds_run_index_jsonl': normalize_repo_or_absolute_path(indexes_dir / 'ds_run_index.jsonl', project_root),
            'ds_latest_json': normalize_repo_or_absolute_path(indexes_dir / 'ds_latest.json', project_root),
        },
        'reason_codes': [],
    }


def _ds_baseline_selectors(source: str, mode: str) -> Dict[str, Any]:
    entries = _ds_saved_baseline_entries(source, mode)
    src = _normalize_source(source)
    m = str(mode or 'watch').strip().lower()
    if m not in MODES:
        m = 'watch'
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-saved-baselines',
        'command_family': 'ds',
        'command_path': 'observerctl ds saved baselines',
        'family': 'baseline-context',
        'source': src,
        'mode': m,
        'summary': 'Retained baseline-context selector surface ready.' if entries else 'No saved baseline-context selectors are available for the current source/mode.',
        'count': int(len(entries)),
        'selector_entries': [_ds_selector_entry_view(entry) for entry in entries],
        'artifacts': {
            'evidence_index_jsonl': str(_evidence_index_path(src, m)).replace('\\', '/'),
        },
        'reason_codes': [],
    }


def _ds_draft_slots() -> Dict[str, Any]:
    entries = _ds_wizard_draft_entries()
    root = _ds_wizard_draft_root()
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-saved-drafts',
        'command_family': 'ds',
        'command_path': 'observerctl ds saved drafts',
        'family': 'wizard-draft',
        'summary': 'Canonical wizard draft slots ready.' if entries else 'No canonical wizard draft slots are available yet.',
        'count': int(len(entries)),
        'selector_entries': [_ds_selector_entry_view(entry) for entry in entries],
        'artifacts': {
            'draft_root': str(root).replace('\\', '/'),
        },
        'reason_codes': [],
    }


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


_DS_WIZARD_WORKFLOWS = (
    'build',
    'train',
    'evaluate',
    'score',
    'run-demo',
    'run-pipeline',
)
_DS_WIZARD_SECTION_ORDER = ('flow', 'in', 'model', 'eval', 'report', 'cmd', 'check', 'run', 'exit')
_DS_WIZARD_WORKFLOW_SECTIONS: Dict[str, Tuple[str, ...]] = {
    'build':        ('flow', 'in', 'model', 'report', 'cmd', 'check', 'run', 'exit'),
    'train':        ('flow', 'model', 'report', 'cmd', 'check', 'run', 'exit'),
    'evaluate':     ('flow', 'model', 'eval', 'report', 'cmd', 'check', 'run', 'exit'),
    'score':        ('flow', 'model', 'report', 'cmd', 'check', 'run', 'exit'),
    'run-demo':     ('flow', 'in', 'model', 'eval', 'report', 'cmd', 'check', 'run', 'exit'),
    'run-pipeline': ('flow', 'in', 'model', 'eval', 'report', 'cmd', 'check', 'run', 'exit'),
}
_DS_WIZARD_LANDING_CHOICES: Tuple[Tuple[str, str], ...] = (
    ('configure', 'guided workflow and configuration'),
    ('review-run', 'validation, command preview, and execution'),
    ('command', 'preview the command and use save/load/hydrate helper commands'),
    ('exit', 'leave wizard'),
)


@dataclass(frozen=True)
class _DSWizardFieldSpec:
    key: str
    section: str
    workflows: Tuple[str, ...]
    required_in: Tuple[str, ...] = ()
    flag: str = ''
    value_kind: str = 'text'
    path_kind: str = ''
    accepts_multiple: bool = False
    default: Any = None
    choices: Tuple[str, ...] = ()
    description: str = ''
    artifact_source: str = ''


@dataclass
class _DSWizardState:
    workflow: str = ''
    active_page: str = 'landing'
    active_group: str = ''
    active_section: str = 'flow'
    values: Dict[str, Any] = field(default_factory=dict)
    source: str = 'sim'
    mode: str = 'watch'
    hydrated_from: Dict[str, str] = field(default_factory=dict)
    run_ledger_path: str = ''
    draft_path: str = ''
    last_action: str = ''
    validation_issues: List[str] = field(default_factory=list)
    transient_view: str = ''
    transient_target: str = ''


@dataclass(frozen=True)
class _DSWizardMenuItem:
    item_type: str
    target: str
    label: str
    status: str = ''
    current: str = ''
    detail: str = ''


_DS_WIZARD_DRAFT_VERSION = 1
_DS_RUNTIME_STATE_WIZARD = 'wizard-available'
_DS_RUNTIME_STATE_COMMAND = 'command-available'
_DS_RUNTIME_STATE_AUTOMATION = 'automation-available'
_DS_RUNTIME_STATE_PLANNED = 'surface-planned'
_DS_WIZARD_POWER_ONLY_KEYS = ('out_dir', 'scores_out')
_DS_WIZARD_ADVANCED_EDIT_KEYS = ('run_id', 'out_dir', 'scores_out')
_DS_WIZARD_ADVANCED_ROUTE_KEYS = ('source', 'mode', 'run_id', 'out_dir', 'scores_out')
_DS_WIZARD_AUTO_DRAFT_TOKEN = '__auto-slot__'
_DS_WIZARD_SPLIT_KEYS = ('split_train', 'split_val', 'split_test')
_DS_WIZARD_ENUM_PICKERS: Dict[str, Tuple[str, ...]] = {
    'source': ('sim', 'real'),
    'mode': MODES,
    'model_type': ('supervised', 'unsupervised'),
}


_DS_WIZARD_FIELD_SPECS: Tuple[_DSWizardFieldSpec, ...] = (
    _DSWizardFieldSpec('workflow', 'flow', _DS_WIZARD_WORKFLOWS, required_in=_DS_WIZARD_WORKFLOWS, description='Workflow preset'),
    _DSWizardFieldSpec('source', 'in', _DS_WIZARD_WORKFLOWS, default='sim', choices=('sim', 'real'), description='Observer source axis', artifact_source='latest_context'),
    _DSWizardFieldSpec('mode', 'in', _DS_WIZARD_WORKFLOWS, default='watch', choices=MODES, description='Observer mode', artifact_source='latest_context'),
    _DSWizardFieldSpec('input_paths', 'in', ('build', 'run-pipeline'), required_in=('build', 'run-pipeline'), flag='--input', value_kind='path-list', path_kind='file', accepts_multiple=True, description='Telemetry JSONL inputs'),
    _DSWizardFieldSpec('dataset_manifest', 'in', ('train', 'score', 'evaluate', 'run-pipeline', 'build'), required_in=('train', 'score'), flag='--dataset', value_kind='path', path_kind='file', description='Dataset manifest path', artifact_source='dataset_manifest'),
    _DSWizardFieldSpec('features_csv', 'in', ('evaluate',), required_in=('evaluate',), flag='--features-csv', value_kind='path', path_kind='file', description='Features CSV path', artifact_source='dataset_manifest'),
    _DSWizardFieldSpec('labels_csv', 'in', ('evaluate',), flag='--labels-csv', value_kind='path', path_kind='file', description='Labels CSV path', artifact_source='dataset_manifest'),
    _DSWizardFieldSpec('out_dir', 'report', ('build', 'train', 'evaluate', 'run-demo', 'run-pipeline'), flag='--out-dir', value_kind='path', path_kind='dir', description='Artifact output directory'),
    _DSWizardFieldSpec('scores_out', 'report', ('score',), flag='--out-file', value_kind='path', path_kind='file-write', description='Scores CSV output path'),
    _DSWizardFieldSpec('model_type', 'model', ('train', 'run-pipeline'), flag='--model-type', default='supervised', choices=('supervised', 'unsupervised'), description='Model family', artifact_source='train_manifest'),
    _DSWizardFieldSpec('seed', 'model', ('build', 'train', 'run-pipeline'), flag='--seed', default=42, value_kind='int', description='Deterministic seed'),
    _DSWizardFieldSpec('dataset_seed', 'model', ('run-demo',), flag='--dataset-seed', default=123, value_kind='int', description='Demo dataset seed'),
    _DSWizardFieldSpec('model_seed', 'model', ('run-demo',), flag='--model-seed', default=42, value_kind='int', description='Demo model seed'),
    _DSWizardFieldSpec('split_train', 'model', ('build', 'run-pipeline'), flag='--split-train', default=0.70, value_kind='float', description='Train split'),
    _DSWizardFieldSpec('split_val', 'model', ('build', 'run-pipeline'), flag='--split-val', default=0.15, value_kind='float', description='Validation split'),
    _DSWizardFieldSpec('split_test', 'model', ('build', 'run-pipeline'), flag='--split-test', default=0.15, value_kind='float', description='Test split'),
    _DSWizardFieldSpec('model_path', 'model', ('evaluate', 'score'), required_in=('score',), flag='--model', value_kind='path', path_kind='file', description='Model path', artifact_source='train_manifest'),
    _DSWizardFieldSpec('train_manifest', 'model', ('score',), value_kind='path', path_kind='file', description='Train manifest path', artifact_source='train_manifest'),
    _DSWizardFieldSpec('max_fpr', 'eval', ('evaluate', 'run-demo', 'run-pipeline'), flag='--max-fpr', default=0.01, value_kind='float', description='Maximum false-positive rate'),
    _DSWizardFieldSpec('run_id', 'model', ('evaluate',), flag='--run-id', value_kind='text', description='Optional name for the evaluation report that will be written'),
    _DSWizardFieldSpec('baseline_analysis_packet', 'model', ('evaluate', 'run-pipeline', 'run-demo'), value_kind='path', path_kind='file', description='Optional baseline packet to cite in generated reports', artifact_source='baseline_analysis'),
    _DSWizardFieldSpec('baseline_window_id', 'model', ('evaluate', 'run-pipeline', 'run-demo'), description='Optional baseline window id to include in generated reports', artifact_source='baseline_analysis'),
)


_DS_WIZARD_SECTION_HELP: Dict[str, Dict[str, str]] = {
    'flow': {
        'label': 'workflow and run type',
        'detail': 'Select the data science pipeline routine to execute.',
        'guidance': 'Changing workflows dynamically pares the remaining wizard pages to show only applicable configuration. The active workflow determines whether we require datasets, models, or both.',
    },
    'in': {
        'label': 'inputs and sources',
        'detail': 'Select authorized upstream data telemetry and dataset targets. The wizard rejects raw filesystem paths and strictly uses registered references.',
        'guidance': 'Always begin by binding the primary dataset. Empty diagnostic blocks later in the wizard typically indicate missing dataset context here.',
    },
    'model': {
        'label': 'model family and context',
        'detail': 'Pin the model architecture and structural boundaries. This page binds algorithms and context for reproducible regeneration.',
        'guidance': 'If building or training, select your architecture. If scoring or evaluating, select a previously certified training artifact.',
    },
    'eval': {
        'label': 'evaluation guards',
        'detail': 'Define the mechanical validation thresholds, such as false positive rates or bounds. Pipelines failing these assertions will halt.',
        'guidance': 'These are hard operational stops. Edit values explicitly by number or use "set <field> <value>".',
    },
    'report': {
        'label': 'artifact targeting',
        'detail': 'Preview the canonical output locations the system will generate. Predictable run logs guarantee safety against production bounds.',
        'guidance': 'This is a read-first view. Overrides should be done securely using direct CLI parameter injection, not guided flow.',
    },
    'cmd': {
        'label': 'execution preview',
        'detail': 'Inspect the raw non-interactive CLI equivalent compiled by your current choices.',
        'guidance': 'Review the flags for unexpected telemetry injections. Before execution, verify you understand why each flag exists.',
    },
    'check': {
        'label': 'validation blockers',
        'detail': 'Review readiness against invariant schema rules before submission.',
        'guidance': 'If blockers remain, type "validate" after making fixes to force a rescan, or "open <section-name>" to navigate directly to the missing parameters.',
    },
    'run': {
        'label': 'workflow dispatch',
        'detail': 'Dispatch the pipeline. Execution yields real artifacts against the active system target.',
        'guidance': 'Execution remains blocked until the validation page clears. When unblocked, type "execute" to launch the payload.',
    },
    'exit': {
        'label': 'leave wizard',
        'detail': 'Terminate the interactive session without triggering any further validations.',
        'guidance': 'State is transient; any un-drafted progress is lost upon exit.',
    },
}


def _ds_wizard_field_map() -> Dict[str, _DSWizardFieldSpec]:
    return {spec.key: spec for spec in _DS_WIZARD_FIELD_SPECS}


def _ds_wizard_default_workflow() -> str:
    return _DS_WIZARD_WORKFLOWS[0]


def _ds_wizard_default_values() -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for spec in _DS_WIZARD_FIELD_SPECS:
        if spec.accepts_multiple:
            values[spec.key] = []
        elif spec.default is not None:
            values[spec.key] = spec.default
        else:
            values[spec.key] = ''
    return values


def _ds_wizard_new_state(workflow: str = '') -> _DSWizardState:
    ssot = _load_state()
    selected_workflow = str(workflow or '').strip()
    if selected_workflow not in _DS_WIZARD_WORKFLOWS:
        selected_workflow = _ds_wizard_default_workflow()
    state = _DSWizardState(
        workflow=selected_workflow,
        active_page='landing',
        active_group='',
        active_section='flow',
        values=_ds_wizard_default_values(),
        source=str(ssot.get('source', 'sim')),
        mode=str(ssot.get('mode', 'watch')),
    )
    state.values['source'] = state.source
    state.values['mode'] = state.mode
    state.values['workflow'] = state.workflow
    return state


def _ds_wizard_workflow_label(workflow: str) -> str:
    return str(workflow or '').strip() or 'unset'


def _ds_wizard_page_for_section(section: str) -> str:
    token = str(section or '').strip().lower()
    if token == 'flow':
        return 'configure'
    if token in ('in', 'model', 'eval', 'report'):
        return 'configure'
    if token == 'cmd':
        return 'utilities'
    if token in ('check', 'run'):
        return 'review-run'
    return 'landing'


def _ds_wizard_group_for_section(section: str) -> str:
    token = str(section or '').strip().lower()
    if token == 'in':
        return 'data'
    if token == 'model':
        return 'model'
    if token in ('eval', 'report'):
        return 'eval-report'
    return ''


def _ds_wizard_sync_page_from_section(state: _DSWizardState) -> _DSWizardState:
    state.active_page = _ds_wizard_page_for_section(state.active_section)
    state.active_group = _ds_wizard_group_for_section(state.active_section)
    return state


def _ds_wizard_open_landing(state: _DSWizardState) -> _DSWizardState:
    state.active_page = 'landing'
    state.active_group = ''
    state.last_action = 'page:landing'
    state.transient_view = ''
    state.transient_target = ''
    return state


def _ds_wizard_preferred_configure_section(state: _DSWizardState) -> str:
    for section in _ds_wizard_visible_sections(state):
        if section not in ('flow', 'cmd', 'check', 'run', 'exit'):
            return section
    return 'flow'


def _ds_wizard_open_top_level_choice(state: _DSWizardState, choice: str) -> _DSWizardState:
    token = str(choice or '').strip().lower().replace('_', '-').replace(' and ', '-').replace(' ', '-')
    if token in ('landing', 'home'):
        return _ds_wizard_open_landing(state)
    if token == 'configure':
        return _ds_wizard_open_section(state, 'flow')
    if token in ('review', 'review-run', 'review-run-gate'):
        return _ds_wizard_open_section(state, 'check')
    if token in ('command', 'cmd', 'command-preview', 'command-utilities', 'utilities'):
        return _ds_wizard_open_section(state, 'cmd')
    return state


def _ds_wizard_landing_choice_map() -> Dict[str, str]:
    choice_map: Dict[str, str] = {}
    for key, detail in _DS_WIZARD_LANDING_CHOICES:
        choice_map[key] = detail
    choice_map['review'] = choice_map['review-run']
    choice_map['cmd'] = choice_map['command']
    choice_map['command-preview'] = choice_map['command']
    choice_map['command-and-utilities'] = choice_map['command']
    choice_map['utilities'] = choice_map['command']
    return choice_map


def _ds_wizard_visible_sections(state: _DSWizardState) -> List[str]:
    workflow = str(state.workflow or '').strip()
    if workflow in _DS_WIZARD_WORKFLOW_SECTIONS:
        return list(_DS_WIZARD_WORKFLOW_SECTIONS[workflow])
    return list(_DS_WIZARD_SECTION_ORDER)


def _ds_wizard_page_sections(state: _DSWizardState) -> List[str]:
    return [section for section in _ds_wizard_visible_sections(state) if section != 'exit']


def _ds_wizard_current_section(state: _DSWizardState) -> str:
    page_sections = _ds_wizard_page_sections(state)
    if state.active_section in page_sections:
        return state.active_section
    if page_sections:
        return page_sections[0]
    visible = _ds_wizard_visible_sections(state)
    if state.active_section in visible:
        return state.active_section
    return 'flow'


def _ds_wizard_section_display_label(section: str) -> str:
    return str(section or '').strip().lower() or str(section)


def _ds_wizard_action_line(state: _DSWizardState) -> str:
    if state.active_page == 'landing':
        return ''
    return 'actions: prev | ? | next | exit'


def _ds_wizard_fields_for_section(state: _DSWizardState, section: str) -> List[_DSWizardFieldSpec]:
    workflow = str(state.workflow or '').strip()
    fields: List[_DSWizardFieldSpec] = []
    for spec in _DS_WIZARD_FIELD_SPECS:
        if spec.section != section or spec.key == 'workflow':
            continue
        if not workflow or workflow in spec.workflows:
            fields.append(spec)
    return fields


def _ds_wizard_field_value(state: _DSWizardState, key: str) -> Any:
    if key == 'workflow':
        return state.workflow
    return state.values.get(key, '')


def _ds_wizard_has_value(value: Any) -> bool:
    if isinstance(value, list):
        return len(value) > 0
    return str(value or '').strip() != ''


def _ds_wizard_clear_context_display(state: _DSWizardState) -> _DSWizardState:
    state.hydrated_from.pop('context', None)
    return state


def _ds_wizard_context_display_value(state: _DSWizardState) -> str:
    if not str(state.hydrated_from.get('context', '') or '').strip():
        return ''
    return '{0} / {1}'.format(str(state.source or 'sim'), str(state.mode or 'watch'))


def _ds_wizard_apply_context_metadata(
    state: _DSWizardState,
    source: Any,
    mode: Any,
    hydrated_from: str,
) -> _DSWizardState:
    source_token = str(source or '').strip().lower()
    mode_token = str(mode or '').strip().lower()
    updated = False
    if source_token in SOURCES:
        normalized_source = _normalize_source(source_token)
        state.source = normalized_source
        state.values['source'] = normalized_source
        updated = True
    if mode_token in MODES:
        state.mode = mode_token
        state.values['mode'] = mode_token
        updated = True
    if updated and str(hydrated_from or '').strip():
        state.hydrated_from['context'] = str(hydrated_from).strip()
    else:
        _ds_wizard_clear_context_display(state)
    return state


def _ds_wizard_status_token(state: _DSWizardState, spec: _DSWizardFieldSpec) -> str:
    value = _ds_wizard_field_value(state, spec.key)
    if _ds_wizard_has_value(value):
        return 'set'
    if spec.default is not None and spec.key not in ('source', 'mode'):
        return 'default'
    if state.workflow and state.workflow in spec.required_in:
        return 'missing'
    return 'optional'


def _ds_wizard_stringify_value(value: Any) -> str:
    if isinstance(value, list):
        return ', '.join([str(item) for item in value if str(item).strip()]) or '<none>'
    text = str(value or '').strip()
    return text or '<none>'


def _ds_wizard_short_list_summary(values: Any) -> str:
    if not isinstance(values, list):
        return _ds_wizard_short_path(str(values)) if _ds_wizard_has_value(values) else '<none>'
    items = [_ds_wizard_short_path(str(item)) for item in values if str(item).strip()]
    if not items:
        return '<none>'
    if len(items) > 2:
        return ', '.join(items[:2]) + ', ...'
    return ', '.join(items)


def _ds_wizard_render_field_current(state: _DSWizardState, spec: _DSWizardFieldSpec) -> str:
    value = _ds_wizard_field_value(state, spec.key)
    if isinstance(value, list):
        return _ds_wizard_short_list_summary(value) if spec.path_kind else _ds_wizard_stringify_value(value)
    if not _ds_wizard_has_value(value):
        return _ds_wizard_stringify_value(value)
    if spec.path_kind:
        return _ds_wizard_short_path(str(value))
    return _ds_wizard_stringify_value(value)


def _ds_wizard_ui_label(key: str) -> str:
    token = str(key or '').strip().lower()
    return {
        'input_paths': 'telemetry inputs',
        'dataset_manifest': 'dataset',
        'features_csv': 'features',
        'labels_csv': 'labels',
        'out_dir': 'output',
        'scores_out': 'scores file',
        'model_type': 'model family',
        'dataset_seed': 'dataset seed',
        'model_seed': 'model seed',
        'split_train': 'split',
        'split_val': 'validation split',
        'split_test': 'test split',
        'model_path': 'model',
        'train_manifest': 'train manifest',
        'max_fpr': 'max FPR',
        'run_id': 'run ID',
        'baseline_analysis_packet': 'baseline packet',
        'baseline_window_id': 'baseline window',
        'baseline_window': 'baseline window',
        'run_ledger': 'run ledger',
    }.get(token, token.replace('_', ' '))


def _ds_wizard_resolve_field_alias(token: str) -> str:
    normalized = ' '.join(str(token or '').strip().lower().replace('-', ' ').replace('_', ' ').split())
    alias_map = {
        'split': 'split_train',
        'train split': 'split_train',
        'validation split': 'split_val',
        'test split': 'split_test',
        'max fpr': 'max_fpr',
        'run id': 'run_id',
        'baseline window': 'baseline_window_id',
        'model family': 'model_type',
    }
    if normalized in alias_map:
        return alias_map[normalized]
    return normalized.replace(' ', '_')


def _ds_wizard_split_is_relevant(state: _DSWizardState) -> bool:
    return str(state.workflow or '').strip() in ('build', 'run-pipeline')


def _ds_wizard_split_values_present(state: _DSWizardState) -> bool:
    return any(_ds_wizard_has_value(state.values.get(key)) for key in _DS_WIZARD_SPLIT_KEYS)


def _ds_wizard_split_values_complete(state: _DSWizardState) -> bool:
    return all(_ds_wizard_has_value(state.values.get(key)) for key in _DS_WIZARD_SPLIT_KEYS)


def _ds_wizard_default_split_values() -> Tuple[float, float, float]:
    field_map = _ds_wizard_field_map()
    return (
        float(field_map['split_train'].default or 0.70),
        float(field_map['split_val'].default or 0.15),
        float(field_map['split_test'].default or 0.15),
    )


def _ds_wizard_parse_split_values(raw_value: str) -> Tuple[float, float]:
    text = str(raw_value or '').strip().replace(',', ' ')
    pieces = [piece for piece in text.split() if piece]
    if len(pieces) != 2:
        raise ValueError('split needs train and test values')
    return float(pieces[0]), float(pieces[1])


def _ds_wizard_clear_split_values(state: _DSWizardState) -> _DSWizardState:
    for key in _DS_WIZARD_SPLIT_KEYS:
        state.values[key] = ''
    state.last_action = 'clear:split'
    _ds_wizard_set_transient_lines(state, ['cleared: split'])
    return state


def _ds_wizard_apply_split_values(state: _DSWizardState, train_value: float, test_value: float) -> _DSWizardState:
    train = float(train_value)
    test = float(test_value)
    if train < 0.0 or test < 0.0:
        raise ValueError('split values cannot be negative')
    if train > 1.0 or test > 1.0:
        raise ValueError('split values must stay within 0.0 and 1.0')
    total = train + test
    if total > 1.0 + 0.000001:
        raise ValueError('train + test cannot exceed 1.0')
    validation = round(1.0 - total, 10)
    if abs(validation) < 0.000001:
        validation = 0.0
    state.values['split_train'] = train
    state.values['split_val'] = validation
    state.values['split_test'] = test
    state.last_action = 'set:split'
    _ds_wizard_set_transient_lines(
        state,
        [
            'updated split: train = {0}, validation = {1}, test = {2}'.format(
                _ds_wizard_stringify_value(train),
                _ds_wizard_stringify_value(validation),
                _ds_wizard_stringify_value(test),
            )
        ],
    )
    return state


def _ds_wizard_prompt_split_values(state: _DSWizardState) -> _DSWizardState:
    if _ds_wizard_split_values_present(state):
        current_text = 'train={0}, validation={1}, test={2}'.format(
            _ds_wizard_stringify_value(state.values.get('split_train', '')),
            _ds_wizard_stringify_value(state.values.get('split_val', '')),
            _ds_wizard_stringify_value(state.values.get('split_test', '')),
        )
        choice = input('split [{0}] -> keep / clear / new: '.format(current_text)).strip().lower()
        if choice == 'clear':
            return _ds_wizard_clear_split_values(state)
        if choice not in ('new', 'n'):
            state.last_action = 'keep:split'
            _ds_wizard_set_transient_lines(state, ['kept existing value for split'])
            return state
    while True:
        train_raw = input('split train value: ').strip()
        test_raw = input('split test value: ').strip()
        try:
            train_value = float(train_raw)
            test_value = float(test_raw)
            return _ds_wizard_apply_split_values(state, train_value, test_value)
        except ValueError as exc:
            choice = input('{0} -> retry / clear / keep: '.format(str(exc) or 'invalid split values')).strip().lower()
            if choice == 'clear':
                return _ds_wizard_clear_split_values(state)
            if choice not in ('retry', 'r'):
                _ds_wizard_set_transient_lines(state, ['kept existing value for split'])
                return state


def _ds_wizard_split_cli_args(state: _DSWizardState) -> List[str]:
    if not _ds_wizard_split_values_present(state):
        return []
    return [
        '--split-train', str(state.values.get('split_train', '')),
        '--split-val', str(state.values.get('split_val', '')),
        '--split-test', str(state.values.get('split_test', '')),
    ]


def _ds_wizard_resolved_split_values(state: _DSWizardState) -> Tuple[float, float, float]:
    if not _ds_wizard_split_values_present(state):
        return _ds_wizard_default_split_values()
    return (
        float(state.values.get('split_train', 0.70)),
        float(state.values.get('split_val', 0.15)),
        float(state.values.get('split_test', 0.15)),
    )


def _ds_wizard_dataset_picker_status(state: _DSWizardState) -> str:
    workflow = str(state.workflow or '').strip()
    dataset_manifest_set = _ds_wizard_has_value(state.values.get('dataset_manifest'))
    features_set = _ds_wizard_has_value(state.values.get('features_csv'))
    if workflow in ('train', 'score') and not dataset_manifest_set:
        return 'missing'
    if workflow == 'evaluate' and not features_set:
        return 'missing'
    return 'set' if dataset_manifest_set or features_set else 'optional'


def _ds_wizard_dataset_picker_current(state: _DSWizardState) -> str:
    bits: List[str] = []
    dataset_manifest = str(state.values.get('dataset_manifest', '') or '').strip()
    if dataset_manifest:
        bits.append(_ds_wizard_short_path(dataset_manifest))
    if _ds_wizard_has_value(state.values.get('features_csv')):
        bits.append('features')
    if _ds_wizard_has_value(state.values.get('labels_csv')):
        bits.append('labels')
    return ', '.join(bits) if bits else '<choose approved dataset>'


def _ds_wizard_train_picker_status(state: _DSWizardState) -> str:
    workflow = str(state.workflow or '').strip()
    has_model_context = _ds_wizard_has_value(state.values.get('train_manifest')) or _ds_wizard_has_value(state.values.get('model_path'))
    if workflow == 'score' and not has_model_context:
        return 'missing'
    return 'set' if has_model_context else 'optional'


def _ds_wizard_train_picker_current(state: _DSWizardState) -> str:
    train_manifest = str(state.values.get('train_manifest', '') or '').strip()
    if train_manifest:
        return _ds_wizard_short_path(train_manifest)
    model_path = str(state.values.get('model_path', '') or '').strip()
    if model_path:
        return _ds_wizard_short_path(model_path)
    return '<choose saved model/train>'


def _ds_wizard_baseline_picker_current(state: _DSWizardState) -> str:
    baseline_window_id = str(state.values.get('baseline_window_id', '') or '').strip()
    if baseline_window_id:
        return baseline_window_id
    baseline_packet = str(state.values.get('baseline_analysis_packet', '') or '').strip()
    if baseline_packet:
        return _ds_wizard_short_path(baseline_packet)
    return '<no saved baseline>'


def _ds_wizard_run_picker_current(state: _DSWizardState) -> str:
    if str(state.run_ledger_path or '').strip():
        return _ds_wizard_short_path(str(state.run_ledger_path))
    run_id = str(state.values.get('run_id', '') or '').strip()
    if run_id:
        return run_id
    return '<no prior run>'


def _ds_wizard_draft_picker_current(state: _DSWizardState) -> str:
    if str(state.draft_path or '').strip():
        return _ds_wizard_short_path(str(state.draft_path))
    return '<choose saved draft>'


def _ds_wizard_menu_items(state: _DSWizardState, section: Optional[str] = None) -> List[_DSWizardMenuItem]:
    current_section = str(section or _ds_wizard_current_section(state)).strip().lower()
    workflow = str(state.workflow or '').strip()
    field_map = _ds_wizard_field_map()

    def _field_item(spec: _DSWizardFieldSpec) -> _DSWizardMenuItem:
        return _DSWizardMenuItem(
            item_type='field',
            target=spec.key,
            label=_ds_wizard_ui_label(spec.key),
            status=_ds_wizard_status_token(state, spec),
            current=_ds_wizard_render_field_current(state, spec),
            detail=spec.description,
        )

    items: List[_DSWizardMenuItem] = []
    if current_section == 'flow':
        return [
            _DSWizardMenuItem(
                'picker',
                'advanced',
                'advanced',
                '',
                '',
                'open the override sandbox for manual or lineage-breaking actions',
            ),
        ]
    if current_section == 'in':
        if workflow in ('build', 'run-pipeline'):
            items.extend([
                _DSWizardMenuItem(
                    'picker',
                    'draft-load',
                    'load saved draft',
                    '',
                    _ds_wizard_draft_picker_current(state),
                    'restore saved workflow state before staging telemetry inputs',
                )
            ])
        elif workflow in ('train', 'evaluate', 'score'):
            items.append(
                _DSWizardMenuItem(
                    'picker',
                    'dataset',
                    'approved dataset',
                    _ds_wizard_dataset_picker_status(state),
                    _ds_wizard_dataset_picker_current(state),
                    'load dataset, feature, and label context',
                )
            )
        for spec in _ds_wizard_fields_for_section(state, current_section):
            if spec.key in ('input_paths', 'dataset_manifest'):
                continue
            if workflow == 'run-demo' and spec.key not in ('source', 'mode'):
                continue
            items.append(_field_item(spec))
        return items
    if current_section == 'model':
        if workflow in ('evaluate', 'run-demo', 'run-pipeline'):
            baseline_status = 'set' if _ds_wizard_has_value(state.values.get('baseline_analysis_packet')) or _ds_wizard_has_value(state.values.get('baseline_window_id')) else 'optional'
            items.append(
                _DSWizardMenuItem(
                    'picker',
                    'baseline',
                    'load saved baseline',
                    baseline_status,
                    _ds_wizard_baseline_picker_current(state),
                    'attach saved baseline context',
                )
            )
        if workflow == 'evaluate':
            run_status = 'set' if str(state.run_ledger_path or '').strip() else 'optional'
            items.append(
                _DSWizardMenuItem(
                    'picker',
                    'run',
                    'load previous',
                    run_status,
                    _ds_wizard_run_picker_current(state),
                    'hydrate a prior evaluation run',
                )
            )
        if workflow in ('evaluate', 'score'):
            items.append(
                _DSWizardMenuItem(
                    'picker',
                    'train',
                    'model artifact',
                    _ds_wizard_train_picker_status(state),
                    _ds_wizard_train_picker_current(state),
                    'load approved saved model context',
                )
            )
        if workflow in ('train', 'evaluate', 'score'):
            items.append(
                _DSWizardMenuItem(
                    'picker',
                    'dataset',
                    'dataset artifact',
                    _ds_wizard_dataset_picker_status(state),
                    _ds_wizard_dataset_picker_current(state),
                    'load dataset, feature, and label context',
                )
            )
        if workflow in ('train', 'run-pipeline'):
            model_spec = field_map.get('model_type')
            if model_spec is not None:
                items.append(
                    _DSWizardMenuItem(
                        'enum',
                        'model_type',
                        'model family',
                        _ds_wizard_status_token(state, model_spec),
                        str(state.values.get('model_type', 'supervised') or 'supervised'),
                        'choose supervised or unsupervised',
                    )
                )
        for spec in _ds_wizard_fields_for_section(state, current_section):
            if spec.key in ('model_type', 'model_path', 'train_manifest', 'baseline_analysis_packet', 'baseline_window_id', 'run_id'):
                continue
            if _ds_wizard_split_is_relevant(state) and spec.key in ('split_val', 'split_test'):
                continue
            items.append(_field_item(spec))
        return items
    if current_section == 'eval':
        return [_field_item(spec) for spec in _ds_wizard_fields_for_section(state, current_section)]
    if current_section == 'report':
        return []
    if current_section == 'cmd':
        return [
            _DSWizardMenuItem(
                'picker',
                'draft-load',
                'load saved draft',
                '',
                _ds_wizard_draft_picker_current(state),
                'restore saved workflow state from a canonical draft slot',
            ),
            _DSWizardMenuItem(
                'action',
                'latest-context',
                'latest saved context',
                '',
                '{0} / {1}'.format(str(state.source or 'sim'), str(state.mode or 'watch')),
                'hydrate source, mode, and the latest saved baseline context',
            ),
        ]
    return items


def _ds_wizard_partition_menu_lines(state: _DSWizardState, section: str, lines: List[str]) -> List[str]:
    current_section = str(section or '').strip().lower()
    workflow = str(state.workflow or '').strip()
    if not lines:
        return []
    if current_section == 'in' and workflow in ('build', 'run-pipeline'):
        grouped = [_style_section_line('load configs'), lines[0]]
        if len(lines) > 1:
            grouped.extend([
                '',
                _style_section_line('load data'),
                *lines[1:],
            ])
        return grouped
    if current_section == 'model' and workflow == 'evaluate':
        grouped: List[str] = [_style_section_line('load configs')]
        grouped.extend(lines[:2])
        if len(lines) > 2:
            grouped.append('')
            grouped.append(_style_section_line('load data'))
            grouped.extend(lines[2:4])
        if len(lines) > 4:
            grouped.append('')
            grouped.extend(lines[4:])
        return grouped
    return lines


def _ds_wizard_render_menu_items(state: _DSWizardState, section: Optional[str] = None) -> List[str]:
    current_section = str(section or _ds_wizard_current_section(state)).strip().lower()
    items = _ds_wizard_menu_items(state, current_section)
    if not items:
        return []

    def _row(label_prefix: str, label: str, status: str, current: str = '', detail: str = '', current_width: int = 0) -> str:
        label_block = _style_padded_choice_label(label_prefix, label, 22)
        status_block = ljust_ansi(str(status or ''), 9)
        current_text = str(current or '').strip()
        detail_text = str(detail or '').strip()
        if current_text and detail_text:
            current_block = rjust_ansi(current_text, current_width or len(strip_ansi(current_text)))
            tail = '{0} | {1}'.format(current_block, detail_text)
        elif current_text:
            tail = current_text
        else:
            tail = detail_text
        return '{0} {1} {2}'.format(label_block, status_block, tail).rstrip()

    start_idx = len(_DS_WIZARD_WORKFLOWS) + 1 if current_section == 'flow' else 1
    current_width = 0
    for item in items:
        if str(item.current or '').strip() and str(item.detail or '').strip():
            current_width = max(current_width, len(strip_ansi(str(item.current))))
    if current_section == 'model' and _ds_wizard_split_is_relevant(state):
        field_map = _ds_wizard_field_map()
        for split_key in _DS_WIZARD_SPLIT_KEYS:
            current_width = max(current_width, len(strip_ansi(_ds_wizard_render_field_current(state, field_map[split_key]))))
    lines: List[str] = []
    for idx, item in enumerate(items, start=start_idx):
        if current_section == 'flow':
            lines.append(_style_choice_label('{0}. '.format(idx), item.label))
            continue
        if current_section == 'cmd':
            line = _style_padded_choice_label('{0}. '.format(idx), item.label, 22)
            if str(item.current or '').strip():
                line = '{0} {1}'.format(line, str(item.current).strip())
            lines.append(line.rstrip())
            continue
        if item.item_type == 'field' and item.target == 'split_train' and _ds_wizard_split_is_relevant(state):
            field_map = _ds_wizard_field_map()
            split_rows = [
                ('{0}. '.format(idx), _ds_wizard_ui_label('split_train'), field_map['split_train']),
                ('', '', field_map['split_val']),
                ('', '', field_map['split_test']),
            ]
            for prefix, label, spec in split_rows:
                lines.append(
                    _row(
                        prefix,
                        label,
                        _ds_wizard_status_token(state, spec),
                        _ds_wizard_render_field_current(state, spec),
                        spec.description,
                        current_width=current_width,
                    )
                )
            continue
        lines.append(_row('{0}. '.format(idx), item.label, item.status, item.current, item.detail, current_width=current_width))
    return _ds_wizard_partition_menu_lines(state, current_section, lines)


def _ds_wizard_menu_item_by_index(state: _DSWizardState, token: str) -> Optional[_DSWizardMenuItem]:
    if not str(token or '').isdigit():
        return None
    idx = int(str(token))
    current_section = _ds_wizard_current_section(state)
    if current_section == 'flow':
        idx -= len(_DS_WIZARD_WORKFLOWS)
    items = _ds_wizard_menu_items(state, current_section)
    if 1 <= idx <= len(items):
        return items[idx - 1]
    return None


def _ds_wizard_direct_fields(state: _DSWizardState, section: Optional[str] = None) -> List[_DSWizardFieldSpec]:
    current_section = str(section or _ds_wizard_current_section(state)).strip().lower()
    section_fields = _ds_wizard_fields_for_section(state, current_section)
    if current_section in ('in', 'report', 'cmd'):
        return []
    hidden_keys: set = set()
    if current_section == 'model':
        hidden_keys.update(('model_type', 'model_path', 'train_manifest', 'baseline_analysis_packet', 'baseline_window_id', 'run_id'))
        if _ds_wizard_split_is_relevant(state):
            hidden_keys.update(('split_val', 'split_test'))
    return [spec for spec in section_fields if spec.key not in hidden_keys]


def _ds_wizard_render_direct_field_lines(state: _DSWizardState, section: Optional[str] = None) -> List[str]:
    current_section = str(section or _ds_wizard_current_section(state)).strip().lower()
    fields = _ds_wizard_direct_fields(state, current_section)
    if not fields:
        return []
    start_idx = len(_ds_wizard_menu_items(state, current_section)) + 1
    lines: List[str] = []
    for idx, spec in enumerate(fields, start=start_idx):
        current = _ds_wizard_render_field_current(state, spec)
        lines.append('{0} {1:<9} {2}'.format(_style_padded_choice_label('{0}. '.format(idx), _ds_wizard_ui_label(spec.key), 22), _ds_wizard_status_token(state, spec), current).rstrip())
    return lines


def _ds_wizard_picker_title(target: str) -> str:
    return {
        'advanced': 'advanced:',
        'dataset': 'approved datasets:',
        'train': 'saved trained:',
        'run': 'saved runs:',
        'baseline': 'saved baselines:',
        'draft-load': 'saved draft slots:',
        'source': 'source choices:',
        'mode': 'mode choices:',
        'model_type': 'model family choices:',
    }.get(str(target or '').strip().lower(), 'guided picker:')


def _ds_wizard_run_id_override_active(state: _DSWizardState) -> bool:
    source = str(state.hydrated_from.get('run_id', '') or '').strip().lower()
    if source in ('run_ledger', 'saved_run'):
        return False
    return _ds_wizard_has_value(state.values.get('run_id'))


def _ds_wizard_advanced_item_rows(state: _DSWizardState) -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str]] = [
        ('context overrides', 'source', 'source context'),
        ('context overrides', 'mode', 'mode context'),
        ('manual identifiers', 'run_id', 'run ID override'),
    ]
    workflow = str(state.workflow or '').strip()
    if workflow == 'score':
        rows.append(('power outputs', 'scores_out', 'scores output override'))
    elif workflow in ('build', 'train', 'evaluate', 'run-demo', 'run-pipeline'):
        rows.append(('power outputs', 'out_dir', 'run root override'))
    return rows


def _ds_wizard_advanced_current_value(state: _DSWizardState, key: str) -> str:
    token = str(key or '').strip().lower()
    if token == 'source':
        return str(state.source or 'sim')
    if token == 'mode':
        return str(state.mode or 'watch')
    if token == 'run_id':
        if _ds_wizard_run_id_override_active(state):
            return str(state.values.get('run_id', '') or '').strip()
        return '<auto-generated>'
    if token == 'out_dir':
        return _ds_wizard_short_path(str(state.values.get('out_dir', '') or '').strip()) if _ds_wizard_has_value(state.values.get('out_dir')) else '<canonical>'
    if token == 'scores_out':
        return _ds_wizard_short_path(str(state.values.get('scores_out', '') or '').strip()) if _ds_wizard_has_value(state.values.get('scores_out')) else '<canonical>'
    return '<unset>'


def _ds_wizard_open_advanced_override(state: _DSWizardState, key: str) -> _DSWizardState:
    state.transient_view = 'advanced-edit'
    state.transient_target = str(key or '').strip().lower()
    state.last_action = 'advanced:{0}'.format(state.transient_target or 'unknown')
    return state


def _ds_wizard_advanced_override_lines(state: _DSWizardState, target: str) -> List[str]:
    key = str(target or '').strip().lower()
    label = {
        'run_id': 'run ID override',
        'out_dir': 'run root override',
        'scores_out': 'scores output override',
    }.get(key, 'advanced override')
    lines = [
        _style_section_line('advanced override'),
        _style_section_line('warning'),
        '  this lane bypasses selector-derived defaults and should be used only when the governed path is insufficient.',
        '',
        '{0}:'.format(label),
        '  current: {0}'.format(_ds_wizard_advanced_current_value(state, key)),
        '',
        _style_section_line('commands'),
        '  set {0} <value>      apply a manual override inside advanced'.format(key),
        '  clear {0}            remove the override and return to defaults'.format(key),
        '  close                dismiss this override surface',
    ]
    return lines


def _ds_wizard_picker_lines(state: _DSWizardState, target: str) -> List[str]:
    picker_target = str(target or '').strip().lower()
    if picker_target == 'advanced':
        lines = [
            _style_section_line('advanced'),
            _style_section_line('warning'),
            '  context overrides are high-risk and can detach the wizard from selector-derived defaults.',
            '  prefer the default context, saved metadata, or CLI seeding unless you have a specific reason.',
        ]
        current_group = ''
        for idx, (group, key, label) in enumerate(_ds_wizard_advanced_item_rows(state), start=1):
            if group != current_group:
                lines.append('')
                lines.append(_style_section_line(group))
                current_group = group
            lines.append('{0} current: {1}'.format(_style_padded_choice_label('{0}. '.format(idx), label, 22), _ds_wizard_advanced_current_value(state, key)))
        lines.append('')
        lines.append(_style_section_line('guidance'))
        lines.append('  choose a number to open an explicit override lane')
        return lines
    if picker_target == 'dataset':
        return _ds_wizard_dataset_selector_lines()
    if picker_target == 'train':
        return _ds_wizard_train_selector_lines()
    if picker_target == 'run':
        return _ds_wizard_run_selector_lines()
    if picker_target == 'baseline':
        return _ds_wizard_baseline_selector_lines(state)
    if picker_target == 'draft-load':
        return _ds_wizard_draft_slot_lines()
    if picker_target in _DS_WIZARD_ENUM_PICKERS:
        options = list(_DS_WIZARD_ENUM_PICKERS.get(picker_target, ()))
        current_value = str(_ds_wizard_field_value(state, picker_target) or '').strip().lower()
        lines = [_ds_wizard_picker_title(picker_target)]
        for idx, option in enumerate(options, start=1):
            marker = '*' if str(option).strip().lower() == current_value else ' '
            lines.append(_style_choice_label('{0}. [{1}] '.format(idx, marker), option))
        lines.append('')
        lines.append(_style_section_line('guidance'))
        lines.append('  choose a number to update the current value')
        return lines
    return ['guided picker unavailable: {0}'.format(picker_target or '<unknown>')]


def _ds_wizard_open_picker(state: _DSWizardState, target: str) -> _DSWizardState:
    state.transient_view = 'picker'
    state.transient_target = str(target or '').strip()
    state.last_action = 'picker:{0}'.format(state.transient_target or 'unknown')
    return state


def _ds_wizard_activate_menu_item(state: _DSWizardState, item: _DSWizardMenuItem) -> _DSWizardState:
    if item.item_type in ('picker', 'enum'):
        return _ds_wizard_open_picker(state, item.target)
    if item.item_type == 'action':
        if item.target == 'save-draft':
            return _ds_wizard_save_draft_reference(state, '')
        if item.target == 'latest-context':
            return _ds_wizard_hydrate_latest_context(state)
        _ds_wizard_set_transient_lines(state, ['guided action unavailable: {0}'.format(item.target or item.label)])
        return state
    if item.item_type == 'cli-only':
        if item.target == 'input_paths':
            _ds_wizard_set_transient_lines(
                state,
                [
                    'telemetry inputs stay CLI-only in the guided flow.',
                    'seed them through observerctl ds flags or load a prepared draft before executing this workflow.',
                ],
            )
            return state
        _ds_wizard_set_transient_lines(state, ['this surface stays CLI-only in the guided flow.'])
        return state
    return state


def _ds_wizard_apply_picker_selection(state: _DSWizardState, target: str, selection: str) -> _DSWizardState:
    picker_target = str(target or '').strip().lower()
    token = str(selection or '').strip()
    if not token:
        _ds_wizard_set_transient_lines(state, ['picker selection is required'])
        return state
    if picker_target == 'advanced':
        advanced_rows = _ds_wizard_advanced_item_rows(state)
        resolved_key = ''
        if token.isdigit():
            idx = int(token)
            if 1 <= idx <= len(advanced_rows):
                resolved_key = advanced_rows[idx - 1][1]
        else:
            normalized = token.lower().replace(' ', '_').replace('-', '_')
            for _, row_key, row_label in advanced_rows:
                if normalized in (row_key, row_label.lower().replace(' ', '_')):
                    resolved_key = row_key
                    break
        if resolved_key in ('source', 'mode'):
            return _ds_wizard_open_picker(state, resolved_key)
        if resolved_key in _DS_WIZARD_ADVANCED_EDIT_KEYS:
            return _ds_wizard_open_advanced_override(state, resolved_key)
        _ds_wizard_set_transient_lines(state, ['advanced selection not recognized: {0}'.format(token)])
        return state
    if picker_target in _DS_WIZARD_ENUM_PICKERS:
        options = list(_DS_WIZARD_ENUM_PICKERS.get(picker_target, ()))
        choice = token
        if token.isdigit():
            idx = int(token)
            if 1 <= idx <= len(options):
                choice = str(options[idx - 1])
            else:
                _ds_wizard_set_transient_lines(state, ['picker selection out of range: {0}'.format(token)])
                return state
        if choice not in options:
            _ds_wizard_set_transient_lines(state, ['picker selection not recognized: {0}'.format(choice)])
            return state
        return _ds_wizard_set_value(state, picker_target, choice)
    try:
        if picker_target == 'dataset':
            return _ds_wizard_hydrate_dataset_reference(state, token)
        if picker_target == 'train':
            return _ds_wizard_hydrate_train_reference(state, token)
        if picker_target == 'run':
            return _ds_wizard_hydrate_run_reference(state, token)
        if picker_target == 'baseline':
            return _ds_wizard_hydrate_baseline_reference(state, token)
        if picker_target == 'draft-load':
            return _ds_wizard_load_draft_reference(token, state=state)
    except Exception as exc:
        _ds_wizard_set_transient_lines(state, ['guided picker failed: {0}'.format(str(exc) or token)])
        return state
    _ds_wizard_set_transient_lines(state, ['guided picker unavailable: {0}'.format(picker_target or '<unknown>')])
    return state


def _ds_wizard_coerce_value(spec: _DSWizardFieldSpec, raw: Any) -> Any:
    if spec.accepts_multiple:
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        text = str(raw or '').strip()
        if not text:
            return []
        return [item.strip() for item in text.split(',') if item.strip()]
    text = str(raw or '').strip()
    if not text:
        return ''
    if spec.value_kind == 'int':
        return int(text)
    if spec.value_kind == 'float':
        return float(text)
    return text


def _ds_wizard_set_value(state: _DSWizardState, key: str, value: Any) -> _DSWizardState:
    spec = _ds_wizard_field_map().get(key)
    if spec is None:
        raise KeyError('unknown wizard field: {0}'.format(key))
    display_label = _ds_wizard_ui_label(key)
    coerced = _ds_wizard_coerce_value(spec, value)
    if key == 'workflow':
        normalized_workflow = str(coerced or '').strip()
        if normalized_workflow not in _DS_WIZARD_WORKFLOWS:
            normalized_workflow = _ds_wizard_default_workflow()
        state.workflow = normalized_workflow
        state.values['workflow'] = state.workflow
        state.last_action = 'set:workflow'
        if state.active_section not in _ds_wizard_visible_sections(state):
            state.active_section = 'flow'
            _ds_wizard_sync_page_from_section(state)
        _ds_wizard_set_transient_lines(
            state,
            [
                'workflow set: {0}'.format(state.workflow or 'unset'),
                'use the left menu or next/prev to continue the guided workflow',
            ],
        )
        return state
    if key == 'source':
        normalized_source = _normalize_source(str(coerced or state.source or 'sim'))
        state.source = normalized_source
        state.values['source'] = normalized_source
        state.last_action = 'set:source'
        _ds_wizard_clear_context_display(state)
        _ds_wizard_set_transient_lines(
            state,
            [
                'updated context: source = {0}'.format(normalized_source),
                'this affects saved-context hydration and wizard framing only.',
            ],
        )
        return state
    if key == 'mode':
        normalized_mode = str(coerced or '').strip().lower()
        if normalized_mode not in MODES:
            _ds_wizard_set_transient_lines(
                state,
                [
                    'mode not updated',
                    'choose one of: {0}'.format(', '.join(MODES)),
                ],
            )
            return state
        state.mode = normalized_mode
        state.values['mode'] = normalized_mode
        state.last_action = 'set:mode'
        _ds_wizard_clear_context_display(state)
        _ds_wizard_set_transient_lines(
            state,
            [
                'updated context: mode = {0}'.format(normalized_mode),
                'this affects saved-context hydration and wizard framing only.',
            ],
        )
        return state
    state.values[key] = coerced
    state.last_action = 'set:{0}'.format(key)
    _ds_wizard_set_transient_lines(state, ['updated: {0} = {1}'.format(display_label, _ds_wizard_stringify_value(coerced))])
    return state


def _ds_wizard_apply_reselection(state: _DSWizardState, key: str, action: str, new_value: Any = '') -> _DSWizardState:
    verb = str(action or '').strip().lower()
    resolved_key = _ds_wizard_resolve_field_alias(key)
    display_label = 'split' if resolved_key in _DS_WIZARD_SPLIT_KEYS else _ds_wizard_ui_label(resolved_key)
    if verb == 'keep':
        state.last_action = 'keep:{0}'.format(resolved_key)
        _ds_wizard_set_transient_lines(state, ['kept existing value for {0}'.format(display_label)])
        return state
    if verb == 'clear':
        if resolved_key in _DS_WIZARD_SPLIT_KEYS:
            return _ds_wizard_clear_split_values(state)
        spec = _ds_wizard_field_map().get(resolved_key)
        if spec is None:
            raise KeyError('unknown wizard field: {0}'.format(resolved_key))
        if key == 'workflow':
            state.workflow = _ds_wizard_default_workflow()
            state.values['workflow'] = state.workflow
            _ds_wizard_clear_context_display(state)
            if state.active_section not in _ds_wizard_visible_sections(state):
                state.active_section = 'flow'
                _ds_wizard_sync_page_from_section(state)
            state.last_action = 'clear:{0}'.format(key)
            _ds_wizard_set_transient_lines(state, ['workflow reset: {0}'.format(state.workflow), 'context: cleared'])
            return state
        state.values[resolved_key] = [] if spec.accepts_multiple else ''
        if key == 'workflow':
            state.workflow = ''
        state.last_action = 'clear:{0}'.format(resolved_key)
        _ds_wizard_set_transient_lines(state, ['cleared: {0}'.format(display_label)])
        return state
    if verb == 'new':
        if resolved_key in _DS_WIZARD_SPLIT_KEYS:
            train_value, test_value = _ds_wizard_parse_split_values(str(new_value or ''))
            return _ds_wizard_apply_split_values(state, train_value, test_value)
        return _ds_wizard_set_value(state, resolved_key, new_value)
    raise ValueError('unsupported reselection action: {0}'.format(action))


def _ds_wizard_move_section(state: _DSWizardState, direction: str) -> _DSWizardState:
    sections = _ds_wizard_page_sections(state)
    if state.active_section not in sections:
        if sections:
            state.active_section = sections[0]
        return state
    idx = sections.index(state.active_section)
    step = 1 if str(direction).strip().lower() == 'next' else -1
    state.active_section = sections[(idx + step) % len(sections)]
    _ds_wizard_sync_page_from_section(state)
    state.last_action = 'section:{0}'.format(state.active_section)
    state.transient_view = ''
    state.transient_target = ''
    return state


def _ds_wizard_open_section(state: _DSWizardState, section: str) -> _DSWizardState:
    target = str(section or '').strip().lower()
    if target in _ds_wizard_visible_sections(state):
        state.active_section = target
        _ds_wizard_sync_page_from_section(state)
        state.last_action = 'section:{0}'.format(target)
        state.transient_view = ''
        state.transient_target = ''
    return state


def _ds_wizard_menu_help_lines(state: _DSWizardState) -> List[str]:
    lines = [_style_section_line('help')]
    if state.active_page == 'landing':
        for key, detail in _DS_WIZARD_LANDING_CHOICES:
            label = 'review and run' if key == 'review-run' else ('command and utilities' if key == 'command' else key)
            lines.append('{0:<18} {1}'.format(label, detail))
        return lines
    for section in _ds_wizard_page_sections(state):
        info = _DS_WIZARD_SECTION_HELP.get(section, {})
        lines.append('{0:<10} {1}'.format(_ds_wizard_section_display_label(section), str(info.get('label', section)).strip()))
    return lines


def _ds_wizard_scope_help_lines(state: _DSWizardState) -> List[str]:
    if state.active_page == 'landing':
        lines = _ds_wizard_menu_help_lines(state)
        lines.append('')
        lines.append(_style_section_line('use'))
        lines.append('  type a number or choice name to open that page')
        lines.append("  type ? <choice> to preview a page before opening it")
        return lines
    
    current_section = _ds_wizard_current_section(state)
    info = _DS_WIZARD_SECTION_HELP.get(current_section, {})
    
    lines = ['{0} {1}'.format(_style_section_line('help'), current_section)]
    
    detail = str(info.get('detail', '')).strip()
    if detail:
        lines.append('  {0}'.format(detail))
    
    guidance = str(info.get('guidance', '')).strip()
    if guidance:
        lines.append('')
        lines.append(_style_section_line('guidance'))
        lines.append('  {0}'.format(guidance))
        
    section_fields = _ds_wizard_fields_for_section(state, current_section)
    if current_section == 'eval':
        lines.append('')
        lines.append(_style_section_line('fields'))
        for spec in section_fields:
            desc = spec.description if spec.description else spec.key
            lines.append('  {0:<16} {1}'.format(_ds_wizard_ui_label(spec.key), desc))

    commands = []
    if current_section == 'check':
        commands.append(('validate', 'recompute blockers for the current workflow'))
        commands.append(('open <section>', 'jump straight to the section you need to fix'))
    elif current_section == 'run':
        commands.append(('execute', 'start the configured workflow when blocked=no'))
    elif current_section == 'eval':
        commands.append(('<number>', 'edit that numbered field interactively'))
        commands.append(('set <field> <val>', 'update a field directly (e.g. set max_fpr 0.02)'))
        commands.append(('clear <field>', 'remove the current value'))
        commands.append(('? <field>', 'explain a field and show the current value'))
        
    if commands:
        lines.append('')
        lines.append(_style_section_line('commands'))
        for cmd, cmd_desc in commands:
            lines.append('  {0:<24} {1}'.format(cmd, cmd_desc))
            
    return lines

def _ds_wizard_set_transient_lines(state: _DSWizardState, lines: List[str], view: str = 'educational') -> _DSWizardState:
    payload = [str(line).strip() for line in lines if str(line).strip()]
    state.transient_view = view
    state.transient_target = '\n'.join(payload)
    return state


def _ds_wizard_transient_lines(state: _DSWizardState) -> List[str]:
    text = str(state.transient_target or '').strip()
    if not text:
        return []
    return [str(line).rstrip() for line in text.splitlines() if str(line).strip()]


def _ds_wizard_short_path(path_text: str) -> str:
    text = str(path_text or '').strip().replace('\\', '/')
    if not text:
        return '<none>'
    parts = [part for part in text.split('/') if part]
    if len(parts) >= 2:
        return '/'.join(parts[-2:])
    return parts[-1] if parts else text


def _resolve_existing_project_path(path_text: str) -> Optional[Path]:
    token = str(path_text or '').strip()
    if not token:
        return None
    raw_path = Path(token)
    candidates = [raw_path]
    if not raw_path.is_absolute():
        candidates.append(_project_root() / raw_path)

    seen: set = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        try:
            if resolved.exists() and resolved.is_file():
                return resolved
        except Exception:
            continue
    return None


def _resolve_existing_reference_path(path_text: str, base_dir: Optional[Path] = None) -> Optional[Path]:
    token = str(path_text or '').strip()
    if not token:
        return None
    raw_path = Path(token)
    candidates: List[Path] = []
    if base_dir is not None and not raw_path.is_absolute():
        candidates.append(Path(base_dir) / raw_path)
    candidates.append(raw_path)
    if not raw_path.is_absolute():
        candidates.append(_project_root() / raw_path)

    seen: set = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        try:
            if resolved.exists() and resolved.is_file():
                return resolved
        except Exception:
            continue
    return None


def _ds_wizard_saved_selector_lines(packet: Dict[str, Any], limit: int = 6) -> List[str]:
    action = str(packet.get('action', '') or '').strip().lower()
    title = {
        'ds-saved-trained': 'saved trained:',
        'ds-saved-runs': 'saved runs:',
        'ds-saved-baselines': 'saved baselines:',
        'ds-saved-drafts': 'saved draft slots:',
    }.get(action, 'saved selectors:')

    entries = packet.get('selector_entries', []) if isinstance(packet.get('selector_entries', []), list) else []
    lines = [_style_section_line(title.rstrip(':'))]
    scope_bits: List[str] = []
    if action == 'ds-saved-baselines':
        source = str(packet.get('source', '') or '').strip()
        mode = str(packet.get('mode', '') or '').strip()
        if source or mode:
            scope_bits.append('{0} / {1}'.format(source or 'sim', mode or 'watch'))
    if scope_bits:
        lines.extend(_render_human_kv_rows([('Scope', ', '.join(scope_bits))], indent='  ', min_label_width=8, max_label_width=8))

    if not entries:
        lines.append('  none available yet')
    else:
        for row in entries[: max(1, int(limit or 6))]:
            if not isinstance(row, dict):
                continue
            if len(lines) > 1:
                lines.append('')
            lines.extend(_render_ds_saved_block(row, include_index=True, indent='  '))
        if len(entries) > max(1, int(limit or 6)):
            lines.append('')
            lines.append('... and {0} more saved selectors'.format(len(entries) - max(1, int(limit or 6))))

    guidance = {
        'ds-saved-trained': ['choose a number to load saved model/train context into the wizard'],
        'ds-saved-runs': ['choose a number to hydrate prior evaluation context into the wizard'],
        'ds-saved-baselines': ['choose a number to attach saved baseline context to the model/evaluation lane'],
        'ds-saved-drafts': ['choose a number to restore a saved draft slot'],
    }.get(action, [])
    if guidance:
        lines.append('')
        lines.append(_style_section_line('guidance'))
        for line in guidance:
            text = str(line or '').strip()
            if text:
                lines.append('  {0}'.format(text))
    return lines


def _ds_wizard_train_selector_lines(limit: int = 6) -> List[str]:
    return _ds_wizard_saved_selector_lines(_ds_train_selectors(), limit=limit)


def _ds_wizard_run_selector_lines(limit: int = 6) -> List[str]:
    return _ds_wizard_saved_selector_lines(_ds_run_selectors(), limit=limit)


def _ds_wizard_baseline_selector_lines(state: _DSWizardState, limit: int = 6) -> List[str]:
    return _ds_wizard_saved_selector_lines(_ds_baseline_selectors(state.source, state.mode), limit=limit)


def _ds_wizard_draft_slot_lines(limit: int = 6) -> List[str]:
    return _ds_wizard_saved_selector_lines(_ds_draft_slots(), limit=limit)


def _ds_wizard_dataset_selector_lines(limit: int = 8) -> List[str]:
    packet = _librarian_datasets()
    if str(packet.get('decision', 'go')).strip().lower() != 'go':
        lines = ['approved datasets: unavailable']
        for reason in packet.get('reason_codes', []) if isinstance(packet.get('reason_codes', []), list) else []:
            lines.append('  {0}'.format(reason))
        lines.append('next: retry after the librarian dataset catalog is available.')
        return lines

    entries = packet.get('selector_entries', []) if isinstance(packet.get('selector_entries', []), list) else []
    if not entries:
        return [
            'approved datasets: none registered yet',
            'next: use observerctl librarian dataset register <manifest> to seed the approved selector surface.',
        ]

    lines = ['approved datasets:']
    for row in entries[: max(1, int(limit or 8))]:
        if not isinstance(row, dict):
            continue
        if len(lines) > 1:
            lines.append('')
        lines.extend(_render_librarian_dataset_block(row, include_index=True, indent='  '))
    if len(entries) > max(1, int(limit or 8)):
        lines.append('')
        lines.append('... and {0} more approved datasets'.format(len(entries) - max(1, int(limit or 8))))
    lines.append('')
    lines.append(_style_section_line('guidance'))
    lines.append('  choose a number to load an approved dataset into the wizard')
    lines.append('  CLI follow-through can still resolve selectors by index, run_id, display name, or manifest path when needed')
    return lines


def _ds_wizard_choice_is_active(state: _DSWizardState, choice_key: str) -> bool:
    token = str(choice_key or '').strip().lower().replace('_', '-').replace(' ', '-')
    if token == 'command':
        return state.active_page == 'utilities'
    if token == 'review-run':
        return state.active_page == 'review-run'
    return token == str(state.active_page or '').strip().lower()


def _ds_wizard_field_by_index(state: _DSWizardState, token: str) -> Optional[_DSWizardFieldSpec]:
    if not str(token or '').isdigit():
        return None
    if state.active_section == 'flow':
        return None
    menu_item = _ds_wizard_menu_item_by_index(state, token)
    if menu_item is not None and menu_item.item_type == 'field':
        return _ds_wizard_field_map().get(menu_item.target)
    idx = int(str(token))
    menu_items = _ds_wizard_menu_items(state, state.active_section)
    non_field_items = [item for item in menu_items if item.item_type != 'field']
    field_idx = idx - len(non_field_items)
    section_fields = _ds_wizard_direct_fields(state, state.active_section)
    if 1 <= field_idx <= len(section_fields):
        return section_fields[field_idx - 1]
    return None


def _ds_wizard_item_peek_lines(state: _DSWizardState, target: str) -> List[str]:
    token = _ds_wizard_resolve_field_alias(str(target or '').strip().lower())
    if not token:
        return ['peek: no target provided']
    if token == 'current':
        token = 'landing' if state.active_page == 'landing' else state.active_section
    if token == 'landing':
        return [
            'peek: landing',
            'Sparse top-level orientation page.',
            'choices: configure, review and run, command and utilities, exit',
        ]
    landing_choice = _ds_wizard_landing_choice_map().get(token.replace(' ', '-').replace('_', '-'))
    if landing_choice is not None:
        label = 'command and utilities' if token.replace(' ', '-').replace('_', '-') == 'command' else token.replace('-', ' ')
        return [
            'peek: {0}'.format(label),
            landing_choice,
            'state: {0}'.format('active' if _ds_wizard_choice_is_active(state, token) else 'available'),
        ]
    menu_item = _ds_wizard_menu_item_by_index(state, token)
    if menu_item is not None and menu_item.item_type == 'field':
        token = menu_item.target
    if menu_item is not None and menu_item.item_type != 'field':
        lines = ['peek: {0}'.format(menu_item.label)]
        if str(menu_item.detail or '').strip():
            lines.append(str(menu_item.detail).strip())
        if str(menu_item.status or '').strip():
            lines.append('status: {0}'.format(menu_item.status))
        if str(menu_item.current or '').strip():
            lines.append('current: {0}'.format(menu_item.current))
        if menu_item.item_type in ('picker', 'enum'):
            lines.append('interaction: choose the numbered item in the guided flow.')
        elif menu_item.item_type == 'action':
            lines.append('interaction: choose the numbered action to apply it.')
        elif menu_item.item_type == 'cli-only':
            lines.append('boundary: this remains CLI-only in the guided flow.')
        return lines
    field_spec = _ds_wizard_field_by_index(state, token)
    if field_spec is not None:
        token = field_spec.key
    if token in _DS_WIZARD_SECTION_HELP:
        info = _DS_WIZARD_SECTION_HELP.get(token, {})
        lines = ['peek: {0}'.format(token)]
        label = str(info.get('label', '')).strip()
        detail = str(info.get('detail', '')).strip()
        if label:
            lines.append(label)
        if detail:
            lines.append(detail)
        if token in _ds_wizard_visible_sections(state):
            lines.append('state: {0}'.format('active' if token == state.active_section else 'available'))
        section_fields = _ds_wizard_fields_for_section(state, token)
        if section_fields:
            lines.append('fields:')
            for spec in section_fields[:6]:
                desc = spec.description if spec.description else spec.key
                lines.append('  {0:<16} {1}'.format(spec.key, desc))
            if len(section_fields) > 6:
                lines.append('  ... and {0} more'.format(len(section_fields) - 6))
        return lines
    spec = _ds_wizard_field_map().get(token)
    if spec is not None:
        value = _ds_wizard_field_value(state, spec.key)
        lines = ['peek: {0}'.format(spec.key)]
        ui_label = _ds_wizard_ui_label(spec.key)
        if ui_label != spec.key:
            lines.append('label: {0}'.format(ui_label))
        if str(spec.description or '').strip():
            lines.append(str(spec.description).strip())
        lines.append('section: {0}'.format(spec.section))
        lines.append('status: {0}'.format(_ds_wizard_status_token(state, spec)))
        lines.append('value: {0}'.format(_ds_wizard_stringify_value(value)))
        if spec.choices:
            lines.append('choices: {0}'.format(', '.join(spec.choices)))
        if spec.accepts_multiple:
            lines.append('accepts: comma-separated list')
        if str(spec.path_kind or '').strip():
            lines.append('path-kind: {0}'.format(spec.path_kind))
        if str(spec.artifact_source or '').strip():
            lines.append('artifact-source: {0}'.format(spec.artifact_source))
        return lines
    return ['peek: {0}'.format(token), 'not found in current wizard scope']


def _ds_wizard_inline_guidance_lines(state: _DSWizardState, section: str) -> List[str]:
    current_section = str(section or '').strip().lower()
    workflow = str(state.workflow or '').strip()
    if current_section == 'flow':
        return []
    if current_section == 'in':
        if workflow in ('build', 'run-pipeline'):
            return [
                'Use load configs for draft restore, then load data for telemetry inputs.',
            ]
        return [
            'Choose the approved dataset item by number to load dataset, feature, and label context.',
        ]
    if current_section == 'model':
        if workflow == 'evaluate':
            return [
                'Use load configs for saved baseline or prior evaluation context, then load data for model and dataset artifacts.',
            ]
        if workflow == 'train':
            return [
                'Choose the approved dataset item first, then set model family and retained training controls.',
            ]
        if workflow == 'score':
            return [
                'Choose the saved model/train item and dataset artifact before scoring.',
            ]
        if workflow == 'run-pipeline':
            return [
                'Choose model family by number; seed and split controls stay on this page.',
            ]
        return [
            'Choose the saved baseline item or retained model controls that apply to this workflow.',
        ]
    if current_section == 'report':
        return [
            'Review the canonical run root, report bundle, and artifact targets before executing.',
        ]
    if current_section == 'eval':
        return [
            'Type 1 to edit max_fpr, or use set max_fpr <value>.',
        ]
    if current_section == 'cmd':
        return []
    if current_section == 'check':
        return [
            'Type validate to recompute blockers after edits or hydration.',
        ]
    if current_section == 'run':
        return [
            'Type execute only when blocked=no.',
        ]
    return []


def _ds_wizard_open_scope_help(state: _DSWizardState) -> _DSWizardState:
    state.transient_view = 'scope-help'
    state.transient_target = 'landing' if state.active_page == 'landing' else (state.active_section if state.active_section in _ds_wizard_visible_sections(state) else 'flow')
    state.last_action = 'help:scope'
    return state


def _ds_wizard_open_item_peek(state: _DSWizardState, target: str) -> _DSWizardState:
    state.transient_view = 'item-peek'
    state.transient_target = str(target or '').strip()
    state.last_action = 'help:item:{0}'.format(state.transient_target or 'unknown')
    return state


def _ds_wizard_clear_transient_view(state: _DSWizardState) -> _DSWizardState:
    state.transient_view = ''
    state.transient_target = ''
    return state


def _ds_wizard_hydrate_dataset_reference(state: _DSWizardState, dataset_ref: str) -> _DSWizardState:
    token = str(dataset_ref or '').strip()
    if not token:
        raise ValueError('dataset reference is required')

    direct_path = _resolve_existing_project_path(token)
    if direct_path is not None:
        return _ds_wizard_hydrate_dataset_manifest(state, direct_path)

    packet = _librarian_dataset_release(
        token,
        requester_id='observerctl-ds-wizard',
        requested_action='hydrate-dataset',
    )
    if str(packet.get('decision', 'no-go')).strip().lower() != 'go':
        summary = str(packet.get('summary', '') or '').strip()
        raise FileNotFoundError(summary or 'approved dataset selector could not be resolved')

    manifest_path = _resolve_existing_project_path(str(packet.get('dataset_manifest_path', '') or '').strip())
    if manifest_path is None:
        raise FileNotFoundError('resolved dataset manifest path is missing')

    state = _ds_wizard_hydrate_dataset_manifest(state, manifest_path)
    for key in ('dataset_manifest', 'features_csv', 'labels_csv'):
        if key in state.hydrated_from:
            state.hydrated_from[key] = 'librarian_dataset'

    dataset_meta = packet.get('dataset', {}) if isinstance(packet.get('dataset', {}), dict) else {}
    _ds_wizard_apply_context_metadata(
        state,
        dataset_meta.get('source', packet.get('source', '')),
        dataset_meta.get('mode', packet.get('mode', '')),
        hydrated_from='librarian_dataset',
    )
    dataset_label = str(dataset_meta.get('display_name', '') or dataset_meta.get('entry_id', '') or token).strip()
    access_class = str(packet.get('release_mode', dataset_meta.get('access_class', 'local')) or 'local').strip()
    lines = [
        'approved dataset ready: {0}'.format(dataset_label),
        '- selector: {0}'.format(str(dataset_meta.get('run_id', '') or dataset_meta.get('entry_id', '') or token).strip()),
        '- access: {0}'.format(access_class),
        '- manifest: {0}'.format(_ds_wizard_short_path(str(manifest_path))),
        '- fields: dataset_manifest, features_csv, labels_csv',
    ]
    if access_class == 'protected-source':
        lines.append('- delegated release receipts were recorded for this hydration')
        receipt_path = str(((packet.get('artifacts', {}) if isinstance(packet.get('artifacts', {}), dict) else {}).get('dataset_access_release_receipt_json', '')) or '').strip()
        if receipt_path:
            lines.append('- release receipt: {0}'.format(_ds_wizard_short_path(receipt_path)))
    else:
        lines.append('- delegated release not required for this approved local dataset')
    lines.append('next: validate now or continue filling the remaining wizard fields.')

    state.last_action = 'hydrate:librarian_dataset'
    _ds_wizard_set_transient_lines(state, lines)
    return state


def _ds_wizard_hydrate_dataset_manifest(state: _DSWizardState, manifest_path: Path) -> _DSWizardState:
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('dataset manifest is not a JSON object')
    _ds_wizard_clear_context_display(state)
    state.values['dataset_manifest'] = str(manifest_path)
    features_ref = str(payload.get('features_csv', '') or '').strip()
    if features_ref:
        features_path = _resolve_existing_reference_path(features_ref, manifest_path.parent)
        state.values['features_csv'] = str(features_path or features_ref).strip()
        state.hydrated_from['features_csv'] = 'dataset_manifest'
    labels_ref = str(payload.get('labels_csv', '') or '').strip()
    if labels_ref:
        labels_path = _resolve_existing_reference_path(labels_ref, manifest_path.parent)
        state.values['labels_csv'] = str(labels_path or labels_ref).strip()
        state.hydrated_from['labels_csv'] = 'dataset_manifest'
    state.hydrated_from['dataset_manifest'] = 'dataset_manifest'
    state.last_action = 'hydrate:dataset_manifest'
    _ds_wizard_set_transient_lines(
        state,
        [
            'hydrated from dataset manifest: {0}'.format(_ds_wizard_short_path(str(manifest_path))),
            'loaded fields: dataset_manifest, features_csv, labels_csv',
        ],
    )
    return state


def _ds_wizard_hydrate_train_manifest(state: _DSWizardState, manifest_path: Path) -> _DSWizardState:
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('train manifest is not a JSON object')
    _ds_wizard_clear_context_display(state)
    state.values['train_manifest'] = str(manifest_path)
    state.hydrated_from['train_manifest'] = 'train_manifest'
    dataset_manifest_ref = str(payload.get('dataset_manifest_path', '') or '').strip()
    if dataset_manifest_ref:
        dataset_manifest_path = _resolve_existing_reference_path(dataset_manifest_ref, manifest_path.parent)
        state.values['dataset_manifest'] = str(dataset_manifest_path or dataset_manifest_ref).strip()
        state.hydrated_from['dataset_manifest'] = 'train_manifest'
    model_path_ref = str(payload.get('model_path', '') or '').strip()
    if model_path_ref:
        model_path = _resolve_existing_reference_path(model_path_ref, manifest_path.parent)
        state.values['model_path'] = str(model_path or model_path_ref).strip()
        state.hydrated_from['model_path'] = 'train_manifest'
    if str(payload.get('model_type', '')).strip():
        state.values['model_type'] = str(payload.get('model_type')).strip()
        state.hydrated_from['model_type'] = 'train_manifest'
    state.last_action = 'hydrate:train_manifest'
    _ds_wizard_set_transient_lines(
        state,
        [
            'hydrated from train manifest: {0}'.format(_ds_wizard_short_path(str(manifest_path))),
            'loaded fields: train_manifest, dataset_manifest, model_path, model_type',
        ],
    )
    return state


def _ds_wizard_hydrate_model_path(state: _DSWizardState, model_path: Path) -> _DSWizardState:
    state.values['model_path'] = str(model_path)
    state.hydrated_from['model_path'] = 'model_path'
    state.last_action = 'hydrate:model_path'
    _ds_wizard_set_transient_lines(state, ['model artifact linked: {0}'.format(_ds_wizard_short_path(str(model_path)))])
    return state


def _ds_wizard_hydrate_baseline_analysis(state: _DSWizardState, packet_path: Path) -> _DSWizardState:
    payload = json.loads(packet_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('baseline analysis packet is not a JSON object')
    _ds_wizard_clear_context_display(state)
    state.values['baseline_analysis_packet'] = str(packet_path)
    state.hydrated_from['baseline_analysis_packet'] = 'baseline_analysis'
    if str(payload.get('baseline_window_id', '')).strip():
        state.values['baseline_window_id'] = str(payload.get('baseline_window_id')).strip()
        state.hydrated_from['baseline_window_id'] = 'baseline_analysis'
    state.last_action = 'hydrate:baseline_analysis'
    _ds_wizard_set_transient_lines(
        state,
        [
            'baseline context attached: {0}'.format(_ds_wizard_short_path(str(packet_path))),
            'loaded fields: baseline_analysis_packet, baseline_window_id',
        ],
    )
    return state


def _ds_wizard_hydrate_run_ledger(state: _DSWizardState, ledger_path: Path) -> _DSWizardState:
    payload = json.loads(ledger_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('run ledger is not a JSON object')
    _ds_wizard_clear_context_display(state)

    identity = payload.get('identity', {}) if isinstance(payload.get('identity', {}), dict) else {}
    context = payload.get('context', {}) if isinstance(payload.get('context', {}), dict) else {}
    constraints = context.get('constraints', {}) if isinstance(context.get('constraints', {}), dict) else {}
    data = payload.get('data', {}) if isinstance(payload.get('data', {}), dict) else {}
    model = payload.get('model', {}) if isinstance(payload.get('model', {}), dict) else {}

    state.run_ledger_path = str(ledger_path)

    run_id = str(identity.get('run_id', '') or '').strip()
    if run_id:
        state.values['run_id'] = run_id
        state.hydrated_from['run_id'] = 'run_ledger'

    max_fpr = constraints.get('max_fpr')
    if max_fpr not in ('', None):
        state.values['max_fpr'] = _ds_wizard_coerce_value(_ds_wizard_field_map()['max_fpr'], max_fpr)
        state.hydrated_from['max_fpr'] = 'run_ledger'

    dataset_manifest_text = str(data.get('dataset_manifest', '') or '').strip()
    if dataset_manifest_text:
        dataset_manifest_path = _resolve_existing_reference_path(dataset_manifest_text, ledger_path.parent)
        state.values['dataset_manifest'] = str(dataset_manifest_path or dataset_manifest_text)
        state.hydrated_from['dataset_manifest'] = 'run_ledger'
        if dataset_manifest_path is not None:
            try:
                _ds_wizard_hydrate_dataset_manifest(state, dataset_manifest_path)
            except Exception:
                pass

    features_csv_text = str(data.get('features_csv', '') or '').strip()
    if features_csv_text:
        features_csv_path = _resolve_existing_reference_path(features_csv_text, ledger_path.parent)
        state.values['features_csv'] = str(features_csv_path or features_csv_text)
        state.hydrated_from['features_csv'] = 'run_ledger'

    labels_csv_text = str(data.get('labels_csv', '') or '').strip()
    if labels_csv_text:
        labels_csv_path = _resolve_existing_reference_path(labels_csv_text, ledger_path.parent)
        state.values['labels_csv'] = str(labels_csv_path or labels_csv_text)
        state.hydrated_from['labels_csv'] = 'run_ledger'

    model_source_text = str(model.get('source', '') or '').strip()
    if model_source_text:
        model_source_path = _resolve_existing_reference_path(model_source_text, ledger_path.parent)
        state.values['model_path'] = str(model_source_path or model_source_text)
        state.hydrated_from['model_path'] = 'run_ledger'

    state.last_action = 'hydrate:run_ledger'
    _ds_wizard_set_transient_lines(
        state,
        [
            'historical evaluation context loaded: {0}'.format(_ds_wizard_short_path(str(ledger_path))),
            'loaded fields: run_id, max_fpr, dataset_manifest, features_csv, labels_csv, model_path',
        ],
    )
    return state


def _ds_wizard_draft_payload(state: _DSWizardState) -> Dict[str, Any]:
    return {
        'draft_schema': 'observerctl.ds.wizard.draft.v{0}'.format(_DS_WIZARD_DRAFT_VERSION),
        'draft_version': int(_DS_WIZARD_DRAFT_VERSION),
        'saved_at_utc': _utc_now(),
        'workflow': str(state.workflow or ''),
        'active_page': str(state.active_page or 'landing'),
        'active_group': str(state.active_group or ''),
        'active_section': str(state.active_section or 'flow'),
        'source': str(state.source or 'sim'),
        'mode': str(state.mode or 'watch'),
        'values': dict(state.values),
        'hydrated_from': dict(state.hydrated_from),
        'run_ledger_path': str(state.run_ledger_path or ''),
    }


def _ds_wizard_draft_ref_display(draft_path: Path) -> str:
    slot_id = _ds_wizard_draft_slot_id(draft_path)
    display = _ds_wizard_short_path(str(draft_path))
    try:
        resolved = draft_path.resolve()
        root = _ds_wizard_draft_root().resolve()
        if slot_id > 0 and resolved.parent == root:
            return '{0} ({1})'.format(_ds_wizard_draft_slot_label(slot_id), display)
    except Exception:
        pass
    return display


def _ds_wizard_matches_preview(matches: List[Dict[str, Any]]) -> str:
    labels: List[str] = []
    for row in matches[:4]:
        if not isinstance(row, dict):
            continue
        label = str(row.get('display_name', '') or row.get('selector_token', '') or row.get('entry_id', '')).strip()
        idx = int(row.get('index', 0) or 0)
        if idx > 0:
            label = '{0}:{1}'.format(idx, label or row.get('entry_id', ''))
        if label:
            labels.append(label)
    return ', '.join(labels)


def _ds_wizard_resolve_saved_entry(entries: List[Dict[str, Any]], selector: str, label: str) -> Dict[str, Any]:
    resolved = _ds_resolve_selector_entry(entries, selector)
    status = str(resolved.get('status', 'missing') or 'missing').strip().lower()
    if status == 'ok':
        return dict(resolved.get('entry', {}) or {})
    if status == 'ambiguous':
        matches = resolved.get('matches', []) if isinstance(resolved.get('matches', []), list) else []
        preview = _ds_wizard_matches_preview(matches)
        if preview:
            raise ValueError('{0} selector is ambiguous: {1}'.format(label, preview))
        raise ValueError('{0} selector is ambiguous'.format(label))
    raise FileNotFoundError('saved {0} selector could not be resolved'.format(label))


def _ds_wizard_hydrate_train_reference(state: _DSWizardState, train_ref: str) -> _DSWizardState:
    token = str(train_ref or '').strip()
    if not token:
        raise ValueError('train reference is required')

    direct_path = _resolve_existing_project_path(token)
    if direct_path is not None:
        return _ds_wizard_hydrate_train_manifest(state, direct_path)

    entry = _ds_wizard_resolve_saved_entry(_ds_saved_train_entries(), token, 'train')
    resolver = entry.get('resolver', {}) if isinstance(entry.get('resolver', {}), dict) else {}
    train_manifest_path = _resolve_existing_project_path(str(resolver.get('train_manifest_path', '') or '').strip())
    if train_manifest_path is None:
        raise FileNotFoundError('resolved train manifest path is missing')

    state = _ds_wizard_hydrate_train_manifest(state, train_manifest_path)
    for key in ('train_manifest', 'dataset_manifest', 'model_path', 'model_type'):
        if key in state.hydrated_from:
            state.hydrated_from[key] = 'saved_train'
    _ds_wizard_apply_context_metadata(
        state,
        entry.get('source', ''),
        entry.get('mode', ''),
        hydrated_from='saved_train',
    )
    dataset_manifest_ref = str(resolver.get('dataset_manifest_path', '') or state.values.get('dataset_manifest', '') or '').strip()
    model_path_ref = str(resolver.get('model_path', '') or state.values.get('model_path', '') or '').strip()
    lines = [
        'saved train ready: {0}'.format(str(entry.get('display_name', '') or entry.get('selector_token', '') or token).strip()),
        '- selector: {0}'.format(str(entry.get('selector_token', '') or entry.get('run_id', '') or token).strip()),
        '- train manifest: {0}'.format(_ds_wizard_short_path(str(train_manifest_path))),
    ]
    if dataset_manifest_ref:
        lines.append('- dataset manifest: {0}'.format(_ds_wizard_short_path(dataset_manifest_ref)))
    if model_path_ref:
        lines.append('- model artifact: {0}'.format(_ds_wizard_short_path(model_path_ref)))
    lines.append('next: validate now or continue filling the remaining wizard fields.')
    state.last_action = 'hydrate:saved_train'
    _ds_wizard_set_transient_lines(state, lines)
    return state


def _ds_wizard_hydrate_baseline_reference(state: _DSWizardState, baseline_ref: str) -> _DSWizardState:
    token = str(baseline_ref or '').strip()
    if not token:
        raise ValueError('baseline reference is required')

    direct_path = _resolve_existing_project_path(token)
    if direct_path is not None:
        return _ds_wizard_hydrate_baseline_analysis(state, direct_path)

    entry = _ds_wizard_resolve_saved_entry(_ds_saved_baseline_entries(state.source, state.mode), token, 'baseline')
    resolver = entry.get('resolver', {}) if isinstance(entry.get('resolver', {}), dict) else {}
    baseline_path = _resolve_existing_project_path(str(resolver.get('baseline_analysis_packet', '') or '').strip())
    if baseline_path is None:
        raise FileNotFoundError('resolved baseline packet path is missing')

    state = _ds_wizard_hydrate_baseline_analysis(state, baseline_path)
    for key in ('baseline_analysis_packet', 'baseline_window_id'):
        if key in state.hydrated_from:
            state.hydrated_from[key] = 'saved_baseline'
    _ds_wizard_apply_context_metadata(
        state,
        entry.get('source', state.source),
        entry.get('mode', state.mode),
        hydrated_from='saved_baseline',
    )
    lines = [
        'saved baseline ready: {0}'.format(str(entry.get('display_name', '') or entry.get('selector_token', '') or token).strip()),
        '- selector: {0}'.format(str(entry.get('selector_token', '') or token).strip()),
        '- source/mode: {0}/{1}'.format(str(entry.get('source', state.source) or state.source), str(entry.get('mode', state.mode) or state.mode)),
        '- packet: {0}'.format(_ds_wizard_short_path(str(baseline_path))),
    ]
    baseline_window_id = str(state.values.get('baseline_window_id', '') or '').strip()
    if baseline_window_id:
        lines.append('- baseline window: {0}'.format(baseline_window_id))
    lines.append('next: validate now or continue filling the remaining wizard fields.')
    state.last_action = 'hydrate:saved_baseline'
    _ds_wizard_set_transient_lines(state, lines)
    return state


def _ds_wizard_hydrate_run_reference(state: _DSWizardState, run_ref: str) -> _DSWizardState:
    token = str(run_ref or '').strip()
    if not token:
        raise ValueError('run reference is required')

    direct_path = _resolve_existing_project_path(token)
    if direct_path is not None:
        return _ds_wizard_hydrate_run_ledger(state, direct_path)

    entry = _ds_wizard_resolve_saved_entry(_ds_saved_run_entries(), token, 'run')
    resolver = entry.get('resolver', {}) if isinstance(entry.get('resolver', {}), dict) else {}
    run_json_path = _resolve_existing_project_path(str(resolver.get('run_json_path', '') or '').strip())
    if run_json_path is None:
        raise FileNotFoundError('resolved run ledger path is missing')

    state = _ds_wizard_hydrate_run_ledger(state, run_json_path)
    for key in ('run_id', 'max_fpr', 'dataset_manifest', 'features_csv', 'labels_csv', 'model_path'):
        if key in state.hydrated_from:
            state.hydrated_from[key] = 'saved_run'
    _ds_wizard_apply_context_metadata(
        state,
        entry.get('source', ''),
        entry.get('mode', ''),
        hydrated_from='saved_run',
    )
    lines = [
        'saved run ready: {0}'.format(str(entry.get('display_name', '') or entry.get('selector_token', '') or token).strip()),
        '- selector: {0}'.format(str(entry.get('selector_token', '') or entry.get('run_id', '') or token).strip()),
        '- run ledger: {0}'.format(_ds_wizard_short_path(str(run_json_path))),
        '- fields: run_id, max_fpr, dataset_manifest, features_csv, labels_csv, model_path',
        'next: validate now or continue filling the remaining wizard fields.',
    ]
    state.last_action = 'hydrate:saved_run'
    _ds_wizard_set_transient_lines(state, lines)
    return state


def _ds_wizard_resolve_draft_path(draft_ref: str, *, for_save: bool, state: Optional[_DSWizardState] = None) -> Path:
    token = str(draft_ref or '').strip()
    if for_save and token in ('', _DS_WIZARD_AUTO_DRAFT_TOKEN, 'auto', 'next', 'slot-next'):
        current_slot_id = _ds_wizard_current_draft_slot_id(state) if state is not None else 0
        if current_slot_id > 0:
            return _ds_wizard_draft_slot_path(current_slot_id)
        return _ds_wizard_draft_slot_path(_ds_wizard_next_draft_slot_id())
    if not for_save and not token:
        current_slot_id = _ds_wizard_current_draft_slot_id(state) if state is not None else 0
        if current_slot_id > 0:
            draft_path = _ds_wizard_draft_slot_path(current_slot_id)
            if draft_path.exists():
                return draft_path
        raise FileNotFoundError('draft reference is required')

    slot_id = _ds_wizard_parse_slot_token(token)
    if slot_id > 0:
        draft_path = _ds_wizard_draft_slot_path(slot_id)
        if not for_save and not draft_path.exists():
            raise FileNotFoundError('canonical draft slot is empty: {0}'.format(_ds_wizard_draft_slot_label(slot_id)))
        return draft_path

    if for_save:
        raw_path = Path(token)
        return raw_path if raw_path.is_absolute() else (_project_root() / raw_path)

    draft_path = _resolve_existing_project_path(token)
    if draft_path is not None:
        return draft_path
    raise FileNotFoundError('draft reference could not be resolved')


def _ds_wizard_save_draft_reference(state: _DSWizardState, draft_ref: str) -> _DSWizardState:
    draft_path = _ds_wizard_resolve_draft_path(draft_ref, for_save=True, state=state)
    return _ds_wizard_save_draft(state, draft_path)


def _ds_wizard_load_draft_reference(draft_ref: str, state: Optional[_DSWizardState] = None) -> _DSWizardState:
    draft_path = _ds_wizard_resolve_draft_path(draft_ref, for_save=False, state=state)
    return _ds_wizard_load_draft(draft_path)


def _ds_wizard_save_draft(state: _DSWizardState, draft_path: Path) -> _DSWizardState:
    _write_json_file(draft_path, _ds_wizard_draft_payload(state))
    state.draft_path = str(draft_path)
    state.last_action = 'draft:save'
    _ds_wizard_set_transient_lines(state, ['draft saved: {0}'.format(_ds_wizard_draft_ref_display(draft_path))])
    return state


def _ds_wizard_load_draft(draft_path: Path) -> _DSWizardState:
    payload = json.loads(draft_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('wizard draft is not a JSON object')

    workflow = str(payload.get('workflow', '') or '').strip()
    state = _ds_wizard_new_state(workflow if workflow in _DS_WIZARD_WORKFLOWS else '')
    values = payload.get('values', {}) if isinstance(payload.get('values', {}), dict) else {}
    field_map = _ds_wizard_field_map()
    for key, spec in field_map.items():
        if key not in values:
            continue
        try:
            state.values[key] = _ds_wizard_coerce_value(spec, values.get(key))
        except (TypeError, ValueError):
            continue

    if workflow in _DS_WIZARD_WORKFLOWS:
        state.workflow = workflow
        state.values['workflow'] = workflow

    state.source = _normalize_source(str(payload.get('source', state.source or 'sim')))
    mode = str(payload.get('mode', state.mode or 'watch')).strip().lower()
    if mode in MODES:
        state.mode = mode
    state.values['source'] = state.source
    state.values['mode'] = state.mode

    hydrated_from = payload.get('hydrated_from', {}) if isinstance(payload.get('hydrated_from', {}), dict) else {}
    state.hydrated_from = {str(key): str(value) for key, value in hydrated_from.items() if str(key).strip()}
    state.run_ledger_path = str(payload.get('run_ledger_path', '') or '').strip()
    state.draft_path = str(draft_path)

    active_section = str(payload.get('active_section', 'flow') or 'flow').strip().lower()
    if active_section in _ds_wizard_visible_sections(state):
        state.active_section = active_section
    else:
        state.active_section = 'flow'

    active_page = str(payload.get('active_page', '') or '').strip().lower()
    if active_page == 'landing':
        state.active_page = 'landing'
        state.active_group = ''
    else:
        _ds_wizard_sync_page_from_section(state)
    payload_group = str(payload.get('active_group', '') or '').strip().lower()
    if state.active_page != 'landing' and payload_group:
        state.active_group = payload_group

    state.last_action = 'draft:load'
    _ds_wizard_set_transient_lines(state, ['draft loaded: {0}'.format(_ds_wizard_draft_ref_display(draft_path))])
    return state


def _ds_wizard_latest_baseline_analysis_path(source: str, mode: str) -> Optional[Path]:
    index_path = get_calamum_data_dir() / 'observer_derived' / _normalize_source(source) / str(mode).strip().lower() / 'evidence' / 'index.jsonl'
    if not index_path.exists():
        return None
    for line in reversed(index_path.read_text(encoding='utf-8').splitlines()):
        text = str(line or '').strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if str(row.get('event', '')).strip().lower() != 'baseline_analysis':
            continue
        packet_path = Path(str(row.get('packet_path', '')).replace('/', os.sep))
        if packet_path.exists():
            return packet_path
    return None


def _ds_wizard_hydrate_latest_context(state: _DSWizardState) -> _DSWizardState:
    ssot = _load_state()
    state.source = str(ssot.get('source', state.source or 'sim'))
    state.mode = str(ssot.get('mode', state.mode or 'watch'))
    state.values['source'] = state.source
    state.values['mode'] = state.mode
    state.hydrated_from['source'] = 'latest_context'
    state.hydrated_from['mode'] = 'latest_context'
    _ds_wizard_clear_context_display(state)
    latest_baseline = _ds_wizard_latest_baseline_analysis_path(state.source, state.mode)
    if latest_baseline is not None:
        _ds_wizard_hydrate_baseline_analysis(state, latest_baseline)
    state.last_action = 'hydrate:latest_context'
    _ds_wizard_set_transient_lines(
        state,
        [
            'latest context loaded: source={0}, mode={1}'.format(state.source, state.mode),
            'baseline attached: {0}'.format(_ds_wizard_short_path(str(latest_baseline))) if latest_baseline is not None else 'baseline attached: none for the current source/mode',
            'dataset note: hydrate latest does not choose a dataset; use datasets or hydrate dataset <selector>.',
            'artifact note: use hydrate train or hydrate run for saved DS artifacts beyond baseline context.',
        ],
    )
    return state


def _ds_wizard_validation_issues(state: _DSWizardState) -> List[str]:
    issues: List[str] = []
    workflow = str(state.workflow or '').strip()
    if workflow not in _DS_WIZARD_WORKFLOWS:
        issues.append('workflow is required')
        state.validation_issues = issues
        return issues
    for spec in _DS_WIZARD_FIELD_SPECS:
        if workflow not in spec.workflows:
            continue
        value = _ds_wizard_field_value(state, spec.key)
        if workflow in spec.required_in and not _ds_wizard_has_value(value):
            issues.append('{0} is required'.format(spec.key))
            continue
        if not _ds_wizard_has_value(value):
            continue
        if spec.path_kind == 'file':
            values = value if isinstance(value, list) else [value]
            for raw in values:
                if not Path(str(raw)).exists():
                    issues.append('{0} does not exist: {1}'.format(spec.key, raw))
        if spec.choices and str(value) not in spec.choices:
            issues.append('{0} must be one of: {1}'.format(spec.key, ', '.join(spec.choices)))
    if workflow in ('build', 'run-pipeline'):
        split_present = _ds_wizard_split_values_present(state)
        split_complete = _ds_wizard_split_values_complete(state)
        if split_present and not split_complete:
            issues.append('split values must be set together')
        elif split_complete:
            try:
                total = float(state.values.get('split_train', 0.0)) + float(state.values.get('split_val', 0.0)) + float(state.values.get('split_test', 0.0))
                if abs(total - 1.0) > 0.001:
                    issues.append('split ratios must sum to 1.0')
            except (TypeError, ValueError):
                issues.append('split ratios must be numeric')
    state.validation_issues = issues
    return issues


def _ds_wizard_decision_state(state: _DSWizardState) -> str:
    return 'ready' if len(_ds_wizard_validation_issues(state)) == 0 else 'needs-input'


def _ds_wizard_preview_run_id(state: _DSWizardState) -> str:
    from analysis._util import sanitize_run_id

    token = ''
    if _ds_wizard_run_id_override_active(state):
        token = sanitize_run_id(str(state.values.get('run_id', '') or '').strip())
    return token or 'auto-run-id'


def _ds_wizard_output_preview(state: _DSWizardState) -> Dict[str, Any]:
    from analysis._util import canonical_ds_workflow_name, default_analysis_dir, normalize_repo_or_absolute_path

    workflow = canonical_ds_workflow_name(str(state.workflow or '').strip())
    if not workflow or workflow == 'run':
        return {}

    project_root = _project_root()
    run_id = _ds_wizard_preview_run_id(state)
    analysis_root = default_analysis_dir(Path(__file__))
    canonical_run_root = analysis_root / 'runs' / workflow / run_id
    preview: Dict[str, Any] = {
        'workflow': workflow,
        'run_id': run_id,
        'canonical_run_root': normalize_repo_or_absolute_path(canonical_run_root, project_root),
        'effective_policy': 'canonical-default',
        'override_value': '',
        'effective_run_root': normalize_repo_or_absolute_path(canonical_run_root, project_root),
        'report_json': normalize_repo_or_absolute_path(canonical_run_root / 'report' / 'report.json', project_root),
        'report_md': normalize_repo_or_absolute_path(canonical_run_root / 'report' / 'report.md', project_root),
        'artifact_targets': [],
    }

    def _render_path(path: Path) -> str:
        return normalize_repo_or_absolute_path(path, project_root)

    if workflow == 'build':
        bundle, dataset_dir = _ds_prepare_bundle_for_artifact('build', str(state.values.get('out_dir', '')), 'dataset', ['datasets'], run_id=run_id)
        preview['override_value'] = str(state.values.get('out_dir', '') or '').strip()
        preview['effective_policy'] = 'power-override' if bundle.run_root_policy == 'explicit-override' else 'canonical-default'
        preview['effective_run_root'] = _render_path(bundle.run_root)
        preview['report_json'] = _render_path(bundle.run_root / 'report' / 'report.json')
        preview['report_md'] = _render_path(bundle.run_root / 'report' / 'report.md')
        preview['artifact_targets'] = [
            ('dataset dir', _render_path(dataset_dir)),
            ('dataset manifest', _render_path(dataset_dir / 'dataset_manifest.json')),
            ('features csv', _render_path(dataset_dir / 'features.csv')),
        ]
        return preview
    if workflow == 'train':
        bundle, model_dir = _ds_prepare_bundle_for_artifact('train', str(state.values.get('out_dir', '')), 'model', ['models'], run_id=run_id)
        preview['override_value'] = str(state.values.get('out_dir', '') or '').strip()
        preview['effective_policy'] = 'power-override' if bundle.run_root_policy == 'explicit-override' else 'canonical-default'
        preview['effective_run_root'] = _render_path(bundle.run_root)
        preview['report_json'] = _render_path(bundle.run_root / 'report' / 'report.json')
        preview['report_md'] = _render_path(bundle.run_root / 'report' / 'report.md')
        preview['artifact_targets'] = [
            ('model dir', _render_path(model_dir)),
            ('train manifest', _render_path(model_dir / 'train_manifest.json')),
            ('metrics path', _render_path(model_dir / 'metrics.json')),
        ]
        return preview
    if workflow == 'evaluate':
        bundle, evaluation_dir = _ds_prepare_bundle_for_artifact('evaluate', str(state.values.get('out_dir', '')), 'evaluation', ['eval'], run_id=run_id)
        preview['override_value'] = str(state.values.get('out_dir', '') or '').strip()
        preview['effective_policy'] = 'power-override' if bundle.run_root_policy == 'explicit-override' else 'canonical-default'
        preview['effective_run_root'] = _render_path(bundle.run_root)
        preview['report_json'] = _render_path(bundle.run_root / 'report' / 'report.json')
        preview['report_md'] = _render_path(bundle.run_root / 'report' / 'report.md')
        preview['artifact_targets'] = [
            ('evaluation dir', _render_path(evaluation_dir)),
            ('run json', _render_path(evaluation_dir / 'run.json')),
            ('run md', _render_path(evaluation_dir / 'run.md')),
        ]
        return preview
    if workflow == 'score':
        override_value = str(state.values.get('scores_out', '') or '').strip()
        target_out_file = Path(override_value) if override_value else (canonical_run_root / 'scoring' / 'scores.csv')
        if override_value:
            parent_name = target_out_file.parent.name.strip().lower()
            effective_run_root = target_out_file.parent.parent if parent_name in ('score', 'scores', 'scoring') else target_out_file.parent
            scoring_dir = target_out_file.parent
            preview['effective_policy'] = 'power-override'
        else:
            effective_run_root = canonical_run_root
            scoring_dir = effective_run_root / 'scoring'
        preview['override_value'] = override_value
        preview['effective_run_root'] = _render_path(effective_run_root)
        preview['report_json'] = _render_path(effective_run_root / 'report' / 'report.json')
        preview['report_md'] = _render_path(effective_run_root / 'report' / 'report.md')
        preview['artifact_targets'] = [
            ('scoring dir', _render_path(scoring_dir)),
            ('scores csv', _render_path(target_out_file)),
        ]
        return preview
    if workflow in ('demo', 'pipeline'):
        override_value = str(state.values.get('out_dir', '') or '').strip()
        effective_run_root = Path(override_value) if override_value else canonical_run_root
        preview['override_value'] = override_value
        preview['effective_policy'] = 'power-override' if override_value else 'canonical-default'
        preview['effective_run_root'] = _render_path(effective_run_root)
        preview['report_json'] = _render_path(effective_run_root / 'report' / 'report.json')
        preview['report_md'] = _render_path(effective_run_root / 'report' / 'report.md')
        artifact_targets: List[Tuple[str, str]] = [
            ('dataset dir', _render_path(effective_run_root / 'dataset')),
            ('models dir', _render_path(effective_run_root / 'models')),
            ('evaluation dir', _render_path(effective_run_root / 'evaluation')),
        ]
        if workflow == 'pipeline':
            artifact_targets.append(('scoring dir', _render_path(effective_run_root / 'scoring')))
        preview['artifact_targets'] = artifact_targets
        return preview
    return preview


def _ds_wizard_output_preview_lines(state: _DSWizardState) -> List[str]:
    workflow = str(state.workflow or '').strip()
    dataset_manifest = state.values.get('dataset_manifest')
    has_dataset = _ds_wizard_has_value(dataset_manifest)
    has_inputs = bool(state.values.get('input_paths'))

    preview = _ds_wizard_output_preview(state)
    if not preview:
        return ['choose a workflow first to preview the canonical DS output layout.']

    lines = _render_human_kv_rows(
        [
            ('Run root mode', 'power override' if preview.get('effective_policy') == 'power-override' else 'canonical'),
            ('Canonical run root', str(preview.get('canonical_run_root', ''))),
            ('Effective run root', str(preview.get('effective_run_root', ''))),
            ('Report JSON', str(preview.get('report_json', ''))),
            ('Report MD', str(preview.get('report_md', ''))),
        ],
        min_label_width=18,
        max_label_width=20,
        indent='  ',
    )
    override_value = str(preview.get('override_value', '') or '').strip()
    if override_value:
        lines.extend(_render_human_kv_rows([('Active override', override_value)], min_label_width=18, max_label_width=20, indent='  '))
    for label, value in preview.get('artifact_targets', []) if isinstance(preview.get('artifact_targets', []), list) else []:
        lines.extend(_render_human_kv_rows([(label, value)], min_label_width=18, max_label_width=20, indent='  '))
    if workflow in ('build', 'run-pipeline') and not has_inputs:
        lines.extend(_render_human_kv_rows([('Input status', 'choose telemetry inputs before execute.')], min_label_width=18, max_label_width=20, indent='  '))
    if workflow in ('train', 'evaluate', 'score') and not has_dataset:
        lines.extend(_render_human_kv_rows([('Dataset status', 'choose approved dataset before execute.')], min_label_width=18, max_label_width=20, indent='  '))
    if override_value:
        lines.extend(_render_human_kv_rows([('Override note', 'clear the override field to return to the canonical DS run/report spine.')], min_label_width=18, max_label_width=20, indent='  '))
    else:
        lines.extend(_render_human_kv_rows([('Override note', 'set out_dir <folder> or set scores_out <file> only when intentionally bypassing the canonical report lane.')], min_label_width=18, max_label_width=20, indent='  '))
    return lines


def _ds_wizard_command_preview(state: _DSWizardState) -> str:
    workflow = str(state.workflow or '').strip()
    if workflow == 'build':
        parts = ['observerctl', 'ds', 'build']
        for item in state.values.get('input_paths', []):
            parts.extend(['--input', str(item)])
        if _ds_wizard_has_value(state.values.get('out_dir')):
            parts.extend(['--out-dir', str(state.values.get('out_dir'))])
        parts.extend(['--seed', str(state.values.get('seed', 42))])
        parts.extend(_ds_wizard_split_cli_args(state))
        return ' '.join(parts)
    if workflow == 'train':
        parts = ['observerctl', 'ds', 'train', '--dataset', str(state.values.get('dataset_manifest', ''))]
        if _ds_wizard_has_value(state.values.get('out_dir')):
            parts.extend(['--out-dir', str(state.values.get('out_dir'))])
        parts.extend(['--model-type', str(state.values.get('model_type', 'supervised')), '--seed', str(state.values.get('seed', 42))])
        return ' '.join(parts)
    if workflow == 'evaluate':
        parts = ['observerctl', 'ds', 'evaluate', '--features-csv', str(state.values.get('features_csv', ''))]
        if _ds_wizard_has_value(state.values.get('labels_csv')):
            parts.extend(['--labels-csv', str(state.values.get('labels_csv'))])
        if _ds_wizard_has_value(state.values.get('dataset_manifest')):
            parts.extend(['--dataset-manifest', str(state.values.get('dataset_manifest'))])
        if _ds_wizard_has_value(state.values.get('out_dir')):
            parts.extend(['--out-dir', str(state.values.get('out_dir'))])
        if _ds_wizard_run_id_override_active(state):
            parts.extend(['--run-id', str(state.values.get('run_id'))])
        if _ds_wizard_has_value(state.values.get('model_path')):
            parts.extend(['--model-path', str(state.values.get('model_path'))])
        parts.extend(['--max-fpr', str(state.values.get('max_fpr', 0.01))])
        return ' '.join(parts)
    if workflow == 'score':
        parts = [
            'observerctl',
            'ds',
            'score',
            '--dataset', str(state.values.get('dataset_manifest', '')),
            '--model', str(state.values.get('train_manifest') or state.values.get('model_path', '')),
        ]
        if _ds_wizard_has_value(state.values.get('scores_out')):
            parts.extend(['--out-file', str(state.values.get('scores_out'))])
        return ' '.join(parts)
    if workflow == 'run-demo':
        parts = ['observerctl', 'ds', 'run', 'demo']
        if _ds_wizard_has_value(state.values.get('out_dir')):
            parts.extend(['--out-dir', str(state.values.get('out_dir'))])
        parts.extend(['--dataset-seed', str(state.values.get('dataset_seed', 123)), '--model-seed', str(state.values.get('model_seed', 42)), '--max-fpr', str(state.values.get('max_fpr', 0.01))])
        return ' '.join(parts)
    if workflow == 'run-pipeline':
        parts = ['observerctl', 'ds', 'run', 'pipeline']
        for item in state.values.get('input_paths', []):
            parts.extend(['--input', str(item)])
        if _ds_wizard_has_value(state.values.get('out_dir')):
            parts.extend(['--out-dir', str(state.values.get('out_dir'))])
        parts.extend([
            '--model-type', str(state.values.get('model_type', 'supervised')),
            '--seed', str(state.values.get('seed', 42)),
            '--max-fpr', str(state.values.get('max_fpr', 0.01)),
        ])
        parts.extend(_ds_wizard_split_cli_args(state))
        return ' '.join(parts)
    return 'observerctl ds <choose-workflow>'


def _ds_wizard_command_context_lines(state: _DSWizardState) -> List[str]:
    workflow = str(state.workflow or '').strip()
    if not workflow:
        return ['choose a workflow first to explain the command surface.']

    preview = _ds_wizard_output_preview(state)
    issues = _ds_wizard_validation_issues(state)
    lines: List[str] = ['workflow lane: {0}'.format(workflow)]

    if workflow in ('build', 'run-pipeline'):
        input_count = len(state.values.get('input_paths', []) if isinstance(state.values.get('input_paths', []), list) else [])
        lines.append('data staging: {0} telemetry input{1} currently seed the command preview'.format(input_count, '' if input_count == 1 else 's'))
    elif workflow in ('train', 'evaluate', 'score'):
        dataset_state = 'loaded' if _ds_wizard_has_value(state.values.get('dataset_manifest')) else 'pending'
        lines.append('dataset artifact: {0}'.format(dataset_state))

    if workflow in ('evaluate', 'score'):
        model_ready = _ds_wizard_has_value(state.values.get('model_path')) or _ds_wizard_has_value(state.values.get('train_manifest'))
        lines.append('model artifact: {0}'.format('loaded' if model_ready else 'pending'))
    elif workflow in ('train', 'run-pipeline'):
        lines.append('model family: {0}'.format(str(state.values.get('model_type', 'supervised') or 'supervised')))

    if workflow in ('evaluate', 'run-demo', 'run-pipeline'):
        lines.append('evaluation guard: max_fpr = {0}'.format(_ds_wizard_stringify_value(state.values.get('max_fpr', 0.01))))

    if preview:
        lines.append('report lane: {0}'.format('power override' if preview.get('effective_policy') == 'power-override' else 'canonical'))
        lines.append('run root: {0}'.format(str(preview.get('effective_run_root', ''))))

    lines.append('validation: {0}'.format('blocked until check passes' if issues else 'ready for execute after review'))
    return lines


def _ds_wizard_left_rail_rows(state: _DSWizardState) -> List[str]:
    model_type = str(state.values.get('model_type', '') or '').strip()
    family_label = model_type if model_type else 'none'
    return [
        'workflow: {0}'.format(_ds_wizard_workflow_label(state.workflow)),
        'status: {0}'.format(_style_readiness_value(_ds_wizard_decision_state(state))),
        'family: {0}'.format(family_label),
    ]


def _ds_wizard_right_pane_ops_rows(state: _DSWizardState) -> List[str]:
    dataset_manifest = state.values.get('dataset_manifest')
    if _ds_wizard_has_value(dataset_manifest):
        run_id = str(state.values.get('run_id', '') or '').strip()
        display_alias = _generate_short_alias(run_id) if run_id else ''
        dataset_label = display_alias if display_alias else _ds_wizard_short_path(str(dataset_manifest))
    else:
        dataset_label = 'none'

    rows = ['dataset: {0}'.format(dataset_label)]
    if dataset_label != 'none':
        source = str(state.source or 'sim').strip()
        mode = str(state.mode or 'watch').strip()
        max_fpr = state.values.get('max_fpr', 0.01)
        fpr_label = '{0:.2f}'.format(float(max_fpr)) if max_fpr is not None else '0.01'
        rows.extend([
            'state: {0}'.format(source),
            'mode: {0}'.format(mode),
            'FPR: {0}'.format(fpr_label),
        ])
    else:
        rows.extend(['', '', ''])

    return rows


def _ds_wizard_summary_rows(state: _DSWizardState) -> List[str]:
    rows = list(_ds_wizard_left_rail_rows(state))
    rows.extend(_ds_wizard_right_pane_ops_rows(state))

    if state.workflow:
        summary_fields: List[Tuple[str, bool]] = [
            ('input_paths', False),
            ('dataset_manifest', True),
            ('features_csv', True),
            ('labels_csv', True),
            ('out_dir', True),
            ('model_path', True),
            ('run_id', False),
            ('baseline_window_id', False),
        ]
        for key, shorten in summary_fields:
            value = state.values.get(key)
            if not _ds_wizard_has_value(value):
                continue
            if isinstance(value, list):
                rendered = _ds_wizard_stringify_value([_ds_wizard_short_path(str(item)) if shorten else str(item) for item in value])
            else:
                rendered = _ds_wizard_short_path(str(value)) if shorten else _ds_wizard_stringify_value(value)
            rows.append('{0}: {1}'.format(_ds_wizard_ui_label(key), rendered))

    if str(state.run_ledger_path or '').strip():
        rows.append('{0}: {1}'.format(_ds_wizard_ui_label('run_ledger'), _ds_wizard_short_path(str(state.run_ledger_path))))
    if str(state.draft_path or '').strip():
        rows.append('draft: {0}'.format(_ds_wizard_short_path(str(state.draft_path))))
    return rows


def _ds_wizard_landing_summary_rows(state: _DSWizardState) -> List[str]:
    rows = list(_ds_wizard_left_rail_rows(state))
    if not state.workflow:
        rows.append('summary: open configure to begin the guided workflow')
        return rows
    if len(_ds_wizard_validation_issues(state)) == 0:
        rows.append('summary: configuration is ready for review and run')
    else:
        rows.append('summary: configuration still has blockers before review and run')
    rows.append('guided workflow: configure opens the flow section and full left-hand menu')
    return rows


def _ds_wizard_path_label(state: _DSWizardState) -> str:
    if state.active_page == 'landing':
        return 'ds wizard > landing'
    if state.active_page == 'workflow':
        return 'ds wizard > workflow'
    if state.active_page == 'configure':
        return 'ds wizard > configure > {0}'.format(state.active_section)
    if state.active_page == 'review-run':
        return 'ds wizard > review and run > {0}'.format(state.active_section)
    if state.active_page == 'utilities':
        return 'ds wizard > command and utilities'
    return 'ds wizard > {0}'.format(state.active_section)


def _ds_wizard_render_path_line(state: _DSWizardState) -> str:
    label = _ds_wizard_path_label(state)
    prefix, separator, tail = label.rpartition(' > ')
    if separator:
        return 'path: {0}{1}{2}'.format(prefix, separator, style_heading(tail))
    return 'path: {0}'.format(style_heading(tail or label))


def _ds_wizard_clear_disabled() -> bool:
    value = str(os.getenv('OBSERVERCTL_DS_WIZARD_NO_CLEAR', '') or '').strip().lower()
    return value in ('1', 'true', 'yes', 'on')


def _ds_wizard_try_clear_terminal() -> bool:
    if _ds_wizard_clear_disabled():
        return False
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    command = 'cls' if os.name == 'nt' else 'clear'
    try:
        return os.system(command) == 0
    except Exception:
        return False


def _ds_wizard_frame_separator_lines(state: _DSWizardState) -> List[str]:
    title = 'next frame: {0}'.format(_ds_wizard_path_label(state))
    width = max(72, len(title) + 4)
    bar = '=' * width
    return [bar, title, bar]


def _ds_wizard_emit_interactive_frame(state: _DSWizardState, redraw_count: int) -> None:
    if int(redraw_count) > 0 and not _ds_wizard_try_clear_terminal():
        for line in _ds_wizard_frame_separator_lines(state):
            print(line)
    for line in _ds_wizard_render(state):
        print(line)
    if state.transient_view == 'educational':
        _ds_wizard_clear_transient_view(state)


def _ds_wizard_exit_packet(state: _DSWizardState, reason: str) -> Dict[str, Any]:
    packet = _ds_wizard_packet(state, interactive=True)
    packet['summary'] = 'DS wizard closed.'
    packet['suppress_human_emit'] = True
    packet['interactive_exit_reason'] = str(reason or 'exit')
    return packet


def _ds_wizard_get_terminal_width() -> int:
    try:
        import shutil
        return shutil.get_terminal_size((80, 24)).columns
    except Exception:
        return 80

def _ds_wizard_render(state: _DSWizardState) -> List[str]:
    width = _ds_wizard_get_terminal_width()
    if state.active_page == 'landing':
        return _ds_wizard_render_stacked(state)
        
    if width >= 100:
        return _ds_wizard_render_wide(state, width)
    elif width >= 80:
        return _ds_wizard_render_stacked(state)
    else:
        return _ds_wizard_render_narrow(state, width)

def _ds_wizard_build_pane(state: _DSWizardState) -> List[str]:
    lines: List[str] = []
    current_section = _ds_wizard_current_section(state)
    if current_section == 'flow':
        lines.append(_style_section_line('workflow setup'))
        for idx, workflow in enumerate(_DS_WIZARD_WORKFLOWS, start=1):
            marker = '*' if workflow == state.workflow else ' '
            lines.append(_style_choice_label('{0}. [{1}] '.format(idx, marker), workflow))
        menu_lines = _ds_wizard_render_menu_items(state, 'flow')
        if menu_lines:
            lines.extend(menu_lines)
        lines.append('')
        if not state.workflow:
            lines.append('next step: choose a workflow, then move through the left menu.')
        else:
            lines.append('next step: use the left menu or next/prev to edit the fields used by {0}.'.format(state.workflow))
        lines.append('')
        lines.extend(_ds_wizard_inline_guidance_lines(state, current_section))
    elif current_section in ('cmd', 'check', 'run', 'exit'):
        if current_section == 'cmd':
            lines.append(_style_section_line('command preview'))
            menu_lines = _ds_wizard_render_menu_items(state, current_section)
            if menu_lines:
                lines.extend(menu_lines)
                lines.append('')
            cmd_preview = _ds_wizard_command_preview(state)
            if len(cmd_preview) > 80:
                from textwrap import wrap
                lines.extend(wrap(cmd_preview, width=80, subsequent_indent='  '))
            else:
                lines.append(cmd_preview)
            lines.append('')
            lines.append(_style_section_line('execution map'))
            lines.extend(_ds_wizard_command_context_lines(state))
        elif current_section == 'check':
            lines.append(_style_section_line('validation'))
            issues = _ds_wizard_validation_issues(state)
            if not issues:
                lines.append('  {0}'.format(style_text('ready', 'positive')))
                lines.append('next step: open run and type execute to start the workflow.')
            else:
                for issue in issues:
                    lines.append('  - {0}'.format(issue))
                lines.append('next step: resolve the blockers above or hydrate saved context.')
        elif current_section == 'run':
            lines.append(_style_section_line('execute'))
            lines.append(_ds_wizard_command_preview(state))
            blocked = len(_ds_wizard_validation_issues(state)) > 0
            lines.append('blocked: {0}'.format(_style_blocked_value(blocked)))
            if blocked:
                lines.append('next step: type validate or open check before execute.')
            else:
                lines.append('next step: type execute to run now. A completion summary will print after the run.')
        else:
            lines.append('type exit to leave the wizard')
        guidance_lines = _ds_wizard_inline_guidance_lines(state, current_section)
        if guidance_lines:
            lines.append('')
            lines.extend(guidance_lines)
    else:
        menu_lines = _ds_wizard_render_menu_items(state, current_section)
        if current_section == 'report':
            lines.append(_style_section_line('report'))
            lines.extend(_ds_wizard_output_preview_lines(state))
        elif current_section == 'in':
            lines.append(_style_section_line('inputs and sources'))
        elif current_section == 'model':
            lines.append(_style_section_line('model context'))
        elif current_section == 'eval':
            lines.append(_style_section_line('evaluation controls'))
        else:
            lines.append(_style_section_line(current_section))
        if current_section != 'report' and menu_lines:
            lines.extend(menu_lines)
        guidance_lines = _ds_wizard_inline_guidance_lines(state, current_section)
        if guidance_lines:
            lines.append('')
            lines.extend(guidance_lines)
    return lines

def _ds_wizard_render_transient(state: _DSWizardState, lines: List[str]) -> None:
    if str(state.transient_view or '').strip():
        lines.append('')
        if state.transient_view == 'scope-help':
            lines.extend(_ds_wizard_scope_help_lines(state))
        elif state.transient_view == 'item-peek':
            lines.extend(_ds_wizard_item_peek_lines(state, state.transient_target))
        elif state.transient_view == 'picker':
            lines.extend(_ds_wizard_picker_lines(state, state.transient_target))
        elif state.transient_view == 'advanced-edit':
            lines.extend(_ds_wizard_advanced_override_lines(state, state.transient_target))
        elif state.transient_view == 'educational':
            lines.extend(_ds_wizard_transient_lines(state))

def _ds_wizard_render_wide(state: _DSWizardState, width: int) -> List[str]:
    page_sections = _ds_wizard_page_sections(state)
    current_section = _ds_wizard_current_section(state)
    
    left_rail_width = 25
    left_lines = [_style_section_title('ObserverCTL'), '']
    left_lines.extend(_ds_wizard_left_rail_rows(state))
    left_lines.append('')
    left_lines.append(_style_section_line('Menu'))
    for sec in page_sections:
        marker = '*' if sec == current_section else ' '
        left_lines.append(_style_choice_label(' [{0}] '.format(marker), _ds_wizard_section_display_label(sec)))
    
    right_lines = []
    right_lines.append(_ds_wizard_render_path_line(state))
    right_lines.append('')
    right_lines.extend(_ds_wizard_right_pane_ops_rows(state))
    right_lines.append('')
    right_lines.extend(_ds_wizard_build_pane(state))
    
    lines: List[str] = []
    max_len = max(len(left_lines), len(right_lines))
    for i in range(max_len):
        l = left_lines[i] if i < len(left_lines) else ''
        r = right_lines[i] if i < len(right_lines) else ''
        lines.append('{0} {1}'.format(ljust_ansi(l, left_rail_width), r).rstrip())
    
    action_line = _ds_wizard_action_line(state)
    lines.append('')
    if action_line:
        lines.append(action_line)
    _ds_wizard_render_transient(state, lines)
    return lines

def _ds_wizard_render_narrow(state: _DSWizardState, width: int) -> List[str]:
    # Placeholder for single-focus breadcrumb mode.
    return _ds_wizard_render_stacked(state)

def _ds_wizard_render_stacked(state: _DSWizardState) -> List[str]:
    page_sections = _ds_wizard_page_sections(state)
    lines: List[str] = []
    lines.append(_style_section_title('ObserverCTL DS Wizard'))
    lines.append(_ds_wizard_render_path_line(state))
    lines.append('')
    if state.active_page == 'landing':
        lines.extend(_ds_wizard_landing_summary_rows(state))
        lines.append('')
        lines.append(_style_section_line('home'))
        lines.append(_style_choice_label('1. ', 'configure'))
        lines.append(_style_choice_label('2. ', 'review and run'))
        lines.append(_style_choice_label('3. ', 'command and utilities'))
        lines.append(_style_choice_label('4. ', 'exit'))
        lines.append('')
        if not state.transient_view:
            lines.append('Type ? for general help, or ? <section> for detail.')
            lines.append('')
    else:
        lines.extend(_ds_wizard_left_rail_rows(state))
        lines.extend(_ds_wizard_right_pane_ops_rows(state))
        lines.append('')
        lines.extend(_ds_wizard_build_pane(state))
        lines.append('')
        if page_sections:
            lines.append('sections: {0}'.format(', '.join([_ds_wizard_section_display_label(sec) for sec in page_sections])))
        action_line = _ds_wizard_action_line(state)
        if action_line:
            lines.append(action_line)
    
    _ds_wizard_render_transient(state, lines)
    return lines

def _ds_wizard_attempt_execute(state: _DSWizardState) -> Dict[str, Any]:
    issues = _ds_wizard_validation_issues(state)
    if issues:
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'ds-wizard-execute',
            'command_family': 'ds',
            'command_path': 'observerctl ds wizard',
            'implementation_state': _DS_RUNTIME_STATE_WIZARD,
            'summary': 'Wizard execution remains blocked until validation passes.',
            'reason_codes': ['critical_check_failed:wizard_validation_blocked'],
            'validation_issues': issues,
            'command_preview': _ds_wizard_command_preview(state),
            'wizard_workflow': str(state.workflow or ''),
        }
    workflow = str(state.workflow or '').strip()
    try:
        if workflow == 'build':
            split_train, split_val, split_test = _ds_wizard_resolved_split_values(state)
            packet = _ds_build(
                input_paths=[Path(str(item)) for item in state.values.get('input_paths', [])],
                out_dir=str(state.values.get('out_dir', '')),
                seed=int(state.values.get('seed', 42)),
                split_train=split_train,
                split_val=split_val,
                split_test=split_test,
                max_lines_per_file=None,
            )
        elif workflow == 'train':
            packet = _ds_train(
                dataset=str(state.values.get('dataset_manifest', '')),
                out_dir=str(state.values.get('out_dir', '')),
                model_type=str(state.values.get('model_type', 'supervised')),
                seed=int(state.values.get('seed', 42)),
            )
        elif workflow == 'evaluate':
            packet = _ds_evaluate(
                features_csv=str(state.values.get('features_csv', '')),
                labels_csv=str(state.values.get('labels_csv', '')),
                dataset_manifest=str(state.values.get('dataset_manifest', '')),
                max_fpr=float(state.values.get('max_fpr', 0.01)),
                out_dir=str(state.values.get('out_dir', '')),
                run_id=str(state.values.get('run_id', '')) if _ds_wizard_run_id_override_active(state) else '',
                model_path=str(state.values.get('model_path', '')),
            )
        elif workflow == 'score':
            packet = _ds_score(
                dataset=str(state.values.get('dataset_manifest', '')),
                model=str(state.values.get('train_manifest') or state.values.get('model_path', '')),
                out_file=str(state.values.get('scores_out', '')),
            )
        elif workflow == 'run-demo':
            packet = _ds_run_demo(
                out_dir=str(state.values.get('out_dir', '')),
                dataset_seed=int(state.values.get('dataset_seed', 123)),
                model_seed=int(state.values.get('model_seed', 42)),
                max_fpr=float(state.values.get('max_fpr', 0.01)),
            )
        elif workflow == 'run-pipeline':
            split_train, split_val, split_test = _ds_wizard_resolved_split_values(state)
            packet = _ds_run_pipeline(
                input_paths=[Path(str(item)) for item in state.values.get('input_paths', [])],
                out_dir=str(state.values.get('out_dir', '')),
                model_type=str(state.values.get('model_type', 'supervised')),
                seed=int(state.values.get('seed', 42)),
                split_train=split_train,
                split_val=split_val,
                split_test=split_test,
                max_fpr=float(state.values.get('max_fpr', 0.01)),
            )
        else:
            return {
                'timestamp_utc': _utc_now(),
                'runtime_cli_surface': 'observerctl',
                'decision': 'no-go',
                'action': 'ds-wizard-execute',
                'command_family': 'ds',
                'command_path': 'observerctl ds wizard',
                'implementation_state': _DS_RUNTIME_STATE_WIZARD,
                'summary': 'Wizard execution could not start because the workflow is unknown.',
                'reason_codes': ['critical_check_failed:wizard_unknown_workflow'],
                'command_preview': _ds_wizard_command_preview(state),
                'wizard_workflow': workflow,
            }
    except Exception as exc:
        return {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'ds-wizard-execute',
            'command_family': 'ds',
            'command_path': 'observerctl ds wizard',
            'implementation_state': _DS_RUNTIME_STATE_WIZARD,
            'summary': 'Workflow execution failed before completion.',
            'reason_codes': ['critical_check_failed:wizard_execution_failed'],
            'command_preview': _ds_wizard_command_preview(state),
            'wizard_workflow': workflow,
            'error_detail': str(exc),
        }

    packet['command_preview'] = _ds_wizard_command_preview(state)
    packet['wizard_workflow'] = workflow
    report_context: Dict[str, Any] = {}
    for key in ('baseline_analysis_packet', 'baseline_window_id'):
        value = state.values.get(key)
        if _ds_wizard_has_value(value):
            report_context[key] = _ds_wizard_stringify_value(value)
    if _ds_wizard_run_id_override_active(state):
        report_context['run_id'] = _ds_wizard_stringify_value(state.values.get('run_id'))
    if report_context:
        packet['report_context'] = report_context
    return packet


def _ds_wizard_packet(state: _DSWizardState, interactive: bool = False) -> Dict[str, Any]:
    issues = _ds_wizard_validation_issues(state)
    return {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-wizard',
        'command_family': 'ds',
        'command_path': 'observerctl ds wizard',
        'implementation_state': _DS_RUNTIME_STATE_WIZARD,
        'summary': 'DS wizard is available with workflow-aware navigation, saved-artifact hydration, prior-run import, and draft persistence.',
        'workflow': str(state.workflow or ''),
        'current_page': str(state.active_page or 'landing'),
        'active_group': str(state.active_group or ''),
        'current_section': str(state.active_section or 'flow'),
        'visible_sections': _ds_wizard_visible_sections(state),
        'execution_state': 'blocked' if issues else 'ready',
        'validation_issues': issues,
        'command_preview': _ds_wizard_command_preview(state),
        'hydrated_from': dict(state.hydrated_from),
        'wizard_view': [] if interactive else _ds_wizard_render(state),
        'artifacts': {
            'dataset_manifest': str(state.values.get('dataset_manifest', '')),
            'train_manifest': str(state.values.get('train_manifest', '')),
            'model_path': str(state.values.get('model_path', '')),
            'baseline_analysis_packet': str(state.values.get('baseline_analysis_packet', '')),
            'run_ledger_path': str(state.run_ledger_path or ''),
            'draft_path': str(state.draft_path or ''),
        },
        'reason_codes': [],
    }


def _ds_wizard_apply_cli_seed(state: _DSWizardState, args: argparse.Namespace) -> _DSWizardState:
    load_draft_path = str(getattr(args, 'load_draft', '') or '').strip()
    if load_draft_path:
        state = _ds_wizard_load_draft_reference(load_draft_path, state=state)
    if str(getattr(args, 'workflow', '') or '').strip():
        _ds_wizard_set_value(state, 'workflow', getattr(args, 'workflow'))
    if bool(getattr(args, 'hydrate_latest_context', False)):
        _ds_wizard_hydrate_latest_context(state)
    dataset_path = str(getattr(args, 'hydrate_dataset', '') or '').strip()
    if dataset_path:
        _ds_wizard_hydrate_dataset_reference(state, dataset_path)
    train_path = str(getattr(args, 'hydrate_train', '') or '').strip()
    if train_path:
        _ds_wizard_hydrate_train_reference(state, train_path)
    model_path = str(getattr(args, 'hydrate_model', '') or '').strip()
    if model_path:
        _ds_wizard_hydrate_model_path(state, Path(model_path))
    baseline_path = str(getattr(args, 'hydrate_baseline_analysis', '') or '').strip()
    if baseline_path:
        _ds_wizard_hydrate_baseline_reference(state, baseline_path)
    run_path = str(getattr(args, 'hydrate_run', '') or '').strip()
    if run_path:
        _ds_wizard_hydrate_run_reference(state, run_path)
    for item in list(getattr(args, 'set_items', []) or []):
        text = str(item or '').strip()
        if '=' not in text:
            continue
        key, raw_value = text.split('=', 1)
        _ds_wizard_set_value(state, key.strip(), raw_value.strip())
    if str(getattr(args, 'section', '') or '').strip():
        _ds_wizard_open_section(state, getattr(args, 'section'))
    return state


def _ds_wizard_handle_command(state: _DSWizardState, command: str) -> Tuple[_DSWizardState, Optional[Dict[str, Any]], bool]:
    text = str(command or '').strip()
    lowered = text.lower()
    if not text:
        if str(state.transient_view or '').strip():
            return _ds_wizard_clear_transient_view(state), None, False
        return state, None, False
    if lowered in ('?', 'help'):
        return _ds_wizard_open_scope_help(state), None, False
    if lowered.startswith('? '):
        return _ds_wizard_open_item_peek(state, _ds_wizard_resolve_field_alias(text.split(' ', 1)[1])), None, False
    if lowered in ('close', 'dismiss'):
        return _ds_wizard_clear_transient_view(state), None, False
    if lowered == 'next':
        return _ds_wizard_move_section(state, 'next'), None, False
    if lowered in ('prev', 'back'):
        return _ds_wizard_move_section(state, 'prev'), None, False
    if lowered in ('home', 'landing'):
        return _ds_wizard_open_landing(state), None, False
    if lowered in ('validate', 'test'):
        issues = _ds_wizard_validation_issues(state)
        if issues:
            _ds_wizard_set_transient_lines(
                state,
                ['validation: blocked'] + ['- {0}'.format(issue) for issue in issues] + ['Use configure or hydrate commands to resolve the blockers.'],
            )
        else:
            _ds_wizard_set_transient_lines(state, ['validation: ready', 'Open run and type execute to start the workflow.'])
        return state, None, False
    if lowered == 'open':
        _ds_wizard_set_transient_lines(state, ["Use 'open <section>' to navigate to a section (for example: open run)."])
        return state, None, False
    if lowered in ('ls', 'list', 'sections'):
        _ds_wizard_set_transient_lines(state, ["Available sections are shown on screen. Use 'open <section>' to navigate."])
        return state, None, False
    if lowered in ('datasets', 'dataset list', 'list datasets'):
        return _ds_wizard_open_picker(state, 'dataset'), None, False
    if lowered in ('trained', 'train list', 'list trained'):
        return _ds_wizard_open_picker(state, 'train'), None, False
    if lowered in ('runs', 'run list', 'list runs'):
        return _ds_wizard_open_picker(state, 'run'), None, False
    if lowered in ('baselines', 'baseline list', 'list baselines'):
        return _ds_wizard_open_picker(state, 'baseline'), None, False
    if lowered in ('drafts', 'draft list', 'list drafts'):
        return _ds_wizard_open_picker(state, 'draft-load'), None, False
    if lowered == 'save draft':
        return _ds_wizard_save_draft_reference(state, ''), None, False
    if lowered.startswith('save draft '):
        draft_arg = text[len('save draft '):].strip()
        if draft_arg:
            return _ds_wizard_save_draft_reference(state, draft_arg), None, False
    if lowered == 'load draft':
        try:
            return _ds_wizard_load_draft_reference('', state=state), None, False
        except Exception:
            _ds_wizard_set_transient_lines(state, ['load draft needs a slot or file path. Use drafts to review canonical slots.'])
            return state, None, False
    if lowered.startswith('load draft '):
        draft_arg = text[len('load draft '):].strip()
        if draft_arg:
            return _ds_wizard_load_draft_reference(draft_arg, state=state), None, False
    if lowered == 'cmd':
        return _ds_wizard_open_section(state, 'cmd'), None, False
    if lowered == 'execute':
        packet = _ds_wizard_attempt_execute(state)
        if str(packet.get('decision', 'no-go')).strip().lower() != 'go':
            issues = packet.get('validation_issues', []) if isinstance(packet.get('validation_issues', []), list) else []
            _ds_wizard_set_transient_lines(
                state,
                ['executing blocked:'] + ['- {0}'.format(issue) for issue in issues] + ['Open check or configure to resolve the blockers, then try execute again.'],
            )
            return state, None, False
        return state, packet, True
    if lowered in ('exit', 'q', 'quit'):
        return state, _ds_wizard_exit_packet(state, 'command'), True
    if lowered in _DS_WIZARD_WORKFLOWS:
        _ds_wizard_set_value(state, 'workflow', lowered)
        return state, None, False
    if lowered in ('configure', 'review', 'review and run', 'review-run', 'command', 'command preview', 'command and utilities', 'utilities'):
        return _ds_wizard_open_top_level_choice(state, lowered), None, False
    if lowered in _ds_wizard_visible_sections(state):
        return _ds_wizard_open_section(state, lowered), None, False
    if lowered.startswith('open '):
        target = lowered.split(' ', 1)[1]
        routed = _ds_wizard_open_top_level_choice(state, target)
        if routed is not state or target in ('landing', 'home', 'configure', 'review', 'review and run', 'review-run', 'command', 'command preview', 'command and utilities', 'utilities'):
            return routed, None, False
        return _ds_wizard_open_section(state, target), None, False
    if lowered.startswith('set '):
        payload = text.split(' ', 2)
        if len(payload) >= 3:
            target_key = _ds_wizard_resolve_field_alias(payload[1])
            if target_key in ('source', 'mode'):
                _ds_wizard_set_transient_lines(
                    state,
                    [
                        '{0} overrides live behind advanced.'.format(target_key.replace('_', ' ')),
                        'open advanced from flow and choose the numbered override instead of setting it directly.',
                    ],
                )
                return state, None, False
            if target_key in _DS_WIZARD_ADVANCED_EDIT_KEYS:
                if not (state.transient_view == 'advanced-edit' and str(state.transient_target or '').strip().lower() == target_key):
                    _ds_wizard_set_transient_lines(
                        state,
                        [
                            '{0} is locked behind advanced.'.format(_ds_wizard_ui_label(target_key)),
                            'open advanced from flow, choose the matching override lane, then use set {0} <value>.'.format(target_key),
                        ],
                    )
                    return state, None, False
            if target_key in _DS_WIZARD_SPLIT_KEYS:
                try:
                    train_value, test_value = _ds_wizard_parse_split_values(payload[2])
                except ValueError as exc:
                    _ds_wizard_set_transient_lines(state, [str(exc)])
                    return state, None, False
                return _ds_wizard_apply_split_values(state, train_value, test_value), None, False
            return _ds_wizard_set_value(state, target_key, payload[2]), None, False
    if lowered.startswith('clear '):
        payload = text.split(' ', 1)
        if len(payload) == 2:
            target_key = _ds_wizard_resolve_field_alias(payload[1])
            if target_key in ('source', 'mode'):
                _ds_wizard_set_transient_lines(
                    state,
                    [
                        '{0} overrides live behind advanced.'.format(target_key.replace('_', ' ')),
                        'open advanced from flow and use the numbered picker instead of clearing it directly.',
                    ],
                )
                return state, None, False
            if target_key in _DS_WIZARD_ADVANCED_EDIT_KEYS and not (state.transient_view == 'advanced-edit' and str(state.transient_target or '').strip().lower() == target_key):
                _ds_wizard_set_transient_lines(
                    state,
                    [
                        '{0} is locked behind advanced.'.format(_ds_wizard_ui_label(target_key)),
                        'open advanced from flow, choose the matching override lane, then clear {0}.'.format(target_key),
                    ],
                )
                return state, None, False
            return _ds_wizard_apply_reselection(state, target_key, 'clear'), None, False
    if lowered.startswith('keep '):
        payload = text.split(' ', 1)
        if len(payload) == 2:
            return _ds_wizard_apply_reselection(state, _ds_wizard_resolve_field_alias(payload[1]), 'keep'), None, False
    if lowered.startswith('hydrate '):
        payload = text.split(' ', 2)
        if len(payload) >= 2:
            target = payload[1]
            arg = payload[2] if len(payload) > 2 else ''
            if target == 'dataset' and arg:
                try:
                    return _ds_wizard_hydrate_dataset_reference(state, arg), None, False
                except Exception as exc:
                    _ds_wizard_set_transient_lines(state, ['hydrate dataset failed: {0}'.format(str(exc) or arg)])
                    return state, None, False
            if target == 'train' and arg:
                try:
                    return _ds_wizard_hydrate_train_reference(state, arg), None, False
                except Exception as exc:
                    _ds_wizard_set_transient_lines(state, ['hydrate train failed: {0}'.format(str(exc) or arg)])
                    return state, None, False
            if target == 'model' and arg:
                try:
                    return _ds_wizard_hydrate_model_path(state, Path(arg)), None, False
                except Exception as exc:
                    _ds_wizard_set_transient_lines(state, ['hydrate model failed: {0}'.format(str(exc) or arg)])
                    return state, None, False
            if target == 'baseline' and arg:
                try:
                    return _ds_wizard_hydrate_baseline_reference(state, arg), None, False
                except Exception as exc:
                    _ds_wizard_set_transient_lines(state, ['hydrate baseline failed: {0}'.format(str(exc) or arg)])
                    return state, None, False
            if target == 'latest':
                return _ds_wizard_hydrate_latest_context(state), None, False
            if target == 'run' and arg:
                try:
                    return _ds_wizard_hydrate_run_reference(state, arg), None, False
                except Exception as exc:
                    _ds_wizard_set_transient_lines(state, ['hydrate run failed: {0}'.format(str(exc) or arg)])
                    return state, None, False
    if text.isdigit():
        if state.transient_view == 'picker':
            return _ds_wizard_apply_picker_selection(state, state.transient_target, text), None, False
        idx = int(text)
        if state.active_page == 'landing' and 1 <= idx <= len(_DS_WIZARD_LANDING_CHOICES):
            choice = _DS_WIZARD_LANDING_CHOICES[idx - 1][0]
            if choice == 'exit':
                return state, _ds_wizard_exit_packet(state, 'landing-choice'), True
            return _ds_wizard_open_top_level_choice(state, choice), None, False
        if state.active_section == 'flow' and 1 <= idx <= len(_DS_WIZARD_WORKFLOWS):
            return _ds_wizard_set_value(state, 'workflow', _DS_WIZARD_WORKFLOWS[idx - 1]), None, False
        menu_item = _ds_wizard_menu_item_by_index(state, text)
        if menu_item is not None:
            if menu_item.item_type != 'field':
                return _ds_wizard_activate_menu_item(state, menu_item), None, False
        spec = _ds_wizard_field_by_index(state, text)
        if spec is not None:
            if spec.key == 'split_train' and _ds_wizard_split_is_relevant(state):
                return _ds_wizard_prompt_split_values(state), None, False
            current_value = _ds_wizard_field_value(state, spec.key)
            display_label = _ds_wizard_ui_label(spec.key)
            if _ds_wizard_has_value(current_value):
                choice = input('{0} [{1}] -> keep / clear / new: '.format(display_label, _ds_wizard_stringify_value(current_value))).strip().lower()
                if choice == 'clear':
                    return _ds_wizard_apply_reselection(state, spec.key, 'clear'), None, False
                if choice == 'new':
                    new_value = input('{0} new value: '.format(display_label))
                    return _ds_wizard_apply_reselection(state, spec.key, 'new', new_value), None, False
                return _ds_wizard_apply_reselection(state, spec.key, 'keep'), None, False
            new_value = input('{0} value: '.format(display_label))
            return _ds_wizard_set_value(state, spec.key, new_value), None, False
    if state.transient_view == 'picker':
        return _ds_wizard_apply_picker_selection(state, state.transient_target, text), None, False
    _ds_wizard_set_transient_lines(state, ['unknown command: {0}'.format(text), 'Use ? for general help or ? <section> for detail.'])
    return state, None, False


def _ds_wizard(args: argparse.Namespace) -> Dict[str, Any]:
    state = _ds_wizard_new_state(str(getattr(args, 'workflow', '') or '').strip())
    state = _ds_wizard_apply_cli_seed(state, args)
    save_draft_path = str(getattr(args, 'save_draft', '') or '').strip()
    if save_draft_path:
        _ds_wizard_save_draft_reference(state, save_draft_path)
    if bool(getattr(args, 'execute', False)):
        return _ds_wizard_attempt_execute(state)
    interactive = bool(sys.stdin.isatty() and not bool(getattr(args, 'json', False)))
    if not interactive:
        return _ds_wizard_packet(state, interactive=False)
    redraw_count = 0
    while True:
        _ds_wizard_emit_interactive_frame(state, redraw_count)
        redraw_count += 1
        print()
        try:
            command = input('wizard> ')
        except (KeyboardInterrupt, EOFError):
            print()
            return _ds_wizard_exit_packet(state, 'interrupt')
        state, packet, should_exit = _ds_wizard_handle_command(state, command)
        if should_exit:
            return packet if isinstance(packet, dict) else _ds_wizard_exit_packet(state, 'fallback')


def _ds_default_analysis_dir() -> Path:
    from analysis._util import default_analysis_dir

    return default_analysis_dir(Path(__file__))


def _ds_artifact_strings(artifact_paths: Mapping[str, Optional[Path]]) -> Dict[str, str]:
    rendered: Dict[str, str] = {}
    for key, value in artifact_paths.items():
        rendered[str(key)] = str(value).replace('\\', '/') if value is not None else ''
    return rendered


def _ds_visual_artifact_paths(visual_state: Mapping[str, Any]) -> Dict[str, Path]:
    artifact_paths: Dict[str, Path] = {}
    if not isinstance(visual_state, Mapping):
        return artifact_paths
    for figure in list(visual_state.get('figures', []) or []):
        if not isinstance(figure, Mapping):
            continue
        figure_id = str(figure.get('id', '') or '').strip()
        figure_path = figure.get('path')
        if not figure_id or figure_path in ('', None):
            continue
        artifact_paths['{0}_png'.format(figure_id)] = Path(str(figure_path))
    return artifact_paths


def _ds_positive_prediction_count(counts: Any) -> int:
    if not isinstance(counts, Mapping):
        return 0
    if 'flagged' in counts:
        try:
            return int(float(counts.get('flagged', 0) or 0))
        except (TypeError, ValueError):
            return 0
    total = 0
    for key in ('tp', 'fp'):
        try:
            total += int(float(counts.get(key, 0) or 0))
        except (TypeError, ValueError):
            continue
    return int(total)


def _ds_total_prediction_count(counts: Any) -> int:
    if not isinstance(counts, Mapping):
        return 0
    if 'total' in counts:
        try:
            return int(float(counts.get('total', 0) or 0))
        except (TypeError, ValueError):
            return 0
    total = 0
    for key in ('tp', 'fp', 'tn', 'fn'):
        try:
            total += int(float(counts.get(key, 0) or 0))
        except (TypeError, ValueError):
            continue
    return int(total)


def _ds_optional_float(value: Any) -> Optional[float]:
    if value in ('', None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ds_prepare_bundle_for_artifact(
    workflow: str,
    out_dir: str,
    artifact_dir_name: str,
    aliases: List[str],
    run_id: str = '',
):
    from analysis._util import resolve_run_root_and_artifact_dir
    from analysis.report_pack import prepare_report_bundle

    explicit_path = Path(str(out_dir).strip()) if str(out_dir).strip() else None
    explicit_run_root, explicit_artifact_dir = resolve_run_root_and_artifact_dir(explicit_path, artifact_dir_name, aliases)
    bundle = prepare_report_bundle(
        Path(__file__),
        workflow,
        explicit_run_root=explicit_run_root,
        run_id=str(run_id or '').strip(),
    )
    target_dir = explicit_artifact_dir if explicit_artifact_dir is not None else bundle.artifact_dirs.get(artifact_dir_name, bundle.run_root / artifact_dir_name)
    bundle.artifact_dirs[artifact_dir_name] = target_dir
    return bundle, target_dir


def _ds_prepare_bundle_for_score(out_file: str):
    from analysis.report_pack import prepare_report_bundle

    explicit_out_file = Path(str(out_file).strip()) if str(out_file).strip() else None
    explicit_run_root = None
    target_out_file = None
    target_scoring_dir = None
    if explicit_out_file is not None:
        parent_name = explicit_out_file.parent.name.strip().lower()
        explicit_run_root = explicit_out_file.parent.parent if parent_name in ('score', 'scores', 'scoring') else explicit_out_file.parent
        target_out_file = explicit_out_file
        target_scoring_dir = explicit_out_file.parent
    bundle = prepare_report_bundle(Path(__file__), 'score', explicit_run_root=explicit_run_root)
    if target_out_file is None:
        target_scoring_dir = bundle.artifact_dirs.get('scoring', bundle.run_root / 'scoring')
        target_out_file = target_scoring_dir / 'scores.csv'
    if target_scoring_dir is None:
        target_scoring_dir = bundle.run_root / 'scoring'
    bundle.artifact_dirs['scoring'] = target_scoring_dir
    return bundle, target_out_file


def _ds_finalize_run_packet(
    packet: Dict[str, Any],
    *,
    bundle,
    artifact_paths: Mapping[str, Optional[Path]],
    context: Optional[Dict[str, Any]] = None,
    lineage: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from calamum_librarian import refresh_librarian_dataset_catalog_from_run_manifest
    from analysis.report_aggregate import append_ds_run_index, publication_eligibility_reasons, refresh_tracked_ds_publication
    from analysis.report_pack import write_report_bundle

    final_packet = dict(packet)
    final_packet['run_id'] = str(bundle.run_id)
    final_packet['artifacts'] = dict(final_packet.get('artifacts', {}))

    report_bundle = write_report_bundle(
        project_anchor=Path(__file__),
        bundle=bundle,
        packet=final_packet,
        artifact_paths=artifact_paths,
        context=context or {},
        lineage=lineage or {},
    )
    aggregate_state = append_ds_run_index(
        project_anchor=Path(__file__),
        manifest_payload=report_bundle['manifest'],
    )
    dataset_refresh = refresh_librarian_dataset_catalog_from_run_manifest(
        project_anchor=_project_anchor(),
        manifest_payload=report_bundle['manifest'],
    )
    publication_state = {
        'decision': 'skipped',
        'reason_codes': publication_eligibility_reasons(
            project_anchor=Path(__file__),
            manifest_payload=report_bundle['manifest'],
        ),
    }
    if len(list(publication_state.get('reason_codes', []))) == 0:
        publication_state = refresh_tracked_ds_publication(
            project_anchor=Path(__file__),
            current_manifest_payload=report_bundle['manifest'],
        )

    final_packet['artifacts'].update({
        'run_root': report_bundle['paths']['run_root'],
        'report_json': report_bundle['paths']['report_json'],
        'report_md': report_bundle['paths']['report_md'],
        'report_manifest_json': report_bundle['paths']['manifest_json'],
        'ds_run_index_jsonl': aggregate_state['ledger_path'],
        'ds_latest_json': aggregate_state['latest_index_path'],
    })
    if isinstance(dataset_refresh, dict) and bool(dataset_refresh.get('catalog_updated')):
        final_packet['artifacts'].update({
            'librarian_dataset_manifest_json': str(dataset_refresh.get('snapshot_path', '') or ''),
            'librarian_dataset_catalog_jsonl': str(dataset_refresh.get('catalog_path', '') or ''),
        })
    if str(publication_state.get('decision', '') or '').strip().lower() == 'go':
        aggregate_paths = publication_state.get('aggregate_paths', {}) if isinstance(publication_state.get('aggregate_paths', {}), dict) else {}
        current_publication = publication_state.get('current_run', {}) if isinstance(publication_state.get('current_run', {}), dict) else {}
        final_packet['artifacts'].update({
            'tracked_ds_index_md': str(aggregate_paths.get('index_md', '') or ''),
            'tracked_ds_latest_json': str(aggregate_paths.get('latest_json', '') or ''),
            'tracked_ds_latest_md': str(aggregate_paths.get('latest_md', '') or ''),
            'tracked_ds_by_workflow_json': str(aggregate_paths.get('by_workflow_json', '') or ''),
            'tracked_ds_by_workflow_md': str(aggregate_paths.get('by_workflow_md', '') or ''),
            'tracked_ds_thresholds_json': str(aggregate_paths.get('thresholds_json', '') or ''),
            'tracked_ds_thresholds_md': str(aggregate_paths.get('thresholds_md', '') or ''),
        })
        published_report_paths = current_publication.get('published_report_paths', {}) if isinstance(current_publication.get('published_report_paths', {}), dict) else {}
        final_packet['artifacts'].update({
            'published_run_dir': str(current_publication.get('published_run_dir', '') or ''),
            'published_report_json': str(published_report_paths.get('json', '') or ''),
            'published_report_md': str(published_report_paths.get('markdown', '') or ''),
            'published_report_manifest_json': str(published_report_paths.get('manifest', '') or ''),
        })
    final_packet['publication'] = publication_state
    return final_packet


def _ds_build(
    input_paths: List[Path],
    out_dir: str,
    seed: int,
    split_train: float,
    split_val: float,
    split_test: float,
    max_lines_per_file: Optional[int],
) -> Dict[str, Any]:
    from dataclasses import asdict

    from analysis.dataset_builder import build_dataset

    bundle, target_out_dir = _ds_prepare_bundle_for_artifact('build', out_dir, 'dataset', ['datasets'])
    manifest = build_dataset(
        input_paths,
        out_dir=target_out_dir,
        seed=int(seed),
        split={
            'train': float(split_train),
            'val': float(split_val),
            'test': float(split_test),
        },
        max_lines_per_file=max_lines_per_file,
    )
    manifest_dict = asdict(manifest)
    artifact_paths = {
        'dataset_manifest': target_out_dir / 'dataset_manifest.json',
        'features_csv': target_out_dir / 'features.csv',
        'labels_csv': (target_out_dir / 'labels.csv') if bool(manifest_dict.get('has_labels', False)) else None,
        'splits_csv': target_out_dir / 'splits.csv',
        'split_manifest_json': target_out_dir / 'split_manifest.json',
    }
    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-build',
        'command_family': 'ds',
        'command_path': 'observerctl ds build',
        'implementation_state': _DS_RUNTIME_STATE_COMMAND,
        'underlying_surface': 'analysis.dataset_builder',
        'summary': 'Dataset built through observerctl ds.',
        'run_id': bundle.run_id,
        'seed': int(seed),
        'split': dict(manifest_dict.get('split', {})),
        'total_records': int(manifest_dict.get('total_records', 0)),
        'has_labels': bool(manifest_dict.get('has_labels', False)),
        'artifacts': _ds_artifact_strings(artifact_paths),
        'reason_codes': [],
    }
    return _ds_finalize_run_packet(
        packet,
        bundle=bundle,
        artifact_paths=artifact_paths,
        context={
            'output_override': bool(str(out_dir).strip()),
        },
        lineage={
            'input_paths': list(input_paths),
        },
    )


def _ds_train(dataset: str, out_dir: str, model_type: str, seed: int) -> Dict[str, Any]:
    from dataclasses import asdict

    from analysis.train_model import train_model

    bundle, target_model_dir = _ds_prepare_bundle_for_artifact('train', out_dir, 'model', ['models'])
    manifest = train_model(
        Path(dataset),
        out_dir=target_model_dir,
        model_type=str(model_type),
        seed=int(seed),
    )
    manifest_dict = asdict(manifest)
    artifact_paths = {
        'train_manifest': target_model_dir / 'train_manifest.json',
        'model_path': Path(str(manifest_dict.get('model_path', ''))),
        'metrics_path': Path(str(manifest_dict.get('metrics_path', ''))),
    }
    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-train',
        'command_family': 'ds',
        'command_path': 'observerctl ds train',
        'implementation_state': _DS_RUNTIME_STATE_COMMAND,
        'underlying_surface': 'analysis.train_model',
        'summary': 'Model training completed through observerctl ds.',
        'run_id': bundle.run_id,
        'model_type': str(model_type),
        'artifacts': _ds_artifact_strings(artifact_paths),
        'metrics': manifest_dict.get('metrics', {}),
        'reason_codes': [],
    }
    return _ds_finalize_run_packet(
        packet,
        bundle=bundle,
        artifact_paths=artifact_paths,
        context={
            'output_override': bool(str(out_dir).strip()),
            'seed': int(seed),
        },
        lineage={
            'dataset_manifest': Path(dataset),
        },
    )


def _ds_evaluate(features_csv: str, labels_csv: str, dataset_manifest: str, max_fpr: float, out_dir: str, run_id: str, model_path: str) -> Dict[str, Any]:
    from dataclasses import asdict

    from analysis.report_visuals import generate_evaluation_visuals
    from analysis.evaluation_harness import evaluate, write_run_artifacts

    bundle, target_out_dir = _ds_prepare_bundle_for_artifact('evaluate', out_dir, 'evaluation', ['eval'], run_id=run_id)
    resolved_run_id = str(bundle.run_id)
    result = evaluate(
        Path(features_csv),
        labels_csv=Path(labels_csv) if str(labels_csv).strip() else None,
        max_fpr=float(max_fpr),
    )
    model_meta = None
    if str(model_path).strip():
        model_meta = {
            'family': 'trained_apexlab',
            'name': Path(model_path).name,
            'source': str(model_path),
        }
    write_run_artifacts(
        out_dir=target_out_dir,
        run_id=resolved_run_id,
        features_csv=Path(features_csv),
        labels_csv=Path(labels_csv) if str(labels_csv).strip() else None,
        result=result,
        dataset_manifest_path=Path(dataset_manifest) if str(dataset_manifest).strip() else None,
        model_meta=model_meta,
    )
    result_dict = asdict(result)
    artifact_paths = {
        'run_json': target_out_dir / 'run.json',
        'run_md': target_out_dir / 'run.md',
    }
    threshold_summary = {
        'threshold': float(result_dict.get('threshold', 0.0)),
        'target_fpr': float(max_fpr),
        'actual_fpr': (result_dict.get('metrics', {}) if isinstance(result_dict.get('metrics', {}), dict) else {}).get('fpr', ''),
        'flagged_records': _ds_positive_prediction_count(result_dict.get('counts', {})),
        'records_scored': _ds_total_prediction_count(result_dict.get('counts', {})),
    }
    visual_state = generate_evaluation_visuals(
        figures_dir=bundle.run_root / 'figures',
        metrics=result_dict.get('metrics', {}) if isinstance(result_dict.get('metrics', {}), dict) else {},
        counts=result_dict.get('counts', {}) if isinstance(result_dict.get('counts', {}), dict) else {},
        threshold=float(result_dict.get('threshold', 0.0)),
        max_fpr=float(max_fpr),
        threshold_summary=threshold_summary,
    )
    artifact_paths.update(_ds_visual_artifact_paths(visual_state))
    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-evaluate',
        'command_family': 'ds',
        'command_path': 'observerctl ds evaluate',
        'implementation_state': _DS_RUNTIME_STATE_COMMAND,
        'underlying_surface': 'analysis.evaluation_harness',
        'summary': 'Evaluation completed through observerctl ds.',
        'run_id': resolved_run_id,
        'has_labels': bool(result_dict.get('has_labels', False)),
        'threshold': float(result_dict.get('threshold', 0.0)),
        'metrics': result_dict.get('metrics', {}),
        'counts': result_dict.get('counts', {}),
        'visuals': visual_state,
        'artifacts': _ds_artifact_strings(artifact_paths),
        'reason_codes': [],
    }
    return _ds_finalize_run_packet(
        packet,
        bundle=bundle,
        artifact_paths=artifact_paths,
        context={
            'max_fpr': float(max_fpr),
            'output_override': bool(str(out_dir).strip()),
        },
        lineage={
            'features_csv': Path(features_csv),
            'labels_csv': Path(labels_csv) if str(labels_csv).strip() else None,
            'dataset_manifest': Path(dataset_manifest) if str(dataset_manifest).strip() else None,
            'model_path': Path(model_path) if str(model_path).strip() else None,
        },
    )


def _ds_score(dataset: str, model: str, out_file: str) -> Dict[str, Any]:
    from analysis.report_visuals import ANOMALY_DIRECTION, generate_score_visuals
    from analysis.score_unsupervised import score_dataset

    bundle, target_out_file = _ds_prepare_bundle_for_score(out_file)
    summary = score_dataset(Path(dataset), Path(model), target_out_file)
    artifact_paths = {
        'scores_csv': Path(str(summary.get('out_file', ''))),
        'resolved_model_path': Path(str(summary.get('resolved_model_path', ''))),
    }
    visual_state = generate_score_visuals(
        scores_csv=artifact_paths['scores_csv'],
        figures_dir=bundle.run_root / 'figures',
    )
    artifact_paths.update(_ds_visual_artifact_paths(visual_state))
    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-score',
        'command_family': 'ds',
        'command_path': 'observerctl ds score',
        'implementation_state': _DS_RUNTIME_STATE_COMMAND,
        'underlying_surface': 'analysis.score_unsupervised',
        'summary': 'Unsupervised scoring completed through observerctl ds.',
        'run_id': bundle.run_id,
        'records_scored': int(summary.get('records_scored', 0)),
        'anomaly_direction': ANOMALY_DIRECTION,
        'visuals': visual_state,
        'artifacts': _ds_artifact_strings(artifact_paths),
        'score_column': str(summary.get('score_column', 'score_anomaly')),
        'reason_codes': [],
    }
    return _ds_finalize_run_packet(
        packet,
        bundle=bundle,
        artifact_paths=artifact_paths,
        context={
            'output_override': bool(str(out_file).strip()),
        },
        lineage={
            'dataset_manifest': Path(dataset),
            'model_reference': Path(model),
        },
    )


def _ds_run_demo(out_dir: str, dataset_seed: int, model_seed: int, max_fpr: float) -> Dict[str, Any]:
    from analysis.report_visuals import ANOMALY_DIRECTION, generate_evaluation_visuals, generate_score_visuals, generate_summary_card_visual, merge_visual_states
    from analysis.run_demo import run_demo

    from analysis.report_pack import prepare_report_bundle

    explicit_root = Path(str(out_dir).strip()) if str(out_dir).strip() else None
    bundle = prepare_report_bundle(Path(__file__), 'demo', explicit_run_root=explicit_root)
    target_out_dir = explicit_root if explicit_root is not None else bundle.run_root
    summary = run_demo(
        root_dir=target_out_dir,
        dataset_seed=int(dataset_seed),
        model_seed=int(model_seed),
        max_fpr=float(max_fpr),
    )
    run_payload = summary.get('run_payload', {}) if isinstance(summary.get('run_payload', {}), dict) else {}
    evaluation_payload = run_payload.get('evaluation', {}) if isinstance(run_payload.get('evaluation', {}), dict) else {}
    evaluation_metrics = (evaluation_payload.get('metrics', {})) if isinstance(evaluation_payload.get('metrics', {}), dict) else {}
    evaluation_counts = (evaluation_payload.get('counts', {})) if isinstance(evaluation_payload.get('counts', {}), dict) else {}
    threshold_value = (((run_payload.get('model', {}) or {}).get('hyperparameters', {})) if isinstance((run_payload.get('model', {}) or {}).get('hyperparameters', {}), dict) else {}).get('threshold')
    artifact_paths = {
        'root_dir': Path(str(summary.get('root_dir', ''))),
        'dataset_manifest': Path(str(summary.get('dataset_manifest', ''))),
        'features_csv': Path(str(summary.get('features_csv', ''))),
        'labels_csv': Path(str(summary.get('labels_csv', ''))),
        'supervised_model_path': Path(str(summary.get('supervised_model_path', ''))),
        'supervised_train_manifest': Path(str(summary.get('supervised_train_manifest', ''))),
        'unsupervised_model_path': Path(str(summary.get('unsupervised_model_path', ''))),
        'unsupervised_train_manifest': Path(str(summary.get('unsupervised_train_manifest', ''))),
        'scores_csv': Path(str(summary.get('scores_csv', ''))),
        'threshold_report_json': Path(str(summary.get('threshold_report_json', ''))),
        'threshold_report_md': Path(str(summary.get('threshold_report_md', ''))),
        'evaluation_run_json': Path(str(summary.get('evaluation_run_json', ''))),
        'evaluation_run_md': Path(str(summary.get('evaluation_run_md', ''))),
    }
    workflow_visuals = generate_summary_card_visual(
        figures_dir=bundle.run_root / 'figures',
        figure_id='workflow_summary',
        title='Demo workflow summary',
        filename='workflow_summary.png',
        caption='High-level summary of the demo workflow report pack.',
        rows={
            'Records': int(summary.get('record_count', 0) or 0),
            'Max FPR': float(summary.get('max_fpr', max_fpr) or max_fpr),
            'Workflow steps': 'generate, build, train-supervised, train-unsupervised, evaluate, score, threshold',
        },
    )
    evaluation_visuals = generate_evaluation_visuals(
        figures_dir=bundle.run_root / 'figures',
        metrics=evaluation_metrics,
        counts=evaluation_counts,
        threshold=_ds_optional_float(threshold_value),
        max_fpr=float(summary.get('max_fpr', max_fpr) or max_fpr),
    )
    score_visuals = generate_score_visuals(
        scores_csv=artifact_paths['scores_csv'],
        figures_dir=bundle.run_root / 'figures',
        threshold_summary=summary.get('threshold_summary', {}) if isinstance(summary.get('threshold_summary', {}), dict) else None,
    )
    visual_state = merge_visual_states(workflow_visuals, evaluation_visuals, score_visuals)
    artifact_paths.update(_ds_visual_artifact_paths(visual_state))
    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-run',
        'command_family': 'ds',
        'command_path': 'observerctl ds run demo',
        'implementation_state': _DS_RUNTIME_STATE_AUTOMATION,
        'underlying_surface': 'analysis.run_demo',
        'run_mode': 'demo',
        'summary': 'Demo pipeline completed through observerctl ds.',
        'run_id': bundle.run_id,
        'total_records': int(summary.get('record_count', 0)),
        'max_fpr': float(summary.get('max_fpr', max_fpr)),
        'workflow_steps': ['generate', 'build', 'train-supervised', 'train-unsupervised', 'evaluate', 'score', 'threshold', 'visualize'],
        'metrics': evaluation_metrics,
        'counts': evaluation_counts,
        'thresholding': summary.get('threshold_summary', {}) if isinstance(summary.get('threshold_summary', {}), dict) else {},
        'score_column': str(summary.get('score_column', 'score_anomaly')),
        'anomaly_direction': ANOMALY_DIRECTION,
        'visuals': visual_state,
        'artifacts': _ds_artifact_strings(artifact_paths),
        'reason_codes': [],
    }
    return _ds_finalize_run_packet(
        packet,
        bundle=bundle,
        artifact_paths=artifact_paths,
        context={
            'dataset_seed': int(dataset_seed),
            'model_seed': int(model_seed),
            'max_fpr': float(max_fpr),
            'output_override': bool(str(out_dir).strip()),
        },
    )


def _ds_write_threshold_artifacts(scores_csv: Path, out_dir: Path, max_fpr: float) -> Dict[str, Any]:
    from analysis.report_visuals import summarize_threshold_scores_csv, write_threshold_report

    return write_threshold_report(
        summarize_threshold_scores_csv(scores_csv, float(max_fpr)),
        out_dir,
    )


def _ds_run_pipeline(
    input_paths: List[Path],
    out_dir: str,
    model_type: str,
    seed: int,
    split_train: float,
    split_val: float,
    split_test: float,
    max_fpr: float,
) -> Dict[str, Any]:
    import pickle

    try:
        import joblib
    except ImportError:
        joblib = None

    from analysis.dataset_builder import build_dataset
    from analysis.evaluation_harness import evaluate, infer_model_score_direction, make_model_scorer, write_run_artifacts
    from analysis.report_pack import prepare_report_bundle
    from analysis.report_visuals import ANOMALY_DIRECTION, generate_evaluation_visuals, generate_score_visuals, generate_summary_card_visual, merge_visual_states
    from analysis.score_unsupervised import score_dataset
    from analysis.train_model import train_model

    explicit_root = Path(str(out_dir).strip()) if str(out_dir).strip() else None
    bundle = prepare_report_bundle(Path(__file__), 'pipeline', explicit_run_root=explicit_root)
    target_root = explicit_root if explicit_root is not None else bundle.run_root
    dataset_dir = target_root / 'dataset'
    model_dir = target_root / 'models' / str(model_type)
    evaluation_dir = target_root / 'evaluation'
    scoring_dir = target_root / 'scoring'

    manifest = build_dataset(
        input_paths,
        out_dir=dataset_dir,
        seed=int(seed),
        split={
            'train': float(split_train),
            'val': float(split_val),
            'test': float(split_test),
        },
    )
    bundle.artifact_dirs['dataset'] = dataset_dir
    bundle.artifact_dirs['models'] = target_root / 'models'
    bundle.artifact_dirs['evaluation'] = evaluation_dir
    bundle.artifact_dirs['scoring'] = scoring_dir
    manifest_path = dataset_dir / 'dataset_manifest.json'
    if str(model_type) == 'supervised' and not bool(manifest.has_labels):
        artifact_paths = {
            'root_dir': target_root,
            'dataset_manifest': manifest_path,
        }
        packet = {
            'timestamp_utc': _utc_now(),
            'runtime_cli_surface': 'observerctl',
            'decision': 'no-go',
            'action': 'ds-run',
            'command_family': 'ds',
            'command_path': 'observerctl ds run pipeline',
            'implementation_state': _DS_RUNTIME_STATE_AUTOMATION,
            'underlying_surface': 'observerctl ds pipeline orchestration',
            'run_mode': 'pipeline',
            'summary': 'Supervised pipeline requires labeled telemetry records.',
            'run_id': bundle.run_id,
            'model_type': str(model_type),
            'artifacts': _ds_artifact_strings(artifact_paths),
            'reason_codes': ['critical_check_failed:labels_required_for_supervised_pipeline'],
        }
        return _ds_finalize_run_packet(
            packet,
            bundle=bundle,
            artifact_paths=artifact_paths,
            context={
                'seed': int(seed),
                'max_fpr': float(max_fpr),
                'output_override': bool(str(out_dir).strip()),
            },
            lineage={
                'input_paths': list(input_paths),
            },
        )

    train_manifest = train_model(
        manifest_path,
        out_dir=model_dir,
        model_type=str(model_type),
        seed=int(seed),
    )

    model_path = Path(train_manifest.model_path)
    try:
        with model_path.open('rb') as f:
            model = pickle.load(f)
    except Exception as pickle_error:
        if joblib is None:
            raise RuntimeError('could not load model via pickle and joblib is unavailable ({0})'.format(pickle_error))
        model = joblib.load(model_path)

    features_csv = Path(manifest.features_csv)
    labels_csv = Path(manifest.labels_csv) if manifest.labels_csv else None
    scorer = make_model_scorer(model)
    score_direction = infer_model_score_direction(model)
    evaluation = evaluate(
        features_csv,
        labels_csv=labels_csv if labels_csv is not None and labels_csv.exists() else None,
        max_fpr=float(max_fpr),
        scorer=scorer,
        score_direction=score_direction,
    )
    run_id = 'pipeline_{0}'.format(_utc_compact_stamp())
    write_run_artifacts(
        out_dir=evaluation_dir,
        run_id=run_id,
        features_csv=features_csv,
        labels_csv=labels_csv if labels_csv is not None and labels_csv.exists() else None,
        result=evaluation,
        dataset_manifest_path=manifest_path,
        model_meta={
            'family': 'trained_apexlab',
            'name': model_path.name,
            'class': type(model).__name__,
            'source': str(model_path),
        },
    )

    workflow_steps = ['build', 'train', 'evaluate']
    artifacts = {
        'root_dir': str(target_root).replace('\\', '/'),
        'dataset_manifest': str(manifest_path).replace('\\', '/'),
        'features_csv': str(features_csv).replace('\\', '/'),
        'labels_csv': str(labels_csv).replace('\\', '/') if labels_csv is not None else '',
        'train_manifest': str(model_dir / 'train_manifest.json').replace('\\', '/'),
        'model_path': str(model_path).replace('\\', '/'),
        'metrics_path': str(Path(train_manifest.metrics_path)).replace('\\', '/'),
        'run_json': str(evaluation_dir / 'run.json').replace('\\', '/'),
        'run_md': str(evaluation_dir / 'run.md').replace('\\', '/'),
    }
    threshold_summary: Dict[str, Any] = {}
    score_visuals: Dict[str, Any] = {'decision': 'skipped', 'reason_codes': ['visualization_skipped:no_score_visuals_applicable'], 'figure_count': 0, 'figures': []}
    if str(model_type) == 'unsupervised':
        scores_csv = scoring_dir / 'scores.csv'
        score_summary = score_dataset(manifest_path, model_dir / 'train_manifest.json', scores_csv)
        threshold_summary = _ds_write_threshold_artifacts(scores_csv, scoring_dir, float(max_fpr))
        score_visuals = generate_score_visuals(
            scores_csv=scores_csv,
            figures_dir=bundle.run_root / 'figures',
            threshold_summary=threshold_summary,
        )
        workflow_steps.extend(['score', 'threshold'])
        artifacts['scores_csv'] = str(score_summary.get('out_file', '')).replace('\\', '/')
        artifacts['threshold_report_json'] = str(threshold_summary.get('report_json', '')).replace('\\', '/')
        artifacts['threshold_report_md'] = str(threshold_summary.get('report_md', '')).replace('\\', '/')

    evaluation_visuals = generate_evaluation_visuals(
        figures_dir=bundle.run_root / 'figures',
        metrics=dict(evaluation.metrics),
        counts=dict(evaluation.counts),
        threshold=float(evaluation.threshold),
        max_fpr=float(max_fpr),
        threshold_summary=threshold_summary if threshold_summary else None,
    )
    workflow_visuals = generate_summary_card_visual(
        figures_dir=bundle.run_root / 'figures',
        figure_id='workflow_summary',
        title='Pipeline workflow summary',
        filename='workflow_summary.png',
        caption='High-level summary of the pipeline run.',
        rows={
            'Model type': str(model_type),
            'Records': int(manifest.total_records),
            'Max FPR': float(max_fpr),
            'Workflow steps': ', '.join(workflow_steps),
        },
    )
    visual_state = merge_visual_states(workflow_visuals, evaluation_visuals, score_visuals)
    visual_artifact_paths = _ds_visual_artifact_paths(visual_state)
    artifacts.update(_ds_artifact_strings(visual_artifact_paths))

    artifact_paths = {
        'root_dir': target_root,
        'dataset_manifest': manifest_path,
        'features_csv': features_csv,
        'labels_csv': labels_csv if labels_csv is not None else None,
        'train_manifest': model_dir / 'train_manifest.json',
        'model_path': model_path,
        'metrics_path': Path(train_manifest.metrics_path),
        'run_json': evaluation_dir / 'run.json',
        'run_md': evaluation_dir / 'run.md',
        'scores_csv': scoring_dir / 'scores.csv' if str(model_type) == 'unsupervised' else None,
        'threshold_report_json': scoring_dir / 'threshold_report.json' if str(model_type) == 'unsupervised' else None,
        'threshold_report_md': scoring_dir / 'threshold_report.md' if str(model_type) == 'unsupervised' else None,
    }
    artifact_paths.update(visual_artifact_paths)
    if str(model_type) == 'unsupervised' and str(visual_state.get('decision', '') or '').strip().lower() == 'go':
        workflow_steps.append('visualize')
    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-run',
        'command_family': 'ds',
        'command_path': 'observerctl ds run pipeline',
        'implementation_state': _DS_RUNTIME_STATE_AUTOMATION,
        'underlying_surface': 'observerctl ds pipeline orchestration',
        'run_mode': 'pipeline',
        'summary': 'Pipeline completed through observerctl ds.',
        'run_id': bundle.run_id,
        'model_type': str(model_type),
        'seed': int(seed),
        'split': {
            'train': float(split_train),
            'val': float(split_val),
            'test': float(split_test),
        },
        'anomaly_direction': ANOMALY_DIRECTION if str(model_type) == 'unsupervised' else '',
        'max_fpr': float(max_fpr),
        'has_labels': bool(manifest.has_labels),
        'total_records': int(manifest.total_records),
        'workflow_steps': workflow_steps,
        'metrics': dict(evaluation.metrics),
        'counts': dict(evaluation.counts),
        'thresholding': threshold_summary,
        'visuals': visual_state,
        'artifacts': dict(artifacts),
        'reason_codes': [],
    }
    return _ds_finalize_run_packet(
        packet,
        bundle=bundle,
        artifact_paths=artifact_paths,
        context={
            'max_fpr': float(max_fpr),
            'output_override': bool(str(out_dir).strip()),
        },
        lineage={
            'input_paths': list(input_paths),
        },
    )


def _ds_spine_packet(ds_cmd: str, command_path: str, underlying_surface: str, run_mode: str = '') -> Dict[str, Any]:
    packet = {
        'timestamp_utc': _utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'ds-{0}'.format(ds_cmd),
        'command_family': 'ds',
        'command_path': command_path,
        'implementation_state': _DS_RUNTIME_STATE_PLANNED,
        'underlying_surface': underlying_surface,
        'reason_codes': [],
        'status': 'planned',
        'summary': 'DS command spine is available as a planning surface without execution behavior in this packet.',
    }
    if run_mode:
        packet['run_mode'] = run_mode
    return packet


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
        if args.lib_cmd == 'datasets':
            return _librarian_datasets()
        if args.lib_cmd == 'dataset-register':
            return _librarian_dataset_register(args.dataset_manifest, args.access_class, args.display_name, args.run_id)
        if args.lib_cmd == 'dataset-release':
            return _librarian_dataset_release(args.dataset, args.requester_id, args.requested_action)
        if args.lib_cmd == 'rotate':
            return _librarian_action('rotate', args.mode)
        if args.lib_cmd == 'compact':
            return _librarian_action('compact', args.mode)
        if args.lib_cmd == 'verify':
            return _librarian_action('verify', args.mode)
        if args.lib_cmd == 'vault-status':
            return _librarian_vault_status()
        if args.lib_cmd == 'vault-verify':
            return _librarian_vault_verify()
        if args.lib_cmd == 'vault-lock':
            return _librarian_vault_lock(args.reason)
        if args.lib_cmd == 'vault-unlock':
            return _librarian_vault_unlock(args.reason)
        if args.lib_cmd == 'vault-rebaseline':
            return _librarian_vault_rebaseline(args.reason)

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

    if cmd == 'ds':
        if args.ds_cmd == 'build':
            return _ds_build(
                input_paths=args.input,
                out_dir=args.out_dir,
                seed=args.seed,
                split_train=args.split_train,
                split_val=args.split_val,
                split_test=args.split_test,
                max_lines_per_file=args.max_lines_per_file,
            )
        if args.ds_cmd == 'train':
            return _ds_train(
                dataset=args.dataset,
                out_dir=args.out_dir,
                model_type=args.model_type,
                seed=args.seed,
            )
        if args.ds_cmd == 'evaluate':
            return _ds_evaluate(
                features_csv=args.features_csv,
                labels_csv=args.labels_csv,
                dataset_manifest=args.dataset_manifest,
                max_fpr=args.max_fpr,
                out_dir=args.out_dir,
                run_id=args.run_id,
                model_path=args.model_path,
            )
        if args.ds_cmd == 'score':
            return _ds_score(
                dataset=args.dataset,
                model=args.model,
                out_file=args.out_file,
            )
        if args.ds_cmd == 'saved-trained':
            return _ds_train_selectors()
        if args.ds_cmd == 'saved-runs':
            return _ds_run_selectors()
        if args.ds_cmd == 'saved-baselines':
            return _ds_baseline_selectors(args.source, args.mode)
        if args.ds_cmd == 'saved-drafts':
            return _ds_draft_slots()
        if args.ds_cmd == 'wizard':
            return _ds_wizard(args)
        if args.ds_cmd == 'run-demo':
            return _ds_run_demo(
                out_dir=args.out_dir,
                dataset_seed=args.dataset_seed,
                model_seed=args.model_seed,
                max_fpr=args.max_fpr,
            )
        if args.ds_cmd == 'run-pipeline':
            return _ds_run_pipeline(
                input_paths=args.input,
                out_dir=args.out_dir,
                model_type=args.model_type,
                seed=args.seed,
                split_train=args.split_train,
                split_val=args.split_val,
                split_test=args.split_test,
                max_fpr=args.max_fpr,
            )

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
    sandbox_runs = sandbox_sub.add_parser('runs', help='Inspect saved sandbox runs')
    sandbox_runs_sub = sandbox_runs.add_subparsers(dest='sandbox_runs_cmd', required=True)
    sandbox_runs_sub.add_parser('list', help='List saved sandbox runs')
    sandbox_runs_show = sandbox_runs_sub.add_parser('show', help='Show one saved sandbox run')
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

    librarian = sub.add_parser('librarian', help='Librarian runtime, store, dataset, and vault operations')
    librarian_sub = librarian.add_subparsers(dest='lib_cmd', required=True)

    lib_runtime = librarian_sub.add_parser('runtime', help='Librarian runtime lifecycle')
    lib_runtime_sub = lib_runtime.add_subparsers(dest='lib_runtime_cmd', required=True)
    lib_runtime_sub.add_parser('status')
    lib_runtime_check_nested = lib_runtime_sub.add_parser('check')
    lib_runtime_check_nested.add_argument('--mode', choices=list(MODES), default=_state_default_mode())
    lib_runtime_restart_nested = lib_runtime_sub.add_parser('restart')
    lib_runtime_restart_nested.add_argument('--timeout-sec', type=float, default=8.0, help='Seconds to wait for librarian stop before escalation')
    lib_runtime_restart_nested.add_argument('--startup-probe-sec', type=float, default=6.0, help='Seconds to probe for librarian heartbeat after restart')

    lib_store = librarian_sub.add_parser('store', help='Librarian store maintenance')
    lib_store_sub = lib_store.add_subparsers(dest='lib_store_cmd', required=True)
    lib_store_sub.add_parser('status')
    lib_store_sub.add_parser('paths')
    lib_store_verify_nested = lib_store_sub.add_parser('verify')
    lib_store_verify_nested.add_argument('--mode', choices=list(MODES), required=True)
    lib_store_rotate_nested = lib_store_sub.add_parser('rotate')
    lib_store_rotate_nested.add_argument('--mode', choices=list(MODES), required=True)
    lib_store_compact_nested = lib_store_sub.add_parser('compact')
    lib_store_compact_nested.add_argument('--mode', choices=list(MODES), required=True)

    lib_dataset = librarian_sub.add_parser('dataset', help='Approved dataset authority surface')
    lib_dataset_sub = lib_dataset.add_subparsers(dest='lib_dataset_cmd', required=True)
    lib_dataset_sub.add_parser('list')
    lib_dataset_register_nested = lib_dataset_sub.add_parser('register')
    lib_dataset_register_nested.add_argument('dataset_manifest', help='Path to dataset manifest.json')
    lib_dataset_register_nested.add_argument('--access-class', choices=['local', 'protected-source'], default='local')
    lib_dataset_register_nested.add_argument('--display-name', default='', help='Optional operator-facing dataset label')
    lib_dataset_register_nested.add_argument('--run-id', default='', help='Optional run identifier to bind into selector resolution')
    lib_dataset_release_nested = lib_dataset_sub.add_parser('release')
    lib_dataset_release_nested.add_argument('dataset', help='Approved dataset selector (index, run_id, display name, or entry_id)')
    lib_dataset_release_nested.add_argument('--requester-id', default='observerctl', help='Requester id recorded in delegated access packets')
    lib_dataset_release_nested.add_argument('--requested-action', default='hydrate-dataset', help='Action label recorded in delegated access packets')

    lib_vault = librarian_sub.add_parser('vault', help='Protected librarian vault control surface')
    lib_vault_sub = lib_vault.add_subparsers(dest='lib_vault_cmd', required=True)
    lib_vault_sub.add_parser('status')
    lib_vault_sub.add_parser('verify')
    lib_vault_lock_nested = lib_vault_sub.add_parser('lock')
    lib_vault_lock_nested.add_argument('--reason', default='', help='Operator reason for locking the vault control plane')
    lib_vault_unlock_nested = lib_vault_sub.add_parser('unlock')
    lib_vault_unlock_nested.add_argument('--reason', default='', help='Operator reason for unlocking the vault control plane')
    lib_vault_rebaseline_nested = lib_vault_sub.add_parser('rebaseline')
    lib_vault_rebaseline_nested.add_argument('--reason', default='', help='Operator reason for refreshing the vault checksum baseline')

    librarian_sub.add_parser('status')
    lib_check = librarian_sub.add_parser('check')
    lib_check.add_argument('--mode', choices=list(MODES), default=_state_default_mode())
    lib_restart = librarian_sub.add_parser('restart')
    lib_restart.add_argument('--timeout-sec', type=float, default=8.0, help='Seconds to wait for librarian stop before escalation')
    lib_restart.add_argument('--startup-probe-sec', type=float, default=6.0, help='Seconds to probe for librarian heartbeat after restart')
    librarian_sub.add_parser('stats')
    librarian_sub.add_parser('stores')
    librarian_sub.add_parser('datasets')
    lib_dataset_register = librarian_sub.add_parser('dataset-register')
    lib_dataset_register.add_argument('dataset_manifest', help='Path to dataset manifest.json')
    lib_dataset_register.add_argument('--access-class', choices=['local', 'protected-source'], default='local')
    lib_dataset_register.add_argument('--display-name', default='', help='Optional operator-facing dataset label')
    lib_dataset_register.add_argument('--run-id', default='', help='Optional run identifier to bind into selector resolution')
    lib_dataset_release = librarian_sub.add_parser('dataset-release')
    lib_dataset_release.add_argument('dataset', help='Approved dataset selector (index, run_id, display name, or entry_id)')
    lib_dataset_release.add_argument('--requester-id', default='observerctl', help='Requester id recorded in delegated access packets')
    lib_dataset_release.add_argument('--requested-action', default='hydrate-dataset', help='Action label recorded in delegated access packets')
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

    ds = sub.add_parser('ds', help='Data-science operations namespace')
    ds_sub = ds.add_subparsers(dest='ds_cmd', required=True)
    ds_build = ds_sub.add_parser('build', help='Build a dataset from observer telemetry inputs')
    ds_build.add_argument('--input', action='append', required=True, type=Path, help='JSONL input path (repeatable)')
    ds_build.add_argument('--out-dir', default='', help='Output dataset directory')
    ds_build.add_argument('--seed', type=int, default=1337, help='Deterministic split seed')
    ds_build.add_argument('--split-train', type=float, default=0.7)
    ds_build.add_argument('--split-val', type=float, default=0.15)
    ds_build.add_argument('--split-test', type=float, default=0.15)
    ds_build.add_argument('--max-lines-per-file', type=int, default=None)

    ds_train = ds_sub.add_parser('train', help='Train a model from a dataset manifest')
    ds_train.add_argument('--dataset', required=True, help='Path to dataset manifest.json')
    ds_train.add_argument('--out-dir', default='', help='Optional run root or model artifact directory')
    ds_train.add_argument('--model-type', choices=['supervised', 'unsupervised'], default='supervised')
    ds_train.add_argument('--seed', type=int, default=42)

    ds_evaluate = ds_sub.add_parser('evaluate', help='Evaluate a heuristic or trained model')
    ds_evaluate.add_argument('--features-csv', required=True, help='Path to features.csv')
    ds_evaluate.add_argument('--labels-csv', default='', help='Optional path to labels.csv')
    ds_evaluate.add_argument('--dataset-manifest', default='', help='Optional path to dataset manifest.json')
    ds_evaluate.add_argument('--max-fpr', type=float, default=0.01)
    ds_evaluate.add_argument('--out-dir', default='', help='Output directory for evaluation artifacts')
    ds_evaluate.add_argument('--run-id', default='', help='Optional run identifier')
    ds_evaluate.add_argument('--model-path', default='', help='Optional serialized model path for metadata handoff')

    ds_score = ds_sub.add_parser('score', help='Score a dataset with an unsupervised model')
    ds_score.add_argument('--dataset', required=True, help='Path to dataset manifest.json')
    ds_score.add_argument('--model', required=True, help='Path to model artifact or train_manifest.json')
    ds_score.add_argument('--out-file', default='', help='Optional output path for scores CSV')

    def _add_ds_saved_baseline_args(parser_obj: argparse.ArgumentParser) -> None:
        parser_obj.add_argument('--source', choices=['sim', 'real'], default=_state_default_source())
        parser_obj.add_argument('--mode', choices=list(MODES), default=_state_default_mode())

    ds_saved = ds_sub.add_parser('saved', help='Inspect saved selector catalogs and draft slots')
    ds_saved_sub = ds_saved.add_subparsers(dest='ds_saved_cmd', required=True)
    ds_saved_sub.add_parser('trained', help='List saved train/model selectors')
    ds_saved_sub.add_parser('runs', help='List saved evaluation run selectors')
    ds_saved_baselines = ds_saved_sub.add_parser('baselines', help='List saved baseline selectors for a source/mode scope')
    _add_ds_saved_baseline_args(ds_saved_baselines)
    ds_saved_sub.add_parser('drafts', help='List canonical wizard draft slots')

    ds_run = ds_sub.add_parser('run', help='Run opinionated end-to-end DS flows')
    ds_run_sub = ds_run.add_subparsers(dest='ds_run_cmd', required=True)
    ds_run_demo = ds_run_sub.add_parser('demo', help='Run the existing observer demo flow')
    ds_run_demo.add_argument('--out-dir', default='', help='Output directory for demo artifacts')
    ds_run_demo.add_argument('--dataset-seed', type=int, default=123)
    ds_run_demo.add_argument('--model-seed', type=int, default=42)
    ds_run_demo.add_argument('--max-fpr', type=float, default=0.01)

    ds_run_pipeline = ds_run_sub.add_parser('pipeline', help='Run the default build/train/evaluate pipeline')
    ds_run_pipeline.add_argument('--input', action='append', required=True, type=Path, help='JSONL input path (repeatable)')
    ds_run_pipeline.add_argument('--out-dir', default='', help='Root output directory for pipeline artifacts')
    ds_run_pipeline.add_argument('--model-type', choices=['supervised', 'unsupervised'], default='supervised')
    ds_run_pipeline.add_argument('--seed', type=int, default=42)
    ds_run_pipeline.add_argument('--split-train', type=float, default=0.7)
    ds_run_pipeline.add_argument('--split-val', type=float, default=0.15)
    ds_run_pipeline.add_argument('--split-test', type=float, default=0.15)
    ds_run_pipeline.add_argument('--max-fpr', type=float, default=0.01)
    ds_wizard = ds_sub.add_parser('wizard', help='Launch the guided DS command wizard')
    ds_wizard.add_argument('--workflow', choices=list(_DS_WIZARD_WORKFLOWS), default='')
    ds_wizard.add_argument('--section', choices=list(_DS_WIZARD_SECTION_ORDER), default='')
    ds_wizard.add_argument('--hydrate-dataset', default='', help='Seed wizard state from an approved dataset selector or dataset manifest.json')
    ds_wizard.add_argument('--hydrate-train', default='', help='Seed wizard state from train_manifest.json')
    ds_wizard.add_argument('--hydrate-model', default='', help='Seed wizard state from a model artifact path')
    ds_wizard.add_argument('--hydrate-baseline-analysis', default='', help='Seed wizard state from a baseline analysis packet')
    ds_wizard.add_argument('--hydrate-run', default='', help='Seed wizard state from an evaluation run.json ledger')
    ds_wizard.add_argument('--hydrate-latest-context', action='store_true', help='Seed wizard state from SSOT source/mode and latest saved baseline-analysis packet when available')
    ds_wizard.add_argument('--load-draft', default='', help='Load wizard state from a canonical draft slot token or saved draft JSON file')
    ds_wizard.add_argument('--save-draft', nargs='?', const=_DS_WIZARD_AUTO_DRAFT_TOKEN, default='', help='Persist the current wizard state to the next canonical slot or an explicit draft JSON path after seeding')
    ds_wizard.add_argument('--set', dest='set_items', action='append', default=[], help='Preload a wizard field using key=value syntax')
    ds_wizard.add_argument('--execute', action='store_true', help='Attempt wizard execute handoff after seeding state')

    parser.add_argument('--json', action='store_true', help='Emit JSON output')
    return parser


def _normalize_nested_aliases(args: argparse.Namespace) -> argparse.Namespace:
    if args.command == 'sandbox' and args.sandbox_cmd == 'runs':
        if args.sandbox_runs_cmd == 'list':
            args.sandbox_cmd = 'runs-list'
        elif args.sandbox_runs_cmd == 'show':
            args.sandbox_cmd = 'runs-show'
    if args.command == 'librarian' and args.lib_cmd == 'runtime':
        if args.lib_runtime_cmd == 'status':
            args.lib_cmd = 'status'
        elif args.lib_runtime_cmd == 'check':
            args.lib_cmd = 'check'
        elif args.lib_runtime_cmd == 'restart':
            args.lib_cmd = 'restart'
    if args.command == 'librarian' and args.lib_cmd == 'store':
        if args.lib_store_cmd == 'status':
            args.lib_cmd = 'stats'
        elif args.lib_store_cmd == 'paths':
            args.lib_cmd = 'stores'
        elif args.lib_store_cmd == 'verify':
            args.lib_cmd = 'verify'
        elif args.lib_store_cmd == 'rotate':
            args.lib_cmd = 'rotate'
        elif args.lib_store_cmd == 'compact':
            args.lib_cmd = 'compact'
    if args.command == 'librarian' and args.lib_cmd == 'dataset':
        if args.lib_dataset_cmd == 'list':
            args.lib_cmd = 'datasets'
        elif args.lib_dataset_cmd == 'register':
            args.lib_cmd = 'dataset-register'
        elif args.lib_dataset_cmd == 'release':
            args.lib_cmd = 'dataset-release'
    if args.command == 'librarian' and args.lib_cmd == 'vault':
        if args.lib_vault_cmd == 'status':
            args.lib_cmd = 'vault-status'
        elif args.lib_vault_cmd == 'verify':
            args.lib_cmd = 'vault-verify'
        elif args.lib_vault_cmd == 'lock':
            args.lib_cmd = 'vault-lock'
        elif args.lib_vault_cmd == 'unlock':
            args.lib_cmd = 'vault-unlock'
        elif args.lib_vault_cmd == 'rebaseline':
            args.lib_cmd = 'vault-rebaseline'
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
    if args.command == 'ds' and args.ds_cmd == 'run':
        if args.ds_run_cmd == 'demo':
            args.ds_cmd = 'run-demo'
        elif args.ds_run_cmd == 'pipeline':
            args.ds_cmd = 'run-pipeline'
    if args.command == 'ds' and args.ds_cmd == 'saved':
        if args.ds_saved_cmd == 'trained':
            args.ds_cmd = 'saved-trained'
        elif args.ds_saved_cmd == 'runs':
            args.ds_cmd = 'saved-runs'
        elif args.ds_saved_cmd == 'baselines':
            args.ds_cmd = 'saved-baselines'
        elif args.ds_saved_cmd == 'drafts':
            args.ds_cmd = 'saved-drafts'
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
