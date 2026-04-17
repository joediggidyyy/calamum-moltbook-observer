from __future__ import annotations

from observerctl_sandbox_render import render_human_packet
from observerctl_terminal import strip_ansi


def _plain(lines: list[str]) -> list[str]:
    return [strip_ansi(line) for line in lines]


def test_sandbox_run_render_preserves_zero_return_code() -> None:
    lines = render_human_packet({
        'action': 'sandbox-run',
        'timestamp_utc': '2026-04-14T14:13:16Z',
        'decision': 'go',
        'template_class': 'transition',
        'template_variant': 'execution',
        'runtime_cli_surface': 'observerctl',
        'definition_id': 'ds-wizard-hydration',
        'result': 'pass',
        'returncode': 0,
        'run_id': 'frame4-ds-wizard-hydration-20260414T141314Z',
        'artifacts': {
            'report_json': 'report_tmp/frame4/report.json',
        },
        'next_review_command': 'observerctl sandbox runs show frame4-ds-wizard-hydration-20260414T141314Z',
    })

    rendered = _plain(lines or [])
    assert any('Return Code' in line and ': 0' in line for line in rendered)
    assert any('Review Command' in line and 'observerctl sandbox runs show' in line for line in rendered)


def test_sandbox_runs_show_render_summarizes_retained_review() -> None:
    lines = render_human_packet({
        'action': 'sandbox-runs-show',
        'timestamp_utc': '2026-04-14T14:15:02Z',
        'decision': 'go',
        'template_class': 'validation',
        'template_variant': 'run_review',
        'runtime_cli_surface': 'observerctl',
        'run': {
            'run_id': 'frameb-ds-wizard-blocked-execute-truthfulness-20260414T141328Z',
            'definition_id': 'ds-wizard-blocked-execute-truthfulness',
            'timestamp_utc': '20260414T141328Z',
            'result': 'pass',
            'report_path': 'report_tmp/frameb/report.json',
            'run_dir': 'report_tmp/frameb/run',
            'index_path': 'C:/repo/report_tmp/frameb/run_index.jsonl',
        },
        'report': {
            'next_bite_result': 'pass',
            'result_matrix': {
                'preview_reports_blocked_execution_state': True,
                'execute_packet_no_go': True,
                'execute_reason_code_is_validation_block': True,
            },
            'command_runs': {
                'wizard_blocked_preview': {'returncode': 0},
                'wizard_blocked_execute': {'returncode': 2},
            },
            'artifact_paths': {},
            'findings': {
                'validation_issues': ['features_csv is required'],
                'reason_codes': ['critical_check_failed:wizard_validation_blocked'],
                'command_preview': 'observerctl ds evaluate --features-csv  --max-fpr 0.01',
            },
        },
    })

    rendered = _plain(lines or [])
    assert any('Next Bite Result' in line and 'pass' in line for line in rendered)
    assert any('Checks Passed' in line and '3/3' in line for line in rendered)
    assert any('Review Signal' in line and 'all retained checks passed' in line for line in rendered)
    assert any('Command Runs' in line and ': 2' in line for line in rendered)
    assert any('validation_issues' in line and 'features_csv is required' in line for line in rendered)
    assert any('reason_codes' in line and 'wizard_validation_blocked' in line for line in rendered)


def test_sandbox_runs_show_render_surfaces_failed_checks() -> None:
    lines = render_human_packet({
        'action': 'sandbox-runs-show',
        'timestamp_utc': '2026-04-14T14:15:02Z',
        'decision': 'go',
        'template_class': 'validation',
        'template_variant': 'run_review',
        'runtime_cli_surface': 'observerctl',
        'run': {
            'run_id': 'run-1',
            'definition_id': 'ds-alias-coherence',
            'timestamp_utc': '20260414T141329Z',
            'result': 'review',
            'report_path': 'report_tmp/framed/report.json',
        },
        'report': {
            'next_bite_result': 'review',
            'result_matrix': {
                'publication_alias_root_exists': True,
                'stage_reports_include_registered_alias': False,
                'missing_alias_fails_closed': False,
            },
            'findings': {
                'published_stage_paths': {
                    'build': 'docs/reports/collections/example/build.md',
                    'train': 'docs/reports/collections/example/train.md',
                    'evaluate': 'docs/reports/collections/example/eval.md',
                    'score': 'docs/reports/collections/example/score.md',
                },
            },
        },
    })

    rendered = _plain(lines or [])
    assert any('Checks Passed' in line and '1/3' in line for line in rendered)
    assert any('Failed Check' in line and 'stage_reports_include_registered_alias' in line for line in rendered)
    assert any('Failed Check' in line and 'missing_alias_fails_closed' in line for line in rendered)
    assert any('published_stage_paths' in line and '4 keys' in line for line in rendered)