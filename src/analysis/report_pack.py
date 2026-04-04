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
    result_payload = report_payload.get('result', {}) if isinstance(report_payload.get('result', {}), MappingABC) else {}
    result_without_visuals = {key: value for key, value in result_payload.items() if str(key) != 'visuals'}
    decision = str(report_payload.get('decision', '') or '').strip()
    runtime_cli_surface = str(report_payload.get('runtime_cli_surface', '') or '').strip()
    command_path = str(report_payload.get('command_path', '') or '').strip()
    summary = str(report_payload.get('summary', '') or '').strip()
    lines = [
        '# {0} Report: {1}'.format(title, str(report_payload.get('run_id', ''))),
        '',
        '**Status**: `{0}`'.format(decision or 'unknown'),
        '**Workflow**: `{0}`'.format(workflow),
        '**Created (UTC)**: `{0}`'.format(str(report_payload.get('timestamp_utc', ''))),
    ]
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
    _append_scalar_table(
        lines,
        'Run snapshot',
        {
            'run_id': report_payload.get('run_id', ''),
            'workflow': workflow,
            'decision': decision,
            'created_utc': report_payload.get('timestamp_utc', ''),
            'runtime_cli_surface': runtime_cli_surface,
            'command_path': command_path,
        },
    )
    _append_scalar_table(lines, 'Context', report_payload.get('context', {}))
    _append_result_section(lines, result_without_visuals)
    _append_visuals(lines, result_payload, project_root=project_root, report_md_path=report_md_path)
    _append_path_table(lines, 'Artifact index', report_payload.get('artifacts', {}), key_label='Artifact')
    _append_provenance_section(lines, report_payload.get('lineage', {}))
    _append_path_table(lines, 'Report paths', report_payload.get('report_paths', {}), key_label='Surface')
    return '\n'.join(lines).rstrip() + '\n'


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


def _append_path_table(lines: list[str], title: str, mapping: Any, *, key_label: str) -> None:
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