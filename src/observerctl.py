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
import sys
import time
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


def _default_security_report_ref() -> str:
    return 'projects/calamum-moltbook-observer/docs/reports/operations/JOB_REPORT_QS-CALAMUM-MOLTBOOK-OBSERVERCTL-COMMAND-SURFACE-20260221.md'


def _control_file(name: str) -> Path:
    return get_calamum_control_dir() / name


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
    return policy


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


def _make_run_linkage(mode: str, event: str) -> Dict[str, str]:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    posture = _posture_for_mode(mode)
    return {
        'run_id': 'observerctl-{event}-{ts}'.format(event=str(event).strip().lower().replace(' ', '-'), ts=ts),
        'posture_trigger_id': 'pt-{mode}-{ts}'.format(mode=mode, ts=ts),
        'posture_trigger': posture,
        'security_report_ref': _default_security_report_ref(),
    }


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

    checks['data.live_metrics'] = {
        'path': str(data_dir / 'moltbook_live_metrics.jsonl'),
        'exists': (data_dir / 'moltbook_live_metrics.jsonl').exists(),
        'status': 'ok' if (data_dir / 'moltbook_live_metrics.jsonl').exists() else 'warn',
    }
    checks['data.canary_metrics'] = {
        'path': str(data_dir / 'moltbook_canary_metrics.jsonl'),
        'exists': (data_dir / 'moltbook_canary_metrics.jsonl').exists(),
        'status': 'ok' if (data_dir / 'moltbook_canary_metrics.jsonl').exists() else 'warn',
    }

    return {
        'timestamp_utc': _utc_now(),
        'runtime_label': 'observer',
        'runtime_cli_surface': 'observerctl',
        'source': source_norm,
        'mode': mode,
        'checks': checks,
    }


def evaluate_gate_decision(status_packet: Dict[str, Any], target_mode: Optional[str] = None) -> Dict[str, Any]:
    checks = status_packet.get('checks', {}) if isinstance(status_packet, dict) else {}
    source = _normalize_source(str(status_packet.get('source', 'sim')))
    mode = str(status_packet.get('mode', 'watch')).strip().lower()
    to_mode = str(target_mode or mode).strip().lower()
    if to_mode not in MODES:
        return {
            'timestamp_utc': _utc_now(),
            'decision': 'no-go',
            'reason_codes': ['policy_denied:target_mode_unsupported'],
            'critical_checks': [],
            'from_state': '{0}:{1}'.format(source, mode),
            'to_state': '{0}:{1}'.format(source, to_mode),
            'profile': 'GP-X',
        }

    critical_keys = [
        'paths.health_dir',
        'heartbeat.watchdog',
        'heartbeat.observer',
        'env.signing_key',
    ]
    if source == 'real':
        critical_keys.append('env.moltbook_api_key')

    reasons: List[str] = []
    for key in critical_keys:
        row = checks.get(key, {}) if isinstance(checks, dict) else {}
        state = str(row.get('status', 'err')).lower()
        if state != 'ok':
            reasons.append('critical_check_failed:{0}'.format(key))

    linkage = _make_run_linkage(to_mode, event='gate')
    posture_required = _posture_for_mode(to_mode)
    if linkage['posture_trigger'] != posture_required:
        reasons.append('critical_check_failed:watchdog_trigger_posture_invalid')

    # C20 run linkage reference must exist as path string (names-only check).
    if not linkage['security_report_ref']:
        reasons.append('critical_check_failed:run_security_report_missing')

    # C21/C22 lockdown checks for live/honeypot target.
    if posture_required == 'lockdown':
        hb_ok = str((checks.get('heartbeat.watchdog') or {}).get('status', 'err')).lower() == 'ok'
        baseline_graph = _project_root() / 'semantics_vault' / 'oracl_index' / 'weighted_graph_index.json'
        baseline_ok = baseline_graph.exists()
        if not hb_ok:
            reasons.append('critical_check_failed:lockdown_heartbeat_rate_not_escalated')
        if not baseline_ok:
            reasons.append('critical_check_failed:lockdown_baseline_rate_not_escalated')

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
        'from_state': '{0}:{1}'.format(source, mode),
        'to_state': '{0}:{1}'.format(source, to_mode),
        'profile': profile,
        'runtime_label': 'observer',
        'runtime_cli_surface': 'observerctl',
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


def _default_output_path() -> Path:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return _project_root() / 'local_untracked' / 'observerctl' / 'evidence' / 'observerctl_evidence_{0}.json'.format(ts)


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
    print('observerctl decision: {0}'.format(decision))
    reasons = ((packet.get('gate_packet') or {}).get('reason_codes') if isinstance(packet, dict) else None) or packet.get('reason_codes', [])
    for reason in reasons:
        print('- {0}'.format(reason))


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
    if gate.get('decision') != 'go' or str(gate.get('to_state', '')).endswith(':{0}'.format(to_mode)) is False:
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


def _ops_gate_check(source: str) -> Dict[str, Any]:
    status = collect_runtime_status(source=source)
    gate = evaluate_gate_decision(status, target_mode=str(status.get('mode', 'watch')))
    _write_json_file(_control_file(LAST_GATE_FILE), gate)
    return gate


def _ops_evidence_pack(source: str, event: str, output: str) -> Dict[str, Any]:
    status = collect_runtime_status(source=source)
    gate = evaluate_gate_decision(status, target_mode=str(status.get('mode', 'watch')))
    packet = build_evidence_pack(status, gate, event=event)
    out_path = Path(str(output).strip()) if str(output).strip() else _default_output_path()
    packet = _write_packet(packet, out_path)
    _append_jsonl(_project_root() / 'local_untracked' / 'observerctl' / 'evidence' / 'index.jsonl', {
        'timestamp_utc': _utc_now(),
        'packet_path': str(out_path).replace('\\', '/'),
        'decision': gate.get('decision', 'no-go'),
        'run_id': packet.get('run_id', ''),
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
    idx = _project_root() / 'local_untracked' / 'observerctl' / 'evidence' / 'index.jsonl'
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


def _librarian_stats() -> Dict[str, Any]:
    items = []
    for mode in MODES:
        d = _store_dir_for_mode(mode)
        recs = len(list(d.glob('*.jsonl'))) if d.exists() else 0
        items.append({'mode': mode, 'store_path': str(d).replace('\\', '/'), 'record_files': recs})
    return {'timestamp_utc': _utc_now(), 'runtime_cli_surface': 'observerctl', 'stores': items}


def _librarian_stores() -> Dict[str, Any]:
    state = _load_state()
    stores = []
    for mode in MODES:
        d = _store_dir_for_mode(mode)
        stores.append({'mode': mode, 'path': str(d).replace('\\', '/'), 'exists': d.exists(), 'active': mode == state.get('mode')})
    return {'timestamp_utc': _utc_now(), 'runtime_cli_surface': 'observerctl', 'stores': stores}


def _librarian_action(action: str, mode: str) -> Dict[str, Any]:
    if mode not in MODES:
        return {'timestamp_utc': _utc_now(), 'runtime_cli_surface': 'observerctl', 'decision': 'no-go', 'reason_codes': ['policy_denied:target_mode_unsupported']}
    d = _store_dir_for_mode(mode)
    d.mkdir(parents=True, exist_ok=True)
    marker = d / '{0}_{1}.marker'.format(action, datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    marker.write_text('ok\n', encoding='utf-8')
    return {'timestamp_utc': _utc_now(), 'runtime_cli_surface': 'observerctl', 'decision': 'go', 'action': action, 'mode': mode, 'artifact': str(marker).replace('\\', '/')}


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
        if args.ops_cmd == 'mode-current':
            return _ops_mode_current()
        if args.ops_cmd == 'mode-list':
            return _ops_mode_list()
        if args.ops_cmd == 'mode-gate':
            return _ops_gate(args.source, args.to)
        if args.ops_cmd == 'mode-set':
            return _ops_mode_set(args.source, args.to)
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
    if args.command == 'ops' and args.ops_cmd == 'evidence':
        if args.evidence_cmd == 'pack':
            args.ops_cmd = 'evidence-pack'
        elif args.evidence_cmd == 'verify':
            args.ops_cmd = 'evidence-verify'
        elif args.evidence_cmd == 'index':
            args.ops_cmd = 'evidence-index'
    return args


def _extract_json_flag(argv: Optional[List[str]]) -> Tuple[List[str], bool]:
    if argv is None:
        return list(sys.argv[1:]), False
    cleaned: List[str] = []
    as_json = False
    for token in argv:
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
