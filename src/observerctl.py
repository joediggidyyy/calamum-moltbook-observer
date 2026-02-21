"""observerctl: standalone observer-scoped operations CLI.

Design constraints:
- No dependency on CodeSentinel runtime process surfaces.
- Names-only outputs suitable for gate evidence.
- Deterministic JSON contracts for preflight/gate/evidence packets.
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _project_root() -> Path:
    # observerctl.py lives in <project_root>/src/
    return Path(__file__).resolve().parent.parent


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve())).replace('\\', '/')
    except Exception:
        return str(path).replace('\\', '/')


def _read_env_presence(name: str) -> bool:
    return bool((os.getenv(name) or '').strip())


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


def collect_runtime_status(source: str = 'sim') -> Dict[str, Any]:
    source_norm = (source or 'sim').strip().lower()
    proj_root = _project_root()

    health_dir = get_calamum_health_dir()
    data_dir = get_calamum_data_dir()
    control_dir = get_calamum_control_dir()

    hb_watchdog = health_dir / 'calamum_ops_watchdog.heartbeat'
    hb_observer = health_dir / 'calamum_observer.heartbeat'
    hb_librarian = health_dir / 'calamum_librarian.heartbeat'

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
        'heartbeat.watchdog': _check_heartbeat(hb_watchdog, max_age_sec=45.0),
        'heartbeat.observer': _check_heartbeat(hb_observer, max_age_sec=60.0),
        'heartbeat.librarian': _check_heartbeat(hb_librarian, max_age_sec=120.0),
    }

    # Signing key presence is required for trustworthy observer records.
    signing_ok = _read_env_presence('CALAMUM_DATA_SIGNING_KEY') or _read_env_presence('CALAMUM_ALLOW_DEV_SIGNING_KEY')
    checks['env.signing_key'] = {
        'names': ['CALAMUM_DATA_SIGNING_KEY', 'CALAMUM_ALLOW_DEV_SIGNING_KEY'],
        'present': bool(signing_ok),
        'status': 'ok' if signing_ok else 'err',
    }

    # Live-source key is required only for live mode.
    if source_norm == 'live':
        live_key_ok = _read_env_presence('MOLTBOOK_API_KEY')
        checks['env.moltbook_api_key'] = {
            'names': ['MOLTBOOK_API_KEY'],
            'present': bool(live_key_ok),
            'status': 'ok' if live_key_ok else 'err',
        }

    live_file = data_dir / 'moltbook_live_metrics.jsonl'
    canary_file = data_dir / 'moltbook_canary_metrics.jsonl'
    checks['data.live_metrics'] = {
        'path': str(live_file),
        'exists': live_file.exists(),
        'status': 'ok' if live_file.exists() else 'warn',
    }
    checks['data.canary_metrics'] = {
        'path': str(canary_file),
        'exists': canary_file.exists(),
        'status': 'ok' if canary_file.exists() else 'warn',
    }

    return {
        'timestamp_utc': _utc_now(),
        'project_root': str(proj_root),
        'runtime_label': 'observer',
        'runtime_cli_surface': 'observerctl',
        'source': source_norm,
        'checks': checks,
    }


def evaluate_gate_decision(status_packet: Dict[str, Any]) -> Dict[str, Any]:
    checks = status_packet.get('checks', {}) if isinstance(status_packet, dict) else {}

    critical_keys = [
        'paths.health_dir',
        'heartbeat.watchdog',
        'heartbeat.observer',
        'env.signing_key',
    ]
    if str(status_packet.get('source', 'sim')).lower() == 'live':
        critical_keys.append('env.moltbook_api_key')

    reasons: List[str] = []
    for key in critical_keys:
        row = checks.get(key, {}) if isinstance(checks, dict) else {}
        state = str(row.get('status', 'err')).lower()
        if state != 'ok':
            reasons.append(f'critical_check_failed:{key}')

    go = len(reasons) == 0
    return {
        'timestamp_utc': _utc_now(),
        'decision': 'go' if go else 'no-go',
        'reason_codes': reasons,
        'critical_checks': critical_keys,
    }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build_evidence_pack(status_packet: Dict[str, Any], gate_packet: Dict[str, Any]) -> Dict[str, Any]:
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
            'missing_or_stale_watchdog_heartbeat',
            'missing_or_stale_observer_heartbeat',
            'missing_signing_key_context',
            'missing_live_api_key_when_live_source',
        ],
        'repro_steps': [
            'observerctl preflight --source <sim|live> --json',
            'observerctl gate-check --source <sim|live> --json',
            'observerctl evidence-pack --source <sim|live> --json',
        ],
    }

    process = {
        'phase': 'observerctl_gate_evaluation',
        'decision': gate_packet.get('decision', 'no-go'),
        'rationale': 'critical-check policy evaluation over observer runtime posture',
        'evidence_refs': evidence_refs,
        'approver_checkpoint': 'required_for_live_transition',
    }

    # provisional provenance (artifact hash finalized by write operation)
    provenance = {
        'artifact_path': 'stdout',
        'artifact_sha256': '',
        'generated_at_utc': _utc_now(),
        'producer_process': 'observerctl evidence-pack',
        'upstream_inputs': {
            'env_presence_keys': ['CALAMUM_DATA_SIGNING_KEY', 'CALAMUM_ALLOW_DEV_SIGNING_KEY', 'MOLTBOOK_API_KEY'],
            'paths': evidence_refs,
        },
    }

    return {
        'timestamp_utc': _utc_now(),
        'runtime_label': 'observer',
        'runtime_cli_surface': 'observerctl',
        'status_packet': status_packet,
        'gate_packet': gate_packet,
        'provenance': provenance,
        'methodology': methodology,
        'process': process,
    }


def _write_packet(packet: Dict[str, Any], output: Path) -> Dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(packet, indent=2, sort_keys=True) + '\n'
    output.write_text(text, encoding='utf-8')
    sha = _sha256_text(text)
    packet['provenance']['artifact_path'] = str(output)
    packet['provenance']['artifact_sha256'] = sha
    # rewrite with finalized provenance hash
    output.write_text(json.dumps(packet, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return packet


def _default_output_path() -> Path:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return _project_root() / 'local_untracked' / 'observerctl' / 'evidence' / f'observerctl_evidence_{ts}.json'


def _emit(packet: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(packet, indent=2, sort_keys=True))
        return
    decision = ((packet.get('gate_packet') or {}).get('decision') if isinstance(packet, dict) else None) or packet.get('decision', '')
    print(f"observerctl decision: {decision}")
    reasons = ((packet.get('gate_packet') or {}).get('reason_codes') if isinstance(packet, dict) else None) or packet.get('reason_codes', [])
    if reasons:
        for reason in reasons:
            print(f"- {reason}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='observerctl standalone operations surface (observer scope)')
    sub = parser.add_subparsers(dest='command', required=True)

    preflight = sub.add_parser('preflight', help='Emit observer runtime status packet')
    preflight.add_argument('--source', choices=['sim', 'live'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))
    preflight.add_argument('--json', action='store_true', help='Emit JSON output')

    gate = sub.add_parser('gate-check', help='Evaluate go/no-go decision over critical checks')
    gate.add_argument('--source', choices=['sim', 'live'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))
    gate.add_argument('--json', action='store_true', help='Emit JSON output')

    ev = sub.add_parser('evidence-pack', help='Emit publication-grade triad packet')
    ev.add_argument('--source', choices=['sim', 'live'], default=os.getenv('CALAMUM_MOLTBOOK_SOURCE', 'sim'))
    ev.add_argument('--output', type=str, default='', help='Write packet to path (default under local_untracked/observerctl/evidence)')
    ev.add_argument('--json', action='store_true', help='Emit JSON output')

    args = parser.parse_args(argv)

    if args.command == 'preflight':
        pkt = collect_runtime_status(source=str(args.source))
        _emit(pkt, as_json=bool(args.json))
        return 0

    if args.command == 'gate-check':
        status_pkt = collect_runtime_status(source=str(args.source))
        gate_pkt = evaluate_gate_decision(status_pkt)
        _emit(gate_pkt, as_json=bool(args.json))
        return 0 if gate_pkt.get('decision') == 'go' else 2

    if args.command == 'evidence-pack':
        status_pkt = collect_runtime_status(source=str(args.source))
        gate_pkt = evaluate_gate_decision(status_pkt)
        packet = build_evidence_pack(status_pkt, gate_pkt)

        out_raw = str(args.output or '').strip()
        out_path = Path(out_raw) if out_raw else _default_output_path()
        packet = _write_packet(packet, out_path)

        _emit(packet, as_json=bool(args.json))
        return 0 if gate_pkt.get('decision') == 'go' else 2

    return 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
