from __future__ import annotations

import os
import sys
from pathlib import Path
import time

# Ensure the Calamum observer `src/` directory is importable when tests run from repo root.
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from ops.telemetry import TelemetryProvider, load_config


def test_telemetry_counts_jsonl_and_heartbeats(tmp_path: Path, monkeypatch) -> None:
    # Build a fake repo root with logs/
    repo_root = tmp_path
    (repo_root / 'logs').mkdir(parents=True, exist_ok=True)

    health_dir = repo_root / 'logs' / 'health'
    data_dir = repo_root / 'logs' / 'data' / 'calamum'
    health_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    wd = health_dir / 'wd.heartbeat'
    obs = health_dir / 'obs.heartbeat'
    wd.touch()
    obs.touch()

    jsonl = data_dir / 'moltbook_canary_metrics.jsonl'
    jsonl.write_text('{"a": 1}\n{"a": 2}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_WATCHDOG_HEARTBEAT_PATH', str(wd))
    monkeypatch.setenv('CALAMUM_OBSERVER_HEARTBEAT_PATH', str(obs))
    monkeypatch.setenv('CALAMUM_DATA_DIR', str(data_dir))
    monkeypatch.setenv('CALAMUM_FRESHNESS_SEC', '60')

    # Provide a module_file inside the temp repo so repo-root discovery finds logs/
    module_file = repo_root / 'src' / 'dummy.py'
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text('# dummy', encoding='utf-8')

    provider = TelemetryProvider(load_config(module_file))

    snap1 = provider.update()
    assert snap1['watchdog_active'] is True
    assert snap1['observer_active'] is True
    assert snap1['total_records'] == 2

    # Append one line and ensure new/total update
    with jsonl.open('a', encoding='utf-8') as f:
        f.write('{"a": 3}\n')

    snap2 = provider.update()
    assert snap2['new_records'] == 1
    assert snap2['total_records'] == 3
    assert isinstance(snap2['density_bins'], list)
    assert len(snap2['density_bins']) == 12


def test_telemetry_stale_heartbeat(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / 'logs').mkdir(parents=True, exist_ok=True)

    health_dir = repo_root / 'logs' / 'health'
    data_dir = repo_root / 'logs' / 'data' / 'calamum'
    health_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    wd = health_dir / 'wd.heartbeat'
    obs = health_dir / 'obs.heartbeat'
    wd.touch()
    obs.touch()

    # Make heartbeats old
    old = time.time() - 120
    wd_m = (old, old)
    obs_m = (old, old)
    os.utime(wd, wd_m)
    os.utime(obs, obs_m)

    monkeypatch.setenv('CALAMUM_WATCHDOG_HEARTBEAT_PATH', str(wd))
    monkeypatch.setenv('CALAMUM_OBSERVER_HEARTBEAT_PATH', str(obs))
    monkeypatch.setenv('CALAMUM_DATA_DIR', str(data_dir))
    monkeypatch.setenv('CALAMUM_FRESHNESS_SEC', '1')

    module_file = repo_root / 'src' / 'dummy.py'
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text('# dummy', encoding='utf-8')

    provider = TelemetryProvider(load_config(module_file))
    snap = provider.update()
    assert snap['watchdog_active'] is False
    assert snap['observer_active'] is False
