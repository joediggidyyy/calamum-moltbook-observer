from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ._util import (
    canonical_ds_workflow_name,
    ds_indexes_dir,
    ds_publication_aggregates_dir,
    ds_publication_internal_dir,
    ds_publication_internal_run_dir,
    ds_publication_dir,
    ds_publication_reference_dir,
    ds_publication_runs_dir,
    ds_publication_validations_dir,
    ds_runs_dir,
    find_project_root,
    iter_jsonl,
    normalize_repo_or_absolute_path,
    sanitize_run_id,
    utc_now_iso,
)
from .report_pack import _normalize_json_value, _report_markdown


PUBLISHED_REPORT_REQUIRED_KEYS = ('markdown', 'json', 'manifest')
PUBLISHED_IMAGE_SUFFIXES = {'.png', '.svg', '.jpg', '.jpeg', '.gif', '.webp'}
PUBLISHED_HUMAN_PATH_KEYS = (
    'markdown',
    'collection_markdown',
    'collection_history_markdown',
    'processing_markdown',
)
PUBLISHED_INTERNAL_PATH_KEYS = ('json', 'manifest')

_EPHEMERAL_RUN_ROOT_MARKERS = (
    'pytest',
    '/Temp/',
    '\\Temp\\',
    'AppData',
    'report_tmp',
)
_NON_PUBLISHABLE_WORKFLOWS = {'demo'}


def _is_ephemeral_run_root(run_root: str) -> bool:
    """Return True if a run-root path is from an ephemeral/test context and should be excluded from selector surfaces."""
    if not run_root:
        return False
    normalized = run_root.replace('\\', '/')
    return any(marker.replace('\\', '/') in normalized for marker in _EPHEMERAL_RUN_ROOT_MARKERS)


def _reset_publication_root(publication_root: Path) -> None:
    if not publication_root.exists():
        return
    for child in publication_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
            continue
        child.unlink()


def _tracked_ds_publication_paths(project_anchor: Path) -> Dict[str, Path]:
    publication_root = ds_publication_dir(project_anchor)
    aggregates_root = ds_publication_aggregates_dir(project_anchor)
    reference_root = ds_publication_reference_dir(project_anchor)
    validations_root = ds_publication_validations_dir(project_anchor)
    internal_root = ds_publication_internal_dir(project_anchor)
    internal_aggregates_root = internal_root / 'aggregates'
    internal_collections_root = internal_root / 'collections'
    indexes_root = ds_indexes_dir(project_anchor)
    collections_root = ds_publication_runs_dir(project_anchor)
    return {
        'publication_root': publication_root,
        'collections_root': collections_root,
        'aggregates_root': aggregates_root,
        'reference_root': reference_root,
        'validations_root': validations_root,
        'internal_root': internal_root,
        'internal_aggregates_root': internal_aggregates_root,
        'internal_collections_root': internal_collections_root,
        'indexes_root': indexes_root,
        'ledger_path': indexes_root / 'ds_run_index.jsonl',
        'latest_index_path': indexes_root / 'ds_latest.json',
        'latest_json_path': internal_aggregates_root / 'latest.json',
        'latest_md_path': aggregates_root / 'LATEST_COLLECTIONS.md',
        'by_workflow_json_path': internal_aggregates_root / 'workflow_rollup.json',
        'by_workflow_md_path': aggregates_root / 'WORKFLOW_ROLLUP.md',
        'thresholds_json_path': internal_aggregates_root / 'threshold_summary.json',
        'thresholds_md_path': aggregates_root / 'THRESHOLD_SUMMARY.md',
        'public_run_ledger_json_path': internal_aggregates_root / 'public_run_ledger.json',
        'public_run_ledger_md_path': aggregates_root / 'PUBLIC_RUN_LEDGER.md',
        'aggregate_report_json_path': internal_aggregates_root / 'aggregate_report.json',
        'aggregate_report_md_path': aggregates_root / 'AGGREGATE_REPORT.md',
        'index_md_path': publication_root / 'INDEX.md',
        'generated_surfaces_md_path': reference_root / 'GENERATED_REPORT_SURFACES.md',
        'validations_index_md_path': validations_root / 'INDEX.md',
    }


def _ensure_tracked_ds_publication_dirs(paths: Mapping[str, Path]) -> None:
    for key in (
        'indexes_root',
        'publication_root',
        'collections_root',
        'aggregates_root',
        'reference_root',
        'validations_root',
        'internal_root',
        'internal_aggregates_root',
        'internal_collections_root',
    ):
        Path(paths[key]).mkdir(parents=True, exist_ok=True)


def _empty_ds_latest_payload(project_root: Path, ledger_path: Path, updated_at_utc: str) -> Dict[str, Any]:
    return {
        'schema_version': '1.0',
        'family_id': 'ds_run',
        'updated_at_utc': str(updated_at_utc or ''),
        'ledger_path': normalize_repo_or_absolute_path(ledger_path, project_root),
        'latest_run': {},
        'by_workflow': {},
    }


def _write_tracked_ds_publication_outputs(
    *,
    project_root: Path,
    paths: Mapping[str, Path],
    published_runs: List[Dict[str, Any]],
    threshold_rows: List[Dict[str, Any]],
) -> Dict[str, str]:
    publication_root = Path(paths['publication_root'])
    latest_payload = _latest_publication_payload(project_root, published_runs, publication_root)
    by_workflow_payload = _by_workflow_publication_payload(project_root, published_runs, publication_root)
    thresholds_payload = _thresholds_publication_payload(project_root, threshold_rows, publication_root)
    public_run_ledger_payload = _public_run_ledger_payload(project_root, published_runs, threshold_rows, publication_root)
    aggregate_report_payload = _aggregate_report_payload(project_root, published_runs, threshold_rows, publication_root)

    latest_json_path = Path(paths['latest_json_path'])
    latest_md_path = Path(paths['latest_md_path'])
    by_workflow_json_path = Path(paths['by_workflow_json_path'])
    by_workflow_md_path = Path(paths['by_workflow_md_path'])
    thresholds_json_path = Path(paths['thresholds_json_path'])
    thresholds_md_path = Path(paths['thresholds_md_path'])
    public_run_ledger_json_path = Path(paths['public_run_ledger_json_path'])
    public_run_ledger_md_path = Path(paths['public_run_ledger_md_path'])
    aggregate_report_json_path = Path(paths['aggregate_report_json_path'])
    aggregate_report_md_path = Path(paths['aggregate_report_md_path'])
    index_md_path = Path(paths['index_md_path'])
    generated_surfaces_md_path = Path(paths['generated_surfaces_md_path'])
    validations_index_md_path = Path(paths['validations_index_md_path'])

    latest_json_path.write_text(json.dumps(latest_payload, indent=2, sort_keys=True), encoding='utf-8')
    latest_md_path.write_text(_latest_publication_markdown(project_root, latest_md_path, latest_payload), encoding='utf-8')
    by_workflow_json_path.write_text(json.dumps(by_workflow_payload, indent=2, sort_keys=True), encoding='utf-8')
    by_workflow_md_path.write_text(_by_workflow_publication_markdown(project_root, by_workflow_md_path, by_workflow_payload), encoding='utf-8')
    thresholds_json_path.write_text(json.dumps(thresholds_payload, indent=2, sort_keys=True), encoding='utf-8')
    thresholds_md_path.write_text(_thresholds_publication_markdown(project_root, thresholds_md_path, thresholds_payload), encoding='utf-8')
    public_run_ledger_json_path.write_text(json.dumps(public_run_ledger_payload, indent=2, sort_keys=True), encoding='utf-8')
    public_run_ledger_md_path.write_text(
        _public_run_ledger_markdown(
            project_root,
            public_run_ledger_md_path,
            public_run_ledger_payload,
            aggregate_report_md_path,
            latest_md_path,
            by_workflow_md_path,
            thresholds_md_path,
        ),
        encoding='utf-8',
    )
    aggregate_report_json_path.write_text(json.dumps(aggregate_report_payload, indent=2, sort_keys=True), encoding='utf-8')
    aggregate_report_md_path.write_text(
        _aggregate_report_markdown(
            project_root,
            aggregate_report_md_path,
            aggregate_report_payload,
            public_run_ledger_md_path,
            latest_md_path,
            by_workflow_md_path,
            thresholds_md_path,
        ),
        encoding='utf-8',
    )
    index_md_path.write_text(
        _ds_publication_index_markdown(
            project_root,
            index_md_path,
            aggregate_report_md_path,
            public_run_ledger_md_path,
            latest_payload,
            by_workflow_payload,
            thresholds_payload,
            published_runs,
        ),
        encoding='utf-8',
    )
    generated_surfaces_md_path.write_text(
        _generated_report_surfaces_markdown(
            project_root,
            generated_surfaces_md_path,
            aggregate_report_md_path,
            public_run_ledger_md_path,
            latest_md_path,
            by_workflow_md_path,
            thresholds_md_path,
        ),
        encoding='utf-8',
    )
    validations_index_md_path.write_text(
        _validations_index_markdown(project_root, validations_index_md_path),
        encoding='utf-8',
    )

    return {
        'index_md': normalize_repo_or_absolute_path(index_md_path, project_root),
        'aggregate_report_json': normalize_repo_or_absolute_path(aggregate_report_json_path, project_root),
        'aggregate_report_md': normalize_repo_or_absolute_path(aggregate_report_md_path, project_root),
        'public_run_ledger_json': normalize_repo_or_absolute_path(public_run_ledger_json_path, project_root),
        'public_run_ledger_md': normalize_repo_or_absolute_path(public_run_ledger_md_path, project_root),
        'latest_json': normalize_repo_or_absolute_path(latest_json_path, project_root),
        'latest_md': normalize_repo_or_absolute_path(latest_md_path, project_root),
        'by_workflow_json': normalize_repo_or_absolute_path(by_workflow_json_path, project_root),
        'by_workflow_md': normalize_repo_or_absolute_path(by_workflow_md_path, project_root),
        'thresholds_json': normalize_repo_or_absolute_path(thresholds_json_path, project_root),
        'thresholds_md': normalize_repo_or_absolute_path(thresholds_md_path, project_root),
        'generated_surfaces_md': normalize_repo_or_absolute_path(generated_surfaces_md_path, project_root),
        'validations_index_md': normalize_repo_or_absolute_path(validations_index_md_path, project_root),
    }


def reset_tracked_ds_publication_state(*, project_anchor: Path) -> Dict[str, Any]:
    project_root = find_project_root(project_anchor)
    paths = _tracked_ds_publication_paths(project_anchor)

    _reset_publication_root(Path(paths['collections_root']))
    _reset_publication_root(Path(paths['internal_collections_root']))
    _ensure_tracked_ds_publication_dirs(paths)

    reset_at_utc = utc_now_iso()
    ledger_path = Path(paths['ledger_path'])
    latest_index_path = Path(paths['latest_index_path'])
    ledger_path.write_text('', encoding='utf-8')
    latest_index_payload = _empty_ds_latest_payload(project_root, ledger_path, reset_at_utc)
    latest_index_path.write_text(json.dumps(latest_index_payload, indent=2, sort_keys=True), encoding='utf-8')

    aggregate_paths = _write_tracked_ds_publication_outputs(
        project_root=project_root,
        paths=paths,
        published_runs=[],
        threshold_rows=[],
    )

    return {
        'decision': 'go',
        'reason_codes': [],
        'publish_root': normalize_repo_or_absolute_path(Path(paths['publication_root']), project_root),
        'published_run_count': 0,
        'excluded_entry_count': 0,
        'current_run': {},
        'reset_at_utc': reset_at_utc,
        'index_paths': {
            'ledger_path': normalize_repo_or_absolute_path(ledger_path, project_root),
            'latest_index_path': normalize_repo_or_absolute_path(latest_index_path, project_root),
        },
        'aggregate_paths': aggregate_paths,
    }


def append_ds_run_index(*, project_anchor: Path, manifest_payload: Mapping[str, Any]) -> Dict[str, Any]:
    project_root = find_project_root(project_anchor)
    indexes_dir = ds_indexes_dir(project_anchor)
    indexes_dir.mkdir(parents=True, exist_ok=True)

    ledger_path = indexes_dir / 'ds_run_index.jsonl'
    latest_path = indexes_dir / 'ds_latest.json'
    entry = _build_entry(manifest_payload, project_root, ledger_path, latest_path)

    with ledger_path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(entry, sort_keys=True) + '\n')

    latest_payload = _refresh_latest(latest_path, entry)
    latest_path.write_text(json.dumps(latest_payload, indent=2, sort_keys=True), encoding='utf-8')

    return {
        'entry': entry,
        'latest': latest_payload,
        'ledger_path': entry['ledger_path'],
        'latest_index_path': entry['latest_index_path'],
    }


def load_ds_run_manifest_records(*, project_anchor: Path) -> List[Dict[str, Any]]:
    project_root = find_project_root(project_anchor)
    ledger_path = ds_indexes_dir(project_anchor) / 'ds_run_index.jsonl'
    if not ledger_path.exists():
        return []

    rows: List[Dict[str, Any]] = []
    for line in iter_jsonl(ledger_path):
        if not isinstance(line.obj, dict):
            continue
        entry = dict(line.obj)
        run_root = str(entry.get('run_root', '') or '').strip()
        if _is_ephemeral_run_root(run_root):
            continue
        report_paths = dict(entry.get('report_paths', {}) or {})
        manifest_path = _resolve_repo_path(project_root, str(report_paths.get('manifest', '') or '').strip())
        rows.append(
            {
                'entry': entry,
                'manifest_path': normalize_repo_or_absolute_path(manifest_path, project_root) if manifest_path is not None else '',
                'manifest_payload': _read_json_dict(manifest_path),
            }
        )

    rows.sort(
        key=lambda row: (
            _publication_sort_key(str((row.get('entry', {}) if isinstance(row.get('entry', {}), dict) else {}).get('timestamp_utc', ''))),
            str((row.get('entry', {}) if isinstance(row.get('entry', {}), dict) else {}).get('run_id', '')),
        ),
        reverse=True,
    )
    return rows


def refresh_tracked_ds_publication(
    *,
    project_anchor: Path,
    current_manifest_payload: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    project_root = find_project_root(project_anchor)
    paths = _tracked_ds_publication_paths(project_anchor)
    publication_root = Path(paths['publication_root'])
    _reset_publication_root(publication_root)
    _reset_publication_root(Path(paths['internal_collections_root']))
    _ensure_tracked_ds_publication_dirs(paths)

    records = load_ds_run_manifest_records(project_anchor=project_anchor)
    publishable: List[Dict[str, Any]] = []
    excluded_entries = 0
    for record in records:
        candidate = _build_publication_candidate(record, project_root, project_anchor)
        if candidate is None:
            excluded_entries += 1
            continue
        publishable.append(candidate)

    publishable.sort(key=lambda candidate: (_publication_sort_key(str(candidate.get('timestamp_utc', ''))), str(candidate.get('run_id', ''))))

    published_runs: List[Dict[str, Any]] = []
    for candidate in publishable:
        _publish_candidate(candidate)
        published_summary = _published_run_summary(candidate, project_root)
        published_runs.append(published_summary)

    _write_collection_reports(publishable, project_root)

    threshold_rows = _threshold_summary_rows(published_runs)
    aggregate_paths = _write_tracked_ds_publication_outputs(
        project_root=project_root,
        paths=paths,
        published_runs=published_runs,
        threshold_rows=threshold_rows,
    )

    current_run: Dict[str, Any] = {}
    if isinstance(current_manifest_payload, Mapping):
        current_key = _publication_identity_key(
            workflow=str(current_manifest_payload.get('workflow', '')),
            run_id=str(current_manifest_payload.get('run_id', '')),
            timestamp_utc=str(current_manifest_payload.get('timestamp_utc', '')),
        )
        for summary in published_runs:
            if _publication_identity_key(
                workflow=str(summary.get('workflow', '')),
                run_id=str(summary.get('run_id', '')),
                timestamp_utc=str(summary.get('timestamp_utc', '')),
            ) == current_key:
                current_run = dict(summary)
                break

    return {
        'decision': 'go',
        'reason_codes': [],
        'publish_root': normalize_repo_or_absolute_path(publication_root, project_root),
        'published_run_count': int(len(published_runs)),
        'excluded_entry_count': int(excluded_entries),
        'current_run': current_run,
        'aggregate_paths': aggregate_paths,
    }


def publication_eligibility_reasons(*, project_anchor: Path, manifest_payload: Mapping[str, Any]) -> List[str]:
    project_root = find_project_root(project_anchor)
    reasons: List[str] = []
    workflow = canonical_ds_workflow_name(str(manifest_payload.get('workflow', '') or '').strip())
    if workflow in _NON_PUBLISHABLE_WORKFLOWS:
        reasons.append('publication_skipped:workflow_not_publishable')
    decision = str(manifest_payload.get('decision', '') or '').strip().lower()
    if decision != 'go':
        reasons.append('publication_skipped:decision_not_publishable')
    if str(manifest_payload.get('run_root_policy', '') or '').strip().lower() != 'canonical':
        reasons.append('publication_skipped:noncanonical_run_root')

    run_root_path = _resolve_repo_path(project_root, str(manifest_payload.get('run_root', '') or '').strip())
    canonical_runs_root = ds_runs_dir(project_anchor)
    if run_root_path is None:
        reasons.append('publication_skipped:run_root_missing')
    else:
        try:
            run_root_path.resolve().relative_to(canonical_runs_root.resolve())
        except Exception:
            reasons.append('publication_skipped:run_root_outside_canonical_spine')

    report_paths = dict(manifest_payload.get('report_paths', {}) or {})
    for key in PUBLISHED_REPORT_REQUIRED_KEYS:
        required_path = _resolve_repo_path(project_root, str(report_paths.get(key, '') or '').strip())
        if required_path is None or not required_path.exists():
            reasons.append('publication_skipped:missing_{0}'.format(key))

    if not sanitize_run_id(str(manifest_payload.get('run_id', '') or '').strip()):
        reasons.append('publication_skipped:run_id_missing')
    if not str(manifest_payload.get('timestamp_utc', '') or '').strip():
        reasons.append('publication_skipped:timestamp_missing')
    return reasons


def _resolve_repo_path(project_root: Path, ref: str) -> Optional[Path]:
    text = str(ref or '').strip()
    if not text:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        return candidate.resolve()
    except Exception:
        return candidate


def _read_json_dict(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_entry(
    manifest_payload: Mapping[str, Any],
    project_root: Path,
    ledger_path: Path,
    latest_path: Path,
) -> Dict[str, Any]:
    workflow = canonical_ds_workflow_name(str(manifest_payload.get('workflow', '')))
    report_paths = dict(manifest_payload.get('report_paths', {}) or {})
    return {
        'schema_version': str(manifest_payload.get('schema_version', '1.0')),
        'kind': str(manifest_payload.get('kind', 'run')),
        'family_id': str(manifest_payload.get('family_id', 'ds_run')),
        'category': str(manifest_payload.get('category', 'ds-run')),
        'workflow': workflow,
        'timestamp_utc': str(manifest_payload.get('timestamp_utc', '')),
        'run_id': str(manifest_payload.get('run_id', '')),
        'collection_alias': str(manifest_payload.get('collection_alias', '')),
        'decision': str(manifest_payload.get('decision', '')),
        'summary': str(manifest_payload.get('summary', '')),
        'producer_command': str(manifest_payload.get('producer_command', '')),
        'producer_entrypoint': str(manifest_payload.get('producer_entrypoint', '')),
        'report_paths': report_paths,
        'ledger_path': normalize_repo_or_absolute_path(ledger_path, project_root),
        'latest_index_path': normalize_repo_or_absolute_path(latest_path, project_root),
        'run_root': str(manifest_payload.get('run_root', '')),
        'git': dict(manifest_payload.get('git', {}) or {}),
        'result': dict(manifest_payload.get('result', {}) or {}),
        'context': dict(manifest_payload.get('context', {}) or {}),
        'lineage': dict(manifest_payload.get('lineage', {}) or {}),
    }


def _refresh_latest(latest_path: Path, entry: Mapping[str, Any]) -> Dict[str, Any]:
    existing: Dict[str, Any] = {}
    if latest_path.exists():
        try:
            loaded = json.loads(latest_path.read_text(encoding='utf-8'))
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}

    latest_summary = _entry_summary(entry)
    by_workflow = dict(existing.get('by_workflow', {}) or {})
    by_workflow[str(entry.get('workflow', ''))] = latest_summary

    return {
        'schema_version': str(entry.get('schema_version', '1.0')),
        'family_id': str(entry.get('family_id', 'ds_run')),
        'updated_at_utc': str(entry.get('timestamp_utc', '')),
        'ledger_path': str(entry.get('ledger_path', '')),
        'latest_run': latest_summary,
        'by_workflow': by_workflow,
    }


def _entry_summary(entry: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(entry.get('result', {}) or {})
    return {
        'collection_alias': str(entry.get('collection_alias', '')),
        'workflow': str(entry.get('workflow', '')),
        'run_id': str(entry.get('run_id', '')),
        'timestamp_utc': str(entry.get('timestamp_utc', '')),
        'decision': str(result.get('decision', entry.get('decision', ''))),
        'summary': str(result.get('summary', entry.get('summary', ''))),
        'run_root': str(entry.get('run_root', '')),
        'report_paths': dict(entry.get('report_paths', {}) or {}),
        'context': dict(entry.get('context', {}) or {}),
    }


def _build_publication_candidate(record: Mapping[str, Any], project_root: Path, project_anchor: Path) -> Optional[Dict[str, Any]]:
    entry = dict(record.get('entry', {}) or {}) if isinstance(record.get('entry', {}), dict) else {}
    manifest_payload = dict(record.get('manifest_payload', {}) or {}) if isinstance(record.get('manifest_payload', {}), dict) else {}
    if not manifest_payload:
        return None
    if publication_eligibility_reasons(project_anchor=project_anchor, manifest_payload=manifest_payload):
        return None

    run_id = sanitize_run_id(str(manifest_payload.get('run_id', '') or entry.get('run_id', '') or '').strip())
    workflow = canonical_ds_workflow_name(str(manifest_payload.get('workflow', '') or entry.get('workflow', '') or '').strip())
    timestamp_utc = str(manifest_payload.get('timestamp_utc', '') or entry.get('timestamp_utc', '') or '').strip()
    if not run_id or not timestamp_utc:
        return None

    collection_alias = _resolve_collection_alias(manifest_payload, project_root, project_anchor, run_id)

    report_paths = dict(manifest_payload.get('report_paths', {}) or {})
    source_report_paths: Dict[str, Path] = {}
    for key in PUBLISHED_REPORT_REQUIRED_KEYS:
        resolved = _resolve_repo_path(project_root, str(report_paths.get(key, '') or '').strip())
        if resolved is None or not resolved.exists():
            return None
        source_report_paths[key] = resolved

    publication_dir = ds_publication_runs_dir(project_anchor) / collection_alias
    collection_dir = publication_dir / 'collection'
    processing_dir = publication_dir / 'processing' / _published_workflow_dir_name(workflow)
    internal_dir = ds_publication_internal_run_dir(project_anchor, run_id)
    figure_sources = _collect_figure_sources(manifest_payload, project_root)
    normalized_source_report_paths = {
        key: normalize_repo_or_absolute_path(value, project_root)
        for key, value in source_report_paths.items()
    }
    source_run_root = normalize_repo_or_absolute_path(
        _resolve_repo_path(project_root, str(manifest_payload.get('run_root', '') or '').strip()),
        project_root,
    )
    published_run_dir = normalize_repo_or_absolute_path(publication_dir, project_root)
    return {
        'project_root': project_root,
        'entry': entry,
        'manifest_payload': manifest_payload,
        'collection_alias': collection_alias,
        'workflow': workflow,
        'run_id': run_id,
        'timestamp_utc': timestamp_utc,
        'source_report_paths': source_report_paths,
        'normalized_source_report_paths': normalized_source_report_paths,
        'source_run_root': source_run_root,
        'published_run_dir': published_run_dir,
        'publication_dir': publication_dir,
        'collection_dir': collection_dir,
        'processing_dir': processing_dir,
        'internal_dir': internal_dir,
        'figure_sources': figure_sources,
    }


def _collect_figure_sources(manifest_payload: Mapping[str, Any], project_root: Path) -> List[Path]:
    sources: List[Path] = []
    seen: set = set()

    def _append_source(raw_value: Any) -> bool:
        resolved = _resolve_repo_path(project_root, str(raw_value or '').strip())
        if resolved is None or not resolved.exists() or not resolved.is_file():
            return False
        if resolved.suffix.lower() not in PUBLISHED_IMAGE_SUFFIXES:
            return False
        key = str(resolved.resolve())
        if key in seen:
            return False
        seen.add(key)
        sources.append(resolved)
        return True

    result = dict(manifest_payload.get('result', {}) or {}) if isinstance(manifest_payload.get('result', {}), dict) else {}
    visuals = dict(result.get('visuals', {}) or {}) if isinstance(result.get('visuals', {}), dict) else {}
    declared_figures = list(visuals.get('figures', []) or [])
    declared_count = 0
    for figure in declared_figures:
        if not isinstance(figure, dict):
            continue
        if _append_source(figure.get('path')):
            declared_count += 1
    if declared_count:
        return sources

    artifacts = dict(manifest_payload.get('artifacts', {}) or {}) if isinstance(manifest_payload.get('artifacts', {}), dict) else {}
    artifact_count = 0
    for value in artifacts.values():
        if _append_source(value):
            artifact_count += 1
    if artifact_count:
        return sources

    run_root = _resolve_repo_path(project_root, str(manifest_payload.get('run_root', '') or '').strip())
    figures_dir = (run_root / 'figures') if run_root is not None else None
    if figures_dir is not None and figures_dir.exists() and figures_dir.is_dir():
        for path in sorted(figures_dir.rglob('*')):
            _append_source(path)
    return sources


def _published_report_paths(
    *,
    publication_dir: Path,
    collection_dir: Path,
    collection_history_report_path: Path,
    processing_report_path: Path,
    internal_dir: Path,
    project_root: Path,
) -> Dict[str, str]:
    return {
        'markdown': normalize_repo_or_absolute_path(collection_history_report_path, project_root),
        'collection_markdown': normalize_repo_or_absolute_path(collection_history_report_path, project_root),
        'collection_history_markdown': normalize_repo_or_absolute_path(collection_history_report_path, project_root),
        'processing_markdown': normalize_repo_or_absolute_path(processing_report_path, project_root),
        'json': normalize_repo_or_absolute_path(internal_dir / 'publication_report.json', project_root),
        'manifest': normalize_repo_or_absolute_path(internal_dir / 'publication_manifest.json', project_root),
        'published_run_dir': normalize_repo_or_absolute_path(publication_dir, project_root),
    }


def _publication_string_replacements(
    project_root: Path,
    normalized_source_report_paths: Mapping[str, str],
    published_report_paths: Mapping[str, str],
    figures_dir: Path,
    figure_sources: List[Path],
) -> Dict[str, str]:
    replacements: Dict[str, str] = {}
    replacement_targets = {
        'markdown': 'processing_markdown',
        'json': 'json',
        'manifest': 'manifest',
    }
    for key in PUBLISHED_REPORT_REQUIRED_KEYS:
        source_value = str(normalized_source_report_paths.get(key, '') or '').strip()
        target_value = str(published_report_paths.get(replacement_targets.get(key, key), '') or '').strip()
        if source_value and target_value:
            replacements[source_value] = target_value
    for source in figure_sources:
        source_value = normalize_repo_or_absolute_path(source, project_root)
        target_value = normalize_repo_or_absolute_path(figures_dir / source.name, project_root)
        replacements[source_value] = target_value
    return replacements


def _rewrite_publication_refs(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, dict):
        return {str(key): _rewrite_publication_refs(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_publication_refs(item, replacements) for item in value]
    if isinstance(value, tuple):
        return [_rewrite_publication_refs(item, replacements) for item in value]
    if isinstance(value, str):
        return str(replacements.get(value, value))
    return value


def _build_published_payload(payload: Mapping[str, Any], candidate: Mapping[str, Any], *, project_root: Path) -> Dict[str, Any]:
    normalized_payload = _normalize_json_value(dict(payload or {}), project_root)
    rewritten_payload = _rewrite_publication_refs(
        normalized_payload,
        dict(candidate.get('publication_string_replacements', {}) or {}),
    )
    if not isinstance(rewritten_payload, dict):
        rewritten_payload = {}

    source_run_root = str(candidate.get('source_run_root', '') or '')
    source_report_paths = dict(candidate.get('normalized_source_report_paths', {}) or {})
    published_run_dir = str(candidate.get('published_run_dir', '') or '')
    published_report_paths = dict(candidate.get('published_report_paths', {}) or {})

    rewritten_payload['report_dir'] = published_run_dir
    rewritten_payload['report_paths'] = dict(published_report_paths)
    rewritten_payload['source_run_root'] = source_run_root
    rewritten_payload['source_report_paths'] = dict(source_report_paths)
    rewritten_payload['published_run_dir'] = published_run_dir

    lineage = dict(rewritten_payload.get('lineage', {}) or {})
    lineage.setdefault('source_run_root', source_run_root)
    lineage.setdefault('source_report_paths', dict(source_report_paths))
    rewritten_payload['lineage'] = lineage
    return rewritten_payload


def _publish_candidate(candidate: Mapping[str, Any]) -> None:
    publication_dir = Path(candidate['publication_dir'])
    collection_dir = Path(candidate['collection_dir'])
    processing_dir = Path(candidate['processing_dir'])
    internal_dir = Path(candidate['internal_dir'])
    project_root = Path(candidate['project_root'])
    publication_dir.mkdir(parents=True, exist_ok=True)
    collection_dir.mkdir(parents=True, exist_ok=True)
    processing_dir.mkdir(parents=True, exist_ok=True)
    internal_dir.mkdir(parents=True, exist_ok=True)

    source_report_paths = dict(candidate.get('source_report_paths', {}) or {})
    source_report_payload = _read_json_dict(source_report_paths.get('json'))
    source_manifest_payload = _read_json_dict(source_report_paths.get('manifest'))
    if not source_report_payload:
        source_report_payload = dict(candidate.get('manifest_payload', {}) or {})
    if not source_manifest_payload:
        source_manifest_payload = dict(candidate.get('manifest_payload', {}) or {})

    collection_history_report_md_path = _next_collection_report_path(
        collection_dir=collection_dir,
        timestamp_utc=str(candidate.get('timestamp_utc', '') or ''),
    )
    processing_report_md_path = _next_processing_report_path(
        processing_dir=processing_dir,
        timestamp_utc=str(candidate.get('timestamp_utc', '') or ''),
        workflow=str(candidate.get('workflow', '') or ''),
    )
    figures_dir = processing_dir / 'figures' / processing_report_md_path.stem
    published_report_paths = _published_report_paths(
        publication_dir=publication_dir,
        collection_dir=collection_dir,
        collection_history_report_path=collection_history_report_md_path,
        processing_report_path=processing_report_md_path,
        internal_dir=internal_dir,
        project_root=project_root,
    )
    publication_string_replacements = _publication_string_replacements(
        project_root,
        dict(candidate.get('normalized_source_report_paths', {}) or {}),
        published_report_paths,
        figures_dir,
        list(candidate.get('figure_sources', []) or []),
    )
    if isinstance(candidate, dict):
        candidate['published_report_paths'] = published_report_paths
        candidate['publication_string_replacements'] = publication_string_replacements

    published_report_payload = _build_published_payload(source_report_payload, candidate, project_root=project_root)
    published_manifest_payload = _build_published_payload(source_manifest_payload, candidate, project_root=project_root)

    report_json_path = internal_dir / 'publication_report.json'
    manifest_json_path = internal_dir / 'publication_manifest.json'

    report_json_path.write_text(json.dumps(published_report_payload, indent=2, sort_keys=True), encoding='utf-8')
    manifest_json_path.write_text(json.dumps(published_manifest_payload, indent=2, sort_keys=True), encoding='utf-8')
    processing_report_md_path.write_text(
        _report_markdown(
            _human_processing_payload(published_report_payload),
            project_root=project_root,
            report_md_path=processing_report_md_path,
        ),
        encoding='utf-8',
    )

    figure_sources = list(candidate.get('figure_sources', []) or [])
    if figure_sources:
        figures_dir.mkdir(parents=True, exist_ok=True)
        published_figures: List[str] = []
        for source in figure_sources:
            target = figures_dir / source.name
            shutil.copy2(source, target)
            published_figures.append(normalize_repo_or_absolute_path(target, project_root))
        if isinstance(candidate, dict):
            candidate['published_figures'] = published_figures
    elif isinstance(candidate, dict):
        candidate['published_figures'] = []

    if isinstance(candidate, dict):
        candidate['published_report_payload'] = published_report_payload
        candidate['published_manifest_payload'] = published_manifest_payload


def _published_run_summary(candidate: Mapping[str, Any], project_root: Path) -> Dict[str, Any]:
    report_payload = dict(candidate.get('published_report_payload', {}) or {})
    manifest_payload = dict(candidate.get('published_manifest_payload', {}) or candidate.get('manifest_payload', {}) or {})
    publication_dir = Path(candidate['publication_dir'])
    source_report_paths = dict(candidate.get('source_report_paths', {}) or {})
    normalized_source_report_paths = dict(candidate.get('normalized_source_report_paths', {}) or {})
    published_report_paths = dict(candidate.get('published_report_paths', {}) or {})
    figure_paths = list(candidate.get('published_figures', []) or [])
    source_run_root = str(report_payload.get('source_run_root', '') or manifest_payload.get('source_run_root', '') or candidate.get('source_run_root', '') or manifest_payload.get('run_root', ''))
    published_run_dir = str(report_payload.get('published_run_dir', '') or manifest_payload.get('published_run_dir', '') or candidate.get('published_run_dir', '') or normalize_repo_or_absolute_path(publication_dir, project_root))
    return {
        'collection_alias': str(candidate.get('collection_alias', '') or ''),
        'workflow': str(candidate.get('workflow', '')),
        'run_id': str(candidate.get('run_id', '')),
        'timestamp_utc': str(candidate.get('timestamp_utc', '')),
        'decision': str(manifest_payload.get('decision', '')),
        'summary': str(manifest_payload.get('summary', '')),
        'source_run_root': source_run_root,
        'source_manifest_path': str(normalized_source_report_paths.get('manifest', '') or normalize_repo_or_absolute_path(source_report_paths.get('manifest'), project_root)),
        'source_report_paths': dict(report_payload.get('source_report_paths', {}) or manifest_payload.get('source_report_paths', {}) or normalized_source_report_paths),
        'published_run_dir': published_run_dir,
        'published_report_paths': dict(report_payload.get('report_paths', {}) or manifest_payload.get('report_paths', {}) or published_report_paths),
        'published_figures': figure_paths,
        'figure_count': int(len(figure_paths)),
        'context': dict(report_payload.get('context', {}) or manifest_payload.get('context', {}) or {}),
        'result': dict(report_payload.get('result', {}) or manifest_payload.get('result', {}) or {}),
    }


def _threshold_summary_row(published_summary: Mapping[str, Any], paired_score_summary: Optional[Mapping[str, Any]] = None) -> Optional[Dict[str, Any]]:
    workflow = canonical_ds_workflow_name(str(published_summary.get('workflow', '')))
    if workflow != 'evaluate':
        return None

    collection_alias = str(published_summary.get('collection_alias', '') or '').strip()
    published_eval_path = str(_published_processing_report_path(published_summary) or '')
    if not collection_alias or not published_eval_path:
        return None

    result = dict(published_summary.get('result', {}) or {})
    context = dict(published_summary.get('context', {}) or {})
    thresholding = dict(result.get('thresholding', {}) or {}) if isinstance(result.get('thresholding', {}), dict) else {}

    threshold_value = thresholding.get('threshold', result.get('threshold'))
    target_fpr = thresholding.get('target_fpr', context.get('max_fpr'))
    actual_fpr = thresholding.get('actual_fpr')
    flagged_records = thresholding.get('flagged_records')
    records_scored = thresholding.get('records_scored', result.get('records_scored'))
    if threshold_value in ('', None) and target_fpr in ('', None) and actual_fpr in ('', None) and flagged_records in ('', None):
        return None

    paired_score_path = ''
    if isinstance(paired_score_summary, Mapping):
        paired_run_id = str(paired_score_summary.get('run_id', '') or '')
        paired_score_report_path = str(_published_processing_report_path(paired_score_summary) or '')
        if paired_run_id and paired_run_id != str(published_summary.get('run_id', '') or '') and paired_score_report_path:
            paired_score_path = paired_score_report_path

    return {
        'collection_alias': collection_alias,
        'workflow': str(published_summary.get('workflow', '')),
        'run_id': str(published_summary.get('run_id', '')),
        'timestamp_utc': str(published_summary.get('timestamp_utc', '')),
        'evaluation_date_utc': str(published_summary.get('timestamp_utc', '')),
        'threshold': threshold_value,
        'target_fpr': target_fpr,
        'actual_fpr': actual_fpr,
        'flagged_records': flagged_records,
        'records_scored': records_scored,
        'flagged_share': _threshold_flagged_share(actual_fpr, flagged_records, records_scored),
        'anomaly_direction': str(thresholding.get('anomaly_direction', result.get('anomaly_direction', context.get('anomaly_direction', ''))) or ''),
        'published_report_md': published_eval_path,
        'paired_score_report_md': paired_score_path,
        'source_run_root': str(published_summary.get('source_run_root', '')),
    }


def _latest_publication_payload(project_root: Path, published_runs: List[Dict[str, Any]], publication_root: Path) -> Dict[str, Any]:
    latest_run = dict(published_runs[-1]) if published_runs else {}
    return {
        'schema_version': '1.0',
        'family_id': 'ds_publication',
        'publish_root': normalize_repo_or_absolute_path(publication_root, project_root),
        'published_at_utc': str(latest_run.get('timestamp_utc', '')),
        'published_run_count': int(len(published_runs)),
        'latest_run': latest_run,
        'collection_rows': _collection_overview_rows(published_runs),
    }


def _by_workflow_publication_payload(project_root: Path, published_runs: List[Dict[str, Any]], publication_root: Path) -> Dict[str, Any]:
    workflows: Dict[str, Dict[str, Any]] = {}
    for summary in published_runs:
        workflow = str(summary.get('workflow', ''))
        slot = workflows.setdefault(workflow, {'count': 0, 'latest_run': {}})
        slot['count'] = int(slot.get('count', 0)) + 1
        slot['latest_run'] = dict(summary)
    return {
        'schema_version': '1.0',
        'family_id': 'ds_publication',
        'publish_root': normalize_repo_or_absolute_path(publication_root, project_root),
        'published_run_count': int(len(published_runs)),
        'workflows': workflows,
    }


def _thresholds_publication_payload(project_root: Path, threshold_rows: List[Dict[str, Any]], publication_root: Path) -> Dict[str, Any]:
    return {
        'schema_version': '1.0',
        'family_id': 'ds_publication',
        'publish_root': normalize_repo_or_absolute_path(publication_root, project_root),
        'threshold_run_count': int(len(threshold_rows)),
        'threshold_rows': threshold_rows,
    }


def _collection_overview_rows(published_runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for summary in published_runs:
        alias = str(summary.get('collection_alias', '') or '').strip()
        if not alias:
            continue
        grouped.setdefault(alias, []).append(dict(summary))

    rows: List[Dict[str, Any]] = []
    for alias, summaries in grouped.items():
        ordered = sorted(
            summaries,
            key=lambda summary: (_publication_sort_key(str(summary.get('timestamp_utc', ''))), str(summary.get('run_id', ''))),
        )
        latest = dict(ordered[-1]) if ordered else {}
        latest_by_workflow: Dict[str, Dict[str, Any]] = {}
        for summary in ordered:
            latest_by_workflow[str(summary.get('workflow', ''))] = dict(summary)
        context = dict(latest.get('context', {}) or {}) if isinstance(latest.get('context', {}), dict) else {}
        rows.append(
            {
                'collection_alias': alias,
                'published_run_count': int(len(ordered)),
                'latest_timestamp_utc': str(latest.get('timestamp_utc', '')),
                'latest_run': latest,
                'source': str(context.get('source', '') or ''),
                'mode': str(context.get('mode', '') or ''),
                'latest_stage_labels': ', '.join(sorted(latest_by_workflow.keys())),
                'reason_to_open': _collection_reason_to_open(latest),
            }
        )
    rows.sort(key=lambda row: (_publication_sort_key(str(row.get('latest_timestamp_utc', ''))), str(row.get('collection_alias', ''))), reverse=True)
    return rows


def _collection_reason_to_open(summary: Mapping[str, Any]) -> str:
    result = dict(summary.get('result', {}) or {}) if isinstance(summary.get('result', {}), dict) else {}
    thresholding = dict(result.get('thresholding', {}) or {}) if isinstance(result.get('thresholding', {}), dict) else {}
    if thresholding or result.get('threshold') not in ('', None):
        return 'Threshold-bearing packet with current guardrail output.'
    workflow = canonical_ds_workflow_name(str(summary.get('workflow', '')))
    if workflow == 'pipeline':
        return 'End-to-end packet showing the current combined run outcome.'
    if workflow == 'build':
        return 'Dataset-build packet for the latest materialized collection.'
    if workflow == 'train':
        return 'Training packet for the latest model-building lane.'
    if workflow == 'evaluate':
        return 'Evaluation packet with the latest validation signal.'
    if workflow == 'score':
        return 'Scoring packet with the latest anomaly output.'
    return 'Latest published packet for this collection.'


def _workflow_contribution_note(workflow: str) -> str:
    token = canonical_ds_workflow_name(workflow)
    if token == 'build':
        return 'Defines the dataset packet baseline.'
    if token == 'train':
        return 'Carries the latest model-training outcome.'
    if token == 'evaluate':
        return 'Captures validation and threshold interpretation.'
    if token == 'score':
        return 'Captures scored anomaly output for reader follow-through.'
    if token == 'pipeline':
        return 'Shows the combined end-to-end execution lane.'
    return 'Maintains a current packet lane for this workflow family.'


def _threshold_summary_rows(published_runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest_score_by_alias: Dict[str, Dict[str, Any]] = {}
    for summary in sorted(
        [dict(summary) for summary in published_runs if isinstance(summary, dict)],
        key=lambda summary: (_publication_sort_key(str(summary.get('timestamp_utc', ''))), str(summary.get('run_id', ''))),
    ):
        if canonical_ds_workflow_name(str(summary.get('workflow', ''))) == 'score':
            alias = str(summary.get('collection_alias', '') or '').strip()
            if alias:
                latest_score_by_alias[alias] = dict(summary)

    rows: List[Dict[str, Any]] = []
    for summary in published_runs:
        alias = str(summary.get('collection_alias', '') or '').strip()
        row = _threshold_summary_row(summary, latest_score_by_alias.get(alias))
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda row: (_publication_sort_key(str(row.get('timestamp_utc', ''))), str(row.get('run_id', ''))), reverse=True)
    return rows


def _public_run_ledger_payload(
    project_root: Path,
    published_runs: List[Dict[str, Any]],
    threshold_rows: List[Dict[str, Any]],
    publication_root: Path,
) -> Dict[str, Any]:
    collection_rows = _collection_overview_rows(published_runs)
    source_mode_counts: Dict[str, int] = {}
    for summary in published_runs:
        context = dict(summary.get('context', {}) or {}) if isinstance(summary.get('context', {}), dict) else {}
        source = str(context.get('source', '') or 'unspecified')
        mode = str(context.get('mode', '') or 'unspecified')
        key = '{0}|{1}'.format(source, mode)
        source_mode_counts[key] = int(source_mode_counts.get(key, 0)) + 1

    source_mode_rows = []
    for key in sorted(source_mode_counts.keys()):
        source, mode = key.split('|', 1)
        source_mode_rows.append({'source': source, 'mode': mode, 'count': int(source_mode_counts[key])})

    workflows = _by_workflow_publication_payload(project_root, published_runs, publication_root).get('workflows', {})
    return {
        'schema_version': '1.0',
        'family_id': 'ds_publication',
        'publish_root': normalize_repo_or_absolute_path(publication_root, project_root),
        'published_run_count': int(len(published_runs)),
        'collection_count': int(len(collection_rows)),
        'workflow_count': int(len(workflows)),
        'threshold_run_count': int(len(threshold_rows)),
        'latest_run': dict(published_runs[-1]) if published_runs else {},
        'workflow_rows': [
            {
                'workflow': workflow,
                'published_run_count': int((row if isinstance(row, dict) else {}).get('count', 0) or 0),
                'latest_run': dict((row if isinstance(row, dict) else {}).get('latest_run', {}) or {}),
            }
            for workflow, row in sorted(dict(workflows).items())
        ],
        'collection_rows': collection_rows,
        'source_mode_rows': source_mode_rows,
    }


def _aggregate_report_payload(
    project_root: Path,
    published_runs: List[Dict[str, Any]],
    threshold_rows: List[Dict[str, Any]],
    publication_root: Path,
) -> Dict[str, Any]:
    collection_rows = _collection_overview_rows(published_runs)
    workflows = _by_workflow_publication_payload(project_root, published_runs, publication_root).get('workflows', {})
    return {
        'schema_version': '1.0',
        'family_id': 'ds_publication',
        'publish_root': normalize_repo_or_absolute_path(publication_root, project_root),
        'published_run_count': int(len(published_runs)),
        'collection_count': int(len(collection_rows)),
        'workflow_count': int(len(workflows)),
        'threshold_run_count': int(len(threshold_rows)),
        'latest_run': dict(published_runs[-1]) if published_runs else {},
        'collection_rows': collection_rows,
        'threshold_rows': list(threshold_rows[:10]),
        'workflow_rows': [
            {
                'workflow': workflow,
                'published_run_count': int((row if isinstance(row, dict) else {}).get('count', 0) or 0),
                'latest_run': dict((row if isinstance(row, dict) else {}).get('latest_run', {}) or {}),
                'note': _workflow_contribution_note(workflow),
            }
            for workflow, row in sorted(dict(workflows).items())
        ],
    }


def _latest_publication_markdown(project_root: Path, target_path: Path, payload: Mapping[str, Any]) -> str:
    latest_run = dict(payload.get('latest_run', {}) or {}) if isinstance(payload.get('latest_run', {}), dict) else {}
    collection_route_path = _aggregate_collection_route_path(latest_run)
    lines = ['# Latest Collections', '']
    lines.append('Use this surface to open the current collection packets first, without having to reverse-engineer the report tree.')
    lines.append('')
    lines.append('- Publish root: `{0}`'.format(str(payload.get('publish_root', ''))))
    lines.append('- Published runs: {0}'.format(int(payload.get('published_run_count', 0) or 0)))
    if not latest_run:
        lines.append('- Latest run: none published yet')
        return '\n'.join(lines).rstrip() + '\n'

    lines.append('- Latest collection: {0}'.format(_markdown_link(target_path, project_root, collection_route_path, str(latest_run.get('collection_alias', '')) or 'collection')))
    lines.append('')
    lines.append('## Current front-door packet')
    lines.append('')
    lines.append('- Collection alias: `{0}`'.format(str(latest_run.get('collection_alias', ''))))
    lines.append('- Workflow: {0}'.format(str(latest_run.get('workflow', ''))))
    lines.append('- Run ID: `{0}`'.format(str(latest_run.get('run_id', ''))))
    lines.append('- Timestamp (UTC): {0}'.format(str(latest_run.get('timestamp_utc', ''))))
    lines.append('- Summary: {0}'.format(str(latest_run.get('summary', ''))))
    lines.append('- Source run root: `{0}`'.format(str(latest_run.get('source_run_root', ''))))
    lines.append('- Latest stage report: {0}'.format(_markdown_link(target_path, project_root, _published_processing_report_path(latest_run), Path(_published_processing_report_path(latest_run)).name or 'stage report')))
    lines.append('')
    lines.append('## Collection packets to open first')
    lines.append('')
    lines.append('| Collection alias | Source / mode | Current packet date | Latest relevant stage(s) | Why open it | Collection packet |')
    lines.append('|---|---|---|---|---|---|')
    collection_rows = list(payload.get('collection_rows', []) or []) if isinstance(payload.get('collection_rows', []), list) else []
    if not collection_rows:
        collection_rows = _collection_overview_rows([latest_run])
    for row in collection_rows[:12]:
        latest_summary = dict(row.get('latest_run', {}) or {}) if isinstance(row.get('latest_run', {}), dict) else {}
        lines.append('| `{0}` | {1} | {2} | {3} | {4} | {5} |'.format(
            str(row.get('collection_alias', '')),
            _source_mode_label(str(row.get('source', '')), str(row.get('mode', ''))),
            str(row.get('latest_timestamp_utc', '')),
            str(row.get('latest_stage_labels', '')),
            str(row.get('reason_to_open', '')),
            _markdown_link(target_path, project_root, _aggregate_collection_route_path(latest_summary), 'collection packet'),
        ))
    return '\n'.join(lines).rstrip() + '\n'


def _by_workflow_publication_markdown(project_root: Path, target_path: Path, payload: Mapping[str, Any]) -> str:
    workflows = dict(payload.get('workflows', {}) or {}) if isinstance(payload.get('workflows', {}), dict) else {}
    lines = ['# Workflow Rollup', '']
    lines.append('Use this surface to understand what each workflow family currently contributes and where its latest human-facing packet lives.')
    lines.append('')
    lines.append('- Publish root: `{0}`'.format(str(payload.get('publish_root', ''))))
    lines.append('- Published runs: {0}'.format(int(payload.get('published_run_count', 0) or 0)))
    lines.append('')
    if not workflows:
        lines.append('No published collections are available yet.')
        return '\n'.join(lines).rstrip() + '\n'
    lines.append('| Workflow | Published runs | Latest collection alias | Latest collection packet | Latest dated stage doc | Current contribution |')
    lines.append('|---|---:|---|---|---|---|')
    for workflow in sorted(workflows.keys()):
        row = workflows[workflow]
        latest_run = dict(row.get('latest_run', {}) or {}) if isinstance(row.get('latest_run', {}), dict) else {}
        collection_link = _markdown_link(target_path, project_root, _aggregate_collection_route_path(latest_run), 'collection packet')
        processing_link = _markdown_link(target_path, project_root, _published_processing_report_path(latest_run), Path(_published_processing_report_path(latest_run)).name or 'stage doc')
        lines.append('| {0} | {1} | `{2}` | {3} | {4} | {5} |'.format(
            workflow,
            int(row.get('count', 0) or 0),
            str(latest_run.get('collection_alias', '')),
            collection_link,
            processing_link,
            _workflow_contribution_note(workflow),
        ))
    return '\n'.join(lines).rstrip() + '\n'


def _thresholds_publication_markdown(project_root: Path, target_path: Path, payload: Mapping[str, Any]) -> str:
    rows = list(payload.get('threshold_rows', []) or []) if isinstance(payload.get('threshold_rows', []), list) else []
    lines = ['# Threshold Summary', '']
    lines.append('This surface covers threshold-bearing packets and routes readers to the dated packet leaves that actually carry the threshold interpretation.')
    lines.append('')
    lines.append('- Publish root: `{0}`'.format(str(payload.get('publish_root', ''))))
    lines.append('- Threshold-bearing runs: {0}'.format(int(payload.get('threshold_run_count', 0) or 0)))
    lines.append('')
    if not rows:
        lines.append('No published threshold-bearing collections are available yet.')
        return '\n'.join(lines).rstrip() + '\n'
    lines.append('| Collection alias | Evaluation date (UTC) | Evaluation run ID | Threshold | Anomaly direction | Target guardrail | Realized flagged share | Eval packet | Paired score packet |')
    lines.append('|---|---|---|---:|---|---:|---:|---|---|')
    for row in rows:
        report_link = _markdown_link(target_path, project_root, str(row.get('published_report_md', '')), 'eval packet') if str(row.get('published_report_md', '')) else ''
        paired_score_link = _markdown_link(target_path, project_root, str(row.get('paired_score_report_md', '')), 'score packet') if str(row.get('paired_score_report_md', '')) else ''
        lines.append('| `{0}` | {1} | `{2}` | {3} | {4} | {5} | {6} | {7} | {8} |'.format(
            str(row.get('collection_alias', '')),
            str(row.get('evaluation_date_utc', '') or row.get('timestamp_utc', '')),
            str(row.get('run_id', '')),
            _markdown_number(row.get('threshold')),
            str(row.get('anomaly_direction', '')),
            _markdown_number(row.get('target_fpr')),
            _markdown_number(row.get('flagged_share')),
            report_link,
            paired_score_link,
        ))
    return '\n'.join(lines).rstrip() + '\n'


def _ds_publication_index_markdown(
    project_root: Path,
    target_path: Path,
    aggregate_report_md_path: Path,
    public_run_ledger_md_path: Path,
    latest_payload: Mapping[str, Any],
    by_workflow_payload: Mapping[str, Any],
    thresholds_payload: Mapping[str, Any],
    published_runs: List[Dict[str, Any]],
) -> str:
    latest_run = dict(latest_payload.get('latest_run', {}) or {}) if isinstance(latest_payload.get('latest_run', {}), dict) else {}
    workflows = dict(by_workflow_payload.get('workflows', {}) or {}) if isinstance(by_workflow_payload.get('workflows', {}), dict) else {}
    lines = ['# Report Collections', '']
    lines.append('Tracked reports are rebuilt as human-facing collection packets derived from the canonical untracked DS run spine.')
    lines.append('Machine-readable authority remains outside `docs/reports/` and is referenced from these collection surfaces rather than duplicated here.')
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    lines.append('- Published runs: {0}'.format(int(len(published_runs))))
    lines.append('- Aggregate report: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(aggregate_report_md_path, project_root), 'AGGREGATE_REPORT.md')))
    lines.append('- Public run ledger: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(public_run_ledger_md_path, project_root), 'PUBLIC_RUN_LEDGER.md')))
    lines.append('- Latest collections: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/aggregates/LATEST_COLLECTIONS.md', 'LATEST_COLLECTIONS.md')))
    lines.append('- Workflow rollup: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/aggregates/WORKFLOW_ROLLUP.md', 'WORKFLOW_ROLLUP.md')))
    lines.append('- Threshold summary: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/aggregates/THRESHOLD_SUMMARY.md', 'THRESHOLD_SUMMARY.md')))
    lines.append('- Generated-report reference: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/reference/GENERATED_REPORT_SURFACES.md', 'GENERATED_REPORT_SURFACES.md')))
    lines.append('- Validation index: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/validations/INDEX.md', 'validations/INDEX.md')))
    lines.append('')
    lines.append('## Latest collection')
    lines.append('')
    if latest_run:
        collection_route_path = _aggregate_collection_route_path(latest_run)
        lines.append('- Collection alias: `{0}`'.format(str(latest_run.get('collection_alias', ''))))
        lines.append('- Run ID: `{0}`'.format(str(latest_run.get('run_id', ''))))
        lines.append('- Workflow: {0}'.format(str(latest_run.get('workflow', ''))))
        lines.append('- Timestamp (UTC): {0}'.format(str(latest_run.get('timestamp_utc', ''))))
        lines.append('- Collection packet: {0}'.format(_markdown_link(target_path, project_root, collection_route_path, Path(collection_route_path).name or 'collection packet')))
        lines.append('- Latest stage report: {0}'.format(_markdown_link(target_path, project_root, _published_processing_report_path(latest_run), Path(_published_processing_report_path(latest_run)).name or 'stage doc')))
    else:
        lines.append('No published collections are available yet.')
    lines.append('')
    lines.append('## Workflow latest')
    lines.append('')
    if workflows:
        lines.append('| Workflow | Published runs | Collection alias | Latest run | Collection packet | Latest stage doc |')
        lines.append('|---|---:|---|---|---|---|')
        for workflow in sorted(workflows.keys()):
            row = workflows[workflow]
            latest_row = dict(row.get('latest_run', {}) or {}) if isinstance(row.get('latest_run', {}), dict) else {}
            lines.append('| {0} | {1} | `{2}` | `{3}` | {4} | {5} |'.format(
                workflow,
                int(row.get('count', 0) or 0),
                str(latest_row.get('collection_alias', '')),
                str(latest_row.get('run_id', '')),
                _markdown_link(target_path, project_root, _aggregate_collection_route_path(latest_row), 'collection packet'),
                _markdown_link(target_path, project_root, _published_processing_report_path(latest_row), Path(_published_processing_report_path(latest_row)).name or 'stage doc'),
            ))
    else:
        lines.append('No workflow rollups are available yet.')
    lines.append('')
    lines.append('## Recent collections')
    lines.append('')
    if published_runs:
        lines.append('| Timestamp (UTC) | Workflow | Collection alias | Run ID | Collection packet | Stage doc |')
        lines.append('|---|---|---|---|---|---|')
        for summary in list(reversed(published_runs[-10:])):
            lines.append('| {0} | {1} | `{2}` | `{3}` | {4} | {5} |'.format(
                str(summary.get('timestamp_utc', '')),
                str(summary.get('workflow', '')),
                str(summary.get('collection_alias', '')),
                str(summary.get('run_id', '')),
                _markdown_link(target_path, project_root, _aggregate_collection_route_path(summary), 'collection packet'),
                _markdown_link(target_path, project_root, _published_processing_report_path(summary), Path(_published_processing_report_path(summary)).name or 'stage doc'),
            ))
    else:
        lines.append('No published collections are available yet.')
    return '\n'.join(lines).rstrip() + '\n'


def _public_run_ledger_markdown(
    project_root: Path,
    target_path: Path,
    payload: Mapping[str, Any],
    aggregate_report_md_path: Path,
    latest_md_path: Path,
    by_workflow_md_path: Path,
    thresholds_md_path: Path,
) -> str:
    latest_run = dict(payload.get('latest_run', {}) or {}) if isinstance(payload.get('latest_run', {}), dict) else {}
    workflow_rows = list(payload.get('workflow_rows', []) or []) if isinstance(payload.get('workflow_rows', []), list) else []
    collection_rows = list(payload.get('collection_rows', []) or []) if isinstance(payload.get('collection_rows', []), list) else []
    source_mode_rows = list(payload.get('source_mode_rows', []) or []) if isinstance(payload.get('source_mode_rows', []), list) else []
    lines = ['# Public Run Ledger', '']
    lines.append('This ledger defines the current public reporting population and provides a runtime-safe census of the tracked report family.')
    lines.append('')
    lines.append('## Purpose')
    lines.append('')
    lines.append('- Count what currently exists in the tracked report family.')
    lines.append('- Keep the reader-facing population separate from the machine-authoritative run ledger.')
    lines.append('- Route readers to synthesis and packet-entry surfaces without pretending this ledger is the authority plane.')
    lines.append('')
    lines.append('## How to read this ledger')
    lines.append('')
    lines.append('- Use `AGGREGATE_REPORT.md` for the flagship synthesis narrative.')
    lines.append('- Use `LATEST_COLLECTIONS.md` when you need the fastest packet-entry route.')
    lines.append('- Use `WORKFLOW_ROLLUP.md` and `THRESHOLD_SUMMARY.md` when you need family-specific rollups.')
    lines.append('')
    lines.append('## Current runtime-safe headline')
    lines.append('')
    lines.append('- Publish root: `{0}`'.format(str(payload.get('publish_root', ''))))
    lines.append('- Published runs: {0}'.format(int(payload.get('published_run_count', 0) or 0)))
    lines.append('- Collection aliases represented: {0}'.format(int(payload.get('collection_count', 0) or 0)))
    lines.append('- Workflow families represented: {0}'.format(int(payload.get('workflow_count', 0) or 0)))
    lines.append('- Threshold-bearing packets: {0}'.format(int(payload.get('threshold_run_count', 0) or 0)))
    if latest_run:
        lines.append('- Latest packet: {0}'.format(_markdown_link(target_path, project_root, _aggregate_collection_route_path(latest_run), str(latest_run.get('collection_alias', '')) or 'collection packet')))
    lines.append('')
    lines.append('## Current lane census')
    lines.append('')
    if workflow_rows:
        lines.append('| Workflow | Published packets | Latest collection | Latest packet |')
        lines.append('|---|---:|---|---|')
        for row in workflow_rows:
            latest_row = dict(row.get('latest_run', {}) or {}) if isinstance(row.get('latest_run', {}), dict) else {}
            lines.append('| {0} | {1} | `{2}` | {3} |'.format(
                str(row.get('workflow', '')),
                int(row.get('published_run_count', 0) or 0),
                str(latest_row.get('collection_alias', '')),
                _markdown_link(target_path, project_root, _published_processing_report_path(latest_row), Path(_published_processing_report_path(latest_row)).name or 'stage doc'),
            ))
    else:
        lines.append('No workflow families are published yet.')
    lines.append('')
    lines.append('## Publication-family census')
    lines.append('')
    if collection_rows:
        lines.append('| Collection alias | Source / mode | Published packets | Latest packet date | Latest stages | Collection packet |')
        lines.append('|---|---|---:|---|---|---|')
        for row in collection_rows[:15]:
            latest_row = dict(row.get('latest_run', {}) or {}) if isinstance(row.get('latest_run', {}), dict) else {}
            lines.append('| `{0}` | {1} | {2} | {3} | {4} | {5} |'.format(
                str(row.get('collection_alias', '')),
                _source_mode_label(str(row.get('source', '')), str(row.get('mode', ''))),
                int(row.get('published_run_count', 0) or 0),
                str(row.get('latest_timestamp_utc', '')),
                str(row.get('latest_stage_labels', '')),
                _markdown_link(target_path, project_root, _aggregate_collection_route_path(latest_row), 'collection packet'),
            ))
    else:
        lines.append('No collection packets are published yet.')
    if source_mode_rows:
        lines.append('')
        lines.append('## Publication-source census')
        lines.append('')
        lines.append('| Source | Mode | Published packets |')
        lines.append('|---|---|---:|')
        for row in source_mode_rows:
            lines.append('| {0} | {1} | {2} |'.format(str(row.get('source', '')), str(row.get('mode', '')), int(row.get('count', 0) or 0)))
    lines.append('')
    lines.append('## Interpretive notes')
    lines.append('')
    lines.append('- This ledger is deliberately derived and runtime-safe; it summarizes the tracked publication family without replacing the canonical machine-readable run records.')
    lines.append('- Absence here means the packet did not enter the tracked publication family; it does not imply the underlying machine artifacts do not exist.')
    lines.append('')
    lines.append('## Provenance')
    lines.append('')
    lines.append('- Machine-readable authority remains outside `docs/reports/`.')
    lines.append('- The tracked report family is rebuilt from the canonical untracked DS run spine and packetized collection surfaces.')
    lines.append('')
    lines.append('## Related surfaces')
    lines.append('')
    lines.append('- Aggregate report: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(aggregate_report_md_path, project_root), 'AGGREGATE_REPORT.md')))
    lines.append('- Latest collections: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(latest_md_path, project_root), 'LATEST_COLLECTIONS.md')))
    lines.append('- Workflow rollup: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(by_workflow_md_path, project_root), 'WORKFLOW_ROLLUP.md')))
    lines.append('- Threshold summary: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(thresholds_md_path, project_root), 'THRESHOLD_SUMMARY.md')))
    return '\n'.join(lines).rstrip() + '\n'


def _aggregate_report_markdown(
    project_root: Path,
    target_path: Path,
    payload: Mapping[str, Any],
    public_run_ledger_md_path: Path,
    latest_md_path: Path,
    by_workflow_md_path: Path,
    thresholds_md_path: Path,
) -> str:
    latest_run = dict(payload.get('latest_run', {}) or {}) if isinstance(payload.get('latest_run', {}), dict) else {}
    collection_rows = list(payload.get('collection_rows', []) or []) if isinstance(payload.get('collection_rows', []), list) else []
    workflow_rows = list(payload.get('workflow_rows', []) or []) if isinstance(payload.get('workflow_rows', []), list) else []
    threshold_rows = list(payload.get('threshold_rows', []) or []) if isinstance(payload.get('threshold_rows', []), list) else []
    lines = ['# Aggregate Report', '']
    lines.append('This synthesis page summarizes the strongest current reader-facing conclusions across the tracked report family.')
    lines.append('')
    lines.append('## Executive summary')
    lines.append('')
    lines.append('- Published packets: {0}'.format(int(payload.get('published_run_count', 0) or 0)))
    lines.append('- Collection aliases represented: {0}'.format(int(payload.get('collection_count', 0) or 0)))
    lines.append('- Workflow families represented: {0}'.format(int(payload.get('workflow_count', 0) or 0)))
    lines.append('- Threshold-bearing packets: {0}'.format(int(payload.get('threshold_run_count', 0) or 0)))
    if latest_run:
        lines.append('- Current front-door packet: {0}'.format(_markdown_link(target_path, project_root, _aggregate_collection_route_path(latest_run), str(latest_run.get('collection_alias', '')) or 'collection packet')))
    lines.append('')
    lines.append('## Why this aggregate exists')
    lines.append('')
    lines.append('The tracked report family now has multiple reader roles: packet entry, workflow rollup, threshold interpretation, population census, and synthesis. This page provides the flagship narrative view over that family.')
    lines.append('')
    lines.append('## Runtime-safe current picture')
    lines.append('')
    if latest_run:
        lines.append('- Latest published workflow: {0}'.format(str(latest_run.get('workflow', ''))))
        lines.append('- Latest packet timestamp (UTC): {0}'.format(str(latest_run.get('timestamp_utc', ''))))
        lines.append('- Latest packet summary: {0}'.format(str(latest_run.get('summary', ''))))
    else:
        lines.append('- No published packets are available yet.')
    lines.append('')
    lines.append('## Aggregate cohort at a glance')
    lines.append('')
    if collection_rows:
        lines.append('| Collection alias | Current packet date | Latest stages | Why it matters now | Collection packet |')
        lines.append('|---|---|---|---|---|')
        for row in collection_rows[:8]:
            latest_row = dict(row.get('latest_run', {}) or {}) if isinstance(row.get('latest_run', {}), dict) else {}
            lines.append('| `{0}` | {1} | {2} | {3} | {4} |'.format(
                str(row.get('collection_alias', '')),
                str(row.get('latest_timestamp_utc', '')),
                str(row.get('latest_stage_labels', '')),
                str(row.get('reason_to_open', '')),
                _markdown_link(target_path, project_root, _aggregate_collection_route_path(latest_row), 'collection packet'),
            ))
    else:
        lines.append('No collection packets are published yet.')
    lines.append('')
    lines.append('## Strongest findings')
    lines.append('')
    if collection_rows:
        lines.append('- The tracked report family is now organized around {0} collection aliases instead of a single cache-shaped run list.'.format(int(payload.get('collection_count', 0) or 0)))
    if workflow_rows:
        lines.append('- Workflow coverage is currently spread across {0}.'.format(', '.join('`{0}`'.format(str(row.get('workflow', ''))) for row in workflow_rows)))
    if threshold_rows:
        lines.append('- Threshold-bearing packets remain visible as dated packet leaves, with the latest threshold summary routed through `THRESHOLD_SUMMARY.md`.')
    else:
        lines.append('- No threshold-bearing packets are currently present in the tracked family.')
    lines.append('')
    lines.append('## Threshold, workflow, and packet synthesis')
    lines.append('')
    if workflow_rows:
        lines.append('| Workflow family | Published packets | Latest collection | Current contribution |')
        lines.append('|---|---:|---|---|')
        for row in workflow_rows:
            latest_row = dict(row.get('latest_run', {}) or {}) if isinstance(row.get('latest_run', {}), dict) else {}
            lines.append('| {0} | {1} | `{2}` | {3} |'.format(
                str(row.get('workflow', '')),
                int(row.get('published_run_count', 0) or 0),
                str(latest_row.get('collection_alias', '')),
                str(row.get('note', '')),
            ))
    if threshold_rows:
        lines.append('')
        lines.append('| Threshold-bearing packet | Threshold | Target guardrail | Eval packet |')
        lines.append('|---|---:|---:|---|')
        for row in threshold_rows[:6]:
            lines.append('| `{0}` / `{1}` | {2} | {3} | {4} |'.format(
                str(row.get('collection_alias', '')),
                str(row.get('run_id', '')),
                _markdown_number(row.get('threshold')),
                _markdown_number(row.get('target_fpr')),
                _markdown_link(target_path, project_root, str(row.get('published_report_md', '')), 'eval packet') if str(row.get('published_report_md', '')) else '',
            ))
    lines.append('')
    lines.append('## Limits and caution notes')
    lines.append('')
    lines.append('- This page is derived and reader-facing; it does not replace the machine-readable authority surfaces.')
    lines.append('- Row-completeness and deeper truthfulness audits remain a downstream concern when packet content needs further repair.')
    lines.append('- Missing links fail closed rather than inventing synthetic packet routes.')
    lines.append('')
    lines.append('## Related authority and lineage')
    lines.append('')
    lines.append('- Publish root: `{0}`'.format(str(payload.get('publish_root', ''))))
    lines.append('- Public run ledger: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(public_run_ledger_md_path, project_root), 'PUBLIC_RUN_LEDGER.md')))
    lines.append('- Generated report surfaces: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/reference/GENERATED_REPORT_SURFACES.md', 'GENERATED_REPORT_SURFACES.md')))
    lines.append('')
    lines.append('## Reader next steps')
    lines.append('')
    lines.append('- Open {0} for the fastest packet-entry lane.'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(latest_md_path, project_root), 'LATEST_COLLECTIONS.md')))
    lines.append('- Open {0} for workflow-family routing.'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(by_workflow_md_path, project_root), 'WORKFLOW_ROLLUP.md')))
    lines.append('- Open {0} for threshold-bearing packet follow-through.'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(thresholds_md_path, project_root), 'THRESHOLD_SUMMARY.md')))
    return '\n'.join(lines).rstrip() + '\n'


def _published_collection_report_path(summary: Mapping[str, Any]) -> str:
    paths = dict(summary.get('published_report_paths', {}) or {}) if isinstance(summary.get('published_report_paths', {}), dict) else {}
    return str(paths.get('collection_history_markdown', '') or paths.get('collection_markdown', '') or paths.get('markdown', '') or '')


def _published_collection_history_path(summary: Mapping[str, Any]) -> str:
    paths = dict(summary.get('published_report_paths', {}) or {}) if isinstance(summary.get('published_report_paths', {}), dict) else {}
    return str(paths.get('collection_history_markdown', '') or paths.get('collection_markdown', '') or paths.get('markdown', '') or '')


def _aggregate_collection_route_path(summary: Mapping[str, Any]) -> str:
    return str(_published_collection_history_path(summary) or '')


def _published_collection_references_path(summary: Mapping[str, Any]) -> str:
    return ''


def _published_processing_report_path(summary: Mapping[str, Any]) -> str:
    paths = dict(summary.get('published_report_paths', {}) or {}) if isinstance(summary.get('published_report_paths', {}), dict) else {}
    return str(paths.get('processing_markdown', '') or '')


def _human_processing_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload or {})
    report_paths = dict(normalized.get('report_paths', {}) or {}) if isinstance(normalized.get('report_paths', {}), dict) else {}
    normalized['report_paths'] = {
        'collection_report_md': str(report_paths.get('collection_markdown', '') or report_paths.get('markdown', '') or ''),
        'processing_report_md': str(report_paths.get('processing_markdown', '') or ''),
    }
    return normalized


def _collection_report_markdown(
    collection_alias: str,
    summaries: List[Dict[str, Any]],
    project_root: Path,
    target_path: Path,
) -> str:
    ordered = sorted(
        [dict(summary) for summary in summaries if isinstance(summary, dict)],
        key=lambda summary: (_publication_sort_key(str(summary.get('timestamp_utc', ''))), str(summary.get('run_id', ''))),
    )
    latest = dict(ordered[-1]) if ordered else {}
    latest_by_workflow: Dict[str, Dict[str, Any]] = {}
    for summary in ordered:
        latest_by_workflow[str(summary.get('workflow', ''))] = dict(summary)

    lines = ['# Collection Packet: {0}'.format(str(collection_alias or 'collection')), '']
    lines.append('This collection packet groups the tracked stage documents published for the selected collection alias.')
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    lines.append('- Collection alias: `{0}`'.format(str(collection_alias or '')))
    lines.append('- Published stage documents: {0}'.format(int(len(ordered))))
    if latest:
        lines.append('- Latest calculation run: `{0}` ({1}, {2})'.format(
            str(latest.get('run_id', '')),
            str(latest.get('workflow', '')),
            str(latest.get('timestamp_utc', '')),
        ))
        latest_snapshot_path = _published_collection_history_path(latest)
        lines.append('- Current collection packet: {0}'.format(
            _markdown_link(target_path, project_root, latest_snapshot_path, Path(latest_snapshot_path).name or 'collection packet')
        ))
        lines.append('- Latest stage document: {0}'.format(
            _markdown_link(target_path, project_root, _published_processing_report_path(latest), Path(_published_processing_report_path(latest)).name or 'stage doc')
        ))
    else:
        lines.append('- Latest calculation run: none published yet')
    lines.append('')
    lines.append('## Collection packet history')
    lines.append('')
    if ordered:
        lines.append('| Published (UTC) | Workflow | Run ID | Collection packet | Stage doc |')
        lines.append('| --- | --- | --- | --- | --- |')
        for summary in reversed(ordered[-12:]):
            snapshot_path = _published_collection_history_path(summary)
            lines.append('| {0} | {1} | `{2}` | {3} | {4} |'.format(
                str(summary.get('timestamp_utc', '')),
                str(summary.get('workflow', '')),
                str(summary.get('run_id', '')),
                _markdown_link(target_path, project_root, snapshot_path, Path(snapshot_path).name or 'collection packet'),
                _markdown_link(target_path, project_root, _published_processing_report_path(summary), Path(_published_processing_report_path(summary)).name or 'stage doc'),
            ))
    else:
        lines.append('No collection packets are available yet.')
    lines.append('')
    lines.append('## Latest stage documents')
    lines.append('')
    if latest_by_workflow:
        lines.append('| Workflow | Latest run | Published (UTC) | Document |')
        lines.append('| --- | --- | --- | --- |')
        for workflow in sorted(latest_by_workflow.keys()):
            summary = latest_by_workflow[workflow]
            report_path = _published_processing_report_path(summary)
            lines.append('| {0} | `{1}` | {2} | {3} |'.format(
                workflow,
                str(summary.get('run_id', '')),
                str(summary.get('timestamp_utc', '')),
                _markdown_link(target_path, project_root, report_path, Path(report_path).name or 'stage doc'),
            ))
    else:
        lines.append('No stage documents are published for this collection yet.')
    lines.append('')
    lines.append('## Recent calculation runs')
    lines.append('')
    if ordered:
        lines.append('| Published (UTC) | Workflow | Run ID | Stage doc |')
        lines.append('| --- | --- | --- | --- |')
        for summary in reversed(ordered[-12:]):
            report_path = _published_processing_report_path(summary)
            lines.append('| {0} | {1} | `{2}` | {3} |'.format(
                str(summary.get('timestamp_utc', '')),
                str(summary.get('workflow', '')),
                str(summary.get('run_id', '')),
                _markdown_link(target_path, project_root, report_path, Path(report_path).name or 'stage doc'),
            ))
    else:
        lines.append('No recent calculation runs are available yet.')
    lines.append('')
    lines.append('## Related authority and lineage')
    lines.append('')
    if latest:
        lines.append('- Canonical source run root: `{0}`'.format(str(latest.get('source_run_root', ''))))
        lines.append('- Latest canonical report JSON: `{0}`'.format(str(((latest.get('source_report_paths', {}) if isinstance(latest.get('source_report_paths', {}), dict) else {}).get('json', '')) or '')))
        lines.append('- Generated report surfaces: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/reference/GENERATED_REPORT_SURFACES.md', 'GENERATED_REPORT_SURFACES.md')))
    return '\n'.join(lines).rstrip() + '\n'


def _collection_references_markdown(candidate: Mapping[str, Any], project_root: Path, target_path: Path) -> str:
    report_paths = dict(candidate.get('published_report_paths', {}) or {})
    source_report_paths = dict(candidate.get('normalized_source_report_paths', {}) or {})
    lines = ['# Collection References: {0}'.format(str(candidate.get('run_id', ''))), '']
    lines.append('All Markdown inside `docs/reports/` is human-facing. Machine-readable authority remains outside this tree and is referenced here for operator follow-through.')
    lines.append('')
    lines.append('## Published surfaces')
    lines.append('')
    lines.append('| Surface | Path |')
    lines.append('|---|---|')
    lines.append('| Collection packet | {0} |'.format(_markdown_link(target_path, project_root, str(report_paths.get('collection_history_markdown', '') or report_paths.get('collection_markdown', '') or report_paths.get('markdown', '') or ''), 'collection packet')))
    lines.append('| Processing packet | {0} |'.format(_markdown_link(target_path, project_root, str(report_paths.get('processing_markdown', '') or ''), 'stage doc')))
    lines.append('| Processing references | {0} |'.format(_markdown_link(target_path, project_root, str(report_paths.get('processing_references_markdown', '') or ''), 'REFERENCES.md')))
    lines.append('')
    lines.append('## Authority pointers')
    lines.append('')
    lines.append('| Authority | Path |')
    lines.append('|---|---|')
    lines.append('| Canonical run root | `{0}` |'.format(str(candidate.get('source_run_root', ''))))
    lines.append('| Canonical report JSON | `{0}` |'.format(str(source_report_paths.get('json', '') or '')))
    lines.append('| Canonical manifest JSON | `{0}` |'.format(str(source_report_paths.get('manifest', '') or '')))
    lines.append('| Canonical report Markdown | `{0}` |'.format(str(source_report_paths.get('markdown', '') or '')))
    return '\n'.join(lines).rstrip() + '\n'


def _processing_references_markdown(candidate: Mapping[str, Any], project_root: Path, target_path: Path) -> str:
    manifest_payload = dict(candidate.get('published_manifest_payload', {}) or candidate.get('manifest_payload', {}) or {})
    lines = ['# Processing References: {0}'.format(str(candidate.get('run_id', ''))), '']
    lines.append('This processing packet captures the stage-specific reader view for the published workflow lane.')
    lines.append('')
    lines.append('## Stage routing')
    lines.append('')
    lines.append('- Workflow: `{0}`'.format(str(candidate.get('workflow', ''))))
    lines.append('- Collection root: `{0}`'.format(str(candidate.get('published_run_dir', ''))))
    lines.append('- Source run root: `{0}`'.format(str(candidate.get('source_run_root', ''))))
    lines.append('')
    lines.append('## Source artifacts')
    lines.append('')
    artifacts = dict(manifest_payload.get('artifacts', {}) or {})
    if artifacts:
        lines.append('| Artifact | Path |')
        lines.append('|---|---|')
        for key in sorted(artifacts.keys()):
            value = artifacts[key]
            if value in ('', None, [], {}, ()):
                continue
            lines.append('| {0} | `{1}` |'.format(str(key).replace('_', ' '), str(value)))
    else:
        lines.append('- No artifact references recorded.')
    if list(candidate.get('figure_sources', []) or []):
        lines.append('')
        lines.append('## Published figures')
        lines.append('')
        for figure_path in list(candidate.get('figure_sources', []) or []):
            rel = normalize_repo_or_absolute_path(Path(candidate['processing_dir']) / 'figures' / Path(figure_path).name, project_root)
            lines.append('- {0}'.format(_markdown_link(target_path, project_root, rel, Path(figure_path).name)))
    return '\n'.join(lines).rstrip() + '\n'


def _generated_report_surfaces_markdown(
    project_root: Path,
    target_path: Path,
    aggregate_report_md_path: Path,
    public_run_ledger_md_path: Path,
    latest_md_path: Path,
    by_workflow_md_path: Path,
    thresholds_md_path: Path,
) -> str:
    lines = ['# Generated Report Surfaces', '']
    lines.append('This reference describes the active human-facing report schema for tracked publication under `docs/reports/`.')
    lines.append('')
    lines.append('## Contract')
    lines.append('')
    lines.append('- All Markdown inside `docs/reports/` is human-facing.')
    lines.append('- Machine-readable authority remains outside this tree and is referenced from these reader surfaces rather than duplicated here.')
    lines.append('- When published runs exist, they are rendered under `docs/reports/collections/<collection-alias>/`.')
    lines.append('- Zero-state publication may leave `docs/reports/collections/` present but empty until a fresh canonical publication pass materializes collection packets.')
    lines.append('- Aggregate-facing collection routes use the dated collection packet leaf under `docs/reports/collections/<collection-alias>/collection/YYYYMMDDTHHMMSSffffffZ.collection.md` when that packet family exists.')
    lines.append('- No stable `collection/report.md` landing page is part of the current tracked packet contract.')
    lines.append('')
    lines.append('## Layout')
    lines.append('')
    lines.append('```text')
    lines.append('docs/reports/')
    lines.append('|- aggregates/AGGREGATE_REPORT.md')
    lines.append('|- aggregates/PUBLIC_RUN_LEDGER.md')
    lines.append('|- aggregates/LATEST_COLLECTIONS.md')
    lines.append('|- aggregates/WORKFLOW_ROLLUP.md')
    lines.append('|- aggregates/THRESHOLD_SUMMARY.md')
    lines.append('|- collections/                         # may be empty at zero-state')
    lines.append('|  `- <collection-alias>/              # materialized only when published packets exist')
    lines.append('|     |- collection/YYYYMMDDTHHMMSSffffffZ.collection.md')
    lines.append('|     `- processing/<stage>/YYYYMMDDTHHMMSSffffffZ.<stage>.md')
    lines.append('|- reference/')
    lines.append('|- validations/')
    lines.append('`- INDEX.md')
    lines.append('```')
    lines.append('')
    lines.append('## Aggregate report family')
    lines.append('')
    lines.append('- `docs/reports/aggregates/AGGREGATE_REPORT.md`')
    lines.append('- `docs/reports/aggregates/PUBLIC_RUN_LEDGER.md`')
    lines.append('- `docs/reports/aggregates/LATEST_COLLECTIONS.md`')
    lines.append('- `docs/reports/aggregates/WORKFLOW_ROLLUP.md`')
    lines.append('- `docs/reports/aggregates/THRESHOLD_SUMMARY.md`')
    lines.append('')
    lines.append('## Tracked packet family')
    lines.append('')
    lines.append('When collection packets are materialized:')
    lines.append('')
    lines.append('- `docs/reports/collections/<collection-alias>/collection/YYYYMMDDTHHMMSSffffffZ.collection.md`')
    lines.append('- `docs/reports/collections/<collection-alias>/processing/<stage>/YYYYMMDDTHHMMSSffffffZ.<stage>.md`')
    lines.append('')
    lines.append('## Reader routes')
    lines.append('')
    lines.append('- Aggregate report: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(aggregate_report_md_path, project_root), 'AGGREGATE_REPORT.md')))
    lines.append('- Public run ledger: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(public_run_ledger_md_path, project_root), 'PUBLIC_RUN_LEDGER.md')))
    lines.append('- Latest collections: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(latest_md_path, project_root), 'LATEST_COLLECTIONS.md')))
    lines.append('- Workflow rollup: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(by_workflow_md_path, project_root), 'WORKFLOW_ROLLUP.md')))
    lines.append('- Threshold summary: {0}'.format(_markdown_link(target_path, project_root, normalize_repo_or_absolute_path(thresholds_md_path, project_root), 'THRESHOLD_SUMMARY.md')))
    lines.append('- Validation index: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/validations/INDEX.md', 'validations/INDEX.md')))
    lines.append('')
    lines.append('## Aggregate-consumer route authority')
    lines.append('')
    lines.append('- `LATEST_COLLECTIONS.md` and aggregate-facing collection links should target the dated collection packet leaf directly whenever packet families are materialized.')
    lines.append('- Workflow and threshold routes should target real dated processing packet leaves and fail closed when those packet routes are missing.')
    lines.append('- Zero-state publication should remain honest: keep the aggregate family readable while leaving packet-route sections empty rather than implying packet leaves that do not yet exist.')
    return '\n'.join(lines).rstrip() + '\n'


def _published_workflow_dir_name(workflow: str) -> str:
    token = canonical_ds_workflow_name(str(workflow or '').strip())
    return 'eval' if token == 'evaluate' else token


def _published_workflow_doc_token(workflow: str) -> str:
    token = canonical_ds_workflow_name(str(workflow or '').strip())
    return 'eval' if token == 'evaluate' else token


def _publication_timestamp_token(timestamp_utc: str) -> str:
    token = str(timestamp_utc or '').strip()
    if not token:
        raise ValueError('Missing canonical publication timestamp.')
    normalized = token[:-1] + '+00:00' if token.endswith('Z') else token
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        digits = ''.join(ch for ch in token if ch.isdigit())
        if len(digits) < 14:
            raise ValueError('Invalid canonical publication timestamp: {0}'.format(token))
        return '{0}T{1}{2}Z'.format(digits[:8], digits[8:14], digits[14:20].ljust(6, '0'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime('%Y%m%dT%H%M%S%fZ')


def _publication_sort_key(timestamp_utc: str) -> str:
    return _publication_timestamp_token(timestamp_utc)


def _next_processing_report_path(*, processing_dir: Path, timestamp_utc: str, workflow: str) -> Path:
    timestamp_token = _publication_timestamp_token(timestamp_utc)
    workflow_token = _published_workflow_doc_token(workflow)
    candidate = processing_dir / '{0}.{1}.md'.format(timestamp_token, workflow_token)
    if candidate.exists():
        raise ValueError('Duplicate canonical processing report path: {0}'.format(candidate.as_posix()))
    return candidate


def _next_collection_report_path(*, collection_dir: Path, timestamp_utc: str) -> Path:
    timestamp_token = _publication_timestamp_token(timestamp_utc)
    candidate = collection_dir / '{0}.collection.md'.format(timestamp_token)
    if candidate.exists():
        raise ValueError('Duplicate canonical collection report path: {0}'.format(candidate.as_posix()))
    return candidate


def _resolve_collection_alias(
    manifest_payload: Mapping[str, Any],
    project_root: Path,
    project_anchor: Path,
    fallback_run_id: str,
) -> str:
    for container in (
        manifest_payload,
        manifest_payload.get('context', {}) if isinstance(manifest_payload.get('context', {}), dict) else {},
        manifest_payload.get('lineage', {}) if isinstance(manifest_payload.get('lineage', {}), dict) else {},
    ):
        alias = str(container.get('collection_alias', '') or container.get('dataset_alias', '') or '').strip()
        if alias:
            return sanitize_run_id(alias) or sanitize_run_id(fallback_run_id) or 'collection'

    manifest_refs: List[str] = []
    artifacts = dict(manifest_payload.get('artifacts', {}) or {}) if isinstance(manifest_payload.get('artifacts', {}), dict) else {}
    lineage = dict(manifest_payload.get('lineage', {}) or {}) if isinstance(manifest_payload.get('lineage', {}), dict) else {}
    context = dict(manifest_payload.get('context', {}) or {}) if isinstance(manifest_payload.get('context', {}), dict) else {}
    for ref in (
        artifacts.get('dataset_manifest', ''),
        lineage.get('dataset_manifest', ''),
        context.get('dataset_manifest', ''),
    ):
        text = str(ref or '').strip()
        if text and text not in manifest_refs:
            manifest_refs.append(text)

    if manifest_refs:
        try:
            from calamum_librarian import dataset_display_alias_for_manifest
        except Exception:
            dataset_display_alias_for_manifest = None
        if dataset_display_alias_for_manifest is not None:
            for manifest_ref in manifest_refs:
                alias = str(dataset_display_alias_for_manifest(project_anchor, manifest_ref) or '').strip()
                if alias:
                    return sanitize_run_id(alias) or sanitize_run_id(fallback_run_id) or 'collection'

    return sanitize_run_id(fallback_run_id) or 'collection'


def _write_collection_reports(candidates: List[Dict[str, Any]], project_root: Path) -> None:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in candidates:
        alias = str(candidate.get('collection_alias', '') or '').strip()
        if not alias:
            continue
        grouped.setdefault(alias, []).append(candidate)
    for alias, rows in grouped.items():
        ordered_rows = sorted(
            [dict(row) for row in rows if isinstance(row, dict)],
            key=lambda row: (_publication_sort_key(str(row.get('timestamp_utc', ''))), str(row.get('run_id', ''))),
        )
        collection_dir = Path(ordered_rows[0]['collection_dir'])
        summaries = [_published_run_summary(row, project_root) for row in ordered_rows]
        for index, summary in enumerate(summaries):
            snapshot_path = _resolve_repo_path(project_root, _published_collection_history_path(summary))
            if snapshot_path is None:
                continue
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(
                _collection_report_markdown(alias, summaries[: index + 1], project_root, snapshot_path),
                encoding='utf-8',
            )


def _validations_index_markdown(project_root: Path, target_path: Path) -> str:
    lines = ['# Validation Reports', '']
    lines.append('Validation publications are routed into this lane when a validation family intentionally emits reader-facing tracked material.')
    lines.append('')
    lines.append('Machine-readable validation evidence remains outside `docs/reports/` and should be referenced from future Markdown packets rather than copied into this tree.')
    lines.append('')
    lines.append('- Return to {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/INDEX.md', 'reports/INDEX.md')))
    return '\n'.join(lines).rstrip() + '\n'


def _publication_identity_key(*, workflow: str, run_id: str, timestamp_utc: str) -> str:
    return '{0}|{1}|{2}'.format(canonical_ds_workflow_name(workflow), sanitize_run_id(run_id), str(timestamp_utc or '').strip())


def _markdown_link(target_path: Path, project_root: Path, repo_or_absolute_path: str, label: str) -> str:
    resolved = _resolve_repo_path(project_root, repo_or_absolute_path)
    if resolved is None:
        return label
    rel = Path(os.path.relpath(resolved, start=target_path.parent)).as_posix()
    return '[{0}]({1})'.format(label, rel)


def _markdown_number(value: Any) -> str:
    if value in ('', None):
        return ''
    try:
        return '{0:.6g}'.format(float(value))
    except (TypeError, ValueError):
        return str(value)


def _markdown_int(value: Any) -> str:
    if value in ('', None):
        return ''
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _source_mode_label(source: str, mode: str) -> str:
    source_text = str(source or '').strip()
    mode_text = str(mode or '').strip()
    if source_text and mode_text:
        return '{0} / {1}'.format(source_text, mode_text)
    if source_text:
        return source_text
    if mode_text:
        return mode_text
    return 'runtime-unspecified'


def _threshold_flagged_share(actual_fpr: Any, flagged_records: Any, records_scored: Any) -> Any:
    if actual_fpr not in ('', None):
        return actual_fpr
    try:
        flagged = float(flagged_records)
        scored = float(records_scored)
    except (TypeError, ValueError):
        return None
    if scored <= 0:
        return None
    return flagged / scored