from __future__ import annotations

import csv
from collections.abc import Mapping as MappingABC
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from apexlab.evaluation.thresholds import select_lower_tail_threshold


ANOMALY_DIRECTION = 'lower-is-more-anomalous'
DEFAULT_SCORE_COLUMNS = ('score_anomaly', 'score_raw')


def _visual_state(
    *,
    decision: str,
    reason_codes: Optional[Iterable[str]] = None,
    figures: Optional[Iterable[Mapping[str, Any]]] = None,
    anomaly_direction: str = '',
    score_column: str = '',
) -> Dict[str, Any]:
    normalized_figures = _normalize_figure_records(figures)
    normalized_reason_codes = _normalize_reason_codes(reason_codes)
    resolved_decision = str(decision or '').strip().lower() or ('go' if normalized_figures else 'skipped')
    if resolved_decision == 'go' and not normalized_figures:
        resolved_decision = 'skipped'
    return {
        'decision': resolved_decision,
        'reason_codes': normalized_reason_codes,
        'figure_count': int(len(normalized_figures)),
        'anomaly_direction': str(anomaly_direction or '').strip(),
        'score_column': str(score_column or '').strip(),
        'figures': normalized_figures,
    }


def _normalize_reason_codes(reason_codes: Optional[Iterable[str]]) -> List[str]:
    normalized: List[str] = []
    for reason_code in list(reason_codes or []):
        text = str(reason_code or '').strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_figure_records(figures: Optional[Iterable[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    ordered_ids: List[str] = []
    by_id: Dict[str, Dict[str, Any]] = {}
    for figure in list(figures or []):
        normalized = _normalize_figure_record(figure)
        if normalized is None:
            continue
        figure_id = str(normalized.get('id', '') or '')
        if figure_id in by_id:
            ordered_ids = [existing for existing in ordered_ids if existing != figure_id]
        ordered_ids.append(figure_id)
        by_id[figure_id] = normalized
    return [dict(by_id[figure_id]) for figure_id in ordered_ids if figure_id in by_id]


def _normalize_figure_record(figure: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(figure, MappingABC):
        return None
    figure_id = str(figure.get('id', '') or '').strip()
    raw_path = figure.get('path')
    if not figure_id or raw_path in ('', None):
        return None
    normalized: Dict[str, Any] = {
        'id': figure_id,
        'title': str(figure.get('title', '') or figure_id).strip() or figure_id,
        'caption': str(figure.get('caption', '') or '').strip(),
        'path': str(raw_path).replace('\\', '/'),
        'kind': str(figure.get('kind', '') or 'unknown').strip() or 'unknown',
    }
    for key, value in figure.items():
        text_key = str(key)
        if text_key in normalized or value in ('', None):
            continue
        if isinstance(value, Path):
            normalized[text_key] = str(value).replace('\\', '/')
        else:
            normalized[text_key] = value
    return normalized


def load_score_series(scores_csv: Path) -> Dict[str, Any]:
    if not scores_csv.exists():
        return {
            'decision': 'skipped',
            'reason_codes': ['visualization_skipped:scores_csv_missing'],
            'scores': [],
            'record_ids': [],
            'score_column': '',
            'records_scored': 0,
            'invalid_rows': 0,
        }

    with scores_csv.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        score_column = ''
        for column in DEFAULT_SCORE_COLUMNS:
            if column in fieldnames:
                score_column = column
                break
        if not score_column:
            return {
                'decision': 'skipped',
                'reason_codes': ['visualization_skipped:score_column_missing'],
                'scores': [],
                'record_ids': [],
                'score_column': '',
                'records_scored': 0,
                'invalid_rows': 0,
            }

        scores: List[float] = []
        record_ids: List[str] = []
        invalid_rows = 0
        for index, row in enumerate(reader):
            raw_score = row.get(score_column)
            if raw_score is None or str(raw_score).strip() == '':
                invalid_rows += 1
                continue
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                invalid_rows += 1
                continue
            record_id = str(row.get('record_id', '') or '').strip() or 'row-{0}'.format(index + 1)
            scores.append(score)
            record_ids.append(record_id)

    if not scores:
        return {
            'decision': 'skipped',
            'reason_codes': ['visualization_skipped:no_scores_loaded'],
            'scores': [],
            'record_ids': [],
            'score_column': score_column,
            'records_scored': 0,
            'invalid_rows': int(invalid_rows),
        }

    return {
        'decision': 'go',
        'reason_codes': [],
        'scores': scores,
        'record_ids': record_ids,
        'score_column': score_column,
        'records_scored': int(len(scores)),
        'invalid_rows': int(invalid_rows),
    }


def summarize_threshold_scores_csv(scores_csv: Path, max_fpr: float) -> Dict[str, Any]:
    series = load_score_series(scores_csv)
    if str(series.get('decision', '')) != 'go':
        return {
            'decision': 'skipped',
            'reason_codes': list(series.get('reason_codes', []) or []),
            'threshold': 0.0,
            'target_fpr': float(max_fpr),
            'actual_fpr': 0.0,
            'flagged_records': 0,
            'records_scored': int(series.get('records_scored', 0) or 0),
            'invalid_rows': int(series.get('invalid_rows', 0) or 0),
            'scores_csv': str(scores_csv).replace('\\', '/'),
            'score_column': str(series.get('score_column', '') or ''),
            'anomaly_direction': ANOMALY_DIRECTION,
            'flag_rule': 'score <= threshold',
            'algorithm': 'apexlab_lower_tail_threshold',
        }

    scores = list(series.get('scores', []) or [])
    threshold = float(select_lower_tail_threshold(scores, target_fpr=float(max_fpr))) if scores else 0.0
    flagged = sum(1 for score in scores if float(score) <= threshold)
    total = int(len(scores))
    actual_fpr = (float(flagged) / float(total)) if total else 0.0
    return {
        'decision': 'go',
        'reason_codes': [],
        'threshold': float(threshold),
        'target_fpr': float(max_fpr),
        'actual_fpr': float(actual_fpr),
        'flagged_records': int(flagged),
        'records_scored': int(total),
        'invalid_rows': int(series.get('invalid_rows', 0) or 0),
        'scores_csv': str(scores_csv).replace('\\', '/'),
        'score_column': str(series.get('score_column', '') or ''),
        'anomaly_direction': ANOMALY_DIRECTION,
        'flag_rule': 'score <= threshold',
        'algorithm': 'apexlab_lower_tail_threshold',
    }


def write_threshold_report(summary: Mapping[str, Any], out_dir: Path, stem: str = 'threshold_report') -> Dict[str, Any]:
    payload = dict(summary)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / '{0}.json'.format(stem)
    report_md = out_dir / '{0}.md'.format(stem)
    report_json.write_text(_threshold_report_json(payload), encoding='utf-8')
    report_md.write_text(_threshold_report_markdown(payload), encoding='utf-8')
    payload['report_json'] = str(report_json).replace('\\', '/')
    payload['report_md'] = str(report_md).replace('\\', '/')
    return payload


def generate_score_visuals(
    *,
    scores_csv: Path,
    figures_dir: Path,
    threshold_summary: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    series = load_score_series(scores_csv)
    if str(series.get('decision', '')) != 'go':
        return _visual_state(
            decision='skipped',
            reason_codes=list(series.get('reason_codes', []) or []),
            anomaly_direction=ANOMALY_DIRECTION,
            score_column=str(series.get('score_column', '') or ''),
        )

    pyplot = _load_pyplot()
    if pyplot is None:
        return _visual_state(
            decision='skipped',
            reason_codes=['visualization_skipped:matplotlib_unavailable'],
            anomaly_direction=ANOMALY_DIRECTION,
            score_column=str(series.get('score_column', '') or ''),
        )

    figures_dir.mkdir(parents=True, exist_ok=True)
    scores = list(series.get('scores', []) or [])
    score_column = str(series.get('score_column', '') or '')
    figures: List[Dict[str, Any]] = []

    distribution_path = figures_dir / 'score_distribution.png'
    _render_distribution_chart(pyplot, scores, distribution_path, score_column=score_column)
    figures.append(_figure_record(
        figure_id='score_distribution',
        title='Score distribution',
        caption='Distribution of anomaly scores. Lower scores indicate more anomalous records.',
        path=distribution_path,
        kind='distribution',
    ))

    threshold_value = _optional_float((threshold_summary or {}).get('threshold')) if threshold_summary is not None else None
    if threshold_value is not None:
        threshold_path = figures_dir / 'threshold_selection.png'
        _render_threshold_chart(
            pyplot,
            scores,
            threshold_path,
            threshold=float(threshold_value),
            target_fpr=_optional_float((threshold_summary or {}).get('target_fpr')),
            actual_fpr=_optional_float((threshold_summary or {}).get('actual_fpr')),
            score_column=score_column,
        )
        figures.append(_figure_record(
            figure_id='threshold_selection',
            title='Threshold selection',
            caption='Lower-tail threshold overlay. Scores at or below the threshold are treated as anomalous.',
            path=threshold_path,
            kind='threshold',
        ))

    return _visual_state(
        decision='go' if figures else 'skipped',
        reason_codes=[] if figures else ['visualization_skipped:no_score_figures_rendered'],
        anomaly_direction=ANOMALY_DIRECTION,
        score_column=score_column,
        figures=figures,
    )


def generate_evaluation_visuals(
    *,
    figures_dir: Path,
    metrics: Mapping[str, Any],
    counts: Mapping[str, Any],
    threshold: Optional[float] = None,
    max_fpr: Optional[float] = None,
    threshold_summary: Optional[Mapping[str, Any]] = None,
    scores_csv: Optional[Path] = None,
) -> Dict[str, Any]:
    pyplot = _load_pyplot()
    if pyplot is None:
        return _visual_state(
            decision='skipped',
            reason_codes=['visualization_skipped:matplotlib_unavailable'],
        )

    figures_dir.mkdir(parents=True, exist_ok=True)
    figures: List[Dict[str, Any]] = []
    anomaly_direction = str((threshold_summary or {}).get('anomaly_direction', '') or '').strip() if isinstance(threshold_summary, MappingABC) else ''
    score_column = str((threshold_summary or {}).get('score_column', '') or '').strip() if isinstance(threshold_summary, MappingABC) else ''

    if _has_confusion_counts(counts):
        confusion_path = figures_dir / 'confusion_matrix.png'
        _render_confusion_matrix(pyplot, counts, confusion_path)
        figures.append(_figure_record(
            figure_id='confusion_matrix',
            title='Confusion matrix',
            caption='Confusion matrix rendered from evaluation counts.',
            path=confusion_path,
            kind='confusion-matrix',
        ))

    numeric_metrics = _numeric_items(metrics)
    if numeric_metrics:
        metric_path = figures_dir / 'metric_comparison.png'
        _render_metric_bars(pyplot, numeric_metrics, metric_path)
        figures.append(_figure_record(
            figure_id='metric_comparison',
            title='Metric comparison',
            caption='Evaluation metric comparison bars derived from the report-pack metrics payload.',
            path=metric_path,
            kind='metrics',
        ))

    threshold_rows: List[tuple] = []
    if threshold_summary is not None:
        threshold_rows.extend([
            ('Threshold', threshold_summary.get('threshold')),
            ('Target FPR', threshold_summary.get('target_fpr')),
            ('Actual FPR', threshold_summary.get('actual_fpr')),
            ('Flagged', threshold_summary.get('flagged_records')),
            ('Records', threshold_summary.get('records_scored')),
        ])
    else:
        threshold_rows.extend([
            ('Threshold', threshold),
            ('Target FPR', max_fpr),
            ('Actual FPR', metrics.get('fpr') if isinstance(metrics, Mapping) else None),
        ])
    threshold_rows = [(label, value) for label, value in threshold_rows if value not in ('', None)]
    if threshold_rows:
        threshold_path = figures_dir / 'threshold_summary.png'
        _render_summary_card(pyplot, threshold_rows, threshold_path, title='Threshold summary')
        figures.append(_figure_record(
            figure_id='threshold_summary',
            title='Threshold summary',
            caption='Threshold and FPR summary derived from the evaluation or threshold payload.',
            path=threshold_path,
            kind='summary',
        ))

    if scores_csv is not None and threshold_summary is not None:
        series = load_score_series(Path(scores_csv))
        if str(series.get('decision', '')) == 'go':
            threshold_value = _optional_float((threshold_summary or {}).get('threshold'))
            if threshold_value is not None:
                score_column = str(series.get('score_column', '') or '')
                anomaly_direction = ANOMALY_DIRECTION
                threshold_path = figures_dir / 'threshold_selection.png'
                _render_threshold_chart(
                    pyplot,
                    list(series.get('scores', []) or []),
                    threshold_path,
                    threshold=float(threshold_value),
                    target_fpr=_optional_float((threshold_summary or {}).get('target_fpr')),
                    actual_fpr=_optional_float((threshold_summary or {}).get('actual_fpr')),
                    score_column=score_column,
                )
                figures.append(_figure_record(
                    figure_id='threshold_selection',
                    title='Threshold selection',
                    caption='Lower-tail threshold overlay. Scores at or below the threshold are treated as anomalous.',
                    path=threshold_path,
                    kind='threshold',
                ))

    return _visual_state(
        decision='go' if figures else 'skipped',
        reason_codes=[] if figures else ['visualization_skipped:no_evaluation_figures_rendered'],
        anomaly_direction=anomaly_direction,
        score_column=score_column,
        figures=figures,
    )


def generate_summary_card_visual(
    *,
    figures_dir: Path,
    figure_id: str,
    title: str,
    rows: Mapping[str, Any],
    filename: str,
    caption: str,
) -> Dict[str, Any]:
    pyplot = _load_pyplot()
    if pyplot is None:
        return _visual_state(
            decision='skipped',
            reason_codes=['visualization_skipped:matplotlib_unavailable'],
        )

    filtered_rows = [(str(key), value) for key, value in rows.items() if value not in ('', None, [], {})]
    if not filtered_rows:
        return _visual_state(
            decision='skipped',
            reason_codes=['visualization_skipped:no_summary_rows'],
        )

    figures_dir.mkdir(parents=True, exist_ok=True)
    output_path = figures_dir / filename
    _render_summary_card(pyplot, filtered_rows, output_path, title=title)
    return _visual_state(
        decision='go',
        figures=[
            _figure_record(
                figure_id=figure_id,
                title=title,
                caption=caption,
                path=output_path,
                kind='summary',
            )
        ],
    )


def merge_visual_states(*states: Mapping[str, Any]) -> Dict[str, Any]:
    figures: List[Dict[str, Any]] = []
    reason_codes: List[str] = []
    anomaly_direction = ''
    score_column = ''
    for state in states:
        if not isinstance(state, MappingABC):
            continue
        for figure in list(state.get('figures', []) or []):
            if isinstance(figure, MappingABC):
                figures.append(dict(figure))
        reason_codes.extend(list(state.get('reason_codes', []) or []))
        if not anomaly_direction and str(state.get('anomaly_direction', '') or '').strip():
            anomaly_direction = str(state.get('anomaly_direction', '') or '').strip()
        if not score_column and str(state.get('score_column', '') or '').strip():
            score_column = str(state.get('score_column', '') or '').strip()

    normalized_figures = _normalize_figure_records(figures)
    return _visual_state(
        decision='go' if normalized_figures else 'skipped',
        reason_codes=reason_codes,
        anomaly_direction=anomaly_direction,
        score_column=score_column,
        figures=normalized_figures,
    )


def _threshold_report_json(payload: Mapping[str, Any]) -> str:
    rendered = dict(payload)
    return json_dumps(rendered)


def _threshold_report_markdown(payload: Mapping[str, Any]) -> str:
    lines = ['# Threshold Selection Report', '']
    lines.append('- Status: {0}'.format(str(payload.get('decision', 'skipped'))))
    lines.append('- Score column: {0}'.format(str(payload.get('score_column', ''))))
    lines.append('- Anomaly direction: {0}'.format(str(payload.get('anomaly_direction', ANOMALY_DIRECTION))))
    lines.append('- Flag rule: {0}'.format(str(payload.get('flag_rule', 'score <= threshold'))))
    lines.append('- Target FPR: {0}'.format(_format_number(payload.get('target_fpr'))))
    lines.append('- Threshold: {0}'.format(_format_number(payload.get('threshold'))))
    lines.append('- Actual FPR: {0}'.format(_format_number(payload.get('actual_fpr'))))
    lines.append('- Flagged records: {0}'.format(_format_int(payload.get('flagged_records'))))
    lines.append('- Records scored: {0}'.format(_format_int(payload.get('records_scored'))))
    lines.append('- Invalid rows skipped: {0}'.format(_format_int(payload.get('invalid_rows'))))
    lines.append('- Scores CSV: {0}'.format(str(payload.get('scores_csv', ''))))
    lines.append('- Algorithm: {0}'.format(str(payload.get('algorithm', ''))))
    reason_codes = list(payload.get('reason_codes', []) or [])
    if reason_codes:
        lines.append('')
        lines.append('## Reason codes')
        lines.append('')
        for reason_code in reason_codes:
            lines.append('- {0}'.format(str(reason_code)))
    return '\n'.join(lines).rstrip() + '\n'


def _load_pyplot():
    try:
        import matplotlib

        matplotlib.use('Agg')
        import matplotlib.pyplot as pyplot

        return pyplot
    except Exception:
        return None


def _render_distribution_chart(pyplot, scores: List[float], output_path: Path, *, score_column: str) -> None:
    figure, axis = pyplot.subplots(figsize=(10, 5))
    axis.hist(scores, bins=min(30, max(10, len(scores))), color='#4C78A8', edgecolor='white', alpha=0.9)
    axis.set_title('Anomaly score distribution')
    axis.set_xlabel('Anomaly score ({0})'.format(ANOMALY_DIRECTION.replace('-', ' ')))
    axis.set_ylabel('Count')
    _annotate_score_stats(axis, scores, score_column)
    figure.tight_layout()
    figure.savefig(output_path)
    pyplot.close(figure)


def _render_threshold_chart(
    pyplot,
    scores: List[float],
    output_path: Path,
    *,
    threshold: float,
    target_fpr: Optional[float],
    actual_fpr: Optional[float],
    score_column: str,
) -> None:
    figure, axis = pyplot.subplots(figsize=(10, 5))
    axis.hist(scores, bins=min(30, max(10, len(scores))), color='#72B7B2', edgecolor='white', alpha=0.9)
    axis.axvline(float(threshold), color='#E45756', linestyle='--', linewidth=2)
    axis.axvspan(min(scores), float(threshold), color='#E45756', alpha=0.12)
    axis.set_title('Threshold selection overlay')
    axis.set_xlabel('Anomaly score ({0})'.format(ANOMALY_DIRECTION.replace('-', ' ')))
    axis.set_ylabel('Count')
    summary_lines = [
        'Column: {0}'.format(score_column),
        'Threshold: {0}'.format(_format_number(threshold)),
    ]
    if target_fpr is not None:
        summary_lines.append('Target FPR: {0}'.format(_format_number(target_fpr)))
    if actual_fpr is not None:
        summary_lines.append('Actual FPR: {0}'.format(_format_number(actual_fpr)))
    axis.text(
        0.02,
        0.98,
        '\n'.join(summary_lines),
        transform=axis.transAxes,
        va='top',
        ha='left',
        fontsize=9,
        bbox={'boxstyle': 'round', 'facecolor': 'white', 'alpha': 0.9},
    )
    figure.tight_layout()
    figure.savefig(output_path)
    pyplot.close(figure)


def _render_confusion_matrix(pyplot, counts: Mapping[str, Any], output_path: Path) -> None:
    matrix = [
        [_as_int(counts.get('tn')), _as_int(counts.get('fp'))],
        [_as_int(counts.get('fn')), _as_int(counts.get('tp'))],
    ]
    figure, axis = pyplot.subplots(figsize=(5, 4))
    image = axis.imshow(matrix, cmap='Blues')
    axis.set_title('Confusion matrix')
    axis.set_xticks([0, 1])
    axis.set_xticklabels(['Predicted normal', 'Predicted anomalous'])
    axis.set_yticks([0, 1])
    axis.set_yticklabels(['Actual normal', 'Actual anomalous'])
    for row_index, row in enumerate(matrix):
        for column_index, value in enumerate(row):
            axis.text(column_index, row_index, str(value), ha='center', va='center', color='black')
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.tight_layout()
    figure.savefig(output_path)
    pyplot.close(figure)


def _render_metric_bars(pyplot, metrics: List[tuple], output_path: Path) -> None:
    labels = [label for label, _ in metrics]
    values = [float(value) for _, value in metrics]
    figure, axis = pyplot.subplots(figsize=(8, 4.5))
    axis.bar(labels, values, color='#54A24B')
    axis.set_title('Metric comparison')
    axis.set_ylabel('Value')
    axis.set_ylim(bottom=min(0.0, min(values) - 0.05), top=max(values) + 0.1 if values else 1.0)
    axis.tick_params(axis='x', rotation=30)
    for index, value in enumerate(values):
        axis.text(index, value, _format_number(value), ha='center', va='bottom', fontsize=8)
    figure.tight_layout()
    figure.savefig(output_path)
    pyplot.close(figure)


def _render_summary_card(pyplot, rows: Iterable[tuple], output_path: Path, *, title: str) -> None:
    text_rows = ['{0}: {1}'.format(label, _format_scalar(value)) for label, value in rows]
    figure, axis = pyplot.subplots(figsize=(8, 4.5))
    axis.axis('off')
    axis.set_title(title)
    axis.text(
        0.02,
        0.98,
        '\n'.join(text_rows),
        transform=axis.transAxes,
        va='top',
        ha='left',
        fontsize=10,
        bbox={'boxstyle': 'round', 'facecolor': 'white', 'alpha': 0.95},
    )
    figure.tight_layout()
    figure.savefig(output_path)
    pyplot.close(figure)


def _annotate_score_stats(axis, scores: List[float], score_column: str) -> None:
    if not scores:
        return
    ordered = sorted(scores)
    count = len(ordered)
    median = ordered[count // 2] if count % 2 == 1 else (ordered[(count // 2) - 1] + ordered[count // 2]) / 2.0
    summary = '\n'.join([
        'Column: {0}'.format(score_column),
        'Count: {0}'.format(count),
        'Min: {0}'.format(_format_number(min(ordered))),
        'Median: {0}'.format(_format_number(median)),
        'Max: {0}'.format(_format_number(max(ordered))),
    ])
    axis.text(
        0.02,
        0.98,
        summary,
        transform=axis.transAxes,
        va='top',
        ha='left',
        fontsize=9,
        bbox={'boxstyle': 'round', 'facecolor': 'white', 'alpha': 0.9},
    )


def _figure_record(*, figure_id: str, title: str, caption: str, path: Path, kind: str) -> Dict[str, Any]:
    return {
        'id': figure_id,
        'title': title,
        'caption': caption,
        'path': str(path).replace('\\', '/'),
        'kind': kind,
    }


def _numeric_items(mapping: Mapping[str, Any]) -> List[tuple]:
    preferred_order = ['precision', 'recall', 'f1', 'fpr', 'flag_rate', 'accuracy']
    seen = set()
    items: List[tuple] = []
    for key in preferred_order:
        value = mapping.get(key) if isinstance(mapping, Mapping) else None
        numeric = _optional_float(value)
        if numeric is None:
            continue
        seen.add(key)
        items.append((key, numeric))
    if isinstance(mapping, Mapping):
        for key in sorted(mapping.keys()):
            if key in seen:
                continue
            numeric = _optional_float(mapping.get(key))
            if numeric is None:
                continue
            items.append((str(key), numeric))
    return items


def _has_confusion_counts(counts: Mapping[str, Any]) -> bool:
    required = {'tp', 'fp', 'tn', 'fn'}
    return isinstance(counts, Mapping) and required.issubset(set(counts.keys()))


def _optional_float(value: Any) -> Optional[float]:
    if value in ('', None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int:
    if value in ('', None):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _format_number(value: Any) -> str:
    numeric = _optional_float(value)
    if numeric is None:
        return ''
    return '{0:.6g}'.format(float(numeric))


def _format_int(value: Any) -> str:
    if value in ('', None):
        return ''
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def _format_scalar(value: Any) -> str:
    numeric = _optional_float(value)
    if numeric is not None:
        return _format_number(numeric)
    return str(value)


def json_dumps(payload: Mapping[str, Any]) -> str:
    normalized = _normalize_json_value(payload)
    import json

    return json.dumps(normalized, indent=2, sort_keys=True)


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value).replace('\\', '/')
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_json_value(item) for item in value]
    return value
