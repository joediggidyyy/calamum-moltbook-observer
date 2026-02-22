from __future__ import annotations

from pathlib import Path
import sys


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from ops.telemetry import _archive_manifest_totals  # noqa: E402


def test_archive_manifest_totals_missing_returns_zero(tmp_path: Path) -> None:
    data_dir = tmp_path / 'logs' / 'data' / 'calamum'
    data_dir.mkdir(parents=True, exist_ok=True)
    total, non_sim, sim_est = _archive_manifest_totals(data_dir)
    assert total == 0
    assert non_sim == 0
    assert sim_est == 0