from __future__ import annotations

import os
import sys
import json
from pathlib import Path
import time

# Ensure the Calamum observer `src/` directory is importable when tests run from repo root.
_SRC_DIR = Path(__file__).resolve().parents[1]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from ops.telemetry import TelemetryProvider, load_config, _newest_jsonl, _JsonlAppendCounter


try:
    import obfuscator_lib  # type: ignore
except ImportError:  # pragma: no cover
    obfuscator_lib = None


def test_telemetry_counts_jsonl_and_heartbeats(tmp_path: Path, monkeypatch) -> None:
    # Build a fake repo root with logs/
    repo_root = tmp_path
    (repo_root / 'logs').mkdir(parents=True, exist_ok=True)

    health_dir = repo_root / 'logs' / 'health'
    data_dir = repo_root / 'logs' / 'data' / 'calamum'
    control_dir = repo_root / 'logs' / 'control' / 'calamum'
    health_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    (control_dir / 'observerctl_state.json').write_text(
        json.dumps({'source': 'sim', 'mode': 'canary'}),
        encoding='utf-8',
    )

    wd = health_dir / 'wd.heartbeat'
    obs = health_dir / 'obs.heartbeat'
    # If signature verification is available, watchdog heartbeat must be signed.
    if obfuscator_lib:
        monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'test-secret-key')
        payload = {"component": "calamum_watchdog", "ts": "2026-01-01T00:00:00Z", "status": "alive"}
        payload = obfuscator_lib.Obfuscator.sign_record(payload)
        wd.write_text(json.dumps(payload), encoding='utf-8')
    else:
        wd.touch()
    obs.touch()

    jsonl = data_dir / 'observer_derived' / 'sim' / 'canary' / 'moltbook_metrics.jsonl'
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    jsonl.write_text('{"a": 1}\n{"a": 2}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_WATCHDOG_HEARTBEAT_PATH', str(wd))
    monkeypatch.setenv('CALAMUM_OBSERVER_HEARTBEAT_PATH', str(obs))
    monkeypatch.setenv('CALAMUM_DATA_DIR', str(data_dir))
    monkeypatch.setenv('CALAMUM_CONTROL_DIR', str(control_dir))
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


def test_telemetry_display_totals_use_archive_plus_non_sim_session(tmp_path: Path, monkeypatch) -> None:
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

    # Active non-sim session file.
    active = data_dir / 'observer_derived' / 'real' / 'canary' / 'moltbook_metrics.jsonl'
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text('{"a": 1}\n{"a": 2}\n{"a": 3}\n', encoding='utf-8')

    # Archive manifest with one normal entry + one simulation-tagged entry.
    archive_dir = data_dir / 'archive'
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        'moltbook_canary_20260210T081214.jsonl': {'records': 100},
        'moltbook_canary_metrics_legacy_simulation.jsonl': {'records': 25},
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_WATCHDOG_HEARTBEAT_PATH', str(wd))
    monkeypatch.setenv('CALAMUM_OBSERVER_HEARTBEAT_PATH', str(obs))
    monkeypatch.setenv('CALAMUM_DATA_DIR', str(data_dir))
    monkeypatch.setenv('CALAMUM_FRESHNESS_SEC', '60')

    module_file = repo_root / 'src' / 'dummy.py'
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text('# dummy', encoding='utf-8')

    provider = TelemetryProvider(load_config(module_file))
    provider._active_jsonl_cache = active
    provider._active_jsonl_last_scan_ts = time.time()
    snap = provider.update()

    assert snap['records_session_display'] == 3
    assert snap['records_archive_display'] == 125
    assert snap['records_total_display'] == 128
    assert snap['records_archive_non_sim'] == 100
    assert snap['records_archive_sim_estimate'] == 25
    assert snap['active_source_is_sim'] is False


def test_newest_jsonl_picks_most_recent_non_archive_file(tmp_path: Path) -> None:
    data_dir = tmp_path / 'logs' / 'data' / 'calamum'
    sim_canary = data_dir / 'observer_derived' / 'sim' / 'canary' / 'moltbook_metrics.jsonl'
    real_canary = data_dir / 'observer_derived' / 'real' / 'canary' / 'moltbook_metrics.jsonl'
    archived = data_dir / 'archive' / 'old.jsonl'

    sim_canary.parent.mkdir(parents=True, exist_ok=True)
    real_canary.parent.mkdir(parents=True, exist_ok=True)
    archived.parent.mkdir(parents=True, exist_ok=True)

    sim_canary.write_text('{"s": 1}\n', encoding='utf-8')
    time.sleep(0.02)
    archived.write_text('{"a": 1}\n', encoding='utf-8')
    time.sleep(0.02)
    real_canary.write_text('{"r": 1}\n', encoding='utf-8')

    pick = _newest_jsonl(data_dir)
    assert pick == real_canary


def test_pick_active_jsonl_recovers_when_cached_path_missing(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / 'logs').mkdir(parents=True, exist_ok=True)

    health_dir = repo_root / 'logs' / 'health'
    data_dir = repo_root / 'logs' / 'data' / 'calamum'
    control_dir = repo_root / 'logs' / 'control' / 'calamum'
    health_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    wd = health_dir / 'wd.heartbeat'
    obs = health_dir / 'obs.heartbeat'
    wd.touch()
    obs.touch()

    active = data_dir / 'observer_derived' / 'sim' / 'watch' / 'moltbook_metrics.jsonl'
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text('{"x": 1}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_WATCHDOG_HEARTBEAT_PATH', str(wd))
    monkeypatch.setenv('CALAMUM_OBSERVER_HEARTBEAT_PATH', str(obs))
    monkeypatch.setenv('CALAMUM_DATA_DIR', str(data_dir))
    monkeypatch.setenv('CALAMUM_CONTROL_DIR', str(control_dir))

    module_file = repo_root / 'src' / 'dummy.py'
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text('# dummy', encoding='utf-8')

    provider = TelemetryProvider(load_config(module_file))

    # Seed a stale cache path that no longer exists with a high-water timestamp.
    missing = data_dir / 'observer_derived' / 'sim' / 'canary' / 'moltbook_metrics.jsonl'
    provider._active_jsonl_cache = missing
    provider._active_path_high_water_mtime = time.time() + 600.0
    provider._active_jsonl_last_scan_ts = 0.0

    picked = provider._pick_active_jsonl()
    assert picked == active


def test_telemetry_uses_resource_index_when_active_jsonl_idle(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / 'logs').mkdir(parents=True, exist_ok=True)

    health_dir = repo_root / 'logs' / 'health'
    data_dir = repo_root / 'logs' / 'data' / 'calamum'
    control_dir = repo_root / 'logs' / 'control' / 'calamum'
    health_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    wd = health_dir / 'wd.heartbeat'
    obs = health_dir / 'obs.heartbeat'
    wd.touch()
    obs.touch()

    # Active ingest lane exists but is idle/empty.
    active = data_dir / 'observer_derived' / 'sim' / 'canary' / 'moltbook_metrics.jsonl'
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text('', encoding='utf-8')

    # Resource collection index has segment deltas (observerctl baseline collect output).
    resource_index = data_dir / 'observer_derived' / 'sim' / 'canary' / 'resource' / 'index.jsonl'
    resource_index.parent.mkdir(parents=True, exist_ok=True)
    resource_index.write_text(
        '\n'.join([
            json.dumps({'timestamp_utc': '2026-02-22T00:00:01Z', 'segment_path': 'seg1.jsonl', 'segment_records': 3}),
            json.dumps({'timestamp_utc': '2026-02-22T00:00:02Z', 'segment_path': 'seg2.jsonl', 'segment_records': 4}),
        ]) + '\n',
        encoding='utf-8',
    )

    # observerctl SSOT state used by telemetry resource-index resolver.
    (control_dir / 'observerctl_state.json').write_text(
        json.dumps({'source': 'sim', 'mode': 'canary'}),
        encoding='utf-8',
    )

    monkeypatch.setenv('CALAMUM_WATCHDOG_HEARTBEAT_PATH', str(wd))
    monkeypatch.setenv('CALAMUM_OBSERVER_HEARTBEAT_PATH', str(obs))
    monkeypatch.setenv('CALAMUM_DATA_DIR', str(data_dir))
    monkeypatch.setenv('CALAMUM_CONTROL_DIR', str(control_dir))
    monkeypatch.setenv('CALAMUM_FRESHNESS_SEC', '60')
    monkeypatch.setenv('CALAMUM_DENSITY_SLICE_SEC', '0.1')

    module_file = repo_root / 'src' / 'dummy.py'
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text('# dummy', encoding='utf-8')

    provider = TelemetryProvider(load_config(module_file))
    snap1 = provider.update()
    assert snap1['new_records'] == 7
    assert snap1['total_records'] >= 7
    assert snap1['resource_new_records'] == 7
    assert snap1['resource_total_records'] >= 7

    # Let density slice roll so histogram source receives a non-zero bucket.
    time.sleep(0.32)
    snap2 = provider.update()
    assert any(int(x) > 0 for x in snap2['density_raw_window'])


def test_pick_active_jsonl_keeps_ssot_route_even_when_other_lane_is_active(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / 'logs').mkdir(parents=True, exist_ok=True)

    health_dir = repo_root / 'logs' / 'health'
    data_dir = repo_root / 'logs' / 'data' / 'calamum'
    control_dir = repo_root / 'logs' / 'control' / 'calamum'
    health_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    wd = health_dir / 'wd.heartbeat'
    obs = health_dir / 'obs.heartbeat'
    wd.touch()
    obs.touch()

    # SSOT route points to real/canary, while sim/watch has activity.
    # Telemetry must keep route fidelity (no lane drift).
    (control_dir / 'observerctl_state.json').write_text(
        json.dumps({'source': 'real', 'mode': 'canary'}),
        encoding='utf-8',
    )

    sim_watch = data_dir / 'observer_derived' / 'sim' / 'watch' / 'moltbook_metrics.jsonl'
    sim_watch.parent.mkdir(parents=True, exist_ok=True)
    sim_watch.write_text('{"x": 1}\n', encoding='utf-8')

    # Route-lane resource activity keeps SSOT pinning even before metrics exists.
    resource_index = data_dir / 'observer_derived' / 'real' / 'canary' / 'resource' / 'index.jsonl'
    resource_index.parent.mkdir(parents=True, exist_ok=True)
    resource_index.write_text(
        json.dumps({
            'timestamp_utc': '2026-02-23T04:25:44Z',
            'segment_path': 'resource/seg-001.jsonl',
            'segment_records': 5,
        }) + '\n',
        encoding='utf-8',
    )

    monkeypatch.setenv('CALAMUM_WATCHDOG_HEARTBEAT_PATH', str(wd))
    monkeypatch.setenv('CALAMUM_OBSERVER_HEARTBEAT_PATH', str(obs))
    monkeypatch.setenv('CALAMUM_DATA_DIR', str(data_dir))
    monkeypatch.setenv('CALAMUM_CONTROL_DIR', str(control_dir))

    module_file = repo_root / 'src' / 'dummy.py'
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text('# dummy', encoding='utf-8')

    provider = TelemetryProvider(load_config(module_file))
    picked = provider._pick_active_jsonl()
    expected = data_dir / 'observer_derived' / 'real' / 'canary' / 'moltbook_metrics.jsonl'
    assert picked == expected


def test_pick_active_jsonl_falls_back_when_route_lane_is_missing_and_resource_stale(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / 'logs').mkdir(parents=True, exist_ok=True)

    health_dir = repo_root / 'logs' / 'health'
    data_dir = repo_root / 'logs' / 'data' / 'calamum'
    control_dir = repo_root / 'logs' / 'control' / 'calamum'
    health_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    wd = health_dir / 'wd.heartbeat'
    obs = health_dir / 'obs.heartbeat'
    wd.touch()
    obs.touch()

    # SSOT route points to real/canary, but real/canary metrics do not exist.
    (control_dir / 'observerctl_state.json').write_text(
        json.dumps({'source': 'real', 'mode': 'canary'}),
        encoding='utf-8',
    )

    # Active stream exists in a different lane.
    sim_watch = data_dir / 'observer_derived' / 'sim' / 'watch' / 'moltbook_metrics.jsonl'
    sim_watch.parent.mkdir(parents=True, exist_ok=True)
    sim_watch.write_text('{"x": 1}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_WATCHDOG_HEARTBEAT_PATH', str(wd))
    monkeypatch.setenv('CALAMUM_OBSERVER_HEARTBEAT_PATH', str(obs))
    monkeypatch.setenv('CALAMUM_DATA_DIR', str(data_dir))
    monkeypatch.setenv('CALAMUM_CONTROL_DIR', str(control_dir))
    monkeypatch.setenv('CALAMUM_RESOURCE_PIN_MAX_AGE_SEC', '120')

    module_file = repo_root / 'src' / 'dummy.py'
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text('# dummy', encoding='utf-8')

    provider = TelemetryProvider(load_config(module_file))
    picked = provider._pick_active_jsonl()
    assert picked == sim_watch


def test_pick_active_jsonl_pins_fresh_route_resource_index(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / 'logs').mkdir(parents=True, exist_ok=True)

    health_dir = repo_root / 'logs' / 'health'
    data_dir = repo_root / 'logs' / 'data' / 'calamum'
    control_dir = repo_root / 'logs' / 'control' / 'calamum'
    health_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    wd = health_dir / 'wd.heartbeat'
    obs = health_dir / 'obs.heartbeat'
    wd.touch()
    obs.touch()

    (control_dir / 'observerctl_state.json').write_text(
        json.dumps({'source': 'real', 'mode': 'canary'}),
        encoding='utf-8',
    )

    # Fresh resource index should keep route pin even before metrics file exists.
    resource_index = data_dir / 'observer_derived' / 'real' / 'canary' / 'resource' / 'index.jsonl'
    resource_index.parent.mkdir(parents=True, exist_ok=True)
    resource_index.write_text('', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_WATCHDOG_HEARTBEAT_PATH', str(wd))
    monkeypatch.setenv('CALAMUM_OBSERVER_HEARTBEAT_PATH', str(obs))
    monkeypatch.setenv('CALAMUM_DATA_DIR', str(data_dir))
    monkeypatch.setenv('CALAMUM_CONTROL_DIR', str(control_dir))
    monkeypatch.setenv('CALAMUM_RESOURCE_PIN_MAX_AGE_SEC', '600')

    module_file = repo_root / 'src' / 'dummy.py'
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text('# dummy', encoding='utf-8')

    provider = TelemetryProvider(load_config(module_file))
    picked = provider._pick_active_jsonl()
    expected = data_dir / 'observer_derived' / 'real' / 'canary' / 'moltbook_metrics.jsonl'
    assert picked == expected


def test_jsonl_counter_resets_baseline_when_stream_path_changes(tmp_path: Path) -> None:
    data_dir = tmp_path / 'logs' / 'data' / 'calamum'
    a = data_dir / 'observer_derived' / 'sim' / 'watch' / 'moltbook_metrics.jsonl'
    b = data_dir / 'observer_derived' / 'real' / 'canary' / 'moltbook_metrics.jsonl'
    a.parent.mkdir(parents=True, exist_ok=True)
    b.parent.mkdir(parents=True, exist_ok=True)

    a.write_text('{"x":1}\n{"x":2}\n{"x":3}\n', encoding='utf-8')
    b.write_text('{"y":1}\n', encoding='utf-8')

    counter = _JsonlAppendCounter(data_dir=data_dir)
    counter.set_path(a)
    d1, t1 = counter.poll()
    assert t1 >= 3

    # Switch streams and append a new record on the new lane.
    counter.set_path(b)
    with b.open('a', encoding='utf-8') as f:
        f.write('{"y":2}\n')

    d2, t2 = counter.poll()
    assert d2 >= 1
    assert t2 >= 2
