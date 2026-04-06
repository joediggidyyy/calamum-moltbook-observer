from __future__ import annotations

import json
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


def test_archive_manifest_totals_excludes_resource_rows(tmp_path: Path) -> None:
    data_dir = tmp_path / 'logs' / 'data' / 'calamum'
    archive_dir = data_dir / 'archive'
    archive_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        'moltbook_canary_20260210T081214.jsonl': {'records': 100},
        'resource_real_canary_baseline_20260210T081214_seg0001.jsonl': {'records': 40},
        'moltbook_canary_metrics_legacy_simulation.jsonl': {'records': 25},
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    total, non_sim, sim_est = _archive_manifest_totals(data_dir)
    assert total == 125
    assert non_sim == 100
    assert sim_est == 25