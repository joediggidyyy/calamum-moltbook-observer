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
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item, project_root) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_json_value(item, project_root) for item in value]
    return value


def _report_markdown(report_payload: Mapping[str, Any], *, project_root: Path, report_md_path: Path) -> str:
    workflow = str(report_payload.get('workflow', 'run'))
    title = WORKFLOW_TITLES.get(workflow, workflow.replace('-', ' ').title())
    result_payload = report_payload.get('result', {}) if isinstance(report_payload.get('result', {}), MappingABC) else {}
    result_without_visuals = {key: value for key, value in result_payload.items() if str(key) != 'visuals'}
    lines = [
        '# {0} Report: {1}'.format(title, str(report_payload.get('run_id', ''))),
        '',
        '- Workflow: {0}'.format(workflow),
        '- Created (UTC): {0}'.format(str(report_payload.get('timestamp_utc', ''))),
        '- Decision: {0}'.format(str(report_payload.get('decision', ''))),
        '- Summary: {0}'.format(str(report_payload.get('summary', ''))),
        '',
    ]
    _append_mapping(lines, 'Context', report_payload.get('context', {}))
    _append_mapping(lines, 'Result', result_without_visuals)
    _append_visuals(lines, result_payload, project_root=project_root, report_md_path=report_md_path)
    _append_mapping(lines, 'Artifacts', report_payload.get('artifacts', {}))
    _append_mapping(lines, 'Lineage', report_payload.get('lineage', {}))
    _append_mapping(lines, 'Report paths', report_payload.get('report_paths', {}))
    return '\n'.join(lines).rstrip() + '\n'


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
    if anomaly_direction:
        lines.append('- Anomaly direction: {0}'.format(anomaly_direction))
    lines.append('- Figure count: {0}'.format(int(visuals.get('figure_count', len(figures)) or len(figures))))
    lines.append('')
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