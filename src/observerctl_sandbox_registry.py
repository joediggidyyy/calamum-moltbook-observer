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


def _ds_alias_coherence_run_index() -> Path:
    return _REPORT_TMP / 'framed_ds_alias_coherence_probe' / 'run_index.jsonl'


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


def _run_ds_alias_coherence() -> int:
    return int(_load_simulation_runner().run_ds_alias_coherence_probe())


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
