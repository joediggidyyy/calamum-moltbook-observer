"""Calamum Observer Agent (local, end-to-end wiring).

This is a lightweight daemon-style loop that:
- Touches observer + watchdog heartbeat markers
- Appends synthetic JSONL records to logs/data/calamum
- Consumes control signals emitted by the Ghost Console (logs/control/calamum/*.signal.json)

It is intended for local full-stack validation without Docker.
No secrets are required.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from calamum_config import get_calamum_data_dir, get_calamum_control_dir, get_calamum_health_dir


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat() + 'Z'


def _find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / 'logs').exists():
            return parent
    return cur


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding='utf-8')


@dataclass
class AgentConfig:
    repo_root: Path
    node_id: str
    interval_sec: float
    mode: str

    # Paths
    data_dir: Path
    output_jsonl: Path
    control_dir: Path
    observer_heartbeat: Path
    watchdog_heartbeat: Path


def load_config(argv_repo_root: Optional[str], mode: str, interval_sec: float, node_id: str) -> AgentConfig:
    # Use consolidated config
    data_dir = get_calamum_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # We determine repo_root as best effort for back-compat or just use the parent of src
    if argv_repo_root:
        repo_root = Path(argv_repo_root).resolve()
    else:
        repo_root = Path(__file__).resolve().parents[1]

    if mode.lower() == 'canary':
        output_jsonl = data_dir / 'moltbook_canary_metrics.jsonl'
    else:
        # Keep a generic filename for future modes
        output_jsonl = data_dir / f'moltbook_{mode.lower()}_metrics.jsonl'

    control_dir = get_calamum_control_dir()
    control_dir.mkdir(parents=True, exist_ok=True)

    health_dir = get_calamum_health_dir()
    observer_heartbeat = Path(os.getenv(
        'CALAMUM_OBSERVER_HEARTBEAT_PATH',
        str(health_dir / 'calamum_observer.heartbeat'),
    ))
    watchdog_heartbeat = Path(os.getenv(
        'CALAMUM_WATCHDOG_HEARTBEAT_PATH',
        str(health_dir / 'calamum_ops_watchdog.heartbeat'),
    ))

    return AgentConfig(
        repo_root=repo_root,
        node_id=node_id,
        interval_sec=interval_sec,
        mode=mode,
        data_dir=data_dir,
        output_jsonl=output_jsonl,
        control_dir=control_dir,
        observer_heartbeat=observer_heartbeat,
        watchdog_heartbeat=watchdog_heartbeat,
    )


def handle_control_signals(control_dir: Path, node_id: str) -> Tuple[bool, Optional[str]]:
    """Handle control signals, returning (should_exit, note)."""

    mapping = {
        'kill.signal.json': 'kill',
        'isolate.signal.json': 'isolate',
        'refresh.signal.json': 'refresh',
        'watchdog_reset.signal.json': 'watchdog_reset',
    }

    if not control_dir.exists():
        return False, None

    for filename, sig_name in mapping.items():
        path = control_dir / filename
        if not path.exists():
            continue

        doc = _read_json(path)
        if not isinstance(doc, dict):
            # If unreadable, skip rather than crash.
            continue

        if doc.get('handled_at'):
            continue

        # Mark handled (idempotent)
        doc['handled_at'] = _utc_now_iso()
        doc['handled_by'] = node_id
        _write_json(path, doc)

        if sig_name == 'kill':
            return True, 'KILL received'
        if sig_name == 'isolate':
            # Local-only isolation marker for integrations to observe.
            _write_json(control_dir / 'isolation.state.json', {
                'ts': _utc_now_iso(),
                'node_id': node_id,
                'isolated': True,
            })
            return False, 'ISOLATE handled'
        if sig_name == 'refresh':
            # Handle config reload / force refresh
            try:
                # Reload config from environment/args
                # Note: We re-use original args via closure or just re-read env vars.
                # For this agent, key params are env-driven or file-driven.
                new_cfg = load_config(None, cfg.mode, cfg.interval_sec, cfg.node_id)
                
                # Update our runtime config reference (this is safe in this single-threaded loop)
                cfg.interval_sec = new_cfg.interval_sec
                cfg.mode = new_cfg.mode
                # Paths usually don't change, but if they did:
                cfg.data_dir = new_cfg.data_dir
                
                return False, 'REFRESH handled: Config reloaded'
            except Exception as e:
                return False, f'REFRESH failed: {e}'
        if sig_name == 'watchdog_reset':
            return False, 'WATCHDOG_RESET handled'

    return False, None


def append_record(jsonl_path: Path, node_id: str, mode: str) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        'ts': _utc_now_iso(),
        'node_id': node_id,
        'mode': mode.upper(),
        'kind': 'heartbeat_sample',
        'status': 'ok',
    }
    with jsonl_path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record) + '\n')


def run_agent(cfg: AgentConfig, max_iterations: Optional[int] = None) -> int:
    i = 0
    while True:
        # Heartbeats
        _touch(cfg.observer_heartbeat)
        _touch(cfg.watchdog_heartbeat)

        # Consume control signals
        should_exit, note = handle_control_signals(cfg.control_dir, cfg.node_id)
        if note:
            # Also append a record so dashboards immediately see activity.
            append_record(cfg.output_jsonl, cfg.node_id, cfg.mode)
        if should_exit:
            return 0

        # Emit a sample record
        append_record(cfg.output_jsonl, cfg.node_id, cfg.mode)

        i += 1
        if max_iterations is not None and i >= max_iterations:
            return 0

        time.sleep(cfg.interval_sec)


def main() -> int:
    parser = argparse.ArgumentParser(description='Calamum Observer Agent (local daemon)')
    parser.add_argument('--repo-root', help='Override repo root (must contain logs/)')
    parser.add_argument('--mode', default=os.getenv('CALAMUM_OPS_MODE', 'canary'))
    parser.add_argument('--interval-sec', type=float, default=float(os.getenv('CALAMUM_AGENT_INTERVAL_SEC', '2.0')))
    parser.add_argument('--node-id', default=os.getenv('CALAMUM_NODE_ID', 'calamum-node-01'))
    parser.add_argument('--max-iterations', type=int, help='For tests: stop after N iterations')
    args = parser.parse_args()

    cfg = load_config(args.repo_root, args.mode, args.interval_sec, args.node_id)
    return run_agent(cfg, max_iterations=args.max_iterations)


if __name__ == '__main__':
    raise SystemExit(main())
