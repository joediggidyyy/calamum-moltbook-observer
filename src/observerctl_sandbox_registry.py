from __future__ import annotations

import importlib
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast


DefinitionRecord = Dict[str, Any]


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REPORT_TMP = _PROJECT_ROOT / 'report_tmp'


def _metadata_contract_run_index() -> Path:
    return _REPORT_TMP / 'frame4_metadata_contract_probe' / 'run_index.jsonl'


def _baseline_monitor_runtime_run_index() -> Path:
    return _REPORT_TMP / 'job0022_baseline_monitor_runtime_probe' / 'run_index.jsonl'


def _load_simulation_runner() -> Any:
    return importlib.import_module('simulation.run_simulation')


def _run_feedback_loop() -> int:
    return int(_load_simulation_runner().run_feedback_loop_simulation())


def _run_metadata_contract() -> int:
    return int(_load_simulation_runner().run_metadata_contract_probe())


def _run_baseline_monitor_runtime() -> int:
    return int(_load_simulation_runner().run_baseline_monitor_runtime_probe())


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
