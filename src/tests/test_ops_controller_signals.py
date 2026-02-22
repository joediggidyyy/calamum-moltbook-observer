from __future__ import annotations

import json
from pathlib import Path

from ops.controller import CalamumController


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def test_controller_emits_signals(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    (repo_root / 'logs').mkdir(parents=True, exist_ok=True)
    out_dir = repo_root / 'logs' / 'control' / 'calamum'
    monkeypatch.setenv('CALAMUM_CONTROL_DIR', str(out_dir))

    c = CalamumController()

    ok, _ = c.force_refresh()
    assert ok is True
    ok, _ = c.isolate_node()
    assert ok is True
    ok, _ = c.reset_watchdog()
    assert ok is True
    ok, _ = c.kill_signal()
    assert ok is True

    assert (out_dir / 'refresh.signal.json').exists()
    assert (out_dir / 'isolate.signal.json').exists()
    assert (out_dir / 'watchdog_reset.signal.json').exists()
    assert (out_dir / 'kill.signal.json').exists()

    doc = _read(out_dir / 'kill.signal.json')
    assert doc['signal'] == 'kill'
    assert 'ts' in doc
