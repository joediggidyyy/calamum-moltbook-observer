from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from obfuscator_lib import Obfuscator

import observerctl as observerctl_module
from calamum_librarian import Librarian

from observerctl import (  # noqa: E402
    _default_output_path,
    _evidence_index_path,
    build_evidence_pack,
    collect_runtime_status,
    evaluate_gate_decision,
    main,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"status":"ok"}\n', encoding='utf-8')


def _read_jsonl_rows(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding='utf-8').splitlines():
        line = str(line).strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _latest_jsonl_row_for_stream(path: Path, stream_type: str) -> dict:
    for row in reversed(_read_jsonl_rows(path)):
        if str(row.get('stream_type', '')).strip().lower() == str(stream_type).strip().lower():
            return row
    return {}


def _latest_jsonl_row_for_event(path: Path, event: str) -> dict:
    for row in reversed(_read_jsonl_rows(path)):
        if str(row.get('event', '')).strip().lower() == str(event).strip().lower():
            return row
    return {}


def _write_watchdog_posture(control_dir: Path, posture: str, heartbeat_interval: float, baseline_interval: float) -> None:
    payload = {
        'posture_trigger': posture,
        'heartbeat_interval_seconds': heartbeat_interval,
        'baseline_validation_interval_seconds': baseline_interval,
    }
    (control_dir / 'watchdog_posture_state.json').write_text(json.dumps(payload), encoding='utf-8')


def _write_watchdog_resource(control_dir: Path, cpu_now: float, ram_now: float, cpu_p95: float, ram_p95: float, score: float, age_s: float) -> None:
    payload = {
        'cpu_pct_now': cpu_now,
        'ram_pct_now': ram_now,
        'cpu_p95_15m': cpu_p95,
        'ram_p95_15m': ram_p95,
        'resource_spike_score': score,
        'sample_age_seconds': age_s,
    }
    (control_dir / 'watchdog_resource_state.json').write_text(json.dumps(payload), encoding='utf-8')


def _set_security_report_ref(monkeypatch, base_dir: Path) -> Path:
    report = base_dir / 'security_report_test.md'
    report.write_text('# security report\n', encoding='utf-8')
    monkeypatch.setenv('CALAMUM_SECURITY_REPORT_REF', str(report))
    return report


def _write_signed_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(Obfuscator.sign_record(record)) + '\n')


def _make_ds_records() -> list[dict]:
    records = []
    for i in range(8):
        records.append({
            'timestamp': f'2026-02-10T00:00:{i:02d}Z',
            'type': 'post',
            'author_hash': f'norm{i:012d}',
            'content_length': 10,
            'has_code_block': False,
            'tags_count': 0,
            'mentions_count': 0,
            'f_complexity': 0.1,
            'f_code_density': 0.0,
            'f_toxicity': 0,
            'f_timestamp_epoch': float(i),
            'tv_id': 'TV-0',
        })
    for i in range(4):
        records.append({
            'timestamp': f'2026-02-10T00:01:{i:02d}Z',
            'type': 'post',
            'author_hash': f'bad{i:013d}',
            'content_length': 500,
            'has_code_block': True,
            'tags_count': 1,
            'mentions_count': 1,
            'f_complexity': 0.8,
            'f_code_density': 0.2,
            'f_toxicity': 1,
            'f_timestamp_epoch': float(100 + i),
            'tv_id': 'TV-3',
        })
    return records


def test_observerctl_top_level_help_exposes_ds_namespace(capsys) -> None:
    parser = observerctl_module._build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(['-h'])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert 'ds' in out
    assert 'Data-science operations namespace' in out


def test_observerctl_ds_help_exposes_frame1_command_family(capsys) -> None:
    parser = observerctl_module._build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(['ds', '-h'])

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert 'build' in out
    assert 'train' in out
    assert 'evaluate' in out
    assert 'score' in out
    assert 'run' in out
    assert 'wizard' in out


def test_ds_wizard_emits_frame4_shell_packet_with_workflow_filtering(capsys) -> None:
    rc = main(['ds', 'wizard', '--workflow', 'run-pipeline', '--json'])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['decision'] == 'go'
    assert payload['action'] == 'ds-wizard'
    assert payload['command_family'] == 'ds'
    assert payload['command_path'] == 'observerctl ds wizard'
    assert payload['implementation_state'] == 'wizard-available'
    assert 'delivery_frame' not in payload
    assert payload['workflow'] == 'run-pipeline'
    assert payload['current_page'] == 'landing'
    assert 'flow' in payload['visible_sections']
    assert 'in' in payload['visible_sections']
    assert 'eval' in payload['visible_sections']
    assert payload['execution_state'] == 'blocked'
    assert 'home:' in payload['wizard_view']
    assert 'sections: flow, in, out, model, eval, report, cmd, check, run, exit' not in payload['wizard_view']


def test_ds_wizard_state_persists_across_section_navigation() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')
    observerctl_module._ds_wizard_set_value(state, 'input_paths', ['alpha.jsonl'])

    observerctl_module._ds_wizard_open_section(state, 'model')
    observerctl_module._ds_wizard_move_section(state, 'next')
    observerctl_module._ds_wizard_move_section(state, 'prev')

    assert state.active_section == 'model'
    assert state.active_page == 'configure'
    assert state.active_group == 'model'
    assert state.values['input_paths'] == ['alpha.jsonl']


def test_ds_wizard_filters_sections_by_workflow() -> None:
    build_state = observerctl_module._ds_wizard_new_state('build')
    demo_state = observerctl_module._ds_wizard_new_state('run-demo')

    build_sections = observerctl_module._ds_wizard_visible_sections(build_state)
    demo_sections = observerctl_module._ds_wizard_visible_sections(demo_state)

    assert 'eval' not in build_sections
    assert 'report' not in build_sections
    assert 'in' not in demo_sections
    assert 'model' in demo_sections


def test_ds_wizard_hydrates_retained_artifacts(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(tmp_path / 'features.csv'),
        'labels_csv': str(tmp_path / 'labels.csv'),
    }), encoding='utf-8')
    (tmp_path / 'features.csv').write_text('record_id\n', encoding='utf-8')
    (tmp_path / 'labels.csv').write_text('record_id,label\n', encoding='utf-8')

    train_manifest = tmp_path / 'train_manifest.json'
    train_manifest.write_text(json.dumps({
        'dataset_manifest_path': str(dataset_manifest),
        'model_path': str(tmp_path / 'model.pkl'),
        'model_type': 'unsupervised',
    }), encoding='utf-8')
    (tmp_path / 'model.pkl').write_bytes(b'model')

    baseline_packet = tmp_path / 'baseline.json'
    baseline_packet.write_text(json.dumps({'baseline_window_id': 'frame4-window'}), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('score')
    observerctl_module._ds_wizard_hydrate_dataset_manifest(state, dataset_manifest)
    observerctl_module._ds_wizard_hydrate_train_manifest(state, train_manifest)
    observerctl_module._ds_wizard_hydrate_baseline_analysis(state, baseline_packet)

    assert state.values['dataset_manifest'] == str(dataset_manifest)
    assert state.values['features_csv'] == str(tmp_path / 'features.csv')
    assert state.values['model_path'] == str(tmp_path / 'model.pkl')
    assert state.values['model_type'] == 'unsupervised'
    assert state.values['baseline_window_id'] == 'frame4-window'


def test_ds_wizard_hydrates_prior_run_ledger(tmp_path: Path) -> None:
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    model_path = tmp_path / 'model.pkl'
    run_json = tmp_path / 'run.json'

    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
    }), encoding='utf-8')
    run_json.write_text(json.dumps({
        'identity': {'run_id': 'frame6-ledger-import'},
        'context': {'constraints': {'max_fpr': 0.02}},
        'data': {
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
            'dataset_manifest': str(dataset_manifest),
        },
        'model': {
            'family': 'trained_apexlab',
            'source': str(model_path),
        },
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_hydrate_run_ledger(state, run_json)

    assert state.run_ledger_path == str(run_json)
    assert state.values['run_id'] == 'frame6-ledger-import'
    assert state.values['max_fpr'] == 0.02
    assert state.values['dataset_manifest'] == str(dataset_manifest)
    assert state.values['features_csv'] == str(features_csv)
    assert state.values['labels_csv'] == str(labels_csv)
    assert state.values['model_path'] == str(model_path)
    assert state.hydrated_from['run_id'] == 'run_ledger'
    assert state.hydrated_from['max_fpr'] == 'run_ledger'
    assert state.hydrated_from['model_path'] == 'run_ledger'


def test_ds_wizard_reselection_supports_keep_clear_new() -> None:
    state = observerctl_module._ds_wizard_new_state('train')
    observerctl_module._ds_wizard_set_value(state, 'out_dir', 'alpha')

    observerctl_module._ds_wizard_apply_reselection(state, 'out_dir', 'keep')
    assert state.values['out_dir'] == 'alpha'

    observerctl_module._ds_wizard_apply_reselection(state, 'out_dir', 'clear')
    assert state.values['out_dir'] == ''

    observerctl_module._ds_wizard_apply_reselection(state, 'out_dir', 'new', 'beta')
    assert state.values['out_dir'] == 'beta'


def test_ds_wizard_execute_is_blocked_when_validation_has_not_passed() -> None:
    state = observerctl_module._ds_wizard_new_state('train')
    packet = observerctl_module._ds_wizard_attempt_execute(state)

    assert packet['decision'] == 'no-go'
    assert 'critical_check_failed:wizard_validation_blocked' in packet['reason_codes']
    assert 'dataset_manifest is required' in packet['validation_issues']


def test_ds_wizard_save_and_load_draft_round_trip(tmp_path: Path) -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'report')
    observerctl_module._ds_wizard_set_value(state, 'run_id', 'draft-run-001')
    observerctl_module._ds_wizard_set_value(state, 'max_fpr', '0.03')
    state.source = 'real'
    state.mode = 'canary'
    state.values['source'] = 'real'
    state.values['mode'] = 'canary'
    state.hydrated_from['run_id'] = 'run_ledger'
    state.run_ledger_path = str(tmp_path / 'prior_run.json')

    draft_path = tmp_path / 'wizard_draft.json'
    observerctl_module._ds_wizard_save_draft(state, draft_path)
    loaded = observerctl_module._ds_wizard_load_draft(draft_path)

    assert draft_path.exists()
    assert loaded.workflow == 'evaluate'
    assert loaded.active_page == 'configure'
    assert loaded.active_group == 'eval-report'
    assert loaded.active_section == 'report'
    assert loaded.values['run_id'] == 'draft-run-001'
    assert loaded.values['max_fpr'] == 0.03
    assert loaded.source == 'real'
    assert loaded.mode == 'canary'
    assert loaded.hydrated_from['run_id'] == 'run_ledger'
    assert loaded.run_ledger_path == str(tmp_path / 'prior_run.json')
    assert loaded.draft_path == str(draft_path)


def test_ds_wizard_starts_on_sparse_landing_page() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')

    rendered = observerctl_module._ds_wizard_render(state)

    assert 'path: ds wizard > landing' in rendered
    assert 'home:' in rendered
    assert '1. configure' in rendered
    assert '2. review and run' in rendered
    assert '3. command and utilities' in rendered
    assert '4. exit' in rendered
    assert 'sections: flow, in, out, model, eval, report, cmd, check, run, exit' not in rendered
    assert not any(line.startswith('next:') for line in rendered)


def test_ds_wizard_scope_help_from_landing_shows_top_level_choices() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '?')

    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'help:' in rendered
    assert 'configure          guided workflow and configuration' in rendered
    assert 'review and run     validation, command preview, and execution' in rendered
    assert 'command and utilities preview the command and use save/load/hydrate helper commands' in rendered


def test_ds_wizard_landing_choices_route_to_top_level_pages() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '1')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'workflow'
    assert state.active_section == 'flow'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'home')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'landing'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '2')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'review-run'
    assert state.active_section == 'check'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'home')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'landing'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '3')
    assert packet is None
    assert should_exit is False
    assert state.active_page == 'utilities'
    assert state.active_section == 'cmd'


def test_ds_wizard_configure_opens_guided_flow_surface_without_preselected_workflow() -> None:
    state = observerctl_module._ds_wizard_new_state('')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'configure')

    assert packet is None
    assert should_exit is False
    assert state.active_page == 'workflow'
    assert state.active_section == 'flow'


def test_ds_wizard_configure_restores_shared_section_rail() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')

    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'configure')
    assert state.active_page == 'workflow'
    assert observerctl_module._ds_wizard_page_sections(state) == ['flow', 'in', 'out', 'model', 'eval', 'report', 'cmd', 'check', 'run']
    assert observerctl_module._ds_wizard_action_line(state) == 'actions: type name | next/prev | validate | cmd | ? | exit'


def test_ds_wizard_scope_help_from_section_is_section_scoped() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '?')

    assert packet is None
    assert should_exit is False
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'help: eval' in rendered
    assert 'Review evaluation thresholds and report-facing controls.' in rendered
    assert 'fields:' in rendered
    assert '  max_fpr          Maximum false-positive rate' in rendered


def test_ds_wizard_execute_runs_workflow_and_surfaces_reports(monkeypatch) -> None:
    state = observerctl_module._ds_wizard_new_state('run-demo')

    def fake_run_demo(*, out_dir: str, dataset_seed: int, model_seed: int, max_fpr: float):
        assert out_dir == ''
        assert dataset_seed == 123
        assert model_seed == 42
        assert max_fpr == 0.01
        return {
            'timestamp_utc': '2026-03-31T00:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-run',
            'command_family': 'ds',
            'command_path': 'observerctl ds run demo',
            'implementation_state': 'automation-available',
            'summary': 'Demo pipeline completed through observerctl ds.',
            'workflow_steps': ['generate', 'build', 'train-supervised', 'train-unsupervised', 'evaluate'],
            'artifacts': {
                'evaluation_run_json': 'C:/temp/demo/evaluation/run.json',
                'evaluation_run_md': 'C:/temp/demo/evaluation/run.md',
            },
            'reason_codes': [],
        }

    monkeypatch.setattr(observerctl_module, '_ds_run_demo', fake_run_demo)

    packet = observerctl_module._ds_wizard_attempt_execute(state)

    assert packet['decision'] == 'go'
    assert packet['action'] == 'ds-run'
    assert packet['wizard_workflow'] == 'run-demo'
    assert packet['command_preview'] == 'observerctl ds run demo --dataset-seed 123 --model-seed 42 --max-fpr 0.01'
    assert packet['artifacts']['evaluation_run_json'].endswith('run.json')
    assert packet['artifacts']['evaluation_run_md'].endswith('run.md')


def test_ds_wizard_item_peek_does_not_change_state() -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')
    observerctl_module._ds_wizard_set_value(state, 'max_fpr', '0.05')

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '? max_fpr')

    assert packet is None
    assert should_exit is False
    assert state.active_section == 'eval'
    assert state.values['max_fpr'] == 0.05
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'peek: max_fpr' in rendered
    assert 'Maximum false-positive rate' in rendered
    assert 'value: 0.05' in rendered


def test_ds_wizard_blank_input_dismisses_transient_help() -> None:
    state = observerctl_module._ds_wizard_new_state('run-pipeline')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, '?')
    assert state.transient_view == 'scope-help'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, '')

    assert packet is None
    assert should_exit is False
    assert state.transient_view == ''
    rendered = observerctl_module._ds_wizard_render(state)
    assert 'help:' not in rendered


def test_ds_wizard_educational_flash_clears_after_interactive_emit(monkeypatch, capsys) -> None:
    state = observerctl_module._ds_wizard_new_state('')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'configure')
    state, _, _ = observerctl_module._ds_wizard_handle_command(state, 'run-pipeline')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_try_clear_terminal', lambda: False)

    observerctl_module._ds_wizard_emit_interactive_frame(state, redraw_count=0)

    out = capsys.readouterr().out
    assert 'workflow set: run-pipeline' in out
    assert state.transient_view == ''


def test_ds_wizard_first_interactive_render_does_not_emit_transition_separator(monkeypatch, capsys) -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_try_clear_terminal', lambda: False)

    observerctl_module._ds_wizard_emit_interactive_frame(state, redraw_count=0)

    out = capsys.readouterr().out.splitlines()
    assert out[0] == 'ObserverCTL DS Wizard'
    assert 'next frame: ds wizard > configure > eval' not in out


def test_ds_wizard_interactive_redraw_uses_separator_when_clear_is_unavailable(monkeypatch, capsys) -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_try_clear_terminal', lambda: False)

    observerctl_module._ds_wizard_emit_interactive_frame(state, redraw_count=1)

    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith('=')
    assert out[1] == 'next frame: ds wizard > configure > eval'
    assert out[2].startswith('=')
    assert 'ObserverCTL DS Wizard' in out


def test_ds_wizard_interactive_redraw_skips_separator_when_clear_succeeds(monkeypatch, capsys) -> None:
    state = observerctl_module._ds_wizard_new_state('evaluate')
    observerctl_module._ds_wizard_open_section(state, 'eval')
    monkeypatch.setattr(observerctl_module, '_ds_wizard_try_clear_terminal', lambda: True)

    observerctl_module._ds_wizard_emit_interactive_frame(state, redraw_count=1)

    out = capsys.readouterr().out.splitlines()
    assert out[0] == 'ObserverCTL DS Wizard'
    assert 'next frame: ds wizard > configure > eval' not in out


def test_ds_wizard_command_surface_supports_run_hydration_and_draft_round_trip(tmp_path: Path) -> None:
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    model_path = tmp_path / 'model.pkl'
    run_json = tmp_path / 'run.json'
    draft_path = tmp_path / 'wizard_draft.json'

    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    model_path.write_bytes(b'model')
    dataset_manifest.write_text(json.dumps({
        'features_csv': str(features_csv),
        'labels_csv': str(labels_csv),
    }), encoding='utf-8')
    run_json.write_text(json.dumps({
        'identity': {'run_id': 'frame6-command-ledger'},
        'context': {'constraints': {'max_fpr': 0.015}},
        'data': {
            'features_csv': str(features_csv),
            'labels_csv': str(labels_csv),
            'dataset_manifest': str(dataset_manifest),
        },
        'model': {'source': str(model_path)},
    }), encoding='utf-8')

    state = observerctl_module._ds_wizard_new_state('evaluate')
    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'hydrate run {0}'.format(run_json))
    assert packet is None
    assert should_exit is False
    assert state.values['run_id'] == 'frame6-command-ledger'

    state, packet, should_exit = observerctl_module._ds_wizard_handle_command(state, 'save draft {0}'.format(draft_path))
    assert packet is None
    assert should_exit is False
    assert draft_path.exists()

    restored = observerctl_module._ds_wizard_new_state('evaluate')
    restored, packet, should_exit = observerctl_module._ds_wizard_handle_command(restored, 'load draft {0}'.format(draft_path))
    assert packet is None
    assert should_exit is False
    assert restored.values['run_id'] == 'frame6-command-ledger'
    assert restored.values['max_fpr'] == 0.015
    assert restored.draft_path == str(draft_path)


def test_ds_run_demo_executes_wrapper_and_emits_artifact_summary(tmp_path: Path, capsys) -> None:
    try:
        import apexlab  # noqa: F401
    except ImportError:
        pytest.skip('ApexLab not installed')

    out_dir = tmp_path / 'demo_flow'
    rc = main(['ds', 'run', 'demo', '--out-dir', str(out_dir), '--json'])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-run'
    assert payload['run_mode'] == 'demo'
    assert payload['implementation_state'] == 'automation-available'
    assert 'delivery_frame' not in payload
    assert payload['total_records'] == 60
    assert Path(payload['artifacts']['root_dir']).exists()
    assert Path(payload['artifacts']['dataset_manifest']).exists()
    assert Path(payload['artifacts']['supervised_model_path']).exists()
    assert Path(payload['artifacts']['unsupervised_model_path']).exists()
    assert Path(payload['artifacts']['evaluation_run_json']).exists()
    assert Path(payload['artifacts']['evaluation_run_md']).exists()


def test_ds_run_pipeline_executes_supervised_flow_and_emits_artifact_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    try:
        import apexlab  # noqa: F401
    except ImportError:
        pytest.skip('ApexLab not installed')

    log_dir = tmp_path / 'logs'
    (log_dir / 'health').mkdir(parents=True, exist_ok=True)
    (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
    (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    input_path = tmp_path / 'input.jsonl'
    _write_signed_jsonl(input_path, _make_ds_records())
    out_dir = tmp_path / 'pipeline_flow'

    rc = main([
        'ds', 'run', 'pipeline',
        '--input', str(input_path),
        '--out-dir', str(out_dir),
        '--model-type', 'supervised',
        '--seed', '42',
        '--json',
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-run'
    assert payload['run_mode'] == 'pipeline'
    assert payload['implementation_state'] == 'automation-available'
    assert 'delivery_frame' not in payload
    assert payload['model_type'] == 'supervised'
    assert payload['has_labels'] is True
    assert payload['workflow_steps'] == ['build', 'train', 'evaluate']
    assert Path(payload['artifacts']['dataset_manifest']).exists()
    assert Path(payload['artifacts']['train_manifest']).exists()
    assert Path(payload['artifacts']['model_path']).exists()
    assert Path(payload['artifacts']['run_json']).exists()
    assert Path(payload['artifacts']['run_md']).exists()


def test_ds_build_executes_wrapper_and_emits_artifact_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    (log_dir / 'health').mkdir(parents=True, exist_ok=True)
    (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
    (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    input_path = tmp_path / 'input.jsonl'
    _write_signed_jsonl(input_path, _make_ds_records())
    out_dir = tmp_path / 'dataset'

    rc = main(['ds', 'build', '--input', str(input_path), '--out-dir', str(out_dir), '--seed', '123', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-build'
    assert payload['implementation_state'] == 'command-available'
    assert 'delivery_frame' not in payload
    assert Path(payload['artifacts']['dataset_manifest']).exists()
    assert Path(payload['artifacts']['features_csv']).exists()
    assert payload['has_labels'] is True
    assert int(payload['total_records']) == 12


def test_ds_train_executes_wrapper_and_emits_expected_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    try:
        import apexlab  # noqa: F401
    except ImportError:
        pytest.skip('ApexLab not installed')

    log_dir = tmp_path / 'logs'
    (log_dir / 'health').mkdir(parents=True, exist_ok=True)
    (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
    (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    from analysis.dataset_builder import build_dataset

    input_path = tmp_path / 'input.jsonl'
    _write_signed_jsonl(input_path, _make_ds_records())
    dataset_dir = tmp_path / 'dataset'
    build_dataset([input_path], out_dir=dataset_dir, seed=123)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    model_dir = tmp_path / 'models'

    rc = main(['ds', 'train', '--dataset', str(manifest_path), '--out-dir', str(model_dir), '--model-type', 'supervised', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-train'
    assert payload['model_type'] == 'supervised'
    assert Path(payload['artifacts']['train_manifest']).exists()
    assert Path(payload['artifacts']['model_path']).exists()
    assert Path(payload['artifacts']['metrics_path']).exists()


def test_ds_evaluate_executes_wrapper_and_emits_run_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    (log_dir / 'health').mkdir(parents=True, exist_ok=True)
    (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
    (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    from analysis.dataset_builder import build_dataset

    input_path = tmp_path / 'input.jsonl'
    _write_signed_jsonl(input_path, _make_ds_records())
    dataset_dir = tmp_path / 'dataset'
    manifest = build_dataset([input_path], out_dir=dataset_dir, seed=123)
    eval_dir = tmp_path / 'evaluation'

    rc = main([
        'ds', 'evaluate',
        '--features-csv', str(Path(manifest.features_csv)),
        '--labels-csv', str(Path(manifest.labels_csv)),
        '--dataset-manifest', str(dataset_dir / 'dataset_manifest.json'),
        '--out-dir', str(eval_dir),
        '--run-id', 'unit-eval',
        '--json',
    ])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-evaluate'
    assert payload['run_id'] == 'unit-eval'
    assert Path(payload['artifacts']['run_json']).exists()
    assert Path(payload['artifacts']['run_md']).exists()
    assert payload['has_labels'] is True


def test_ds_score_executes_wrapper_and_emits_score_artifact_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    try:
        import apexlab  # noqa: F401
    except ImportError:
        pytest.skip('ApexLab not installed')

    log_dir = tmp_path / 'logs'
    (log_dir / 'health').mkdir(parents=True, exist_ok=True)
    (log_dir / 'data' / 'calamum').mkdir(parents=True, exist_ok=True)
    (log_dir / 'control' / 'calamum').mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    from analysis.dataset_builder import build_dataset
    from analysis.train_model import train_model

    input_path = tmp_path / 'input.jsonl'
    _write_signed_jsonl(input_path, _make_ds_records())
    dataset_dir = tmp_path / 'dataset'
    build_dataset([input_path], out_dir=dataset_dir, seed=123)
    manifest_path = dataset_dir / 'dataset_manifest.json'
    model_dir = tmp_path / 'models_unsupervised'
    train_model(manifest_path, out_dir=model_dir, model_type='unsupervised', seed=42)

    out_file = tmp_path / 'scores.csv'
    rc = main([
        'ds', 'score',
        '--dataset', str(manifest_path),
        '--model', str(model_dir / 'train_manifest.json'),
        '--out-file', str(out_file),
        '--json',
    ])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'ds-score'
    assert payload['records_scored'] == 12
    assert payload['score_column'] == 'score_anomaly'
    assert Path(payload['artifacts']['scores_csv']).exists()


def test_sandbox_list_emits_definition_catalog_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_definitions', lambda: [
        {
            'id': 'metadata-contract',
            'title': 'Metadata contract probe',
            'summary': 'Validate metadata contract expectations.',
            'status': 'stable',
            'category': 'metadata-probe',
            'writes_to': 'report_tmp/frame4_metadata_contract_probe',
        }
    ])

    rc = main(['sandbox', 'list', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-list'
    assert payload['decision'] == 'go'
    assert payload['definitions'][0]['id'] == 'metadata-contract'


def test_sandbox_list_human_output_uses_structured_decision_block(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_definitions', lambda: [
        {
            'id': 'metadata-contract',
            'title': 'Metadata contract probe',
            'summary': 'Validate metadata contract expectations.',
            'status': 'stable',
            'category': 'metadata-probe',
            'writes_to': 'report_tmp/frame4_metadata_contract_probe',
        }
    ])

    rc = main(['sandbox', 'list'])
    assert rc == 0

    out = capsys.readouterr().out
    assert '[ ORACL-Prime :: observerctl ] SANDBOX/CATALOG' in out
    assert '[OK] SANDBOX_DEFINITIONS_LISTED' in out
    assert 'Template Class  : decision' in out
    assert 'Definition Count: 1' in out
    assert '- metadata-contract' in out
    assert 'Purpose         : Validate metadata contract expectations.' in out


def test_sandbox_show_emits_definition_detail_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_definition', lambda definition_id: {
        'id': definition_id,
        'title': 'Metadata contract probe',
        'summary': 'Validate metadata contract expectations.',
        'status': 'stable',
        'category': 'metadata-probe',
        'aliases': [],
        'selector_policy': 'exact-name-only',
        'writes_to': 'report_tmp/frame4_metadata_contract_probe',
        'purpose': 'Verify metadata contract fields.',
        'command': 'observerctl sandbox run metadata-contract',
        'run_index_path': 'report_tmp/frame4_metadata_contract_probe/run_index.jsonl',
    })

    rc = main(['sandbox', 'show', 'metadata-contract', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-show'
    assert payload['definition']['id'] == 'metadata-contract'
    assert payload['definition']['command'] == 'observerctl sandbox run metadata-contract'


def test_real_sandbox_registry_includes_ds_wizard_hydration_definition() -> None:
    definition = observerctl_module.sandbox_get_definition('ds-wizard-hydration')

    assert definition is not None
    assert definition['id'] == 'ds-wizard-hydration'
    assert definition['command'] == 'observerctl sandbox run ds-wizard-hydration'
    assert definition['run_index_path'].endswith('frame4_ds_wizard_hydration_probe/run_index.jsonl')


def test_real_sandbox_registry_includes_ds_wizard_durability_definition() -> None:
    definition = observerctl_module.sandbox_get_definition('ds-wizard-durability')

    assert definition is not None
    assert definition['id'] == 'ds-wizard-durability'
    assert definition['command'] == 'observerctl sandbox run ds-wizard-durability'
    assert definition['run_index_path'].endswith('frame6_ds_wizard_durability_probe/run_index.jsonl')


def test_sandbox_show_human_output_includes_alias_policy_and_trailing_contract(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_definition', lambda definition_id: {
        'id': definition_id,
        'title': 'Baseline monitor runtime probe',
        'summary': 'Validate baseline-monitor runtime liveness plus resource_normal retention continuity.',
        'status': 'stable',
        'category': 'runtime-probe',
        'aliases': [],
        'selector_policy': 'exact-name-only',
        'writes_to': 'report_tmp/job0022_baseline_monitor_runtime_probe',
        'purpose': 'Prove the sandboxed baseline-monitor runtime and retained evidence flow are intact.',
        'command': 'observerctl sandbox run baseline-monitor-runtime',
        'run_index_path': 'report_tmp/job0022_baseline_monitor_runtime_probe/run_index.jsonl',
    })

    rc = main(['sandbox', 'show', 'baseline-monitor-runtime'])
    assert rc == 0

    out = capsys.readouterr().out
    assert '[OK] SANDBOX_DEFINITION_READY' in out
    assert 'Selection' in out
    assert 'Aliases         : none (exact-name-only)' in out
    assert 'Guardrails' in out
    assert 'Contract' in out


def test_sandbox_run_emits_execution_packet_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_run_definition', lambda definition_id: {
        'decision': 'go',
        'reason_codes': [],
        'definition_id': definition_id,
        'result': 'pass',
        'returncode': 0,
        'run_id': 'metadata-contract-001',
        'artifacts': {
            'report_json': 'report_tmp/frame4_metadata_contract_probe/metadata-contract-001/report.json',
            'run_index': 'report_tmp/frame4_metadata_contract_probe/run_index.jsonl',
        },
        'stdout_text': 'run_id=metadata-contract-001\n',
        'stderr_text': '',
        'next_review_command': 'observerctl sandbox runs show metadata-contract-001',
    })

    rc = main(['sandbox', 'run', 'metadata-contract', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-run'
    assert payload['definition_id'] == 'metadata-contract'
    assert payload['run_id'] == 'metadata-contract-001'


def test_sandbox_runs_list_emits_retained_runs_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_list_runs', lambda: [
        {
            'run_id': 'baseline-monitor-runtime-001',
            'definition_id': 'baseline-monitor-runtime',
            'timestamp_utc': '2026-03-23T00:00:00Z',
            'result': 'pass',
            'report_path': 'report_tmp/job0022_baseline_monitor_runtime_probe/baseline-monitor-runtime-001/report.json',
            'run_dir': 'report_tmp/job0022_baseline_monitor_runtime_probe/baseline-monitor-runtime-001',
            'index_path': 'report_tmp/job0022_baseline_monitor_runtime_probe/run_index.jsonl',
        }
    ])

    rc = main(['sandbox', 'runs', 'list', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-runs-list'
    assert payload['runs'][0]['definition_id'] == 'baseline-monitor-runtime'


def test_sandbox_runs_show_emits_run_review_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(observerctl_module, 'sandbox_get_run', lambda run_id: (
        {
            'run_id': run_id,
            'definition_id': 'metadata-contract',
            'timestamp_utc': '2026-03-23T00:00:00Z',
            'result': 'pass',
            'report_path': 'report_tmp/frame4_metadata_contract_probe/{0}/report.json'.format(run_id),
        },
        {
            'next_bite_result': 'pass',
            'all_sample_fields_present': True,
            'all_index_fields_present': True,
        },
    ))

    rc = main(['sandbox', 'runs', 'show', 'metadata-contract-001', '--json'])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload['action'] == 'sandbox-runs-show'
    assert payload['run']['run_id'] == 'metadata-contract-001'
    assert payload['report']['all_sample_fields_present'] is True


def test_gate_check_go_in_sim_mode(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'go'
    assert gate['reason_codes'] == []


def test_gate_noop_transition_denied(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='watch')
    assert gate['decision'] == 'no-go'
    assert 'policy_denied:no_op_transition' in gate['reason_codes']


def test_gate_check_real_requires_api_key(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    monkeypatch.delenv('MOLTBOOK_API_KEY', raising=False)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='real')
    gate = evaluate_gate_decision(status)
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:env.moltbook_api_key' in gate['reason_codes']


def test_gate_allows_idle_service_when_observer_heartbeat_stale(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    observer_hb = health / 'calamum_observer.heartbeat'
    stale_ts = 946684800.0  # 2000-01-01 UTC
    os.utime(observer_hb, (stale_ts, stale_ts))

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)

    status = collect_runtime_status(source='sim')
    assert status['checks']['runtime.observer_service']['status'] == 'ok'
    assert status['checks']['runtime.collection_state']['state'] in ('idle', 'warmup', 'stopped')

    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'go'
    assert 'critical_check_failed:observer_heartbeat_stale' not in gate.get('reason_codes', [])


def test_watchdog_check_stale_observer_heartbeat_is_advisory_when_service_alive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    observer_hb = health / 'calamum_observer.heartbeat'
    stale_ts = 946684800.0  # 2000-01-01 UTC
    os.utime(observer_hb, (stale_ts, stale_ts))

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)

    packet = observerctl_module._watchdog_check()
    assert packet.get('decision') == 'go'
    assert 'critical_check_failed:observer_heartbeat_stale' not in packet.get('reason_codes', [])
    assert 'major_check_failed:observer_heartbeat_stale_service_alive' in packet.get('advisory_reason_codes', [])


def test_evidence_pack_writes_publish_grade_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    output = tmp_path / 'evidence.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--output', str(output), '--json'])
    assert rc == 0
    assert output.exists()

    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['runtime_cli_surface'] == 'observerctl'
    assert 'provenance' in payload
    assert 'methodology' in payload
    assert 'process' in payload
    assert 'readiness_surfaces' in payload
    assert 'readiness_projection' in payload
    assert 'stage5_prerequisites' in payload
    assert payload['readiness_surfaces']['posture_receipt']['path'].endswith('watchdog_posture_state.json')
    assert payload['provenance']['artifact_sha256']


def test_evidence_pack_supports_non_activation_live_projection_and_retained_refs(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    segment_path = archive_dir / 'resource_sim_canary_normal_unit_seg0001.jsonl'
    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_frame8-proof_seg0001.jsonl'
    segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z","baseline_window_id":"frame8-proof-window"}\n', encoding='utf-8')
    resource_index = resource_dir / 'index.jsonl'
    resource_index.write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_normal',
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_baseline',
            'baseline_window_id': 'frame8-proof-window',
            'window_id': 'frame8-proof-window',
        }) + '\n',
        encoding='utf-8',
    )

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_test.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'baseline_window_id': 'frame8-proof-window',
        'sample_counts': {'resource_normal': 5, 'resource_baseline': 5},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    evidence_index = evidence_dir / 'index.jsonl'
    evidence_index.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-live-proof', '--output', str(output), '--json'])
    assert rc == 0
    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['gate_packet']['to_state'] == 'sim:live'
    assert payload['readiness_projection']['projection_mode'] == 'non-activation'
    assert payload['stage5_prerequisites']['C22_baseline_validation_rate_escalated']['status'] == 'ok'
    assert payload['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['C25_resource_baseline_window_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['baseline_monitor_runtime_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['overall']['status'] == 'ok'
    assert payload['readiness_surfaces']['baseline_monitor']['monitor_state_path'].endswith('baseline_monitor_state.json')
    assert payload['readiness_surfaces']['resource_stream_retention']['index_path'].endswith('resource/index.jsonl')
    assert payload['readiness_surfaces']['baseline_window']['packet_path'].endswith('observerctl_baseline-analysis_test.json')
    assert any(str(ref).endswith('baseline_monitor_state.json') for ref in payload['process']['evidence_refs'])


def test_non_activation_live_projection_keeps_c24_ready_when_collection_is_idle_with_fresh_resource_normal(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    segment_path = archive_dir / 'resource_sim_canary_normal_idle_seg0001.jsonl'
    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_idle_seg0001.jsonl'
    segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z","baseline_window_id":"frame8-idle-window"}\n', encoding='utf-8')
    (resource_dir / 'index.jsonl').write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(segment_path).replace('\\', '/'),
            'segment_records': 2,
            'stream_type': 'resource_normal',
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_baseline',
            'baseline_window_id': 'frame8-idle-window',
            'window_id': 'frame8-idle-window',
        }) + '\n',
        encoding='utf-8',
    )

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_idle_continuity.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'baseline_window_id': 'frame8-idle-window',
        'sample_counts': {'resource_normal': 2, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    status = collect_runtime_status(source='sim')
    assert status['checks']['runtime.observer_service']['status'] == 'ok'
    assert status['checks']['runtime.collection_state']['state'] in ('idle', 'warmup', 'stopped')
    assert status['checks']['watchdog.resource_stream_retention']['status'] == 'ok'
    assert status['checks']['watchdog.resource_stream_retention']['records_indexed'] == 2

    output = tmp_path / 'evidence_live_projection_idle_continuity.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-idle-continuity-proof', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['overall']['status'] == 'ok'


def test_non_activation_live_projection_denies_c24_when_only_baseline_stream_is_fresh(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_only_seg0001.jsonl'
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    (resource_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'segment_path': str(baseline_segment_path).replace('\\', '/'),
        'segment_records': 3,
        'stream_type': 'resource_baseline',
    }) + '\n', encoding='utf-8')

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_baseline_only.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'sample_counts': {'resource_normal': 0, 'resource_baseline': 3},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection_baseline_only.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-baseline-only-not-continuity', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    c24 = payload['stage5_prerequisites']['C24_resource_stream_retention_ready']
    assert c24['status'] == 'err'
    assert 'critical_check_failed:resource_stream_retention_unavailable' in c24['reason_codes']
    assert payload['stage5_prerequisites']['overall']['status'] == 'err'


def test_resource_stream_retention_resolves_archived_normal_segment_via_manifest(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame7-archived-normal',
        '--json',
    ]) == 0

    archive_dir = log_dir / 'data' / 'calamum' / 'archive'
    raw_segments_before = sorted(archive_dir.glob('resource_sim_canary_normal_frame7-archived-normal_seg*.jsonl'))
    assert len(raw_segments_before) >= 1

    Librarian(interval_sec=0.01).run_once()

    raw_segments_after = sorted(archive_dir.glob('resource_sim_canary_normal_frame7-archived-normal_seg*.jsonl'))
    archived_segments = sorted(archive_dir.glob('resource_sim_canary_normal_frame7-archived-normal_seg*.jsonl.gz'))
    assert raw_segments_after == []
    assert len(archived_segments) >= 1

    status = collect_runtime_status(source='sim')
    resource_row = status['checks']['watchdog.resource_stream_retention']
    assert resource_row['status'] == 'ok'
    assert resource_row['segment_exists'] is True
    assert resource_row['segment_resolution'] == 'archived'
    assert resource_row['resolved_segment_path'].endswith('.jsonl.gz')
    assert resource_row['archive_manifest_exists'] is True


def test_baseline_window_health_resolves_archived_baseline_segment_via_manifest(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame8-normal-support',
        '--json',
    ]) == 0

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'baseline',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame8-archived-baseline',
        '--json',
    ]) == 0

    Librarian(interval_sec=0.01).run_once()

    assert main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '1',
        '--min-normal-samples', '1',
        '--min-baseline-samples', '1',
        '--json',
    ]) == 0

    status = collect_runtime_status(source='sim')
    baseline_row = status['checks']['watchdog.resource_baseline_window']
    assert baseline_row['status'] == 'ok'
    assert baseline_row['baseline_window_id'] == 'frame8-archived-baseline'
    assert baseline_row['segment_count'] >= 1
    assert baseline_row['resolved_segment_count'] == baseline_row['segment_count']
    assert baseline_row['segment_resolution'] == 'archived'
    assert baseline_row['archive_manifest_exists'] is True
    assert any(str(ref).endswith('.jsonl.gz') for ref in baseline_row['resolved_segment_paths'])


def test_non_activation_live_projection_keeps_c24_ready_when_latest_normal_segment_is_archived(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame7-live-proof-archived',
        '--json',
    ]) == 0

    Librarian(interval_sec=0.01).run_once()

    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_frame7_archived.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'sample_counts': {'resource_normal': 2, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection_archived_normal.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-archived-normal-proof', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    resource_surface = payload['readiness_surfaces']['resource_stream_retention']
    c24 = payload['stage5_prerequisites']['C24_resource_stream_retention_ready']
    assert resource_surface['status'] == 'ok'
    assert resource_surface['segment_resolution'] == 'archived'
    assert resource_surface['resolved_segment_path'].endswith('.jsonl.gz')
    assert resource_surface['archive_manifest_path'].endswith('archive/manifest.json')
    assert c24['status'] == 'ok'
    assert c24['segment_resolution'] == 'archived'
    assert any(str(ref).endswith('archive/manifest.json') for ref in c24['evidence_refs'])
    assert any(str(ref).endswith('.jsonl.gz') for ref in c24['evidence_refs'])


def test_non_activation_live_projection_denies_c25_when_archived_baseline_artifact_is_missing(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame8-normal-continuity',
        '--json',
    ]) == 0

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'baseline',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame8-missing-baseline',
        '--json',
    ]) == 0

    Librarian(interval_sec=0.01).run_once()

    assert main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '1',
        '--min-normal-samples', '1',
        '--min-baseline-samples', '1',
        '--json',
    ]) == 0

    archive_dir = data / 'archive'
    archived_baseline_segments = sorted(archive_dir.glob('resource_sim_canary_baseline_frame8-missing-baseline_seg*.jsonl.gz'))
    assert archived_baseline_segments
    for path in archived_baseline_segments:
        path.unlink()

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection_missing_archived_baseline.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-missing-archived-baseline', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    c24 = payload['stage5_prerequisites']['C24_resource_stream_retention_ready']
    baseline_surface = payload['readiness_surfaces']['baseline_window']
    c25 = payload['stage5_prerequisites']['C25_resource_baseline_window_ready']
    assert c24['status'] == 'ok'
    assert baseline_surface['status'] == 'err'
    assert baseline_surface['baseline_window_id'] == 'frame8-missing-baseline'
    assert baseline_surface['segment_resolution'] == 'missing'
    assert baseline_surface['resolved_segment_count'] == 0
    assert any('frame8-missing-baseline' in str(ref) for ref in baseline_surface['missing_segment_paths'])
    assert c25['status'] == 'err'
    assert 'critical_check_failed:resource_baseline_window_incomplete' in c25['reason_codes']


def test_non_activation_live_projection_denies_c24_when_archived_manifest_artifact_is_missing(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')
    _touch(health / 'calamum_baseline_monitor.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'lockdown'}), encoding='utf-8')

    archive_dir = data / 'archive'
    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir.mkdir(parents=True, exist_ok=True)
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    raw_segment_path = archive_dir / 'resource_sim_canary_normal_frame7-missing-archive_seg0001.jsonl'
    manifest_path = archive_dir / 'manifest.json'
    manifest_path.write_text(json.dumps({
        raw_segment_path.name: {
            'artifact_path': 'resource_sim_canary_normal_frame7-missing-archive_seg0001.jsonl.gz',
            'records': 2,
            'uncompressed_bytes': 100,
        }
    }), encoding='utf-8')

    (resource_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'segment_path': str(raw_segment_path).replace('\\', '/'),
        'segment_records': 2,
        'stream_type': 'resource_normal',
    }) + '\n', encoding='utf-8')

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_frame7_missing_archive.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'sample_counts': {'resource_normal': 2, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    output = tmp_path / 'evidence_live_projection_missing_archived_normal.json'
    rc = main(['ops', 'evidence', 'pack', '--source', 'sim', '--to', 'live', '--event', 'unit-missing-archived-normal', '--output', str(output), '--json'])
    assert rc == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    resource_surface = payload['readiness_surfaces']['resource_stream_retention']
    c24 = payload['stage5_prerequisites']['C24_resource_stream_retention_ready']
    assert resource_surface['status'] == 'err'
    assert resource_surface['segment_resolution'] == 'missing'
    assert resource_surface['archive_manifest_path'].endswith('archive/manifest.json')
    assert c24['status'] == 'err'
    assert 'critical_check_failed:resource_stream_retention_unavailable' in c24['reason_codes']


def test_ops_mode_gate_and_set_flow(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    rc_gate = main(['ops', 'mode', 'gate', '--to', 'canary', '--source', 'sim', '--json'])
    assert rc_gate == 0

    rc_set = main(['ops', 'mode', 'set', '--to', 'canary', '--source', 'sim', '--json'])
    assert rc_set == 0

    rc_current = main(['ops', 'mode', 'current', '--json'])
    assert rc_current == 0


def test_ops_mode_transition_atomic_flow(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    out = tmp_path / 'transition_evidence.json'
    rc = main([
        'ops', 'mode', 'transition',
        '--to', 'canary',
        '--source', 'sim',
        '--event', 'unit-transition',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()


def test_ops_mode_switch_single_action_syncs_runtime_and_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    observerctl_module._save_state('sim', 'watch')

    # Stabilize gate inputs without requiring real process lifecycle.
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_observer_status',
        lambda max_age_sec=60.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 1234, 'alive': True},
            'pending_stop_signal': False,
        },
    )
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_baseline_monitor_status',
        lambda max_age_sec=90.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 2222, 'alive': True},
            'monitor_state': {'mode': 'canary'},
        },
    )

    calls = {'stop': 0, 'start': 0}

    def _fake_runtime_status() -> dict:
        return {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 1234, 'alive': True},
            'pending_stop_signal': False,
        }

    def _fake_runtime_stop(timeout_sec: float = 8.0) -> dict:
        calls['stop'] += 1
        return {
            'timestamp_utc': '2026-01-01T00:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'runtime-stop',
            'reason_codes': [],
            'stopped_cleanly': True,
            'escalated_terminate': False,
        }

    def _fake_runtime_start(source: str, mode: str, interval_sec: float, timeout_sec: float) -> dict:
        calls['start'] += 1
        return {
            'timestamp_utc': '2026-01-01T00:00:01Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'runtime-start',
            'reason_codes': [],
            'startup_verified': True,
            'state': 'active',
            'pid': {'value': 5678, 'alive': True},
            'source': source,
            'mode': mode,
        }

    monkeypatch.setattr(observerctl_module, '_ops_runtime_status', _fake_runtime_status)
    monkeypatch.setattr(observerctl_module, '_ops_runtime_stop', _fake_runtime_stop)
    monkeypatch.setattr(observerctl_module, '_ops_runtime_start', _fake_runtime_start)

    rc = main(['ops', 'mode', 'switch', '--to', 'canary', '--json'])
    assert rc == 0

    state = observerctl_module._load_state()
    assert state.get('source') == 'sim'
    assert state.get('mode') == 'canary'
    assert calls['stop'] == 1
    assert calls['start'] == 1


def test_ops_mode_switch_defaults_source_from_ssot_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'test-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    observerctl_module._save_state('real', 'watch')

    monkeypatch.setattr(
        observerctl_module,
        '_runtime_observer_status',
        lambda max_age_sec=60.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 1111, 'alive': True},
            'pending_stop_signal': False,
        },
    )
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_baseline_monitor_status',
        lambda max_age_sec=90.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 3333, 'alive': True},
            'monitor_state': {'mode': 'canary'},
        },
    )
    monkeypatch.setattr(observerctl_module, '_ops_runtime_status', lambda: {
        'state': 'stopped',
        'heartbeat': {'status': 'err'},
        'pid': {'value': None, 'alive': False},
        'pending_stop_signal': False,
    })
    monkeypatch.setattr(observerctl_module, '_ops_runtime_stop', lambda timeout_sec=8.0: {
        'timestamp_utc': '2026-01-01T00:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'runtime-stop',
        'reason_codes': [],
    })

    seen = {'source': ''}

    def _fake_runtime_start(source: str, mode: str, interval_sec: float, timeout_sec: float) -> dict:
        seen['source'] = source
        return {
            'timestamp_utc': '2026-01-01T00:00:01Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'runtime-start',
            'reason_codes': [],
            'startup_verified': True,
            'state': 'active',
            'pid': {'value': 5678, 'alive': True},
        }

    monkeypatch.setattr(observerctl_module, '_ops_runtime_start', _fake_runtime_start)

    rc = main(['ops', 'mode', 'switch', '--to', 'canary', '--json'])
    assert rc == 0
    assert seen['source'] == 'real'



def test_ops_evidence_verify_schema_failure(tmp_path: Path, monkeypatch) -> None:
    bad_packet = tmp_path / 'bad_packet.json'
    bad_packet.write_text('{"timestamp_utc":"2026-02-21T00:00:00Z"}\n', encoding='utf-8')

    rc = main(['ops', 'evidence', 'verify', '--packet', str(bad_packet), '--json'])
    assert rc == 2


def test_baseline_librarian_watchdog_health_policy_commands(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    assert main(['baseline', 'status', '--json']) in (0, 2)
    assert main(['baseline', 'check', '--json']) in (0, 2)
    assert main(['baseline', 'set', '--id', 'baseline-ci', '--json']) == 0

    assert main(['librarian', 'stats', '--json']) == 0
    assert main(['librarian', 'stores', '--json']) == 0
    assert main(['librarian', 'rotate', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'compact', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'verify', '--mode', 'watch', '--json']) == 0

    assert main(['watchdog', 'status', '--json']) == 0
    assert main(['watchdog', 'check', '--json']) in (0, 2)
    assert main(['watchdog', 'reasons', '--json']) == 0
    assert main(['watchdog', 'ack', '--code', 'critical_check_failed:watchdog_heartbeat_stale', '--json']) == 0

    assert main(['health', 'quick', '--json']) in (0, 2)
    assert main(['health', 'full', '--json']) in (0, 2)
    assert main(['health', 'explain', '--code', 'critical_check_failed:real_key_missing', '--json']) == 0

    assert main(['policy', 'show', '--json']) == 0
    assert main(['policy', 'validate', '--json']) in (0, 2)


def test_baseline_collect_writes_publish_grade_packet_and_resource_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = tmp_path / 'baseline_collect_packet.json'
    rc = main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'unit-window-001',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-collect'
    assert packet.get('profile') == 'normal'
    assert int(packet.get('sample_count', 0)) >= 2
    assert packet.get('provenance', {}).get('artifact_sha256')
    assert 'interpretation_policy_ref' not in packet
    assert 'authorization_boundary_ref' not in packet
    assert 'recommendation_profile' not in packet

    resource_state = log_dir / 'control' / 'calamum' / 'watchdog_resource_state.json'
    assert resource_state.exists()
    resource_doc = json.loads(resource_state.read_text(encoding='utf-8'))
    assert float(resource_doc.get('sample_count', 0)) >= 2
    assert resource_doc.get('stream_type') == 'resource_normal'


def test_baseline_collect_preserves_frame4_metadata_contract_on_samples_and_index_rows(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    normal_out = tmp_path / 'baseline_collect_normal_packet.json'
    baseline_out = tmp_path / 'baseline_collect_baseline_packet.json'

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'normal',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame4-normal-window',
        '--output', str(normal_out),
        '--json',
    ]) == 0

    assert main([
        'baseline', 'collect',
        '--source', 'sim',
        '--mode', 'canary',
        '--profile', 'baseline',
        '--duration-sec', '0.02',
        '--interval-sec', '0.01',
        '--window-id', 'frame4-baseline-window',
        '--output', str(baseline_out),
        '--json',
    ]) == 0

    normal_packet = json.loads(normal_out.read_text(encoding='utf-8'))
    baseline_packet = json.loads(baseline_out.read_text(encoding='utf-8'))

    normal_segment_path = Path(str((normal_packet.get('segments', [{}])[0] or {}).get('path', '')).replace('/', os.sep))
    baseline_segment_path = Path(str((baseline_packet.get('segments', [{}])[0] or {}).get('path', '')).replace('/', os.sep))
    normal_sample = _read_jsonl_rows(normal_segment_path)[0]
    baseline_sample = _read_jsonl_rows(baseline_segment_path)[0]

    resource_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'resource' / 'index.jsonl'
    normal_index = _latest_jsonl_row_for_stream(resource_index, 'resource_normal')
    baseline_index = _latest_jsonl_row_for_stream(resource_index, 'resource_baseline')

    for row in (normal_sample, normal_index, baseline_sample, baseline_index):
        assert row.get('sampling_profile_id')
        assert row.get('mode_at_capture') == 'canary'
        assert row.get('source_axis') == 'sim'
        assert row.get('stream_type') in ('resource_normal', 'resource_baseline')

    assert normal_sample.get('sampling_profile_id') == 'resource_normal_v1'
    assert normal_index.get('sampling_profile_id') == 'resource_normal_v1'
    assert baseline_sample.get('sampling_profile_id') == 'resource_baseline_v1'
    assert baseline_index.get('sampling_profile_id') == 'resource_baseline_v1'

    assert normal_sample.get('baseline_window_id') == 'frame4-normal-window'
    assert 'baseline_window_id' not in normal_index
    assert baseline_sample.get('baseline_window_id') == 'frame4-baseline-window'
    assert baseline_index.get('baseline_window_id') == 'frame4-baseline-window'


def test_baseline_analyze_returns_go_when_minimums_met(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    # Build one normal stream sample set and one rapid stream sample set.
    assert main([
        'baseline', 'collect',
        '--source', 'sim', '--mode', 'canary', '--profile', 'normal',
        '--duration-sec', '0.02', '--interval-sec', '0.01', '--window-id', 'unit-window-normal', '--json',
    ]) == 0
    assert main([
        'baseline', 'collect',
        '--source', 'sim', '--mode', 'canary', '--profile', 'baseline',
        '--duration-sec', '0.02', '--interval-sec', '0.01', '--window-id', 'unit-window-baseline', '--json',
    ]) == 0

    out = tmp_path / 'baseline_analysis_packet.json'
    rc = main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '24',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('action') == 'baseline-analyze'
    assert packet.get('baseline_ready') is True
    assert packet.get('decision') == 'go'
    stats = packet.get('resource_statistics', {})
    assert 'cpu_p95' in stats
    assert 'cpu_rate_p95_per_s' in stats
    assert packet.get('provenance', {}).get('artifact_sha256')
    assert 'recommendation_profile' not in packet
    assert 'policy_snapshot_ref' not in packet
    assert 'identity_assurance' not in packet
    assert 'human_impersonation_risk' not in packet


def test_baseline_analyze_no_go_when_window_incomplete(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    # Create only normal samples; require both normal+rapid to force a fail-closed no-go.
    assert main([
        'baseline', 'collect',
        '--source', 'sim', '--mode', 'canary', '--profile', 'normal',
        '--duration-sec', '0.02', '--interval-sec', '0.01', '--window-id', 'unit-window-only-normal', '--json',
    ]) == 0

    out = tmp_path / 'baseline_analysis_incomplete.json'
    rc = main([
        'baseline', 'analyze',
        '--source', 'sim',
        '--mode', 'canary',
        '--hours', '24',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
        '--output', str(out),
        '--json',
    ])
    assert rc == 2
    assert out.exists()
    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'no-go'
    assert 'critical_check_failed:resource_baseline_window_incomplete' in packet.get('reason_codes', [])
    assert 'recommendation_profile' not in packet


def test_baseline_overnight_plan_emits_publish_grade_schedule_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = tmp_path / 'overnight_plan_packet.json'
    rc = main([
        'baseline', 'overnight-plan',
        '--source', 'real',
        '--mode', 'canary',
        '--overnight-hours', '8',
        '--normal-interval-sec', '30',
        '--rapid-interval-sec', '2',
        '--rapid-phase-sec', '1800',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-overnight-plan'
    assert packet.get('schedule_model') == 'baseline_start_then_normal_overnight_then_baseline_end'
    assert packet.get('provenance', {}).get('artifact_sha256')
    cmds = packet.get('execution_commands', [])
    assert isinstance(cmds, list)
    assert len(cmds) == 4
    assert 'baseline collect' in cmds[0]
    assert 'profile baseline' in cmds[0]
    assert 'profile normal' in cmds[1]
    assert 'baseline analyze' in cmds[3]
    assert 'recommendation_profile' not in packet
    assert 'policy_snapshot_ref' not in packet
    assert 'identity_assurance' not in packet
    assert 'human_impersonation_risk' not in packet


def test_baseline_overnight_plan_flags_projection_when_thresholds_too_high(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main([
        'baseline', 'overnight-plan',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '1',
        '--normal-interval-sec', '60',
        '--rapid-interval-sec', '10',
        '--rapid-phase-sec', '300',
        '--min-normal-samples', '1000',
        '--min-rapid-samples', '1000',
        '--json',
    ])
    assert rc == 0

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl'
    assert evidence_index.exists()
    lines = [ln for ln in evidence_index.read_text(encoding='utf-8').splitlines() if ln.strip()]
    assert len(lines) >= 1
    latest = json.loads(lines[-1])
    plan_packet_path = Path(str(latest.get('packet_path', '')).replace('/', os.sep))
    assert plan_packet_path.exists()
    plan_packet = json.loads(plan_packet_path.read_text(encoding='utf-8'))

    projection = plan_packet.get('readiness_projection', {})
    assert projection.get('normal_requirement_met_by_plan') is False
    assert projection.get('rapid_requirement_met_by_plan') is False

def test_baseline_overnight_run_executes_all_phases_and_returns_go(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = tmp_path / 'overnight_run_packet.json'
    rc = main([
        'baseline', 'overnight-run',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '0.0006',
        '--normal-interval-sec', '0.05',
        '--rapid-interval-sec', '0.05',
        '--rapid-phase-sec', '0.5',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
        '--output', str(out),
        '--json',
    ])
    assert rc == 0
    assert out.exists()

    packet = json.loads(out.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'go'
    assert packet.get('action') == 'baseline-overnight-run'
    checkpoints = packet.get('checkpoints', [])
    assert isinstance(checkpoints, list)
    assert len(checkpoints) == 4
    phases = [cp.get('phase') for cp in checkpoints]
    assert phases == ['baseline_start', 'normal_overnight', 'baseline_end', 'analysis']
    assert all(str(cp.get('decision', 'no-go')) == 'go' for cp in checkpoints)
    assert packet.get('provenance', {}).get('artifact_sha256')


def test_baseline_overnight_run_fails_closed_when_analysis_not_ready(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main([
        'baseline', 'overnight-run',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '0.0006',
        '--normal-interval-sec', '0.05',
        '--rapid-interval-sec', '0.05',
        '--rapid-phase-sec', '0.5',
        '--min-normal-samples', '1000',
        '--min-rapid-samples', '1000',
        '--json',
    ])
    assert rc == 2

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl'
    assert evidence_index.exists()
    lines = [ln for ln in evidence_index.read_text(encoding='utf-8').splitlines() if ln.strip()]
    run_entries = [json.loads(ln) for ln in lines if 'baseline_overnight_run' in ln]
    assert len(run_entries) >= 1
    latest = run_entries[-1]
    packet_path = Path(str(latest.get('packet_path', '')).replace('/', os.sep))
    assert packet_path.exists()
    packet = json.loads(packet_path.read_text(encoding='utf-8'))
    assert packet.get('decision') == 'no-go'
    reasons = packet.get('reason_codes', [])
    assert any('resource_baseline_window_incomplete' in str(r) for r in reasons)


def test_baseline_overnight_run_emits_progress_lines_without_json(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main([
        'baseline', 'overnight-run',
        '--source', 'sim',
        '--mode', 'canary',
        '--overnight-hours', '0.0006',
        '--normal-interval-sec', '0.05',
        '--rapid-interval-sec', '0.05',
        '--rapid-phase-sec', '0.5',
        '--min-normal-samples', '1',
        '--min-rapid-samples', '1',
    ])
    assert rc == 0

    captured = capsys.readouterr()
    err = captured.err
    assert 'baseline overnight run started' in err
    assert 'phase_start baseline_start' in err
    assert 'phase_complete analysis decision=go baseline_ready=True' in err
    assert 'baseline overnight run completed decision=go' in err


def test_ops_mode_set_persists_lockdown_posture_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    gate_doc = {
        'decision': 'go',
        'timestamp_utc': observerctl_module._utc_now(),
        'from_state': 'sim:canary',
        'to_state': 'sim:live',
    }
    (control / 'observerctl_last_gate.json').write_text(json.dumps(gate_doc), encoding='utf-8')

    packet = observerctl_module._ops_mode_set(source='sim', to_mode='live')
    assert packet.get('decision') == 'go'
    posture_packet = packet.get('posture_packet', {})
    assert posture_packet.get('decision') == 'go'
    assert posture_packet.get('readback_verified') is True
    assert posture_packet.get('posture_trigger') == 'lockdown'
    assert float(posture_packet.get('heartbeat_interval_seconds', 0)) == 4.0
    assert float(posture_packet.get('baseline_validation_interval_seconds', 0)) == 45.0

    posture_state_path = Path(str(posture_packet.get('posture_state_path', '')).replace('/', os.sep))
    receipt_path = Path(str(posture_packet.get('receipt_path', '')).replace('/', os.sep))
    assert posture_state_path.exists()
    assert receipt_path.exists()

    posture_doc = json.loads((control / 'watchdog_posture_state.json').read_text(encoding='utf-8'))
    assert posture_doc.get('posture_trigger') == 'lockdown'
    assert float(posture_doc.get('heartbeat_interval_seconds', 0)) == 4.0
    assert float(posture_doc.get('baseline_validation_interval_seconds', 0)) == 45.0
    assert posture_doc.get('readback_verified') is False

    receipt_doc = json.loads(receipt_path.read_text(encoding='utf-8'))
    assert receipt_doc.get('decision') == 'go'
    assert receipt_doc.get('action') == 'posture-apply'
    assert receipt_doc.get('mode') == 'live'
    assert (receipt_doc.get('posture') or {}).get('readback_verified') is True
    assert (receipt_doc.get('provenance') or {}).get('artifact_sha256')


def test_ops_mode_set_rolls_back_state_when_posture_apply_fails(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    gate_doc = {
        'decision': 'go',
        'timestamp_utc': observerctl_module._utc_now(),
        'from_state': 'sim:canary',
        'to_state': 'sim:live',
    }
    (control / 'observerctl_last_gate.json').write_text(json.dumps(gate_doc), encoding='utf-8')

    monkeypatch.setattr(observerctl_module, '_apply_watchdog_posture', lambda source, mode, event='mode-set': {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': 'posture-apply',
        'source': source,
        'mode': mode,
        'reason_codes': ['critical_check_failed:watchdog_posture_persist_failed'],
        'readback_verified': False,
        'posture_state_path': str(control / 'watchdog_posture_state.json').replace('\\', '/'),
        'receipt_path': '',
    })

    packet = observerctl_module._ops_mode_set(source='sim', to_mode='live')
    assert packet.get('decision') == 'no-go'
    assert 'critical_check_failed:watchdog_posture_persist_failed' in packet.get('reason_codes', [])
    assert packet.get('attempted_to_state') == 'sim:live'
    assert packet.get('rollback_anchor') == {'source': 'sim', 'mode': 'canary'}
    assert packet.get('rollback_applied') is True
    assert packet.get('restored_state') == {'source': 'sim', 'mode': 'canary'}
    assert packet.get('restored_readback_state') == {'source': 'sim', 'mode': 'canary'}

    state = observerctl_module._load_state()
    assert state.get('source') == 'sim'
    assert state.get('mode') == 'canary'


def test_ops_mode_transition_surfaces_mode_set_rollback_failure(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    observerctl_module._save_state('sim', 'canary')
    monkeypatch.setattr(observerctl_module, 'evaluate_gate_decision', lambda status, target_mode='watch': {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'phase': 'gate',
        'reason_codes': [],
        'advisory_reason_codes': [],
        'source': 'sim',
        'from_state': 'sim:canary',
        'to_state': 'sim:live',
        'target_mode': target_mode,
    })
    monkeypatch.setattr(observerctl_module, '_apply_watchdog_posture', lambda source, mode, event='mode-set': {
        'timestamp_utc': observerctl_module._utc_now(),
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': 'posture-apply',
        'source': source,
        'mode': mode,
        'reason_codes': ['critical_check_failed:watchdog_posture_persist_failed'],
        'readback_verified': False,
        'posture_state_path': str(control / 'watchdog_posture_state.json').replace('\\', '/'),
        'receipt_path': '',
    })

    packet = observerctl_module._ops_mode_transition(source='sim', to_mode='live', event='unit-transition-rollback', output='')
    assert packet.get('decision') == 'no-go'
    assert 'critical_check_failed:watchdog_posture_persist_failed' in packet.get('reason_codes', [])
    assert (packet.get('gate_packet') or {}).get('decision') == 'go'
    mode_set_packet = packet.get('mode_set_packet') or {}
    assert mode_set_packet.get('decision') == 'no-go'
    assert mode_set_packet.get('rollback_applied') is True
    assert mode_set_packet.get('rollback_anchor') == {'source': 'sim', 'mode': 'canary'}
    assert any(str(ref).endswith('watchdog_posture_state.json') for ref in packet.get('evidence_refs', []))


def test_baseline_monitor_once_writes_state_and_normal_stream(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')

    rc = main([
        'baseline', 'monitor-once',
        '--source', 'sim',
        '--mode', 'canary',
        '--normal-interval-sec', '0.01',
        '--baseline-interval-sec', '45',
        '--baseline-window-sec', '0.2',
        '--baseline-sample-interval-sec', '0.05',
        '--min-normal-samples', '1',
        '--min-baseline-samples', '1',
        '--json',
    ])
    assert rc == 0

    monitor_state = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
    assert monitor_state.exists()
    monitor_doc = json.loads(monitor_state.read_text(encoding='utf-8'))
    assert monitor_doc.get('mode') == 'canary'
    assert monitor_doc.get('last_validation_cycle_event') == 'baseline_monitor_cycle'
    cycle_packet_path = Path(str(monitor_doc.get('last_validation_cycle_packet_path', '')).replace('/', os.sep))
    assert cycle_packet_path.exists()

    cycle_packet = json.loads(cycle_packet_path.read_text(encoding='utf-8'))
    assert cycle_packet.get('action') == 'baseline-monitor-cycle'
    assert cycle_packet.get('mode') == 'canary'
    assert cycle_packet.get('posture_trigger') == 'isolation'
    assert cycle_packet.get('baseline_window_id') == ''
    assert cycle_packet.get('normal_packet_path')
    assert cycle_packet.get('analysis_packet_path') == ''
    assert (cycle_packet.get('continuity') or {}).get('state') == 'fresh_start'

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'evidence' / 'index.jsonl'
    cycle_row = _latest_jsonl_row_for_event(evidence_index, 'baseline_monitor_cycle')
    assert cycle_row.get('decision') == 'go'
    assert Path(str(cycle_row.get('packet_path', '')).replace('/', os.sep)).exists()

    resource_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'canary' / 'resource' / 'index.jsonl'
    assert resource_index.exists()
    latest = json.loads([ln for ln in resource_index.read_text(encoding='utf-8').splitlines() if ln.strip()][-1])
    assert latest.get('stream_type') == 'resource_normal'


def test_baseline_monitor_once_lockdown_cycle_emits_append_only_validation_record_with_baseline_linkage(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'live')

    packet = observerctl_module._baseline_monitor_once(
        source='sim',
        mode='live',
        normal_interval_sec=0.01,
        baseline_interval_sec=0.01,
        baseline_window_sec=0.2,
        baseline_sample_interval_sec=0.05,
        min_normal_samples=1,
        min_baseline_samples=1,
    )

    assert packet.get('decision') == 'go'
    assert packet.get('validation_cycle_event') == 'baseline_monitor_cycle'

    cycle_packet_path = Path(str(packet.get('validation_cycle_packet_path', '')).replace('/', os.sep))
    assert cycle_packet_path.exists()

    cycle_packet = json.loads(cycle_packet_path.read_text(encoding='utf-8'))
    assert cycle_packet.get('action') == 'baseline-monitor-cycle'
    assert cycle_packet.get('mode') == 'live'
    assert cycle_packet.get('posture_trigger') == 'lockdown'
    assert cycle_packet.get('baseline_window_id')
    assert cycle_packet.get('baseline_packet_path')
    assert cycle_packet.get('analysis_packet_path')
    assert cycle_packet.get('monitor_state_path').endswith('baseline_monitor_state.json')
    assert (cycle_packet.get('continuity') or {}).get('state') == 'fresh_start'

    evidence_index = log_dir / 'data' / 'calamum' / 'observer_derived' / 'sim' / 'live' / 'evidence' / 'index.jsonl'
    cycle_row = _latest_jsonl_row_for_event(evidence_index, 'baseline_monitor_cycle')
    assert cycle_row.get('decision') == 'go'
    assert Path(str(cycle_row.get('packet_path', '')).replace('/', os.sep)).exists()

    monitor_state = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
    monitor_doc = json.loads(monitor_state.read_text(encoding='utf-8'))
    assert monitor_doc.get('last_validation_cycle_event') == 'baseline_monitor_cycle'
    assert monitor_doc.get('last_validation_cycle_decision') == 'go'
    assert monitor_doc.get('last_validation_cycle_packet_path') == str(cycle_packet_path).replace('\\', '/')
    assert monitor_doc.get('last_baseline_window_id') == cycle_packet.get('baseline_window_id')


def test_baseline_monitor_once_preserves_restart_continuity_anchors_between_cycles(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'live')

    observerctl_module._baseline_monitor_once(
        source='sim',
        mode='live',
        normal_interval_sec=0.01,
        baseline_interval_sec=0.01,
        baseline_window_sec=0.2,
        baseline_sample_interval_sec=0.05,
        min_normal_samples=1,
        min_baseline_samples=1,
    )

    monitor_state_path = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
    first_monitor_doc = json.loads(monitor_state_path.read_text(encoding='utf-8'))
    first_cycle_path = str(first_monitor_doc.get('last_validation_cycle_packet_path', '') or '')
    first_baseline_packet_path = str(first_monitor_doc.get('last_baseline_packet_path', '') or '')
    first_analysis_packet_path = str(first_monitor_doc.get('last_analysis_packet_path', '') or '')
    first_baseline_window_id = str(first_monitor_doc.get('last_baseline_window_id', '') or '')

    second_packet = observerctl_module._baseline_monitor_once(
        source='sim',
        mode='live',
        normal_interval_sec=999.0,
        baseline_interval_sec=999.0,
        baseline_window_sec=0.2,
        baseline_sample_interval_sec=0.05,
        min_normal_samples=1,
        min_baseline_samples=1,
    )

    second_cycle_path = str(second_packet.get('validation_cycle_packet_path', '') or '')
    assert second_cycle_path
    assert second_cycle_path != first_cycle_path

    second_cycle_doc = json.loads(Path(second_cycle_path.replace('/', os.sep)).read_text(encoding='utf-8'))
    continuity = second_cycle_doc.get('continuity') or {}
    assert continuity.get('state') == 'preserved'
    assert (continuity.get('previous_validation_cycle') or {}).get('packet_path') == first_cycle_path
    assert (continuity.get('previous_baseline') or {}).get('packet_path') == first_baseline_packet_path
    assert (continuity.get('previous_baseline') or {}).get('window_id') == first_baseline_window_id
    assert continuity.get('previous_analysis_packet_path') == first_analysis_packet_path
    assert second_cycle_doc.get('baseline_packet_path') == ''
    assert second_cycle_doc.get('analysis_packet_path') == ''
    assert first_cycle_path in ((second_cycle_doc.get('process') or {}).get('evidence_refs') or [])

    second_monitor_doc = json.loads(monitor_state_path.read_text(encoding='utf-8'))
    assert second_monitor_doc.get('last_baseline_packet_path') == first_baseline_packet_path
    assert second_monitor_doc.get('last_analysis_packet_path') == first_analysis_packet_path
    assert second_monitor_doc.get('last_baseline_window_id') == first_baseline_window_id


def test_baseline_monitor_once_degrades_explicitly_when_persisted_state_is_malformed(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')

    malformed_state_path = log_dir / 'control' / 'calamum' / 'baseline_monitor_state.json'
    malformed_state_path.write_text(json.dumps({
        'last_normal_sample_epoch_s': 'not-a-float',
        'last_validation_cycle_packet_path': 123,
        'last_validation_cycle_at_utc': 'definitely-not-utc',
        'last_baseline_packet_path': 456,
    }), encoding='utf-8')

    packet = observerctl_module._baseline_monitor_once(
        source='sim',
        mode='canary',
        normal_interval_sec=0.01,
        baseline_interval_sec=45.0,
        baseline_window_sec=0.2,
        baseline_sample_interval_sec=0.05,
        min_normal_samples=1,
        min_baseline_samples=1,
    )

    cycle_packet_path = Path(str(packet.get('validation_cycle_packet_path', '')).replace('/', os.sep))
    cycle_packet = json.loads(cycle_packet_path.read_text(encoding='utf-8'))
    continuity = cycle_packet.get('continuity') or {}
    assert continuity.get('state') == 'degraded'
    assert 'major_check_failed:baseline_monitor_state_malformed' in (continuity.get('reason_codes') or [])
    assert (continuity.get('detail_codes') or [])
    assert (continuity.get('previous_validation_cycle') or {}).get('packet_path') == '123'

    repaired_state = json.loads(malformed_state_path.read_text(encoding='utf-8'))
    assert repaired_state.get('last_normal_sample_epoch_s') != 'not-a-float'
    assert repaired_state.get('last_baseline_packet_path') == '456'


def test_non_activation_live_projection_can_prove_c22_from_projected_lockdown_defaults(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    pid_path = tmp_path / 'calamum_agent.pid'
    pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monitor_pid_path = tmp_path / 'calamum_baseline_monitor.pid'
    monitor_pid_path.write_text(str(os.getpid()), encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_agent_pid_path', lambda: pid_path)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_pid_path', lambda: monitor_pid_path)

    monitor_state = control / 'baseline_monitor_state.json'
    monitor_state.write_text(json.dumps({'mode': 'canary', 'posture_trigger': 'isolation'}), encoding='utf-8')

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    segment_path = archive_dir / 'resource_sim_canary_normal_projection_seg0001.jsonl'
    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_projection_seg0001.jsonl'
    segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z","baseline_window_id":"frame8-monitor-window"}\n', encoding='utf-8')
    (resource_dir / 'index.jsonl').write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_normal',
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_baseline',
            'baseline_window_id': 'frame8-monitor-window',
            'window_id': 'frame8-monitor-window',
        }) + '\n',
        encoding='utf-8',
    )

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_projection_test.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'baseline_window_id': 'frame8-monitor-window',
        'sample_counts': {'resource_normal': 1, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    output = tmp_path / 'evidence_live_projection_from_monitor.json'
    rc_pack = main([
        'ops', 'evidence', 'pack',
        '--source', 'sim',
        '--to', 'live',
        '--event', 'unit-live-proof-from-monitor',
        '--output', str(output),
        '--json',
    ])
    assert rc_pack == 0

    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['readiness_projection']['projection_mode'] == 'non-activation'
    assert payload['stage5_prerequisites']['C22_baseline_validation_rate_escalated']['status'] == 'ok'
    assert payload['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['C25_resource_baseline_window_ready']['status'] == 'ok'
    assert payload['stage5_prerequisites']['overall']['status'] == 'ok'


def test_baseline_generate_and_check_filesystem_hashes(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('hello baseline\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    rc_generate = main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json'])
    assert rc_generate == 0
    assert baseline_path.exists()

    rc_check = main(['baseline', 'check', '--baseline', str(baseline_path), '--json'])
    assert rc_check == 0


def test_baseline_check_detects_hash_mismatch(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('v1\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    assert main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json']) == 0

    tracked.write_text('v2\n', encoding='utf-8')
    rc_check = main(['baseline', 'check', '--baseline', str(baseline_path), '--json'])
    assert rc_check == 2


def test_baseline_check_ignores_local_untracked_runtime_state(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    for d in [log_dir / 'health', log_dir / 'data' / 'calamum', log_dir / 'control' / 'calamum']:
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    tracked = tmp_path / 'tracked.txt'
    tracked.write_text('stable\n', encoding='utf-8')

    runtime_state = tmp_path / 'local_untracked' / 'scheduler' / 'watchdog_schedule_state.json'
    runtime_state.parent.mkdir(parents=True, exist_ok=True)
    runtime_state.write_text('{"tick":1}\n', encoding='utf-8')

    baseline_path = tmp_path / 'fs_baseline.json'
    assert main(['baseline', 'generate', '--output', str(baseline_path), '--max-files', '1000', '--json']) == 0

    # Runtime state mutates between baseline/check cycles; baseline should ignore it.
    runtime_state.write_text('{"tick":2}\n', encoding='utf-8')
    rc_check = main(['baseline', 'check', '--baseline', str(baseline_path), '--json'])
    assert rc_check == 0


def test_librarian_rotate_compact_verify_operational(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'watch'
    store.mkdir(parents=True, exist_ok=True)

    active = store / 'active.jsonl'
    active.write_text('{"x":1}\n{"x":2}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')

    control = log_dir / 'control' / 'calamum'
    control.mkdir(parents=True, exist_ok=True)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    assert main(['librarian', 'rotate', '--mode', 'watch', '--json']) == 0

    manifest_path = store / 'manifest.json'
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert isinstance(manifest.get('archives'), list)

    # Create another segment then compact archives.
    active.write_text('{"x":3}\n', encoding='utf-8')
    assert main(['librarian', 'rotate', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'compact', '--mode', 'watch', '--json']) == 0
    assert main(['librarian', 'verify', '--mode', 'watch', '--json']) == 0

    manifest_after = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest_after.get('archives') == []
    assert len(manifest_after.get('compacted_files', [])) >= 1

    # Ensure former marker-stub artifacts are not used.
    assert list(store.glob('*.marker')) == []


def test_librarian_stats_reports_archive_manifest_by_mode(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'canary'
    archive_dir = data / 'archive'

    store.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Session-active records in the store pointer.
    active = store / 'active.jsonl'
    active.write_text('{"x":1}\n{"x":2}\n', encoding='utf-8')

    # Archive manifest bundles (compressed artifacts + metadata) by mode.
    bundle_file = archive_dir / 'moltbook_canary_20260222T000000.jsonl.gz'
    bundle_file.write_text('compressed-bytes-placeholder', encoding='utf-8')
    manifest_payload = {
        'moltbook_canary_20260222T000000.jsonl': {
            'artifact_path': bundle_file.name,
            'records': 123,
            'uncompressed_bytes': 4567,
        }
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest_payload), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    stats = observerctl_module._librarian_stats()
    assert stats.get('runtime_cli_surface') == 'observerctl'

    summary = stats.get('archive_manifest_summary', {})
    assert summary.get('manifest_exists') is True
    assert (summary.get('totals') or {}).get('records') == 123

    stores = stats.get('stores', [])
    canary_row = next((row for row in stores if row.get('mode') == 'canary'), None)
    assert canary_row is not None
    assert canary_row.get('session_records') == 2
    assert canary_row.get('archive_bundle_count') == 1
    assert canary_row.get('archive_records') == 123
    assert canary_row.get('records_total_display') == 125


def test_librarian_stats_human_output_without_json_flag(tmp_path: Path, monkeypatch, capsys) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'canary'
    archive_dir = data / 'archive'

    store.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    (store / 'active.jsonl').write_text('{"x":1}\n', encoding='utf-8')
    bundle_file = archive_dir / 'moltbook_canary_20260222T010000.jsonl.gz'
    bundle_file.write_text('x', encoding='utf-8')
    manifest_payload = {
        'moltbook_canary_20260222T010000.jsonl': {
            'artifact_path': bundle_file.name,
            'records': 7,
            'uncompressed_bytes': 77,
        }
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest_payload), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main(['librarian', 'stats'])
    assert rc == 0

    out = capsys.readouterr().out
    assert 'Librarian stats' in out
    assert 'archive_totals:' in out
    assert 'per_mode:' in out
    assert '- CANARY' in out
    assert 'session_records_display:' in out


def test_librarian_stats_prefers_derived_session_display_counts(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    store = data / 'stores' / 'canary'
    archive_dir = data / 'archive'
    derived_canary = data / 'observer_derived' / 'sim' / 'canary'

    store.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    derived_canary.mkdir(parents=True, exist_ok=True)

    # Empty store pointer but populated derived ingest lane.
    (store / 'active.jsonl').write_text('', encoding='utf-8')
    (derived_canary / 'moltbook_metrics.jsonl').write_text('{"x":1}\n{"x":2}\n{"x":3}\n', encoding='utf-8')

    bundle_file = archive_dir / 'moltbook_canary_20260222T010000.jsonl.gz'
    bundle_file.write_text('x', encoding='utf-8')
    manifest_payload = {
        'moltbook_canary_20260222T010000.jsonl': {
            'artifact_path': bundle_file.name,
            'records': 7,
            'uncompressed_bytes': 77,
        }
    }
    (archive_dir / 'manifest.json').write_text(json.dumps(manifest_payload), encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('sim', 'canary')

    stats = observerctl_module._librarian_stats()
    stores = stats.get('stores', [])
    canary_row = next((row for row in stores if row.get('mode') == 'canary'), None)
    assert canary_row is not None
    assert canary_row.get('session_records') == 0
    assert canary_row.get('ingest_session_records') == 3
    assert canary_row.get('session_records_display') == 3
    assert canary_row.get('records_total_display') == 10


def test_librarian_stats_ignores_non_active_lane_derived_sessions(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    archive_dir = data / 'archive'
    derived_sim_live = data / 'observer_derived' / 'sim' / 'live'
    derived_real_canary = data / 'observer_derived' / 'real' / 'canary'

    archive_dir.mkdir(parents=True, exist_ok=True)
    derived_sim_live.mkdir(parents=True, exist_ok=True)
    derived_real_canary.mkdir(parents=True, exist_ok=True)

    (derived_sim_live / 'moltbook_metrics.jsonl').write_text('{"x":1}\n{"x":2}\n{"x":3}\n', encoding='utf-8')
    (derived_real_canary / 'moltbook_metrics.jsonl').write_text('{"x":10}\n{"x":11}\n', encoding='utf-8')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    observerctl_module._save_state('real', 'canary')

    stats = observerctl_module._librarian_stats()
    stores = stats.get('stores', [])
    live_row = next((row for row in stores if row.get('mode') == 'live'), None)
    canary_row = next((row for row in stores if row.get('mode') == 'canary'), None)

    assert live_row is not None
    assert canary_row is not None

    assert live_row.get('ingest_mode_active') is False
    assert live_row.get('ingest_session_records') == 0
    assert live_row.get('session_records_display') == 0

    assert canary_row.get('ingest_mode_active') is True
    assert canary_row.get('ingest_source_scope') == 'real'
    assert canary_row.get('ingest_session_records') == 2
    assert canary_row.get('session_records_display') == 2


def test_gate_denies_when_security_report_link_missing(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.delenv('CALAMUM_SECURITY_REPORT_REF', raising=False)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:run_security_report_missing' in gate['reason_codes']


def test_gate_denies_when_security_report_link_unresolvable(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.setenv('CALAMUM_SECURITY_REPORT_REF', str(log_dir / 'missing_security_report.md'))
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='canary')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:run_security_report_missing' in gate['reason_codes']


def test_live_gate_denies_when_baseline_monitor_runtime_inactive_but_surfaces_retained_evidence(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    resource_dir = data / 'observer_derived' / 'sim' / 'canary' / 'resource'
    evidence_dir = data / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    archive_dir = data / 'archive'
    resource_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    segment_path = archive_dir / 'resource_sim_canary_normal_frame9_gate_seg0001.jsonl'
    baseline_segment_path = archive_dir / 'resource_sim_canary_baseline_frame9_gate_seg0001.jsonl'
    segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z"}\n', encoding='utf-8')
    baseline_segment_path.write_text('{"timestamp_utc":"2026-03-22T00:00:00Z","baseline_window_id":"frame9-gate-window"}\n', encoding='utf-8')
    (resource_dir / 'index.jsonl').write_text(
        json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_normal',
        }) + '\n' + json.dumps({
            'timestamp_utc': observerctl_module._utc_now(),
            'segment_path': str(baseline_segment_path).replace('\\', '/'),
            'segment_records': 1,
            'stream_type': 'resource_baseline',
            'baseline_window_id': 'frame9-gate-window',
            'window_id': 'frame9-gate-window',
        }) + '\n',
        encoding='utf-8',
    )

    baseline_packet_path = evidence_dir / 'observerctl_baseline-analysis_frame9_gate.json'
    baseline_packet_path.write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'decision': 'go',
        'baseline_window_id': 'frame9-gate-window',
        'sample_counts': {'resource_normal': 2, 'resource_baseline': 1},
        'provenance': {'artifact_path': str(baseline_packet_path).replace('\\', '/')},
    }), encoding='utf-8')
    (evidence_dir / 'index.jsonl').write_text(json.dumps({
        'timestamp_utc': observerctl_module._utc_now(),
        'event': 'baseline_analysis',
        'packet_path': str(baseline_packet_path).replace('\\', '/'),
    }) + '\n', encoding='utf-8')

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='live')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:baseline_monitor_runtime_inactive' in gate['reason_codes']
    assert gate['stage5_prerequisites']['C24_resource_stream_retention_ready']['status'] == 'ok'
    assert gate['stage5_prerequisites']['C25_resource_baseline_window_ready']['status'] == 'ok'
    assert gate['stage5_prerequisites']['baseline_monitor_runtime_ready']['status'] == 'err'
    assert any(str(ref).endswith('watchdog_posture_state.json') for ref in gate['evidence_refs'])
    assert any(str(ref).endswith('resource/index.jsonl') for ref in gate['evidence_refs'])
    assert any(str(ref).endswith('observerctl_baseline-analysis_frame9_gate.json') for ref in gate['evidence_refs'])


def test_live_gate_reason_codes_follow_deterministic_activation_order(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)

    observerctl_module._save_state('sim', 'canary')
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=45, ram_now=50, cpu_p95=40, ram_p95=45, score=0.1, age_s=3)

    status = collect_runtime_status(source='sim')
    gate = evaluate_gate_decision(status, target_mode='live')
    assert gate['decision'] == 'no-go'
    assert gate['reason_codes'] == [
        'critical_check_failed:lockdown_heartbeat_rate_not_escalated',
        'critical_check_failed:lockdown_baseline_rate_not_escalated',
        'critical_check_failed:baseline_monitor_runtime_inactive',
        'critical_check_failed:resource_stream_retention_unavailable',
        'critical_check_failed:resource_baseline_window_incomplete',
    ]


def test_live_lockdown_requires_escalated_cadence(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'test-key')

    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)
    status = collect_runtime_status(source='real')
    gate = evaluate_gate_decision(status, target_mode='live')
    assert gate['decision'] == 'no-go'
    assert 'critical_check_failed:lockdown_heartbeat_rate_not_escalated' in gate['reason_codes']
    assert 'critical_check_failed:lockdown_baseline_rate_not_escalated' in gate['reason_codes']


def test_lockdown_cpu_spike_denies_live_and_honeypot_same_standard(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    monkeypatch.setenv('MOLTBOOK_API_KEY', 'test-key')

    # Cadence escalated correctly for lockdown; denial should come from spike standard.
    _write_watchdog_posture(control, posture='lockdown', heartbeat_interval=4, baseline_interval=45)
    _write_watchdog_resource(control, cpu_now=80, ram_now=70, cpu_p95=50, ram_p95=55, score=0.6, age_s=3)

    live_status = collect_runtime_status(source='real')
    live_gate = evaluate_gate_decision(live_status, target_mode='live')
    honeypot_gate = evaluate_gate_decision(live_status, target_mode='honeypot')

    assert live_gate['decision'] == 'no-go'
    assert honeypot_gate['decision'] == 'no-go'
    assert 'critical_check_failed:cpu_spike_lockdown' in live_gate['reason_codes']
    assert 'critical_check_failed:cpu_spike_lockdown' in honeypot_gate['reason_codes']


def test_ops_mode_set_denies_stale_gate_packet(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    monkeypatch.setenv('CALAMUM_GATE_PACKET_MAX_AGE_SEC', '1')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    assert main(['ops', 'mode', 'gate', '--to', 'canary', '--source', 'sim', '--json']) == 0

    gate_path = control / 'observerctl_last_gate.json'
    gate_doc = json.loads(gate_path.read_text(encoding='utf-8'))
    gate_doc['timestamp_utc'] = '2000-01-01T00:00:00Z'
    gate_path.write_text(json.dumps(gate_doc), encoding='utf-8')

    assert main(['ops', 'mode', 'set', '--to', 'canary', '--source', 'sim', '--json']) == 2


def test_default_evidence_paths_use_canonical_data_cache(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data_dir = log_dir / 'data' / 'calamum'
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    out = _default_output_path(source='sim', mode='canary', event='unit-test')
    idx = _evidence_index_path(source='sim', mode='canary')

    expected_dir = data_dir / 'observer_derived' / 'sim' / 'canary' / 'evidence'
    assert out.parent == expected_dir
    assert out.name.startswith('observerctl_unit-test_evidence_')
    assert out.suffix == '.json'
    assert idx == expected_dir / 'index.jsonl'


def test_ops_runtime_stop_writes_kill_signal(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control_dir = log_dir / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    rc = main(['ops', 'runtime', 'stop', '--json'])
    assert rc == 0

    signal_path = control_dir / 'kill.signal.json'
    assert signal_path.exists()
    payload = json.loads(signal_path.read_text(encoding='utf-8'))
    assert payload.get('signal') == 'kill'
    assert payload.get('requested_by') == 'observerctl'


def test_ops_runtime_stop_cleans_stale_pidfile(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control_dir = log_dir / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    pid_file = tmp_path / 'calamum_agent.pid'
    pid_file.write_text('424242', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_pid_alive', lambda _pid: False)

    packet = observerctl_module._ops_runtime_stop(timeout_sec=0.0)
    assert packet['decision'] == 'go'
    assert packet['stopped_cleanly'] is True
    assert packet['escalated_terminate'] is False
    assert not pid_file.exists()


def test_ops_runtime_stop_escalates_when_process_persists(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    control_dir = log_dir / 'control' / 'calamum'
    control_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    pid_file = tmp_path / 'calamum_agent.pid'
    pid_file.write_text('424242', encoding='utf-8')

    calls = {'pid_alive': 0, 'terminate': 0}

    def _fake_pid_alive(_pid):
        calls['pid_alive'] += 1
        # Alive during initial check(s), then false after terminate path has run.
        if calls['terminate'] == 0:
            return True
        return False

    def _fake_terminate(_pid, graceful_timeout_sec=2.0):
        calls['terminate'] += 1
        return True

    monkeypatch.setattr(observerctl_module, '_pid_alive', _fake_pid_alive)
    monkeypatch.setattr(observerctl_module, '_terminate_pid_best_effort', _fake_terminate)

    packet = observerctl_module._ops_runtime_stop(timeout_sec=0.0)
    assert packet['decision'] == 'go'
    assert packet['stopped_cleanly'] is True
    assert packet['escalated_terminate'] is True
    assert calls['terminate'] == 1


def test_ops_runtime_status_reports_active_when_heartbeat_and_pid_alive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    _touch(health / 'calamum_observer.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)
    (tmp_path / 'calamum_agent.pid').write_text(str(os.getpid()), encoding='utf-8')

    packet = observerctl_module._ops_runtime_status()
    assert packet['state'] == 'active'
    assert packet['heartbeat']['status'] == 'ok'
    assert packet['pid']['alive'] is True


def test_librarian_status_reports_active_when_heartbeat_and_pid_alive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)
    (tmp_path / 'calamum_librarian.pid').write_text(str(os.getpid()), encoding='utf-8')

    packet = observerctl_module._librarian_status()
    assert packet['decision'] == 'go'
    assert packet['state'] == 'active'
    assert packet['heartbeat']['status'] == 'ok'
    assert packet['pid']['alive'] is True


def test_librarian_check_go_when_runtime_active_and_store_ok(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    data = log_dir / 'data' / 'calamum'
    health = log_dir / 'health'
    for d in [data, health]:
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_runtime_librarian_status', lambda max_age_sec=120.0: {
        'state': 'active',
        'heartbeat': {'status': 'ok'},
        'pid': {'value': 123, 'alive': True},
    })

    rc = main(['librarian', 'check', '--mode', 'watch', '--json'])
    assert rc == 0


def test_librarian_restart_starts_process_and_reports_go(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    (log_dir / 'health').mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    src_dir = tmp_path / 'src'
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / 'calamum_librarian.py').write_text('print("ok")\n', encoding='utf-8')

    class _DummyProc:
        pid = 12345

    monkeypatch.setattr(observerctl_module.subprocess, 'Popen', lambda *args, **kwargs: _DummyProc())

    states = [
        {'state': 'degraded', 'heartbeat': {'status': 'warn'}, 'pid': {'value': 12345, 'alive': True}},
        {'state': 'active', 'heartbeat': {'status': 'ok'}, 'pid': {'value': 12345, 'alive': True}},
    ]

    def _fake_status(max_age_sec=120.0):
        if len(states) > 1:
            return states.pop(0)
        return states[0]

    monkeypatch.setattr(observerctl_module, '_runtime_librarian_status', _fake_status)

    packet = observerctl_module._librarian_restart(timeout_sec=0.0, startup_probe_sec=0.2)
    assert packet['decision'] == 'go'
    assert int(packet['new_pid']) == 12345


def test_pid_alive_uses_psutil_when_os_kill_unreliable(monkeypatch) -> None:
    class _FakeProc:
        def is_running(self):
            return True

        def status(self):
            return 'running'

    monkeypatch.setattr(observerctl_module.psutil, 'Process', lambda _pid: _FakeProc())
    monkeypatch.setattr(observerctl_module.os, 'kill', lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError('unsupported')))

    assert observerctl_module._pid_alive(4242) is True


def test_ops_runtime_start_delegates_launcher_non_interactive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    launcher = tmp_path / 'launch_ghost_console.ps1'
    launcher.write_text('# test launcher\n', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    class _DummyProc:
        pid = 12345

    def _fake_popen(cmd, env, cwd, stdin, stdout, stderr, creationflags):
        (tmp_path / 'calamum_agent.pid').write_text(str(os.getpid()), encoding='utf-8')
        _touch(health / 'calamum_observer.heartbeat')
        return _DummyProc()

    monkeypatch.setattr(observerctl_module.subprocess, 'Popen', _fake_popen)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_start', lambda **kwargs: {
        'timestamp_utc': '2026-01-01T00:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'baseline-monitor-start',
        'reason_codes': [],
        'state': 'active',
        'pid': {'value': 2468, 'alive': True},
        'startup_verified': True,
    })

    rc = main([
        'ops', 'runtime', 'start',
        '--source', 'sim',
        '--mode', 'canary',
        '--interval-sec', '1.0',
        '--timeout-sec', '2',
        '--json',
    ])
    assert rc == 0


def test_ops_runtime_start_fails_closed_when_monitor_start_fails(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    health.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))

    launcher = tmp_path / 'launch_ghost_console.ps1'
    launcher.write_text('# test launcher\n', encoding='utf-8')
    monkeypatch.setattr(observerctl_module, '_project_root', lambda: tmp_path)

    class _DummyProc:
        pid = 12345

    def _fake_popen(cmd, env, cwd, stdin, stdout, stderr, creationflags):
        (tmp_path / 'calamum_agent.pid').write_text(str(os.getpid()), encoding='utf-8')
        _touch(health / 'calamum_observer.heartbeat')
        return _DummyProc()

    monkeypatch.setattr(observerctl_module.subprocess, 'Popen', _fake_popen)
    monkeypatch.setattr(observerctl_module, '_baseline_monitor_start', lambda **kwargs: {
        'timestamp_utc': '2026-01-01T00:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'no-go',
        'action': 'baseline-monitor-start',
        'reason_codes': ['critical_check_failed:baseline_monitor_startup_unverified'],
        'state': 'stopped',
        'pid': {'value': None, 'alive': False},
        'startup_verified': False,
    })

    rc = main([
        'ops', 'runtime', 'start',
        '--source', 'sim',
        '--mode', 'canary',
        '--interval-sec', '1.0',
        '--timeout-sec', '2',
        '--json',
    ])
    assert rc == 2


def test_ops_mode_switch_fails_when_postflight_monitor_inactive(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path / 'logs'
    health = log_dir / 'health'
    data = log_dir / 'data' / 'calamum'
    control = log_dir / 'control' / 'calamum'

    for d in [health, data, control]:
        d.mkdir(parents=True, exist_ok=True)

    _touch(health / 'calamum_ops_watchdog.heartbeat')
    _touch(health / 'calamum_observer.heartbeat')
    _touch(health / 'calamum_librarian.heartbeat')

    monkeypatch.setenv('CALAMUM_LOG_DIR', str(log_dir))
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-signing-key')
    _set_security_report_ref(monkeypatch, log_dir)
    _write_watchdog_posture(control, posture='isolation', heartbeat_interval=10, baseline_interval=120)
    _write_watchdog_resource(control, cpu_now=55, ram_now=60, cpu_p95=50, ram_p95=55, score=0.2, age_s=5)

    observerctl_module._save_state('sim', 'watch')

    monkeypatch.setattr(
        observerctl_module,
        '_runtime_observer_status',
        lambda max_age_sec=60.0: {
            'state': 'active',
            'heartbeat': {'status': 'ok'},
            'pid': {'value': 1111, 'alive': True},
            'pending_stop_signal': False,
        },
    )
    monkeypatch.setattr(observerctl_module, '_ops_runtime_status', lambda: {
        'state': 'active',
        'heartbeat': {'status': 'ok'},
        'pid': {'value': 1111, 'alive': True},
        'pending_stop_signal': False,
    })
    monkeypatch.setattr(observerctl_module, '_ops_runtime_stop', lambda timeout_sec=8.0: {
        'timestamp_utc': '2026-01-01T00:00:00Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'runtime-stop',
        'reason_codes': [],
    })
    monkeypatch.setattr(observerctl_module, '_ops_runtime_start', lambda source, mode, interval_sec, timeout_sec: {
        'timestamp_utc': '2026-01-01T00:00:01Z',
        'runtime_cli_surface': 'observerctl',
        'decision': 'go',
        'action': 'runtime-start',
        'reason_codes': [],
        'startup_verified': True,
        'state': 'active',
        'pid': {'value': 5678, 'alive': True},
    })
    monkeypatch.setattr(
        observerctl_module,
        '_runtime_baseline_monitor_status',
        lambda max_age_sec=90.0: {
            'state': 'stopped',
            'heartbeat': {'status': 'err'},
            'pid': {'value': None, 'alive': False},
            'monitor_state': {},
        },
    )

    rc = main(['ops', 'mode', 'switch', '--to', 'canary', '--json'])
    assert rc == 2
