from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ._util import (
    canonical_ds_workflow_name,
    ds_indexes_dir,
    ds_publication_aggregates_dir,
    ds_publication_dir,
    ds_published_run_dir,
    ds_runs_dir,
    find_project_root,
    iter_jsonl,
    normalize_repo_or_absolute_path,
    sanitize_run_id,
)
from .report_pack import _normalize_json_value, _report_markdown


PUBLISHED_REPORT_REQUIRED_KEYS = ('markdown', 'json', 'manifest')
PUBLISHED_IMAGE_SUFFIXES = {'.png', '.svg', '.jpg', '.jpeg', '.gif', '.webp'}


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
            str((row.get('entry', {}) if isinstance(row.get('entry', {}), dict) else {}).get('timestamp_utc', '')),
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
    publication_root = ds_publication_dir(project_anchor)
    aggregates_root = ds_publication_aggregates_dir(project_anchor)
    publication_root.mkdir(parents=True, exist_ok=True)
    aggregates_root.mkdir(parents=True, exist_ok=True)

    records = load_ds_run_manifest_records(project_anchor=project_anchor)
    publishable: List[Dict[str, Any]] = []
    excluded_entries = 0
    for record in records:
        candidate = _build_publication_candidate(record, project_root, project_anchor)
        if candidate is None:
            excluded_entries += 1
            continue
        publishable.append(candidate)

    publishable.sort(key=lambda candidate: (str(candidate.get('timestamp_utc', '')), str(candidate.get('run_id', ''))))

    published_runs: List[Dict[str, Any]] = []
    threshold_rows: List[Dict[str, Any]] = []
    for candidate in publishable:
        _publish_candidate(candidate)
        published_summary = _published_run_summary(candidate, project_root)
        published_runs.append(published_summary)
        threshold_row = _threshold_summary_row(candidate, published_summary)
        if threshold_row is not None:
            threshold_rows.append(threshold_row)

    latest_payload = _latest_publication_payload(project_root, published_runs, publication_root)
    by_workflow_payload = _by_workflow_publication_payload(project_root, published_runs, publication_root)
    thresholds_payload = _thresholds_publication_payload(project_root, threshold_rows, publication_root)

    latest_json_path = aggregates_root / 'latest.json'
    latest_md_path = aggregates_root / 'latest.md'
    by_workflow_json_path = aggregates_root / 'by_workflow.json'
    by_workflow_md_path = aggregates_root / 'by_workflow.md'
    thresholds_json_path = aggregates_root / 'thresholds.json'
    thresholds_md_path = aggregates_root / 'thresholds.md'
    index_md_path = publication_root / 'INDEX.md'

    latest_json_path.write_text(json.dumps(latest_payload, indent=2, sort_keys=True), encoding='utf-8')
    latest_md_path.write_text(_latest_publication_markdown(project_root, latest_md_path, latest_payload), encoding='utf-8')
    by_workflow_json_path.write_text(json.dumps(by_workflow_payload, indent=2, sort_keys=True), encoding='utf-8')
    by_workflow_md_path.write_text(_by_workflow_publication_markdown(project_root, by_workflow_md_path, by_workflow_payload), encoding='utf-8')
    thresholds_json_path.write_text(json.dumps(thresholds_payload, indent=2, sort_keys=True), encoding='utf-8')
    thresholds_md_path.write_text(_thresholds_publication_markdown(project_root, thresholds_md_path, thresholds_payload), encoding='utf-8')
    index_md_path.write_text(
        _ds_publication_index_markdown(
            project_root,
            index_md_path,
            latest_payload,
            by_workflow_payload,
            thresholds_payload,
            published_runs,
        ),
        encoding='utf-8',
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
        'aggregate_paths': {
            'index_md': normalize_repo_or_absolute_path(index_md_path, project_root),
            'latest_json': normalize_repo_or_absolute_path(latest_json_path, project_root),
            'latest_md': normalize_repo_or_absolute_path(latest_md_path, project_root),
            'by_workflow_json': normalize_repo_or_absolute_path(by_workflow_json_path, project_root),
            'by_workflow_md': normalize_repo_or_absolute_path(by_workflow_md_path, project_root),
            'thresholds_json': normalize_repo_or_absolute_path(thresholds_json_path, project_root),
            'thresholds_md': normalize_repo_or_absolute_path(thresholds_md_path, project_root),
        },
    }


def publication_eligibility_reasons(*, project_anchor: Path, manifest_payload: Mapping[str, Any]) -> List[str]:
    project_root = find_project_root(project_anchor)
    reasons: List[str] = []
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

    report_paths = dict(manifest_payload.get('report_paths', {}) or {})
    source_report_paths: Dict[str, Path] = {}
    for key in PUBLISHED_REPORT_REQUIRED_KEYS:
        resolved = _resolve_repo_path(project_root, str(report_paths.get(key, '') or '').strip())
        if resolved is None or not resolved.exists():
            return None
        source_report_paths[key] = resolved

    publication_dir = ds_published_run_dir(project_anchor, timestamp_utc, run_id)
    figure_sources = _collect_figure_sources(manifest_payload, project_root)
    normalized_source_report_paths = {
        key: normalize_repo_or_absolute_path(value, project_root)
        for key, value in source_report_paths.items()
    }
    published_report_paths = _published_report_paths(publication_dir, project_root)
    source_run_root = normalize_repo_or_absolute_path(
        _resolve_repo_path(project_root, str(manifest_payload.get('run_root', '') or '').strip()),
        project_root,
    )
    published_run_dir = normalize_repo_or_absolute_path(publication_dir, project_root)
    return {
        'project_root': project_root,
        'entry': entry,
        'manifest_payload': manifest_payload,
        'workflow': workflow,
        'run_id': run_id,
        'timestamp_utc': timestamp_utc,
        'source_report_paths': source_report_paths,
        'normalized_source_report_paths': normalized_source_report_paths,
        'published_report_paths': published_report_paths,
        'source_run_root': source_run_root,
        'published_run_dir': published_run_dir,
        'publication_dir': publication_dir,
        'figure_sources': figure_sources,
        'publication_string_replacements': _publication_string_replacements(
            project_root,
            normalized_source_report_paths,
            published_report_paths,
            publication_dir,
            figure_sources,
        ),
    }


def _collect_figure_sources(manifest_payload: Mapping[str, Any], project_root: Path) -> List[Path]:
    sources: List[Path] = []
    seen: set = set()

    artifacts = dict(manifest_payload.get('artifacts', {}) or {}) if isinstance(manifest_payload.get('artifacts', {}), dict) else {}
    for value in artifacts.values():
        resolved = _resolve_repo_path(project_root, str(value or '').strip())
        if resolved is None or not resolved.exists() or not resolved.is_file():
            continue
        if resolved.suffix.lower() not in PUBLISHED_IMAGE_SUFFIXES:
            continue
        key = str(resolved.resolve())
        if key in seen:
            continue
        seen.add(key)
        sources.append(resolved)

    run_root = _resolve_repo_path(project_root, str(manifest_payload.get('run_root', '') or '').strip())
    figures_dir = (run_root / 'figures') if run_root is not None else None
    if figures_dir is not None and figures_dir.exists() and figures_dir.is_dir():
        for path in sorted(figures_dir.rglob('*')):
            if not path.is_file() or path.suffix.lower() not in PUBLISHED_IMAGE_SUFFIXES:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            sources.append(path)
    return sources


def _published_report_paths(publication_dir: Path, project_root: Path) -> Dict[str, str]:
    return {
        'markdown': normalize_repo_or_absolute_path(publication_dir / 'report.md', project_root),
        'json': normalize_repo_or_absolute_path(publication_dir / 'report.json', project_root),
        'manifest': normalize_repo_or_absolute_path(publication_dir / 'manifest.json', project_root),
    }


def _publication_string_replacements(
    project_root: Path,
    normalized_source_report_paths: Mapping[str, str],
    published_report_paths: Mapping[str, str],
    publication_dir: Path,
    figure_sources: List[Path],
) -> Dict[str, str]:
    replacements: Dict[str, str] = {}
    for key in PUBLISHED_REPORT_REQUIRED_KEYS:
        source_value = str(normalized_source_report_paths.get(key, '') or '').strip()
        target_value = str(published_report_paths.get(key, '') or '').strip()
        if source_value and target_value:
            replacements[source_value] = target_value
    for source in figure_sources:
        source_value = normalize_repo_or_absolute_path(source, project_root)
        target_value = normalize_repo_or_absolute_path(publication_dir / 'figures' / source.name, project_root)
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
    project_root = Path(candidate['project_root'])
    publication_dir.mkdir(parents=True, exist_ok=True)

    source_report_paths = dict(candidate.get('source_report_paths', {}) or {})
    source_report_payload = _read_json_dict(source_report_paths.get('json'))
    source_manifest_payload = _read_json_dict(source_report_paths.get('manifest'))
    if not source_report_payload:
        source_report_payload = dict(candidate.get('manifest_payload', {}) or {})
    if not source_manifest_payload:
        source_manifest_payload = dict(candidate.get('manifest_payload', {}) or {})

    published_report_payload = _build_published_payload(source_report_payload, candidate, project_root=project_root)
    published_manifest_payload = _build_published_payload(source_manifest_payload, candidate, project_root=project_root)

    report_md_path = publication_dir / 'report.md'
    report_json_path = publication_dir / 'report.json'
    manifest_json_path = publication_dir / 'manifest.json'

    report_json_path.write_text(json.dumps(published_report_payload, indent=2, sort_keys=True), encoding='utf-8')
    manifest_json_path.write_text(json.dumps(published_manifest_payload, indent=2, sort_keys=True), encoding='utf-8')
    report_md_path.write_text(
        _report_markdown(published_report_payload, project_root=project_root, report_md_path=report_md_path),
        encoding='utf-8',
    )

    figure_sources = list(candidate.get('figure_sources', []) or [])
    if figure_sources:
        figures_dir = publication_dir / 'figures'
        figures_dir.mkdir(parents=True, exist_ok=True)
        for source in figure_sources:
            target = figures_dir / source.name
            shutil.copy2(source, target)

    if isinstance(candidate, dict):
        candidate['published_report_payload'] = published_report_payload
        candidate['published_manifest_payload'] = published_manifest_payload


def _published_run_summary(candidate: Mapping[str, Any], project_root: Path) -> Dict[str, Any]:
    report_payload = dict(candidate.get('published_report_payload', {}) or {})
    manifest_payload = dict(candidate.get('published_manifest_payload', {}) or candidate.get('manifest_payload', {}) or {})
    publication_dir = Path(candidate['publication_dir'])
    source_report_paths = dict(candidate.get('source_report_paths', {}) or {})
    normalized_source_report_paths = dict(candidate.get('normalized_source_report_paths', {}) or {})
    published_report_paths = dict(candidate.get('published_report_paths', {}) or _published_report_paths(publication_dir, project_root))
    figure_sources = list(candidate.get('figure_sources', []) or [])
    figure_paths = [
        normalize_repo_or_absolute_path(publication_dir / 'figures' / source.name, project_root)
        for source in figure_sources
    ]
    source_run_root = str(report_payload.get('source_run_root', '') or manifest_payload.get('source_run_root', '') or candidate.get('source_run_root', '') or manifest_payload.get('run_root', ''))
    published_run_dir = str(report_payload.get('published_run_dir', '') or manifest_payload.get('published_run_dir', '') or candidate.get('published_run_dir', '') or normalize_repo_or_absolute_path(publication_dir, project_root))
    return {
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


def _threshold_summary_row(candidate: Mapping[str, Any], published_summary: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
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

    return {
        'workflow': str(published_summary.get('workflow', '')),
        'run_id': str(published_summary.get('run_id', '')),
        'timestamp_utc': str(published_summary.get('timestamp_utc', '')),
        'threshold': threshold_value,
        'target_fpr': target_fpr,
        'actual_fpr': actual_fpr,
        'flagged_records': flagged_records,
        'records_scored': records_scored,
        'published_report_md': str(((published_summary.get('published_report_paths', {}) if isinstance(published_summary.get('published_report_paths', {}), dict) else {}).get('markdown', '')) or ''),
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


def _latest_publication_markdown(project_root: Path, target_path: Path, payload: Mapping[str, Any]) -> str:
    latest_run = dict(payload.get('latest_run', {}) or {}) if isinstance(payload.get('latest_run', {}), dict) else {}
    lines = ['# DS Latest Published Run', '']
    lines.append('- Publish root: `{0}`'.format(str(payload.get('publish_root', ''))))
    lines.append('- Published runs: {0}'.format(int(payload.get('published_run_count', 0) or 0)))
    if not latest_run:
        lines.append('- Latest run: none published yet')
        return '\n'.join(lines).rstrip() + '\n'

    lines.append('- Latest run: {0}'.format(_markdown_link(target_path, project_root, str(((latest_run.get('published_report_paths', {}) if isinstance(latest_run.get('published_report_paths', {}), dict) else {}).get('markdown', '')) or ''), str(latest_run.get('run_id', '')) or 'report')))
    lines.append('')
    lines.append('## Run summary')
    lines.append('')
    lines.append('- Workflow: {0}'.format(str(latest_run.get('workflow', ''))))
    lines.append('- Run ID: `{0}`'.format(str(latest_run.get('run_id', ''))))
    lines.append('- Timestamp (UTC): {0}'.format(str(latest_run.get('timestamp_utc', ''))))
    lines.append('- Summary: {0}'.format(str(latest_run.get('summary', ''))))
    lines.append('- Source run root: `{0}`'.format(str(latest_run.get('source_run_root', ''))))
    return '\n'.join(lines).rstrip() + '\n'


def _by_workflow_publication_markdown(project_root: Path, target_path: Path, payload: Mapping[str, Any]) -> str:
    workflows = dict(payload.get('workflows', {}) or {}) if isinstance(payload.get('workflows', {}), dict) else {}
    lines = ['# DS Published Runs by Workflow', '']
    lines.append('- Publish root: `{0}`'.format(str(payload.get('publish_root', ''))))
    lines.append('- Published runs: {0}'.format(int(payload.get('published_run_count', 0) or 0)))
    lines.append('')
    if not workflows:
        lines.append('No published DS runs are available yet.')
        return '\n'.join(lines).rstrip() + '\n'
    lines.append('| Workflow | Published runs | Latest run | Published report |')
    lines.append('|---|---:|---|---|')
    for workflow in sorted(workflows.keys()):
        row = workflows[workflow]
        latest_run = dict(row.get('latest_run', {}) or {}) if isinstance(row.get('latest_run', {}), dict) else {}
        report_path = str(((latest_run.get('published_report_paths', {}) if isinstance(latest_run.get('published_report_paths', {}), dict) else {}).get('markdown', '')) or '')
        report_link = _markdown_link(target_path, project_root, report_path, 'report') if report_path else ''
        lines.append('| {0} | {1} | `{2}` | {3} |'.format(
            workflow,
            int(row.get('count', 0) or 0),
            str(latest_run.get('run_id', '')),
            report_link,
        ))
    return '\n'.join(lines).rstrip() + '\n'


def _thresholds_publication_markdown(project_root: Path, target_path: Path, payload: Mapping[str, Any]) -> str:
    rows = list(payload.get('threshold_rows', []) or []) if isinstance(payload.get('threshold_rows', []), list) else []
    lines = ['# DS Threshold Summary', '']
    lines.append('- Publish root: `{0}`'.format(str(payload.get('publish_root', ''))))
    lines.append('- Threshold-bearing runs: {0}'.format(int(payload.get('threshold_run_count', 0) or 0)))
    lines.append('')
    if not rows:
        lines.append('No published threshold-bearing DS runs are available yet.')
        return '\n'.join(lines).rstrip() + '\n'
    lines.append('| Workflow | Run ID | Threshold | Target FPR | Actual FPR | Flagged | Records | Report |')
    lines.append('|---|---|---:|---:|---:|---:|---:|---|')
    for row in rows:
        report_link = _markdown_link(target_path, project_root, str(row.get('published_report_md', '')), 'report') if str(row.get('published_report_md', '')) else ''
        lines.append('| {0} | `{1}` | {2} | {3} | {4} | {5} | {6} | {7} |'.format(
            str(row.get('workflow', '')),
            str(row.get('run_id', '')),
            _markdown_number(row.get('threshold')),
            _markdown_number(row.get('target_fpr')),
            _markdown_number(row.get('actual_fpr')),
            _markdown_int(row.get('flagged_records')),
            _markdown_int(row.get('records_scored')),
            report_link,
        ))
    return '\n'.join(lines).rstrip() + '\n'


def _ds_publication_index_markdown(
    project_root: Path,
    target_path: Path,
    latest_payload: Mapping[str, Any],
    by_workflow_payload: Mapping[str, Any],
    thresholds_payload: Mapping[str, Any],
    published_runs: List[Dict[str, Any]],
) -> str:
    latest_run = dict(latest_payload.get('latest_run', {}) or {}) if isinstance(latest_payload.get('latest_run', {}), dict) else {}
    workflows = dict(by_workflow_payload.get('workflows', {}) or {}) if isinstance(by_workflow_payload.get('workflows', {}), dict) else {}
    lines = ['# DS Reports', '']
    lines.append('Tracked DS publication is a curated reader-facing surface derived from the canonical untracked DS run spine.')
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    lines.append('- Published runs: {0}'.format(int(len(published_runs))))
    lines.append('- Latest aggregate: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/ds/aggregates/latest.md', 'latest.md')))
    lines.append('- Workflow rollup: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/ds/aggregates/by_workflow.md', 'by_workflow.md')))
    lines.append('- Threshold summary: {0}'.format(_markdown_link(target_path, project_root, 'docs/reports/ds/aggregates/thresholds.md', 'thresholds.md')))
    lines.append('')
    lines.append('## Latest published run')
    lines.append('')
    if latest_run:
        lines.append('- Run ID: `{0}`'.format(str(latest_run.get('run_id', ''))))
        lines.append('- Workflow: {0}'.format(str(latest_run.get('workflow', ''))))
        lines.append('- Timestamp (UTC): {0}'.format(str(latest_run.get('timestamp_utc', ''))))
        lines.append('- Published report: {0}'.format(_markdown_link(target_path, project_root, str(((latest_run.get('published_report_paths', {}) if isinstance(latest_run.get('published_report_paths', {}), dict) else {}).get('markdown', '')) or ''), 'report.md')))
    else:
        lines.append('No published DS runs are available yet.')
    lines.append('')
    lines.append('## Workflow latest')
    lines.append('')
    if workflows:
        lines.append('| Workflow | Published runs | Latest run | Report |')
        lines.append('|---|---:|---|---|')
        for workflow in sorted(workflows.keys()):
            row = workflows[workflow]
            latest_row = dict(row.get('latest_run', {}) or {}) if isinstance(row.get('latest_run', {}), dict) else {}
            lines.append('| {0} | {1} | `{2}` | {3} |'.format(
                workflow,
                int(row.get('count', 0) or 0),
                str(latest_row.get('run_id', '')),
                _markdown_link(target_path, project_root, str(((latest_row.get('published_report_paths', {}) if isinstance(latest_row.get('published_report_paths', {}), dict) else {}).get('markdown', '')) or ''), 'report.md'),
            ))
    else:
        lines.append('No workflow rollups are available yet.')
    lines.append('')
    lines.append('## Recent published runs')
    lines.append('')
    if published_runs:
        lines.append('| Timestamp (UTC) | Workflow | Run ID | Report |')
        lines.append('|---|---|---|---|')
        for summary in list(reversed(published_runs[-10:])):
            lines.append('| {0} | {1} | `{2}` | {3} |'.format(
                str(summary.get('timestamp_utc', '')),
                str(summary.get('workflow', '')),
                str(summary.get('run_id', '')),
                _markdown_link(target_path, project_root, str(((summary.get('published_report_paths', {}) if isinstance(summary.get('published_report_paths', {}), dict) else {}).get('markdown', '')) or ''), 'report.md'),
            ))
    else:
        lines.append('No published DS runs are available yet.')
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