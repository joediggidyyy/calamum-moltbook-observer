from __future__ import annotations

import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from simulation import run_simulation as simulation_runner


def test_simulation_runner_lists_available_definitions(capsys) -> None:
    rc = simulation_runner.main(['--list-definitions'])
    out = capsys.readouterr().out

    assert rc == 0
    assert 'feedback-loop' in out
    assert 'metadata-contract' in out
    assert 'baseline-monitor-runtime' in out


def test_simulation_runner_dispatches_metadata_contract_definition(monkeypatch) -> None:
    called = {'metadata_contract': False}

    def fake_runner() -> int:
        called['metadata_contract'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_metadata_contract_probe', fake_runner)

    rc = simulation_runner.main(['metadata-contract'])

    assert rc == 0
    assert called['metadata_contract'] is True


def test_simulation_runner_defaults_to_feedback_loop_definition(monkeypatch) -> None:
    called = {'feedback': False}

    def fake_runner() -> int:
        called['feedback'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_feedback_loop_simulation', fake_runner)

    rc = simulation_runner.main([])

    assert rc == 0
    assert called['feedback'] is True