from __future__ import annotations

from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


import ops_dashboard as dashboard_module  # noqa: E402
from ops_dashboard import normalize_mode  # noqa: E402


def test_normalize_mode_aliases_and_fallback() -> None:
    assert normalize_mode('passive') == 'PASSIVE_LISTENER'
    assert normalize_mode('chaos') == 'CHAOS_MODE'
    assert normalize_mode('unknown-mode') == 'CANARY'


def test_snapshot_uses_live_total_and_raw_breakdown(monkeypatch) -> None:
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
    assert snap['records_breakdown']['session'] == 23
    assert snap['records_breakdown']['archive'] == 100