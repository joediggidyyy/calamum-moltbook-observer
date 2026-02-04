from __future__ import annotations

import json
from pathlib import Path

from calamum_observer_agent import handle_control_signals


def test_agent_handles_kill_and_marks_handled(tmp_path: Path) -> None:
    control_dir = tmp_path / 'logs' / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)

    kill_path = control_dir / 'kill.signal.json'
    kill_path.write_text(json.dumps({'signal': 'kill', 'ts': 'x'}), encoding='utf-8')

    should_exit, note = handle_control_signals(control_dir, 'node-1')
    assert should_exit is True
    assert note == 'KILL received'

    doc = json.loads(kill_path.read_text(encoding='utf-8'))
    assert doc.get('handled_at')
    assert doc.get('handled_by') == 'node-1'


def test_agent_handles_isolate(tmp_path: Path) -> None:
    control_dir = tmp_path / 'logs' / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)

    iso_path = control_dir / 'isolate.signal.json'
    iso_path.write_text(json.dumps({'signal': 'isolate', 'ts': 'x'}), encoding='utf-8')

    should_exit, note = handle_control_signals(control_dir, 'node-2')
    assert should_exit is False
    assert note == 'ISOLATE handled'

    state_path = control_dir / 'isolation.state.json'
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding='utf-8'))
    assert state['isolated'] is True
    assert state['node_id'] == 'node-2'
