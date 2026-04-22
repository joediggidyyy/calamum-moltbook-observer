from __future__ import annotations

import importlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast


DefinitionRecord = Dict[str, Any]


_SRC_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SRC_DIR.parent
_REPO_ROOT = _PROJECT_ROOT.parents[1]
_REPORT_TMP = _REPO_ROOT / 'report_tmp'


def _metadata_contract_run_index() -> Path:
    return _REPORT_TMP / 'frame4_metadata_contract_probe' / 'run_index.jsonl'


def _metadata_contract_regression_run_index() -> Path:
    return _REPORT_TMP / 'frame4_metadata_contract_regression_probe' / 'run_index.jsonl'


def _ds_wizard_hydration_run_index() -> Path:
    return _REPORT_TMP / 'frame4_ds_wizard_hydration_probe' / 'run_index.jsonl'


def _ds_wizard_stale_state_continuity_run_index() -> Path:
    return _REPORT_TMP / 'frameb_ds_wizard_stale_state_continuity_probe' / 'run_index.jsonl'


def _ds_wizard_durability_run_index() -> Path:
    return _REPORT_TMP / 'frame6_ds_wizard_durability_probe' / 'run_index.jsonl'


def _ds_wizard_labeled_eval_contract_coherence_run_index() -> Path:
    return _REPORT_TMP / 'frameb_ds_wizard_labeled_eval_contract_coherence_probe' / 'run_index.jsonl'


def _ds_wizard_blocked_execute_truthfulness_run_index() -> Path:
    return _REPORT_TMP / 'frameb_ds_wizard_blocked_execute_truthfulness_probe' / 'run_index.jsonl'


def _ds_wizard_execute_failure_truthfulness_run_index() -> Path:
    return _REPORT_TMP / 'frameb_ds_wizard_execute_failure_truthfulness_probe' / 'run_index.jsonl'


def _ds_alias_coherence_run_index() -> Path:
    return _REPORT_TMP / 'framed_ds_alias_coherence_probe' / 'run_index.jsonl'


def _posture_transition_bypass_run_index() -> Path:
    return _REPORT_TMP / 'frameb_posture_transition_bypass_probe' / 'run_index.jsonl'


def _stale_gate_replay_run_index() -> Path:
    return _REPORT_TMP / 'frameb_stale_gate_replay_probe' / 'run_index.jsonl'


def _names_only_persistence_escape_run_index() -> Path:
    return _REPORT_TMP / 'framec_names_only_persistence_escape_probe' / 'run_index.jsonl'


def _packet_artifact_divergence_truthfulness_run_index() -> Path:
    return _REPORT_TMP / 'framec_packet_artifact_divergence_truthfulness_probe' / 'run_index.jsonl'


def _watchdog_heartbeat_spoof_resistance_run_index() -> Path:
    return _REPORT_TMP / 'framed_watchdog_heartbeat_spoof_resistance_probe' / 'run_index.jsonl'


def _resource_lockdown_chaos_run_index() -> Path:
    return _REPORT_TMP / 'framed_resource_lockdown_chaos_probe' / 'run_index.jsonl'


def _baseline_authority_tamper_run_index() -> Path:
    return _REPORT_TMP / 'framee_baseline_authority_tamper_probe' / 'run_index.jsonl'


def _report_lineage_forgery_run_index() -> Path:
    return _REPORT_TMP / 'framee_report_lineage_forgery_probe' / 'run_index.jsonl'


def _keysmith_version_parity_break_run_index() -> Path:
    return _REPORT_TMP / 'framef_keysmith_version_parity_break_probe' / 'run_index.jsonl'


def _public_report_boundary_escape_run_index() -> Path:
    return _REPORT_TMP / 'frameg_public_report_boundary_escape_probe' / 'run_index.jsonl'


def _bootstrap_root_starvation_run_index() -> Path:
    return _REPORT_TMP / 'frameg_bootstrap_root_starvation_probe' / 'run_index.jsonl'


def _sandbox_catalog_authority_drift_run_index() -> Path:
    return _REPORT_TMP / 'frameg_sandbox_catalog_authority_drift_probe' / 'run_index.jsonl'


def _baseline_monitor_runtime_run_index() -> Path:
    return _REPORT_TMP / 'job0022_baseline_monitor_runtime_probe' / 'run_index.jsonl'


def _validation_cycle_lineage_run_index() -> Path:
    return _REPORT_TMP / 'frame5_validation_cycle_lineage_probe' / 'run_index.jsonl'


def _baseline_monitor_restart_continuity_run_index() -> Path:
    return _REPORT_TMP / 'frame6_restart_continuity_probe' / 'run_index.jsonl'


def _baseline_monitor_state_recovery_run_index() -> Path:
    return _REPORT_TMP / 'frame6_state_recovery_probe' / 'run_index.jsonl'


def _librarian_access_exchange_run_index() -> Path:
    return _REPORT_TMP / 'librarian_access_exchange_probe' / 'run_index.jsonl'


def _librarian_vault_controls_run_index() -> Path:
    return _REPORT_TMP / 'librarian_vault_controls_probe' / 'run_index.jsonl'


def _load_simulation_runner() -> Any:
    return importlib.import_module('simulation.run_simulation')


def _run_feedback_loop() -> int:
    return int(_load_simulation_runner().run_feedback_loop_simulation())


def _run_metadata_contract() -> int:
    return int(_load_simulation_runner().run_metadata_contract_probe())


def _run_metadata_contract_regression() -> int:
    return int(_load_simulation_runner().run_metadata_contract_regression_probe())


def _run_ds_wizard_hydration() -> int:
    return int(_load_simulation_runner().run_ds_wizard_hydration_probe())


def _run_ds_wizard_stale_state_continuity() -> int:
    return int(_load_simulation_runner().run_ds_wizard_stale_state_continuity_probe())


def _run_ds_wizard_durability() -> int:
    return int(_load_simulation_runner().run_ds_wizard_durability_probe())


def _run_ds_wizard_labeled_eval_contract_coherence() -> int:
    return int(_load_simulation_runner().run_ds_wizard_labeled_eval_contract_coherence_probe())


def _run_ds_wizard_blocked_execute_truthfulness() -> int:
    return int(_load_simulation_runner().run_ds_wizard_blocked_execute_truthfulness_probe())


def _run_ds_wizard_execute_failure_truthfulness() -> int:
    return int(_load_simulation_runner().run_ds_wizard_execute_failure_truthfulness_probe())


def _run_ds_alias_coherence() -> int:
    return int(_load_simulation_runner().run_ds_alias_coherence_probe())


def _run_posture_transition_bypass() -> int:
    return int(_load_simulation_runner().run_posture_transition_bypass_probe())


def _run_stale_gate_replay() -> int:
    return int(_load_simulation_runner().run_stale_gate_replay_probe())


def _run_names_only_persistence_escape() -> int:
    return int(_load_simulation_runner().run_names_only_persistence_escape_probe())


def _run_packet_artifact_divergence_truthfulness() -> int:
    return int(_load_simulation_runner().run_packet_artifact_divergence_truthfulness_probe())


def _run_watchdog_heartbeat_spoof_resistance() -> int:
    return int(_load_simulation_runner().run_watchdog_heartbeat_spoof_resistance_probe())


def _run_resource_lockdown_chaos() -> int:
    return int(_load_simulation_runner().run_resource_lockdown_chaos_probe())


def _run_baseline_authority_tamper() -> int:
    return int(_load_simulation_runner().run_baseline_authority_tamper_probe())


def _run_report_lineage_forgery() -> int:
    return int(_load_simulation_runner().run_report_lineage_forgery_probe())


def _run_keysmith_version_parity_break() -> int:
    return int(_load_simulation_runner().run_keysmith_version_parity_break_probe())


def _run_public_report_boundary_escape() -> int:
    return int(_load_simulation_runner().run_public_report_boundary_escape_probe())


def _run_bootstrap_root_starvation() -> int:
    return int(_load_simulation_runner().run_bootstrap_root_starvation_probe())


def _run_sandbox_catalog_authority_drift() -> int:
    return int(_load_simulation_runner().run_sandbox_catalog_authority_drift_probe())


def _run_baseline_monitor_runtime() -> int:
    return int(_load_simulation_runner().run_baseline_monitor_runtime_probe())


def _run_validation_cycle_lineage() -> int:
    return int(_load_simulation_runner().run_validation_cycle_lineage_probe())


def _run_baseline_monitor_restart_continuity() -> int:
    return int(_load_simulation_runner().run_baseline_monitor_restart_continuity_probe())


def _run_baseline_monitor_state_recovery() -> int:
    return int(_load_simulation_runner().run_baseline_monitor_state_recovery_probe())


def _run_librarian_access_exchange() -> int:
    return int(_load_simulation_runner().run_librarian_access_exchange_probe())


def _run_librarian_vault_controls() -> int:
    return int(_load_simulation_runner().run_librarian_vault_controls_probe())


def get_definitions() -> List[DefinitionRecord]:
    return [
        {
            'id': 'feedback-loop',
            'title': 'Feedback loop simulation',
            'summary': 'Local simulation proving observer/librarian feedback behavior.',
            'status': 'stable',
            'category': 'simulation',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'temp-only',
            'purpose': 'Exercise the original Calamum feedback loop in an isolated temp workspace.',
            'command': 'observerctl sandbox run feedback-loop',
            'run_index_path': '',
            'runner': _run_feedback_loop,
        },
        {
            'id': 'metadata-contract',
            'title': 'Metadata contract probe',
            'summary': 'Validate resource metadata contract expectations for normal and baseline samples.',
            'status': 'stable',
            'category': 'metadata-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frame4_metadata_contract_probe',
            'purpose': 'Verify that retained resource rows and indexes carry the expected metadata contract fields.',
            'command': 'observerctl sandbox run metadata-contract',
            'run_index_path': str(_metadata_contract_run_index()).replace('\\', '/'),
            'runner': _run_metadata_contract,
        },
        {
            'id': 'metadata-contract-regression',
            'title': 'Metadata contract regression probe',
            'summary': 'Validate that known-bad retained metadata rows are flagged as contract regressions.',
            'status': 'stable',
            'category': 'metadata-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frame4_metadata_contract_regression_probe',
            'purpose': 'Prove Frame 4 negative-path regression detection catches missing required metadata fields.',
            'command': 'observerctl sandbox run metadata-contract-regression',
            'run_index_path': str(_metadata_contract_regression_run_index()).replace('\\', '/'),
            'runner': _run_metadata_contract_regression,
        },
        {
            'id': 'ds-wizard-hydration',
            'title': 'DS wizard hydration probe',
            'summary': 'Validate DS wizard artifact hydration and current narrow latest-context import behavior.',
            'status': 'stable',
            'category': 'ds-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frame4_ds_wizard_hydration_probe',
            'purpose': 'Prove the DS wizard can hydrate dataset, train, baseline, and current latest-context inputs through the canonical sandbox lane.',
            'command': 'observerctl sandbox run ds-wizard-hydration',
            'run_index_path': str(_ds_wizard_hydration_run_index()).replace('\\', '/'),
            'runner': _run_ds_wizard_hydration,
        },
        {
            'id': 'ds-wizard-stale-state-continuity',
            'title': 'DS wizard stale-state continuity probe',
            'summary': 'Validate train-context hydration refreshes dataset-adjacent wizard state instead of retaining stale evaluate paths.',
            'status': 'stable',
            'category': 'ds-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frameb_ds_wizard_stale_state_continuity_probe',
            'purpose': 'Prove cross-hydrating dataset and train context leaves one coherent evaluate lane with refreshed dataset, feature, label, and model paths.',
            'command': 'observerctl sandbox run ds-wizard-stale-state-continuity',
            'run_index_path': str(_ds_wizard_stale_state_continuity_run_index()).replace('\\', '/'),
            'runner': _run_ds_wizard_stale_state_continuity,
        },
        {
            'id': 'ds-wizard-durability',
            'title': 'DS wizard durability probe',
            'summary': 'Validate prior-run ledger import and draft round-trip persistence for the DS wizard.',
            'status': 'stable',
            'category': 'ds-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frame6_ds_wizard_durability_probe',
            'purpose': 'Prove Frame 6 durable-use behavior: prior-run import plus draft save/load through the canonical sandbox lane.',
            'command': 'observerctl sandbox run ds-wizard-durability',
            'run_index_path': str(_ds_wizard_durability_run_index()).replace('\\', '/'),
            'runner': _run_ds_wizard_durability,
        },
        {
            'id': 'ds-wizard-labeled-eval-contract-coherence',
            'title': 'DS wizard labeled eval contract coherence probe',
            'summary': 'Validate wizard evaluation stays in labeled mode when the dataset uses the approved label-column contract.',
            'status': 'stable',
            'category': 'ds-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frameb_ds_wizard_labeled_eval_contract_coherence_probe',
            'purpose': 'Prove supervised train and wizard evaluate agree on the same label file and retain a coherent labeled evaluation run ledger.',
            'command': 'observerctl sandbox run ds-wizard-labeled-eval-contract-coherence',
            'run_index_path': str(_ds_wizard_labeled_eval_contract_coherence_run_index()).replace('\\', '/'),
            'runner': _run_ds_wizard_labeled_eval_contract_coherence,
        },
        {
            'id': 'ds-wizard-blocked-execute-truthfulness',
            'title': 'DS wizard blocked execute truthfulness probe',
            'summary': 'Validate blocked wizard execution remains fail-closed, operator-legible, and free of false-success artifact claims.',
            'status': 'stable',
            'category': 'ds-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frameb_ds_wizard_blocked_execute_truthfulness_probe',
            'purpose': 'Prove the wizard surfaces no-go execution truthfully with explicit blocker codes, validation issues, and no misleading artifact residue.',
            'command': 'observerctl sandbox run ds-wizard-blocked-execute-truthfulness',
            'run_index_path': str(_ds_wizard_blocked_execute_truthfulness_run_index()).replace('\\', '/'),
            'runner': _run_ds_wizard_blocked_execute_truthfulness,
        },
        {
            'id': 'ds-wizard-execute-failure-truthfulness',
            'title': 'DS wizard execute failure truthfulness probe',
            'summary': 'Validate post-validation execute failures render truthful terminal guidance instead of blaming validation.',
            'status': 'stable',
            'category': 'ds-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frameb_ds_wizard_execute_failure_truthfulness_probe',
            'purpose': 'Prove rendered wizard run-pane output agrees with the derived no-go packet when execution fails after validation has already passed.',
            'command': 'observerctl sandbox run ds-wizard-execute-failure-truthfulness',
            'run_index_path': str(_ds_wizard_execute_failure_truthfulness_run_index()).replace('\\', '/'),
            'runner': _run_ds_wizard_execute_failure_truthfulness,
        },
        {
            'id': 'ds-alias-coherence',
            'title': 'DS alias coherence probe',
            'summary': 'Validate one collection alias across build, train, evaluate, and score publication plus fail-closed unresolved-alias behavior.',
            'status': 'stable',
            'category': 'ds-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/framed_ds_alias_coherence_probe',
            'purpose': 'Prove the sandboxed DS lane keeps one registered collection alias across four workflows without fallback alias drift or unresolved-alias residue.',
            'command': 'observerctl sandbox run ds-alias-coherence',
            'run_index_path': str(_ds_alias_coherence_run_index()).replace('\\', '/'),
            'runner': _run_ds_alias_coherence,
        },
        {
            'id': 'posture-transition-bypass',
            'title': 'Posture transition bypass probe',
            'summary': 'Validate a fresh-looking gate packet cannot be reused after the live current-state tuple changes.',
            'status': 'stable',
            'category': 'transition-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frameb_posture_transition_bypass_probe',
            'purpose': 'Prove Frame B S1 denies mode-set attempts when the active state no longer matches the go gate packet that authorized the transition.',
            'command': 'observerctl sandbox run posture-transition-bypass',
            'run_index_path': str(_posture_transition_bypass_run_index()).replace('\\', '/'),
            'runner': _run_posture_transition_bypass,
        },
        {
            'id': 'stale-gate-replay',
            'title': 'Stale gate replay probe',
            'summary': 'Validate stale gate packets and replayed transition lineage are both denied before state mutation.',
            'status': 'stable',
            'category': 'transition-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frameb_stale_gate_replay_probe',
            'purpose': 'Prove Frame B S2 fails closed for aged gate packets and for fresh packets whose run lineage no longer matches the active transition context.',
            'command': 'observerctl sandbox run stale-gate-replay',
            'run_index_path': str(_stale_gate_replay_run_index()).replace('\\', '/'),
            'runner': _run_stale_gate_replay,
        },
        {
            'id': 'names-only-persistence-escape',
            'title': 'Names-only persistence escape probe',
            'summary': 'Validate hostile raw and secret lure strings do not persist into retained outputs or command surfaces.',
            'status': 'stable',
            'category': 'containment-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/framec_names_only_persistence_escape_probe',
            'purpose': 'Prove Frame C S3 keeps retained packets, control artifacts, and command output names-only even when hostile lure material exists nearby in the sandbox.',
            'command': 'observerctl sandbox run names-only-persistence-escape',
            'run_index_path': str(_names_only_persistence_escape_run_index()).replace('\\', '/'),
            'runner': _run_names_only_persistence_escape,
        },
        {
            'id': 'packet-artifact-divergence-truthfulness',
            'title': 'Packet artifact divergence truthfulness probe',
            'summary': 'Validate cross-surface review surfaces missing-current-artifact divergence instead of preserving a false-success narrative.',
            'status': 'stable',
            'category': 'truthfulness-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/framec_packet_artifact_divergence_truthfulness_probe',
            'purpose': 'Prove Frame C S4 treats command-success plus missing-current-artifact drift as an explicit no-go review outcome rather than silently reusing stale proof.',
            'command': 'observerctl sandbox run packet-artifact-divergence-truthfulness',
            'run_index_path': str(_packet_artifact_divergence_truthfulness_run_index()).replace('\\', '/'),
            'runner': _run_packet_artifact_divergence_truthfulness,
        },
        {
            'id': 'watchdog-heartbeat-spoof-resistance',
            'title': 'Watchdog heartbeat spoof resistance probe',
            'summary': 'Validate stale observer heartbeat signals degrade explicitly instead of surviving as false clean health.',
            'status': 'stable',
            'category': 'runtime-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/framed_watchdog_heartbeat_spoof_resistance_probe',
            'purpose': 'Prove Frame D S5 degrades stale or spoof-like observer heartbeat signals explicitly while preserving service-truth semantics.',
            'command': 'observerctl sandbox run watchdog-heartbeat-spoof-resistance',
            'run_index_path': str(_watchdog_heartbeat_spoof_resistance_run_index()).replace('\\', '/'),
            'runner': _run_watchdog_heartbeat_spoof_resistance,
        },
        {
            'id': 'resource-lockdown-chaos',
            'title': 'Resource lockdown chaos probe',
            'summary': 'Validate lockdown gate evaluation fails closed under synthetic resource spikes for live and honeypot targets.',
            'status': 'stable',
            'category': 'chaos-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/framed_resource_lockdown_chaos_probe',
            'purpose': 'Prove Frame D S6 keeps runtime-chaos pressure bounded and fail-closed when synthetic spike conditions would make lockdown unsafe.',
            'command': 'observerctl sandbox run resource-lockdown-chaos',
            'run_index_path': str(_resource_lockdown_chaos_run_index()).replace('\\', '/'),
            'runner': _run_resource_lockdown_chaos,
        },
        {
            'id': 'baseline-authority-tamper',
            'title': 'Baseline authority tamper probe',
            'summary': 'Validate explicit comparison-baseline selector tampering is repaired from authoritative dataset state before reuse.',
            'status': 'stable',
            'category': 'authority-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/framee_baseline_authority_tamper_probe',
            'purpose': 'Prove Frame E S7 rejects forged selector linkage on explicit comparison-baseline packets and repairs the packet from librarian authority before report normalization.',
            'command': 'observerctl sandbox run baseline-authority-tamper',
            'run_index_path': str(_baseline_authority_tamper_run_index()).replace('\\', '/'),
            'runner': _run_baseline_authority_tamper,
        },
        {
            'id': 'report-lineage-forgery',
            'title': 'Report lineage forgery probe',
            'summary': 'Validate tracked publication fails closed when persisted run lineage is tampered to an ephemeral dataset manifest.',
            'status': 'stable',
            'category': 'lineage-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/framee_report_lineage_forgery_probe',
            'purpose': 'Prove Frame E S8 blocks publication when a persisted DS run manifest is rewritten to point at forged ephemeral dataset lineage.',
            'command': 'observerctl sandbox run report-lineage-forgery',
            'run_index_path': str(_report_lineage_forgery_run_index()).replace('\\', '/'),
            'runner': _run_report_lineage_forgery,
        },
        {
            'id': 'keysmith-version-parity-break',
            'title': 'KEYSMITH version parity break probe',
            'summary': 'Validate retained KEYSMITH proof mismatches are surfaced explicitly instead of standing in for the current build under review.',
            'status': 'stable',
            'category': 'proof-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/framef_keysmith_version_parity_break_probe',
            'purpose': 'Prove Frame F S11 fails closed when retained KEYSMITH build proof diverges from the candidate build surfaces and version under review.',
            'command': 'observerctl sandbox run keysmith-version-parity-break',
            'run_index_path': str(_keysmith_version_parity_break_run_index()).replace('\\', '/'),
            'runner': _run_keysmith_version_parity_break,
        },
        {
            'id': 'public-report-boundary-escape',
            'title': 'Public report boundary escape probe',
            'summary': 'Validate reader-facing report publication strips local authority residue and absolute-path noise before tracked surfaces are rendered.',
            'status': 'stable',
            'category': 'publication-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frameg_public_report_boundary_escape_probe',
            'purpose': 'Prove Frame G S12 keeps docs/reports publication human-facing and derived, even when source report artifacts contain local-only lure material.',
            'command': 'observerctl sandbox run public-report-boundary-escape',
            'run_index_path': str(_public_report_boundary_escape_run_index()).replace('\\', '/'),
            'runner': _run_public_report_boundary_escape,
        },
        {
            'id': 'bootstrap-root-starvation',
            'title': 'Bootstrap-root starvation probe',
            'summary': 'Validate blocked bootstrap roots degrade truthfully instead of letting partial preparation masquerade as runtime readiness.',
            'status': 'stable',
            'category': 'bootstrap-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frameg_bootstrap_root_starvation_probe',
            'purpose': 'Prove Frame G S13 surfaces missing and blocked runtime roots as an explicit no-go while still recording partial creation work honestly.',
            'command': 'observerctl sandbox run bootstrap-root-starvation',
            'run_index_path': str(_bootstrap_root_starvation_run_index()).replace('\\', '/'),
            'runner': _run_bootstrap_root_starvation,
        },
        {
            'id': 'sandbox-catalog-authority-drift',
            'title': 'Sandbox catalog authority drift probe',
            'summary': 'Validate exact-name-only catalog discipline and fail-closed retained-run review when stale run references appear.',
            'status': 'stable',
            'category': 'catalog-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frameg_sandbox_catalog_authority_drift_probe',
            'purpose': 'Prove Frame G S14 denies alias-like lookup drift and refuses to treat stale run references as trustworthy catalog review material.',
            'command': 'observerctl sandbox run sandbox-catalog-authority-drift',
            'run_index_path': str(_sandbox_catalog_authority_drift_run_index()).replace('\\', '/'),
            'runner': _run_sandbox_catalog_authority_drift,
        },
        {
            'id': 'baseline-monitor-runtime',
            'title': 'Baseline monitor runtime probe',
            'summary': 'Validate baseline-monitor runtime liveness plus resource_normal retention continuity.',
            'status': 'stable',
            'category': 'runtime-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/job0022_baseline_monitor_runtime_probe',
            'purpose': 'Prove the sandboxed baseline-monitor runtime and retained evidence flow are intact.',
            'command': 'observerctl sandbox run baseline-monitor-runtime',
            'run_index_path': str(_baseline_monitor_runtime_run_index()).replace('\\', '/'),
            'runner': _run_baseline_monitor_runtime,
        },
        {
            'id': 'validation-cycle-lineage',
            'title': 'Validation cycle lineage probe',
            'summary': 'Validate append-only validation-cycle evidence growth and prior-cycle linkage semantics.',
            'status': 'stable',
            'category': 'evidence-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frame5_validation_cycle_lineage_probe',
            'purpose': 'Prove Frame 5 validation-cycle lineage is append-only and references prior retained evidence correctly.',
            'command': 'observerctl sandbox run validation-cycle-lineage',
            'run_index_path': str(_validation_cycle_lineage_run_index()).replace('\\', '/'),
            'runner': _run_validation_cycle_lineage,
        },
        {
            'id': 'baseline-monitor-restart-continuity',
            'title': 'Baseline monitor restart continuity probe',
            'summary': 'Validate restart-safe continuity anchor preservation across resumed monitor cycles.',
            'status': 'stable',
            'category': 'continuity-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frame6_restart_continuity_probe',
            'purpose': 'Prove Frame 6 restart continuity preserves prior validation and baseline anchors across resumed cycles.',
            'command': 'observerctl sandbox run baseline-monitor-restart-continuity',
            'run_index_path': str(_baseline_monitor_restart_continuity_run_index()).replace('\\', '/'),
            'runner': _run_baseline_monitor_restart_continuity,
        },
        {
            'id': 'baseline-monitor-state-recovery',
            'title': 'Baseline monitor state recovery probe',
            'summary': 'Validate malformed persisted monitor state degrades explicitly and repairs cleanly.',
            'status': 'stable',
            'category': 'recovery-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/frame6_state_recovery_probe',
            'purpose': 'Prove malformed persisted baseline-monitor state is surfaced as degraded continuity and normalized on writeback.',
            'command': 'observerctl sandbox run baseline-monitor-state-recovery',
            'run_index_path': str(_baseline_monitor_state_recovery_run_index()).replace('\\', '/'),
            'runner': _run_baseline_monitor_state_recovery,
        },
        {
            'id': 'librarian-access-exchange',
            'title': 'Librarian access exchange probe',
            'summary': 'Validate requester, librarian, and source delegated-access packets through the sandbox CLI lane.',
            'status': 'stable',
            'category': 'librarian-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/librarian_access_exchange_probe',
            'purpose': 'Prove protected-source dataset release writes and verifies delegated request, attestation, and release receipts without relying on the shared signing root.',
            'command': 'observerctl sandbox run librarian-access-exchange',
            'run_index_path': str(_librarian_access_exchange_run_index()).replace('\\', '/'),
            'runner': _run_librarian_access_exchange,
        },
        {
            'id': 'librarian-vault-controls',
            'title': 'Librarian vault controls probe',
            'summary': 'Validate librarian vault status, lock, unlock, rebaseline, and verify behavior through the sandbox CLI lane.',
            'status': 'stable',
            'category': 'librarian-probe',
            'aliases': [],
            'selector_policy': 'exact-name-only',
            'writes_to': 'report_tmp/librarian_vault_controls_probe',
            'purpose': 'Prove the protected librarian vault control plane fails closed for ordinary mutation while retaining stable verify and audit behavior.',
            'command': 'observerctl sandbox run librarian-vault-controls',
            'run_index_path': str(_librarian_vault_controls_run_index()).replace('\\', '/'),
            'runner': _run_librarian_vault_controls,
        },
    ]


def get_definition(definition_id: str) -> Optional[DefinitionRecord]:
    candidate = str(definition_id or '').strip().lower()
    for item in get_definitions():
        if str(item.get('id', '')).strip().lower() == candidate:
            return dict(item)
    return None


def run_definition(definition_id: str) -> Dict[str, Any]:
    record = get_definition(definition_id)
    if record is None:
        return {
            'decision': 'no-go',
            'reason_codes': ['critical_check_failed:unknown_sandbox_definition'],
            'definition_id': str(definition_id or ''),
        }

    runner = cast(Optional[Callable[[], int]], record.get('runner'))
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        rc = int(runner()) if runner is not None else 1

    stdout_text = stdout_buffer.getvalue()
    stderr_text = stderr_buffer.getvalue()
    artifacts: Dict[str, str] = {}
    run_id = ''
    for raw_line in stdout_text.splitlines():
        line = str(raw_line or '').strip()
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = str(key).strip()
        value = str(value).strip()
        if not key:
            continue
        if key == 'run_id':
            run_id = value
        artifacts[key] = value

    packet = {
        'decision': 'go' if rc == 0 else 'no-go',
        'reason_codes': [] if rc == 0 else ['critical_check_failed:sandbox_definition_run_failed'],
        'definition_id': str(record.get('id', '')),
        'result': 'pass' if rc == 0 else 'failed',
        'returncode': int(rc),
        'run_id': run_id,
        'artifacts': artifacts,
        'stdout_text': stdout_text,
        'stderr_text': stderr_text,
    }
    if str(record.get('run_index_path', '')).strip():
        packet['next_review_command'] = 'observerctl sandbox runs show {0}'.format(run_id) if run_id else 'observerctl sandbox runs list'
    return packet
