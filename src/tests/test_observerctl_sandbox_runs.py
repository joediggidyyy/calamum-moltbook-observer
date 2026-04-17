from __future__ import annotations

import json
from pathlib import Path

import observerctl_sandbox_runs as sandbox_runs_module


def test_get_run_resolves_repo_relative_report_path(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    report_json = repo_root / 'report_tmp' / 'frameb_probe' / 'runs' / 'run-1' / 'report.json'
    run_index = repo_root / 'report_tmp' / 'frameb_probe' / 'run_index.jsonl'

    report_json.parent.mkdir(parents=True, exist_ok=True)
    run_index.parent.mkdir(parents=True, exist_ok=True)

    report_json.write_text(json.dumps({
        'next_bite_result': 'pass',
        'result_matrix': {
            'execute_packet_no_go': True,
        },
    }) + '\n', encoding='utf-8')
    run_index.write_text(json.dumps({
        'run_id': 'run-1',
        'timestamp_utc': '20260414T141328Z',
        'report_json': 'report_tmp/frameb_probe/runs/run-1/report.json',
        'run_dir': 'report_tmp/frameb_probe/runs/run-1',
        'next_bite_result': 'pass',
    }) + '\n', encoding='utf-8')

    monkeypatch.setattr(sandbox_runs_module, '_REPO_ROOT', repo_root)
    monkeypatch.setattr(
        sandbox_runs_module,
        'get_definitions',
        lambda: [{
            'id': 'frameb-probe',
            'run_index_path': str(run_index),
        }],
    )

    found = sandbox_runs_module.get_run('run-1')

    assert found is not None
    row, payload = found
    assert row['report_path'] == 'report_tmp/frameb_probe/runs/run-1/report.json'
    assert payload['next_bite_result'] == 'pass'
    assert payload['result_matrix']['execute_packet_no_go'] is True