from __future__ import annotations

from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


import ops_dashboard as dashboard_module  # noqa: E402
from ops_dashboard import normalize_mode, normalize_ops_runtime_mode  # noqa: E402


def test_normalize_mode_aliases_and_fallback() -> None:
    assert normalize_mode('passive') == 'PASSIVE_LISTENER'
    assert normalize_mode('chaos') == 'CHAOS_MODE'
    assert normalize_mode('unknown-mode') == 'CANARY'


def test_normalize_ops_runtime_mode_aliases() -> None:
    assert normalize_ops_runtime_mode('ACTIVE_GATED') == 'live'
    assert normalize_ops_runtime_mode('sampler') == 'watch'
    assert normalize_ops_runtime_mode('watch') == 'watch'


def test_density_bin_width_choices_are_deterministic() -> None:
    assert list(dashboard_module.DENSITY_BIN_WIDTH_CHOICES) == [
        'off',
        2,
        4,
        6,
        8,
        10,
        12,
        14,
        16,
        18,
        20,
    ]


def test_density_bin_width_default_is_valid_choice() -> None:
    assert dashboard_module.DENSITY_BIN_WIDTH_DEFAULT in dashboard_module.DENSITY_BIN_WIDTH_CHOICES
    assert dashboard_module.DENSITY_BIN_WIDTH_DEFAULT == 10


def test_snapshot_uses_live_total_and_display_breakdown(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_module, 'get_calamum_control_dir', lambda: Path('does-not-exist'))
    monkeypatch.setenv('CALAMUM_MOLTBOOK_SOURCE', 'real')
    monkeypatch.setenv('CALAMUM_OPS_MODE', 'canary')
    monkeypatch.setattr(
        dashboard_module.telemetry,
        'update',
        lambda: {
            'cpu': 10,
            'mem': 20,
            'total_records': 123,
            'records_total_display': 99,
            'new_records': 2,
            'records_session': 23,
            'records_archive': 100,
            'records_session_display': 0,
            'records_archive_display': 99,
            'resource_total_records': 0,
            'resource_archive_records': 0,
            'resource_total_display': 0,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'x.jsonl',
        },
    )

    snap = dashboard_module._compute_snapshot()
    assert snap['total_records'] == 123
    assert snap['records_total_display'] == 99
    assert snap['display_main_records'] == 99
    assert snap['source'] == 'real'
    assert snap['records_breakdown']['session'] == 0
    assert snap['records_breakdown']['archive'] == 99
    assert snap['records_breakdown']['session_raw'] == 23
    assert snap['records_breakdown']['archive_raw'] == 100
    assert snap['records_breakdown']['resource_session'] == 0
    assert snap['records_breakdown']['resource_archive'] == 0
    assert snap['records_breakdown']['resource_total'] == 0
    assert snap['records_breakdown_display']['main'] == 99
    assert snap['records_counter'] == {
        'total': 99,
        'session': 23,
        'archive': 99,
        'resource_session': 0,
        'resource_archive': 0,
        'resource_total': 0,
        'default_view': 'total',
    }


def test_snapshot_main_display_uses_session_only_for_sim(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_module, 'get_calamum_control_dir', lambda: Path('does-not-exist'))
    monkeypatch.setenv('CALAMUM_MOLTBOOK_SOURCE', 'sim')
    monkeypatch.setenv('CALAMUM_OPS_MODE', 'canary')
    monkeypatch.setattr(
        dashboard_module.telemetry,
        'update',
        lambda: {
            'cpu': 10,
            'mem': 20,
            'total_records': 123,
            'records_total_display': 99,
            'new_records': 2,
            'records_session': 23,
            'records_archive': 100,
            'records_session_display': 23,
            'records_archive_display': 99,
            'resource_total_records': 0,
            'resource_archive_records': 0,
            'resource_total_display': 0,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'x.jsonl',
        },
    )

    snap = dashboard_module._compute_snapshot()
    assert snap['total_records'] == 123
    assert snap['records_total_display'] == 99
    assert snap['display_main_records'] == 23
    assert snap['source'] == 'sim'
    assert snap['records_breakdown_display']['main'] == 23
    assert snap['records_counter'] == {
        'total': 99,
        'session': 23,
        'archive': 99,
        'resource_session': 0,
        'resource_archive': 0,
        'resource_total': 0,
        'default_view': 'session',
    }


def test_snapshot_main_display_uses_session_when_real_route_mismatch_to_sim(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_module, 'get_calamum_control_dir', lambda: Path('does-not-exist'))
    monkeypatch.setenv('CALAMUM_MOLTBOOK_SOURCE', 'real')
    monkeypatch.setenv('CALAMUM_OPS_MODE', 'canary')
    monkeypatch.setattr(
        dashboard_module.telemetry,
        'update',
        lambda: {
            'cpu': 10,
            'mem': 20,
            'total_records': 500,
            'records_total_display': 200,
            'new_records': 4,
            'records_session': 50,
            'records_archive': 450,
            'records_session_display': 0,
            'records_archive_display': 200,
            'resource_total_records': 12,
            'resource_archive_records': 30,
            'resource_total_display': 42,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'observer_derived/sim/watch/moltbook_metrics.jsonl',
            'route_stream_mismatch': True,
            'active_stream_source': 'sim',
            'active_stream_mode': 'watch',
        },
    )

    snap = dashboard_module._compute_snapshot()
    assert snap['source'] == 'real'
    assert snap['route_stream_mismatch'] is True
    assert snap['active_stream_source'] == 'sim'
    assert snap['active_stream_mode'] == 'watch'
    assert snap['display_main_records'] == 500
    assert snap['records_counter'] == {
        'total': 500,
        'session': 50,
        'archive': 200,
        'resource_session': 12,
        'resource_archive': 30,
        'resource_total': 42,
        'default_view': 'total',
    }


def test_snapshot_degrades_when_live_source_fetch_errors(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_module, 'get_calamum_control_dir', lambda: Path('does-not-exist'))
    monkeypatch.setenv('CALAMUM_MOLTBOOK_SOURCE', 'real')
    monkeypatch.setenv('CALAMUM_OPS_MODE', 'canary')

    dashboard_module.state.log_items = []
    dashboard_module.state.log_seq = 0
    dashboard_module.state._last_obs_active = True
    dashboard_module.state._last_wd_active = True
    dashboard_module.state._last_lib_active = True
    dashboard_module.state._last_source_fetch_signature = None
    dashboard_module.state._last_collection_state = None

    monkeypatch.setattr(
        dashboard_module.telemetry,
        'update',
        lambda: {
            'cpu': 10,
            'mem': 20,
            'total_records': 123,
            'records_total_display': 99,
            'new_records': 0,
            'records_session': 23,
            'records_archive': 100,
            'records_session_display': 0,
            'records_archive_display': 99,
            'resource_total_records': 0,
            'resource_archive_records': 0,
            'resource_total_display': 0,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'x.jsonl',
            'runtime_source_fetch': {'status': 'err', 'error_kind': 'http_404', 'endpoint': 'feed'},
            'runtime_collection_state': {'state': 'error', 'status': 'err'},
        },
    )

    snap = dashboard_module._compute_snapshot()
    assert snap['status'] == {'text': 'DEGRADED', 'color': 'orange'}
    assert snap['status_detail'] == 'live source fetch error (http_404 @ feed)'
    assert snap['runtime_source_fetch']['endpoint'] == 'feed'
    assert snap['runtime_collection_state']['state'] == 'error'
    assert any('Live source fetch error' in line for _, line in dashboard_module.state.log_items)
    assert any('Collection state -> ERROR' in line for _, line in dashboard_module.state.log_items)


def test_snapshot_logs_live_source_fetch_recovery(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_module, 'get_calamum_control_dir', lambda: Path('does-not-exist'))
    monkeypatch.setenv('CALAMUM_MOLTBOOK_SOURCE', 'real')
    monkeypatch.setenv('CALAMUM_OPS_MODE', 'canary')

    dashboard_module.state.log_items = []
    dashboard_module.state.log_seq = 0
    dashboard_module.state._last_obs_active = True
    dashboard_module.state._last_wd_active = True
    dashboard_module.state._last_lib_active = True
    dashboard_module.state._last_source_fetch_signature = ('err', 'http_404', 'feed')
    dashboard_module.state._last_collection_state = 'error'

    monkeypatch.setattr(
        dashboard_module.telemetry,
        'update',
        lambda: {
            'cpu': 10,
            'mem': 20,
            'total_records': 123,
            'records_total_display': 99,
            'new_records': 0,
            'records_session': 23,
            'records_archive': 100,
            'records_session_display': 0,
            'records_archive_display': 99,
            'resource_total_records': 0,
            'resource_archive_records': 0,
            'resource_total_display': 0,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'x.jsonl',
            'runtime_source_fetch': {'status': 'ok', 'observed': True},
            'runtime_collection_state': {'state': 'idle', 'status': 'ok'},
        },
    )

    snap = dashboard_module._compute_snapshot()
    assert snap['status'] == {'text': 'NOMINAL', 'color': 'green'}
    assert any('Live source fetch recovered' in line for _, line in dashboard_module.state.log_items)
    assert any('Collection state -> IDLE' in line for _, line in dashboard_module.state.log_items)


def test_snapshot_reports_live_collection_detail_when_healthy(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_module, 'get_calamum_control_dir', lambda: Path('does-not-exist'))
    monkeypatch.setenv('CALAMUM_MOLTBOOK_SOURCE', 'real')
    monkeypatch.setenv('CALAMUM_OPS_MODE', 'live')

    dashboard_module.state.log_items = []
    dashboard_module.state.log_seq = 0
    dashboard_module.state._last_obs_active = True
    dashboard_module.state._last_wd_active = True
    dashboard_module.state._last_lib_active = True
    dashboard_module.state._last_source_fetch_signature = ('ok', '', '')
    dashboard_module.state._last_collection_state = 'collecting'

    monkeypatch.setattr(
        dashboard_module.telemetry,
        'update',
        lambda: {
            'cpu': 10,
            'mem': 20,
            'total_records': 123,
            'records_total_display': 123,
            'new_records': 2,
            'records_session': 123,
            'records_archive': 0,
            'records_session_display': 123,
            'records_archive_display': 0,
            'resource_total_records': 0,
            'resource_archive_records': 0,
            'resource_total_display': 0,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'observer_derived/real/live/moltbook_metrics.jsonl',
            'runtime_source_fetch': {'status': 'ok', 'observed': True},
            'runtime_collection_state': {'state': 'collecting', 'status': 'ok', 'metrics_age_seconds': 1.26},
        },
    )

    snap = dashboard_module._compute_snapshot()
    assert snap['status'] == {'text': 'NOMINAL', 'color': 'green'}
    assert snap['status_detail'] == 'live collection healthy (metrics 1.3s old)'


def test_snapshot_aggregates_resource_archive_log_until_interval(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_module, 'get_calamum_control_dir', lambda: Path('does-not-exist'))
    monkeypatch.setenv('CALAMUM_MOLTBOOK_SOURCE', 'real')
    monkeypatch.setenv('CALAMUM_OPS_MODE', 'canary')

    dashboard_module.state.log_items = []
    dashboard_module.state.log_seq = 0
    dashboard_module.state._last_obs_active = True
    dashboard_module.state._last_wd_active = True
    dashboard_module.state._last_lib_active = True
    dashboard_module.state._last_source_fetch_signature = ('ok', '', '')
    dashboard_module.state._last_collection_state = 'idle'
    dashboard_module.state._last_resource_archive_count = 10
    dashboard_module.state._pending_resource_archive_delta = 0
    dashboard_module.state._last_resource_archive_log_at = 1000.0

    current_time = {'value': 1060.0}
    monkeypatch.setattr(dashboard_module.time, 'time', lambda: current_time['value'])
    monkeypatch.setattr(dashboard_module.psutil, 'boot_time', lambda: 0.0)

    snapshots = iter([
        {
            'cpu': 10,
            'mem': 20,
            'total_records': 0,
            'records_total_display': 0,
            'new_records': 0,
            'records_session': 0,
            'records_archive': 0,
            'records_session_display': 0,
            'records_archive_display': 0,
            'resource_total_records': 0,
            'resource_archive_records': 12,
            'resource_total_display': 12,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'x.jsonl',
            'runtime_source_fetch': {'status': 'ok', 'observed': True},
            'runtime_collection_state': {'state': 'idle', 'status': 'ok'},
        },
        {
            'cpu': 10,
            'mem': 20,
            'total_records': 0,
            'records_total_display': 0,
            'new_records': 0,
            'records_session': 0,
            'records_archive': 0,
            'records_session_display': 0,
            'records_archive_display': 0,
            'resource_total_records': 0,
            'resource_archive_records': 15,
            'resource_total_display': 15,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'x.jsonl',
            'runtime_source_fetch': {'status': 'ok', 'observed': True},
            'runtime_collection_state': {'state': 'idle', 'status': 'ok'},
        },
        {
            'cpu': 10,
            'mem': 20,
            'total_records': 0,
            'records_total_display': 0,
            'new_records': 0,
            'records_session': 0,
            'records_archive': 0,
            'records_session_display': 0,
            'records_archive_display': 0,
            'resource_total_records': 0,
            'resource_archive_records': 15,
            'resource_total_display': 15,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'x.jsonl',
            'runtime_source_fetch': {'status': 'ok', 'observed': True},
            'runtime_collection_state': {'state': 'idle', 'status': 'ok'},
        },
    ])
    monkeypatch.setattr(dashboard_module.telemetry, 'update', lambda: next(snapshots))

    dashboard_module._compute_snapshot()
    current_time['value'] = 1110.0
    dashboard_module._compute_snapshot()
    assert not any('[RES] Archived +' in line for _, line in dashboard_module.state.log_items)

    current_time['value'] = 1125.0
    dashboard_module._compute_snapshot()
    assert any('[RES] Archived +5 resource records (Total: 15)' in line for _, line in dashboard_module.state.log_items)


def test_snapshot_flushes_resource_archive_log_on_collection_state_change(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_module, 'get_calamum_control_dir', lambda: Path('does-not-exist'))
    monkeypatch.setenv('CALAMUM_MOLTBOOK_SOURCE', 'real')
    monkeypatch.setenv('CALAMUM_OPS_MODE', 'canary')

    dashboard_module.state.log_items = []
    dashboard_module.state.log_seq = 0
    dashboard_module.state._last_obs_active = True
    dashboard_module.state._last_wd_active = True
    dashboard_module.state._last_lib_active = True
    dashboard_module.state._last_source_fetch_signature = ('ok', '', '')
    dashboard_module.state._last_collection_state = 'idle'
    dashboard_module.state._last_resource_archive_count = 10
    dashboard_module.state._pending_resource_archive_delta = 0
    dashboard_module.state._last_resource_archive_log_at = 1000.0

    current_time = {'value': 1060.0}
    monkeypatch.setattr(dashboard_module.time, 'time', lambda: current_time['value'])
    monkeypatch.setattr(dashboard_module.psutil, 'boot_time', lambda: 0.0)

    snapshots = iter([
        {
            'cpu': 10,
            'mem': 20,
            'total_records': 0,
            'records_total_display': 0,
            'new_records': 0,
            'records_session': 0,
            'records_archive': 0,
            'records_session_display': 0,
            'records_archive_display': 0,
            'resource_total_records': 0,
            'resource_archive_records': 12,
            'resource_total_display': 12,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'x.jsonl',
            'runtime_source_fetch': {'status': 'ok', 'observed': True},
            'runtime_collection_state': {'state': 'idle', 'status': 'ok'},
        },
        {
            'cpu': 10,
            'mem': 20,
            'total_records': 0,
            'records_total_display': 0,
            'new_records': 0,
            'records_session': 0,
            'records_archive': 0,
            'records_session_display': 0,
            'records_archive_display': 0,
            'resource_total_records': 0,
            'resource_archive_records': 12,
            'resource_total_display': 12,
            'density_bins': [0] * 12,
            'density_raw_window': [0] * 12,
            'density_slice_sec': 2.0,
            'watchdog_active': True,
            'observer_active': True,
            'librarian_active': True,
            'watchdog_stats': {},
            'observer_stats': {},
            'librarian_stats': {},
            'active_jsonl_path': 'x.jsonl',
            'runtime_source_fetch': {'status': 'ok', 'observed': True},
            'runtime_collection_state': {'state': 'error', 'status': 'err'},
        },
    ])
    monkeypatch.setattr(dashboard_module.telemetry, 'update', lambda: next(snapshots))

    dashboard_module._compute_snapshot()
    assert not any('[RES] Archived +' in line for _, line in dashboard_module.state.log_items)

    current_time['value'] = 1070.0
    dashboard_module._compute_snapshot()
    assert any('[RES] Archived +2 resource records (Total: 12)' in line for _, line in dashboard_module.state.log_items)