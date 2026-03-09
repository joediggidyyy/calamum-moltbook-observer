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
    assert snap['records_breakdown_display']['main'] == 99


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