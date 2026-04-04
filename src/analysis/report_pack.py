from __future__ import annotations

from collections.abc import Mapping as MappingABC
import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ._util import (
    canonical_ds_workflow_name,
    collect_git_provenance,
    default_analysis_dir,
    default_run_id,
    default_run_root,
    ds_indexes_dir,
    find_project_root,
    normalize_repo_or_absolute_path,
    sanitize_run_id,
)


REPORT_SCHEMA_VERSION = '1.0'
WORKFLOW_ARTIFACT_DIRS = {
    'build': ('dataset',),
    'train': ('model',),
    'evaluate': ('evaluation',),
    'score': ('scoring',),
    'demo': ('dataset', 'models', 'evaluation'),
    'pipeline': ('dataset', 'models', 'evaluation', 'scoring'),
}
WORKFLOW_CATEGORIES = {
    'build': 'dataset-build',
    'train': 'model-train',
    'evaluate': 'model-eval',
    'score': 'model-eval',
    'demo': 'pipeline-run',
    'pipeline': 'pipeline-run',
}
WORKFLOW_TITLES = {
    'build': 'Dataset Build',
    'train': 'Model Training',
    'evaluate': 'Evaluation',
    'score': 'Scoring',
    'demo': 'Demo Pipeline',
    'pipeline': 'Pipeline',
}
WORKFLOW_PACKET_ROLES = {
    'build': 'processing-stage packet',
    'train': 'processing-stage packet',
    'evaluate': 'processing-stage packet',
    'score': 'processing-stage packet',
    'demo': 'composite workflow packet',
    'pipeline': 'composite workflow packet',
}
WORKFLOW_PURPOSES = {
    'build': 'This packet explains how the current observer evidence was shaped into an analysis-ready dataset for downstream model work.',
    'train': 'This packet explains how the current dataset was turned into a trained model and what fitting posture the run recorded.',
    'evaluate': 'This packet explains how the current model output was translated into evaluation evidence and threshold posture.',
    'score': 'This packet explains how the current score surface was turned into a review-ready ordering of records.',
    'demo': 'This packet summarizes a composite demo chain so a reader can move from the headline outcome into the stage-specific evidence without treating the Markdown as machine authority.',
    'pipeline': 'This packet summarizes the end-to-end pipeline so a reader can move from the headline outcome into the stage-specific evidence without treating the Markdown as machine authority.',
}
WORKFLOW_LIMIT_NOTES = {
    'build': 'Build packets explain dataset construction and handoff posture; they do not establish model quality on their own.',
    'train': 'Training packets explain fit posture and produced model artifacts; they do not by themselves establish deployment readiness.',
    'evaluate': 'Evaluation packets explain threshold and assessment posture; they should be read with care when labels are absent or partial.',
    'score': 'Score packets rank or separate records for review; they do not assign semantic intent to the flagged set.',
    'demo': 'Composite workflow packets summarize multiple stages at once; inspect the listed artifacts before treating them as a single-stage conclusion.',
    'pipeline': 'Composite workflow packets summarize multiple stages at once; inspect the listed artifacts before treating them as a single-stage conclusion.',
}
WORKFLOW_NEXT_STEP_HINTS = {
    'build': 'Read the dataset artifacts first, then move to the downstream training or evaluation surfaces that consume this dataset.',
    'train': 'Read the model and evaluation companions next so the fitting posture can be interpreted through downstream performance evidence.',
    'evaluate': 'Read the threshold companions and then move to the score-stage surfaces that show the resulting review posture.',
    'score': 'Read the scoring companions and threshold context next so the selected review set can be interpreted in context.',
    'demo': 'Use the machine-readable companions and listed artifacts to drill into the stage-specific outputs that the composite demo chain produced.',
    'pipeline': 'Use the machine-readable companions and listed artifacts to drill into the stage-specific outputs that the composite pipeline produced.',
}
PACKET_RESULT_EXCLUDED_FIELDS = {
    'timestamp_utc',
    'runtime_cli_surface',
    'action',
    'command_family',
    'command_path',
    'implementation_state',
    'underlying_surface',
    'summary',
    'decision',
    'artifacts',
    'run_id',
    'collection_alias',
}


@dataclass
class ReportBundlePaths:
    project_root: Path
    analysis_root: Path
    indexes_dir: Path
    workflow: str
    run_id: str
    run_root: Path
    report_dir: Path
    artifact_dirs: Dict[str, Path]
    run_root_policy: str


def prepare_report_bundle(
    project_anchor: Path,
    workflow: str,
    *,
    explicit_run_root: Optional[Path] = None,
    run_id: str = '',
) -> ReportBundlePaths:
    project_root = find_project_root(project_anchor)
    analysis_root = default_analysis_dir(project_anchor)
    workflow_name = canonical_ds_workflow_name(workflow)
    resolved_run_id = sanitize_run_id(run_id) or default_run_id(workflow_name)
    if explicit_run_root is None:
        run_root = default_run_root(project_anchor, workflow_name, resolved_run_id)
        run_root_policy = 'canonical'
    else:
        run_root = Path(explicit_run_root).resolve()
        run_root_policy = 'explicit-override'
    artifact_dirs = {
        name: run_root / name
        for name in WORKFLOW_ARTIFACT_DIRS.get(workflow_name, ())
    }
    return ReportBundlePaths(
        project_root=project_root,
        analysis_root=analysis_root,
        indexes_dir=ds_indexes_dir(project_anchor),
        workflow=workflow_name,
        run_id=resolved_run_id,
        run_root=run_root,
        report_dir=run_root / 'report',
        artifact_dirs=artifact_dirs,
        run_root_policy=run_root_policy,
    )


def write_report_bundle(
    *,
    project_anchor: Path,
    bundle: ReportBundlePaths,
    packet: Dict[str, Any],
    artifact_paths: Optional[Mapping[str, Optional[Path]]] = None,
    context: Optional[Mapping[str, Any]] = None,
    lineage: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    project_root = find_project_root(project_anchor)
    bundle.run_root.mkdir(parents=True, exist_ok=True)
    bundle.report_dir.mkdir(parents=True, exist_ok=True)

    report_json_path = bundle.report_dir / 'report.json'
    report_md_path = bundle.report_dir / 'report.md'
    manifest_path = bundle.report_dir / 'manifest.json'

    normalized_artifacts = _normalize_json_value(dict(artifact_paths or {}), project_root)
    normalized_context = _normalize_json_value(dict(context or {}), project_root)
    normalized_lineage = _normalize_json_value(dict(lineage or {}), project_root)
    normalized_artifact_dirs = _normalize_json_value(dict(bundle.artifact_dirs), project_root)
    result_payload = _packet_result_payload(packet, project_root)
    timestamp_utc = str(packet.get('timestamp_utc') or '').strip() or packet.get('created_at_utc') or ''
    if not timestamp_utc:
        from ._util import utc_now_iso

        timestamp_utc = utc_now_iso()

    report_paths = {
        'markdown': normalize_repo_or_absolute_path(report_md_path, project_root),
        'json': normalize_repo_or_absolute_path(report_json_path, project_root),
        'manifest': normalize_repo_or_absolute_path(manifest_path, project_root),
    }
    run_root_path = normalize_repo_or_absolute_path(bundle.run_root, project_root)
    report_dir_path = normalize_repo_or_absolute_path(bundle.report_dir, project_root)

    report_payload = {
        'schema_version': REPORT_SCHEMA_VERSION,
        'workflow': bundle.workflow,
        'run_id': bundle.run_id,
        'collection_alias': str(packet.get('collection_alias', '') or '').strip(),
        'timestamp_utc': timestamp_utc,
        'decision': str(packet.get('decision', '')),
        'summary': str(packet.get('summary', '')),
        'runtime_cli_surface': str(packet.get('runtime_cli_surface', 'observerctl')),
        'command_family': str(packet.get('command_family', 'ds')),
        'command_path': str(packet.get('command_path', '')),
        'implementation_state': str(packet.get('implementation_state', '')),
        'underlying_surface': str(packet.get('underlying_surface', '')),
        'run_root': run_root_path,
        'report_dir': report_dir_path,
        'report_paths': report_paths,
        'artifacts': normalized_artifacts,
        'context': normalized_context,
        'result': result_payload,
        'lineage': normalized_lineage,
    }
    manifest_payload = {
        'schema_version': REPORT_SCHEMA_VERSION,
        'kind': 'run',
        'family_id': 'ds_run',
        'category': WORKFLOW_CATEGORIES.get(bundle.workflow, 'ds-run'),
        'workflow': bundle.workflow,
        'run_id': bundle.run_id,
        'collection_alias': str(packet.get('collection_alias', '') or '').strip(),
        'timestamp_utc': timestamp_utc,
        'producer_command': str(packet.get('command_path', '')),
        'producer_entrypoint': 'projects/calamum-moltbook-observer/src/observerctl.py',
        'runtime_cli_surface': str(packet.get('runtime_cli_surface', 'observerctl')),
        'action': str(packet.get('action', '')),
        'summary': str(packet.get('summary', '')),
        'decision': str(packet.get('decision', '')),
        'implementation_state': str(packet.get('implementation_state', '')),
        'underlying_surface': str(packet.get('underlying_surface', '')),
        'run_root_policy': bundle.run_root_policy,
        'analysis_root': normalize_repo_or_absolute_path(bundle.analysis_root, project_root),
        'indexes_dir': normalize_repo_or_absolute_path(bundle.indexes_dir, project_root),
        'run_root': run_root_path,
        'report_dir': report_dir_path,
        'report_paths': report_paths,
        'artifact_dirs': normalized_artifact_dirs,
        'artifacts': normalized_artifacts,
        'context': normalized_context,
        'result': result_payload,
        'lineage': normalized_lineage,
        'git': collect_git_provenance(project_root),
    }

    report_json_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding='utf-8')
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True), encoding='utf-8')
    report_md_path.write_text(_report_markdown(report_payload, project_root=project_root, report_md_path=report_md_path), encoding='utf-8')

    return {
        'paths': {
            'run_root': run_root_path,
            'report_dir': report_dir_path,
            'report_json': report_paths['json'],
            'report_md': report_paths['markdown'],
            'manifest_json': report_paths['manifest'],
        },
        'report': report_payload,
        'manifest': manifest_payload,
    }


def _packet_result_payload(packet: Mapping[str, Any], project_root: Path) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for key, value in packet.items():
        if key in PACKET_RESULT_EXCLUDED_FIELDS:
            continue
        payload[str(key)] = _normalize_json_value(value, project_root)
    return payload


def _normalize_json_value(value: Any, project_root: Path) -> Any:
    if isinstance(value, Path):
        return normalize_repo_or_absolute_path(value, project_root)
    if isinstance(value, str):
        return _normalize_string_path(value, project_root)
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item, project_root) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_json_value(item, project_root) for item in value]
    return value


def _normalize_string_path(value: str, project_root: Path) -> str:
    text = str(value or '')
    if not text:
        return text
    if not _looks_like_path(text):
        return text

    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = project_root / candidate

    try:
        if candidate.exists():
            return normalize_repo_or_absolute_path(candidate, project_root)
    except Exception:
        return text

    try:
        resolved_candidate = candidate.resolve()
        resolved_root = Path(project_root).resolve()
        resolved_candidate.relative_to(resolved_root)
        return normalize_repo_or_absolute_path(resolved_candidate, project_root)
    except Exception:
        return text


def _looks_like_path(text: str) -> bool:
    value = str(text or '').strip()
    if not value:
        return False
    if value.startswith('file://'):
        return False
    return os.path.isabs(value) or '/' in value or '\\' in value


def _report_markdown(report_payload: Mapping[str, Any], *, project_root: Path, report_md_path: Path) -> str:
    workflow = str(report_payload.get('workflow', 'run'))
    title = WORKFLOW_TITLES.get(workflow, workflow.replace('-', ' ').title())
    packet_role = WORKFLOW_PACKET_ROLES.get(workflow, 'analysis packet')
    result_payload = report_payload.get('result', {}) if isinstance(report_payload.get('result', {}), MappingABC) else {}
    result_without_visuals = {key: value for key, value in result_payload.items() if str(key) != 'visuals'}
    decision = str(report_payload.get('decision', '') or '').strip()
    runtime_cli_surface = str(report_payload.get('runtime_cli_surface', '') or '').strip()
    command_path = str(report_payload.get('command_path', '') or '').strip()
    summary = str(report_payload.get('summary', '') or '').strip()
    collection_alias = str(report_payload.get('collection_alias', '') or '').strip()
    lines = [
        '# {0} packet — {1}'.format(title, str(report_payload.get('run_id', ''))),
        '',
        '**Decision**: `{0}`'.format(decision or 'unknown'),
        '**Workflow**: `{0}`'.format(workflow),
        '**Created (UTC)**: `{0}`'.format(str(report_payload.get('timestamp_utc', ''))),
    ]
    if collection_alias:
        lines.append('**Collection alias**: `{0}`'.format(collection_alias))
    if runtime_cli_surface:
        lines.append('**Runtime CLI surface**: `{0}`'.format(runtime_cli_surface))
    if command_path:
        lines.append('**Command path**: `{0}`'.format(command_path))
    lines.extend([
        '',
        '## Executive summary',
        '',
        summary or 'No summary was recorded for this run.',
        '',
    ])
    _append_narrative_section(lines, 'Why this packet exists', _workflow_purpose_text(workflow, collection_alias))
    _append_scalar_table(
        lines,
        'Run snapshot',
        {
            'collection_alias': collection_alias,
            'run_id': report_payload.get('run_id', ''),
            'workflow': workflow,
            'packet_role': packet_role,
            'decision': decision,
            'created_utc': report_payload.get('timestamp_utc', ''),
            'runtime_cli_surface': runtime_cli_surface,
            'command_path': command_path,
        },
    )
    _append_scalar_table(lines, 'Context', report_payload.get('context', {}))
    _append_narrative_section(lines, 'What this packet shows', _workflow_evidence_summary_text(workflow, decision, result_payload))
    _append_result_section(lines, result_without_visuals)
    _append_visuals(lines, result_payload, project_root=project_root, report_md_path=report_md_path)
    _append_bullet_section(lines, 'Limits and cautions', _workflow_limit_items(workflow, decision, result_payload))
    _append_provenance_section(lines, report_payload.get('lineage', {}))
    _append_path_table(
        lines,
        'Artifact index',
        report_payload.get('artifacts', {}),
        key_label='Artifact',
        intro_text='These are the primary run-local artifacts referenced by the packet narrative.',
    )
    _append_path_table(
        lines,
        'Report paths',
        report_payload.get('report_paths', {}),
        key_label='Surface',
        intro_text='These companion surfaces carry the serialized Markdown and JSON outputs for the same run.',
    )
    _append_next_steps_section(
        lines,
        report_payload,
        project_root=project_root,
        report_md_path=report_md_path,
    )
    return '\n'.join(lines).rstrip() + '\n'


def _append_narrative_section(lines: list[str], title: str, body: str) -> None:
    text = str(body or '').strip()
    if not text:
        return
    lines.append('## {0}'.format(title))
    lines.append('')
    lines.append(text)
    lines.append('')


def _append_bullet_section(lines: list[str], title: str, items: list[str]) -> None:
    normalized = [str(item).strip() for item in items if str(item or '').strip()]
    if not normalized:
        return
    lines.append('## {0}'.format(title))
    lines.append('')
    for item in normalized:
        lines.append('- {0}'.format(item))
    lines.append('')


def _workflow_purpose_text(workflow: str, collection_alias: str) -> str:
    purpose = WORKFLOW_PURPOSES.get(
        workflow,
        'This packet explains the current run in reader-facing language while keeping the machine-readable companions intact.',
    )
    alias = str(collection_alias or '').strip()
    if not alias:
        return purpose
    return '{0} It is associated with the `{1}` collection alias.'.format(purpose, alias)


def _workflow_evidence_summary_text(workflow: str, decision: str, result_payload: Mapping[str, Any]) -> str:
    role = WORKFLOW_PACKET_ROLES.get(workflow, 'analysis packet')
    counts = result_payload.get('counts', {}) if isinstance(result_payload.get('counts', {}), MappingABC) else {}
    metrics = result_payload.get('metrics', {}) if isinstance(result_payload.get('metrics', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    visuals = result_payload.get('visuals', {}) if isinstance(result_payload.get('visuals', {}), MappingABC) else {}
    workflow_steps = result_payload.get('workflow_steps', []) if isinstance(result_payload.get('workflow_steps', []), (list, tuple, set)) else []
    reason_codes = _normalized_strings(result_payload.get('reason_codes', []))

    sentences = [_decision_summary_sentence(role, decision)]

    count_sentence = _count_summary_sentence(counts, thresholding)
    if count_sentence:
        sentences.append(count_sentence)

    metric_sentence = _metric_summary_sentence(metrics)
    if metric_sentence:
        sentences.append(metric_sentence)

    threshold_sentence = _threshold_summary_sentence(result_payload, thresholding)
    if threshold_sentence:
        sentences.append(threshold_sentence)

    if workflow in {'demo', 'pipeline'} and workflow_steps:
        sentences.append(
            'The packet records the following workflow steps: `{0}`.'.format('`, `'.join(str(step) for step in workflow_steps))
        )

    figure_count = int(visuals.get('figure_count', 0) or 0)
    if figure_count > 0:
        sentences.append(
            'The packet also carries {0} declared figure{1} so the visual evidence stays tied to the same run contract.'.format(
                figure_count,
                '' if figure_count == 1 else 's',
            )
        )

    if reason_codes:
        sentences.append(
            'Current guardrails are captured in {0} reason code{1}.'.format(
                len(reason_codes),
                '' if len(reason_codes) == 1 else 's',
            )
        )
    elif str(decision or '').strip().lower() == 'go':
        sentences.append('No blocking reason codes were recorded for this packet.')

    return ' '.join(sentence for sentence in sentences if str(sentence or '').strip())


def _decision_summary_sentence(role: str, decision: str) -> str:
    normalized_decision = str(decision or '').strip().lower()
    if normalized_decision == 'go':
        return 'This {0} currently reports a `go` decision and should be read as a usable handoff within the DS reporting spine.'.format(role)
    if normalized_decision:
        return 'This {0} currently reports a `{1}` decision and should be read as a blocked or conditional handoff until the cited guardrails are resolved.'.format(role, normalized_decision)
    return 'This packet does not record a final decision state, so the reader should treat it as an incomplete handoff summary.'


def _count_summary_sentence(counts: Mapping[str, Any], thresholding: Mapping[str, Any]) -> str:
    threshold_flagged = thresholding.get('flagged_records')
    threshold_total = thresholding.get('records_scored') or thresholding.get('records_evaluated')
    if threshold_flagged not in ('', None) and threshold_total not in ('', None):
        return 'The packet summarizes `{0}` flagged records out of `{1}` scored records.'.format(
            _format_countish(threshold_flagged),
            _format_countish(threshold_total),
        )
    confusion_keys = ('tp', 'fp', 'tn', 'fn')
    if any(key in counts for key in confusion_keys):
        available = [
            '{0}={1}'.format(_friendly_label(key), _format_countish(counts.get(key)))
            for key in confusion_keys
            if counts.get(key) not in ('', None)
        ]
        if available:
            return 'The packet records confusion-style count evidence for {0}.'.format(', '.join(available))
    if counts:
        first_key = next(iter(counts.keys()))
        return 'Count-level evidence is present, including `{0}` = `{1}`.'.format(
            str(first_key),
            _format_countish(counts[first_key]),
        )
    return ''


def _metric_summary_sentence(metrics: Mapping[str, Any]) -> str:
    ordered_keys = [key for key in ('precision', 'recall', 'f1', 'fpr', 'flag_rate') if key in metrics and metrics.get(key) not in ('', None)]
    if not ordered_keys:
        ordered_keys = [str(key) for key, value in metrics.items() if value not in ('', None)][:3]
    if not ordered_keys:
        return ''
    return 'Primary metric evidence is available for {0}.'.format(
        ', '.join(
            '{0}={1}'.format(_friendly_label(str(key)), _format_countish(metrics.get(key)))
            for key in ordered_keys
        )
    )


def _threshold_summary_sentence(result_payload: Mapping[str, Any], thresholding: Mapping[str, Any]) -> str:
    threshold = thresholding.get('threshold')
    flag_rule = str(thresholding.get('flag_rule', '') or '').strip()
    anomaly_direction = str(
        thresholding.get('anomaly_direction', '')
        or result_payload.get('anomaly_direction', '')
        or result_payload.get('score_column', '')
    ).strip()
    target_fpr = thresholding.get('target_fpr')
    actual_fpr = thresholding.get('actual_fpr')
    if threshold in ('', None) and not anomaly_direction and target_fpr in ('', None) and actual_fpr in ('', None):
        return ''
    parts = []
    if threshold not in ('', None):
        parts.append('Threshold posture is recorded at `{0}`'.format(_format_countish(threshold)))
    else:
        parts.append('Threshold posture is recorded for this packet')
    if anomaly_direction:
        parts.append('using `{0}`'.format(anomaly_direction))
    if flag_rule:
        parts.append('with rule `{0}`'.format(flag_rule))
    sentence = ' '.join(parts) + '.'
    if target_fpr not in ('', None) or actual_fpr not in ('', None):
        sentence += ' Guardrail context: target FPR `{0}`, actual FPR `{1}`.'.format(
            _format_countish(target_fpr),
            _format_countish(actual_fpr),
        )
    return sentence


def _workflow_limit_items(workflow: str, decision: str, result_payload: Mapping[str, Any]) -> list[str]:
    items = [
        WORKFLOW_LIMIT_NOTES.get(
            workflow,
            'This packet is scoped to one run and should be interpreted within its workflow context rather than as a whole-system readiness claim.',
        )
    ]
    if result_payload.get('has_labels') is False:
        items.append('This packet is operating without labels, so threshold and flagged-share values should be read as review posture rather than verified labeled error rates.')
    reason_codes = _normalized_strings(result_payload.get('reason_codes', []))
    if reason_codes:
        items.append('Current reason codes: {0}.'.format(', '.join('`{0}`'.format(code) for code in reason_codes)))
    normalized_decision = str(decision or '').strip().lower()
    if normalized_decision and normalized_decision != 'go':
        items.append('The current packet decision is `{0}`, so downstream interpretation should remain conditional on that state.'.format(normalized_decision))
    return items


def _append_next_steps_section(
    lines: list[str],
    report_payload: Mapping[str, Any],
    *,
    project_root: Path,
    report_md_path: Path,
) -> None:
    workflow = str(report_payload.get('workflow', 'run') or 'run')
    lines.append('## Reader next steps')
    lines.append('')
    lines.append(
        WORKFLOW_NEXT_STEP_HINTS.get(
            workflow,
            'Use the companion JSON surfaces and the indexed artifacts below to move from this narrative packet into the exact run evidence you need next.',
        )
    )
    lines.append('')

    items = _workflow_next_step_items(report_payload, project_root=project_root, report_md_path=report_md_path)
    if not items:
        items = ['Inspect `report.json` and `manifest.json` for the machine-readable companion surfaces.']

    for item in items:
        lines.append('- {0}'.format(item))
    lines.append('')


def _workflow_next_step_items(
    report_payload: Mapping[str, Any],
    *,
    project_root: Path,
    report_md_path: Path,
) -> list[str]:
    result_payload = report_payload.get('result', {}) if isinstance(report_payload.get('result', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    report_paths = report_payload.get('report_paths', {}) if isinstance(report_payload.get('report_paths', {}), MappingABC) else {}
    artifacts = report_payload.get('artifacts', {}) if isinstance(report_payload.get('artifacts', {}), MappingABC) else {}

    items: list[str] = []
    seen_paths: set[str] = set()

    def add_item(label: str, value: Any) -> None:
        value_text = str(value or '').strip()
        if not value_text or value_text in seen_paths:
            return
        seen_paths.add(value_text)
        items.append(_markdown_link_or_path(label, value_text, project_root=project_root, report_md_path=report_md_path))

    add_item('Report JSON', report_paths.get('json', ''))
    add_item('Manifest JSON', report_paths.get('manifest', ''))
    add_item('Threshold report (Markdown)', thresholding.get('report_md', ''))
    add_item('Threshold report (JSON)', thresholding.get('report_json', ''))
    add_item('Score surface CSV', thresholding.get('scores_csv', ''))

    preferred_artifacts = [
        'dataset_manifest',
        'features_csv',
        'labels_csv',
        'evaluation_run_json',
        'evaluation_run_md',
        'scores_csv',
        'threshold_report_json',
        'threshold_report_md',
        'model_path',
        'model_pickle',
    ]
    for key in preferred_artifacts:
        if key in artifacts:
            add_item(_friendly_label(key), artifacts.get(key))

    for key in sorted(artifacts.keys()):
        if len(items) >= 6:
            break
        add_item(_friendly_label(str(key)), artifacts.get(key))

    return items[:6]


def _markdown_link_or_path(label: str, value: str, *, project_root: Path, report_md_path: Path) -> str:
    rel_path = _markdown_relative_path(report_md_path, project_root, value)
    if rel_path:
        return '[{0}]({1})'.format(label, rel_path)
    return '`{0}`: `{1}`'.format(label, value)


def _normalized_strings(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    return [str(value).strip() for value in values if str(value or '').strip()]


def _format_countish(value: Any) -> str:
    if value in ('', None):
        return 'n/a'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return '{0:,}'.format(value)
    if isinstance(value, float):
        if value.is_integer():
            return '{0:,}'.format(int(value))
        return '{0:.6g}'.format(value)
    return str(value)


def _append_result_section(lines: list[str], mapping: Any) -> None:
    if not isinstance(mapping, MappingABC) or not mapping:
        return

    scalar_mapping: Dict[str, Any] = {}
    counts = mapping.get('counts', {}) if isinstance(mapping.get('counts', {}), MappingABC) else {}
    metrics = mapping.get('metrics', {}) if isinstance(mapping.get('metrics', {}), MappingABC) else {}
    thresholding = mapping.get('thresholding', {}) if isinstance(mapping.get('thresholding', {}), MappingABC) else {}
    workflow_steps = mapping.get('workflow_steps', [])
    reason_codes = mapping.get('reason_codes', [])

    for key, value in mapping.items():
        if str(key) in {'counts', 'metrics', 'thresholding', 'workflow_steps', 'reason_codes'}:
            continue
        scalar_mapping[str(key)] = value

    _append_scalar_table(lines, 'Result overview', scalar_mapping)
    _append_horizontal_value_table(lines, 'Counts', counts)
    _append_key_value_table(lines, 'Metrics', metrics, key_label='Metric')
    _append_key_value_table(lines, 'Thresholding', thresholding, key_label='Field', code_values=True)
    _append_list_section(lines, 'Workflow steps', workflow_steps)
    _append_reason_codes_section(lines, reason_codes)


def _append_visuals(lines: list, result_payload: Any, *, project_root: Path, report_md_path: Path) -> None:
    if not isinstance(result_payload, MappingABC):
        return
    visuals = result_payload.get('visuals', {})
    if not isinstance(visuals, MappingABC):
        return
    figures = list(visuals.get('figures', []) or [])
    if not figures:
        return

    lines.append('## Visuals')
    lines.append('')
    lines.append('These figures are declared by the packet itself, so the visual evidence stays tied to the same run contract as the numeric tables and companion JSON.')
    lines.append('')
    anomaly_direction = str(visuals.get('anomaly_direction', '') or '').strip()
    _append_key_value_table(
        lines,
        'Visual summary',
        {
            'anomaly_direction': anomaly_direction,
            'figure_count': int(visuals.get('figure_count', len(figures)) or len(figures)),
        },
        key_label='Field',
    )
    for figure in figures:
        if not isinstance(figure, MappingABC):
            continue
        title = str(figure.get('title', '') or figure.get('id', '') or 'Figure').strip()
        caption = str(figure.get('caption', '') or '').strip()
        rel_path = _markdown_relative_path(report_md_path, project_root, figure.get('path'))
        lines.append('### {0}'.format(title))
        lines.append('')
        if caption:
            lines.append(caption)
            lines.append('')
        if rel_path:
            lines.append('![{0}]({1})'.format(title, rel_path))
            lines.append('')


def _append_mapping(lines: list, title: str, mapping: Any) -> None:
    if not isinstance(mapping, MappingABC) or not mapping:
        return
    lines.append('## {0}'.format(title))
    lines.append('')


def _append_scalar_table(lines: list[str], title: str, mapping: Any) -> None:
    if not isinstance(mapping, MappingABC) or not mapping:
        return
    rows = []
    for key, value in mapping.items():
        if value in ('', None, [], {}, ()):
            continue
        if isinstance(value, (MappingABC, list, tuple, set)):
            continue
        rows.append((str(key), value))
    if not rows:
        return

    lines.append('## {0}'.format(title))
    lines.append('')
    lines.append('| Field | Value |')
    lines.append('| --- | --- |')
    for key, value in rows:
        lines.append('| {0} | {1} |'.format(_table_escape(_friendly_label(key)), _table_escape(_format_scalar(value))))
    lines.append('')


def _append_horizontal_value_table(lines: list[str], title: str, mapping: Any) -> None:
    if not isinstance(mapping, MappingABC) or not mapping:
        return
    ordered_keys = [key for key in ('tp', 'fp', 'tn', 'fn') if key in mapping]
    ordered_keys.extend([key for key in mapping.keys() if key not in ordered_keys])
    if not ordered_keys:
        return

    lines.append('### {0}'.format(title))
    lines.append('')
    lines.append('| {0} |'.format(' | '.join(_table_escape(_friendly_label(str(key))) for key in ordered_keys)))
    lines.append('| {0} |'.format(' | '.join('---:' for _ in ordered_keys)))
    lines.append('| {0} |'.format(' | '.join(_table_escape(_format_scalar(mapping[key])) for key in ordered_keys)))
    lines.append('')


def _append_key_value_table(
    lines: list[str],
    title: str,
    mapping: Any,
    *,
    key_label: str = 'Field',
    code_values: bool = False,
) -> None:
    if not isinstance(mapping, MappingABC) or not mapping:
        return

    rows = []
    for key, value in mapping.items():
        if value in ('', None, [], {}, ()):
            continue
        rows.append((str(key), value))
    if not rows:
        return

    lines.append('### {0}'.format(title))
    lines.append('')
    lines.append('| {0} | Value |'.format(key_label))
    lines.append('| --- | --- |')
    for key, value in rows:
        lines.append(
            '| {0} | {1} |'.format(
                _table_escape(_friendly_label(key)),
                _table_escape(_format_scalar(value, code_like=code_values)),
            )
        )
    lines.append('')


def _append_path_table(lines: list[str], title: str, mapping: Any, *, key_label: str, intro_text: str = '') -> None:
    if not isinstance(mapping, MappingABC) or not mapping:
        return
    rows = []
    for key in sorted(mapping.keys()):
        value = mapping[key]
        if value in ('', None, [], {}, ()):
            continue
        if isinstance(value, MappingABC):
            continue
        rows.append((str(key), value))
    if not rows:
        return

    lines.append('## {0}'.format(title))
    lines.append('')
    intro = str(intro_text or '').strip()
    if intro:
        lines.append(intro)
        lines.append('')
    lines.append('| {0} | Path |'.format(key_label))
    lines.append('| --- | --- |')
    for key, value in rows:
        lines.append('| {0} | {1} |'.format(_table_escape(_friendly_label(key)), _table_escape(_format_path_value(value))))
    lines.append('')


def _append_provenance_section(lines: list[str], mapping: Any) -> None:
    if not isinstance(mapping, MappingABC) or not mapping:
        return

    lines.append('## Provenance')
    lines.append('')
    lines.append('This Markdown packet is interpretive. Canonical machine-readable authority remains in `report.json`, `manifest.json`, and the underlying run artifacts referenced below.')
    lines.append('')
    scalar_rows: Dict[str, Any] = {}
    nested_mappings: Dict[str, Mapping[str, Any]] = {}
    for key, value in mapping.items():
        if value in ('', None, [], {}, ()):
            continue
        if isinstance(value, MappingABC):
            nested_mappings[str(key)] = value
        else:
            scalar_rows[str(key)] = value

    if scalar_rows:
        lines.append('### Source lineage')
        lines.append('')
        lines.append('| Field | Value |')
        lines.append('| --- | --- |')
        for key, value in scalar_rows.items():
            lines.append('| {0} | {1} |'.format(_table_escape(_friendly_label(key)), _table_escape(_format_path_value(value))))
        lines.append('')

    for key, value in nested_mappings.items():
        lines.append('### {0}'.format(_friendly_label(key)))
        lines.append('')
        lines.append('| Surface | Path |')
        lines.append('| --- | --- |')
        for subkey in sorted(value.keys()):
            lines.append('| {0} | {1} |'.format(_table_escape(_friendly_label(str(subkey))), _table_escape(_format_path_value(value[subkey]))))
        lines.append('')


def _append_list_section(lines: list[str], title: str, values: Any) -> None:
    if not isinstance(values, (list, tuple, set)):
        return
    normalized = [str(value) for value in values if str(value or '').strip()]
    if not normalized:
        return
    lines.append('### {0}'.format(title))
    lines.append('')
    for index, value in enumerate(normalized, start=1):
        lines.append('{0}. `{1}`'.format(index, value))
    lines.append('')


def _append_reason_codes_section(lines: list[str], values: Any) -> None:
    if not isinstance(values, (list, tuple, set)):
        return
    normalized = [str(value) for value in values if str(value or '').strip()]
    lines.append('### Reason codes')
    lines.append('')
    if not normalized:
        lines.append('- none')
        lines.append('')
        return
    for value in normalized:
        lines.append('- `{0}`'.format(value))
    lines.append('')


def _friendly_label(key: str) -> str:
    tokens = str(key or '').replace('-', ' ').replace('_', ' ').split()
    acronyms = {
        'id': 'ID',
        'utc': 'UTC',
        'cli': 'CLI',
        'fpr': 'FPR',
        'json': 'JSON',
        'md': 'MD',
        'csv': 'CSV',
        'png': 'PNG',
    }
    if not tokens:
        return ''
    return ' '.join(acronyms.get(token.lower(), token.capitalize()) for token in tokens)


def _format_scalar(value: Any, *, code_like: bool = False) -> str:
    if isinstance(value, (list, tuple, set, dict)):
        text = json.dumps(value, sort_keys=True)
    else:
        text = str(value)
    if code_like:
        return '`{0}`'.format(text)
    return text


def _format_path_value(value: Any) -> str:
    return '`{0}`'.format(str(value))


def _table_escape(value: str) -> str:
    return str(value).replace('|', '\\|').replace('\n', '<br>')
    for key in sorted(mapping.keys()):
        value = mapping[key]
        if isinstance(value, MappingABC):
            lines.append('- {0}:'.format(key))
            for subkey in sorted(value.keys()):
                lines.append('  - {0}: {1}'.format(subkey, _markdown_scalar(value[subkey])))
            continue
        lines.append('- {0}: {1}'.format(key, _markdown_scalar(value)))
    lines.append('')


def _markdown_scalar(value: Any) -> str:
    if isinstance(value, (list, tuple, set, dict)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _markdown_relative_path(report_md_path: Path, project_root: Path, value: Any) -> str:
    if value in ('', None):
        return ''
    candidate = Path(str(value))
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        return Path(os.path.relpath(candidate.resolve(), start=report_md_path.parent.resolve())).as_posix()
    except Exception:
        return Path(os.path.relpath(candidate, start=report_md_path.parent)).as_posix()