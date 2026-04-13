from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from obfuscator_lib import Obfuscator

from analysis.dataset_builder import build_dataset
from analysis.evaluation_harness import EvalResult, evaluate, write_run_artifacts
from analysis.tv_review import apply_suggested_labels_to_dataset_manifest, run_tv_review
from analysis.validate_jsonl import validate_jsonl_file


@pytest.fixture(autouse=True)
def _set_signing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('CALAMUM_DATA_SIGNING_KEY', 'unit-test-key')


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r) + '\n')


def test_validate_jsonl_passes_signed_records(tmp_path: Path) -> None:
    rec = {
        'timestamp': '2026-02-10T00:00:00Z',
        'type': 'post',
        'author_hash': 'abcd' * 4,
        'content_length': 12,
        'has_code_block': False,
        'tags_count': 0,
        'mentions_count': 0,
        'f_complexity': 0.2,
        'f_code_density': 0.0,
        'f_toxicity': 0,
        'f_timestamp_epoch': 0.0,
    }
    signed = Obfuscator.sign_record(rec)
    p = tmp_path / 'input.jsonl'
    _write_jsonl(p, [signed])

    summary, errors = validate_jsonl_file(p, verify_signatures=True)
    assert summary.error_lines == 0
    assert errors == []
    assert summary.signature_present == 1
    assert summary.signature_verified == 1


def test_validate_jsonl_blocks_forbidden_payload_keys(tmp_path: Path) -> None:
    rec = {
        'timestamp': '2026-02-10T00:00:00Z',
        'type': 'post',
        'content': 'raw semantic payload is not allowed',
    }
    p = tmp_path / 'bad.jsonl'
    _write_jsonl(p, [rec])

    summary, errors = validate_jsonl_file(p)
    assert summary.error_lines == 1
    assert any('forbidden_raw_payload_key' in e for e in errors)


def test_run_demo_default_root_uses_local_untracked_analysis_spine() -> None:
    from analysis._util import default_analysis_dir
    from analysis.run_demo import _default_demo_root

    root = _default_demo_root()

    assert root.is_absolute()
    assert root.parent == default_analysis_dir(Path(__file__)) / 'runs' / 'demo'
    assert root != default_analysis_dir(Path(__file__)).parent / 'demo_output'
    assert root.name != 'demo_output'


def test_build_dataset_deterministic_splits_and_eval(tmp_path: Path) -> None:
    # Create a small labeled synthetic dataset (tv_id) and sign it.
    records = []
    for i in range(8):
        r = {
            'timestamp': f'2026-02-10T00:00:{i:02d}Z',
            'type': 'post',
            'author_hash': f'{i:016d}',
            'content_length': 10,
            'has_code_block': False,
            'tags_count': 0,
            'mentions_count': 0,
            'f_complexity': 0.1,
            'f_code_density': 0.0,
            'f_toxicity': 0,
            'f_timestamp_epoch': float(i),
            'tv_id': 'TV-0',
        }
        records.append(Obfuscator.sign_record(r))

    for i in range(2):
        r = {
            'timestamp': f'2026-02-10T00:01:{i:02d}Z',
            'type': 'post',
            'author_hash': f'tv3{i:014d}',
            'content_length': 50,
            'has_code_block': True,
            'tags_count': 1,
            'mentions_count': 1,
            'f_complexity': 0.8,
            'f_code_density': 0.2,
            'f_toxicity': 2,
            'f_timestamp_epoch': float(100 + i),
            'tv_id': 'TV-3',
        }
        records.append(Obfuscator.sign_record(r))

    jsonl = tmp_path / 'synthetic.jsonl'
    _write_jsonl(jsonl, records)

    out1 = tmp_path / 'out1'
    out2 = tmp_path / 'out2'

    m1 = build_dataset([jsonl], out_dir=out1, seed=42)
    m2 = build_dataset([jsonl], out_dir=out2, seed=42)

    # Deterministic split mapping should match byte-for-byte (sorted by record_id)
    splits1 = (Path(m1.splits_csv)).read_text(encoding='utf-8')
    splits2 = (Path(m2.splits_csv)).read_text(encoding='utf-8')
    assert splits1 == splits2

    # Baseline evaluator should respect max_fpr constraint (easy synthetic separability here)
    res = evaluate(Path(m1.features_csv), labels_csv=Path(m1.labels_csv) if m1.labels_csv else None, max_fpr=0.01)
    assert res.has_labels is True
    assert res.metrics.get('fpr', 1.0) <= 0.01


def test_build_dataset_carries_packet_uplift_fields(tmp_path: Path) -> None:
    rec = {
        'timestamp': '2026-02-10T00:00:00Z',
        'type': 'post',
        'packet_family': 'obs.content_item',
        'packet_version': 'p1',
        'venue_id': 'moltbook',
        'entity_kind': 'content_item',
        'author_hash': 'abcd' * 4,
        'content_length': 64,
        'content_length_words': 10,
        'has_code_block': True,
        'code_block_count': 1,
        'has_link': True,
        'link_count': 1,
        'tags_count': 2,
        'mentions_count': 1,
        'line_count': 3,
        'question_count': 1,
        'exclamation_count': 2,
        'contains_ignore_previous': True,
        'contains_system_prompt_reference': True,
        'contains_developer_message_reference': False,
        'contains_env_var_reference': True,
        'prompt_injection_score': 2,
        'matched_pattern_count': 3,
        'f_complexity': 0.7,
        'f_code_density': 0.2,
        'f_toxicity': 2,
        'f_timestamp_epoch': 123.0,
    }
    signed = Obfuscator.sign_record(rec)
    jsonl = tmp_path / 'uplift.jsonl'
    _write_jsonl(jsonl, [signed])

    out_dir = tmp_path / 'dataset'
    manifest = build_dataset([jsonl], out_dir=out_dir, seed=42)

    with Path(manifest.features_csv).open('r', encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    row = rows[0]
    assert row['content_length_words'] == '10'
    assert row['code_block_count'] == '1'
    assert row['link_count'] == '1'
    assert row['line_count'] == '3'
    assert row['question_count'] == '1'
    assert row['exclamation_count'] == '2'
    assert row['contains_ignore_previous'] == '1'
    assert row['contains_system_prompt_reference'] == '1'
    assert row['contains_developer_message_reference'] == '0'
    assert row['contains_env_var_reference'] == '1'
    assert row['prompt_injection_score'] == '2'
    assert row['matched_pattern_count'] == '3'


def test_tv_review_emits_runtime_artifacts_and_updates_manifest_labels(tmp_path: Path) -> None:
    benign = Obfuscator.sign_record({
        'timestamp': '2026-02-10T00:00:00Z',
        'type': 'post',
        'author_hash': 'good' * 4,
        'content_length': 48,
        'content_length_words': 8,
        'has_code_block': False,
        'code_block_count': 0,
        'has_link': False,
        'link_count': 0,
        'tags_count': 0,
        'mentions_count': 0,
        'line_count': 2,
        'question_count': 0,
        'exclamation_count': 0,
        'contains_ignore_previous': False,
        'contains_system_prompt_reference': False,
        'contains_developer_message_reference': False,
        'contains_env_var_reference': False,
        'prompt_injection_score': 0,
        'matched_pattern_count': 0,
        'f_complexity': 0.01,
        'f_code_density': 0.0,
        'f_toxicity': 0,
        'f_timestamp_epoch': 1.0,
    })
    risky = Obfuscator.sign_record({
        'timestamp': '2026-02-10T00:00:01Z',
        'type': 'post',
        'author_hash': 'risk' * 4,
        'content_length': 220,
        'content_length_words': 30,
        'has_code_block': True,
        'code_block_count': 1,
        'has_link': True,
        'link_count': 1,
        'tags_count': 1,
        'mentions_count': 1,
        'line_count': 6,
        'question_count': 1,
        'exclamation_count': 0,
        'contains_ignore_previous': True,
        'contains_system_prompt_reference': True,
        'contains_developer_message_reference': False,
        'contains_env_var_reference': False,
        'prompt_injection_score': 2,
        'matched_pattern_count': 1,
        'f_complexity': 0.7,
        'f_code_density': 0.3,
        'f_toxicity': 1,
        'f_timestamp_epoch': 2.0,
    })
    input_path = tmp_path / 'real_source.jsonl'
    _write_jsonl(input_path, [benign, risky])

    dataset_dir = tmp_path / 'dataset'
    manifest = build_dataset([input_path], out_dir=dataset_dir, seed=42)
    assert manifest.has_labels is False

    review_summary = run_tv_review([input_path], dataset_dir)
    apply_result = apply_suggested_labels_to_dataset_manifest(
        dataset_dir / 'dataset_manifest.json',
        Path(str(review_summary['suggested_labels_csv'])),
        labeled_unique_count=int(review_summary['labeled_unique_count']),
    )

    manifest_payload = json.loads((dataset_dir / 'dataset_manifest.json').read_text(encoding='utf-8'))
    labels_text = (dataset_dir / 'labels.csv').read_text(encoding='utf-8')

    assert Path(str(review_summary['review_inventory_csv'])).name == 'tv_review_inventory.csv'
    assert Path(str(review_summary['suggested_labels_csv'])).name == 'tv_suggested_labels.csv'
    assert review_summary['labeled_unique_count'] == 2
    assert apply_result['labels_applied'] is True
    assert manifest_payload['has_labels'] is True
    assert Path(str(manifest_payload['labels_csv'])).name == 'labels.csv'
    assert 'TV-0' in labels_text
    assert 'TV-3' in labels_text


def test_evaluation_run_ledger_emits_fields_needed_for_ds_wizard_import(tmp_path: Path) -> None:
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    dataset_manifest = tmp_path / 'dataset_manifest.json'
    model_path = tmp_path / 'model.pkl'
    out_dir = tmp_path / 'evaluation_run'

    features_csv.write_text('record_id,feature\n', encoding='utf-8')
    labels_csv.write_text('record_id,label\n', encoding='utf-8')
    dataset_manifest.write_text(json.dumps({'features_csv': str(features_csv), 'labels_csv': str(labels_csv)}), encoding='utf-8')
    model_path.write_bytes(b'model')

    write_run_artifacts(
        out_dir=out_dir,
        run_id='frame6-ledger-contract',
        features_csv=features_csv,
        labels_csv=labels_csv,
        dataset_manifest_path=dataset_manifest,
        result=EvalResult(
            threshold=0.42,
            max_fpr=0.01,
            has_labels=True,
            counts={'tp': 1, 'fp': 0, 'tn': 1, 'fn': 0},
            metrics={'fpr': 0.0, 'precision': 1.0},
        ),
        model_meta={
            'family': 'trained_apexlab',
            'name': 'model.pkl',
            'source': str(model_path),
        },
    )

    run_json = json.loads((out_dir / 'run.json').read_text(encoding='utf-8'))
    assert run_json['identity']['run_id'] == 'frame6-ledger-contract'
    assert run_json['context']['constraints']['max_fpr'] == 0.01
    assert run_json['data']['features_csv'] == str(features_csv)
    assert run_json['data']['labels_csv'] == str(labels_csv)
    assert run_json['data']['dataset_manifest'] == str(dataset_manifest)
    assert run_json['model']['source'] == str(model_path)


def test_evaluate_supports_lower_tail_anomaly_direction(tmp_path: Path) -> None:
    features_csv = tmp_path / 'features.csv'
    labels_csv = tmp_path / 'labels.csv'
    features_csv.write_text(
        'record_id,feature\nlow-1,0.0\nlow-2,0.0\nhigh-1,0.0\nhigh-2,0.0\n',
        encoding='utf-8',
    )
    labels_csv.write_text(
        'record_id,tv_id\nlow-1,TV-3\nlow-2,TV-3\nhigh-1,TV-0\nhigh-2,TV-0\n',
        encoding='utf-8',
    )
    score_map = {
        'low-1': 0.1,
        'low-2': 0.2,
        'high-1': 0.8,
        'high-2': 0.9,
    }

    result = evaluate(
        features_csv,
        labels_csv=labels_csv,
        max_fpr=0.5,
        scorer=lambda row: score_map[str(row.get('record_id', ''))],
        score_direction='lower',
    )

    assert result.threshold == pytest.approx(0.2)
    assert result.counts == {'tp': 2, 'fp': 0, 'tn': 2, 'fn': 0}
    assert result.metrics['f1'] == pytest.approx(1.0)


def test_report_visuals_emit_threshold_report_and_score_figures(tmp_path: Path) -> None:
    from analysis.report_visuals import generate_score_visuals, summarize_threshold_scores_csv, write_threshold_report

    scores_csv = tmp_path / 'scores.csv'
    scores_csv.write_text('record_id,score_anomaly\na,0.1\nb,0.2\nc,0.8\nd,0.9\n', encoding='utf-8')

    summary = summarize_threshold_scores_csv(scores_csv, 0.25)
    summary = write_threshold_report(summary, tmp_path)
    visuals = generate_score_visuals(
        scores_csv=scores_csv,
        figures_dir=tmp_path / 'figures',
        threshold_summary=summary,
    )

    assert summary['anomaly_direction'] == 'lower-is-more-anomalous'
    assert summary['threshold'] == pytest.approx(0.2)
    assert summary['flag_rule'] == 'score <= threshold'
    assert (tmp_path / 'threshold_report.json').exists()
    assert 'score <= threshold' in (tmp_path / 'threshold_report.md').read_text(encoding='utf-8')
    assert visuals['decision'] == 'go'
    assert visuals['figure_count'] == 2
    assert {figure['id'] for figure in visuals['figures']} == {'score_distribution', 'threshold_selection'}
    for figure in visuals['figures']:
        assert Path(figure['path']).exists()


def test_report_visuals_emit_evaluation_figures(tmp_path: Path) -> None:
    from analysis.report_visuals import generate_evaluation_visuals

    visuals = generate_evaluation_visuals(
        figures_dir=tmp_path / 'figures',
        metrics={'precision': 1.0, 'recall': 0.5, 'f1': 0.6667, 'fpr': 0.0},
        counts={'tp': 1, 'fp': 0, 'tn': 2, 'fn': 1},
        threshold=0.2,
        max_fpr=0.01,
    )

    assert visuals['decision'] == 'go'
    assert visuals['figure_count'] >= 3
    assert {'confusion_matrix', 'metric_comparison', 'threshold_summary'}.issubset({figure['id'] for figure in visuals['figures']})
    for figure in visuals['figures']:
        assert Path(figure['path']).exists()


def test_report_visuals_emit_evaluation_threshold_overlay_when_scores_are_available(tmp_path: Path) -> None:
    from analysis.report_visuals import generate_evaluation_visuals

    scores_csv = tmp_path / 'scores.csv'
    scores_csv.write_text('record_id,score_anomaly\na,0.1\nb,0.2\nc,0.8\nd,0.9\n', encoding='utf-8')

    visuals = generate_evaluation_visuals(
        figures_dir=tmp_path / 'figures',
        metrics={'flag_rate': 0.5},
        counts={'flagged': 2, 'total': 4},
        threshold=0.2,
        max_fpr=0.25,
        threshold_summary={
            'threshold': 0.2,
            'target_fpr': 0.25,
            'actual_fpr': 0.5,
            'flagged_records': 2,
            'records_scored': 4,
        },
        scores_csv=scores_csv,
    )

    assert visuals['decision'] == 'go'
    assert visuals['anomaly_direction'] == 'lower-is-more-anomalous'
    assert visuals['score_column'] == 'score_anomaly'
    assert 'threshold_selection' in {figure['id'] for figure in visuals['figures']}


def test_report_visuals_emit_build_figures_from_dataset_metadata(tmp_path: Path) -> None:
    from analysis.report_visuals import generate_build_visuals

    input_a = tmp_path / 'slice_a.jsonl'
    input_b = tmp_path / 'slice_b.jsonl'
    records_a = []
    for index in range(6):
        records_a.append(Obfuscator.sign_record({
            'timestamp': '2026-02-10T00:00:{0:02d}Z'.format(index),
            'type': 'post',
            'author_hash': 'a{0:015d}'.format(index),
            'content_length': 32,
            'content_length_words': 6,
            'has_code_block': bool(index % 2),
            'code_block_count': 1 if index % 2 else 0,
            'has_link': bool(index % 3 == 0),
            'link_count': 1 if index % 3 == 0 else 0,
            'tags_count': 1,
            'mentions_count': 0,
            'line_count': 2,
            'question_count': 0,
            'exclamation_count': 1,
            'contains_ignore_previous': False,
            'contains_system_prompt_reference': False,
            'contains_developer_message_reference': False,
            'contains_env_var_reference': False,
            'prompt_injection_score': 0,
            'matched_pattern_count': 0,
            'f_complexity': 0.2,
            'f_code_density': 0.1,
            'f_toxicity': 0,
            'f_timestamp_epoch': float(index),
            'tv_id': 'TV-0',
        }))
    records_b = []
    for index in range(3):
        records_b.append(Obfuscator.sign_record({
            'timestamp': '2026-02-10T00:01:{0:02d}Z'.format(index),
            'type': 'mention',
            'author_hash': 'b{0:015d}'.format(index),
            'content_length': 180,
            'content_length_words': 24,
            'has_code_block': True,
            'code_block_count': 2,
            'has_link': True,
            'link_count': 1,
            'tags_count': 2,
            'mentions_count': 3,
            'line_count': 5,
            'question_count': 1,
            'exclamation_count': 0,
            'contains_ignore_previous': True,
            'contains_system_prompt_reference': True,
            'contains_developer_message_reference': False,
            'contains_env_var_reference': True,
            'prompt_injection_score': 2,
            'matched_pattern_count': 2,
            'f_complexity': 0.7,
            'f_code_density': 0.3,
            'f_toxicity': 1,
            'f_timestamp_epoch': float(100 + index),
            'tv_id': 'TV-3',
        }))

    _write_jsonl(input_a, records_a)
    _write_jsonl(input_b, records_b)

    out_dir = tmp_path / 'dataset'
    manifest = build_dataset([input_a, input_b], out_dir=out_dir, seed=42)
    visuals = generate_build_visuals(
        figures_dir=tmp_path / 'figures',
        dataset_manifest_path=Path(out_dir / 'dataset_manifest.json'),
        split_manifest_path=Path(manifest.split_manifest_json),
    )

    assert visuals['decision'] == 'go'
    assert visuals['figure_count'] == 3
    assert {figure['id'] for figure in visuals['figures']} == {
        'split_balance',
        'input_slice_volume',
        'feature_family_breakdown',
    }
    for figure in visuals['figures']:
        assert Path(figure['path']).exists()


def test_report_visuals_skipped_states_preserve_shared_contract_keys(tmp_path: Path, monkeypatch) -> None:
    import analysis.report_visuals as report_visuals_module

    monkeypatch.setattr(report_visuals_module, '_load_pyplot', lambda: None)

    evaluation_visuals = report_visuals_module.generate_evaluation_visuals(
        figures_dir=tmp_path / 'evaluation-figures',
        metrics={},
        counts={},
    )
    summary_visuals = report_visuals_module.generate_summary_card_visual(
        figures_dir=tmp_path / 'summary-figures',
        figure_id='workflow_summary',
        title='Workflow summary',
        rows={'Records': 10},
        filename='workflow_summary.png',
        caption='Demo summary card.',
    )

    for visuals in (evaluation_visuals, summary_visuals):
        assert visuals['decision'] == 'skipped'
        assert visuals['figure_count'] == 0
        assert visuals['anomaly_direction'] == ''
        assert visuals['score_column'] == ''
        assert visuals['figures'] == []
        assert visuals['reason_codes'] == ['visualization_skipped:matplotlib_unavailable']


def test_report_visuals_merge_deduplicates_figure_ids_and_preserves_latest_metadata(tmp_path: Path) -> None:
    from analysis.report_visuals import merge_visual_states

    merged = merge_visual_states(
        {
            'decision': 'go',
            'reason_codes': ['visualization_skipped:first-state-note'],
            'figures': [
                {
                    'id': 'threshold_selection',
                    'title': 'Old threshold selection',
                    'caption': 'Old caption.',
                    'path': tmp_path / 'threshold_old.png',
                    'kind': 'threshold',
                }
            ],
        },
        {
            'decision': 'go',
            'reason_codes': ['visualization_skipped:second-state-note'],
            'anomaly_direction': 'lower-is-more-anomalous',
            'score_column': 'score_anomaly',
            'figures': [
                {
                    'id': 'threshold_selection',
                    'title': 'Threshold selection',
                    'caption': 'Lower-tail threshold overlay.',
                    'path': tmp_path / 'threshold_latest.png',
                    'kind': 'threshold',
                },
                {
                    'id': 'metric_comparison',
                    'title': 'Metric comparison',
                    'caption': 'Evaluation metric bars.',
                    'path': tmp_path / 'metric_comparison.png',
                    'kind': 'metrics',
                },
            ],
        },
    )

    assert merged['decision'] == 'go'
    assert merged['figure_count'] == 2
    assert merged['anomaly_direction'] == 'lower-is-more-anomalous'
    assert merged['score_column'] == 'score_anomaly'
    assert [figure['id'] for figure in merged['figures']] == ['threshold_selection', 'metric_comparison']
    assert merged['figures'][0]['title'] == 'Threshold selection'
    assert merged['figures'][0]['caption'] == 'Lower-tail threshold overlay.'
    assert merged['figures'][0]['path'].endswith('threshold_latest.png')
    assert merged['figures'][0]['kind'] == 'threshold'
    assert merged['reason_codes'] == [
        'visualization_skipped:first-state-note',
        'visualization_skipped:second-state-note',
    ]


def test_report_pack_markdown_uses_codesentinel_style_sections(tmp_path: Path) -> None:
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    bundle = prepare_report_bundle(anchor, 'demo', run_id='demo-style-001')
    dataset_dir = bundle.artifact_dirs['dataset']
    models_dir = bundle.artifact_dirs['models']
    evaluation_dir = bundle.artifact_dirs['evaluation']
    figures_dir = bundle.run_root / 'figures'
    dataset_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    features_csv = dataset_dir / 'features.csv'
    run_json = evaluation_dir / 'run.json'
    run_md = evaluation_dir / 'run.md'
    figure_path = figures_dir / 'score_distribution.png'

    dataset_manifest.write_text('{}\n', encoding='utf-8')
    features_csv.write_text('record_id\n', encoding='utf-8')
    run_json.write_text('{"decision":"go"}\n', encoding='utf-8')
    run_md.write_text('# run\n', encoding='utf-8')
    figure_path.write_bytes(b'fake-png')

    bundle_result = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-04-02T12:00:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-run',
            'collection_alias': 'can-demo-style',
            'command_family': 'ds',
            'command_path': 'observerctl ds run demo',
            'implementation_state': 'automation-available',
            'underlying_surface': 'analysis.demo_runner',
            'summary': 'Demo pipeline completed through observerctl ds.',
            'run_id': bundle.run_id,
            'anomaly_direction': 'lower-is-more-anomalous',
            'counts': {'tp': 10, 'fp': 0, 'tn': 50, 'fn': 0},
            'metrics': {'precision': 1.0, 'recall': 1.0, 'f1': 1.0, 'fpr': 0.0},
            'thresholding': {
                'target_fpr': 0.01,
                'actual_fpr': 0.0,
                'threshold': 0.42,
            },
            'workflow_steps': ['generate', 'build', 'evaluate'],
            'reason_codes': [],
            'visuals': {
                'anomaly_direction': 'lower-is-more-anomalous',
                'figure_count': 1,
                'figures': [
                    {
                        'id': 'score_distribution',
                        'title': 'Score distribution',
                        'caption': 'Distribution of anomaly scores.',
                        'path': figure_path,
                    }
                ],
            },
            'artifacts': {},
        },
        artifact_paths={
            'dataset_manifest': dataset_manifest,
            'features_csv': features_csv,
            'evaluation_run_json': run_json,
            'evaluation_run_md': run_md,
        },
        context={'dataset_seed': 123, 'max_fpr': 0.01},
        lineage={'source_run_root': bundle.run_root},
    )

    report_md = (project_root / bundle_result['paths']['report_md']).read_text(encoding='utf-8')

    assert '**Decision**: `go`' in report_md
    assert '**Collection alias**: `can-demo-style`' in report_md
    assert '## Executive summary' in report_md
    assert '## Why this packet exists' in report_md
    assert '## Run snapshot' in report_md
    assert '## Context' in report_md
    assert '## What this packet shows' in report_md
    assert '## Result overview' in report_md
    assert '### Counts' in report_md
    assert '### Metrics' in report_md
    assert '### Thresholding' in report_md
    assert '### Workflow steps' in report_md
    assert '### Reason codes' in report_md
    assert 'composite workflow packet' in report_md
    assert '## Limits and cautions' in report_md
    assert '## Artifact index' in report_md
    assert '## Provenance' in report_md
    assert '## Report paths' in report_md
    assert '## Reader next steps' in report_md
    assert '[Report JSON](report.json)' in report_md
    assert '[Manifest JSON](manifest.json)' in report_md
    assert '![Score distribution](../figures/score_distribution.png)' in report_md
    assert '| Field | Value |' in report_md


def test_report_pack_markdown_marks_stage_workflows_as_processing_stage_packets(tmp_path: Path) -> None:
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    bundle = prepare_report_bundle(anchor, 'build', run_id='build-style-001')
    dataset_dir = bundle.artifact_dirs['dataset']
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_manifest = dataset_dir / 'dataset_manifest.json'
    dataset_manifest.write_text('{}\n', encoding='utf-8')

    bundle_result = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-04-02T12:30:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-build',
            'collection_alias': 'can-build-style',
            'command_family': 'ds',
            'command_path': 'observerctl ds build',
            'implementation_state': 'automation-available',
            'underlying_surface': 'analysis.dataset_builder',
            'summary': 'Dataset build completed through observerctl ds.',
            'run_id': bundle.run_id,
            'counts': {'records_built': 1284},
            'reason_codes': [],
            'artifacts': {},
        },
        artifact_paths={
            'dataset_manifest': dataset_manifest,
        },
        context={'dataset_seed': 123},
        lineage={'source_run_root': bundle.run_root},
    )

    report_md = (project_root / bundle_result['paths']['report_md']).read_text(encoding='utf-8')

    assert 'Role In The Report Spine' in report_md
    assert 'first processing packet' in report_md
    assert 'composite workflow packet' not in report_md
    assert '## Build identity' in report_md
    assert '## Run summary' in report_md
    assert '## Build handoff map' in report_md
    assert '## Build method' in report_md
    assert '## Dataset materialization summary' in report_md
    assert '## Split and schema summary' in report_md
    assert '## Visual surfaces' in report_md
    assert 'No declared figures were emitted for this packet.' in report_md
    assert '## Run implications' in report_md
    assert '## Limits' in report_md
    assert '## Related surfaces' in report_md
    assert '## Artifact index' not in report_md
    assert '## Report paths' not in report_md
    assert '## Reader next steps' not in report_md


def test_report_pack_stage_markdown_keeps_visual_links_and_compact_related_surfaces(tmp_path: Path) -> None:
    from analysis.report_pack import prepare_report_bundle, write_report_bundle

    project_root = tmp_path / 'observer_project'
    anchor = project_root / 'src' / 'observerctl_anchor.py'
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text('# anchor\n', encoding='utf-8')
    (project_root / 'PROJECT_MANIFEST.json').write_text('{}\n', encoding='utf-8')

    bundle = prepare_report_bundle(anchor, 'score', run_id='score-style-001')
    scoring_dir = bundle.artifact_dirs['scoring']
    figures_dir = bundle.run_root / 'figures'
    scoring_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    scores_csv = scoring_dir / 'scores.csv'
    figure_path = figures_dir / 'score_distribution.png'
    scores_csv.write_text('record_id,score_anomaly\na,0.1\nb,0.9\n', encoding='utf-8')
    figure_path.write_bytes(b'fake-png')

    bundle_result = write_report_bundle(
        project_anchor=anchor,
        bundle=bundle,
        packet={
            'timestamp_utc': '2026-04-02T12:45:00Z',
            'runtime_cli_surface': 'observerctl',
            'decision': 'go',
            'action': 'ds-score',
            'collection_alias': 'can-score-style',
            'command_family': 'ds',
            'command_path': 'observerctl ds score',
            'implementation_state': 'command-available',
            'underlying_surface': 'analysis.score_unsupervised',
            'summary': 'Unsupervised scoring completed through observerctl ds.',
            'run_id': bundle.run_id,
            'records_scored': 2,
            'score_column': 'score_anomaly',
            'anomaly_direction': 'lower-is-more-anomalous',
            'thresholding': {
                'threshold': 0.2,
                'report_json': scoring_dir / 'threshold_report.json',
                'report_md': scoring_dir / 'threshold_report.md',
                'scores_csv': scores_csv,
            },
            'reason_codes': [],
            'visuals': {
                'decision': 'go',
                'figure_count': 1,
                'anomaly_direction': 'lower-is-more-anomalous',
                'score_column': 'score_anomaly',
                'figures': [
                    {
                        'id': 'score_distribution',
                        'title': 'Score distribution',
                        'caption': 'Distribution of anomaly scores. Lower scores indicate more anomalous records.',
                        'path': figure_path,
                    }
                ],
            },
            'artifacts': {},
        },
        artifact_paths={
            'scores_csv': scores_csv,
        },
        context={'output_override': False},
        lineage={'source_run_root': bundle.run_root},
    )

    report_md = (project_root / bundle_result['paths']['report_md']).read_text(encoding='utf-8')

    assert '## Score identity' in report_md
    assert '## Run summary' in report_md
    assert '## Score handoff map' in report_md
    assert '## Score method' in report_md
    assert '## Score surface summary' in report_md
    assert '## Distribution summary' in report_md
    assert '## Visual surfaces' in report_md
    assert '## Related surfaces' in report_md
    assert '## Run implications' in report_md
    assert '## Limits' in report_md
    assert 'This stage exposes the score surface rather than making a semantic case judgment about the ranked records.' in report_md
    assert '[Report JSON](report.json)' in report_md
    assert '[Manifest JSON](manifest.json)' in report_md
    assert '[Score surface CSV](../scoring/scores.csv)' in report_md
    assert '![Score distribution](../figures/score_distribution.png)' in report_md
