from __future__ import annotations

import json
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
    assert 'metadata-contract-regression' in out
    assert 'ds-wizard-hydration' in out
    assert 'ds-wizard-durability' in out
    assert 'baseline-monitor-runtime' in out
    assert 'validation-cycle-lineage' in out
    assert 'baseline-monitor-restart-continuity' in out
    assert 'baseline-monitor-state-recovery' in out


def test_simulation_runner_dispatches_metadata_contract_definition(monkeypatch) -> None:
    called = {'metadata_contract': False}

    def fake_runner() -> int:
        called['metadata_contract'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_metadata_contract_probe', fake_runner)

    rc = simulation_runner.main(['metadata-contract'])

    assert rc == 0
    assert called['metadata_contract'] is True


def test_simulation_runner_dispatches_metadata_contract_regression_definition(monkeypatch) -> None:
    called = {'metadata_contract_regression': False}

    def fake_runner() -> int:
        called['metadata_contract_regression'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_metadata_contract_regression_probe', fake_runner)

    rc = simulation_runner.main(['metadata-contract-regression'])

    assert rc == 0
    assert called['metadata_contract_regression'] is True


def test_simulation_runner_dispatches_ds_wizard_hydration_definition(monkeypatch) -> None:
    called = {'ds_wizard_hydration': False}

    def fake_runner() -> int:
        called['ds_wizard_hydration'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_ds_wizard_hydration_probe', fake_runner)

    rc = simulation_runner.main(['ds-wizard-hydration'])

    assert rc == 0
    assert called['ds_wizard_hydration'] is True


def test_simulation_runner_dispatches_ds_wizard_durability_definition(monkeypatch) -> None:
    called = {'ds_wizard_durability': False}

    def fake_runner() -> int:
        called['ds_wizard_durability'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_ds_wizard_durability_probe', fake_runner)

    rc = simulation_runner.main(['ds-wizard-durability'])

    assert rc == 0
    assert called['ds_wizard_durability'] is True


def test_simulation_runner_defaults_to_feedback_loop_definition(monkeypatch) -> None:
    called = {'feedback': False}

    def fake_runner() -> int:
        called['feedback'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_feedback_loop_simulation', fake_runner)

    rc = simulation_runner.main([])

    assert rc == 0
    assert called['feedback'] is True


def test_simulation_runner_dispatches_validation_cycle_lineage_definition(monkeypatch) -> None:
    called = {'lineage': False}

    def fake_runner() -> int:
        called['lineage'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_validation_cycle_lineage_probe', fake_runner)

    rc = simulation_runner.main(['validation-cycle-lineage'])

    assert rc == 0
    assert called['lineage'] is True


def test_simulation_runner_dispatches_restart_continuity_definition(monkeypatch) -> None:
    called = {'restart': False}

    def fake_runner() -> int:
        called['restart'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_baseline_monitor_restart_continuity_probe', fake_runner)

    rc = simulation_runner.main(['baseline-monitor-restart-continuity'])

    assert rc == 0
    assert called['restart'] is True


def test_simulation_runner_dispatches_state_recovery_definition(monkeypatch) -> None:
    called = {'recovery': False}

    def fake_runner() -> int:
        called['recovery'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_baseline_monitor_state_recovery_probe', fake_runner)

    rc = simulation_runner.main(['baseline-monitor-state-recovery'])

    assert rc == 0
    assert called['recovery'] is True


def _configure_probe_roots(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(simulation_runner, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(simulation_runner, 'FRAME4_PROBE_DIR', tmp_path / 'report_tmp' / 'frame4_metadata_contract_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME4_REGRESSION_PROBE_DIR', tmp_path / 'report_tmp' / 'frame4_metadata_contract_regression_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME4_DS_WIZARD_HYDRATION_PROBE_DIR', tmp_path / 'report_tmp' / 'frame4_ds_wizard_hydration_probe')
    monkeypatch.setattr(simulation_runner, 'JOB0022_PROBE_DIR', tmp_path / 'report_tmp' / 'job0022_baseline_monitor_runtime_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME5_LINEAGE_PROBE_DIR', tmp_path / 'report_tmp' / 'frame5_validation_cycle_lineage_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME6_DS_WIZARD_DURABILITY_PROBE_DIR', tmp_path / 'report_tmp' / 'frame6_ds_wizard_durability_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME6_RESTART_PROBE_DIR', tmp_path / 'report_tmp' / 'frame6_restart_continuity_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME6_RECOVERY_PROBE_DIR', tmp_path / 'report_tmp' / 'frame6_state_recovery_probe')


def test_new_probe_definitions_emit_retained_reports(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    scenarios = [
        (
            simulation_runner.run_metadata_contract_regression_probe,
            tmp_path / 'report_tmp' / 'frame4_metadata_contract_regression_probe' / 'run_index.jsonl',
            'frame4_metadata_contract_regression_probe.json',
        ),
        (
            simulation_runner.run_ds_wizard_hydration_probe,
            tmp_path / 'report_tmp' / 'frame4_ds_wizard_hydration_probe' / 'run_index.jsonl',
            'frame4_ds_wizard_hydration_probe.json',
        ),
        (
            simulation_runner.run_ds_wizard_durability_probe,
            tmp_path / 'report_tmp' / 'frame6_ds_wizard_durability_probe' / 'run_index.jsonl',
            'frame6_ds_wizard_durability_probe.json',
        ),
        (
            simulation_runner.run_validation_cycle_lineage_probe,
            tmp_path / 'report_tmp' / 'frame5_validation_cycle_lineage_probe' / 'run_index.jsonl',
            'frame5_validation_cycle_lineage_probe.json',
        ),
        (
            simulation_runner.run_baseline_monitor_restart_continuity_probe,
            tmp_path / 'report_tmp' / 'frame6_restart_continuity_probe' / 'run_index.jsonl',
            'frame6_restart_continuity_probe.json',
        ),
        (
            simulation_runner.run_baseline_monitor_state_recovery_probe,
            tmp_path / 'report_tmp' / 'frame6_state_recovery_probe' / 'run_index.jsonl',
            'frame6_state_recovery_probe.json',
        ),
    ]

    for runner, run_index_path, report_name in scenarios:
        rc = runner()
        assert rc == 0
        assert run_index_path.exists()

        rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
        assert rows
        latest = rows[-1]
        report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
        assert report_json.name == report_name
        assert report_json.exists()

        payload = json.loads(report_json.read_text(encoding='utf-8'))
        assert payload['next_bite_result'] == 'pass'
        assert all(bool(value) for value in payload['result_matrix'].values())