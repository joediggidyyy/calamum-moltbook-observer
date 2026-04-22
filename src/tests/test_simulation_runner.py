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
    assert 'ds-wizard-execute-failure-truthfulness' in out
    assert 'ds-alias-coherence' in out
    assert 'names-only-persistence-escape' in out
    assert 'packet-artifact-divergence-truthfulness' in out
    assert 'watchdog-heartbeat-spoof-resistance' in out
    assert 'resource-lockdown-chaos' in out
    assert 'baseline-authority-tamper' in out
    assert 'report-lineage-forgery' in out
    assert 'keysmith-version-parity-break' in out
    assert 'public-report-boundary-escape' in out
    assert 'bootstrap-root-starvation' in out
    assert 'sandbox-catalog-authority-drift' in out
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


def test_simulation_runner_dispatches_ds_wizard_execute_failure_truthfulness_definition(monkeypatch) -> None:
    called = {'ds_wizard_execute_failure_truthfulness': False}

    def fake_runner() -> int:
        called['ds_wizard_execute_failure_truthfulness'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_ds_wizard_execute_failure_truthfulness_probe', fake_runner)

    rc = simulation_runner.main(['ds-wizard-execute-failure-truthfulness'])

    assert rc == 0
    assert called['ds_wizard_execute_failure_truthfulness'] is True


def test_simulation_runner_dispatches_ds_alias_coherence_definition(monkeypatch) -> None:
    called = {'ds_alias_coherence': False}

    def fake_runner() -> int:
        called['ds_alias_coherence'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_ds_alias_coherence_probe', fake_runner)

    rc = simulation_runner.main(['ds-alias-coherence'])

    assert rc == 0
    assert called['ds_alias_coherence'] is True


def test_simulation_runner_dispatches_names_only_persistence_escape_definition(monkeypatch) -> None:
    called = {'names_only_persistence_escape': False}

    def fake_runner() -> int:
        called['names_only_persistence_escape'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_names_only_persistence_escape_probe', fake_runner)

    rc = simulation_runner.main(['names-only-persistence-escape'])

    assert rc == 0
    assert called['names_only_persistence_escape'] is True


def test_simulation_runner_dispatches_packet_artifact_divergence_truthfulness_definition(monkeypatch) -> None:
    called = {'packet_artifact_divergence_truthfulness': False}

    def fake_runner() -> int:
        called['packet_artifact_divergence_truthfulness'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_packet_artifact_divergence_truthfulness_probe', fake_runner)

    rc = simulation_runner.main(['packet-artifact-divergence-truthfulness'])

    assert rc == 0
    assert called['packet_artifact_divergence_truthfulness'] is True


def test_simulation_runner_dispatches_watchdog_heartbeat_spoof_resistance_definition(monkeypatch) -> None:
    called = {'watchdog_heartbeat_spoof_resistance': False}

    def fake_runner() -> int:
        called['watchdog_heartbeat_spoof_resistance'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_watchdog_heartbeat_spoof_resistance_probe', fake_runner)

    rc = simulation_runner.main(['watchdog-heartbeat-spoof-resistance'])

    assert rc == 0
    assert called['watchdog_heartbeat_spoof_resistance'] is True


def test_simulation_runner_dispatches_resource_lockdown_chaos_definition(monkeypatch) -> None:
    called = {'resource_lockdown_chaos': False}

    def fake_runner() -> int:
        called['resource_lockdown_chaos'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_resource_lockdown_chaos_probe', fake_runner)

    rc = simulation_runner.main(['resource-lockdown-chaos'])

    assert rc == 0
    assert called['resource_lockdown_chaos'] is True


def test_simulation_runner_dispatches_baseline_authority_tamper_definition(monkeypatch) -> None:
    called = {'baseline_authority_tamper': False}

    def fake_runner() -> int:
        called['baseline_authority_tamper'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_baseline_authority_tamper_probe', fake_runner)

    rc = simulation_runner.main(['baseline-authority-tamper'])

    assert rc == 0
    assert called['baseline_authority_tamper'] is True


def test_simulation_runner_dispatches_report_lineage_forgery_definition(monkeypatch) -> None:
    called = {'report_lineage_forgery': False}

    def fake_runner() -> int:
        called['report_lineage_forgery'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_report_lineage_forgery_probe', fake_runner)

    rc = simulation_runner.main(['report-lineage-forgery'])

    assert rc == 0
    assert called['report_lineage_forgery'] is True


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


def test_simulation_runner_dispatches_keysmith_version_parity_break_definition(monkeypatch) -> None:
    called = {'keysmith_version_parity_break': False}

    def fake_runner() -> int:
        called['keysmith_version_parity_break'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_keysmith_version_parity_break_probe', fake_runner)

    rc = simulation_runner.main(['keysmith-version-parity-break'])

    assert rc == 0
    assert called['keysmith_version_parity_break'] is True


def test_simulation_runner_dispatches_public_report_boundary_escape_definition(monkeypatch) -> None:
    called = {'public_report_boundary_escape': False}

    def fake_runner() -> int:
        called['public_report_boundary_escape'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_public_report_boundary_escape_probe', fake_runner)

    rc = simulation_runner.main(['public-report-boundary-escape'])

    assert rc == 0
    assert called['public_report_boundary_escape'] is True


def test_simulation_runner_dispatches_bootstrap_root_starvation_definition(monkeypatch) -> None:
    called = {'bootstrap_root_starvation': False}

    def fake_runner() -> int:
        called['bootstrap_root_starvation'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_bootstrap_root_starvation_probe', fake_runner)

    rc = simulation_runner.main(['bootstrap-root-starvation'])

    assert rc == 0
    assert called['bootstrap_root_starvation'] is True


def test_simulation_runner_dispatches_sandbox_catalog_authority_drift_definition(monkeypatch) -> None:
    called = {'sandbox_catalog_authority_drift': False}

    def fake_runner() -> int:
        called['sandbox_catalog_authority_drift'] = True
        return 0

    monkeypatch.setattr(simulation_runner, 'run_sandbox_catalog_authority_drift_probe', fake_runner)

    rc = simulation_runner.main(['sandbox-catalog-authority-drift'])

    assert rc == 0
    assert called['sandbox_catalog_authority_drift'] is True


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
    monkeypatch.setattr(simulation_runner, 'FRAMEB_DS_WIZARD_EXECUTE_FAILURE_TRUTHFULNESS_PROBE_DIR', tmp_path / 'report_tmp' / 'frameb_ds_wizard_execute_failure_truthfulness_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEC_NAMES_ONLY_PERSISTENCE_ESCAPE_PROBE_DIR', tmp_path / 'report_tmp' / 'framec_names_only_persistence_escape_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEC_PACKET_ARTIFACT_DIVERGENCE_TRUTHFULNESS_PROBE_DIR', tmp_path / 'report_tmp' / 'framec_packet_artifact_divergence_truthfulness_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMED_WATCHDOG_HEARTBEAT_SPOOF_RESISTANCE_PROBE_DIR', tmp_path / 'report_tmp' / 'framed_watchdog_heartbeat_spoof_resistance_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMED_RESOURCE_LOCKDOWN_CHAOS_PROBE_DIR', tmp_path / 'report_tmp' / 'framed_resource_lockdown_chaos_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEE_BASELINE_AUTHORITY_TAMPER_PROBE_DIR', tmp_path / 'report_tmp' / 'framee_baseline_authority_tamper_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEE_REPORT_LINEAGE_FORGERY_PROBE_DIR', tmp_path / 'report_tmp' / 'framee_report_lineage_forgery_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEF_KEYSMITH_VERSION_PARITY_BREAK_PROBE_DIR', tmp_path / 'report_tmp' / 'framef_keysmith_version_parity_break_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEG_PUBLIC_REPORT_BOUNDARY_ESCAPE_PROBE_DIR', tmp_path / 'report_tmp' / 'frameg_public_report_boundary_escape_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEG_BOOTSTRAP_ROOT_STARVATION_PROBE_DIR', tmp_path / 'report_tmp' / 'frameg_bootstrap_root_starvation_probe')
    monkeypatch.setattr(simulation_runner, 'FRAMEG_SANDBOX_CATALOG_AUTHORITY_DRIFT_PROBE_DIR', tmp_path / 'report_tmp' / 'frameg_sandbox_catalog_authority_drift_probe')
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
    wizard_report_names = {
        'frame4_ds_wizard_hydration_probe.json',
        'frameb_ds_wizard_stale_state_continuity_probe.json',
        'frame6_ds_wizard_durability_probe.json',
        'frameb_ds_wizard_labeled_eval_contract_coherence_probe.json',
        'frameb_ds_wizard_blocked_execute_truthfulness_probe.json',
        'frameb_ds_wizard_execute_failure_truthfulness_probe.json',
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
        'frameb_ds_wizard_execute_failure_truthfulness_probe.json': [
            'derived_reason_code_is_execution_failure',
            'terminal_transient_mentions_execute_failed',
            'render_keeps_processing_ready',
        ],
        'framed_ds_alias_coherence_probe.json': [
            'build_preview_ready',
            'score_preview_ready',
            'preview_packets_display_registered_alias',
        ],
        'framee_baseline_authority_tamper_probe.json': [
            'comparison_baseline_candidate_exists_before_tamper',
            'explicit_candidate_repaired_from_authority',
            'report_context_packet_restored_selector_entry',
        ],
        'framee_report_lineage_forgery_probe.json': [
            'pre_tamper_publication_eligible',
            'tampered_publication_reason_emitted',
            'collection_alias_not_materialized',
        ],
        'framef_keysmith_version_parity_break_probe.json': [
            'positive_proof_review_go',
            'tampered_proof_review_no_go',
            'tampered_proof_surfaces_version_mismatch',
        ],
        'frameg_public_report_boundary_escape_probe.json': [
            'publication_refresh_go',
            'absolute_project_root_removed_from_public_markdown',
            'local_authority_lure_removed_from_reader_surfaces',
        ],
        'frameg_bootstrap_root_starvation_probe.json': [
            'check_bootstrap_no_go',
            'mutating_bootstrap_no_go',
            'blocked_root_reason_emitted',
        ],
        'frameg_sandbox_catalog_authority_drift_probe.json': [
            'catalog_ids_unique',
            'prefix_alias_lookup_denied',
            'stale_run_reason_emitted',
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
            simulation_runner.run_ds_wizard_execute_failure_truthfulness_probe,
            tmp_path / 'report_tmp' / 'frameb_ds_wizard_execute_failure_truthfulness_probe' / 'run_index.jsonl',
            'frameb_ds_wizard_execute_failure_truthfulness_probe.json',
        ),
        (
            simulation_runner.run_ds_alias_coherence_probe,
            tmp_path / 'report_tmp' / 'framed_ds_alias_coherence_probe' / 'run_index.jsonl',
            'framed_ds_alias_coherence_probe.json',
        ),
        (
            simulation_runner.run_names_only_persistence_escape_probe,
            tmp_path / 'report_tmp' / 'framec_names_only_persistence_escape_probe' / 'run_index.jsonl',
            'framec_names_only_persistence_escape_probe.json',
        ),
        (
            simulation_runner.run_packet_artifact_divergence_truthfulness_probe,
            tmp_path / 'report_tmp' / 'framec_packet_artifact_divergence_truthfulness_probe' / 'run_index.jsonl',
            'framec_packet_artifact_divergence_truthfulness_probe.json',
        ),
        (
            simulation_runner.run_watchdog_heartbeat_spoof_resistance_probe,
            tmp_path / 'report_tmp' / 'framed_watchdog_heartbeat_spoof_resistance_probe' / 'run_index.jsonl',
            'framed_watchdog_heartbeat_spoof_resistance_probe.json',
        ),
        (
            simulation_runner.run_resource_lockdown_chaos_probe,
            tmp_path / 'report_tmp' / 'framed_resource_lockdown_chaos_probe' / 'run_index.jsonl',
            'framed_resource_lockdown_chaos_probe.json',
        ),
        (
            simulation_runner.run_baseline_authority_tamper_probe,
            tmp_path / 'report_tmp' / 'framee_baseline_authority_tamper_probe' / 'run_index.jsonl',
            'framee_baseline_authority_tamper_probe.json',
        ),
        (
            simulation_runner.run_report_lineage_forgery_probe,
            tmp_path / 'report_tmp' / 'framee_report_lineage_forgery_probe' / 'run_index.jsonl',
            'framee_report_lineage_forgery_probe.json',
        ),
        (
            simulation_runner.run_keysmith_version_parity_break_probe,
            tmp_path / 'report_tmp' / 'framef_keysmith_version_parity_break_probe' / 'run_index.jsonl',
            'framef_keysmith_version_parity_break_probe.json',
        ),
        (
            simulation_runner.run_public_report_boundary_escape_probe,
            tmp_path / 'report_tmp' / 'frameg_public_report_boundary_escape_probe' / 'run_index.jsonl',
            'frameg_public_report_boundary_escape_probe.json',
        ),
        (
            simulation_runner.run_bootstrap_root_starvation_probe,
            tmp_path / 'report_tmp' / 'frameg_bootstrap_root_starvation_probe' / 'run_index.jsonl',
            'frameg_bootstrap_root_starvation_probe.json',
        ),
        (
            simulation_runner.run_sandbox_catalog_authority_drift_probe,
            tmp_path / 'report_tmp' / 'frameg_sandbox_catalog_authority_drift_probe' / 'run_index.jsonl',
            'frameg_sandbox_catalog_authority_drift_probe.json',
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
        if report_name in wizard_report_names:
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


def test_names_only_persistence_escape_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_names_only_persistence_escape_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'framec_names_only_persistence_escape_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'framec_names_only_persistence_escape_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'names_only_boundary_preserved'
    assert all(bool(value) for value in payload['result_matrix'].values())


def test_packet_artifact_divergence_truthfulness_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_packet_artifact_divergence_truthfulness_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'framec_packet_artifact_divergence_truthfulness_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'framec_packet_artifact_divergence_truthfulness_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'packet_artifact_divergence_detected_fail_closed'
    assert payload['findings']['review_decision'] == 'no-go'
    assert all(bool(value) for value in payload['result_matrix'].values())


def test_watchdog_heartbeat_spoof_resistance_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_watchdog_heartbeat_spoof_resistance_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'framed_watchdog_heartbeat_spoof_resistance_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'framed_watchdog_heartbeat_spoof_resistance_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'observer_heartbeat_spoof_degraded_explicitly'
    assert 'major_check_failed:observer_heartbeat_stale_service_alive' in payload['findings']['watchdog_advisory_reason_codes']
    assert all(bool(value) for value in payload['result_matrix'].values())


def test_resource_lockdown_chaos_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_resource_lockdown_chaos_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'framed_resource_lockdown_chaos_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'framed_resource_lockdown_chaos_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'resource_lockdown_chaos_fail_closed'
    assert 'critical_check_failed:cpu_spike_lockdown' in payload['findings']['live_reason_codes']
    assert 'critical_check_failed:cpu_spike_lockdown' in payload['findings']['honeypot_reason_codes']
    assert all(bool(value) for value in payload['result_matrix'].values())


def test_baseline_authority_tamper_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_baseline_authority_tamper_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'framee_baseline_authority_tamper_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'framee_baseline_authority_tamper_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'baseline_authority_tamper_repaired_from_authoritative_selector'
    assert payload['findings']['tampered_selector_entry_id'] == 'forged-selector-entry'
    assert payload['result_matrix']['explicit_candidate_repaired_from_authority'] is True
    assert all(bool(value) for value in payload['result_matrix'].values())


def test_report_lineage_forgery_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_report_lineage_forgery_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'framee_report_lineage_forgery_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'framee_report_lineage_forgery_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'report_lineage_forgery_blocked_before_publication'
    assert 'publication_skipped:dataset_manifest_ephemeral' in payload['findings']['tampered_reasons']
    assert payload['result_matrix']['published_run_count_zero'] is True
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


def test_keysmith_version_parity_break_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_keysmith_version_parity_break_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'framef_keysmith_version_parity_break_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'framef_keysmith_version_parity_break_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'keysmith_version_parity_break_detected_fail_closed'
    assert 'critical_check_failed:keysmith_version_parity_mismatch' in payload['artifact_snapshots']['tampered_review']['reason_codes']
    assert all(bool(value) for value in payload['result_matrix'].values())


def test_public_report_boundary_escape_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_public_report_boundary_escape_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'frameg_public_report_boundary_escape_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'frameg_public_report_boundary_escape_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'public_report_boundary_preserved'
    assert payload['result_matrix']['published_figure_rewritten_relative'] is True
    assert payload['result_matrix']['human_facing_generated_surfaces_contract_present'] is True
    assert all(bool(value) for value in payload['result_matrix'].values())


def test_bootstrap_root_starvation_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_bootstrap_root_starvation_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'frameg_bootstrap_root_starvation_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'frameg_bootstrap_root_starvation_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'bootstrap_root_starvation_degraded_truthfully'
    assert 'critical_check_failed:runtime_bootstrap_blocked_reports_operations_root' in payload['findings']['bootstrap_reason_codes']
    assert payload['result_matrix']['other_roots_created_under_partial_success'] is True
    assert all(bool(value) for value in payload['result_matrix'].values())


def test_sandbox_catalog_authority_drift_probe_writes_retained_report_artifacts(tmp_path: Path, monkeypatch) -> None:
    _configure_probe_roots(monkeypatch, tmp_path)

    rc = simulation_runner.run_sandbox_catalog_authority_drift_probe()

    assert rc == 0
    run_index_path = tmp_path / 'report_tmp' / 'frameg_sandbox_catalog_authority_drift_probe' / 'run_index.jsonl'
    assert run_index_path.exists()

    rows = [json.loads(line) for line in run_index_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert rows
    latest = rows[-1]
    report_json = tmp_path / str(latest['report_json']).replace('/', '\\')
    assert report_json.name == 'frameg_sandbox_catalog_authority_drift_probe.json'
    assert report_json.exists()

    payload = json.loads(report_json.read_text(encoding='utf-8'))
    assert payload['next_bite_result'] == 'pass'
    assert payload['observed_boundary_result'] == 'sandbox_catalog_authority_drift_visible_fail_closed'
    assert 'critical_check_failed:sandbox_run_report_missing' in payload['findings']['stale_review_reason_codes']
    assert payload['result_matrix']['stale_run_visible_in_catalog_list'] is True
    assert all(bool(value) for value in payload['result_matrix'].values())