"""Calamum Observer Daemon (LEGACY / SIMULATION ONLY)

DEPRECATED (governance):
- This module is not SSOT for Calamum operations.
- Do not wire this into the production launcher.
- Prefer `calamum_observer_agent.py` + Watchdog-owned supervision for active experimentation.

Long-running observer process that:
- writes obfuscated telemetry records to JSONL (no raw content)
- touches an observer heartbeat file periodically
- consumes file-based control signals emitted by the Ghost Console Control Deck

Signals are non-destructive:
- signals are read from logs/control/calamum/*.signal.json
- acknowledgements are written to logs/control/calamum/*.ack.json

Supported modes:
- canary (default): inbound notifications (dm/mention/follow)

Sources:
- sim: generated notifications
- live: Moltbook API (read-only)

Env vars (live mode):
- MOLTBOOK_API_KEY
- MOLTBOOK_HOST (default https://api.moltbook.com/v1)

Env vars (paths):
- CALAMUM_OBSERVER_HEARTBEAT_PATH
- CALAMUM_CONTROL_DIR
- CALAMUM_DATA_DIR

"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from obfuscator_lib import Obfuscator
from moltbook_client import MoltbookAPIClient
from calamum_sampler import simulate_moltbook_notifications


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def _find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / 'logs').exists():
            return parent
    return start.resolve()


@dataclass
class DaemonConfig:
    mode: str
    source: str
    interval_sec: float
    output_jsonl: Path
    heartbeat_path: Path
    control_dir: Path
    isolation_marker: Path


def load_daemon_config(module_file: Path, mode: str, source: str, interval_sec: float, output: Optional[Path]) -> DaemonConfig:
    repo_root = _find_repo_root(module_file)

    data_dir = Path(os.getenv('CALAMUM_DATA_DIR', str(repo_root / 'logs' / 'data' / 'calamum')))
    data_dir.mkdir(parents=True, exist_ok=True)

    if output is None:
        output_jsonl = data_dir / 'moltbook_canary_metrics.jsonl'
    else:
        output_jsonl = output
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    heartbeat_path = Path(os.getenv(
        'CALAMUM_OBSERVER_HEARTBEAT_PATH',
        str(repo_root / 'logs' / 'health' / 'calamum_observer.heartbeat'),
    ))
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)

    control_dir = Path(os.getenv(
        'CALAMUM_CONTROL_DIR',
        str(repo_root / 'logs' / 'control' / 'calamum'),
    ))
    control_dir.mkdir(parents=True, exist_ok=True)

    isolation_marker = repo_root / 'logs' / 'health' / 'calamum_isolation.active'
    isolation_marker.parent.mkdir(parents=True, exist_ok=True)

    return DaemonConfig(
        mode=mode,
        source=source,
        interval_sec=interval_sec,
        output_jsonl=output_jsonl,
        heartbeat_path=heartbeat_path,
        control_dir=control_dir,
        isolation_marker=isolation_marker,
    )


class ControlSignals:
    """Consumes control signals from the dashboard."""

    def __init__(self, control_dir: Path) -> None:
        self.control_dir = control_dir
        self._last_mtime: Dict[str, float] = {}

    def _signal_path(self, name: str) -> Path:
        return self.control_dir / f'{name}.signal.json'

    def _ack_path(self, name: str) -> Path:
        return self.control_dir / f'{name}.ack.json'

    def poll(self) -> List[Tuple[str, Dict[str, Any]]]:
        actions: List[Tuple[str, Dict[str, Any]]] = []
        for name in ['kill', 'isolate', 'refresh', 'watchdog_reset']:
            path = self._signal_path(name)
            if not path.exists():
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            last = self._last_mtime.get(name)
            if last is not None and mtime <= last:
                continue

            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                payload = {'parse_error': True}

            self._last_mtime[name] = mtime
            actions.append((name, payload if isinstance(payload, dict) else {'payload': payload}))

        return actions

    def ack(self, name: str, payload: Dict[str, Any], status: str, note: str = '') -> None:
        record: Dict[str, Any] = {
            'ack_ts': _utc_iso(),
            'signal': name,
            'status': status,
            'note': note,
            'original': payload,
        }
        try:
            self._ack_path(name).write_text(json.dumps(record, indent=2, sort_keys=True), encoding='utf-8')
        except Exception:
            pass


def _iter_notifications(source: str) -> Iterable[Dict[str, Any]]:
    if source == 'sim':
        return simulate_moltbook_notifications()

    api_key = os.getenv('MOLTBOOK_API_KEY')
    base_url = os.getenv('MOLTBOOK_HOST', 'https://api.moltbook.com/v1')
    if not api_key:
        raise EnvironmentError('MOLTBOOK_API_KEY required for live mode')
    client = MoltbookAPIClient(base_url, api_key)
    return client.fetch_notifications()


def append_obfuscated_notifications(output_jsonl: Path, notifications: Iterable[Dict[str, Any]]) -> int:
    count = 0
    with output_jsonl.open('a', encoding='utf-8') as f:
        for n in notifications:
            safe = Obfuscator.obfuscate_notification(n)
            f.write(json.dumps(safe) + '\n')
            count += 1
    return count


def touch_heartbeat(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def run_once(cfg: DaemonConfig, signals: ControlSignals) -> Dict[str, Any]:
    touch_heartbeat(cfg.heartbeat_path)

    actions = signals.poll()
    should_exit = False
    isolated = cfg.isolation_marker.exists()

    for name, payload in actions:
        if name == 'kill':
            should_exit = True
            signals.ack(name, payload, status='ok', note='observer exiting')
        elif name == 'isolate':
            cfg.isolation_marker.write_text(_utc_iso(), encoding='utf-8')
            isolated = True
            signals.ack(name, payload, status='ok', note='isolation marker set')
        elif name == 'refresh':
            signals.ack(name, payload, status='ok', note='noop refresh (stub)')
        elif name == 'watchdog_reset':
            signals.ack(name, payload, status='ok', note='watchdog reset intent acknowledged (no-op)')
        else:
            signals.ack(name, payload, status='ignored', note='unknown signal')

    written = 0
    if not should_exit:
        if cfg.mode != 'canary':
            written = 0
        else:
            notifications = _iter_notifications(cfg.source)
            written = append_obfuscated_notifications(cfg.output_jsonl, notifications)

    return {
        'ts': _utc_iso(),
        'written': written,
        'should_exit': should_exit,
        'isolated': isolated,
        'output_jsonl': str(cfg.output_jsonl),
        'heartbeat_path': str(cfg.heartbeat_path),
        'control_dir': str(cfg.control_dir),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Calamum Observer Daemon')
    parser.add_argument('--mode', choices=['canary'], default='canary')
    parser.add_argument('--source', choices=['sim', 'live'], default='sim')
    parser.add_argument('--interval-sec', type=float, default=5.0)
    parser.add_argument('--output', type=Path, help='Explicit JSONL output path')
    parser.add_argument('--once', action='store_true', help='Run a single iteration and exit')
    args = parser.parse_args(argv)

    cfg = load_daemon_config(Path(__file__).resolve(), args.mode, args.source, args.interval_sec, args.output)
    signals = ControlSignals(cfg.control_dir)

    if args.once:
        run_once(cfg, signals)
        return 0

    while True:
        summary = run_once(cfg, signals)
        if summary.get('should_exit'):
            return 0
        time.sleep(cfg.interval_sec)


if __name__ == '__main__':
    raise SystemExit(main())
