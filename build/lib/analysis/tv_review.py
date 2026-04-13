from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Sequence, Tuple

from ._util import iter_jsonl, stable_record_id


DEFAULT_REVIEW_INVENTORY_FILENAME = 'tv_review_inventory.csv'
DEFAULT_SUGGESTED_LABELS_FILENAME = 'tv_suggested_labels.csv'


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or '').strip().lower()
    return text in {'1', 'true', 'yes', 'y'}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _iso_text(value: Any) -> str:
    return str(value or '').strip()


def _iter_records(input_paths: Sequence[Path]) -> Iterator[Dict[str, Any]]:
    for input_path in input_paths:
        for row in iter_jsonl(Path(input_path)):
            if row.obj is None or row.error is not None:
                continue
            if isinstance(row.obj, dict):
                yield row.obj


def classify_row(record: Dict[str, Any]) -> Tuple[str, str, List[str]]:
    has_code_block = _safe_bool(record.get('has_code_block')) or _safe_int(record.get('code_block_count')) > 0
    has_link = _safe_bool(record.get('has_link')) or _safe_int(record.get('link_count')) > 0
    f_toxicity = _safe_int(record.get('f_toxicity'))
    prompt_injection_score = _safe_int(record.get('prompt_injection_score'))
    matched_pattern_count = _safe_int(record.get('matched_pattern_count'))
    contains_ignore_previous = _safe_bool(record.get('contains_ignore_previous'))
    contains_system_prompt_reference = _safe_bool(record.get('contains_system_prompt_reference'))
    contains_developer_message_reference = _safe_bool(record.get('contains_developer_message_reference'))
    contains_env_var_reference = _safe_bool(record.get('contains_env_var_reference'))
    question_count = _safe_int(record.get('question_count'))
    exclamation_count = _safe_int(record.get('exclamation_count'))
    line_count = _safe_int(record.get('line_count'))
    content_length = _safe_int(record.get('content_length'))
    content_length_words = _safe_int(record.get('content_length_words'))
    f_complexity = _safe_float(record.get('f_complexity'))
    f_code_density = _safe_float(record.get('f_code_density'))

    high_risk_signals: List[str] = []
    benign_guardrails: List[str] = []

    if contains_ignore_previous:
        high_risk_signals.append('contains_ignore_previous')
    if contains_system_prompt_reference:
        high_risk_signals.append('contains_system_prompt_reference')
    if contains_developer_message_reference:
        high_risk_signals.append('contains_developer_message_reference')
    if contains_env_var_reference:
        high_risk_signals.append('contains_env_var_reference')
    if prompt_injection_score >= 1:
        high_risk_signals.append('prompt_injection_score>=1')
    if matched_pattern_count >= 1:
        high_risk_signals.append('matched_pattern_count>=1')
    if f_toxicity >= 1:
        high_risk_signals.append('f_toxicity>=1')
    if has_link and _safe_int(record.get('link_count')) >= 1:
        high_risk_signals.append('has_link')
    if has_code_block:
        high_risk_signals.append('has_code_block')

    prompt_attack = any(
        [
            contains_ignore_previous,
            contains_system_prompt_reference,
            contains_developer_message_reference,
            contains_env_var_reference,
        ]
    )
    compound_pattern_risk = bool(
        prompt_injection_score >= 1
        and (has_link or has_code_block or matched_pattern_count >= 1 or line_count >= 20)
    )
    hostile_contact_risk = bool(
        f_toxicity >= 1
        and (has_link or has_code_block or question_count >= 1 or content_length >= 1000 or line_count >= 10)
    )

    if prompt_attack or compound_pattern_risk or hostile_contact_risk:
        rationale = ' / '.join(high_risk_signals) if high_risk_signals else 'compound high-risk metadata pattern'
        return 'TV-3', rationale, high_risk_signals

    if not has_code_block:
        benign_guardrails.append('no_code_block')
    if not has_link:
        benign_guardrails.append('no_link')
    if f_toxicity == 0:
        benign_guardrails.append('f_toxicity==0')
    if prompt_injection_score == 0:
        benign_guardrails.append('prompt_injection_score==0')
    if matched_pattern_count == 0:
        benign_guardrails.append('matched_pattern_count==0')
    if not contains_ignore_previous:
        benign_guardrails.append('no_ignore_previous')
    if not contains_system_prompt_reference:
        benign_guardrails.append('no_system_prompt_reference')
    if not contains_developer_message_reference:
        benign_guardrails.append('no_developer_message_reference')
    if not contains_env_var_reference:
        benign_guardrails.append('no_env_var_reference')

    benign_enough = bool(
        not has_code_block
        and not has_link
        and f_toxicity == 0
        and prompt_injection_score == 0
        and matched_pattern_count == 0
        and not contains_ignore_previous
        and not contains_system_prompt_reference
        and not contains_developer_message_reference
        and not contains_env_var_reference
        and f_complexity <= 0.05
        and f_code_density <= 0.05
        and line_count <= 20
        and question_count <= 1
        and exclamation_count <= 1
        and content_length_words <= 700
        and content_length <= 3500
    )
    if benign_enough:
        rationale = ' / '.join(benign_guardrails)
        return 'TV-0', rationale, benign_guardrails

    rationale = 'metadata insufficient for bounded TV-0/TV-3 decision'
    return '', rationale, high_risk_signals + benign_guardrails


def summarize_records(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    signal_counter: Counter[str] = Counter()
    label_counter: Counter[str] = Counter()
    occurrence_counter: Counter[str] = Counter()
    unique_rows: List[Dict[str, Any]] = []
    first_by_record_id: Dict[str, Dict[str, Any]] = {}
    last_ts_by_record_id: Dict[str, str] = {}

    total_rows = 0
    for record in records:
        total_rows += 1
        record_id = stable_record_id(record)
        occurrence_counter[record_id] += 1
        if record_id not in first_by_record_id:
            first_by_record_id[record_id] = dict(record)
        last_ts_by_record_id[record_id] = _iso_text(record.get('ts') or record.get('timestamp'))

    for record_id, record in first_by_record_id.items():
        suggested_tv_id, rationale, signals = classify_row(record)
        label_counter[suggested_tv_id or 'unlabeled'] += 1
        for signal in signals:
            signal_counter[signal] += 1
        unique_rows.append(
            {
                'record_id': record_id,
                'source_id_hash': _iso_text(record.get('source_id_hash')),
                'occurrence_count': int(occurrence_counter[record_id]),
                'first_seen_ts': _iso_text(record.get('ts') or record.get('timestamp')),
                'last_seen_ts': last_ts_by_record_id.get(record_id, ''),
                'timestamp': _iso_text(record.get('timestamp')),
                'type': _iso_text(record.get('type')),
                'content_length': _safe_int(record.get('content_length')),
                'content_length_words': _safe_int(record.get('content_length_words')),
                'has_code_block': int(_safe_bool(record.get('has_code_block'))),
                'code_block_count': _safe_int(record.get('code_block_count')),
                'has_link': int(_safe_bool(record.get('has_link'))),
                'link_count': _safe_int(record.get('link_count')),
                'tags_count': _safe_int(record.get('tags_count')),
                'mentions_count': _safe_int(record.get('mentions_count')),
                'line_count': _safe_int(record.get('line_count')),
                'question_count': _safe_int(record.get('question_count')),
                'exclamation_count': _safe_int(record.get('exclamation_count')),
                'contains_ignore_previous': int(_safe_bool(record.get('contains_ignore_previous'))),
                'contains_system_prompt_reference': int(_safe_bool(record.get('contains_system_prompt_reference'))),
                'contains_developer_message_reference': int(_safe_bool(record.get('contains_developer_message_reference'))),
                'contains_env_var_reference': int(_safe_bool(record.get('contains_env_var_reference'))),
                'prompt_injection_score': _safe_int(record.get('prompt_injection_score')),
                'matched_pattern_count': _safe_int(record.get('matched_pattern_count')),
                'f_complexity': _safe_float(record.get('f_complexity')),
                'f_code_density': _safe_float(record.get('f_code_density')),
                'f_toxicity': _safe_int(record.get('f_toxicity')),
                'suggested_tv_id': suggested_tv_id,
                'suggested_rationale': rationale,
            }
        )

    unique_rows.sort(
        key=lambda row: (
            0 if row['suggested_tv_id'] == 'TV-3' else 1 if row['suggested_tv_id'] == '' else 2,
            -int(row['occurrence_count']),
            str(row['record_id']),
        )
    )
    duplicate_row_count = total_rows - len(unique_rows)
    duplicate_unique_record_count = sum(1 for count in occurrence_counter.values() if count > 1)

    return {
        'total_rows': int(total_rows),
        'unique_record_count': int(len(unique_rows)),
        'duplicate_row_count': int(duplicate_row_count),
        'duplicate_unique_record_count': int(duplicate_unique_record_count),
        'label_counts_unique': dict(label_counter),
        'top_signals': dict(signal_counter.most_common(20)),
        'unique_rows': unique_rows,
    }


def write_review_inventory(
    output_dir: Path,
    unique_rows: List[Dict[str, Any]],
    *,
    filename: str = DEFAULT_REVIEW_INVENTORY_FILENAME,
) -> Path:
    path = output_dir / str(filename)
    fieldnames = list(unique_rows[0].keys()) if unique_rows else [
        'record_id',
        'source_id_hash',
        'occurrence_count',
        'first_seen_ts',
        'last_seen_ts',
        'timestamp',
        'type',
        'content_length',
        'content_length_words',
        'has_code_block',
        'code_block_count',
        'has_link',
        'link_count',
        'tags_count',
        'mentions_count',
        'line_count',
        'question_count',
        'exclamation_count',
        'contains_ignore_previous',
        'contains_system_prompt_reference',
        'contains_developer_message_reference',
        'contains_env_var_reference',
        'prompt_injection_score',
        'matched_pattern_count',
        'f_complexity',
        'f_code_density',
        'f_toxicity',
        'suggested_tv_id',
        'suggested_rationale',
    ]
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in unique_rows:
            writer.writerow(row)
    return path


def write_suggested_labels(
    output_dir: Path,
    unique_rows: List[Dict[str, Any]],
    *,
    filename: str = DEFAULT_SUGGESTED_LABELS_FILENAME,
) -> Path:
    path = output_dir / str(filename)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['record_id', 'tv_id'])
        for row in unique_rows:
            tv_id = str(row.get('suggested_tv_id', '') or '').strip()
            if not tv_id:
                continue
            writer.writerow([row.get('record_id', ''), tv_id])
    return path


def count_suggested_labels(unique_rows: List[Dict[str, Any]]) -> int:
    return sum(1 for row in unique_rows if str(row.get('suggested_tv_id', '') or '').strip())


def run_tv_review(
    input_paths: Sequence[Path],
    output_dir: Path,
    *,
    inventory_filename: str = DEFAULT_REVIEW_INVENTORY_FILENAME,
    suggested_labels_filename: str = DEFAULT_SUGGESTED_LABELS_FILENAME,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_inputs = [Path(path) for path in input_paths]
    summary = summarize_records(_iter_records(normalized_inputs))
    unique_rows = list(summary.pop('unique_rows', []))
    review_inventory_path = write_review_inventory(
        output_dir,
        unique_rows,
        filename=inventory_filename,
    )
    suggested_labels_path = write_suggested_labels(
        output_dir,
        unique_rows,
        filename=suggested_labels_filename,
    )
    labeled_unique_count = count_suggested_labels(unique_rows)
    return {
        'input_paths': [str(path).replace('\\', '/') for path in normalized_inputs],
        'review_inventory_csv': str(review_inventory_path).replace('\\', '/'),
        'suggested_labels_csv': str(suggested_labels_path).replace('\\', '/'),
        'labeled_unique_count': int(labeled_unique_count),
        **summary,
    }


def apply_suggested_labels_to_dataset_manifest(
    dataset_manifest_path: Path,
    suggested_labels_path: Path,
    *,
    labeled_unique_count: int,
) -> Dict[str, Any]:
    manifest_path = Path(dataset_manifest_path)
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('dataset manifest is not a JSON object after materialization')

    if int(labeled_unique_count) <= 0:
        return {
            'manifest_updated': False,
            'labels_applied': False,
            'labels_csv': str(payload.get('labels_csv', '') or ''),
            'has_labels': bool(payload.get('has_labels', False)),
        }

    source_path = Path(suggested_labels_path)
    if not source_path.exists():
        raise FileNotFoundError('suggested labels file not found: {0}'.format(source_path))

    labels_path = manifest_path.parent / 'labels.csv'
    if str(source_path.resolve()) != str(labels_path.resolve()):
        shutil.copy2(source_path, labels_path)
    payload['labels_csv'] = str(labels_path).replace('\\', '/')
    payload['has_labels'] = True
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return {
        'manifest_updated': True,
        'labels_applied': True,
        'labels_csv': str(labels_path).replace('\\', '/'),
        'has_labels': True,
    }


__all__ = [
    'DEFAULT_REVIEW_INVENTORY_FILENAME',
    'DEFAULT_SUGGESTED_LABELS_FILENAME',
    'apply_suggested_labels_to_dataset_manifest',
    'classify_row',
    'count_suggested_labels',
    'run_tv_review',
    'summarize_records',
    'write_review_inventory',
    'write_suggested_labels',
]