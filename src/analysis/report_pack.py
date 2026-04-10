from __future__ import annotations

from collections.abc import Mapping as MappingABC
import os
import json
import re
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
STAGE_WORKFLOWS = {'build', 'train', 'evaluate', 'score'}
STAGE_SECTION_TITLES = {
    'build': 'Build',
    'train': 'Training',
    'evaluate': 'Evaluation',
    'score': 'Score',
}
STAGE_ROLE_SUMMARIES = {
    'build': 'first processing packet that turns the approved collection evidence into the run-local dataset bundle consumed by later stages',
    'train': 'model-publication packet that turns the current dataset bundle into the trained artifact consumed by downstream evaluation and scoring',
    'evaluate': 'threshold-publication packet that explains how the current model and score surface were turned into downstream review posture',
    'score': 'score-surface packet that shows the full anomaly distribution the paired evaluation threshold is selecting from',
}
STAGE_PRIMARY_SECTION_TITLES = {
    'build': 'Dataset materialization summary',
    'train': 'Model publication summary',
    'evaluate': 'Threshold publication summary',
    'score': 'Score surface summary',
}
STAGE_SECONDARY_SECTION_TITLES = {
    'build': 'Split and schema summary',
    'train': 'Feature contract summary',
    'evaluate': 'Review-set summary',
    'score': 'Distribution summary',
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
    collection_alias = resolve_collection_alias(
        project_anchor=project_anchor,
        packet=packet,
        artifact_paths=artifact_paths,
        context=context or {},
        lineage=lineage or {},
    )
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
        'collection_alias': collection_alias,
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
        'collection_alias': collection_alias,
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


def _explicit_collection_alias(mapping: Optional[Mapping[str, Any]]) -> str:
    if not isinstance(mapping, MappingABC):
        return ''
    alias = str(mapping.get('collection_alias', '') or mapping.get('dataset_alias', '') or '').strip()
    return sanitize_run_id(alias) or ''


def _collection_alias_dataset_refs(
    packet: Optional[Mapping[str, Any]],
    artifact_paths: Optional[Mapping[str, Optional[Path]]],
    context: Optional[Mapping[str, Any]],
    lineage: Optional[Mapping[str, Any]],
) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()

    def _append_ref(value: Any) -> None:
        text = str(value or '').strip()
        if not text or text in seen:
            return
        seen.add(text)
        refs.append(text)

    if isinstance(packet, MappingABC):
        artifacts = packet.get('artifacts', {}) if isinstance(packet.get('artifacts', {}), MappingABC) else {}
        _append_ref(artifacts.get('dataset_manifest', ''))
    if isinstance(artifact_paths, MappingABC):
        _append_ref(artifact_paths.get('dataset_manifest'))
    for mapping in (context, lineage):
        if not isinstance(mapping, MappingABC):
            continue
        _append_ref(mapping.get('dataset_manifest', ''))
    return refs


def resolve_collection_alias(
    *,
    project_anchor: Path,
    packet: Optional[Mapping[str, Any]] = None,
    artifact_paths: Optional[Mapping[str, Optional[Path]]] = None,
    context: Optional[Mapping[str, Any]] = None,
    lineage: Optional[Mapping[str, Any]] = None,
) -> str:
    for mapping in (packet, context, lineage):
        alias = _explicit_collection_alias(mapping)
        if alias:
            return alias

    try:
        from calamum_librarian import dataset_display_alias_for_manifest
    except Exception:
        dataset_display_alias_for_manifest = None

    if dataset_display_alias_for_manifest is None:
        return ''

    for manifest_ref in _collection_alias_dataset_refs(packet, artifact_paths, context, lineage):
        alias = sanitize_run_id(dataset_display_alias_for_manifest(project_anchor, manifest_ref) or '')
        if alias:
            return alias
    return ''


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
    if workflow in STAGE_WORKFLOWS:
        return _stage_report_markdown(report_payload, project_root=project_root, report_md_path=report_md_path)
    return _composite_report_markdown(report_payload, project_root=project_root, report_md_path=report_md_path)


def _composite_report_markdown(report_payload: Mapping[str, Any], *, project_root: Path, report_md_path: Path) -> str:
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


def _stage_report_markdown(report_payload: Mapping[str, Any], *, project_root: Path, report_md_path: Path) -> str:
    workflow = str(report_payload.get('workflow', 'run'))
    title = WORKFLOW_TITLES.get(workflow, workflow.replace('-', ' ').title())
    stage_label = STAGE_SECTION_TITLES.get(workflow, title)
    result_payload = report_payload.get('result', {}) if isinstance(report_payload.get('result', {}), MappingABC) else {}
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
    lines.append('')
    _append_scalar_table(lines, '{0} identity'.format(stage_label), _workflow_identity_mapping(workflow, report_payload, result_payload))
    _append_code_summary_section(lines, 'Run summary', _workflow_run_summary_mapping(workflow, report_payload, result_payload))
    run_summary_text = _workflow_run_summary_text(workflow, report_payload, result_payload)
    if run_summary_text:
        lines.append(run_summary_text)
        lines.append('')
    handoff_map = _workflow_handoff_map_markdown(workflow, report_payload, result_payload)
    if handoff_map:
        lines.append('## {0} handoff map'.format(stage_label))
        lines.append('')
        lines.append('```mermaid')
        lines.extend(handoff_map.splitlines())
        lines.append('```')
        lines.append('')
    lines.append('## {0} method'.format(stage_label))
    lines.append('')
    lines.append(_workflow_method_summary_text(workflow, report_payload, result_payload))
    lines.append('')
    _append_code_summary_section(lines, '', _workflow_method_reference_mapping(workflow, report_payload, result_payload))
    _append_code_summary_section(
        lines,
        STAGE_PRIMARY_SECTION_TITLES.get(workflow, 'Stage summary'),
        _workflow_primary_summary_mapping(workflow, report_payload, result_payload),
    )
    _append_code_summary_section(
        lines,
        STAGE_SECONDARY_SECTION_TITLES.get(workflow, 'Stage evidence summary'),
        _workflow_secondary_summary_mapping(workflow, report_payload, result_payload),
    )
    interpretation_text = _workflow_interpretation_text(workflow, report_payload, result_payload)
    if interpretation_text:
        lines.append(interpretation_text)
        lines.append('')
    _append_stage_visual_surfaces(lines, workflow, result_payload, project_root=project_root, report_md_path=report_md_path)
    _append_code_summary_section(lines, 'Run implications', _workflow_run_implication_mapping(workflow, report_payload, result_payload))
    handoff_text = _workflow_stage_handoff_text(workflow, report_payload, result_payload)
    if handoff_text:
        lines.append(handoff_text)
        lines.append('')
    _append_bullet_section(lines, 'Limits', _workflow_limit_items(workflow, decision, result_payload))
    _append_related_surfaces_section(lines, report_payload, project_root=project_root, report_md_path=report_md_path)
    return '\n'.join(lines).rstrip() + '\n'


def _workflow_identity_mapping(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> Dict[str, Any]:
    context = report_payload.get('context', {}) if isinstance(report_payload.get('context', {}), MappingABC) else {}
    artifacts = report_payload.get('artifacts', {}) if isinstance(report_payload.get('artifacts', {}), MappingABC) else {}
    mapping: Dict[str, Any] = {}
    _maybe_add(mapping, 'Collection alias', report_payload.get('collection_alias', ''))
    source_scope = _source_scope_text(context)
    _maybe_add(mapping, 'Source scope', source_scope)
    _maybe_add(mapping, 'Calculation run', report_payload.get('run_id', ''))

    build_lineage = _first_nonempty_run_token(
        artifacts.get('dataset_manifest', ''),
        artifacts.get('features_csv', ''),
        artifacts.get('labels_csv', ''),
    )
    model_lineage = _first_nonempty_run_token(
        artifacts.get('model_path', ''),
        artifacts.get('model_pickle', ''),
        artifacts.get('resolved_model_path', ''),
        artifacts.get('train_manifest', ''),
    )
    if workflow in {'train', 'evaluate', 'score'}:
        _maybe_add(mapping, 'Build lineage', build_lineage if str(build_lineage).startswith('build_') else '')
    if workflow in {'evaluate', 'score'}:
        _maybe_add(mapping, 'Model lineage', model_lineage if str(model_lineage).startswith('train_') else '')

    mapping['Reader posture'] = 'curated, public-safe, names-only'
    mapping['Role in the report spine'] = STAGE_ROLE_SUMMARIES.get(
        workflow,
        'reader-facing stage packet for the current workflow lane',
    )
    return mapping


def _workflow_run_summary_mapping(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> Dict[str, Any]:
    context = report_payload.get('context', {}) if isinstance(report_payload.get('context', {}), MappingABC) else {}
    counts = result_payload.get('counts', {}) if isinstance(result_payload.get('counts', {}), MappingABC) else {}
    metrics = result_payload.get('metrics', {}) if isinstance(result_payload.get('metrics', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    visuals = result_payload.get('visuals', {}) if isinstance(result_payload.get('visuals', {}), MappingABC) else {}
    mapping: Dict[str, Any] = {'decision': report_payload.get('decision', '') or 'unknown'}

    if workflow == 'build':
        _maybe_add(mapping, 'source materialization', True)
        _maybe_add(mapping, 'total records', _first_present(result_payload, 'records_built') or _first_present(counts, 'records_built'))
        _maybe_add(mapping, 'labels present', _boolish_text(_first_present(result_payload, 'has_labels')))
        _maybe_add(mapping, 'seed', _first_present(context, 'dataset_seed', 'seed'))
        _maybe_add(mapping, 'feature columns', _feature_column_summary(result_payload))
    elif workflow == 'train':
        _maybe_add(mapping, 'model type', _first_present(result_payload, 'model_type'))
        _maybe_add(mapping, 'seed', _first_present(context, 'dataset_seed', 'seed'))
        _maybe_add(mapping, 'lineage records', _first_present(counts, 'records_built', 'records_scored', 'records_evaluated'))
        _maybe_add(mapping, 'feature columns', _feature_column_summary(result_payload))
        _maybe_add(mapping, 'metrics emitted', _nonempty_mapping_count(metrics), allow_empty_zero=True)
        _maybe_add(mapping, 'local figures', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)
    elif workflow == 'evaluate':
        _maybe_add(mapping, 'threshold', _first_present(thresholding, 'threshold') or _first_present(result_payload, 'threshold'))
        _maybe_add(mapping, 'max FPR constraint', _first_present(thresholding, 'target_fpr') or _first_present(context, 'max_fpr'))
        _maybe_add(mapping, 'score direction', _first_present(thresholding, 'anomaly_direction') or _first_present(result_payload, 'anomaly_direction'))
        _maybe_add(mapping, 'score column', _first_present(thresholding, 'score_column') or _first_present(result_payload, 'score_column'))
        _maybe_add(mapping, 'records evaluated', _first_present(thresholding, 'records_evaluated', 'records_scored') or _first_present(result_payload, 'records_evaluated', 'records_scored'))
        _maybe_add(mapping, 'flagged records', _first_present(thresholding, 'flagged_records') or _first_present(result_payload, 'flagged_records'))
        _maybe_add(mapping, 'flag rate', _flag_rate_text(thresholding, result_payload))
        _maybe_add(mapping, 'labels present', _boolish_text(_first_present(result_payload, 'has_labels')))
        _maybe_add(mapping, 'local figures', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)
    elif workflow == 'score':
        _maybe_add(mapping, 'records scored', _first_present(thresholding, 'records_scored') or _first_present(result_payload, 'records_scored'))
        _maybe_add(mapping, 'score column', _first_present(result_payload, 'score_column') or _first_present(thresholding, 'score_column'))
        _maybe_add(mapping, 'score direction', _first_present(result_payload, 'anomaly_direction') or _first_present(thresholding, 'anomaly_direction'))
        _maybe_add(mapping, 'paired threshold', _first_present(thresholding, 'threshold'))
        _maybe_add(mapping, 'local figures', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)

    return {key: value for key, value in mapping.items() if value not in ('', None, [], {}, ())}


def _workflow_run_summary_text(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> str:
    summary = str(report_payload.get('summary', '') or '').strip()
    if workflow == 'build':
        return 'This run reads as a materialization pass rather than a model-quality claim. {0}'.format(
            summary or 'The packet focuses on the dataset handoff that later stages will consume.'
        )
    if workflow == 'train':
        return 'This run reads as artifact publication rather than as a metric-heavy training story. {0}'.format(
            summary or 'The packet exists to show that the approved dataset bundle was converted into a reusable model handoff.'
        )
    if workflow == 'evaluate':
        return 'This run publishes threshold posture and review-volume evidence instead of claiming labeled certainty. {0}'.format(
            summary or 'The packet exists to show the operating point that the paired score surface should be read through.'
        )
    if workflow == 'score':
        return 'This run publishes the full score surface for the current lineage rather than a standalone flagged-case verdict. {0}'.format(
            summary or 'The packet exists to make the paired evaluation threshold legible at collection scale.'
        )
    return summary


def _workflow_handoff_map_markdown(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> str:
    run_id = str(report_payload.get('run_id', '') or 'current-run')
    collection_alias = str(report_payload.get('collection_alias', '') or 'collection')
    context = report_payload.get('context', {}) if isinstance(report_payload.get('context', {}), MappingABC) else {}
    source_scope = _source_scope_text(context) or collection_alias
    artifacts = report_payload.get('artifacts', {}) if isinstance(report_payload.get('artifacts', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    build_lineage = _first_nonempty_run_token(
        artifacts.get('dataset_manifest', ''),
        artifacts.get('features_csv', ''),
        collection_alias,
    ) or 'build-lineage'
    model_lineage = _first_nonempty_run_token(
        artifacts.get('model_path', ''),
        artifacts.get('model_pickle', ''),
        artifacts.get('resolved_model_path', ''),
        artifacts.get('train_manifest', ''),
    ) or 'trained-model'

    if workflow == 'build':
        return '\n'.join([
            'flowchart LR',
            '\tA[Collection packet<br/>{0}] --> B[Build run<br/>{1}]'.format(source_scope, run_id),
            '\tB --> C[Run-local dataset bundle<br/>manifest + features + splits]',
            '\tC --> D[Train / Eval / Score]',
        ])
    if workflow == 'train':
        return '\n'.join([
            'flowchart LR',
            '\tA[Dataset bundle<br/>{0}] --> B[Training run<br/>{1}]'.format(build_lineage, run_id),
            '\tB --> C[Model bundle<br/>model + manifest + metrics]',
            '\tC --> D[Evaluation packet]',
            '\tC --> E[Score packet]',
        ])
    if workflow == 'evaluate':
        threshold_value = _summary_value_text(_first_present(thresholding, 'threshold') or _first_present(result_payload, 'threshold')) or 'current threshold'
        flagged = _summary_value_text(_first_present(thresholding, 'flagged_records') or _first_present(result_payload, 'flagged_records')) or 'flagged set'
        return '\n'.join([
            'flowchart LR',
            '\tA[Build dataset<br/>{0}] --> B[Trained model<br/>{1}]'.format(build_lineage, model_lineage),
            '\tB --> C[Evaluation run<br/>{0}]'.format(run_id),
            '\tC --> D[Published threshold<br/>{0}]'.format(threshold_value),
            '\tD --> E[Score review set<br/>{0}]'.format(flagged),
        ])
    if workflow == 'score':
        return '\n'.join([
            'flowchart LR',
            '\tA[Build dataset<br/>{0}] --> B[Trained model<br/>{1}]'.format(build_lineage, model_lineage),
            '\tB --> C[Score run<br/>{0}]'.format(run_id),
            '\tC --> D[Full score surface<br/>scores.csv + figures]',
            '\tD --> E[Threshold-aware reading<br/>paired evaluation packet]',
        ])
    return ''


def _workflow_method_reference_mapping(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> Dict[str, Any]:
    report_paths = report_payload.get('report_paths', {}) if isinstance(report_payload.get('report_paths', {}), MappingABC) else {}
    artifacts = report_payload.get('artifacts', {}) if isinstance(report_payload.get('artifacts', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    mapping: Dict[str, Any] = {}
    _maybe_add(mapping, 'command surface', report_payload.get('command_path', ''))
    _maybe_add(mapping, 'runtime report json', report_paths.get('json', ''))
    _maybe_add(mapping, 'runtime report manifest', report_paths.get('manifest', ''))
    _maybe_add(mapping, 'runtime report markdown', report_paths.get('markdown', ''))

    if workflow == 'build':
        _maybe_add(mapping, 'run-local dataset', artifacts.get('dataset_manifest', ''))
        _maybe_add(mapping, 'feature table', artifacts.get('features_csv', ''))
        _maybe_add(mapping, 'labels table', artifacts.get('labels_csv', ''))
    elif workflow == 'train':
        _maybe_add(mapping, 'dataset lineage', artifacts.get('dataset_manifest', ''))
        _maybe_add(mapping, 'model bundle', _first_present(artifacts, 'model_path', 'model_pickle', 'resolved_model_path'))
        _maybe_add(mapping, 'train manifest', artifacts.get('train_manifest', ''))
    elif workflow == 'evaluate':
        _maybe_add(mapping, 'dataset lineage', artifacts.get('dataset_manifest', ''))
        _maybe_add(mapping, 'model reference', _first_present(artifacts, 'model_path', 'model_pickle', 'resolved_model_path'))
        _maybe_add(mapping, 'evaluation ledger', _first_present(artifacts, 'evaluation_run_json', 'run_json'))
        _maybe_add(mapping, 'score surface', _first_present(thresholding, 'scores_csv') or artifacts.get('scores_csv', ''))
    elif workflow == 'score':
        _maybe_add(mapping, 'model reference', _first_present(artifacts, 'model_path', 'model_pickle', 'resolved_model_path'))
        _maybe_add(mapping, 'score surface', _first_present(thresholding, 'scores_csv') or artifacts.get('scores_csv', ''))
        _maybe_add(mapping, 'threshold context', _first_present(thresholding, 'report_md', 'report_json'))

    return mapping


def _workflow_primary_summary_mapping(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> Dict[str, Any]:
    context = report_payload.get('context', {}) if isinstance(report_payload.get('context', {}), MappingABC) else {}
    metrics = result_payload.get('metrics', {}) if isinstance(result_payload.get('metrics', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    visuals = result_payload.get('visuals', {}) if isinstance(result_payload.get('visuals', {}), MappingABC) else {}
    mapping: Dict[str, Any] = {}
    if workflow == 'build':
        _maybe_add(mapping, 'underlying surface', report_payload.get('underlying_surface', ''))
        _maybe_add(mapping, 'output override', _boolish_text(_first_present(context, 'output_override')))
        _maybe_add(mapping, 'feature columns', _feature_column_summary(result_payload))
        _maybe_add(mapping, 'seed', _first_present(context, 'dataset_seed', 'seed'))
    elif workflow == 'train':
        _maybe_add(mapping, 'published model type', _first_present(result_payload, 'model_type'))
        _maybe_add(mapping, 'output override', _boolish_text(_first_present(context, 'output_override')))
        _maybe_add(mapping, 'metrics payload', _nonempty_mapping_count(metrics), allow_empty_zero=True)
        _maybe_add(mapping, 'local figures', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)
    elif workflow == 'evaluate':
        _maybe_add(mapping, 'published threshold', _first_present(thresholding, 'threshold') or _first_present(result_payload, 'threshold'))
        _maybe_add(mapping, 'constraint type', 'max_fpr')
        _maybe_add(mapping, 'constraint value', _first_present(thresholding, 'target_fpr') or _first_present(context, 'max_fpr'))
        _maybe_add(mapping, 'score direction', _first_present(thresholding, 'anomaly_direction') or _first_present(result_payload, 'anomaly_direction'))
        _maybe_add(mapping, 'score column', _first_present(thresholding, 'score_column') or _first_present(result_payload, 'score_column'))
        _maybe_add(mapping, 'local figures', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)
    elif workflow == 'score':
        _maybe_add(mapping, 'records scored', _first_present(thresholding, 'records_scored') or _first_present(result_payload, 'records_scored'))
        _maybe_add(mapping, 'output override', _boolish_text(_first_present(context, 'output_override')))
        _maybe_add(mapping, 'score column', _first_present(result_payload, 'score_column') or _first_present(thresholding, 'score_column'))
        _maybe_add(mapping, 'anomaly direction', _first_present(result_payload, 'anomaly_direction') or _first_present(thresholding, 'anomaly_direction'))
        _maybe_add(mapping, 'reason codes', _reason_code_text(result_payload.get('reason_codes', [])))
    return mapping


def _workflow_secondary_summary_mapping(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> Dict[str, Any]:
    context = report_payload.get('context', {}) if isinstance(report_payload.get('context', {}), MappingABC) else {}
    counts = result_payload.get('counts', {}) if isinstance(result_payload.get('counts', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    visuals = result_payload.get('visuals', {}) if isinstance(result_payload.get('visuals', {}), MappingABC) else {}
    mapping: Dict[str, Any] = {}
    if workflow == 'build':
        _maybe_add(mapping, 'records built', _first_present(result_payload, 'records_built') or _first_present(counts, 'records_built'))
        _maybe_add(mapping, 'labels present', _boolish_text(_first_present(result_payload, 'has_labels')))
        _maybe_add(mapping, 'feature columns', _feature_column_summary(result_payload))
        _maybe_add(mapping, 'split authority', _first_present(report_payload.get('artifacts', {}) if isinstance(report_payload.get('artifacts', {}), MappingABC) else {}, 'split_manifest_json', 'splits_csv'))
    elif workflow == 'train':
        _maybe_add(mapping, 'feature columns', _feature_column_summary(result_payload))
        _maybe_add(mapping, 'labels present', _boolish_text(_first_present(result_payload, 'has_labels')))
        _maybe_add(mapping, 'metrics emitted', _nonempty_mapping_count(result_payload.get('metrics', {}) if isinstance(result_payload.get('metrics', {}), MappingABC) else {}), allow_empty_zero=True)
        _maybe_add(mapping, 'figure count', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)
    elif workflow == 'evaluate':
        _maybe_add(mapping, 'records evaluated', _first_present(thresholding, 'records_evaluated', 'records_scored') or _first_present(result_payload, 'records_evaluated', 'records_scored'))
        _maybe_add(mapping, 'flagged records', _first_present(thresholding, 'flagged_records') or _first_present(result_payload, 'flagged_records'))
        _maybe_add(mapping, 'flagged share', _flag_rate_text(thresholding, result_payload))
        _maybe_add(mapping, 'labels present', _boolish_text(_first_present(result_payload, 'has_labels')))
    elif workflow == 'score':
        _maybe_add(mapping, 'paired eval threshold', _first_present(thresholding, 'threshold'))
        _maybe_add(mapping, 'score direction', _first_present(result_payload, 'anomaly_direction') or _first_present(thresholding, 'anomaly_direction'))
        _maybe_add(mapping, 'figure count', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)
        _maybe_add(mapping, 'reader message', _workflow_stage_handoff_text(workflow, report_payload, result_payload))
    return mapping


def _workflow_run_implication_mapping(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> Dict[str, Any]:
    ready = 'ready' if str(report_payload.get('decision', '') or '').strip().lower() == 'go' else 'conditional'
    mapping: Dict[str, Any] = {}
    if workflow == 'build':
        mapping['train handoff posture'] = ready
        mapping['main value'] = 'stable custody, explicit schema, reusable dataset bundle'
        mapping['reader caution'] = 'do not treat a build packet as model-quality evidence on its own'
    elif workflow == 'train':
        mapping['eval handoff posture'] = ready
        mapping['score handoff posture'] = ready
        mapping['main value'] = 'reusable model custody with explicit lineage'
        mapping['reader caution'] = 'training posture still needs downstream evaluation before it becomes a readiness signal'
    elif workflow == 'evaluate':
        mapping['score handoff posture'] = ready
        mapping['main value'] = 'explicit operating threshold tied to a concrete review volume'
        mapping['reader caution'] = 'do not read the max-FPR setting as labeled certainty when labels are absent'
    elif workflow == 'score':
        mapping['review handoff posture'] = ready
        mapping['main value'] = 'full score surface that makes the paired threshold interpretable'
        mapping['reader caution'] = 'scoring emits the distribution; threshold selection and final review posture live elsewhere'
    return mapping


def _append_code_summary_section(lines: list[str], title: str, mapping: Mapping[str, Any]) -> None:
    if not isinstance(mapping, MappingABC) or not mapping:
        return
    rows = [(str(key), value) for key, value in mapping.items() if value not in ('', None, [], {}, ())]
    if not rows:
        return
    if str(title or '').strip():
        lines.append('## {0}'.format(title))
        lines.append('')
    width = max(len(key) for key, _ in rows)
    lines.append('```')
    for key, value in rows:
        lines.append('{0:<{1}} : {2}'.format(key, width, _summary_value_text(value)))
    lines.append('```')
    lines.append('')


def _summary_value_text(value: Any) -> str:
    if value in ('', None):
        return 'n/a'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, int):
        return '{0:,}'.format(value)
    if isinstance(value, float):
        if value.is_integer():
            return '{0:,}'.format(int(value))
        return '{0:.6g}'.format(value)
    if isinstance(value, (list, tuple, set)):
        return ', '.join(str(item) for item in value)
    return str(value)


def _source_scope_text(context: Mapping[str, Any]) -> str:
    source = str(context.get('source', '') or '').strip()
    mode = str(context.get('mode', '') or '').strip()
    if source and mode:
        return '{0}:{1}'.format(source, mode)
    if source:
        return source
    if mode:
        return mode
    return ''


def _boolish_text(value: Any) -> str:
    if value in ('', None):
        return ''
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {'true', 'yes', '1'}:
            return 'yes'
        if text in {'false', 'no', '0'}:
            return 'no'
        return value
    return 'yes' if bool(value) else 'no'


def _feature_column_summary(result_payload: Mapping[str, Any]) -> Any:
    feature_columns = result_payload.get('feature_columns') if isinstance(result_payload, MappingABC) else None
    if isinstance(feature_columns, (list, tuple, set)):
        return len(feature_columns)
    return feature_columns


def _flag_rate_text(thresholding: Mapping[str, Any], result_payload: Mapping[str, Any]) -> str:
    actual_fpr = _first_present(thresholding, 'actual_fpr')
    if actual_fpr not in ('', None):
        try:
            return '{0:.3%}'.format(float(actual_fpr))
        except (TypeError, ValueError):
            return str(actual_fpr)
    flagged = _first_present(thresholding, 'flagged_records') or _first_present(result_payload, 'flagged_records')
    total = _first_present(thresholding, 'records_evaluated', 'records_scored') or _first_present(result_payload, 'records_evaluated', 'records_scored')
    try:
        flagged_value = float(flagged)
        total_value = float(total)
    except (TypeError, ValueError):
        return ''
    if total_value <= 0:
        return ''
    return '{0:.3%}'.format(flagged_value / total_value)


def _reason_code_text(values: Any) -> str:
    normalized = _normalized_strings(values)
    if not normalized:
        return 'none'
    return ', '.join(normalized)


def _first_nonempty_run_token(*values: Any) -> str:
    for value in values:
        token = _extract_run_token(value)
        if token:
            return token
    return ''


def _extract_run_token(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    match = re.search(r'(?:build|train|evaluate|score|demo|pipeline)_[0-9T]+Z', text)
    if match is not None:
        return match.group(0)
    return ''


def _workflow_input_items(workflow: str, report_payload: Mapping[str, Any]) -> list[str]:
    artifacts = report_payload.get('artifacts', {}) if isinstance(report_payload.get('artifacts', {}), MappingABC) else {}
    lineage = report_payload.get('lineage', {}) if isinstance(report_payload.get('lineage', {}), MappingABC) else {}
    result_payload = report_payload.get('result', {}) if isinstance(report_payload.get('result', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    items: list[str] = []

    if workflow == 'build':
        if _has_any_value(artifacts, 'dataset_manifest', 'features_csv', 'labels_csv'):
            items.append('The build stage uses the run-local dataset materialization surfaces that define the feature bundle, any available labels, and the current analysis-ready handoff.')
        if lineage:
            items.append('Upstream lineage metadata remains attached so later stages can trace the dataset bundle back to its approved source surfaces without treating this Markdown packet as the canonical ledger.')
    elif workflow == 'train':
        if _has_any_value(artifacts, 'dataset_manifest', 'features_csv', 'labels_csv'):
            items.append('The training stage consumes the published dataset bundle rather than an ad hoc sample so model custody stays tied to the same dataset contract.')
        if _has_any_value(artifacts, 'model_path', 'model_pickle', 'train_manifest', 'metrics_path'):
            items.append('The primary training outputs are the model artifact, the train-manifest companion, and any emitted metrics surface recorded for the run.')
    elif workflow == 'evaluate':
        if _has_any_value(artifacts, 'dataset_manifest', 'features_csv', 'labels_csv', 'run_json', 'run_md'):
            items.append('The evaluation stage uses the run-local dataset and evaluation companions that describe how the current operating threshold was selected and recorded.')
        if _has_any_value(artifacts, 'model_path', 'model_pickle', 'resolved_model_path'):
            items.append('A trained model reference is required so the threshold posture is tied to the same model lineage that the downstream score packet will use.')
    elif workflow == 'score':
        if _has_any_value(artifacts, 'scores_csv') or _has_any_value(thresholding, 'scores_csv'):
            items.append('The score stage is anchored to the full score surface so the packet can explain ordering and review posture across the complete scored set instead of a narrow sample.')
        if _has_any_value(artifacts, 'resolved_model_path', 'model_path', 'model_pickle'):
            items.append('A resolved trained-model reference is retained so the score surface can be read as a direct descendant of the published training handoff.')
        if _has_any_value(thresholding, 'report_md', 'report_json', 'threshold'):
            items.append('Threshold context remains paired to the score surface so the reader can connect score ordering to the downstream review boundary without blurring the score and evaluate roles.')

    if not items:
        items.append('Use the related surfaces and provenance sections below to move from the human-facing packet into the machine-readable companions for this run.')
    return items


def _workflow_method_summary_text(workflow: str, report_payload: Mapping[str, Any], result_payload: Mapping[str, Any]) -> str:
    command_path = str(report_payload.get('command_path', '') or '').strip() or 'the active observerctl surface'
    if workflow == 'build':
        return 'For this run, `{0}` materialized the current dataset bundle into a reusable run-local handoff. The packet focuses on what was built, how the dataset contract was preserved, and whether the resulting bundle is ready for downstream model work.'.format(command_path)
    if workflow == 'train':
        return 'For this run, `{0}` consumed the current dataset bundle and wrote the trained-model handoff surfaces that downstream evaluation and scoring will read. The packet emphasizes lineage continuity and fit-posture truth rather than pretending that artifact publication alone proves deployment readiness.'.format(command_path)
    if workflow == 'evaluate':
        return 'For this run, `{0}` translated the current model response surface into threshold posture, guardrail context, and review-volume evidence. The packet stays focused on how the operating point was selected and what that choice means for the paired score surface.'.format(command_path)
    if workflow == 'score':
        score_column = _first_present(result_payload, 'score_column') or _first_present(
            result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {},
            'score_column',
        )
        if score_column not in ('', None):
            return 'For this run, `{0}` scored the available records into `{1}` and routed any declared figures through the shared visual registry. The packet is meant to explain how the score surface should be read, not to turn the scored set into an unsupported semantic verdict.'.format(command_path, str(score_column))
        return 'For this run, `{0}` produced the current score surface and routed any declared figures through the shared visual registry. The packet is meant to explain how the ordering should be read, not to turn the scored set into an unsupported semantic verdict.'.format(command_path)
    return 'This packet summarizes the current run in reader-facing language while leaving machine-readable authority in the companion JSON surfaces.'


def _append_stage_key_results(
    lines: list[str],
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> None:
    lines.append('## Key results')
    lines.append('')
    lines.append('This section highlights the strongest run-level evidence for the current stage without duplicating the full machine-readable payload.')
    lines.append('')

    stage_summary = _workflow_key_results_mapping(workflow, report_payload, result_payload)
    counts = result_payload.get('counts', {}) if isinstance(result_payload.get('counts', {}), MappingABC) else {}
    metrics = result_payload.get('metrics', {}) if isinstance(result_payload.get('metrics', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    reason_codes = result_payload.get('reason_codes', [])

    _append_key_value_table(lines, 'Stage summary', stage_summary, key_label='Field')
    _append_horizontal_value_table(lines, 'Count evidence', counts)
    _append_key_value_table(lines, 'Metric evidence', metrics, key_label='Metric')
    _append_key_value_table(lines, 'Threshold posture', thresholding, key_label='Field', code_values=True)
    _append_reason_codes_section(lines, reason_codes)


def _workflow_key_results_mapping(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> Dict[str, Any]:
    counts = result_payload.get('counts', {}) if isinstance(result_payload.get('counts', {}), MappingABC) else {}
    metrics = result_payload.get('metrics', {}) if isinstance(result_payload.get('metrics', {}), MappingABC) else {}
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    visuals = result_payload.get('visuals', {}) if isinstance(result_payload.get('visuals', {}), MappingABC) else {}
    context = report_payload.get('context', {}) if isinstance(report_payload.get('context', {}), MappingABC) else {}
    mapping: Dict[str, Any] = {}

    if workflow == 'build':
        _maybe_add(mapping, 'records_built', _first_present(result_payload, 'records_built') or _first_present(counts, 'records_built'))
        _maybe_add(mapping, 'feature_columns', _first_present(result_payload, 'feature_columns'))
        _maybe_add(mapping, 'labels_present', _first_present(result_payload, 'has_labels'))
        _maybe_add(mapping, 'dataset_seed', _first_present(context, 'dataset_seed', 'seed'))
    elif workflow == 'train':
        _maybe_add(mapping, 'model_type', _first_present(result_payload, 'model_type'))
        _maybe_add(mapping, 'feature_columns', _first_present(result_payload, 'feature_columns'))
        _maybe_add(mapping, 'labels_present', _first_present(result_payload, 'has_labels'))
        _maybe_add(mapping, 'metrics_emitted', _nonempty_mapping_count(metrics), allow_empty_zero=True)
        _maybe_add(mapping, 'figure_count', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)
    elif workflow == 'evaluate':
        _maybe_add(mapping, 'records_evaluated', _first_present(thresholding, 'records_evaluated') or _first_present(result_payload, 'records_evaluated'))
        _maybe_add(mapping, 'flagged_records', _first_present(thresholding, 'flagged_records') or _first_present(result_payload, 'flagged_records'))
        _maybe_add(mapping, 'threshold', _first_present(thresholding, 'threshold') or _first_present(result_payload, 'threshold'))
        _maybe_add(mapping, 'target_fpr', _first_present(thresholding, 'target_fpr') or _first_present(context, 'max_fpr') or _first_present(result_payload, 'max_fpr'))
        _maybe_add(mapping, 'actual_fpr', _first_present(thresholding, 'actual_fpr'))
        _maybe_add(mapping, 'anomaly_direction', _first_present(thresholding, 'anomaly_direction') or _first_present(result_payload, 'anomaly_direction'))
        _maybe_add(mapping, 'score_column', _first_present(thresholding, 'score_column') or _first_present(result_payload, 'score_column'))
        _maybe_add(mapping, 'figure_count', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)
    elif workflow == 'score':
        _maybe_add(mapping, 'records_scored', _first_present(thresholding, 'records_scored') or _first_present(result_payload, 'records_scored'))
        _maybe_add(mapping, 'score_column', _first_present(result_payload, 'score_column') or _first_present(thresholding, 'score_column'))
        _maybe_add(mapping, 'anomaly_direction', _first_present(result_payload, 'anomaly_direction') or _first_present(thresholding, 'anomaly_direction'))
        _maybe_add(mapping, 'paired_threshold', _first_present(thresholding, 'threshold'))
        _maybe_add(mapping, 'figure_count', int(visuals.get('figure_count', 0) or 0), allow_empty_zero=True)

    return mapping


def _workflow_interpretation_text(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> str:
    thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
    visuals = result_payload.get('visuals', {}) if isinstance(result_payload.get('visuals', {}), MappingABC) else {}
    counts = result_payload.get('counts', {}) if isinstance(result_payload.get('counts', {}), MappingABC) else {}
    metrics = result_payload.get('metrics', {}) if isinstance(result_payload.get('metrics', {}), MappingABC) else {}
    figure_count = int(visuals.get('figure_count', 0) or 0)
    has_labels = result_payload.get('has_labels')

    if workflow == 'build':
        records_built = _first_present(result_payload, 'records_built') or _first_present(counts, 'records_built')
        parts = ['This stage should be read as dataset materialization rather than model judgment.']
        if records_built not in ('', None):
            parts.append('It establishes a reusable dataset handoff for `{0}` records, which is the foundation that later training, evaluation, and scoring packets will inherit.'.format(_format_countish(records_built)))
        if has_labels is False:
            parts.append('Because labels are absent, downstream evaluation and score packets should be interpreted as review-posture evidence rather than labeled performance proof.')
        parts.append('The main reader value is custody and reproducibility: the dataset contract is explicit, reusable, and ready for the next stage in the reporting spine.')
        return ' '.join(parts)

    if workflow == 'train':
        model_type = _first_present(result_payload, 'model_type')
        parts = ['This stage should be read as a model-publication handoff rather than as the final word on model quality.']
        if model_type not in ('', None):
            parts.append('The reported model type is `{0}`, which matters mainly as context for how the downstream evaluation and score surfaces should be interpreted.'.format(str(model_type)))
        if _nonempty_mapping_count(metrics) == 0 and figure_count == 0:
            parts.append('The current run records artifact custody more strongly than fit diagnostics, so the packet stays explicit about the absence of richer training metrics or visual posture.')
        elif figure_count > 0:
            parts.append('Declared training figures are present, which helps translate model posture into reader-facing evidence instead of leaving the packet as a pure artifact ledger.')
        else:
            parts.append('Metric evidence is available, but the packet should still be paired with downstream evaluation before it is treated as a readiness signal.')
        return ' '.join(parts)

    if workflow == 'evaluate':
        threshold = _first_present(thresholding, 'threshold') or _first_present(result_payload, 'threshold')
        flagged_records = _first_present(thresholding, 'flagged_records') or _first_present(result_payload, 'flagged_records')
        total_records = _first_present(thresholding, 'records_evaluated', 'records_scored') or _first_present(result_payload, 'records_evaluated', 'records_scored')
        parts = ['This stage defines the operating threshold and review burden for the paired score surface.']
        if threshold not in ('', None):
            parts.append('The current operating point is recorded at `{0}`.'.format(_format_countish(threshold)))
        if flagged_records not in ('', None) and total_records not in ('', None):
            parts.append('That selection yields `{0}` flagged records out of `{1}` evaluated records, which keeps the review volume concrete rather than abstract.'.format(_format_countish(flagged_records), _format_countish(total_records)))
        if has_labels is False:
            parts.append('Because labels are absent, threshold constraints in this packet should be read as operational guardrails rather than as verified labeled error rates.')
        if figure_count > 0:
            parts.append('Declared figures anchor the threshold story in visible evidence instead of leaving the operating point buried in tables alone.')
        return ' '.join(parts)

    if workflow == 'score':
        records_scored = _first_present(thresholding, 'records_scored') or _first_present(result_payload, 'records_scored')
        anomaly_direction = _first_present(result_payload, 'anomaly_direction') or _first_present(thresholding, 'anomaly_direction')
        parts = ['This stage exposes the score surface rather than making a semantic case judgment about the ranked records.']
        if records_scored not in ('', None):
            parts.append('The packet covers `{0}` scored records, which makes the ordering legible across the full scored set rather than only through a narrow flagged slice.'.format(_format_countish(records_scored)))
        if anomaly_direction not in ('', None):
            parts.append('The anomaly direction remains `{0}`, so the reader should interpret the review-relevant edge accordingly.'.format(str(anomaly_direction)))
        if figure_count > 0:
            parts.append('Declared visual evidence is present, which helps the reader connect the distribution shape to any paired threshold context without confusing score output with final review disposition.')
        else:
            parts.append('No declared score figure is present, so any threshold interpretation should stay anchored to the paired evaluation or aggregate surfaces rather than being inferred from absent visuals.')
        return ' '.join(parts)

    return _workflow_evidence_summary_text(workflow, str(report_payload.get('decision', '') or ''), result_payload)


def _append_stage_visual_surfaces(
    lines: list[str],
    workflow: str,
    result_payload: Mapping[str, Any],
    *,
    project_root: Path,
    report_md_path: Path,
) -> None:
    visuals = result_payload.get('visuals', {}) if isinstance(result_payload.get('visuals', {}), MappingABC) else {}
    figures = list(visuals.get('figures', []) or []) if isinstance(visuals, MappingABC) else []

    lines.append('## Visual surfaces')
    lines.append('')
    visual_summary = {
        'figure count': int(visuals.get('figure_count', len(figures)) or len(figures)),
        'lead figure': str(((figures[0] if figures else {}) if figures else {}).get('title', '') or ((figures[0] if figures else {}) if figures else {}).get('id', '') or 'none emitted'),
        'score direction': str(visuals.get('anomaly_direction', '') or '').strip(),
        'score column': str(visuals.get('score_column', '') or '').strip(),
    }
    if not figures:
        _append_code_summary_section(lines, '', visual_summary)
        lines.append(_workflow_missing_visual_note(workflow, result_payload))
        lines.append('')
        return

    _append_code_summary_section(lines, '', visual_summary)
    lines.append('These figures are declared by the packet itself, so the visual evidence stays tied to the same run contract as the narrative summary and companion JSON surfaces.')
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


def _workflow_missing_visual_note(workflow: str, result_payload: Mapping[str, Any]) -> str:
    if workflow == 'train':
        return 'No declared figures were emitted for this packet. Treat that as an honest reporting gap: the current training lane publishes artifact custody more strongly than plot-level model posture, so downstream evaluation should carry more of the explanatory burden.'
    if workflow == 'build':
        return 'No declared figures were emitted for this packet. The build stage can still be read through dataset counts and lineage continuity, but this packet does not pretend that a plot-backed dataset profile was published when it was not.'
    if workflow == 'evaluate':
        return 'No declared figures were emitted for this packet. That absence should be read as a current visualization gap rather than as evidence that the threshold posture no longer needs explicit visual support.'
    if workflow == 'score':
        return 'No declared figures were emitted for this packet. Any threshold interpretation should therefore remain anchored to the paired evaluation or aggregate surfaces instead of being inferred from an absent score figure.'
    return 'No declared figures were emitted for this packet, so the reader should treat the visual story as incomplete rather than assuming that a figure exists somewhere off-page.'


def _workflow_stage_handoff_text(
    workflow: str,
    report_payload: Mapping[str, Any],
    result_payload: Mapping[str, Any],
) -> str:
    decision = str(report_payload.get('decision', '') or '').strip().lower()
    if decision and decision != 'go':
        return 'The packet is not in a final `go` state, so downstream interpretation should remain conditional on the cited guardrails and the machine-readable companions.'

    base = WORKFLOW_NEXT_STEP_HINTS.get(
        workflow,
        'Use the related surfaces below to move from this narrative packet into the next workflow handoff or the machine-readable companions.',
    )
    if workflow == 'train':
        return base + ' The next useful read is whichever evaluation or scoring surface turns the published model artifact into observable downstream behavior.'
    if workflow == 'score':
        thresholding = result_payload.get('thresholding', {}) if isinstance(result_payload.get('thresholding', {}), MappingABC) else {}
        if _has_any_value(thresholding, 'threshold', 'report_md', 'report_json'):
            return base + ' Keep the paired threshold surface nearby so the score distribution is not mistaken for a standalone flagged-case decision.'
    return base


def _append_related_surfaces_section(
    lines: list[str],
    report_payload: Mapping[str, Any],
    *,
    project_root: Path,
    report_md_path: Path,
) -> None:
    items = _workflow_next_step_items(report_payload, project_root=project_root, report_md_path=report_md_path)
    lines.append('## Related surfaces')
    lines.append('')
    lines.append('Use these companion surfaces when you need the machine-readable evidence or the next useful route in the reporting spine.')
    lines.append('')
    if not items:
        lines.append('- Inspect `report.json` and `manifest.json` for the machine-readable companion surfaces.')
        lines.append('')
        return
    for item in items:
        lines.append('- {0}'.format(item))
    lines.append('')


def _has_any_value(mapping: Mapping[str, Any], *keys: str) -> bool:
    return _first_present(mapping, *keys) not in ('', None)


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value in ('', None, [], {}, ()):
            continue
        return value
    return None


def _maybe_add(mapping: Dict[str, Any], key: str, value: Any, *, allow_empty_zero: bool = False) -> None:
    if allow_empty_zero and value == 0:
        mapping[key] = value
        return
    if value in ('', None, [], {}, ()):
        return
    mapping[key] = value


def _nonempty_mapping_count(mapping: Mapping[str, Any]) -> int:
    return len([value for value in mapping.values() if value not in ('', None, [], {}, ())])


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