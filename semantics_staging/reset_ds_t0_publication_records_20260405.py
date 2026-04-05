from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
SRC_ROOT = PROJECT_ROOT / 'src'
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from analysis._util import iter_jsonl  # noqa: E402
from analysis.report_aggregate import refresh_tracked_ds_publication  # noqa: E402


_EPHEMERAL_RUN_ROOT_MARKERS = (
    'pytest',
    '/Temp/',
    '\\Temp\\',
    'AppData',
    'report_tmp',
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _normalize_text(value: Any) -> str:
    return str(value or '').strip()


def _is_ephemeral_run_root(run_root: str) -> bool:
    normalized = _normalize_text(run_root).replace('\\', '/')
    if not normalized:
        return False
    return any(marker.replace('\\', '/') in normalized for marker in _EPHEMERAL_RUN_ROOT_MARKERS)


def _read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _move_path(source: Path, destination: Path) -> Dict[str, Any]:
    if not source.exists():
        return {
            'source': str(source),
            'destination': str(destination),
            'moved': False,
            'reason': 'missing',
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return {
        'source': str(source),
        'destination': str(destination),
        'moved': True,
        'kind': 'directory' if destination.is_dir() else 'file',
    }


def _count_tree_files(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(1 for candidate in root.rglob('*') if candidate.is_file())


def _runs_summary(runs_root: Path) -> Dict[str, Any]:
    workflows: Dict[str, int] = {}
    if runs_root.exists():
        for child in sorted(runs_root.iterdir()):
            if not child.is_dir():
                continue
            workflows[child.name] = sum(1 for candidate in child.iterdir() if candidate.is_dir())
    return {
        'workflow_run_counts': workflows,
        'total_run_dirs': int(sum(workflows.values())),
        'total_files': int(_count_tree_files(runs_root)),
    }


def _ds_ledger_summary(ledger_path: Path) -> Dict[str, Any]:
    if not ledger_path.exists():
        return {
            'ledger_path': str(ledger_path),
            'exists': False,
            'entry_count': 0,
            'workflow_counts': {},
            'ephemeral_root_entries': 0,
        }

    workflow_counts: Dict[str, int] = {}
    ephemeral_root_entries = 0
    entry_count = 0
    for line in iter_jsonl(ledger_path):
        if not isinstance(line.obj, dict):
            continue
        entry_count += 1
        workflow = _normalize_text(line.obj.get('workflow', 'unknown')) or 'unknown'
        workflow_counts[workflow] = int(workflow_counts.get(workflow, 0)) + 1
        if _is_ephemeral_run_root(_normalize_text(line.obj.get('run_root', ''))):
            ephemeral_root_entries += 1
    return {
        'ledger_path': str(ledger_path),
        'exists': True,
        'entry_count': int(entry_count),
        'workflow_counts': workflow_counts,
        'ephemeral_root_entries': int(ephemeral_root_entries),
    }


def _librarian_manifest_audit(indexes_root: Path) -> Dict[str, Any]:
    snapshot_path = indexes_root / 'librarian_dataset_manifest.json'
    catalog_path = indexes_root / 'librarian_dataset_catalog.jsonl'
    snapshot = _read_json_dict(snapshot_path)
    entries = snapshot.get('entries', []) if isinstance(snapshot.get('entries', []), list) else []

    missing_dataset_manifest_entries: List[Dict[str, Any]] = []
    missing_report_manifest_refs: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resolver = dict(entry.get('resolver', {}) or {}) if isinstance(entry.get('resolver', {}), dict) else {}
        dataset_manifest_ref = _normalize_text(resolver.get('dataset_manifest_path', ''))
        report_manifest_ref = _normalize_text(entry.get('report_manifest_ref', ''))
        dataset_manifest_path = PROJECT_ROOT / Path(dataset_manifest_ref) if dataset_manifest_ref and not Path(dataset_manifest_ref).is_absolute() else Path(dataset_manifest_ref) if dataset_manifest_ref else None
        report_manifest_path = PROJECT_ROOT / Path(report_manifest_ref) if report_manifest_ref and not Path(report_manifest_ref).is_absolute() else Path(report_manifest_ref) if report_manifest_ref else None
        if dataset_manifest_path is None or not dataset_manifest_path.exists():
            missing_dataset_manifest_entries.append(
                {
                    'entry_id': _normalize_text(entry.get('entry_id', '')),
                    'dataset_manifest_path': dataset_manifest_ref,
                }
            )
        if report_manifest_ref and (report_manifest_path is None or not report_manifest_path.exists()):
            missing_report_manifest_refs.append(
                {
                    'entry_id': _normalize_text(entry.get('entry_id', '')),
                    'report_manifest_ref': report_manifest_ref,
                }
            )

    catalog_entries = 0
    if catalog_path.exists():
        for line in iter_jsonl(catalog_path):
            if isinstance(line.obj, dict):
                catalog_entries += 1

    return {
        'snapshot_path': str(snapshot_path),
        'catalog_path': str(catalog_path),
        'snapshot_entry_count': int(len([entry for entry in entries if isinstance(entry, dict)])),
        'catalog_entry_count': int(catalog_entries),
        'missing_dataset_manifest_entries': missing_dataset_manifest_entries,
        'missing_report_manifest_refs': missing_report_manifest_refs,
        'has_orphaned_manifest_refs': bool(missing_dataset_manifest_entries or missing_report_manifest_refs),
    }


def _post_reset_verification(indexes_root: Path, runs_root: Path, reports_root: Path, refresh_payload: Dict[str, Any]) -> Dict[str, Any]:
    aggregate_report_path = reports_root / 'aggregates' / 'AGGREGATE_REPORT.md'
    ledger_report_path = reports_root / 'aggregates' / 'PUBLIC_RUN_LEDGER.md'
    latest_report_path = reports_root / 'aggregates' / 'LATEST_COLLECTIONS.md'

    aggregate_text = aggregate_report_path.read_text(encoding='utf-8') if aggregate_report_path.exists() else ''
    ledger_text = ledger_report_path.read_text(encoding='utf-8') if ledger_report_path.exists() else ''
    latest_text = latest_report_path.read_text(encoding='utf-8') if latest_report_path.exists() else ''

    collections_dir = reports_root / 'collections'
    return {
        'ds_run_index_exists': (indexes_root / 'ds_run_index.jsonl').exists(),
        'ds_latest_exists': (indexes_root / 'ds_latest.json').exists(),
        'runs_dir_exists': runs_root.exists(),
        'runs_dir_empty': not any(runs_root.iterdir()) if runs_root.exists() else True,
        'collections_dir_exists': collections_dir.exists(),
        'collections_dir_empty': not any(collections_dir.iterdir()) if collections_dir.exists() else True,
        'published_run_count': int(refresh_payload.get('published_run_count', 0) or 0),
        'aggregate_report_zero_marker': '- Published packets: 0' in aggregate_text,
        'public_run_ledger_zero_marker': '- Published runs: 0' in ledger_text,
        'latest_collections_zero_marker': '- Published runs: 0' in latest_text,
    }


def main() -> int:
    stamp = _utc_stamp()
    archive_root = (
        REPO_ROOT
        / 'quarantine_legacy_archive'
        / 'calamum-moltbook-observer'
        / f'ds_t0_reset_{stamp}'
    )
    archive_root.mkdir(parents=True, exist_ok=True)

    indexes_root = PROJECT_ROOT / 'local_untracked' / 'analysis' / 'indexes'
    runs_root = PROJECT_ROOT / 'local_untracked' / 'analysis' / 'runs'
    reports_root = PROJECT_ROOT / 'docs' / 'reports'

    librarian_audit = _librarian_manifest_audit(indexes_root)
    ledger_summary = _ds_ledger_summary(indexes_root / 'ds_run_index.jsonl')
    runs_summary = _runs_summary(runs_root)

    archived_items = [
        _move_path(runs_root, archive_root / 'analysis' / 'runs'),
        _move_path(indexes_root / 'ds_run_index.jsonl', archive_root / 'analysis' / 'indexes' / 'ds_run_index.jsonl'),
        _move_path(indexes_root / 'ds_latest.json', archive_root / 'analysis' / 'indexes' / 'ds_latest.json'),
        _move_path(indexes_root / 'ds_publication', archive_root / 'analysis' / 'indexes' / 'ds_publication'),
        _move_path(reports_root, archive_root / 'docs' / 'reports'),
    ]

    runs_root.mkdir(parents=True, exist_ok=True)
    indexes_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)

    refresh_payload = refresh_tracked_ds_publication(project_anchor=PROJECT_ROOT / 'src' / 'observerctl.py')
    (reports_root / 'collections').mkdir(parents=True, exist_ok=True)
    verification = _post_reset_verification(indexes_root, runs_root, reports_root, refresh_payload)

    manifest = {
        'action': 'archive-and-reset-ds-publication-records',
        'reason': 't-zero purge of collection and data-processing records before fresh canonical reruns',
        'project_root': str(PROJECT_ROOT),
        'archive_root': str(archive_root),
        'reset_at_utc': datetime.now(timezone.utc).isoformat(),
        'pre_reset': {
            'ds_ledger': ledger_summary,
            'runs': runs_summary,
            'librarian_manifest_audit': librarian_audit,
        },
        'archived_items': archived_items,
        'tracked_publication_refresh': refresh_payload,
        'post_reset_verification': verification,
    }
    (archive_root / 'reset_manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
