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
    assert 'ds-wizard-stale-state-continuity' in out
    assert 'ds-wizard-durability' in out
    assert 'ds-wizard-labeled-eval-contract-coherence' in out
    assert 'ds-wizard-blocked-execute-truthfulness' in out
    assert 'ds-alias-coherence' in out
    assert 'baseline-monitor-runtime' in out
    assert 'validation-cycle-lineage' in out
    assert 'baseline-monitor-restart-continuity' in out
    assert 'baseline-monitor-state-recovery' in out
    assert 'librarian-access-exchange' in out
    assert 'librarian-vault-controls' in out


def test_simulation_runner_lists_librarian_sandbox_definitions(capsys) -> None:
    rc = simulation_runner.main(['--list-definitions'])
    out = capsys.readouterr().out

    assert rc == 0
    assert 'librarian-access-exchange' in out
    assert 'librarian-vault-controls' in out


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


def test_simulation_runner_dispatches_ds_wizard_stale_state_continuity_definition(monkeypatch) -> None:
    called = {'ds_wizard_stale_state_continuity': False}

    def fake_runner() -> int:
        called['ds_wizard_stale_state_continuity'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_ds_wizard_stale_state_continuity_probe', fake_runner)

    rc = simulation_runner.main(['ds-wizard-stale-state-continuity'])

    assert rc == 0
    assert called['ds_wizard_stale_state_continuity'] is True


def test_simulation_runner_dispatches_ds_wizard_durability_definition(monkeypatch) -> None:
    called = {'ds_wizard_durability': False}

    def fake_runner() -> int:
        called['ds_wizard_durability'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_ds_wizard_durability_probe', fake_runner)

    rc = simulation_runner.main(['ds-wizard-durability'])

    assert rc == 0
    assert called['ds_wizard_durability'] is True


def test_simulation_runner_dispatches_ds_wizard_labeled_eval_contract_coherence_definition(monkeypatch) -> None:
    called = {'ds_wizard_labeled_eval_contract_coherence': False}

    def fake_runner() -> int:
        called['ds_wizard_labeled_eval_contract_coherence'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_ds_wizard_labeled_eval_contract_coherence_probe', fake_runner)

    rc = simulation_runner.main(['ds-wizard-labeled-eval-contract-coherence'])

    assert rc == 0
    assert called['ds_wizard_labeled_eval_contract_coherence'] is True


def test_simulation_runner_dispatches_ds_wizard_blocked_execute_truthfulness_definition(monkeypatch) -> None:
    called = {'ds_wizard_blocked_execute_truthfulness': False}

    def fake_runner() -> int:
        called['ds_wizard_blocked_execute_truthfulness'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_ds_wizard_blocked_execute_truthfulness_probe', fake_runner)

    rc = simulation_runner.main(['ds-wizard-blocked-execute-truthfulness'])

    assert rc == 0
    assert called['ds_wizard_blocked_execute_truthfulness'] is True


def test_simulation_runner_dispatches_ds_alias_coherence_definition(monkeypatch) -> None:
    called = {'ds_alias_coherence': False}

    def fake_runner() -> int:
        called['ds_alias_coherence'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_ds_alias_coherence_probe', fake_runner)

    rc = simulation_runner.main(['ds-alias-coherence'])

    assert rc == 0
    assert called['ds_alias_coherence'] is True


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


def test_simulation_runner_dispatches_librarian_access_exchange_definition(monkeypatch) -> None:
    called = {'access_exchange': False}

    def fake_runner() -> int:
        called['access_exchange'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_librarian_access_exchange_probe', fake_runner)

    rc = simulation_runner.main(['librarian-access-exchange'])

    assert rc == 0
    assert called['access_exchange'] is True


def test_simulation_runner_dispatches_librarian_vault_controls_definition(monkeypatch) -> None:
    called = {'vault_controls': False}

    def fake_runner() -> int:
        called['vault_controls'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_librarian_vault_controls_probe', fake_runner)

    rc = simulation_runner.main(['librarian-vault-controls'])

    assert rc == 0
    assert called['vault_controls'] is True


def _configure_probe_roots(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(simulation_runner, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(simulation_runner, 'FRAME4_PROBE_DIR', tmp_path / 'report_tmp' / 'frame4_metadata_contract_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME4_REGRESSION_PROBE_DIR', tmp_path / 'report_tmp' / 'frame4_metadata_contract_regression_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME4_DS_WIZARD_HYDRATION_PROBE_DIR', tmp_path / 'report_tmp' / 'frame4_ds_wizard_hydration_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEB_DS_WIZARD_STALE_STATE_CONTINUITY_PROBE_DIR', tmp_path / 'report_tmp' / 'frameb_ds_wizard_stale_state_continuity_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMED_DS_ALIAS_COHERENCE_PROBE_DIR', tmp_path / 'report_tmp' / 'framed_ds_alias_coherence_probe')
    monkeypatch.setattr(simulation_runner, 'JOB0022_PROBE_DIR', tmp_path / 'report_tmp' / 'job0022_baseline_monitor_runtime_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME5_LINEAGE_PROBE_DIR', tmp_path / 'report_tmp' / 'frame5_validation_cycle_lineage_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME6_DS_WIZARD_DURABILITY_PROBE_DIR', tmp_path / 'report_tmp' / 'frame6_ds_wizard_durability_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEB_DS_WIZARD_LABELED_EVAL_CONTRACT_COHERENCE_PROBE_DIR', tmp_path / 'report_tmp' / 'frameb_ds_wizard_labeled_eval_contract_coherence_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEB_DS_WIZARD_BLOCKED_EXECUTE_TRUTHFULNESS_PROBE_DIR', tmp_path / 'report_tmp' / 'frameb_ds_wizard_blocked_execute_truthfulness_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME6_RESTART_PROBE_DIR', tmp_path / 'report_tmp' / 'frame6_restart_continuity_probe')
    monkeypatch.setattr(simulation_runner, 'FRAME6_RECOVERY_PROBE_DIR', tmp_path / 'report_tmp' / 'frame6_state_recovery_probe')
    monkeypatch.setattr(simulation_runner, 'LIBRARIAN_ACCESS_EXCHANGE_PROBE_DIR', tmp_path / 'report_tmp' / 'librarian_access_exchange_probe')
    monkeypatch.setattr(simulation_runner, 'LIBRARIAN_VAULT_CONTROLS_PROBE_DIR', tmp_path / 'report_tmp' / 'librarian_vault_controls_probe')


def test_new_probe_definitions_emit_retained_reports(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    wizard_view_reports = {
        'frame4_ds_wizard_hydration_probe.json',
        'frameb_ds_wizard_stale_state_continuity_probe.json',
        'frame6_ds_wizard_durability_probe.json',
        'framed_ds_alias_coherence_probe.json',
    }

    wizard_probe_expectations = {
        'frame4_ds_wizard_hydration_probe.json': [
            'hydrate_execution_ready',
            'latest_context_execution_truthful',
            'report_preview_lists_dataset_and_model_artifacts',
        ],
        'frameb_ds_wizard_stale_state_continuity_probe.json': [
            'direct_train_hydration_refreshes_features_csv',
            'preview_command_uses_refreshed_labels',
            'preview_dataset_manifest_matches_train_context',
        ],
        'frame6_ds_wizard_durability_probe.json': [
            'draft_round_trip_command_preview',
            'load_report_section_persisted',
            'report_preview_lists_run_dataset_and_model_artifacts',
        ],
        'frameb_ds_wizard_labeled_eval_contract_coherence_probe.json': [
            'supervised_train_succeeds_on_label_column',
            'wizard_eval_packet_has_labels_true',
            'run_json_thresholding_is_labeled_mode',
        ],
        'frameb_ds_wizard_blocked_execute_truthfulness_probe.json': [
            'execute_packet_no_go',
            'execute_reason_code_is_validation_block',
            'execute_packet_claims_no_success_artifacts',
        ],
        'framed_ds_alias_coherence_probe.json': [
            'build_preview_ready',
            'score_preview_ready',
            'preview_packets_display_registered_alias',
        ],
    }

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
            simulation_runner.run_ds_wizard_stale_state_continuity_probe,
            tmp_path / 'report_tmp' / 'frameb_ds_wizard_stale_state_continuity_probe' / 'run_index.jsonl',
            'frameb_ds_wizard_stale_state_continuity_probe.json',
        ),
        (
            simulation_runner.run_ds_wizard_durability_probe,
            tmp_path / 'report_tmp' / 'frame6_ds_wizard_durability_probe' / 'run_index.jsonl',
            'frame6_ds_wizard_durability_probe.json',
        ),
        (
            simulation_runner.run_ds_wizard_labeled_eval_contract_coherence_probe,
            tmp_path / 'report_tmp' / 'frameb_ds_wizard_labeled_eval_contract_coherence_probe' / 'run_index.jsonl',
            'frameb_ds_wizard_labeled_eval_contract_coherence_probe.json',
        ),
        (
            simulation_runner.run_ds_wizard_blocked_execute_truthfulness_probe,
            tmp_path / 'report_tmp' / 'frameb_ds_wizard_blocked_execute_truthfulness_probe' / 'run_index.jsonl',
            'frameb_ds_wizard_blocked_execute_truthfulness_probe.json',
        ),
        (
            simulation_runner.run_ds_alias_coherence_probe,
            tmp_path / 'report_tmp' / 'framed_ds_alias_coherence_probe' / 'run_index.jsonl',
            'framed_ds_alias_coherence_probe.json',
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

        expected_keys = wizard_probe_expectations.get(report_name, [])
        if expected_keys:
            wizard_command_runs = [
                command
                for command in payload['command_runs'].values()
                if isinstance(command, dict) and list(command.get('args', []))[:2] == ['ds', 'wizard']
            ]
            assert wizard_command_runs
            if report_name in wizard_view_reports:
                assert any(
                    isinstance(command.get('stdout_json', {}), dict) and bool(command['stdout_json'].get('wizard_view'))
                    for command in wizard_command_runs
                )
            for key in expected_keys:
                assert payload['result_matrix'][key] is True


def test_librarian_access_exchange_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_librarian_access_exchange_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'librarian_access_exchange_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'librarian_access_exchange_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert all(bool(value) for value in payload['result_matrix'].values())


def test_librarian_vault_controls_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_librarian_vault_controls_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'librarian_vault_controls_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'librarian_vault_controls_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert all(bool(value) for value in payload['result_matrix'].values())